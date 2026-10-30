import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.import_models import ImportJob, ImportRow
from app.import_parser import parse_record
from app.main import create_app
from app.tmdb_client import TMDBError
from test_catalog import catalog  # noqa: F401 -- shared TMDB fixture


def record(title="Alpha", source_id="1", info="2010-01-01 / 剧情", stars=4, status="collect"):
    return dict(title=title, subjectId=source_id, info=info, stars=stars, status=status, markedAt="2025-01-02", url=f"https://movie.douban.com/subject/{source_id}/")


def create(client, records):
    response = client.post("/imports", json={"filename": "sample.json", "data": {"records": records}})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def finish(client, job_id):
    async def wait():
        task = client.app.state.import_runner.task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), 15)
    client.portal.call(wait)
    return client.get(f"/imports/{job_id}").json()


def test_parser_uses_stars_only_and_preserves_original_date():
    raw = {**record("Series", info="2012-04-01 / 剧情", stars=None), "originalTitle": "Series Season 2", "rating": 10}
    parsed = parse_record(raw)
    assert parsed.rating is None and parsed.season_number == 2 and parsed.year == 2012
    assert parsed.marked_at == int(datetime(2025, 1, 2, tzinfo=timezone(timedelta(hours=8))).timestamp())
    assert parse_record({**raw, "markedAt": ""}).marked_at is None


def test_file_import_records_results_without_guessing_missing_ratings(catalog):
    client, _, _ = catalog
    rows = [record(), {**record("Series 第二季", "2", "2012-04-01", None), "rating": 10, "markedAt": ""}, record("nothing", "3"), {"subjectId": "4"}]
    job_id = create(client, rows)
    summary = finish(client, job_id)
    assert summary["status"] == "completed" and summary["processed"] == 4
    assert summary["counts"] == {"added": 2, "upgraded": 0, "duplicate": 0, "skipped": 1, "failed": 1}
    library = client.get("/library").json()
    assert library["counts"] == {"wish": 0, "watched": 2}
    season = next(item for item in library["items"] if item["catalog"]["media_type"] == "season")
    assert season["rating"] is None and season["marked_at"] is None and season["source"] == "douban"
    assert next(item for item in library["items"] if item["catalog"]["media_type"] == "movie")["score"] == 8
    report = client.get(f"/imports/{job_id}/rows").json()
    assert report["total"] == 4 and [r["outcome"] for r in report["items"]] == ["added", "added", "skipped", "failed"]
    assert client.get(f"/imports/{job_id}/rows?outcome=skipped").json()["total"] == 1


def test_import_requires_empty_library_and_valid_records_array(catalog):
    client, _, _ = catalog
    assert client.post("/imports", json={"filename": "bad.json", "data": {"records": {}}}).status_code == 400
    assert client.get("/imports").json() == []
    client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "wish"})
    response = client.post("/imports", json={"filename": "sample.json", "data": {"records": [record()]}})
    assert response.status_code == 409


def test_network_pause_and_resume_processes_only_unfinished_rows(catalog, monkeypatch):
    client, _, _ = catalog
    runner = client.app.state.import_runner
    original = runner.catalog.match
    visited = []
    unavailable = True

    async def match(body):
        visited.append(body.title)
        if body.title == "Series 第二季" and unavailable:
            raise TMDBError(502, "TMDB 连接中断。")
        return await original(body)

    monkeypatch.setattr(runner.catalog, "match", match)
    job_id = create(client, [record(), record("Series 第二季", "2", "2012-04-01")])
    paused = finish(client, job_id)
    assert paused["status"] == "paused" and paused["processed"] == 1
    assert client.get(f"/imports/{job_id}/rows?outcome=pending").json()["total"] == 1
    unavailable = False
    assert client.post(f"/imports/{job_id}/resume").status_code == 200
    done = finish(client, job_id)
    assert done["status"] == "completed" and done["counts"]["added"] == 2
    assert visited.count("Alpha") == 1


def test_unmarked_season_uses_first_of_multiple_formal_seasons(catalog):
    client, _, _ = catalog
    job_id = create(client, [record("Series", "1", "2010-01-01")])
    assert finish(client, job_id)["status"] == "completed"
    item = client.get("/library").json()["items"][0]
    assert item["catalog"]["media_type"] == "season" and item["catalog"]["season_number"] == 1
    assert "第一季" in client.get(f"/imports/{job_id}/rows").json()["items"][0]["message"]


def test_unmarked_season_uses_the_only_formal_season(catalog, monkeypatch):
    client, _, _ = catalog
    runner = client.app.state.import_runner
    original = runner.catalog.detail

    async def detail(ref, refresh=False):
        item = await original(ref, refresh)
        if item.media_type == "tv":
            item = item.model_copy(update={"seasons": [s for s in item.seasons if s.season_number == 1]})
        return item

    monkeypatch.setattr(runner.catalog, "detail", detail)
    job_id = create(client, [record("Series", info="2010-01-01")])
    assert finish(client, job_id)["counts"]["added"] == 1
    assert "唯一正式季" in client.get(f"/imports/{job_id}/rows").json()["items"][0]["message"]


def test_pause_allows_clearing_and_ends_old_job(catalog, monkeypatch):
    client, _, _ = catalog
    runner = client.app.state.import_runner

    async def waiting_match(body):
        await asyncio.sleep(60)

    monkeypatch.setattr(runner.catalog, "match", waiting_match)
    job_id = create(client, [record()])
    assert client.delete("/library").status_code == 409
    assert client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "wish"}).status_code == 409
    assert client.post(f"/imports/{job_id}/pause").json()["status"] == "paused"
    assert client.delete("/library").status_code == 200
    assert client.get(f"/imports/{job_id}").json()["status"] == "cancelled"
    assert client.post(f"/imports/{job_id}/resume").status_code == 409


def test_reimport_after_clear_reuses_source_mapping_without_remote_lookup(catalog):
    client, _, calls = catalog
    job_id = create(client, [record()])
    assert finish(client, job_id)["counts"]["added"] == 1
    client.delete("/library")
    before = calls.copy()
    new_job = create(client, [record()])
    assert finish(client, new_job)["counts"]["added"] == 1
    assert calls == before


def test_restart_recovers_running_job_as_paused_and_preserves_checkpoint(catalog, migrated_settings):
    client, engine, _ = catalog
    job_id = create(client, [record()])
    finish(client, job_id)
    with Session(engine) as session:
        session.get(ImportJob, job_id).status = "running"
        session.commit()
    with TestClient(create_app(migrated_settings)) as restarted:
        jobs = restarted.get("/imports").json()
        assert jobs[0]["id"] == job_id and jobs[0]["status"] == "paused"
        assert jobs[0]["processed"] == 1


def test_resume_storage_excludes_comments_tags_and_raw_rating(catalog):
    client, engine, _ = catalog
    raw = {**record(), "comment": "private comment", "tags": ["private tag"], "rating": 8, "cover": "unused"}
    job_id = create(client, [raw])
    finish(client, job_id)
    with Session(engine) as session:
        row = session.scalar(select(ImportRow).where(ImportRow.job_id == job_id))
        assert not set(row.payload).intersection({"comment", "tags", "rating", "cover"})
    assert client.get(f"/imports/{job_id}/rows").json()["items"][0]["matched_title"] == "Alpha"
