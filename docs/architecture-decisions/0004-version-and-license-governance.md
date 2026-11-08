# ADR 0004: Gate resource adoption on version, provenance, and license review

- Status: Accepted
- Date: 2026-11-08

## Context

External engines change release cadence, runtime requirements, licenses, and service
topology independently. A catalog that automatically installs every evaluated resource
would enlarge the attack surface and create unreviewed license obligations.

## Decision

- Every registry entry cites official release and license evidence.
- Enabled software requires a verified version and pinned installation locator.
- Container builds and Compose use full version tags; production deployments should
  additionally resolve and admit approved image digests.
- Optional and future entries remain absent from dependencies and Compose.
- License expressions are recorded as SPDX where available. Non-SPDX source-available
  terms use a `LicenseRef-*` marker and require legal review.
- Copyleft and source-available tools run as process/service boundaries unless a later
  legal and architectural review approves tighter linkage or distribution.
- Version promotion requires compatibility checks, image/package build verification,
  and an updated registry verification date.

## Current licensing decisions

- Apache-2.0, MIT, BSD, PostgreSQL, and PSF components are compatible with the current
  orchestration model, subject to notice obligations.
- Semgrep Community Edition is LGPL-2.1-or-later and remains an optional process
  boundary.
- SLSA v1.2 is a specification under Community-Spec-1.0, not an application dependency.
- Redis 8 uses `AGPL-3.0-only OR SSPL-1.0 OR LicenseRef-RSAL-2.0`; deployment and
  redistribution obligations require review.
- MinIO Community Server is AGPL-3.0-only and its community repository is archived; it
  is not selected.

## Consequences

The registry is evidence, not an installer. Upgrades are deliberate and auditable.
ChainGuard can evaluate broad open-source coverage without silently accepting runtime,
security, or licensing risk.
