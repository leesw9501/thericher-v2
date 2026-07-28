from __future__ import annotations

import math
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_history_candle_state_input as candle_input
from thericher_v2.data import kis_paper_daily_history_sequence_input as sequence_input
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.causal_bar_features import (
    KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES,
    KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS,
    KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH,
    build_kis_nas_d1_candle_state_feature_sequence,
    build_kis_nas_d1_candle_state_feature_sequences,
)


def test_candle_state_feature_math_handles_gap_zero_range_and_zero_volume() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = tuple(
        _bar(
            symbol="AAPL",
            start_ts=start + timedelta(days=index),
            open_value=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=Decimal("0"),
        )
        for index in range(KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS)
    )
    gap_bar = replace(
        bars[-1],
        open=Decimal("12"),
        high=Decimal("14"),
        low=Decimal("10"),
        close=Decimal("13"),
    )
    gap_features = build_kis_nas_d1_candle_state_feature_sequence(
        (*bars[:-1], gap_bar),
        symbol="AAPL",
        decision_index=KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
    )
    assert gap_features[-1] == pytest.approx(
        (
            math.log(1.2),
            0.25,
            0.5,
            0.4,
            0.0,
        )
    )

    zero_range_bar = replace(
        bars[-1],
        open=Decimal("10"),
        high=Decimal("10"),
        low=Decimal("10"),
        close=Decimal("10"),
    )
    zero_range_features = build_kis_nas_d1_candle_state_feature_sequence(
        (*bars[:-1], zero_range_bar),
        symbol="AAPL",
        decision_index=KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
    )
    assert zero_range_features[-1] == pytest.approx((0.0, 0.0, 0.0, 0.0, 0.0))


def test_candle_state_feature_values_ignore_the_callers_decimal_precision() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = tuple(
        _bar(
            symbol="AAPL",
            start_ts=start + timedelta(days=index),
            open_value=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=Decimal("100"),
        )
        for index in range(KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS)
    )
    final_bar = replace(
        bars[-1],
        high=Decimal("13"),
        low=Decimal("10"),
        close=Decimal("11"),
    )
    chain = (*bars[:-1], final_bar)

    with localcontext() as context:
        context.prec = 8
        low_precision = build_kis_nas_d1_candle_state_feature_sequence(
            chain,
            symbol="AAPL",
            decision_index=KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
        )
    with localcontext() as context:
        context.prec = 48
        high_precision = build_kis_nas_d1_candle_state_feature_sequence(
            chain,
            symbol="AAPL",
            decision_index=KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
        )

    assert low_precision == high_precision


def test_bulk_feature_sequences_match_the_single_causal_builder() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = tuple(
        _bar(
            symbol="AAPL",
            start_ts=start + timedelta(days=index),
            open_value=Decimal("100") + Decimal(index),
            high=Decimal("101") + Decimal(index),
            low=Decimal("99") + Decimal(index),
            close=Decimal("100") + Decimal(index),
            volume=Decimal(index % 3),
        )
        for index in range(KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS + 3)
    )
    bulk = build_kis_nas_d1_candle_state_feature_sequences(bars, symbol="AAPL")

    assert bulk == tuple(
        build_kis_nas_d1_candle_state_feature_sequence(
            bars,
            symbol="AAPL",
            decision_index=decision_index,
        )
        for decision_index in range(KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1, len(bars))
    )


def test_relative_volume_uses_only_the_prior_twenty_completed_bars() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = tuple(
        _bar(
            symbol="AAPL",
            start_ts=start + timedelta(days=index),
            open_value=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal(index + 1),
        )
        for index in range(KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS + 1)
    )
    baseline = build_kis_nas_d1_candle_state_feature_sequence(
        bars,
        symbol="AAPL",
        decision_index=KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
    )
    changed_future_volume = (*bars[:40], replace(bars[40], volume=Decimal("999999")))
    changed = build_kis_nas_d1_candle_state_feature_sequence(
        changed_future_volume,
        symbol="AAPL",
        decision_index=KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
    )
    expected_relative_volume = math.log1p(40.0) - sum(
        math.log1p(float(value)) for value in range(20, 40)
    ) / 20.0

    assert baseline[-1][4] == pytest.approx(expected_relative_volume)
    assert changed == baseline


def test_completed_features_ignore_later_bars_and_have_frozen_shape(tmp_path: Path) -> None:
    baseline = candle_input.build_kis_paper_daily_history_candle_state_input(
        _source(tmp_path / "baseline")
    )
    future_changed = candle_input.build_kis_paper_daily_history_candle_state_input(
        _source(
            tmp_path / "future-changed",
            altered_symbol="AAPL",
            altered_from_index=40,
            alteration=Decimal("7"),
        )
    )

    baseline_sample = baseline.development_samples("AAPL")[0]
    changed_sample = future_changed.development_samples("AAPL")[0]

    assert baseline_sample == changed_sample
    assert len(baseline_sample.feature_sequence) == KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH
    assert all(
        len(row) == len(KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES)
        for row in baseline_sample.feature_sequence
    )
    assert baseline_sample.lookback_anchor_start < baseline_sample.feature_start
    assert baseline_sample.feature_start <= baseline_sample.decision_start
    assert baseline_sample.decision_start < baseline_sample.decision_end


def test_validation_is_target_free_and_does_not_cross_the_phase_boundary(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    prepared = candle_input.build_kis_paper_daily_history_candle_state_input(source)
    first_validation = prepared.validation_samples("AAPL")[0]
    payload = prepared.safe_payload()

    assert len(prepared.development_samples("AAPL")) == 1471
    assert len(prepared.validation_samples("AAPL")) == 608
    assert first_validation.lookback_anchor_start.date() == source.validation.common_sessions[0]
    assert not hasattr(first_validation, "label")
    assert not hasattr(first_validation, "entry_start")
    assert not hasattr(first_validation, "exit_start")
    assert payload["features"]["future_bars_read"] is False
    _assert_no_value_fields(payload)


def test_incomplete_invalid_ohlcv_and_short_inputs_reject(tmp_path: Path) -> None:
    incomplete = _source(tmp_path / "incomplete")
    incomplete_stream = incomplete.development.bars_by_symbol["AAPL"]
    object.__setattr__(
        incomplete_stream,
        "bars",
        (replace(incomplete_stream.bars[0], complete=False), *incomplete_stream.bars[1:]),
    )
    with pytest.raises(ValueError):
        candle_input.build_kis_paper_daily_history_candle_state_input(incomplete)

    invalid_volume = _source(tmp_path / "invalid-volume")
    invalid_stream = invalid_volume.development.bars_by_symbol["AAPL"]
    object.__setattr__(invalid_stream.bars[0], "volume", Decimal("NaN"))
    with pytest.raises(ValueError, match="volume"):
        candle_input.build_kis_paper_daily_history_candle_state_input(invalid_volume)

    short_bars = _source(tmp_path / "short").development.stream("AAPL").bars[
        : KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1
    ]
    with pytest.raises(ValueError, match="decision index"):
        build_kis_nas_d1_candle_state_feature_sequence(
            short_bars,
            symbol="AAPL",
            decision_index=len(short_bars) - 1,
        )


def test_builder_stays_offline_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source(tmp_path / "source")
    _deny_external_access(monkeypatch)

    prepared = candle_input.build_kis_paper_daily_history_candle_state_input(source)

    assert prepared.development.feature_input_hash.startswith("sha256:")
    assert prepared.validation.feature_input_hash.startswith("sha256:")


def _source(
    root: Path,
    *,
    altered_symbol: str | None = None,
    altered_from_index: int = 0,
    alteration: Decimal = Decimal("0"),
) -> sequence_input.KisPaperDailyHistorySequenceInput:
    return sequence_input._prepare_kis_paper_daily_history_sequence_input(  # noqa: SLF001
        _panel(
            root,
            altered_symbol=altered_symbol,
            altered_from_index=altered_from_index,
            alteration=alteration,
        )
    )


def _panel(
    root: Path,
    *,
    altered_symbol: str | None,
    altered_from_index: int,
    alteration: Decimal,
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    start = datetime(2018, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(2179))
    dataset_hash = sequence_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for symbol_offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        bars = tuple(
            _bar(
                symbol=symbol,
                start_ts=start + timedelta(days=index),
                open_value=(
                    Decimal("100")
                    + Decimal(symbol_offset)
                    + Decimal(index) / Decimal("100")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
                high=(
                    Decimal("101")
                    + Decimal(symbol_offset)
                    + Decimal(index) / Decimal("100")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
                low=(
                    Decimal("99")
                    + Decimal(symbol_offset)
                    + Decimal(index) / Decimal("100")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
                close=(
                    Decimal("100")
                    + Decimal(symbol_offset)
                    + Decimal(index) / Decimal("100")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
                volume=Decimal("1000"),
            )
            for index in range(2179)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state="complete",
            last_reason=None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket=_quarter(sessions[0]),
            coverage_end_bucket=_quarter(sessions[-1]),
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "a" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(
    *,
    symbol: str,
    start_ts: datetime,
    open_value: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: Decimal,
) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=open_value,
        high=high,
        low=low,
        close=close,
        volume=volume,
        complete=True,
    )


def _quarter(value: date) -> str:
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("candle-state adapter must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(os, "getenv", denied)


def _assert_no_value_fields(value: object) -> None:
    forbidden = {
        "bars",
        "close",
        "entry",
        "exit",
        "feature_sequence",
        "high",
        "label",
        "low",
        "open",
        "prices",
        "volume",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden)
        for nested in value.values():
            _assert_no_value_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_value_fields(nested)
