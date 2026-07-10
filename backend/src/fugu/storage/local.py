"""Filesystem-backed attachment storage for development and isolated tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from fugu.storage.errors import AttachmentObjectNotFoundError, AttachmentStorageError
from fugu.storage.objects import StoredObjectMetadata


class LocalObjectStorage:
    """Persist private attachment objects below one configured root."""

    backend_name = "local"

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def _path(self, bucket: str, key: str) -> Path:
        candidate = (self._root / bucket / key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise AttachmentStorageError("The attachment object key escaped the configured storage root.") from exc
        return candidate

    @staticmethod
    def _metadata_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.metadata.json")

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str,
        checksum_sha256: str,
    ) -> StoredObjectMetadata:
        actual_checksum = hashlib.sha256(content).hexdigest()
        if actual_checksum != checksum_sha256:
            raise AttachmentStorageError("The attachment checksum changed before storage.")
        path = self._path(bucket, key)
        metadata_path = self._metadata_path(path)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.upload")
            temporary.write_bytes(content)
            temporary.replace(path)
            metadata_path.write_text(
                json.dumps({"content_type": content_type, "checksum_sha256": checksum_sha256}),
                encoding="utf-8",
            )

        await asyncio.to_thread(write)
        return StoredObjectMetadata(
            size_bytes=len(content),
            content_type=content_type,
            etag=actual_checksum,
            checksum_sha256=actual_checksum,
        )

    async def get(self, *, bucket: str, key: str) -> bytes:
        path = self._path(bucket, key)
        if not path.is_file():
            raise AttachmentObjectNotFoundError("The attachment object is unavailable.")
        return await asyncio.to_thread(path.read_bytes)

    async def inspect(self, *, bucket: str, key: str) -> StoredObjectMetadata | None:
        path = self._path(bucket, key)
        if not path.is_file():
            return None

        def inspect_file() -> StoredObjectMetadata:
            content = path.read_bytes()
            metadata_path = self._metadata_path(path)
            metadata: dict[str, str] = {}
            if metadata_path.is_file():
                decoded = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(decoded, dict):
                    metadata = {str(name): str(value) for name, value in decoded.items()}
            checksum = hashlib.sha256(content).hexdigest()
            return StoredObjectMetadata(
                size_bytes=len(content),
                content_type=metadata.get("content_type"),
                etag=checksum,
                checksum_sha256=metadata.get("checksum_sha256", checksum),
            )

        return await asyncio.to_thread(inspect_file)

    async def delete(self, *, bucket: str, key: str) -> None:
        path = self._path(bucket, key)
        metadata_path = self._metadata_path(path)

        def remove() -> None:
            path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)

        await asyncio.to_thread(remove)
