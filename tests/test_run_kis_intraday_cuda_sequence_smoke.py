from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_cuda_sequence_script_uses_kis_cache_and_external_artifacts(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    session_dates = tuple(date(2026, 6, day) for day in range(1, 21))
    source = object()
    artifact_root = tmp_path / "model-artifacts"
    summary_path = artifact_root / "kis-intraday-cuda-sequence-smoke" / "unit-r1" / "summary.json"

    def load_catalog(**kwargs: object) -> object:
        assert kwargs == {
            "cache_root": tmp_path / "market-data",
            "repo_root": script._REPO_ROOT,
            "symbol": "QQQ",
            "exchange": "NAS",
        }
        return source

    def run_smoke(
        catalog: object,
        *,
        session_dates: tuple[date, ...],
        artifact_root: Path,
        run_label: str,
        repo_root: Path,
    ) -> object:
        assert catalog is source
        assert session_dates == tuple(date(2026, 6, day) for day in range(1, 21))
        assert artifact_root == tmp_path / "model-artifacts"
        assert run_label == "unit-r1"
        assert repo_root == script._REPO_ROOT
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(
            json.dumps({"mode": "offline_cuda_research", "checkpoint_written": False}),
            encoding="utf-8",
        )
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    monkeypatch.setattr(script, "run_kis_intraday_cuda_sequence_smoke", run_smoke)

    args = ["--run-label", "unit-r1"]
    for session_date in session_dates:
        args.extend(("--session-date", session_date.isoformat()))
    args.extend(("--cache-root", str(tmp_path / "market-data")))
    args.extend(("--artifact-root", str(artifact_root)))
    script.main(args)

    assert json.loads(capsys.readouterr().out) == json.loads(
        summary_path.read_text(encoding="utf-8")
    )


def test_cuda_sequence_script_rejects_a_reused_label(tmp_path: Path) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    (artifact_root / "kis-intraday-cuda-sequence-smoke" / "already-used").mkdir(
        parents=True
    )

    try:
        script.main(
            [
                "--run-label",
                "already-used",
                "--session-date",
                "2026-06-01",
                "--artifact-root",
                str(artifact_root),
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("reused label should terminate through argparse")


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_kis_intraday_cuda_sequence_smoke.py"
    spec = importlib.util.spec_from_file_location("run_kis_intraday_cuda_sequence_smoke_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
