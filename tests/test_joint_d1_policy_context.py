import builtins
import json
import math
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research.joint_d1_policy_context import (
    CHANNELS,
    CONTEXT_CLOSES,
    CONTEXT_OBSERVATIONS,
    FEATURE_NAMES,
    SYMBOLS,
    JointD1PolicyInputUnavailable,
    build_joint_d1_policy_context,
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
    # Caller-scheduled NYSE dates, including the July 4 holiday gap.
    dates = tuple(
        date(2022, 6, 1) + timedelta(days=offset)
        for offset in range(48)
        if (date(2022, 6, 1) + timedelta(days=offset)).weekday() < 5
        and date(2022, 6, 1) + timedelta(days=offset) not in {date(2022, 6, 20), date(2022, 7, 4)}
    )
    assert len(dates) == CONTEXT_CLOSES
    sources = {
        symbol: tuple(
            bar(
                symbol,
                day,
                Decimal(100 + (i * (column + 2)) % 23),
                open=Decimal(99 + (i * (column + 2)) % 23),
                high=Decimal(102 + (i * (column + 2)) % 23),
                low=Decimal(97 + (i * (column + 2)) % 23),
            )
            for i, day in enumerate(dates)
        )
        for column, symbol in enumerate(SYMBOLS)
    }
    return sources, {
        "scheduled_dates": dates,
        "decision_at": datetime(2022, 7, 19, 13, 30, tzinfo=UTC),
        "vintage_ref_by_symbol": dict.fromkeys(SYMBOLS, VINTAGE),
    }


def build(panel, sources=None, **changes):
    source, arguments = panel
    return build_joint_d1_policy_context(
        source if sources is None else sources, **(arguments | changes)
    )


def test_exact_asset_major_ordered_channels(panel):
    result = build(panel)
    sources, arguments = panel
    assert result.symbols == ("SPY", "QQQ", "IWM")
    assert result.channels == CHANNELS == tuple(
        f"{symbol}.{feature}" for symbol in SYMBOLS for feature in FEATURE_NAMES
    )
    assert len(result.features) == 9
    assert all(len(channel) == CONTEXT_OBSERVATIONS == 31 for channel in result.features)
    assert result.scheduled_dates == arguments["scheduled_dates"]
    assert result.observation_dates == arguments["scheduled_dates"][1:]
    assert result.source_vintage_ref == VINTAGE
    for column, symbol in enumerate(SYMBOLS):
        bars = sources[symbol]
        expected = (
            tuple(
                math.log(float(right.close)) - math.log(float(left.close))
                for left, right in zip(bars, bars[1:], strict=False)
            ),
            tuple(math.log(float(item.close)) - math.log(float(item.open)) for item in bars[1:]),
            tuple(math.log(float(item.high)) - math.log(float(item.low)) for item in bars[1:]),
        )
        for actual, channel in zip(
            result.features[column * 3 : column * 3 + 3], expected, strict=True
        ):
            assert actual == pytest.approx(channel, rel=1e-14, abs=1e-15)
            assert all(math.isfinite(value) for value in actual)
    assert build(panel, dict(reversed(tuple(sources.items())))) == result


def test_private_immutable_values_and_safe_counts(panel):
    result = build(panel)
    assert "features=" not in repr(result) and VINTAGE not in repr(result)
    assert "Decimal" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.source_vintage_ref = "changed"
    with pytest.raises(TypeError):
        result.features[0][0] = 5
    facts = result.safe_facts()
    assert facts["symbol_count"] == 3
    assert facts["close_count_per_symbol"] == 32
    assert facts["channel_count"] == 9 and facts["observation_count_per_channel"] == 31
    assert set(facts) == {
        "status",
        "symbol_count",
        "close_count_per_symbol",
        "channel_count",
        "observation_count_per_channel",
        "history_start",
        "history_last_session",
        "completed_through",
        "decision_at",
    }
    assert VINTAGE not in json.dumps(facts)
    facts["channel_count"] = 0
    assert result.safe_facts()["channel_count"] == 9


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("mutation", ["remove", "value", "incomplete", "identity", "support"])
def test_current_open_and_future_mutations_are_irrelevant(panel, symbol, mutation):
    sources, arguments = panel
    baseline = build(panel)
    current = arguments["decision_at"].date()
    outside = [bar(symbol, current), bar(symbol, current + timedelta(days=30))]
    if mutation == "remove":
        outside = []
    elif mutation == "value":
        outside = [
            altered(item, open=Decimal("NaN"), close=Decimal("Infinity")) for item in outside
        ]
    elif mutation == "incomplete":
        outside = [replace(item, complete=False) for item in outside]
    elif mutation == "identity":
        outside = [altered(item, symbol="OTHER", market="KR", timeframe="bad") for item in outside]
    else:
        outside += [outside[-1], SimpleNamespace(start_ts=outside[-1].start_ts)]
    past_extra = altered(
        bar(symbol, arguments["scheduled_dates"][0] - timedelta(days=4)), close=Decimal("NaN")
    )
    changed = dict(sources) | {symbol: (past_extra, *sources[symbol], *outside)}
    assert build(panel, changed) == baseline
    assert build(panel, changed).safe_facts() == baseline.safe_facts()


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reorder", "misaligned"])
def test_required_past_support_failure_is_scoped(panel, symbol, mutation):
    sources, _ = panel
    changed = list(sources[symbol])
    reasons = {
        "missing": "required_session_missing",
        "duplicate": "required_session_duplicate",
        "reorder": "required_session_alignment_or_order",
        "misaligned": "required_session_alignment_or_order",
    }
    if mutation == "missing":
        del changed[0]
    elif mutation == "duplicate":
        changed.insert(12, changed[12])
    elif mutation == "reorder":
        changed[12], changed[13] = changed[13], changed[12]
    else:
        changed[12] = replace(changed[12], start_ts=changed[12].start_ts + timedelta(seconds=1))
    with pytest.raises(JointD1PolicyInputUnavailable) as caught:
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
        ({"open": Decimal("0")}, "required_bar_values_invalid"),
        ({"close": Decimal("-1")}, "required_bar_values_invalid"),
        ({"close": Decimal("NaN")}, "required_bar_values_invalid"),
        ({"high": Decimal("Infinity")}, "required_bar_values_invalid"),
        ({"low": Decimal("1e400")}, "required_bar_values_invalid"),
        ({"close": 100.0}, "required_bar_values_invalid"),
        ({"high": Decimal("1")}, "required_bar_values_invalid"),
        ({"volume": Decimal("-1")}, "required_bar_values_invalid"),
    ],
)
def test_selected_bars_are_reattested_without_raw_error_values(panel, changes, reason):
    sources, _ = panel
    changed = list(sources["SPY"])
    changed[12] = altered(changed[12], **changes)
    with pytest.raises(JointD1PolicyInputUnavailable) as caught:
        build(panel, dict(sources) | {"SPY": changed})
    assert str(caught.value) == reason
    assert repr(caught.value) == f"JointD1PolicyInputUnavailable('{reason}')"


def test_required_non_bar_cannot_impersonate_a_session(panel):
    sources, _ = panel
    changed = list(sources["SPY"])
    changed[12] = SimpleNamespace(start_ts=changed[12].start_ts)
    with pytest.raises(JointD1PolicyInputUnavailable, match="required_bar_identity"):
        build(panel, dict(sources) | {"SPY": changed})


def test_prior_bar_only_contributes_its_close(panel):
    sources, _ = panel
    changed = list(sources["SPY"])
    changed[0] = replace(
        changed[0], open=Decimal("80"), high=Decimal("140"), low=Decimal("50")
    )
    assert build(panel, dict(sources) | {"SPY": changed}) == build(panel)
    changed[0] = replace(changed[0], close=Decimal("110"))
    baseline = build(panel)
    result = build(panel, dict(sources) | {"SPY": changed})
    assert result.features[0][0] != baseline.features[0][0]
    assert result.features[0][1:] == baseline.features[0][1:]
    assert result.features[1:] == baseline.features[1:]


def test_constant_prices_and_zero_volume_are_valid(panel):
    _, arguments = panel
    sources = {
        symbol: tuple(bar(symbol, day) for day in arguments["scheduled_dates"])
        for symbol in SYMBOLS
    }
    assert build(panel, sources).features == ((0.0,) * 31,) * 9


def test_fixed_arithmetic_is_ambient_context_and_price_scale_independent(panel):
    sources, _ = panel
    baseline = build(panel)
    with localcontext() as context:
        context.prec = 4
        assert build(panel) == baseline
    with localcontext() as context:
        context.prec = 50
        scaled = {
            symbol: tuple(
                replace(
                    item,
                    **{
                        key: getattr(item, key) * Decimal("1e400")
                        for key in ("open", "high", "low", "close")
                    },
                )
                for item in bars
            )
            for symbol, bars in sources.items()
        }
    assert build(panel, scaled).features == baseline.features


@pytest.mark.parametrize("magnitude", ["1e400", "1e-400"])
def test_extreme_price_ratios_have_finite_log_features(panel, magnitude):
    sources, arguments = panel
    changed = list(sources["SPY"])
    changed[12] = bar("SPY", arguments["scheduled_dates"][12], Decimal(magnitude))
    result = build(panel, dict(sources) | {"SPY": changed})
    assert all(math.isfinite(value) for channel in result.features for value in channel)


def test_range_never_forms_a_float_ratio_and_intraday_can_be_negative(panel):
    sources, arguments = panel
    changed = list(sources["SPY"])
    changed[12] = bar(
        "SPY",
        arguments["scheduled_dates"][12],
        Decimal("110"),
        open=Decimal("120"),
        high=Decimal("1e400"),
        low=Decimal("1e-400"),
    )
    result = build(panel, dict(sources) | {"SPY": changed})
    assert result.features[1][11] < 0
    assert math.isfinite(result.features[2][11]) and result.features[2][11] > 0


@pytest.mark.parametrize("move,available", [("1e-200", True), ("1e-400", False)])
def test_tiny_nonzero_log_moves_are_preserved_or_unavailable(panel, move, available):
    _, arguments = panel
    with localcontext() as context:
        context.prec = 500
        sources = {
            symbol: tuple(
                bar(symbol, day, Decimal(1) + Decimal(i % 2) * Decimal(move))
                for i, day in enumerate(arguments["scheduled_dates"])
            )
            for symbol in SYMBOLS
        }
    if available:
        result = build(panel, sources)
        assert result.features[0][0] == float(Decimal(move))
        assert all(value != 0 for value in result.features[0])
    else:
        with pytest.raises(JointD1PolicyInputUnavailable, match="features_not_representable"):
            build(panel, sources)


@pytest.mark.parametrize("mutation", ["short", "long", "list", "duplicate", "order", "datetime"])
def test_exact_date_contract(panel, mutation):
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


def test_cutoff_and_utc_normalization(panel):
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
def test_exact_source_columns(panel, columns):
    with pytest.raises(ValueError, match="source_columns"):
        build(panel, columns)


@pytest.mark.parametrize("columns", [None, SYMBOLS])
def test_sources_must_be_mapping(panel, columns):
    with pytest.raises(ValueError, match="source_columns"):
        build_joint_d1_policy_context(columns, **panel[1])


@pytest.mark.parametrize("source", [None, "raw", b"raw", iter(())])
def test_each_source_must_be_sequence(panel, source):
    with pytest.raises(ValueError, match="source_sequence"):
        build(panel, dict(panel[0]) | {"SPY": source})


@pytest.mark.parametrize("refs", [None, {}, {"SPY": VINTAGE}, dict.fromkeys(SYMBOLS, " ")])
def test_vintage_contract(panel, refs):
    with pytest.raises(ValueError, match="source_vintage"):
        build(panel, vintage_ref_by_symbol=refs)


def test_same_shared_vintage_is_required(panel):
    with pytest.raises(JointD1PolicyInputUnavailable, match="source_vintage_mismatch"):
        build(panel, vintage_ref_by_symbol=dict.fromkeys(SYMBOLS, VINTAGE) | {"IWM": "other"})


def test_no_calendar_inference_or_gap_imputation(panel):
    sources, arguments = panel
    assert date(2022, 7, 4) not in arguments["scheduled_dates"]
    assert build(panel).safe_facts()["close_count_per_symbol"] == 32
    changed = dict(sources) | {"QQQ": sources["QQQ"][:12] + sources["QQQ"][13:]}
    with pytest.raises(JointD1PolicyInputUnavailable, match="required_session_missing"):
        build(panel, changed)


def test_helper_has_no_file_or_network_side_effect(panel, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure policy context must not perform I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert build(panel).safe_facts()["status"] == "ready"


def test_result_is_detached_from_mutable_caller_containers(panel):
    sources, arguments = panel
    caller_sources = {symbol: list(bars) for symbol, bars in sources.items()}
    caller_refs = dict(arguments["vintage_ref_by_symbol"])
    result = build(panel, caller_sources, vintage_ref_by_symbol=caller_refs)
    caller_sources["SPY"].clear()
    caller_refs["IWM"] = "changed"
    assert result == build(panel)
