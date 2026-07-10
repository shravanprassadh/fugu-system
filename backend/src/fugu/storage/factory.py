"""Attachment object-storage construction."""

from __future__ import annotations

from functools import lru_cache

from fugu.storage.config import AttachmentStorageConfig, get_attachment_storage_config
from fugu.storage.errors import AttachmentStorageUnavailableError
from fugu.storage.local import LocalObjectStorage
from fugu.storage.objects import ObjectStorage
from fugu.storage.s3 import S3CompatibleObjectStorage


@lru_cache(maxsize=1)
def get_object_storage() -> ObjectStorage:
    """Return the configured private object store or fail without affecting core startup."""
    config: AttachmentStorageConfig = get_attachment_storage_config()
    if config.backend == "local":
        return LocalObjectStorage(config.local_root)
    if config.backend == "s3-compatible":
        return S3CompatibleObjectStorage(config)
    raise AttachmentStorageUnavailableError(
        "Attachment storage is disabled. Configure ATTACHMENT_STORAGE_BACKEND before uploading files."
    )
