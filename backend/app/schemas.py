from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from .models import JobStatus, MembershipRole, SourceType


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

    id: UUID
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


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)
    organization_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid email address")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    organization_slug: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=8192)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)
    role: MembershipRole = MembershipRole.member

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class MembershipCreate(BaseModel):
    user_id: UUID
    role: MembershipRole = MembershipRole.member


class MembershipUpdate(BaseModel):
    role: MembershipRole


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: MembershipRole
    created_at: datetime
    updated_at: datetime


class MeResponse(BaseModel):
    user: UserRead
    organization: OrganizationRead
    role: MembershipRole


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
    description: str | None = Field(default=None, max_length=5000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class Page[PageItem](BaseModel):
    items: list[PageItem]
    total: int
    limit: int
    offset: int
