"""Authenticated SSE endpoint for prepared pipeline execution."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fugu.api.dependencies import CurrentUser
from fugu.execution.exceptions import (
    PipelineRunFailureError,
    PipelineValidationError,
    ThreadAccessDeniedError,
)
from fugu.execution.kernel import PipelineExecutionKernel, get_execution_kernel

execution_router = APIRouter(prefix="/api/threads", tags=["execution"])


class PipelineExecutionPayload(BaseModel):
    """Validated user prompt submitted to the pipeline engine."""

    prompt: str = Field(min_length=1, max_length=100_000)


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
