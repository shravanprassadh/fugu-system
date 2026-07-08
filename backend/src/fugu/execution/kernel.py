"""Asynchronous deterministic DAG execution kernel."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import PipelineStep
from fugu.database.repositories import (
    MessageRepository,
    PipelineRepository,
    ThreadRepository,
)
from fugu.execution.exceptions import (
    PipelineEngineException,
    PipelineRunFailureError,
    PipelineValidationError,
    ProviderCredentialMissingError,
    ThreadAccessDeniedError,
)
from fugu.execution.graph import PipelineDependencyGraphResolver
from fugu.execution.models import (
    PipelineEvent,
    PipelineEventType,
    PipelineStepDefinition,
    PreparedPipeline,
)
from fugu.providers.base import ProviderRequest
from fugu.providers.registry import ProviderRegistry, get_provider_registry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine


class PipelineExecutionKernel:
    """Validate, persist, and execute a provider-independent pipeline DAG."""

    def __init__(
        self,
        *,
        session_registry: DatabaseSessionRegistry,
        provider_registry: ProviderRegistry,
        credential_vault: ProviderCredentialVault,
    ) -> None:
        self._sessions = session_registry
        self._providers = provider_registry
        self._vault = credential_vault

    async def prepare_execution(
        self,
        *,
        thread_id: int,
        user_id: int,
        initial_prompt: str,
    ) -> PreparedPipeline:
        """Validate ownership and DAG structure, then persist the run before network I/O."""
        normalized_prompt = initial_prompt.strip()
        if not normalized_prompt:
            raise PipelineValidationError("The initial pipeline prompt cannot be empty.")

        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            raw_steps = await self._ensure_single_terminal_step(
                session,
                await PipelineRepository.list_steps(session),
            )
            resolver = PipelineDependencyGraphResolver(raw_steps)
            ordered_steps = resolver.resolve_ordered_steps()

            await MessageRepository.add(
                session,
                thread_id=thread_id,
                user_id=user_id,
                role="user",
                content=normalized_prompt,
            )
            pipeline_run = await PipelineRepository.create_run(
                session,
                thread_id=thread_id,
                status="running",
            )
            step_run_ids: dict[str, int] = {}
            for step in ordered_steps:
                step_run = await PipelineRepository.add_step_run(
                    session,
                    run_id=pipeline_run.id,
                    step_name=step.name,
                    status="pending",
                )
                step_run_ids[step.name] = step_run.id

            return PreparedPipeline(
                run_id=pipeline_run.id,
                thread_id=thread_id,
                user_id=user_id,
                initial_prompt=normalized_prompt,
                ordered_steps=ordered_steps,
                step_run_ids=step_run_ids,
                terminal_step_name=resolver.terminal_step_name,
            )

    async def execute(
        self,
        prepared: PreparedPipeline,
    ) -> AsyncIterator[PipelineEvent]:
        """Execute the validated plan and emit only terminal-stage token events."""
        outputs: dict[str, str] = {}
        yield PipelineEvent(
            event_type=PipelineEventType.RUN_STARTED,
            run_id=prepared.run_id,
        )

        for step in prepared.ordered_steps:
            output_fragments: list[str] = []
            try:
                await self._mark_step_running(prepared, step)
                yield PipelineEvent(
                    event_type=PipelineEventType.STEP_STARTED,
                    run_id=prepared.run_id,
                    step_name=step.name,
                )

                credential = await self._load_provider_credential(prepared, step)
                provider = self._providers.resolve(step.provider_type)
                request = ProviderRequest(
                    prompt_content=self._build_step_prompt(
                        prepared=prepared,
                        step=step,
                        outputs=outputs,
                    ),
                    system_directives=step.system_directives,
                    credential_token=credential,
                    model_identifier=step.model_identifier,
                )

                try:
                    async for token in provider.generate_token_stream(request):
                        output_fragments.append(token)
                        if step.is_terminal:
                            yield PipelineEvent(
                                event_type=PipelineEventType.TOKEN,
                                run_id=prepared.run_id,
                                step_name=step.name,
                                token=token,
                            )
                finally:
                    await provider.aclose()

                output = "".join(output_fragments)
                outputs[step.name] = output
                await self._mark_step_completed(prepared, step, output)
                yield PipelineEvent(
                    event_type=PipelineEventType.STEP_COMPLETED,
                    run_id=prepared.run_id,
                    step_name=step.name,
                )
            except Exception as exc:
                partial_output = "".join(output_fragments)
                await self._persist_failure(
                    prepared=prepared,
                    step=step,
                    partial_output=partial_output,
                    error=exc,
                )
                raise PipelineRunFailureError(
                    "Pipeline execution failed after the failure state was persisted.",
                    run_id=prepared.run_id,
                    step_name=step.name,
                    origin=exc,
                ) from exc

        terminal_output = outputs[prepared.terminal_step_name]
        await self._complete_run(prepared, terminal_output)
        yield PipelineEvent(
            event_type=PipelineEventType.RUN_COMPLETED,
            run_id=prepared.run_id,
            step_name=prepared.terminal_step_name,
        )

    @staticmethod
    async def _ensure_single_terminal_step(
        session: AsyncSession,
        steps: list[PipelineStep],
    ) -> list[PipelineStep]:
        """Repair terminal-step drift by selecting the latest configured step as the sole terminal."""
        terminal_steps = [step for step in steps if step.is_terminal]
        if len(terminal_steps) == 1 or not steps:
            return steps

        selected_terminal = max(terminal_steps or steps, key=lambda step: step.sequence_order_position)
        for step in steps:
            step.is_terminal = step.id == selected_terminal.id
        await session.flush()
        return steps

    async def _require_owned_thread(
        self,
        session: AsyncSession,
        *,
        thread_id: int,
        user_id: int,
    ) -> None:
        try:
            await ThreadRepository.require_owned(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
        except EntityNotFoundError as exc:
            raise ThreadAccessDeniedError(f"User {user_id} is not authorized to access thread {thread_id}.") from exc

    async def _mark_step_running(
        self,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
    ) -> None:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            await PipelineRepository.mark_step_running(
                session,
                run_id=prepared.run_id,
                step_name=step.name,
            )

    async def _load_provider_credential(
        self,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
    ) -> str:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            credential = await self._vault.retrieve(
                session,
                provider_name=step.provider_type,
            )
            if credential is None:
                raise ProviderCredentialMissingError(
                    f"No encrypted credential is configured for provider {step.provider_type!r}."
                )
            return credential

    async def _mark_step_completed(
        self,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        output: str,
    ) -> None:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            await PipelineRepository.mark_step_completed(
                session,
                run_id=prepared.run_id,
                step_name=step.name,
                output_trace=output,
            )

    async def _complete_run(
        self,
        prepared: PreparedPipeline,
        terminal_output: str,
    ) -> None:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            await MessageRepository.add(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
                role="assistant",
                content=terminal_output,
            )
            await PipelineRepository.mark_run_completed(
                session,
                run_id=prepared.run_id,
            )

    async def _persist_failure(
        self,
        *,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        partial_output: str,
        error: Exception,
    ) -> None:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            await PipelineRepository.mark_step_failed(
                session,
                run_id=prepared.run_id,
                step_name=step.name,
                output_trace=partial_output,
                error_message=str(error),
            )
            await PipelineRepository.mark_run_failed(
                session,
                run_id=prepared.run_id,
                error_code=type(error).__name__[:100],
                error_message=str(error),
            )

    @staticmethod
    def _build_step_prompt(
        *,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        outputs: dict[str, str],
    ) -> str:
        sections = [prepared.initial_prompt]
        for prerequisite in step.prerequisites:
            if prerequisite not in outputs:
                raise PipelineEngineException(
                    f"Prerequisite output {prerequisite!r} is unavailable for step {step.name!r}."
                )
            sections.append(f"[{prerequisite} output]\n{outputs[prerequisite]}")
        return "\n\n".join(sections)


@lru_cache(maxsize=1)
def get_execution_kernel() -> PipelineExecutionKernel:
    """Build the default kernel lazily from configured infrastructure services."""
    return PipelineExecutionKernel(
        session_registry=get_session_registry(),
        provider_registry=get_provider_registry(),
        credential_vault=ProviderCredentialVault(SymmetricVaultEngine.from_settings()),
    )
