"""SQLAlchemy models for Fugu's relational data tier."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with deterministic constraint naming for Alembic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    """Authenticated application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    threads: Mapped[list[Thread]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="user_role"),
        CheckConstraint("token_version >= 0", name="user_token_version"),
    )


class Thread(Base):
    """Conversation thread owned by one user."""

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="threads")
    messages: Mapped[list[Message]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memory: Mapped[ThreadMemory | None] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    pipeline_runs: Mapped[list[PipelineRun]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_threads_user_created", "user_id", "created_at"),)


class Message(Base):
    """Immutable user, assistant, or system message."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    thread: Mapped[Thread] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="message_role"),
        Index("ix_messages_thread_created", "thread_id", "created_at"),
    )


class ThreadMemory(Base):
    """Rolling markdown memory for one conversation thread."""

    __tablename__ = "thread_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    key_facts_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    open_tasks_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    last_summarized_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    summarizer_provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="google-ai-studio",
        server_default="google-ai-studio",
    )
    summarizer_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="gemini-2.5-flash-lite",
        server_default="gemini-2.5-flash-lite",
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="idle", server_default="idle")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    thread: Mapped[Thread] = relationship(back_populates="memory")

    __table_args__ = (
        CheckConstraint(
            "status IN ('idle', 'running', 'completed', 'failed')",
            name="thread_memory_status",
        ),
        Index("ix_thread_memories_thread_updated", "thread_id", "updated_at"),
    )


class ProviderCredential(Base):
    """Encrypted provider credential and sanitized validation metadata."""

    __tablename__ = "provider_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (CheckConstraint("key_version > 0", name="provider_key_version"),)


class PipelineStep(Base):
    """Legacy mutable pipeline step retained only for migration compatibility."""

    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence_order_position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model_string: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt_directives: Mapped[str | None] = mapped_column(Text, nullable=True)
    prerequisite_dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("sequence_order_position", name="pipeline_sequence_position"),
        UniqueConstraint("step_name", name="pipeline_step_name"),
        CheckConstraint("sequence_order_position > 0", name="pipeline_positive_position"),
    )


class PipelineVersion(Base):
    """Immutable published pipeline or mutable administrative draft."""

    __tablename__ = "pipeline_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", server_default="draft")
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    change_description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    validation_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default="pending"
    )
    validation_issues: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stages: Mapped[list[PipelineVersionStage]] = relationship(
        back_populates="pipeline_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PipelineVersionStage.position",
    )
    runs: Mapped[list[PipelineRun]] = relationship(back_populates="pipeline_version")

    __table_args__ = (
        CheckConstraint("version_number > 0", name="pipeline_version_positive_number"),
        CheckConstraint(
            "state IN ('draft', 'published', 'superseded')",
            name="pipeline_version_state",
        ),
        CheckConstraint(
            "validation_status IN ('pending', 'valid', 'invalid')",
            name="pipeline_version_validation_status",
        ),
        Index("ix_pipeline_versions_state_number", "state", "version_number"),
    )


class PipelineVersionStage(Base):
    """One ordered stage owned by a specific pipeline version."""

    __tablename__ = "pipeline_version_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_version_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stable_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model_string: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt_directives: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    prerequisite_dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    thinking_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=45, server_default="45")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    fallback_provider_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fallback_model_string: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_policy: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    output_policy: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    required_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    pipeline_version: Mapped[PipelineVersion] = relationship(back_populates="stages")

    __table_args__ = (
        UniqueConstraint(
            "pipeline_version_id",
            "stable_identifier",
            name="pipeline_version_stage_identifier",
        ),
        UniqueConstraint(
            "pipeline_version_id",
            "position",
            name="pipeline_version_stage_position",
        ),
        CheckConstraint("position > 0", name="pipeline_version_stage_positive_position"),
        CheckConstraint("timeout_seconds > 0", name="pipeline_version_stage_positive_timeout"),
        CheckConstraint("retry_count >= 0", name="pipeline_version_stage_nonnegative_retries"),
        CheckConstraint("token_limit IS NULL OR token_limit > 0", name="pipeline_version_stage_positive_token_limit"),
        CheckConstraint(
            "thinking_budget IS NULL OR thinking_budget >= 0",
            name="pipeline_version_stage_nonnegative_thinking_budget",
        ),
        Index("ix_pipeline_version_stages_version_position", "pipeline_version_id", "position"),
    )


class PipelineRun(Base):
    """Execution-level lifecycle record for one original request or retry."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    retry_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retry_stage_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    initial_prompt_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_options: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    attachment_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default="pending")
    failed_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    final_result_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    thread: Mapped[Thread] = relationship(back_populates="pipeline_runs")
    pipeline_version: Mapped[PipelineVersion | None] = relationship(back_populates="runs")
    step_runs: Mapped[list[PipelineStepRun]] = relationship(
        back_populates="pipeline_run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'cancelling', 'cancelled', 'completed', 'failed')",
            name="pipeline_run_status",
        ),
        CheckConstraint(
            "retry_kind IS NULL OR retry_kind IN ('whole_run', 'stage')",
            name="pipeline_run_retry_kind",
        ),
        Index("ix_pipeline_runs_thread_created", "thread_id", "created_at"),
        Index("ix_pipeline_runs_status_created", "status", "created_at"),
    )


class PipelineStepRun(Base):
    """Sanitised lifecycle and diagnostic snapshot for one pipeline stage."""

    __tablename__ = "pipeline_step_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_string: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default="pending")
    input_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    input_token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side_effect_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="step_runs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'cancelled', 'completed', 'failed')",
            name="pipeline_step_run_status",
        ),
        CheckConstraint("retry_attempt_count >= 0", name="pipeline_step_run_nonnegative_retry_attempts"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="pipeline_step_run_nonnegative_latency"),
        UniqueConstraint("run_id", "step_name", name="pipeline_step_run_identity"),
        Index("ix_pipeline_step_runs_run_created", "run_id", "created_at"),
    )
