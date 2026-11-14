from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from backend.app.domain import ToolProvenance
from backend.app.integrations.contracts import (
    Capability,
    ExecutionRequirements,
    IntegrationHealth,
    IntegrationIdentity,
    IntegrationResult,
    ResultMetadata,
    SBOMGenerator,
    VersionInfo,
)


class FakeRequest(BaseModel):
    tenant_id: str


class TestOnlySBOMGenerator(SBOMGenerator[FakeRequest]):
    __test__ = False
    test_only = True

    @property
    def identity(self) -> IntegrationIdentity:
        return IntegrationIdentity(id="syft", name="Test-only SBOM generator")

    @property
    def version(self) -> VersionInfo:
        return VersionInfo(installed="test-only", catalog_verified="test-only")

    @property
    def capabilities(self) -> AbstractSet[Capability]:
        return {Capability.SBOM_GENERATION}

    @property
    def execution_requirements(self) -> ExecutionRequirements:
        return ExecutionRequirements()

    @property
    def input_formats(self) -> AbstractSet[str]:
        return {"test-input"}

    @property
    def output_formats(self) -> AbstractSet[str]:
        return {"test-output"}

    def validate_config(self, config: Mapping[str, Any]) -> tuple[str, ...]:
        return () if config.get("enabled") is True else ("enabled must be true",)

    async def health_check(self) -> IntegrationHealth:
        return IntegrationHealth(
            healthy=True,
            status="test-only",
            checked_at=datetime.now(UTC),
            details={"test_only": True},
        )

    async def execute(self, request: FakeRequest) -> IntegrationResult:
        now = datetime.now(UTC)
        provenance = ToolProvenance(
            tenant_id=request.tenant_id,
            tool_identity="test-only-sbom-generator",
            tool_version="test-only",
            original_data_source="controlled-test-fixture",
            original_record_id="test-record",
            collection_timestamp=now,
            test_only=True,
        )
        return IntegrationResult(
            metadata=ResultMetadata(
                integration_id="syft",
                tool_version="test-only",
                started_at=now,
                completed_at=now,
            ),
            payload={
                "tenant_id": request.tenant_id,
                "test_only": True,
                "provenance": provenance.model_dump(mode="json"),
            },
            original_output=b'{"test_only":true}',
        )
