import os

# Must run before any app import: app.config builds Settings() on import, and tests
# should never see (or use) the real secrets from .env.
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["SESSION_SECRET_KEY"] = "test-session-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402, F401 - importing registers the tables on Base
from app.db import Base, create_db_engine, get_db  # noqa: E402
from app.dependencies import get_current_user, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


# Set to a Postgres URL to run the suite against Postgres instead of SQLite, e.g.
#   TEST_DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5432/postgres
# Every test wipes that database, so never point it at one with data you want to keep.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def wipe_postgres(url: str) -> None:
    engine = create_db_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    engine.dispose()


@pytest.fixture
def empty_database_url(tmp_path) -> str:
    """The URL of an empty database: TEST_DATABASE_URL (wiped first), or a throwaway SQLite file."""
    if TEST_DATABASE_URL:
        wipe_postgres(TEST_DATABASE_URL)
        return TEST_DATABASE_URL
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def db() -> Session:
    """A fresh, empty database for each test (never touches app.db): in-memory SQLite by
    default, or TEST_DATABASE_URL."""
    if TEST_DATABASE_URL:
        wipe_postgres(TEST_DATABASE_URL)
        engine = create_db_engine(TEST_DATABASE_URL)
    else:
        engine = create_db_engine(
            "sqlite://",
            # One shared connection: an in-memory database only lives as long as its connection.
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def user(db: Session) -> User:
    user = User(google_subject="google-user-1", email="student@example.com")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def signed_out_client(db: Session) -> TestClient:
    """An HTTP client for the real app, using the test database, with no one signed in.

    Like a browser, it keeps cookies between requests - so tests can sign in for real.
    """

    def use_test_db():
        yield db

    app.dependency_overrides[get_db] = use_test_db
    # Background jobs open their own sessions; point those at the test database too.
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(bind=db.get_bind())
    # Deliberately not `with TestClient(app)`: that would run the app's startup code,
    # which checks the real app.db. The test database already has its tables.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(signed_out_client: TestClient, user: User) -> TestClient:
    """An HTTP client signed in as `user`, for tests about everything *except* signing in.

    Skips the Google round trip by answering get_current_user directly; test_auth_routes.py
    tests the real sign-in.
    """
    app.dependency_overrides[get_current_user] = lambda: user
    return signed_out_client
