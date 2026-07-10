"""Immutable execution plans and events shared by the kernel and HTTP layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fugu.database.models import PipelineStep, PipelineVersionStage


@dataclass(frozen=True, slots=True)
class PipelineStepDefinition:
    """Detached immutable representation of one configured pipeline stage."""

    name: str
    sequence_order_position: int
    provider_type: str
    model_identifier: str
    system_directives: str
    prerequisites: tuple[str, ...]
    is_terminal: bool
    temperature: float | None = None
    max_output_tokens: int | None = None
    thinking_budget: int | None = None
    timeout_seconds: int = 45
    retry_count: int = 0
    fallback_provider_type: str | None = None
    fallback_model_identifier: str | None = None
    display_name: str = ""
    side_effect_free: bool = True

    @classmethod
    def from_record(cls, step: PipelineStep | PipelineVersionStage) -> PipelineStepDefinition:
        prerequisites = step.prerequisite_dependencies
        if not isinstance(prerequisites, list) or not all(isinstance(item, str) for item in prerequisites):
            raise TypeError("Pipeline stage has malformed prerequisite data.")
        if isinstance(step, PipelineVersionStage):
            side_effect_free = step.input_policy.get("side_effect_free", True) is not False
            return cls(
                name=step.stable_identifier,
                display_name=step.name,
                sequence_order_position=step.position,
                provider_type=step.provider_type,
                model_identifier=step.model_string,
                system_directives=step.system_prompt_directives,
                prerequisites=tuple(item.strip() for item in prerequisites if item.strip()),
                is_terminal=step.is_terminal,
                temperature=step.temperature,
                max_output_tokens=step.token_limit,
                thinking_budget=step.thinking_budget,
                timeout_seconds=step.timeout_seconds,
                retry_count=step.retry_count,
                fallback_provider_type=step.fallback_provider_type,
                fallback_model_identifier=step.fallback_model_string,
                side_effect_free=side_effect_free,
            )
        return cls(
            name=step.step_name,
            display_name=step.step_name,
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
    pipeline_version_id: int
    pipeline_version_number: int
    thread_id: int
    user_id: int
    initial_prompt: str
    conversation_context: str
    ordered_steps: tuple[PipelineStepDefinition, ...]
    step_run_ids: dict[str, int]
    terminal_step_name: str
    seed_outputs: dict[str, str] | None = None
    source_run_id: int | None = None
    retry_kind: str | None = None
    retry_stage_name: str | None = None


class PipelineEventType(StrEnum):
    """Public event types emitted by the execution kernel."""

    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    TOKEN = "token"
    STEP_COMPLETED = "step_completed"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"


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
