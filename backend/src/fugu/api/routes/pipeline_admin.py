"""Administrative API for immutable pipeline version history."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from fugu.api.dependencies import AdminUser, MasterSession
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import PipelineVersion, PipelineVersionStage
from fugu.database.repositories import PipelineVersionRepository
from fugu.pipelines import (
    PipelineControlConflictError,
    PipelineControlService,
    PipelineStageConfiguration,
    PipelineValidationResult,
)

pipeline_admin_router = APIRouter(prefix="/api/admin/pipeline-versions", tags=["pipeline administration"])

PipelineVersionState = Literal["draft", "published", "superseded"]
PipelineValidationState = Literal["pending", "valid", "invalid"]


class PipelineStagePayload(BaseModel):
    """Complete editable configuration for one pipeline draft stage."""

    stable_identifier: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4_000)
    enabled: bool = True
    position: int = Field(ge=1, le=10_000)
    provider_type: str = Field(min_length=2, max_length=100)
    model_string: str = Field(min_length=1, max_length=255)
    system_prompt_directives: str = Field(default="", max_length=24_000)
    prerequisite_dependencies: list[str] = Field(default_factory=list, max_length=100)
    is_terminal: bool = False
    temperature: float | None = None
    thinking_budget: int | None = Field(default=None, ge=0)
    token_limit: int | None = Field(default=None, ge=1)
    timeout_seconds: int = Field(default=45, ge=1, le=3_600)
    retry_count: int = Field(default=0, ge=0, le=10)
    fallback_provider_type: str | None = Field(default=None, max_length=100)
    fallback_model_string: str | None = Field(default=None, max_length=255)
    input_policy: dict[str, object] = Field(default_factory=dict)
    output_policy: dict[str, object] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=lambda: ["text_generation"], max_length=20)

    @field_validator("stable_identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("provider_type")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("name", "model_string", "system_prompt_directives", "description")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("fallback_provider_type", "fallback_model_string")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @field_validator("prerequisite_dependencies", "required_capabilities")
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        return [item.strip().lower() for item in value if item.strip()]

    def to_configuration(self) -> PipelineStageConfiguration:
        return PipelineStageConfiguration(
            stable_identifier=self.stable_identifier,
            name=self.name,
            description=self.description,
            enabled=self.enabled,
            position=self.position,
            provider_type=self.provider_type,
            model_string=self.model_string,
            system_prompt_directives=self.system_prompt_directives,
            prerequisite_dependencies=tuple(self.prerequisite_dependencies),
            is_terminal=self.is_terminal,
            temperature=self.temperature,
            thinking_budget=self.thinking_budget,
            token_limit=self.token_limit,
            timeout_seconds=self.timeout_seconds,
            retry_count=self.retry_count,
            fallback_provider_type=self.fallback_provider_type,
            fallback_model_string=self.fallback_model_string,
            input_policy=self.input_policy,
            output_policy=self.output_policy,
            required_capabilities=tuple(self.required_capabilities),
        )


class PipelineStageResponse(BaseModel):
    """One version-owned pipeline stage returned to the builder."""

    id: int
    stable_identifier: str
    name: str
    description: str
    enabled: bool
    position: int
    provider_type: str
    model_string: str
    system_prompt_directives: str
    prerequisite_dependencies: list[str]
    is_terminal: bool
    temperature: float | None
    thinking_budget: int | None
    token_limit: int | None
    timeout_seconds: int
    retry_count: int
    fallback_provider_type: str | None
    fallback_model_string: str | None
    input_policy: dict[str, object]
    output_policy: dict[str, object]
    required_capabilities: list[str]

    @classmethod
    def from_stage(cls, stage: PipelineVersionStage) -> PipelineStageResponse:
        return cls(
            id=stage.id,
            stable_identifier=stage.stable_identifier,
            name=stage.name,
            description=stage.description,
            enabled=stage.enabled,
            position=stage.position,
            provider_type=stage.provider_type,
            model_string=stage.model_string,
            system_prompt_directives=stage.system_prompt_directives,
            prerequisite_dependencies=list(stage.prerequisite_dependencies),
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
            required_capabilities=list(stage.required_capabilities),
        )


class PipelineVersionSummaryResponse(BaseModel):
    """Compact version history entry."""

    id: int
    version_number: int
    state: PipelineVersionState
    change_description: str
    validation_status: PipelineValidationState
    validation_issues: list[dict[str, object]]
    stage_count: int
    created_by_user_id: int | None
    created_at: datetime
    validated_at: datetime | None
    published_at: datetime | None

    @classmethod
    def from_version(cls, version: PipelineVersion) -> PipelineVersionSummaryResponse:
        return cls(
            id=version.id,
            version_number=version.version_number,
            state=version.state,
            change_description=version.change_description,
            validation_status=version.validation_status,
            validation_issues=list(version.validation_issues),
            stage_count=len(version.stages),
            created_by_user_id=version.created_by_user_id,
            created_at=version.created_at,
            validated_at=version.validated_at,
            published_at=version.published_at,
        )


class PipelineVersionResponse(PipelineVersionSummaryResponse):
    """Complete version and ordered stage configuration."""

    stages: list[PipelineStageResponse]

    @classmethod
    def from_version(cls, version: PipelineVersion) -> PipelineVersionResponse:
        summary = PipelineVersionSummaryResponse.from_version(version)
        return cls(
            **summary.model_dump(),
            stages=[
                PipelineStageResponse.from_stage(stage)
                for stage in sorted(version.stages, key=lambda item: item.position)
            ],
        )


class CreatePipelineDraftPayload(BaseModel):
    """Create a new draft by cloning an existing or current published version."""

    source_version_id: int | None = Field(default=None, ge=1)
    change_description: str = Field(min_length=1, max_length=4_000)


class SavePipelineDraftPayload(BaseModel):
    """Replace one draft's complete configuration atomically."""

    change_description: str = Field(min_length=1, max_length=4_000)
    stages: list[PipelineStagePayload] = Field(min_length=1, max_length=100)


class RollbackPipelinePayload(BaseModel):
    """Create and publish a new version copied from historical configuration."""

    change_description: str = Field(default="", max_length=4_000)


class PipelineValidationResponse(BaseModel):
    """Stored draft validation outcome."""

    version: PipelineVersionResponse
    valid: bool
    issues: list[dict[str, object]]

    @classmethod
    def from_result(
        cls,
        version: PipelineVersion,
        result: PipelineValidationResult,
    ) -> PipelineValidationResponse:
        return cls(
            version=PipelineVersionResponse.from_version(version),
            valid=result.is_valid,
            issues=[issue.to_payload() for issue in result.issues],
        )


class PipelinePublicationResponse(PipelineValidationResponse):
    """Publication or rollback attempt."""

    published: bool


async def _require_version(session: MasterSession, version_id: int) -> PipelineVersion:
    try:
        return await PipelineVersionRepository.require(session, version_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline version not found.") from exc


def _conflict(exc: PipelineControlConflictError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _publication_payload(
    version: PipelineVersion,
    result: PipelineValidationResult,
    *,
    published: bool,
) -> dict[str, object]:
    return PipelinePublicationResponse(
        version=PipelineVersionResponse.from_version(version),
        valid=result.is_valid,
        issues=[issue.to_payload() for issue in result.issues],
        published=published,
    ).model_dump(mode="json")


@pipeline_admin_router.get("", response_model=list[PipelineVersionSummaryResponse])
async def list_pipeline_versions(
    _: AdminUser,
    session: MasterSession,
) -> list[PipelineVersionSummaryResponse]:
    """List draft and immutable historical pipeline versions newest first."""
    versions = await PipelineVersionRepository.list_versions(session)
    return [PipelineVersionSummaryResponse.from_version(version) for version in versions]


@pipeline_admin_router.get("/{version_id}", response_model=PipelineVersionResponse)
async def get_pipeline_version(
    version_id: int,
    _: AdminUser,
    session: MasterSession,
) -> PipelineVersionResponse:
    """Return one complete pipeline version for inspection or draft editing."""
    return PipelineVersionResponse.from_version(await _require_version(session, version_id))


@pipeline_admin_router.post("/drafts", response_model=PipelineVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline_draft(
    payload: CreatePipelineDraftPayload,
    current_admin: AdminUser,
    session: MasterSession,
) -> PipelineVersionResponse:
    """Clone the current or selected pipeline version into a mutable draft."""
    try:
        version = await PipelineControlService().create_draft(
            session,
            created_by_user_id=current_admin.id,
            source_version_id=payload.source_version_id,
            change_description=payload.change_description,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PipelineVersionResponse.from_version(version)


@pipeline_admin_router.put("/{version_id}", response_model=PipelineVersionResponse)
async def save_pipeline_draft(
    version_id: int,
    payload: SavePipelineDraftPayload,
    _: AdminUser,
    session: MasterSession,
) -> PipelineVersionResponse:
    """Replace the complete content of one mutable draft."""
    try:
        version = await PipelineControlService().save_draft(
            session,
            pipeline_version_id=version_id,
            change_description=payload.change_description,
            stages=[stage.to_configuration() for stage in payload.stages],
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineControlConflictError as exc:
        raise _conflict(exc) from exc
    return PipelineVersionResponse.from_version(version)


@pipeline_admin_router.post("/{version_id}/validate", response_model=PipelineValidationResponse)
async def validate_pipeline_draft(
    version_id: int,
    _: AdminUser,
    session: MasterSession,
) -> PipelineValidationResponse:
    """Validate and persist all publication-blocking draft issues."""
    try:
        version, result = await PipelineControlService().validate_draft(
            session,
            pipeline_version_id=version_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineControlConflictError as exc:
        raise _conflict(exc) from exc
    return PipelineValidationResponse.from_result(version, result)


@pipeline_admin_router.post("/{version_id}/publish")
async def publish_pipeline_draft(
    version_id: int,
    _: AdminUser,
    session: MasterSession,
) -> PipelinePublicationResponse | JSONResponse:
    """Validate and atomically make a draft the sole current published pipeline."""
    try:
        publication = await PipelineControlService().publish_draft(
            session,
            pipeline_version_id=version_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineControlConflictError as exc:
        raise _conflict(exc) from exc
    payload = _publication_payload(
        publication.version,
        publication.validation,
        published=publication.published,
    )
    if not publication.published:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)
    return PipelinePublicationResponse.model_validate(payload)


@pipeline_admin_router.post("/{version_id}/rollback")
async def rollback_pipeline_version(
    version_id: int,
    payload: RollbackPipelinePayload,
    current_admin: AdminUser,
    session: MasterSession,
) -> PipelinePublicationResponse | JSONResponse:
    """Publish a new version copied from a previously published configuration."""
    try:
        publication = await PipelineControlService().rollback_to_version(
            session,
            source_version_id=version_id,
            created_by_user_id=current_admin.id,
            change_description=payload.change_description,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineControlConflictError as exc:
        raise _conflict(exc) from exc
    response_payload = _publication_payload(
        publication.version,
        publication.validation,
        published=publication.published,
    )
    if not publication.published:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=response_payload)
    return PipelinePublicationResponse.model_validate(response_payload)


@pipeline_admin_router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_pipeline_draft(
    version_id: int,
    _: AdminUser,
    session: MasterSession,
) -> Response:
    """Delete only an unpublished draft; immutable history cannot be removed."""
    try:
        await PipelineControlService().delete_draft(session, pipeline_version_id=version_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineControlConflictError as exc:
        raise _conflict(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
