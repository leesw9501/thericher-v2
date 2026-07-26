from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

from thericher_v2.research.historical_kis_campaign import HISTORICAL_KIS_DAILY_TARGET_KEYS


def test_control_script_uses_pinned_offline_pair_and_external_artifacts(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    source = object()
    artifact_root = tmp_path / "model-artifacts"
    summary_path = (
        artifact_root / "kis-daily-l2-logistic-control-v1" / "unit-r1" / "summary.json"
    )

    def load_catalog(**kwargs: object) -> object:
        assert kwargs == {
            "cache_root": tmp_path / "market-data",
            "target_keys": HISTORICAL_KIS_DAILY_TARGET_KEYS,
            "expected_index_hash": script.KIS_DAILY_SEQUENCE_EXPECTED_INDEX_HASH,
            "expected_full_dataset_hash": script.KIS_DAILY_SEQUENCE_EXPECTED_FULL_DATASET_HASH,
            "repo_root": script._REPO_ROOT,
        }
        return source

    def run_control(
        catalog: object,
        *,
        artifact_root: Path,
        run_label: str,
        repo_root: Path,
    ) -> object:
        assert catalog is source
        assert artifact_root == tmp_path / "model-artifacts"
        assert run_label == "unit-r1"
        assert repo_root == script._REPO_ROOT
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(
            json.dumps(
                {
                    "mode": "offline_cpu_local_paper",
                    "reporting": {"winner": None},
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "load_kis_paper_private_daily_catalog", load_catalog)
    monkeypatch.setattr(script, "run_kis_daily_l2_logistic_control", run_control)

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

    assert json.loads(capsys.readouterr().out) == json.loads(
        summary_path.read_text(encoding="utf-8")
    )


def test_control_script_rejects_reused_external_label(tmp_path: Path) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    (artifact_root / "kis-daily-l2-logistic-control-v1" / "already-used").mkdir(
        parents=True
    )

    try:
        script.main(
            [
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
    path = Path(__file__).parents[1] / "scripts" / "run_kis_daily_l2_logistic_control.py"
    source = path.read_text(encoding="utf-8")
    assert ".env" not in source
    assert "KIS_PAPER_APP_KEY" not in source
    assert "torch" not in source
    spec = importlib.util.spec_from_file_location(
        "run_kis_daily_l2_logistic_control_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
