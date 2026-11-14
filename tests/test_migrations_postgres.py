import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.config import get_settings


def test_upgrade_downgrade_upgrade_preserves_prompt01_scan_data() -> None:
    base_url = make_url(get_settings().database_url)
    database_name = f"chainguard_migration_{uuid.uuid4().hex[:12]}"
    admin_url = base_url.set(database="postgres")
    admin_dsn = admin_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{database_name}"')
    test_url = base_url.set(database=database_name)
    config = Config(str(Path(__file__).resolve().parents[1] / "backend" / "alembic.ini"))
    config.attributes["database_url"] = test_url.render_as_string(hide_password=False)
    engine = create_engine(test_url)
    job_id = str(uuid.uuid4())
    try:
        command.upgrade(config, "0001")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO inspection_jobs
                        (id, source_type, source_ref, status, created_at)
                    VALUES (:id, 'image', 'alpine:3.20', 'completed', :created_at)
                    """
                ),
                {"id": job_id, "created_at": datetime.now(UTC)},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO scan_results
                        (job_id, raw_sbom, normalized_sbom, raw_vulnerability_report,
                         vulnerabilities, dependencies, provenance, created_at)
                    VALUES
                        (:job_id, '{}', '{}', '{}', '[]', '[]', '{"source":"prompt-01"}',
                         :created_at)
                    """
                ),
                {"job_id": job_id, "created_at": datetime.now(UTC)},
            )

        command.upgrade(config, "head")
        new_job_id = str(uuid.uuid4())
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    """
                    SELECT j.id::text, r.legacy_id, r.provenance->>'source'
                    FROM inspection_jobs j JOIN scan_results r ON r.job_id = j.id
                    """
                )
            ).one()
            assert migrated == (job_id, 1, "prompt-01")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO inspection_jobs
                        (id, source_type, source_ref, status)
                    VALUES (:id, 'repository', 'https://example.invalid/repo', 'timed_out')
                    """
                ),
                {"id": new_job_id},
            )

        command.downgrade(config, "0001")
        with engine.connect() as connection:
            restored = connection.execute(
                text(
                    """
                    SELECT j.id, r.id, r.provenance->>'source'
                    FROM inspection_jobs j JOIN scan_results r ON r.job_id = j.id
                    """
                )
            ).one()
            assert restored == (job_id, 1, "prompt-01")
            mapped = connection.execute(
                text("SELECT source_type, status FROM inspection_jobs WHERE id = :id"),
                {"id": new_job_id},
            ).one()
            assert mapped == ("archive", "failed")

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
    finally:
        engine.dispose()
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
