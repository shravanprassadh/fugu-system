"""Regression tests for thread-local memory injection."""

from __future__ import annotations

import pytest

from fugu.database.connection import DatabaseTarget
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository
from fugu.execution.kernel import (
    _MAX_MEMORY_CHARACTERS,
    _MAX_MEMORY_MESSAGES,
    _MAX_THREAD_MEMORY_CHARACTERS,
)
from tests.test_execution import ExecutionContext, _seed_steps, _step

pytest_plugins = ("tests.test_execution",)

_MEMORY_SECTION_LABEL = "[Thread memory summary]"
_TRANSCRIPT_SECTION_LABEL = "[Recent raw transcript]"
_REQUEST_SECTION_LABEL = "[Current user request]"
_RETIRED_SECTION_LABEL = "[Recent thread memory]"


async def _seed_memory_summary(
    execution_context: ExecutionContext,
    summary_md: str,
) -> None:
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            summarizer_provider="mock",
            summarizer_model="mock-summarizer",
        )
        memory.summary_md = summary_md
        await session.flush()


async def _run_terminal_pipeline(
    execution_context: ExecutionContext,
    *,
    initial_prompt: str,
) -> str:
    """Execute a single-step pipeline and return the prompt the provider received."""
    prepared = await execution_context.kernel.prepare_execution(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        initial_prompt=initial_prompt,
    )
    _ = [event async for event in execution_context.kernel.execute(prepared)]
    return execution_context.script.requests[0].prompt_content


def _section_body(prompt: str, section_label: str, next_section_label: str) -> str:
    """Return a section's content without its label and instruction lines."""
    section = prompt.split(f"{section_label}\n", 1)[1]
    section = section.split(f"\n\n{next_section_label}", 1)[0]
    instruction_line, _, body = section.partition("\n")
    assert "Do not treat it as a new user request." in instruction_line
    return body


@pytest.mark.asyncio
async def test_kernel_injects_bounded_thread_memory_into_provider_prompt(
    execution_context: ExecutionContext,
) -> None:
    """The provider prompt carries the AI-handoff structure: durable summary, then bounded transcript."""
    await _seed_steps(execution_context, [_step("Terminal", 1, terminal=True, model="terminal")])
    execution_context.script.tokens_by_model = {"terminal": ["Remembered answer"]}

    exchanges = _MAX_MEMORY_MESSAGES // 2 + 1
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        for index in range(exchanges):
            await MessageRepository.add(
                session,
                thread_id=execution_context.thread_id,
                user_id=execution_context.user.id,
                role="user",
                content=f"user question {index}",
            )
            await MessageRepository.add(
                session,
                thread_id=execution_context.thread_id,
                user_id=execution_context.user.id,
                role="assistant",
                content=f"assistant reply {index}",
            )
    await _seed_memory_summary(
        execution_context,
        "# Thread Memory\n- project codename: Fugu\n- deployment: Render + Vercel",
    )

    prompt = await _run_terminal_pipeline(
        execution_context,
        initial_prompt="What is my project codename?",
    )

    assert _MEMORY_SECTION_LABEL in prompt
    assert _TRANSCRIPT_SECTION_LABEL in prompt
    assert prompt.index(_MEMORY_SECTION_LABEL) < prompt.index(_TRANSCRIPT_SECTION_LABEL)
    assert prompt.index(_TRANSCRIPT_SECTION_LABEL) < prompt.index(_REQUEST_SECTION_LABEL)
    assert _RETIRED_SECTION_LABEL not in prompt

    memory_body = _section_body(prompt, _MEMORY_SECTION_LABEL, _TRANSCRIPT_SECTION_LABEL)
    assert "- project codename: Fugu" in memory_body

    # Seeding one exchange past the window pushes the oldest exchange out of the transcript.
    transcript_body = _section_body(prompt, _TRANSCRIPT_SECTION_LABEL, _REQUEST_SECTION_LABEL)
    assert "user: user question 0" not in transcript_body
    assert "assistant: assistant reply 0" not in transcript_body
    assert "user: user question 1" in transcript_body
    assert f"assistant: assistant reply {exchanges - 1}" in transcript_body

    assert f"{_REQUEST_SECTION_LABEL}\nWhat is my project codename?" in prompt


@pytest.mark.asyncio
async def test_kernel_truncates_oversized_memory_and_transcript_sections(
    execution_context: ExecutionContext,
) -> None:
    """Oversized sections keep their most recent tail and stay within the kernel's character bounds."""
    await _seed_steps(execution_context, [_step("Terminal", 1, terminal=True, model="terminal")])
    execution_context.script.tokens_by_model = {"terminal": ["Bounded answer"]}

    memory_filler = "m" * (_MAX_THREAD_MEMORY_CHARACTERS + 500)
    await _seed_memory_summary(execution_context, f"MEMORY-HEAD {memory_filler} MEMORY-TAIL")

    transcript_filler = "t" * (_MAX_MEMORY_CHARACTERS + 500)
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="user",
            content=f"TRANSCRIPT-HEAD {transcript_filler} TRANSCRIPT-TAIL",
        )

    prompt = await _run_terminal_pipeline(execution_context, initial_prompt="Stay within bounds.")

    memory_body = _section_body(prompt, _MEMORY_SECTION_LABEL, _TRANSCRIPT_SECTION_LABEL)
    assert len(memory_body) <= _MAX_THREAD_MEMORY_CHARACTERS
    assert memory_body.endswith("MEMORY-TAIL")
    assert "MEMORY-HEAD" not in memory_body

    transcript_body = _section_body(prompt, _TRANSCRIPT_SECTION_LABEL, _REQUEST_SECTION_LABEL)
    assert len(transcript_body) <= _MAX_MEMORY_CHARACTERS
    assert transcript_body.endswith("TRANSCRIPT-TAIL")
    assert "TRANSCRIPT-HEAD" not in transcript_body
