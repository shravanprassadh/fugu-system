"""Execution retry lineage, stage safety, and cooperative cancellation tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base, PipelineStep, PipelineVersion, PipelineVersionStage, User
from fugu.database.repositories import PipelineRepository, ThreadRepository, UserRepository
from fugu.execution.exceptions import ExecutionRecoveryError, PipelineRunFailureError
from fugu.execution.kernel import PipelineExecutionKernel
from fugu.execution.models import PipelineEventType
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.exceptions import ProviderTransportError
from fugu.providers.registry import ProviderRegistry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from tests.database_helpers import create_sqlite_engine_map


@dataclass
class RecoveryProviderScript:
    """Deterministic provider outputs and failures for recovery tests."""

    tokens_by_model: dict[str, list[str]] = field(default_factory=dict)
    fail_after_stream: set[str] = field(default_factory=set)
    requests: list[ProviderRequest] = field(default_factory=list)


class RecoveryProvider(ExecutionProvider):
    """Provider adapter driven by a shared recovery script."""

    def __init__(self, script: RecoveryProviderScript) -> None:
        self._script = script

    async def generate_token_stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        self._script.requests.append(request)
        for token in self._script.tokens_by_model.get(request.model_identifier, []):
            yield token
        if request.model_identifier in self._script.fail_after_stream:
            raise ProviderTransportError("simulated recovery failure")


@dataclass
class RecoveryContext:
    """Isolated kernel and persistence resources."""

    registry: DatabaseSessionRegistry
    kernel: PipelineExecutionKernel
    script: RecoveryProviderScript
    user: User
    thread_id: int


@pytest_asyncio.fixture
async def recovery_context() -> AsyncIterator[RecoveryContext]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    script = RecoveryProviderScript()
    providers = ProviderRegistry()
    providers.register("mock", lambda: RecoveryProvider(script))
    vault = ProviderCredentialVault(SymmetricVaultEngine(Fernet.generate_key().decode("ascii")))
    kernel = PipelineExecutionKernel(
        session_registry=registry,
        provider_registry=providers,
        credential_vault=vault,
    )

    async with registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(
            session,
            username="recovery-user",
            password_hash="test-hash",
        )
        thread = await ThreadRepository.add(
            session,
            user_id=user.id,
            name="Recovery thread",
        )
        await vault.store(
            session,
            provider_name="mock",
            plaintext_secret="mock-provider-secret",
        )

    yield RecoveryContext(
        registry=registry,
        kernel=kernel,
        script=script,
        user=user,
        thread_id=thread.id,
    )
    await registry.dispose_pools()


def _step(
    name: str,
    position: int,
    *,
    prerequisites: list[str] | None = None,
    terminal: bool = False,
    model: str | None = None,
) -> PipelineStep:
    return PipelineStep(
        sequence_order_position=position,
        step_name=name,
        provider_type="mock",
        model_string=model or name.lower(),
        system_prompt_directives=f"Directives for {name}",
        prerequisite_dependencies=prerequisites or [],
        is_terminal=terminal,
    )


async def _seed_steps(context: RecoveryContext, steps: list[PipelineStep]) -> None:
    async with context.registry.session(DatabaseTarget.MASTER) as session:
        session.add_all(steps)
        await session.flush()


async def _prepare_and_fail_at_verifier(context: RecoveryContext) -> int:
    await _seed_steps(
        context,
        [
            _step("Reader", 1, model="reader"),
            _step("Verifier", 2, prerequisites=["Reader"], model="verifier"),
            _step("Terminal", 3, prerequisites=["Verifier"], terminal=True, model="terminal"),
        ],
    )
    context.script.tokens_by_model = {
        "reader": ["reader-output"],
        "verifier": ["partial-verification"],
        "terminal": ["never-reached"],
    }
    context.script.fail_after_stream = {"verifier"}

    prepared = await context.kernel.prepare_execution(
        thread_id=context.thread_id,
        user_id=context.user.id,
        initial_prompt="Recover this request",
    )
    with pytest.raises(PipelineRunFailureError):
        _ = [event async for event in context.kernel.execute(prepared)]
    return prepared.run_id


@pytest.mark.asyncio
async def test_whole_run_retry_uses_exact_recorded_superseded_version(
    recovery_context: RecoveryContext,
) -> None:
    await _seed_steps(recovery_context, [_step("Terminal", 1, terminal=True, model="terminal")])
    recovery_context.script.tokens_by_model = {"terminal": ["original-result"]}

    source = await recovery_context.kernel.prepare_execution(
        thread_id=recovery_context.thread_id,
        user_id=recovery_context.user.id,
        initial_prompt="Original retry prompt",
    )
    _ = [event async for event in recovery_context.kernel.execute(source)]

    async with recovery_context.registry.session(DatabaseTarget.MASTER) as session:
        version = await session.get(PipelineVersion, source.pipeline_version_id)
        assert version is not None
        version.state = "superseded"

    recovery_context.script.requests.clear()
    recovery_context.script.tokens_by_model = {"terminal": ["retried-result"]}
    retry = await recovery_context.kernel.prepare_retry(source_run_id=source.run_id)

    assert retry.pipeline_version_id == source.pipeline_version_id
    assert retry.source_run_id == source.run_id
    assert retry.retry_kind == "whole_run"
    assert retry.initial_prompt == "Original retry prompt"

    _ = [event async for event in recovery_context.kernel.execute(retry)]
    async with recovery_context.registry.session(DatabaseTarget.MASTER) as session:
        retry_run = await PipelineRepository.require_run(session, retry.run_id)

    assert retry_run.status == "completed"
    assert retry_run.source_run_id == source.run_id
    assert retry_run.pipeline_version_id == source.pipeline_version_id
    assert retry_run.final_result_trace == "retried-result"


@pytest.mark.asyncio
async def test_stage_retry_reuses_completed_prerequisite_and_runs_only_downstream_path(
    recovery_context: RecoveryContext,
) -> None:
    source_run_id = await _prepare_and_fail_at_verifier(recovery_context)
    recovery_context.script.requests.clear()
    recovery_context.script.fail_after_stream.clear()
    recovery_context.script.tokens_by_model = {
        "verifier": ["verified-output"],
        "terminal": ["recovered-result"],
    }

    retry = await recovery_context.kernel.prepare_retry(
        source_run_id=source_run_id,
        retry_stage_name="Verifier",
    )

    assert [step.name for step in retry.ordered_steps] == ["Verifier", "Terminal"]
    assert retry.seed_outputs == {"Reader": "reader-output"}
    assert retry.retry_kind == "stage"
    assert retry.retry_stage_name == "Verifier"

    events = [event async for event in recovery_context.kernel.execute(retry)]
    assert [event.token for event in events if event.event_type is PipelineEventType.TOKEN] == ["recovered-result"]
    assert [request.model_identifier for request in recovery_context.script.requests] == ["verifier", "terminal"]
    assert "reader-output" in recovery_context.script.requests[0].prompt_content

    async with recovery_context.registry.session(DatabaseTarget.MASTER) as session:
        retry_run = await PipelineRepository.require_run(session, retry.run_id)
        verifier = await PipelineRepository.require_step_run(
            session,
            run_id=retry.run_id,
            step_name="Verifier",
        )

    assert retry_run.status == "completed"
    assert retry_run.source_run_id == source_run_id
    assert verifier.input_trace is not None
    assert verifier.output_trace == "verified-output"


@pytest.mark.asyncio
async def test_stage_retry_rejects_side_effecting_downstream_path(
    recovery_context: RecoveryContext,
) -> None:
    source_run_id = await _prepare_and_fail_at_verifier(recovery_context)

    async with recovery_context.registry.session(DatabaseTarget.MASTER) as session:
        source_run = await PipelineRepository.require_run(session, source_run_id)
        result = await session.scalars(
            select(PipelineVersionStage).where(
                PipelineVersionStage.pipeline_version_id == source_run.pipeline_version_id,
                PipelineVersionStage.stable_identifier == "Verifier",
            )
        )
        verifier_stage = result.one()
        verifier_stage.input_policy = {"side_effect_free": False}

    with pytest.raises(ExecutionRecoveryError, match="side-effecting"):
        await recovery_context.kernel.prepare_retry(
            source_run_id=source_run_id,
            retry_stage_name="Verifier",
        )


@pytest.mark.asyncio
async def test_cancellation_is_cooperative_idempotent_and_persisted(
    recovery_context: RecoveryContext,
) -> None:
    await _seed_steps(recovery_context, [_step("Terminal", 1, terminal=True, model="terminal")])
    recovery_context.script.tokens_by_model = {"terminal": ["should-not-run"]}
    prepared = await recovery_context.kernel.prepare_execution(
        thread_id=recovery_context.thread_id,
        user_id=recovery_context.user.id,
        initial_prompt="Cancel this request",
    )

    first_status = await recovery_context.kernel.request_cancellation(prepared.run_id)
    second_status = await recovery_context.kernel.request_cancellation(prepared.run_id)
    events = [event async for event in recovery_context.kernel.execute(prepared)]

    assert first_status == "cancelling"
    assert second_status == "cancelling"
    assert [event.event_type for event in events] == [
        PipelineEventType.RUN_STARTED,
        PipelineEventType.RUN_CANCELLED,
    ]
    assert recovery_context.script.requests == []

    async with recovery_context.registry.session(DatabaseTarget.MASTER) as session:
        run = await PipelineRepository.require_run(session, prepared.run_id)
        stage = await PipelineRepository.require_step_run(
            session,
            run_id=prepared.run_id,
            step_name="Terminal",
        )

    assert run.status == "cancelled"
    assert run.cancellation_requested_at is not None
    assert run.cancelled_at is not None
    assert run.completed_at is not None
    assert run.error_category == "cancelled"
    assert stage.status == "cancelled"
