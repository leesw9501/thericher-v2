from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.prospective_spy_intraday_session import (
    PROSPECTIVE_SPY_INTRADAY_SESSION_RECORD_ID,
    ProspectiveSpyIntradaySessionInputError,
    build_prospective_spy_intraday_session_record,
)

_EASTERN = ZoneInfo("America/New_York")
_SOURCE_CONTRACT_HASH = "sha256:" + "a" * 64


@pytest.mark.parametrize(
    "session_date",
    (date(2026, 1, 2), date(2026, 7, 1)),
    ids=("est", "edt"),
)
def test_builds_fixed_dst_aware_causal_windows_without_raw_values(
    session_date: date,
) -> None:
    session, cutoff = _regular_session(session_date)
    record = build_prospective_spy_intraday_session_record(
        _session_bars(session, cutoff, market="NYSE_ARCA"),
        session=session,
        cutoff=cutoff,
        source_contract_hash=_SOURCE_CONTRACT_HASH,
    )

    assert record.source_contract_hash == _SOURCE_CONTRACT_HASH
    assert record.contract_hash.startswith("sha256:")
    assert record.cutoff == cutoff
    assert record.sequence_window.symbol == "SPY"
    assert record.sequence_window.market == "NYSE_ARCA"
    assert {
        timeframe.value: len(window.bars)
        for timeframe, window in record.sequence_window.windows.items()
    } == {"1m": 30, "5m": 6, "10m": 3, "1h": 2, "3h": 2}
    assert all(window.end_ts == cutoff for window in record.sequence_window.windows.values())
    assert record.sequence_window.windows[Timeframe.H3].start_ts == session.open_ts

    payload = record.safe_payload()
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["record_id"] == PROSPECTIVE_SPY_INTRADAY_SESSION_RECORD_ID
    assert payload["market"] == "NYSE_ARCA"
    assert payload["cutoff"] == cutoff.isoformat()
    assert payload["session"] == {
        "open_ts": session.open_ts.isoformat(),
        "close_ts": session.close_ts.isoformat(),
    }
    assert payload["sequence_window"]["windows"]["1m"]["bar_count"] == 30
    assert payload["sequence_window"]["windows"]["3h"]["window_end"] == cutoff.isoformat()
    assert payload["sequence_window"]["windows"]["3h"]["bar_count"] == 2
    assert "999.123" not in encoded
    assert "7777" not in encoded
    assert "open" not in payload["sequence_window"]["windows"]["1m"]


@pytest.mark.parametrize(
    ("mutate", "status"),
    (
        (lambda bars, _cutoff: bars[:-1], "missing"),
        (lambda bars, _cutoff: (*bars[:120], *bars[121:]), "non_contiguous"),
        (lambda bars, _cutoff: (*bars, bars[-1]), "duplicate"),
        (
            lambda bars, _cutoff: (*bars[:-1], replace(bars[-1], complete=False)),
            "incomplete",
        ),
        (
            lambda bars, cutoff: (*bars[:-1], replace(bars[-1], start_ts=cutoff)),
            "future",
        ),
        (
            lambda bars, _cutoff: (*bars[:-1], replace(bars[-1], timeframe=Timeframe.M5)),
            "misaligned",
        ),
        (
            lambda bars, _cutoff: (*bars[:-1], replace(bars[-1], symbol="QQQ")),
            "misaligned",
        ),
    ),
)
def test_rejects_invalid_source_input_shapes(mutate, status: str) -> None:
    session, cutoff = _regular_session(date(2026, 7, 1))

    with pytest.raises(ProspectiveSpyIntradaySessionInputError) as raised:
        build_prospective_spy_intraday_session_record(
            mutate(_session_bars(session, cutoff), cutoff),
            session=session,
            cutoff=cutoff,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )

    assert raised.value.status == status


def test_rejects_empty_source_and_mixed_market_identity() -> None:
    session, cutoff = _regular_session(date(2026, 7, 1))
    with pytest.raises(ProspectiveSpyIntradaySessionInputError) as missing:
        build_prospective_spy_intraday_session_record(
            (),
            session=session,
            cutoff=cutoff,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )
    assert missing.value.status == "missing"

    bars = _session_bars(session, cutoff)
    with pytest.raises(ProspectiveSpyIntradaySessionInputError) as mixed_market:
        build_prospective_spy_intraday_session_record(
            (*bars[:-1], replace(bars[-1], market="NYSE")),
            session=session,
            cutoff=cutoff,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )
    assert mixed_market.value.status == "misaligned"


@pytest.mark.parametrize(
    "session,cutoff",
    (
        (
            SessionWindow(
                datetime(2026, 7, 1, 13, 30, tzinfo=UTC),
                datetime(2026, 7, 1, 17, 0, tzinfo=UTC),
            ),
            datetime(2026, 7, 1, 19, 30, tzinfo=UTC),
        ),
        (
            SessionWindow(
                datetime(2026, 7, 1, 14, 30, tzinfo=UTC),
                datetime(2026, 7, 1, 21, 0, tzinfo=UTC),
            ),
            datetime(2026, 7, 1, 20, 30, tzinfo=UTC),
        ),
        (
            SessionWindow(
                datetime(2026, 7, 4, 13, 30, tzinfo=UTC),
                datetime(2026, 7, 4, 20, 0, tzinfo=UTC),
            ),
            datetime(2026, 7, 4, 19, 30, tzinfo=UTC),
        ),
    ),
    ids=("early-close", "summer-dst-misaligned", "weekend"),
)
def test_rejects_non_regular_or_dst_misaligned_session_geometry(
    session: SessionWindow,
    cutoff: datetime,
) -> None:
    with pytest.raises(ProspectiveSpyIntradaySessionInputError) as raised:
        build_prospective_spy_intraday_session_record(
            (),
            session=session,
            cutoff=cutoff,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )

    assert raised.value.status == "misaligned"


def test_rejects_nonfixed_cutoff() -> None:
    session, cutoff = _regular_session(date(2026, 1, 2))
    with pytest.raises(ProspectiveSpyIntradaySessionInputError) as raised:
        build_prospective_spy_intraday_session_record(
            _session_bars(session, cutoff),
            session=session,
            cutoff=cutoff - timedelta(minutes=1),
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )

    assert raised.value.status == "misaligned"


def _regular_session(session_date: date) -> tuple[SessionWindow, datetime]:
    open_ts = datetime.combine(session_date, time(9, 30), _EASTERN).astimezone(UTC)
    close_ts = datetime.combine(session_date, time(16, 0), _EASTERN).astimezone(UTC)
    cutoff = datetime.combine(session_date, time(15, 30), _EASTERN).astimezone(UTC)
    return SessionWindow(open_ts, close_ts), cutoff


def _session_bars(
    session: SessionWindow,
    cutoff: datetime,
    *,
    market: str = "IEX",
) -> tuple[Bar, ...]:
    count = (cutoff - session.open_ts) // Timeframe.M1.duration
    return tuple(
        Bar(
            symbol="SPY",
            market=market,
            timeframe=Timeframe.M1,
            start_ts=session.open_ts + Timeframe.M1.duration * index,
            open=Decimal("999.123"),
            high=Decimal("999.223"),
            low=Decimal("999.023"),
            close=Decimal("999.173"),
            volume=Decimal("7777"),
            complete=True,
        )
        for index in range(count)
    )
