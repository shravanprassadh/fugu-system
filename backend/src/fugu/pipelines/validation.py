"""Deterministic validation for versioned pipeline drafts."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.models import PipelineVersionStage
from fugu.database.repositories import ProviderCredentialRepository
from fugu.providers.catalogue import ModelDefinition, get_provider_catalogue
from fugu.providers.parameters import validate_model_parameters

_ALLOWED_CAPABILITIES = {
    "text_generation",
    "image_understanding",
    "document_input",
    "tool_support",
    "reasoning_support",
}


@dataclass(frozen=True, slots=True)
class PipelineValidationIssue:
    """One sanitized publication-blocking pipeline issue."""

    code: str
    message: str
    stage_identifier: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.stage_identifier is not None:
            payload["stage_identifier"] = self.stage_identifier
        return payload


@dataclass(frozen=True, slots=True)
class PipelineValidationResult:
    """Complete deterministic validation outcome for one pipeline draft."""

    issues: tuple[PipelineValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def to_payload(self) -> dict[str, object]:
        return {
            "valid": self.is_valid,
            "issues": [issue.to_payload() for issue in self.issues],
        }


class PipelineVersionValidator:
    """Validate graph structure, provider contracts and execution prerequisites."""

    async def validate(
        self,
        session: AsyncSession,
        stages: list[PipelineVersionStage],
    ) -> PipelineValidationResult:
        issues: list[PipelineValidationIssue] = []
        if not stages:
            return PipelineValidationResult(
                issues=(
                    PipelineValidationIssue(
                        code="empty_pipeline",
                        message="A pipeline must contain at least one stage.",
                    ),
                ),
            )

        self._validate_identifiers_and_positions(stages, issues)
        enabled_stages = [stage for stage in stages if stage.enabled]
        if not enabled_stages:
            issues.append(
                PipelineValidationIssue(
                    code="no_enabled_stages",
                    message="A published pipeline must contain at least one enabled stage.",
                )
            )
            return PipelineValidationResult(tuple(issues))

        self._validate_terminal_stage(enabled_stages, issues)
        self._validate_dependencies(enabled_stages, issues)
        self._validate_cycles(enabled_stages, issues)
        await self._validate_provider_contracts(session, enabled_stages, issues)
        return PipelineValidationResult(tuple(issues))

    @staticmethod
    def _validate_identifiers_and_positions(
        stages: list[PipelineVersionStage],
        issues: list[PipelineValidationIssue],
    ) -> None:
        seen_identifiers: set[str] = set()
        seen_positions: set[int] = set()
        for stage in stages:
            identifier = stage.stable_identifier.strip()
            if not identifier:
                issues.append(
                    PipelineValidationIssue(
                        code="blank_stage_identifier",
                        message="Every stage requires a stable identifier.",
                    )
                )
            elif identifier in seen_identifiers:
                issues.append(
                    PipelineValidationIssue(
                        code="duplicate_stage_identifier",
                        message=f"Stage identifier {identifier!r} is used more than once.",
                        stage_identifier=identifier,
                    )
                )
            seen_identifiers.add(identifier)

            if stage.position in seen_positions:
                issues.append(
                    PipelineValidationIssue(
                        code="duplicate_stage_position",
                        message=f"Stage position {stage.position} is used more than once.",
                        stage_identifier=identifier or None,
                    )
                )
            if stage.position < 1:
                issues.append(
                    PipelineValidationIssue(
                        code="invalid_stage_position",
                        message="Stage positions must be positive integers.",
                        stage_identifier=identifier or None,
                    )
                )
            seen_positions.add(stage.position)

    @staticmethod
    def _validate_terminal_stage(
        enabled_stages: list[PipelineVersionStage],
        issues: list[PipelineValidationIssue],
    ) -> None:
        terminals = [stage for stage in enabled_stages if stage.is_terminal]
        if not terminals:
            issues.append(
                PipelineValidationIssue(
                    code="missing_terminal_stage",
                    message="Exactly one enabled stage must be terminal.",
                )
            )
        elif len(terminals) > 1:
            issues.append(
                PipelineValidationIssue(
                    code="multiple_terminal_stages",
                    message="Only one enabled stage can be terminal.",
                )
            )

    @staticmethod
    def _validate_dependencies(
        enabled_stages: list[PipelineVersionStage],
        issues: list[PipelineValidationIssue],
    ) -> None:
        identifiers = {stage.stable_identifier for stage in enabled_stages}
        terminal_identifiers = {stage.stable_identifier for stage in enabled_stages if stage.is_terminal}
        for stage in enabled_stages:
            seen_dependencies: set[str] = set()
            for dependency in stage.prerequisite_dependencies:
                if not isinstance(dependency, str) or not dependency.strip():
                    issues.append(
                        PipelineValidationIssue(
                            code="invalid_prerequisite",
                            message="Prerequisite identifiers must be non-empty strings.",
                            stage_identifier=stage.stable_identifier,
                        )
                    )
                    continue
                normalized = dependency.strip()
                if normalized == stage.stable_identifier:
                    issues.append(
                        PipelineValidationIssue(
                            code="self_dependency",
                            message="A stage cannot depend on itself.",
                            stage_identifier=stage.stable_identifier,
                        )
                    )
                elif normalized not in identifiers:
                    issues.append(
                        PipelineValidationIssue(
                            code="missing_prerequisite",
                            message=f"Prerequisite {normalized!r} is missing or disabled.",
                            stage_identifier=stage.stable_identifier,
                        )
                    )
                elif normalized in terminal_identifiers:
                    issues.append(
                        PipelineValidationIssue(
                            code="terminal_has_dependent",
                            message="A terminal stage cannot be a prerequisite for another enabled stage.",
                            stage_identifier=stage.stable_identifier,
                        )
                    )
                if normalized in seen_dependencies:
                    issues.append(
                        PipelineValidationIssue(
                            code="duplicate_prerequisite",
                            message=f"Prerequisite {normalized!r} is repeated.",
                            stage_identifier=stage.stable_identifier,
                        )
                    )
                seen_dependencies.add(normalized)

    @staticmethod
    def _validate_cycles(
        enabled_stages: list[PipelineVersionStage],
        issues: list[PipelineValidationIssue],
    ) -> None:
        identifiers = {stage.stable_identifier for stage in enabled_stages}
        dependencies = {
            stage.stable_identifier: {
                dependency.strip()
                for dependency in stage.prerequisite_dependencies
                if isinstance(dependency, str) and dependency.strip() in identifiers
            }
            for stage in enabled_stages
        }
        remaining = set(identifiers)
        while remaining:
            ready = {identifier for identifier in remaining if not (dependencies[identifier] & remaining)}
            if not ready:
                issues.append(
                    PipelineValidationIssue(
                        code="dependency_cycle",
                        message="The enabled pipeline stages contain a dependency cycle.",
                    )
                )
                return
            remaining -= ready

    async def _validate_provider_contracts(
        self,
        session: AsyncSession,
        enabled_stages: list[PipelineVersionStage],
        issues: list[PipelineValidationIssue],
    ) -> None:
        for stage in enabled_stages:
            model = self._validate_model(stage, issues)
            if model is not None:
                self._validate_capabilities(stage, model, issues)
            await self._validate_credential(session, stage.provider_type, stage.stable_identifier, issues)
            await self._validate_fallback(session, stage, issues)
            if stage.timeout_seconds < 1:
                issues.append(
                    PipelineValidationIssue(
                        code="invalid_timeout",
                        message="Stage timeout must be at least one second.",
                        stage_identifier=stage.stable_identifier,
                    )
                )
            if stage.retry_count < 0 or stage.retry_count > 10:
                issues.append(
                    PipelineValidationIssue(
                        code="invalid_retry_count",
                        message="Stage retry count must be between 0 and 10.",
                        stage_identifier=stage.stable_identifier,
                    )
                )

    @staticmethod
    def _validate_model(
        stage: PipelineVersionStage,
        issues: list[PipelineValidationIssue],
    ) -> ModelDefinition | None:
        try:
            parameters = validate_model_parameters(
                stage.provider_type,
                stage.model_string,
                temperature=stage.temperature,
                max_output_tokens=stage.token_limit,
                thinking_budget=stage.thinking_budget,
            )
            del parameters
            return get_provider_catalogue().validate_selection(stage.provider_type, stage.model_string)
        except ValueError as exc:
            issues.append(
                PipelineValidationIssue(
                    code="invalid_model_configuration",
                    message=str(exc),
                    stage_identifier=stage.stable_identifier,
                )
            )
            return None

    @staticmethod
    def _validate_capabilities(
        stage: PipelineVersionStage,
        model: ModelDefinition,
        issues: list[PipelineValidationIssue],
    ) -> None:
        for capability in stage.required_capabilities:
            if capability not in _ALLOWED_CAPABILITIES:
                issues.append(
                    PipelineValidationIssue(
                        code="unknown_required_capability",
                        message=f"Required capability {capability!r} is not recognized.",
                        stage_identifier=stage.stable_identifier,
                    )
                )
                continue
            if not bool(getattr(model.capabilities, capability)):
                issues.append(
                    PipelineValidationIssue(
                        code="missing_model_capability",
                        message=(
                            f"Model {model.identifier!r} does not provide required capability {capability!r}."
                        ),
                        stage_identifier=stage.stable_identifier,
                    )
                )

    @staticmethod
    async def _validate_credential(
        session: AsyncSession,
        provider_type: str,
        stage_identifier: str,
        issues: list[PipelineValidationIssue],
    ) -> None:
        credential = await ProviderCredentialRepository.get_by_provider(session, provider_type)
        if credential is None:
            issues.append(
                PipelineValidationIssue(
                    code="missing_provider_credential",
                    message=f"No active credential is configured for provider {provider_type!r}.",
                    stage_identifier=stage_identifier,
                )
            )

    async def _validate_fallback(
        self,
        session: AsyncSession,
        stage: PipelineVersionStage,
        issues: list[PipelineValidationIssue],
    ) -> None:
        fallback_provider = (stage.fallback_provider_type or "").strip().lower()
        fallback_model = (stage.fallback_model_string or "").strip()
        if not fallback_provider and not fallback_model:
            return
        if not fallback_provider or not fallback_model:
            issues.append(
                PipelineValidationIssue(
                    code="incomplete_fallback",
                    message="Fallback provider and fallback model must be supplied together.",
                    stage_identifier=stage.stable_identifier,
                )
            )
            return
        if fallback_provider == stage.provider_type and fallback_model == stage.model_string:
            issues.append(
                PipelineValidationIssue(
                    code="recursive_fallback",
                    message="A stage cannot fall back to its primary provider and model.",
                    stage_identifier=stage.stable_identifier,
                )
            )
            return
        try:
            get_provider_catalogue().validate_selection(fallback_provider, fallback_model)
        except ValueError as exc:
            issues.append(
                PipelineValidationIssue(
                    code="invalid_fallback_model",
                    message=str(exc),
                    stage_identifier=stage.stable_identifier,
                )
            )
            return
        await self._validate_credential(session, fallback_provider, stage.stable_identifier, issues)
