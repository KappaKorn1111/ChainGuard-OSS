# Compatibility matrix

Validated on 2026-11-08. “Validated” means dependency resolution, lint/tests, build, or
official compatibility documentation was checked; it does not mean every optional
resource was installed.

## Current application and infrastructure

| Component | Selected version | License (SPDX) | Validation | Compatibility decision |
| --- | --- | --- | --- | --- |
| React | 19.3.1 | MIT | npm lock and production build | Preserve |
| TypeScript | 7.0.2 | Apache-2.0 | `tsc -b` passes | Preserve |
| Vite | 8.3.6 | MIT | Production build passes on Node 22 | Preserve |
| Tailwind CSS | 4.3.5 | MIT | Vite plugin build passes | Preserve |
| Python | 3.12 | PSF-2.0 | API/worker tests and images | Preserve |
| FastAPI | 0.162.2 | MIT | API contract tests pass | Preserve |
| Pydantic | 2.14.3 | MIT | Settings and registry validation tests | Preserve |
| Pydantic Settings | 2.16.2 | MIT | Environment parsing tests | Preserve |
| SQLAlchemy | 2.1.8 | MIT | SQLite contracts and PostgreSQL image import | Preserve |
| Alembic | 1.20.1 | MIT | Reversible migration smoke test | Preserve |
| Celery | 5.7.0 | BSD-3-Clause | Worker import and dependency resolution | Preserve |
| redis-py | 8.1.0 | MIT | Celery-compatible locked resolution | Preserve |
| Redis server | 8.10.1 | AGPL-3.0-only OR SSPL-1.0 OR LicenseRef-RSAL-2.0 | Compose health configuration | Updated from security-stale 8.2.2; license review required for redistribution/service offerings |
| PostgreSQL | 17.11 | PostgreSQL | Compose configuration and migration target | Updated within supported major 17 from stale 17.6 |
| HTTPX | 0.28.1 | BSD-3-Clause | Dependency-Track client import/tests | Preserve; TestClient emits an upstream `httpx2` migration warning |
| python-json-logger | 4.2.0 | BSD-2-Clause | JSON logging active | Preserve instead of adding Structlog |
| Docker Engine | 29.1.3 used for validation | Apache-2.0 | Application images build | Runtime prerequisite, not an app dependency |
| Docker Compose | 2.40.3 used for validation | Apache-2.0 | Development and production configs parse | Preserve |

Versions are locked in `frontend/package-lock.json` and `backend/uv.lock`; container
versions are pinned in Dockerfiles and `compose.yaml`.

## Evaluated additions

| Resource | Status | Compatibility concern | Decision |
| --- | --- | --- | --- |
| Structlog 26.1.0 | Deferred | Duplicates the existing JSON logging pipeline and adds migration work | Revisit only for context propagation requirements |
| Prometheus 3.16.0 | Deferred | Requires metric definitions, cardinality policy, endpoint security, and retention ownership | Add through an observability adapter, not Prompt 02 |
| OpenTelemetry Python 1.45.2 | API transitively present; SDK/export deferred | Requires collector/export policy and trace context design across API/Celery | Future observability architecture |
| MinIO Community Server final binary release `RELEASE.2025-10-15T17-29-55Z` | Deferred | Community repository is archived/unmaintained, AGPL-3.0-only, and object storage adds credentials/lifecycle/backup concerns | Do not select without a supported object-store evaluation |

No incompatibility requires replacing the Prompt 01 stack.

## Security engine compatibility

| Producer | Consumer | Compatibility | Constraint |
| --- | --- | --- | --- |
| Syft CycloneDX JSON | Grype | Current Prompt 01 path | Preserve raw Syft and Grype reports |
| Syft CycloneDX JSON | sbom-convert / Protobom | Current Prompt 01 path | Convert only supported JSON schema versions |
| Syft CycloneDX JSON | Dependency-Track 5.2.1 | BOM upload path | v5 accepts CycloneDX uploads only; requires API key and project permissions |
| Syft/Protobom SBOM | OSV-Scanner | Planned | Adapter must select an upstream-supported SBOM schema |
| OCI image/filesystem | Trivy | Planned | Enable vulnerability, misconfiguration, or SBOM modes explicitly |
| CycloneDX document | CycloneDX CLI | Planned | Use for validation/transform operations only |
| Scanner-native reports | DefectDojo | Future | Map parser type and retain ChainGuard evidence IDs |
| SBOM/attestation | GUAC | Future | Requires graph entity identity and ingestion lifecycle |

## Official sources

- React: <https://github.com/facebook/react>
- TypeScript: <https://github.com/microsoft/TypeScript>
- Vite: <https://github.com/vitejs/vite>
- Tailwind CSS: <https://github.com/tailwindlabs/tailwindcss>
- FastAPI: <https://github.com/fastapi/fastapi>
- Pydantic: <https://github.com/pydantic/pydantic>
- SQLAlchemy: <https://github.com/sqlalchemy/sqlalchemy>
- Alembic: <https://github.com/sqlalchemy/alembic>
- Celery: <https://github.com/celery/celery>
- Redis: <https://github.com/redis/redis>
- PostgreSQL: <https://www.postgresql.org/docs/17/>
- HTTPX: <https://github.com/encode/httpx>
- Docker Compose: <https://github.com/docker/compose>
- OpenTelemetry: <https://opentelemetry.io/docs/>
- Prometheus: <https://prometheus.io/docs/>
- MinIO: <https://github.com/minio/minio>
