"""Authenticated SSE endpoint for prepared pipeline execution."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from fugu.api.dependencies import CurrentUser
from fugu.execution.exceptions import (
    PipelineRunFailureError,
    PipelineValidationError,
    ThreadAccessDeniedError,
)
from fugu.execution.kernel import PipelineExecutionKernel, get_execution_kernel
from fugu.providers.parameters import validate_model_parameters

execution_router = APIRouter(prefix="/api/threads", tags=["execution"])


class PipelineExecutionPayload(BaseModel):
    """Validated user prompt and optional terminal-model override."""

    prompt: str = Field(min_length=1, max_length=100_000)
    provider_type: str | None = Field(default=None, min_length=1, max_length=50)
    model_identifier: str | None = Field(default=None, min_length=1, max_length=255)
    temperature: float | None = None
    max_output_tokens: int | None = None
    thinking_budget: int | None = None

    @model_validator(mode="after")
    def validate_model_override(self) -> PipelineExecutionPayload:
        """Validate optional model overrides and parameters against the backend catalogue."""
        has_parameters = any(
            value is not None
            for value in (
                self.temperature,
                self.max_output_tokens,
                self.thinking_budget,
            )
        )
        if self.provider_type is None and self.model_identifier is None:
            if has_parameters:
                raise ValueError(
                    "provider_type and model_identifier are required when model parameters are supplied."
                )
            return self
        if not self.provider_type or not self.model_identifier:
            raise ValueError(
                "provider_type and model_identifier must be supplied together."
            )

        provider_type = self.provider_type.strip().lower()
        model_identifier = self.model_identifier.strip()
        try:
            validate_model_parameters(
                provider_type,
                model_identifier,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                thinking_budget=self.thinking_budget,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        self.provider_type = provider_type
        self.model_identifier = model_identifier
        return self


ExecutionKernel = Annotated[
    PipelineExecutionKernel,
    Depends(get_execution_kernel),
]


def _sse(event_name: str, payload: object) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


def _pipeline_error_payload(exc: PipelineRunFailureError) -> dict[str, object]:
    origin = exc.origin
    origin_message = str(origin) if origin is not None and str(origin) else str(exc)
    origin_type = type(origin).__name__ if origin is not None else type(exc).__name__
    return {
        "event": "error",
        "run_id": exc.run_id,
        "step_name": exc.step_name,
        "error": origin_message,
        "error_type": origin_type,
        "wrapper_error": str(exc),
    }


@execution_router.post("/{thread_id}/execute")
async def execute_pipeline(
    thread_id: int,
    payload: PipelineExecutionPayload,
    current_user: CurrentUser,
    kernel: ExecutionKernel,
) -> StreamingResponse:
    """Prepare an owned pipeline run, then stream transport-neutral kernel events."""
    try:
        prepared = await kernel.prepare_execution(
            thread_id=thread_id,
            user_id=current_user.id,
            initial_prompt=payload.prompt,
            selected_provider_type=payload.provider_type,
            selected_model_identifier=payload.model_identifier,
            selected_temperature=payload.temperature,
            selected_max_output_tokens=payload.max_output_tokens,
            selected_thinking_budget=payload.thinking_budget,
        )
    except ThreadAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The authenticated user cannot execute against this thread.",
        ) from exc
    except PipelineValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in kernel.execute(prepared):
                yield _sse(event.event_type.value, event.to_payload())
        except PipelineRunFailureError as exc:
            yield _sse("error", _pipeline_error_payload(exc))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
