from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import thericher_v2.models.session_reset_donchian as session_reset_donchian
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.session_reset_donchian import SessionResetDonchianRule

_FIRST_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_SECOND_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 4, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 4, 20, 0, tzinfo=UTC),
)


def test_module_has_no_kis_broker_network_or_credential_route() -> None:
    source = inspect.getsource(session_reset_donchian)
    imports = _imported_modules(source)

    forbidden_prefixes = (
        "dotenv",
        "http",
        "os",
        "requests",
        "socket",
        "subprocess",
        "thericher_v2.data.kis",
        "thericher_v2.execution",
        "urllib",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imports
        for prefix in forbidden_prefixes
    )
    assert "KIS" not in source
    assert "credential" not in source.lower()


def test_flat_position_enters_after_close_exceeds_prior_twenty_bar_high() -> None:
    bars = _baseline_bars(_FIRST_SESSION, 20)
    bars.append(_bar(_FIRST_SESSION, 20, close=Decimal("102"), high=Decimal("102")))

    decision = SessionResetDonchianRule().decide(
        bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=bars[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.reason) == (
        "enter",
        "long",
        "entry_breakout",
    )
    assert decision.feature_window_end == bars[-1].end_ts


def test_long_position_exits_after_close_falls_below_prior_ten_bar_low() -> None:
    bars = _baseline_bars(_FIRST_SESSION, 10)
    bars.append(_bar(_FIRST_SESSION, 10, close=Decimal("98"), low=Decimal("98")))

    decision = SessionResetDonchianRule().decide(
        bars,
        position="long",
        session=_FIRST_SESSION,
        as_of=bars[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.reason) == (
        "exit",
        "flat",
        "exit_breakdown",
    )


def test_future_completed_bars_do_not_change_an_earlier_causal_decision() -> None:
    bars = _baseline_bars(_FIRST_SESSION, 20)
    bars.append(_bar(_FIRST_SESSION, 20, close=Decimal("102"), high=Decimal("102")))
    as_of = bars[-1].end_ts
    future_bar = _bar(_FIRST_SESSION, 21, high=Decimal("999"))

    original = SessionResetDonchianRule().decide(
        bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=as_of,
    )
    changed = SessionResetDonchianRule().decide(
        [*bars, future_bar],
        position="flat",
        session=_FIRST_SESSION,
        as_of=as_of,
    )

    assert changed == original


def test_prior_session_history_is_excluded_after_a_declared_session_reset() -> None:
    previous_session = _baseline_bars(_FIRST_SESSION, 20)
    current_session = [_bar(_SECOND_SESSION, 0)]

    decision = SessionResetDonchianRule().decide(
        [*previous_session, *current_session],
        position="flat",
        session=_SECOND_SESSION,
        as_of=current_session[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.reason) == (
        "hold",
        "flat",
        "insufficient_entry_history",
    )
    assert decision.feature_window_end == current_session[-1].end_ts


def test_insufficient_current_session_history_holds_flat() -> None:
    bars = _baseline_bars(_FIRST_SESSION, 20)

    decision = SessionResetDonchianRule().decide(
        bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=bars[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.reason) == (
        "hold",
        "flat",
        "insufficient_entry_history",
    )


@pytest.mark.parametrize(
    "minute_offsets",
    [
        (1, 0),
        (0, 0),
    ],
)
def test_rejects_unordered_or_duplicate_timestamps(minute_offsets: tuple[int, int]) -> None:
    bars = [_bar(_FIRST_SESSION, minute_offset) for minute_offset in minute_offsets]

    with pytest.raises(ValueError, match="strictly timestamp-ordered"):
        SessionResetDonchianRule().decide(
            bars,
            position="flat",
            session=_FIRST_SESSION,
            as_of=_FIRST_SESSION.open_ts + timedelta(minutes=2),
        )


def test_rejects_incomplete_bars() -> None:
    incomplete = replace(_bar(_FIRST_SESSION, 0), complete=False)

    with pytest.raises(ValueError, match="complete"):
        SessionResetDonchianRule().decide(
            [incomplete],
            position="flat",
            session=_FIRST_SESSION,
            as_of=incomplete.end_ts,
        )


def test_rejects_a_gap_inside_the_declared_session() -> None:
    bars = [_bar(_FIRST_SESSION, 0), _bar(_FIRST_SESSION, 2)]

    with pytest.raises(ValueError, match="contiguous"):
        SessionResetDonchianRule().decide(
            bars,
            position="flat",
            session=_FIRST_SESSION,
            as_of=bars[-1].end_ts,
        )


def _baseline_bars(session: SessionWindow, count: int) -> list[Bar]:
    return [_bar(session, index) for index in range(count)]


def _bar(
    session: SessionWindow,
    minute_offset: int,
    *,
    close: Decimal = Decimal("100"),
    high: Decimal = Decimal("101"),
    low: Decimal = Decimal("99"),
) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=session.open_ts + timedelta(minutes=minute_offset),
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
    )


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports
