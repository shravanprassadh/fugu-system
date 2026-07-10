"""Production attachment kernel with retry-safe Reader selection."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from fugu.database.connection import DatabaseTarget, get_session_registry
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import PipelineRun
from fugu.database.repositories import AttachmentRepository
from fugu.execution.attachment_kernel import AttachmentAwarePipelineExecutionKernel
from fugu.execution.exceptions import PipelineValidationError
from fugu.execution.kernel import PipelineExecutionKernel
from fugu.execution.models import PipelineStepDefinition, PreparedPipeline
from fugu.memory import ThreadMemorySummarizer
from fugu.providers.base import ProviderImageInput
from fugu.providers.registry import get_provider_registry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine


class DocumentPipelineExecutionKernel(AttachmentAwarePipelineExecutionKernel):
    """Prevent downstream stage retries from re-reading raw attachment objects."""

    async def prepare_retry(
        self,
        *,
        source_run_id: int,
        retry_stage_name: str | None = None,
    ) -> PreparedPipeline:
        prepared = await PipelineExecutionKernel.prepare_retry(
            self,
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

            reader_step = self._retry_reader_step(prepared) if normalised_snapshot else None
            image_inputs: tuple[ProviderImageInput, ...] = ()
            if reader_step is not None:
                attachment_ids = [str(item["id"]) for item in normalised_snapshot if isinstance(item.get("id"), str)]
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
                if any(
                    recorded_hashes.get(attachment.public_id) != attachment.sha256_hex for attachment in attachments
                ):
                    raise PipelineValidationError(
                        "An attachment changed after the source run and cannot be retried safely."
                    )
                image_inputs = await self._load_image_inputs(attachments=attachments, reader_step=reader_step)
            return replace(
                prepared,
                attachment_snapshot=normalised_snapshot,
                attachment_reader_step_name=reader_step.name if reader_step else None,
                image_inputs=image_inputs,
            )

    def _retry_reader_step(self, prepared: PreparedPipeline) -> PipelineStepDefinition | None:
        if prepared.retry_kind == "whole_run":
            return self._reader_step(prepared.ordered_steps)
        return next(
            (
                step
                for step in prepared.ordered_steps
                if step.name.strip().lower() == "reader" or step.display_name.strip().lower() == "reader"
            ),
            None,
        )


@lru_cache(maxsize=1)
def get_document_execution_kernel() -> DocumentPipelineExecutionKernel:
    """Build the process-wide document-aware execution kernel."""
    session_registry = get_session_registry()
    provider_registry = get_provider_registry()
    credential_vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    return DocumentPipelineExecutionKernel(
        session_registry=session_registry,
        provider_registry=provider_registry,
        credential_vault=credential_vault,
        memory_summarizer=ThreadMemorySummarizer(
            session_registry=session_registry,
            credential_vault=credential_vault,
        ),
    )
