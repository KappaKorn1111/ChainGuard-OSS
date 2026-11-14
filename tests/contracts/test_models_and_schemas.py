import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from backend.app.contract_schemas import CONTRACT_MODELS
from backend.app.domain import (
    Component,
    SBOMDocument,
    ScanExecution,
    ScanStatus,
    ToolProvenance,
    Vulnerability,
    validate_scan_transition,
)
from backend.app.integrations.errors import ErrorCategory, StructuredError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIRECTORY = ROOT / "backend" / "app" / "schemas" / "generated"


def provenance() -> ToolProvenance:
    return ToolProvenance(
        tenant_id="tenant-a",
        tool_identity="source-tool",
        tool_version=None,
        original_data_source="source-database",
        original_record_id="record-1",
        artifact_checksum="sha256:" + "a" * 64,
        collection_timestamp=datetime.now(UTC),
    )


def test_sbom_contract_round_trip() -> None:
    component = Component(
        tenant_id="tenant-a",
        id="component-1",
        name="example",
        version="1.0",
        purl="pkg:pypi/example@1.0",
    )
    document = SBOMDocument(
        tenant_id="tenant-a",
        id="sbom-1",
        format="CycloneDX-JSON",
        document_schema_version="1.6",
        source_project="project-a",
        source_repository="https://example.invalid/repository",
        commit="abc123",
        artifact_checksum="sha256:" + "b" * 64,
        generated_at=datetime.now(UTC),
        generator_identity="syft",
        generator_version=None,
        original_artifact_location="oci://example.invalid/image@sha256:digest",
        components=[component],
    )
    assert SBOMDocument.model_validate_json(document.model_dump_json()) == document
    assert document.schema_version == "1.0"


def test_vulnerability_requires_provenance() -> None:
    with pytest.raises(ValueError):
        Vulnerability.model_validate(
            {
                "tenant_id": "tenant-a",
                "id": "CVE-2026-12345",
                "source_database": "OSV",
                "affected_package": "pkg:pypi/example@1.0",
            }
        )


def test_committed_json_schemas_match_models_and_validate_instances() -> None:
    assert {path.stem for path in SCHEMA_DIRECTORY.glob("*.json")} == set(CONTRACT_MODELS)
    for name, model in CONTRACT_MODELS.items():
        committed = json.loads((SCHEMA_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))
        assert committed == model.model_json_schema()
        jsonschema.Draft202012Validator.check_schema(committed)

    instance = provenance().model_dump(mode="json")
    schema = json.loads((SCHEMA_DIRECTORY / "tool-provenance-v1.json").read_text())
    jsonschema.validate(instance=instance, schema=schema)


def test_scan_state_machine_and_terminal_contract() -> None:
    validate_scan_transition(ScanStatus.PENDING, ScanStatus.QUEUED)
    validate_scan_transition(ScanStatus.RUNNING, ScanStatus.COMPLETED)
    with pytest.raises(ValueError, match="invalid scan transition"):
        validate_scan_transition(ScanStatus.COMPLETED, ScanStatus.RUNNING)
    with pytest.raises(ValueError, match="completed_at"):
        ScanExecution(
            tenant_id="tenant-a",
            scan_id="scan-a",
            project_id="project-a",
            integration_id="syft",
            status=ScanStatus.COMPLETED,
            correlation_id="correlation-a",
            idempotency_key="idempotency-a",
        )


def test_safe_error_serialization_redacts_nested_secrets() -> None:
    error = StructuredError(
        category=ErrorCategory.UPSTREAM,
        code="UPSTREAM_UNAVAILABLE",
        safe_message="upstream unavailable",
        retryable=True,
        integration_id="dependency-track",
        integration_details={
            "api_token": "sensitive",
            "nested": {"password": "sensitive", "status": 503},
        },
    )
    serialized = error.safe_dump()
    assert serialized["integration_details"]["api_token"] == "[REDACTED]"
    assert serialized["integration_details"]["nested"]["password"] == "[REDACTED]"
    assert "traceback" not in serialized
