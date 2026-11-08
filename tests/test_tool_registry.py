from pathlib import Path

import yaml

from backend.app.tool_registry import EnablementStatus, Priority, load_tool_registry

ROOT = Path(__file__).resolve().parents[1]


def test_registry_contains_every_evaluated_security_resource() -> None:
    registry = load_tool_registry()
    expected = {
        "syft",
        "grype",
        "protobom",
        "dependency-track",
        "trivy",
        "osv-scanner",
        "cyclonedx-cli",
        "cdxgen",
        "bomctl",
        "dependency-check",
        "guac",
        "openssf-scorecard",
        "defectdojo",
        "sigstore",
        "cosign",
        "slsa",
        "in-toto",
        "gitleaks",
        "semgrep",
        "bandit",
        "checkov",
    }
    assert {tool.id for tool in registry.tools} == expected
    assert set(registry.priority_mapping) == set(Priority)


def test_only_prompt_01_core_tools_are_enabled() -> None:
    registry = load_tool_registry()
    enabled = {
        tool.id for tool in registry.tools if tool.enablement.status == EnablementStatus.enabled
    }
    assert enabled == {"syft", "grype", "protobom", "dependency-track"}
    assert all(tool.installation.pinned for tool in registry.tools if tool.id in enabled)


def test_enabled_versions_match_worker_and_compose() -> None:
    registry = load_tool_registry()
    worker_dockerfile = (ROOT / "worker" / "Dockerfile").read_text()
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())

    assert registry.by_id("syft").installation.locator in worker_dockerfile
    assert registry.by_id("grype").installation.locator in worker_dockerfile
    assert "github.com/protobom/sbom-convert@v0.0.8" in worker_dockerfile

    dtrack_version = registry.by_id("dependency-track").verified_version
    assert compose["services"]["dependency-track-api"]["image"] == (
        f"ghcr.io/dependencytrack/apiserver:{dtrack_version}"
    )
    assert compose["services"]["dependency-track-frontend"]["image"] == (
        f"ghcr.io/dependencytrack/frontend:{dtrack_version}"
    )


def test_catalog_entries_are_traceable_and_do_not_install_optional_tools() -> None:
    registry = load_tool_registry()
    compose_text = (ROOT / "compose.yaml").read_text()
    worker_dockerfile = (ROOT / "worker" / "Dockerfile").read_text()

    for tool in registry.tools:
        assert tool.official_source.host == "github.com"
        assert len(tool.sources) >= 2
        if tool.enablement.status != EnablementStatus.enabled:
            assert tool.installation.locator not in compose_text
            assert tool.installation.locator not in worker_dockerfile


def test_dependency_track_v5_and_security_patch_configuration() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]
    dtrack = services["dependency-track-api"]

    assert services["redis"]["image"] == "redis:8.10.1-alpine"
    assert services["postgres"]["image"] == "postgres:17.11-bookworm"
    assert services["dtrack-postgres"]["image"] == "postgres:17.11-bookworm"
    assert set(dtrack["environment"]) >= {
        "DT_DATASOURCE_URL",
        "DT_DATASOURCE_USERNAME",
        "DT_DATASOURCE_PASSWORD",
        "DT_CORS_ALLOWED_ORIGINS",
    }
    assert not any(key.startswith("ALPINE_") for key in dtrack["environment"])
    assert "127.0.0.1:9000/health" in " ".join(dtrack["healthcheck"]["test"])
