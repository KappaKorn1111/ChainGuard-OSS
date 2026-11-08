import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class SourceType(enum.StrEnum):
    image = "image"
    archive = "archive"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class InspectionJob(Base):
    __tablename__ = "inspection_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    source_ref: Mapped[str] = mapped_column(String(2048))
    artifact_path: Mapped[str | None] = mapped_column(String(4096))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.queued, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped["ScanResult | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("inspection_jobs.id", ondelete="CASCADE"), unique=True, index=True
    )
    raw_sbom: Mapped[dict] = mapped_column(JSON)
    normalized_sbom: Mapped[dict] = mapped_column(JSON)
    raw_vulnerability_report: Mapped[dict] = mapped_column(JSON)
    vulnerabilities: Mapped[list] = mapped_column(JSON)
    dependencies: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    dependency_track_project_uuid: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[InspectionJob] = relationship(back_populates="result")


Index("ix_inspection_jobs_created_at", InspectionJob.created_at.desc())
