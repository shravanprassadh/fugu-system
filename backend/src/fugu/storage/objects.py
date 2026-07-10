"""Vendor-neutral object-storage contract for attachment binaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PresignedOperation:
    """A time-limited object-store operation returned to an authenticated client."""

    url: str
    method: str
    expires_at: datetime
    required_headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class StoredObjectMetadata:
    """Sanitised object metadata used to verify upload completion."""

    size_bytes: int
    content_type: str | None
    etag: str | None


class ObjectStorage(Protocol):
    """Minimal capabilities required by Fugu's attachment lifecycle."""

    async def create_upload(
        self,
        *,
        bucket: str,
        key: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
    ) -> PresignedOperation: ...

    async def create_download(self, *, bucket: str, key: str, filename: str) -> PresignedOperation: ...

    async def inspect(self, *, bucket: str, key: str) -> StoredObjectMetadata | None: ...

    async def delete(self, *, bucket: str, key: str) -> None: ...
