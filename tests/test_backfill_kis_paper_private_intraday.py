from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

from thericher_v2.execution.kis_private_intraday_backfill import (
    KisPaperPrivateIntradayBackfillRun,
)


def test_intraday_backfill_script_requires_explicit_execution_without_credentials(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_load_paper_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    script.main([])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_intraday_project_only_writes_metadata_without_reading_credentials(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    projected: dict[str, object] = {}
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    monkeypatch.setattr(
        script,
        "_load_paper_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )
    monkeypatch.setattr(
        script,
        "build_kis_paper_private_intraday_freshness_snapshot",
        lambda **kwargs: projected.setdefault("build", kwargs) or object(),
    )
    monkeypatch.setattr(
        script,
        "write_market_data_freshness_runtime",
        lambda snapshot, path: projected.update({"snapshot": snapshot, "path": path}),
    )

    projection_path = tmp_path / "runtime" / "freshness.json"
    script.main(
        ["--project-only", "--runtime-projection", str(projection_path)],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    )

    assert json.loads(capsys.readouterr().out) == {
        "scope": "backfill_and_head",
        "status": "freshness_projected",
    }
    assert projected["build"] == {
        "cache_root": tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday",
        "repo_root": script._REPO_ROOT,
        "observed_at": datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    }
    assert projected["path"] == projection_path


def test_intraday_backfill_script_uses_only_injected_paper_values(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("dotenv must stay unread")),
    )

    def paper_client(**kwargs: object) -> object:
        config = kwargs["config"]
        assert config.app_key == "paper-key"
        assert config.app_secret == "paper-secret"
        assert kwargs["max_minute_page_attempts"] == 2
        return object()

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["cache_root"] == (
            tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday"
        )
        assert kwargs["pages_per_target"] == 1
        assert kwargs["resume_cursor"] is True
        return (
            KisPaperPrivateIntradayBackfillRun(
                status="recovered",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)

    script.main(
        ["--execute", "--pages-per-target", "1"],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    )

    assert json.loads(capsys.readouterr().out) == {
        "mode": "backfill",
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "recovered",
                "target_key": "QQQ/NAS/1m",
            }
        ],
    }


def test_intraday_head_script_uses_a_separate_cache_without_resuming_cursor(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))

    def paper_client(**_kwargs: object) -> object:
        return object()

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["cache_root"] == (
            tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday-head"
        )
        assert kwargs["pages_per_target"] == 1
        assert kwargs["resume_cursor"] is False
        return (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)

    script.main(
        ["--execute", "--mode", "head", "--pages-per-target", "1"],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    )

    assert json.loads(capsys.readouterr().out) == {
        "mode": "head",
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "QQQ/NAS/1m",
            }
        ],
    }


def test_intraday_historical_probe_uses_a_separate_cache_without_seed_cursor(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))

    def paper_client(**_kwargs: object) -> object:
        return object()

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["cache_root"] == (
            tmp_path
            / "market-data"
            / "us_equities"
            / "kis_paper_private"
            / "intraday-historical-probe"
        )
        assert kwargs["pages_per_target"] == 1
        assert kwargs["resume_cursor"] is False
        return (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)

    script.main(
        ["--execute", "--mode", "historical-probe", "--pages-per-target", "1"],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    )

    assert json.loads(capsys.readouterr().out) == {
        "mode": "historical-probe",
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "QQQ/NAS/1m",
            }
        ],
    }


def test_intraday_backfill_script_rejects_live_mode_before_reading_config(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setenv("THERICHER_MODE", "live")
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("config must stay unread")),
    )

    script.main(["--execute"])

    assert json.loads(capsys.readouterr().out) == {
        "reason": "config_missing",
        "status": "not_executed",
    }


def test_current_code_revision_marks_staged_or_untracked_work_dirty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    script = _load_script()
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="test-revision\n")
        assert args == ["git", "status", "--porcelain", "--untracked-files=normal"]
        return SimpleNamespace(stdout="M  staged-file.py\n")

    monkeypatch.setattr(script.subprocess, "run", run)

    assert script._current_code_revision(tmp_path) == "git:test-revision+dirty"
    assert calls == [
        ["git", "rev-parse", "HEAD"],
        ["git", "status", "--porcelain", "--untracked-files=normal"],
    ]


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_private_intraday.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_kis_paper_private_intraday_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
