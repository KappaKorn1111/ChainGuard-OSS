from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Priority(StrEnum):
    core = "CORE"
    secondary = "SECONDARY"
    optional = "OPTIONAL"
    future = "FUTURE"


class EnablementStatus(StrEnum):
    enabled = "enabled"
    disabled = "disabled"
    planned = "planned"


class License(BaseModel):
    name: str
    spdx: str
    source: HttpUrl


class Installation(BaseModel):
    method: str
    locator: str
    pinned: bool


class SupportedEnvironment(BaseModel):
    operating_systems: list[str] = Field(min_length=1)
    architectures: list[str] = Field(min_length=1)
    input_formats: list[str] = Field(default_factory=list)
    output_formats: list[str] = Field(default_factory=list)


class ConfigurationRequirements(BaseModel):
    required: list[str] = Field(default_factory=list)
    authentication: str
    secrets: list[str] = Field(default_factory=list)


class Enablement(BaseModel):
    status: EnablementStatus
    current_integration: str
    rationale: str


class HealthCheck(BaseModel):
    required: bool
    method: str
    target: str | None = None

    @model_validator(mode="after")
    def require_target_for_enabled_check(self) -> "HealthCheck":
        if self.required and not self.target:
            raise ValueError("required health checks must define a target")
        return self


class Maintenance(BaseModel):
    status: Literal["active", "stable", "framework", "unverified"]
    release_evidence: HttpUrl


class RegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    category: str
    official_source: HttpUrl
    documentation: HttpUrl
    verified_version: str
    version_status: Literal["verified", "framework", "unverified"]
    release_verified_at: date
    license: License
    installation: Installation
    capabilities: list[str] = Field(min_length=1)
    responsibility: str
    boundary: str
    dependencies: list[str] = Field(default_factory=list)
    supported: SupportedEnvironment
    interfaces: list[str] = Field(min_length=1)
    configuration: ConfigurationRequirements
    priority: Priority
    tags: list[str] = Field(default_factory=list)
    enablement: Enablement
    health_check: HealthCheck
    security_considerations: list[str] = Field(min_length=1)
    maintenance: Maintenance
    sources: list[HttpUrl] = Field(min_length=2)

    @model_validator(mode="after")
    def enforce_verification_and_enablement(self) -> "RegistryEntry":
        if self.version_status == "unverified" and self.verified_version != "UNVERIFIED":
            raise ValueError("unverified entries must use the UNVERIFIED version marker")
        if self.enablement.status == EnablementStatus.enabled:
            if self.version_status != "verified":
                raise ValueError("enabled tools must have a verified version")
            if not self.installation.pinned:
                raise ValueError("enabled tools must use a pinned installation")
        return self


class ToolRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    generated_at: date
    verification_policy: str
    priority_mapping: dict[Priority, str]
    tools: list[RegistryEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_tool_ids(self) -> "ToolRegistry":
        ids = [tool.id for tool in self.tools]
        if len(ids) != len(set(ids)):
            raise ValueError("tool registry IDs must be unique")
        return self

    def by_id(self, tool_id: str) -> RegistryEntry:
        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        raise KeyError(tool_id)


def load_tool_registry(path: Path | None = None) -> ToolRegistry:
    registry_path = path or Path(__file__).resolve().parents[2] / "config" / "tool-registry.yaml"
    with registry_path.open(encoding="utf-8") as registry_file:
        data = yaml.safe_load(registry_file)
    return ToolRegistry.model_validate(data)
