import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.library_models import UserItem
from app.main import create_app
from app.recommendation_models import BlockedMovie, MovieVerification, RecommendationBatch, RecommendationTask
from app.recommendation_schemas import RecommendationSelection
from test_catalog import movie
from test_profiles import seed
from test_recommendations import AUTH, legacy, recommendations  # noqa: F401


def context(client):
    response = client.post("/recommendations/contexts", json={"request_text": "根据电影知识推荐未看过的作品"})
    assert response.status_code == 200
    assert response.json()["strategy"] == "ai_nomination"
    return response.json()["task_id"]


def verify(client, task_id, titles, constraints=None):
    body = {"task_id": task_id, "movies": [dict(title=f"Film {i}", year=2010) if isinstance(i, int) else i for i in titles]}
    if constraints is not None:
        body["constraints"] = constraints
    return client.post("/internal/movie-tools/verify", headers=AUTH, json=body)


def test_verify_auth_schema_first_constraints_and_batch_limit(recommendations):
    client, _, calls = recommendations
    task_id = context(client)
    assert client.post("/internal/movie-tools/verify", json={"task_id": task_id, "movies": [{"title": "Film 1"}]}).status_code == 401
    assert verify(client, task_id, [1]).status_code == 422
    assert verify(client, task_id, list(range(1, 10)), {}).status_code == 422
    assert verify(client, "missing-task", [1], {}).status_code == 404
    schema = client.get("/recommendations/tools/openapi.json").json()
    assert set(schema["paths"]) == {"/internal/movie-tools/verify"}
    assert schema["paths"]["/internal/movie-tools/verify"]["post"]["operationId"] == "verify_movies"
    assert calls["discover"] == []
    properties = schema["components"]["schemas"]["VerifyMoviesInput"]["properties"]
    assert properties["movies"]["type"] == "string" and properties["constraints"]["type"] == "string"


def test_dify_json_text_parameters_are_decoded_and_malformed_json_is_rejected(recommendations):
    client, _, _ = recommendations
    task_id = context(client)
    response = client.post("/internal/movie-tools/verify", headers=AUTH,
                           json={"task_id": task_id, "movies": json.dumps([{"title": "Film 1", "year": 2010}]),
                                 "constraints": "{}"})
    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "eligible"
    assert client.post("/internal/movie-tools/verify", headers=AUTH,
                       json={"task_id": task_id, "movies": "broken json"}).status_code == 422


def test_only_proposed_movies_are_verified_with_duplicate_and_not_found_history(recommendations):
    client, _, calls = recommendations
    task_id = context(client)
    response = verify(client, task_id, [1, 2, 1, {"title": "Invented film"}], {})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [item["status"] for item in result["items"]] == ["eligible", "eligible", "duplicate", "not_found"]
    assert len(result["eligible_movie_ids"]) == 2
    assert {item["movie"]["tmdb_id"] for item in result["items"] if item["status"] == "eligible"} == {1, 2}
    assert calls["discover"] == []
    assert len(calls["search"]) == 3
    history = client.get(f"/recommendations/tasks/{task_id}/verifications").json()["items"]
    assert len(history) == 4 and history[2]["status"] == "duplicate"
    assert all(row["proposal"] for row in history)


def test_watched_cross_source_exclusion_and_wish_remains_eligible(recommendations):
    client, engine, calls = recommendations
    seed(engine, 2)  # Film 0、Film 1，来源为导入身份。
    seed(engine, 1, "wish")  # Film 2。
    task_id = context(client)
    items = verify(client, task_id, [1, 2, 3], {}).json()["items"]
    assert [item["status"] for item in items] == ["watched", "eligible", "eligible"]
    first_id = items[1]["movie_id"]
    with Session(engine) as session:
        session.add(BlockedMovie(catalog_id=first_id, created_at=1))
        task = session.get(RecommendationTask, task_id)
        session.get(RecommendationBatch, task.batch_id).shown_ids = [items[2]["movie_id"]]
        session.commit()
    items = verify(client, task_id, [2, 3]).json()["items"]
    assert [item["status"] for item in items] == ["blocked", "already_shown"]
    assert calls["discover"] == []


def test_unique_title_without_year_and_ambiguous_title_can_be_refined(recommendations):
    client, _, calls = recommendations
    calls["search_results"]["Shared"] = [movie(10, "Shared", 2010), movie(20, "Shared", 2020)]
    task_id = context(client)
    result = verify(client, task_id, [{"title": "Film 1"}, {"title": "Shared"}], {}).json()
    assert [item["status"] for item in result["items"]] == ["eligible", "ambiguous"]
    assert len(result["items"][1]["candidates"]) == 2
    response = verify(client, task_id, [{"title": "Shared", "year": 2020}])
    assert response.json()["items"][0]["status"] == "eligible"
    assert response.json()["items"][0]["movie"]["tmdb_id"] == 20


def test_hard_constraints_are_frozen_and_director_cannot_be_relaxed(recommendations):
    client, _, calls = recommendations
    calls["director_mismatch_ids"] = [2]
    task_id = context(client)
    response = verify(client, task_id, [1, 2], {"directors": ["Director"]})
    assert [item["status"] for item in response.json()["items"]] == ["eligible", "condition_mismatch"]
    assert verify(client, task_id, [3], {"directors": ["Director", "Director"]}).status_code == 200
    assert verify(client, task_id, [3], {}).status_code == 409
    assert verify(client, task_id, [3]).status_code == 200
    assert calls["discover"] == []
    assert all("with_crew" not in params for params in calls["search"])


def test_numeric_country_language_and_genre_constraints_are_checked(recommendations):
    client, _, _ = recommendations
    invalid = [{"year_from": 2020}, {"year_to": 2000}, {"runtime_max": 90}, {"runtime_min": 110},
               {"countries": ["JP"]}, {"languages": ["ja"]}, {"required_genres": ["恐怖"]}, {"excluded_genres": ["剧情"]}]
    for constraints in invalid:
        item = verify(client, context(client), [1], constraints).json()["items"][0]
        assert item["status"] == "condition_mismatch", constraints
    response = verify(client, context(client), [1], {"countries": ["US"], "languages": ["en"],
                      "required_genres": ["剧情"], "runtime_max": 120, "year_from": 2000})
    assert response.json()["items"][0]["status"] == "eligible"


def test_actor_uses_full_cast_and_backfills_legacy_cache(recommendations):
    client, engine, calls = recommendations
    calls["extra_actor_ids"] = [18, 77]
    calls["people"] = [{"id": 77, "name": "Supporting Actor"}]
    detail = client.get("/catalog/details?media_type=movie&tmdb_id=1").json()
    assert 77 not in [person["id"] for person in detail["cast"]]
    with Session(engine) as session:
        work = session.get(CatalogItem, detail["catalog_id"])
        work.details = {key: value for key, value in work.details.items() if key != "cast_ids"}
        session.commit()
    response = verify(client, context(client), [1], {"actors": ["Supporting Actor"]})
    assert response.json()["items"][0]["status"] == "eligible"
    with Session(engine) as session:
        assert 77 in session.get(CatalogItem, detail["catalog_id"]).details["cast_ids"]
    assert calls["detail"].count(1) == 2


def test_final_validation_checks_latest_conditions_membership_and_watched(recommendations, migrated_settings):
    client, engine, _ = recommendations
    task_id = context(client)
    result = verify(client, task_id, [1, 2, 3, 4], {"runtime_max": 120}).json()
    ids = result["eligible_movie_ids"]
    service = client.app.state.recommendation_runner.service
    with pytest.raises(HTTPException):
        service.complete(task_id, RecommendationSelection(movie_ids=[ids[0], ids[1], 9999], reasons=["r"] * 3), "run")
    with Session(engine) as session:
        work = session.get(CatalogItem, ids[0])
        work.details = {**work.details, "runtime": 150}
        session.commit()
    with pytest.raises(HTTPException):
        service.complete(task_id, RecommendationSelection(movie_ids=ids[:3], reasons=["r"] * 3), "run")
    with Session(engine) as session:
        session.add(UserItem(catalog_item_id=ids[1], status="watched", rating=None, source="manual",
                             marked_at=1, created_at=1, updated_at=1))
        session.commit()
    with pytest.raises(HTTPException):
        service.complete(task_id, RecommendationSelection(movie_ids=ids[1:4], reasons=["r"] * 3), "run")
    with Session(engine) as session:
        assert session.scalar(select(MovieVerification.id).where(MovieVerification.task_id == task_id)) is not None
    with TestClient(create_app(migrated_settings)) as restarted:
        assert len(restarted.get(f"/recommendations/tasks/{task_id}/verifications").json()["items"]) == 4


def test_service_error_is_not_reported_as_not_found_and_legacy_cannot_use_verify(recommendations):
    client, _, calls = recommendations
    task_id = context(client)
    calls["fail"] = True
    assert verify(client, task_id, [1], {}).status_code == 503
    assert client.get(f"/recommendations/tasks/{task_id}/verifications").json()["items"] == []
    legacy(client, task_id)
    assert verify(client, task_id, [1], {}).status_code == 409
    client.app.state.settings.dify_request_api_key = SecretStr("request-test")
    assert client.post(f"/recommendations/tasks/{task_id}/run").status_code == 409
