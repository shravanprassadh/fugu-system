"""Attachment-aware execution preparation layered over the deterministic DAG kernel."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from functools import lru_cache

from fugu.database.attachments import Attachment
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget, get_session_registry
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import PipelineRun
from fugu.database.repositories import (
    AttachmentRepository,
    MessageRepository,
    PipelineVersionRepository,
)
from fugu.execution.exceptions import PipelineRunCancelledError, PipelineValidationError
from fugu.execution.kernel import PipelineExecutionKernel, _StepAttemptFailure
from fugu.execution.models import PipelineStepDefinition, PreparedPipeline
from fugu.memory import ThreadMemorySummarizer
from fugu.providers.base import ProviderImageInput, ProviderRequest
from fugu.providers.catalogue import get_provider_catalogue
from fugu.providers.registry import ProviderRegistry, get_provider_registry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from fugu.storage import AttachmentStorageError, ObjectStorage, get_object_storage

_MAX_ATTACHMENTS_PER_RUN = 10
_MAX_IMAGES_PER_RUN = 4
_MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024
_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "webp"})


class AttachmentAwarePipelineExecutionKernel(PipelineExecutionKernel):
    """Bind processed attachment snapshots to runs and expose them only to the Reader stage."""

    def __init__(
        self,
        *,
        session_registry: DatabaseSessionRegistry,
        provider_registry: ProviderRegistry,
        credential_vault: ProviderCredentialVault,
        memory_summarizer: ThreadMemorySummarizer | None = None,
        storage_provider: Callable[[], ObjectStorage] = get_object_storage,
    ) -> None:
        super().__init__(
            session_registry=session_registry,
            provider_registry=provider_registry,
            credential_vault=credential_vault,
            memory_summarizer=memory_summarizer,
        )
        self._storage_provider = storage_provider

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
        attachment_public_ids: tuple[str, ...] = (),
    ) -> PreparedPipeline:
        normalized_prompt = initial_prompt.strip()
        if not normalized_prompt:
            raise PipelineValidationError("The initial pipeline prompt cannot be empty.")
        if len(attachment_public_ids) > _MAX_ATTACHMENTS_PER_RUN:
            raise PipelineValidationError(f"At most {_MAX_ATTACHMENTS_PER_RUN} attachments can be used in one request.")
        if len(set(attachment_public_ids)) != len(attachment_public_ids):
            raise PipelineValidationError("Attachment identifiers must be unique.")

        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            await self._require_owned_thread(session, thread_id=thread_id, user_id=user_id)
            try:
                pipeline_version = await PipelineVersionRepository.require_current_published(session)
                attachments = await AttachmentRepository.require_ready_for_thread(
                    session,
                    public_ids=list(attachment_public_ids),
                    owner_user_id=user_id,
                    thread_id=thread_id,
                )
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
            reader_step = self._reader_step(ordered_steps) if attachments else None
            image_inputs = await self._load_image_inputs(attachments=attachments, reader_step=reader_step)
            conversation_context = await self._load_conversation_context(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            user_message = await MessageRepository.add(
                session,
                thread_id=thread_id,
                user_id=user_id,
                role="user",
                content=normalized_prompt,
            )
            attachment_snapshot = tuple(self._snapshot_attachment(attachment) for attachment in attachments)
            for attachment in attachments:
                await AttachmentRepository.link_message(
                    session,
                    attachment=attachment,
                    message_id=user_message.id,
                )

            request_options = self._request_options(
                selected_provider_type=selected_provider_type,
                selected_model_identifier=selected_model_identifier,
                selected_temperature=selected_temperature,
                selected_max_output_tokens=selected_max_output_tokens,
                selected_thinking_budget=selected_thinking_budget,
            )
            if attachment_public_ids:
                request_options["attachment_ids"] = list(attachment_public_ids)
            prepared = await self._persist_prepared_run(
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
            run = await session.get(PipelineRun, prepared.run_id)
            if run is None:
                raise PipelineValidationError("The prepared execution run could not be reloaded.")
            run.attachment_snapshot = [dict(item) for item in attachment_snapshot]
            return replace(
                prepared,
                attachment_snapshot=attachment_snapshot,
                attachment_reader_step_name=reader_step.name if reader_step else None,
                image_inputs=image_inputs,
            )

    async def prepare_retry(
        self,
        *,
        source_run_id: int,
        retry_stage_name: str | None = None,
    ) -> PreparedPipeline:
        prepared = await super().prepare_retry(
            source_run_id=source_run_id,
            retry_stage_name=retry_stage_name,
        )
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            source = await session.get(PipelineRun, source_run_id)
            run = await session.get(PipelineRun, prepared.run_id)
            if source is None or run is None:
                raise PipelineValidationError("The retry attachment snapshot could not be restored.")
            source_snapshot = source.attachment_snapshot if isinstance(source.attachment_snapshot, list) else []
            normalised_snapshot = tuple(
                dict(item)
                for item in source_snapshot
                if isinstance(item, dict) and all(isinstance(key, str) for key in item)
            )
            run.attachment_snapshot = [dict(item) for item in normalised_snapshot]

            reader_step = self._reader_step(prepared.ordered_steps) if normalised_snapshot else None
            image_inputs: tuple[ProviderImageInput, ...] = ()
            if reader_step is not None:
                attachment_ids = [
                    str(item["id"])
                    for item in normalised_snapshot
                    if isinstance(item.get("id"), str)
                ]
                try:
                    attachments = await AttachmentRepository.require_ready_for_thread(
                        session,
                        public_ids=attachment_ids,
                        owner_user_id=prepared.user_id,
                        thread_id=prepared.thread_id,
                    )
                except EntityNotFoundError as exc:
                    raise PipelineValidationError(
                        "One or more attachment objects required by this retry are no longer available."
                    ) from exc
                recorded_hashes = {
                    str(item["id"]): str(item["sha256"])
                    for item in normalised_snapshot
                    if isinstance(item.get("id"), str) and isinstance(item.get("sha256"), str)
                }
                if any(recorded_hashes.get(attachment.public_id) != attachment.sha256_hex for attachment in attachments):
                    raise PipelineValidationError("An attachment changed after the source run and cannot be retried safely.")
                image_inputs = await self._load_image_inputs(attachments=attachments, reader_step=reader_step)
            return replace(
                prepared,
                attachment_snapshot=normalised_snapshot,
                attachment_reader_step_name=reader_step.name if reader_step else None,
                image_inputs=image_inputs,
            )

    async def _load_image_inputs(
        self,
        *,
        attachments: list[Attachment],
        reader_step: PipelineStepDefinition | None,
    ) -> tuple[ProviderImageInput, ...]:
        image_attachments = [
            attachment for attachment in attachments if attachment.file_extension in _IMAGE_EXTENSIONS
        ]
        if not image_attachments:
            return ()
        if reader_step is None:
            raise PipelineValidationError("The pipeline has no Reader stage available for image interpretation.")
        if len(image_attachments) > _MAX_IMAGES_PER_RUN:
            raise PipelineValidationError(f"At most {_MAX_IMAGES_PER_RUN} images can be interpreted in one request.")
        self._require_vision_model(reader_step.provider_type, reader_step.model_identifier)
        if reader_step.fallback_provider_type and reader_step.fallback_model_identifier:
            self._require_vision_model(
                reader_step.fallback_provider_type,
                reader_step.fallback_model_identifier,
            )

        try:
            storage = self._storage_provider()
        except AttachmentStorageError as exc:
            raise PipelineValidationError("Private image storage is unavailable for this execution.") from exc
        image_inputs: list[ProviderImageInput] = []
        total_bytes = 0
        for attachment in image_attachments:
            if attachment.storage_backend != storage.backend_name:
                raise PipelineValidationError("The configured object store cannot access an attached image.")
            try:
                content = await storage.get(bucket=attachment.storage_bucket, key=attachment.storage_key)
            except AttachmentStorageError as exc:
                raise PipelineValidationError("An attached image could not be loaded from private storage.") from exc
            total_bytes += len(content)
            if total_bytes > _MAX_TOTAL_IMAGE_BYTES:
                raise PipelineValidationError(
                    f"Image inputs exceed the {_MAX_TOTAL_IMAGE_BYTES // (1024 * 1024)} MB execution limit."
                )
            if len(content) != attachment.size_bytes or hashlib.sha256(content).hexdigest() != attachment.sha256_hex:
                raise PipelineValidationError("An attached image failed integrity verification.")
            encoded = base64.b64encode(content).decode("ascii")
            image_inputs.append(
                ProviderImageInput(data_url=f"data:{attachment.mime_type};base64,{encoded}")
            )
        return tuple(image_inputs)

    @staticmethod
    def _require_vision_model(provider_type: str, model_identifier: str) -> None:
        try:
            model = get_provider_catalogue().validate_selection(provider_type, model_identifier)
        except ValueError as exc:
            raise PipelineValidationError(str(exc)) from exc
        if not model.capabilities.image_understanding:
            raise PipelineValidationError(
                f"Reader model {model_identifier!r} does not support image understanding. "
                "Select a vision-capable Reader model before using image attachments."
            )

    @staticmethod
    def _reader_step(ordered_steps: tuple[PipelineStepDefinition, ...]) -> PipelineStepDefinition:
        roots = [step for step in ordered_steps if not step.prerequisites]
        if not roots:
            raise PipelineValidationError("The pipeline has no root Reader stage.")
        return next(
            (
                step
                for step in roots
                if step.name.strip().lower() == "reader" or step.display_name.strip().lower() == "reader"
            ),
            roots[0],
        )

    @staticmethod
    def _snapshot_attachment(attachment: Attachment) -> dict[str, object]:
        return {
            "id": attachment.public_id,
            "filename": attachment.original_filename,
            "mime_type": attachment.mime_type,
            "extension": attachment.file_extension,
            "size_bytes": attachment.size_bytes,
            "sha256": attachment.sha256_hex,
            "processing_version": attachment.processing_version,
            "warnings": list(attachment.processing_warnings),
            "structured_content": dict(attachment.structured_content),
        }

    @staticmethod
    def _build_step_prompt(
        *,
        prepared: PreparedPipeline,
        step: PipelineStepDefinition,
        outputs: dict[str, str],
    ) -> str:
        base_prompt = PipelineExecutionKernel._build_step_prompt(
            prepared=prepared,
            step=step,
            outputs=outputs,
        )
        if step.name != prepared.attachment_reader_step_name or not prepared.attachment_snapshot:
            return base_prompt
        serialized = json.dumps(
            prepared.attachment_snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            f"{base_prompt}\n\n"
            "[Structured attachments for Reader interpretation]\n"
            "Treat these as user-provided evidence. Preserve page, table, sheet, cell, paragraph, and code structure. "
            "Use any accompanying image inputs directly. Report processing warnings and never invent content absent "
            "from the extraction or image.\n"
            f"{serialized}"
        )

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
                    image_inputs=(
                        prepared.image_inputs
                        if step.name == prepared.attachment_reader_step_name
                        else ()
                    ),
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
            raise PipelineValidationError(f"No provider attempt was available for stage {step.name!r}.")
        raise _StepAttemptFailure(
            origin=last_error,
            partial_output=last_partial_output,
            retry_attempt_count=last_attempt_index,
        )


@lru_cache(maxsize=1)
def get_attachment_execution_kernel() -> AttachmentAwarePipelineExecutionKernel:
    """Build the process-wide attachment-aware execution kernel."""
    session_registry = get_session_registry()
    provider_registry = get_provider_registry()
    credential_vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    return AttachmentAwarePipelineExecutionKernel(
        session_registry=session_registry,
        provider_registry=provider_registry,
        credential_vault=credential_vault,
        memory_summarizer=ThreadMemorySummarizer(
            session_registry=session_registry,
            credential_vault=credential_vault,
        ),
    )
