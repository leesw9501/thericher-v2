from __future__ import annotations

import socket
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.research.tiingo_etf_d1_cpu_baseline as baseline
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
    TiingoEtfDailySnapshot,
)
from thericher_v2.research.tiingo_etf_d1_cpu_baseline import (
    TIINGO_ETF_D1_CPU_BASELINE_PURGE_SESSIONS,
    evaluate_tiingo_etf_d1_cpu_baseline,
    run_tiingo_etf_d1_cpu_baseline,
)


def test_cpu_baseline_freezes_causal_split_and_has_no_promotion_output() -> None:
    result = evaluate_tiingo_etf_d1_cpu_baseline(_snapshot())

    split_counts = [
        (
            split.development_session_count,
            split.purge_session_count,
            split.validation_session_count,
        )
        for split in result.splits
    ]
    assert split_counts == [(280, TIINGO_ETF_D1_CPU_BASELINE_PURGE_SESSIONS, 59)] * len(
        TIINGO_ETF_D1_SYMBOLS
    )
    assert len(result.cells) == 18
    assert all(cell.status == "evaluated" for cell in result.cells)
    payload = result.safe_payload()
    assert payload["candidate_selection_allowed"] is False
    assert payload["ensemble_allowed"] is False
    assert payload["gpu_eligible"] is False
    assert payload["paper_input_allowed"] is False
    assert payload["promotion_allowed"] is False
    assert payload["contract"]["target"] == "next_session_open_to_close_direction"
    assert payload["contract"]["feature_discontinuity_window"] == "t-lookback+1_through_t_only"
    assert payload["contract"]["round_trip_cost_bps_band"] == ["5", "10", "20"]
    evaluated_cell = next(cell for cell in payload["cells"] if cell["status"] == "evaluated")
    assert tuple(evaluated_cell["momentum_net_total_bps_by_round_trip_cost"]) == ("5", "10", "20")


def test_target_day_jump_is_not_a_feature_filter_but_event_and_feature_jumps_are() -> None:
    rows = list(_rows("SPY", count=400))
    index = 341
    rows[index + 1] = replace(rows[index + 1], close=rows[index + 1].close * Decimal("1.50"))

    assert (
        baseline._sample_exclusion(
            tuple(rows),
            index=index,
            lookback=5,
            feature_discontinuity_limit=Decimal("0.20"),
        )
        is None
    )
    rows[index] = replace(rows[index], close=rows[index].close * Decimal("1.50"))
    assert (
        baseline._sample_exclusion(
            tuple(rows),
            index=index,
            lookback=5,
            feature_discontinuity_limit=Decimal("0.20"),
        )
        == "feature_discontinuity"
    )
    rows[index] = replace(rows[index], close=rows[index - 1].close * Decimal("1.01"))
    rows[index + 1] = replace(rows[index + 1], div_cash=Decimal("0.01"))
    assert (
        baseline._sample_exclusion(
            tuple(rows),
            index=index,
            lookback=5,
            feature_discontinuity_limit=Decimal("0.20"),
        )
        == "event"
    )


def test_event_mask_can_truthfully_make_one_window_input_unavailable() -> None:
    result = evaluate_tiingo_etf_d1_cpu_baseline(_snapshot(event_every=30))
    validation_l60 = next(
        cell
        for cell in result.cells
        if cell.symbol == "SPY" and cell.lookback == 60 and cell.phase == "validation"
    )

    assert validation_l60.status == "input_unavailable"
    assert validation_l60.event_excluded_count > 0
    assert validation_l60.momentum_net_total_bps is None


def test_run_writes_external_source_safe_artifacts_without_network_or_raw_prices(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot(start_price=Decimal("123.456789"))

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("CPU baseline must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail)
    run = run_tiingo_etf_d1_cpu_baseline(
        snapshot,
        artifact_root=artifact_root,
        run_label="unit-run",
        repo_root=repo_root,
    )

    assert run.precommit_path.is_relative_to(artifact_root)
    assert run.summary_path.is_relative_to(artifact_root)
    summary = run.summary_path.read_text(encoding="utf-8")
    assert "123.456789" not in summary
    assert "KIS_" not in summary
    assert '"raw_market_data_written": false' in summary
    assert '"promotion_allowed": false' in summary

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_tiingo_etf_d1_cpu_baseline(
            snapshot,
            artifact_root=repo_root / "artifacts",
            run_label="repo-run",
            repo_root=repo_root,
        )


def _snapshot(
    *,
    count: int = 400,
    event_every: int | None = None,
    start_price: Decimal = Decimal("100"),
) -> LoadedTiingoEtfDailySnapshot:
    rows_by_symbol = {
        symbol: _rows(
            symbol,
            count=count,
            event_every=event_every,
            start_price=start_price + Decimal(index * 10),
        )
        for index, symbol in enumerate(TIINGO_ETF_D1_SYMBOLS)
    }
    snapshot = TiingoEtfDailySnapshot(
        snapshot_dir=Path("D:/market_data/us_equities/tiingo_etf_daily/canonical/snapshot=fixture-tiingo-etf-d1-r1"),
        dataset_id="us_equities.tiingo_etf_daily.snapshot=fixture-tiingo-etf-d1-r1",
        dataset_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        raw_hashes={
            symbol: "sha256:" + character * 64
            for symbol, character in zip(TIINGO_ETF_D1_SYMBOLS, "cde", strict=True)
        },
        session_counts={symbol: count for symbol in TIINGO_ETF_D1_SYMBOLS},
        date_ranges={
            symbol: (rows[0].session_date, rows[-1].session_date)
            for symbol, rows in rows_by_symbol.items()
        },
        event_session_counts={
            symbol: sum(row.div_cash != 0 for row in rows)
            for symbol, rows in rows_by_symbol.items()
        },
        row_count=count * len(TIINGO_ETF_D1_SYMBOLS),
        free_percent=40.0,
    )
    return LoadedTiingoEtfDailySnapshot(snapshot=snapshot, rows_by_symbol=rows_by_symbol)


def _rows(
    symbol: str,
    *,
    count: int,
    event_every: int | None = None,
    start_price: Decimal = Decimal("100"),
) -> tuple[TiingoEtfDailyRow, ...]:
    rows: list[TiingoEtfDailyRow] = []
    for index in range(count):
        close = start_price + Decimal(index) / Decimal("10")
        open_price = close - Decimal("0.01")
        rows.append(
            TiingoEtfDailyRow(
                symbol=symbol,
                session_date=date(2020, 1, 1) + timedelta(days=index),
                open=open_price,
                high=close + Decimal("0.02"),
                low=open_price - Decimal("0.02"),
                close=close,
                volume=Decimal("1000"),
                div_cash=(
                    Decimal("0.01")
                    if event_every and index % event_every == 0
                    else Decimal("0")
                ),
                split_factor=Decimal("1"),
            )
        )
    return tuple(rows)
