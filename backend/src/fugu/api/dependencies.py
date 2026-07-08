"""FastAPI dependencies for authenticated users, roles, and owned threads."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import Thread, User
from fugu.database.repositories import ThreadRepository, UserRepository
from fugu.security.auth import IdentitySecurityManager
from fugu.security.exceptions import InvalidTokenError, TokenExpiredError

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_identity_security_manager() -> IdentitySecurityManager:
    """Create the configured identity manager lazily."""
    return IdentitySecurityManager.from_settings()


async def get_master_session(
    registry: Annotated[DatabaseSessionRegistry, Depends(get_session_registry)],
) -> AsyncIterator[AsyncSession]:
    """Provide one request-scoped transactional master-database session."""
    async with registry.session(DatabaseTarget.MASTER) as session:
        yield session


MasterSession = Annotated[AsyncSession, Depends(get_master_session)]
IdentityManager = Annotated[IdentitySecurityManager, Depends(get_identity_security_manager)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: BearerCredentials,
    session: MasterSession,
    identity_manager: IdentityManager,
) -> User:
    """Resolve a signed, current, active user identity from the bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("A valid bearer token is required.")

    try:
        claims = identity_manager.decode_access_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise _unauthorized("The access token has expired.") from exc
    except InvalidTokenError as exc:
        raise _unauthorized("The access token is invalid or incorrectly scoped.") from exc

    user = await UserRepository.get_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        raise _unauthorized("The authenticated user is unavailable.")
    if claims.ver != user.token_version:
        raise _unauthorized("The access token has been revoked.")
    if claims.username != user.username or claims.role != user.role:
        raise _unauthorized("The access token no longer matches the user identity.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed_roles: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Create a dependency that restricts access to the supplied roles."""
    allowed = frozenset(allowed_roles)
    if not allowed:
        raise ValueError("At least one authorized role is required.")

    async def role_dependency(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The authenticated user lacks the required role.",
            )
        return current_user

    return role_dependency


AdminUser = Annotated[User, Depends(require_roles("admin"))]


async def require_owned_thread(
    thread_id: int,
    current_user: CurrentUser,
    session: MasterSession,
) -> Thread:
    """Resolve a thread only when it belongs to the authenticated user."""
    try:
        return await ThreadRepository.require_owned(
            session,
            thread_id=thread_id,
            user_id=current_user.id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found.",
        ) from exc


OwnedThread = Annotated[Thread, Depends(require_owned_thread)]
