"""Synthetic exact-month momentum, causal calibration and immutable one-pass checks."""

import calendar
import copy
import json
import runpy
import socket
import time
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from thericher_v2.data import tiingo_adjusted_etf_daily as data
from thericher_v2.research import tiingo_monthly_momentum_development as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("real source/network/credentials forbidden")

    for obj, attr in (
        (s, "load_adjusted"),
        (socket, "create_connection"),
        (socket.socket, "connect"),
    ):
        monkeypatch.setattr(obj, attr, forbidden)
    with localcontext() as context:
        context.prec = 50
        yield


@pytest.fixture
def sample(monkeypatch):
    days = []
    for serial in range(2000 * 12 + 11, 2026 * 12 + 7):
        year, month = serial // 12, serial % 12 + 1
        first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        while first.weekday() >= 5:
            first += timedelta(days=1)
        while last.weekday() >= 5:
            last -= timedelta(days=1)
        days.extend([first.isoformat(), last.isoformat()])
    rows = {}
    for symbol in s.SYMBOLS:
        previous, stream = Decimal(100), []
        for i, d in enumerate(days):
            opening = previous * (1 + Decimal(i % 5 - 2) / 10000)
            closing = Decimal(100 + (i // 2) % 48 - 24) + Decimal(i % 2) / 10
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


def replay(p, actions, cost="5", rows=None):
    return s.replay(
        index(p, rows),
        p.days,
        p.contract["plan"]["periods"][0]["bounds"],
        actions,
        cost,
        deadline=time.monotonic() + 30,
    )


def change_close(row, close):
    return replace(
        row,
        adj_close=close,
        adj_high=max(row.adj_open, close) * Decimal("1.01"),
        adj_low=min(row.adj_open, close) * Decimal("0.99"),
    )


def test_exact_twelve_calendar_month_lag_and_unique_frozen_support(sample):
    plan = sample.contract["plan"]
    segment = plan["periods"][0]
    first = segment["decisions"][0]
    assert sample.days[first["index"]] == "2013-01-01"
    assert first["month_ends"][0] == "2011-12-30"
    assert first["month_ends"][-1] == "2012-12-31"
    assert len(first["month_ends"]) == 13 and "2012-02-29" in first["month_ends"]
    assert plan["train"]["bounds"][0] == sample.days.index("2002-01-01")
    assert plan["train"]["decisions"][0]["month_ends"][0] == "2000-12-29"
    union = set(sample.days[slice(*segment["bounds"])]) | {
        d for action in segment["decisions"] for d in action["month_ends"]
    }
    assert segment["support"] == sorted(union)
    assert len(union) < len(segment["decisions"]) * 13 + len(sample.days[slice(*segment["bounds"])])
    assert sample.contract["source"]["raw_sha256"] == dict(data.RAW_SHA256)
    assert set(s.monthly.CODE) <= set(s.CODE)


@pytest.mark.parametrize("sign", [-1, 0, 1])
def test_binary_signal_strict_equality_flat_and_no_eleven_month_substitute(sample, sign):
    segment = sample.contract["plan"]["periods"][0]
    first = segment["decisions"][0]
    rows = index(sample)
    older, endpoint = first["month_ends"][0], first["month_ends"][-1]
    rows[older] = change_close(rows[older], Decimal(100))
    rows[endpoint] = change_close(rows[endpoint], Decimal(100 + sign))
    assert s.targets(rows, segment)[first["index"]] == int(sign > 0)
    intermediate = first["month_ends"][1]
    rows[intermediate] = change_close(rows[intermediate], Decimal("1000000"))
    assert s.targets(rows, segment)[first["index"]] == int(sign > 0)


def test_full_matrix_cash_long_endpoints_costs_and_source_safe_output(sample):
    r = evaluate(sample)
    assert r["status"] == "complete" and len(r["cells"]) == 72
    assert r["criterion"] == "descriptive_only_no_selection"
    assert sample.contract["config"]["train"] == list(s.TRAIN)
    assert sample.contract["config"]["budget"] == dict(
        cpu_threads=1,
        memory_bytes=2 * 1024**3,
        wall_seconds=600,
        gpu=False,
        passes=1,
        retries=False,
        fitting=False,
    )
    for c in r["cells"]:
        fee, turnover = Decimal(c["fees_initial_nav"]), Decimal(c["turnover_initial_nav"])
        assert abs(fee - Decimal(c["cost_per_side_bps"]) * turnover / 10000) < Decimal("2e-12")
        if c["policy"] == "always_long":
            assert c["trades"] == 2
        if c["policy"] == "cash":
            assert c["trades"] == 0 and Decimal(c["final_nav"]) == 1
    assert not any(k in s.encode(r).decode() for k in ('"weights":', '"navs":', '"adj_close":'))


def test_train_only_same_all_train_return_dates_and_one_calibration(sample, monkeypatch):
    class TrainOnly(dict):
        def get(self, d):
            assert "2000-12-01" <= d <= s.TRAIN[1]
            assert d in sample.contract["plan"]["train"]["support"]
            return super().get(d)

    rows, plan = TrainOnly(index(sample)), sample.contract["plan"]
    constant, facts = s.calibrate(rows, plan, deadline=time.monotonic() + 30)
    segment = plan["train"]
    actions = s.targets(rows, segment)
    managed = s.replay(
        rows, plan["days"], segment["bounds"], actions, "0", deadline=time.monotonic() + 30
    )
    passive = s.replay(
        rows,
        plan["days"],
        segment["bounds"],
        dict.fromkeys(actions, Decimal(1)),
        "0",
        deadline=time.monotonic() + 30,
    )
    assert len(managed["returns"]) == len(passive["returns"]) == facts["sessions"]
    assert facts["sessions"] == sum(s.TRAIN[0] <= d <= s.TRAIN[1] for d in sample.days)
    assert constant == min(
        Decimal(1), (s.variance(managed["returns"]) / s.variance(passive["returns"])).sqrt()
    )
    calls, original = [], s.calibrate

    def capture(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(s, "calibrate", capture)
    evaluate(sample)
    assert len(calls) == 3


@pytest.mark.parametrize("mutation", ["own_close", "own_open", "future_close"])
def test_own_and_future_rows_cannot_change_earlier_decisions_or_nav(sample, mutation):
    segment = sample.contract["plan"]["periods"][0]
    original = s.targets(index(sample), segment)
    j = [i for i, weight in original.items() if weight == 1][2]
    rows = dict(sample.rows)
    changed = []
    for i, row in enumerate(rows["SPY"]):
        if i == j and mutation == "own_open":
            opening = row.adj_open * Decimal("1.1")
            row = replace(
                row,
                adj_open=opening,
                adj_high=max(opening, row.adj_close) * 2,
                adj_low=min(opening, row.adj_close) / 2,
            )
        if i == j and mutation == "own_close" or i >= j and mutation == "future_close":
            row = change_close(row, row.adj_close * Decimal("1.5"))
        changed.append(row)
    rows["SPY"] = tuple(changed)
    modified = s.targets(index(sample, rows), segment)
    assert all(modified[i] == w for i, w in original.items() if i <= j)
    assert calibrated(sample) == calibrated(sample, rows)
    earlier = j - segment["bounds"][0]
    assert any(nav != 1 for nav in replay(sample, original)["navs"][:earlier])
    assert (
        replay(sample, original)["navs"][:earlier]
        == replay(sample, modified, rows=rows)["navs"][:earlier]
    )


@pytest.mark.parametrize("kind", ["daily", "endpoint", "intermediate", "train"])
@pytest.mark.parametrize("bad", ["missing", "invalid"])
def test_exact_required_date_gap_unavailable_no_shift_or_duplicate_counts(sample, kind, bad):
    segment = sample.contract["plan"]["periods"][0]
    decision = segment["decisions"][0]
    d = (
        sample.days[segment["bounds"][0] + 2]
        if kind == "daily"
        else decision["month_ends"][0]
        if kind == "endpoint"
        else decision["month_ends"][6]
        if kind == "intermediate"
        else "2005-03-01"
    )
    rows = dict(sample.rows)
    rows["SPY"] = tuple(
        SimpleNamespace(**(asdict(r) | {"adj_close": Decimal("NaN")}))
        if bad == "invalid" and r.session_date.isoformat() == d
        else r
        for r in rows["SPY"]
        if bad != "missing" or r.session_date.isoformat() != d
    )
    r = evaluate(sample, rows)
    assert r["status"] == "input_unavailable"
    target = r["groups"][0]["train"] if kind == "train" else r["groups"][0]
    assert target[bad if bad == "missing" else "invalid"] == 1
    unavailable = 24 if d in sample.contract["plan"]["train"]["support"] else 12
    assert all(c["final_nav"] is None for c in r["cells"][:unavailable])
    assert all(c["final_nav"] is not None for c in r["cells"][unavailable:])
    if kind in {"endpoint", "intermediate"}:
        assert s.targets(index(sample, rows), segment)[decision["index"]] is None
    assert segment == sample.contract["plan"]["periods"][0]


def test_later_fold_gap_does_not_suppress_earlier_fold_or_other_symbols(sample):
    segment = sample.contract["plan"]["periods"][1]
    d = next(
        action["month_ends"][0]
        for action in segment["decisions"]
        if sample.days[action["index"]][:7] == "2025-01"
    )
    rows = dict(sample.rows)
    rows["SPY"] = tuple(r for r in rows["SPY"] if r.session_date.isoformat() != d)
    assert calibrated(sample) == calibrated(sample, rows)
    r = evaluate(sample, rows)
    assert [g["status"] for g in r["groups"]] == ["evaluated", "input_unavailable"] + [
        "evaluated"
    ] * 4
    assert r["groups"][1]["missing"] == 1
    assert all(c["final_nav"] is not None for c in r["cells"][:12] + r["cells"][24:])
    assert all(c["final_nav"] is None for c in r["cells"][12:24])


def test_missing_calendar_month_cannot_use_nearest_calendar_date(sample):
    days = [d for d in sample.days if d[:7] != "2011-12"]
    with pytest.raises(ValueError, match="historical_month_calendar_missing"):
        s.build_plan(days)


def test_zero_train_momentum_risk_legitimately_calibrates_cash(sample):
    rows = dict(sample.rows)
    rows["SPY"] = tuple(change_close(r, Decimal(1000 - i) / 10) for i, r in enumerate(rows["SPY"]))
    constant, facts = calibrated(sample, rows)
    assert constant == 0 and facts["calibration_sha256"] is not None
    r = evaluate(sample, rows)
    assert r["status"] == "complete"
    for c in r["cells"][:24]:
        if c["policy"] in {"abs_momentum", "train_risk_matched", "cash"}:
            assert Decimal(c["final_nav"]) == 1 and c["trades"] == 0


@pytest.mark.parametrize("scale", ["0.00001", "100000"])
def test_global_price_scale_invariance_and_cost_invariant_targets(sample, scale):
    rows = {
        symbol: tuple(
            replace(
                r,
                **{
                    k: getattr(r, k) * Decimal(scale)
                    for k in ("adj_open", "adj_high", "adj_low", "adj_close")
                },
            )
            for r in stream
        )
        for symbol, stream in sample.rows.items()
    }
    r = evaluate(sample)
    assert evaluate(sample, rows) == r
    for symbol in s.SYMBOLS:
        for period, _, _ in s.PERIODS:
            for policy in s.POLICIES:
                assert (
                    len(
                        {
                            c["action_sha256"]
                            for c in r["cells"]
                            if (c["symbol"], c["period"], c["policy"]) == (symbol, period, policy)
                        }
                    )
                    == 1
                )


def test_inherited_ledger_initial_final_fees_close_returns_and_no_daily_rebalance(sample):
    segment = sample.contract["plan"]["periods"][0]
    actions = s.targets(index(sample), segment)
    passive = dict.fromkeys(actions, Decimal(1))
    r = replay(sample, passive, "10")
    first, last = (sample.rows["SPY"][i] for i in (segment["bounds"][0], segment["bounds"][1] - 1))
    growth, fee = last.adj_close / first.adj_open, Decimal("0.001")
    assert r["trades"] == 2
    assert abs(r["final_nav"] - growth * (1 - fee) / (1 + fee)) < Decimal("1e-40")
    assert abs(r["fees_initial_nav"] - fee * (1 + growth) / (1 + fee)) < Decimal("1e-40")
    assert r["returns"][0] == r["navs"][0] - 1
    assert r["returns"][-1] == r["navs"][-1] / r["navs"][-2] - 1
    managed = replay(sample, actions)
    assert managed["trades"] <= len(actions) + 1
    assert managed["trades"] < len(managed["navs"])
    assert s.replay is s.monthly.replay and s.variance is s.monthly.variance


@pytest.mark.parametrize("bad", ["duplicate", "reverse", "symbol", "date"])
def test_invalid_binding_duplicate_order_identity(sample, bad):
    rows = dict(sample.rows)
    stream = rows["SPY"]
    attrs = asdict(stream[0]) | {"symbol" if bad == "symbol" else "session_date": "WRONG"}
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
    [
        "extra",
        "partial",
        "cash",
        "fees",
        "trades",
        "action",
        "metric",
        "count",
        "source",
        "paired",
        "cohort",
        "train",
    ],
)
def test_result_closed_fields_and_accounting_tamper_rejected(sample, bad):
    r = evaluate(sample)
    if bad == "extra":
        r["weights"] = []
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
    if bad == "cohort":
        r["groups"][0]["cohort_sha256"] = "sha256:" + "0" * 64
    if bad == "train":
        r["groups"][0]["train"]["support_dates"] += 1
    with pytest.raises((ValueError, TypeError)):
        s.validate_result(r, sample.contract, sample.pin)


@pytest.mark.parametrize("field", ["config", "source", "plan", "code_sha256"])
def test_contract_binding_and_deadline(sample, field):
    changed = copy.deepcopy(sample.contract)
    changed[field] = {}
    with pytest.raises(ValueError):
        s.evaluate(sample.rows, changed, sample.pin, deadline=time.monotonic() + 30)
    with pytest.raises(ValueError, match="hard_timeout"):
        s.evaluate(sample.rows, sample.contract, sample.pin, deadline=0)


@pytest.mark.parametrize("mode", ["success", "timeout", "invalid", "interrupt", "source_drift"])
def test_synthetic_metadata_freeze_one_attempt_worker_failures_no_links(
    sample, tmp_path, monkeypatch, mode
):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    pins = {}
    for path in (artifact / s.base.RECEIPT, market / s.base.SNAPSHOT / "manifest.json"):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"synthetic":true}\n')
        pins[path] = s.digest(path.read_bytes())

    def metadata(a, m):
        assert (a, m) == (artifact, market)
        for path, pin in pins.items():
            s.require(s.digest(path.read_bytes()) == pin, "synthetic_metadata_changed")

    monkeypatch.setattr(s, "verify_metadata", metadata)
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
                (market / s.base.SNAPSHOT / "manifest.json").write_bytes(b"changed")
        return dict(timed_out=mode == "timeout", exit_code=None if mode == "timeout" else 0)

    ns["supervise"] = supervise
    result = runner["dispatch"](artifact, market, pin)
    assert result["status"] == ("complete" if mode == "success" else "failed")
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


def test_importable_worker_spawn_fails_bounded_without_precommit(tmp_path):
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
        name="momentum-synthetic",
    )
    assert r["exit_code"] == 1 and r["timed_out"] is False
    assert not (tmp_path / "unused.json").exists()


def test_cli_uses_fresh_runner_globals_and_never_mutates_frozen_modules(monkeypatch):
    original = (s.monthly.NAME, s.monthly.TRAIN, s.monthly.POLICIES, s.base.NAME)
    namespace = runpy.run_path(str(s.REPO / "scripts/run_tiingo_monthly_momentum_development.py"))
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
    assert original == (s.monthly.NAME, s.monthly.TRAIN, s.monthly.POLICIES, s.base.NAME)
