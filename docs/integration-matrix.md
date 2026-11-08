# Integration matrix

This matrix separates validated resources from installed integrations. A registry entry
does not authorize installation. `advanced` is a tag mapped to `OPTIONAL` or `FUTURE`
as defined by [ADR 0002](architecture-decisions/0002-priority-and-enablement.md).

| Resource | Adapter boundary | Priority | Enablement | Input | Native output | ChainGuard relationship |
| --- | --- | --- | --- | --- | --- | --- |
| Syft | SBOM generator | CORE | Enabled | Image, filesystem/archive | CycloneDX, SPDX, Syft JSON | Sole component discovery engine in Prompt 01 |
| Grype | Vulnerability intelligence provider | CORE | Enabled | Syft/CycloneDX SBOM | Grype JSON | Correlates components; does not generate/normalize SBOMs |
| Protobom / sbom-convert | SBOM normalizer | CORE | Enabled | CycloneDX/SPDX JSON | CycloneDX/SPDX JSON | Explicit format translation only |
| Dependency-Track | External monitoring | CORE | Enabled when API key is configured | BOM upload | REST portfolio/findings data | Continuous downstream analysis; does not own jobs |
| Trivy | Scanner adapter | SECONDARY | Planned | Images, filesystems, repositories, IaC | JSON, SARIF, CycloneDX/SPDX | Complementary container/configuration coverage |
| OSV-Scanner | Vulnerability intelligence provider | SECONDARY | Planned | Lockfiles, SBOMs, source trees | OSV JSON/SARIF | Ecosystem-native OSV correlation |
| CycloneDX CLI | SBOM validator/normalizer | SECONDARY | Planned | CycloneDX documents | CycloneDX, validation result | CycloneDX-specific validation and transformations |
| cdxgen | SBOM generator | OPTIONAL | Disabled | Source trees, containers | CycloneDX | Alternate ecosystem-heavy generator; not run with Syft by default |
| bomctl | SBOM normalizer/store client | FUTURE (advanced) | Planned | SPDX/CycloneDX | SPDX/CycloneDX | Experimental format-neutral workflow with limited recent release activity |
| Dependency-Check | Vulnerability intelligence provider | OPTIONAL | Disabled | Project dependencies | XML, JSON, HTML, SARIF | Java/CPE-oriented analysis; avoid duplicate default findings |
| GUAC | Supply-chain graph provider | FUTURE (advanced) | Planned | SBOMs and attestations | GraphQL graph | Requires graph ingestion/query architecture |
| OpenSSF Scorecard | Repository assessment provider | OPTIONAL (advanced) | Planned | Source repository | JSON/SARIF | Repository practice signals, never artifact vulnerability findings |
| DefectDojo | External findings processor | FUTURE (advanced) | Planned | Scanner reports/API | REST findings model | Optional enterprise aggregation, not ChainGuard persistence |
| Sigstore | Trust-system resource | FUTURE (advanced) | Planned | Signing identities/transparency records | Verification material | Ecosystem boundary; concrete verification uses Cosign |
| Cosign | Artifact verification adapter | FUTURE (advanced) | Planned | OCI artifact/signature/attestation | Verification JSON | Signature and attestation verification only |
| SLSA | Assurance framework | FUTURE (advanced) | Planned | Provenance claims/process evidence | Conformance level | Policy vocabulary, not an executable scanner |
| in-toto | Provenance verification adapter | FUTURE (advanced) | Planned | Layouts, link metadata, attestations | Verification result | Supply-chain step/layout verification |
| Gitleaks | Secret scanner | OPTIONAL | Disabled | Git history/tree | JSON, SARIF | Secret discovery only |
| Semgrep | Static analysis adapter | OPTIONAL | Disabled | Source code/rules | JSON, SARIF | SAST and policy matching only |
| Bandit | Python static analysis adapter | OPTIONAL | Disabled | Python source | JSON, SARIF | Python-specific security linting only |
| Checkov | Infrastructure security adapter | OPTIONAL | Disabled | IaC/configuration | JSON, SARIF | IaC and policy scanning only |

## Adapter contracts

```text
ingestion
  ├── sbom_generator[] ──> raw SBOM evidence
  │                         └── sbom_normalizer[] ──> canonical SBOM view
  ├── vulnerability_provider[] ──> native advisory matches
  ├── artifact_verifier[] ──> signature/attestation result
  ├── provenance_verifier[] ──> layout/provenance result
  ├── infrastructure_scanner[] ──> IaC/config findings
  └── repository_assessor[] ──> repository practice signals

raw evidence + adapter metadata
  └── findings_processor ──> attributed ChainGuard views
       ├── supply_chain_graph_provider (future)
       └── external_monitoring (optional downstream synchronization)
```

Every adapter invocation must emit an engine identity/version, timestamps, source
identity, native report hash, terminal status, and bounded diagnostics. Findings
processors may link or deduplicate views but cannot delete or rewrite native evidence.

## Dependency and flow constraints

- Grype and OSV-Scanner consume component identity but use different advisory sources;
  their findings remain separately attributed.
- Trivy's overlapping SBOM and vulnerability capabilities are opt-in per capability.
  The adapter must not silently replace Syft or Grype.
- Protobom is the current cross-format normalizer. CycloneDX CLI is reserved for
  CycloneDX validation and supported CycloneDX operations.
- GUAC ingestion depends on durable evidence identifiers and graph lifecycle design.
- Cosign and in-toto depend on immutable artifact identity and policy inputs, not SBOM
  generation.
- DefectDojo and Dependency-Track are downstream systems. Failure to synchronize cannot
  erase a locally completed result.
