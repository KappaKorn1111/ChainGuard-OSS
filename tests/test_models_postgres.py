import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import (
    IntegrationSetting,
    JobStatus,
    Organization,
    Project,
    ScanJob,
    ScanResult,
    SourceType,
)


def test_uuid_primary_keys_and_tenant_unique_constraints(db_session: Session) -> None:
    organization = Organization(name="Model Test", slug="model-test")
    db_session.add(organization)
    db_session.flush()
    assert isinstance(organization.id, uuid.UUID)

    db_session.add_all(
        [
            Project(organization_id=organization.id, name="One", slug="same"),
            Project(organization_id=organization.id, name="Two", slug="same"),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_integration_settings_reference_central_catalog(db_session: Session) -> None:
    organization = Organization(name="Registry Test", slug="registry-test")
    db_session.add(organization)
    db_session.flush()
    db_session.add(
        IntegrationSetting(
            organization_id=organization.id,
            tool_id="not-a-real-tool",
            enabled=True,
        )
    )
    with pytest.raises(ValueError, match="central catalog"):
        db_session.flush()


def test_integration_settings_reject_plaintext_secrets(db_session: Session) -> None:
    organization = Organization(name="Secret Test", slug="secret-test")
    db_session.add(organization)
    db_session.flush()
    db_session.add(
        IntegrationSetting(
            organization_id=organization.id,
            tool_id="dependency-track",
            configuration={"api_token": "must-not-be-stored"},
        )
    )
    with pytest.raises(ValueError, match="external secret reference"):
        db_session.flush()


def test_prompt01_worker_can_persist_scan_result_with_new_uuid_key(
    db_session: Session,
) -> None:
    job = ScanJob(
        source_type=SourceType.image,
        source_ref="alpine:3.20",
        status=JobStatus.running,
    )
    db_session.add(job)
    db_session.flush()
    result = ScanResult(
        job_id=job.id,
        raw_sbom={},
        normalized_sbom={},
        raw_vulnerability_report={},
        vulnerabilities=[],
        dependencies=[],
        provenance={"source": "worker-compatibility-test"},
    )
    db_session.add(result)
    db_session.flush()
    assert isinstance(result.id, uuid.UUID)
    assert result.legacy_id > 0
