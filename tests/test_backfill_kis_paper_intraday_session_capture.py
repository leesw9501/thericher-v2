from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

from thericher_v2.execution.kis_private_intraday_backfill import (
    KisPaperPrivateIntradayBackfillRun,
)


def test_session_capture_script_builds_one_client_and_preserves_qqq_preparation_handoff(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("KIS_PAPER_ACCOUNT_NO", "must-not-be-used")
    monkeypatch.setenv("KIS_LIVE_APP_KEY", "must-not-be-used")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("dotenv must stay unread")),
    )
    clients: list[object] = []

    def paper_client(**kwargs: object) -> object:
        assert kwargs["max_minute_page_attempts"] == 2
        client = object()
        clients.append(client)
        return client

    runs = (
        KisPaperPrivateIntradayBackfillRun(
            status="collected",
            target_key="QQQ/NAS/1m",
            row_count=240,
            exact_overlap_rows=0,
        ),
        KisPaperPrivateIntradayBackfillRun(
            status="collected",
            target_key="SPY/AMS/1m",
            row_count=240,
            exact_overlap_rows=0,
        ),
    )

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["client"] is clients[0]
        assert kwargs["cache_root"] == (
            tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday-head"
        )
        assert kwargs["resume_cursor"] is False
        assert kwargs["pages_per_target"] == 1
        return runs

    captured: dict[str, object] = {}

    def finalize(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(
            outcome=SimpleNamespace(
                safe_payload=lambda: {
                    "collection_mode": "session_capture",
                    "route_class": "kis_paper_market_data",
                    "status": "complete",
                }
            )
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)
    monkeypatch.setattr(script, "build_and_write_kis_paper_intraday_session_capture", finalize)
    preparations: list[dict[str, object]] = []
    monkeypatch.setattr(
        script,
        "_prepare_head_observation",
        lambda **kwargs: preparations.append(kwargs) or {"status": "pending"},
    )
    artifact_root = tmp_path / "model-artifacts"

    assert (
        script.main(
            [
                "--execute",
                "--mode",
                "session-capture",
                "--pages-per-target",
                "1",
                "--preparation-artifact-root",
                str(artifact_root),
            ],
            clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
            code_revision=lambda _: "git:test",
        )
        == 0
    )

    assert len(clients) == 1
    assert captured == {
        "runs": runs,
        "cache_root": tmp_path
        / "market-data"
        / "us_equities"
        / "kis_paper_private"
        / "intraday-head",
        "repository_root": script._REPO_ROOT,
        "observed_at": datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    }
    assert preparations == [
        {
            "head_cache_root": tmp_path
            / "market-data"
            / "us_equities"
            / "kis_paper_private"
            / "intraday-head",
            "artifact_root": artifact_root,
        }
    ]
    assert json.loads(capsys.readouterr().out) == {
        "collection_mode": "session_capture",
        "mode": "session-capture",
        "preparation": {"status": "pending"},
        "route_class": "kis_paper_market_data",
        "status": "complete",
    }


def test_session_capture_prepares_qqq_even_when_spy_makes_the_cycle_incomplete(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "_load_paper_config", lambda _: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "run_kis_paper_private_intraday_backfill_cycle",
        lambda **_kwargs: (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="rejected",
                target_key="SPY/AMS/1m",
                row_count=0,
                exact_overlap_rows=0,
                reason="collector_incomplete",
            ),
        ),
    )
    monkeypatch.setattr(
        script,
        "build_and_write_kis_paper_intraday_session_capture",
        lambda **_kwargs: SimpleNamespace(
            outcome=SimpleNamespace(
                safe_payload=lambda: {
                    "collection_mode": "session_capture",
                    "route_class": "kis_paper_market_data",
                    "status": "complete",
                }
            )
        ),
    )
    preparations: list[object] = []
    monkeypatch.setattr(
        script,
        "_prepare_head_observation",
        lambda **kwargs: preparations.append(kwargs) or {"status": "pending"},
    )

    assert (
        script.main(
            ["--execute", "--mode", "session-capture"],
            code_revision=lambda _: "git:test",
        )
        == 1
    )

    assert len(preparations) == 1
    assert json.loads(capsys.readouterr().out) == {
        "collection_mode": "session_capture",
        "mode": "session-capture",
        "preparation": {"status": "pending"},
        "route_class": "kis_paper_market_data",
        "status": "complete",
    }


def test_session_capture_preparation_fault_does_not_change_collector_success(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "_load_paper_config", lambda _: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "run_kis_paper_private_intraday_backfill_cycle",
        lambda **_kwargs: (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="SPY/AMS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        ),
    )
    monkeypatch.setattr(
        script,
        "build_and_write_kis_paper_intraday_session_capture",
        lambda **_kwargs: SimpleNamespace(
            outcome=SimpleNamespace(
                safe_payload=lambda: {
                    "collection_mode": "session_capture",
                    "route_class": "kis_paper_market_data",
                    "status": "complete",
                }
            )
        ),
    )
    monkeypatch.setattr(
        script,
        "_prepare_head_observation",
        lambda **_kwargs: {
            "status": "preparation_unavailable",
            "reason": "child_exit_nonzero",
        },
    )

    assert (
        script.main(
            ["--execute", "--mode", "session-capture"],
            code_revision=lambda _: "git:test",
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {
        "collection_mode": "session_capture",
        "mode": "session-capture",
        "preparation": {
            "reason": "child_exit_nonzero",
            "status": "preparation_unavailable",
        },
        "route_class": "kis_paper_market_data",
        "status": "complete",
    }


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_private_intraday.py"
    spec = importlib.util.spec_from_file_location(
        "backfill_kis_paper_private_intraday_session_capture_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
