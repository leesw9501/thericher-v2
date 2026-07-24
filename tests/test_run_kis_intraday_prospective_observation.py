from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_script_reports_missing_pair_as_pending_without_opening_a_cache(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()

    def fail_loader(**_kwargs: object) -> object:
        raise AssertionError("missing pair must not open a cache")

    monkeypatch.setattr(script, "load_kis_intraday_prospective_observation_input", fail_loader)

    result = script.main(
        [
            "--preparation-dir",
            str(tmp_path / "missing-pair"),
            "--historical-cache-root",
            str(tmp_path / "historical"),
            "--head-cache-root",
            str(tmp_path / "head"),
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_intraday_prospective_observation",
        "status": "pending",
        "reason": "preparation_pair_missing",
    }


def test_script_runs_only_verified_input_and_prints_safe_summary(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    historical_cache_root = tmp_path / "historical"
    head_cache_root = tmp_path / "head"
    preparation_dir = tmp_path / "preparation"
    artifact_root = tmp_path / "artifacts"
    preparation_dir.mkdir()
    for name in ("precommit.json", "planning-receipt.json"):
        (preparation_dir / name).write_text("{}", encoding="utf-8")
    observation_input = object()
    summary_path = artifact_root / "summary.json"
    summary_path.parent.mkdir()
    summary_path.write_text(
        json.dumps({"mode": "offline_local_paper", "broker_order_submitted": False}),
        encoding="utf-8",
    )

    def load_input(**kwargs: object) -> object:
        assert kwargs == {
            "historical_cache_root": historical_cache_root,
            "head_cache_root": head_cache_root,
            "preparation_dir": preparation_dir,
            "repo_root": script._REPO_ROOT,
        }
        return observation_input

    def run_observation(
        supplied_input: object,
        *,
        artifact_root: Path,
        repo_root: Path,
    ) -> object:
        assert supplied_input is observation_input
        assert artifact_root == artifact_root_argument
        assert repo_root == script._REPO_ROOT
        return SimpleNamespace(summary_path=summary_path)

    artifact_root_argument = artifact_root
    monkeypatch.setattr(script, "load_kis_intraday_prospective_observation_input", load_input)
    monkeypatch.setattr(script, "run_kis_intraday_prospective_observation", run_observation)

    result = script.main(
        [
            "--historical-cache-root",
            str(historical_cache_root),
            "--head-cache-root",
            str(head_cache_root),
            "--preparation-dir",
            str(preparation_dir),
            "--artifact-root",
            str(artifact_root_argument),
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_intraday_prospective_observation",
        "status": "complete",
        "summary": {"mode": "offline_local_paper", "broker_order_submitted": False},
    }


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_kis_intraday_prospective_observation.py"
    spec = importlib.util.spec_from_file_location(
        "run_kis_intraday_prospective_observation_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
