# ChainGuard API v1

All application endpoints are rooted at `/api/v1`. The original Prompt 01 job routes
remain unchanged. Health endpoints are available both under `/api/v1/health/*` and at
their original `/health/*` paths.

## Errors and correlation IDs

Every API error uses:

```json
{
  "error": {
    "code": "permission_denied",
    "message": "insufficient permissions",
    "details": {},
    "request_id": "fb8c49ce-30cf-4af5-a324-c73713080e49"
  }
}
```

Clients may send `X-Request-ID` containing 1–100 letters, numbers, dots, underscores,
or hyphens. Invalid values are replaced. The effective ID is returned in the response
header and error envelope. Validation, authentication, permission, not-found, conflict,
rate-limit, service, and server failures all use this envelope. Internal exception
details and credentials are never returned.

## Authentication

`POST /auth/bootstrap` and its compatibility alias `/auth/register` create the first
platform administrator, organization, owner membership, and token pair. PostgreSQL
serializes this operation; after the first user it returns conflict.

`POST /auth/login` accepts email, password, and optional `organization_slug`.
`POST /auth/refresh` rotates the persisted refresh token. `POST /auth/logout` revokes
the token family. `GET /auth/me` returns the current user, organization, and role.

Pass access tokens as `Authorization: Bearer <token>`. Access tokens default to 15
minutes and refresh tokens to seven days. Only refresh-token hashes are persisted.

## Authorization

| Role | Read | Create/update projects | Manage users/members | Delete org |
| --- | --- | --- | --- | --- |
| viewer | yes | no | no | no |
| member | yes | yes | no | no |
| admin | yes | yes | yes, except owners | no |
| owner | yes | yes | yes | yes |

Platform superusers may perform platform-level organization administration. Tenant
resources are always filtered by the organization claim in the access token.

## Resources

### Users

- `GET /users` — paginated; filters: `search`, `active`
- `POST /users` — owner/admin; creates user and membership
- `GET /users/{id}`
- `PATCH /users/{id}` — owner/admin
- `DELETE /users/{id}` — safe deactivation, owner/admin

### Organizations and memberships

- `GET /organizations`
- `POST /organizations`
- `GET|PATCH|DELETE /organizations/{id}`
- `GET|POST /organizations/{id}/memberships`
- `PATCH|DELETE /organizations/{id}/memberships/{membership_id}`

The final owner cannot be removed.

### Projects

- `GET /projects` — paginated; optional `search`
- `POST /projects`
- `GET|PATCH|DELETE /projects/{id}`

### Existing inspection API

- `POST /jobs`
- `POST /jobs/upload`
- `GET /jobs`
- `GET /jobs/{id}`
- `GET /jobs/{id}/results`
- `GET /jobs/{id}/sbom`
- `GET /jobs/{id}/vulnerabilities`
- `GET /jobs/{id}/dependencies`

These routes retain Prompt 01 behavior and physical tables. New tenant APIs do not
expose unassigned legacy scan rows.

## Pagination and rate limits

List responses contain `items`, `total`, `limit`, and `offset`; `limit` is capped at
100. Authentication and general API limits are independently configurable. A rejected
request returns `429` and `Retry-After`.

Authentication fails closed with `503` when Redis is unavailable. General endpoints
fail open, as documented in ADR 0006.

## Health

Liveness checks only the API process. Readiness verifies PostgreSQL, Redis, and that
the database's Alembic revision equals the configured migration head.
