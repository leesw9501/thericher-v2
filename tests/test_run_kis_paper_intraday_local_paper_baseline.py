from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

from thericher_v2.contracts import Timeframe


def test_baseline_script_writes_a_sanitized_external_local_paper_summary(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    source = object()
    session_source = object()
    artifact_root = tmp_path / "model-artifacts"

    def load_catalog(**kwargs: object) -> object:
        assert kwargs["cache_root"] == tmp_path / "market-data"
        assert kwargs["symbol"] == "QQQ"
        assert kwargs["exchange"] == "NAS"
        return source

    def require_complete(catalog: object, *, session: object) -> object:
        assert catalog is source
        assert session.open_ts == datetime(2026, 7, 21, 13, 30, tzinfo=UTC)  # type: ignore[attr-defined]
        return session_source

    def run_baseline(
        catalog: object,
        *,
        run_id: str,
        work_root: Path,
        repo_root: Path,
        session: object,
    ) -> SimpleNamespace:
        assert catalog is session_source
        assert run_id == "unit-session"
        assert work_root == artifact_root
        assert repo_root == script._REPO_ROOT
        assert session.close_ts == datetime(2026, 7, 21, 20, 0, tzinfo=UTC)  # type: ignore[attr-defined]
        return SimpleNamespace(
            dataset_id="kis.paper.private.intraday.qqq.nas.m1.v1",
            dataset_hash="sha256:" + "a" * 64,
            cells=(
                SimpleNamespace(
                    timeframe=Timeframe.M1,
                    status="completed",
                    resampled_bar_count=390,
                    local_paper_fill_count=2,
                    event_jsonl_sha256="sha256:" + "b" * 64,
                    all_fills_local_paper=True,
                ),
            ),
        )

    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_private_intraday_catalog",
        load_catalog,
    )
    monkeypatch.setattr(
        script,
        "require_complete_kis_paper_private_intraday_session",
        require_complete,
    )
    monkeypatch.setattr(script, "run_intraday_multitimeframe_local_paper_baseline", run_baseline)

    script.main(
        [
            "--session-date",
            "2026-07-21",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(artifact_root),
            "--run-id",
            "unit-session",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    summary_path = (
        artifact_root
        / "intraday-multitimeframe-baseline"
        / "unit-session"
        / "summary.json"
    )
    assert output == json.loads(summary_path.read_text(encoding="utf-8"))
    assert output["mode"] == "offline_local_paper"
    assert output["all_fills_local_paper"] is True
    assert output["cells"] == [
        {
            "event_jsonl_sha256": "sha256:" + "b" * 64,
            "local_paper_fill_count": 2,
            "resampled_bar_count": 390,
            "status": "completed",
            "timeframe": "1m",
        }
    ]
    assert "price" not in json.dumps(output)
    assert "credential" not in json.dumps(output)


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).parents[1]
        / "scripts"
        / "run_kis_paper_intraday_local_paper_baseline.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_kis_paper_intraday_local_paper_baseline_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
