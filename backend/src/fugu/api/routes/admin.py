"""Administrative API routes for Fugu operators."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.api.dependencies import AdminUser, IdentityManager, MasterSession
from fugu.database.models import Thread, User
from fugu.database.repositories import UserRepository

admin_router = APIRouter(prefix="/api/admin", tags=["administration"])

UserRole = Literal["user", "admin"]


class AdminUserResponse(BaseModel):
    """Sanitized user record for the administrative console."""

    id: int
    username: str
    role: UserRole
    is_active: bool
    token_version: int
    created_at: datetime
    thread_count: int

    @classmethod
    def from_user(cls, user: User, *, thread_count: int = 0) -> AdminUserResponse:
        return cls(
            id=user.id,
            username=user.username,
            role=cast(UserRole, user.role),
            is_active=user.is_active,
            token_version=user.token_version,
            created_at=user.created_at,
            thread_count=thread_count,
        )


class CreateUserPayload(BaseModel):
    """Admin-created user account."""

    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=1_024)
    role: UserRole = "user"
    is_active: bool = True


class UpdateUserPayload(BaseModel):
    """Editable non-secret user account fields."""

    role: UserRole | None = None
    is_active: bool | None = None


class ResetPasswordPayload(BaseModel):
    """Password reset payload submitted by an administrator."""

    password: str = Field(min_length=8, max_length=1_024)


async def _get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await UserRepository.get_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


async def _active_admin_count(session: AsyncSession) -> int:
    statement = select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
    result = await session.scalar(statement)
    return int(result or 0)


async def _thread_count(session: AsyncSession, user_id: int) -> int:
    statement = select(func.count()).select_from(Thread).where(Thread.user_id == user_id)
    result = await session.scalar(statement)
    return int(result or 0)


async def _prevent_last_admin_loss(
    session: AsyncSession,
    *,
    target_user: User,
    next_role: str | None = None,
    next_is_active: bool | None = None,
) -> None:
    current_is_active_admin = target_user.role == "admin" and target_user.is_active
    would_remain_admin = next_role in (None, "admin")
    would_remain_active = target_user.is_active if next_is_active is None else next_is_active
    if not current_is_active_admin or (would_remain_admin and would_remain_active):
        return
    if await _active_admin_count(session) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one active administrator must remain.",
        )


@admin_router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _: AdminUser,
    session: MasterSession,
) -> list[AdminUserResponse]:
    """List all users with non-sensitive account metadata."""
    statement = (
        select(User, func.count(Thread.id).label("thread_count"))
        .outerjoin(Thread, Thread.user_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc(), User.id.desc())
    )
    result = await session.execute(statement)
    return [
        AdminUserResponse.from_user(user, thread_count=int(thread_count or 0)) for user, thread_count in result.all()
    ]


@admin_router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserPayload,
    _: AdminUser,
    session: MasterSession,
    identity_manager: IdentityManager,
) -> AdminUserResponse:
    """Create a user without using Neon directly."""
    normalized_username = payload.username.strip()
    if await UserRepository.get_by_username(session, normalized_username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.")
    user = await UserRepository.add(
        session,
        username=normalized_username,
        password_hash=identity_manager.compute_secure_hash(payload.password),
        role=payload.role,
    )
    user.is_active = payload.is_active
    await session.flush()
    return AdminUserResponse.from_user(user)


@admin_router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    payload: UpdateUserPayload,
    current_admin: AdminUser,
    session: MasterSession,
) -> AdminUserResponse:
    """Update a user's role or active state from the admin console."""
    if payload.role is None and payload.is_active is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user changes were supplied.",
        )
    target_user = await _get_user_or_404(session, user_id)
    if target_user.id == current_admin.id and (payload.role == "user" or payload.is_active is False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable or demote your own admin account.",
        )
    await _prevent_last_admin_loss(
        session,
        target_user=target_user,
        next_role=payload.role,
        next_is_active=payload.is_active,
    )
    if payload.role is not None:
        target_user.role = payload.role
    if payload.is_active is not None:
        target_user.is_active = payload.is_active
    target_user.token_version += 1
    await session.flush()
    return AdminUserResponse.from_user(target_user, thread_count=await _thread_count(session, target_user.id))


@admin_router.post(
    "/users/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordPayload,
    _: AdminUser,
    session: MasterSession,
    identity_manager: IdentityManager,
) -> Response:
    """Reset a user's password and revoke existing tokens."""
    target_user = await _get_user_or_404(session, user_id)
    target_user.password_hash = identity_manager.compute_secure_hash(payload.password)
    target_user.token_version += 1
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_user(
    user_id: int,
    current_admin: AdminUser,
    session: MasterSession,
) -> Response:
    """Delete a user and cascade their owned workspace records."""
    target_user = await _get_user_or_404(session, user_id)
    if target_user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own admin account.",
        )
    await _prevent_last_admin_loss(session, target_user=target_user, next_is_active=False)
    await session.delete(target_user)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
