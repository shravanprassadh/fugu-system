"""Transactional draft, publication, and rollback operations for pipeline versions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.models import PipelineVersion, PipelineVersionStage
from fugu.database.repositories import PipelineVersionRepository
from fugu.pipelines.validation import PipelineValidationResult, PipelineVersionValidator


class PipelineControlConflictError(RuntimeError):
    """Raised when an operation would mutate immutable pipeline history."""


@dataclass(frozen=True, slots=True)
class PipelineStageConfiguration:
    """Complete normalized configuration submitted for one draft stage."""

    stable_identifier: str
    name: str
    description: str = ""
    enabled: bool = True
    position: int = 1
    provider_type: str = ""
    model_string: str = ""
    system_prompt_directives: str = ""
    prerequisite_dependencies: tuple[str, ...] = ()
    is_terminal: bool = False
    temperature: float | None = None
    thinking_budget: int | None = None
    token_limit: int | None = None
    timeout_seconds: int = 45
    retry_count: int = 0
    fallback_provider_type: str | None = None
    fallback_model_string: str | None = None
    input_policy: dict[str, object] = field(default_factory=dict)
    output_policy: dict[str, object] = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ("text_generation",)

    @classmethod
    def from_stage(cls, stage: PipelineVersionStage) -> PipelineStageConfiguration:
        return cls(
            stable_identifier=stage.stable_identifier,
            name=stage.name,
            description=stage.description,
            enabled=stage.enabled,
            position=stage.position,
            provider_type=stage.provider_type,
            model_string=stage.model_string,
            system_prompt_directives=stage.system_prompt_directives,
            prerequisite_dependencies=tuple(stage.prerequisite_dependencies),
            is_terminal=stage.is_terminal,
            temperature=stage.temperature,
            thinking_budget=stage.thinking_budget,
            token_limit=stage.token_limit,
            timeout_seconds=stage.timeout_seconds,
            retry_count=stage.retry_count,
            fallback_provider_type=stage.fallback_provider_type,
            fallback_model_string=stage.fallback_model_string,
            input_policy=dict(stage.input_policy),
            output_policy=dict(stage.output_policy),
            required_capabilities=tuple(stage.required_capabilities),
        )


@dataclass(frozen=True, slots=True)
class PipelinePublicationResult:
    """Publication attempt and the resulting active-state decision."""

    version: PipelineVersion
    validation: PipelineValidationResult
    published: bool


class PipelineControlService:
    """Coordinate immutable version history through one database transaction."""

    def __init__(self, validator: PipelineVersionValidator | None = None) -> None:
        self._validator = validator or PipelineVersionValidator()

    async def create_draft(
        self,
        session: AsyncSession,
        *,
        created_by_user_id: int,
        change_description: str,
        source_version_id: int | None = None,
    ) -> PipelineVersion:
        source = (
            await PipelineVersionRepository.require(session, source_version_id)
            if source_version_id is not None
            else await PipelineVersionRepository.require_current_published(session)
        )
        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=created_by_user_id,
            change_description=change_description,
            state="draft",
        )
        await self._add_configurations(
            session,
            version_id=version.id,
            configurations=[PipelineStageConfiguration.from_stage(stage) for stage in source.stages],
        )
        await session.refresh(version, attribute_names=["stages"])
        return version

    async def save_draft(
        self,
        session: AsyncSession,
        *,
        pipeline_version_id: int,
        change_description: str,
        stages: list[PipelineStageConfiguration],
    ) -> PipelineVersion:
        version = await PipelineVersionRepository.require(session, pipeline_version_id, for_update=True)
        self._require_draft(version)
        for stage in list(version.stages):
            await session.delete(stage)
        await session.flush()
        version.change_description = change_description.strip()
        version.validation_status = "pending"
        version.validation_issues = []
        version.validated_at = None
        await self._add_configurations(session, version_id=version.id, configurations=stages)
        await session.refresh(version, attribute_names=["stages"])
        return version

    async def validate_draft(
        self,
        session: AsyncSession,
        *,
        pipeline_version_id: int,
    ) -> tuple[PipelineVersion, PipelineValidationResult]:
        version = await PipelineVersionRepository.require(session, pipeline_version_id, for_update=True)
        self._require_draft(version)
        result = await self._validator.validate(session, version.stages)
        await PipelineVersionRepository.record_validation(
            session,
            version=version,
            valid=result.is_valid,
            issues=[issue.to_payload() for issue in result.issues],
        )
        return version, result

    async def publish_draft(
        self,
        session: AsyncSession,
        *,
        pipeline_version_id: int,
    ) -> PipelinePublicationResult:
        version, validation = await self.validate_draft(
            session,
            pipeline_version_id=pipeline_version_id,
        )
        if not validation.is_valid:
            return PipelinePublicationResult(version=version, validation=validation, published=False)

        current = await PipelineVersionRepository.get_current_published(session, for_update=True)
        if current is not None and current.id != version.id:
            current.state = "superseded"
        version.state = "published"
        version.published_at = datetime.now(timezone.utc)
        await session.flush()
        return PipelinePublicationResult(version=version, validation=validation, published=True)

    async def rollback_to_version(
        self,
        session: AsyncSession,
        *,
        source_version_id: int,
        created_by_user_id: int,
        change_description: str,
    ) -> PipelinePublicationResult:
        source = await PipelineVersionRepository.require(session, source_version_id)
        if source.state == "draft":
            raise PipelineControlConflictError("Rollback sources must have been published previously.")
        draft = await self.create_draft(
            session,
            created_by_user_id=created_by_user_id,
            source_version_id=source.id,
            change_description=change_description or f"Rollback to pipeline version {source.version_number}",
        )
        return await self.publish_draft(session, pipeline_version_id=draft.id)

    async def delete_draft(
        self,
        session: AsyncSession,
        *,
        pipeline_version_id: int,
    ) -> None:
        version = await PipelineVersionRepository.require(session, pipeline_version_id, for_update=True)
        self._require_draft(version)
        await session.delete(version)
        await session.flush()

    @staticmethod
    def _require_draft(version: PipelineVersion) -> None:
        if version.state != "draft":
            raise PipelineControlConflictError(
                f"Pipeline version {version.version_number} is immutable because it is {version.state}."
            )

    @staticmethod
    async def _add_configurations(
        session: AsyncSession,
        *,
        version_id: int,
        configurations: list[PipelineStageConfiguration],
    ) -> None:
        for configuration in configurations:
            await PipelineVersionRepository.add_stage(
                session,
                pipeline_version_id=version_id,
                stable_identifier=configuration.stable_identifier,
                name=configuration.name,
                description=configuration.description,
                enabled=configuration.enabled,
                position=configuration.position,
                provider_type=configuration.provider_type,
                model_string=configuration.model_string,
                system_prompt_directives=configuration.system_prompt_directives,
                prerequisite_dependencies=list(configuration.prerequisite_dependencies),
                is_terminal=configuration.is_terminal,
                temperature=configuration.temperature,
                thinking_budget=configuration.thinking_budget,
                token_limit=configuration.token_limit,
                timeout_seconds=configuration.timeout_seconds,
                retry_count=configuration.retry_count,
                fallback_provider_type=configuration.fallback_provider_type,
                fallback_model_string=configuration.fallback_model_string,
                input_policy=configuration.input_policy,
                output_policy=configuration.output_policy,
                required_capabilities=list(configuration.required_capabilities),
            )
