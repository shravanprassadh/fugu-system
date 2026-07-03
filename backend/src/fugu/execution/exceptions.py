"""Typed failures for DAG validation and pipeline execution."""

from __future__ import annotations

from fugu.providers.exceptions import ProviderError


class PipelineEngineException(RuntimeError):
    """Base exception for all graph orchestration failures."""


class ThreadAccessDeniedError(PipelineEngineException):
    """Raised when a user attempts to execute against an unowned thread."""


class PipelineValidationError(PipelineEngineException):
    """Base exception for invalid pipeline definitions."""


class EmptyPipelineError(PipelineValidationError):
    """Raised when no pipeline steps are configured."""


class DuplicateStepNameError(PipelineValidationError):
    """Raised when multiple steps use the same identifier."""


class DuplicateSequencePositionError(PipelineValidationError):
    """Raised when multiple steps use the same ordering position."""


class PrerequisiteNotFoundError(PipelineValidationError):
    """Raised when a step depends on an unknown prerequisite."""


class DependencyLoopError(PipelineValidationError):
    """Raised when the pipeline contains a directed cycle."""


class TerminalStepConfigurationError(PipelineValidationError):
    """Raised when the terminal output step is missing, duplicated, or not a sink."""


class ProviderCredentialMissingError(PipelineEngineException):
    """Raised when an execution step has no configured encrypted credential."""


class PipelineRunFailureError(PipelineEngineException):
    """Raised after a failed run and step trace have been persisted."""

    def __init__(
        self,
        message: str,
        *,
        run_id: int,
        step_name: str | None,
        origin: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.step_name = step_name
        self.origin = origin

    @property
    def provider_origin(self) -> ProviderError | None:
        """Return the typed provider origin when the failure came from a provider."""
        return self.origin if isinstance(self.origin, ProviderError) else None
