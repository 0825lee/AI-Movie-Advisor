import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem
from app.douban_metadata import parse_info
from app.import_models import ImportJob, ImportRow
from app.import_parser import parse_record
from app.main import create_app
from test_catalog import catalog  # noqa: F401 -- 手动添加沿用现有 TMDB 模拟。


def record(title="Alpha", source_id="1", info="2010-01-01 / Actor / 美国 / Director / 100分钟 / 剧情 / Writer / 英语", stars=4, status="collect"):
    return dict(title=title, subjectId=source_id, info=info, stars=stars, status=status,
                markedAt="2025-01-02", url=f"https://movie.douban.com/subject/{source_id}/")


def create(client, records):
    response = client.post("/imports", json={"filename": "sample.json", "data": {"records": records}})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def finish(client, job_id):
    async def wait():
        await asyncio.wait_for(asyncio.shield(client.app.state.import_runner.task), 15)
    client.portal.call(wait)
    return client.get(f"/imports/{job_id}").json()


def test_parser_uses_stars_only_and_preserves_original_date():
    raw = {**record("Series", info="2012-04-01 / 剧情", stars=None), "originalTitle": "Series Season 2", "rating": 10}
    parsed = parse_record(raw)
    assert parsed.rating is None and parsed.season_number == 2 and parsed.year == 2012
    assert parsed.marked_at == int(datetime(2025, 1, 2, tzinfo=timezone(timedelta(hours=8))).timestamp())
    assert parse_record({**raw, "markedAt": ""}).marked_at is None
    assert parse_record(record("横道世之介")).original_title == "横道世之介"


def test_info_parser_separates_actors_directors_countries_and_writers():
    info = "2024-09-02(威尼斯电影节) / 2024-10-04(日本) / 栗原飒人 / 日高由起刀 / 日本 / 美国 / 空音央 / 113分钟 / 昨日青春 / 剧情 / 空音央 Neo Sora / 日语 / 汉语普通话"
    parsed = parse_info(info, "昨日青春")
    assert parsed["cast"] == [{"name": "栗原飒人"}, {"name": "日高由起刀"}]
    assert parsed["directors"] == [{"name": "空音央"}]
    assert parsed["countries"] == [{"name": "日本"}, {"name": "美国"}]
    assert parsed["genres"] == [{"name": "剧情"}]
    assert parsed["languages"] == ["日语", "汉语普通话"]
    assert parsed["runtime"] == 113 and parsed["info"] == info


def test_director_segment_removes_website_series_name_and_dates():
    parsed = parse_info("2010(美国) / Actor / 美国 / abc.go.com/show / Director A / Director B / Series / 2010-05-20 20:00 / 50分钟 / Series / 剧情 / Writer / 英语", "Series 第二季")
    assert parsed["directors"] == [{"name": "Director A"}, {"name": "Director B"}]
    missing = parse_info("2026(美国) / Actor / 美国 / 瑞克和莫蒂 / 22分钟 / 瑞克和莫蒂 / 喜剧 / 动画 / 英语", "瑞克和莫蒂 第九季")
    assert missing["directors"] == []


def test_multiple_runtimes_and_missing_runtime_or_info():
    parsed = parse_info("2002(中国大陆/香港) / 李连杰 / 中国大陆 / 中国香港 / 张艺谋 / 93分钟(公映版) / 110分钟(导演版) / 剧情 / 编剧 / 汉语普通话", "英雄")
    assert parsed["directors"] == [{"name": "张艺谋"}] and parsed["runtime"] == 93
    parsed = parse_info("2030(美国) / 迈尔斯·特勒 / 美国 / 蒂姆·米勒 / 文森佐·纳塔利 / 神经漫游者 / 科幻 / 威廉·吉布森 William Gibson / 英语", "神经漫游者")
    assert parsed["directors"] == [{"name": "蒂姆·米勒"}, {"name": "文森佐·纳塔利"}]
    assert parsed["runtime"] is None
    assert parse_info("", "电锯人")["cast"] == []


def test_file_import_needs_no_tmdb_and_keeps_missing_data(catalog):
    client, _, calls = catalog
    rows = [record(), {**record("Series 第二季", "2", "2012-04-01", None), "originalTitle": "Series Season 2", "rating": 10, "markedAt": ""}, record("未收录作品", "3", ""), {"subjectId": "4"}]
    job_id = create(client, rows)
    summary = finish(client, job_id)
    assert summary["status"] == "completed" and summary["processed"] == 4
    assert summary["counts"] == {"added": 3, "upgraded": 0, "duplicate": 0, "skipped": 0, "failed": 1}
    assert not calls
    page = client.get("/library").json()
    assert page["counts"] == {"wish": 0, "watched": 3}
    season = next(item for item in page["items"] if item["catalog"]["season_number"] == 2)
    assert season["rating"] is None and season["marked_at"] is None
    assert season["catalog"]["tmdb_id"] is None
    assert season["catalog"]["source_url"] == "https://movie.douban.com/subject/2/"
    assert season["catalog"]["source_name"] == "豆瓣"
    assert client.get(f"/imports/{job_id}/rows?outcome=failed").json()["total"] == 1


def test_offline_import_without_any_api_credentials(migrated_settings):
    app = create_app(migrated_settings)
    with TestClient(app) as client:
        async def forbidden(*args, **kwargs):
            raise AssertionError("Import must not call TMDB")
        app.state.tmdb.get = forbidden
        job_id = create(client, [record()])
        assert finish(client, job_id)["counts"]["added"] == 1
        work = client.get("/library").json()["items"][0]["catalog"]
        assert work["directors"] == [{"id": None, "name": "Director"}]
        assert work["cast"] == [{"id": None, "name": "Actor"}]


def test_import_requires_empty_library_and_valid_records_array(catalog):
    client, _, _ = catalog
    assert client.post("/imports", json={"filename": "bad.json", "data": {"records": {}}}).status_code == 400
    finish(client, create(client, [record()]))
    assert client.post("/imports", json={"filename": "sample.json", "data": {"records": [record()]}}).status_code == 409


def test_cross_source_state_and_manual_add_reuse_imported_record(catalog):
    client, _, calls = catalog
    finish(client, create(client, [{**record("中文名"), "originalTitle": "Alpha"}]))
    imported = client.get("/library").json()["items"][0]
    state = client.get("/library/state?media_type=movie&tmdb_id=1").json()
    assert state["status"] == "watched" and state["item_id"] == imported["id"]
    duplicate = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "wish"}).json()
    assert duplicate["id"] == imported["id"] and duplicate["rating"] == 4
    assert duplicate["catalog"]["source_name"] == "豆瓣"
    assert client.get("/library").json()["total"] == 1
    assert calls["/movie/1"] == 1


def test_imported_wish_upgrades_without_replacing_source_or_metadata(catalog):
    client, _, _ = catalog
    finish(client, create(client, [record(status="wish")]))
    before = client.get("/library?status=wish").json()["items"][0]
    updated = client.post("/library/manual", json={"media_type": "movie", "tmdb_id": 1, "status": "watched", "rating": 5}).json()
    assert updated["id"] == before["id"] and updated["score"] == 10
    assert updated["catalog"]["source_name"] == "豆瓣"
    assert updated["catalog"]["directors"][0]["name"] == "Director"


def test_same_name_different_year_and_different_seasons_are_independent(catalog):
    client, _, _ = catalog
    finish(client, create(client, [record("Alpha", "1", "2020-01-01"), record("Series 第一季", "2", "2010-01-01"), record("Series 第二季", "3", "2012-01-01")]))
    assert client.get("/library/state?media_type=movie&tmdb_id=1").json()["status"] is None
    one = client.get("/library/state?media_type=season&tmdb_id=1&season_number=1").json()
    two = client.get("/library/state?media_type=season&tmdb_id=1&season_number=2").json()
    assert one["status"] == two["status"] == "watched" and one["item_id"] != two["item_id"]


def test_pause_resume_preserves_committed_rows(catalog, monkeypatch):
    client, _, _ = catalog
    runner = client.app.state.import_runner
    process = runner.process
    second_started = asyncio.Event()
    async def paused_process(row_id):
        if runner.summary(runner.active_job_id).processed == 1:
            second_started.set()
            await asyncio.sleep(60)
        await process(row_id)
    monkeypatch.setattr(runner, "process", paused_process)
    job_id = create(client, [record(), record("Other", "2")])
    client.portal.call(second_started.wait)
    assert client.delete("/library").status_code == 409
    assert client.post(f"/imports/{job_id}/pause").json()["processed"] == 1
    monkeypatch.setattr(runner, "process", process)
    assert client.post(f"/imports/{job_id}/resume").status_code == 200
    assert finish(client, job_id)["counts"]["added"] == 2
    assert client.delete("/library").json()["deleted"] == 2
    assert finish(client, create(client, [record()]))["counts"]["added"] == 1


def test_restart_preserves_details_and_clear_cancels_old_job(catalog, migrated_settings):
    client, engine, _ = catalog
    job_id = create(client, [record()])
    finish(client, job_id)
    with Session(engine) as session:
        session.get(ImportJob, job_id).status = "running"
        session.commit()
    migrated_settings.tmdb_read_access_token = None
    with TestClient(create_app(migrated_settings)) as restarted:
        job = restarted.get("/imports").json()[0]
        assert job["status"] == "paused" and job["processed"] == 1
        work = restarted.get("/library").json()["items"][0]["catalog"]
        assert work["source_name"] == "豆瓣" and work["directors"][0]["name"] == "Director"
        assert restarted.delete("/library").json()["deleted"] == 1
        assert restarted.get(f"/imports/{job_id}").json()["status"] == "cancelled"
        assert restarted.post(f"/imports/{job_id}/resume").status_code == 409


def test_resume_storage_keeps_profile_fields_and_excludes_unused_fields(catalog):
    client, engine, _ = catalog
    raw = {**record(), "comment": "private comment", "tags": ["private tag"], "rating": 8, "cover": "unused"}
    job_id = create(client, [raw])
    finish(client, job_id)
    with Session(engine) as session:
        row = session.scalar(select(ImportRow).where(ImportRow.job_id == job_id))
        assert not set(row.payload).intersection({"tags", "cover"})
        assert row.payload["comment"] == "private comment" and row.payload["rating"] == 8
        work = session.get(CatalogItem, row.catalog_item_id)
        assert not set(work.details).intersection({"comment", "tags", "rating", "cover"})


def test_duplicate_original_name_year_uses_one_record(catalog):
    client, _, _ = catalog
    finish(client, create(client, [record("不同中文名", "1"), {**record("另一译名", "2"), "originalTitle": "不同中文名"}]))
    assert client.get("/library").json()["total"] == 1
