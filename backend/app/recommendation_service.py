import asyncio
import time
from itertools import product
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.catalog_schemas import CatalogRef
from app.catalog_service import CatalogService, serialized, work_match_keys
from app.library_models import UserItem
from app.recommendation_models import BlockedMovie, RecommendationBatch, RecommendationCandidate, RecommendationTask
from app.recommendation_schemas import RecommendationCard, RecommendationSelection, RecommendationState, RequestCriteria

RELAXATIONS = ["完整条件", "放宽年代", "放宽时长", "放宽国家和语言", "放宽正向类型"]


def exclusions(session: Session, shown_ids: list[int] = ()) -> tuple[set[int], set[str]]:
    ids = set(session.scalars(select(UserItem.catalog_item_id).where(UserItem.status == "watched")))
    ids.update(session.scalars(select(BlockedMovie.catalog_id)))
    ids.update(shown_ids)
    keys = set()
    for work in session.scalars(select(CatalogItem).where(CatalogItem.id.in_(ids))):
        keys.update(work.details.get("match_keys") or work_match_keys(work.details))
    return ids, keys


def is_excluded(work: CatalogItem, excluded: tuple[set[int], set[str]]) -> bool:
    ids, keys = excluded
    return work.id in ids or bool(keys.intersection(work.details.get("match_keys") or work_match_keys(work.details)))


def task_row(session: Session, task_id: str) -> RecommendationTask:
    task = session.get(RecommendationTask, task_id)
    if task is None:
        raise HTTPException(404, "推荐任务不存在。")
    return task


def open_task(session: Session, task_id: str) -> RecommendationTask:
    task = task_row(session, task_id)
    if task.status not in {"prepared", "running"}:
        raise HTTPException(409, "推荐任务已结束，请创建新任务或重试。")
    return task


class RecommendationService:
    def __init__(self, engine: Engine, catalog: CatalogService):
        self.engine, self.catalog = engine, catalog

    def create(self, request_text: str) -> str:
        if not request_text.strip():
            raise HTTPException(422, "请输入本次观影需求。")
        now = int(time.time())
        batch_id, task_id = str(uuid4()), str(uuid4())
        with Session(self.engine) as session:
            session.add(RecommendationBatch(id=batch_id, request_text=request_text, shown_ids=[], created_at=now))
            session.flush()
            session.add(RecommendationTask(id=task_id, batch_id=batch_id, status="prepared", target_count=3,
                                           created_at=now, updated_at=now))
            session.commit()
        return task_id

    def state(self, task_id: str) -> RecommendationState:
        with Session(self.engine) as session:
            task = task_row(session, task_id)
            batch = session.get(RecommendationBatch, task.batch_id)
            # 已展示的卡片仍能读取；只有新增看过或屏蔽会使它失效。
            excluded = exclusions(session)
            cards = [RecommendationCard.model_validate(card) for card in task.result or []
                     if not is_excluded(session.get(CatalogItem, card["movie_id"]), excluded)]
            return RecommendationState(task_id=task.id, batch_id=task.batch_id, status=task.status,
                                       request_text=batch.request_text, target_count=task.target_count,
                                       criteria=task.criteria, cards=cards,
                                       needs_refresh=task.status == "succeeded" and len(cards) != task.target_count,
                                       workflow_run_id=task.workflow_run_id, error=task.error, created_at=task.created_at)

    async def register_criteria(self, task_id: str, criteria: RequestCriteria) -> dict:
        payload = criteria.model_dump()
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            if task.criteria is not None:
                if task.criteria != payload:
                    raise HTTPException(409, "本次任务条件已经固定，不能在检索过程中改写。")
                return {"task_id": task_id, "criteria": task.criteria, "filters": task.filters}
        genre_ids = {}
        if criteria.preferred_genres or criteria.excluded_genres:
            genres = await self.catalog.tmdb.get("/genre/movie/list")
            genre_ids = {genre["name"]: genre["id"] for genre in genres["genres"]}

        def resolve(names: list[str]) -> list[int]:
            unknown = [name for name in names if name not in genre_ids]
            if unknown:
                raise HTTPException(422, "请使用 TMDB 类型名称：" + "、".join(unknown))
            return list(dict.fromkeys(genre_ids[name] for name in names))

        filters = {"year_from": criteria.year_from, "year_to": criteria.year_to,
                   "runtime_min": criteria.runtime_min, "runtime_max": criteria.runtime_max,
                   "countries": criteria.countries, "languages": criteria.languages,
                   "genre_ids": resolve(criteria.preferred_genres), "excluded_genre_ids": resolve(criteria.excluded_genres)}
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            if task.criteria is not None and task.criteria != payload:
                raise HTTPException(409, "本次任务条件已经固定。")
            task.criteria, task.filters = payload, filters
            session.commit()
        return {"task_id": task_id, "criteria": payload, "filters": filters}

    def candidates(self, session: Session, task: RecommendationTask) -> list[dict]:
        batch = session.get(RecommendationBatch, task.batch_id)
        excluded = exclusions(session, batch.shown_ids)
        rows = session.execute(select(RecommendationCandidate, CatalogItem).join(
            CatalogItem, CatalogItem.id == RecommendationCandidate.catalog_id,
        ).where(RecommendationCandidate.task_id == task.id).order_by(
            RecommendationCandidate.relaxation_stage, RecommendationCandidate.catalog_id,
        )).all()
        result, keys = [], set()
        for candidate, work in rows:
            movie_keys = set(work.details.get("match_keys") or work_match_keys(work.details))
            excluded_genres = set((task.filters or {}).get("excluded_genre_ids", []))
            if (is_excluded(work, excluded) or movie_keys.intersection(keys)
                    or any(genre["id"] in excluded_genres for genre in work.details["genres"])):
                continue
            keys.update(movie_keys)
            result.append({"movie_id": work.id, "tmdb_id": work.tmdb_id, "title": work.title,
                           "original_title": work.original_title, "year": work.year,
                           "overview": work.details["overview"], "runtime": work.details["runtime"],
                           "genres": work.details["genres"], "countries": work.details["countries"],
                           "relaxation_stage": candidate.relaxation_stage})
        return result

    async def search(self, task_id: str, target_count: int) -> dict:
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            if target_count != task.target_count:
                raise HTTPException(422, "target_count 必须使用本次任务提供的值。")
            if task.criteria is None:
                raise HTTPException(409, "请先登记本次需求条件。")
            filters, criteria = task.filters, task.criteria
            cached = self.candidates(session, task)
            if len(cached) >= target_count:
                return self.search_result(task_id, criteria, cached)

        pool_size = target_count * 4
        visited, tried = set(), set()
        for stage in range(len(RELAXATIONS)):
            params = {"include_adult": "false", "include_video": "false", "sort_by": "popularity.desc"}
            if filters["excluded_genre_ids"]:
                params["without_genres"] = ",".join(map(str, filters["excluded_genre_ids"]))
            if stage < 1:
                if filters["year_from"] is not None:
                    params["primary_release_date.gte"] = f"{filters['year_from']}-01-01"
                if filters["year_to"] is not None:
                    params["primary_release_date.lte"] = f"{filters['year_to']}-12-31"
            if stage < 2:
                for bound in ["min", "max"]:
                    if filters[f"runtime_{bound}"] is not None:
                        params[f"with_runtime.{ 'gte' if bound == 'min' else 'lte' }"] = filters[f"runtime_{bound}"]
            if stage < 4 and filters["genre_ids"]:
                params["with_genres"] = "|".join(map(str, filters["genre_ids"]))
            countries = (filters["countries"] or [None]) if stage < 3 else [None]
            languages = (filters["languages"] or [None]) if stage < 3 else [None]
            variants = []
            for country, language in product(countries, languages):
                variant = dict(params)
                if country:
                    variant["with_origin_country"] = country
                if language:
                    variant["with_original_language"] = language
                signature = tuple(sorted(variant.items()))
                if signature not in tried:
                    tried.add(signature)
                    variants.append(variant)
            for variant in variants:
                for page in range(1, 4):
                    response = await self.catalog.tmdb.get("/discover/movie", page=page, **variant)
                    with Session(self.engine) as session:
                        task = open_task(session, task_id)
                        batch = session.get(RecommendationBatch, task.batch_id)
                        excluded = exclusions(session, batch.shown_ids)
                    rows = []
                    for item in response["results"]:
                        if item["id"] in visited:
                            continue
                        visited.add(item["id"])
                        data = dict(title=item["title"], original_title=item["original_title"],
                                    year=int(item["release_date"][:4]) if item.get("release_date") else None)
                        if not excluded[1].intersection(work_match_keys(data)):
                            rows.append(item)
                    # 小批并发获取详情，复用现有七天缓存，不给每次检索拉取全部候选的详情。
                    for offset in range(0, len(rows), 4):
                        details = await asyncio.gather(*[self.catalog.detail(CatalogRef(media_type="movie", tmdb_id=item["id"]))
                                                         for item in rows[offset:offset + 4]])
                        with Session(self.engine) as session:
                            open_task(session, task_id)
                            for detail in details:
                                if any(g.id in filters["excluded_genre_ids"] for g in detail.genres):
                                    continue
                                if session.get(RecommendationCandidate, (task_id, detail.catalog_id)) is None:
                                    session.add(RecommendationCandidate(task_id=task_id, catalog_id=detail.catalog_id,
                                                                        relaxation_stage=stage))
                            session.commit()
                            current = self.candidates(session, session.get(RecommendationTask, task_id))
                        if len(current) >= pool_size:
                            return self.search_result(task_id, criteria, current)
                    if page >= response["total_pages"]:
                        break
            with Session(self.engine) as session:
                current = self.candidates(session, open_task(session, task_id))
            if len(current) >= target_count:
                return self.search_result(task_id, criteria, current)
        return self.search_result(task_id, criteria, current)

    @staticmethod
    def search_result(task_id: str, criteria: dict, items: list[dict]) -> dict:
        return {"task_id": task_id, "criteria": criteria, "items": items,
                "relaxation_stages": RELAXATIONS,
                "note": "主题、氛围及其他内容禁忌请结合真实简介判断；不可确定时不要选择。"}

    async def detail(self, task_id: str, movie_id: int) -> dict:
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            if session.get(RecommendationCandidate, (task_id, movie_id)) is None:
                raise HTTPException(422, "只能读取本次任务实际检索到的候选。")
            batch = session.get(RecommendationBatch, task.batch_id)
            work = session.get(CatalogItem, movie_id)
            if is_excluded(work, exclusions(session, batch.shown_ids)):
                raise HTTPException(409, "该影片已进入排除范围，请重新检索。")
            tmdb_id = work.tmdb_id
        movie = await self.catalog.detail(CatalogRef(media_type="movie", tmdb_id=tmdb_id))
        return {"movie_id": movie_id, "movie": movie.model_dump()}

    def complete(self, task_id: str, selection: RecommendationSelection, workflow_run_id: str) -> None:
        with Session(self.engine) as session:
            task = open_task(session, task_id)
            ids = selection.movie_ids
            if len(ids) != task.target_count or len(set(ids)) != len(ids) or len(selection.reasons) != len(ids):
                raise HTTPException(422, "推荐必须包含规定数量的不重复候选及逐部推荐理由。")
            candidates = {item["movie_id"] for item in self.candidates(session, task)}
            if not set(ids).issubset(candidates):
                raise HTTPException(422, "推荐包含候选外、已看过、已屏蔽或本批次已展示的影片。")
            cards = []
            for movie_id, reason in zip(ids, selection.reasons):
                if not reason.strip():
                    raise HTTPException(422, "推荐理由不能为空。")
                movie = serialized(session.get(CatalogItem, movie_id))
                cards.append(RecommendationCard(movie_id=movie_id, reason=reason, movie=movie).model_dump())
            task.result, task.status, task.workflow_run_id = cards, "succeeded", workflow_run_id
            task.error, task.updated_at = None, int(time.time())
            batch = session.get(RecommendationBatch, task.batch_id)
            batch.shown_ids = list(dict.fromkeys([*batch.shown_ids, *ids]))
            session.commit()
