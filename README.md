# ChainGuard-OSS

Continuous Software Supply Chain & SBOM Inspection Engine.

ChainGuard OSS inspects container images and uploaded software archives with real
open-source supply-chain tooling. It generates SBOMs with Syft, normalizes them through
OpenSSF Protobom, finds vulnerabilities with Grype, preserves evidence and provenance
in PostgreSQL, and optionally synchronizes BOMs to Dependency-Track.

## Foundation features

- React, TypeScript, and Tailwind dashboard for jobs, findings, dependencies, SBOMs,
  provenance, and service status
- FastAPI job and result API with bounded archive ingestion
- Organization-scoped users, projects, RBAC, Argon2id passwords, rotating JWT refresh
  tokens, audit logs, and Redis-backed rate limits
- PostgreSQL persistence with reversible Alembic migrations
- Celery worker and authenticated Redis broker/result backend
- Real Syft, Grype, and Protobom-based `sbom-convert` binaries in the worker image
- Real Dependency-Track API/frontend with dedicated PostgreSQL persistence
- JSON structured application logs and live/readiness health endpoints
- Non-root containers, isolated networks, scanner timeouts, upload limits, and Compose
  resource constraints
- Locked Python and JavaScript dependencies plus CI lint, test, build, and Compose checks

See [the architecture document](docs/architecture.md) for data flow, interfaces, and
trust boundaries.

The validated integration ecosystem is documented in:

- [Open-source resource catalog](docs/resource-catalog.md)
- [Integration and adapter matrix](docs/integration-matrix.md)
- [Application and engine compatibility matrix](docs/compatibility-matrix.md)
- [Machine-readable tool registry](config/tool-registry.yaml)
- [Architecture decisions](docs/architecture-decisions/)
- [API v1 documentation](docs/api.md)

## Start the development stack

Requirements: Docker Engine with Docker Compose v2, at least 10 GiB available memory,
and internet access for image pulls and Grype database updates.

```bash
git clone https://github.com/KappaKorn1111/ChainGuard-OSS.git
cd ChainGuard-OSS
cp .env.example .env
# Edit .env and replace every example credential, including JWT_SECRET.

docker compose build
docker compose up -d postgres redis dtrack-postgres dependency-track-api
docker compose run --rm migrate
docker compose up -d
```

The same sequence is available as:

```bash
./scripts/bootstrap.sh
```

Open:

- ChainGuard UI: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API liveness: <http://localhost:8000/health/live>
- API readiness (checks PostgreSQL, Redis, and migration head): <http://localhost:8000/health/ready>
- Dependency-Track UI: <http://localhost:8081>
- Dependency-Track API: <http://localhost:8082>
- Dependency-Track management health: <http://localhost:9001/health>

On first boot, sign in to Dependency-Track with its documented bootstrap account,
immediately replace the default administrator password,
create an API key with BOM upload/project permissions, set
`DEPENDENCY_TRACK_API_KEY` in `.env`, and recreate the worker:

```bash
docker compose up -d --force-recreate worker
```

Without that key, local inspection remains fully functional and BOM synchronization is
explicitly skipped.

## Bootstrap the API

Only an empty database accepts bootstrap:

```bash
curl --fail --json '{
  "email":"owner@example.com",
  "password":"ReplaceWithAStrongPassword123",
  "display_name":"Owner",
  "organization_name":"Example",
  "organization_slug":"example"
}' http://localhost:8000/api/v1/auth/bootstrap
```

The response contains short-lived access and rotating refresh tokens. See
[`docs/api.md`](docs/api.md) for login, refresh, logout, RBAC, user, organization,
membership, and project endpoints.

## Submit an inspection

```bash
curl --fail --json '{"image_ref":"alpine:3.20"}' \
  http://localhost:8000/api/v1/jobs

curl --fail -F 'archive=@./application.tar.gz' \
  http://localhost:8000/api/v1/jobs/upload

curl --fail http://localhost:8000/api/v1/jobs
```

The UI refreshes queued/running jobs automatically. A completed result contains the
normalized SPDX SBOM, Grype findings, dependencies, tool versions, source hash, and
scanner-output hashes.

## Verify

With the stack running:

```bash
./scripts/verify.sh
docker compose ps
docker compose logs worker
```

Host-side checks:

```bash
uv sync --project backend --frozen --dev
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend ruff check backend worker tests scripts
uv run --project backend pytest tests

cd frontend
npm ci
npm run lint
npm run build

cd ..
docker compose --env-file .env.example config --quiet
```

Backend tests require a real PostgreSQL database and never substitute SQLite. Set
`DATABASE_URL`, `JWT_SECRET`, and `ENVIRONMENT=test` before running them outside
Compose. The migration suite creates and drops a temporary database, so the configured
PostgreSQL role needs `CREATEDB` in test environments.

Apply or reverse the Prompt 04 migration explicitly:

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini downgrade 0001
uv run --project backend alembic -c backend/alembic.ini upgrade head
```

## Production settings

Provide secret values through your deployment environment, set production origins and
URLs, terminate TLS at a trusted reverse proxy, then apply the production override:

```bash
docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml up -d
```

The override removes the backend's direct host port. Route `/api` and health traffic
through your production ingress and build the frontend with the public API URL.

## Repository layout

```text
frontend/       React application and production web image
backend/        FastAPI application, configuration, and Alembic migrations
worker/         Celery orchestration and scanner image
infrastructure/ Web-server and deployment support configuration
scripts/        Bootstrap, migration, and verification entrypoints
tests/          API, health, configuration, and contract tests
docs/           Architecture and operating decisions
.github/        Continuous integration workflows
```

## License

Apache-2.0. See [LICENSE](LICENSE).