from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        movie_internal_token="test-internal-token",
        dify_smoke_api_key=None,
        dify_profile_api_key=None,
        tmdb_read_access_token=None,
    )


def migration_config(settings: Settings) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["settings"] = settings
    return config


@pytest.fixture
def migrated_settings(settings: Settings) -> Settings:
    command.upgrade(migration_config(settings), "head")
    return settings
