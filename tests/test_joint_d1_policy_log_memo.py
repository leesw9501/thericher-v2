"""Synthetic-only causal memo equivalence, boundedness and lifetime checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import joint_d1_policy_context as context


def bars(count=42):
    result = {}
    for j, symbol in enumerate(context.SYMBOLS):
        records = []
        for i in range(count):
            opened = Decimal(10000 + 1000 * j + 3 * i)
            closed = opened + Decimal(i % 7 - 3)
            records.append(
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=datetime(2001, 1, 1, tzinfo=UTC) + timedelta(days=i),
                    open=opened,
                    high=max(opened, closed) + 2,
                    low=min(opened, closed) - 2,
                    close=closed,
                    volume=Decimal(0),
                    complete=True,
                )
            )
        result[symbol] = tuple(records)
    return result


def build(source, i=32, *, memo=None, vintages=None, cutoff=None):
    return context.build_joint_d1_policy_context(
        source,
        vintage_ref_by_symbol=vintages or dict.fromkeys(context.SYMBOLS, "synthetic-vintage"),
        scheduled_dates=tuple(date(2001, 1, 1) + timedelta(days=k) for k in range(i - 32, i)),
        decision_at=cutoff or datetime(2001, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=i),
        log_memo=memo,
    )


def facts_or_features(source, *, memo=None, **kwargs):
    try:
        result = build(source, memo=memo, **kwargs)
        return result.features, result.safe_facts()
    except context.JointD1PolicyInputUnavailable as exc:
        return exc.safe_facts()
    except ValueError as exc:
        return dict(status="contract_invalid", reason_code=exc.args[0])


def test_overlapping_windows_are_exact_and_arithmetic_calls_are_reduced(monkeypatch):
    source, calls = bars(), []
    original = context._log_ratio

    def counted(n, d):
        calls.append(None)
        return original(n, d)

    monkeypatch.setattr(context, "_log_ratio", counted)
    expected = [facts_or_features(source, i=i) for i in range(32, 42)]
    baseline = len(calls)
    assert baseline == 10 * 9 * 31
    calls.clear()
    with context.JointD1PolicyLogMemo() as memo:
        actual = [facts_or_features(source, i=i, memo=memo) for i in range(32, 42)]
        assert actual == expected
        assert memo.safe_facts()["hits"] > 0
        assert memo.safe_facts()["misses"] == len(calls)
        assert len(calls) <= 9 * 31 + 9 * 9
        assert len(calls) < baseline / 5
    assert memo.safe_facts()["entries"] == 0
    assert memo.safe_facts()["status"] == "closed"


@pytest.mark.parametrize("symbol", context.SYMBOLS)
@pytest.mark.parametrize(
    "fault", ("missing", "duplicate", "reordered", "incomplete", "identity", "nan")
)
def test_warm_memo_never_bypasses_required_past_validation(symbol, fault):
    source = bars()
    changed = dict(source)
    records = list(changed[symbol])
    if fault == "missing":
        del records[12]
    elif fault == "duplicate":
        records.insert(12, records[12])
    elif fault == "reordered":
        records[12], records[13] = records[13], records[12]
    else:
        records[12] = replace(records[12])
        field, value = {
            "incomplete": ("complete", False),
            "identity": ("symbol", "OTHER"),
            "nan": ("close", Decimal("NaN")),
        }[fault]
        object.__setattr__(records[12], field, value)
    changed[symbol] = tuple(records)
    expected = facts_or_features(changed)
    assert expected["status"] == "input_unavailable"
    with context.JointD1PolicyLogMemo() as memo:
        build(source, memo=memo)
        before = memo.safe_facts()
        assert facts_or_features(changed, memo=memo) == expected
        assert memo.safe_facts() == before


@pytest.mark.parametrize("symbol", context.SYMBOLS)
@pytest.mark.parametrize("fault", ("absent", "values", "incomplete", "duplicate", "identity"))
def test_current_future_mutations_do_not_change_input_or_mask(symbol, fault):
    source, changed = bars(), bars()
    records = list(changed[symbol])
    if fault == "absent":
        records = records[:32]
    elif fault == "duplicate":
        records.extend(records[32:])
    else:
        for i in range(32, len(records)):
            records[i] = replace(records[i])
            field, value = {
                "values": ("close", Decimal("NaN")),
                "incomplete": ("complete", False),
                "identity": ("symbol", "OTHER"),
            }[fault]
            object.__setattr__(records[i], field, value)
    changed[symbol] = tuple(records)
    with context.JointD1PolicyLogMemo() as memo:
        expected = facts_or_features(source, memo=memo)
        assert facts_or_features(changed, memo=memo) == expected
        assert facts_or_features(changed) == expected


def test_changed_past_prices_recompute_exactly_not_by_date_identity():
    source, changed = bars(), bars()
    item = changed["SPY"][12]
    modified = replace(item, close=item.close + 8, high=max(item.high, item.close + 8))
    changed["SPY"] = (*changed["SPY"][:12], modified, *changed["SPY"][13:])
    expected = facts_or_features(changed)
    with context.JointD1PolicyLogMemo() as memo:
        original = facts_or_features(source, memo=memo)
        before = memo.safe_facts()["misses"]
        assert facts_or_features(changed, memo=memo) == expected
        assert original[0] != expected[0]
        assert memo.safe_facts()["misses"] > before


def test_vintage_and_cutoff_checks_are_not_cached():
    source = bars()
    with context.JointD1PolicyLogMemo() as memo:
        build(source, memo=memo)
        before = memo.safe_facts()
        for kwargs in (
            dict(vintages=dict(SPY="a", QQQ="b", IWM="a")),
            dict(cutoff=datetime(2001, 2, 1, 12, tzinfo=UTC)),
        ):
            expected = facts_or_features(source, **kwargs)
            assert expected["status"] in {"input_unavailable", "contract_invalid"}
            assert facts_or_features(source, memo=memo, **kwargs) == expected
        assert memo.safe_facts() == before


def test_capacity_is_bounded_lru_recomputes_evicted_pair(monkeypatch):
    calls, original = [], context._log_ratio

    def counted(n, d):
        calls.append(None)
        return original(n, d)

    monkeypatch.setattr(context, "_log_ratio", counted)
    with context.JointD1PolicyLogMemo() as memo:
        first = memo.ratio(Decimal(100), Decimal(77))
        for i in range(context.LOG_MEMO_MAX_ENTRIES):
            memo.ratio(Decimal(101 + i), Decimal(77))
            assert memo.safe_facts()["entries"] <= context.LOG_MEMO_MAX_ENTRIES
        count = len(calls)
        assert memo.ratio(Decimal(100), Decimal(77)) == first
        assert len(calls) == count + 1
        assert memo.safe_facts()["entries"] == context.LOG_MEMO_MAX_ENTRIES
    assert memo.safe_facts()["entries"] == 0


def test_no_failure_or_private_values_survive_scope(monkeypatch):
    calls = []

    def fail(n, d):
        calls.append(None)
        raise context.JointD1PolicyInputUnavailable("features_not_representable")

    monkeypatch.setattr(context, "_log_ratio", fail)
    with context.JointD1PolicyLogMemo() as memo:
        for _ in range(2):
            with pytest.raises(
                context.JointD1PolicyInputUnavailable, match="features_not_representable"
            ):
                memo.ratio(Decimal(100), Decimal(77))
        assert memo.safe_facts()["entries"] == 0
        assert len(calls) == 2
    assert not memo._cache
    assert "Decimal" not in repr(memo)
    with pytest.raises(ValueError, match="log_memo_scope"):
        memo.ratio(Decimal(100), Decimal(77))
    with pytest.raises(ValueError, match="log_memo_scope"):
        with memo:
            pass


def test_scope_clears_on_unhandled_exception():
    memo = context.JointD1PolicyLogMemo()
    with pytest.raises(RuntimeError):
        with memo:
            memo.ratio(Decimal(100), Decimal(77))
            raise RuntimeError("synthetic interruption")
    assert memo.safe_facts()["entries"] == 0
    assert memo.safe_facts()["status"] == "closed"


@pytest.mark.parametrize(
    "n,d",
    (("1E99999", "1E-99999"), ("100.000", "100"), ("0.000000123456789", "987654321.987654321")),
)
def test_precision_and_extreme_ratios_unchanged(n, d):
    numerator, denominator = Decimal(n), Decimal(d)
    expected = context._log_ratio(numerator, denominator)
    with context.JointD1PolicyLogMemo() as memo:
        assert memo.ratio(numerator, denominator) == expected
        with localcontext() as ctx:
            ctx.prec = 6
            assert memo.ratio(numerator, denominator) == expected


def prep_rows_plan():
    source = bars()
    rows = {
        s: tuple(
            SimpleNamespace(
                session_date=b.start_ts.date(),
                adj_open=b.open,
                adj_high=b.high,
                adj_low=b.low,
                adj_close=b.close,
            )
            for b in seq
        )
        for s, seq in source.items()
    }
    days = [(date(2001, 1, 1) + timedelta(days=i)).isoformat() for i in range(42)]
    spec = dict(
        period="TRAIN",
        bounds=[32, 42],
        quarters=[32],
        decisions=[
            dict(
                index=i,
                session_date=days[i],
                decision_at=f"{days[i]}T14:30:00+00:00",
                scheduled_dates=days[i - 32 : i],
            )
            for i in range(32, 42)
        ],
    )
    return rows, dict(days=days, periods=[spec])


def test_prepare_inputs_wires_one_memo_and_preserves_exact_output(monkeypatch):
    from thericher_v2.research import tiingo_joint_d1_policy as study

    rows, plan = prep_rows_plan()
    instances, cls, builder = (
        [],
        context.JointD1PolicyLogMemo,
        context.build_joint_d1_policy_context,
    )

    class Observed(cls):
        def __init__(self):
            super().__init__()
            instances.append(self)

    monkeypatch.setattr(context, "JointD1PolicyLogMemo", Observed)
    actual = study.prepare_inputs(rows, plan, deadline=float("inf"))
    assert len(instances) == 1
    assert instances[0].safe_facts()["entries"] == 0
    assert instances[0].safe_facts()["hits"] > 0

    def uncached(*args, **kwargs):
        kwargs.pop("log_memo")
        return builder(*args, **kwargs)

    monkeypatch.setattr(context, "build_joint_d1_policy_context", uncached)
    expected = study.prepare_inputs(rows, plan, deadline=float("inf"))
    assert actual[0].facts == expected[0].facts
    assert actual[0].marks == expected[0].marks
    assert np.array_equal(actual[0].x, expected[0].x)


def test_prepare_inputs_exception_clears_local_cache(monkeypatch):
    from thericher_v2.research import tiingo_joint_d1_policy as study

    rows, plan = prep_rows_plan()
    instances, cls = [], context.JointD1PolicyLogMemo

    class Observed(cls):
        def __init__(self):
            super().__init__()
            instances.append(self)

    monkeypatch.setattr(context, "JointD1PolicyLogMemo", Observed)
    with pytest.raises(ValueError, match="hard_timeout"):
        study.prepare_inputs(rows, plan, deadline=0)
    assert len(instances) == 1
    assert instances[0].safe_facts()["status"] == "closed"
    assert instances[0].safe_facts()["entries"] == 0
