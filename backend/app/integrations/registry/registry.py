from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from backend.app.integrations.contracts import Capability, Integration, IntegrationHealth
from backend.app.tool_registry import (
    EnablementStatus,
    RegistryEntry,
    ToolRegistry,
    load_tool_registry,
)
from pydantic import BaseModel, ConfigDict, Field


class IntegrationAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    MISCONFIGURED = "misconfigured"
    DISABLED = "disabled"
    PLANNED = "planned"


class IntegrationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration_id: str
    availability: IntegrationAvailability
    enabled_capabilities: set[str] = Field(default_factory=set)
    installed_version: str | None = None
    last_health: IntegrationHealth | None = None
    last_error: str | None = None
    last_success_at: datetime | None = None


class IntegrationRegistry:
    """Runtime adapter registry backed by Prompt 02's catalog."""

    def __init__(
        self,
        catalog: ToolRegistry | None = None,
        *,
        test_mode: bool = False,
    ) -> None:
        self.catalog = catalog or load_tool_registry()
        self.test_mode = test_mode
        self._adapters: dict[str, Integration[Any]] = {}
        self._configuration: dict[str, Mapping[str, Any]] = {}
        self._states = {
            entry.id: self._initial_state(entry)
            for entry in self.catalog.tools
        }

    @staticmethod
    def _initial_state(entry: RegistryEntry) -> IntegrationState:
        status = entry.enablement.status
        availability = (
            IntegrationAvailability.DISABLED
            if status == EnablementStatus.disabled
            else IntegrationAvailability.PLANNED
            if status == EnablementStatus.planned
            else IntegrationAvailability.UNAVAILABLE
        )
        return IntegrationState(
            integration_id=entry.id,
            availability=availability,
            enabled_capabilities=(
                set(entry.capabilities) if status == EnablementStatus.enabled else set()
            ),
        )

    def register(
        self,
        adapter: Integration[Any],
        *,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        integration_id = adapter.identity.id
        if integration_id not in self.catalog.available_ids():
            raise ValueError(f"integration {integration_id!r} is not in the central tool registry")
        if adapter.test_only and not self.test_mode:
            raise ValueError("test-only adapters cannot be registered outside test mode")
        if integration_id in self._adapters:
            raise ValueError(f"integration {integration_id!r} is already registered")
        errors = adapter.validate_config(config or {})
        state = self._states[integration_id]
        state.installed_version = adapter.version.installed
        if errors:
            state.availability = IntegrationAvailability.MISCONFIGURED
            state.last_error = "; ".join(errors)
        else:
            state.availability = IntegrationAvailability.AVAILABLE
            state.last_error = None
        self._adapters[integration_id] = adapter
        self._configuration[integration_id] = config or {}

    def get(self, integration_id: str) -> Integration[Any]:
        try:
            return self._adapters[integration_id]
        except KeyError as error:
            raise KeyError(f"integration {integration_id!r} has no runtime adapter") from error

    def catalog_entry(self, integration_id: str) -> RegistryEntry:
        return self.catalog.by_id(integration_id)

    def state(self, integration_id: str) -> IntegrationState:
        return self._states[integration_id].model_copy(deep=True)

    def report_capabilities(self, integration_id: str) -> set[str]:
        adapter = self._adapters.get(integration_id)
        if adapter:
            return {capability.value for capability in adapter.capabilities}
        return set(self.catalog.by_id(integration_id).capabilities)

    def set_enabled_capabilities(
        self, integration_id: str, capabilities: set[Capability]
    ) -> None:
        adapter = self.get(integration_id)
        unsupported = capabilities - set(adapter.capabilities)
        if unsupported:
            raise ValueError(f"adapter does not declare capabilities: {sorted(unsupported)}")
        self._states[integration_id].enabled_capabilities = {
            capability.value for capability in capabilities
        }

    def disable(self, integration_id: str) -> None:
        self._states[integration_id].availability = IntegrationAvailability.DISABLED

    async def health_check(self, integration_id: str) -> IntegrationHealth:
        adapter = self.get(integration_id)
        state = self._states[integration_id]
        try:
            health = await adapter.health_check()
        except Exception:
            state.last_error = "integration health check failed"
            state.availability = IntegrationAvailability.UNAVAILABLE
            raise
        state.last_health = health
        state.availability = (
            IntegrationAvailability.AVAILABLE
            if health.healthy
            else IntegrationAvailability.UNAVAILABLE
        )
        if health.healthy:
            state.last_success_at = health.checked_at
            state.last_error = None
        return health

    def record_error(self, integration_id: str, safe_message: str) -> None:
        state = self._states[integration_id]
        state.last_error = safe_message
        state.availability = IntegrationAvailability.UNAVAILABLE

    def record_success(self, integration_id: str, at: datetime) -> None:
        state = self._states[integration_id]
        state.last_success_at = at
        state.last_error = None
