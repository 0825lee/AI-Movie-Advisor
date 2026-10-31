import pytest
from alembic import command
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import migration_config


def test_health_reads_actual_migrated_database(migrated_settings):
    with TestClient(create_app(migrated_settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "database_revision": "0010",
        "dify_configured": False,
        "tmdb_configured": False,
    }
    assert migrated_settings.sqlite_path.is_file()


def test_health_does_not_claim_unmigrated_database_is_ready(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 503


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, 401),
        ({"X-Internal-Token": "wrong-token"}, 401),
        ({"X-Internal-Token": "test-internal-token"}, 200),
    ],
)
def test_internal_health_requires_token(migrated_settings, headers, expected):
    with TestClient(create_app(migrated_settings)) as client:
        assert client.get("/internal/health", headers=headers).status_code == expected


def test_unconfigured_internal_token_does_not_disable_auth(settings):
    settings.movie_internal_token = None
    with TestClient(create_app(settings)) as client:
        assert client.get("/internal/health").status_code == 503


def test_missing_dify_key_is_reported_without_upstream_request(migrated_settings):
    with TestClient(create_app(migrated_settings)) as client:
        response = client.post(
            "/internal/dify/check",
            headers={"X-Internal-Token": "test-internal-token"},
            json={"inputs": {"query": "hello"}},
        )
    assert response.status_code == 503
    assert "DIFY_SMOKE_API_KEY" in response.json()["detail"]


def test_migration_can_downgrade_and_upgrade(migrated_settings):
    config = migration_config(migrated_settings)
    command.downgrade(config, "base")
    with TestClient(create_app(migrated_settings)) as client:
        assert client.get("/health").status_code == 503
    command.upgrade(config, "head")
    with TestClient(create_app(migrated_settings)) as client:
        assert client.get("/health").json()["database_revision"] == "0010"
