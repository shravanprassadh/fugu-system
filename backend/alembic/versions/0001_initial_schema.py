"""Create the initial Fugu relational schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), server_default=sa.text("'user'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_user_role"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("key_version > 0", name="ck_provider_credentials_provider_key_version"),
        sa.PrimaryKeyConstraint("id", name="pk_provider_credentials"),
        sa.UniqueConstraint("provider_name", name="uq_provider_credentials_provider_name"),
    )

    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sequence_order_position", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=100), nullable=False),
        sa.Column("model_string", sa.String(length=255), nullable=False),
        sa.Column("system_prompt_directives", sa.Text(), nullable=True),
        sa.Column("prerequisite_dependencies", sa.JSON(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "sequence_order_position > 0",
            name="ck_pipeline_steps_pipeline_positive_position",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_steps"),
        sa.UniqueConstraint(
            "sequence_order_position",
            name="pipeline_sequence_position",
        ),
        sa.UniqueConstraint("step_name", name="pipeline_step_name"),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_threads_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_threads"),
    )
    op.create_index("ix_threads_user_id", "threads", ["user_id"], unique=False)
    op.create_index(
        "ix_threads_user_created",
        "threads",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_message_role",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["threads.id"],
            name="fk_messages_thread_id_threads",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_thread_id", "messages", ["thread_id"], unique=False)
    op.create_index(
        "ix_messages_thread_created",
        "messages",
        ["thread_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_pipeline_runs_pipeline_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["threads.id"],
            name="fk_pipeline_runs_thread_id_threads",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_runs"),
    )
    op.create_index("ix_pipeline_runs_thread_id", "pipeline_runs", ["thread_id"], unique=False)
    op.create_index(
        "ix_pipeline_runs_thread_created",
        "pipeline_runs",
        ["thread_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "pipeline_step_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("output_trace", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_pipeline_step_runs_pipeline_step_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_runs.id"],
            name="fk_pipeline_step_runs_run_id_pipeline_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_step_runs"),
    )
    op.create_index(
        "ix_pipeline_step_runs_run_id",
        "pipeline_step_runs",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_step_runs_run_created",
        "pipeline_step_runs",
        ["run_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_step_runs_run_created", table_name="pipeline_step_runs")
    op.drop_index("ix_pipeline_step_runs_run_id", table_name="pipeline_step_runs")
    op.drop_table("pipeline_step_runs")

    op.drop_index("ix_pipeline_runs_thread_created", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_thread_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("ix_messages_thread_created", table_name="messages")
    op.drop_index("ix_messages_thread_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_threads_user_created", table_name="threads")
    op.drop_index("ix_threads_user_id", table_name="threads")
    op.drop_table("threads")

    op.drop_table("pipeline_steps")
    op.drop_table("provider_credentials")
    op.drop_table("users")
