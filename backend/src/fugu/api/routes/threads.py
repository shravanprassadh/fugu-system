"""Authenticated CRUD routes for user-owned conversation threads."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from fugu.api.dependencies import CurrentUser, MasterSession, OwnedThread
from fugu.database.models import Message, Thread, ThreadMemory
from fugu.database.repositories import MessageRepository, ThreadMemoryRepository, ThreadRepository

threads_router = APIRouter(prefix="/api/threads", tags=["threads"])

MAX_THREAD_NAME_LENGTH = 255


class ThreadNamePayload(BaseModel):
    """Client-supplied thread display name used for creation and renaming."""

    name: str = Field(min_length=1, max_length=MAX_THREAD_NAME_LENGTH)


class ThreadResponse(BaseModel):
    """Non-sensitive thread summary returned to the owning user."""

    id: int
    name: str
    created_at: datetime

    @classmethod
    def from_thread(cls, thread: Thread) -> ThreadResponse:
        return cls(id=thread.id, name=thread.name, created_at=thread.created_at)


class MessageResponse(BaseModel):
    """Immutable message record scoped through thread ownership."""

    id: int
    role: str
    content: str
    created_at: datetime

    @classmethod
    def from_message(cls, message: Message) -> MessageResponse:
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class ThreadMemoryResponse(BaseModel):
    """Current stored markdown memory for one owned thread."""

    thread_id: int
    has_memory: bool
    status: str
    summary_md: str
    key_facts_md: str
    open_tasks_md: str
    last_summarized_message_id: int | None
    summarizer_provider: str | None
    summarizer_model: str | None
    error_message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_memory(cls, *, thread_id: int, memory: ThreadMemory | None) -> ThreadMemoryResponse:
        if memory is None:
            return cls(
                thread_id=thread_id,
                has_memory=False,
                status="not created",
                summary_md="",
                key_facts_md="",
                open_tasks_md="",
                last_summarized_message_id=None,
                summarizer_provider=None,
                summarizer_model=None,
                error_message=None,
                created_at=None,
                updated_at=None,
            )
        return cls(
            thread_id=memory.thread_id,
            has_memory=True,
            status=memory.status,
            summary_md=memory.summary_md,
            key_facts_md=memory.key_facts_md,
            open_tasks_md=memory.open_tasks_md,
            last_summarized_message_id=memory.last_summarized_message_id,
            summarizer_provider=memory.summarizer_provider,
            summarizer_model=memory.summarizer_model,
            error_message=memory.error_message,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )


def _normalized_thread_name(raw_name: str) -> str:
    """Collapse surrounding whitespace and reject names that become empty."""
    normalized = raw_name.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The thread name cannot be empty.",
        )
    return normalized[:MAX_THREAD_NAME_LENGTH]


@threads_router.get("", response_model=list[ThreadResponse])
async def list_threads(
    current_user: CurrentUser,
    session: MasterSession,
) -> list[ThreadResponse]:
    """Return the authenticated user's threads, most recent first."""
    threads = await ThreadRepository.list_owned(session, user_id=current_user.id)
    return [ThreadResponse.from_thread(thread) for thread in threads]


@threads_router.post("", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadNamePayload,
    current_user: CurrentUser,
    session: MasterSession,
) -> ThreadResponse:
    """Create a new empty thread owned by the authenticated user."""
    thread = await ThreadRepository.add(
        session,
        user_id=current_user.id,
        name=_normalized_thread_name(payload.name),
    )
    return ThreadResponse.from_thread(thread)


@threads_router.get("/{thread_id}/messages", response_model=list[MessageResponse])
async def list_thread_messages(
    thread: OwnedThread,
    session: MasterSession,
) -> list[MessageResponse]:
    """Return the full message history of one owned thread, oldest first."""
    messages = await MessageRepository.list_for_thread(
        session,
        thread_id=thread.id,
        user_id=thread.user_id,
    )
    return [MessageResponse.from_message(message) for message in messages]


@threads_router.get("/{thread_id}/memory", response_model=ThreadMemoryResponse)
async def get_thread_memory(
    thread: OwnedThread,
    session: MasterSession,
) -> ThreadMemoryResponse:
    """Return the stored rolling memory for one owned thread without raw secrets."""
    memory = await ThreadMemoryRepository.get_for_thread(
        session,
        thread_id=thread.id,
        user_id=thread.user_id,
    )
    return ThreadMemoryResponse.from_memory(thread_id=thread.id, memory=memory)


@threads_router.patch("/{thread_id}", response_model=ThreadResponse)
async def rename_thread(
    payload: ThreadNamePayload,
    thread: OwnedThread,
    session: MasterSession,
) -> ThreadResponse:
    """Rename one owned thread."""
    renamed = await ThreadRepository.rename(
        session,
        thread=thread,
        name=_normalized_thread_name(payload.name),
    )
    return ThreadResponse.from_thread(renamed)


@threads_router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_thread(
    thread: OwnedThread,
    session: MasterSession,
) -> Response:
    """Delete one owned thread together with its messages and run history."""
    await ThreadRepository.delete(session, thread=thread)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
