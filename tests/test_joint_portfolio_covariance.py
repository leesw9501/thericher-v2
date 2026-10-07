import builtins
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pandas_market_calendars as mcal
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research.joint_portfolio_covariance import (
    CONTEXT_CLOSES,
    CONTEXT_RETURNS,
    SYMBOLS,
    JointPortfolioInputUnavailable,
    build_joint_portfolio_covariance,
)

VINTAGE = "sha256:" + "a" * 64


def bar(symbol, day, close=Decimal("100"), **changes):
    fields = {
        "symbol": symbol,
        "market": "US",
        "timeframe": Timeframe.D1,
        "start_ts": datetime.combine(day, time(), UTC),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": Decimal("0"),
    }
    return Bar(**(fields | changes))


def altered(original, **changes):
    result = replace(original)
    for key, value in changes.items():
        object.__setattr__(result, key, value)
    return result


@pytest.fixture(scope="module")
def panel():
    # Calendar only, synthetic values: reuse the pinned existing NYSE calendar.
    sessions = tuple(
        timestamp.date()
        for timestamp in mcal.get_calendar("NYSE").valid_days("2022-01-01", "2023-02-01")
    )
    dates = sessions[:CONTEXT_CLOSES]
    decision = datetime.combine(sessions[CONTEXT_CLOSES], time(14, 30), UTC)
    sources = {
        symbol: tuple(
            bar(symbol, day, Decimal(100 + (i * (column + 2)) % 23)) for i, day in enumerate(dates)
        )
        for column, symbol in enumerate(SYMBOLS)
    }
    return sources, {
        "scheduled_dates": dates,
        "decision_at": decision,
        "vintage_ref_by_symbol": dict.fromkeys(SYMBOLS, VINTAGE),
    }


def build(panel, sources=None, **changes):
    source, arguments = panel
    return build_joint_portfolio_covariance(
        source if sources is None else sources, **(arguments | changes)
    )


def test_exact_ordered_features_and_population_covariance(panel):
    result = build(panel)
    source, arguments = panel
    expected = np.array(
        [
            [
                float((right.close - left.close) / left.close)
                for left, right in zip(bars, bars[1:], strict=False)
            ]
            for bars in (source[symbol] for symbol in SYMBOLS)
        ]
    ).T
    actual = np.asarray(result.returns)
    covariance = np.asarray(result.covariance)
    assert result.symbols == ("SPY", "QQQ", "IWM")
    assert result.scheduled_dates == arguments["scheduled_dates"]
    assert result.source_vintage_ref == VINTAGE
    assert actual.shape == (252, 3) and covariance.shape == (3, 3)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_allclose(covariance, np.cov(expected, rowvar=False, ddof=0), atol=1e-16)
    np.testing.assert_array_equal(covariance, covariance.T)
    assert np.linalg.eigvalsh(covariance).min() >= -1e-15
    assert result.completed_through <= result.decision_at
    assert build(panel, dict(reversed(tuple(source.items())))) == result


def test_immutable_private_values_and_source_safe_projection(panel):
    result = build(panel)
    assert "Decimal" not in repr(result) and VINTAGE not in repr(result)
    assert "returns=" not in repr(result) and "covariance=" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.source_vintage_ref = "changed"
    with pytest.raises(TypeError):
        result.covariance[0][0] = 5
    facts = result.safe_facts()
    assert facts["status"] == "ready"
    assert facts["symbol_count"] == facts["covariance_rows"] == 3
    assert facts["close_count_per_symbol"] == 253 and facts["return_count"] == 252
    assert set(facts) == {
        "status",
        "symbol_count",
        "close_count_per_symbol",
        "return_count",
        "covariance_rows",
        "covariance_columns",
        "history_start",
        "history_last_session",
        "completed_through",
        "decision_at",
    }
    assert VINTAGE not in json.dumps(facts)
    facts["return_count"] = 0
    assert result.safe_facts()["return_count"] == CONTEXT_RETURNS


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("mutation", ["remove", "value", "incomplete", "identity", "support"])
def test_current_and_future_mutations_never_change_features_or_availability(
    panel, symbol, mutation
):
    source, arguments = panel
    baseline = build(panel)
    current = arguments["decision_at"].date()
    past_extra = bar(symbol, arguments["scheduled_dates"][0] - timedelta(days=4))
    outside = [bar(symbol, current), bar(symbol, current + timedelta(days=30))]
    if mutation == "remove":
        outside = []
    elif mutation == "value":
        outside = [
            altered(item, close=Decimal("NaN"), high=Decimal("Infinity")) for item in outside
        ]
    elif mutation == "incomplete":
        outside = [replace(item, complete=False) for item in outside]
    elif mutation == "identity":
        outside = [altered(item, symbol="OTHER", market="KR", timeframe="bad") for item in outside]
    else:
        outside += [outside[-1], SimpleNamespace(start_ts=outside[-1].start_ts)]
    changed = dict(source) | {symbol: (past_extra, *source[symbol], *outside)}
    assert build(panel, changed) == baseline
    assert build(panel, changed).safe_facts() == baseline.safe_facts()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reorder", "misaligned"])
def test_one_etf_past_support_failure_is_scoped(panel, symbol, mutation):
    sources, _ = panel
    changed = list(sources[symbol])
    reasons = {
        "missing": "required_session_missing",
        "duplicate": "required_session_duplicate",
        "reorder": "required_session_alignment_or_order",
        "misaligned": "required_session_alignment_or_order",
    }
    if mutation == "missing":
        del changed[120]
    elif mutation == "duplicate":
        changed.insert(120, changed[120])
    elif mutation == "reorder":
        changed[120], changed[121] = changed[121], changed[120]
    else:
        changed[120] = replace(changed[120], start_ts=changed[120].start_ts + timedelta(seconds=1))
    with pytest.raises(JointPortfolioInputUnavailable) as caught:
        build(panel, dict(sources) | {symbol: changed})
    assert caught.value.safe_facts() == {
        "status": "input_unavailable",
        "reason_code": reasons[mutation],
    }
    assert build(panel).safe_facts()["status"] == "ready"


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"symbol": "IWM"}, "required_bar_identity"),
        ({"market": "KR"}, "required_bar_identity"),
        ({"timeframe": Timeframe.M1}, "required_bar_identity"),
        ({"complete": False}, "required_bar_incomplete"),
        ({"complete": 1}, "required_bar_incomplete"),
        ({"close": Decimal("0")}, "required_bar_values_invalid"),
        ({"close": Decimal("-1")}, "required_bar_values_invalid"),
        ({"close": Decimal("NaN")}, "required_bar_values_invalid"),
        ({"close": Decimal("Infinity")}, "required_bar_values_invalid"),
        ({"close": 100.0}, "required_bar_values_invalid"),
        ({"high": Decimal("1")}, "required_bar_values_invalid"),
        ({"volume": Decimal("-1")}, "required_bar_values_invalid"),
    ],
)
def test_required_canonical_bar_is_reattested(panel, changes, reason):
    sources, _ = panel
    changed = list(sources["SPY"])
    changed[100] = altered(changed[100], **changes)
    with pytest.raises(JointPortfolioInputUnavailable, match=reason):
        build(panel, dict(sources) | {"SPY": changed})


def test_zero_returns_volume_and_singular_covariance_are_valid(panel):
    sources, arguments = panel
    constant = {
        symbol: tuple(bar(symbol, day) for day in arguments["scheduled_dates"])
        for symbol in SYMBOLS
    }
    result = build(panel, constant)
    assert result.returns == ((0.0, 0.0, 0.0),) * 252
    assert result.covariance == ((0.0, 0.0, 0.0),) * 3
    collinear = {
        symbol: tuple(replace(item, symbol=symbol) for item in sources["SPY"]) for symbol in SYMBOLS
    }
    covariance = np.asarray(build(panel, collinear).covariance)
    assert np.linalg.matrix_rank(covariance) == 1
    assert np.linalg.eigvalsh(covariance).min() > -1e-15


def test_features_do_not_depend_on_ambient_decimal_context_or_price_scale(panel):
    sources, _ = panel
    baseline = build(panel)
    with localcontext() as context:
        context.prec = 4
        assert build(panel) == baseline
    with localcontext() as context:
        context.prec = 50
        scaled = {
            symbol: tuple(
                bar(symbol, item.start_ts.date(), item.close * Decimal("1e400")) for item in bars
            )
            for symbol, bars in sources.items()
        }
    assert build(panel, scaled).returns == baseline.returns
    assert build(panel, scaled).covariance == baseline.covariance


@pytest.mark.parametrize("close", [Decimal("1e400"), Decimal("1e-400")])
def test_unrepresentable_returns_are_scoped_unavailable(panel, close):
    sources, arguments = panel
    changed = list(sources["SPY"])
    changed[120] = bar("SPY", arguments["scheduled_dates"][120], close)
    with pytest.raises(JointPortfolioInputUnavailable, match="returns_not_representable"):
        build(panel, dict(sources) | {"SPY": changed})


def test_finite_returns_with_overflowing_covariance_are_unavailable(panel):
    sources, arguments = panel
    changed = list(sources["SPY"])
    changed[-1] = bar("SPY", arguments["scheduled_dates"][-1], Decimal("1e200"))
    with pytest.raises(JointPortfolioInputUnavailable, match="covariance_not_representable"):
        build(panel, dict(sources) | {"SPY": changed})


@pytest.mark.parametrize("mutation", ["short", "long", "list", "duplicate", "order", "datetime"])
def test_exact_caller_date_contract_rejects_invalid_requests(panel, mutation):
    _, arguments = panel
    dates = arguments["scheduled_dates"]
    invalid = {
        "short": dates[:-1],
        "long": dates + (dates[-1] + timedelta(days=1),),
        "list": list(dates),
        "duplicate": dates[:-1] + (dates[-2],),
        "order": tuple(reversed(dates)),
        "datetime": (datetime.combine(dates[0], time(), UTC),) + dates[1:],
    }[mutation]
    with pytest.raises(ValueError, match="scheduled_dates"):
        build(panel, scheduled_dates=invalid)


def test_cutoff_assertions_and_utc_normalization(panel):
    _, arguments = panel
    last = arguments["scheduled_dates"][-1]
    with pytest.raises(ValueError, match="not_past"):
        build(panel, decision_at=datetime.combine(last, time(23, 59), UTC))
    with pytest.raises(ValueError, match="timezone-aware"):
        build(panel, decision_at=arguments["decision_at"].replace(tzinfo=None))
    with pytest.raises(ValueError, match="decision_at"):
        build(panel, decision_at="not-a-time")
    boundary = datetime.combine(last + timedelta(days=1), time(), UTC)
    assert build(panel, decision_at=boundary).completed_through == boundary
    local = arguments["decision_at"].astimezone(timezone(timedelta(hours=9)))
    assert build(panel, decision_at=local) == build(panel)


@pytest.mark.parametrize(
    "columns", [{}, {"SPY": ()}, {"SPY": (), "QQQ": (), "IWM": (), "OTHER": ()}]
)
def test_source_columns_are_exact(panel, columns):
    with pytest.raises(ValueError, match="source_columns"):
        build(panel, columns)


def test_vintage_binding_requires_the_same_three_explicit_refs(panel):
    with pytest.raises(ValueError, match="vintage_columns"):
        build(panel, vintage_ref_by_symbol={"SPY": VINTAGE})
    with pytest.raises(ValueError, match="vintage_ref"):
        build(panel, vintage_ref_by_symbol=dict.fromkeys(SYMBOLS, " "))
    with pytest.raises(JointPortfolioInputUnavailable, match="source_vintage_mismatch"):
        build(panel, vintage_ref_by_symbol=dict.fromkeys(SYMBOLS, VINTAGE) | {"IWM": "other"})


def test_input_uses_only_scheduled_dates_not_weekday_inference(panel):
    _, arguments = panel
    dates = arguments["scheduled_dates"]
    assert any((right - left).days > 3 for left, right in zip(dates, dates[1:], strict=False))
    assert date(2022, 7, 4) not in dates and date(2022, 11, 25) in dates
    assert build(panel).safe_facts()["close_count_per_symbol"] == 253


def test_helper_has_no_file_network_or_execution_dependency(panel, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure covariance input must not perform I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert build(panel).safe_facts()["status"] == "ready"


def test_output_remains_detached_from_mutable_caller_containers(panel):
    sources, arguments = panel
    caller_sources = {symbol: list(bars) for symbol, bars in sources.items()}
    caller_vintages = dict(arguments["vintage_ref_by_symbol"])
    result = build(panel, caller_sources, vintage_ref_by_symbol=caller_vintages)
    caller_sources["SPY"].clear()
    caller_vintages["IWM"] = "changed"
    assert result == build(panel)


def test_required_non_bar_cannot_impersonate_a_daily_close(panel):
    sources, _ = panel
    changed = list(sources["SPY"])
    changed[120] = SimpleNamespace(start_ts=changed[120].start_ts)
    with pytest.raises(JointPortfolioInputUnavailable, match="required_bar_identity"):
        build(panel, dict(sources) | {"SPY": changed})


@pytest.mark.parametrize("columns", [("SPY",), SYMBOLS])
def test_representable_tiny_returns_do_not_silently_become_zero_covariance(panel, columns):
    _, arguments = panel
    with localcontext() as context:
        context.prec = 240
        tiny = {
            symbol: tuple(
                bar(symbol, day, Decimal(1) + Decimal(i % 2) * Decimal("1e-200"))
                for i, day in enumerate(arguments["scheduled_dates"])
            )
            for symbol in columns
        }
    with pytest.raises(JointPortfolioInputUnavailable, match="covariance_not_representable"):
        build(panel, dict(panel[0]) | tiny)


def test_constant_nonzero_returns_have_exactly_zero_population_covariance(panel):
    _, arguments = panel
    with localcontext() as context:
        context.prec = 400
        sources = {
            symbol: tuple(
                bar(symbol, day, Decimal(100) * Decimal("1.1") ** index)
                for index, day in enumerate(arguments["scheduled_dates"])
            )
            for symbol in SYMBOLS
        }
    result = build(panel, sources)
    assert result.returns == ((0.1, 0.1, 0.1),) * 252
    assert result.covariance == ((0.0, 0.0, 0.0),) * 3
