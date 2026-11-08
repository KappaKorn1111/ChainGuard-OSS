import hashlib
import json
import logging
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from celery import Celery
from pythonjsonlogger.json import JsonFormatter
from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database import SessionLocal
from backend.app.models import InspectionJob, JobStatus, ScanResult, SourceType

settings = get_settings()
logger = logging.getLogger("chainguard.worker")
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(settings.log_level)

app = Celery(
    "chainguard-worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=settings.scan_timeout_seconds + 60,
    task_soft_time_limit=settings.scan_timeout_seconds,
)


def run_tool(command: list[str], output_path: Path | None = None) -> str:
    logger.info("scanner_started", extra={"tool": command[0]})
    if output_path:
        with output_path.open("wb") as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=settings.scan_timeout_seconds,
                check=False,
            )
    else:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=settings.scan_timeout_seconds,
            check=False,
        )
    if completed.returncode != 0:
        stderr = completed.stderr.decode(errors="replace")[-4000:]
        raise RuntimeError(f"{command[0]} exited {completed.returncode}: {stderr}")
    logger.info("scanner_completed", extra={"tool": command[0]})
    return completed.stdout.decode(errors="replace") if completed.stdout else ""


def tool_version(name: str) -> str:
    try:
        completed = subprocess.run(
            [name, "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return (completed.stdout or completed.stderr).strip().splitlines()[0][:300]
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        return f"unavailable: {type(exc).__name__}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependencies_from_sbom(sbom: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies = []
    for package in sbom.get("packages", []):
        declared_license = package.get("licenseDeclared")
        licenses = (
            [declared_license]
            if isinstance(declared_license, str) and declared_license != "NOASSERTION"
            else []
        )
        checksums = {
            checksum.get("algorithm", ""): checksum.get("checksumValue", "")
            for checksum in package.get("checksums", [])
        }
        dependencies.append(
            {
                "name": package.get("name", "unknown"),
                "version": package.get("versionInfo"),
                "type": package.get("primaryPackagePurpose"),
                "purl": next(
                    (
                        ref.get("referenceLocator")
                        for ref in package.get("externalRefs", [])
                        if ref.get("referenceType") == "purl"
                    ),
                    None,
                ),
                "licenses": licenses,
                "checksums": checksums,
            }
        )
    return dependencies


def vulnerabilities_from_grype(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for match in report.get("matches", []):
        vulnerability = match.get("vulnerability", {})
        artifact = match.get("artifact", {})
        findings.append(
            {
                "id": vulnerability.get("id", "unknown"),
                "severity": vulnerability.get("severity", "Unknown"),
                "package": artifact.get("name", "unknown"),
                "installed_version": artifact.get("version"),
                "fixed_versions": vulnerability.get("fix", {}).get("versions", []),
                "source": vulnerability.get("namespace"),
                "data_source": vulnerability.get("dataSource"),
                "purl": artifact.get("purl"),
                "match_details": match.get("matchDetails", []),
            }
        )
    return findings


def submit_dependency_track(sbom_path: Path, job_id: str) -> str | None:
    if not settings.dependency_track_enabled:
        return None
    assert settings.dependency_track_url and settings.dependency_track_api_key
    base_url = settings.dependency_track_url.rstrip("/")
    headers = {"X-Api-Key": settings.dependency_track_api_key}
    project_name = f"{settings.dependency_track_project_name}:{job_id}"
    with httpx.Client(base_url=base_url, headers=headers, timeout=60) as client:
        with sbom_path.open("rb") as bom:
            response = client.post(
                "/api/v1/bom",
                data={
                    "autoCreate": "true",
                    "projectName": project_name,
                    "projectVersion": settings.dependency_track_project_version,
                },
                files={"bom": ("sbom.spdx.json", bom, "application/json")},
            )
        response.raise_for_status()
        lookup = client.get(
            "/api/v1/project/lookup",
            params={
                "name": project_name,
                "version": settings.dependency_track_project_version,
            },
        )
        lookup.raise_for_status()
        return lookup.json().get("uuid")


@app.task(name="worker.tasks.inspect_job", bind=True, max_retries=2)
def inspect_job(self, job_id: str) -> None:
    with SessionLocal() as db:
        job = db.scalar(select(InspectionJob).where(InspectionJob.id == job_id))
        if job is None:
            logger.error("job_missing", extra={"job_id": job_id})
            return
        if job.status == JobStatus.completed:
            return
        job.status = JobStatus.running
        job.started_at = datetime.now(UTC)
        job.error = None
        db.commit()

        try:
            source = job.source_ref if job.source_type == SourceType.image else job.artifact_path
            if not source:
                raise RuntimeError("job has no scan source")
            with tempfile.TemporaryDirectory(prefix=f"chainguard-{job_id}-") as temp:
                temp_dir = Path(temp)
                raw_path = temp_dir / "syft.cdx.json"
                normalized_path = temp_dir / "normalized.spdx.json"
                grype_path = temp_dir / "grype.json"

                run_tool(["syft", source, "-o", f"cyclonedx-json={raw_path}"])
                run_tool(
                    [
                        "sbom-convert",
                        "convert",
                        str(raw_path),
                        "--format",
                        "spdx-2.3",
                        "--output",
                        str(normalized_path),
                    ]
                )
                run_tool(["grype", f"sbom:{raw_path}", "-o", "json"], grype_path)

                raw_sbom = json.loads(raw_path.read_text())
                normalized_sbom = json.loads(normalized_path.read_text())
                grype_report = json.loads(grype_path.read_text())
                project_uuid = submit_dependency_track(normalized_path, job_id)
                provenance = {
                    "job_id": job_id,
                    "source_type": job.source_type.value,
                    "source_ref": job.source_ref,
                    "artifact_sha256": job.artifact_sha256,
                    "scanner_output_sha256": {
                        "syft": sha256_file(raw_path),
                        "protobom_normalized": sha256_file(normalized_path),
                        "grype": sha256_file(grype_path),
                    },
                    "tools": {
                        "syft": tool_version("syft"),
                        "grype": tool_version("grype"),
                        "sbom-convert": tool_version("sbom-convert"),
                    },
                    "completed_at": datetime.now(UTC).isoformat(),
                }
                result = ScanResult(
                    job_id=job_id,
                    raw_sbom=raw_sbom,
                    normalized_sbom=normalized_sbom,
                    raw_vulnerability_report=grype_report,
                    vulnerabilities=vulnerabilities_from_grype(grype_report),
                    dependencies=dependencies_from_sbom(normalized_sbom),
                    provenance=provenance,
                    dependency_track_project_uuid=project_uuid,
                )
                existing = db.scalar(select(ScanResult).where(ScanResult.job_id == job_id))
                if existing:
                    db.delete(existing)
                    db.flush()
                db.add(result)
                job.status = JobStatus.completed
                job.completed_at = datetime.now(UTC)
                db.commit()
                logger.info("job_completed", extra={"job_id": job_id})
        except Exception as exc:
            db.rollback()
            job = db.scalar(select(InspectionJob).where(InspectionJob.id == job_id))
            if job:
                job.status = JobStatus.failed
                job.error = str(exc)[:4000]
                job.completed_at = datetime.now(UTC)
                db.commit()
            logger.exception("job_failed", extra={"job_id": job_id})
            if isinstance(exc, (subprocess.TimeoutExpired, httpx.TransportError)) and self.request.retries < 2:
                raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
            raise
