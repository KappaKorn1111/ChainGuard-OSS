# ADR 0003: Preserve native evidence and normalize through explicit contracts

- Status: Accepted
- Date: 2026-11-08

## Context

SPDX, CycloneDX, SARIF, OSV, CSAF, and tool-specific JSON are not lossless substitutes
for one another. Conversion and finding aggregation can discard identifiers,
relationships, match rationale, and advisory provenance.

## Decision

1. Store each engine's native output before transformation.
2. Hash the exact bytes produced by every engine.
3. Record tool name, version, invocation class, source identity, and completion time.
4. Use Protobom only for supported SBOM transformations; it is not a scanner.
5. Use CycloneDX CLI only for CycloneDX validation/conversion workflows when enabled.
6. Normalize findings into ChainGuard views while retaining engine-native identifiers,
   data-source URLs, match details, and raw evidence references.
7. Never infer a successful scan from an absent or unparsable report.

The current canonical interchange path is Syft CycloneDX JSON to Protobom SPDX 2.3 JSON.
Canonical storage does not replace the original Syft document or Grype report.

## Consequences

Storage use is higher, but results remain auditable and reprocessable. Format upgrades
require explicit migration/versioning rather than silent reinterpretation.
