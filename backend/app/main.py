import hashlib
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

import structlog.contextvars
from celery import Celery
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .api import API_ROUTERS
from .config import get_settings
from .database import get_db
from .errors import install_error_handlers
from .logging import configure_logging, get_logger
from .models import InspectionJob, JobStatus, ScanResult, SourceType
from .rate_limit import rate_limit
from .schemas import HealthCheck, ImageJobCreate, JobRead, JobResultRead

settings = get_settings()
logger = get_logger("chainguard.api")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("api_started", environment=settings.environment)
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
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
install_error_handlers(app)
for router in API_ROUTERS:
    app.include_router(
        router,
        prefix="/api/v1",
        dependencies=[Depends(rate_limit())],
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    correlation_id = supplied if _REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
    request.state.request_id = correlation_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=correlation_id,
        method=request.method,
        path=request.url.path,
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response

celery_client = Celery(
    "chainguard-api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


def dispatch_scan(job_id: str) -> None:
    try:
        celery_client.send_task("worker.tasks.inspect_job", args=[job_id])
    except Exception as exc:
        logger.error("job_dispatch_failed", job_id=job_id)
        raise HTTPException(status_code=503, detail="scanner queue is unavailable") from exc


def get_job_or_404(db: Session, job_id: UUID, *, with_result: bool = False) -> InspectionJob:
    query = select(InspectionJob).where(InspectionJob.id == job_id)
    if with_result:
        query = query.options(selectinload(InspectionJob.result))
    job = db.scalar(query)
    if job is None:
        raise HTTPException(status_code=404, detail="inspection job not found")
    return job


@app.get("/health/live", response_model=HealthCheck, tags=["health"])
@app.get("/api/v1/health/live", response_model=HealthCheck, tags=["health"])
def liveness() -> HealthCheck:
    return HealthCheck(status="ok", checks={"api": "ok"})


@app.get("/health/ready", response_model=HealthCheck, tags=["health"])
@app.get("/api/v1/health/ready", response_model=HealthCheck, tags=["health"])
def readiness(db: Annotated[Session, Depends(get_db)]) -> HealthCheck:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.error("database_health_failed")
        checks["database"] = "unavailable"
    try:
        Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception:
        logger.error("redis_health_failed")
        checks["redis"] = "unavailable"
    try:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        checks["migration"] = "ok" if revision == settings.migration_head else "outdated"
    except Exception:
        logger.error("migration_health_failed")
        checks["migration"] = "unavailable"
    if any(value != "ok" for value in checks.values()):
        raise HTTPException(status_code=503, detail={"status": "degraded", "checks": checks})
    return HealthCheck(status="ok", checks=checks)


@app.post(
    "/api/v1/jobs",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit())],
)
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
        dispatch_scan(str(job.id))
    except HTTPException:
        job.status = JobStatus.failed
        job.error = "scanner queue is unavailable"
        db.commit()
        raise
    logger.info("job_created", job_id=str(job.id), source_type="image")
    return job


@app.post(
    "/api/v1/jobs/upload",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit())],
)
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
        dispatch_scan(str(job.id))
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
        job_id=str(job.id),
        sha256=job.artifact_sha256,
        bytes=written,
    )
    return job


@app.get("/api/v1/jobs", response_model=list[JobRead], dependencies=[Depends(rate_limit())])
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


@app.get(
    "/api/v1/jobs/{job_id}",
    response_model=JobRead,
    dependencies=[Depends(rate_limit())],
)
def get_job(job_id: UUID, db: Annotated[Session, Depends(get_db)]) -> InspectionJob:
    return get_job_or_404(db, job_id)


def completed_result(db: Session, job_id: UUID) -> tuple[InspectionJob, ScanResult]:
    job = get_job_or_404(db, job_id, with_result=True)
    if job.status != JobStatus.completed or job.result is None:
        raise HTTPException(status_code=409, detail="inspection result is not available")
    return job, job.result


@app.get(
    "/api/v1/jobs/{job_id}/results",
    response_model=JobResultRead,
    dependencies=[Depends(rate_limit())],
)
def get_result(job_id: UUID, db: Annotated[Session, Depends(get_db)]) -> JobResultRead:
    job, result = completed_result(db, job_id)
    return JobResultRead(
        job=JobRead.model_validate(job),
        sbom=result.normalized_sbom,
        vulnerabilities=result.vulnerabilities,
        dependencies=result.dependencies,
        provenance=result.provenance,
        dependency_track_project_uuid=result.dependency_track_project_uuid,
    )


@app.get("/api/v1/jobs/{job_id}/sbom", dependencies=[Depends(rate_limit())])
def get_sbom(job_id: UUID, db: Annotated[Session, Depends(get_db)]) -> dict:
    return completed_result(db, job_id)[1].normalized_sbom


@app.get("/api/v1/jobs/{job_id}/vulnerabilities", dependencies=[Depends(rate_limit())])
def get_vulnerabilities(job_id: UUID, db: Annotated[Session, Depends(get_db)]) -> list:
    return completed_result(db, job_id)[1].vulnerabilities


@app.get("/api/v1/jobs/{job_id}/dependencies", dependencies=[Depends(rate_limit())])
def get_dependencies(job_id: UUID, db: Annotated[Session, Depends(get_db)]) -> list:
    return completed_result(db, job_id)[1].dependencies
