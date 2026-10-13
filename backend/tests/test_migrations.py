"""The Alembic migrations, run against real (throwaway) SQLite files."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from app.config import BACKEND_DIR
from app.db import Base, create_db_engine, ensure_database_is_up_to_date

BASELINE = "99d09efe8ba7"  # migrations/versions/99d09efe8ba7_initial_schema.py


@pytest.fixture
def database(tmp_path: Path):
    """An empty SQLite file, plus an Alembic config pointed at it."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    engine = create_db_engine(url)
    yield config, engine
    engine.dispose()


def test_migrations_build_exactly_what_the_models_describe(database):
    # If someone edits models.py but forgets to write a migration, this fails.
    config, engine = database
    command.upgrade(config, "head")

    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []


def test_upgrading_an_existing_database_keeps_its_data(database):
    # The path the real app.db takes: it already has the original tables and data.
    config, engine = database
    command.upgrade(config, BASELINE)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(text(
            "INSERT INTO uploads (id, user_id, filename, raw_text, status) VALUES (1, 1, 'a.pdf', '...', 'extracted')"
        ))
        connection.execute(text(
            "INSERT INTO extracted_events (upload_id, title, start_date, date_is_approximate, included, status) "
            "VALUES (1, 'Lab L1', '2026-09-21', 1, 0, 'pending_review')"
        ))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT title, sync_key FROM extracted_events")).all()
    assert rows == [("Lab L1", None)]  # data kept; the new column starts empty


def test_every_migration_can_be_undone(database):
    config, engine = database
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_the_app_refuses_to_start_on_a_database_that_is_behind(database):
    config, engine = database
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        ensure_database_is_up_to_date(engine)  # brand-new, never migrated

    command.upgrade(config, BASELINE)
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        ensure_database_is_up_to_date(engine)  # one migration behind

    command.upgrade(config, "head")
    ensure_database_is_up_to_date(engine)  # up to date: no error
