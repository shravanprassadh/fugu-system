"""Render deployment contract tests."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_render_blueprint_installs_package_and_uses_supported_entrypoint() -> None:
    """Render must install the package and start through the migration-aware launcher."""
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "rootDir: backend" in blueprint
    assert "requirements-runtime.txt" in blueprint
    assert "python -m pip install --no-deps ." in blueprint
    assert "startCommand: bash ./entrypoint.sh" in blueprint
    assert "healthCheckPath: /api/health/live" in blueprint


def test_entrypoint_honors_render_port_and_worker_variables() -> None:
    """Render-provided runtime variables must override local defaults."""
    entrypoint = (REPOSITORY_ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")

    assert 'WEB_WORKERS_COUNT="${WEB_WORKERS_COUNT:-${WEB_CONCURRENCY:-2}}"' in entrypoint
    assert 'SERVER_BIND_PORT="${SERVER_BIND_PORT:-${PORT:-8000}}"' in entrypoint
    assert "fugu.main:app" in entrypoint
    assert "python -m fugu.boot.migrations" in entrypoint
