import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_multitenant_migration_upgrades_a_fresh_database():
    database = Path(f".migration-{uuid.uuid4().hex}.db").resolve()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")

    try:
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        tables = set(inspect(engine).get_table_names())
        engine.dispose()
        assert {
            "alembic_version",
            "tenant_account",
            "user_identity",
        } <= tables
    finally:
        database.unlink(missing_ok=True)


def test_multitenant_migration_preserves_existing_inbox_data():
    database = Path(f".migration-{uuid.uuid4().hex}.db").resolve()
    url = f"sqlite:///{database.as_posix()}"
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE inbox_email (id INTEGER PRIMARY KEY, account_id TEXT)")
            )
            connection.execute(text("INSERT INTO inbox_email (id, account_id) VALUES (1, 'test')"))

        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")

        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT account_id FROM inbox_email WHERE id = 1")) == "test"
            )
        assert "tenant_account" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        database.unlink(missing_ok=True)
