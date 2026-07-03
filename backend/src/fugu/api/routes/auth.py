"""Authentication routes for issuing and revoking access tokens."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from fugu.api.dependencies import CurrentUser, IdentityManager, MasterSession
from fugu.database.models import User
from fugu.database.repositories import UserRepository
from fugu.security.auth import IdentitySecurityManager


auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])


class AuthenticationPayload(BaseModel):
    """Username and password submitted to the login endpoint."""

    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=1_024)


class AccessTokenResponse(BaseModel):
    """Short-lived bearer access token response."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class AuthenticatedUserResponse(BaseModel):
    """Non-sensitive authenticated user profile."""

    id: int
    username: str
    role: str

    @classmethod
    def from_user(cls, user: User) -> AuthenticatedUserResponse:
        return cls(id=user.id, username=user.username, role=user.role)


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Provide a valid hash so unknown-user login paths still perform password work."""
    return IdentitySecurityManager.compute_secure_hash("fugu-dummy-login-password")


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@auth_router.post("/login", response_model=AccessTokenResponse)
async def login(
    payload: AuthenticationPayload,
    response: Response,
    session: MasterSession,
    identity_manager: IdentityManager,
) -> AccessTokenResponse:
    """Verify active-user credentials and issue a scoped short-lived token."""
    normalized_username = payload.username.strip()
    user = await UserRepository.get_by_username(session, normalized_username)
    candidate_hash = user.password_hash if user is not None else _dummy_password_hash()
    password_valid = identity_manager.verify_hash_match(payload.password, candidate_hash)

    if user is None or not user.is_active or not password_valid:
        raise _invalid_credentials()

    token = identity_manager.issue_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        token_version=user.token_version,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return AccessTokenResponse(access_token=token)


@auth_router.get("/me", response_model=AuthenticatedUserResponse)
async def get_authenticated_profile(current_user: CurrentUser) -> AuthenticatedUserResponse:
    """Return the profile associated with the current valid access token."""
    return AuthenticatedUserResponse.from_user(current_user)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    current_user: CurrentUser,
    session: MasterSession,
) -> Response:
    """Revoke all currently issued access tokens for the authenticated user."""
    await UserRepository.increment_token_version(session, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
