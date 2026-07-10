"""Private S3-compatible attachment object storage."""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from fugu.storage.config import AttachmentStorageConfig
from fugu.storage.errors import AttachmentObjectNotFoundError, AttachmentStorageError
from fugu.storage.objects import StoredObjectMetadata


class S3CompatibleObjectStorage:
    """Use an S3-compatible private bucket through controlled backend operations."""

    backend_name = "s3-compatible"

    def __init__(self, config: AttachmentStorageConfig) -> None:
        if config.s3_access_key_id is None or config.s3_secret_access_key is None:
            raise AttachmentStorageError("S3-compatible attachment credentials are unavailable.")
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=config.s3_endpoint_url,
            region_name=config.s3_region,
            aws_access_key_id=config.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=config.s3_secret_access_key.get_secret_value(),
        )

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str,
        checksum_sha256: str,
    ) -> StoredObjectMetadata:
        try:
            response = await asyncio.to_thread(
                self._client.put_object,
                Bucket=bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata={"sha256": checksum_sha256},
            )
        except (BotoCoreError, ClientError) as exc:
            raise AttachmentStorageError("The attachment object could not be stored.") from exc
        return StoredObjectMetadata(
            size_bytes=len(content),
            content_type=content_type,
            etag=str(response.get("ETag", "")).strip('"') or None,
            checksum_sha256=checksum_sha256,
        )

    async def get(self, *, bucket: str, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(self._client.get_object, Bucket=bucket, Key=key)
            return await asyncio.to_thread(response["Body"].read)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise AttachmentObjectNotFoundError("The attachment object is unavailable.") from exc
            raise AttachmentStorageError("The attachment object could not be retrieved.") from exc
        except BotoCoreError as exc:
            raise AttachmentStorageError("The attachment object could not be retrieved.") from exc

    async def inspect(self, *, bucket: str, key: str) -> StoredObjectMetadata | None:
        try:
            response = await asyncio.to_thread(self._client.head_object, Bucket=bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "NotFound", "404"}:
                return None
            raise AttachmentStorageError("The attachment object could not be inspected.") from exc
        except BotoCoreError as exc:
            raise AttachmentStorageError("The attachment object could not be inspected.") from exc
        metadata = response.get("Metadata") if isinstance(response.get("Metadata"), dict) else {}
        return StoredObjectMetadata(
            size_bytes=int(response.get("ContentLength", 0)),
            content_type=str(response.get("ContentType")) if response.get("ContentType") else None,
            etag=str(response.get("ETag", "")).strip('"') or None,
            checksum_sha256=str(metadata.get("sha256")) if metadata.get("sha256") else None,
        )

    async def delete(self, *, bucket: str, key: str) -> None:
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise AttachmentStorageError("The attachment object could not be deleted.") from exc
