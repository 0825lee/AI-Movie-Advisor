from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.catalog_service import normalized_name, work_match_keys
from app.library_models import UserItem
from app.recommendation_models import BlockedMovie, MovieVerification, RecommendationBatch, RecommendationCandidate, RecommendationTask

AI_NOMINATION = "ai_nomination"


def clear_personalized_history(session: Session) -> None:
    task_ids = select(RecommendationTask.id).where(RecommendationTask.mode == "personalized")
    batch_ids = list(session.scalars(select(RecommendationTask.batch_id).where(RecommendationTask.mode == "personalized")))
    session.execute(delete(MovieVerification).where(MovieVerification.task_id.in_(task_ids)))
    session.execute(delete(RecommendationCandidate).where(RecommendationCandidate.task_id.in_(task_ids)))
    session.execute(delete(RecommendationTask).where(RecommendationTask.mode == "personalized"))
    session.execute(delete(RecommendationBatch).where(RecommendationBatch.id.in_(batch_ids),
        ~select(RecommendationTask.id).where(RecommendationTask.batch_id == RecommendationBatch.id).exists()))


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


async def person_ids(tmdb, names: list[str], role: str) -> list[int]:
    result = []
    for name in names:
        response = await tmdb.get("/search/person", query=name, include_adult="false")
        people = response["results"]
        exact = [p for p in people if normalized_name(name) in {
            normalized_name(p["name"]), normalized_name(p.get("original_name") or ""),
        }]
        matches = exact or people
        if len(matches) != 1:
            raise HTTPException(422, f"未能唯一确定{role}“{name}”，请补充其完整姓名或原文姓名。")
        result.append(matches[0]["id"])
    return sorted(set(result))


def constraint_mismatch(work: CatalogItem, filters: dict) -> str | None:
    data = work.details
    if filters["director_ids"] and not set(filters["director_ids"]).intersection(p["id"] for p in data["directors"]):
        return "导演署名不符合指定条件。"
    if filters["actor_ids"] and not set(filters["actor_ids"]).intersection(data.get("cast_ids", [])):
        return "完整演员表不符合指定演员条件。"
    for field, value in [("year", data["year"]), ("runtime", data["runtime"])]:
        for bound, comparison in [("min", lambda x, y: x < y), ("max", lambda x, y: x > y)]:
            expected = filters[f"{field}_{bound}"]
            if expected is not None:
                if value is None or value <= 0:
                    return "缺少核实年份或时长条件所需的资料。"
                if comparison(value, expected):
                    return "年份或时长不符合指定条件。"
    if filters["countries"] and not set(filters["countries"]).intersection(c["iso_3166_1"] for c in data["countries"]):
        return "制作国家／地区不符合指定条件。"
    if filters["languages"] and data["original_language"] not in filters["languages"]:
        return "原语言不符合指定条件。"
    genres = {genre["id"] for genre in data["genres"]}
    if filters["required_genre_ids"] and not genres.intersection(filters["required_genre_ids"]):
        return "类型不符合指定条件。"
    if genres.intersection(filters["excluded_genre_ids"]):
        return "影片包含已排除的类型。"
    return None
