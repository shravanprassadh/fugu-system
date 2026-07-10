"""Vendor-neutral object-storage contract for attachment binaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObjectMetadata:
    """Sanitised object metadata used to verify persistence."""

    size_bytes: int
    content_type: str | None
    etag: str | None
    checksum_sha256: str | None = None


class ObjectStorage(Protocol):
    """Capabilities required by Fugu's controlled attachment lifecycle."""

    backend_name: str

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str,
        checksum_sha256: str,
    ) -> StoredObjectMetadata: ...

    async def get(self, *, bucket: str, key: str) -> bytes: ...

    async def inspect(self, *, bucket: str, key: str) -> StoredObjectMetadata | None: ...

    async def delete(self, *, bucket: str, key: str) -> None: ...
