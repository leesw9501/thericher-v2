from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize("fold_id", ("expanding-1", "expanding-2", "expanding-3"))
def test_runner_stays_offline_when_its_external_inputs_are_injected(
    monkeypatch,
    capsys,
    tmp_path: Path,
    fold_id: str,
) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    fold_pin = script._SCREEN_FOLD_PINS[fold_id]
    materializer = SimpleNamespace(
        materializer_identity="sha256:" + "a" * 64,
        fold_input=SimpleNamespace(fold_input_identity="sha256:" + "b" * 64),
    )
    target_adapter = SimpleNamespace(target_cost_identity=fold_pin.target_cost_identity)
    summary_path = (
        artifact_root
        / script.KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
        / f"unit-{fold_id}"
        / "summary.json"
    )

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate-only script must not use network or environment access")

    def load_materializer(**kwargs: object) -> object:
        assert kwargs == {
            "artifact_root": artifact_root,
            "fold_id": fold_id,
            "parent_artifact": artifact_root / "research-contracts" / script._PARENT_ARTIFACT_NAME,
            "fold_artifact": artifact_root / "research-contracts" / fold_pin.fold_artifact_name,
            "market_data_root": tmp_path / "market-data",
        }
        return materializer

    def build_adapter(*, materializer: object) -> object:
        assert materializer is materializer_source
        return target_adapter

    def attest(**kwargs: object) -> None:
        assert kwargs == {
            "path": artifact_root / "research-contracts" / fold_pin.target_cost_artifact_name,
            "artifact_root": artifact_root,
            "materializer_identity": materializer.materializer_identity,
            "fold_input_identity": materializer.fold_input.fold_input_identity,
            "target_cost_identity": target_adapter.target_cost_identity,
            "expected_target_cost_receipt_sha256": fold_pin.target_cost_receipt_sha256,
            "expected_target_cost_identity": fold_pin.target_cost_identity,
        }

    def run_screen(**kwargs: object) -> object:
        assert kwargs == {
            "materializer": materializer,
            "target_adapter": target_adapter,
            "artifact_root": artifact_root,
            "run_label": f"unit-{fold_id}",
            "mode": "cpu-smoke",
            "repo_root": script._REPO_ROOT,
        }
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(
            json.dumps(
                {
                    "scope": {
                        "candidate_only": True,
                        "candidate_selection_eligible": False,
                        "replay_materialized": False,
                        "paper_decision_eligible": False,
                    }
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(summary_path=summary_path)

    materializer_source = materializer
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(
        script,
        "load_pinned_kis_daily_joint_event_d1_materializer",
        load_materializer,
    )
    monkeypatch.setattr(script, "build_kis_daily_joint_event_d1_target_cost_adapter", build_adapter)
    monkeypatch.setattr(script, "_attest_target_cost_receipt", attest)
    monkeypatch.setattr(script, "run_kis_daily_joint_event_d1_sequence_screen", run_screen)

    script.main(
        [
            "--mode",
            "cpu-smoke",
            "--run-label",
            f"unit-{fold_id}",
            "--fold-id",
            fold_id,
            "--artifact-root",
            str(artifact_root),
            "--market-data-root",
            str(tmp_path / "market-data"),
        ]
    )

    assert json.loads(capsys.readouterr().out) == json.loads(
        summary_path.read_text(encoding="utf-8")
    )


def test_expanding_3_runner_pin_matches_the_frozen_external_contract() -> None:
    script = _load_script()

    assert script._SCREEN_FOLD_PINS["expanding-3"] == script._ScreenFoldPin(
        fold_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-3-v1.json"
        ),
        target_cost_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-3-validation-first-v2.json"
        ),
        target_cost_receipt_sha256=(
            "sha256:4c389d437ed5c6ad35908dd98e1639e8ab17d41db889a7e5d1d6437c78961560"
        ),
        target_cost_identity=(
            "sha256:5511c3f072e81debe81c39792d6ca4b9500773ebf0d4029b9c7d501286176cc3"
        ),
    )


def test_runner_rejects_a_reused_external_label(tmp_path: Path) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    (artifact_root / script.KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID / "already-used").mkdir(
        parents=True
    )

    try:
        script.main(
            [
                "--mode",
                "cpu-smoke",
                "--run-label",
                "already-used",
                "--artifact-root",
                str(artifact_root),
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("reused label should terminate through argparse")


def _load_script() -> ModuleType:
    scripts_path = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts_path))
    try:
        path = scripts_path / "run_kis_daily_joint_event_d1_sequence_screen.py"
        spec = importlib.util.spec_from_file_location(
            "run_kis_daily_joint_event_d1_sequence_screen_for_test",
            path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            return module
        finally:
            sys.modules.pop(spec.name, None)
    finally:
        sys.path.remove(str(scripts_path))
