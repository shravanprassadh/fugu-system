"""Immutable execution plans and events shared by the kernel and HTTP layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fugu.database.models import PipelineStep


@dataclass(frozen=True, slots=True)
class PipelineStepDefinition:
    """Detached immutable representation of one configured pipeline step."""

    name: str
    sequence_order_position: int
    provider_type: str
    model_identifier: str
    system_directives: str
    prerequisites: tuple[str, ...]
    is_terminal: bool

    @classmethod
    def from_record(cls, step: PipelineStep) -> PipelineStepDefinition:
        prerequisites = step.prerequisite_dependencies
        if not isinstance(prerequisites, list) or not all(isinstance(item, str) for item in prerequisites):
            raise TypeError(f"Pipeline step {step.step_name!r} has malformed prerequisite data.")
        return cls(
            name=step.step_name,
            sequence_order_position=step.sequence_order_position,
            provider_type=step.provider_type,
            model_identifier=step.model_string,
            system_directives=step.system_prompt_directives or "",
            prerequisites=tuple(item.strip() for item in prerequisites if item.strip()),
            is_terminal=step.is_terminal,
        )


@dataclass(frozen=True, slots=True)
class PreparedPipeline:
    """Validated and persisted execution plan safe to use outside a DB session."""

    run_id: int
    thread_id: int
    user_id: int
    initial_prompt: str
    ordered_steps: tuple[PipelineStepDefinition, ...]
    step_run_ids: dict[str, int]
    terminal_step_name: str


class PipelineEventType(StrEnum):
    """Public event types emitted by the execution kernel."""

    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    TOKEN = "token"
    STEP_COMPLETED = "step_completed"
    RUN_COMPLETED = "run_completed"


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    """Transport-neutral execution event."""

    event_type: PipelineEventType
    run_id: int
    step_name: str | None = None
    token: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": self.event_type.value,
            "run_id": self.run_id,
        }
        if self.step_name is not None:
            payload["step_name"] = self.step_name
        if self.token is not None:
            payload["token"] = self.token
        return payload
