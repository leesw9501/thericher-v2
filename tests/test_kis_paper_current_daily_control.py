from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_etf_daily_context import (
    CompletedSession,
    DailyContext,
    DailyContextReceipt,
    DailyObservation,
    completed_sessions,
)
from thericher_v2.research.kis_paper_current_daily_control import (
    CurrentDailyControlUnavailable,
    build_current_daily_control,
)
from thericher_v2.research.kis_paper_daily_portfolio_control import build_capped_thirds_control


@pytest.fixture
def contexts():
    captured = datetime(2026, 10, 13, 14, tzinfo=UTC)
    calendar = completed_sessions(captured)
    result = {}
    for index, (symbol, venue) in enumerate((("SPY", "AMS"), ("TLT", "NAS"), ("GLD", "AMS"))):
        observations = tuple(
            DailyObservation(
                session.provider_date,
                Bar(
                    symbol,
                    "US",
                    Timeframe.D1,
                    datetime.combine(session.provider_date, datetime.min.time(), UTC),
                    Decimal(100),
                    Decimal(110),
                    Decimal(90),
                    Decimal(100 + i % 3),
                    Decimal(1000),
                ),
            )
            for i, session in enumerate(calendar)
        )
        receipt = DailyContextReceipt(
            symbol=symbol,
            exchange=venue,
            captured_at_utc=captured,
            observed_at_utc=captured,
            first_available_at_utc=captured + timedelta(seconds=index),
            excluded_current_us_date=date(2026, 10, 13),
            calendar=calendar,
            provider_dates=tuple(s.provider_date for s in calendar),
            raw_relative_path=f"synthetic/{symbol}.csv.gz",
            raw_sha256="sha256:" + "1" * 64,
            raw_size_bytes=200,
            source_sha256="sha256:" + "2" * 64,
            page_count=3,
            duplicate_count=0,
            outside_window_count=0,
            next_cursor=None,
            source_code_sha256=(("synthetic", "sha256:" + "3" * 64),),
            token_interval_seconds=60,
        )
        result[symbol] = DailyContext(receipt, "sha256:" + str(index + 1) * 64, observations)
    return result


def test_same_current_receipts_have_stable_identity_and_original_arithmetic(contexts):
    a = build_current_daily_control(contexts, as_of=datetime(2026, 10, 13, 15, tzinfo=UTC))
    b = build_current_daily_control(contexts, as_of=datetime(2026, 10, 13, 19, tzinfo=UTC))
    assert a == b
    assert a.available_at == datetime(2026, 10, 13, 14, 0, 2, tzinfo=UTC)
    assert a.target_as_of == datetime(2026, 10, 12, 20, tzinfo=UTC)
    assert a.valid_until == datetime(2026, 10, 13, 20, tzinfo=UTC)
    expected = build_capped_thirds_control(
        {s: tuple(b.close for b in c.bars) for s, c in contexts.items()}
    )
    assert (a.weights_by_symbol, a.covariance_by_symbol) == expected
    assert "weights" not in a.safe_payload() and "covariance" not in a.safe_payload()
    with pytest.raises(TypeError):
        a.weights_by_symbol["SPY"] = Decimal(1)


@pytest.mark.parametrize(
    "at", [datetime(2026, 10, 13, 20, tzinfo=UTC), datetime(2026, 10, 14, 15, tzinfo=UTC)]
)
def test_archived_input_does_not_gain_new_intent_eligibility(contexts, at):
    with pytest.raises(CurrentDailyControlUnavailable, match="outside_next_session"):
        build_current_daily_control(contexts, as_of=at)


def test_before_publication_rejected_without_reclocking(contexts):
    with pytest.raises(CurrentDailyControlUnavailable, match="input_not_available"):
        build_current_daily_control(contexts, as_of=datetime(2026, 10, 13, 14, tzinfo=UTC))
    assert contexts["GLD"].receipt.first_available_at_utc == datetime(
        2026, 10, 13, 14, 0, 2, tzinfo=UTC
    )


def test_cross_source_calendar_mismatch_rejected(contexts):
    old = contexts["GLD"]
    calendar = old.receipt.calendar[:-1] + (
        CompletedSession(
            old.receipt.calendar[-1].provider_date,
            old.receipt.calendar[-1].calendar_close_utc - timedelta(minutes=1),
        ),
    )
    contexts["GLD"] = replace(old, receipt=replace(old.receipt, calendar=calendar))
    with pytest.raises(CurrentDailyControlUnavailable, match="sessions_mismatch"):
        build_current_daily_control(contexts, as_of=datetime(2026, 10, 13, 15, tzinfo=UTC))


def test_small_tail_or_other_instrument_cannot_replace_original_control(contexts):
    contexts["SPY"] = replace(contexts["SPY"], observations=contexts["SPY"].observations[-21:])
    with pytest.raises(CurrentDailyControlUnavailable, match="context_incomplete"):
        build_current_daily_control(contexts, as_of=datetime(2026, 10, 13, 15, tzinfo=UTC))
    contexts["QQQ"] = contexts.pop("SPY")
    with pytest.raises(CurrentDailyControlUnavailable, match="instrument_scope"):
        build_current_daily_control(contexts, as_of=datetime(2026, 10, 13, 15, tzinfo=UTC))
