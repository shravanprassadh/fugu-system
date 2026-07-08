"""Alembic configuration resolution tests."""

from pathlib import Path

import pytest
from fugu.boot.migrations import MigrationError, _resolve_alembic_config


def test_alembic_config_resolves_from_runtime_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Installed packages must still use the deployment working directory."""
    config_path = tmp_path / "alembic.ini"
    config_path.write_text("[alembic]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALEMBIC_CONFIG", raising=False)

    assert _resolve_alembic_config() == config_path.resolve()


def test_alembic_config_honors_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Operators may point the migration runner at a non-default config."""
    config_path = tmp_path / "custom-alembic.ini"
    config_path.write_text("[alembic]\n", encoding="utf-8")
    monkeypatch.setenv("ALEMBIC_CONFIG", str(config_path))

    assert _resolve_alembic_config() == config_path.resolve()


def test_missing_alembic_config_fails_before_database_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A missing deployment config should produce a precise startup error."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALEMBIC_CONFIG", raising=False)

    with pytest.raises(MigrationError, match="Could not find Alembic configuration"):
        _resolve_alembic_config()
