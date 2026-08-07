from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_pnl_attribution_script_uses_local_cache_and_external_parent_receipt(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    catalog = object()
    parent_receipt = object()
    parent_precommit = tmp_path / "parent" / "precommit.json"
    parent_summary = tmp_path / "parent" / "summary.json"
    artifact_root = tmp_path / "attribution-artifacts"
    summary_path = artifact_root / "research" / "attribution" / "unit-r1" / "summary.json"
    expected = {
        "artifact_policy": {"network_called": False, "raw_fill_events_retained": False},
        "mode": "offline_local_cache_local_paper_only",
        "status": "complete",
    }

    def load_catalog(**kwargs: object) -> object:
        assert kwargs == {
            "cache_root": tmp_path / "market-data",
            "repo_root": script._REPO_ROOT,
            "symbol": "QQQ",
            "exchange": "NAS",
        }
        return catalog

    def load_parent_receipt(**kwargs: object) -> object:
        assert kwargs == {
            "precommit_path": parent_precommit,
            "summary_path": parent_summary,
            "repo_root": script._REPO_ROOT,
        }
        return parent_receipt

    def run_attribution(
        received_catalog: object,
        *,
        parent_receipt: object,
        artifact_root: Path,
        run_label: str,
        repo_root: Path,
    ) -> SimpleNamespace:
        assert received_catalog is catalog
        assert parent_receipt is globals_parent_receipt
        assert artifact_root == tmp_path / "attribution-artifacts"
        assert run_label == "unit-r1"
        assert repo_root == script._REPO_ROOT
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(json.dumps(expected), encoding="utf-8")
        return SimpleNamespace(summary_path=summary_path)

    globals_parent_receipt = parent_receipt
    monkeypatch.setattr(script, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    monkeypatch.setattr(script, "load_kis_intraday_ema_replay_receipt", load_parent_receipt)
    monkeypatch.setattr(script, "run_source_local_ema_local_paper_pnl_attribution", run_attribution)

    script.main(
        [
            "--run-label",
            "unit-r1",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(artifact_root),
            "--parent-precommit",
            str(parent_precommit),
            "--parent-summary",
            str(parent_summary),
        ]
    )

    output = capsys.readouterr().out
    assert json.loads(output) == expected
    assert "price" not in output
    assert "KIS_PAPER_" not in output


def _load_script() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "run_source_local_ema_local_paper_pnl_attribution.py"
    )
    spec = importlib.util.spec_from_file_location("run_ema_pnl_attribution_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
