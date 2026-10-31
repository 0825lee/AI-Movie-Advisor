import asyncio
import logging
import time

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.catalog_service import name_year_key
from app.import_models import ImportJob, ImportRow
from app.import_parser import IMPORT_FIELDS, parse_record
from app.import_schemas import ImportCounts, ImportRequest, ImportRowResult, ImportRowsPage, ImportSummary
from app.library_models import UserItem
from app.library_service import save_item

logger = logging.getLogger(__name__)


class ImportRunner:
    """本地解析并逐条提交；继续时只读取 pending 行。"""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.task: asyncio.Task | None = None
        self.active_job_id: int | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def ensure_idle(self) -> None:
        if self.running:
            raise HTTPException(409, "正在导入，请先暂停导入再操作。")

    def create(self, body: ImportRequest) -> ImportSummary:
        self.ensure_idle()
        records = body.data.get("records")
        if not isinstance(records, list):
            raise HTTPException(400, "JSON 中需要包含 records 数组。")
        now = int(time.time())
        with Session(self.engine) as session:
            if session.scalar(select(func.count()).select_from(UserItem)):
                raise HTTPException(409, "请先清空片库，再开始导入。")
            session.execute(update(ImportJob).where(ImportJob.status.in_(["running", "paused"])).values(
                status="cancelled", message="已创建新的导入任务。", updated_at=now,
            ))
            job = ImportJob(filename=body.filename, status="running", total=len(records), created_at=now, updated_at=now)
            session.add(job)
            session.flush()
            for number, record in enumerate(records, 1):
                payload = {key: record[key] for key in IMPORT_FIELDS if key in record} if isinstance(record, dict) else {}
                session.add(ImportRow(
                    job_id=job.id, row_number=number, title=payload.get("title") or f"第 {number} 条记录",
                    payload=payload, outcome="pending",
                ))
            session.commit()
            job_id = job.id
        self.start(job_id)
        return self.summary(job_id)

    def start(self, job_id: int) -> None:
        self.active_job_id = job_id
        self.task = asyncio.create_task(self.run(job_id))

    def set_status(self, job_id: int, status: str, message: str | None = None) -> None:
        with Session(self.engine) as session:
            session.execute(update(ImportJob).where(ImportJob.id == job_id).values(
                status=status, message=message, updated_at=int(time.time()),
            ))
            session.commit()

    def summary(self, job_id: int) -> ImportSummary:
        with Session(self.engine) as session:
            job = session.get(ImportJob, job_id)
            if job is None:
                raise HTTPException(404, "没有找到这个导入任务。")
            if job.status == "running" and self.active_job_id != job.id:
                job.status = "paused"
                job.message = "后端已重启，点击继续导入即可接着处理。"
                session.commit()
            counts = dict(session.execute(select(ImportRow.outcome, func.count()).where(
                ImportRow.job_id == job.id,
            ).group_by(ImportRow.outcome)).all())
            current = session.scalar(select(ImportRow.title).where(
                ImportRow.job_id == job.id, ImportRow.outcome == "pending",
            ).order_by(ImportRow.row_number).limit(1))
            return ImportSummary(
                id=job.id, filename=job.filename, status=job.status, total=job.total,
                processed=job.total - counts.get("pending", 0), counts=ImportCounts(**counts),
                message=job.message, current_title=current, created_at=job.created_at,
            )

    def jobs(self) -> list[ImportSummary]:
        with Session(self.engine) as session:
            ids = list(session.scalars(select(ImportJob.id).order_by(ImportJob.id.desc()).limit(10)))
        return [self.summary(job_id) for job_id in ids]

    def rows(self, job_id: int, outcome: str, page: int) -> ImportRowsPage:
        self.summary(job_id)
        with Session(self.engine) as session:
            conditions = [ImportRow.job_id == job_id]
            if outcome != "all":
                conditions.append(ImportRow.outcome == outcome)
            total = session.scalar(select(func.count()).select_from(ImportRow).where(*conditions))
            rows = session.execute(select(ImportRow, CatalogItem.title).outerjoin(
                CatalogItem, CatalogItem.id == ImportRow.catalog_item_id,
            ).where(*conditions).order_by(ImportRow.row_number).offset((page - 1) * 20).limit(20)).all()
            return ImportRowsPage(items=[ImportRowResult(
                row_number=row.row_number, title=row.title, outcome=row.outcome,
                message=row.message, matched_title=matched_title,
            ) for row, matched_title in rows], total=total, page=page)

    def resume(self, job_id: int) -> ImportSummary:
        self.ensure_idle()
        job = self.summary(job_id)
        if job.status != "paused":
            raise HTTPException(409, "这个任务已结束，不能继续导入。")
        self.set_status(job_id, "running")
        self.start(job_id)
        return self.summary(job_id)

    async def pause(self, job_id: int) -> ImportSummary:
        job = self.summary(job_id)
        if job.status == "running" and self.active_job_id == job_id:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        return self.summary(job_id)

    async def close(self) -> None:
        if self.running:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    def finish_row(self, row_id: int, outcome: str, message: str) -> None:
        with Session(self.engine) as session:
            row = session.get(ImportRow, row_id)
            row.outcome = outcome
            row.message = message
            session.commit()

    async def process(self, row_id: int) -> None:
        with Session(self.engine) as session:
            payload = session.get(ImportRow, row_id).payload
        try:
            record = parse_record(payload)
        except (KeyError, ValueError) as exc:
            self.finish_row(row_id, "failed", f"记录字段无法解析：{exc}")
            return
        now = int(time.time())
        media_type = "work"
        details = dict(
            **record.metadata, title=record.title, original_title=record.original_title,
            year=record.year, media_type=media_type, tmdb_id=None, season_number=record.season_number,
            douban_id=record.source_id,
            douban_url=record.source_url or f"https://movie.douban.com/subject/{record.source_id}/",
        )
        with Session(self.engine) as session:
            identity = f"douban:{record.source_id}"
            work = session.scalar(select(CatalogItem).where(CatalogItem.identity_key == identity))
            if work is None:
                work = CatalogItem(identity_key=identity, fetched_at=now)
                session.add(work)
            work.media_type, work.tmdb_id = media_type, None
            work.title, work.original_title = record.title, record.original_title
            work.year, work.season_number = record.year, record.season_number
            work.match_key = name_year_key(record.original_title, record.title, record.year, record.season_number)
            work.details, work.fetched_at = details, now
            session.flush()
            item, outcome = save_item(session, work.id, record.status, record.rating, record.marked_at, "douban")
            row = session.get(ImportRow, row_id)
            row.outcome = outcome
            row.message = {"added": "已导入", "duplicate": "记录已存在。", "upgraded": "想看已更新为看过。"}[outcome]
            row.catalog_item_id = item.catalog_item_id
            session.commit()

    async def run(self, job_id: int) -> None:
        try:
            with Session(self.engine) as session:
                row_ids = list(session.scalars(select(ImportRow.id).where(
                    ImportRow.job_id == job_id, ImportRow.outcome == "pending",
                ).order_by(ImportRow.row_number)))
            for row_id in row_ids:
                await self.process(row_id)
                await asyncio.sleep(0)
            self.set_status(job_id, "completed")
        except asyncio.CancelledError:
            self.set_status(job_id, "paused", "导入已暂停，已完成的记录会保留。")
            raise
        except Exception:
            logger.exception("Import job %s interrupted", job_id)
            self.set_status(job_id, "paused", "导入中断，请查看后端日志后继续。")
        finally:
            self.active_job_id = None
