import os

# Must run before any app import: app.config builds Settings() on import, and tests
# should never see (or use) the real API key from .env.
os.environ["ANTHROPIC_API_KEY"] = "test-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402, F401 - importing registers the tables on Base
from app.db import Base, create_db_engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture
def db() -> Session:
    """A fresh, empty in-memory database for each test (never touches app.db)."""
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
    user = User()
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client(db: Session) -> TestClient:
    """An HTTP client for the real app, with every route using the test database."""

    def use_test_db():
        yield db

    app.dependency_overrides[get_db] = use_test_db
    # Deliberately not `with TestClient(app)`: that would run the app's startup code,
    # which creates tables in the real app.db. The test database already has its tables.
    yield TestClient(app)
    app.dependency_overrides.clear()
