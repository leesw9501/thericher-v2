from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import thericher_v2.execution.kis_private_intraday_backfill as private_intraday_backfill
from thericher_v2.execution.kis_market_data import (
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    KisPaperPrivateIntradayBackfillRun,
)


def test_session_capture_script_builds_one_client_and_preserves_qqq_preparation_handoff(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    schedule_run_id = "intraday-head-20260722T0500000000000Z"
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
        assert kwargs["quarantine_retained_head_conflicts"] is True
        return runs

    captured: dict[str, object] = {}

    def finalize(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(
            safe_output_payload=lambda: {
                "collection_mode": "session_capture",
                "route_class": "kis_paper_market_data",
                "status": "complete",
                "terminal_receipt_binding": {
                    "schedule_run_id": schedule_run_id,
                    "observed_at": "2026-07-22T05:00:00+00:00",
                    "receipt_sha256": "sha256:" + "e" * 64,
                    "current_session_cumulative_coverage_digest": "sha256:" + "c" * 64,
                    "current_session_cumulative_coverage_category": "complete",
                },
            }
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
                "--schedule-run-id",
                schedule_run_id,
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
        "schedule_run_id": schedule_run_id,
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
        "terminal_receipt_binding": {
            "schedule_run_id": schedule_run_id,
            "observed_at": "2026-07-22T05:00:00+00:00",
            "receipt_sha256": "sha256:" + "e" * 64,
            "current_session_cumulative_coverage_digest": "sha256:" + "c" * 64,
            "current_session_cumulative_coverage_category": "complete",
        },
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
            safe_output_payload=lambda: {
                "collection_mode": "session_capture",
                "route_class": "kis_paper_market_data",
                "status": "complete",
            }
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


def test_session_capture_rejects_an_invalid_schedule_run_id_before_collector_setup(
    monkeypatch,
) -> None:
    script = _load_script()
    setup_attempted = False

    def load_config(_dotenv_path: Path) -> object:
        nonlocal setup_attempted
        setup_attempted = True
        return object()

    monkeypatch.setattr(script, "_load_paper_config", load_config)

    with pytest.raises(SystemExit):
        script.main(
            [
                "--execute",
                "--mode",
                "session-capture",
                "--schedule-run-id",
                "not-a-schedule-run-id",
            ]
        )

    assert setup_attempted is False


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
            safe_output_payload=lambda: {
                "collection_mode": "session_capture",
                "route_class": "kis_paper_market_data",
                "status": "complete",
            }
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


def test_session_capture_quarantines_a_complete_head_then_a_future_run_recovers_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    monkeypatch.setattr(script, "_load_paper_config", lambda _: object())
    monkeypatch.setattr(
        private_intraday_backfill,
        "_RequestPacer",
        lambda **_kwargs: SimpleNamespace(wait_before_request=lambda: None),
    )
    original_rows = _rows()
    changed_rows = (
        KisPaperMinuteRawBar(
            exchange_date=original_rows[0].exchange_date,
            exchange_time=original_rows[0].exchange_time,
            korea_date=original_rows[0].korea_date,
            korea_time=original_rows[0].korea_time,
            open=original_rows[0].open,
            high=original_rows[0].high + Decimal("1"),
            low=original_rows[0].low,
            last=original_rows[0].last + Decimal("1"),
            volume=original_rows[0].volume,
        ),
        original_rows[1],
    )
    clients = iter(
        (
            _MinuteClient((original_rows, original_rows)),
            _MinuteClient((changed_rows, original_rows)),
            _MinuteClient((changed_rows, original_rows)),
        )
    )
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: next(clients))
    monkeypatch.setattr(
        script,
        "build_and_write_kis_paper_intraday_session_capture",
        lambda **_kwargs: SimpleNamespace(
            safe_output_payload=lambda: {
                "collection_mode": "session_capture",
                "route_class": "kis_paper_market_data",
                "status": "complete",
            }
        ),
    )
    arguments = [
        "--execute",
        "--mode",
        "session-capture",
        "--pages-per-target",
        "1",
        "--skip-legacy-preparation",
    ]

    assert script.main(
        arguments,
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    ) == 0
    index_path = (
        tmp_path
        / "market-data"
        / "us_equities"
        / "kis_paper_private"
        / "intraday-head"
        / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
        / "index.json"
    )
    initial_index = json.loads(index_path.read_text(encoding="utf-8"))
    initial_qqq = _target_state(initial_index, "QQQ/NAS/1m")
    original_chunk = initial_qqq["chunks"][0]
    original_manifest = index_path.parent / original_chunk["manifest_path"]
    original_manifest_bytes = original_manifest.read_bytes()

    assert script.main(
        arguments,
        clock=lambda: datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    ) == 1
    quarantined_index = json.loads(index_path.read_text(encoding="utf-8"))
    quarantined_qqq = _target_state(quarantined_index, "QQQ/NAS/1m")
    assert original_manifest.read_bytes() == original_manifest_bytes
    assert quarantined_qqq["chunks"] == [
        {
            "historical_note": "quarantined_head_retained_cache_conflict",
            "quarantined_chunk_key": original_chunk["chunk_key"],
            "quarantined_manifest_hash": original_chunk["manifest_hash"],
            "quarantined_raw_sha256": original_chunk["raw_sha256"],
            "raw_market_data_retained": False,
        }
    ]

    assert script.main(
        arguments,
        clock=lambda: datetime(2026, 7, 22, 5, 10, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    ) == 0
    recovered_index = json.loads(index_path.read_text(encoding="utf-8"))
    recovered_qqq = _target_state(recovered_index, "QQQ/NAS/1m")
    assert [chunk["raw_market_data_retained"] for chunk in recovered_qqq["chunks"]] == [
        False,
        True,
    ]
    assert sum(chunk["raw_market_data_retained"] is True for chunk in recovered_qqq["chunks"]) == 1


class _MinuteClient:
    def __init__(self, rows_by_request: tuple[tuple[KisPaperMinuteRawBar, ...], ...]) -> None:
        self._rows_by_request = iter(rows_by_request)

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: object | None = None,
    ) -> KisPaperMinutePage:
        if callable(before_request):
            before_request()
        return KisPaperMinutePage(
            query=query,
            bars=next(self._rows_by_request),
            next_cursor=None,
            more="",
        )


def _rows() -> tuple[KisPaperMinuteRawBar, ...]:
    return (
        KisPaperMinuteRawBar(
            exchange_date="20260722",
            exchange_time="093000",
            korea_date="20260722",
            korea_time="223000",
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            last=Decimal("100"),
            volume=Decimal("10"),
        ),
        KisPaperMinuteRawBar(
            exchange_date="20260722",
            exchange_time="093100",
            korea_date="20260722",
            korea_time="223100",
            open=Decimal("101"),
            high=Decimal("102"),
            low=Decimal("100"),
            last=Decimal("101"),
            volume=Decimal("11"),
        ),
    )


def _target_state(index: dict[str, object], target_key: str) -> dict[str, object]:
    targets = index["targets"]
    assert isinstance(targets, list)
    return next(target for target in targets if target["target_key"] == target_key)


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
