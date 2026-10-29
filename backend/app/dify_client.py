import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel


class DifyWorkflowError(RuntimeError):
    pass


class WorkflowResult(BaseModel):
    task_id: str | None
    workflow_run_id: str
    outputs: dict[str, Any]


async def _read_events(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    data: list[str] = []
    async for line in lines:
        if not line:
            if data:
                yield _decode_event(data)
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield _decode_event(data)


def _decode_event(data: list[str]) -> dict[str, Any]:
    try:
        return json.loads("\n".join(data))
    except json.JSONDecodeError as exc:
        raise DifyWorkflowError("Dify 返回了无法解析的 SSE 事件。") from exc


class DifyClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str):
        self.http = http
        self.base_url = base_url.rstrip("/")

    async def run_workflow(
        self,
        api_key: str,
        inputs: dict[str, Any],
        user: str = "local-user",
    ) -> WorkflowResult:
        task_id = None
        async with self.http.stream(
            "POST",
            self.base_url + "/workflows/run",
            headers={
                "Authorization": "Bearer " + api_key,
                "Accept": "text/event-stream",
            },
            json={"inputs": inputs, "response_mode": "streaming", "user": user},
        ) as response:
            response.raise_for_status()
            async for event in _read_events(response.aiter_lines()):
                task_id = event.get("task_id", task_id)
                if event["event"] == "error":
                    raise DifyWorkflowError(event.get("message", "Dify 执行失败。"))
                if event["event"] == "workflow_finished":
                    data = event["data"]
                    if data["status"] != "succeeded":
                        raise DifyWorkflowError(data.get("error") or "Dify 工作流执行失败。")
                    return WorkflowResult(
                        task_id=task_id,
                        workflow_run_id=event.get("workflow_run_id") or data["id"],
                        outputs=data["outputs"],
                    )
        raise DifyWorkflowError("Dify 事件流结束，但没有收到工作流完成事件。")
