"""DAG validation, pipeline lifecycle, streaming, and authorization tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fugu.api.dependencies import get_current_user
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base, PipelineStep, User
from fugu.database.repositories import (
    MessageRepository,
    PipelineRepository,
    ThreadRepository,
    UserRepository,
)
from fugu.execution.exceptions import (
    DependencyLoopError,
    PipelineRunFailureError,
    PrerequisiteNotFoundError,
    TerminalStepConfigurationError,
    ThreadAccessDeniedError,
)
from fugu.execution.graph import PipelineDependencyGraphResolver
from fugu.execution.kernel import PipelineExecutionKernel, get_execution_kernel
from fugu.execution.models import PipelineEventType
from fugu.main import create_app
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.exceptions import ProviderTransportError
from fugu.providers.registry import ProviderRegistry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine


@dataclass
class ProviderScript:
    """Deterministic model outputs and failures used by fake providers."""

    tokens_by_model: dict[str, list[str]] = field(default_factory=dict)
    fail_after_stream: set[str] = field(default_factory=set)
    requests: list[ProviderRequest] = field(default_factory=list)


class ScriptedProvider(ExecutionProvider):
    """Provider adapter driven by a shared test script."""

    def __init__(self, script: ProviderScript) -> None:
        self._script = script

    async def generate_token_stream(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[str]:
        self._script.requests.append(request)
        for token in self._script.tokens_by_model.get(request.model_identifier, []):
            yield token
        if request.model_identifier in self._script.fail_after_stream:
            raise ProviderTransportError("simulated provider stream failure")


@dataclass
class ExecutionContext:
    """Isolated resources for kernel and route integration tests."""

    registry: DatabaseSessionRegistry
    kernel: PipelineExecutionKernel
    vault: ProviderCredentialVault
    script: ProviderScript
    user: User
    other_user: User
    thread_id: int


@pytest_asyncio.fixture
async def execution_context() -> AsyncIterator[ExecutionContext]:
    engines: dict[DatabaseTarget, AsyncEngine] = {
        target: create_async_engine("sqlite+aiosqlite:///:memory:")
        for target in DatabaseTarget
    }
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    script = ProviderScript()
    provider_registry = ProviderRegistry()
    provider_registry.register("mock", lambda: ScriptedProvider(script))

    vault = ProviderCredentialVault(
        SymmetricVaultEngine(Fernet.generate_key().decode("ascii"))
    )
    kernel = PipelineExecutionKernel(
        session_registry=registry,
        provider_registry=provider_registry,
        credential_vault=vault,
    )

    async with registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(
            session,
            username="execution-user",
            password_hash="test-hash",
        )
        other_user = await UserRepository.add(
            session,
            username="other-execution-user",
            password_hash="test-hash",
        )
        thread = await ThreadRepository.add(
            session,
            user_id=user.id,
            name="Owned execution thread",
        )
        await vault.store(
            session,
            provider_name="mock",
            plaintext_secret="mock-provider-secret",
        )
        thread_id = thread.id

    yield ExecutionContext(
        registry=registry,
        kernel=kernel,
        vault=vault,
        script=script,
        user=user,
        other_user=other_user,
        thread_id=thread_id,
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


async def _seed_steps(
    context: ExecutionContext,
    steps: list[PipelineStep],
) -> None:
    async with context.registry.session(DatabaseTarget.MASTER) as session:
        session.add_all(steps)
        await session.flush()


def test_graph_resolver_orders_multi_path_dag_deterministically() -> None:
    resolver = PipelineDependencyGraphResolver(
        [
            _step("Terminal", 4, prerequisites=["BranchB", "BranchA"], terminal=True),
            _step("BranchB", 3, prerequisites=["Root"]),
            _step("Root", 1),
            _step("BranchA", 2, prerequisites=["Root"]),
        ]
    )

    assert resolver.resolve_safe_execution_sequence() == [
        "Root",
        "BranchA",
        "BranchB",
        "Terminal",
    ]


def test_graph_resolver_rejects_missing_prerequisite() -> None:
    with pytest.raises(PrerequisiteNotFoundError):
        PipelineDependencyGraphResolver(
            [_step("Terminal", 1, prerequisites=["Missing"], terminal=True)]
        )


def test_graph_resolver_rejects_cycles() -> None:
    with pytest.raises(DependencyLoopError):
        PipelineDependencyGraphResolver(
            [
                _step("NodeA", 1, prerequisites=["NodeB"]),
                _step("NodeB", 2, prerequisites=["NodeA"], terminal=True),
            ]
        ).resolve_safe_execution_sequence()


def test_graph_resolver_requires_one_terminal_sink() -> None:
    with pytest.raises(TerminalStepConfigurationError):
        PipelineDependencyGraphResolver([_step("Root", 1)])

    with pytest.raises(TerminalStepConfigurationError):
        PipelineDependencyGraphResolver(
            [
                _step("TerminalA", 1, terminal=True),
                _step("TerminalB", 2, terminal=True),
            ]
        )


@pytest.mark.asyncio
async def test_kernel_streams_only_terminal_output_and_persists_clean_message(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [
            _step("Root", 1, model="root"),
            _step("BranchA", 2, prerequisites=["Root"], model="branch-a"),
            _step("BranchB", 3, prerequisites=["Root"], model="branch-b"),
            _step(
                "Terminal",
                4,
                prerequisites=["BranchA", "BranchB"],
                terminal=True,
                model="terminal",
            ),
        ],
    )
    execution_context.script.tokens_by_model = {
        "root": ["root-output"],
        "branch-a": ["branch-a-output"],
        "branch-b": ["branch-b-output"],
        "terminal": ["Final", " answer"],
    }

    prepared = await execution_context.kernel.prepare_execution(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        initial_prompt="Original prompt",
    )
    events = [event async for event in execution_context.kernel.execute(prepared)]

    token_events = [
        event for event in events if event.event_type is PipelineEventType.TOKEN
    ]
    assert [event.token for event in token_events] == ["Final", " answer"]
    assert {event.step_name for event in token_events} == {"Terminal"}

    requests_by_model = {
        request.model_identifier: request
        for request in execution_context.script.requests
    }
    assert "root-output" in requests_by_model["branch-a"].prompt_content
    assert "root-output" in requests_by_model["branch-b"].prompt_content
    terminal_prompt = requests_by_model["terminal"].prompt_content
    assert "branch-a-output" in terminal_prompt
    assert "branch-b-output" in terminal_prompt

    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        messages = await MessageRepository.list_for_thread(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
        )
        pipeline_run = await PipelineRepository.require_run(session, prepared.run_id)
        root_trace = await PipelineRepository.require_step_run(
            session,
            run_id=prepared.run_id,
            step_name="Root",
        )
        terminal_trace = await PipelineRepository.require_step_run(
            session,
            run_id=prepared.run_id,
            step_name="Terminal",
        )

    assert [(message.role, message.content) for message in messages] == [
        ("user", "Original prompt"),
        ("assistant", "Final answer"),
    ]
    assert pipeline_run.status == "completed"
    assert root_trace.output_trace == "root-output"
    assert terminal_trace.output_trace == "Final answer"


@pytest.mark.asyncio
async def test_failed_intermediate_stage_preserves_user_message_and_failure_trace(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [
            _step("Failing", 1, model="failing"),
            _step(
                "Terminal",
                2,
                prerequisites=["Failing"],
                terminal=True,
                model="terminal",
            ),
        ],
    )
    execution_context.script.tokens_by_model = {
        "failing": ["partial-output"],
        "terminal": ["never-reached"],
    }
    execution_context.script.fail_after_stream = {"failing"}

    prepared = await execution_context.kernel.prepare_execution(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        initial_prompt="Persist this prompt",
    )

    with pytest.raises(PipelineRunFailureError) as captured:
        _ = [event async for event in execution_context.kernel.execute(prepared)]

    assert isinstance(captured.value.origin, ProviderTransportError)
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        messages = await MessageRepository.list_for_thread(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
        )
        pipeline_run = await PipelineRepository.require_run(session, prepared.run_id)
        failed_trace = await PipelineRepository.require_step_run(
            session,
            run_id=prepared.run_id,
            step_name="Failing",
        )
        pending_trace = await PipelineRepository.require_step_run(
            session,
            run_id=prepared.run_id,
            step_name="Terminal",
        )

    assert [(message.role, message.content) for message in messages] == [
        ("user", "Persist this prompt")
    ]
    assert pipeline_run.status == "failed"
    assert pipeline_run.error_code == "ProviderTransportError"
    assert failed_trace.status == "failed"
    assert failed_trace.output_trace == "partial-output"
    assert pending_trace.status == "pending"


@pytest.mark.asyncio
async def test_kernel_rejects_cross_user_thread_access(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [_step("Terminal", 1, terminal=True)],
    )

    with pytest.raises(ThreadAccessDeniedError):
        await execution_context.kernel.prepare_execution(
            thread_id=execution_context.thread_id,
            user_id=execution_context.other_user.id,
            initial_prompt="Unauthorized prompt",
        )


@pytest.mark.asyncio
async def test_execution_route_maps_cross_user_access_to_http_403(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [_step("Terminal", 1, terminal=True)],
    )
    application: FastAPI = create_app()

    async def override_current_user() -> User:
        return execution_context.other_user

    def override_kernel() -> PipelineExecutionKernel:
        return execution_context.kernel

    application.dependency_overrides[get_current_user] = override_current_user
    application.dependency_overrides[get_execution_kernel] = override_kernel

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/threads/{execution_context.thread_id}/execute",
            json={"prompt": "Unauthorized prompt"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "The authenticated user cannot execute against this thread."
    )
