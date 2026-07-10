"""Prompt contract for evidence-based thread-memory reconciliation."""

from __future__ import annotations

MAX_PREVIOUS_MEMORY_CHARACTERS = 6_000

MEMORY_SYSTEM_DIRECTIVES = (
    "You maintain durable conversation memory for future AI agents. "
    "This is state reconciliation, not a conversational recap.\n"
    "Return exactly one JSON object and no markdown fences or commentary.\n"
    "Use only facts supported by the existing memory or new transcript. "
    "Never turn assistant guesses, proposals, or uncertainty into facts.\n"
    "When information conflicts, the newest explicit user correction or confirmed outcome wins. "
    "Remove superseded state instead of preserving both versions.\n"
    "Keep completed work, current state, open tasks, decisions, references, and failures separate. "
    "Preserve exact names, paths, IDs, URLs, branch names, commit SHAs, errors, and constraints when useful.\n"
    "Never output credentials or secret values. Record only whether a credential exists, is missing, failed, "
    "or was rotated.\n"
    "Keep bullets atomic and concise. Use an empty array when a section has no supported facts.\n"
    "Prefer the existing thread title while it remains accurate. The title must be 3-8 words with no markdown.\n"
    "Required JSON keys: thread_title, objective, user_requirements, current_state, decisions, "
    "technical_references, completed_work, open_tasks, risks_and_failures, recent_changes. "
    "Every key except thread_title must contain an array of strings."
)


def clip_previous_memory(value: str) -> str:
    """Retain both durable foundations and the newest checkpoint details."""
    normalized = value.strip()
    if len(normalized) <= MAX_PREVIOUS_MEMORY_CHARACTERS:
        return normalized
    marker = "\n\n[older memory middle omitted]\n\n"
    head_length = (MAX_PREVIOUS_MEMORY_CHARACTERS - len(marker)) * 2 // 3
    tail_length = MAX_PREVIOUS_MEMORY_CHARACTERS - len(marker) - head_length
    return f"{normalized[:head_length]}{marker}{normalized[-tail_length:]}"


def build_memory_prompt(
    *,
    previous_summary: str,
    transcript: str,
    current_thread_title: str,
    batch_number: int,
    total_batches: int,
    force_rebuild: bool,
) -> str:
    """Build one complete-state replacement request from existing state and new evidence."""
    previous = previous_summary.strip() or "No prior memory is available. Build state only from this transcript."
    mode = "full rebuild from the complete thread" if force_rebuild else "incremental consolidation"
    return (
        "[Update mode]\n"
        f"{mode}; batch {batch_number} of {total_batches}\n\n"
        "[Current thread title]\n"
        f"{current_thread_title.strip() or 'Untitled thread'}\n\n"
        "[Existing durable memory]\n"
        f"{previous}\n\n"
        "[New chronological transcript evidence]\n"
        f"{transcript}\n\n"
        "Reconcile the memory with the evidence and return the complete replacement JSON state. "
        "Retain valid facts, add confirmed information, remove superseded state, and keep unresolved items open. "
        "recent_changes must cover meaningful changes across this refresh, including relevant changes retained "
        "from earlier batches in the existing durable memory."
    )
