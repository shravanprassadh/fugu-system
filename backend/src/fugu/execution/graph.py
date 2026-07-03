"""Deterministic DAG validation and topological ordering."""

from __future__ import annotations

import heapq
from collections.abc import Sequence

from fugu.database.models import PipelineStep
from fugu.execution.exceptions import (
    DependencyLoopError,
    DuplicateSequencePositionError,
    DuplicateStepNameError,
    EmptyPipelineError,
    PipelineValidationError,
    PrerequisiteNotFoundError,
    TerminalStepConfigurationError,
)
from fugu.execution.models import PipelineStepDefinition


class PipelineDependencyGraphResolver:
    """Validate pipeline structure and resolve a deterministic execution order."""

    def __init__(self, raw_steps: Sequence[PipelineStep]) -> None:
        if not raw_steps:
            raise EmptyPipelineError("At least one pipeline step must be configured.")

        definitions: list[PipelineStepDefinition] = []
        try:
            definitions = [PipelineStepDefinition.from_record(step) for step in raw_steps]
        except (TypeError, ValueError) as exc:
            raise PipelineValidationError(str(exc)) from exc

        names = [step.name for step in definitions]
        if len(names) != len(set(names)):
            raise DuplicateStepNameError("Pipeline step names must be unique.")

        positions = [step.sequence_order_position for step in definitions]
        if len(positions) != len(set(positions)):
            raise DuplicateSequencePositionError("Pipeline sequence positions must be unique.")

        self.steps: dict[str, PipelineStepDefinition] = {step.name: step for step in definitions}
        self.adjacency_list: dict[str, set[str]] = {step.name: set() for step in definitions}
        self.in_degree: dict[str, int] = {step.name: 0 for step in definitions}
        self._build_graph()
        self._resolved_sequence = self._resolve_topological_sequence()
        self.terminal_step_name = self._validate_terminal_step()

    def _build_graph(self) -> None:
        for step in self.steps.values():
            seen_dependencies: set[str] = set()
            for prerequisite in step.prerequisites:
                if prerequisite == step.name:
                    raise DependencyLoopError(f"Pipeline step {step.name!r} cannot depend on itself.")
                if prerequisite not in self.steps:
                    raise PrerequisiteNotFoundError(
                        f"Pipeline step {step.name!r} depends on unknown prerequisite " f"{prerequisite!r}."
                    )
                if prerequisite in seen_dependencies:
                    continue
                seen_dependencies.add(prerequisite)
                self.adjacency_list[prerequisite].add(step.name)
                self.in_degree[step.name] += 1

    def _resolve_topological_sequence(self) -> tuple[str, ...]:
        remaining_in_degree = dict(self.in_degree)
        ready: list[tuple[int, str]] = [
            (self.steps[name].sequence_order_position, name)
            for name, degree in remaining_in_degree.items()
            if degree == 0
        ]
        heapq.heapify(ready)
        ordered_names: list[str] = []

        while ready:
            _, current = heapq.heappop(ready)
            ordered_names.append(current)
            neighbors = sorted(
                self.adjacency_list[current],
                key=lambda name: (
                    self.steps[name].sequence_order_position,
                    name,
                ),
            )
            for neighbor in neighbors:
                remaining_in_degree[neighbor] -= 1
                if remaining_in_degree[neighbor] == 0:
                    heapq.heappush(
                        ready,
                        (
                            self.steps[neighbor].sequence_order_position,
                            neighbor,
                        ),
                    )

        if len(ordered_names) != len(self.steps):
            raise DependencyLoopError("The pipeline contains a directed dependency cycle.")
        return tuple(ordered_names)

    def _validate_terminal_step(self) -> str:
        terminal_steps = [step for step in self.steps.values() if step.is_terminal]
        if len(terminal_steps) != 1:
            raise TerminalStepConfigurationError("Exactly one pipeline step must be marked as terminal.")
        terminal_step = terminal_steps[0]
        if self.adjacency_list[terminal_step.name]:
            raise TerminalStepConfigurationError(f"Terminal step {terminal_step.name!r} must not have dependent steps.")
        return terminal_step.name

    def resolve_safe_execution_sequence(self) -> list[str]:
        """Return the validated Kahn ordering with deterministic tie-breakers."""
        return list(self._resolved_sequence)

    def resolve_ordered_steps(self) -> tuple[PipelineStepDefinition, ...]:
        """Return detached step definitions in deterministic execution order."""
        return tuple(self.steps[name] for name in self._resolved_sequence)
