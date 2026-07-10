"""Persistence operations for versioned pipeline definitions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import PipelineStep, PipelineVersion, PipelineVersionStage


class PipelineVersionRepository:
    """Typed persistence operations for pipeline versions and owned stages."""

    @staticmethod
    async def next_version_number(session: AsyncSession) -> int:
        value = await session.scalar(select(func.max(PipelineVersion.version_number)))
        return int(value or 0) + 1

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        created_by_user_id: int | None,
        change_description: str,
        state: str = "draft",
    ) -> PipelineVersion:
        version = PipelineVersion(
            version_number=await PipelineVersionRepository.next_version_number(session),
            state=state,
            created_by_user_id=created_by_user_id,
            change_description=change_description.strip(),
            validation_status="pending",
            validation_issues=[],
        )
        session.add(version)
        await session.flush()
        return version

    @staticmethod
    async def add_stage(
        session: AsyncSession,
        *,
        pipeline_version_id: int,
        stable_identifier: str,
        name: str,
        description: str,
        enabled: bool,
        position: int,
        provider_type: str,
        model_string: str,
        system_prompt_directives: str,
        prerequisite_dependencies: list[str],
        is_terminal: bool,
        temperature: float | None = None,
        thinking_budget: int | None = None,
        token_limit: int | None = None,
        timeout_seconds: int = 45,
        retry_count: int = 0,
        fallback_provider_type: str | None = None,
        fallback_model_string: str | None = None,
        input_policy: dict[str, object] | None = None,
        output_policy: dict[str, object] | None = None,
        required_capabilities: list[str] | None = None,
    ) -> PipelineVersionStage:
        stage = PipelineVersionStage(
            pipeline_version_id=pipeline_version_id,
            stable_identifier=stable_identifier.strip(),
            name=name.strip(),
            description=description.strip(),
            enabled=enabled,
            position=position,
            provider_type=provider_type.strip().lower(),
            model_string=model_string.strip(),
            system_prompt_directives=system_prompt_directives.strip(),
            prerequisite_dependencies=[value.strip() for value in prerequisite_dependencies if value.strip()],
            is_terminal=is_terminal,
            temperature=temperature,
            thinking_budget=thinking_budget,
            token_limit=token_limit,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            fallback_provider_type=(fallback_provider_type or "").strip().lower() or None,
            fallback_model_string=(fallback_model_string or "").strip() or None,
            input_policy=dict(input_policy or {}),
            output_policy=dict(output_policy or {}),
            required_capabilities=list(required_capabilities or []),
        )
        session.add(stage)
        await session.flush()
        return stage

    @staticmethod
    async def get(
        session: AsyncSession,
        pipeline_version_id: int,
    ) -> PipelineVersion | None:
        statement = (
            select(PipelineVersion)
            .options(selectinload(PipelineVersion.stages))
            .where(PipelineVersion.id == pipeline_version_id)
        )
        result = await session.scalars(statement)
        return result.one_or_none()

    @staticmethod
    async def require(
        session: AsyncSession,
        pipeline_version_id: int,
    ) -> PipelineVersion:
        version = await PipelineVersionRepository.get(session, pipeline_version_id)
        if version is None:
            raise EntityNotFoundError(f"Pipeline version {pipeline_version_id} does not exist.")
        return version

    @staticmethod
    async def get_current_published(session: AsyncSession) -> PipelineVersion | None:
        statement = (
            select(PipelineVersion)
            .options(selectinload(PipelineVersion.stages))
            .where(
                PipelineVersion.state == "published",
                PipelineVersion.validation_status == "valid",
            )
            .order_by(PipelineVersion.version_number.desc())
            .limit(1)
        )
        result = await session.scalars(statement)
        return result.one_or_none()

    @staticmethod
    async def require_current_published(session: AsyncSession) -> PipelineVersion:
        version = await PipelineVersionRepository.get_current_published(session)
        if version is None:
            raise EntityNotFoundError("No valid published pipeline version is available for execution.")
        return version

    @staticmethod
    async def import_legacy_steps(
        session: AsyncSession,
        *,
        steps: list[PipelineStep],
    ) -> PipelineVersion:
        """Convert an unversioned baseline once for metadata-created or pre-migration databases."""
        current = await PipelineVersionRepository.get_current_published(session)
        if current is not None:
            return current
        if not steps:
            raise EntityNotFoundError("No valid published pipeline version is available for execution.")

        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=None,
            change_description="Imported legacy pipeline configuration",
            state="published",
        )
        now = datetime.now(timezone.utc)
        version.validation_status = "valid"
        version.validation_issues = []
        version.validated_at = now
        version.published_at = now
        for step in steps:
            await PipelineVersionRepository.add_stage(
                session,
                pipeline_version_id=version.id,
                stable_identifier=step.step_name,
                name=step.step_name,
                description="Imported from the legacy pipeline definition.",
                enabled=True,
                position=step.sequence_order_position,
                provider_type=step.provider_type,
                model_string=step.model_string,
                system_prompt_directives=step.system_prompt_directives or "",
                prerequisite_dependencies=list(step.prerequisite_dependencies),
                is_terminal=step.is_terminal,
                required_capabilities=["text_generation"],
            )
        await session.refresh(version, attribute_names=["stages"])
        return version

    @staticmethod
    async def record_validation(
        session: AsyncSession,
        *,
        version: PipelineVersion,
        valid: bool,
        issues: list[dict[str, object]],
    ) -> PipelineVersion:
        version.validation_status = "valid" if valid else "invalid"
        version.validation_issues = issues
        version.validated_at = datetime.now(timezone.utc)
        await session.flush()
        return version
