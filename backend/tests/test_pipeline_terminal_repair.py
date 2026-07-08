"""Regression tests for automatic terminal-step repair before execution."""

from __future__ import annotations

import pytest

from fugu.database.connection import DatabaseTarget
from fugu.database.repositories import PipelineRepository
from tests.test_execution import ExecutionContext, _seed_steps, _step, execution_context


@pytest.mark.asyncio
async def test_kernel_repairs_multiple_terminal_steps_before_graph_validation(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [
            _step("Root", 1, terminal=True),
            _step("Final", 2, prerequisites=["Root"], terminal=True),
        ],
    )

    prepared = await execution_context.kernel.prepare_execution(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        initial_prompt="Repair terminal drift",
    )

    assert prepared.terminal_step_name == "Final"
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        steps = await PipelineRepository.list_steps(session)

    assert [(step.step_name, step.is_terminal) for step in steps] == [("Root", False), ("Final", True)]


@pytest.mark.asyncio
async def test_kernel_repairs_missing_terminal_step_before_graph_validation(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [
            _step("Root", 1),
            _step("Final", 2, prerequisites=["Root"]),
        ],
    )

    prepared = await execution_context.kernel.prepare_execution(
        thread_id=execution_context.thread_id,
        user_id=execution_context.user.id,
        initial_prompt="Repair missing terminal",
    )

    assert prepared.terminal_step_name == "Final"
    async with execution_context.registry.session(DatabaseTarget.MASTER) as session:
        steps = await PipelineRepository.list_steps(session)

    assert [(step.step_name, step.is_terminal) for step in steps] == [("Root", False), ("Final", True)]
