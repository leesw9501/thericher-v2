from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_window_feasibility_script_uses_local_cache_and_external_receipt(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    source = object()
    receipt = object()
    artifact_root = tmp_path / "window-artifacts"
    precommit_path = tmp_path / "mechanics" / "precommit.json"
    mechanics_summary_path = tmp_path / "mechanics" / "summary.json"
    summary_path = artifact_root / "data" / "window" / "unit-r1" / "summary.json"
    expected = {
        "artifact_policy": {"network_called": False, "raw_market_data_written": False},
        "mode": "offline_existing_local_catalog_only",
        "status": "complete",
    }

    def load_catalog(**kwargs: object) -> object:
        assert kwargs == {
            "cache_root": tmp_path / "market-data",
            "repo_root": script._REPO_ROOT,
            "symbol": "QQQ",
            "exchange": "NAS",
        }
        return source

    def load_receipt(**kwargs: object) -> object:
        assert kwargs == {
            "precommit_path": precommit_path,
            "summary_path": mechanics_summary_path,
            "repo_root": script._REPO_ROOT,
        }
        return receipt

    def run_feasibility(
        catalog: object,
        *,
        mechanics_receipt: object,
        artifact_root: Path,
        run_label: str,
        repo_root: Path,
    ) -> SimpleNamespace:
        assert catalog is source
        assert mechanics_receipt is receipt
        assert artifact_root == tmp_path / "window-artifacts"
        assert run_label == "unit-r1"
        assert repo_root == script._REPO_ROOT
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(json.dumps(expected), encoding="utf-8")
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    monkeypatch.setattr(script, "load_kis_qqq_mtf_mechanics_receipt", load_receipt)
    monkeypatch.setattr(script, "run_kis_qqq_mtf_window_feasibility", run_feasibility)

    script.main(
        [
            "--run-label",
            "unit-r1",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(artifact_root),
            "--mechanics-precommit",
            str(precommit_path),
            "--mechanics-summary",
            str(mechanics_summary_path),
        ]
    )

    output = capsys.readouterr().out
    assert json.loads(output) == expected
    assert "price" not in output
    assert "KIS_PAPER_" not in output


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_kis_qqq_mtf_window_feasibility.py"
    spec = importlib.util.spec_from_file_location("run_kis_qqq_mtf_window_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
