"""Versioned pipeline persistence, validation, and execution-binding tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base, PipelineStep, ProviderCredential
from fugu.database.repositories import PipelineVersionRepository, ThreadRepository, UserRepository
from fugu.execution.kernel import PipelineExecutionKernel
from fugu.pipelines import PipelineVersionValidator
from fugu.providers.registry import ProviderRegistry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from tests.database_helpers import create_sqlite_engine_map


@pytest_asyncio.fixture
async def version_registry() -> AsyncIterator[DatabaseSessionRegistry]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield registry
    await registry.dispose_pools()


async def _create_version(
    registry: DatabaseSessionRegistry,
    *,
    include_credential: bool = True,
) -> int:
    async with registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(session, username="pipeline-admin", password_hash="test-hash", role="admin")
        if include_credential:
            session.add(
                ProviderCredential(
                    provider_name="openrouter",
                    encrypted_secret="encrypted-test-value",
                    key_version=1,
                )
            )
            await session.flush()
        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=user.id,
            change_description="Test draft",
        )
        await PipelineVersionRepository.add_stage(
            session,
            pipeline_version_id=version.id,
            stable_identifier="reader",
            name="Reader",
            description="Reads the request.",
            enabled=True,
            position=1,
            provider_type="openrouter",
            model_string="openrouter/free",
            system_prompt_directives="Read the request.",
            prerequisite_dependencies=[],
            is_terminal=False,
            required_capabilities=["text_generation"],
        )
        await PipelineVersionRepository.add_stage(
            session,
            pipeline_version_id=version.id,
            stable_identifier="consolidator",
            name="Consolidator",
            description="Returns the answer.",
            enabled=True,
            position=2,
            provider_type="openrouter",
            model_string="openrouter/free",
            system_prompt_directives="Return the final answer.",
            prerequisite_dependencies=["reader"],
            is_terminal=True,
            temperature=0.7,
            token_limit=1024,
            required_capabilities=["text_generation"],
        )
        return version.id


@pytest.mark.asyncio
async def test_valid_pipeline_draft_records_no_publication_issues(
    version_registry: DatabaseSessionRegistry,
) -> None:
    version_id = await _create_version(version_registry)
    async with version_registry.session(DatabaseTarget.MASTER) as session:
        version = await PipelineVersionRepository.require(session, version_id)
        result = await PipelineVersionValidator().validate(session, version.stages)
        await PipelineVersionRepository.record_validation(
            session,
            version=version,
            valid=result.is_valid,
            issues=[issue.to_payload() for issue in result.issues],
        )

        assert result.is_valid is True
        assert version.validation_status == "valid"
        assert version.validation_issues == []


@pytest.mark.asyncio
async def test_validator_rejects_cycles_missing_credentials_and_capability_mismatch(
    version_registry: DatabaseSessionRegistry,
) -> None:
    version_id = await _create_version(version_registry, include_credential=False)
    async with version_registry.session(DatabaseTarget.MASTER) as session:
        version = await PipelineVersionRepository.require(session, version_id)
        reader, consolidator = version.stages
        reader.prerequisite_dependencies = ["consolidator"]
        reader.required_capabilities = ["image_understanding"]
        await session.flush()

        result = await PipelineVersionValidator().validate(session, version.stages)
        codes = {issue.code for issue in result.issues}

        assert result.is_valid is False
        assert "dependency_cycle" in codes
        assert "missing_provider_credential" in codes
        assert "missing_model_capability" in codes


@pytest.mark.asyncio
async def test_validator_rejects_incomplete_and_recursive_fallbacks(
    version_registry: DatabaseSessionRegistry,
) -> None:
    version_id = await _create_version(version_registry)
    async with version_registry.session(DatabaseTarget.MASTER) as session:
        version = await PipelineVersionRepository.require(session, version_id)
        terminal = version.stages[-1]
        terminal.fallback_provider_type = "openrouter"
        terminal.fallback_model_string = None
        await session.flush()
        incomplete = await PipelineVersionValidator().validate(session, version.stages)
        assert "incomplete_fallback" in {issue.code for issue in incomplete.issues}

        terminal.fallback_model_string = "openrouter/free"
        await session.flush()
        recursive = await PipelineVersionValidator().validate(session, version.stages)
        assert "recursive_fallback" in {issue.code for issue in recursive.issues}


@pytest.mark.asyncio
async def test_prepare_execution_imports_legacy_definition_and_binds_run_to_version(
    version_registry: DatabaseSessionRegistry,
) -> None:
    vault = ProviderCredentialVault(SymmetricVaultEngine(Fernet.generate_key().decode("ascii")))
    async with version_registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(session, username="execution-owner", password_hash="test-hash")
        thread = await ThreadRepository.add(session, user_id=user.id, name="Version binding")
        session.add(
            PipelineStep(
                sequence_order_position=1,
                step_name="terminal",
                provider_type="openrouter",
                model_string="openrouter/free",
                system_prompt_directives="Answer.",
                prerequisite_dependencies=[],
                is_terminal=True,
            )
        )
        await vault.store(session, provider_name="openrouter", plaintext_secret="provider-secret")
        await session.flush()
        user_id = user.id
        thread_id = thread.id

    registry = ProviderRegistry()
    kernel = PipelineExecutionKernel(
        session_registry=version_registry,
        provider_registry=registry,
        credential_vault=vault,
    )
    prepared = await kernel.prepare_execution(
        thread_id=thread_id,
        user_id=user_id,
        initial_prompt="Bind this run",
    )

    async with version_registry.session(DatabaseTarget.MASTER) as session:
        version = await PipelineVersionRepository.require(session, prepared.pipeline_version_id)
        run = await session.get(__import__("fugu.database.models", fromlist=["PipelineRun"]).PipelineRun, prepared.run_id)

        assert version.state == "published"
        assert prepared.pipeline_version_number == version.version_number
        assert run is not None
        assert run.pipeline_version_id == version.id
