"""Private object-storage services for Fugu attachments."""

from fugu.storage.config import AttachmentStorageConfig, get_attachment_storage_config
from fugu.storage.errors import (
    AttachmentObjectNotFoundError,
    AttachmentStorageError,
    AttachmentStorageUnavailableError,
    AttachmentValidationError,
)
from fugu.storage.factory import get_object_storage
from fugu.storage.local import LocalObjectStorage
from fugu.storage.objects import ObjectStorage, StoredObjectMetadata
from fugu.storage.s3 import S3CompatibleObjectStorage

__all__ = [
    "AttachmentObjectNotFoundError",
    "AttachmentStorageConfig",
    "AttachmentStorageError",
    "AttachmentStorageUnavailableError",
    "AttachmentValidationError",
    "LocalObjectStorage",
    "ObjectStorage",
    "S3CompatibleObjectStorage",
    "StoredObjectMetadata",
    "get_attachment_storage_config",
    "get_object_storage",
]
