from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

from thericher_v2.execution.kis_private_intraday_backfill import (
    KisPaperPrivateIntradayBackfillRun,
)


def test_session_capture_script_builds_one_client_and_never_starts_research(
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
    monkeypatch.setattr(
        script,
        "_prepare_head_observation",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("research must not start")),
    )

    assert (
        script.main(
            ["--execute", "--mode", "session-capture", "--pages-per-target", "1"],
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
    assert json.loads(capsys.readouterr().out) == {
        "collection_mode": "session_capture",
        "mode": "session-capture",
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
