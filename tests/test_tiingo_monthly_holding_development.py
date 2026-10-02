"""Synthetic monthly decisions, adjusted-mark ledger and immutable worker checks."""

import copy
import json
import runpy
import socket
import time
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from statistics import median
from types import SimpleNamespace

import pytest

from thericher_v2.data import tiingo_adjusted_etf_daily as data
from thericher_v2.data import tiingo_etf_daily as raw_data
from thericher_v2.research import tiingo_monthly_holding_development as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("real source/network/credentials forbidden")

    for obj, attr in (
        (s, "load_adjusted"),
        (data, "load_verified_adjusted_etf_snapshot"),
        (raw_data, "read_tiingo_api_token"),
        (socket, "create_connection"),
        (socket.socket, "connect"),
    ):
        monkeypatch.setattr(obj, attr, forbidden)
    with localcontext() as context:
        context.prec = 50
        yield


@pytest.fixture
def sample(monkeypatch):
    def weekdays(start, count):
        days = []
        while len(days) < count:
            if start.weekday() < 5:
                days.append(start.isoformat())
            start += timedelta(days=1)
        return days

    days = (
        weekdays(date(2000, 12, 1), 21)
        + weekdays(date(2001, 1, 1), 165)
        + weekdays(date(2013, 1, 1), 80)
        + weekdays(date(2020, 1, 1), 80)
    )
    rows = {}
    for symbol in s.SYMBOLS:
        previous, stream = Decimal(100), []
        for i, d in enumerate(days):
            opening = previous * (1 + Decimal((i % 5) - 2) / 10000)
            closing = opening * (1 + Decimal(((i % 11) - 5) * 13) * (1 + (i // 23) % 3) / 10000)
            stream.append(
                data.AdjustedEtfRow(
                    symbol,
                    date.fromisoformat(d),
                    opening,
                    max(opening, closing) * Decimal("1.01"),
                    min(opening, closing) * Decimal("0.99"),
                    closing,
                )
            )
            previous = closing
        rows[symbol] = tuple(stream)
    monkeypatch.setattr(s, "calendar_days", lambda: days)
    contract = s.proposed_contract()
    return SimpleNamespace(
        days=days, rows=rows, contract=contract, pin=s.digest(s.encode(contract))
    )


def index(p, rows=None):
    return {r.session_date.isoformat(): r for r in (p.rows if rows is None else rows)["SPY"]}


def evaluate(p, rows=None):
    return s.evaluate(
        p.rows if rows is None else rows, p.contract, p.pin, deadline=time.monotonic() + 30
    )


def calibrated(p, rows=None):
    return s.calibrate(index(p, rows), p.contract["plan"], deadline=time.monotonic() + 30)


def policy(p, rows=None):
    ref, _, _ = calibrated(p, rows)
    bounds = p.contract["plan"]["periods"][0]["bounds"]
    return s.targets(index(p, rows), p.days, bounds, ref)


def replay(p, actions, cost="5", rows=None):
    return s.replay(
        index(p, rows),
        p.days,
        p.contract["plan"]["periods"][0]["bounds"],
        actions,
        cost,
        deadline=time.monotonic() + 30,
    )


def test_full_matrix_endpoints_controls_fee_identity_and_boundaries(sample):
    result = evaluate(sample)
    assert result["status"] == "complete" and len(result["cells"]) == 72
    assert sample.contract["config"]["train"] == list(s.TRAIN)
    assert sample.contract["config"]["budget"] == dict(
        cpu_threads=1,
        memory_bytes=2 * 1024**3,
        wall_seconds=600,
        gpu=False,
        passes=1,
        retries=False,
    )
    assert sample.contract["source"]["raw_sha256"] == dict(data.RAW_SHA256)
    for cell in result["cells"]:
        fees, notional = Decimal(cell["fees_initial_nav"]), Decimal(cell["turnover_initial_nav"])
        assert abs(fees - Decimal(cell["cost_per_side_bps"]) * notional / 10000) < Decimal("2e-12")
        if cell["policy"] == "cash":
            assert cell["trades"] == 0 and Decimal(cell["final_nav"]) == 1
        if cell["policy"] == "always_long":
            assert cell["trades"] == 2
    assert not any(
        key in s.encode(result).decode() for key in ('"navs":', '"weights":', '"adj_close":')
    )


@pytest.mark.parametrize(
    "stock,weight", [("0", "1"), ("0.2", "0.6"), ("0.8", "0.2"), ("1", "0"), ("0.6", "0.6")]
)
def test_piecewise_postfee_target_and_cash_closure(stock, weight):
    e, w, c = Decimal(stock), Decimal(weight), Decimal("0.001")
    x, cash, fee, turnover = s.rebalance(e, Decimal(1), w, c)
    assert abs(x + cash + fee - 1) < Decimal("1e-40")
    assert fee == c * turnover and abs(x / (x + cash) - w) < Decimal("1e-40")
    assert cash >= 0 and x >= 0
    expected = w * (1 + c * e) / (1 + w * c) if w >= e else w * (1 - c * e) / (1 - w * c)
    assert abs(x - expected) < Decimal("1e-40")


@pytest.mark.parametrize(
    "center,stock,nav,expected",
    [
        (".5", "0", "1", ".4"),
        (".5", ".4", "1", ".4"),
        (".5", ".55", "1", ".55"),
        (".5", ".6", "1", ".6"),
        (".5", "1", "1", ".6"),
        ("0", ".05", "1", ".05"),
        ("0", ".5", "1", ".1"),
        ("1", "0", "1", ".9"),
        ("1", "1", "1", "1"),
        (".5", "1.1", "2", ".55"),
    ],
)
def test_fixed_band_clips_actual_exposure_and_edges(center, stock, nav, expected):
    assert s.fixed_band_target(*map(Decimal, (center, stock, nav))) == Decimal(expected)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("center", Decimal("-.01")),
        ("center", Decimal("1.01")),
        ("center", Decimal("NaN")),
        ("center", Decimal("sNaN")),
        ("center", Decimal("Infinity")),
        ("center", 0.5),
        ("stock", Decimal("-.01")),
        ("stock", Decimal("1.01")),
        ("stock", Decimal("NaN")),
        ("stock", 0),
        ("nav", Decimal(0)),
        ("nav", Decimal(-1)),
        ("nav", Decimal("NaN")),
        ("nav", Decimal("Infinity")),
        ("nav", True),
    ],
)
def test_fixed_band_rejects_invalid_inputs_before_division(field, bad):
    values = dict(center=Decimal(".5"), stock=Decimal(".5"), nav=Decimal(1))
    values[field] = bad
    with pytest.raises(ValueError, match="fixed_band_input"):
        s.fixed_band_target(**values)


def test_fixed_band_uses_local_decimal50_without_changing_caller_context():
    with localcontext() as context:
        context.prec = 8
        actual = s.fixed_band_target(Decimal(".5"), Decimal(4), Decimal(7))
        assert context.prec == 8
    assert actual == Decimal(4) / 7


@pytest.fixture
def band_path():
    days = (
        "2024-01-02",
        "2024-01-03",
        "2024-02-01",
        "2024-02-02",
        "2024-03-01",
        "2024-03-04",
        "2024-04-01",
        "2024-04-02",
    )
    marks = (
        ("1", "1.2"),
        ("1.3", "1.5"),
        ("2", "2.2"),
        ("2.4", "3"),
        ("4", "3.2"),
        ("3.4", "2"),
        ("1", ".9"),
        ("1.1", "1"),
    )
    rows = {}
    for day, (opening, closing) in zip(days, marks, strict=True):
        o, c = Decimal(opening), Decimal(closing)
        rows[day] = data.AdjustedEtfRow("SPY", date.fromisoformat(day), o, max(o, c), min(o, c), c)
    return days, rows, dict.fromkeys((0, 2, 4, 6), Decimal(".5"))


@pytest.mark.parametrize("cost", s.COSTS)
def test_fixed_band_gap_drift_independent_postfee_reconstruction(band_path, monkeypatch, cost):
    days, rows, actions = band_path
    targets, events = [], []
    original = s.rebalance

    def transform(center, stock, nav):
        target = s.fixed_band_target(center, stock, nav)
        targets.append((stock / nav, target))
        return target

    def capture(stock, nav, weight, fee):
        result = original(stock, nav, weight, fee)
        events.append((stock, nav, weight, result))
        return result

    monkeypatch.setattr(s, "rebalance", capture)
    actual = s.replay(
        rows,
        days,
        (0, len(days)),
        actions,
        cost,
        deadline=time.monotonic() + 30,
        target_transform=transform,
    )
    fee, cash, units = Decimal(cost) / 10000, Decimal(1), Decimal(0)
    fees, turnover, navs, expected_events = Decimal(0), Decimal(0), [], []
    for i, day in enumerate(days):
        row = rows[day]
        if i in actions:
            stock, nav = units * row.adj_open, cash + units * row.adj_open
            weight = Decimal(".4") if i in (0, 6) else Decimal(".6")
            if i == 2:
                delta = Decimal(0)
                weight = stock / nav
            else:
                denominator = 1 + fee * weight if i in (0, 6) else 1 - fee * weight
                delta = (weight * nav - stock) / denominator
            paid = fee * abs(delta)
            cash -= delta + paid
            units += delta / row.adj_open
            fees, turnover = fees + paid, turnover + abs(delta)
            expected_events.append((weight, paid, abs(delta)))
        nav = cash + units * row.adj_close
        if i == len(days) - 1:
            liquidated = units * row.adj_close
            paid = fee * liquidated
            cash, units = nav - paid, Decimal(0)
            fees, turnover = fees + paid, turnover + liquidated
            expected_events.append((Decimal(0), paid, liquidated))
            nav = cash
        navs.append(nav)
    exposures = (Decimal(0), Decimal(4) / 7, Decimal(8) / 11, Decimal(3) / 11)
    projected = (Decimal(".4"), Decimal(4) / 7, Decimal(".6"), Decimal(".4"))
    assert len(targets) == 4 and len(events) == 5 and actual["trades"] == 4
    for (exposure, target), prior, expected in zip(targets, exposures, projected, strict=True):
        assert abs(exposure - prior) < s.EPS and abs(target - expected) < s.EPS
    for (stock, nav, weight, (value, remaining, paid, traded)), expected in zip(
        events, expected_events, strict=True
    ):
        assert abs(weight - expected[0]) < s.EPS
        assert abs(paid - expected[1]) < s.EPS and abs(traded - expected[2]) < s.EPS
        assert traded == abs(value - stock) and paid == fee * traded
        assert abs(value + remaining + paid - nav) < s.EPS
        assert abs(value / (value + remaining) - weight) < s.EPS
    assert events[1][3][2:] == (Decimal(0), Decimal(0))
    assert events[-1][2] == 0 and events[-1][3][0] == 0
    assert all(abs(a - b) < s.EPS for a, b in zip(actual["navs"], navs, strict=True))
    assert abs(actual["final_nav"] - cash) < s.EPS
    assert abs(actual["fees_initial_nav"] - fees) < s.EPS
    assert abs(actual["turnover_initial_nav"] - turnover) < s.EPS


@pytest.mark.parametrize("cost", s.COSTS)
@pytest.mark.parametrize("center", (Decimal(0), Decimal(".5"), Decimal(1)))
def test_replay_default_none_and_identity_transform_parity(sample, cost, center):
    actions = dict.fromkeys(policy(sample), center)
    rows, days = index(sample), sample.days
    bounds = sample.contract["plan"]["periods"][0]["bounds"]
    kwargs = dict(deadline=time.monotonic() + 30)
    expected = s.replay(rows, days, bounds, actions, cost, **kwargs)
    assert s.replay(rows, days, bounds, actions, cost, target_transform=None, **kwargs) == expected
    assert (
        s.replay(
            rows,
            days,
            bounds,
            actions,
            cost,
            target_transform=lambda center, stock, nav: center,
            **kwargs,
        )
        == expected
    )


@pytest.mark.parametrize("mutation", ("own_close", "future_payoffs"))
def test_fixed_band_future_payoffs_cannot_change_current_target(band_path, mutation):
    days, rows, actions = band_path
    changed, trace = dict(rows), []
    for i, day in enumerate(days):
        if i == 4 or mutation == "future_payoffs" and i > 4:
            row = rows[day]
            opening = row.adj_open * 3 if i > 4 else row.adj_open
            closing = row.adj_close * 3
            changed[day] = replace(
                row,
                adj_open=opening,
                adj_close=closing,
                adj_high=max(opening, closing),
                adj_low=min(opening, closing),
            )

    def transform(center, stock, nav):
        target = s.fixed_band_target(center, stock, nav)
        trace.append((center, stock, nav, target))
        return target

    kwargs = dict(deadline=time.monotonic() + 30, target_transform=transform)
    original = s.replay(rows, days, (0, len(days)), actions, "10", **kwargs)
    before = trace[:]
    trace.clear()
    mutated = s.replay(changed, days, (0, len(days)), actions, "10", **kwargs)
    assert trace[:3] == before[:3]
    assert mutated["navs"][:4] == original["navs"][:4]
    assert mutated["navs"] != original["navs"]


@pytest.mark.parametrize(
    "malformed",
    [
        True,
        False,
        0.5,
        1.0,
        0,
        1,
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-.01"),
        Decimal("1.01"),
        object(),
    ],
)
def test_replay_rejects_malformed_transform_result_before_ledger(band_path, monkeypatch, malformed):
    days, rows, actions = band_path

    def forbidden(*args, **kwargs):
        pytest.fail("malformed callback result reached ledger")

    monkeypatch.setattr(s, "rebalance", forbidden)
    with pytest.raises(ValueError, match="target_transform_result"):
        s.replay(
            rows,
            days,
            (0, len(days)),
            actions,
            "5",
            deadline=time.monotonic() + 30,
            target_transform=lambda center, stock, nav: malformed,
        )


def test_replay_rejects_noncallable_transform(band_path):
    days, rows, actions = band_path
    with pytest.raises(ValueError, match="target_transform"):
        s.replay(
            rows,
            days,
            (0, len(days)),
            actions,
            "5",
            deadline=time.monotonic() + 30,
            target_transform=False,
        )


def test_passive_only_initial_final_costs_and_first_last_daily_returns(sample):
    actions = dict.fromkeys(policy(sample), Decimal(1))
    r = replay(sample, actions, "10")
    bounds = sample.contract["plan"]["periods"][0]["bounds"]
    first, last = (sample.rows["SPY"][i] for i in (bounds[0], bounds[1] - 1))
    growth, fee = last.adj_close / first.adj_open, Decimal("0.001")
    assert r["trades"] == 2
    assert abs(r["final_nav"] - growth * (1 - fee) / (1 + fee)) < Decimal("1e-40")
    assert abs(r["fees_initial_nav"] - fee * (1 + growth) / (1 + fee)) < Decimal("1e-40")
    assert r["returns"][0] == r["navs"][0] - 1
    assert r["returns"][-1] == r["navs"][-1] / r["navs"][-2] - 1
    assert r["daily_return_std"] == s.variance(r["returns"]).sqrt()


def test_months_closed_no_daily_rebalance_and_fee_only_on_changes(sample):
    actions = dict.fromkeys(policy(sample), Decimal("0.6"))
    assert all(
        i == min(j for j, d in enumerate(sample.days) if d[:7] == sample.days[i][:7])
        for i in actions
    )
    a = replay(sample, actions, "0")
    b = replay(sample, actions, "5")
    assert a["trades"] <= len(actions) + 1 and b["trades"] == a["trades"]
    assert b["final_nav"] < a["final_nav"]
    assert b["trades"] < len(b["navs"])
    p = dict.fromkeys(actions, Decimal(0))
    r = replay(sample, p)
    assert r["navs"] == [Decimal(1)] * len(r["navs"]) and r["trades"] == 0


@pytest.mark.parametrize("mutation", ["own_close", "future_close", "own_open"])
def test_future_mutation_cannot_change_prior_decisions_or_nav(sample, mutation):
    actions = policy(sample)
    j = list(actions)[1]
    rows = dict(sample.rows)
    changed = []
    for i, r in enumerate(rows["SPY"]):
        own = i == j
        alter_close = own and mutation == "own_close" or i >= j and mutation == "future_close"
        alter_open = own and mutation == "own_open"
        o = r.adj_open * Decimal("1.05") if alter_open else r.adj_open
        c = r.adj_close * Decimal("1.05") if alter_close else r.adj_close
        changed.append(
            replace(
                r,
                adj_open=o,
                adj_close=c,
                adj_high=max(o, c) * Decimal("1.01"),
                adj_low=min(o, c) * Decimal("0.99"),
            )
        )
    rows["SPY"] = tuple(changed)
    assert calibrated(sample)[1:] == calibrated(sample, rows)[1:]
    assert all(policy(sample, rows)[i] == w for i, w in actions.items() if i <= j)
    prior = j - sample.contract["plan"]["periods"][0]["bounds"][0]
    assert (
        replay(sample, actions)["navs"][:prior]
        == replay(sample, policy(sample, rows), rows=rows)["navs"][:prior]
    )


def test_calibration_only_reads_train_and_ratio_uses_same_warm_subset(sample):
    class TrainOnly(dict):
        def get(self, d):
            assert sample.days[0] <= d <= s.TRAIN[1]
            return super().get(d)

    rows, plan = TrainOnly(index(sample)), sample.contract["plan"]
    ref, constant, facts = s.calibrate(rows, plan, deadline=time.monotonic() + 30)
    vs = {i: s.prior_variance(rows, sample.days, i) for i in range(*plan["train"])}
    assert ref == median(v for v in vs.values() if v is not None and v > 0)
    actions = s.targets(rows, sample.days, plan["train"], ref)
    managed = s.replay(
        rows, sample.days, plan["train"], actions, "0", deadline=time.monotonic() + 30
    )
    passive = s.replay(
        rows,
        sample.days,
        plan["train"],
        dict.fromkeys(actions, Decimal(1)),
        "0",
        deadline=time.monotonic() + 30,
    )
    warm = [i - plan["train"][0] for i, v in vs.items() if v is not None]
    assert facts["warm_sessions"] == len(warm)
    expected = min(
        Decimal(1),
        (
            s.variance([managed["returns"][i] for i in warm])
            / s.variance([passive["returns"][i] for i in warm])
        ).sqrt(),
    )
    assert constant == expected


@pytest.mark.parametrize("scale", ["0.00001", "100000"])
def test_global_adjusted_price_scale_invariance(sample, scale):
    scaled = {
        symbol: tuple(
            replace(
                r,
                **{
                    key: getattr(r, key) * Decimal(scale)
                    for key in ("adj_open", "adj_high", "adj_low", "adj_close")
                },
            )
            for r in stream
        )
        for symbol, stream in sample.rows.items()
    }
    assert evaluate(sample, scaled) == evaluate(sample)


@pytest.mark.parametrize("bad", ["missing", "invalid"])
def test_normal_calendar_gap_never_bridges_or_relabels_other_group(sample, bad):
    j = sample.contract["plan"]["periods"][0]["bounds"][0] + 10
    rows = dict(sample.rows)
    rows["SPY"] = tuple(
        SimpleNamespace(**(asdict(r) | {"adj_close": Decimal("NaN")}))
        if bad == "invalid" and i == j
        else r
        for i, r in enumerate(rows["SPY"])
        if bad != "missing" or i != j
    )
    r = evaluate(sample, rows)
    assert r["status"] == "input_unavailable"
    assert r["groups"][0]["missing" if bad == "missing" else "invalid"] == 1
    assert all(c["final_nav"] is None for c in r["cells"][:12])
    assert all(c["final_nav"] is not None for c in r["cells"][12:])
    with pytest.raises(ValueError, match="calendar_gap_or_invalid_bar"):
        replay(sample, policy(sample), rows=rows)


def test_zero_missing_variance_target_is_flat_and_exact_23_close_requirement(sample):
    assert s.prior_variance(index(sample), sample.days, 22) is None
    assert s.prior_variance(index(sample), sample.days, 23) is not None
    rows = {
        d: replace(
            r,
            adj_open=Decimal(100),
            adj_high=Decimal(100),
            adj_low=Decimal(100),
            adj_close=Decimal(100),
        )
        for d, r in index(sample).items()
    }
    assert all(
        w == 0
        for w in s.targets(rows, sample.days, sample.contract["plan"]["train"], Decimal(1)).values()
    )
    assert all(
        w == 0
        for w in s.targets({}, sample.days, sample.contract["plan"]["train"], Decimal(1)).values()
    )


@pytest.mark.parametrize("bad", ["train_gap", "zero_passive_std"])
def test_train_input_unavailability_suppresses_only_affected_symbol(sample, bad):
    rows = dict(sample.rows)
    bounds = sample.contract["plan"]["train"]
    if bad == "train_gap":
        rows["SPY"] = tuple(r for i, r in enumerate(rows["SPY"]) if i != bounds[0] + 10)
    else:
        rows["SPY"] = tuple(
            replace(
                r,
                adj_open=Decimal(100),
                adj_high=Decimal(100),
                adj_low=Decimal(100),
                adj_close=Decimal(100),
            )
            if bounds[0] <= i < bounds[1]
            else r
            for i, r in enumerate(rows["SPY"])
        )
    ref, constant, facts = calibrated(sample, rows)
    assert constant is None and facts["calibration_sha256"] is None
    if bad == "zero_passive_std":
        assert ref > 0 and facts["positive_variances"] > 0
    result = evaluate(sample, rows)
    assert [g["status"] for g in result["groups"]] == ["input_unavailable"] * 2 + ["evaluated"] * 4
    assert all(c["final_nav"] is None for c in result["cells"][:24])
    assert all(c["final_nav"] is not None for c in result["cells"][24:])


def test_train_calibration_once_per_symbol_and_cost_invariant_actions(sample, monkeypatch):
    calls = []
    original = s.calibrate

    def capture(rows, plan, *, deadline):
        assert plan is sample.contract["plan"]
        calls.append(next(iter(rows.values())).symbol)
        return original(rows, plan, deadline=deadline)

    monkeypatch.setattr(s, "calibrate", capture)
    result = evaluate(sample)
    assert calls == list(s.SYMBOLS)
    for symbol in s.SYMBOLS:
        for period, _, _ in s.PERIODS:
            for policy in s.POLICIES:
                selected = [
                    c
                    for c in result["cells"]
                    if (c["symbol"], c["period"], c["policy"]) == (symbol, period, policy)
                ]
                assert len({c["action_sha256"] for c in selected}) == 1


@pytest.mark.parametrize("bad", ["duplicate", "reverse", "symbol", "date"])
def test_invalid_source_identity_order(sample, bad):
    rows = dict(sample.rows)
    stream = rows["SPY"]
    attrs = {
        k: getattr(stream[0], k)
        for k in ("symbol", "session_date", "adj_open", "adj_high", "adj_low", "adj_close")
    }
    attrs["symbol" if bad == "symbol" else "session_date"] = "WRONG"
    rows["SPY"] = (
        (stream[0],) + stream
        if bad == "duplicate"
        else stream[::-1]
        if bad == "reverse"
        else (SimpleNamespace(**attrs),) + stream[1:]
    )
    with pytest.raises(ValueError):
        evaluate(sample, rows)


@pytest.mark.parametrize(
    "bad",
    ["extra", "partial", "cash", "fees", "trades", "action", "metric", "count", "source", "paired"],
)
def test_result_rejects_tampering(sample, bad):
    r = evaluate(sample)
    if bad == "extra":
        r["raw_prices"] = []
    if bad == "partial":
        r["cells"].pop()
    if bad == "cash":
        r["cells"][3]["final_nav"] = "2.000000000000"
    if bad == "fees":
        r["cells"][0]["fees_initial_nav"] = "99.000000000000"
    if bad == "trades":
        r["cells"][2]["trades"] = 3
    if bad == "action":
        r["cells"][4]["action_sha256"] = "sha256:" + "0" * 64
    if bad == "metric":
        r["cells"][0]["daily_return_std"] = "NaN"
    if bad == "count":
        r["groups"][0]["missing"] = False
    if bad == "source":
        r["source_sha256"] = "sha256:" + "0" * 64
    if bad == "paired":
        r["cells"][0]["difference_vs_long_nav"] = "99.000000000000"
    with pytest.raises((ValueError, TypeError)):
        s.validate_result(r, sample.contract, sample.pin)


@pytest.mark.parametrize("field", ["config", "source", "plan", "code_sha256"])
def test_contract_binding_and_budget(sample, field):
    changed = copy.deepcopy(sample.contract)
    changed[field] = {}
    with pytest.raises(ValueError):
        s.evaluate(sample.rows, changed, sample.pin, deadline=time.monotonic() + 30)
    with pytest.raises(ValueError, match="hard_timeout"):
        s.evaluate(sample.rows, sample.contract, sample.pin, deadline=0)


@pytest.mark.parametrize("mode", ["success", "timeout", "invalid", "interrupt", "source_drift"])
def test_synthetic_metadata_freeze_single_attempt_supervisor_failure(
    sample, tmp_path, monkeypatch, mode
):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    for path, name in (
        (artifact / s.base.RECEIPT, "RECEIPT_HASH"),
        (market / s.base.SNAPSHOT / "manifest.json", "MANIFEST_HASH"),
    ):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"synthetic":true}\n')
        monkeypatch.setattr(s.base, name, s.digest(path.read_bytes()))
    pin = s.freeze(artifact, market)
    output, contract = s.verify(artifact, market, pin)
    assert {p.name for p in output.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(artifact, market)

    def load(path, root):
        assert path == market / s.base.SNAPSHOT and root == market
        assert json.loads((output / "started.json").read_bytes()) == {"contract_sha256": pin}
        return sample.rows

    monkeypatch.setattr(s, "load_adjusted", load)
    runner = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    ns = runner["main"].__globals__
    ns["study"], ns["worker"] = s, s.worker_entry

    def supervise(target, args, *, seconds):
        assert target is s.worker_entry and 0 < seconds <= 600
        if mode == "interrupt":
            raise KeyboardInterrupt
        if mode != "timeout":
            target(*args)
            if mode == "invalid":
                payload = json.loads(args[-2].read_bytes())
                payload["weights"] = "PRIVATE"
                args[-2].write_bytes(s.encode(payload))
            if mode == "source_drift":
                (artifact / s.base.RECEIPT).write_bytes(b"changed")
        return dict(timed_out=mode == "timeout", exit_code=0)

    ns["supervise"] = supervise
    r = runner["dispatch"](artifact, market, pin)
    assert r["status"] == ("complete" if mode == "success" else "failed")
    original = (output / "summary.json").read_bytes()
    s.validate_result(json.loads(original), contract, pin)
    assert b"PRIVATE" not in original
    with pytest.raises(ValueError):
        runner["dispatch"](artifact, market, pin)
    assert (output / "summary.json").read_bytes() == original
    for path in tmp_path.rglob("*"):
        assert not path.is_symlink()
        if path.is_file():
            assert path.stat().st_nlink == 1


def test_cli_delegates_existing_supervisor_without_running_campaign(monkeypatch):
    namespace = runpy.run_path(str(s.REPO / "scripts/run_tiingo_monthly_holding_development.py"))
    delegated = {"__builtins__": __builtins__}
    exec("def main(argv):\n    return study.NAME, worker, argv", delegated)

    def parent(path):
        assert path == str(s.REPO / "scripts/run_tiingo_month_start_development.py")
        return {"main": delegated["main"]}

    monkeypatch.setattr(runpy, "run_path", parent)
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "9")
    assert namespace["main"](["--help"]) == (s.NAME, s.worker_entry, ["--help"])
    assert all(
        namespace["main"].__globals__["os"].environ[name] == "1"
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "BLIS_NUM_THREADS",
        )
    )


def test_importable_worker_spawn_is_bounded_and_missing_precommit_fails(tmp_path):
    ns = runpy.run_path(str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    r = ns["supervise"](
        s.worker_entry,
        (
            tmp_path / "empty-artifact",
            tmp_path / "empty-market",
            "invalid",
            tmp_path / "unused.json",
            time.monotonic() + 10,
        ),
        seconds=10,
        name="monthly-holding-synthetic",
    )
    assert r["exit_code"] == 1 and r["timed_out"] is False
    assert not (tmp_path / "unused.json").exists()
