from alembic import command
from sqlalchemy import text

from app.database import create_database_engine
from conftest import migration_config


def test_upgrade_keeps_existing_library_source_mapping_and_import_report(settings):
    config = migration_config(settings)
    command.upgrade(config, "0004")
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO catalog_items
            (id,identity_key,media_type,tmdb_id,title,original_title,year,details,fetched_at)
            VALUES (7,'movie:1','movie',1,'Alpha','Alpha',2010,'{}',1)"""))
        connection.execute(text("""INSERT INTO user_items
            (id,catalog_item_id,status,rating,marked_at,source,created_at,updated_at)
            VALUES (3,7,'watched',4,1,'manual',1,1)"""))
        connection.execute(text("""INSERT INTO source_mappings
            (source,source_id,catalog_item_id) VALUES ('douban','123',7)"""))
        connection.execute(text("""INSERT INTO import_jobs
            (id,filename,status,total,created_at,updated_at) VALUES (1,'old.json','paused',1,1,1)"""))
        connection.execute(text("""INSERT INTO import_rows
            (job_id,row_number,title,payload,outcome,catalog_item_id)
            VALUES (1,1,'Alpha','{}','added',7)"""))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert connection.scalar(text("SELECT match_key FROM catalog_items WHERE id=7")) == "alpha:2010"
        assert connection.execute(text("SELECT catalog_item_id,rating FROM user_items WHERE id=3")).one() == (7, 4)
        assert connection.scalar(text("SELECT catalog_item_id FROM source_mappings")) == 7
        assert connection.scalar(text("SELECT catalog_item_id FROM import_rows")) == 7
    engine.dispose()


def test_nomination_migration_keeps_old_task_strategy_and_payload(settings):
    config = migration_config(settings)
    command.upgrade(config, "0010")
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recommendation_batches (id,request_text,shown_ids,created_at) VALUES ('old-batch','old request','[]',1)"))
        connection.execute(text("""INSERT INTO recommendation_tasks
            (id,batch_id,status,target_count,criteria,filters,result,created_at,updated_at)
            VALUES ('old-task','old-batch','prepared',3,'{"directors":[]}','{}',NULL,1,1)"""))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT strategy,criteria,status FROM recommendation_tasks WHERE id='old-task'")).one() == (
            "criteria", '{"directors":[]}', "prepared",
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()
