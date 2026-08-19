from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import BROKER_DISABLED_SOURCE, LOCAL_PAPER_SOURCE
from thericher_v2.research.trade_path_attribution import (
    TradePathEventArtifact,
    attribute_trade_paths_from_local_paper_events,
)


def test_trade_path_attribution_pairs_fifo_partial_fills_and_fee_deltas(
    tmp_path,
) -> None:
    events = tmp_path / "events.jsonl"
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    _write_events(
        events,
        (
            _fill_event(
                created_at=start,
                side="buy",
                price="10.00",
                quantity="2",
                fee="0.02",
                source=LOCAL_PAPER_SOURCE,
            ),
            _fill_event(
                created_at=start + timedelta(minutes=2),
                side="sell",
                price="10.50",
                quantity="1",
                fee="0.01",
                source=LOCAL_PAPER_SOURCE,
            ),
        ),
    )

    result = attribute_trade_paths_from_local_paper_events(
        event_artifacts=(
            TradePathEventArtifact(
                path=events,
                expected_fill_count=2,
                slice_id="aaa_slice",
                variant_id="t01",
                symbol="AAA",
            ),
        ),
        bars=(
            _bar("AAA", start, low="9.80", high="10.10", close="10.00"),
            _bar(
                "AAA",
                start + timedelta(minutes=1),
                low="9.90",
                high="10.60",
                close="10.40",
            ),
            _bar(
                "AAA",
                start + timedelta(minutes=2),
                low="10.20",
                high="10.70",
                close="10.50",
            ),
        ),
        checked_at=start,
    )

    segment = result.closed_segments[0]
    open_segment = result.open_segments[0]
    assert result.metrics["closed_segment_count"] == 1
    assert result.metrics["open_segment_count"] == 1
    assert result.metrics["fee_aware_delta_sum"] == "0.48"
    assert segment["gross_delta"] == "0.5"
    assert segment["fee_total"] == "0.02"
    assert segment["fee_aware_delta"] == "0.48"
    assert segment["holding_duration_seconds"] == "120"
    assert segment["path_summary"]["adverse_delta_from_entry"] == "-0.2"
    assert segment["path_summary"]["favorable_delta_from_entry"] == "0.7"
    assert open_segment["entry"]["quantity"] == "1"
    assert result.local_paper_verification["all_fills_local_paper"] is True
    assert result.to_payload()["result_scope"]["mode"] == "research_trade_path_attribution_only"


def test_trade_path_attribution_surfaces_non_local_sources(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    _write_events(
        events,
        (
            _fill_event(
                created_at=start,
                side="buy",
                price="10.00",
                quantity="1",
                fee="0.01",
                source=LOCAL_PAPER_SOURCE,
            ),
            _fill_event(
                created_at=start + timedelta(minutes=1),
                side="sell",
                price="10.10",
                quantity="1",
                fee="0.01",
                source=LOCAL_PAPER_SOURCE,
            ),
            _fill_event(
                created_at=start + timedelta(minutes=2),
                side="buy",
                price="10.20",
                quantity="1",
                fee="0.00",
                source=BROKER_DISABLED_SOURCE,
            ),
        ),
    )

    result = attribute_trade_paths_from_local_paper_events(
        event_artifacts=(
            TradePathEventArtifact(
                path=events,
                expected_fill_count=3,
                slice_id="aaa_slice",
                variant_id="t01",
                symbol="AAA",
            ),
        ),
        bars=(
            _bar("AAA", start, low="9.90", high="10.20", close="10.05"),
            _bar(
                "AAA",
                start + timedelta(minutes=1),
                low="10.00",
                high="10.30",
                close="10.10",
            ),
        ),
        checked_at=start,
    )

    verification = result.local_paper_verification
    assert result.metrics["closed_segment_count"] == 1
    assert verification["all_fills_local_paper"] is False
    assert verification["non_local_fill_source_counts"] == {BROKER_DISABLED_SOURCE: 1}
    assert verification["local_paper_fill_count"] == 2


def test_trade_path_attribution_fails_closed_for_fill_instrument_mismatch(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    _write_events(
        events,
        (
            _fill_event(
                created_at=start,
                side="buy",
                price="10.00",
                quantity="1",
                fee="0.01",
                source=LOCAL_PAPER_SOURCE,
                symbol="MSFT",
            ),
            _fill_event(
                created_at=start + timedelta(minutes=1),
                side="sell",
                price="10.50",
                quantity="1",
                fee="0.01",
                source=LOCAL_PAPER_SOURCE,
                symbol="MSFT",
            ),
        ),
    )

    with pytest.raises(ValueError, match="does not match trade-path artifact instrument"):
        attribute_trade_paths_from_local_paper_events(
            event_artifacts=(
                TradePathEventArtifact(
                    path=events,
                    expected_fill_count=2,
                    slice_id="aaa_slice",
                    variant_id="t01",
                    symbol="AAA",
                ),
            ),
            bars=(
                _bar("AAA", start, low="9.90", high="10.10", close="10.00"),
                _bar(
                    "AAA",
                    start + timedelta(minutes=1),
                    low="10.00",
                    high="10.60",
                    close="10.50",
                ),
            ),
            checked_at=start,
        )


def test_trade_path_attribution_tolerates_zero_fill_missing_artifacts_only(
    tmp_path,
) -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    missing = tmp_path / "missing.jsonl"

    zero_fill = attribute_trade_paths_from_local_paper_events(
        event_artifacts=(
            TradePathEventArtifact(
                path=missing,
                expected_fill_count=0,
                slice_id="zero",
                variant_id="t00",
                symbol="AAA",
            ),
        ),
        bars=(),
        checked_at=start,
    )
    nonzero_fill = attribute_trade_paths_from_local_paper_events(
        event_artifacts=(
            TradePathEventArtifact(
                path=missing,
                expected_fill_count=1,
                slice_id="nonzero",
                variant_id="t01",
                symbol="AAA",
            ),
        ),
        bars=(),
        checked_at=start,
    )

    assert zero_fill.local_paper_verification["all_fills_local_paper"] is True
    assert zero_fill.local_paper_verification["missing_zero_fill_event_artifacts"] == [
        str(missing)
    ]
    assert nonzero_fill.local_paper_verification["all_fills_local_paper"] is False
    assert nonzero_fill.local_paper_verification["unreadable_event_artifacts"] == [
        "nonzero:t01"
    ]


def test_trade_path_attribution_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("trade-path attribution must not open network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("trade-path attribution must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    events = tmp_path / "events.jsonl"
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    _write_events(
        events,
        (
            _fill_event(
                created_at=start,
                side="buy",
                price="10.00",
                quantity="1",
                fee="0.01",
                source=LOCAL_PAPER_SOURCE,
            ),
        ),
    )

    result = attribute_trade_paths_from_local_paper_events(
        event_artifacts=(
            TradePathEventArtifact(
                path=events,
                expected_fill_count=1,
                slice_id="aaa_slice",
                variant_id="t01",
                symbol="AAA",
            ),
        ),
        bars=(_bar("AAA", start, low="9.90", high="10.10", close="10.00"),),
        checked_at=start,
    )

    assert result.metrics["open_segment_count"] == 1
    assert result.local_paper_verification["all_fills_local_paper"] is True


def _fill_event(
    *,
    created_at: datetime,
    side: str,
    price: str,
    quantity: str,
    fee: str,
    source: str,
    symbol: str = "AAA",
    market: str = "US",
) -> dict[str, object]:
    return {
        "created_at": created_at.isoformat(),
        "event_type": "fill",
        "payload": {
            "source": source,
            "side": side,
            "price": price,
            "quantity": quantity,
            "fee": fee,
            "symbol": symbol,
            "market": market,
        },
    }


def _bar(
    symbol: str,
    start_ts: datetime,
    *,
    low: str,
    high: str,
    close: str,
) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
    )


def _write_events(path: Path, events: tuple[dict[str, object], ...]) -> None:
    path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
