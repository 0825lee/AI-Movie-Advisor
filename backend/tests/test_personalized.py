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

from app.main import create_app
from app.profile_models import ProfileVersion
from app.recommendation_models import MovieVerification, RecommendationBatch, RecommendationCandidate, RecommendationTask
from app.recommendation_schemas import VerifyMoviesInput
from app.verification_service import MovieVerificationService
from test_dify_client import ChunkedStream, sse
from test_recommendations import recommendations  # noqa: F401


def save_profile(engine, version=1):
    data = dict(version=version, covered_count=50, summary=f"第{version}版画像" + "完整内容" * 600,
                preferences=[], less_preferred=[], recent_changes=[], limitations=[])
    with Session(engine) as session:
        session.add(ProfileVersion(version=version, data=data, covered_item_ids=list(range(1, 51)),
                                   conversation_id="profile-conversation", created_at=version))
        session.commit()
    return data


@pytest.fixture
def personalized(recommendations):
    client, engine, calls = recommendations
    app = client.app
    app.state.settings.dify_personalized_api_key = SecretStr("personalized-test")
    app.state.settings.dify_request_api_key = SecretStr("request-test")
    app.state.settings.dify_profile_api_key = SecretStr("profile-test")
    calls.update(uploads=[], workflow_inputs=[], model_fail=False, hold=False, started=asyncio.Event())

    async def handler(request):
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/files/upload"):
            assert request.headers["Authorization"] == "Bearer personalized-test"
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content)
            file = next(part for part in message.iter_parts() if part.get_filename())
            calls["uploads"].append(json.loads(file.get_payload(decode=True)))
            return httpx.Response(201, json={"id": f"file-{len(calls['uploads'])}"})
        assert request.url.path.endswith("/workflows/run")
        body = json.loads(request.content)
        inputs = body["inputs"]
        calls["workflow_inputs"].append((request.headers["Authorization"], inputs))
        if "profile_files" in inputs:
            assert request.headers["Authorization"] == "Bearer personalized-test"
            assert set(inputs) == {"task_id", "target_count", "profile_files"}
        else:
            assert request.headers["Authorization"] == "Bearer request-test"
            assert set(inputs) == {"task_id", "target_count", "request_text"}
        if calls["hold"]:
            calls["started"].set()
            await asyncio.Event().wait()
        if calls["model_fail"]:
            return httpx.Response(200, stream=ChunkedStream(sse({"event": "error", "message": "model unavailable"}).encode()))
        service = app.state.recommendation_runner.service
        verified = await MovieVerificationService(engine, service.catalog).verify(VerifyMoviesInput(
            task_id=inputs["task_id"], constraints={}, movies=[{"title": f"Film {i}", "year": 2010} for i in calls.get("proposal_ids", range(1, 4))]))
        result = {"movie_ids": verified.eligible_movie_ids, "reasons": ["符合本次推荐依据"] * 3}
        return httpx.Response(200, stream=ChunkedStream(sse({"event": "workflow_finished", "task_id": "remote-task",
            "workflow_run_id": "personalized-run", "data": {"status": "succeeded", "outputs": {"result": result}}}).encode()))

    fake = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.state.recommendation_runner.client.http = fake
    app.state.profile_runner.client.http = fake
    yield client, engine, calls
    client.portal.call(app.state.recommendation_runner.close)
    client.portal.call(fake.aclose)


def finish(client, task_id):
    async def wait():
        task = client.app.state.recommendation_runner.tasks.get(task_id)
        if task:
            await asyncio.wait_for(asyncio.shield(task), 10)
    client.portal.call(wait)
    return client.get(f"/recommendations/tasks/{task_id}").json()


def test_no_profile_is_reported_and_request_mode_still_works(personalized):
    client, _, calls = personalized
    assert client.post("/recommendations/personalized/contexts").status_code == 409
    assert client.post("/recommendations/personalized").status_code == 409
    task = client.post("/recommendations/request", json={"request_text": "看一部电影"}).json()
    assert finish(client, task["task_id"])["status"] == "succeeded"
    assert calls["uploads"] == []


def test_personalized_task_freezes_full_profile_and_uses_independent_key_and_file(personalized):
    client, engine, calls = personalized
    first = save_profile(engine)
    task = client.post("/recommendations/personalized/contexts").json()
    assert task["mode"] == "personalized" and task["profile_version"] == 1
    save_profile(engine, 2)
    assert client.get(f"/recommendations/tasks/{task['task_id']}/profile-input").json() == first
    assert client.post(f"/recommendations/tasks/{task['task_id']}/run").status_code == 200
    state = finish(client, task["task_id"])
    assert state["status"] == "succeeded" and len(state["cards"]) == 3
    assert state["profile_version"] == 1 and state["profile_summary"] == first["summary"]
    assert calls["uploads"] == [first] and len(first["summary"]) > 2000
    assert calls["workflow_inputs"][0][1]["profile_files"] == [
        {"type": "document", "transfer_method": "local_file", "upload_file_id": "file-1"}]
    assert client.post("/recommendations/personalized/contexts").json()["profile_version"] == 2


def test_request_mode_does_not_read_or_upload_profile(personalized):
    client, engine, calls = personalized
    save_profile(engine)
    task = client.post("/recommendations/request", json={"request_text": "只按本次需求推荐"}).json()
    assert finish(client, task["task_id"])["status"] == "succeeded"
    assert calls["uploads"] == []
    assert client.get(f"/recommendations/tasks/{task['task_id']}/profile-input").status_code == 409
    with Session(engine) as session:
        saved = session.get(RecommendationTask, task["task_id"])
        assert saved.profile_snapshot is None and saved.profile_version is None


def test_missing_personalized_key_does_not_fall_back_to_request_key(personalized):
    client, engine, calls = personalized
    save_profile(engine)
    client.app.state.settings.dify_personalized_api_key = None
    response = client.post("/recommendations/personalized")
    assert response.status_code == 503 and "DIFY_PERSONALIZED_API_KEY" in response.json()["detail"]
    assert calls["workflow_inputs"] == [] and calls["uploads"] == []


def test_retry_keeps_original_profile_snapshot(personalized):
    client, engine, calls = personalized
    first = save_profile(engine)
    calls["model_fail"] = True
    task = client.post("/recommendations/personalized").json()
    assert finish(client, task["task_id"])["status"] == "failed"
    save_profile(engine, 2)
    calls["model_fail"] = False
    assert client.post(f"/recommendations/tasks/{task['task_id']}/run").status_code == 200
    assert finish(client, task["task_id"])["status"] == "succeeded"
    assert calls["uploads"] == [first, first]


def test_restart_preserves_personalized_snapshot_and_result(personalized, migrated_settings):
    client, engine, _ = personalized
    first = save_profile(engine)
    task = client.post("/recommendations/personalized").json()
    finish(client, task["task_id"])
    with TestClient(create_app(migrated_settings)) as restarted:
        state = restarted.get(f"/recommendations/tasks/{task['task_id']}").json()
        assert state["mode"] == "personalized" and len(state["cards"]) == 3
        assert state["profile_summary"] == first["summary"]


def test_clear_removes_personalized_tasks_snapshots_candidates_and_logs_only(personalized):
    client, engine, _ = personalized
    save_profile(engine)
    request_task = client.post("/recommendations/request", json={"request_text": "本次需求"}).json()
    finish(client, request_task["task_id"])
    profile_task = client.post("/recommendations/personalized").json()
    finish(client, profile_task["task_id"])
    assert client.delete("/library").status_code == 200
    assert client.get(f"/recommendations/tasks/{profile_task['task_id']}").status_code == 404
    assert client.get(f"/recommendations/tasks/{request_task['task_id']}").json()["status"] == "succeeded"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RecommendationTask).where(RecommendationTask.mode == "personalized")) == 0
        assert session.scalar(select(func.count()).select_from(MovieVerification).where(MovieVerification.task_id == profile_task["task_id"])) == 0
        assert session.scalar(select(func.count()).select_from(RecommendationCandidate).where(RecommendationCandidate.task_id == profile_task["task_id"])) == 0
        assert session.get(RecommendationBatch, profile_task["batch_id"]) is None
        assert session.scalar(select(func.count()).select_from(ProfileVersion)) == 0


def test_clear_cancels_running_personalized_task_before_deleting_snapshot(personalized):
    client, engine, calls = personalized
    save_profile(engine)
    calls["hold"] = True
    task = client.post("/recommendations/personalized").json()
    client.portal.call(calls["started"].wait)
    assert task["task_id"] in client.app.state.recommendation_runner.tasks
    assert client.delete("/library").status_code == 200
    assert task["task_id"] not in client.app.state.recommendation_runner.tasks
    assert client.get(f"/recommendations/tasks/{task['task_id']}").status_code == 404
