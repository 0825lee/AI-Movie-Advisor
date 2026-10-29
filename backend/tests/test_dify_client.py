import asyncio
import json

import httpx
import pytest

from app.dify_client import DifyClient, DifyWorkflowError


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, wire: bytes):
        self.wire = wire

    async def __aiter__(self):
        for index in range(0, len(self.wire), 7):
            yield self.wire[index:index + 7]


def sse(event):
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def execute_wire(wire: str):
    def handler(request):
        assert request.url.path == "/v1/workflows/run"
        assert request.headers["Authorization"] == "Bearer test-app-key"
        body = json.loads(request.content)
        assert body["response_mode"] == "streaming"
        assert body["inputs"] == {"query": "hello"}
        assert body["user"] == "local-user"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=ChunkedStream(wire.encode("utf-8")),
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await DifyClient(http, "http://dify.test/v1").run_workflow(
                "test-app-key", {"query": "hello"}
            )

    return asyncio.run(run())


def test_sse_handles_chunked_utf8_comments_and_node_events():
    wire = ": ping\n\n" + sse({
        "event": "workflow_started",
        "task_id": "task-1",
        "workflow_run_id": "run-1",
        "data": {},
    })
    wire += sse({"event": "node_finished", "data": {"status": "succeeded"}})
    wire += sse({
        "event": "workflow_finished",
        "task_id": "task-1",
        "workflow_run_id": "run-1",
        "data": {
            "id": "run-1",
            "status": "succeeded",
            "outputs": {"result": "连接成功"},
        },
    })
    result = execute_wire(wire)
    assert result.task_id == "task-1"
    assert result.workflow_run_id == "run-1"
    assert result.outputs == {"result": "连接成功"}


def test_sse_supports_multiline_data_and_final_event_without_blank_line():
    wire = 'data: {"event":"workflow_finished",\n'
    wire += 'data: "task_id":"task-2","data":{"id":"run-2",'
    wire += '"status":"succeeded","outputs":{"result":"ok"}}}\n'
    assert execute_wire(wire).workflow_run_id == "run-2"


@pytest.mark.parametrize("status", ["failed", "stopped", "partial-succeeded"])
def test_unsuccessful_workflow_is_not_treated_as_success(status):
    wire = sse({
        "event": "workflow_finished",
        "data": {"status": status, "error": "model failed"},
    })
    with pytest.raises(DifyWorkflowError, match="model failed"):
        execute_wire(wire)


def test_error_event_is_reported():
    with pytest.raises(DifyWorkflowError, match="invalid input"):
        execute_wire(sse({"event": "error", "message": "invalid input"}))


def test_truncated_stream_is_reported():
    with pytest.raises(DifyWorkflowError, match="没有收到"):
        execute_wire(sse({"event": "workflow_started", "task_id": "task-1"}))


def test_malformed_event_is_reported():
    with pytest.raises(DifyWorkflowError, match="无法解析"):
        execute_wire("data: {not json}\n\n")
