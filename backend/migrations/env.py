from alembic import context

from app import catalog_models  # noqa: F401 -- register Alembic metadata
from app import library_models  # noqa: F401
from app import import_models  # noqa: F401
from app import profile_record_models  # noqa: F401
from app import profile_models  # noqa: F401
from app.config import Settings
from app.database import Base, create_database_engine, database_url

settings = context.config.attributes.get("settings") or Settings()

if context.is_offline_mode():
    context.configure(
        url=database_url(settings),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database_engine(settings)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
