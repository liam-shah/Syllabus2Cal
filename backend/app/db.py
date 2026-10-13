"""SQLAlchemy engine + session setup, and the check that the database schema is current."""

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BACKEND_DIR, settings


def create_db_engine(url: str, **engine_options) -> Engine:
    """Create an engine; for SQLite, turn on foreign key checks for every connection.

    Tests use this too, so their in-memory database follows the same rules as app.db.
    """
    engine = create_engine(url, **engine_options)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    return engine


engine = create_db_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def latest_migration() -> str:
    """The newest migration in migrations/versions (Alembic calls it the "head")."""
    return ScriptDirectory.from_config(Config(BACKEND_DIR / "alembic.ini")).get_current_head()


def ensure_database_is_up_to_date(engine: Engine) -> None:
    """Refuse to start on a database that's missing migrations, with a message saying what to run."""
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    expected = latest_migration()
    if current != expected:
        raise RuntimeError(
            f"The database is at migration {current or '(none)'} but the code expects {expected}. "
            "From backend/, run:  alembic upgrade head"
        )
