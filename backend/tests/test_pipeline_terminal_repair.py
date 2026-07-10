"""Regression tests for immutable published terminal-stage topology."""

from __future__ import annotations

import pytest

from fugu.execution.exceptions import TerminalStepConfigurationError
from tests.test_execution import ExecutionContext, _seed_steps, _step

pytest_plugins = ("tests.test_execution",)


@pytest.mark.asyncio
async def test_kernel_rejects_multiple_terminal_stages_without_repairing_configuration(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [
            _step("Root", 1, terminal=True),
            _step("Final", 2, prerequisites=["Root"], terminal=True),
        ],
    )

    with pytest.raises(TerminalStepConfigurationError):
        await execution_context.kernel.prepare_execution(
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            initial_prompt="Reject terminal drift",
        )


@pytest.mark.asyncio
async def test_kernel_rejects_missing_terminal_stage_without_repairing_configuration(
    execution_context: ExecutionContext,
) -> None:
    await _seed_steps(
        execution_context,
        [
            _step("Root", 1),
            _step("Final", 2, prerequisites=["Root"]),
        ],
    )

    with pytest.raises(TerminalStepConfigurationError):
        await execution_context.kernel.prepare_execution(
            thread_id=execution_context.thread_id,
            user_id=execution_context.user.id,
            initial_prompt="Reject missing terminal",
        )
