from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_script_uses_only_the_daily_kis_loader_and_prints_sanitized_summary(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    run_root = artifact_root / "historical-kis-daily-cpu-baseline" / "script-contract-r2"
    source = object()
    daily_catalog = SimpleNamespace(bars_by_symbol={"QQQ": source})
    campaign = SimpleNamespace()
    contract_path = run_root / "campaign-contract.json"
    result = SimpleNamespace()
    summary = {
        "status": "complete",
        "mode": "offline_local_paper",
        "input": {
            "dataset_id": "kis.paper.private.daily.backfill-v1.common-panel",
            "dataset_hash": "sha256:" + "a" * 64,
        },
    }

    def validate_label(value: str) -> None:
        assert value == "script-contract-r2"

    def validate_root(path: Path, *, repo_root: Path) -> Path:
        assert path == artifact_root
        assert repo_root == script._REPO_ROOT
        return artifact_root

    def load_catalog(**kwargs: object) -> object:
        assert kwargs == {
            "cache_root": tmp_path / "market-data",
            "repo_root": script._REPO_ROOT,
            "target_keys": script.HISTORICAL_KIS_DAILY_TARGET_KEYS,
        }
        return daily_catalog

    def build_campaign(
        loaded: object,
        *,
        artifact_root: Path,
        repo_root: Path,
    ) -> object:
        assert loaded is source
        assert artifact_root == tmp_path / "model-artifacts"
        assert repo_root == script._REPO_ROOT
        return campaign

    def write_contract(
        received_campaign: object,
        *,
        path: Path,
        repo_root: Path,
    ) -> Path:
        assert received_campaign is campaign
        assert path == contract_path
        assert repo_root == script._REPO_ROOT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        return path

    def run_baselines(
        received_campaign: object,
        *,
        contract_path: Path,
        work_root: Path,
        repo_root: Path,
        run_label: str,
    ) -> object:
        assert received_campaign is campaign
        assert contract_path == run_root / "campaign-contract.json"
        assert work_root == run_root / "work"
        assert repo_root == script._REPO_ROOT
        assert run_label == "script-contract-r2"
        return result

    def build_summary(received_result: object, *, run_label: str) -> dict[str, object]:
        assert received_result is result
        assert run_label == "script-contract-r2"
        return summary

    def write_summary(
        received_summary: dict[str, object],
        *,
        path: Path,
        artifact_root: Path,
        repo_root: Path,
    ) -> Path:
        assert received_summary is summary
        assert path == run_root / "summary.json"
        assert artifact_root == tmp_path / "model-artifacts"
        assert repo_root == script._REPO_ROOT
        path.write_text(json.dumps(summary), encoding="utf-8")
        return path

    monkeypatch.setattr(script, "validate_historical_kis_run_label", validate_label)
    monkeypatch.setattr(script, "validate_historical_kis_artifact_root", validate_root)
    monkeypatch.setattr(script, "load_kis_paper_private_daily_catalog", load_catalog)
    monkeypatch.setattr(script, "build_historical_kis_daily_campaign", build_campaign)
    monkeypatch.setattr(script, "write_frozen_historical_kis_campaign_contract", write_contract)
    monkeypatch.setattr(script, "run_historical_kis_daily_cpu_baselines", run_baselines)
    monkeypatch.setattr(script, "build_sanitized_historical_kis_summary", build_summary)
    monkeypatch.setattr(script, "write_sanitized_historical_kis_summary", write_summary)

    script.main(
        [
            "--symbol",
            "QQQ",
            "--run-label",
            "script-contract-r2",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output == summary
    assert json.loads((run_root / "summary.json").read_text(encoding="utf-8")) == summary
    assert "source_path" not in json.dumps(output)
    assert "credential" not in json.dumps(output)


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "run_historical_kis_cpu_baseline.py"
    spec = importlib.util.spec_from_file_location(
        "run_historical_kis_cpu_baseline_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
