from __future__ import annotations

import json
import socket
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
    TiingoEtfDailySnapshot,
)
from thericher_v2.research import tiingo_d1_trend_mean_reversion_rotation as rotation


def test_causal_masking_ignores_target_day_event_but_masks_feature_window() -> None:
    config = rotation.TiingoD1TrendMeanReversionRotationConfig()
    index = 705
    aligned = _aligned_active_rows()

    target_event = dict(aligned)
    target_event["SPY"] = _replace_row(
        aligned["SPY"],
        index + 1,
        div_cash=Decimal("0.01"),
    )
    assert rotation._mask_reason(
        index=index,
        rows_by_symbol=target_event,
        config=config,
    ) is None

    feature_event = dict(aligned)
    feature_event["QQQ"] = _replace_row(
        aligned["QQQ"],
        index,
        div_cash=Decimal("0.01"),
    )
    assert rotation._mask_reason(
        index=index,
        rows_by_symbol=feature_event,
        config=config,
    ) == "event"

    prior_close = aligned["IWM"][index - 1].close
    jump_close = prior_close * Decimal("1.25")
    discontinuity = dict(aligned)
    discontinuity["IWM"] = _replace_row(
        aligned["IWM"],
        index,
        open=jump_close - Decimal("0.01"),
        high=jump_close + Decimal("0.02"),
        low=jump_close - Decimal("0.03"),
        close=jump_close,
    )
    assert rotation._mask_reason(
        index=index,
        rows_by_symbol=discontinuity,
        config=config,
    ) == "feature_discontinuity"


def test_fixed_symbol_order_breaks_equal_score_ties() -> None:
    aligned = _aligned_active_rows()

    decision = rotation._decision(
        index=705,
        rows_by_symbol=aligned,
        config=rotation.TiingoD1TrendMeanReversionRotationConfig(),
    )

    assert decision.candidate_symbol == "SPY"
    assert decision.trend_symbol == "SPY"


def test_flat_history_abstains_and_fails_minimum_active_preflight() -> None:
    prepared = rotation.prepare_tiingo_d1_trend_mean_reversion_rotation(
        _snapshot(profile="flat")
    )

    assert prepared.status == "input_unavailable"
    assert prepared.reason == "insufficient_validation_active_decisions"
    assert prepared.validation.scheduled_decision_count > 0
    assert prepared.validation.accepted_decision_count == (
        prepared.validation.scheduled_decision_count
    )
    assert prepared.validation.no_signal_count == prepared.validation.accepted_decision_count
    assert prepared.validation.active_decision_count == 0
    assert prepared.validation.active_decision_count < (
        rotation.TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_MIN_VALIDATION_ACTIVE_DECISIONS
    )

    result = rotation.evaluate_tiingo_d1_trend_mean_reversion_rotation(prepared)
    assert result.status == "input_unavailable"
    assert result.validation is None


def test_evaluation_applies_full_cost_band_and_falsifies_active_comparators() -> None:
    prepared = rotation.prepare_tiingo_d1_trend_mean_reversion_rotation(
        _snapshot(profile="active")
    )

    assert prepared.status == "ready"
    result = rotation.evaluate_tiingo_d1_trend_mean_reversion_rotation(prepared)
    assert result.status == "falsified"
    assert result.validation is not None
    validation = result.validation
    active_count = Decimal(validation.active_decision_count)

    assert validation.active_decision_count >= 100
    assert validation.candidate_net_total_bps_by_cost == (
        validation.equal_weight_net_total_bps_by_cost
    )
    assert validation.candidate_net_total_bps_by_cost == (
        validation.trend_rotation_net_total_bps_by_cost
    )
    assert (
        validation.candidate_net_total_bps_by_cost["10"]
        - validation.candidate_net_total_bps_by_cost["5"]
        == -Decimal("5") * active_count
    )
    assert (
        validation.candidate_net_total_bps_by_cost["20"]
        - validation.candidate_net_total_bps_by_cost["10"]
        == -Decimal("10") * active_count
    )
    assert validation.candidate_net_total_bps_by_cost["20"] <= 0
    assert validation.kill_reasons == (
        "candidate_net_flat_or_worse_at_20bp",
        "candidate_no_better_than_both_active_comparators_across_cost_band",
    )


def test_source_reuse_is_explicitly_labeled_non_promoting() -> None:
    prepared = rotation.prepare_tiingo_d1_trend_mean_reversion_rotation(
        _snapshot(profile="active")
    )

    payload = prepared.safe_payload()
    source = payload["source"]
    contract = payload["contract"]

    assert source["source_reuse_families"] == list(
        rotation.TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_SOURCE_REUSE_FAMILIES
    )
    assert source["independent_holdout_claim_allowed"] is False
    assert source["sealed_tail_claim_allowed"] is False
    assert source["paper_input_eligible"] is False
    assert contract["split"]["source_reuse_grade"] == (
        "repeat_source_non_promoting_falsification"
    )
    assert contract["promotion_allowed"] is False


def test_external_artifacts_are_idempotent_external_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("rotation falsification must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "not-for-artifacts")
    monkeypatch.setenv("TIINGO_API_TOKEN", "not-for-artifacts")
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot(
        profile="active",
        start_price=Decimal("123.456789"),
    )

    first = rotation.run_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="unit-run",
        repo_root=repo_root,
    )
    rerun = rotation.run_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="unit-run",
        repo_root=repo_root,
    )

    assert first.precommit_path == rerun.precommit_path
    assert first.summary_path == rerun.summary_path
    assert first.precommit_hash == rerun.precommit_hash
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    written = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (first.precommit_path, first.summary_path)
    )
    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert summary["result"]["raw_market_data_written"] is False
    assert "123.456789" not in written
    assert "not-for-artifacts" not in written
    assert "KIS_PAPER_APP_KEY" not in written
    assert "TIINGO_API_TOKEN" not in written

    with pytest.raises(ValueError, match="outside Git"):
        rotation.run_tiingo_d1_trend_mean_reversion_rotation(
            snapshot,
            artifact_root=repo_root / "model-artifacts",
            run_label="repo-root-run",
            repo_root=repo_root,
        )


def test_validation_recomputes_and_binds_existing_safe_evidence(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot(profile="active")
    run = rotation.run_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="validation-r1",
        repo_root=repo_root,
    )

    receipt = rotation.validate_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="validation-r1",
        repo_root=repo_root,
    )

    validation = json.loads(receipt.validation_path.read_text(encoding="utf-8"))
    assert receipt.status == "verified"
    assert receipt.source_reattached is True
    assert receipt.precommit_hash == run.precommit_hash
    assert validation["summary_sha256"].startswith("sha256:")
    assert validation["raw_market_data_written"] is False
    assert validation["paper_input_allowed"] is False
    assert validation["promotion_allowed"] is False

    run.summary_path.write_text("{}\n", encoding="ascii")
    with pytest.raises(ValueError, match="evidence binding"):
        rotation.validate_tiingo_d1_trend_mean_reversion_rotation(
            snapshot,
            artifact_root=artifact_root,
            run_label="validation-r1",
            repo_root=repo_root,
        )


def _snapshot(
    *,
    count: int = 1_000,
    profile: str,
    start_price: Decimal = Decimal("100"),
) -> LoadedTiingoEtfDailySnapshot:
    rows_by_symbol = {
        symbol: _rows(
            symbol,
            count=count,
            profile=profile,
            start_price=start_price,
        )
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    snapshot = TiingoEtfDailySnapshot(
        snapshot_dir=Path(
            "D:/market_data/us_equities/tiingo_etf_daily/canonical/"
            "snapshot=fixture-tiingo-etf-d1-r1"
        ),
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


def _aligned_active_rows() -> dict[str, tuple[TiingoEtfDailyRow, ...]]:
    return {
        symbol: _rows(
            symbol,
            count=1_000,
            profile="active",
            start_price=Decimal("100"),
        )
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }


def _replace_row(
    rows: tuple[TiingoEtfDailyRow, ...],
    index: int,
    **changes: Decimal,
) -> tuple[TiingoEtfDailyRow, ...]:
    updated = list(rows)
    updated[index] = replace(updated[index], **changes)
    return tuple(updated)


def _rows(
    symbol: str,
    *,
    count: int,
    profile: str,
    start_price: Decimal,
) -> tuple[TiingoEtfDailyRow, ...]:
    rows: list[TiingoEtfDailyRow] = []
    for index in range(count):
        if profile == "active":
            close = (
                start_price
                + Decimal(index) * Decimal("0.15")
                - Decimal(index % 10) * Decimal("0.8")
            )
        elif profile == "flat":
            close = start_price
        else:
            raise AssertionError(f"unknown fixture profile: {profile}")
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
                div_cash=Decimal("0"),
                split_factor=Decimal("1"),
            )
        )
    return tuple(rows)
