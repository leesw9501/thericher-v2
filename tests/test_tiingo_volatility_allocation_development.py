"""Synthetic-only allocation checks; no market snapshot, provider or credentials."""

import copy
import json
import runpy
import socket
import time
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from types import SimpleNamespace

import pytest

from thericher_v2.data import tiingo_etf_daily as daily
from thericher_v2.research import tiingo_volatility_allocation_development as s


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("real source/network/credentials forbidden")

    for obj, attr in (
        (s.base, "load_verified_tiingo_etf_d1_snapshot"),
        (daily, "read_tiingo_api_token"),
        (socket, "create_connection"),
        (socket.socket, "connect"),
    ):
        monkeypatch.setattr(obj, attr, forbidden)


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
        + weekdays(date(2001, 1, 1), 110)
        + weekdays(date(2013, 1, 1), 55)
        + weekdays(date(2020, 1, 1), 55)
    )
    monkeypatch.setattr(s.geometry, "calendar_days", lambda: days)
    rows = {
        symbol: tuple(
            daily.TiingoEtfDailyRow(
                symbol,
                date.fromisoformat(d),
                Decimal(100),
                Decimal(110),
                Decimal(90),
                Decimal(100) + Decimal(((i % 9) - 4) * 13 + 3) * (1 + (i // 22) % 3) / 100,
                Decimal(1000),
                Decimal(0),
                Decimal(1),
            )
            for i, d in enumerate(days)
        )
        for symbol in s.SYMBOLS
    }
    contract = s.proposed_contract()
    return SimpleNamespace(
        days=days, rows=rows, contract=contract, pin=s.digest(s.encode(contract))
    )


def evaluate(p, rows=None):
    return s.evaluate(
        p.rows if rows is None else rows, p.contract, p.pin, deadline=time.monotonic() + 30
    )


def index(p, rows=None):
    return {r.session_date.isoformat(): r for r in (p.rows if rows is None else rows)["SPY"]}


def weights(p, rows=None):
    indexed = index(p, rows)
    vref, constant, facts = s.calibrate(indexed, p.contract["plan"])
    bounds = p.contract["plan"]["periods"][0]["bounds"]
    variances = s.prior_variances(indexed, p.days, bounds)
    return s.exposures(variances, vref), constant, facts


def test_matrix_controls_costs_and_frozen_dates(sample):
    r = evaluate(sample)
    assert r["status"] == "complete" and len(r["cells"]) == 72
    assert sample.contract["config"]["train"] == ["2001-01-01", "2012-12-31"]
    assert sample.contract["config"]["budget"] == dict(
        cpu_threads=1, wall_seconds=600, memory_bytes=1024**3, gpu=False, passes=1, retries=False
    )
    assert sample.contract["config"]["scope"]["paper_input"] is False
    for c in r["cells"]:
        assert c["observed"] == 55
        if c["policy"] == "cash":
            assert all(Decimal(c[k]) == 0 for k in s.METRICS[:5])
        if c["policy"] == "always_long":
            assert Decimal(c["mean_exposure"]) == Decimal(c["rms_exposure"]) == 1
        peers = [x for x in r["cells"] if all(x[k] == c[k] for k in ("symbol", "period", "policy"))]
        assert len({x["action_sha256"] for x in peers}) == 1
        assert abs(
            Decimal(c["mean_gross_bps"])
            - c["cost_bps"] * Decimal(c["mean_exposure"])
            - Decimal(c["paired_mean_net_bps"])
        ) < Decimal("3e-11")
    assert not any(k in s.encode(r).decode() for k in ('"weights":', '"open":', '"close":'))


@pytest.mark.parametrize("mutation", ["own_close", "future", "missing"])
def test_future_or_target_cannot_change_own_or_earlier_exposure(sample, mutation):
    a = weights(sample)
    first = sample.contract["plan"]["periods"][0]["bounds"][0]
    j = first + 10
    rows = dict(sample.rows)
    rows["SPY"] = tuple(
        replace(r, close=Decimal(105))
        if i >= j and mutation == "future" or i == j and mutation == "own_close"
        else r
        for i, r in enumerate(rows["SPY"])
        if mutation != "missing" or i != j
    )
    b = weights(sample, rows)
    assert a[1:] == b[1:] and a[0][:11] == b[0][:11]
    if mutation == "missing":
        assert b[0][11:33] == [Decimal(0)] * 22 and a[0][33:] == b[0][33:]
        r = evaluate(sample, rows)
        assert r["groups"][0]["past_excluded"] == 22 and r["groups"][0]["censored"] == 1
        assert all(c["observed"] == 32 for c in r["cells"][:12])


@pytest.mark.parametrize("missing_train", [False, True])
def test_train_calibration_reads_no_eval_and_matches_formula(sample, missing_train):
    class TrainOnly(dict):
        def get(self, day):
            assert sample.contract["plan"]["days"][0] <= day <= s.TRAIN[1]
            return super().get(day)

    rows = TrainOnly(index(sample))
    if missing_train:
        rows.pop(sample.days[60])
    ref, constant, _ = s.calibrate(rows, sample.contract["plan"])
    bounds = sample.contract["plan"]["train"]
    variance = s.prior_variances(rows, sample.days, bounds)
    assert ref == median(v for v in variance if v is not None and v > 0)
    w = s.exposures(variance, ref)
    y = [s.geometry.outcome(rows.get(sample.days[i])) for i in range(*bounds)]
    eligible = [i for i, v in enumerate(variance) if v is not None and y[i] is not None]
    expected = min(
        Decimal(1),
        (
            s.moments([w[i] * y[i] for i in eligible])[1] / s.moments([y[i] for i in eligible])[1]
        ).sqrt(),
    )
    assert constant == expected
    assert s.exposures([None, Decimal(0), ref / 2, ref * 2], ref) == [0, 0, 1, Decimal("0.5")]
    assert s.moments([Decimal(-1), Decimal(1)] * 11) == (0, 1)


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity"])
def test_invalid_target_is_censored_not_shifted(sample, bad):
    j = sample.contract["plan"]["periods"][0]["bounds"][0] + 10
    rows = dict(
        sample.rows,
        SPY=tuple(
            replace(r, open=Decimal(bad)) if i == j else r for i, r in enumerate(sample.rows["SPY"])
        ),
    )
    assert weights(sample, rows)[0][:11] == weights(sample)[0][:11]
    g = evaluate(sample, rows)["groups"][0]
    assert g["censored"] == 1 and g["past_excluded"] == 22


@pytest.mark.parametrize("bad", ["duplicate", "reverse", "symbol", "date", "absent_symbol"])
def test_invalid_identity_fails(sample, bad):
    rows = dict(sample.rows)
    stream = rows["SPY"]
    rows["SPY"] = (
        (stream[0],) + stream
        if bad == "duplicate"
        else stream[::-1]
        if bad == "reverse"
        else (
            replace(
                stream[0],
                **({"symbol": "WRONG"} if bad == "symbol" else {"session_date": "2000-12-01"}),
            ),
        )
        + stream[1:]
        if bad != "absent_symbol"
        else stream
    )
    if bad == "absent_symbol":
        rows.pop("IWM")
    with pytest.raises(ValueError):
        evaluate(sample, rows)


@pytest.mark.parametrize(
    "bad", ["extra", "bool", "partial", "net", "hash", "metric", "source", "calibration"]
)
def test_closed_result_rejects_tampering(sample, bad):
    r = evaluate(sample)
    if bad == "extra":
        r["raw_rows"] = []
    if bad == "bool":
        r["groups"][0]["observed"] = True
    if bad == "partial":
        r["cells"].pop()
    if bad == "net":
        r["cells"][0]["paired_mean_net_bps"] = "999.000000000000"
    if bad == "hash":
        r["cells"][0]["action_sha256"] = "sha256:" + "0" * 64
    if bad == "metric":
        r["cells"][0]["net_std_bps"] = "NaN"
    if bad == "source":
        r["source_sha256"] = "sha256:" + "0" * 64
    if bad == "calibration":
        r["groups"][0]["train"] = copy.deepcopy(r["groups"][0]["train"])
        r["groups"][0]["train"]["calibration_sha256"] = "sha256:" + "0" * 64
    with pytest.raises((ValueError, TypeError)):
        s.validate_result(r, sample.contract, sample.pin)


def test_zero_train_variance_is_symbol_scoped_unavailable(sample):
    rows = dict(sample.rows, SPY=tuple(replace(r, close=r.open) for r in sample.rows["SPY"]))
    r = evaluate(sample, rows)
    assert r["status"] == "input_unavailable"
    assert all(c["paired_mean_net_bps"] is None for c in r["cells"][:24])
    assert all(c["paired_mean_net_bps"] is not None for c in r["cells"][24:])


@pytest.mark.parametrize("field", ["source", "config", "plan"])
def test_contract_binding_and_deadline(sample, field):
    changed = copy.deepcopy(sample.contract)
    changed[field] = {}
    with pytest.raises((ValueError, KeyError)):
        s.evaluate(sample.rows, changed, sample.pin, deadline=time.monotonic() + 30)
    with pytest.raises(ValueError, match="hard_timeout"):
        s.evaluate(sample.rows, sample.contract, sample.pin, deadline=0)


@pytest.mark.parametrize(
    "mode", ["success", "timeout", "invalid", "interrupt", "wrong_source", "drift"]
)
def test_metadata_freeze_one_pass_and_supervised_failures(sample, tmp_path, monkeypatch, mode):
    artifact, market = tmp_path / "artifacts", tmp_path / "market"
    for path, name in (
        (artifact / s.base.RECEIPT, "RECEIPT_HASH"),
        (market / s.base.SNAPSHOT / "manifest.json", "MANIFEST_HASH"),
    ):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"synthetic":true}\n')
        monkeypatch.setattr(s.base, name, s.digest(path.read_bytes()))
    pin = s.freeze(artifact, market)
    output, bound = s.verify(artifact, market, pin)
    assert {p.name for p in output.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(artifact, market)

    def load(path, **kwargs):
        assert json.loads((output / "started.json").read_bytes()) == {"contract_sha256": pin}
        return SimpleNamespace(
            rows_by_symbol=sample.rows,
            snapshot=SimpleNamespace(
                dataset_id=s.base.DATASET_ID,
                dataset_hash="wrong" if mode == "wrong_source" else s.base.DATASET_HASH,
                manifest_hash=s.base.MANIFEST_HASH,
            ),
        )

    monkeypatch.setattr(s.base, "load_verified_tiingo_etf_d1_snapshot", load)
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
                r = json.loads(args[-2].read_bytes())
                r["raw_rows"] = "PRIVATE"
                args[-2].write_bytes(s.encode(r))
            if mode == "drift":
                (artifact / s.base.RECEIPT).write_bytes(b"changed after worker")
        return dict(timed_out=mode == "timeout", exit_code=0)

    ns["supervise"] = supervise
    result = runner["dispatch"](artifact, market, pin)
    assert result["status"] == ("complete" if mode == "success" else "failed")
    raw = (output / "summary.json").read_bytes()
    assert b"PRIVATE" not in raw
    s.validate_result(json.loads(raw), bound, pin)
    with pytest.raises(ValueError, match="attempt_already_exists|receipt_hash"):
        runner["dispatch"](artifact, market, pin)
    assert (output / "summary.json").read_bytes() == raw


def test_complete_zero_variance_history_is_eligible_and_flat(sample):
    first = sample.contract["plan"]["periods"][0]["bounds"][0]
    rows = dict(
        sample.rows,
        SPY=tuple(
            replace(r, close=r.open) if first - 22 <= i < first else r
            for i, r in enumerate(sample.rows["SPY"])
        ),
    )
    assert weights(sample, rows)[0][0] == 0
    result = evaluate(sample, rows)
    assert result["groups"][0]["zero_variance"] >= 1
    assert all(c["observed"] == 55 for c in result["cells"][:12])


def test_constant_observed_train_targets_cannot_calibrate_from_eval(sample):
    end = sample.contract["plan"]["train"][1]
    rows = dict(
        sample.rows,
        SPY=tuple(
            replace(r, close=r.open) if 22 <= i < end else r
            for i, r in enumerate(sample.rows["SPY"])
        ),
    )
    _, constant, facts = s.calibrate(index(sample, rows), sample.contract["plan"])
    assert facts["positive_variance"] > 0 and constant is None
    assert evaluate(sample, rows)["groups"][0]["status"] == "input_unavailable"


def test_same_train_control_cannot_change_between_eval_periods(sample):
    result = evaluate(sample)
    assert Decimal(result["cells"][13]["mean_exposure"]) != Decimal("0.5")
    for offset in (12, 16, 20):
        batch = result["cells"][offset : offset + 4]
        risk, long = batch[1:3]
        risk["mean_exposure"] = risk["rms_exposure"] = "0.500000000000"
        for key in s.METRICS[:3]:
            risk[key] = s.base._number(Decimal(long[key]) / 2)
        for cell in batch:
            for field, control in zip(s.METRICS[5:], batch[1:3], strict=True):
                cell[field] = s.base._number(
                    Decimal(cell[s.METRICS[1]]) - Decimal(control[s.METRICS[1]])
                )
    with pytest.raises(ValueError, match="EVAL_recalibration"):
        s.validate_result(result, sample.contract, sample.pin)


def test_calendar_plan_train_targets_fixed_with_only_prior_warmup():
    plan = s.build_plan(s.geometry.calendar_days())
    assert plan["days"][0] == "2000-12-01" and plan["days"][-1] == "2026-07-31"
    assert plan["days"][plan["train"][0]] == "2001-01-02"
    assert plan["days"][plan["train"][1] - 1] == "2012-12-31"
    assert s.prior_variances({}, plan["days"], [0, 22]) == [None] * 22


def test_cli_delegates_existing_runner_without_market_run(monkeypatch):
    ns = runpy.run_path(str(s.REPO / "scripts/run_tiingo_volatility_allocation_development.py"))

    def delegated(argv):
        return argv

    def load(path):
        assert path == str(s.REPO / "scripts/run_tiingo_month_start_development.py")
        return {"main": delegated}

    monkeypatch.setattr(ns["runpy"], "run_path", load)
    assert ns["main"](["synthetic"]) == ["synthetic"]
    assert delegated.__globals__["study"] is s and delegated.__globals__["worker"] is s.worker_entry


def test_importable_worker_exits_under_existing_spawn_supervisor(tmp_path):
    ns = runpy.run_path(str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    report = ns["supervise"](
        s.worker_entry,
        (
            tmp_path / "empty-artifacts",
            tmp_path / "empty-market",
            "invalid",
            tmp_path / "unused.json",
            time.monotonic() + 10,
        ),
        seconds=10,
        name="allocation-synthetic",
    )
    assert report["exit_code"] == 1 and report["timed_out"] is False
    assert not (tmp_path / "unused.json").exists()
