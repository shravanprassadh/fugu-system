"""Repository baseline collection and drift validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from alembic.config import Config
from alembic.script import Script, ScriptDirectory
from fugu.database.connection import DatabaseTarget
from fugu.database.models import Base
from fugu.main import create_app

_HTTP_METHODS = frozenset({"delete", "get", "patch", "post", "put"})
_DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONTRACT_PATH = _DEFAULT_REPOSITORY_ROOT / "docs" / "baseline" / "system-contract.json"
_DEFAULT_BACKEND_ROOT = _DEFAULT_REPOSITORY_ROOT / "backend"


class BaselineDriftError(RuntimeError):
    """Raised when code and migrations no longer match the recorded baseline."""


def _api_contract() -> dict[str, Any]:
    schema = create_app().openapi()
    operations: list[dict[str, str]] = []
    for path, path_item in schema["paths"].items():
        for method in path_item:
            if method.lower() in _HTTP_METHODS:
                operations.append({"method": method.upper(), "path": path})
    operations.sort(key=lambda item: (item["path"], item["method"]))
    return {
        "title": schema["info"]["title"],
        "version": schema["info"]["version"],
        "operations": operations,
    }


def _alembic_chain(backend_root: Path) -> tuple[str, list[str]]:
    configuration = Config(str(backend_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(configuration)
    heads = scripts.get_heads()
    if len(heads) != 1:
        rendered_heads = ", ".join(sorted(heads)) or "none"
        raise BaselineDriftError(f"Expected one Alembic head, found: {rendered_heads}.")

    head = heads[0]
    reverse_chain: list[str] = []
    current: Script | None = scripts.get_revision(head)
    while current is not None:
        reverse_chain.append(current.revision)
        parent = current.down_revision
        if isinstance(parent, (tuple, list)):
            raise BaselineDriftError(
                f"Alembic revision {current.revision!r} has multiple parents; the baseline requires a linear chain."
            )
        current = scripts.get_revision(parent) if parent is not None else None
    return head, list(reversed(reverse_chain))


def collect_repository_baseline(*, backend_root: Path = _DEFAULT_BACKEND_ROOT) -> dict[str, Any]:
    """Collect the non-secret API, migration, schema, and routing baseline."""
    head, chain = _alembic_chain(backend_root)
    return {
        "api": _api_contract(),
        "database": {
            "alembic_head": head,
            "alembic_chain": chain,
            "tables": sorted(Base.metadata.tables),
            "runtime_targets": [target.value for target in DatabaseTarget],
            "current_table_target": DatabaseTarget.MASTER.value,
        },
    }


def load_recorded_baseline(*, contract_path: Path = _DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    """Load the committed baseline contract."""
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BaselineDriftError(f"Recorded baseline {contract_path} must contain a JSON object.")
    return cast(dict[str, Any], payload)


def verify_repository_baseline(
    *,
    contract_path: Path = _DEFAULT_CONTRACT_PATH,
    backend_root: Path = _DEFAULT_BACKEND_ROOT,
) -> dict[str, Any]:
    """Reject undocumented API, schema, migration, or target drift."""
    expected = load_recorded_baseline(contract_path=contract_path)
    actual = collect_repository_baseline(backend_root=backend_root)
    if actual != expected:
        expected_text = json.dumps(expected, indent=2, sort_keys=True)
        actual_text = json.dumps(actual, indent=2, sort_keys=True)
        raise BaselineDriftError(
            "Repository baseline drift detected. Update the implementation or deliberately refresh "
            f"{contract_path}.\n\nExpected:\n{expected_text}\n\nActual:\n{actual_text}"
        )
    return actual
