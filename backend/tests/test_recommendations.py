import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.library_models import UserItem
from app.main import create_app
from app.recommendation_models import BlockedMovie, RecommendationBatch, RecommendationTask
from app.recommendation_schemas import RecommendationSelection, RequestCriteria
from test_catalog import movie
from test_dify_client import ChunkedStream, sse
from test_profiles import seed

AUTH = {"X-Internal-Token": "test-internal-token"}


@pytest.fixture
def recommendations(migrated_settings):
    migrated_settings.tmdb_read_access_token = SecretStr("tmdb-test")
    app = create_app(migrated_settings)
    calls = {"discover": [], "detail": [], "workflow": [], "rows": list(range(1, 17)), "fail": False}

    def handler(request):
        path = request.url.path
        if path.endswith("/configuration"):
            return httpx.Response(200, json={"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}})
        if path.endswith("/genre/movie/list"):
            return httpx.Response(200, json={"genres": [{"id": 18, "name": "剧情"}, {"id": 27, "name": "恐怖"}]})
        if path.endswith("/discover/movie"):
            params = dict(request.url.params)
            calls["discover"].append(params)
            if calls["fail"]:
                return httpx.Response(429, json={"status_message": "slow down"})
            ids = [] if params.get("primary_release_date.gte") else calls["rows"]
            return httpx.Response(200, json={"results": [movie(i, f"Film {i}") for i in ids], "total_pages": 1})
        if "/movie/" in path:
            movie_id = int(path.rsplit("/", 1)[-1])
            calls["detail"].append(movie_id)
            return httpx.Response(200, json=movie(movie_id, f"Film {movie_id}"))
        raise AssertionError(path)

    with TestClient(app) as client:
        fake_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        app.state.tmdb.http = fake_http
        yield client, app.state.engine, calls
        client.portal.call(fake_http.aclose)


def prepared(client, criteria=None):
    response = client.post("/recommendations/contexts", json={"request_text": "轻松的日本电影，不要恐怖"})
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    response = client.post(f"/internal/recommendation-contexts/{task_id}/criteria", headers=AUTH,
                           json=criteria or {"excluded_genres": ["恐怖"], "moods": ["轻松"]})
    assert response.status_code == 200, response.text
    return task_id


def search(client, task_id):
    return client.post("/internal/movie-tools/search", headers=AUTH, json={"task_id": task_id, "target_count": 3})


def test_task_preparation_and_tools_schema_expose_only_authenticated_read_tools(recommendations):
    client, _, _ = recommendations
    task_id = prepared(client)
    assert search(client, task_id).status_code == 200
    assert client.post("/internal/movie-tools/search", json={"task_id": task_id}).status_code == 401
    assert client.post(f"/internal/recommendation-contexts/{task_id}/criteria", json={}).status_code == 401
    schema = client.get("/recommendations/tools/openapi.json").json()
    assert set(schema["paths"]) == {"/internal/movie-tools/search", "/internal/movie-tools/details"}
    assert {entry["post"]["operationId"] for entry in schema["paths"].values()} == {"search_movies", "get_movie_details"}
    assert all(entry["post"]["security"] for entry in schema["paths"].values())
    assert client.get(f"/recommendations/tasks/{task_id}").json()["status"] == "prepared"


def test_criteria_are_fixed_and_invalid_ranges_or_genres_are_reported(recommendations):
    client, _, _ = recommendations
    task_id = prepared(client)
    endpoint = f"/internal/recommendation-contexts/{task_id}/criteria"
    assert client.post(endpoint, headers=AUTH, json={"excluded_genres": ["恐怖"], "moods": ["轻松"]}).status_code == 200
    assert client.post(endpoint, headers=AUTH, json={"moods": ["悲伤"]}).status_code == 409
    assert client.post(endpoint, headers=AUTH, json={"year_from": 2020, "year_to": 2000}).status_code == 422
    new_id = client.post("/recommendations/contexts", json={"request_text": "新任务"}).json()["task_id"]
    assert client.post(f"/internal/recommendation-contexts/{new_id}/criteria", headers=AUTH,
                       json={"preferred_genres": ["随便编造的类型"]}).status_code == 422


def test_candidates_exclude_imported_watched_but_keep_wish_and_cache_details(recommendations):
    client, engine, calls = recommendations
    seed(engine, 3)
    seed(engine, 1, "wish")
    task_id = prepared(client)
    items = search(client, task_id).json()["items"]
    assert 1 not in [item["tmdb_id"] for item in items] and 2 not in [item["tmdb_id"] for item in items]
    assert 3 in [item["tmdb_id"] for item in items]
    assert len(items) >= 3
    first = items[0]
    count = len(calls["detail"])
    detail = client.post("/internal/movie-tools/details", headers=AUTH,
                         json={"task_id": task_id, "movie_id": first["movie_id"]})
    assert detail.status_code == 200 and detail.json()["movie"]["tmdb_id"] == first["tmdb_id"]
    search(client, task_id)
    assert len(calls["detail"]) == count
    assert len(calls["discover"]) == 1


def test_relaxation_keeps_negative_genres_and_rejects_model_changes(recommendations):
    client, _, calls = recommendations
    task_id = prepared(client, {"year_from": 2020, "runtime_max": 120, "countries": ["JP"],
                               "languages": ["ja"], "preferred_genres": ["剧情"], "excluded_genres": ["恐怖"]})
    result = search(client, task_id)
    assert result.status_code == 200
    assert "primary_release_date.gte" in calls["discover"][0]
    assert "primary_release_date.gte" not in calls["discover"][1]
    assert all(p["without_genres"] == "27" for p in calls["discover"])
    assert all(p["with_runtime.lte"] == "120" for p in calls["discover"])
    assert all(item["relaxation_stage"] == 1 for item in result.json()["items"])
    assert client.post("/internal/movie-tools/search", headers=AUTH,
                       json={"task_id": task_id, "target_count": 1}).status_code == 422


def test_final_check_rejects_unknown_duplicates_and_latest_watched(recommendations):
    client, engine, _ = recommendations
    task_id = prepared(client)
    ids = [item["movie_id"] for item in search(client, task_id).json()["items"]][:3]
    service = client.app.state.recommendation_runner.service
    from fastapi import HTTPException
    for invalid in [[ids[0]] * 3, [*ids[:2], 99999], ids[:2]]:
        with pytest.raises(HTTPException):
            service.complete(task_id, RecommendationSelection(movie_ids=invalid, reasons=["理由"] * len(invalid)), "run")
    with Session(engine) as session:
        work = session.get(CatalogItem, ids[0])
        original = work.details
        work.details = {**original, "genres": [{"id": 27, "name": "恐怖"}]}
        session.commit()
    with pytest.raises(HTTPException):
        service.complete(task_id, RecommendationSelection(movie_ids=ids, reasons=["理由"] * 3), "run")
    with Session(engine) as session:
        session.get(CatalogItem, ids[0]).details = original
        session.add(UserItem(catalog_item_id=ids[0], status="watched", rating=None, source="manual",
                             marked_at=1, created_at=1, updated_at=1))
        session.commit()
    with pytest.raises(HTTPException):
        service.complete(task_id, RecommendationSelection(movie_ids=ids, reasons=["理由"] * 3), "run")
    assert client.post("/internal/movie-tools/details", headers=AUTH,
                       json={"task_id": task_id, "movie_id": ids[0]}).status_code == 409
    assert client.post("/internal/movie-tools/details", headers=AUTH,
                       json={"task_id": task_id, "movie_id": 99999}).status_code == 422


def test_blocked_and_batch_shown_are_excluded_and_success_is_persistent(recommendations, migrated_settings):
    client, engine, _ = recommendations
    task_id = prepared(client)
    items = search(client, task_id).json()["items"]
    ids = [row["movie_id"] for row in items]
    with Session(engine) as session:
        session.add(BlockedMovie(catalog_id=ids[0], created_at=1))
        task = session.get(RecommendationTask, task_id)
        session.get(RecommendationBatch, task.batch_id).shown_ids = [ids[1]]
        session.commit()
    remaining = search(client, task_id).json()["items"]
    assert not {ids[0], ids[1]}.intersection(row["movie_id"] for row in remaining)
    selected = [row["movie_id"] for row in remaining][:3]
    client.app.state.recommendation_runner.service.complete(
        task_id, RecommendationSelection(movie_ids=selected, reasons=["根据简介符合本次需求"] * 3), "workflow-1")
    with TestClient(create_app(migrated_settings)) as restarted:
        state = restarted.get(f"/recommendations/tasks/{task_id}").json()
        assert state["status"] == "succeeded" and len(state["cards"]) == 3
        assert state["needs_refresh"] is False
    with Session(engine) as session:
        session.add(BlockedMovie(catalog_id=selected[0], created_at=1))
        session.commit()
    state = client.get(f"/recommendations/tasks/{task_id}").json()
    assert len(state["cards"]) == 2 and state["needs_refresh"] is True


def test_upstream_error_is_not_hidden_and_missing_criteria_is_reported(recommendations):
    client, _, calls = recommendations
    task_id = client.post("/recommendations/contexts", json={"request_text": "电影"}).json()["task_id"]
    assert search(client, task_id).status_code == 409
    task_id = prepared(client)
    calls["fail"] = True
    assert search(client, task_id).status_code == 503
    assert client.post("/recommendations/request", json={"request_text": "电影"}).status_code == 503


def test_all_relaxation_stages_keep_negatives_and_do_not_fabricate_candidates(recommendations):
    client, _, calls = recommendations
    calls["rows"] = []
    task_id = prepared(client, {"year_from": 2020, "runtime_max": 120, "countries": ["JP"],
                               "languages": ["ja"], "preferred_genres": ["剧情"], "excluded_genres": ["恐怖"],
                               "other_exclusions": ["不要血腥内容"]})
    result = search(client, task_id).json()
    params = calls["discover"]
    assert len(params) == 5 and result["items"] == []
    assert "primary_release_date.gte" not in params[1]
    assert "with_runtime.lte" not in params[2]
    assert "with_origin_country" not in params[3] and "with_original_language" not in params[3]
    assert "with_genres" not in params[4]
    assert all(p["without_genres"] == "27" for p in params)
    assert result["criteria"]["other_exclusions"] == ["不要血腥内容"]


def test_workflow_call_has_only_request_context_and_can_retry(recommendations):
    client, _, calls = recommendations
    app = client.app
    app.state.settings.dify_request_api_key = SecretStr("request-test")
    service = app.state.recommendation_runner.service
    attempt = 0

    async def workflow(request):
        nonlocal attempt
        attempt += 1
        assert request.headers["Authorization"] == "Bearer request-test"
        body = json.loads(request.content)
        inputs = body["inputs"]
        calls["workflow"].append(inputs)
        assert set(inputs) == {"task_id", "request_text", "target_count"}
        assert "画像" not in json.dumps(inputs, ensure_ascii=False)
        if attempt == 1:
            return httpx.Response(200, stream=ChunkedStream(sse({"event": "error", "message": "model busy"}).encode()))
        await service.register_criteria(inputs["task_id"], RequestCriteria())
        items = (await service.search(inputs["task_id"], 3))["items"]
        result = {"movie_ids": [item["movie_id"] for item in items[:3]], "reasons": ["符合本次需求"] * 3}
        return httpx.Response(200, stream=ChunkedStream(sse({"event": "workflow_finished", "task_id": "dify-task",
            "workflow_run_id": "workflow-2", "data": {"status": "succeeded", "outputs": {"result": result}}}).encode()))

    fake = httpx.AsyncClient(transport=httpx.MockTransport(workflow))
    app.state.recommendation_runner.client.http = fake
    task_id = client.post("/recommendations/request", json={"request_text": "轻松的电影"}).json()["task_id"]

    async def finish():
        task = app.state.recommendation_runner.tasks.get(task_id)
        if task:
            await asyncio.wait_for(asyncio.shield(task), 10)

    client.portal.call(finish)
    assert client.get(f"/recommendations/tasks/{task_id}").json()["status"] == "failed"
    assert client.post(f"/recommendations/tasks/{task_id}/run").status_code == 200
    client.portal.call(finish)
    state = client.get(f"/recommendations/tasks/{task_id}").json()
    assert state["status"] == "succeeded" and len(state["cards"]) == 3
    assert state["workflow_run_id"] == "workflow-2"
    assert client.post(f"/recommendations/tasks/{task_id}/run").status_code == 409
    client.portal.call(fake.aclose)
