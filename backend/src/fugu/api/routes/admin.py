# fmt: off
"""Administrative API routes for Fugu operators."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.sql.schema import Table

from fugu.api.dependencies import AdminUser, IdentityManager, MasterSession
from fugu.boot.config import get_settings
from fugu.database.connection import (
    DatabaseTarget,
)
from fugu.database.models import Base, PipelineStep, ProviderCredential, Thread, User
from fugu.database.repositories import PipelineRepository, UserRepository
from fugu.database.urls import sqlalchemy_asyncpg_url
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine

admin_router = APIRouter(prefix="/api/admin", tags=["administration"])

UserRole = Literal["user", "admin"]
_MAX_USER_ACCOUNTS = 3


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


class ProviderCredentialResponse(BaseModel):
    """Non-secret provider credential metadata."""

    provider_name: str
    key_version: int
    created_at: datetime
    updated_at: datetime
    configured: bool = True

    @classmethod
    def from_credential(cls, credential: ProviderCredential) -> ProviderCredentialResponse:
        return cls(
            provider_name=credential.provider_name,
            key_version=credential.key_version,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )


class UpsertProviderCredentialPayload(BaseModel):
    """Write-only provider secret rotation payload."""

    provider_name: str = Field(min_length=2, max_length=100)
    secret: str = Field(min_length=8, max_length=8_192)


class PipelineStepResponse(BaseModel):
    """Editable pipeline step metadata."""

    id: int
    sequence_order_position: int
    step_name: str
    provider_type: str
    model_string: str
    system_prompt_directives: str | None
    prerequisite_dependencies: list[str]
    is_terminal: bool

    @classmethod
    def from_step(cls, step: PipelineStep) -> PipelineStepResponse:
        return cls(
            id=step.id,
            sequence_order_position=step.sequence_order_position,
            step_name=step.step_name,
            provider_type=step.provider_type,
            model_string=step.model_string,
            system_prompt_directives=step.system_prompt_directives,
            prerequisite_dependencies=list(step.prerequisite_dependencies),
            is_terminal=step.is_terminal,
        )


class UpdatePipelineStepPayload(BaseModel):
    """Admin-editable pipeline step fields."""

    provider_type: str | None = Field(default=None, min_length=2, max_length=100)
    model_string: str | None = Field(default=None, min_length=2, max_length=255)
    system_prompt_directives: str | None = Field(default=None, max_length=12_000)
    prerequisite_dependencies: list[str] | None = None
    is_terminal: bool | None = None


class DatabaseConnectionPayload(BaseModel):
    """Write-only database URLs used by the transfer workflow."""

    master_router_db_url: str = Field(min_length=20, max_length=4_096)
    metadata_sidebar_db_url: str = Field(min_length=20, max_length=4_096)
    transactional_logs_db_url: str = Field(min_length=20, max_length=4_096)


class DatabaseTransferPayload(DatabaseConnectionPayload):
    """Guarded database transfer request."""

    confirmation: str
    replace_existing: bool = False
    apply_to_current_process: bool = True


class DatabaseTargetStatus(BaseModel):
    """Sanitized database target status."""

    target: str
    masked_url: str
    status: Literal["connected", "failed", "copied", "active"]
    row_count: int | None = None
    error: str | None = None


class DatabaseTransferResponse(BaseModel):
    """Result of a database connection test or guarded transfer."""

    status: Literal["ready", "transferred"]
    targets: list[DatabaseTargetStatus]
    active_until_restart: bool = False
    render_env_update_required: bool = False
    note: str


async def _get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await UserRepository.get_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


async def _user_count(session: AsyncSession) -> int:
    result = await session.scalar(select(func.count()).select_from(User))
    return int(result or 0)


async def _active_admin_count(session: AsyncSession) -> int:
    statement = (
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", User.is_active.is_(True))
    )
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


def _database_url_map(payload: DatabaseConnectionPayload) -> dict[DatabaseTarget, str]:
    return {
        DatabaseTarget.MASTER: payload.master_router_db_url,
        DatabaseTarget.METADATA: payload.metadata_sidebar_db_url,
        DatabaseTarget.LOGS: payload.transactional_logs_db_url,
    }


def _masked_database_url(url: str) -> str:
    parsed = urlsplit(url)
    username = "****" if parsed.username else ""
    password = ":********" if parsed.password else ""
    credentials = f"{username}{password}@" if username or password else ""
    host = parsed.hostname or "unknown-host"
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{credentials}{host}{port}{database}{query}"


def _temporary_engine(url: str) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        sqlalchemy_asyncpg_url(url),
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        pool_timeout=settings.network_request_timeout,
    )


async def _dispose_engines(engines: dict[DatabaseTarget, AsyncEngine]) -> None:
    for engine in engines.values():
        await engine.dispose()


async def _test_target_url(target: DatabaseTarget, url: str) -> DatabaseTargetStatus:
    engine = _temporary_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return DatabaseTargetStatus(
            target=target.value,
            masked_url=_masked_database_url(url),
            status="connected",
        )
    except SQLAlchemyError as exc:
        return DatabaseTargetStatus(
            target=target.value,
            masked_url=_masked_database_url(url),
            status="failed",
            error=str(exc),
        )
    finally:
        await engine.dispose()


async def _test_target_urls(urls: dict[DatabaseTarget, str]) -> list[DatabaseTargetStatus]:
    return [await _test_target_url(target, url) for target, url in urls.items()]


async def _source_database_has_rows(source_engine: AsyncEngine) -> bool:
    async with source_engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            result = await connection.execute(select(func.count()).select_from(table))
            if int(result.scalar_one() or 0) > 0:
                return True
    return False


async def _copy_table_rows(
    *,
    source_engine: AsyncEngine,
    destination_engine: AsyncEngine,
    table: Table,
    replace_existing: bool,
) -> int:
    copied_rows = 0
    async with destination_engine.begin() as destination_connection:
        if replace_existing:
            await destination_connection.execute(table.delete())
        async with source_engine.connect() as source_connection:
            async with source_connection.begin():
                result = await source_connection.execute(select(table))
                rows = [dict(row) for row in result.mappings().all()]
            if rows:
                await destination_connection.execute(table.insert(), rows)
                copied_rows += len(rows)
    return copied_rows


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
        AdminUserResponse.from_user(user, thread_count=int(thread_count or 0))
        for user, thread_count in result.all()
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
    if await _user_count(session) >= _MAX_USER_ACCOUNTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fugu is limited to {_MAX_USER_ACCOUNTS} user accounts.",
        )
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


@admin_router.get("/provider-credentials", response_model=list[ProviderCredentialResponse])
async def list_provider_credentials(
    _: AdminUser,
    session: MasterSession,
) -> list[ProviderCredentialResponse]:
    """List configured provider credentials without returning plaintext secrets."""
    statement = select(ProviderCredential).order_by(ProviderCredential.provider_name.asc())
    result = await session.scalars(statement)
    return [ProviderCredentialResponse.from_credential(credential) for credential in result.all()]


@admin_router.post("/provider-credentials", response_model=ProviderCredentialResponse)
async def upsert_provider_credential(
    payload: UpsertProviderCredentialPayload,
    _: AdminUser,
    session: MasterSession,
) -> ProviderCredentialResponse:
    """Create or rotate a provider API key from the admin console."""
    vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    credential = await vault.store(
        session,
        provider_name=payload.provider_name,
        plaintext_secret=payload.secret,
    )
    return ProviderCredentialResponse.from_credential(credential)


@admin_router.get("/pipeline-steps", response_model=list[PipelineStepResponse])
async def list_pipeline_steps(
    _: AdminUser,
    session: MasterSession,
) -> list[PipelineStepResponse]:
    """Return pipeline steps in execution order."""
    steps = await PipelineRepository.list_steps(session)
    return [PipelineStepResponse.from_step(step) for step in steps]
