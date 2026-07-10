"""Attachment-aware pipeline execution, snapshot, and multimodal isolation tests."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.attachments.processing import process_attachment_bytes
from fugu.database.attachments import Attachment
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base, PipelineRun, User
from fugu.database.repositories import (
    AttachmentRepository,
    PipelineVersionRepository,
    ThreadRepository,
    UserRepository,
)
from fugu.execution.attachment_kernel import AttachmentAwarePipelineExecutionKernel
from fugu.execution.exceptions import PipelineValidationError
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.registry import ProviderRegistry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from fugu.storage.local import LocalObjectStorage
from tests.database_helpers import create_sqlite_engine_map

VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"


@dataclass
class ProviderScript:
    """Capture requests and emit deterministic Reader and terminal outputs."""

    requests: list[ProviderRequest] = field(default_factory=list)


class ScriptedProvider(ExecutionProvider):
    """Return one deterministic output per invocation."""

    def __init__(self, script: ProviderScript) -> None:
        self._script = script

    async def generate_token_stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        self._script.requests.append(request)
        yield "reader interpretation" if len(self._script.requests) == 1 else "final response"


@dataclass
class AttachmentExecutionContext:
    registry: DatabaseSessionRegistry
    user: User
    other_user: User
    thread_id: int
    vault: ProviderCredentialVault
    script: ProviderScript
    providers: ProviderRegistry
    storage: LocalObjectStorage


@pytest_asyncio.fixture
async def attachment_execution_context(tmp_path: Path) -> AsyncIterator[AttachmentExecutionContext]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    script = ProviderScript()
    providers = ProviderRegistry()
    providers.register("nvidia", lambda: ScriptedProvider(script))
    providers.register("openrouter", lambda: ScriptedProvider(script))
    vault = ProviderCredentialVault(SymmetricVaultEngine(Fernet.generate_key().decode("ascii")))
    storage = LocalObjectStorage(tmp_path)

    async with registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(session, username="attachment-runner", password_hash="hash")
        other_user = await UserRepository.add(session, username="attachment-outsider", password_hash="hash")
        thread = await ThreadRepository.add(session, user_id=user.id, name="Attachment execution")
        await vault.store(session, provider_name="nvidia", plaintext_secret="nvidia-secret")
        await vault.store(session, provider_name="openrouter", plaintext_secret="openrouter-secret")
        thread_id = thread.id

    yield AttachmentExecutionContext(
        registry=registry,
        user=user,
        other_user=other_user,
        thread_id=thread_id,
        vault=vault,
        script=script,
        providers=providers,
        storage=storage,
    )
    await registry.dispose_pools()


async def _publish_pipeline(
    context: AttachmentExecutionContext,
    *,
    reader_provider: str = "nvidia",
    reader_model: str = VISION_MODEL,
) -> None:
    async with context.registry.session(DatabaseTarget.MASTER) as session:
        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=context.user.id,
            change_description="Attachment pipeline",
            state="published",
        )
        version.validation_status = "valid"
        version.validation_issues = []
        version.validated_at = datetime.now(timezone.utc)
        version.published_at = datetime.now(timezone.utc)
        await PipelineVersionRepository.add_stage(
            session,
            pipeline_version_id=version.id,
            stable_identifier="reader",
            name="Reader",
            description="Interprets attachments once.",
            enabled=True,
            position=1,
            provider_type=reader_provider,
            model_string=reader_model,
            system_prompt_directives="Read the request and attached evidence.",
            prerequisite_dependencies=[],
            is_terminal=False,
            required_capabilities=["text_generation"],
        )
        await PipelineVersionRepository.add_stage(
            session,
            pipeline_version_id=version.id,
            stable_identifier="consolidator",
            name="Consolidator",
            description="Produces the final response.",
            enabled=True,
            position=2,
            provider_type="nvidia",
            model_string=VISION_MODEL,
            system_prompt_directives="Consolidate the Reader interpretation.",
            prerequisite_dependencies=["reader"],
            is_terminal=True,
            required_capabilities=["text_generation"],
        )


async def _add_ready_attachment(
    context: AttachmentExecutionContext,
    *,
    public_id: str,
    filename: str,
    mime_type: str,
    extension: str,
    content: bytes,
) -> Attachment:
    checksum = hashlib.sha256(content).hexdigest()
    storage_key = f"users/{context.user.id}/threads/{context.thread_id}/{public_id}/source.{extension}"
    await context.storage.put(
        bucket="attachments",
        key=storage_key,
        content=content,
        content_type=mime_type,
        checksum_sha256=checksum,
    )
    processed = process_attachment_bytes(extension=extension, content=content)
    async with context.registry.session(DatabaseTarget.MASTER) as session:
        attachment = await AttachmentRepository.add_pending(
            session,
            public_id=public_id,
            owner_user_id=context.user.id,
            thread_id=context.thread_id,
            original_filename=filename,
            mime_type=mime_type,
            file_extension=extension,
            size_bytes=len(content),
            sha256_hex=checksum,
            storage_backend="local",
            storage_bucket="attachments",
            storage_key=storage_key,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        await AttachmentRepository.mark_uploaded(session, attachment=attachment)
        return await AttachmentRepository.mark_ready(
            session,
            attachment=attachment,
            structured_content=processed.structured_content,
            warnings=processed.warnings,
            processing_version=processed.processing_version,
        )


def _kernel(context: AttachmentExecutionContext) -> AttachmentAwarePipelineExecutionKernel:
    return AttachmentAwarePipelineExecutionKernel(
        session_registry=context.registry,
        provider_registry=context.providers,
        credential_vault=context.vault,
        storage_provider=lambda: context.storage,
    )


@pytest.mark.asyncio
async def test_structured_attachment_is_injected_only_into_reader_and_snapshotted(
    attachment_execution_context: AttachmentExecutionContext,
) -> None:
    await _publish_pipeline(attachment_execution_context)
    attachment = await _add_ready_attachment(
        attachment_execution_context,
        public_id="00000000-0000-4000-8000-000000000101",
        filename="evidence.txt",
        mime_type="text/plain",
        extension="txt",
        content=b"ALPHA-RAW-EVIDENCE\nsecond line",
    )
    kernel = _kernel(attachment_execution_context)
    prepared = await kernel.prepare_execution(
        thread_id=attachment_execution_context.thread_id,
        user_id=attachment_execution_context.user.id,
        initial_prompt="Summarise the attached evidence.",
        attachment_public_ids=(attachment.public_id,),
    )
    _ = [event async for event in kernel.execute(prepared)]

    reader_request, terminal_request = attachment_execution_context.script.requests
    assert "[Structured attachments for Reader interpretation]" in reader_request.prompt_content
    assert "ALPHA-RAW-EVIDENCE" in reader_request.prompt_content
    assert reader_request.image_inputs == ()
    assert "reader interpretation" in terminal_request.prompt_content
    assert "ALPHA-RAW-EVIDENCE" not in terminal_request.prompt_content
    assert terminal_request.image_inputs == ()

    async with attachment_execution_context.registry.session(DatabaseTarget.MASTER) as session:
        run = await session.get(PipelineRun, prepared.run_id)
        persisted = await AttachmentRepository.require_owned(
            session,
            public_id=attachment.public_id,
            owner_user_id=attachment_execution_context.user.id,
        )
    assert run is not None
    assert run.attachment_snapshot[0]["sha256"] == attachment.sha256_hex
    assert run.attachment_snapshot[0]["structured_content"]["kind"] == "text"
    assert persisted.message_id is not None


@pytest.mark.asyncio
async def test_private_image_bytes_are_sent_only_to_vision_reader(
    attachment_execution_context: AttachmentExecutionContext,
) -> None:
    await _publish_pipeline(attachment_execution_context)
    image = Image.new("RGB", (4, 3))
    payload = BytesIO()
    image.save(payload, format="PNG")
    attachment = await _add_ready_attachment(
        attachment_execution_context,
        public_id="00000000-0000-4000-8000-000000000102",
        filename="diagram.png",
        mime_type="image/png",
        extension="png",
        content=payload.getvalue(),
    )
    kernel = _kernel(attachment_execution_context)
    prepared = await kernel.prepare_execution(
        thread_id=attachment_execution_context.thread_id,
        user_id=attachment_execution_context.user.id,
        initial_prompt="Interpret this image.",
        attachment_public_ids=(attachment.public_id,),
    )
    _ = [event async for event in kernel.execute(prepared)]

    reader_request, terminal_request = attachment_execution_context.script.requests
    assert len(reader_request.image_inputs) == 1
    assert reader_request.image_inputs[0].data_url.startswith("data:image/png;base64,")
    multimodal_content = reader_request.user_message_content()
    assert isinstance(multimodal_content, list)
    assert multimodal_content[0] == {"type": "text", "text": reader_request.prompt_content}
    assert terminal_request.image_inputs == ()


@pytest.mark.asyncio
async def test_image_execution_rejects_non_vision_reader_before_provider_call(
    attachment_execution_context: AttachmentExecutionContext,
) -> None:
    await _publish_pipeline(
        attachment_execution_context,
        reader_provider="openrouter",
        reader_model="openrouter/free",
    )
    image = Image.new("RGB", (2, 2))
    payload = BytesIO()
    image.save(payload, format="PNG")
    attachment = await _add_ready_attachment(
        attachment_execution_context,
        public_id="00000000-0000-4000-8000-000000000103",
        filename="unsupported.png",
        mime_type="image/png",
        extension="png",
        content=payload.getvalue(),
    )

    with pytest.raises(PipelineValidationError, match="does not support image understanding"):
        await _kernel(attachment_execution_context).prepare_execution(
            thread_id=attachment_execution_context.thread_id,
            user_id=attachment_execution_context.user.id,
            initial_prompt="Read the image.",
            attachment_public_ids=(attachment.public_id,),
        )
    assert attachment_execution_context.script.requests == []


@pytest.mark.asyncio
async def test_attachment_selection_rejects_cross_user_scope(
    attachment_execution_context: AttachmentExecutionContext,
) -> None:
    await _publish_pipeline(attachment_execution_context)
    attachment = await _add_ready_attachment(
        attachment_execution_context,
        public_id="00000000-0000-4000-8000-000000000104",
        filename="private.txt",
        mime_type="text/plain",
        extension="txt",
        content=b"private evidence",
    )

    with pytest.raises(PipelineValidationError, match="outside the authenticated thread scope"):
        await _kernel(attachment_execution_context).prepare_execution(
            thread_id=attachment_execution_context.thread_id,
            user_id=attachment_execution_context.other_user.id,
            initial_prompt="Steal the attachment.",
            attachment_public_ids=(attachment.public_id,),
        )
