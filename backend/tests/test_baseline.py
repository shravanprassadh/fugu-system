from __future__ import annotations

import json
from pathlib import Path

import pytest

from fugu.baseline import BaselineDriftError, collect_repository_baseline, verify_repository_baseline


def test_repository_matches_committed_baseline() -> None:
    baseline = verify_repository_baseline()

    assert baseline["api"]["title"] == "Fugu Modular Kernel API"
    assert baseline["database"]["alembic_head"] == "0005_provider_credential_validation"
    assert baseline["database"]["current_table_target"] == "master"


def test_baseline_verification_rejects_undocumented_drift(tmp_path: Path) -> None:
    recorded = collect_repository_baseline()
    recorded["api"]["operations"] = recorded["api"]["operations"][:-1]
    contract_path = tmp_path / "drifted-contract.json"
    contract_path.write_text(json.dumps(recorded), encoding="utf-8")

    with pytest.raises(BaselineDriftError, match="Repository baseline drift detected"):
        verify_repository_baseline(contract_path=contract_path)
