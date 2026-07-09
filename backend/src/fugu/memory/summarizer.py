"""Background thread-memory summarisation service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Message
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository
from fugu.providers.base import ProviderRequest
from fugu.providers.google import GoogleGeminiProvider
from fugu.security.encryption import ProviderCredentialVault

LOGGER = logging.getLogger(__name__)

MEMORY_CREDENTIAL_PROVIDER_NAME = "thread_memory_google_ai_studio"
MEMORY_PROVIDER_LABEL = "google-ai-studio"
MEMORY_MODEL_IDENTIFIER = "gemini-2.5-flash-lite"
MAX_DELTA_MESSAGES = 30
MAX_TRANSCRIPT_CHARACTERS = 16_000
MAX_PREVIOUS_MEMORY_CHARACTERS = 8_000

MEMORY_SYSTEM_DIRECTIVES = (
    "You are Fugu's thread-memory maintainer.\n"
    "Your only task is to update a concise markdown memory document for one chat thread.\n"
    "Return markdown only. Do not add commentary outside the document.\n"
    "Never store API keys, passwords, full secrets, private tokens, or sensitive credentials.\n"
    "Do preserve durable project state, decisions, files touched, user preferences, constraints, "
    "unresolved tasks, and exact technical identifiers when useful.\n"
    "Remove stale details that no longer affect future work.\n"
    "Use these headings exactly:\n"
    "# Thread Memory\n"
    "## Current goal\n"
    "## Stable facts\n"
    "## Decisions made\n"
    "## Files / modules touched\n"
    "## Current implementation state\n"
    "## Open tasks\n"
    "## Last summarized range\n"
)


class ThreadMemorySummarizer:
    """Maintain rolling markdown summaries for completed conversation turns."""

    def __init__(
        self,
        *,
        session_registry: DatabaseSessionRegistry,
        credential_vault: ProviderCredentialVault,
        credential_provider_name: str = MEMORY_CREDENTIAL_PROVIDER_NAME,
        provider_label: str = MEMORY_PROVIDER_LABEL,
        model_identifier: str = MEMORY_MODEL_IDENTIFIER,
    ) -> None:
        self._sessions = session_registry
        self._vault = credential_vault
        self._credential_provider_name = credential_provider_name
        self._provider_label = provider_label
        self._model_identifier = model_identifier

    def schedule(
        self,
        *,
        thread_id: int,
        user_id: int,
        latest_message_id: int,
    ) -> None:
        """Fire-and-forget a memory refresh after the assistant response is persisted."""
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
            )
        )
        task.add_done_callback(self._log_task_failure)

    async def refresh(
        self,
        *,
        thread_id: int,
        user_id: int,
        latest_message_id: int,
    ) -> None:
        """Update the stored markdown memory using the configured Google AI Studio key."""
        previous_summary = ""
        transcript = ""
        credential: str | None = None
        try:
            async with self._sessions.session(DatabaseTarget.MASTER) as session:
                credential = await self._vault.retrieve(session, provider_name=self._credential_provider_name)
                if credential is None:
                    return
                memory = await ThreadMemoryRepository.mark_running(
                    session,
                    thread_id=thread_id,
                    user_id=user_id,
                    summarizer_provider=self._provider_label,
                    summarizer_model=self._model_identifier,
                )
                previous_summary = self._trim(memory.summary_md or "", MAX_PREVIOUS_MEMORY_CHARACTERS)
                messages = await MessageRepository.list_for_thread(
                    session,
                    thread_id=thread_id,
                    user_id=user_id,
                )
                delta_messages = self._select_delta_messages(
                    messages,
                    after_message_id=memory.last_summarized_message_id,
                )
                if not delta_messages:
                    await ThreadMemoryRepository.mark_completed(
                        session,
                        thread_id=thread_id,
                        user_id=user_id,
                        summary_md=memory.summary_md,
                        last_summarized_message_id=latest_message_id,
                        summarizer_provider=self._provider_label,
                        summarizer_model=self._model_identifier,
                    )
                    return
                transcript = self._format_transcript(delta_messages)

            provider = GoogleGeminiProvider()
            try:
                request = ProviderRequest(
                    prompt_content=self._build_prompt(previous_summary=previous_summary, transcript=transcript),
                    system_directives=MEMORY_SYSTEM_DIRECTIVES,
                    credential_token=credential,
                    model_identifier=self._model_identifier,
                )
                fragments: list[str] = []
                async for token in provider.generate_token_stream(request):
                    fragments.append(token)
                updated_summary = "".join(fragments).strip()
            finally:
                await provider.aclose()

            if not updated_summary:
                raise RuntimeError("The memory summarizer returned an empty summary.")

            async with self._sessions.session(DatabaseTarget.MASTER) as session:
                await ThreadMemoryRepository.mark_completed(
                    session,
                    thread_id=thread_id,
                    user_id=user_id,
                    summary_md=updated_summary,
                    last_summarized_message_id=latest_message_id,
                    summarizer_provider=self._provider_label,
                    summarizer_model=self._model_identifier,
                )
        except Exception as exc:  # pragma: no cover - defensive background task boundary
            LOGGER.warning("Thread memory refresh failed for thread %s: %s", thread_id, exc)
            try:
                async with self._sessions.session(DatabaseTarget.MASTER) as session:
                    await ThreadMemoryRepository.mark_failed(
                        session,
                        thread_id=thread_id,
                        user_id=user_id,
                        error_message=str(exc),
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

    @staticmethod
    def _select_delta_messages(messages: list[Message], *, after_message_id: int | None) -> list[Message]:
        if after_message_id is None:
            return messages[-MAX_DELTA_MESSAGES:]
        selected = [message for message in messages if message.id > after_message_id]
        return selected[-MAX_DELTA_MESSAGES:]

    @classmethod
    def _format_transcript(cls, messages: Iterable[Message]) -> str:
        lines: list[str] = []
        total = 0
        for message in messages:
            content = message.content.strip()
            if not content:
                continue
            line = f"message_id={message.id} role={message.role}: {content}"
            remaining = MAX_TRANSCRIPT_CHARACTERS - total
            if remaining <= 0:
                break
            if len(line) > remaining:
                line = line[:remaining]
            lines.append(line)
            total += len(line)
        return "\n\n".join(lines)

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[-limit:]

    @staticmethod
    def _build_prompt(*, previous_summary: str, transcript: str) -> str:
        previous = previous_summary.strip() or "No prior memory exists for this thread."
        return (
            "[Previous thread memory]\n"
            f"{previous}\n\n"
            "[New transcript since last memory update]\n"
            f"{transcript}\n\n"
            "Update the full thread memory document now. The returned document replaces the previous memory."
        )
