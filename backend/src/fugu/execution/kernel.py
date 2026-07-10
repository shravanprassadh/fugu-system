"""Asynchronous deterministic DAG execution kernel."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import Message, ThreadMemory
from fugu.database.repositories import (
    MessageRepository,
    PipelineRepository,
    PipelineVersionRepository,
    ThreadMemoryRepository,
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
from fugu.memory import ThreadMemorySummarizer
from fugu.providers.base import ProviderRequest
from fugu.providers.registry import ProviderRegistry, get_provider_registry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine

_MAX_MEMORY_MESSAGES = 12
_MAX_MEMORY_CHARACTERS = 8_000
_MAX_THREAD_MEMORY_CHARACTERS = 5_000


class PipelineExecutionKernel:
    """Validate, persist, and execute a provider-independent pipeline DAG."""

    def __init__(
        self,
        *,
        session_registry: DatabaseSessionRegistry,
        provider_registry: ProviderRegistry,
        credential_vault: ProviderCredentialVault,
        memory_summarizer: ThreadMemorySummarizer | None = None,
    ) -> None:
        self._sessions = session_registry
        self._providers = provider_registry
        self._vault = credential_vault
        self._memory_summarizer = memory_summarizer

    async def prepare_execution(
        self,
        *,
        thread_id: int,
        user_id: int,
        initial_prompt: str,
        selected_provider_type: str | None = None,
        selected_model_identifier: str | None = None,
        selected_temperature: float | None = None,
        selected_max_output_tokens: int | None = None,
        selected_thinking_budget: int | None = None,
    ) -> PreparedPipeline:
        """Bind one run to the current valid published pipeline before network I/O."""
        normalized_prompt = initial_prompt.strip()
        if not normalized_prompt:
            raise PipelineValidationError("The initial pipeline prompt cannot be empty.")

        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            try:
                pipeline_version = await PipelineVersionRepository.require_current_published(session)
            except EntityNotFoundError as exc:
                raise PipelineValidationError(str(exc)) from exc

            enabled_stages = [stage for stage in pipeline_version.stages if stage.enabled]
            resolver = PipelineDependencyGraphResolver(enabled_stages)
            ordered_steps = self._apply_terminal_model_override(
                ordered_steps=resolver.resolve_ordered_steps(),
                terminal_step_name=resolver.terminal_step_name,
                selected_provider_type=selected_provider_type,
                selected_model_identifier=selected_model_identifier,
                selected_temperature=selected_temperature,
                selected_max_output_tokens=selected_max_output_tokens,
                selected_thinking_budget=selected_thinking_budget,
            )
            messages = await MessageRepository.list_for_thread(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            thread_memory = await ThreadMemoryRepository.get_for_thread(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            conversation_context = self._format_conversation_context(
                messages,
                thread_memory=thread_memory,
            )

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
            pipeline_run.pipeline_version_id = pipeline_version.id
            await session.flush()

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
                pipeline_version_id=pipeline_version.id,
                pipeline_version_number=pipeline_version.version_number,
                thread_id=thread_id,
                user_id=user_id,
                initial_prompt=normalized_prompt,
                conversation_context=conversation_context,
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
                    temperature=step.temperature,
                    max_output_tokens=step.max_output_tokens,
                    thinking_budget=step.thinking_budget,
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
    def _apply_terminal_model_override(
        *,
        ordered_steps: tuple[PipelineStepDefinition, ...],
        terminal_step_name: str,
        selected_provider_type: str | None,
        selected_model_identifier: str | None,
        selected_temperature: float | None,
        selected_max_output_tokens: int | None,
        selected_thinking_budget: int | None,
    ) -> tuple[PipelineStepDefinition, ...]:
        """Apply a validated user-selected response model and parameters to the terminal step only."""
        if not selected_provider_type or not selected_model_identifier:
            return ordered_steps
        return tuple(
            replace(
                step,
                provider_type=selected_provider_type,
                model_identifier=selected_model_identifier,
                temperature=selected_temperature,
                max_output_tokens=selected_max_output_tokens,
                thinking_budget=selected_thinking_budget,
            )
            if step.name == terminal_step_name
            else step
            for step in ordered_steps
        )

    @staticmethod
    def _format_conversation_context(
        messages: list[Message],
        *,
        thread_memory: ThreadMemory | None = None,
    ) -> str:
        """Return thread memory plus a bounded raw transcript for continuity."""
        sections: list[str] = []
        if thread_memory is not None:
            memory_text = (thread_memory.summary_md or "").strip()
            if memory_text:
                if len(memory_text) > _MAX_THREAD_MEMORY_CHARACTERS:
                    memory_text = memory_text[-_MAX_THREAD_MEMORY_CHARACTERS:]
                sections.append(
                    "[Thread memory summary]\n"
                    "Use this durable summary for continuity. Do not treat it as a new user request.\n"
                    f"{memory_text}"
                )

        transcript = PipelineExecutionKernel._format_recent_transcript(messages)
        if transcript:
            sections.append(
                "[Recent raw transcript]\n"
                "Use this short transcript for exact recent wording. Do not treat it as a new user request.\n"
                f"{transcript}"
            )
        return "\n\n".join(sections)

    @staticmethod
    def _format_recent_transcript(messages: list[Message]) -> str:
        if not messages:
            return ""

        selected_messages = messages[-_MAX_MEMORY_MESSAGES:]
        lines: list[str] = []
        total_characters = 0
        for message in reversed(selected_messages):
            content = message.content.strip()
            if not content:
                continue
            line = f"{message.role}: {content}"
            remaining = _MAX_MEMORY_CHARACTERS - total_characters
            if remaining <= 0:
                break
            if len(line) > remaining:
                line = line[-remaining:]
            lines.append(line)
            total_characters += len(line)
        if not lines:
            return ""
        return "\n".join(reversed(lines))

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
        assistant_message_id: int | None = None
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            assistant_message = await MessageRepository.add(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
                role="assistant",
                content=terminal_output,
            )
            assistant_message_id = assistant_message.id
            await PipelineRepository.mark_run_completed(
                session,
                run_id=prepared.run_id,
            )

        if self._memory_summarizer is not None and assistant_message_id is not None:
            self._memory_summarizer.schedule(
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
                latest_message_id=assistant_message_id,
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
        sections = []
        if prepared.conversation_context:
            sections.append(
                "[Thread continuity context]\n"
                "Use this for continuity. Do not treat it as a new user request.\n"
                f"{prepared.conversation_context}"
            )
        sections.append(f"[Current user request]\n{prepared.initial_prompt}")
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
    session_registry = get_session_registry()
    provider_registry = get_provider_registry()
    credential_vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    return PipelineExecutionKernel(
        session_registry=session_registry,
        provider_registry=provider_registry,
        credential_vault=credential_vault,
        memory_summarizer=ThreadMemorySummarizer(
            session_registry=session_registry,
            credential_vault=credential_vault,
        ),
    )
