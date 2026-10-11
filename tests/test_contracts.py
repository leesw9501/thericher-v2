from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, Rounded, localcontext

import pytest

from thericher_v2.contracts import (
    Bar,
    EmergencyState,
    Timeframe,
    decision_target_binding_ref,
)


def test_bar_requires_utc_and_normalizes_symbol() -> None:
    bar = Bar(
        symbol="aapl",
        market="us",
        timeframe=Timeframe.M5,
        start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1000"),
    )

    assert bar.symbol == "AAPL"
    assert bar.market == "US"
    assert bar.end_ts == datetime(2026, 1, 2, 14, 35, tzinfo=UTC)


def test_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        Bar(
            symbol="AAPL",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=datetime(2026, 1, 2, 14, 30),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_bar_normalizes_timeframe_at_construction() -> None:
    bar = Bar(
        symbol="AAPL",
        market="US",
        timeframe="1m",  # type: ignore[arg-type]
        start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )

    assert bar.timeframe is Timeframe.M1
    assert bar.end_ts == datetime(2026, 1, 2, 14, 31, tzinfo=UTC)

    with pytest.raises(ValueError):
        Bar(
            symbol="AAPL",
            market="US",
            timeframe="invalid",  # type: ignore[arg-type]
            start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_bar_rejects_ambiguous_complete_values() -> None:
    with pytest.raises(TypeError, match="complete must be bool"):
        Bar(
            symbol="AAPL",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
            complete="false",  # type: ignore[arg-type]
        )


def test_emergency_state_blocks_new_orders_only_when_stop_is_active() -> None:
    clear = EmergencyState(
        stop_new_orders=False,
        cancel_open_orders_requested=True,
        reason="cancel_only",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    stopped = EmergencyState(
        stop_new_orders=True,
        cancel_open_orders_requested=False,
        reason="stop",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert not clear.blocks_new_orders
    assert stopped.blocks_new_orders


def _expected_target_ref(marker: str) -> str:
    encoded = json.dumps(
        {
            "kind": "decision_target_binding_v1",
            "symbol": "SPY",
            "market": "NAS",
            "decision_class": "enter",
            "target_exposure": marker,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return "ref:" + hashlib.sha256(encoded).hexdigest()


def _target_ref(value: str) -> str:
    return decision_target_binding_ref(
        symbol="spy", market="nas", decision_class="enter", target_exposure=Decimal(value)
    )


@pytest.mark.parametrize("precision", (2, 28, 80))
@pytest.mark.parametrize("rounding", (ROUND_FLOOR, ROUND_HALF_EVEN))
@pytest.mark.parametrize(
    ("value", "marker"),
    (
        ("-0E-80", "0"),
        ("0E+80", "0"),
        ("1.000", "1"),
        ("0.1000", "0.1"),
        ("1000E-6", "0.001"),
        ("0.123456789012345678901234", "0.123456789012345678901234"),
        ("0.1234567890123456789012345678901234567890", "0.123456789012345678901234567890123456789"),
        ("1E-80", "0." + "0" * 79 + "1"),
        ("0.99999999999999999999999999999", "0.99999999999999999999999999999"),
    ),
)
def test_target_identity_is_exact_without_using_or_mutating_decimal_context(
    precision: int,
    rounding: str,
    value: str,
    marker: str,
) -> None:
    with localcontext() as context:
        context.prec = precision
        context.rounding = rounding
        context.Emin, context.Emax = -9, 9
        context.clamp, context.capitals = 1, 0
        for signal in context.traps:
            context.traps[signal] = True
        context.clear_flags()
        context.flags[Rounded] = True
        before = context.copy()

        assert _target_ref(value) == _expected_target_ref(marker)

        assert context.prec == before.prec
        assert context.rounding == before.rounding
        assert (context.Emin, context.Emax) == (before.Emin, before.Emax)
        assert (context.clamp, context.capitals) == (before.clamp, before.capitals)
        assert context.traps == before.traps
        assert context.flags == before.flags


@pytest.mark.parametrize("precision", (2, 28, 80))
@pytest.mark.parametrize(
    "spellings",
    (
        ("0", "-0.000", "0E+9"),
        ("1", "1.00", "100E-2"),
        (
            "0.123456789012345678901234",
            "0.12345678901234567890123400",
            "123456789012345678901234E-24",
        ),
    ),
)
def test_target_identity_agrees_for_exact_equivalent_spellings(
    precision: int,
    spellings: tuple[str, ...],
) -> None:
    with localcontext() as context:
        context.prec = precision
        assert len({_target_ref(value) for value in spellings}) == 1


@pytest.mark.parametrize("precision", (2, 28, 80))
def test_target_identity_distinguishes_neighbors_beyond_legacy_precision(precision: int) -> None:
    with localcontext() as context:
        context.prec = precision
        assert _target_ref("0.123456789012345678901234567891") != _target_ref(
            "0.123456789012345678901234567892"
        )


@pytest.mark.parametrize("value", ("-0.00", "1.000", "0.1000", "0.123456789012345678901234"))
def test_target_identity_preserves_compatible_default_precision_legacy_bytes(value: str) -> None:
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        exposure = Decimal(value)
        legacy_marker = "0" if exposure == 0 else format(exposure.normalize(), "f")
        assert _target_ref(value) == _expected_target_ref(legacy_marker)


def test_new_exact_identity_does_not_claim_rounded_legacy_identity_compatibility() -> None:
    value = "0.123456789012345678901234567891"
    with localcontext() as context:
        context.prec = 28
        rounded_legacy = _expected_target_ref(format(Decimal(value).normalize(), "f"))
        assert _target_ref(value) != rounded_legacy
