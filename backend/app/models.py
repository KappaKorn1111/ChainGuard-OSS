import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    FetchedValue,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SourceType(enum.StrEnum):
    image = "image"
    archive = "archive"
    repository = "repository"


class JobStatus(enum.StrEnum):
    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed-out"
    partially_completed = "partially-completed"


class MembershipRole(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMembership(Base, TimestampMixin):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        Index("ix_memberships_org_role", "organization_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, native_enum=False), default=MembershipRole.member
    )
    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
        Index("ix_projects_org_name", "organization_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("project_id", "url", name="uq_repositories_project_url"),
        Index("ix_repositories_org_project", "organization_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2048))
    default_branch: Mapped[str | None] = mapped_column(String(255))


class ScanJob(Base, TimestampMixin):
    __tablename__ = "inspection_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_scan_jobs_org_idempotency"),
        Index("ix_inspection_jobs_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    source_ref: Mapped[str] = mapped_column(String(2048))
    artifact_path: Mapped[str | None] = mapped_column(String(4096))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.queued, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    result: Mapped["ScanResult | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


InspectionJob = ScanJob


class ScanResult(Base, TimestampMixin):
    __tablename__ = "scan_results"
    __table_args__ = (
        UniqueConstraint("job_id"),
        UniqueConstraint("legacy_id", name="uq_scan_results_legacy_id"),
        Index("ix_scan_results_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=new_uuid, server_default=func.gen_random_uuid()
    )
    legacy_id: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspection_jobs.id", ondelete="CASCADE")
    )
    raw_sbom: Mapped[dict] = mapped_column(JSON)
    normalized_sbom: Mapped[dict] = mapped_column(JSON)
    raw_vulnerability_report: Mapped[dict] = mapped_column(JSON)
    vulnerabilities: Mapped[list] = mapped_column(JSON)
    dependencies: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    dependency_track_project_uuid: Mapped[str | None] = mapped_column(String(36))
    job: Mapped[ScanJob] = relationship(back_populates="result")


class SBOMArtifact(Base, TimestampMixin):
    __tablename__ = "sbom_artifacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "checksum", name="uq_sbom_artifacts_org_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    scan_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scan_results.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[str] = mapped_column(String(50))
    checksum: Mapped[str] = mapped_column(String(150))
    location: Mapped[str | None] = mapped_column(String(4096))
    document: Mapped[dict[str, Any]] = mapped_column(JSON)


class ComponentRecord(Base, TimestampMixin):
    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint("sbom_artifact_id", "component_key", name="uq_components_artifact_key"),
        Index("ix_components_org_purl", "organization_id", "purl"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    sbom_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sbom_artifacts.id", ondelete="CASCADE"), index=True
    )
    component_key: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(255))
    purl: Mapped[str | None] = mapped_column(String(2048))
    ecosystem: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class VulnerabilityRecord(Base, TimestampMixin):
    __tablename__ = "vulnerabilities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_database", "vulnerability_id", name="uq_vuln_org_source_id"
        ),
        Index("ix_vulnerabilities_org_severity", "organization_id", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    vulnerability_id: Mapped[str] = mapped_column(String(100))
    source_database: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(50))
    cvss_score: Mapped[float | None] = mapped_column(Float)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    advisory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ScanFinding(Base, TimestampMixin):
    __tablename__ = "scan_findings"
    __table_args__ = (
        UniqueConstraint(
            "scan_result_id", "source_finding_id", name="uq_findings_result_source_id"
        ),
        Index("ix_findings_org_severity", "organization_id", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    scan_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scan_results.id", ondelete="CASCADE"), index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), index=True
    )
    vulnerability_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vulnerabilities.id", ondelete="SET NULL"), index=True
    )
    source_finding_id: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(50))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified")


class SecurityPolicy(Base, TimestampMixin):
    __tablename__ = "security_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_policies_org_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_org_read", "organization_id", "read_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(200), index=True)
    target_type: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IntegrationSetting(Base, TimestampMixin):
    __tablename__ = "integration_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", "tool_id", name="uq_integration_settings_org_tool"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    tool_id: Mapped[str] = mapped_column(String(100), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    secret_reference: Mapped[str | None] = mapped_column(String(500))


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),
        Index("ix_refresh_tokens_user_family", "user_id", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )


Index("ix_inspection_jobs_created_at", InspectionJob.created_at)


@event.listens_for(IntegrationSetting, "before_insert")
@event.listens_for(IntegrationSetting, "before_update")
def validate_integration_tool_id(_mapper, _connection, target: IntegrationSetting) -> None:
    from .tool_registry import load_tool_registry

    if target.tool_id not in load_tool_registry().available_ids():
        raise ValueError("integration setting tool_id is not present in the central catalog")
    sensitive = {"password", "secret", "token", "api_key", "credential"}

    def contains_secret_key(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                any(marker in str(key).lower() for marker in sensitive)
                or contains_secret_key(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(contains_secret_key(item) for item in value)
        return False

    if contains_secret_key(target.configuration):
        raise ValueError("integration secrets must use an external secret reference")
