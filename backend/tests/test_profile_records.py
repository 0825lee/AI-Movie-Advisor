from datetime import datetime

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.library_models import UserItem
from app.main import create_app
from app.profile_record_models import ProfileRecord
from app.profile_records import PROFILE_FIELDS, backfill_from_export
from conftest import migration_config
from test_catalog import catalog  # noqa: F401
from test_imports import create, finish, record


def test_import_preserves_six_original_fields_and_exposes_comments(catalog):
    client, engine, calls = catalog
    watched = {**record(), "originalTitle": "", "rating": 8, "markedAt": "", "info": "2010(美国) /  Actor  / 美国 / Director / 100分钟", "comment": "  原始评论\n保留换行和空格。  "}
    wish = {**record("Other", "2", status="wish"), "rating": None, "comment": "想看的理由"}
    finish(client, create(client, [watched, wish]))
    expected = {key: watched[key] for key in PROFILE_FIELDS}
    assert client.get("/library/profile-input").json() == {"records": [expected]}
    assert client.get("/library").json()["items"][0]["comment"] == watched["comment"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProfileRecord)) == 2
    assert not calls


def test_manual_add_stores_comment_and_six_field_profile_data(catalog):
    client, _, _ = catalog
    response = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "watched", "rating": 5, "comment": "叙事很好，想再看一次。"})
    assert response.status_code == 200, response.text
    assert response.json()["comment"] == "叙事很好，想再看一次。"
    payload = client.get("/library/profile-input").json()["records"][0]
    assert set(payload) == set(PROFILE_FIELDS)
    assert payload["title"] == payload["originalTitle"] == "Alpha"
    assert payload["rating"] == 10 and payload["comment"] == response.json()["comment"]
    assert "Actor" in payload["info"] and "Director" in payload["info"]
    datetime.fromisoformat(payload["markedAt"])
    state = client.get("/library/state?media_type=movie&tmdb_id=1").json()
    assert state["comment"] == response.json()["comment"]


def test_skip_rating_still_saves_comment_and_wish_becomes_profile_input(catalog):
    client, _, _ = catalog
    wish = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "wish"}).json()
    assert client.get("/library/profile-input").json() == {"records": []}
    updated = client.post(f"/library/{wish['id']}/watched", json={"rating": None, "comment": "暂时不评分，但想记录感受。"})
    assert updated.status_code == 200, updated.text
    payload = client.get("/library/profile-input").json()["records"][0]
    assert payload["rating"] is None and payload["comment"] == "暂时不评分，但想记录感受。"
    assert updated.json()["id"] == wish["id"]


def test_imported_wish_keeps_source_info_and_comment_when_marked_watched(catalog):
    client, _, _ = catalog
    raw = {**record(status="wish"), "originalTitle": "", "rating": None, "comment": "原有想看评论"}
    finish(client, create(client, [raw]))
    wish = client.get("/library?status=wish").json()["items"][0]
    updated = client.post(f"/library/{wish['id']}/watched", json={"rating": 3}).json()
    payload = client.get("/library/profile-input").json()["records"][0]
    assert payload["info"] == raw["info"] and payload["originalTitle"] == ""
    assert payload["rating"] == 6 and payload["comment"] == "原有想看评论"
    assert updated["comment"] == "原有想看评论"


def test_duplicate_does_not_overwrite_rating_or_comment(catalog):
    client, _, _ = catalog
    finish(client, create(client, [{**record(), "rating": 8, "comment": "豆瓣原评论"}]))
    response = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "watched", "rating": 1, "comment": "不应覆盖"})
    assert response.status_code == 200
    assert response.json()["rating"] == 4 and response.json()["comment"] == "豆瓣原评论"
    payloads = client.get("/library/profile-input").json()["records"]
    assert len(payloads) == 1 and payloads[0]["rating"] == 8 and payloads[0]["comment"] == "豆瓣原评论"


def test_clear_cascades_to_all_profile_records_and_reimport_is_fresh(catalog):
    client, engine, _ = catalog
    finish(client, create(client, [{**record(), "comment": "旧评论"}, record("Other", "2", status="wish")]))
    assert client.delete("/library").json()["deleted"] == 2
    assert client.get("/library/profile-input").json() == {"records": []}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProfileRecord)) == 0
        assert session.scalar(select(func.count()).select_from(UserItem)) == 0
        assert session.scalar(select(func.count()).select_from(CatalogItem)) == 2
    finish(client, create(client, [{**record(), "comment": "新评论"}]))
    assert client.get("/library").json()["items"][0]["comment"] == "新评论"


def test_comments_and_profile_input_survive_restart_without_tmdb(catalog, migrated_settings):
    client, _, _ = catalog
    finish(client, create(client, [{**record(), "comment": "重启后也保留"}]))
    before = client.get("/library/profile-input").json()
    migrated_settings.tmdb_read_access_token = None
    with TestClient(create_app(migrated_settings)) as restarted:
        assert restarted.get("/library/profile-input").json() == before
        assert restarted.get("/library").json()["items"][0]["comment"] == "重启后也保留"


def test_migration_backfills_existing_records_and_preserves_personal_score(catalog, migrated_settings):
    client, engine, _ = catalog
    added = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "watched", "rating": 4}).json()
    command.downgrade(migration_config(migrated_settings), "0007")
    command.upgrade(migration_config(migrated_settings), "head")
    with Session(engine) as session:
        record = session.get(ProfileRecord, added["id"])
        assert record.payload["title"] == "Alpha" and record.payload["rating"] == 8
        assert record.payload["comment"] == ""
        assert session.get(UserItem, added["id"]).rating == 4


def test_backfill_keeps_changes_made_after_original_export(catalog):
    client, engine, _ = catalog
    raw = {**record(status="wish"), "originalTitle": "", "rating": None, "comment": "原始想看评论"}
    finish(client, create(client, [raw]))
    item = client.get("/library?status=wish").json()["items"][0]
    response = client.post(f"/library/{item['id']}/watched", json={"rating": 5, "comment": "后来写的观后评论"})
    assert response.status_code == 200
    with Session(engine) as session:
        assert backfill_from_export(session, [raw]) == 1
        session.commit()
    payload = client.get("/library/profile-input").json()["records"][0]
    assert payload["originalTitle"] == "" and payload["info"] == raw["info"]
    assert payload["rating"] == 10 and payload["comment"] == "后来写的观后评论"
    assert payload["markedAt"] != raw["markedAt"]
