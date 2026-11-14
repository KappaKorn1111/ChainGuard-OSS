from datetime import UTC, datetime

from backend.app.domain import ToolProvenance
from backend.app.integrations.correlation import (
    EvidenceRelationship,
    FindingsCorrelator,
    IngestedFinding,
    normalize_purl,
    normalize_vulnerability_id,
)


def finding(
    *,
    record_id: str,
    vulnerability_id: str = "CVE-2026-12345",
    aliases: list[str] | None = None,
    tool: str = "grype",
    database: str = "grype-db",
    severity: str | None = "high",
    fixed_version: str | None = "2.0",
) -> IngestedFinding:
    now = datetime.now(UTC)
    return IngestedFinding(
        tenant_id="tenant-a",
        source_record_id=record_id,
        vulnerability_id=vulnerability_id,
        aliases=aliases or ["GHSA-AAAA-BBBB-CCCC"],
        component_id="component-1",
        package_purl="pkg:pypi/example@1.0",
        source_database=database,
        severity=severity,
        affected_range="<2.0",
        fixed_version=fixed_version,
        original_record={"id": record_id, "scanner_specific": {"preserved": True}},
        provenance=ToolProvenance(
            tenant_id="tenant-a",
            tool_identity=tool,
            tool_version=None,
            original_data_source=database,
            original_record_id=record_id,
            collection_timestamp=now,
        ),
        observed_at=now,
    )


def test_identifier_and_purl_normalization() -> None:
    assert normalize_vulnerability_id(" cve-2026-12345 ") == "CVE-2026-12345"
    assert normalize_purl("PKG:PyPI/example@1.0") == "pkg:pypi/example@1.0"


def test_duplicate_and_independent_corroboration_are_distinct() -> None:
    correlator = FindingsCorrelator()
    group = correlator.ingest(finding(record_id="grype-1"))
    group = correlator.ingest(finding(record_id="grype-1"))
    assert group.evidence[-1].relationship == EvidenceRelationship.DUPLICATE

    group = correlator.ingest(
        finding(
            record_id="osv-1",
            vulnerability_id="GHSA-AAAA-BBBB-CCCC",
            aliases=["CVE-2026-12345"],
            tool="osv-scanner",
            database="OSV",
        )
    )
    assert group.evidence[-1].relationship == EvidenceRelationship.CORROBORATION
    assert group.evidence[-1].finding.original_record["scanner_specific"]["preserved"] is True
    assert group.confirmed_absent is False


def test_conflicting_evidence_is_retained_and_flagged() -> None:
    correlator = FindingsCorrelator()
    correlator.ingest(finding(record_id="one"))
    group = correlator.ingest(
        finding(
            record_id="two",
            tool="osv-scanner",
            database="OSV",
            severity="critical",
            fixed_version="3.0",
        )
    )
    evidence = group.evidence[-1]
    assert evidence.relationship == EvidenceRelationship.CONFLICT
    assert set(evidence.conflicts) == {"severity", "fixed_version"}
    assert {item.finding.severity for item in group.evidence} == {"high", "critical"}


def test_missing_metadata_is_explicit_not_absence() -> None:
    correlator = FindingsCorrelator()
    item = finding(record_id="sparse", severity=None, fixed_version=None)
    item.affected_range = None
    item.package_purl = None
    group = correlator.ingest(item)
    assert set(group.evidence[0].missing_metadata) == {
        "severity",
        "affected_range",
        "fixed_version",
        "package_purl",
    }
    assert group.confirmed_absent is False
