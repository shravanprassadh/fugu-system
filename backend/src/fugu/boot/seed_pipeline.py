"""Operator CLI for bootstrapping a published pipeline and provider credentials.

The website becomes the canonical pipeline-control surface in Phase 3. This command
remains only for fresh-environment bootstrap and creates the same immutable
versioned records consumed by runtime execution.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from getpass import getpass
from typing import TypeVar

from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.models import PipelineVersionStage, ProviderCredential
from fugu.database.repositories import PipelineVersionRepository
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


def build_default_steps(*, provider_type: str, model: str) -> list[PipelineVersionStage]:
    """Build the default Reader → Reasoner → Verifier → Consolidator DAG."""
    shared = {
        "pipeline_version_id": 0,
        "enabled": True,
        "provider_type": provider_type,
        "model_string": model,
        "temperature": None,
        "thinking_budget": None,
        "token_limit": None,
        "timeout_seconds": 45,
        "retry_count": 0,
        "fallback_provider_type": None,
        "fallback_model_string": None,
        "input_policy": {},
        "output_policy": {},
        "required_capabilities": ["text_generation"],
    }
    return [
        PipelineVersionStage(
            **shared,
            stable_identifier="reader",
            name="Reader",
            description="Understands the request and prepares structured context for downstream stages.",
            position=1,
            system_prompt_directives=(
                "Read the user's request carefully. Identify the objective, constraints, supplied evidence, "
                "unknowns, and the exact output required. Produce a precise structured handoff."
            ),
            prerequisite_dependencies=[],
            is_terminal=False,
        ),
        PipelineVersionStage(
            **shared,
            stable_identifier="reasoner",
            name="Reasoner",
            description="Performs the main analysis and develops a defensible solution.",
            position=2,
            system_prompt_directives=(
                "Use the Reader handoff to perform the main analysis. State assumptions, resolve trade-offs, "
                "and develop the strongest answer supported by the available context."
            ),
            prerequisite_dependencies=["reader"],
            is_terminal=False,
        ),
        PipelineVersionStage(
            **shared,
            stable_identifier="verifier",
            name="Verifier",
            description="Checks accuracy, omissions, contradictions, and unsupported claims.",
            position=3,
            system_prompt_directives=(
                "Audit the Reader and Reasoner outputs. Identify factual risks, missing requirements, internal "
                "contradictions, and unsupported claims. Return concrete corrections for the final stage."
            ),
            prerequisite_dependencies=["reader", "reasoner"],
            is_terminal=False,
        ),
        PipelineVersionStage(
            **shared,
            stable_identifier="consolidator",
            name="Consolidator",
            description="Produces the final response shown to the user.",
            position=4,
            system_prompt_directives=(
                "Produce one clear, self-contained final answer using the prior stage outputs. Apply the "
                "Verifier corrections, remove internal process commentary, and satisfy the user's requested format."
            ),
            prerequisite_dependencies=["reader", "reasoner", "verifier"],
            is_terminal=True,
        ),
    ]


async def seed_pipeline_steps(
    registry: DatabaseSessionRegistry,
    *,
    provider_type: str,
    model: str,
    replace: bool = False,
) -> list[PipelineVersionStage]:
    """Publish the default pipeline as a new immutable version."""
    validated_provider = validate_provider_type(provider_type)
    validated_model = validate_model_string(model)
    stages = build_default_steps(provider_type=validated_provider, model=validated_model)
    PipelineDependencyGraphResolver(stages).resolve_ordered_steps()

    async with registry.session(DatabaseTarget.MASTER) as session:
        current = await PipelineVersionRepository.get_current_published(session)
        if current is not None and not replace:
            raise PipelineBootstrapError(
                f"Published pipeline version {current.version_number} already exists. "
                "Re-run with --replace to supersede it."
            )
        if current is not None:
            current.state = "superseded"

        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=None,
            change_description="Bootstrap the default four-stage pipeline",
            state="published",
        )
        now = datetime.now(timezone.utc)
        version.validation_status = "valid"
        version.validation_issues = []
        version.validated_at = now
        version.published_at = now
        for stage in stages:
            stage.pipeline_version_id = version.id
        session.add_all(stages)
        await session.flush()
        return stages


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
        description="Publish the default four-stage pipeline definition for one provider and model.",
    )
    parser.add_argument("--provider", required=True, help="Registered provider adapter, e.g. openrouter.")
    parser.add_argument("--model", required=True, help="Model identifier passed to the provider on every stage.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Supersede the current published version with a new default version.",
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
        stages = asyncio.run(
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

    names = " → ".join(stage.name for stage in stages)
    print(f"Published {len(stages)} pipeline stages: {names}.")
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
