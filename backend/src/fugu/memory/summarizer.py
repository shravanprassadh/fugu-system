"""Background thread-memory summarisation service."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Message
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository, ThreadRepository
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
MAX_THREAD_TITLE_CHARACTERS = 64

MEMORY_SYSTEM_DIRECTIVES = (
    "You are Fugu's thread-memory maintainer.\n"
    "Your output is consumed by future AI agents, not just humans. Write it as an operational handoff.\n"
    "Return markdown only. Do not add commentary outside the document.\n"
    "Never store API keys, passwords, full secrets, private tokens, or sensitive credentials.\n"
    "Do not write vague narrative. Use dense bullets with exact names, paths, IDs, URLs, branch names, commit SHAs, "
    "status messages, blockers, and user decisions when available.\n"
    "Preserve user preferences and constraints that affect future actions. Preserve mistakes already made and fixes applied.\n"
    "Remove stale details only when they are clearly superseded. If uncertain, keep the fact and mark it as uncertain.\n"
    "The title must be 3-8 words, specific to the conversation, and must not include quotes or markdown.\n"
    "Each section except ## Thread title should use short bullets. Prefer 'key: value' bullets when possible.\n"
    "Use these headings exactly:\n"
    "# Thread Memory\n"
    "## Thread title\n"
    "## AI handoff brief\n"
    "## User intent and preferences\n"
    "## Current implementation state\n"
    "## Exact technical references\n"
    "## Decisions and constraints\n"
    "## Known failures and blockers\n"
    "## Open tasks / next actions\n"
    "## Last summarized range\n"
)


class ThreadMemorySummarizer:
    """Maintain rolling AI handoff summaries and concise thread titles."""

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
        """Update the stored markdown memory and thread title using the configured Google AI Studio key."""
        previous_summary = ""
        transcript = ""
        current_thread_title = ""
        credential: str | None = None
        try:
            async with self._sessions.session(DatabaseTarget.MASTER) as session:
                credential = await self._vault.retrieve(session, provider_name=self._credential_provider_name)
                if credential is None:
                    return
                thread = await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
                current_thread_title = thread.name
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
                    prompt_content=self._build_prompt(
                        previous_summary=previous_summary,
                        transcript=transcript,
                        current_thread_title=current_thread_title,
                    ),
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

            suggested_title = self._extract_thread_title(updated_summary)
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
                if suggested_title:
                    thread = await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
                    thread.name = suggested_title
                    await session.flush()
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
    def _extract_thread_title(summary_md: str) -> str:
        match = re.search(
            r"^##\s+Thread title\s*$\s*(.*?)(?=^##\s+|\Z)",
            summary_md,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if match is None:
            return ""
        raw_title = match.group(1).strip().splitlines()[0] if match.group(1).strip() else ""
        title = re.sub(r"^[\-*>#\s]+", "", raw_title).strip().strip('"`*_')
        title = re.sub(r"\s+", " ", title)
        if not title:
            return ""
        return title[:MAX_THREAD_TITLE_CHARACTERS].rstrip(" -—:,.#")

    @staticmethod
    def _build_prompt(*, previous_summary: str, transcript: str, current_thread_title: str) -> str:
        previous = previous_summary.strip() or "No prior memory exists for this thread."
        title = current_thread_title.strip() or "Untitled thread"
        return (
            "[Current thread title]\n"
            f"{title}\n\n"
            "[Previous AI handoff memory]\n"
            f"{previous}\n\n"
            "[New transcript since last memory update]\n"
            f"{transcript}\n\n"
            "Rewrite the full memory as a future-agent handoff. The returned document replaces the previous memory. "
            "Prioritize details that let a future AI continue work without rereading the thread: exact current goal, "
            "what changed, where code lives, commits, file paths, APIs, UI routes, deployment state, blockers, "
            "mistakes to avoid, user preferences, and next action. Also fill ## Thread title with the best concise page heading. "
            "Avoid conversational recap unless it directly affects future work."
        )
