from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem, SourceMapping
from app.catalog_service import parse_title
from app.main import create_app


def movie(tmdb_id=1, title="Alpha", year=2010):
    return dict(
        id=tmdb_id, title=title, original_title=title, release_date=f"{year}-01-01",
        overview="中文简介", original_language="en", poster_path="/alpha.jpg", runtime=100,
        genres=[{"id": 18, "name": "剧情"}], production_countries=[{"iso_3166_1": "US", "name": "美国"}],
        credits={"crew": [{"id": 9, "name": "Director", "job": "Director"}], "cast": [{"id": 8, "name": "Actor"}]},
        alternative_titles={"titles": [{"title": "Alt Alpha"}]},
    )


def series():
    return dict(
        id=1, name="Series", original_name="Series", first_air_date="2010-01-01",
        overview="整剧简介", original_language="en", poster_path=None,
        genres=[{"id": 18, "name": "剧情"}], production_countries=[], episode_run_time=[50],
        created_by=[{"id": 3, "name": "Creator"}], number_of_episodes=20,
        aggregate_credits={"cast": [{"id": 4, "name": "Series Actor"}], "crew": []},
        seasons=[dict(season_number=n, name=f"第 {n} 季", air_date=f"{y}-01-01", episode_count=10, poster_path=None) for n, y in [(0, 2009), (1, 2010), (2, 2012)]],
    )


@pytest.fixture
def catalog(migrated_settings):
    calls = Counter()

    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-tmdb-token"
        path = request.url.path.removeprefix("/3")
        calls[path] += 1
        if path == "/configuration":
            data = {"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}}
        elif path.startswith("/search/"):
            query = request.url.params["query"].casefold()
            assert request.url.params["include_adult"] == "false"
            if path == "/search/movie":
                data = {"results": [movie()] if "alpha" in query else [movie(10, "Shared", 2010), movie(20, "Shared", 2020)] if query == "shared" else []}
            else:
                data = {"results": [series()] if query == "series" else [{**series(), "id": 10, "name": "Shared", "original_name": "Shared"}] if query == "shared" else []}
            data["total_pages"] = 1 if data["results"] else 0
        elif path.startswith("/movie/"):
            movie_id = int(path.rsplit("/", 1)[-1])
            if movie_id in [401, 404, 429]:
                return httpx.Response(movie_id, json={"status_message": "upstream error"})
            data = movie(movie_id)
            if movie_id == 2:
                data.update(overview="English overview" if request.url.params["language"] == "en-US" else "", poster_path=None)
        elif path == "/tv/1":
            data = series()
        elif path.startswith("/tv/1/season/"):
            n = int(path.rsplit("/", 1)[-1])
            data = dict(id=100+n, name=f"第 {n} 季", season_number=n, air_date=f"{2012 if n == 2 else 2009 if n == 0 else 2010}-01-01",
                        overview="本季简介", poster_path=None, episodes=[{"id": 1}],
                        aggregate_credits={"cast": [{"id": 5, "name": "Season Actor"}], "crew": [{"id": 6, "name": "Season Director", "jobs": [{"job": "Director"}]}]})
        else:
            raise AssertionError("Unexpected request: " + path)
        return httpx.Response(200, json=data)

    migrated_settings.tmdb_read_access_token = SecretStr("test-tmdb-token")
    app = create_app(migrated_settings)
    with TestClient(app) as client:
        app.state.tmdb.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        yield client, app.state.engine, calls
        client.portal.call(app.state.tmdb.http.aclose)


def detail(client, media_type="movie", tmdb_id=1, **params):
    response = client.get("/catalog/details", params=dict(media_type=media_type, tmdb_id=tmdb_id, **params))
    assert response.status_code == 200, response.text
    return response.json()


def test_search_keeps_movie_and_tv_with_same_id_separate(catalog):
    client, _, _ = catalog
    result = client.get("/catalog/search", params={"query": "Shared"}).json()
    assert {(p["media_type"], p["tmdb_id"]) for p in result["items"]} == {("movie", 10), ("movie", 20), ("tv", 10)}


def test_detail_cache_refresh_and_confirmation_are_persistent(catalog, migrated_settings):
    client, engine, calls = catalog
    first = detail(client)
    assert first["confirmed"] is False
    assert first["directors"] == [{"id": 9, "name": "Director"}]
    assert client.get("/catalog/items").json()["total"] == 0
    assert detail(client)["catalog_id"] == first["catalog_id"]
    assert calls["/movie/1"] == 1
    for _ in range(2):
        assert client.post("/catalog/confirm", json={"media_type": "movie", "tmdb_id": 1}).json()["confirmed"]
    assert client.get("/catalog/items").json()["total"] == 1
    assert detail(client, refresh=True)["confirmed"]
    with Session(engine) as session:
        item = session.get(CatalogItem, first["catalog_id"])
        item.fetched_at = 0
        session.commit()
    assert detail(client)["confirmed"]
    assert calls["/movie/1"] == 3
    # 重建应用后仍读同一 SQLite；缓存命中不需要真实网络或令牌。
    migrated_settings.tmdb_read_access_token = None
    with TestClient(create_app(migrated_settings)) as restarted:
        assert detail(restarted)["confirmed"]
        assert restarted.get("/catalog/items").json()["total"] == 1


def test_movie_series_seasons_and_specials_have_distinct_identities(catalog):
    client, _, _ = catalog
    items = [detail(client), detail(client, "tv"), detail(client, "season", season_number=0), detail(client, "season", season_number=1), detail(client, "season", season_number=2)]
    assert len({item["catalog_id"] for item in items}) == 5
    assert items[1]["year"] == 2010 and items[4]["year"] == 2012
    assert items[4]["cast"] == [{"id": 5, "name": "Season Actor"}]
    assert items[4]["directors"] == [{"id": 6, "name": "Season Director"}]
    assert items[4]["overview"] == "本季简介"


def test_missing_chinese_overview_uses_english_and_missing_poster_stays_empty(catalog):
    client, _, _ = catalog
    item = detail(client, tmdb_id=2)
    assert item["overview"] == "English overview"
    assert item["overview_language"] == "en-US"
    assert item["poster_url"] is None


def test_matching_requires_unambiguous_name_year_and_type(catalog):
    client, _, _ = catalog
    def match(**body):
        r = client.post("/catalog/match", json=body)
        assert r.status_code == 200, r.text
        return r.json()
    assert match(title="Alpha", media_type="movie", year=2010)["status"] == "matched"
    assert match(title="Alt Alpha", media_type="movie", year=2010)["status"] == "matched"
    assert match(title="Alpha")["status"] == "missing_data"
    assert match(title="Alpha", year=2020)["status"] == "ambiguous"
    assert match(title="Shared", year=2010)["status"] == "ambiguous"
    assert match(title="Shared", media_type="movie", year=2010)["item"]["tmdb_id"] == 10
    assert match(title="nothing", year=2010)["status"] == "not_found"


def test_season_matching_uses_season_year_instead_of_series_first_air_year(catalog):
    client, _, _ = catalog
    result = client.post("/catalog/match", json={"title": "Series 第二季（2012）"}).json()
    assert result["status"] == "matched"
    assert result["item"]["media_type"] == "season"
    assert result["item"]["season_number"] == 2
    assert result["item"]["year"] == 2012
    assert client.post("/catalog/match", json={"title": "Series", "media_type": "season", "season_number": 99, "year": 2012}).json()["status"] == "not_found"
    assert client.post("/catalog/match", json={"title": "Series", "media_type": "season"}).json()["status"] == "missing_data"


def test_source_mapping_reused_and_not_silently_reassigned(catalog):
    client, engine, calls = catalog
    source = {"source_id": "123", "source_url": "https://movie.douban.com/subject/123/"}
    body = {"media_type": "movie", "tmdb_id": 1, "source": source}
    assert client.post("/catalog/confirm", json=body).status_code == 200
    before = calls.copy()
    result = client.post("/catalog/match", json={"title": "different spelling", "source": source}).json()
    assert result["status"] == "matched" and result["item"]["tmdb_id"] == 1
    assert calls == before
    assert client.post("/catalog/confirm", json={**body, "tmdb_id": 2}).status_code == 409
    with Session(engine) as session:
        assert len(session.scalars(select(SourceMapping)).all()) == 1


def test_movie_tools_require_auth_and_expose_movie_only_openapi(catalog):
    client, _, _ = catalog
    assert client.get("/internal/movies/search?query=Shared").status_code == 401
    headers = {"X-Internal-Token": "test-internal-token"}
    result = client.get("/internal/movies/search?query=Shared", headers=headers).json()
    assert all(item["media_type"] == "movie" for item in result["items"])
    assert client.get("/internal/movies/1", headers=headers).json()["media_type"] == "movie"
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/internal/movies/search"]["get"]["operationId"] == "search_movies"
    assert spec["paths"]["/internal/movies/{tmdb_id}"]["get"]["operationId"] == "get_movie_details"
    assert spec["paths"]["/internal/movies/search"]["get"]["security"] == [{"APIKeyHeader": []}]


@pytest.mark.parametrize(("upstream", "expected"), [(401, 502), (404, 404), (429, 503)])
def test_tmdb_errors_are_not_reported_as_empty_search_results(catalog, upstream, expected):
    client, _, _ = catalog
    assert client.get("/catalog/details", params={"media_type": "movie", "tmdb_id": upstream}).status_code == expected


def test_invalid_season_reference_is_rejected(catalog):
    client, _, _ = catalog
    assert client.get("/catalog/details?media_type=season&tmdb_id=1").status_code == 422
    assert client.post("/catalog/confirm", json={"media_type": "movie", "tmdb_id": 1, "season_number": 1}).status_code == 422


def test_title_parser_preserves_numeric_titles_and_understands_explicit_seasons():
    assert parse_title("2001: A Space Odyssey (1968)") == ("2001: A Space Odyssey", 1968, None)
    assert parse_title("Series 第十二季（2020）") == ("Series", 2020, 12)
    assert parse_title("Series Season 2") == ("Series", None, 2)
    assert parse_title("Series S00") == ("Series", None, 0)
