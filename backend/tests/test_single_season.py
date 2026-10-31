from alembic import command
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.main import create_app
from app.library_models import UserItem
from conftest import migration_config
from test_catalog import catalog  # noqa: F401
from test_imports import create, finish, record


def test_single_formal_season_uses_series_name_and_link_but_special_stays_separate(catalog):
    client, _, _ = catalog
    result = client.get("/catalog/search?query=Solo&media_type=tv").json()["items"]
    formal, special = result
    assert formal["title"] == formal["original_title"] == "Solo"
    assert formal["season_number"] == 1 and special["season_number"] == 0
    assert special["original_title"] == "Solo · Season 0"
    work = client.get("/catalog/details?media_type=season&tmdb_id=2&season_number=1").json()
    assert work["title"] == work["original_title"] == "Solo"
    assert work["tmdb_url"] == "https://www.themoviedb.org/tv/2"


@pytest.mark.parametrize("title", ["Solo", "Solo 第一季"])
def test_imported_work_blocks_single_season_duplicate(catalog, title):
    client, _, _ = catalog
    finish(client, create(client, [record(title)]))
    imported = client.get("/library").json()["items"][0]
    params = {"media_type": "season", "tmdb_id": 2, "season_number": 1}
    state = client.get("/library/state", params=params).json()
    assert state["status"] == "watched" and state["item_id"] == imported["id"]
    added = client.post("/library/manual", json={**params, "status": "watched", "rating": 1}).json()
    assert added["id"] == imported["id"] and added["rating"] == 4
    assert client.get("/library").json()["total"] == 1


def test_imported_first_season_of_multi_season_series_keeps_season_identity(catalog):
    client, _, _ = catalog
    finish(client, create(client, [{**record("Series 第一季"), "originalTitle": "Series Season 1"}]))
    items = client.get("/catalog/search?query=Series").json()["items"]
    assert [item["season_number"] for item in items] == [1, 2, 0]
    assert items[0]["original_title"] == "Series · Season 1"
    assert client.get("/library/state?media_type=season&tmdb_id=1&season_number=1").json()["status"] == "watched"
    assert client.get("/library/state?media_type=season&tmdb_id=1&season_number=2").json()["status"] is None


def test_migration_updates_existing_single_season_cache_without_losing_rating(catalog, migrated_settings):
    client, engine, _ = catalog
    added = client.post("/library/manual", json={"media_type": "season", "tmdb_id": 2, "season_number": 1, "status": "watched", "rating": 5}).json()
    work_id = added["catalog"]["catalog_id"]
    with Session(engine) as session:
        work = session.get(CatalogItem, work_id)
        work.title, work.original_title = "Solo · 第 1 季", "Solo · Season 1"
        work.match_key = "solo:2010:season:1"
        details = {**work.details, "title": work.title, "original_title": work.original_title,
                   "tmdb_url": "https://www.themoviedb.org/tv/2/season/1"}
        details.pop("single_season")
        work.details = details
        session.execute(text("UPDATE alembic_version SET version_num='0005'"))
        session.commit()
    command.upgrade(migration_config(migrated_settings), "head")
    with TestClient(create_app(migrated_settings)) as restarted:
        saved = restarted.get("/library").json()["items"][0]
        assert saved["id"] == added["id"] and saved["rating"] == 5
        assert saved["catalog"]["title"] == "Solo"
        assert saved["catalog"]["source_url"] == "https://www.themoviedb.org/tv/2"
    with Session(engine) as session:
        assert session.get(CatalogItem, work_id).match_key == "solo:2010"
        assert len(session.scalars(select(UserItem)).all()) == 1
