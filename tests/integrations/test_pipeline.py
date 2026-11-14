import asyncio
from dataclasses import dataclass

import pytest

from backend.app.integrations.pipeline import (
    PIPELINE_ORDER,
    PLANNED_STAGE_COMPATIBILITY,
    PipelineContext,
    PipelineStageName,
    RepositoryInput,
    ScanPipeline,
)


@dataclass
class TestStage:
    __test__ = False
    name: PipelineStageName
    test_only: bool = True

    @property
    def implementation_id(self) -> str:
        return f"test-{self.name.value}"

    async def run(self, context: PipelineContext) -> PipelineContext:
        context.artifacts[self.name.value] = True
        if self.name == PipelineStageName.EVIDENCE_PRESERVATION:
            context.original_evidence["scanner.json"] = b'{"source":"unchanged"}'
        return context


def source() -> RepositoryInput:
    return RepositoryInput(
        tenant_id="tenant-a",
        project_id="project-a",
        repository_url="https://example.invalid/repository",
        revision="abc123",
        correlation_id="correlation-a",
        idempotency_key="idempotency-a",
    )


def test_complete_pipeline_is_pluggable_and_ordered() -> None:
    pipeline = ScanPipeline([TestStage(name) for name in PIPELINE_ORDER], test_mode=True)
    result = asyncio.run(pipeline.execute(source()))
    assert tuple(record.stage for record in result.records) == PIPELINE_ORDER
    assert result.original_evidence["scanner.json"] == b'{"source":"unchanged"}'
    assert result.artifacts["structured-scan-result"] is True


def test_pipeline_rejects_missing_or_reordered_stages() -> None:
    with pytest.raises(ValueError, match="complete contract order"):
        ScanPipeline([TestStage(PipelineStageName.SBOM_GENERATION)], test_mode=True)


def test_pipeline_rejects_test_stages_in_production() -> None:
    with pytest.raises(ValueError, match="test-only"):
        ScanPipeline([TestStage(name) for name in PIPELINE_ORDER])


def test_planned_tools_only_claim_compatible_stages() -> None:
    assert PLANNED_STAGE_COMPATIBILITY["syft"] == {PipelineStageName.SBOM_GENERATION}
    assert PLANNED_STAGE_COMPATIBILITY["guac"] == set()
    assert PLANNED_STAGE_COMPATIBILITY["openssf-scorecard"] == set()
