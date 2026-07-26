from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_runner_uses_only_the_external_artifact_root(monkeypatch, capsys, tmp_path: Path) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    summary_path = (
        artifact_root / "kis-paper-daily-universe-cpu-baseline-v1" / "unit-r1" / "summary.json"
    )

    def run_baseline(*, artifact_root: Path, run_label: str, repo_root: Path) -> object:
        assert artifact_root == tmp_path / "model-artifacts"
        assert run_label == "unit-r1"
        assert repo_root == script._REPO_ROOT
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(
            json.dumps({"mode": "offline_cpu_local_paper", "reporting": {"winner": None}}),
            encoding="utf-8",
        )
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "run_kis_paper_daily_universe_cpu_baseline", run_baseline)

    script.main(
        [
            "--run-label",
            "unit-r1",
            "--artifact-root",
            str(artifact_root),
        ]
    )

    assert json.loads(capsys.readouterr().out) == json.loads(
        summary_path.read_text(encoding="utf-8")
    )


def test_runner_rejects_reused_evidence_label(tmp_path: Path) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    (artifact_root / "kis-paper-daily-universe-cpu-baseline-v1" / "already-used").mkdir(
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
    path = Path(__file__).parents[1] / "scripts" / "run_kis_paper_daily_universe_cpu_baseline.py"
    source = path.read_text(encoding="utf-8").lower()
    for forbidden in (".env", "kis_paper_app_key", "requests", "socket", "urllib"):
        assert forbidden not in source
    spec = importlib.util.spec_from_file_location(
        "run_kis_paper_daily_universe_cpu_baseline_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
