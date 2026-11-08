from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("backend.app.main.dispatch_scan", lambda _: None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"api": "ok"}}


def test_readiness_checks_database_and_redis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class HealthyRedis:
        def ping(self) -> bool:
            return True

    monkeypatch.setattr(
        "backend.app.main.Redis.from_url",
        lambda *_args, **_kwargs: HealthyRedis(),
    )
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "redis": "ok"}


def test_image_job_contract(client: TestClient) -> None:
    created = client.post("/api/v1/jobs", json={"image_ref": "alpine:3.20"})
    assert created.status_code == 202
    payload = created.json()
    assert payload["source_type"] == "image"
    assert payload["source_ref"] == "alpine:3.20"
    assert payload["status"] == "queued"
    assert len(payload["id"]) == 36

    listed = client.get("/api/v1/jobs")
    assert listed.status_code == 200
    assert [job["id"] for job in listed.json()] == [payload["id"]]

    fetched = client.get(f"/api/v1/jobs/{payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payload["id"]

    pending_result = client.get(f"/api/v1/jobs/{payload['id']}/results")
    assert pending_result.status_code == 409


@pytest.mark.parametrize("image_ref", ["", "-o json", "image\nmalicious"])
def test_rejects_unsafe_image_references(client: TestClient, image_ref: str) -> None:
    response = client.post("/api/v1/jobs", json={"image_ref": image_ref})
    assert response.status_code == 422
