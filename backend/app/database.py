from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings


class Base(DeclarativeBase):
    pass


def database_url(settings: Settings) -> URL:
    return URL.create("sqlite", database=str(settings.sqlite_path))


def create_database_engine(settings: Settings) -> Engine:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        database_url(settings),
        connect_args={"check_same_thread": False},
    )
