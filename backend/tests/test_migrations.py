"""The Alembic migrations, run against a real (throwaway) database: a SQLite file, or
TEST_DATABASE_URL when it's set (see conftest.py)."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import BACKEND_DIR
from app.db import Base, create_db_engine, ensure_database_is_up_to_date

BASELINE = "99d09efe8ba7"  # migrations/versions/99d09efe8ba7_initial_schema.py


@pytest.fixture
def database(empty_database_url: str):
    """An empty database, plus an Alembic config pointed at it."""
    url = empty_database_url
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
            "VALUES (1, 'Lab L1', '2026-09-21', TRUE, FALSE, 'pending_review')"
        ))

    command.upgrade(config, "head")

    with engine.begin() as connection:
        rows = connection.execute(text("SELECT title, sync_key FROM extracted_events")).all()
        # uploads was rebuilt to allow the new status: its rows (and the events' links to them) survive.
        connection.execute(text("UPDATE uploads SET status = 'processing' WHERE id = 1"))
    assert rows == [("Lab L1", None)]  # data kept; the new column starts empty


def test_the_migrated_status_constraint_still_rejects_unknown_values(database):
    # Changing the allowed statuses must replace the CHECK constraint, not just drop it.
    config, engine = database
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))
    with pytest.raises(IntegrityError, match="(?i)check constraint"), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO uploads (user_id, filename, raw_text, status) VALUES (1, 'a.pdf', '...', 'bogus')"
        ))


def test_undoing_the_processing_status_fails_uploads_that_were_mid_extraction(database):
    # The older schema doesn't allow 'processing', so the downgrade has to change those rows first.
    config, engine = database
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(text(
            "INSERT INTO uploads (user_id, filename, raw_text, status) VALUES (1, 'a.pdf', '...', 'processing')"
        ))

    command.downgrade(config, "e6f01ca19a79")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM uploads")).scalar_one() == "failed"


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
