"""Validated state model and canonical rendering for thread memory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast

MAX_STORED_MEMORY_CHARACTERS = 5_000
MAX_THREAD_TITLE_CHARACTERS = 64
MAX_BULLET_CHARACTERS = 320
MAX_ITEMS_PER_SECTION = 10

SECTION_HEADINGS = {
    "objective": "Objective",
    "user_requirements": "User requirements and preferences",
    "current_state": "Current state",
    "decisions": "Decisions",
    "technical_references": "Technical references",
    "completed_work": "Completed work",
    "open_tasks": "Open tasks",
    "risks_and_failures": "Risks and failures",
    "recent_changes": "Recent changes",
}
SECTION_FIELDS = tuple(SECTION_HEADINGS)
KEY_FACT_FIELDS = (
    "objective",
    "user_requirements",
    "current_state",
    "decisions",
    "technical_references",
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
    r"(?i)\b(api[ _-]?key|password|secret|access[ _-]?token|refresh[ _-]?token)\b" r"(\s*[:=]\s*)([^\s,;]+)"
)
_SECRET_TOKEN_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|" r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9._~+/=-]{12,})")
_DATABASE_CREDENTIAL_PATTERN = re.compile(r"(?i)\b((?:postgres(?:ql)?|mysql|mariadb)://[^:\s/@]+:)([^@\s/]+)(@)")


@dataclass(slots=True)
class ThreadMemoryDocument:
    """Complete validated memory state returned by the summarizer."""

    thread_title: str
    sections: dict[str, list[str]]

    def to_markdown(self, *, checkpoint_message_id: int, update_mode: str) -> str:
        lines = ["# Thread Memory", "", "## Thread title", self.thread_title]
        for field_name, heading in SECTION_HEADINGS.items():
            lines.extend(["", f"## {heading}"])
            values = self.sections[field_name]
            if values:
                lines.extend(f"- {value}" for value in values)
            else:
                lines.append("- None recorded.")
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
        return self._selected_markdown(KEY_FACT_FIELDS)

    def open_tasks_markdown(self) -> str:
        return self._selected_markdown(("open_tasks",))

    def _selected_markdown(self, fields: tuple[str, ...]) -> str:
        rendered: list[str] = []
        for field_name in fields:
            values = self.sections[field_name]
            bullets = "\n".join(f"- {value}" for value in values) if values else "- None recorded."
            rendered.append(f"## {SECTION_HEADINGS[field_name]}\n{bullets}")
        return "\n\n".join(rendered)


def parse_memory_document(raw_output: str, *, fallback_title: str) -> ThreadMemoryDocument:
    """Parse model JSON into bounded, redacted, canonical memory state."""
    candidate = raw_output.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("The memory summarizer returned malformed JSON.")
    try:
        decoded: object = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("The memory summarizer returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("The memory summarizer JSON must be an object.")

    payload = cast(dict[str, object], decoded)
    raw_title = payload.get("thread_title")
    title_source = raw_title if isinstance(raw_title, str) and raw_title.strip() else fallback_title
    sections = {field_name: _coerce_list(payload, field_name) for field_name in SECTION_FIELDS}
    return ThreadMemoryDocument(
        thread_title=_clean_title(title_source) or "Conversation thread",
        sections=sections,
    )


def fit_memory_document(
    document: ThreadMemoryDocument,
    *,
    checkpoint_message_id: int,
    update_mode: str,
) -> None:
    """Reduce low-priority bullets until canonical memory fits its storage budget."""
    while (
        len(
            document.to_markdown(
                checkpoint_message_id=checkpoint_message_id,
                update_mode=update_mode,
            )
        )
        > MAX_STORED_MEMORY_CHARACTERS
    ):
        for field_name in _TRIM_ORDER:
            values = document.sections[field_name]
            if len(values) > _PRIORITY_MINIMUM_ITEMS.get(field_name, 0):
                values.pop()
                break
        else:
            raise RuntimeError("The validated thread memory exceeds the storage limit.")


def redact_sensitive_text(value: str) -> str:
    """Remove common credential forms before external processing or persistence."""
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[redacted]", value)
    redacted = _SECRET_TOKEN_PATTERN.sub("[redacted]", redacted)
    redacted = _BEARER_TOKEN_PATTERN.sub(r"\1[redacted]", redacted)
    return _DATABASE_CREDENTIAL_PATTERN.sub(r"\1[redacted]\3", redacted)


def _coerce_list(payload: dict[str, object], field_name: str) -> list[str]:
    raw_values = payload.get(field_name, [])
    if not isinstance(raw_values, list):
        raise RuntimeError(f"Memory field {field_name!r} must be a JSON array.")
    values: list[str] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            continue
        value = _clean_bullet(raw_value)
        if value and value not in values:
            values.append(value)
        if len(values) >= MAX_ITEMS_PER_SECTION:
            break
    return values


def _clean_bullet(value: str) -> str:
    cleaned = re.sub(r"^[\s\-*>#]+", "", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip('`*_"')
    return redact_sensitive_text(cleaned)[:MAX_BULLET_CHARACTERS].rstrip(" -—:,.#")


def _clean_title(value: str) -> str:
    title = re.sub(r"^[\s\-*>#]+", "", value)
    title = re.sub(r"\s+", " ", title).strip().strip('`*_"')
    return title[:MAX_THREAD_TITLE_CHARACTERS].rstrip(" -—:,.#")
