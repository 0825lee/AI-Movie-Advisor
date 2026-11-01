import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.library_models import UserItem
from app.profile_record_models import ProfileRecord
from app.recommendation_models import BlockedMovie, RecommendationBatch, RecommendationTask
from app.recommendation_schemas import RecommendationSelection
from test_personalized import finish, personalized, save_profile  # noqa: F401
from test_recommendations import recommendations  # noqa: F401

AUTH = {"X-Internal-Token": "test-internal-token"}


def prepare(client, mode="request"):
    return client.post(f"/recommendations/{'personalized/contexts' if mode == 'personalized' else 'contexts'}",
                       **({"json": {"request_text": "本次原始观影需求"}} if mode == "request" else {})).json()


def verify(client, task, ids, constraints=None):
    body = {"task_id": task["task_id"], "movies": [{"title": f"Film {i}", "year": 2010} for i in ids]}
    if constraints is not None:
        body["constraints"] = constraints
    response = client.post("/internal/movie-tools/verify", headers=AUTH, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def successful(client, mode="request"):
    task = prepare(client, mode)
    ids = verify(client, task, [1, 2, 3], {})["eligible_movie_ids"]
    client.app.state.recommendation_runner.service.complete(task["task_id"],
        RecommendationSelection(movie_ids=ids, reasons=["符合本次推荐依据"] * 3), "test-run")
    return client.get(f"/recommendations/tasks/{task['task_id']}").json()


def test_wish_reuses_library_and_stays_eligible_until_watched(personalized):
    client, engine, _ = personalized
    task = successful(client)
    card = task["cards"][0]
    assert card["library_status"] is None
    body = {"media_type": "movie", "tmdb_id": card["movie"]["tmdb_id"], "status": "wish"}
    first = client.post("/library/manual", json=body).json()
    assert client.post("/library/manual", json=body).json()["id"] == first["id"]
    state = client.get(f"/recommendations/tasks/{task['task_id']}").json()
    assert len(state["cards"]) == 3 and state["cards"][0]["library_status"] == "wish"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserItem)) == 1
        assert session.get(ProfileRecord, first["id"]) is not None
    assert verify(client, prepare(client), [1], {})["items"][0]["status"] == "eligible"
    assert client.post(f"/library/{first['id']}/watched", json={"rating": None}).status_code == 200
    state = client.get(f"/recommendations/tasks/{task['task_id']}").json()
    assert len(state["cards"]) == 2 and state["needs_refresh"] is True
    assert verify(client, prepare(client), [1], {})["items"][0]["status"] == "watched"


def test_blocked_list_is_persistent_and_excludes_both_modes(personalized, migrated_settings):
    client, engine, _ = personalized
    save_profile(engine)
    task = successful(client)
    movie_id = task["cards"][0]["movie_id"]
    path = f"/recommendations/tasks/{task['task_id']}/movies/{movie_id}/block"
    for _ in range(2):
        state = client.post(path).json()
        assert len(state["cards"]) == 2 and state["needs_refresh"]
    blocked = client.get("/recommendations/blocked").json()
    assert blocked["total"] == 1 and blocked["items"][0]["movie_id"] == movie_id
    assert client.get("/recommendations/blocked?query=Film+1").json()["total"] == 1
    assert client.get("/recommendations/blocked?query=missing").json()["total"] == 0
    assert client.get("/recommendations/blocked?page=0").status_code == 422
    for mode in ["request", "personalized"]:
        assert verify(client, prepare(client, mode), [1], {})["items"][0]["status"] == "blocked"
    with TestClient(create_app(migrated_settings)) as restarted:
        assert restarted.get("/recommendations/blocked").json()["total"] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserItem)) == 0


def test_block_only_accepts_actual_recommendation_and_clear_removes_blocked_list(personalized):
    client, engine, _ = personalized
    task = successful(client)
    base = f"/recommendations/tasks/{task['task_id']}/movies"
    assert client.post(base + "/99999/block").status_code == 422
    assert client.post("/recommendations/tasks/missing/movies/1/block").status_code == 404
    client.post(base + f"/{task['cards'][0]['movie_id']}/block")
    assert client.delete("/library").status_code == 200
    assert client.get("/recommendations/blocked").json()["total"] == 0
    # 需求推荐记录保留；取消全部屏蔽后，旧结果重新按当前排除状态读取。
    assert len(client.get(f"/recommendations/tasks/{task['task_id']}").json()["cards"]) == 3
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(BlockedMovie)) == 0
    assert verify(client, prepare(client), [1], {})["items"][0]["status"] == "eligible"


@pytest.mark.parametrize("mode", ["request", "personalized"])
def test_next_batch_excludes_shown_keeps_context_and_new_recommendation_can_repeat(personalized, mode):
    client, engine, calls = personalized
    first_profile = save_profile(engine)
    first = successful(client, mode)
    if mode == "personalized":
        save_profile(engine, 2)
    calls["proposal_ids"] = [4, 5, 6]
    response = client.post(f"/recommendations/tasks/{first['task_id']}/next")
    assert response.status_code == 200, response.text
    second = finish(client, response.json()["task_id"])
    assert second["status"] == "succeeded", second
    assert second["batch_id"] == first["batch_id"] and second["task_id"] != first["task_id"]
    assert second["request_text"] == first["request_text"]
    assert not {c["movie_id"] for c in first["cards"]}.intersection(c["movie_id"] for c in second["cards"])
    if mode == "personalized":
        assert calls["uploads"] == [first_profile] and second["profile_version"] == 1
    with Session(engine) as session:
        batch = session.get(RecommendationBatch, first["batch_id"])
        assert len(batch.shown_ids) == 6
        child = session.get(RecommendationTask, second["task_id"])
        assert child.criteria == session.get(RecommendationTask, first["task_id"]).criteria
    third_id = client.app.state.recommendation_runner.service.next_batch(second["task_id"])
    third = {"task_id": third_id}
    assert [x["status"] for x in verify(client, third, [1, 4])["items"]] == ["already_shown", "already_shown"]
    assert verify(client, prepare(client, mode), [1], {})["items"][0]["status"] == "eligible"


def test_failed_next_batch_retries_same_task_without_losing_shown_set(personalized):
    client, engine, calls = personalized
    first = successful(client)
    calls["proposal_ids"] = [4, 5, 6]
    calls["model_fail"] = True
    second = client.post(f"/recommendations/tasks/{first['task_id']}/next").json()
    assert finish(client, second["task_id"])["status"] == "failed"
    calls["model_fail"] = False
    assert client.post(f"/recommendations/tasks/{second['task_id']}/run").status_code == 200
    assert finish(client, second["task_id"])["status"] == "succeeded"
    with Session(engine) as session:
        assert len(session.get(RecommendationBatch, first["batch_id"]).shown_ids) == 6


def test_next_requires_completed_task_and_reuses_prepared_child(personalized):
    client, _, _ = personalized
    pending = prepare(client)
    assert client.post(f"/recommendations/tasks/{pending['task_id']}/next").status_code == 409
    first = successful(client)
    service = client.app.state.recommendation_runner.service
    child_id = service.next_batch(first["task_id"])
    assert service.next_batch(first["task_id"]) == child_id
