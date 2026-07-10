"""Add versioned pipeline definitions and bind runs to published versions.

Revision ID: 0006_versioned_pipeline_control
Revises: 0005_provider_credential_validation
Create Date: 2026-07-10
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_versioned_pipeline_control"
down_revision: str | None = "0005_provider_credential_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stable_identifier(name: str, row_id: int) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return (normalized or f"stage-{row_id}")[:100]


def upgrade() -> None:
    op.create_table(
        "pipeline_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=50), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("change_description", sa.Text(), server_default="", nullable=False),
        sa.Column("validation_status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("validation_issues", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version_number > 0",
            name=op.f("ck_pipeline_versions_pipeline_version_positive_number"),
        ),
        sa.CheckConstraint(
            "state IN ('draft', 'published', 'superseded')",
            name=op.f("ck_pipeline_versions_pipeline_version_state"),
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'valid', 'invalid')",
            name=op.f("ck_pipeline_versions_pipeline_version_validation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_pipeline_versions_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_versions")),
        sa.UniqueConstraint("version_number", name=op.f("uq_pipeline_versions_version_number")),
    )
    op.create_index(
        "ix_pipeline_versions_created_by_user_id",
        "pipeline_versions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_versions_state_number",
        "pipeline_versions",
        ["state", "version_number"],
        unique=False,
    )

    op.create_table(
        "pipeline_version_stages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pipeline_version_id", sa.Integer(), nullable=False),
        sa.Column("stable_identifier", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("provider_type", sa.String(length=100), nullable=False),
        sa.Column("model_string", sa.String(length=255), nullable=False),
        sa.Column("system_prompt_directives", sa.Text(), server_default="", nullable=False),
        sa.Column("prerequisite_dependencies", sa.JSON(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("thinking_budget", sa.Integer(), nullable=True),
        sa.Column("token_limit", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default="45", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fallback_provider_type", sa.String(length=100), nullable=True),
        sa.Column("fallback_model_string", sa.String(length=255), nullable=True),
        sa.Column("input_policy", sa.JSON(), nullable=False),
        sa.Column("output_policy", sa.JSON(), nullable=False),
        sa.Column("required_capabilities", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "position > 0",
            name=op.f("ck_pipeline_version_stages_pipeline_version_stage_positive_position"),
        ),
        sa.CheckConstraint(
            "timeout_seconds > 0",
            name=op.f("ck_pipeline_version_stages_pipeline_version_stage_positive_timeout"),
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name=op.f("ck_pipeline_version_stages_pipeline_version_stage_nonnegative_retries"),
        ),
        sa.CheckConstraint(
            "token_limit IS NULL OR token_limit > 0",
            name=op.f("ck_pipeline_version_stages_pipeline_version_stage_positive_token_limit"),
        ),
        sa.CheckConstraint(
            "thinking_budget IS NULL OR thinking_budget >= 0",
            name=op.f("ck_pipeline_version_stages_pipeline_version_stage_nonnegative_thinking_budget"),
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id"],
            ["pipeline_versions.id"],
            name=op.f("fk_pipeline_version_stages_pipeline_version_id_pipeline_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_version_stages")),
        sa.UniqueConstraint(
            "pipeline_version_id",
            "stable_identifier",
            name="pipeline_version_stage_identifier",
        ),
        sa.UniqueConstraint(
            "pipeline_version_id",
            "position",
            name="pipeline_version_stage_position",
        ),
    )
    op.create_index(
        "ix_pipeline_version_stages_pipeline_version_id",
        "pipeline_version_stages",
        ["pipeline_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_version_stages_version_position",
        "pipeline_version_stages",
        ["pipeline_version_id", "position"],
        unique=False,
    )

    op.add_column("pipeline_runs", sa.Column("pipeline_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_pipeline_runs_pipeline_version_id_pipeline_versions"),
        "pipeline_runs",
        "pipeline_versions",
        ["pipeline_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_pipeline_runs_pipeline_version_id",
        "pipeline_runs",
        ["pipeline_version_id"],
        unique=False,
    )

    connection = op.get_bind()
    legacy_steps = sa.table(
        "pipeline_steps",
        sa.column("id", sa.Integer()),
        sa.column("sequence_order_position", sa.Integer()),
        sa.column("step_name", sa.String()),
        sa.column("provider_type", sa.String()),
        sa.column("model_string", sa.String()),
        sa.column("system_prompt_directives", sa.Text()),
        sa.column("prerequisite_dependencies", sa.JSON()),
        sa.column("is_terminal", sa.Boolean()),
    )
    version_table = sa.table(
        "pipeline_versions",
        sa.column("id", sa.Integer()),
        sa.column("version_number", sa.Integer()),
        sa.column("state", sa.String()),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("change_description", sa.Text()),
        sa.column("validation_status", sa.String()),
        sa.column("validation_issues", sa.JSON()),
        sa.column("validated_at", sa.DateTime(timezone=True)),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )
    stage_table = sa.table(
        "pipeline_version_stages",
        sa.column("pipeline_version_id", sa.Integer()),
        sa.column("stable_identifier", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("position", sa.Integer()),
        sa.column("provider_type", sa.String()),
        sa.column("model_string", sa.String()),
        sa.column("system_prompt_directives", sa.Text()),
        sa.column("prerequisite_dependencies", sa.JSON()),
        sa.column("is_terminal", sa.Boolean()),
        sa.column("temperature", sa.Float()),
        sa.column("thinking_budget", sa.Integer()),
        sa.column("token_limit", sa.Integer()),
        sa.column("timeout_seconds", sa.Integer()),
        sa.column("retry_count", sa.Integer()),
        sa.column("fallback_provider_type", sa.String()),
        sa.column("fallback_model_string", sa.String()),
        sa.column("input_policy", sa.JSON()),
        sa.column("output_policy", sa.JSON()),
        sa.column("required_capabilities", sa.JSON()),
    )

    rows = list(
        connection.execute(
            sa.select(legacy_steps).order_by(legacy_steps.c.sequence_order_position)
        ).mappings()
    )
    if rows:
        creator_id = connection.scalar(
            sa.text("SELECT id FROM users ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, id LIMIT 1")
        )
        now = sa.func.now()
        result = connection.execute(
            version_table.insert().values(
                version_number=1,
                state="published",
                created_by_user_id=creator_id,
                change_description="Migrated legacy pipeline configuration",
                validation_status="valid",
                validation_issues=[],
                validated_at=now,
                published_at=now,
            )
        )
        version_id = int(result.inserted_primary_key[0])

        identifier_by_name: dict[str, str] = {}
        seen_identifiers: set[str] = set()
        for row in rows:
            legacy_name = str(row["step_name"])
            identifier = _stable_identifier(legacy_name, int(row["id"]))
            if identifier in seen_identifiers:
                identifier = f"{identifier[:90]}-{row['id']}"
            seen_identifiers.add(identifier)
            identifier_by_name[legacy_name] = identifier

        for row in rows:
            legacy_name = str(row["step_name"])
            prerequisites = [
                identifier_by_name.get(str(dependency), str(dependency)[:100])
                for dependency in list(row["prerequisite_dependencies"] or [])
            ]
            connection.execute(
                stage_table.insert().values(
                    pipeline_version_id=version_id,
                    stable_identifier=identifier_by_name[legacy_name],
                    name=legacy_name,
                    description="Migrated from the legacy pipeline definition.",
                    enabled=True,
                    position=int(row["sequence_order_position"]),
                    provider_type=str(row["provider_type"]),
                    model_string=str(row["model_string"]),
                    system_prompt_directives=str(row["system_prompt_directives"] or ""),
                    prerequisite_dependencies=prerequisites,
                    is_terminal=bool(row["is_terminal"]),
                    temperature=None,
                    thinking_budget=None,
                    token_limit=None,
                    timeout_seconds=45,
                    retry_count=0,
                    fallback_provider_type=None,
                    fallback_model_string=None,
                    input_policy={},
                    output_policy={},
                    required_capabilities=["text_generation"],
                )
            )
        connection.execute(
            sa.text("UPDATE pipeline_runs SET pipeline_version_id = :version_id WHERE pipeline_version_id IS NULL"),
            {"version_id": version_id},
        )


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_pipeline_version_id", table_name="pipeline_runs")
    op.drop_constraint(
        op.f("fk_pipeline_runs_pipeline_version_id_pipeline_versions"),
        "pipeline_runs",
        type_="foreignkey",
    )
    op.drop_column("pipeline_runs", "pipeline_version_id")
    op.drop_index("ix_pipeline_version_stages_version_position", table_name="pipeline_version_stages")
    op.drop_index("ix_pipeline_version_stages_pipeline_version_id", table_name="pipeline_version_stages")
    op.drop_table("pipeline_version_stages")
    op.drop_index("ix_pipeline_versions_state_number", table_name="pipeline_versions")
    op.drop_index("ix_pipeline_versions_created_by_user_id", table_name="pipeline_versions")
    op.drop_table("pipeline_versions")
