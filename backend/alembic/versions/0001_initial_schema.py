"""Create inspection jobs and immutable scan evidence.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inspection_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "source_type", sa.Enum("image", "archive", name="sourcetype", native_enum=False)
        ),
        sa.Column("source_ref", sa.String(length=2048), nullable=False),
        sa.Column("artifact_path", sa.String(length=4096), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="jobstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspection_jobs_created_at", "inspection_jobs", ["created_at"])
    op.create_index("ix_inspection_jobs_status", "inspection_jobs", ["status"])
    op.create_table(
        "scan_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("raw_sbom", sa.JSON(), nullable=False),
        sa.Column("normalized_sbom", sa.JSON(), nullable=False),
        sa.Column("raw_vulnerability_report", sa.JSON(), nullable=False),
        sa.Column("vulnerabilities", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("dependency_track_project_uuid", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["inspection_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_scan_results_job_id", "scan_results", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_results_job_id", table_name="scan_results")
    op.drop_table("scan_results")
    op.drop_index("ix_inspection_jobs_status", table_name="inspection_jobs")
    op.drop_index("ix_inspection_jobs_created_at", table_name="inspection_jobs")
    op.drop_table("inspection_jobs")
