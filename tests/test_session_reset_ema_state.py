from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import thericher_v2.models.session_reset_ema_state as session_reset_ema_state
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.session_reset_ema_state import SessionResetEmaStateRule

_FIRST_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_SECOND_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 4, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 4, 20, 0, tzinfo=UTC),
)


def test_module_has_no_provider_broker_network_or_credential_route() -> None:
    source = inspect.getsource(session_reset_ema_state)
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


def test_default_periods_expose_warmup_as_missing_until_slow_ema_seeds() -> None:
    rule = SessionResetEmaStateRule()
    warmup_bars = _bars(_FIRST_SESSION, [Decimal("100")] * 29)

    warmup = rule.decide(
        warmup_bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=warmup_bars[-1].end_ts,
    )

    assert (
        warmup.action,
        warmup.position_after,
        warmup.input_status,
        warmup.reason,
    ) == ("hold", "flat", "missing", "ema_warmup")
    assert warmup.feature_window_end == warmup_bars[-1].end_ts
    assert warmup.fast_ema is None
    assert warmup.slow_ema is None

    ready_bars = [*warmup_bars, _bar(_FIRST_SESSION, 29, close=Decimal("100"))]
    ready = rule.decide(
        ready_bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=ready_bars[-1].end_ts,
    )

    assert (ready.input_status, ready.reason) == ("ready", "fast_not_above_entry_threshold")
    assert ready.feature_window_end == ready_bars[-1].end_ts
    assert (ready.fast_ema, ready.slow_ema) == (Decimal("100"), Decimal("100"))


def test_each_ema_uses_its_own_sma_seed_then_decimal_recursive_updates() -> None:
    bars = _bars(_FIRST_SESSION, [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")])

    rule = SessionResetEmaStateRule(
        fast_period=2,
        slow_period=3,
        tolerance=Decimal("0"),
    )
    decision = rule.decide(
        bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=bars[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.input_status) == (
        "enter",
        "long",
        "ready",
    )
    assert (decision.fast_ema, decision.slow_ema) == (Decimal("35"), Decimal("30"))


def test_entry_threshold_is_strict_at_the_configured_tolerance() -> None:
    rule = SessionResetEmaStateRule(fast_period=2, slow_period=3)
    at_threshold_bars = _bars(
        _FIRST_SESSION,
        [Decimal("19991"), Decimal("19991"), Decimal("19991"), Decimal("20009")],
    )

    at_threshold = rule.decide(
        at_threshold_bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=at_threshold_bars[-1].end_ts,
    )

    assert (at_threshold.fast_ema, at_threshold.slow_ema) == (Decimal("20003"), Decimal("20000"))
    assert at_threshold.fast_ema == at_threshold.slow_ema * (Decimal("1") + rule.tolerance)
    assert (at_threshold.action, at_threshold.position_after, at_threshold.reason) == (
        "hold",
        "flat",
        "fast_not_above_entry_threshold",
    )

    above_threshold_bars = _bars(
        _FIRST_SESSION,
        [Decimal("19991"), Decimal("19991"), Decimal("19991"), Decimal("20010")],
    )
    above_threshold = rule.decide(
        above_threshold_bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=above_threshold_bars[-1].end_ts,
    )

    assert (above_threshold.action, above_threshold.position_after) == ("enter", "long")
    assert above_threshold.reason == "fast_above_entry_threshold"


def test_long_position_exits_only_when_fast_ema_is_strictly_below_slow_ema() -> None:
    bars = _bars(_FIRST_SESSION, [Decimal("100"), Decimal("100"), Decimal("100"), Decimal("70")])

    decision = SessionResetEmaStateRule(fast_period=2, slow_period=3).decide(
        bars,
        position="long",
        session=_FIRST_SESSION,
        as_of=bars[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.reason) == (
        "exit",
        "flat",
        "fast_below_slow",
    )
    assert (decision.fast_ema, decision.slow_ema) == (Decimal("80"), Decimal("85"))


def test_prior_session_history_cannot_seed_the_current_declared_session() -> None:
    previous_session = _bars(_FIRST_SESSION, [Decimal("100")] * 30)
    current_session = _bars(_SECOND_SESSION, [Decimal("200")])

    decision = SessionResetEmaStateRule().decide(
        [*previous_session, *current_session],
        position="flat",
        session=_SECOND_SESSION,
        as_of=current_session[-1].end_ts,
    )

    assert (decision.action, decision.position_after, decision.input_status, decision.reason) == (
        "hold",
        "flat",
        "missing",
        "ema_warmup",
    )
    assert decision.feature_window_end == current_session[-1].end_ts


def test_rejects_incomplete_bars() -> None:
    incomplete = replace(_bar(_FIRST_SESSION, 0), complete=False)

    with pytest.raises(ValueError, match="complete"):
        SessionResetEmaStateRule().decide(
            [incomplete],
            position="flat",
            session=_FIRST_SESSION,
            as_of=incomplete.end_ts,
        )


def test_rejects_noncontiguous_bars_inside_the_declared_session() -> None:
    bars = [_bar(_FIRST_SESSION, 0), _bar(_FIRST_SESSION, 2)]

    with pytest.raises(ValueError, match="contiguous"):
        SessionResetEmaStateRule().decide(
            bars,
            position="flat",
            session=_FIRST_SESSION,
            as_of=bars[-1].end_ts,
        )


def test_rejects_mismatched_session_identity() -> None:
    bars = [_bar(_FIRST_SESSION, 0), replace(_bar(_FIRST_SESSION, 1), symbol="SPY")]

    with pytest.raises(ValueError, match="share symbol, market, and timeframe"):
        SessionResetEmaStateRule().decide(
            bars,
            position="flat",
            session=_FIRST_SESSION,
            as_of=bars[-1].end_ts,
        )


def test_later_completed_bars_cannot_change_an_earlier_causal_decision() -> None:
    bars = _bars(_FIRST_SESSION, [Decimal("100")] * 30)
    as_of = bars[-1].end_ts
    later_bar = _bar(_FIRST_SESSION, 30, close=Decimal("999"))

    original = SessionResetEmaStateRule().decide(
        bars,
        position="flat",
        session=_FIRST_SESSION,
        as_of=as_of,
    )
    changed = SessionResetEmaStateRule().decide(
        [*bars, later_bar],
        position="flat",
        session=_FIRST_SESSION,
        as_of=as_of,
    )

    assert changed == original


@pytest.mark.parametrize(
    ("fast_period", "slow_period", "tolerance"),
    [
        (0, 30, Decimal("0")),
        (15, 15, Decimal("0")),
        (15, 30, Decimal("-0.00001")),
    ],
)
def test_rule_validates_periods_and_tolerance(
    fast_period: int,
    slow_period: int,
    tolerance: Decimal,
) -> None:
    with pytest.raises(ValueError):
        SessionResetEmaStateRule(
            fast_period=fast_period,
            slow_period=slow_period,
            tolerance=tolerance,
        )


def _bars(session: SessionWindow, closes: list[Decimal]) -> list[Bar]:
    return [_bar(session, index, close=close) for index, close in enumerate(closes)]


def _bar(session: SessionWindow, minute_offset: int, *, close: Decimal = Decimal("100")) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=session.open_ts + timedelta(minutes=minute_offset),
        open=close,
        high=close,
        low=close,
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
