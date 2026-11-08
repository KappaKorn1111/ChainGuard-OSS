import hashlib
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from celery import Celery
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger.json import JsonFormatter
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_db
from .models import InspectionJob, JobStatus, ScanResult, SourceType
from .schemas import HealthCheck, ImageJobCreate, JobRead, JobResultRead

settings = get_settings()
logger = logging.getLogger("chainguard.api")


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=settings.log_level, handlers=[handler], force=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("api_started", extra={"environment": settings.environment})
    yield


app = FastAPI(
    title="ChainGuard OSS API",
    version="0.1.0",
    description="Continuous software supply-chain inspection API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

celery_client = Celery(
    "chainguard-api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


def dispatch_scan(job_id: str) -> None:
    try:
        celery_client.send_task("worker.tasks.inspect_job", args=[job_id])
    except Exception as exc:
        logger.exception("job_dispatch_failed", extra={"job_id": job_id})
        raise HTTPException(status_code=503, detail="scanner queue is unavailable") from exc


def get_job_or_404(db: Session, job_id: str, *, with_result: bool = False) -> InspectionJob:
    query = select(InspectionJob).where(InspectionJob.id == job_id)
    if with_result:
        query = query.options(selectinload(InspectionJob.result))
    job = db.scalar(query)
    if job is None:
        raise HTTPException(status_code=404, detail="inspection job not found")
    return job


@app.get("/health/live", response_model=HealthCheck, tags=["health"])
def liveness() -> HealthCheck:
    return HealthCheck(status="ok", checks={"api": "ok"})


@app.get("/health/ready", response_model=HealthCheck, tags=["health"])
def readiness(db: Annotated[Session, Depends(get_db)]) -> HealthCheck:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.exception("database_health_failed")
        checks["database"] = "unavailable"
    try:
        Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception:
        logger.exception("redis_health_failed")
        checks["redis"] = "unavailable"
    if any(value != "ok" for value in checks.values()):
        raise HTTPException(status_code=503, detail={"status": "degraded", "checks": checks})
    return HealthCheck(status="ok", checks=checks)


@app.post("/api/v1/jobs", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def create_image_job(
    payload: ImageJobCreate, db: Annotated[Session, Depends(get_db)]
) -> InspectionJob:
    job = InspectionJob(
        source_type=SourceType.image,
        source_ref=payload.image_ref,
        status=JobStatus.queued,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        dispatch_scan(job.id)
    except HTTPException:
        job.status = JobStatus.failed
        job.error = "scanner queue is unavailable"
        db.commit()
        raise
    logger.info("job_created", extra={"job_id": job.id, "source_type": "image"})
    return job


@app.post("/api/v1/jobs/upload", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_archive_job(
    db: Annotated[Session, Depends(get_db)],
    archive: Annotated[UploadFile, File(description="Software archive or filesystem image")],
) -> InspectionJob:
    safe_name = Path(archive.filename or "artifact.bin").name
    job = InspectionJob(
        source_type=SourceType.archive,
        source_ref=safe_name,
        status=JobStatus.queued,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    destination = settings.upload_dir / f"{job.id}-{safe_name}"
    digest = hashlib.sha256()
    written = 0
    try:
        with destination.open("xb") as output:
            while chunk := await archive.read(1024 * 1024):
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="archive exceeds configured limit")
                digest.update(chunk)
                output.write(chunk)
        job.artifact_path = str(destination)
        job.artifact_sha256 = digest.hexdigest()
        db.commit()
        dispatch_scan(job.id)
    except Exception:
        destination.unlink(missing_ok=True)
        job.status = JobStatus.failed
        job.error = "archive ingestion or queue dispatch failed"
        db.commit()
        raise
    finally:
        await archive.close()
    logger.info(
        "archive_ingested",
        extra={"job_id": job.id, "sha256": job.artifact_sha256, "bytes": written},
    )
    return job


@app.get("/api/v1/jobs", response_model=list[JobRead])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InspectionJob]:
    return list(
        db.scalars(
            select(InspectionJob)
            .order_by(InspectionJob.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Annotated[Session, Depends(get_db)]) -> InspectionJob:
    return get_job_or_404(db, job_id)


def completed_result(db: Session, job_id: str) -> tuple[InspectionJob, ScanResult]:
    job = get_job_or_404(db, job_id, with_result=True)
    if job.status != JobStatus.completed or job.result is None:
        raise HTTPException(status_code=409, detail="inspection result is not available")
    return job, job.result


@app.get("/api/v1/jobs/{job_id}/results", response_model=JobResultRead)
def get_result(job_id: str, db: Annotated[Session, Depends(get_db)]) -> JobResultRead:
    job, result = completed_result(db, job_id)
    return JobResultRead(
        job=JobRead.model_validate(job),
        sbom=result.normalized_sbom,
        vulnerabilities=result.vulnerabilities,
        dependencies=result.dependencies,
        provenance=result.provenance,
        dependency_track_project_uuid=result.dependency_track_project_uuid,
    )


@app.get("/api/v1/jobs/{job_id}/sbom")
def get_sbom(job_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    return completed_result(db, job_id)[1].normalized_sbom


@app.get("/api/v1/jobs/{job_id}/vulnerabilities")
def get_vulnerabilities(job_id: str, db: Annotated[Session, Depends(get_db)]) -> list:
    return completed_result(db, job_id)[1].vulnerabilities


@app.get("/api/v1/jobs/{job_id}/dependencies")
def get_dependencies(job_id: str, db: Annotated[Session, Depends(get_db)]) -> list:
    return completed_result(db, job_id)[1].dependencies
