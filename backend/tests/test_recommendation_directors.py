import json

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.recommendation_models import RecommendationTask
from app.recommendation_schemas import RecommendationSelection
from dify_nodes.parse_recommendation_result import main
from test_recommendations import AUTH, legacy, prepared, recommendations, search  # noqa: F401


def test_actual_empty_result_with_trailing_explanation_is_preserved():
    text = '{"movie_ids": [], "reasons": []}\n\n候选不足：需求是“李沧东”导演的未看过作品，但没有匹配候选。'
    result = main(text)["result"]
    assert result["movie_ids"] == [] and result["reasons"] == []
    assert result["error"] == text.split("\n\n")[1]


def test_valid_result_and_explicit_failure_stay_unchanged():
    for result in [{"movie_ids": [1, 2, 3], "reasons": ["a", "b", "c"]},
                   {"movie_ids": [], "reasons": [], "error": "符合要求的影片不足"}]:
        assert main(json.dumps(result))["result"] == result
    with pytest.raises(json.JSONDecodeError):
        main('not json')


@pytest.mark.parametrize("prefix,suffix", [
    ("已核实到足够合格作品，现在开始最终选择。\n\n```json\n", "\n```"),
    ("```json\n", "\n```"),
    ("推荐结果如下：\n", ""),
])
def test_agent_explanation_and_markdown_wrapper_are_accepted(prefix, suffix):
    result = {"movie_ids": [638, 700, 696], "reasons": ["a", "b", "c"]}
    assert main(prefix + json.dumps(result) + suffix)["result"] == result


def test_empty_fenced_result_does_not_use_closing_fence_as_error():
    assert main('```json\n{"movie_ids":[],"reasons":[]}\n```')["result"] == {"movie_ids": [], "reasons": []}


def test_director_is_not_relaxed_and_producer_only_films_are_not_candidates(recommendations):
    client, _, calls = recommendations
    calls["rows"] = [1, 2, 3]
    calls["director_mismatch_ids"] = [3]
    task_id = prepared(client, {"directors": ["Director"], "year_from": 2020, "runtime_max": 120,
                               "countries": ["JP"], "preferred_genres": ["剧情"]})
    response = search(client, task_id)
    assert response.status_code == 200
    assert {item["tmdb_id"] for item in response.json()["items"]} == {1, 2}
    assert all(p["with_crew"] == "9" for p in calls["discover"])
    assert len(calls["discover"]) == 5
    assert all(item["directors"][0]["id"] == 9 for item in response.json()["items"])
    service = client.app.state.recommendation_runner.service
    with pytest.raises(HTTPException) as error:
        service.complete(task_id, RecommendationSelection(movie_ids=[], reasons=[], error="该导演未看过作品不足三部"), "run")
    assert error.value.detail == "该导演未看过作品不足三部"


def test_ambiguous_director_is_reported_instead_of_picking_someone(recommendations):
    client, _, calls = recommendations
    calls["people"] = [{"id": 9, "name": "Director"}, {"id": 10, "name": "Director"}]
    task_id = client.post("/recommendations/contexts", json={"request_text": "Director 的作品"}).json()["task_id"]
    legacy(client, task_id)
    response = client.post(f"/internal/recommendation-contexts/{task_id}/criteria", headers=AUTH,
                           json={"directors": ["Director"]})
    assert response.status_code == 422
    assert calls["discover"] == []


def test_legacy_criteria_without_director_field_can_be_registered_again(recommendations):
    client, engine, _ = recommendations
    task_id = prepared(client)
    with Session(engine) as session:
        task = session.get(RecommendationTask, task_id)
        task.criteria = {key: value for key, value in task.criteria.items() if key != "directors"}
        task.filters = {key: value for key, value in task.filters.items() if key != "director_ids"}
        session.commit()
    assert client.post(f"/internal/recommendation-contexts/{task_id}/criteria", headers=AUTH,
                       json={"excluded_genres": ["恐怖"], "moods": ["轻松"]}).status_code == 200
    assert search(client, task_id).status_code == 200
