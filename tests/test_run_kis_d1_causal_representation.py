from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_cpu_runner_uses_explicit_offline_mounts_and_safe_output(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    dataset = object()
    contract = SimpleNamespace(contract_sha256="sha256:" + "c" * 64)
    result = SimpleNamespace(
        phase="cpu_smoke",
        status="completed",
        device="cpu",
        steps_completed=4,
        training_loss_finite=True,
        training_loss_decreased=True,
        diagnostic_loss_finite=True,
        summary_sha256="sha256:" + "a" * 64,
        weights_sha256="sha256:" + "b" * 64,
        registry_outcome=None,
    )
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "model-artifacts"

    def load_dataset(**kwargs: object) -> object:
        assert kwargs == {
            "manifest_path": (
                market_data_root
                / "us_equities"
                / "kis_paper_private"
                / "daily-nas-history-panel"
                / "v1"
                / "panel=7e8d6fe54dd5252fc4b9"
                / "manifest.json"
            ),
            "cache_root": (
                market_data_root
                / "us_equities"
                / "kis_paper_private"
                / "daily-nas-history"
                / "v1"
            ),
            "panel_root": (
                market_data_root
                / "us_equities"
                / "kis_paper_private"
                / "daily-nas-history-panel"
                / "v1"
            ),
            "repo_root": script._REPOSITORY_ROOT,
        }
        return dataset

    def freeze(candidate: object, **kwargs: object) -> object:
        assert candidate is dataset
        assert kwargs["artifact_root"] == artifact_root
        assert kwargs["repo_root"] == script._REPOSITORY_ROOT
        assert kwargs["attempt_id"] == "unit-r2"
        assert str(kwargs["code_revision"]).startswith("sha256:")
        return contract

    monkeypatch.setattr(script, "load_kis_d1_causal_representation_dataset", load_dataset)
    monkeypatch.setattr(script, "freeze_kis_d1_causal_representation_campaign", freeze)
    monkeypatch.setattr(
        script,
        "run_kis_d1_causal_representation_cpu_smoke",
        lambda candidate: result if candidate is contract else None,
    )

    script.main(
        [
            "--mode",
            "cpu-smoke",
            "--market-data-root",
            str(market_data_root),
            "--artifact-root",
            str(artifact_root),
            "--attempt-id",
            "unit-r2",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "campaign_id": "kis-d1-causal-representation-feasibility-v1",
        "contract_sha256": "sha256:" + "c" * 64,
        "device": "cpu",
        "diagnostic_loss_finite": True,
        "phase": "cpu_smoke",
        "registry_outcome_sha256": None,
        "status": "completed",
        "steps_completed": 4,
        "summary_sha256": "sha256:" + "a" * 64,
        "training_loss_decreased": True,
        "training_loss_finite": True,
        "weights_sha256": "sha256:" + "b" * 64,
    }


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_kis_d1_causal_representation.py"
    spec = importlib.util.spec_from_file_location("run_kis_d1_causal_representation_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
