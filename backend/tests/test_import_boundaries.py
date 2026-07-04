"""Regression tests for startup-safe package import boundaries."""

from __future__ import annotations

import subprocess
import sys


def test_boot_config_import_does_not_initialize_database_connections() -> None:
    """Configuration must import without re-entering the connection module."""
    script = "import sys; import fugu.boot.config; assert 'fugu.database.connection' not in sys.modules"

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_database_package_preserves_lazy_public_exports() -> None:
    """Existing package-level imports remain available after removing eager imports."""
    from fugu import database

    assert database.Base is not None
    assert database.DatabaseSessionRegistry is not None
    assert database.DatabaseTarget is not None
    assert callable(database.get_session_registry)
