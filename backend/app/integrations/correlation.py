from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from backend.app.domain.common import ToolProvenance
from pydantic import BaseModel, ConfigDict, Field

_KNOWN_ID = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA-[0-9A-Z-]+|OSV-[0-9A-Z-]+)$", re.I)


def normalize_vulnerability_id(identifier: str) -> str:
    normalized = identifier.strip().upper()
    return normalized if _KNOWN_ID.fullmatch(normalized) else identifier.strip()


def normalize_purl(purl: str | None) -> str | None:
    if not purl:
        return None
    normalized = purl.strip()
    if not normalized.lower().startswith("pkg:"):
        raise ValueError("package identity must be a valid PURL")
    prefix, remainder = normalized.split(":", 1)
    package_type, separator, package_path = remainder.partition("/")
    return f"{prefix.lower()}:{package_type.lower()}{separator}{package_path}"


class EvidenceRelationship(StrEnum):
    ORIGINAL = "original"
    DUPLICATE = "duplicate"
    CORROBORATION = "corroboration"
    CONFLICT = "conflict"


class IngestedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    source_record_id: str
    vulnerability_id: str
    aliases: list[str] = Field(default_factory=list)
    component_id: str | None = None
    package_purl: str | None = None
    source_database: str
    severity: str | None = None
    affected_range: str | None = None
    fixed_version: str | None = None
    original_record: dict[str, Any]
    provenance: ToolProvenance
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceFindingIngestionContract(Protocol):
    """A source-specific parser that preserves its complete input in each result."""

    source_id: str

    def ingest(
        self,
        record: Mapping[str, Any],
        *,
        tenant_id: str,
        provenance: ToolProvenance,
    ) -> Sequence[IngestedFinding]: ...


class CorrelatedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: IngestedFinding
    relationship: EvidenceRelationship
    conflicts: list[str] = Field(default_factory=list)
    missing_metadata: list[str] = Field(default_factory=list)


class CorrelationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_vulnerability_id: str
    package_purl: str | None
    component_ids: set[str] = Field(default_factory=set)
    evidence: list[CorrelatedEvidence] = Field(default_factory=list)
    aliases: set[str] = Field(default_factory=set)
    history: list[datetime] = Field(default_factory=list)
    confirmed_absent: bool = False


class FindingsCorrelator:
    """Correlates evidence without replacing, suppressing, or inventing source records."""

    def __init__(self) -> None:
        self._groups: dict[tuple[str, str | None, str], CorrelationGroup] = {}
        self._aliases: dict[str, str] = {}

    def ingest(self, finding: IngestedFinding) -> CorrelationGroup:
        primary = normalize_vulnerability_id(finding.vulnerability_id)
        normalized_aliases = {normalize_vulnerability_id(alias) for alias in finding.aliases}
        canonical = self._aliases.get(primary, primary)
        for alias in normalized_aliases:
            canonical = self._aliases.get(alias, canonical)
        for identifier in normalized_aliases | {primary}:
            self._aliases[identifier] = canonical

        purl = normalize_purl(finding.package_purl)
        key = (finding.tenant_id, purl, canonical)
        group = self._groups.setdefault(
            key,
            CorrelationGroup(
                canonical_vulnerability_id=canonical,
                package_purl=purl,
                aliases=normalized_aliases | {primary},
            ),
        )
        group.aliases.update(normalized_aliases | {primary})
        if finding.component_id:
            group.component_ids.add(finding.component_id)

        duplicate = next(
            (
                item
                for item in group.evidence
                if item.finding.provenance.tool_identity == finding.provenance.tool_identity
                and item.finding.source_database == finding.source_database
                and item.finding.source_record_id == finding.source_record_id
            ),
            None,
        )
        independent = any(
            item.finding.source_database != finding.source_database
            or item.finding.provenance.tool_identity != finding.provenance.tool_identity
            for item in group.evidence
        )
        conflicts = self._conflicts(group, finding)
        relationship = (
            EvidenceRelationship.DUPLICATE
            if duplicate
            else EvidenceRelationship.CONFLICT
            if conflicts
            else EvidenceRelationship.CORROBORATION
            if independent
            else EvidenceRelationship.ORIGINAL
        )
        missing = [
            field
            for field in ("severity", "affected_range", "fixed_version", "package_purl")
            if getattr(finding, field) is None
        ]
        group.evidence.append(
            CorrelatedEvidence(
                finding=finding,
                relationship=relationship,
                conflicts=conflicts,
                missing_metadata=missing,
            )
        )
        group.history.append(finding.observed_at)
        return group

    @staticmethod
    def _conflicts(group: CorrelationGroup, incoming: IngestedFinding) -> list[str]:
        conflicts: list[str] = []
        for field in ("severity", "affected_range", "fixed_version"):
            value = getattr(incoming, field)
            prior = {
                getattr(item.finding, field)
                for item in group.evidence
                if getattr(item.finding, field) is not None
            }
            if value is not None and prior and value not in prior:
                conflicts.append(field)
        return conflicts

    def groups(self) -> tuple[CorrelationGroup, ...]:
        return tuple(self._groups.values())
