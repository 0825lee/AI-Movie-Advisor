import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from pydantic import BaseModel


class DifyWorkflowError(RuntimeError):
    pass


class WorkflowResult(BaseModel):
    task_id: str | None
    workflow_run_id: str
    outputs: dict[str, Any]


class ChatResult(BaseModel):
    answer: str
    conversation_id: str
    message_id: str | None
    task_id: str | None


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

    async def upload_text(self, api_key: str, text: str, user: str = "local-user") -> str:
        response = await self.http.post(
            self.base_url + "/files/upload", headers={"Authorization": "Bearer " + api_key},
            data={"user": user}, files={"file": ("profile-input.txt", text.encode("utf-8"), "text/plain")},
        )
        response.raise_for_status()
        return response.json()["id"]

    async def stop_chat(self, api_key: str, task_id: str, user: str = "local-user") -> None:
        response = await self.http.post(
            self.base_url + f"/chat-messages/{task_id}/stop",
            headers={"Authorization": "Bearer " + api_key}, json={"user": user},
        )
        response.raise_for_status()

    async def delete_conversation(self, api_key: str, conversation_id: str, user: str = "local-user") -> None:
        response = await self.http.request(
            "DELETE", self.base_url + f"/conversations/{conversation_id}",
            headers={"Authorization": "Bearer " + api_key}, json={"user": user},
        )
        if response.status_code != 404:
            response.raise_for_status()

    async def chat(
        self, api_key: str, query: str, file_id: str, conversation_id: str | None = None,
        user: str = "local-user", on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ChatResult:
        answer, task_id, message_id = "", None, None
        async with self.http.stream(
            "POST", self.base_url + "/chat-messages",
            headers={"Authorization": "Bearer " + api_key, "Accept": "text/event-stream"},
            json={"inputs": {}, "query": query, "user": user, "response_mode": "streaming",
                  "conversation_id": conversation_id or "", "auto_generate_name": False,
                  "files": [{"type": "document", "transfer_method": "local_file", "upload_file_id": file_id}]},
        ) as response:
            response.raise_for_status()
            async for event in _read_events(response.aiter_lines()):
                conversation_id = event.get("conversation_id") or conversation_id
                task_id = event.get("task_id") or task_id
                message_id = event.get("message_id") or message_id
                if on_event:
                    on_event(event)
                kind = event["event"]
                if kind == "error":
                    raise DifyWorkflowError(event.get("message", "Dify 画像生成失败。"))
                if kind == "workflow_finished" and event["data"]["status"] != "succeeded":
                    raise DifyWorkflowError(event["data"].get("error") or "画像 Chatflow 执行失败。")
                if kind == "message":
                    answer += event.get("answer", "")
                elif kind == "message_replace":
                    answer = event["answer"]
                elif kind == "message_end":
                    if not conversation_id:
                        raise DifyWorkflowError("画像回复缺少 conversation_id。")
                    return ChatResult(answer=answer, conversation_id=conversation_id, message_id=message_id, task_id=task_id)
        raise DifyWorkflowError("Dify 回复结束，但没有收到 message_end。")

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
