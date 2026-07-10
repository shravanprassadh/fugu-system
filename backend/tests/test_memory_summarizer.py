"""Behavioral tests for durable thread-memory consolidation."""

from __future__ import annotations

import json

import pytest

from fugu.database.connection import DatabaseTarget
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository, ThreadRepository
from fugu.memory.summarizer import ThreadMemorySummarizer
from tests.test_execution import ExecutionContext, ScriptedProvider

pytest_plugins = ("tests.test_execution",)


def _memory_json(
    *,
    title: str = "Reliable Thread Memory",
    objective: list[str] | None = None,
    open_tasks: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "thread_title": title,
            "objective": objective or ["Maintain accurate durable memory"],
            "user_requirements": ["Keep the handoff concise and operational"],
            "current_state": ["Structured memory consolidation is active"],
            "decisions": ["Use validated JSON before rendering markdown"],
            "technical_references": ["backend/src/fugu/memory/summarizer.py"],
            "completed_work": ["Replaced free-form summary generation"],
            "open_tasks": open_tasks or ["Verify the pull request CI gate"],
            "risks_and_failures": ["Malformed model output must not replace valid memory"],
            "recent_changes": ["Memory is rebuilt from chronological evidence"],
        }
    )


def _summarizer(execution_context: ExecutionContext) -> ThreadMemorySummarizer:
    return ThreadMemorySummarizer(
        session_registry=execution_context.registry,
        credential_vault=execution_context.vault,
        credential_provider_name="mock",
        provider_label="mock",
        model_identifier="memory",
        provider_factory=lambda: ScriptedProvider(execution_context.script),
    )


@pytest.mark.asyncio
async def test_manual_refresh_rebuilds_from_the_complete_thread_and_redacts_secrets(
    execution_context: ExecutionContext,
) -> None:
    """A manual refresh ignores the old checkpoint and reconstructs memory from message one."""
    raw_api_key = "sk-test-secret-value-123456789"
    raw_bearer = "header.payload.signaturevalue123456789"
    raw_database_password = "database-password"
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        first_message = await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="user",
            content=(
                f"Start from this requirement. api_key={raw_api_key}; "
                f"Bearer {raw_bearer}; postgresql://operator:{raw_database_password}@db.example/fugu"
            ),
        )
        latest_message = await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="assistant",
            content="The current implementation still needs a full rebuild.",
        )
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            summarizer_provider="old-provider",
            summarizer_model="old-model",
        )
        memory.summary_md = "# Stale memory\n- This must not be used during a full rebuild."
        memory.last_summarized_message_id = latest_message.id
        await session.flush()

    execution_context.script.tokens_by_model = {
        "memory": [
            _memory_json(
                objective=[
                    f"Protect api_key={raw_api_key}",
                    f"Do not persist password={raw_database_password}",
                ]
            )
        ]
    }

    await _summarizer(execution_context).refresh(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        latest_message_id=latest_message.id,
    )

    assert len(execution_context.script.requests) == 1
    provider_prompt = execution_context.script.requests[0].prompt_content
    assert f"message_id={first_message.id}" in provider_prompt
    assert "full rebuild from the complete thread" in provider_prompt
    assert "No prior memory is available" in provider_prompt
    assert "This must not be used during a full rebuild" not in provider_prompt
    assert raw_api_key not in provider_prompt
    assert raw_bearer not in provider_prompt
    assert raw_database_password not in provider_prompt
    assert "[redacted]" in provider_prompt

    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        stored_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
        )
        thread = await ThreadRepository.require_owned(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
        )

    assert stored_memory is not None
    assert stored_memory.status == "completed"
    assert stored_memory.last_summarized_message_id == latest_message.id
    assert stored_memory.summary_md.startswith("# Thread Memory")
    assert "- update mode: full rebuild" in stored_memory.summary_md
    assert "[redacted]" in stored_memory.summary_md
    assert raw_api_key not in stored_memory.summary_md
    assert raw_database_password not in stored_memory.summary_md
    assert "## Objective" in stored_memory.key_facts_md
    assert "## Open tasks" in stored_memory.open_tasks_md
    assert thread.name == "Reliable Thread Memory"


@pytest.mark.asyncio
async def test_incremental_refresh_processes_every_unsummarized_message_across_batches(
    execution_context: ExecutionContext,
) -> None:
    """More than one batch is consolidated in order without silently discarding older deltas."""
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        checkpoint_message = await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="assistant",
            content="Already summarized checkpoint.",
        )
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            summarizer_provider="mock",
            summarizer_model="memory",
        )
        memory.summary_md = "# Thread Memory\n\n## Objective\n- Preserve every pending message."
        memory.last_summarized_message_id = checkpoint_message.id

        pending_messages = []
        for index in range(35):
            pending_messages.append(
                await MessageRepository.add(
                    session,
                    thread_id=execution_context.thread_id,
                    user_id=execution_context.user.id,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"delta message {index}",
                )
            )
        await session.flush()

    execution_context.script.tokens_by_model = {"memory": [_memory_json()]}

    await _summarizer(execution_context).refresh(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        latest_message_id=pending_messages[-1].id,
        force_rebuild=False,
    )

    assert len(execution_context.script.requests) == 2
    first_prompt = execution_context.script.requests[0].prompt_content
    second_prompt = execution_context.script.requests[1].prompt_content
    assert "incremental consolidation; batch 1 of 2" in first_prompt
    assert "delta message 0" in first_prompt
    assert "delta message 29" in first_prompt
    assert "delta message 30" not in first_prompt
    assert "incremental consolidation; batch 2 of 2" in second_prompt
    assert "delta message 30" in second_prompt
    assert "delta message 34" in second_prompt
    assert "# Thread Memory" in second_prompt

    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        stored_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
        )

    assert stored_memory is not None
    assert stored_memory.status == "completed"
    assert stored_memory.last_summarized_message_id == pending_messages[-1].id
    assert "- update mode: incremental" in stored_memory.summary_md


@pytest.mark.asyncio
async def test_malformed_model_output_preserves_existing_memory_and_records_failure(
    execution_context: ExecutionContext,
) -> None:
    """Unvalidated model text cannot replace the last known-good durable memory."""
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        message = await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="user",
            content="Generate a durable handoff.",
        )
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            summarizer_provider="mock",
            summarizer_model="memory",
        )
        memory.summary_md = "# Last known good memory"
        await session.flush()

    execution_context.script.tokens_by_model = {"memory": ["not valid JSON"]}

    await _summarizer(execution_context).refresh(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        latest_message_id=message.id,
    )

    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        stored_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
        )

    assert stored_memory is not None
    assert stored_memory.status == "failed"
    assert stored_memory.summary_md == "# Last known good memory"
    assert stored_memory.error_message == "The memory summarizer returned malformed JSON."


@pytest.mark.asyncio
async def test_long_single_message_is_fragmented_without_losing_its_tail(
    execution_context: ExecutionContext,
) -> None:
    """Large messages are split into chronological fragments rather than truncated."""
    content = f"BEGIN-{('x' * 15_000)}-END"
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        message = await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="user",
            content=content,
        )

    batches = ThreadMemorySummarizer._build_transcript_batches([message])

    assert len(batches) == 1
    assert "part=1/3" in batches[0].text
    assert "part=3/3" in batches[0].text
    assert "BEGIN-" in batches[0].text
    assert "-END" in batches[0].text
    assert batches[0].last_message_id == message.id
