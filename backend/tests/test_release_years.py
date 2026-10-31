from alembic import command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.douban_metadata import release_years
from app.library_models import UserItem
from conftest import migration_config
from test_catalog import catalog  # noqa: F401
from test_imports import create, finish, record


def test_release_years_only_reads_leading_release_dates():
    info = "2023-10-23(东京国际电影节) / 2024-04-11(中国香港) / 2024(中国大陆) / Actor / 中国香港 / Director / 2025-05-01 / 112分钟"
    assert release_years(info) == [2023, 2024]
    assert release_years("", 2010) == [2010]


def test_any_recorded_release_year_matches_without_changing_display_year(catalog):
    client, _, _ = catalog
    finish(client, create(client, [record(info="2009-10-23(电影节) / 2010-04-11(美国) / Actor / 美国 / Director / 100分钟", status="wish")]))
    before = client.get("/library?status=wish").json()["items"][0]
    state = client.get("/library/state?media_type=movie&tmdb_id=1").json()
    assert state["status"] == "wish" and state["item_id"] == before["id"]
    added = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "wish"}).json()
    assert added["id"] == before["id"]
    assert added["catalog"]["year"] == 2009
    assert client.get("/library?status=wish").json()["total"] == 1


def test_adjacent_but_unrecorded_year_does_not_match(catalog):
    client, _, _ = catalog
    finish(client, create(client, [record(info="2009-01-01(电影节)")]))
    assert client.get("/library/state?media_type=movie&tmdb_id=1").json()["status"] is None


def test_release_year_aliases_do_not_merge_different_seasons(catalog):
    client, _, _ = catalog
    info = "2009-01-01(电影节) / 2010-01-01(美国) / 2012-01-01(重映)"
    finish(client, create(client, [{**record("Series 第一季", info=info), "originalTitle": "Series Season 1"}]))
    assert client.get("/library/state?media_type=season&tmdb_id=1&season_number=1").json()["status"] == "watched"
    assert client.get("/library/state?media_type=season&tmdb_id=1&season_number=2").json()["status"] is None


def test_migration_backfills_year_aliases_without_reimport_or_rating_change(catalog, migrated_settings):
    client, engine, _ = catalog
    finish(client, create(client, [record(info="2009(电影节) / 2010(美国)")]))
    before = client.get("/library").json()["items"][0]
    with Session(engine) as session:
        work = session.scalar(select(CatalogItem).where(CatalogItem.tmdb_id.is_(None)))
        data = dict(work.details)
        data.pop("release_years")
        data.pop("match_keys")
        work.details = data
        session.commit()
    command.downgrade(migration_config(migrated_settings), "0006")
    command.upgrade(migration_config(migrated_settings), "head")
    state = client.get("/library/state?media_type=movie&tmdb_id=1").json()
    assert state["item_id"] == before["id"] and state["rating"] == 4
    with Session(engine) as session:
        item = session.get(UserItem, before["id"])
        work = session.get(CatalogItem, item.catalog_item_id)
        assert work.year == 2009 and work.details["release_years"] == [2009, 2010]
