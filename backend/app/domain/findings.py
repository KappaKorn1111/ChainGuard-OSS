from datetime import datetime
from enum import StrEnum
from typing import Any

from .common import ContractModel, ToolProvenance


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    FALSE_POSITIVE = "false-positive"


class SecurityFinding(ContractModel):
    id: str
    category: str
    related_component_id: str | None = None
    related_vulnerability_id: str | None = None
    detection_source: str
    severity: str | None = None
    evidence: dict[str, Any]
    remediation: str | None = None
    detected_at: datetime
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    provenance: ToolProvenance
