from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_path: Path = Path("data/movie_advisor.db")
    backend_port: int = 8000
    dify_base_url: str = "http://127.0.0.1:18080/v1"
    dify_timeout_seconds: float = 120
    dify_smoke_api_key: SecretStr | None = None
    dify_profile_api_key: SecretStr | None = None
    dify_request_api_key: SecretStr | None = None
    dify_personalized_api_key: SecretStr | None = None
    movie_internal_token: SecretStr | None = None
    tmdb_read_access_token: SecretStr | None = None

    @property
    def sqlite_path(self) -> Path:
        if self.database_path.is_absolute():
            return self.database_path
        return BACKEND_DIR / self.database_path
