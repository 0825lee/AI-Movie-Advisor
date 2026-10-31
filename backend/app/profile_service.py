import asyncio
import json
import logging
import time

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.dify_client import DifyClient, DifyWorkflowError
from app.library_models import UserItem
from app.profile_models import ProfileJob, ProfileVersion
from app.profile_record_models import ProfileRecord
from app.profile_schemas import ProfileJobState, ProfileState, TasteProfile

logger = logging.getLogger(__name__)
PROFILE_THRESHOLD = 50


class ProfileRunner:
    def __init__(self, engine: Engine, client: DifyClient, settings: Settings):
        self.engine, self.client, self.settings = engine, client, settings
        self.task: asyncio.Task | None = None
        self.active_job_id: int | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def state(self) -> ProfileState:
        with Session(self.engine) as session:
            latest = session.scalar(select(ProfileVersion).order_by(ProfileVersion.version.desc()).limit(1))
            ids = set(session.scalars(select(UserItem.id).where(UserItem.status == "watched")))
            covered = set(latest.covered_item_ids) if latest else set()
            pending = len(ids - covered)
            job = session.scalar(select(ProfileJob).order_by(ProfileJob.id.desc()).limit(1))
            if job and job.status == "running" and self.active_job_id != job.id:
                job.status, job.error = "failed", "后端已重启，本次画像未完成，请重试。"
                job.updated_at = int(time.time())
                session.commit()
            return ProfileState(
                profile=TasteProfile.model_validate(latest.data) if latest else None,
                created_at=latest.created_at if latest else None,
                watched_count=len(ids), covered_count=len(covered), pending_count=pending,
                remaining=max(0, PROFILE_THRESHOLD - pending), configured=bool(self.settings.dify_profile_api_key),
                generating=self.running,
                job=ProfileJobState(id=job.id, status=job.status, stage=job.stage, version=job.version,
                                    batch_count=len(job.batch_item_ids), error=job.error, created_at=job.created_at) if job else None,
            )

    def start(self) -> ProfileState:
        if self.running:
            raise HTTPException(409, "画像正在生成，请等待本次完成。")
        if self.settings.dify_profile_api_key is None:
            raise HTTPException(503, "请配置并保存 DIFY_PROFILE_API_KEY 后重启后端。")
        with Session(self.engine) as session:
            latest = session.scalar(select(ProfileVersion).order_by(ProfileVersion.version.desc()).limit(1))
            covered = set(latest.covered_item_ids) if latest else set()
            rows = session.execute(select(UserItem.id, ProfileRecord.payload).join(
                ProfileRecord, ProfileRecord.user_item_id == UserItem.id,
            ).where(UserItem.status == "watched").order_by(UserItem.id)).all()
            batch = [(item_id, payload) for item_id, payload in rows if item_id not in covered]
            if len(batch) < PROFILE_THRESHOLD:
                raise HTTPException(409, f"再记录 {PROFILE_THRESHOLD - len(batch)} 部看过的影片后生成画像。")
            # 同一应用的 API 会话由后端维护，不复用 Dify 调试窗口的会话。
            conversation_id = session.scalar(select(ProfileJob.conversation_id).where(
                ProfileJob.conversation_id.is_not(None),
            ).order_by(ProfileJob.id.desc()).limit(1))
            previous = latest.data if latest else None
            now = int(time.time())
            job = ProfileJob(status="running", stage="uploading", version=latest.version + 1 if latest else 1,
                             batch_item_ids=[item_id for item_id, _ in batch],
                             covered_item_ids=sorted(covered | {item_id for item_id, _ in batch}),
                             conversation_id=conversation_id, created_at=now, updated_at=now)
            session.add(job)
            session.commit()
            job_id = job.id
        self.active_job_id = job_id
        self.task = asyncio.create_task(self.run(job_id, [payload for _, payload in batch], previous))
        return self.state()

    def maybe_start(self) -> None:
        if not self.settings.dify_profile_api_key or self.running:
            return
        state = self.state()
        if state.remaining == 0 and not (state.job and state.job.status in {"failed", "cancelled"}):
            self.start()

    def finish_job(self, job_id: int, status: str, error: str | None = None) -> None:
        with Session(self.engine) as session:
            job = session.get(ProfileJob, job_id)
            job.status, job.error, job.updated_at = status, error, int(time.time())
            session.commit()

    async def run(self, job_id: int, records: list[dict], previous: dict | None) -> None:
        try:
            key = self.settings.dify_profile_api_key.get_secret_value()
            with Session(self.engine) as session:
                job = session.get(ProfileJob, job_id)
                version, covered_count, conversation_id = job.version, len(job.covered_item_ids), job.conversation_id
            query = (
                f"请{'更新' if previous else '首次构建'}观影画像。本批记录数：{len(records)}。"
                f"目标 version：{version}；目标 covered_count：{covered_count}。"
                + ("附件是尚未纳入上一版的新增看过记录，请返回完整新画像。" if previous else "附件是全部看过记录，recent_changes 使用空数组。")
            )
            if previous:
                query += "\n本次任务明确提供的上一版完整画像（以此版本为更新基准）：\n" + json.dumps(previous, ensure_ascii=False)
            file_id = await self.client.upload_text(key, json.dumps({"records": records}, ensure_ascii=False, indent=2))
            trace = {"conversation_id": conversation_id, "message_id": None, "task_id": None}

            def track(event: dict) -> None:
                changed = {name: event[name] for name in trace if event.get(name) and event[name] != trace[name]}
                if changed:
                    trace.update(changed)
                    with Session(self.engine) as session:
                        row = session.get(ProfileJob, job_id)
                        for name, value in changed.items():
                            setattr(row, name, value)
                        session.commit()

            with Session(self.engine) as session:
                session.get(ProfileJob, job_id).stage = "generating"
                session.commit()
            result = await self.client.chat(key, query, file_id, conversation_id, on_event=track)
            profile = TasteProfile.model_validate_json(result.answer)
            profile.version, profile.covered_count = version, covered_count
            with Session(self.engine) as session:
                job = session.get(ProfileJob, job_id)
                session.add(ProfileVersion(version=version, data=profile.model_dump(), covered_item_ids=job.covered_item_ids,
                                           conversation_id=result.conversation_id, message_id=result.message_id, created_at=int(time.time())))
                job.status, job.stage, job.updated_at = "succeeded", "done", int(time.time())
                session.commit()
        except asyncio.CancelledError:
            self.finish_job(job_id, "cancelled", "本次画像生成已取消，原画像保持不变。")
            raise
        except (httpx.HTTPError, DifyWorkflowError, ValidationError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                error = f"Dify 返回 HTTP {exc.response.status_code}，请检查已发布应用的 Key 和配置。"
            elif isinstance(exc, ValidationError):
                error = "Dify 回复未符合画像 JSON 格式，请检查 Chatflow 的最终回答。"
            else:
                error = str(exc) or "无法连接 Dify，请检查服务。"
            self.finish_job(job_id, "failed", error)
        except Exception:
            logger.exception("Profile job %s failed", job_id)
            self.finish_job(job_id, "failed", "画像生成中断，请查看后端日志后重试。")
        finally:
            self.active_job_id = None

    async def cancel(self) -> None:
        if not self.running:
            return
        with Session(self.engine) as session:
            task_id = session.get(ProfileJob, self.active_job_id).task_id
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        if task_id and self.settings.dify_profile_api_key:
            try:
                await self.client.stop_chat(self.settings.dify_profile_api_key.get_secret_value(), task_id)
            except httpx.HTTPError:
                logger.warning("Could not stop remote profile task %s", task_id)
