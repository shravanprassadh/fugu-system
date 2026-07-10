"""Background thread-memory consolidation service."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import cast

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Message
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository, ThreadRepository
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.google import GoogleGeminiProvider
from fugu.security.encryption import ProviderCredentialVault

LOGGER = logging.getLogger(__name__)

MEMORY_CREDENTIAL_PROVIDER_NAME = "thread_memory_google_ai_studio"
MEMORY_PROVIDER_LABEL = "google-ai-studio"
MEMORY_MODEL_IDENTIFIER = "gemini-2.5-flash-lite"
MAX_BATCH_FRAGMENTS = 30
MAX_TRANSCRIPT_CHARACTERS = 16_000
MAX_MESSAGE_FRAGMENT_CHARACTERS = 7_000
MAX_PREVIOUS_MEMORY_CHARACTERS = 6_000
MAX_STORED_MEMORY_CHARACTERS = 5_000
MAX_THREAD_TITLE_CHARACTERS = 64
MAX_BULLET_CHARACTERS = 320
MAX_ITEMS_PER_SECTION = 10

_SECTION_SPECS: tuple[tuple[str, str], ...] = (
    ("Objective", "objective"),
    ("User requirements and preferences", "user_requirements"),
    ("Current state", "current_state"),
    ("Decisions", "decisions"),
    ("Technical references", "technical_references"),
    ("Completed work", "completed_work"),
    ("Open tasks", "open_tasks"),
    ("Risks and failures", "risks_and_failures"),
    ("Recent changes", "recent_changes"),
)
_TRIM_ORDER = (
    "recent_changes",
    "completed_work",
    "technical_references",
    "decisions",
    "risks_and_failures",
    "user_requirements",
    "current_state",
    "open_tasks",
    "objective",
)
_PRIORITY_MINIMUM_ITEMS = {"current_state": 2, "open_tasks": 2, "objective": 1}
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[ _-]?key|password|secret|access[ _-]?token|refresh[ _-]?token)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_SECRET_TOKEN_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,})\b")

MEMORY_SYSTEM_DIRECTIVES = (
    "You maintain durable conversation memory for future AI agents. "
    "This is state reconciliation, not a conversational recap.\n"
    "Return exactly one JSON object and no markdown fences or commentary.\n"
    "Use only facts supported by the existing memory or the new transcript. "
    "Do not convert assistant guesses, proposals, or uncertainty into facts.\n"
    "When information conflicts, the newest explicit user correction or confirmed outcome wins. "
    "Remove superseded state instead of preserving both versions.\n"
    "Separate completed work, current state, open tasks, and failures. "
    "Keep exact names, paths, IDs, URLs, branch names, commit SHAs, error messages, and constraints when useful.\n"
    "Never output API keys, passwords, private tokens, credentials, or secret values. "
    "You may record that a credential exists, is missing, failed, or was rotated without recording its value.\n"
    "Keep bullets atomic and concise. Use an empty array when a section has no supported facts.\n"
    "Prefer the existing thread title when it is still accurate; do not rename for minor conversational changes. "
    "The title must be 3-8 words and contain no markdown.\n"
    "Required JSON keys: thread_title, objective, user_requirements, current_state, decisions, "
    "technical_references, completed_work, open_tasks, risks_and_failures, recent_changes. "
    "Every key except thread_title must contain an array of strings."
)


@dataclass
class TranscriptBatch:
    """One chronological transcript batch sent to the summarizer."""

    text: str
    last_message_id: int


@dataclass
class ThreadMemoryDocument:
    """Validated structured state rendered into canonical markdown by the server."""

    thread_title: str
    objective: list[str]
    user_requirements: list[str]
    current_state: list[str]
    decisions: list[str]
    technical_references: list[str]
    completed_work: list[str]
    open_tasks: list[str]
    risks_and_failures: list[str]
    recent_changes: list[str]

    def to_markdown(self, *, checkpoint_message_id: int, update_mode: str) -> str:
        lines = ["# Thread Memory", "", "## Thread title", self.thread_title]
        for heading, field_name in _SECTION_SPECS:
            lines.extend(["", f"## {heading}"])
            values = cast(list[str], getattr(self, field_name))
            lines.extend(f"- {value}" for value in values) if values else lines.append("- None recorded.")
        lines.extend(
            [
                "",
                "## Memory checkpoint",
                f"- summarized through message_id: {checkpoint_message_id}",
                f"- update mode: {update_mode}",
            ]
        )
        return "\n".join(lines).strip()

    def key_facts_markdown(self) -> str:
        sections = (
            ("Objective", self.objective),
            ("User requirements and preferences", self.user_requirements),
            ("Current state", self.current_state),
            ("Decisions", self.decisions),
            ("Technical references", self.technical_references),
        )
        return self._render_selected_sections(sections)

    def open_tasks_markdown(self) -> str:
        return self._render_selected_sections((("Open tasks", self.open_tasks),))

    @staticmethod
    def _render_selected_sections(sections: Iterable[tuple[str, list[str]]]) -> str:
        lines: list[str] = []
        for heading, values in sections:
            if lines:
                lines.append("")
            lines.append(f"## {heading}")
            lines.extend(f"- {value}" for value in values) if values else lines.append("- None recorded.")
        return "\n".join(lines)


class ThreadMemorySummarizer:
    """Maintain rolling AI handoff memory and concise thread titles."""

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
        self._refresh_locks: dict[int, asyncio.Lock] = {}

    def schedule(
        self,
        *,
        thread_id: int,
        user_id: int,
        latest_message_id: int,
    ) -> None:
        """Queue an incremental memory update after an assistant response is persisted."""
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
        """Rebuild all memory by default; scheduled updates explicitly use incremental mode."""
        lock = self._refresh_locks.setdefault(thread_id, asyncio.Lock())
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
        previous_summary = ""
        current_thread_title = ""
        credential: str | None = None
        batches: list[TranscriptBatch] = []
        update_mode = "full rebuild" if force_rebuild else "incremental"
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
                if not force_rebuild:
                    previous_summary = self._clip_for_prompt(
                        memory.summary_md or "",
                        MAX_PREVIOUS_MEMORY_CHARACTERS,
                    )
                messages = await MessageRepository.list_for_thread(
                    session,
                    thread_id=thread_id,
                    user_id=user_id,
                )
                pending_messages = self._select_pending_messages(
                    messages,
                    after_message_id=None if force_rebuild else memory.last_summarized_message_id,
                    through_message_id=latest_message_id,
                )
                if not pending_messages:
                    memory.status = "completed"
                    memory.error_message = None
                    await session.flush()
                    return
                batches = self._build_transcript_batches(pending_messages)

            provider = self._provider_factory()
            document: ThreadMemoryDocument | None = None
            rolling_summary = previous_summary
            try:
                for batch_number, batch in enumerate(batches, start=1):
                    request = ProviderRequest(
                        prompt_content=self._build_prompt(
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
                    fragments: list[str] = []
                    async for token in provider.generate_token_stream(request):
                        fragments.append(token)
                    raw_document = "".join(fragments).strip()
                    if not raw_document:
                        raise RuntimeError("The memory summarizer returned an empty document.")
                    document = self._parse_document(raw_document, fallback_title=current_thread_title)
                    self._fit_document(document, checkpoint_message_id=batch.last_message_id, update_mode=update_mode)
                    rolling_summary = document.to_markdown(
                        checkpoint_message_id=batch.last_message_id,
                        update_mode=update_mode,
                    )
            finally:
                await provider.aclose()

            if document is None:
                raise RuntimeError("The memory summarizer did not process any transcript batches.")

            checkpoint_message_id = batches[-1].last_message_id
            summary_md = document.to_markdown(
                checkpoint_message_id=checkpoint_message_id,
                update_mode=update_mode,
            )
            async with self._sessions.session(DatabaseTarget.MASTER) as session:
                completed_memory = await ThreadMemoryRepository.mark_completed(
                    session,
                    thread_id=thread_id,
                    user_id=user_id,
                    summary_md=summary_md,
                    last_summarized_message_id=checkpoint_message_id,
                    summarizer_provider=self._provider_label,
                    summarizer_model=self._model_identifier,
                )
                completed_memory.key_facts_md = document.key_facts_markdown()
                completed_memory.open_tasks_md = document.open_tasks_markdown()
                thread = await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
                thread.name = document.thread_title
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
    def _select_pending_messages(
        messages: list[Message],
        *,
        after_message_id: int | None,
        through_message_id: int,
    ) -> list[Message]:
        return [
            message
            for message in messages
            if message.id <= through_message_id and (after_message_id is None or message.id > after_message_id)
        ]

    @classmethod
    def _build_transcript_batches(cls, messages: Iterable[Message]) -> list[TranscriptBatch]:
        batches: list[TranscriptBatch] = []
        current_fragments: list[str] = []
        current_characters = 0
        current_last_message_id: int | None = None

        for message in messages:
            content = message.content.strip()
            if not content:
                continue
            chunks = [
                content[index : index + MAX_MESSAGE_FRAGMENT_CHARACTERS]
                for index in range(0, len(content), MAX_MESSAGE_FRAGMENT_CHARACTERS)
            ]
            for chunk_index, chunk in enumerate(chunks, start=1):
                fragment = (
                    f"message_id={message.id} role={message.role} "
                    f"part={chunk_index}/{len(chunks)}\n{chunk}"
                )
                separator_characters = 2 if current_fragments else 0
                would_overflow = (
                    current_fragments
                    and (
                        len(current_fragments) >= MAX_BATCH_FRAGMENTS
                        or current_characters + separator_characters + len(fragment) > MAX_TRANSCRIPT_CHARACTERS
                    )
                )
                if would_overflow:
                    assert current_last_message_id is not None
                    batches.append(
                        TranscriptBatch(
                            text="\n\n".join(current_fragments),
                            last_message_id=current_last_message_id,
                        )
                    )
                    current_fragments = []
                    current_characters = 0
                    separator_characters = 0
                current_fragments.append(fragment)
                current_characters += separator_characters + len(fragment)
                current_last_message_id = message.id

        if current_fragments:
            assert current_last_message_id is not None
            batches.append(
                TranscriptBatch(
                    text="\n\n".join(current_fragments),
                    last_message_id=current_last_message_id,
                )
            )
        return batches

    @classmethod
    def _parse_document(cls, raw_output: str, *, fallback_title: str) -> ThreadMemoryDocument:
        candidate = raw_output.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*```$", "", candidate)
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end < start:
            raise RuntimeError("The memory summarizer returned malformed JSON.")
        try:
            decoded = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError("The memory summarizer returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("The memory summarizer JSON must be an object.")
        payload = cast(dict[str, object], decoded)
        raw_title = payload.get("thread_title")
        title_source = raw_title if isinstance(raw_title, str) and raw_title.strip() else fallback_title
        title = cls._clean_title(title_source)
        return ThreadMemoryDocument(
            thread_title=title or "Conversation thread",
            objective=cls._coerce_list(payload, "objective"),
            user_requirements=cls._coerce_list(payload, "user_requirements"),
            current_state=cls._coerce_list(payload, "current_state"),
            decisions=cls._coerce_list(payload, "decisions"),
            technical_references=cls._coerce_list(payload, "technical_references"),
            completed_work=cls._coerce_list(payload, "completed_work"),
            open_tasks=cls._coerce_list(payload, "open_tasks"),
            risks_and_failures=cls._coerce_list(payload, "risks_and_failures"),
            recent_changes=cls._coerce_list(payload, "recent_changes"),
        )

    @classmethod
    def _coerce_list(cls, payload: dict[str, object], field_name: str) -> list[str]:
        raw_values = payload.get(field_name, [])
        if not isinstance(raw_values, list):
            raise RuntimeError(f"Memory field {field_name!r} must be a JSON array.")
        values: list[str] = []
        for raw_value in raw_values:
            if not isinstance(raw_value, str):
                continue
            value = cls._clean_bullet(raw_value)
            if value and value not in values:
                values.append(value)
            if len(values) >= MAX_ITEMS_PER_SECTION:
                break
        return values

    @classmethod
    def _clean_bullet(cls, value: str) -> str:
        cleaned = re.sub(r"^[\s\-*>#]+", "", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().strip("`*_\"")
        cleaned = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[redacted]", cleaned)
        cleaned = _SECRET_TOKEN_PATTERN.sub("[redacted]", cleaned)
        return cleaned[:MAX_BULLET_CHARACTERS].rstrip(" -—:,.#")

    @staticmethod
    def _clean_title(value: str) -> str:
        title = re.sub(r"^[\s\-*>#]+", "", value)
        title = re.sub(r"\s+", " ", title).strip().strip("`*_\"")
        return title[:MAX_THREAD_TITLE_CHARACTERS].rstrip(" -—:,.#")

    @classmethod
    def _fit_document(
        cls,
        document: ThreadMemoryDocument,
        *,
        checkpoint_message_id: int,
        update_mode: str,
    ) -> None:
        while (
            len(
                document.to_markdown(
                    checkpoint_message_id=checkpoint_message_id,
                    update_mode=update_mode,
                )
            )
            > MAX_STORED_MEMORY_CHARACTERS
        ):
            changed = False
            for field_name in _TRIM_ORDER:
                values = cast(list[str], getattr(document, field_name))
                minimum = _PRIORITY_MINIMUM_ITEMS.get(field_name, 0)
                if len(values) > minimum:
                    values.pop()
                    changed = True
                    break
            if not changed:
                raise RuntimeError("The validated thread memory could not be reduced to the storage limit.")

    @staticmethod
    def _clip_for_prompt(value: str, limit: int) -> str:
        normalized = value.strip()
        if len(normalized) <= limit:
            return normalized
        marker = "\n\n[older memory middle omitted]\n\n"
        head_length = (limit - len(marker)) * 2 // 3
        tail_length = limit - len(marker) - head_length
        return f"{normalized[:head_length]}{marker}{normalized[-tail_length:]}"

    @staticmethod
    def _build_prompt(
        *,
        previous_summary: str,
        transcript: str,
        current_thread_title: str,
        batch_number: int,
        total_batches: int,
        force_rebuild: bool,
    ) -> str:
        previous = previous_summary.strip() or "No prior memory is available. Build state only from this transcript."
        title = current_thread_title.strip() or "Untitled thread"
        mode = "full rebuild from the complete thread" if force_rebuild else "incremental consolidation"
        return (
            "[Update mode]\n"
            f"{mode}; batch {batch_number} of {total_batches}\n\n"
            "[Current thread title]\n"
            f"{title}\n\n"
            "[Existing durable memory]\n"
            f"{previous}\n\n"
            "[New chronological transcript evidence]\n"
            f"{transcript}\n\n"
            "Reconcile the existing memory with the transcript evidence and return the complete replacement JSON state. "
            "Retain still-valid facts, incorporate new confirmed information, remove superseded state, and keep unresolved "
            "items open. recent_changes must contain only meaningful changes introduced by this batch."
        )
