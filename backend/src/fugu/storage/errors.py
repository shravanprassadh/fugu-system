"""Typed failures for attachment storage and validation."""


class AttachmentStorageError(RuntimeError):
    """Base class for storage operations that cannot be completed safely."""


class AttachmentStorageUnavailableError(AttachmentStorageError):
    """Raised when attachment storage is disabled or incorrectly configured."""


class AttachmentObjectNotFoundError(AttachmentStorageError):
    """Raised when metadata references an object that no longer exists."""


class AttachmentValidationError(ValueError):
    """Raised when a client-supplied file violates the upload contract."""
