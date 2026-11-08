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

## Start the development stack

Requirements: Docker Engine with Docker Compose v2, at least 10 GiB available memory,
and internet access for image pulls and Grype database updates.

```bash
git clone https://github.com/KappaKorn1111/ChainGuard-OSS.git
cd ChainGuard-OSS
cp .env.example .env
# Edit .env and replace every change-this-* development credential.

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
- API readiness (checks PostgreSQL and Redis): <http://localhost:8000/health/ready>
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
cd backend
uv sync --dev
uv run ruff check .
uv run pytest ../tests

cd ../frontend
npm ci
npm run lint
npm run build

cd ..
docker compose --env-file .env.example config --quiet
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