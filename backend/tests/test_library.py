import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_catalog import catalog  # noqa: F401 -- reuse the TMDB fixture


def add(client, status="wish", tmdb_id=1, media_type="movie", rating=None, **extra):
    response = client.post("/library/manual", json=dict(
        media_type=media_type, tmdb_id=tmdb_id, status=status, rating=rating, **extra,
    ))
    assert response.status_code == 200, response.text
    return response.json()


def test_wish_is_unique_and_state_is_read_from_database(catalog):
    client, _, _ = catalog
    params = {"media_type": "movie", "tmdb_id": 1}
    assert client.get("/library/state", params=params).json()["status"] is None
    first = add(client)
    assert first["rating"] is None and first["score"] is None
    assert add(client)["id"] == first["id"]
    assert client.get("/library/state", params=params).json() == {
        "item_id": first["id"], "status": "wish", "rating": None, "score": None,
    }
    page = client.get("/library?status=wish").json()
    assert page["total"] == 1 and page["counts"] == {"wish": 1, "watched": 0}


def test_all_five_integer_ratings_have_corresponding_ten_point_scores(catalog):
    client, _, _ = catalog
    for stars in range(1, 6):
        item = add(client, "watched", tmdb_id=100+stars, rating=stars)
        assert item["rating"] == stars and item["score"] == stars * 2


def test_skip_rating_is_watched_and_cannot_be_overwritten_by_duplicate(catalog):
    client, _, _ = catalog
    item = add(client, "watched")
    assert item["rating"] is None and item["score"] is None
    again = add(client, "watched", rating=5)
    assert again["id"] == item["id"] and again["rating"] is None
    assert client.get("/library").json()["counts"]["watched"] == 1


def test_watched_does_not_downgrade_or_change_existing_score(catalog):
    client, _, _ = catalog
    item = add(client, "watched", rating=4)
    assert add(client)["status"] == "watched"
    assert add(client, "watched", rating=1)["rating"] == 4
    again = client.post(f"/library/{item['id']}/watched", json={"rating": 2}).json()
    assert again["rating"] == 4
    assert client.get("/library").json()["counts"] == {"wish": 0, "watched": 1}


def test_wish_can_be_marked_watched_without_any_new_tmdb_request(catalog):
    client, _, calls = catalog
    wish = add(client)
    before = calls.copy()
    response = client.post(f"/library/{wish['id']}/watched", json={"rating": 3})
    assert response.status_code == 200
    assert response.json()["id"] == wish["id"]
    assert response.json()["status"] == "watched" and response.json()["score"] == 6
    assert calls == before
    assert client.get("/library").json()["counts"] == {"wish": 0, "watched": 1}
    second = add(client, tmdb_id=2)
    skipped = add(client, "watched", tmdb_id=2)
    assert skipped["id"] == second["id"] and skipped["rating"] is None


def test_half_stars_and_out_of_range_scores_are_rejected(catalog):
    client, _, _ = catalog
    for value in [0, 6, 4.5, "4", True]:
        assert client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "watched", "rating": value}).status_code == 422
    assert client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "wish", "rating": 3}).status_code == 422


def test_pagination_search_and_tv_filter_keep_global_counts(catalog):
    client, _, _ = catalog
    for movie_id in range(30, 45):
        add(client, "watched", tmdb_id=movie_id)
    add(client, media_type="tv")
    add(client, media_type="season", season_number=2)
    first = client.get("/library?status=watched&media_type=movie").json()
    second = client.get("/library?status=watched&media_type=movie&page=2").json()
    assert first["total"] == 15 and len(first["items"]) == 12 and len(second["items"]) == 3
    assert not {item["id"] for item in first["items"]}.intersection(item["id"] for item in second["items"])
    tv = client.get("/library?status=wish&media_type=tv&query=series").json()
    assert tv["total"] == 2 and tv["counts"] == {"wish": 2, "watched": 15}
    assert {item["catalog"]["media_type"] for item in tv["items"]} == {"tv", "season"}
    assert client.get("/library?query=no-such-film").json()["total"] == 0


def test_library_survives_app_restart_without_tmdb_credentials(catalog, migrated_settings):
    client, _, _ = catalog
    item = add(client, "watched", rating=5)
    migrated_settings.tmdb_read_access_token = None
    with TestClient(create_app(migrated_settings)) as restarted:
        saved = restarted.get("/library").json()
        assert saved["items"][0]["id"] == item["id"]
        assert saved["items"][0]["score"] == 10
        state = restarted.get("/library/state?media_type=movie&tmdb_id=1").json()
        assert state["status"] == "watched"


def test_missing_library_item_returns_not_found(catalog):
    client, _, _ = catalog
    assert client.post("/library/999/watched", json={"rating": None}).status_code == 404
