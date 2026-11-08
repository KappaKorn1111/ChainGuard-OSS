# ADR 0001: Orchestrate external security engines through typed adapters

- Status: Accepted
- Date: 2026-11-08

## Context

ChainGuard needs broad supply-chain coverage without duplicating mature open-source
engines. The tools have distinct data models, update schedules, trust assumptions, and
operational requirements. Treating them as a single generic scanner would erase
provenance and make findings difficult to reproduce.

## Decision

ChainGuard remains the orchestration and evidence system. External tools retain narrow,
explicit responsibilities:

- SBOM generators discover components and relationships.
- SBOM normalizers translate documents without becoming discovery authorities.
- Vulnerability intelligence providers correlate components with their own advisory
  sources.
- Artifact and provenance verifiers validate signatures, attestations, and layouts.
- Repository assessors measure source-project practices.
- Infrastructure scanners evaluate configuration and deployment artifacts.
- Findings processors aggregate results without changing the original evidence.
- Supply-chain graph providers connect evidence across artifacts and repositories.
- External monitoring platforms receive normalized results but do not own ChainGuard's
  job lifecycle.

Each adapter must declare accepted inputs, emitted formats, tool/version identity,
configuration and authentication requirements, timeout/health behavior, and raw
evidence retention. Adapter output is associated with a job and cannot overwrite output
from another engine.

The Prompt 01 worker remains the first implementation: Syft generation, Protobom
normalization, Grype analysis, and optional Dependency-Track submission. Additional
catalog entries are disabled until a dedicated adapter and contract tests exist.

## Consequences

- Engines can evolve independently behind stable ChainGuard contracts.
- Overlapping findings remain attributable rather than silently deduplicated.
- Adding a catalog record does not install or execute a tool.
- Adapter-specific resource limits and network permissions are required.
- Cross-engine normalization belongs in a findings processor, after raw evidence is
  persisted.
