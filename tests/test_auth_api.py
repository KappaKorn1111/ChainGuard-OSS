from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import RefreshToken, User

ADMIN = {
    "email": "owner@example.com",
    "password": "StrongPassword123",
    "display_name": "Owner",
    "organization_name": "Example Organization",
    "organization_slug": "example-org",
}


def bootstrap(client: TestClient) -> dict:
    response = client.post("/api/v1/auth/bootstrap", json=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def test_bootstrap_hashes_password_and_is_one_time(
    client: TestClient, db_session: Session
) -> None:
    bootstrap(client)
    user = db_session.scalar(select(User).where(User.email == ADMIN["email"]))
    assert user is not None
    assert user.password_hash != ADMIN["password"]
    assert user.password_hash.startswith("$argon2id$")

    duplicate = client.post("/api/v1/auth/register", json=ADMIN)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "bootstrap_complete"


def test_login_does_not_enumerate_users(client: TestClient) -> None:
    bootstrap(client)
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN["email"], "password": "WrongPassword123"},
    )
    missing_user = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "WrongPassword123"},
    )
    assert wrong_password.status_code == missing_user.status_code == 401
    assert wrong_password.json()["error"]["message"] == missing_user.json()["error"]["message"]


def test_refresh_rotation_reuse_detection_and_logout(
    client: TestClient, db_session: Session
) -> None:
    tokens = bootstrap(client)
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert rotated.status_code == 200
    replacement = rotated.json()["refresh_token"]
    assert replacement != tokens["refresh_token"]

    reuse = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "refresh_token_reuse"
    assert all(token.revoked_at is not None for token in db_session.scalars(select(RefreshToken)))

    revoked_replacement = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": replacement},
    )
    assert revoked_replacement.status_code == 401

    fresh_login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN["email"], "password": ADMIN["password"]},
    ).json()
    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": fresh_login["refresh_token"]},
    )
    assert logout.status_code == 204
    after_logout = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": fresh_login["refresh_token"]},
    )
    assert after_logout.status_code == 401


def test_me_requires_access_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    tokens = bootstrap(client)
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == ADMIN["email"]
    assert response.json()["role"] == "owner"
