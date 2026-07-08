"""Regression tests for thread-local memory injection."""

from __future__ import annotations

import pytest

from fugu.database.connection import DatabaseTarget
from fugu.database.repositories import MessageRepository
from tests.test_execution import ExecutionContext, _seed_steps, _step

pytest_plugins = ("tests.test_execution",)


@pytest.mark.asyncio
async def test_kernel_injects_bounded_thread_memory_into_provider_prompt(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(execution_context, [_step("Terminal", 1, terminal=True, model="terminal")])
    execution_context.script.tokens_by_model = {"terminal": ["Remembered answer"]}

    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="user",
            content="My project codename is Fugu.",
        )
        await MessageRepository.add(
            session,
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            role="assistant",
            content="Noted: the project codename is Fugu.",
        )

    prepared = await execution_context.kernel.prepare_execution(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        initial_prompt="What is my project codename?",
    )
    _ = [event async for event in execution_context.kernel.execute(prepared)]

    prompt = execution_context.script.requests[0].prompt_content
    assert "[Recent thread memory]" in prompt
    assert "user: My project codename is Fugu." in prompt
    assert "assistant: Noted: the project codename is Fugu." in prompt
    assert "[Current user request]\nWhat is my project codename?" in prompt
