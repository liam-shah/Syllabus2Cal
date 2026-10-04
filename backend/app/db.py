"""SQLAlchemy engine + session setup."""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


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
