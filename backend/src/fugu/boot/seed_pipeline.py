from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.boot.config import load_settings
from fugu.database.connection import create_database_engines, sessionmaker_for
from fugu.database.models import PipelineStep, ProviderCredential
from fugu.execution.graph import PipelineGraph
from fugu.execution.models import PipelineStepDefinition
from fugu.providers.registry import get_provider
from fugu.security.encryption import Vault

DEFAULT_PIPELINE_IDENTITY = "default-chat-pipeline"


def _build_default_pipeline(provider: str, model: str) -> list[PipelineStepDefinition]:
    return [
        PipelineStepDefinition(
            step_id="input-normalization",
            provider=provider,
            model=model,
            depends_on=[],
            system_prompt="Normalize the user request into a concise execution brief.",
        ),
        PipelineStepDefinition(
            step_id="reasoning-pass",
            provider=provider,
            model=model,
            depends_on=["input-normalization"],
            system_prompt="Reason through the brief and produce the best answer plan.",
        ),
        PipelineStepDefinition(
            step_id="final-response",
            provider=provider,
            model=model,
            depends_on=["reasoning-pass"],
            system_prompt="Write the final user-facing response.",
        ),
    ]


def _parse_seed_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the default Fugu execution pipeline.")
    parser.add_argument("--provider", required=True, help="Registered provider adapter name, for example openrouter.")
    parser.add_argument("--model", required=True, help="Provider model identifier.")
    parser.add_argument("--replace", action="store_true", help="Replace existing pipeline steps for the same identity.")
    return parser.parse_args(argv)


def _parse_credential_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Store an encrypted provider credential.")
    parser.add_argument("--provider", required=True, help="Registered provider adapter name, for example openrouter.")
    return parser.parse_args(argv)


async def _seed_pipeline(session: AsyncSession, provider: str, model: str, *, replace: bool) -> None:
    get_provider(provider)
    definitions = _build_default_pipeline(provider, model)
    PipelineGraph.from_definitions(definitions)

    existing = await session.scalar(
        select(PipelineStep.id).where(PipelineStep.pipeline_identity == DEFAULT_PIPELINE_IDENTITY).limit(1)
    )
    if existing is not None and not replace:
        raise SystemExit(
            f"Pipeline {DEFAULT_PIPELINE_IDENTITY!r} already exists. Re-run with --replace to overwrite it."
        )

    if replace:
        await session.execute(delete(PipelineStep).where(PipelineStep.pipeline_identity == DEFAULT_PIPELINE_IDENTITY))

    for order, definition in enumerate(definitions):
        session.add(
            PipelineStep(
                pipeline_identity=DEFAULT_PIPELINE_IDENTITY,
                step_identity=definition.step_id,
                provider_name=definition.provider,
                model_name=definition.model,
                depends_on=definition.depends_on,
                system_prompt=definition.system_prompt,
                execution_order=order,
                is_active=True,
            )
        )

    await session.commit()


async def _set_provider_credential(session: AsyncSession, provider: str, secret: str) -> None:
    get_provider(provider)
    settings = load_settings()
    vault = Vault(settings.vault_encryption_key)
    encrypted_secret = vault.encrypt(secret)

    existing = await session.scalar(select(ProviderCredential).where(ProviderCredential.provider_name == provider).limit(1))
    if existing is None:
        session.add(ProviderCredential(provider_name=provider, encrypted_secret=encrypted_secret, is_active=True))
    else:
        existing.encrypted_secret = encrypted_secret
        existing.is_active = True

    await session.commit()


async def _with_master_session() -> AsyncSession:
    settings = load_settings()
    engines = create_database_engines(settings)
    return sessionmaker_for(engines.master_router)()


async def _seed_pipeline_async(argv: Sequence[str] | None = None) -> None:
    args = _parse_seed_args(argv)
    async with await _with_master_session() as session:
        await _seed_pipeline(session, args.provider, args.model, replace=args.replace)


async def _set_provider_credential_async(argv: Sequence[str] | None = None) -> None:
    args = _parse_credential_args(argv)
    secret = os.environ.get("FUGU_PROVIDER_SECRET")
    if secret is None:
        secret = getpass.getpass("Provider secret: ")
    if not secret:
        raise SystemExit("Provider secret cannot be empty.")
    async with await _with_master_session() as session:
        await _set_provider_credential(session, args.provider, secret)


def seed_pipeline_main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(_seed_pipeline_async(argv))


def set_provider_credential_main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(_set_provider_credential_async(argv))
