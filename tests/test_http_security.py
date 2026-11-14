import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import app
from backend.app.rate_limit import get_rate_limit_redis


class BrokenRedis:
    def incr(self, _key: str) -> int:
        raise ConnectionError("unavailable")


def test_validation_and_not_found_use_error_envelope(client: TestClient) -> None:
    invalid = client.post("/api/v1/jobs", json={"image_ref": "-unsafe"})
    assert invalid.status_code == 422
    assert set(invalid.json()["error"]) == {"code", "message", "details", "request_id"}
    assert invalid.json()["error"]["code"] == "validation_error"

    missing = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert missing.headers["X-Request-ID"] == missing.json()["error"]["request_id"]


def test_server_errors_do_not_leak_stack_traces_or_secrets(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.app.main.dispatch_scan",
        lambda _job_id: (_ for _ in ()).throw(RuntimeError("secret-value")),
    )
    with TestClient(app, raise_server_exceptions=False) as server_client:
        response = server_client.post("/api/v1/jobs", json={"image_ref": "alpine:3.20"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret-value" not in response.text
    assert "traceback" not in response.text.lower()


def test_cors_allows_configured_origin_without_credentials(client: TestClient) -> None:
    response = client.options(
        "/api/v1/projects",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") != "true"


def test_auth_rate_limit_is_strict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "auth_rate_limit", 1)
    payload = {"email": "missing@example.com", "password": "WrongPassword123"}
    first = client.post("/api/v1/auth/login", json=payload)
    second = client.post("/api/v1/auth/login", json=payload)
    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    assert second.headers["Retry-After"] == str(get_settings().rate_limit_window_seconds)


def test_rate_limit_fails_closed_for_auth_and_open_for_general_api(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_rate_limit_redis] = lambda: BrokenRedis()
    auth_response = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "WrongPassword123"},
    )
    assert auth_response.status_code == 503
    assert auth_response.json()["error"]["code"] == "rate_limit_unavailable"

    job_response = client.post("/api/v1/jobs", json={"image_ref": "alpine:3.20"})
    assert job_response.status_code == 202
