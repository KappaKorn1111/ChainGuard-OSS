# ADR 0005: ChainGuard owns a contract-first integration framework

- Status: Accepted
- Date: 2026-11-14

## Context

Prompt 01 established a working Syft, Protobom, Grype, and Dependency-Track execution
path. Prompt 02 established a verified central resource catalog. Adding integrations
directly to the worker would couple orchestration to tool-specific output, make
cross-source evidence ambiguous, and risk turning planned catalog entries into implied
capabilities.

## Decision

ChainGuard will use typed, versioned contracts at its internal boundary. Specialized
adapter interfaces depend on domain models rather than tool implementations. The
runtime registry reads Prompt 02's catalog through the existing loader and separately
tracks whether a real adapter is installed, configured, enabled, and healthy.

The scan pipeline is an ordered composition of replaceable stages. Scanner output is
immutable source evidence; normalization and correlation append provenance and
relationships rather than replacing it. Duplicate source observations, independent
corroboration, conflicts, and missing metadata are distinct states.

Local tools execute only through an exact-path allowlist, validated argument arrays,
bounded capture, minimal environments, time and resource limits, and structured safe
records. The framework is designed for isolated workers with restricted network and
filesystem access.

Prompt 03 does not add production adapters, database tables, API routes, authentication,
or a replacement Celery task. The established worker remains the production scan path.

## Consequences

- New integrations must implement a declared interface and cannot claim undeclared
  capabilities.
- JSON Schema artifacts are generated from Pydantic models and checked in CI.
- Catalog presence and runtime availability remain intentionally separate.
- Multi-tenant identity and provenance are required at contract boundaries.
- Test-only adapters cannot enter a production registry or pipeline.
- The current database job status remains unchanged until a future migration and API
  compatibility plan explicitly adopts the broader state contract.

The tradeoff is an additional translation layer for each scanner. That cost is accepted
to preserve evidence, support interchangeable tools, and avoid coupling core models to
external formats.
