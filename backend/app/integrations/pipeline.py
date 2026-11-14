from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class PipelineStageName(StrEnum):
    SOURCE_VALIDATION = "source-validation"
    SBOM_GENERATION = "sbom-generation"
    SBOM_VALIDATION = "sbom-validation"
    SBOM_NORMALIZATION = "sbom-normalization"
    VULNERABILITY_ANALYSIS = "vulnerability-analysis"
    FINDINGS_CORRELATION = "findings-correlation"
    EVIDENCE_PRESERVATION = "evidence-preservation"
    STRUCTURED_SCAN_RESULT = "structured-scan-result"


PIPELINE_ORDER = tuple(PipelineStageName)


class RepositoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    project_id: str
    repository_url: str
    revision: str
    local_path: str | None = None
    artifact_checksum: str | None = None
    correlation_id: str
    idempotency_key: str


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PipelineStageName
    implementation_id: str
    started_at: datetime
    completed_at: datetime
    warnings: list[str] = Field(default_factory=list)


class PipelineContext(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    source: RepositoryInput
    artifacts: dict[str, Any] = Field(default_factory=dict)
    original_evidence: dict[str, bytes] = Field(default_factory=dict, repr=False)
    records: list[StageRecord] = Field(default_factory=list)


class PipelineStage(Protocol):
    name: PipelineStageName
    implementation_id: str
    test_only: bool

    async def run(self, context: PipelineContext) -> PipelineContext: ...


class ScanPipeline:
    def __init__(self, stages: Sequence[PipelineStage], *, test_mode: bool = False) -> None:
        names = tuple(stage.name for stage in stages)
        if names != PIPELINE_ORDER:
            expected = [item.value for item in PIPELINE_ORDER]
            raise ValueError(
                f"pipeline stages must follow the complete contract order: {expected}"
            )
        if not test_mode and any(stage.test_only for stage in stages):
            raise ValueError("test-only pipeline stages are forbidden outside test mode")
        self._stages = tuple(stages)

    async def execute(self, source: RepositoryInput) -> PipelineContext:
        context = PipelineContext(source=source)
        for stage in self._stages:
            started_at = datetime.now(UTC)
            context = await stage.run(context)
            context.records.append(
                StageRecord(
                    stage=stage.name,
                    implementation_id=stage.implementation_id,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )
            )
        return context


PLANNED_STAGE_COMPATIBILITY: dict[str, frozenset[PipelineStageName]] = {
    "syft": frozenset({PipelineStageName.SBOM_GENERATION}),
    "protobom": frozenset({PipelineStageName.SBOM_NORMALIZATION}),
    "grype": frozenset({PipelineStageName.VULNERABILITY_ANALYSIS}),
    "osv-scanner": frozenset({PipelineStageName.VULNERABILITY_ANALYSIS}),
    "trivy": frozenset({PipelineStageName.VULNERABILITY_ANALYSIS}),
    "dependency-track": frozenset({PipelineStageName.VULNERABILITY_ANALYSIS}),
    "cyclonedx-cli": frozenset({PipelineStageName.SBOM_VALIDATION}),
    "guac": frozenset(),
    "openssf-scorecard": frozenset(),
}
