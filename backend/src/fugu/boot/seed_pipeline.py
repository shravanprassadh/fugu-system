"""Operator CLI for seeding pipeline definitions and provider credentials.

A fresh database contains no ``pipeline_steps`` rows and no
``provider_credentials`` rows, so authenticated execution fails until both are
bootstrapped. This module provides two console commands:

``fugu-seed-pipeline``
    Seed the default three-stage pipeline (input analysis → reasoning branch →
    terminal synthesis) for one provider and model.

``fugu-set-provider-credential``
    Encrypt and store (or rotate) one provider API credential through the same
    vault used at runtime. The secret is read from the
    ``FUGU_PROVIDER_SECRET`` environment variable or an interactive prompt —
    never from shell arguments, which leak into process listings.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from getpass import getpass
from typing import TypeVar

from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.models import PipelineStep, ProviderCredential
from fugu.database.repositories import PipelineRepository
from fugu.execution.graph import PipelineDependencyGraphResolver
from fugu.providers.registry import get_provider_registry
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine

PROVIDER_SECRET_ENVIRONMENT_VARIABLE = "FUGU_PROVIDER_SECRET"


class PipelineBootstrapError(RuntimeError):
    """Raised when operator-supplied pipeline configuration cannot be applied safely."""


def validate_provider_type(provider_type: str) -> str:
    """Normalize a provider name and require a registered runtime adapter."""
    normalized = provider_type.strip().lower()
    if not normalized:
        raise PipelineBootstrapError("Provider names cannot be empty.")
    registered = get_provider_registry().registered_names()
    if normalized not in registered:
        available = ", ".join(registered) or "none"
        raise PipelineBootstrapError(
            f"Provider {normalized!r} has no registered runtime adapter. Available providers: {available}."
        )
    return normalized


def validate_model_string(model: str) -> str:
    """Require a non-empty model identifier within the schema's length limit."""
    normalized = model.strip()
    if not 1 <= len(normalized) <= 255:
        raise PipelineBootstrapError("Model identifiers must contain between 1 and 255 characters.")
    return normalized


def build_default_steps(*, provider_type: str, model: str) -> list[PipelineStep]:
    """Build the default three-stage DAG with exactly one terminal sink."""
    return [
        PipelineStep(
            sequence_order_position=1,
            step_name="input_analysis",
            provider_type=provider_type,
            model_string=model,
            system_prompt_directives=(
                "Analyze the user's request. Restate the task, constraints, and expected output precisely."
            ),
            prerequisite_dependencies=[],
            is_terminal=False,
        ),
        PipelineStep(
            sequence_order_position=2,
            step_name="reasoning_branch",
            provider_type=provider_type,
            model_string=model,
            system_prompt_directives=(
                "Reason step by step about how to satisfy the analyzed task. Surface risks and assumptions."
            ),
            prerequisite_dependencies=["input_analysis"],
            is_terminal=False,
        ),
        PipelineStep(
            sequence_order_position=3,
            step_name="terminal_synthesis",
            provider_type=provider_type,
            model_string=model,
            system_prompt_directives=(
                "Synthesize one final, self-contained answer for the user from the prior stage outputs."
            ),
            prerequisite_dependencies=["input_analysis", "reasoning_branch"],
            is_terminal=True,
        ),
    ]


async def seed_pipeline_steps(
    registry: DatabaseSessionRegistry,
    *,
    provider_type: str,
    model: str,
    replace: bool = False,
) -> list[PipelineStep]:
    """Persist the default pipeline after validating it resolves as an executable DAG."""
    validated_provider = validate_provider_type(provider_type)
    validated_model = validate_model_string(model)
    steps = build_default_steps(provider_type=validated_provider, model=validated_model)
    # Prove the seeded definition is executable before touching the database.
    PipelineDependencyGraphResolver(steps).resolve_ordered_steps()

    async with registry.session(DatabaseTarget.MASTER) as session:
        existing = await PipelineRepository.list_steps(session)
        if existing and not replace:
            raise PipelineBootstrapError(
                f"{len(existing)} pipeline step(s) already exist. Re-run with --replace to overwrite them."
            )
        for step in existing:
            await session.delete(step)
        await session.flush()
        session.add_all(steps)
        await session.flush()
        return steps


async def store_provider_secret(
    registry: DatabaseSessionRegistry,
    *,
    provider_name: str,
    secret: str,
    vault: ProviderCredentialVault | None = None,
) -> ProviderCredential:
    """Encrypt and store (or rotate) one provider credential through the runtime vault."""
    validated_provider = validate_provider_type(provider_name)
    resolved_vault = vault or ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    async with registry.session(DatabaseTarget.MASTER) as session:
        return await resolved_vault.store(
            session,
            provider_name=validated_provider,
            plaintext_secret=secret,
        )


def read_provider_secret() -> str:
    """Read the provider secret from the environment or an interactive prompt."""
    from_environment = os.environ.get(PROVIDER_SECRET_ENVIRONMENT_VARIABLE, "")
    secret = from_environment or getpass("Provider API secret: ")
    if not secret.strip():
        raise PipelineBootstrapError("Provider secrets cannot be empty.")
    return secret


BootstrapResult = TypeVar("BootstrapResult")


async def _run_with_registry(
    coroutine_factory: Callable[[DatabaseSessionRegistry], Awaitable[BootstrapResult]],
) -> BootstrapResult:
    """Run one bootstrap coroutine against the configured registry, then release pools."""
    registry = get_session_registry()
    try:
        return await coroutine_factory(registry)
    finally:
        await registry.dispose_pools()
        if get_session_registry.cache_info().currsize:
            get_session_registry.cache_clear()


def build_seed_argument_parser() -> argparse.ArgumentParser:
    """Build the pipeline-seeding command-line contract."""
    parser = argparse.ArgumentParser(
        prog="fugu-seed-pipeline",
        description="Seed the default three-stage pipeline definition for one provider and model.",
    )
    parser.add_argument("--provider", required=True, help="Registered provider adapter, e.g. openrouter.")
    parser.add_argument("--model", required=True, help="Model identifier passed to the provider on every stage.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite existing pipeline steps instead of refusing when any exist.",
    )
    return parser


def build_credential_argument_parser() -> argparse.ArgumentParser:
    """Build the credential-storage command-line contract."""
    parser = argparse.ArgumentParser(
        prog="fugu-set-provider-credential",
        description=(
            "Encrypt and store one provider API credential. The secret is read from the "
            f"{PROVIDER_SECRET_ENVIRONMENT_VARIABLE} environment variable or an interactive prompt."
        ),
    )
    parser.add_argument("--provider", required=True, help="Registered provider adapter, e.g. openrouter.")
    return parser


def seed_pipeline_main() -> int:
    """Execute the pipeline-definition bootstrap command."""
    arguments = build_seed_argument_parser().parse_args()
    try:
        steps = asyncio.run(
            _run_with_registry(
                lambda registry: seed_pipeline_steps(
                    registry,
                    provider_type=arguments.provider,
                    model=arguments.model,
                    replace=arguments.replace,
                )
            )
        )
    except PipelineBootstrapError as exc:
        print(f"Pipeline seeding failed: {exc}", file=sys.stderr)
        return 1

    names = " → ".join(step.step_name for step in steps)
    print(f"Seeded {len(steps)} pipeline steps: {names}.")
    return 0


def set_provider_credential_main() -> int:
    """Execute the provider-credential bootstrap command."""
    arguments = build_credential_argument_parser().parse_args()
    try:
        secret = read_provider_secret()
        credential = asyncio.run(
            _run_with_registry(
                lambda registry: store_provider_secret(
                    registry,
                    provider_name=arguments.provider,
                    secret=secret,
                )
            )
        )
    except PipelineBootstrapError as exc:
        print(f"Credential storage failed: {exc}", file=sys.stderr)
        return 1

    print(f"Stored encrypted credential for provider {credential.provider_name!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(seed_pipeline_main())
