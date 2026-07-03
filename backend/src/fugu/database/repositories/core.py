"""Typed repository operations for Fugu's core relational entities."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import (
    Message,
    PipelineRun,
    PipelineStep,
    PipelineStepRun,
    ProviderCredential,
    Thread,
    User,
)


class UserRepository:
    """Persistence operations for authenticated users."""

    @staticmethod
    async def add(
        session: AsyncSession,
        *,
        username: str,
        password_hash: str,
        role: str = "user",
    ) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> User | None:
        statement = select(User).where(User.username == username)
        result = await session.scalars(statement)
        return result.one_or_none()

    @staticmethod
    async def increment_token_version(session: AsyncSession, user: User) -> int:
        """Revoke every existing token by advancing the user's session version."""
        user.token_version += 1
        await session.flush()
        return user.token_version


class ThreadRepository:
    """Persistence operations for user-owned conversation threads."""

    @staticmethod
    async def add(session: AsyncSession, *, user_id: int, name: str) -> Thread:
        thread = Thread(user_id=user_id, name=name)
        session.add(thread)
        await session.flush()
        return thread

    @staticmethod
    async def get_owned(session: AsyncSession, *, thread_id: int, user_id: int) -> Thread | None:
        statement = select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
        result = await session.scalars(statement)
        return result.one_or_none()

    @staticmethod
    async def require_owned(session: AsyncSession, *, thread_id: int, user_id: int) -> Thread:
        thread = await ThreadRepository.get_owned(session, thread_id=thread_id, user_id=user_id)
        if thread is None:
            raise EntityNotFoundError("Thread does not exist within the authenticated user's scope.")
        return thread

    @staticmethod
    async def list_owned(session: AsyncSession, *, user_id: int) -> list[Thread]:
        statement = select(Thread).where(Thread.user_id == user_id).order_by(Thread.created_at.desc())
        result = await session.scalars(statement)
        return list(result.all())


class MessageRepository:
    """Persistence operations for messages scoped through thread ownership."""

    @staticmethod
    async def add(
        session: AsyncSession,
        *,
        thread_id: int,
        user_id: int,
        role: str,
        content: str,
    ) -> Message:
        await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
        message = Message(thread_id=thread_id, role=role, content=content)
        session.add(message)
        await session.flush()
        return message

    @staticmethod
    async def list_for_thread(
        session: AsyncSession,
        *,
        thread_id: int,
        user_id: int,
    ) -> list[Message]:
        await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=user_id)
        statement = select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at.asc())
        result = await session.scalars(statement)
        return list(result.all())


class ProviderCredentialRepository:
    """Persistence operations for encrypted provider credentials."""

    @staticmethod
    async def add(
        session: AsyncSession,
        *,
        provider_name: str,
        encrypted_secret: str,
        key_version: int = 1,
    ) -> ProviderCredential:
        credential = ProviderCredential(
            provider_name=provider_name,
            encrypted_secret=encrypted_secret,
            key_version=key_version,
        )
        session.add(credential)
        await session.flush()
        return credential

    @staticmethod
    async def get_by_provider(session: AsyncSession, provider_name: str) -> ProviderCredential | None:
        statement = select(ProviderCredential).where(ProviderCredential.provider_name == provider_name)
        result = await session.scalars(statement)
        return result.one_or_none()


class PipelineRepository:
    """Persistence operations for pipeline definitions and execution traces."""

    @staticmethod
    async def list_steps(session: AsyncSession) -> list[PipelineStep]:
        statement = select(PipelineStep).order_by(PipelineStep.sequence_order_position.asc())
        result = await session.scalars(statement)
        return list(result.all())

    @staticmethod
    async def create_run(
        session: AsyncSession,
        *,
        thread_id: int,
        status: str = "running",
    ) -> PipelineRun:
        pipeline_run = PipelineRun(thread_id=thread_id, status=status)
        session.add(pipeline_run)
        await session.flush()
        return pipeline_run

    @staticmethod
    async def get_run(session: AsyncSession, run_id: int) -> PipelineRun | None:
        return await session.get(PipelineRun, run_id)

    @staticmethod
    async def require_run(session: AsyncSession, run_id: int) -> PipelineRun:
        pipeline_run = await PipelineRepository.get_run(session, run_id)
        if pipeline_run is None:
            raise EntityNotFoundError(f"Pipeline run {run_id} does not exist.")
        return pipeline_run

    @staticmethod
    async def add_step_run(
        session: AsyncSession,
        *,
        run_id: int,
        step_name: str,
        status: str = "pending",
    ) -> PipelineStepRun:
        step_run = PipelineStepRun(run_id=run_id, step_name=step_name, status=status)
        session.add(step_run)
        await session.flush()
        return step_run

    @staticmethod
    async def get_step_run(
        session: AsyncSession,
        *,
        run_id: int,
        step_name: str,
    ) -> PipelineStepRun | None:
        statement = select(PipelineStepRun).where(
            PipelineStepRun.run_id == run_id,
            PipelineStepRun.step_name == step_name,
        )
        result = await session.scalars(statement)
        return result.one_or_none()

    @staticmethod
    async def require_step_run(
        session: AsyncSession,
        *,
        run_id: int,
        step_name: str,
    ) -> PipelineStepRun:
        step_run = await PipelineRepository.get_step_run(
            session,
            run_id=run_id,
            step_name=step_name,
        )
        if step_run is None:
            raise EntityNotFoundError(
                f"Pipeline step trace {step_name!r} for run {run_id} does not exist."
            )
        return step_run

    @staticmethod
    async def mark_step_running(
        session: AsyncSession,
        *,
        run_id: int,
        step_name: str,
    ) -> PipelineStepRun:
        step_run = await PipelineRepository.require_step_run(
            session,
            run_id=run_id,
            step_name=step_name,
        )
        step_run.status = "running"
        step_run.error_message = None
        await session.flush()
        return step_run

    @staticmethod
    async def mark_step_completed(
        session: AsyncSession,
        *,
        run_id: int,
        step_name: str,
        output_trace: str,
    ) -> PipelineStepRun:
        step_run = await PipelineRepository.require_step_run(
            session,
            run_id=run_id,
            step_name=step_name,
        )
        step_run.status = "completed"
        step_run.output_trace = output_trace
        step_run.error_message = None
        step_run.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return step_run

    @staticmethod
    async def mark_step_failed(
        session: AsyncSession,
        *,
        run_id: int,
        step_name: str,
        output_trace: str,
        error_message: str,
    ) -> PipelineStepRun:
        step_run = await PipelineRepository.require_step_run(
            session,
            run_id=run_id,
            step_name=step_name,
        )
        step_run.status = "failed"
        step_run.output_trace = output_trace
        step_run.error_message = error_message
        step_run.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return step_run

    @staticmethod
    async def mark_run_completed(
        session: AsyncSession,
        *,
        run_id: int,
    ) -> PipelineRun:
        pipeline_run = await PipelineRepository.require_run(session, run_id)
        pipeline_run.status = "completed"
        pipeline_run.error_code = None
        pipeline_run.error_message = None
        pipeline_run.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return pipeline_run

    @staticmethod
    async def mark_run_failed(
        session: AsyncSession,
        *,
        run_id: int,
        error_code: str,
        error_message: str,
    ) -> PipelineRun:
        pipeline_run = await PipelineRepository.require_run(session, run_id)
        pipeline_run.status = "failed"
        pipeline_run.error_code = error_code
        pipeline_run.error_message = error_message
        pipeline_run.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return pipeline_run
