"""Behavioral tests for durable thread-memory consolidation."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository, ThreadRepository, UserRepository
from fugu.memory.summarizer import ThreadMemorySummarizer
from fugu.memory.transcript import build_transcript_batches
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from tests.database_helpers import create_sqlite_engine_map


@dataclass(slots=True)
class ProviderScript:
    """Deterministic memory-model output and captured provider requests."""

    tokens: list[str] = field(default_factory=list)
    requests: list[ProviderRequest] = field(default_factory=list)


class ScriptedProvider(ExecutionProvider):
    """Provider adapter driven by the shared test script."""

    def __init__(self, script: ProviderScript) -> None:
        self._script = script

    async def generate_token_stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        self._script.requests.append(request)
        for token in self._script.tokens:
            yield token


@dataclass(slots=True)
class MemoryContext:
    """Isolated database, credential vault, and provider script."""

    registry: DatabaseSessionRegistry
    vault: ProviderCredentialVault
    script: ProviderScript
    user_id: int
    thread_id: int


@pytest_asyncio.fixture
async def memory_context() -> AsyncIterator[MemoryContext]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    vault = ProviderCredentialVault(SymmetricVaultEngine(Fernet.generate_key().decode("ascii")))
    script = ProviderScript()
    async with registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(session, username="memory-user", password_hash="test-hash")
        thread = await ThreadRepository.add(session, user_id=user.id, name="Memory test thread")
        await vault.store(session, provider_name="mock-memory", plaintext_secret="mock-provider-secret")
        user_id, thread_id = user.id, thread.id

    yield MemoryContext(
        registry=registry,
        vault=vault,
        script=script,
        user_id=user_id,
        thread_id=thread_id,
    )
    await registry.dispose_pools()


def _memory_json(
    *,
    title: str = "Reliable Thread Memory",
    objective: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "thread_title": title,
            "objective": objective or ["Maintain accurate durable memory"],
            "user_requirements": ["Keep the handoff concise and operational"],
            "current_state": ["Structured memory consolidation is active"],
            "decisions": ["Validate JSON before rendering markdown"],
            "technical_references": ["backend/src/fugu/memory/summarizer.py"],
            "completed_work": ["Replaced free-form summary generation"],
            "open_tasks": ["Verify the pull request CI gate"],
            "risks_and_failures": ["Malformed output must not replace valid memory"],
            "recent_changes": ["Memory is rebuilt from chronological evidence"],
        }
    )


def _summarizer(context: MemoryContext) -> ThreadMemorySummarizer:
    return ThreadMemorySummarizer(
        session_registry=context.registry,
        credential_vault=context.vault,
        credential_provider_name="mock-memory",
        provider_label="mock",
        model_identifier="memory-model",
        provider_factory=lambda: ScriptedProvider(context.script),
    )


@pytest.mark.asyncio
async def test_manual_refresh_rebuilds_complete_thread_and_redacts_secrets(memory_context: MemoryContext) -> None:
    """Manual rebuild ignores the checkpoint and reconstructs memory from message one."""
    raw_api_key = "sk-test-secret-value-123456789"
    raw_bearer = "header.payload.signaturevalue123456789"
    raw_database_password = "database-password"
    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        first_message = await MessageRepository.add(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            role="user",
            content=(
                f"Start here. api_key={raw_api_key}; Bearer {raw_bearer}; "
                f"postgresql://operator:{raw_database_password}@db.example/fugu"
            ),
        )
        latest_message = await MessageRepository.add(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            role="assistant",
            content="The implementation still needs a full rebuild.",
        )
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            summarizer_provider="old-provider",
            summarizer_model="old-model",
        )
        memory.summary_md = "# Stale memory\n- Do not reuse this during a full rebuild."
        memory.last_summarized_message_id = latest_message.id
        await session.flush()

    memory_context.script.tokens = [
        _memory_json(
            objective=[
                f"Protect api_key={raw_api_key}",
                f"Do not persist password={raw_database_password}",
            ]
        )
    ]
    await _summarizer(memory_context).refresh(
        thread_id=memory_context.thread_id,
        user_id=memory_context.user_id,
        latest_message_id=latest_message.id,
    )

    assert len(memory_context.script.requests) == 1
    provider_prompt = memory_context.script.requests[0].prompt_content
    assert f"message_id={first_message.id}" in provider_prompt
    assert "full rebuild from the complete thread" in provider_prompt
    assert "No prior memory is available" in provider_prompt
    assert "Do not reuse this during a full rebuild" not in provider_prompt
    assert raw_api_key not in provider_prompt
    assert raw_bearer not in provider_prompt
    assert raw_database_password not in provider_prompt
    assert "[redacted]" in provider_prompt

    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        stored_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
        )
        thread = await ThreadRepository.require_owned(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
        )
        stored_thread_name = thread.name

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
    assert stored_thread_name == "Reliable Thread Memory"


@pytest.mark.asyncio
async def test_incremental_refresh_processes_all_pending_messages_across_batches(
    memory_context: MemoryContext,
) -> None:
    """Large deltas are consolidated in order without silently skipping older messages."""
    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        checkpoint = await MessageRepository.add(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            role="assistant",
            content="Already summarized checkpoint.",
        )
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            summarizer_provider="mock",
            summarizer_model="memory-model",
        )
        memory.summary_md = "# Thread Memory\n\n## Objective\n- Preserve every pending message."
        memory.last_summarized_message_id = checkpoint.id
        pending_messages = [
            await MessageRepository.add(
                session,
                thread_id=memory_context.thread_id,
                user_id=memory_context.user_id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"delta message {index}",
            )
            for index in range(35)
        ]
        await session.flush()

    memory_context.script.tokens = [_memory_json()]
    await _summarizer(memory_context).refresh(
        thread_id=memory_context.thread_id,
        user_id=memory_context.user_id,
        latest_message_id=pending_messages[-1].id,
        force_rebuild=False,
    )

    assert len(memory_context.script.requests) == 2
    first_prompt = memory_context.script.requests[0].prompt_content
    second_prompt = memory_context.script.requests[1].prompt_content
    assert "incremental consolidation; batch 1 of 2" in first_prompt
    assert "delta message 0" in first_prompt
    assert "delta message 29" in first_prompt
    assert "delta message 30" not in first_prompt
    assert "incremental consolidation; batch 2 of 2" in second_prompt
    assert "delta message 30" in second_prompt
    assert "delta message 34" in second_prompt
    assert "# Thread Memory" in second_prompt

    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        stored_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
        )
    assert stored_memory is not None
    assert stored_memory.status == "completed"
    assert stored_memory.last_summarized_message_id == pending_messages[-1].id
    assert "- update mode: incremental" in stored_memory.summary_md


@pytest.mark.asyncio
async def test_malformed_output_preserves_existing_memory_and_records_failure(memory_context: MemoryContext) -> None:
    """Unvalidated model text cannot replace the last known-good memory."""
    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        message = await MessageRepository.add(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            role="user",
            content="Generate a durable handoff.",
        )
        memory = await ThreadMemoryRepository.get_or_create(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            summarizer_provider="mock",
            summarizer_model="memory-model",
        )
        memory.summary_md = "# Last known good memory"
        await session.flush()

    memory_context.script.tokens = ["not valid JSON"]
    await _summarizer(memory_context).refresh(
        thread_id=memory_context.thread_id,
        user_id=memory_context.user_id,
        latest_message_id=message.id,
    )

    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        stored_memory = await ThreadMemoryRepository.get_for_thread(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
        )
    assert stored_memory is not None
    assert stored_memory.status == "failed"
    assert stored_memory.summary_md == "# Last known good memory"
    assert stored_memory.error_message == "The memory summarizer returned malformed JSON."


@pytest.mark.asyncio
async def test_long_message_is_fragmented_without_losing_its_tail(memory_context: MemoryContext) -> None:
    """Large messages are split into chronological fragments rather than truncated."""
    content = f"BEGIN-{('x' * 15_000)}-END"
    async with memory_context.registry.session(DatabaseTarget.MASTER) as session:
        message = await MessageRepository.add(
            session,
            thread_id=memory_context.thread_id,
            user_id=memory_context.user_id,
            role="user",
            content=content,
        )

    batches = build_transcript_batches([message])
    assert len(batches) == 1
    assert "part=1/3" in batches[0].text
    assert "part=3/3" in batches[0].text
    assert "BEGIN-" in batches[0].text
    assert "-END" in batches[0].text
    assert batches[0].last_message_id == message.id
