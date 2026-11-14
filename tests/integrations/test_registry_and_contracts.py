import asyncio
from datetime import UTC, datetime

import pytest

from backend.app.integrations.contracts import Capability, Integration
from backend.app.integrations.registry import (
    IntegrationAvailability,
    IntegrationRegistry,
)
from tests.integrations.fakes import FakeRequest, TestOnlySBOMGenerator


def test_fake_implements_typed_integration_contract() -> None:
    adapter = TestOnlySBOMGenerator()
    assert isinstance(adapter, Integration)
    assert adapter.capabilities == {Capability.SBOM_GENERATION}
    assert adapter.input_formats == {"test-input"}
    assert adapter.output_formats == {"test-output"}


def test_registry_rejects_test_adapter_in_production() -> None:
    registry = IntegrationRegistry()
    with pytest.raises(ValueError, match="test-only"):
        registry.register(TestOnlySBOMGenerator(), config={"enabled": True})


def test_registry_tracks_configuration_health_and_success() -> None:
    registry = IntegrationRegistry(test_mode=True)
    adapter = TestOnlySBOMGenerator()
    registry.register(adapter, config={"enabled": True})
    assert registry.state("syft").availability == IntegrationAvailability.AVAILABLE
    registry.set_enabled_capabilities("syft", {Capability.SBOM_GENERATION})
    health = asyncio.run(registry.health_check("syft"))
    assert health.healthy
    result = asyncio.run(adapter.execute(FakeRequest(tenant_id="tenant-a")))
    assert result.payload["test_only"] is True
    assert result.payload["provenance"]["test_only"] is True
    registry.record_success("syft", datetime.now(UTC))
    assert registry.state("syft").last_success_at is not None


def test_registry_exposes_catalog_without_fabricating_runtime_adapter() -> None:
    registry = IntegrationRegistry()
    assert registry.catalog_entry("guac").enablement.status.value == "planned"
    assert registry.state("guac").availability == IntegrationAvailability.PLANNED
    with pytest.raises(KeyError, match="no runtime adapter"):
        registry.get("guac")
