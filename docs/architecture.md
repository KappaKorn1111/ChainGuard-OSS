# ChainGuard OSS architecture

## Scope

Prompt 01 establishes an executable, modular inspection platform. It accepts container
image references and uploaded archives, generates a real SBOM, normalizes it, scans it
for vulnerabilities, preserves evidence, and can synchronize the resulting BOM to
Dependency-Track.

## Components

| Component | Responsibility | State |
| --- | --- | --- |
| React frontend | Submit and monitor jobs; display findings, dependencies, SBOM, provenance, and health | Stateless |
| FastAPI backend | Validate ingestion, persist contracts, stream uploads, dispatch work, expose results and health | PostgreSQL and upload volume |
| Celery worker | Execute Syft, Protobom `sbom-convert`, Grype, and Dependency-Track synchronization | PostgreSQL, upload volume, Grype cache |
| PostgreSQL | Jobs and scan evidence | Persistent volume |
| Redis | Celery broker and result backend | AOF persistent volume |
| Dependency-Track | Portfolio-level component and vulnerability analysis | Dedicated PostgreSQL and application-data volumes |

The backend never runs scanners in its request process. A job is committed before its
Celery task is dispatched. Scanner commands are argument arrays, never shell strings.

## Inspection flow

1. The API validates an image reference or streams an archive to bounded storage.
2. Uploaded bytes are SHA-256 hashed during ingestion.
3. The API persists a queued job and sends only its UUID to Redis.
4. The worker loads the source from PostgreSQL and marks the job running.
5. Syft emits CycloneDX JSON.
6. `sbom-convert`, the CLI built on OpenSSF Protobom, ingests that document and emits
   normalized SPDX 2.3 JSON.
7. Grype evaluates the Syft CycloneDX document against its real vulnerability database.
8. The worker stores raw and normalized SBOMs, normalized findings and dependencies,
   tool versions, completion time, source hash, and SHA-256 hashes of all scanner output.
9. If both Dependency-Track URL and API key are configured, the original CycloneDX BOM
   is submitted to a per-job project and its project UUID is stored. Dependency-Track
   v5 accepts CycloneDX uploads, not SPDX.

Failures are explicit job states and retain a bounded diagnostic message. Scanner output
is never synthesized.

## Data model and migrations

`inspection_jobs` is the lifecycle record and source envelope. `scan_results` has a
one-to-one relationship with a completed job and stores raw Syft and Grype evidence,
the normalized SBOM, derived views, and provenance JSON. Migration
`0001_initial_schema` is reversible: downgrade drops result data before jobs.

Alembic is the only supported schema-change mechanism. The one-shot `migrate` Compose
service runs before the API and worker start.

## Interfaces

The versioned REST API is rooted at `/api/v1`:

- `POST /jobs` — submit `{ "image_ref": "registry/repository:tag" }`
- `POST /jobs/upload` — multipart field `archive`
- `GET /jobs` and `GET /jobs/{id}` — lifecycle
- `GET /jobs/{id}/results` — aggregate completed result
- `GET /jobs/{id}/sbom`, `/vulnerabilities`, `/dependencies` — focused evidence views
- `GET /health/live` — process liveness
- `GET /health/ready` — live PostgreSQL and Redis checks

A result request returns `409` until the job is complete, and `404` for unknown jobs.

## Trust boundaries and security

- Development publishes the ChainGuard UI/API and Dependency-Track UI/API. PostgreSQL,
  Redis, and the worker have no host port. Production ingress must protect both APIs.
- The worker has outbound network access because registry pulls and vulnerability
  database updates require it. It is non-root and constrained by Compose CPU, memory,
  and PID limits.
- The API and worker run as UID 10001. The frontend uses unprivileged Nginx.
- Upload names are reduced to their basename, upload size is bounded, content is hashed,
  and scanner processes have hard timeouts.
- Credentials are supplied through environment variables. `.env` is ignored.
- Redis requires authentication and Dependency-Track uses a dedicated database.
- CORS is explicit and credentials are disabled.

Container image tags and Python/JavaScript lockfiles make builds reproducible at the
application layer. Production operators should additionally pin container images by
digest and place TLS/authentication in front of the public services.

## Development and production settings

`compose.yaml` defaults to development and exposes UI/API ports.
`compose.production.yaml` sets production mode, lowers log verbosity, and removes the
backend host port. Production deployments must provide a public API routing strategy
and build the frontend with its externally reachable API URL.

## Known operational constraint

Dependency-Track v5 starts with a documented bootstrap administrator account whose
default password must be changed immediately. An API key must then be created through
the Dependency-Track UI and placed in the local `.env`.
This cannot be safely automated without embedding or extracting bootstrap credentials.
Until configured, ChainGuard scans and stores complete local results but intentionally
skips BOM synchronization.

## Internal integration framework

The contract-first orchestration layer is documented in
[`integration-sdk.md`](integration-sdk.md) and ADR 0005. It adds typed integration
interfaces, versioned domain models and JSON Schemas, a catalog-backed runtime registry,
secure process execution, evidence-preserving correlation, and a pluggable future scan
pipeline. These modules are additive: the Prompt 01 worker path, database schema,
Compose services, and API remain unchanged.
