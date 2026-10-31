import time

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.catalog_schemas import CatalogRef, SearchType
from app.catalog_service import CatalogService, name_year_key
from app.library_models import UserItem
from app.import_models import ImportJob
from app.library_schemas import LibraryCounts, LibraryEntry, LibraryPage, LibraryState, LibraryStatus, LibraryWork, ManualAdd


def entry(item: UserItem, work: CatalogItem) -> LibraryEntry:
    return LibraryEntry(
        id=item.id, status=item.status, rating=item.rating,
        score=item.rating * 2 if item.rating is not None else None,
        marked_at=item.marked_at, source=item.source, catalog=LibraryWork(
            **work.details, catalog_id=work.id,
            source_url=work.details.get("douban_url") or work.details.get("tmdb_url"),
            source_name="豆瓣" if work.tmdb_id is None else "TMDB",
        ),
    )


def find_item(session: Session, work: CatalogItem) -> UserItem | None:
    conditions = [UserItem.catalog_item_id == work.id]
    if work.match_key is not None:
        keys = [work.match_key]
        if work.details.get("single_season"):
            keys.append(name_year_key(work.original_title, work.title, work.year, work.season_number))
        conditions.append(CatalogItem.match_key.in_(keys))
    return session.scalar(select(UserItem).join(CatalogItem).where(or_(*conditions)).order_by(
        (UserItem.status == "watched").desc(), UserItem.id,
    ).limit(1))


def save_item(
    session: Session, catalog_item_id: int, status: str, rating: int | None,
    marked_at: int | None, source: str,
) -> tuple[UserItem, str]:
    now = int(time.time())
    item = find_item(session, session.get(CatalogItem, catalog_item_id))
    outcome = "duplicate"
    if item is None:
        item = UserItem(
            catalog_item_id=catalog_item_id, status=status, rating=rating,
            marked_at=marked_at, source=source, created_at=now, updated_at=now,
        )
        session.add(item)
        outcome = "added"
    elif item.status == "wish" and status == "watched":
        item.status = status
        item.rating = rating
        item.marked_at = marked_at
        item.updated_at = now
        item.source = source
        outcome = "upgraded"
    return item, outcome


class LibraryService:
    def __init__(self, engine: Engine, catalog: CatalogService):
        self.engine = engine
        self.catalog = catalog

    async def state(self, ref: CatalogRef) -> LibraryState:
        detail = await self.catalog.detail(ref)
        with Session(self.engine) as session:
            item = find_item(session, session.get(CatalogItem, detail.catalog_id))
            if item is None:
                return LibraryState()
            return LibraryState(
                item_id=item.id, status=item.status, rating=item.rating,
                score=item.rating * 2 if item.rating is not None else None,
            )

    def clear(self) -> int:
        with Session(self.engine) as session:
            result = session.execute(delete(UserItem))
            session.execute(update(ImportJob).where(ImportJob.status.in_(["running", "paused"])).values(
                status="cancelled", message="片库已清空，请重新选择文件导入。", updated_at=int(time.time()),
            ))
            session.commit()
            return result.rowcount

    def list(self, status: LibraryStatus, media_type: SearchType, query: str, page: int) -> LibraryPage:
        with Session(self.engine) as session:
            counts = dict(session.execute(select(UserItem.status, func.count()).group_by(UserItem.status)).all())
            conditions = [UserItem.status == status]
            if media_type == "movie":
                conditions.append(CatalogItem.media_type == "movie")
            elif media_type == "tv":
                conditions.append(CatalogItem.media_type.in_(["tv", "season"]))
            if query.strip():
                conditions.append(or_(
                    CatalogItem.title.icontains(query.strip(), autoescape=True),
                    CatalogItem.original_title.icontains(query.strip(), autoescape=True),
                ))
            total = session.scalar(select(func.count()).select_from(UserItem).join(CatalogItem).where(*conditions))
            rows = session.execute(select(UserItem, CatalogItem).join(CatalogItem).where(*conditions).order_by(
                func.coalesce(UserItem.marked_at, UserItem.created_at).desc(), UserItem.id.desc(),
            ).offset((page - 1) * 12).limit(12)).all()
            return LibraryPage(
                items=[entry(item, work) for item, work in rows],
                counts=LibraryCounts(**counts), total=total, page=page,
            )

    async def add(self, body: ManualAdd) -> LibraryEntry:
        # 先解析作品，网络请求不放在片库写事务中。
        detail = await self.catalog.detail(body)
        with Session(self.engine) as session:
            work = session.get(CatalogItem, detail.catalog_id)
            item, _ = save_item(session, work.id, body.status, body.rating, int(time.time()), "manual")
            session.commit()
            return entry(item, session.get(CatalogItem, item.catalog_item_id))

    def mark_watched(self, item_id: int, rating: int | None) -> LibraryEntry:
        with Session(self.engine) as session:
            item = session.get(UserItem, item_id)
            if item is None:
                raise HTTPException(404, "片库中没有这条记录。")
            if item.status == "wish":
                item.status = "watched"
                item.rating = rating
                item.marked_at = int(time.time())
                item.updated_at = item.marked_at
            session.commit()
            return entry(item, session.get(CatalogItem, item.catalog_item_id))
