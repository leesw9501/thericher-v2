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
