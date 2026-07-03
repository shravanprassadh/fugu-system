"""Password hashing and signed access-token management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fugu.boot.config import InfrastructureConfig, get_settings
from fugu.security.exceptions import InvalidTokenError, TokenExpiredError
from jwt.exceptions import ExpiredSignatureError
from jwt.exceptions import InvalidTokenError as PyJWTInvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

JWT_ALGORITHM = "HS256"
REQUIRED_TOKEN_CLAIMS = (
    "sub",
    "username",
    "role",
    "ver",
    "jti",
    "iat",
    "nbf",
    "exp",
    "iss",
    "aud",
)
_PASSWORD_HASH = PasswordHash.recommended()


class AccessTokenClaims(BaseModel):
    """Validated identity and authorization claims carried by an access token."""

    sub: str
    username: str = Field(min_length=1, max_length=255)
    role: str = Field(pattern="^(user|admin)$")
    ver: int = Field(ge=0)
    jti: str = Field(min_length=1)
    iat: int
    nbf: int
    exp: int
    iss: str
    aud: str

    model_config = ConfigDict(extra="forbid")

    @property
    def user_id(self) -> int:
        """Return the integer user identifier encoded in the subject claim."""
        try:
            user_id = int(self.sub)
        except ValueError as exc:
            raise InvalidTokenError("The token subject is not a valid user identifier.") from exc
        if user_id < 1:
            raise InvalidTokenError("The token subject is not a valid user identifier.")
        return user_id


class IdentitySecurityManager:
    """Hash passwords and issue or validate scoped short-lived JWT access tokens."""

    def __init__(
        self,
        *,
        signing_secret: str,
        issuer: str,
        audience: str,
        access_token_ttl: timedelta,
    ) -> None:
        if len(signing_secret.strip()) < 32:
            raise ValueError("JWT signing secrets must contain at least 32 characters.")
        if access_token_ttl <= timedelta(0):
            raise ValueError("Access-token lifetimes must be positive.")
        self._signing_secret = signing_secret
        self._issuer = issuer
        self._audience = audience
        self._access_token_ttl = access_token_ttl

    @classmethod
    def from_settings(
        cls,
        settings: InfrastructureConfig | None = None,
    ) -> IdentitySecurityManager:
        """Construct an identity manager from validated runtime configuration."""
        resolved_settings = settings or get_settings()
        return cls(
            signing_secret=resolved_settings.system_session_secret.get_secret_value(),
            issuer=resolved_settings.jwt_issuer,
            audience=resolved_settings.jwt_audience,
            access_token_ttl=timedelta(minutes=resolved_settings.access_token_ttl_minutes),
        )

    @staticmethod
    def compute_secure_hash(plain_password: str) -> str:
        """Hash a non-empty password using the recommended Argon2 parameters."""
        if not plain_password or not plain_password.strip():
            raise ValueError("Passwords cannot be empty.")
        return _PASSWORD_HASH.hash(plain_password)

    @staticmethod
    def verify_hash_match(plain_password: str, hashed_value: str) -> bool:
        """Verify a password without exposing comparison timing or hash details."""
        if not plain_password or not hashed_value:
            return False
        try:
            return _PASSWORD_HASH.verify(plain_password, hashed_value)
        except UnknownHashError:
            return False

    def issue_access_token(
        self,
        *,
        user_id: int,
        username: str,
        role: str,
        token_version: int,
        expires_delta: timedelta | None = None,
        issued_at: datetime | None = None,
    ) -> str:
        """Issue a signed access token with explicit scope and revocation claims."""
        if user_id < 1:
            raise ValueError("User identifiers must be positive integers.")
        now = issued_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Token timestamps must be timezone-aware.")
        expiration = now + (expires_delta or self._access_token_ttl)
        payload: dict[str, object] = {
            "sub": str(user_id),
            "username": username,
            "role": role,
            "ver": token_version,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": expiration,
            "iss": self._issuer,
            "aud": self._audience,
        }
        return jwt.encode(
            payload,
            self._signing_secret,
            algorithm=JWT_ALGORITHM,
        )

    def decode_access_token(self, encoded_token: str) -> AccessTokenClaims:
        """Verify signature, expiry, issuer, audience, and required claim structure."""
        if not encoded_token or not encoded_token.strip():
            raise InvalidTokenError("An access token is required.")
        try:
            raw_payload = jwt.decode(
                encoded_token,
                self._signing_secret,
                algorithms=[JWT_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": list(REQUIRED_TOKEN_CLAIMS),
                    "strict_aud": True,
                },
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("The access token has expired.") from exc
        except PyJWTInvalidTokenError as exc:
            raise InvalidTokenError("The access token is invalid or incorrectly scoped.") from exc

        try:
            claims = AccessTokenClaims.model_validate(raw_payload)
            _ = claims.user_id
            return claims
        except ValidationError as exc:
            raise InvalidTokenError("The access token claims are malformed.") from exc
