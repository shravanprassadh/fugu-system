"""Bootstrap tests for pipeline seeding and provider credential storage."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.boot.seed_pipeline import (
    PipelineBootstrapError,
    build_default_steps,
    seed_pipeline_steps,
    store_provider_secret,
    validate_provider_type,
)
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base
from fugu.database.repositories import PipelineRepository
from fugu.execution.graph import PipelineDependencyGraphResolver
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from tests.database_helpers import create_sqlite_engine_map


@pytest_asyncio.fixture
async def bootstrap_registry() -> AsyncIterator[DatabaseSessionRegistry]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    master_engine = registry.get_engine(DatabaseTarget.MASTER)
    async with master_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield registry
    await registry.dispose_pools()


def test_default_steps_form_an_executable_dag_with_one_terminal_sink() -> None:
    steps = build_default_steps(provider_type="openrouter", model="anthropic/claude-sonnet")
    resolver = PipelineDependencyGraphResolver(steps)

    assert resolver.resolve_safe_execution_sequence() == [
        "input_analysis",
        "reasoning_branch",
        "terminal_synthesis",
    ]
    assert [step.is_terminal for step in steps] == [False, False, True]


def test_provider_validation_rejects_unregistered_adapters() -> None:
    assert validate_provider_type(" OpenRouter ") == "openrouter"
    with pytest.raises(PipelineBootstrapError):
        validate_provider_type("unregistered-provider")
    with pytest.raises(PipelineBootstrapError):
        validate_provider_type("   ")


@pytest.mark.asyncio
async def test_seeding_refuses_to_overwrite_without_replace(
    bootstrap_registry: DatabaseSessionRegistry,
) -> None:
    await seed_pipeline_steps(
        bootstrap_registry,
        provider_type="openrouter",
        model="first-model",
    )

    with pytest.raises(PipelineBootstrapError):
        await seed_pipeline_steps(
            bootstrap_registry,
            provider_type="openrouter",
            model="second-model",
        )

    async with bootstrap_registry.session(DatabaseTarget.MASTER) as session:
        steps = await PipelineRepository.list_steps(session)
        assert all(step.model_string == "first-model" for step in steps)


@pytest.mark.asyncio
async def test_seeding_with_replace_swaps_the_definition_atomically(
    bootstrap_registry: DatabaseSessionRegistry,
) -> None:
    await seed_pipeline_steps(
        bootstrap_registry,
        provider_type="openrouter",
        model="first-model",
    )
    await seed_pipeline_steps(
        bootstrap_registry,
        provider_type="openrouter",
        model="second-model",
        replace=True,
    )

    async with bootstrap_registry.session(DatabaseTarget.MASTER) as session:
        steps = await PipelineRepository.list_steps(session)
        assert len(steps) == 3
        assert all(step.model_string == "second-model" for step in steps)
        assert [step.sequence_order_position for step in steps] == [1, 2, 3]


@pytest.mark.asyncio
async def test_provider_secret_round_trips_through_the_runtime_vault(
    bootstrap_registry: DatabaseSessionRegistry,
) -> None:
    vault = ProviderCredentialVault(SymmetricVaultEngine(Fernet.generate_key().decode("ascii")))

    await store_provider_secret(
        bootstrap_registry,
        provider_name="openrouter",
        secret="initial-secret",
        vault=vault,
    )
    await store_provider_secret(
        bootstrap_registry,
        provider_name="openrouter",
        secret="rotated-secret",
        vault=vault,
    )

    async with bootstrap_registry.session(DatabaseTarget.MASTER) as session:
        assert await vault.retrieve(session, provider_name="openrouter") == "rotated-secret"
