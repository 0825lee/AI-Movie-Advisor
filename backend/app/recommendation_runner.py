import asyncio
import logging
import time
import json

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import Settings
from app.dify_client import DifyClient, DifyWorkflowError
from app.recommendation_models import RecommendationBatch, RecommendationTask
from app.recommendation_rules import AI_NOMINATION
from app.recommendation_schemas import RecommendationSelection, RecommendationState
from app.recommendation_service import RecommendationService, task_row

logger = logging.getLogger(__name__)


class RecommendationRunner:
    def __init__(self, service: RecommendationService, client: DifyClient, settings: Settings):
        self.service, self.client, self.settings = service, client, settings
        self.tasks: dict[str, asyncio.Task] = {}

    def state(self, task_id: str) -> RecommendationState:
        with Session(self.service.engine) as session:
            task = task_row(session, task_id)
            if task.status == "running" and task_id not in self.tasks:
                task.status, task.error = "failed", "后端已重启，本次推荐未完成，请重试。"
                session.commit()
        return self.service.state(task_id)

    def start(self, task_id: str) -> RecommendationState:
        if not self.settings.movie_internal_token:
            raise HTTPException(503, "请配置 MOVIE_INTERNAL_TOKEN，并在 Dify 工具中填写相同值。")
        with Session(self.service.engine) as session:
            task = task_row(session, task_id)
            key = self.settings.dify_personalized_api_key if task.mode == "personalized" else self.settings.dify_request_api_key
            if not key:
                name = "DIFY_PERSONALIZED_API_KEY" if task.mode == "personalized" else "DIFY_REQUEST_API_KEY"
                raise HTTPException(503, f"请配置 {name} 并发布对应的推荐 Workflow。")
            if task.strategy != AI_NOMINATION:
                raise HTTPException(409, "旧任务采用旧检索策略，请重新提交原始需求创建新任务。")
            if task.status not in {"prepared", "failed"}:
                raise HTTPException(409, "推荐正在执行或已经完成。")
            task.status, task.error, task.updated_at = "running", None, int(time.time())
            session.commit()
        self.tasks[task_id] = asyncio.create_task(self.run(task_id))
        return self.service.state(task_id)

    def fail(self, task_id: str, error: str) -> None:
        with Session(self.service.engine) as session:
            task = task_row(session, task_id)
            task.status, task.error, task.updated_at = "failed", error, int(time.time())
            session.commit()

    async def run(self, task_id: str) -> None:
        try:
            with Session(self.service.engine) as session:
                task = task_row(session, task_id)
                batch = session.get(RecommendationBatch, task.batch_id)
                mode, snapshot = task.mode, task.profile_snapshot
                inputs = {"task_id": task_id, "target_count": task.target_count}
                if mode == "request":
                    inputs["request_text"] = batch.request_text
            key = self.settings.dify_personalized_api_key if mode == "personalized" else self.settings.dify_request_api_key
            if mode == "personalized":
                file_id = await self.client.upload_text(key.get_secret_value(), json.dumps(snapshot, ensure_ascii=False, indent=2))
                inputs["profile_files"] = [{"type": "document", "transfer_method": "local_file", "upload_file_id": file_id}]
            result = await self.client.run_workflow(key.get_secret_value(), inputs)
            selection = RecommendationSelection.model_validate(result.outputs["result"])
            self.service.complete(task_id, selection, result.workflow_run_id)
        except asyncio.CancelledError:
            self.fail(task_id, "后端已停止，本次推荐未完成，请重试。")
            raise
        except HTTPException as exc:
            self.fail(task_id, str(exc.detail))
        except httpx.HTTPStatusError as exc:
            self.fail(task_id, f"Dify 返回 HTTP {exc.response.status_code}，请检查应用 Key 和工作流配置。")
        except (ValidationError, KeyError):
            self.fail(task_id, "Dify 输出应为 result 对象，包含 movie_ids 和逐部对应的 reasons 数组。")
        except (httpx.HTTPError, DifyWorkflowError) as exc:
            self.fail(task_id, str(exc) or "无法连接 Dify，请稍后重试。")
        except Exception:
            logger.exception("Recommendation task %s failed", task_id)
            self.fail(task_id, "推荐失败，请查看后端日志后重试。")
        finally:
            self.tasks.pop(task_id, None)

    async def close(self) -> None:
        pending = list(self.tasks.values())
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def cancel_personalized(self) -> None:
        with Session(self.service.engine) as session:
            ids = list(session.scalars(select(RecommendationTask.id).where(
                RecommendationTask.mode == "personalized", RecommendationTask.id.in_(list(self.tasks)),
            )))
        pending = [self.tasks[task_id] for task_id in ids]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
