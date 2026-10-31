import asyncio
import json
from email import policy
from email.parser import BytesParser

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.library_models import UserItem
from app.main import create_app
from app.profile_models import ProfileJob, ProfileVersion
from app.profile_records import PROFILE_FIELDS, sync_profile_record
from test_dify_client import ChunkedStream, sse


def seed(engine, count, status="watched"):
    with Session(engine) as session:
        start = session.scalar(select(func.count()).select_from(CatalogItem))
        for i in range(start, start + count):
            title = f"Film {i}"
            work = CatalogItem(identity_key=f"test:{i}", media_type="work", tmdb_id=None,
                               title=title, original_title=title, year=2010, fetched_at=1,
                               match_key=f"film{i}:2010", details=dict(title=title, original_title=title,
                               year=2010, season_number=None, media_type="work", tmdb_id=None,
                               info="2010 / Actor / Country / Director / 100分钟", douban_url=f"https://movie.douban.com/subject/{i}/"))
            session.add(work)
            session.flush()
            item = UserItem(catalog_item_id=work.id, status=status, rating=4 if status == "watched" else None,
                            marked_at=1, source="douban", created_at=1, updated_at=1)
            session.add(item)
            sync_profile_record(session, item, work)
        session.commit()


def finish(client):
    async def wait():
        task = client.app.state.profile_runner.task
        if task:
            await asyncio.wait_for(asyncio.shield(task), 10)
    client.portal.call(wait)
    return client.get("/profile").json()


@pytest.fixture
def profile_app(migrated_settings):
    migrated_settings.dify_profile_api_key = SecretStr("test-profile-key")
    app = create_app(migrated_settings)
    calls = {"uploads": [], "messages": [], "stops": [], "fail": False, "invalid": False, "hold": False,
             "started": asyncio.Event(), "release": asyncio.Event()}

    class HoldingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse({"event": "workflow_started", "task_id": "task-held", "conversation_id": "conversation-1"}).encode()
            calls["started"].set()
            await calls["release"].wait()
            answer = json.dumps(dict(version=1, covered_count=50, summary="快照画像", preferences=[],
                                     less_preferred=[], recent_changes=[], limitations=[]), ensure_ascii=False)
            yield (sse({"event": "message", "answer": answer, "conversation_id": "conversation-1"})
                   + sse({"event": "message_end", "conversation_id": "conversation-1"})).encode()

    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-profile-key"
        if request.url.path.endswith("/files/upload"):
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content)
            file = next(part for part in message.iter_parts() if part.get_filename())
            data = json.loads(file.get_payload(decode=True))
            calls["uploads"].append(data)
            return httpx.Response(201, json={"id": f"file-{len(calls['uploads'])}"})
        if request.url.path.endswith("/stop"):
            calls["stops"].append(request.url.path)
            return httpx.Response(200, json={"result": "success"})
        assert request.url.path.endswith("/chat-messages")
        body = json.loads(request.content)
        calls["messages"].append(body)
        if calls["hold"]:
            return httpx.Response(200, stream=HoldingStream())
        wire = sse({"event": "workflow_started", "task_id": "task-1", "conversation_id": "conversation-1"})
        if calls["fail"]:
            wire += sse({"event": "error", "message": "model unavailable"})
        else:
            answer = "not json" if calls["invalid"] else json.dumps(dict(
                version=0, covered_count=0, summary="测试画像", preferences=[], less_preferred=[],
                recent_changes=[], limitations=[]), ensure_ascii=False)
            for index in range(0, len(answer), 9):
                wire += sse({"event": "message", "answer": answer[index:index + 9],
                             "conversation_id": "conversation-1", "message_id": "message-1", "task_id": "task-1"})
            wire += sse({"event": "message_end", "conversation_id": "conversation-1", "message_id": "message-1"})
        return httpx.Response(200, stream=ChunkedStream(wire.encode()))

    with TestClient(app) as client:
        fake_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        app.state.profile_runner.client.http = fake_http
        yield client, app.state.engine, calls
        client.portal.call(app.state.profile_runner.cancel)
        client.portal.call(fake_http.aclose)


def test_first_profile_threshold_and_six_field_upload(profile_app):
    client, engine, calls = profile_app
    seed(engine, 49)
    assert client.get("/profile").json()["remaining"] == 1
    assert client.post("/profile/generate").status_code == 409
    seed(engine, 1)
    assert client.post("/profile/generate").status_code == 200
    state = finish(client)
    assert state["profile"]["version"] == 1 and state["profile"]["covered_count"] == 50
    assert state["covered_count"] == 50 and state["remaining"] == 50
    assert len(calls["uploads"][0]["records"]) == 50
    assert all(set(row) == set(PROFILE_FIELDS) for row in calls["uploads"][0]["records"])
    assert calls["messages"][0]["conversation_id"] == ""
    assert calls["messages"][0]["files"][0]["upload_file_id"] == "file-1"


def test_update_uses_only_new_fifty_and_old_wish_id_is_not_skipped(profile_app):
    client, engine, calls = profile_app
    seed(engine, 1, "wish")
    with Session(engine) as session:
        wish_id = session.scalar(select(UserItem.id))
    seed(engine, 50)
    client.post("/profile/generate")
    finish(client)
    seed(engine, 49)
    assert client.get("/profile").json()["pending_count"] == 49
    assert client.post("/profile/generate").status_code == 409
    assert client.post(f"/library/{wish_id}/watched", json={"rating": 5}).status_code == 200
    state = finish(client)
    assert state["profile"]["version"] == 2 and state["covered_count"] == 100
    assert len(calls["uploads"][1]["records"]) == 50
    assert calls["uploads"][1]["records"][0]["title"] == "Film 0"
    assert calls["messages"][1]["conversation_id"] == "conversation-1"
    assert "目标 version：2" in calls["messages"][1]["query"]
    assert "测试画像" in calls["messages"][1]["query"]


def test_failed_update_keeps_old_profile_and_retry_reuses_conversation(profile_app):
    client, engine, calls = profile_app
    seed(engine, 50)
    client.post("/profile/generate")
    finish(client)
    seed(engine, 50)
    calls["fail"] = True
    client.post("/profile/generate")
    failed = finish(client)
    assert failed["profile"]["version"] == 1 and failed["covered_count"] == 50
    assert failed["pending_count"] == 50 and failed["job"]["status"] == "failed"
    client.portal.call(client.app.state.profile_runner.maybe_start)
    assert len(calls["messages"]) == 2
    calls["fail"] = False
    client.post("/profile/generate")
    assert finish(client)["profile"]["version"] == 2
    assert calls["messages"][2]["conversation_id"] == "conversation-1"


def test_invalid_json_does_not_advance_coverage(profile_app):
    client, engine, calls = profile_app
    seed(engine, 50)
    calls["invalid"] = True
    client.post("/profile/generate")
    state = finish(client)
    assert state["profile"] is None and state["covered_count"] == 0
    assert state["job"]["status"] == "failed"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProfileVersion)) == 0


def test_clear_cancels_generation_and_removes_profile_state(profile_app):
    client, engine, calls = profile_app
    seed(engine, 50)
    calls["hold"] = True
    client.post("/profile/generate")
    client.portal.call(calls["started"].wait)
    assert client.post("/profile/generate").status_code == 409
    assert client.delete("/library").json()["deleted"] == 50
    state = client.get("/profile").json()
    assert state["profile"] is None and state["watched_count"] == 0 and state["job"] is None
    assert calls["stops"] == ["/v1/chat-messages/task-held/stop"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProfileJob)) == 0


def test_restart_keeps_profile_and_failed_running_job_does_not_advance_baseline(profile_app, migrated_settings):
    client, engine, _ = profile_app
    seed(engine, 50)
    client.post("/profile/generate")
    finish(client)
    with Session(engine) as session:
        session.add(ProfileJob(status="running", stage="generating", version=2, batch_item_ids=[999],
                               covered_item_ids=list(range(1, 52)), created_at=1, updated_at=1))
        session.commit()
    with TestClient(create_app(migrated_settings)) as restarted:
        state = restarted.get("/profile").json()
        assert state["profile"]["version"] == 1 and state["covered_count"] == 50
        assert state["job"]["status"] == "failed"


def test_missing_key_is_reported_without_generation(migrated_settings):
    with TestClient(create_app(migrated_settings)) as client:
        assert client.get("/profile").json()["configured"] is False
        assert client.post("/profile/generate").status_code == 503


def test_records_added_during_generation_stay_pending_for_next_version(profile_app):
    client, engine, calls = profile_app
    seed(engine, 50)
    calls["hold"] = True
    client.post("/profile/generate")
    client.portal.call(calls["started"].wait)
    seed(engine, 1)
    client.portal.call(calls["release"].set)
    state = finish(client)
    assert state["watched_count"] == 51 and state["covered_count"] == 50
    assert state["pending_count"] == 1 and state["remaining"] == 49


def test_large_import_triggers_one_initial_profile_after_import_finishes(profile_app):
    client, _, calls = profile_app
    records = [dict(status="collect", subjectId=str(i), title=f"Auto {i}", originalTitle=f"Auto {i}",
                    info="2010(美国)", stars=4, rating=8, markedAt="2025-01-01", comment="") for i in range(60)]
    response = client.post("/imports", json={"filename": "initial.json", "data": {"records": records}})
    assert response.status_code == 200
    async def imported():
        await asyncio.wait_for(asyncio.shield(client.app.state.import_runner.task), 10)
    client.portal.call(imported)
    state = finish(client)
    assert state["profile"]["covered_count"] == 60
    assert len(calls["messages"]) == 1 and len(calls["uploads"][0]["records"]) == 60
