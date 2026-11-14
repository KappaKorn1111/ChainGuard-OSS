from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import AuditLog
from tests.test_auth_api import ADMIN, bootstrap


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str, password: str, organization_slug: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "organization_slug": organization_slug,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_users_projects_pagination_and_rbac(
    client: TestClient, db_session: Session
) -> None:
    owner_tokens = bootstrap(client)
    owner_headers = auth(owner_tokens["access_token"])
    viewer = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": "viewer@example.com",
            "password": "ViewerPassword123",
            "display_name": "Viewer",
            "role": "viewer",
        },
    )
    assert viewer.status_code == 201, viewer.text

    users = client.get("/api/v1/users?limit=1&search=viewer", headers=owner_headers)
    assert users.status_code == 200
    assert users.json()["total"] == 1
    assert users.json()["items"][0]["email"] == "viewer@example.com"

    first = client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={"name": "Alpha", "slug": "alpha", "description": "first"},
    )
    second = client.post(
        "/api/v1/projects",
        headers=owner_headers,
        json={"name": "Beta", "slug": "beta"},
    )
    assert first.status_code == second.status_code == 201
    page = client.get("/api/v1/projects?limit=1&offset=1", headers=owner_headers)
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1

    viewer_token = login(
        client,
        "viewer@example.com",
        "ViewerPassword123",
        ADMIN["organization_slug"],
    )["access_token"]
    forbidden = client.post(
        "/api/v1/projects",
        headers=auth(viewer_token),
        json={"name": "Forbidden", "slug": "forbidden"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"

    assert db_session.scalar(select(func.count()).select_from(AuditLog)) >= 4


def test_cross_tenant_project_and_organization_isolation(client: TestClient) -> None:
    owner_tokens = bootstrap(client)
    org_one_headers = auth(owner_tokens["access_token"])
    created_org = client.post(
        "/api/v1/organizations",
        headers=org_one_headers,
        json={"name": "Second Organization", "slug": "second-org"},
    )
    assert created_org.status_code == 201
    second_org_id = created_org.json()["id"]

    org_two_token = login(
        client,
        ADMIN["email"],
        ADMIN["password"],
        "second-org",
    )["access_token"]
    project = client.post(
        "/api/v1/projects",
        headers=auth(org_two_token),
        json={"name": "Private", "slug": "private"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    hidden_project = client.get(f"/api/v1/projects/{project_id}", headers=org_one_headers)
    assert hidden_project.status_code == 404
    hidden_org = client.get(f"/api/v1/organizations/{second_org_id}", headers=org_one_headers)
    assert hidden_org.status_code == 200  # platform superuser may inspect organizations

    organizations = client.get("/api/v1/organizations", headers=org_one_headers)
    assert organizations.json()["total"] == 2
