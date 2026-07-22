from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_script_prints_metadata_only_preparation_result(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "model-artifacts"

    def prepare(**kwargs: object) -> object:
        assert kwargs == {
            "head_cache_root": head_cache_root,
            "artifact_root": artifact_root,
            "run_label": "unit-r1",
            "repo_root": script._REPO_ROOT,
        }
        return SimpleNamespace(to_payload=lambda: {"status": "pending", "raw_bars_read": False})

    monkeypatch.setattr(script, "prepare_kis_intraday_prospective_head_observation", prepare)

    script.main(
        [
            "--run-label",
            "unit-r1",
            "--head-cache-root",
            str(head_cache_root),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    assert json.loads(capsys.readouterr().out) == {"raw_bars_read": False, "status": "pending"}


def _load_script() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "prepare_kis_intraday_prospective_head_observation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "prepare_kis_intraday_prospective_head_observation_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
