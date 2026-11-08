from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from .models import JobStatus, SourceType


class ImageJobCreate(BaseModel):
    image_ref: str = Field(min_length=1, max_length=2048, examples=["alpine:3.20"])

    @field_validator("image_ref")
    @classmethod
    def reject_flags(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("-") or any(char in value for char in ("\x00", "\n", "\r")):
            raise ValueError("invalid image reference")
        return value


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: SourceType
    source_ref: str
    artifact_sha256: str | None
    status: JobStatus
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class DependencyRead(BaseModel):
    name: str
    version: str | None = None
    type: str | None = None
    purl: str | None = None
    licenses: list[str] = Field(default_factory=list)


class VulnerabilityRead(BaseModel):
    id: str
    severity: str
    package: str
    installed_version: str | None = None
    fixed_versions: list[str] = Field(default_factory=list)
    source: str | None = None
    data_source: HttpUrl | None = None


class JobResultRead(BaseModel):
    job: JobRead
    sbom: dict[str, Any]
    vulnerabilities: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    provenance: dict[str, Any]
    dependency_track_project_uuid: str | None


class HealthCheck(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(default_factory=dict)
