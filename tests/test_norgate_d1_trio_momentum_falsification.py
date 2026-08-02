from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import norgate_d1_trio_momentum_falsification as momentum


def test_target_free_plan_uses_the_fixed_causal_window_and_purge() -> None:
    streams = momentum._validated_panel(_panel())
    validation_indices, long_indices = momentum._target_free_validation_indices(streams)

    assert validation_indices == tuple(range(371, 511))
    assert long_indices == validation_indices
    assert len(tuple(range(20, 350))) == 330
    assert len(validation_indices) == 140
    assert len(tuple(index for index in validation_indices if index + 2 < 511)) == 138


def test_validation_target_opens_do_not_change_target_free_decisions() -> None:
    baseline = momentum._target_free_validation_indices(momentum._validated_panel(_panel()))
    changed = _replace_spy_opens(_panel(), start=372)

    assert momentum._target_free_validation_indices(momentum._validated_panel(changed)) == baseline


def test_minimum_long_floor_rejects_before_any_target_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def target_access_forbidden(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("the long-count preflight must not inspect validation targets")

    monkeypatch.setattr(momentum, "_target_is_strictly_positive", target_access_forbidden)
    result = momentum.run_norgate_d1_trio_momentum_falsification(_panel(qqq_after=371))

    assert result.status == "rejected"
    assert result.reason == "insufficient_validation_long_decisions"
    assert result.target_evaluation_performed is False
    assert result.rule_hit_count is None
    assert result.always_long_hit_count is None


def test_comparator_uses_all_eligible_slots_and_win_stays_inconclusive() -> None:
    result = momentum.run_norgate_d1_trio_momentum_falsification(
        _panel(qqq_after=411, positive_target_through=410)
    )

    assert result.status == "inconclusive_non_promoting"
    assert result.reason == "rule_hit_rate_strictly_above_always_long"
    assert result.validation_long_decision_count == 40
    assert result.rule_hit_count == 40
    assert result.always_long_hit_count == 40
    payload = result.safe_payload()
    assert payload["rule_hit_rate"] == {
        "hit_count": 40,
        "decision_count": 40,
        "hit_rate": "1",
    }
    assert payload["always_long_hit_rate"]["decision_count"] == 138
    assert payload["promotion_allowed"] is False
    assert "701.234" not in str(payload)


def test_equal_hit_rates_are_rejected() -> None:
    result = momentum.run_norgate_d1_trio_momentum_falsification(
        _panel(flat_validation_targets=True)
    )

    assert result.status == "rejected"
    assert result.reason == "rule_hit_rate_not_above_always_long"
    assert result.rule_hit_count == 0
    assert result.always_long_hit_count == 0


@pytest.mark.parametrize("kind", ["missing", "length", "misaligned", "incomplete", "market", "tz"])
def test_invalid_panel_contracts_are_rejected(kind: str) -> None:
    panel = _panel()
    invalid = {symbol: values for symbol, values in panel.items()}
    if kind == "missing":
        del invalid["IWM"]
    elif kind == "length":
        invalid["QQQ"] = invalid["QQQ"][:-1]
    elif kind == "misaligned":
        invalid["IWM"] = (
            *invalid["IWM"][:-1],
            replace(invalid["IWM"][-1], start_ts=datetime(2030, 1, 1, tzinfo=UTC)),
        )
    elif kind == "incomplete":
        invalid["SPY"] = (replace(invalid["SPY"][0], complete=False), *invalid["SPY"][1:])
    elif kind == "market":
        invalid["SPY"] = (replace(invalid["SPY"][0], market="CA"), *invalid["SPY"][1:])
    else:
        object.__setattr__(
            invalid["SPY"][0],
            "start_ts",
            datetime(2024, 1, 1, tzinfo=timezone(timedelta(0), "other")),
        )

    with pytest.raises(ValueError):
        momentum.run_norgate_d1_trio_momentum_falsification(invalid)


def test_core_remains_offline_and_has_no_public_plan_injection_surface() -> None:
    source = inspect.getsource(momentum)
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert not imported_roots.intersection(
        {"os", "pathlib", "socket", "subprocess", "requests", "norgatedata", "torch", "numpy"}
    )
    assert not hasattr(momentum, "evaluate_norgate_d1_trio_momentum_falsification")
    assert "OrderIntent" not in source
    assert "os.environ" not in source


def _panel(
    *,
    qqq_after: int | None = None,
    positive_target_through: int | None = None,
    flat_validation_targets: bool = False,
) -> dict[str, tuple[Bar, ...]]:
    return {
        symbol: tuple(
            _bar(
                symbol,
                index,
                _close(symbol, index, qqq_after),
                _open(index, positive_target_through, flat_validation_targets),
            )
            for index in range(511)
        )
        for symbol in momentum.NORGATE_D1_TRIO_MOMENTUM_SYMBOLS
    }


def _close(symbol: str, index: int, qqq_after: int | None) -> Decimal:
    if symbol == "QQQ" and qqq_after is not None and index >= qqq_after:
        return Decimal("2")
    return Decimal("701.234") + Decimal(index)


def _open(index: int, positive_target_through: int | None, flat: bool) -> Decimal:
    if flat and index >= 372:
        return Decimal("1000")
    if positive_target_through is not None and index > positive_target_through + 2:
        return Decimal("2")
    return Decimal("100") + Decimal(index)


def _bar(symbol: str, index: int, close: Decimal, open_price: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open=open_price,
        high=max(close, open_price) + Decimal("1"),
        low=min(close, open_price) - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _replace_spy_opens(
    panel: dict[str, tuple[Bar, ...]],
    *,
    start: int,
) -> dict[str, tuple[Bar, ...]]:
    changed = {symbol: values for symbol, values in panel.items()}
    spy = list(changed["SPY"])
    for index in range(start, 511):
        current = spy[index]
        spy[index] = _bar("SPY", index, current.close, Decimal("1000") - Decimal(index))
    changed["SPY"] = tuple(spy)
    return changed
