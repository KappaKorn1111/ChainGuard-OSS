# ADR 0002: Separate integration priority from enablement

- Status: Accepted
- Date: 2026-11-08

## Context

A resource can be strategically important without being safe or necessary to install in
the current deployment. The prompt's `ADVANCED` grouping also overlaps operational
priority rather than defining a fifth mutually exclusive lifecycle state.

## Decision

The registry uses four priorities:

- `CORE`: required for the current inspection lifecycle.
- `SECONDARY`: the next complementary engines with bounded overlap.
- `OPTIONAL`: useful extensions selected by deployment policy.
- `FUTURE`: architecture is reserved, but implementation requires further design.

`advanced` is a tag, not a priority. Advanced resources map to `OPTIONAL` when they can
be integrated independently and to `FUTURE` when they require new graph, attestation,
or external-platform workflows.

Enablement is independent:

- `enabled`: installed and wired into Prompt 01.
- `disabled`: validated but intentionally not installed.
- `planned`: selected for a future adapter.

An enabled record must have a verified version and pinned installation. A planned or
disabled record must not create a Compose service or runtime dependency.

## Consequences

The catalog can document the ecosystem without increasing the attack surface or resource
footprint. Promotion to enabled requires an adapter, health behavior, evidence contract,
tests, and a deployment decision.
