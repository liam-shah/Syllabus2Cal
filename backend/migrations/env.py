"""Alembic's entry point: connects to the database and runs the migration scripts.

Run from backend/:
    alembic upgrade head          apply every migration that hasn't run yet
    alembic revision --autogenerate -m "describe the change"
                                  write a new migration by comparing models.py to the database
"""

from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401 - importing registers the tables on Base
from app.config import settings
from app.db import Base, create_db_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What the database *should* look like. --autogenerate compares the real database to this.
target_metadata = Base.metadata

# The app's own setting, so migrations always hit the same database as the app. Tests pass a
# different URL (a throwaway database) by setting sqlalchemy.url themselves.
database_url = config.get_main_option("sqlalchemy.url") or settings.database_url


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (`alembic upgrade head --sql`), e.g. to review it."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(database_url)  # same foreign-key settings as the app
    with engine.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        if is_sqlite:
            # Rebuilding a table drops the old copy, which other tables' foreign keys still point
            # at, so SQLite's own instructions say to switch the checks off while rebuilding.
            # (It can only be switched outside a transaction, hence the commit.)
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite can't change most things about an existing table with ALTER TABLE, so
            # "batch mode" rebuilds the table (copy -> drop -> rename) when it has to.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
            if is_sqlite:
                # ...and then to check that every foreign key still points at a real row.
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
                if broken:
                    raise RuntimeError(f"Migration left broken foreign keys: {broken}")
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
