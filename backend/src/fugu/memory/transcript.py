"""Chronological transcript selection and lossless batching for thread memory."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fugu.database.models import Message
from fugu.memory.state import redact_sensitive_text

MAX_BATCH_FRAGMENTS = 30
MAX_TRANSCRIPT_CHARACTERS = 16_000
MAX_MESSAGE_FRAGMENT_CHARACTERS = 7_000


@dataclass(frozen=True, slots=True)
class TranscriptBatch:
    """One chronological transcript batch sent to the summarizer."""

    text: str
    last_message_id: int


def select_pending_messages(
    messages: list[Message],
    *,
    after_message_id: int | None,
    through_message_id: int,
) -> list[Message]:
    """Return every message in the requested checkpoint interval, in order."""
    return [
        message
        for message in messages
        if message.id <= through_message_id and (after_message_id is None or message.id > after_message_id)
    ]


def build_transcript_batches(messages: Iterable[Message]) -> list[TranscriptBatch]:
    """Batch all transcript evidence without dropping old deltas or message tails."""
    batches: list[TranscriptBatch] = []
    fragments: list[str] = []
    characters = 0
    last_message_id: int | None = None

    for message in messages:
        content = redact_sensitive_text(message.content.strip())
        if not content:
            continue
        chunks = [
            content[index : index + MAX_MESSAGE_FRAGMENT_CHARACTERS]
            for index in range(0, len(content), MAX_MESSAGE_FRAGMENT_CHARACTERS)
        ]
        for part_number, chunk in enumerate(chunks, start=1):
            fragment = f"message_id={message.id} role={message.role} part={part_number}/{len(chunks)}\n{chunk}"
            separator = 2 if fragments else 0
            overflow = bool(
                fragments
                and (
                    len(fragments) >= MAX_BATCH_FRAGMENTS
                    or characters + separator + len(fragment) > MAX_TRANSCRIPT_CHARACTERS
                )
            )
            if overflow:
                if last_message_id is None:
                    raise RuntimeError("Transcript batching lost its message checkpoint.")
                batches.append(TranscriptBatch("\n\n".join(fragments), last_message_id))
                fragments, characters, separator = [], 0, 0
            fragments.append(fragment)
            characters += separator + len(fragment)
            last_message_id = message.id

    if fragments:
        if last_message_id is None:
            raise RuntimeError("Transcript batching ended without a message checkpoint.")
        batches.append(TranscriptBatch("\n\n".join(fragments), last_message_id))
    return batches
