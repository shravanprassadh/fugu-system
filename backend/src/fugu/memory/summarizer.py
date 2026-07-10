"""Background thread-memory consolidation service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import ClassVar

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository, ThreadRepository
from fugu.memory.prompting import MEMORY_SYSTEM_DIRECTIVES, build_memory_prompt, clip_previous_memory
from fugu.memory.state import ThreadMemoryDocument, fit_memory_document, parse_memory_document, redact_sensitive_text
from fugu.memory.transcript import TranscriptBatch, build_transcript_batches, select_pending_messages
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.google import GoogleGeminiProvider
from fugu.security.encryption import ProviderCredentialVault

LOGGER = logging.getLogger(__name__)

MEMORY_CREDENTIAL_PROVIDER_NAME = "thread_memory_google_ai_studio"
MEMORY_PROVIDER_LABEL = "google-ai-studio"
MEMORY_MODEL_IDENTIFIER = "gemini-2.5-flash-lite"


class ThreadMemorySummarizer:
    """Maintain rolling AI handoff memory and concise thread titles."""

    _refresh_locks: ClassVar[dict[tuple[int, int], asyncio.Lock]] = {}

    def __init__(
        self,
        *,
        session_registry: DatabaseSessionRegistry,
        credential_vault: ProviderCredentialVault,
        credential_provider_name: str = MEMORY_CREDENTIAL_PROVIDER_NAME,
        provider_label: str = MEMORY_PROVIDER_LABEL,
        model_identifier: str = MEMORY_MODEL_IDENTIFIER,
        provider_factory: Callable[[], ExecutionProvider] = GoogleGeminiProvider,
    ) -> None:
        self._sessions = session_registry
        self._vault = credential_vault
        self._credential_provider_name = credential_provider_name
        self._provider_label = provider_label
        self._model_identifier = model_identifier
        self._provider_factory = provider_factory

    def schedule(self, *, thread_id: int, user_id: int, latest_message_id: int) -> None:
        """Queue an incremental update after an assistant response is persisted."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            LOGGER.debug("Thread memory refresh skipped because no event loop is running.")
            return
        task = loop.create_task(
            self.refresh(
                thread_id=thread_id,
                user_id=user_id,
                latest_message_id=latest_message_id,
                force_rebuild=False,
            )
        )
        task.add_done_callback(self._log_task_failure)

    async def refresh(
        self,
        *,
        thread_id: int,
        user_id: int,
        latest_message_id: int,
        force_rebuild: bool = True,
    ) -> None:
        """Rebuild all memory by default; scheduled updates explicitly stay incremental."""
        loop_key = (id(asyncio.get_running_loop()), thread_id)
        lock = self._refresh_locks.setdefault(loop_key, asyncio.Lock())
        async with lock:
            await self._refresh_locked(
                thread_id=thread_id,
                user_id=user_id,
                latest_message_id=latest_message_id,
                force_rebuild=force_rebuild,
            )

    async def _refresh_locked(
        self,
        *,
        thread_id: int,
        user_id: int,
        latest_message_id: int,
        force_rebuild: bool,
    ) -> None:
        update_mode = "full rebuild" if force_rebuild else "incremental"
        try:
            credential, title, prior_memory, batches = await self._load_refresh_input(
                thread_id=thread_id,
                user_id=user_id,
                latest_message_id=latest_message_id,
                force_rebuild=force_rebuild,
            )
            if credential is None or not batches:
                return
            document = await self._consolidate_batches(
                credential=credential,
                current_thread_title=title,
                previous_summary=prior_memory,
                batches=batches,
                force_rebuild=force_rebuild,
                update_mode=update_mode,
            )
            await self._persist_completed(
                thread_id=thread_id,
                user_id=user_id,
                document=document,
                checkpoint_message_id=batches[-1].last_message_id,
                update_mode=update_mode,
            )
        except Exception as exc:  # pragma: no cover - defensive task boundary
            LOGGER.warning("Thread memory refresh failed for thread %s: %s", thread_id, exc)
            await self._persist_failure(thread_id=thread_id, user_id=user_id, error=exc)

    async def _load_refresh_input(
        self,
        *,
        thread_id: int,
        user_id: int,
        latest_message_id: int,
        force_rebuild: bool,
    ) -> tuple[str | None, str, str, list[TranscriptBatch]]:
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            credential = await self._vault.retrieve(session, provider_name=self._credential_provider_name)
            if credential is None:
                return None, "", "", []
            thread = await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
            memory = await ThreadMemoryRepository.mark_running(
                session,
                thread_id=thread_id,
                user_id=user_id,
                summarizer_provider=self._provider_label,
                summarizer_model=self._model_identifier,
            )
            previous_summary = ""
            if not force_rebuild:
                previous_summary = clip_previous_memory(redact_sensitive_text(memory.summary_md or ""))
            messages = await MessageRepository.list_for_thread(
                session,
                thread_id=thread_id,
                user_id=user_id,
            )
            pending = select_pending_messages(
                messages,
                after_message_id=None if force_rebuild else memory.last_summarized_message_id,
                through_message_id=latest_message_id,
            )
            if not pending:
                memory.status = "completed"
                memory.error_message = None
                await session.flush()
                return credential, thread.name, previous_summary, []
            batches = build_transcript_batches(pending)
            if not batches:
                raise RuntimeError("No non-empty messages were available for memory consolidation.")
            return credential, thread.name, previous_summary, batches

    async def _consolidate_batches(
        self,
        *,
        credential: str,
        current_thread_title: str,
        previous_summary: str,
        batches: list[TranscriptBatch],
        force_rebuild: bool,
        update_mode: str,
    ) -> ThreadMemoryDocument:
        provider = self._provider_factory()
        document: ThreadMemoryDocument | None = None
        rolling_summary = previous_summary
        try:
            for batch_number, batch in enumerate(batches, start=1):
                request = ProviderRequest(
                    prompt_content=build_memory_prompt(
                        previous_summary=rolling_summary,
                        transcript=batch.text,
                        current_thread_title=current_thread_title,
                        batch_number=batch_number,
                        total_batches=len(batches),
                        force_rebuild=force_rebuild,
                    ),
                    system_directives=MEMORY_SYSTEM_DIRECTIVES,
                    credential_token=credential,
                    model_identifier=self._model_identifier,
                )
                fragments = [token async for token in provider.generate_token_stream(request)]
                raw_document = "".join(fragments).strip()
                if not raw_document:
                    raise RuntimeError("The memory summarizer returned an empty document.")
                document = parse_memory_document(raw_document, fallback_title=current_thread_title)
                fit_memory_document(
                    document,
                    checkpoint_message_id=batch.last_message_id,
                    update_mode=update_mode,
                )
                rolling_summary = document.to_markdown(
                    checkpoint_message_id=batch.last_message_id,
                    update_mode=update_mode,
                )
        finally:
            await provider.aclose()
        if document is None:
            raise RuntimeError("The memory summarizer did not process any transcript batches.")
        return document

    async def _persist_completed(
        self,
        *,
        thread_id: int,
        user_id: int,
        document: ThreadMemoryDocument,
        checkpoint_message_id: int,
        update_mode: str,
    ) -> None:
        summary_md = document.to_markdown(
            checkpoint_message_id=checkpoint_message_id,
            update_mode=update_mode,
        )
        async with self._sessions.session(DatabaseTarget.MASTER) as session:
            memory = await ThreadMemoryRepository.mark_completed(
                session,
                thread_id=thread_id,
                user_id=user_id,
                summary_md=summary_md,
                last_summarized_message_id=checkpoint_message_id,
                summarizer_provider=self._provider_label,
                summarizer_model=self._model_identifier,
            )
            memory.key_facts_md = document.key_facts_markdown()
            memory.open_tasks_md = document.open_tasks_markdown()
            thread = await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
            thread.name = document.thread_title
            await session.flush()

    async def _persist_failure(self, *, thread_id: int, user_id: int, error: Exception) -> None:
        try:
            async with self._sessions.session(DatabaseTarget.MASTER) as session:
                await ThreadMemoryRepository.mark_failed(
                    session,
                    thread_id=thread_id,
                    user_id=user_id,
                    error_message=str(error),
                    summarizer_provider=self._provider_label,
                    summarizer_model=self._model_identifier,
                )
        except Exception:
            LOGGER.exception("Could not persist thread memory failure for thread %s.", thread_id)

    @staticmethod
    def _log_task_failure(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            LOGGER.exception("Unhandled thread memory background task failure.")
