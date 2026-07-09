"""Create rolling thread memory table.

Revision ID: 0004_thread_memories
Revises: 0003_pipeline_step_run_identity
Create Date: 2026-07-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_thread_memories"
down_revision: str | None = "0003_pipeline_step_run_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "thread_memories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("summary_md", sa.Text(), server_default="", nullable=False),
        sa.Column("key_facts_md", sa.Text(), server_default="", nullable=False),
        sa.Column("open_tasks_md", sa.Text(), server_default="", nullable=False),
        sa.Column("last_summarized_message_id", sa.Integer(), nullable=True),
        sa.Column("summarizer_provider", sa.String(length=100), server_default="google-ai-studio", nullable=False),
        sa.Column("summarizer_model", sa.String(length=255), server_default="gemini-2.5-flash-lite", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="idle", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('idle', 'running', 'completed', 'failed')", name="thread_memory_status"),
        sa.ForeignKeyConstraint(["last_summarized_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index("ix_thread_memories_thread_id", "thread_memories", ["thread_id"])
    op.create_index("ix_thread_memories_thread_updated", "thread_memories", ["thread_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_thread_memories_thread_updated", table_name="thread_memories")
    op.drop_index("ix_thread_memories_thread_id", table_name="thread_memories")
    op.drop_table("thread_memories")
