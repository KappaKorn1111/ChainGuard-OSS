import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/chainguard_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("UPLOAD_DIR", "/tmp/chainguard-test-uploads")
os.environ.setdefault("JWT_SECRET", "test-secret-with-at-least-thirty-two-characters")

from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_db
from backend.app.main import app
from backend.app.rate_limit import get_rate_limit_redis


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, _key: str, _seconds: int) -> bool:
        return True

    def ping(self) -> bool:
        return True


@pytest.fixture(scope="session")
def migrated_engine():
    config = Config(str(Path(__file__).resolve().parents[1] / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(config, "head")
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine) -> Generator[Session, None, None]:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def client(
    db_session: Session,
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_rate_limit_redis] = lambda: fake_redis
    monkeypatch.setattr("backend.app.main.Redis.from_url", lambda *_args, **_kwargs: fake_redis)
    monkeypatch.setattr("backend.app.main.dispatch_scan", lambda _: None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
