from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Capability(StrEnum):
    SBOM_GENERATION = "sbom-generation"
    SBOM_NORMALIZATION = "sbom-normalization"
    VULNERABILITY_SCANNING = "vulnerability-scanning"
    VULNERABILITY_INTELLIGENCE = "vulnerability-intelligence"
    COMPONENT_ANALYSIS = "component-analysis"
    REPOSITORY_RISK = "repository-risk"
    SUPPLY_CHAIN_GRAPH = "supply-chain-graph"
    PROVENANCE_VERIFICATION = "provenance-verification"
    ARTIFACT_SIGNATURE_VERIFICATION = "artifact-signature-verification"
    CONTAINER_SCANNING = "container-scanning"
    SOURCE_CODE_SCANNING = "source-code-scanning"
    INFRASTRUCTURE_SCANNING = "infrastructure-scanning"
    SECURITY_FINDINGS = "security-findings"


class IntegrationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)


class VersionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    installed: str | None = None
    catalog_verified: str
    detected_at: datetime | None = None


class ExecutionRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    executable: Path | None = None
    network_required: bool = False
    filesystem_read_required: bool = False
    credentials: tuple[str, ...] = ()


class IntegrationHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    healthy: bool
    status: str
    checked_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class ResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    integration_id: str
    tool_version: str | None
    started_at: datetime
    completed_at: datetime
    source_record_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class IntegrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: ResultMetadata
    payload: dict[str, Any]
    original_output: bytes | None = Field(default=None, repr=False)


class IntegrationErrorCategory(StrEnum):
    CONFIGURATION = "configuration"
    UNAVAILABLE = "unavailable"
    INVALID_INPUT = "invalid-input"
    EXECUTION = "execution"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INVALID_OUTPUT = "invalid-output"
    UPSTREAM = "upstream"


class IntegrationError(Exception):
    def __init__(
        self,
        category: IntegrationErrorCategory,
        safe_message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message
        self.retryable = retryable
        self.details = details or {}
