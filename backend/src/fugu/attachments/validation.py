"""Strict filename, MIME, size, and content validation for attachments."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from fugu.storage.errors import AttachmentValidationError

_BINARY_MIME_BY_EXTENSION: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "png": frozenset({"image/png"}),
    "jpg": frozenset({"image/jpeg"}),
    "jpeg": frozenset({"image/jpeg"}),
    "webp": frozenset({"image/webp"}),
    "xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    "docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
}
_TEXT_MIME_BY_EXTENSION: dict[str, frozenset[str]] = {
    "txt": frozenset({"text/plain"}),
    "md": frozenset({"text/markdown", "text/plain", "text/x-markdown"}),
    "csv": frozenset({"text/csv", "application/csv", "text/plain"}),
    "py": frozenset({"text/plain", "text/x-python", "application/x-python-code"}),
    "js": frozenset({"text/plain", "text/javascript", "application/javascript"}),
    "jsx": frozenset({"text/plain", "text/javascript", "application/javascript"}),
    "ts": frozenset({"text/plain", "text/typescript", "application/typescript"}),
    "tsx": frozenset({"text/plain", "text/typescript", "application/typescript"}),
    "java": frozenset({"text/plain", "text/x-java-source"}),
    "c": frozenset({"text/plain", "text/x-c"}),
    "h": frozenset({"text/plain", "text/x-c"}),
    "cpp": frozenset({"text/plain", "text/x-c++src"}),
    "hpp": frozenset({"text/plain", "text/x-c++hdr"}),
    "cs": frozenset({"text/plain", "text/x-csharp"}),
    "go": frozenset({"text/plain", "text/x-go"}),
    "rs": frozenset({"text/plain", "text/x-rust"}),
    "rb": frozenset({"text/plain", "application/x-ruby"}),
    "php": frozenset({"text/plain", "application/x-httpd-php"}),
    "swift": frozenset({"text/plain", "text/x-swift"}),
    "kt": frozenset({"text/plain", "text/x-kotlin"}),
    "kts": frozenset({"text/plain", "text/x-kotlin"}),
    "sql": frozenset({"text/plain", "application/sql"}),
    "sh": frozenset({"text/plain", "application/x-sh", "text/x-shellscript"}),
    "bash": frozenset({"text/plain", "application/x-sh", "text/x-shellscript"}),
    "json": frozenset({"application/json", "text/json", "text/plain"}),
    "yaml": frozenset({"application/yaml", "text/yaml", "text/plain"}),
    "yml": frozenset({"application/yaml", "text/yaml", "text/plain"}),
    "xml": frozenset({"application/xml", "text/xml", "text/plain"}),
    "html": frozenset({"text/html", "text/plain"}),
    "css": frozenset({"text/css", "text/plain"}),
}
_ALLOWED_MIME_BY_EXTENSION = {**_BINARY_MIME_BY_EXTENSION, **_TEXT_MIME_BY_EXTENSION}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ValidatedAttachment:
    """Normalised attachment details safe for persistence and object storage."""

    filename: str
    extension: str
    mime_type: str
    size_bytes: int
    sha256_hex: str


def supported_extensions() -> tuple[str, ...]:
    """Return the explicit first-release attachment extension allowlist."""
    return tuple(sorted(_ALLOWED_MIME_BY_EXTENSION))


def _normalise_filename(filename: str) -> tuple[str, str]:
    cleaned = _CONTROL_CHARACTERS.sub("", Path(filename or "").name).strip()
    if not cleaned or cleaned in {".", ".."}:
        raise AttachmentValidationError("The attachment filename is invalid.")
    if len(cleaned) > 255:
        raise AttachmentValidationError("The attachment filename exceeds 255 characters.")
    suffix = Path(cleaned).suffix.lower().lstrip(".")
    if suffix not in _ALLOWED_MIME_BY_EXTENSION:
        raise AttachmentValidationError(f"Files with the .{suffix or 'unknown'} extension are not supported.")
    return cleaned, suffix


def _reject_executable(content: bytes) -> None:
    signatures = (
        b"MZ",
        b"\x7fELF",
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
    )
    if any(content.startswith(signature) for signature in signatures):
        raise AttachmentValidationError("Executable files are prohibited.")


def _validate_binary_signature(extension: str, content: bytes) -> None:
    checks = {
        "pdf": content.startswith(b"%PDF-"),
        "png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpg": content.startswith(b"\xff\xd8\xff"),
        "jpeg": content.startswith(b"\xff\xd8\xff"),
        "webp": len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        "xlsx": content.startswith(b"PK\x03\x04"),
        "docx": content.startswith(b"PK\x03\x04"),
    }
    if extension in checks and not checks[extension]:
        raise AttachmentValidationError("The file contents do not match the declared attachment format.")


def validate_attachment(
    *,
    filename: str,
    declared_mime_type: str | None,
    content: bytes,
    max_file_size_bytes: int,
) -> ValidatedAttachment:
    """Validate and normalise an uploaded attachment before any object is persisted."""
    normalised_filename, extension = _normalise_filename(filename)
    if not content:
        raise AttachmentValidationError("Empty files cannot be uploaded.")
    if len(content) > max_file_size_bytes:
        raise AttachmentValidationError(
            f"The attachment exceeds the {max_file_size_bytes // (1024 * 1024)} MB upload limit."
        )
    mime_type = (declared_mime_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if mime_type not in _ALLOWED_MIME_BY_EXTENSION[extension]:
        raise AttachmentValidationError("The attachment MIME type does not match its extension.")

    _reject_executable(content)
    if extension in _BINARY_MIME_BY_EXTENSION:
        _validate_binary_signature(extension, content)
    else:
        if b"\x00" in content:
            raise AttachmentValidationError("Text and source-code attachments cannot contain binary null bytes.")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AttachmentValidationError("Text and source-code attachments must use UTF-8 encoding.") from exc

    return ValidatedAttachment(
        filename=normalised_filename,
        extension=extension,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256_hex=hashlib.sha256(content).hexdigest(),
    )
