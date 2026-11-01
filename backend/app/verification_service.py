import asyncio
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.catalog_schemas import MatchRequest
from app.catalog_service import CatalogService, normalized_name, parse_title, work_match_keys
from app.library_models import UserItem
from app.recommendation_models import BlockedMovie, MovieVerification, RecommendationBatch, RecommendationCandidate
from app.recommendation_rules import AI_NOMINATION, constraint_mismatch, is_excluded, open_task, person_ids, task_row
from app.recommendation_schemas import (MovieProposal, VerificationConstraints, VerificationResult,
                                        VerifiedMovie, VerifyMoviesInput)
from app.recommendation_service import RecommendationService


class MovieVerificationService:
    def __init__(self, engine: Engine, catalog: CatalogService):
        self.engine, self.catalog = engine, catalog
        self.recommendations = RecommendationService(engine, catalog)

    async def register(self, task_id: str, constraints: VerificationConstraints | None) -> dict:
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            if task.strategy != AI_NOMINATION:
                raise HTTPException(409, "请重新提交原始需求，创建支持 Agent 提名的新任务。")
            if task.criteria is not None:
                if constraints is not None and task.criteria != constraints.model_dump():
                    raise HTTPException(409, "硬条件已经登记，后续核实不能改写。")
                return task.filters
            if constraints is None:
                raise HTTPException(422, "首次核实请提交 constraints；没有硬条件时提交空对象。")

        genre_ids = {}
        if constraints.required_genres or constraints.excluded_genres:
            data = await self.catalog.tmdb.get("/genre/movie/list")
            genre_ids = {g["name"]: g["id"] for g in data["genres"]}

        def genres(names: list[str]) -> list[int]:
            unknown = [name for name in names if name not in genre_ids]
            if unknown:
                raise HTTPException(422, "请使用 TMDB 类型名称：" + "、".join(unknown))
            return sorted({genre_ids[name] for name in names})

        filters = {
            "director_ids": await person_ids(self.catalog.tmdb, constraints.directors, "导演"),
            "actor_ids": await person_ids(self.catalog.tmdb, constraints.actors, "演员"),
            "year_min": constraints.year_from, "year_max": constraints.year_to,
            "runtime_min": constraints.runtime_min, "runtime_max": constraints.runtime_max,
            "countries": constraints.countries, "languages": constraints.languages,
            "required_genre_ids": genres(constraints.required_genres),
            "excluded_genre_ids": genres(constraints.excluded_genres),
        }
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            if task.criteria is not None and task.criteria != constraints.model_dump():
                raise HTTPException(409, "硬条件已经登记，后续核实不能改写。")
            task.criteria, task.filters = constraints.model_dump(), filters
            session.commit()
        return filters

    async def match(self, proposal: MovieProposal, actor_check: bool) -> VerifiedMovie:
        if parse_title(proposal.title)[2] is not None:
            return VerifiedMovie(proposal=proposal, status="not_found", reason="此工具仅核实电影，不核实剧集各季。")
        matched = await self.catalog.match(MatchRequest(**proposal.model_dump(), media_type="movie"))
        detail = matched.item
        if matched.status == "missing_data" and len(matched.candidates) == 1:
            detail = await self.catalog.detail(matched.candidates[0])
        if detail is None:
            return VerifiedMovie(proposal=proposal,
                                 status="not_found" if matched.status == "not_found" else "ambiguous",
                                 reason=matched.reason, candidates=matched.candidates[:5])
        if detail.media_type != "movie":
            return VerifiedMovie(proposal=proposal, status="not_found", reason="匹配结果不是电影。")
        if actor_check:
            with Session(self.engine) as session:
                needs_cast = "cast_ids" not in session.get(CatalogItem, detail.catalog_id).details
            if needs_cast:
                detail = await self.catalog.detail(detail, refresh=True)
        return VerifiedMovie(proposal=proposal, status="eligible", reason="已核实为提名电影。",
                             movie_id=detail.catalog_id, movie=detail)

    @staticmethod
    def exclusion_groups(session: Session, shown_ids: list[int]) -> list[tuple[str, tuple[set[int], set[str]]]]:
        queries = [
            ("watched", select(CatalogItem).join(UserItem).where(UserItem.status == "watched")),
            ("blocked", select(CatalogItem).join(BlockedMovie)),
            ("already_shown", select(CatalogItem).where(CatalogItem.id.in_(shown_ids))),
        ]
        groups = []
        for status, query in queries:
            works = list(session.scalars(query))
            ids = {work.id for work in works}
            keys = {key for work in works for key in (work.details.get("match_keys") or work_match_keys(work.details))}
            groups.append((status, (ids, keys)))
        return groups

    async def verify(self, body: VerifyMoviesInput) -> VerificationResult:
        filters = await self.register(body.task_id, body.constraints)
        semaphore = asyncio.Semaphore(4)

        async def match(proposal: MovieProposal) -> VerifiedMovie:
            async with semaphore:
                return await self.match(proposal, bool(filters["actor_ids"]))

        # 相同提名只查询一次；之后按原输入顺序判断同批重复。
        proposal_keys = [(normalized_name(p.original_title or p.title), p.year) for p in body.movies]
        unique = dict(zip(proposal_keys, body.movies))
        matched = await asyncio.gather(*[match(proposal) for proposal in unique.values()])
        results = dict(zip(unique, matched))
        items, seen_ids, seen_keys = [], set(), set()
        with Session(self.engine) as session:
            task = open_task(session, body.task_id)
            batch = session.get(RecommendationBatch, task.batch_id)
            groups = self.exclusion_groups(session, batch.shown_ids)
            for proposal, key in zip(body.movies, proposal_keys):
                item = results[key].model_copy(update={"proposal": proposal})
                if item.movie_id is not None:
                    work = session.get(CatalogItem, item.movie_id)
                    keys = set(work.details.get("match_keys") or work_match_keys(work.details))
                    status = next((status for status, excluded in groups if is_excluded(work, excluded)), None)
                    mismatch = constraint_mismatch(work, filters)
                    if status:
                        item.status, item.reason = status, {"watched": "已在看过片库。", "blocked": "已被屏蔽。", "already_shown": "本批次已展示。"}[status]
                    elif mismatch:
                        item.status, item.reason = "condition_mismatch", mismatch
                    elif work.id in seen_ids or keys.intersection(seen_keys):
                        item.status, item.reason = "duplicate", "本批提名对应同一影片，只保留一次。"
                    else:
                        seen_ids.add(work.id)
                        seen_keys.update(keys)
                        if session.get(RecommendationCandidate, (task.id, work.id)) is None:
                            session.add(RecommendationCandidate(task_id=task.id, catalog_id=work.id, relaxation_stage=0))
                session.add(MovieVerification(task_id=task.id, proposal=proposal.model_dump(), status=item.status,
                                              catalog_id=item.movie_id, reason=item.reason, created_at=int(time.time())))
                items.append(item)
            session.commit()
            eligible_ids = [c["movie_id"] for c in self.recommendations.candidates(session, task)]
            constraints = VerificationConstraints.model_validate(task.criteria)
        return VerificationResult(task_id=body.task_id, constraints=constraints, items=items, eligible_movie_ids=eligible_ids)

    def history(self, task_id: str) -> dict:
        with Session(self.engine) as session:
            task_row(session, task_id)
            rows = session.scalars(select(MovieVerification).where(MovieVerification.task_id == task_id).order_by(MovieVerification.id))
            return {"items": [dict(id=row.id, proposal=row.proposal, status=row.status, movie_id=row.catalog_id,
                                   reason=row.reason, created_at=row.created_at) for row in rows]}
