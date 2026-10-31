from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.library_models import UserItem
from app.profile_record_models import ProfileRecord

PROFILE_FIELDS = ("title", "originalTitle", "info", "rating", "markedAt", "comment")
SHANGHAI = timezone(timedelta(hours=8))


def manual_info(details: dict) -> str:
    if details.get("info"):
        return details["info"]
    parts = [str(details["year"])] if details.get("year") is not None else []
    parts.extend(person["name"] for person in details.get("cast", []))
    parts.extend(country["name"] for country in details.get("countries", []))
    parts.extend(person["name"] for person in details.get("directors", []))
    if details.get("runtime"):
        parts.append(f"{details['runtime']}分钟")
    parts.extend(genre["name"] for genre in details.get("genres", []))
    parts.extend(details.get("languages") or ([details["original_language"]] if details.get("original_language") else []))
    return " / ".join(parts)


def current_payload(item: UserItem, work: CatalogItem) -> dict:
    return dict(
        title=work.title, originalTitle=work.original_title, info=manual_info(work.details),
        rating=item.rating * 2 if item.rating is not None else None,
        markedAt=datetime.fromtimestamp(item.marked_at, SHANGHAI).date().isoformat() if item.marked_at is not None else "",
        comment="",
    )


def sync_profile_record(
    session: Session, item: UserItem, work: CatalogItem, *, raw: dict | None = None,
    comment: str | None = None,
) -> ProfileRecord:
    session.flush()
    record = session.get(ProfileRecord, item.id)
    if raw is not None:
        defaults = current_payload(item, work)
        payload = {key: raw[key] if key in raw else defaults[key] for key in PROFILE_FIELDS}
    else:
        payload = dict(record.payload) if record is not None else current_payload(item, work)
        payload["rating"] = item.rating * 2 if item.rating is not None else None
        payload["markedAt"] = datetime.fromtimestamp(item.marked_at, SHANGHAI).date().isoformat() if item.marked_at is not None else ""
        if comment is not None:
            payload["comment"] = comment
    if record is None:
        record = ProfileRecord(user_item_id=item.id, payload=payload)
        session.add(record)
    else:
        record.payload = payload
    return record


def watched_profile_input(session: Session) -> dict:
    records = session.scalars(select(ProfileRecord).join(UserItem).where(
        UserItem.status == "watched",
    ).order_by(UserItem.id))
    return {"records": [record.payload for record in records]}


def backfill_from_export(session: Session, records: list[dict]) -> int:
    by_id = {str(record["subjectId"]): record for record in records}
    matched = 0
    for item, work in session.execute(select(UserItem, CatalogItem).join(CatalogItem)).all():
        raw = by_id.get(work.details.get("douban_id"))
        if raw is None:
            continue
        existing = session.get(ProfileRecord, item.id)
        comment = (existing.payload.get("comment") or "") if existing else ""
        sync_profile_record(session, item, work, raw=raw)
        # 补齐原始字段，同时保留用户在导入后更新的个人评分、标记日期和评论。
        sync_profile_record(session, item, work, comment=comment or raw.get("comment", ""))
        matched += 1
    return matched
