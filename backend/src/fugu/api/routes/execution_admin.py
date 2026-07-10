"""Administrative run history and sanitised execution inspection API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from fugu.api.dependencies import AdminUser, MasterSession
from fugu.database.models import (
    PipelineRun,
    PipelineStepRun,
    PipelineVersion,
    PipelineVersionStage,
    Thread,
)
from fugu.execution.diagnostics import (
    SafeExecutionError,
    classify_stored_execution_error,
    sanitise_diagnostic_text,
)

execution_admin_router = APIRouter(
    prefix="/api/admin/execution-runs", tags=["execution administration"]
)

RunStatus = Literal["pending", "running", "completed", "failed"]
StageStatus = Literal["pending", "running", "completed", "failed"]


class ExecutionRunSummaryResponse(BaseModel):
    """Compact administrative history row for one pipeline execution."""

    id: int
    thread_id: int
    thread_name: str
    user_id: int
    username: str
    pipeline_version_id: int | None
    pipeline_version_number: int | None
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    latency_ms: int | None
    failed_stage: str | None
    error_category: str | None
    error_message: str | None
    retryable: bool | None


class ExecutionStageDiagnosticResponse(BaseModel):
    """Sanitised stage-level diagnostics available only to administrators."""

    id: int
    step_name: str
    display_name: str
    provider: str | None
    model: str | None
    status: StageStatus
    started_at: datetime
    completed_at: datetime | None
    latency_ms: int | None
    configured_retry_count: int
    sanitised_input: str | None
    sanitised_output: str | None
    token_usage: int | None
    error_category: str | None
    error_message: str | None
    retryable: bool | None


class ExecutionRunDetailResponse(ExecutionRunSummaryResponse):
    """Complete sanitised run and per-stage inspector payload."""

    final_result: str | None
    stages: list[ExecutionStageDiagnosticResponse]


class ExecutionDiagnosticExportResponse(BaseModel):
    """Copy-safe diagnostic document with no raw stack trace or credential data."""

    generated_at: datetime
    run: ExecutionRunDetailResponse


def _base_run_statement() -> Select[tuple[PipelineRun]]:
    return select(PipelineRun).options(
        selectinload(PipelineRun.thread).selectinload(Thread.user),
        selectinload(PipelineRun.pipeline_version).selectinload(PipelineVersion.stages),
        selectinload(PipelineRun.step_runs),
    )


def _latency_ms(started_at: datetime, completed_at: datetime | None) -> int | None:
    if completed_at is None:
        return None
    return max(int((completed_at - started_at).total_seconds() * 1_000), 0)


def _failed_stage(run: PipelineRun) -> str | None:
    return next(
        (step.step_name for step in run.step_runs if step.status == "failed"), None
    )


def _safe_run_error(
    run: PipelineRun, *, failed_stage: str | None
) -> SafeExecutionError | None:
    return classify_stored_execution_error(
        run.error_code,
        run.error_message,
        stage_name=failed_stage,
    )


def _summary_response(run: PipelineRun) -> ExecutionRunSummaryResponse:
    failed_stage = _failed_stage(run)
    safe_error = _safe_run_error(run, failed_stage=failed_stage)
    version = run.pipeline_version
    thread = run.thread
    return ExecutionRunSummaryResponse(
        id=run.id,
        thread_id=thread.id,
        thread_name=thread.name,
        user_id=thread.user.id,
        username=thread.user.username,
        pipeline_version_id=run.pipeline_version_id,
        pipeline_version_number=version.version_number if version is not None else None,
        status=cast(RunStatus, run.status),
        started_at=run.created_at,
        completed_at=run.completed_at,
        latency_ms=_latency_ms(run.created_at, run.completed_at),
        failed_stage=failed_stage,
        error_category=safe_error.category if safe_error is not None else None,
        error_message=safe_error.message if safe_error is not None else None,
        retryable=safe_error.retryable if safe_error is not None else None,
    )


def _stage_order(
    stage: PipelineStepRun, stage_map: dict[str, PipelineVersionStage]
) -> tuple[int, datetime]:
    configured = stage_map.get(stage.step_name)
    return (configured.position if configured is not None else 10_000, stage.created_at)


def _stage_response(
    run: PipelineRun,
    stage_run: PipelineStepRun,
    stage_map: dict[str, PipelineVersionStage],
) -> ExecutionStageDiagnosticResponse:
    configured = stage_map.get(stage_run.step_name)
    safe_error = (
        classify_stored_execution_error(
            run.error_code,
            stage_run.error_message or run.error_message,
            stage_name=stage_run.step_name,
        )
        if stage_run.status == "failed"
        else None
    )
    return ExecutionStageDiagnosticResponse(
        id=stage_run.id,
        step_name=stage_run.step_name,
        display_name=configured.name if configured is not None else stage_run.step_name,
        provider=configured.provider_type if configured is not None else None,
        model=configured.model_string if configured is not None else None,
        status=cast(StageStatus, stage_run.status),
        started_at=stage_run.created_at,
        completed_at=stage_run.completed_at,
        latency_ms=_latency_ms(stage_run.created_at, stage_run.completed_at),
        configured_retry_count=configured.retry_count if configured is not None else 0,
        sanitised_input=None,
        sanitised_output=sanitise_diagnostic_text(stage_run.output_trace),
        token_usage=None,
        error_category=safe_error.category if safe_error is not None else None,
        error_message=safe_error.message if safe_error is not None else None,
        retryable=safe_error.retryable if safe_error is not None else None,
    )


def _detail_response(run: PipelineRun) -> ExecutionRunDetailResponse:
    version = run.pipeline_version
    stage_map = {
        stage.stable_identifier: stage
        for stage in (version.stages if version is not None else [])
    }
    ordered_stage_runs = sorted(
        run.step_runs, key=lambda item: _stage_order(item, stage_map)
    )
    terminal_identifier = next(
        (stage.stable_identifier for stage in stage_map.values() if stage.is_terminal),
        None,
    )
    terminal_run = next(
        (
            stage
            for stage in ordered_stage_runs
            if stage.step_name == terminal_identifier
        ),
        None,
    )
    summary = _summary_response(run)
    return ExecutionRunDetailResponse(
        **summary.model_dump(),
        final_result=sanitise_diagnostic_text(terminal_run.output_trace)
        if terminal_run is not None
        else None,
        stages=[_stage_response(run, stage, stage_map) for stage in ordered_stage_runs],
    )


async def _require_run(session: MasterSession, run_id: int) -> PipelineRun:
    statement = _base_run_statement().where(PipelineRun.id == run_id)
    result = await session.scalars(statement)
    run = result.one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution run not found."
        )
    return run


@execution_admin_router.get("", response_model=list[ExecutionRunSummaryResponse])
async def list_execution_runs(
    _: AdminUser,
    session: MasterSession,
    run_status: RunStatus | None = Query(default=None, alias="status"),
    user_id: int | None = Query(default=None, ge=1),
    provider: str | None = Query(default=None, min_length=1, max_length=100),
    model: str | None = Query(default=None, min_length=1, max_length=255),
    thread_id: int | None = Query(default=None, ge=1),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ExecutionRunSummaryResponse]:
    """List newest runs with server-side operational filters."""
    statement = _base_run_statement()
    if run_status is not None:
        statement = statement.where(PipelineRun.status == run_status)
    if user_id is not None:
        statement = statement.where(PipelineRun.thread.has(Thread.user_id == user_id))
    if thread_id is not None:
        statement = statement.where(PipelineRun.thread_id == thread_id)
    if date_from is not None:
        statement = statement.where(PipelineRun.created_at >= date_from)
    if date_to is not None:
        statement = statement.where(PipelineRun.created_at <= date_to)
    if provider is not None:
        normalized_provider = provider.strip().lower()
        statement = statement.where(
            PipelineRun.pipeline_version.has(
                PipelineVersion.stages.any(
                    PipelineVersionStage.provider_type == normalized_provider
                )
            )
        )
    if model is not None:
        normalized_model = model.strip()
        statement = statement.where(
            PipelineRun.pipeline_version.has(
                PipelineVersion.stages.any(
                    PipelineVersionStage.model_string == normalized_model
                )
            )
        )
    statement = statement.order_by(PipelineRun.created_at.desc()).limit(limit)
    result = await session.scalars(statement)
    return [_summary_response(run) for run in result.unique().all()]


@execution_admin_router.get("/{run_id}", response_model=ExecutionRunDetailResponse)
async def get_execution_run(
    run_id: int,
    _: AdminUser,
    session: MasterSession,
) -> ExecutionRunDetailResponse:
    """Return one run with ordered, sanitised stage diagnostics."""
    return _detail_response(await _require_run(session, run_id))


@execution_admin_router.get(
    "/{run_id}/diagnostics", response_model=ExecutionDiagnosticExportResponse
)
async def export_execution_diagnostics(
    run_id: int,
    _: AdminUser,
    session: MasterSession,
) -> ExecutionDiagnosticExportResponse:
    """Return a copy-safe diagnostic document for support or incident review."""
    return ExecutionDiagnosticExportResponse(
        generated_at=datetime.now(timezone.utc),
        run=_detail_response(await _require_run(session, run_id)),
    )
