"""Add tenant backend entities while preserving inspection evidence.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("CURRENT_TIMESTAMP")
NEW_UUID = sa.text("gen_random_uuid()")
SOURCE_TYPE = sa.Enum(
    "image",
    "archive",
    "repository",
    name="sourcetype",
    native_enum=False,
)
JOB_STATUS = sa.Enum(
    "pending",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "partially_completed",
    name="jobstatus",
    native_enum=False,
)
MEMBERSHIP_ROLE = sa.Enum(
    "owner",
    "admin",
    "member",
    "viewer",
    name="membershiprole",
    native_enum=False,
)


def id_column() -> sa.Column:
    return sa.Column("id", UUID, server_default=NEW_UUID, nullable=False)


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        id_column(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.false(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "organizations",
        id_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "organization_memberships",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role", MEMBERSHIP_ROLE, nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index(
        "ix_memberships_org_role", "organization_memberships", ["organization_id", "role"]
    )
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_memberships_user_id", "organization_memberships", ["user_id"]
    )

    op.create_table(
        "projects",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_index("ix_projects_org_name", "projects", ["organization_id", "name"])

    op.create_table(
        "repositories",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "url", name="uq_repositories_project_url"),
    )
    op.create_index("ix_repositories_organization_id", "repositories", ["organization_id"])
    op.create_index("ix_repositories_project_id", "repositories", ["project_id"])
    op.create_index(
        "ix_repositories_org_project", "repositories", ["organization_id", "project_id"]
    )

    # Existing UUID strings are converted in place. Scanner rows and their relationship survive.
    op.drop_constraint("scan_results_job_id_fkey", "scan_results", type_="foreignkey")
    op.alter_column(
        "inspection_jobs",
        "id",
        existing_type=sa.String(36),
        type_=UUID,
        postgresql_using="id::uuid",
    )
    op.alter_column(
        "scan_results",
        "job_id",
        existing_type=sa.String(36),
        type_=UUID,
        postgresql_using="job_id::uuid",
    )
    op.create_foreign_key(
        "scan_results_job_id_fkey",
        "scan_results",
        "inspection_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "inspection_jobs",
        "source_type",
        existing_type=sa.String(7),
        type_=SOURCE_TYPE,
        nullable=False,
    )
    op.alter_column(
        "inspection_jobs",
        "status",
        existing_type=sa.String(9),
        type_=JOB_STATUS,
        nullable=False,
    )
    op.drop_constraint("scan_results_pkey", "scan_results", type_="primary")
    op.alter_column("scan_results", "id", new_column_name="legacy_id")
    op.add_column("scan_results", sa.Column("id", UUID, server_default=NEW_UUID, nullable=False))
    op.create_primary_key("scan_results_pkey", "scan_results", ["id"])
    op.create_unique_constraint("uq_scan_results_legacy_id", "scan_results", ["legacy_id"])

    op.add_column("inspection_jobs", sa.Column("organization_id", UUID, nullable=True))
    op.add_column("inspection_jobs", sa.Column("project_id", UUID, nullable=True))
    op.add_column("inspection_jobs", sa.Column("repository_id", UUID, nullable=True))
    op.add_column(
        "inspection_jobs",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.add_column("inspection_jobs", sa.Column("correlation_id", sa.String(100), nullable=True))
    op.add_column("inspection_jobs", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.create_foreign_key(
        "fk_inspection_jobs_organization",
        "inspection_jobs",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_inspection_jobs_project",
        "inspection_jobs",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inspection_jobs_repository",
        "inspection_jobs",
        "repositories",
        ["repository_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_scan_jobs_org_idempotency", "inspection_jobs", ["organization_id", "idempotency_key"]
    )
    op.create_index(
        "ix_inspection_jobs_organization_id", "inspection_jobs", ["organization_id"]
    )
    op.create_index("ix_inspection_jobs_project_id", "inspection_jobs", ["project_id"])
    op.create_index("ix_inspection_jobs_repository_id", "inspection_jobs", ["repository_id"])
    op.create_index("ix_inspection_jobs_correlation_id", "inspection_jobs", ["correlation_id"])
    op.create_index(
        "ix_inspection_jobs_org_status", "inspection_jobs", ["organization_id", "status"]
    )
    op.alter_column(
        "inspection_jobs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=NOW,
    )

    op.add_column("scan_results", sa.Column("organization_id", UUID, nullable=True))
    op.add_column(
        "scan_results",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_foreign_key(
        "fk_scan_results_organization",
        "scan_results",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_scan_results_organization_id", "scan_results", ["organization_id"])
    op.alter_column(
        "scan_results",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=NOW,
    )

    op.create_table(
        "sbom_artifacts",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("scan_result_id", UUID, nullable=False),
        sa.Column("format", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("checksum", sa.String(150), nullable=False),
        sa.Column("location", sa.String(4096), nullable=True),
        sa.Column("document", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_result_id"], ["scan_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "checksum", name="uq_sbom_artifacts_org_checksum"
        ),
    )
    op.create_index("ix_sbom_artifacts_organization_id", "sbom_artifacts", ["organization_id"])
    op.create_index("ix_sbom_artifacts_scan_result_id", "sbom_artifacts", ["scan_result_id"])

    op.create_table(
        "components",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("sbom_artifact_id", UUID, nullable=False),
        sa.Column("component_key", sa.String(500), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("version", sa.String(255), nullable=True),
        sa.Column("purl", sa.String(2048), nullable=True),
        sa.Column("ecosystem", sa.String(100), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sbom_artifact_id"], ["sbom_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sbom_artifact_id", "component_key", name="uq_components_artifact_key"
        ),
    )
    op.create_index("ix_components_organization_id", "components", ["organization_id"])
    op.create_index("ix_components_sbom_artifact_id", "components", ["sbom_artifact_id"])
    op.create_index("ix_components_org_purl", "components", ["organization_id", "purl"])

    op.create_table(
        "vulnerabilities",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("vulnerability_id", sa.String(100), nullable=False),
        sa.Column("source_database", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=True),
        sa.Column("cvss_score", sa.Float(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("advisory", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "source_database",
            "vulnerability_id",
            name="uq_vuln_org_source_id",
        ),
    )
    op.create_index("ix_vulnerabilities_organization_id", "vulnerabilities", ["organization_id"])
    op.create_index(
        "ix_vulnerabilities_org_severity", "vulnerabilities", ["organization_id", "severity"]
    )

    op.create_table(
        "scan_findings",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("scan_result_id", UUID, nullable=False),
        sa.Column("component_id", UUID, nullable=True),
        sa.Column("vulnerability_id", UUID, nullable=True),
        sa.Column("source_finding_id", sa.String(500), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(50), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_result_id"], ["scan_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["vulnerability_id"], ["vulnerabilities.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scan_result_id", "source_finding_id", name="uq_findings_result_source_id"
        ),
    )
    for column in (
        "organization_id",
        "scan_result_id",
        "component_id",
        "vulnerability_id",
    ):
        op.create_index(f"ix_scan_findings_{column}", "scan_findings", [column])
    op.create_index(
        "ix_findings_org_severity", "scan_findings", ["organization_id", "severity"]
    )

    op.create_table(
        "security_policies",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_policies_org_name"),
    )
    op.create_index(
        "ix_security_policies_organization_id",
        "security_policies",
        ["organization_id"],
    )

    op.create_table(
        "notifications",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "ix_notifications_org_read", "notifications", ["organization_id", "read_at"]
    )

    op.create_table(
        "audit_logs",
        id_column(),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["organization_id", "created_at"])

    op.create_table(
        "integration_settings",
        id_column(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("secret_reference", sa.String(500), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "tool_id", name="uq_integration_settings_org_tool"
        ),
    )
    op.create_index(
        "ix_integration_settings_organization_id", "integration_settings", ["organization_id"]
    )
    op.create_index("ix_integration_settings_tool_id", "integration_settings", ["tool_id"])

    op.create_table(
        "refresh_tokens",
        id_column(),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("family_id", UUID, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", UUID, nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_organization_id", "refresh_tokens", ["organization_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_index(
        "ix_refresh_tokens_user_family", "refresh_tokens", ["user_id", "family_id"]
    )


def downgrade() -> None:
    for table in (
        "refresh_tokens",
        "integration_settings",
        "audit_logs",
        "notifications",
        "security_policies",
        "scan_findings",
        "vulnerabilities",
        "components",
        "sbom_artifacts",
    ):
        op.drop_table(table)

    op.drop_index("ix_scan_results_organization_id", table_name="scan_results")
    op.alter_column(
        "scan_results",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
    )
    op.drop_constraint("fk_scan_results_organization", "scan_results", type_="foreignkey")
    op.drop_column("scan_results", "organization_id")
    op.drop_column("scan_results", "updated_at")

    op.drop_index("ix_inspection_jobs_org_status", table_name="inspection_jobs")
    op.alter_column(
        "inspection_jobs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
    )
    op.drop_index("ix_inspection_jobs_correlation_id", table_name="inspection_jobs")
    op.drop_index("ix_inspection_jobs_repository_id", table_name="inspection_jobs")
    op.drop_index("ix_inspection_jobs_project_id", table_name="inspection_jobs")
    op.drop_index("ix_inspection_jobs_organization_id", table_name="inspection_jobs")
    op.drop_constraint("uq_scan_jobs_org_idempotency", "inspection_jobs", type_="unique")
    op.drop_constraint("fk_inspection_jobs_repository", "inspection_jobs", type_="foreignkey")
    op.drop_constraint("fk_inspection_jobs_project", "inspection_jobs", type_="foreignkey")
    op.drop_constraint("fk_inspection_jobs_organization", "inspection_jobs", type_="foreignkey")
    for column in (
        "idempotency_key",
        "correlation_id",
        "updated_at",
        "repository_id",
        "project_id",
        "organization_id",
    ):
        op.drop_column("inspection_jobs", column)

    op.drop_constraint("scan_results_job_id_fkey", "scan_results", type_="foreignkey")
    op.execute(
        """
        UPDATE inspection_jobs
        SET source_type = 'archive'
        WHERE source_type = 'repository'
        """
    )
    op.execute(
        """
        UPDATE inspection_jobs
        SET status = CASE
            WHEN status = 'pending' THEN 'queued'
            WHEN status IN ('cancelled', 'timed_out') THEN 'failed'
            WHEN status = 'partially_completed' THEN 'completed'
            ELSE status
        END
        """
    )
    op.alter_column(
        "inspection_jobs",
        "source_type",
        existing_type=SOURCE_TYPE,
        type_=sa.String(7),
        nullable=True,
    )
    op.alter_column(
        "inspection_jobs",
        "status",
        existing_type=JOB_STATUS,
        type_=sa.String(9),
        nullable=False,
    )
    op.alter_column(
        "inspection_jobs",
        "id",
        existing_type=UUID,
        type_=sa.String(36),
        postgresql_using="id::text",
    )
    op.alter_column(
        "scan_results",
        "job_id",
        existing_type=UUID,
        type_=sa.String(36),
        postgresql_using="job_id::text",
    )
    op.create_foreign_key(
        "scan_results_job_id_fkey",
        "scan_results",
        "inspection_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_scan_results_legacy_id", "scan_results", type_="unique")
    op.drop_constraint("scan_results_pkey", "scan_results", type_="primary")
    op.drop_column("scan_results", "id")
    op.alter_column("scan_results", "legacy_id", new_column_name="id")
    op.create_primary_key("scan_results_pkey", "scan_results", ["id"])

    op.drop_table("repositories")
    op.drop_table("projects")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
    op.drop_table("users")
