"""Asynchronous deterministic DAG execution kernel."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from time import monotonic

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import Message, PipelineRun, PipelineStepRun, PipelineVersion, Thread, ThreadMemory
from fugu.database.repositories import (
    MessageRepository,
    PipelineRepository,
    PipelineVersionRepository,
    ThreadMemoryRepository,
    ThreadRepository,
)
from fugu.execution.diagnostics import classify_execution_error, sanitise_diagnostic_text
from fugu.execution.exceptions import (
    ExecutionRecoveryError,
    PipelineEngineException,
    PipelineRunCancelledError,
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


@dataclass(frozen=True, slots=True)
class _StepAttemptFailure(Exception):
    """Internal failure retaining the final provider attempt's safe execution context."""

    origin: Exception
    partial_output: str
    retry_attempt_count: int


class PipelineExecutionKernel:
    """Validate, persist, execute, cancel, and safely retry pipeline DAGs."""

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
        self._cancellation_requests: set[int] = set()
        self._background_tasks: set[asyncio.Task[None]] = set()

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
            await self._require_owned_thread(session, thread_id=thread_id, user_id=user_id)
            try:
                pipeline_version = await PipelineVersionRepository.require_current_published(session)
            except EntityNotFoundError as exc:
                raise PipelineValidationError(str(exc)) from exc

            ordered_steps, terminal_step_name = self._resolve_version_steps(
                pipeline_version,
                selected_provider_type=selected_provider_type,
                selected_model_identifier=selected_model_identifier,
                selected_temperature=selected_temperature,
                selected_max_output_tokens=selected_max_output_tokens,
                selected_thinking_budget=selected_thinking_budget,
            )
            conversation_context = await self._load_conversation_context(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            await MessageRepository.add(
                session,
                thread_id=thread_id,
                user_id=user_id,
                role="user",
                content=normalized_prompt,
            )
            request_options = self._request_options(
                selected_provider_type=selected_provider_type,
                selected_model_identifier=selected_model_identifier,
                selected_temperature=selected_temperature,
                selected_max_output_tokens=selected_max_output_tokens,
                selected_thinking_budget=selected_thinking_budget,
            )
            return await self._persist_prepared_run(
                session,
                thread_id=thread_id,
                user_id=user_id,
                pipeline_version=pipeline_version,
                initial_prompt=normalized_prompt,
                conversation_context=conversation_context,
                ordered_steps=ordered_steps,
                terminal_step_name=terminal_step_name,
                request_options=request_options,
            )

    async def prepare_retry(
        self,
        *,
        source_run_id: int,
        retry_stage_name: str | None = None,
    ) -> PreparedPipeline:
        """Create an immutable retry run from the source run's recorded version and snapshots."""
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            source = await self._require_retry_source(session, source_run_id)
            if source.pipeline_version is None:
                raise ExecutionRecoveryError("The source run has no recorded pipeline version.")
            if not source.initial_prompt_snapshot:
                raise ExecutionRecoveryError("The source run predates prompt snapshots and cannot be retried safely.")

            options = source.request_options if isinstance(source.request_options, dict) else {}
            ordered_steps, terminal_step_name = self._resolve_version_steps(
                source.pipeline_version,
                selected_provider_type=self._optional_string(options.get("provider_type")),
                selected_model_identifier=self._optional_string(options.get("model_identifier")),
                selected_temperature=self._optional_float(options.get("temperature")),
                selected_max_output_tokens=self._optional_int(options.get("max_output_tokens")),
                selected_thinking_budget=self._optional_int(options.get("thinking_budget")),
            )
            seed_outputs: dict[str, str] = {}
            selected_steps = ordered_steps
            retry_kind = "whole_run"

            if retry_stage_name is not None:
                retry_kind = "stage"
                target = retry_stage_name.strip()
                if source.status != "failed" or source.failed_stage != target:
                    raise ExecutionRecoveryError("Only the failed stage of a failed run can be retried independently.")
                selected_steps, seed_outputs = self._select_safe_stage_retry(
                    ordered_steps=ordered_steps,
                    source=source,
                    target=target,
                    terminal_step_name=terminal_step_name,
                )

            thread = source.thread
            conversation_context = await self._load_conversation_context(
                session,
                thread_id=thread.id,
                user_id=thread.user_id,
            )
            return await self._persist_prepared_run(
                session,
                thread_id=thread.id,
                user_id=thread.user_id,
                pipeline_version=source.pipeline_version,
                initial_prompt=source.initial_prompt_snapshot,
                conversation_context=conversation_context,
                ordered_steps=selected_steps,
                terminal_step_name=terminal_step_name,
                request_options=dict(options),
                seed_outputs=seed_outputs,
                source_run_id=source.id,
                retry_kind=retry_kind,
                retry_stage_name=retry_stage_name,
            )

    def start_background(self, prepared: PreparedPipeline) -> int:
        """Start a prepared administrative retry and retain the task until completion."""
        task = asyncio.create_task(self._consume_background(prepared))
        self._background_tasks.add(task)
        task.add_done_callback(self._discard_background_task)
        return prepared.run_id

    async def request_cancellation(self, run_id: int) -> str:
        """Request cooperative cancellation and persist the intent immediately."""
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            run = await session.get(PipelineRun, run_id)
            if run is None:
                raise EntityNotFoundError(f"Pipeline run {run_id} was not found.")
            if run.status in {"completed", "failed", "cancelled"}:
                return run.status
            now = datetime.now(timezone.utc)
            run.cancellation_requested_at = run.cancellation_requested_at or now
            if run.status == "pending":
                run.status = "cancelled"
                run.cancelled_at = now
                run.completed_at = now
            else:
                run.status = "cancelling"
            self._cancellation_requests.add(run_id)
            return run.status

    async def execute(self, prepared: PreparedPipeline) -> AsyncIterator[PipelineEvent]:
        """Execute the validated plan and emit only terminal-stage token events."""
        outputs: dict[str, str] = dict(prepared.seed_outputs or {})
        yield PipelineEvent(event_type=PipelineEventType.RUN_STARTED, run_id=prepared.run_id)

        try:
            for step in prepared.ordered_steps:
                await self._raise_if_cancelled(prepared.run_id)
                prompt = self._build_step_prompt(prepared=prepared, step=step, outputs=outputs)
                started = monotonic()
                await self._mark_step_running(prepared, step, prompt)
                yield PipelineEvent(
                    event_type=PipelineEventType.STEP_STARTED,
                    run_id=prepared.run_id,
                    step_name=step.name,
                )

                try:
                    output, retry_attempt_count, provider_tokens = await self._execute_step(
                        prepared=prepared,
                        step=step,
                        prompt=prompt,
                    )
                except PipelineRunCancelledError:
                    raise
                except _StepAttemptFailure as exc:
                    await self._persist_failure(
                        prepared=prepared,
                        step=step,
                        partial_output=exc.partial_output,
                        input_prompt=prompt,
                        retry_attempt_count=exc.retry_attempt_count,
                        latency_ms=self._elapsed_ms(started),
                        error=exc.origin,
                    )
                    raise PipelineRunFailureError(
                        "Pipeline execution failed after the failure state was persisted.",
                        run_id=prepared.run_id,
                        step_name=step.name,
                        origin=exc.origin,
                    ) from exc.origin

                outputs[step.name] = output
                await self._mark_step_completed(
                    prepared,
                    step,
                    input_prompt=prompt,
                    output=output,
                    retry_attempt_count=retry_attempt_count,
                    latency_ms=self._elapsed_ms(started),
                )
                if step.is_terminal:
                    for token in provider_tokens:
                        yield PipelineEvent(
                            event_type=PipelineEventType.TOKEN,
                            run_id=prepared.run_id,
                            step_name=step.name,
                            token=token,
                        )
                yield PipelineEvent(
                    event_type=PipelineEventType.STEP_COMPLETED,
                    run_id=prepared.run_id,
                    step_name=step.name,
                )

            terminal_output = outputs[prepared.terminal_step_name]
            await self._complete_run(prepared, terminal_output)
            yield PipelineEvent(
                event_type=PipelineEventType.RUN_COMPLETED,
                run_id=prepared.run_id,
                step_name=prepared.terminal_step_name,
            )
        except PipelineRunCancelledError:
            await self._persist_cancellation(prepared)
            yield PipelineEvent(event_type=PipelineEventType.RUN_CANCELLED, run_id=prepared.run_id)
        finally:
            self._cancellation_requests.discard(prepared.run_id)

    async def _execute_step(
        self,
        *,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        prompt: str,
    ) -> tuple[str, int, tuple[str, ...]]:
        attempts: list[tuple[str, str]] = [
            (step.provider_type, step.model_identifier) for _ in range(step.retry_count + 1)
        ]
        if step.fallback_provider_type and step.fallback_model_identifier:
            attempts.append((step.fallback_provider_type, step.fallback_model_identifier))

        last_error: Exception | None = None
        last_partial_output = ""
        last_attempt_index = 0
        for attempt_index, (provider_type, model_identifier) in enumerate(attempts):
            await self._raise_if_cancelled(prepared.run_id)
            provider = self._providers.resolve(provider_type)
            output_fragments: list[str] = []
            try:
                credential = await self._load_provider_credential(prepared, provider_type)
                request = ProviderRequest(
                    prompt_content=prompt,
                    system_directives=step.system_directives,
                    credential_token=credential,
                    model_identifier=model_identifier,
                    temperature=step.temperature,
                    max_output_tokens=step.max_output_tokens,
                    thinking_budget=step.thinking_budget,
                )
                async for token in provider.generate_token_stream(request):
                    await self._raise_if_cancelled(prepared.run_id)
                    output_fragments.append(token)
                return "".join(output_fragments), attempt_index, tuple(output_fragments)
            except PipelineRunCancelledError:
                raise
            except Exception as exc:
                last_error = exc
                last_partial_output = "".join(output_fragments)
                last_attempt_index = attempt_index
            finally:
                await provider.aclose()
        if last_error is None:
            raise PipelineEngineException(f"No provider attempt was available for stage {step.name!r}.")
        raise _StepAttemptFailure(
            origin=last_error,
            partial_output=last_partial_output,
            retry_attempt_count=last_attempt_index,
        )

    async def _consume_background(self, prepared: PreparedPipeline) -> None:
        try:
            async for _ in self.execute(prepared):
                pass
        except PipelineRunFailureError:
            return

    def _discard_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.discard(task)

    async def _persist_prepared_run(
        self,
        session: AsyncSession,
        *,
        thread_id: int,
        user_id: int,
        pipeline_version: PipelineVersion,
        initial_prompt: str,
        conversation_context: str,
        ordered_steps: tuple[PipelineStepDefinition, ...],
        terminal_step_name: str,
        request_options: dict[str, object],
        seed_outputs: dict[str, str] | None = None,
        source_run_id: int | None = None,
        retry_kind: str | None = None,
        retry_stage_name: str | None = None,
    ) -> PreparedPipeline:
        pipeline_run = await PipelineRepository.create_run(session, thread_id=thread_id, status="running")
        pipeline_run.pipeline_version_id = pipeline_version.id
        pipeline_run.requested_by_user_id = user_id
        pipeline_run.source_run_id = source_run_id
        pipeline_run.retry_kind = retry_kind
        pipeline_run.retry_stage_name = retry_stage_name
        pipeline_run.initial_prompt_snapshot = initial_prompt
        pipeline_run.request_options = request_options
        await session.flush()

        step_run_ids: dict[str, int] = {}
        for step in ordered_steps:
            step_run = await PipelineRepository.add_step_run(
                session,
                run_id=pipeline_run.id,
                step_name=step.name,
                status="pending",
            )
            step_run.provider_type = step.provider_type
            step_run.model_string = step.model_identifier
            step_run.side_effect_free = step.side_effect_free
            step_run_ids[step.name] = step_run.id

        return PreparedPipeline(
            run_id=pipeline_run.id,
            pipeline_version_id=pipeline_version.id,
            pipeline_version_number=pipeline_version.version_number,
            thread_id=thread_id,
            user_id=user_id,
            initial_prompt=initial_prompt,
            conversation_context=conversation_context,
            ordered_steps=ordered_steps,
            step_run_ids=step_run_ids,
            terminal_step_name=terminal_step_name,
            seed_outputs=dict(seed_outputs or {}),
            source_run_id=source_run_id,
            retry_kind=retry_kind,
            retry_stage_name=retry_stage_name,
        )

    async def _require_retry_source(self, session: AsyncSession, run_id: int) -> PipelineRun:
        statement = (
            select(PipelineRun)
            .where(PipelineRun.id == run_id)
            .options(
                selectinload(PipelineRun.thread).selectinload(Thread.user),
                selectinload(PipelineRun.pipeline_version).selectinload(PipelineVersion.stages),
                selectinload(PipelineRun.step_runs),
            )
        )
        result = await session.scalars(statement)
        run = result.one_or_none()
        if run is None:
            raise ExecutionRecoveryError("The source execution run was not found.")
        if run.status in {"pending", "running", "cancelling"}:
            raise ExecutionRecoveryError("An active execution cannot be retried.")
        return run

    def _select_safe_stage_retry(
        self,
        *,
        ordered_steps: tuple[PipelineStepDefinition, ...],
        source: PipelineRun,
        target: str,
        terminal_step_name: str,
    ) -> tuple[tuple[PipelineStepDefinition, ...], dict[str, str]]:
        step_by_name = {step.name: step for step in ordered_steps}
        target_step = step_by_name.get(target)
        if target_step is None:
            raise ExecutionRecoveryError("The failed stage is absent from the recorded pipeline version.")

        selected_names = {target}
        for step in ordered_steps:
            if any(dependency in selected_names for dependency in step.prerequisites):
                selected_names.add(step.name)
        if terminal_step_name not in selected_names:
            raise ExecutionRecoveryError(
                "The failed stage does not lead to the terminal result and cannot be retried alone."
            )

        selected_steps = tuple(step for step in ordered_steps if step.name in selected_names)
        if any(not step.side_effect_free for step in selected_steps):
            raise ExecutionRecoveryError("The failed stage or a downstream stage is marked as side-effecting.")

        completed_outputs = {
            step_run.step_name: step_run.output_trace
            for step_run in source.step_runs
            if step_run.status == "completed" and step_run.output_trace
        }
        seed_outputs = {name: output for name, output in completed_outputs.items() if name not in selected_names}
        for step in selected_steps:
            for prerequisite in step.prerequisites:
                if prerequisite not in selected_names and prerequisite not in seed_outputs:
                    raise ExecutionRecoveryError(
                        f"Completed prerequisite output {prerequisite!r} is unavailable for safe stage retry."
                    )
        return selected_steps, seed_outputs

    def _resolve_version_steps(
        self,
        pipeline_version: PipelineVersion,
        *,
        selected_provider_type: str | None,
        selected_model_identifier: str | None,
        selected_temperature: float | None,
        selected_max_output_tokens: int | None,
        selected_thinking_budget: int | None,
    ) -> tuple[tuple[PipelineStepDefinition, ...], str]:
        if pipeline_version.validation_status != "valid" or pipeline_version.state not in {"published", "superseded"}:
            raise PipelineValidationError("The recorded pipeline version is not a valid immutable version.")
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
        return ordered_steps, resolver.terminal_step_name

    async def _load_conversation_context(
        self,
        session: AsyncSession,
        *,
        thread_id: int,
        user_id: int,
    ) -> str:
        messages = await MessageRepository.list_for_thread(session, thread_id=thread_id, user_id=user_id)
        thread_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=thread_id,
            user_id=user_id,
        )
        return self._format_conversation_context(messages, thread_memory=thread_memory)

    @staticmethod
    def _request_options(
        *,
        selected_provider_type: str | None,
        selected_model_identifier: str | None,
        selected_temperature: float | None,
        selected_max_output_tokens: int | None,
        selected_thinking_budget: int | None,
    ) -> dict[str, object]:
        values: dict[str, object | None] = {
            "provider_type": selected_provider_type,
            "model_identifier": selected_model_identifier,
            "temperature": selected_temperature,
            "max_output_tokens": selected_max_output_tokens,
            "thinking_budget": selected_thinking_budget,
        }
        return {key: value for key, value in values.items() if value is not None}

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
        return "\n".join(reversed(lines)) if lines else ""

    async def _require_owned_thread(
        self,
        session: AsyncSession,
        *,
        thread_id: int,
        user_id: int,
    ) -> None:
        try:
            await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
        except EntityNotFoundError as exc:
            raise ThreadAccessDeniedError(f"User {user_id} is not authorized to access thread {thread_id}.") from exc

    async def _mark_step_running(
        self,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        input_prompt: str,
    ) -> None:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            step_run = await self._require_step_run(session, prepared.run_id, step.name)
            step_run.status = "running"
            step_run.provider_type = step.provider_type
            step_run.model_string = step.model_identifier
            step_run.input_trace = sanitise_diagnostic_text(input_prompt)
            step_run.side_effect_free = step.side_effect_free

    async def _load_provider_credential(self, prepared: PreparedPipeline, provider_type: str) -> str:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(
                session,
                thread_id=prepared.thread_id,
                user_id=prepared.user_id,
            )
            credential = await self._vault.retrieve(session, provider_name=provider_type)
            if credential is None:
                raise ProviderCredentialMissingError(
                    f"No encrypted credential is configured for provider {provider_type!r}."
                )
            return credential

    async def _mark_step_completed(
        self,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        *,
        input_prompt: str,
        output: str,
        retry_attempt_count: int,
        latency_ms: int,
    ) -> None:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            step_run = await self._require_step_run(session, prepared.run_id, step.name)
            step_run.status = "completed"
            step_run.input_trace = sanitise_diagnostic_text(input_prompt)
            step_run.output_trace = sanitise_diagnostic_text(output)
            step_run.retry_attempt_count = retry_attempt_count
            step_run.input_token_usage = self._estimate_tokens(input_prompt)
            step_run.output_token_usage = self._estimate_tokens(output)
            step_run.latency_ms = latency_ms
            step_run.completed_at = datetime.now(timezone.utc)

    async def _complete_run(self, prepared: PreparedPipeline, terminal_output: str) -> None:
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
            run = await self._require_run(session, prepared.run_id)
            run.status = "completed"
            run.final_result_trace = sanitise_diagnostic_text(terminal_output)
            run.completed_at = datetime.now(timezone.utc)

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
        input_prompt: str,
        retry_attempt_count: int,
        latency_ms: int,
        error: Exception,
    ) -> None:
        safe_error = classify_execution_error(error, stage_name=step.name)
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            step_run = await self._require_step_run(session, prepared.run_id, step.name)
            step_run.status = "failed"
            step_run.input_trace = sanitise_diagnostic_text(input_prompt)
            step_run.output_trace = sanitise_diagnostic_text(partial_output)
            step_run.retry_attempt_count = retry_attempt_count
            step_run.error_code = type(error).__name__[:100]
            step_run.error_category = safe_error.category
            step_run.error_message = safe_error.message
            step_run.retryable = safe_error.retryable
            step_run.latency_ms = latency_ms
            step_run.completed_at = datetime.now(timezone.utc)
            run = await self._require_run(session, prepared.run_id)
            run.status = "failed"
            run.failed_stage = step.name
            run.error_code = type(error).__name__[:100]
            run.error_category = safe_error.category
            run.error_message = safe_error.message
            run.retryable = safe_error.retryable
            run.completed_at = datetime.now(timezone.utc)

    async def _persist_cancellation(self, prepared: PreparedPipeline) -> None:
        now = datetime.now(timezone.utc)
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            run = await self._require_run(session, prepared.run_id)
            run.status = "cancelled"
            run.cancelled_at = now
            run.completed_at = now
            run.error_category = "cancelled"
            run.error_message = "The pipeline was cancelled before completion."
            run.retryable = True
            for step_run in run.step_runs:
                if step_run.status in {"pending", "running"}:
                    step_run.status = "cancelled"
                    step_run.completed_at = now

    async def _raise_if_cancelled(self, run_id: int) -> None:
        if run_id in self._cancellation_requests:
            raise PipelineRunCancelledError("Execution cancellation was requested.")
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            run = await session.get(PipelineRun, run_id)
            if run is not None and (
                run.cancellation_requested_at is not None or run.status in {"cancelling", "cancelled"}
            ):
                self._cancellation_requests.add(run_id)
                raise PipelineRunCancelledError("Execution cancellation was requested.")

    @staticmethod
    async def _require_run(session: AsyncSession, run_id: int) -> PipelineRun:
        statement = select(PipelineRun).where(PipelineRun.id == run_id).options(selectinload(PipelineRun.step_runs))
        result = await session.scalars(statement)
        run = result.one_or_none()
        if run is None:
            raise EntityNotFoundError(f"Pipeline run {run_id} was not found.")
        return run

    @staticmethod
    async def _require_step_run(session: AsyncSession, run_id: int, step_name: str) -> PipelineStepRun:
        statement = select(PipelineStepRun).where(
            PipelineStepRun.run_id == run_id,
            PipelineStepRun.step_name == step_name,
        )
        result = await session.scalars(statement)
        step_run = result.one_or_none()
        if step_run is None:
            raise EntityNotFoundError(f"Pipeline step run {run_id}/{step_name} was not found.")
        return step_run

    @staticmethod
    def _build_step_prompt(
        *,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        outputs: dict[str, str],
    ) -> str:
        sections: list[str] = []
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

    @staticmethod
    def _estimate_tokens(value: str) -> int:
        return max((len(value) + 3) // 4, 1) if value else 0

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(int((monotonic() - started) * 1_000), 0)

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None


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
