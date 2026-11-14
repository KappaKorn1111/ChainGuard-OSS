# ChainGuard integration SDK and contracts

## Boundary

ChainGuard owns orchestration, normalized contracts, evidence preservation, integration
state, and correlation. External tools continue to own discovery and analysis. Prompt 03
does not add production scanner adapters or change the Prompt 01 Celery scan path.

The Python SDK lives under `backend/app/integrations`. Its base `Integration` contract
requires every adapter to expose identity, catalog and installed version information,
declared capabilities, execution requirements, accepted input/output formats, config
validation, health, and typed execution results. Expected failures use
`IntegrationError`; adapters must not return fabricated findings after a tool failure.

Specialized interfaces are:

- `SBOMGenerator` and `SBOMNormalizer`
- `VulnerabilityScanner` and `VulnerabilityIntelligenceProvider`
- `ComponentAnalysisProvider`, `RepositoryRiskProvider`, and
  `SupplyChainGraphProvider`
- `ProvenanceVerifier` and `ArtifactSignatureVerifier`
- `ContainerScanner`, `SourceCodeScanner`, and `InfrastructureScanner`
- `SecurityFindingsProvider`

Capabilities are independently enabled and must be a subset of an adapter's declared
capabilities. Merely appearing in the resource catalog does not make an integration
installed or available.

## Versioned data contracts

The models in `backend/app/domain` use contract schema version `1.0`, reject unknown
fields, and carry a required `tenant_id`. They cover:

- SBOM documents and components, including dependency and source relationships
- vulnerabilities, aliases, affected ranges, fixes, CVSS, advisories, and provenance
- security findings, evidence, remediation, and verification state
- scan execution, resource usage, failure metadata, correlation IDs, and idempotency
- tool provenance and transformation history

Generated JSON Schemas are committed in
`backend/app/schemas/generated`. Regenerate them from the repository root:

```bash
uv run --project backend python scripts/generate_contract_schemas.py
```

The contract test compares every committed schema to Pydantic's current output and
validates the schemas with JSON Schema Draft 2020-12 tooling.

## Registry and health

`IntegrationRegistry` loads `config/tool-registry.yaml` only through the existing
`backend.app.tool_registry.load_tool_registry`. It does not maintain a second tool
manifest. Catalog entries without runtime adapters remain unavailable, disabled, or
planned as configured. Runtime registration:

1. requires an existing catalog ID;
2. rejects duplicate registrations;
3. validates adapter configuration;
4. tracks installed version, enabled capabilities, health, last safe error, and last
   success;
5. rejects `test_only` adapters unless the registry was explicitly constructed in test
   mode.

Test adapters live only under `tests/integrations` and mark their output and provenance
as test-only. The production registry and pipeline reject them.

## Secure process execution

`SecureProcessRunner` is for isolated worker use, not API request handlers. Its policy
requires exact allowlisted resolved executable paths and working directories beneath
approved roots. It:

- always uses argument arrays with `shell=False`;
- rejects shells and general-purpose interpreters in production policies;
- rejects non-string, oversized, NUL, and multiline arguments;
- supplies a minimal explicit environment and rejects non-allowlisted keys;
- redacts credential-like environment keys in execution records;
- closes stdin and captures stdout/stderr with independent byte limits;
- enforces timeout and cancellation and kills the process group;
- records timestamps, duration, exit status, bounded output, and terminal reason;
- applies POSIX address-space, CPU, file-size, and file-descriptor limits when
  available.

The allowlist must be assembled by trusted deployment configuration. Repository build
scripts, repository-supplied command names, and arbitrary working directories must
never be passed to this runner. Production workers should additionally use filesystem,
process, and network isolation.

## Correlation rules

`FindingsCorrelator` accepts source-specific records while preserving each complete
original record and `ToolProvenance`. It normalizes recognized CVE, GHSA, and OSV-style
identifiers, follows aliases, and associates packages by PURL when present.

It never treats missing evidence as confirmed absence. Re-reporting the same source
record is marked `duplicate`; evidence from another tool or database is
`corroboration`. Conflicting severity, affected range, or fixed version values remain
side-by-side and are marked `conflict`; no source silently overwrites another.
Incomplete fields are listed as missing metadata and every observation is retained in
history.

## Pipeline contract

`ScanPipeline` requires one pluggable implementation for every stage in this order:

1. repository input and source validation;
2. SBOM generation;
3. SBOM validation;
4. SBOM normalization;
5. vulnerability analysis;
6. findings correlation;
7. evidence preservation;
8. structured scan result.

The compatibility map assigns Syft to generation, CycloneDX CLI to validation,
Protobom to normalization, and Grype/OSV-Scanner/Trivy/Dependency-Track to analysis.
GUAC and OpenSSF Scorecard are retained as later graph and repository-risk providers,
not forced into an incompatible current stage. This map is architectural compatibility,
not proof that an adapter is installed.

## Jobs and errors

The framework state contract adds Pending, Queued, Running, Completed, Failed,
Cancelled, TimedOut, and PartiallyCompleted with explicit legal transitions. It is
Celery-ready but does not duplicate or alter Prompt 01's current database enum or task.
Structured errors include category, safe code/message, retry eligibility, optional
retry delay, and integration details. Safe serialization recursively redacts
credential-like fields and does not serialize exceptions or stack traces.
