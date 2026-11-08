# Validated open-source resource catalog

Validation date: **2026-11-08**. The machine-readable source of truth is
[`config/tool-registry.yaml`](../config/tool-registry.yaml); this document is the
operator-facing summary.

## Verification method

Versions were checked against official upstream GitHub release/tag data and licenses
against upstream license files. Capability and installation claims were checked against
official documentation or release README files linked in each registry record. A field
that could not be established from those sources is `UNVERIFIED`; unverified resources
cannot be enabled by the registry schema.

“Current” means current at the validation date, not an unattended update policy.
ChainGuard does not automatically install catalog entries. Maintenance status `active`
means upstream had a current release and/or recent repository activity at validation.

## Security engines and intelligence

| Resource | Official source | Verified release | License (SPDX) | Install/runtime | Formats and interface | Priority / state |
| --- | --- | --- | --- | --- | --- | --- |
| Syft | [anchore/syft](https://github.com/anchore/syft) | v1.57.0 | Apache-2.0 | Pinned OCI build stage; native Go binary | Images/filesystems → Syft, SPDX, CycloneDX; CLI/library | CORE / enabled |
| Grype | [anchore/grype](https://github.com/anchore/grype) | v0.121.2 | Apache-2.0 | Pinned OCI build stage; DB cache and updates | Images/SBOMs → JSON, SARIF, CycloneDX; CLI/library | CORE / enabled |
| Protobom via sbom-convert | [protobom/sbom-convert](https://github.com/protobom/sbom-convert) | v0.0.8 (uses Protobom v0.6.1; current library v0.7.0) | Apache-2.0 | Go 1.26 build stage; static CLI | SPDX/CycloneDX JSON conversion; CLI/library | CORE / enabled |
| Dependency-Track | [DependencyTrack/dependency-track](https://github.com/DependencyTrack/dependency-track) | 5.2.1 | Apache-2.0 | API/UI containers, Java runtime, PostgreSQL | CycloneDX upload; REST/UI | CORE / enabled, sync needs API key |
| Trivy | [aquasecurity/trivy](https://github.com/aquasecurity/trivy) | v0.76.2 | Apache-2.0 | Pinned container or binary; DB/policy cache | Images, filesystems, IaC, SBOM → JSON/SARIF/SBOM | SECONDARY / planned |
| OSV-Scanner | [google/osv-scanner](https://github.com/google/osv-scanner) | v2.7.0 | Apache-2.0 | Pinned Go CLI; OSV data/API | Lockfiles/source/SBOM → JSON/SARIF | SECONDARY / planned |
| CycloneDX CLI | [CycloneDX/cyclonedx-cli](https://github.com/CycloneDX/cyclonedx-cli) | v0.33.1 | Apache-2.0 | Pinned container/.NET CLI | CycloneDX/SPDX → CycloneDX; CLI | SECONDARY / planned |
| cdxgen | [cdxgen/cdxgen](https://github.com/cdxgen/cdxgen) | v13.7.0 | Apache-2.0 | Pinned `@cdxgen/cdxgen` npm package; Node 24+ and ecosystem tools | Source/container → CycloneDX; CLI/library/server | OPTIONAL / disabled |
| bomctl | [bomctl/bomctl](https://github.com/bomctl/bomctl) | v0.4.3 | Apache-2.0 | Pinned release binary | SPDX/CycloneDX import/export/merge; CLI | FUTURE / planned / advanced |
| OWASP Dependency-Check | [dependency-check/DependencyCheck](https://github.com/dependency-check/DependencyCheck) | v13.0.0 | Apache-2.0 | Pinned container; Java and advisory feeds | Project metadata → JSON/XML/HTML/SARIF | OPTIONAL / disabled |
| GUAC | [guacsec/guac](https://github.com/guacsec/guac) | v1.1.0 | Apache-2.0 | Multi-component deployment and graph backend | SBOM/attestation/vulnerability documents → GraphQL | FUTURE / planned / advanced |
| OpenSSF Scorecard | [ossf/scorecard](https://github.com/ossf/scorecard) | v5.6.0 | Apache-2.0 | Pinned binary/action; source-host API | Repository → JSON/SARIF | OPTIONAL / planned / advanced |
| OWASP DefectDojo | [DefectDojo/django-DefectDojo](https://github.com/DefectDojo/django-DefectDojo) | 3.5.0 | BSD-3-Clause | External multi-service deployment | Scanner reports/REST → findings workflows | FUTURE / planned / advanced |

All listed releases had official release evidence and active upstream maintenance at the
validation date. DefectDojo's supported container architectures were not explicitly
established and are marked `UNVERIFIED` in the registry.

## Security assurance resources

| Resource | Official source | Verified release/spec | License (SPDX) | Exact responsibility | Priority / state |
| --- | --- | --- | --- | --- | --- |
| Sigstore | [sigstore/sigstore](https://github.com/sigstore/sigstore) | v1.11.3 | Apache-2.0 | Trust ecosystem: identity certificates, transparency, roots and bundle formats | FUTURE / planned / advanced |
| Cosign | [sigstore/cosign](https://github.com/sigstore/cosign) | v3.1.4 | Apache-2.0 | OCI signature and attestation verification against identity/key policy | FUTURE / planned / advanced |
| SLSA | [slsa-framework/slsa](https://github.com/slsa-framework/slsa) | specification v1.2 | Community-Spec-1.0 | Assurance requirements and vocabulary; not executable software | FUTURE / planned / advanced |
| in-toto | [in-toto/in-toto](https://github.com/in-toto/in-toto) | v3.0.0 | Apache-2.0 | Verify signed supply-chain layouts and link metadata | FUTURE / planned / advanced |
| Gitleaks | [gitleaks/gitleaks](https://github.com/gitleaks/gitleaks) | v8.30.1 | MIT | Secret pattern detection in Git content | OPTIONAL / disabled |
| Semgrep CE | [semgrep/semgrep](https://github.com/semgrep/semgrep) | v1.184.0 | LGPL-2.1-or-later | Rule-driven source static analysis | OPTIONAL / disabled |
| Bandit | [PyCQA/bandit](https://github.com/PyCQA/bandit) | 1.9.4 | Apache-2.0 | Python AST security linting | OPTIONAL / disabled |
| Checkov | [bridgecrewio/checkov](https://github.com/bridgecrewio/checkov) | 3.4.3 | Apache-2.0 | Infrastructure-as-code and configuration policy analysis | OPTIONAL / disabled |

These capabilities intentionally remain separate. A signature verifier cannot establish
SLSA conformance; a secret detector is not SAST; SAST does not provide dependency
vulnerability intelligence; and an IaC scanner does not inspect runtime artifacts.

## Authentication and security summary

- Local Syft, Grype, Protobom, CycloneDX CLI, Bandit, and local document operations do
  not require application authentication.
- Private registries and repositories require source-specific, read-only credentials.
- Dependency-Track and DefectDojo use API tokens. Keys must be injected through the
  environment/secret manager and scoped to required operations.
- OpenSSF Scorecard uses a source-host token for private repositories and reliable API
  limits.
- Dependency-Check benefits from an NVD API key.
- Sigstore keyless signing uses OIDC; private registries still require registry auth.
- Gitleaks output may contain secret material and needs dedicated redaction/access rules.
- Signing keys, trust roots, and in-toto layouts require a separate trust-policy store;
  they must not be placed in the registry.

## Current boundaries

Prompt 01 remains unchanged conceptually:

1. Syft discovers components and emits raw CycloneDX JSON.
2. Protobom normalizes to SPDX 2.3 JSON while the source is retained.
3. Grype correlates the SBOM with its vulnerability database.
4. ChainGuard stores raw evidence, derived views, hashes, and provenance.
5. Dependency-Track receives the BOM only when configured.

No optional or future catalog resource creates a service, package dependency, or scanner
invocation.
