from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_ema_replay_script_uses_only_local_cache_and_external_artifacts(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    source = object()
    artifact_root = tmp_path / "model-artifacts"
    summary_path = artifact_root / "research" / "ema" / "unit-r1" / "summary.json"
    expected = {
        "artifact_policy": {"network_called": False, "raw_market_data_written": False},
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
        return source

    def run_replay(
        catalog: object,
        *,
        artifact_root: Path,
        run_label: str,
    ) -> SimpleNamespace:
        assert catalog is source
        assert artifact_root == tmp_path / "model-artifacts"
        assert run_label == "unit-r1"
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(json.dumps(expected), encoding="utf-8")
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    monkeypatch.setattr(script, "run_kis_intraday_session_reset_ema_replay", run_replay)

    script.main(
        [
            "--run-label",
            "unit-r1",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    output = capsys.readouterr().out
    assert json.loads(output) == expected
    assert "price" not in output
    assert "KIS_PAPER_" not in output


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_kis_intraday_ema_replay.py"
    spec = importlib.util.spec_from_file_location("run_kis_intraday_ema_replay_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
