"""Typed exceptions for authentication, authorization, and encryption."""


class SecurityError(RuntimeError):
    """Base error for all Fugu security-layer failures."""


class AuthenticationError(SecurityError):
    """Raised when user authentication cannot be completed."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when supplied credentials do not identify an active user."""


class TokenExpiredError(AuthenticationError):
    """Raised when a signed access token has expired."""


class InvalidTokenError(AuthenticationError):
    """Raised when a token is malformed, incorrectly scoped, or has an invalid signature."""


class RevokedTokenError(AuthenticationError):
    """Raised when a token version no longer matches the user's active session version."""


class AuthorizationError(SecurityError):
    """Raised when an authenticated user lacks permission for an operation."""


class CryptographicError(SecurityError):
    """Base error for provider-secret encryption and decryption failures."""


class EncryptionFailedError(CryptographicError):
    """Raised when a provider credential cannot be encrypted."""


class DecryptionFailedError(CryptographicError):
    """Raised when encrypted provider data cannot be authenticated or decrypted."""
