from alembic import context

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
