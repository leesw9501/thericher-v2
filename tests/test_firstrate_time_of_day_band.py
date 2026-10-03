"""Synthetic-only causal band decisions, common controls and supervisor custody."""

import copy
import json
import multiprocessing
import runpy
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import EmergencyStore
from thericher_v2.research import firstrate_time_of_day_band as s

HASH = "sha256:" + "a" * 64
OPEN = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)


def day(opening=OPEN, *, count=78, signal=None, symbol="SPY", exit_price="100"):
    bars = []
    for i in range(count):
        price = Decimal(exit_price) if i == count - 1 else Decimal(100)
        close = Decimal(102) if i == signal else price
        bars.append(Bar(symbol=symbol, market="US", timeframe=Timeframe.M5,
                        start_ts=opening + i * s.STEP, open=price, close=close,
                        high=max(price, close) + 1, low=min(price, close) - 1,
                        volume=Decimal(100), complete=True))
    return tuple(bars)


def context(*, count=78, signal=5, history_count=15):
    schedule, bars = [], []
    for i in range(history_count + 1):
        opening = OPEN + timedelta(days=i)
        n = count if i == history_count else 78
        schedule.append((opening, opening + n * s.STEP))
        bars.extend(day(opening, count=n, signal=signal if i == history_count else None,
                        exit_price="102" if i == history_count else "100"))
    return tuple(schedule), {b.start_ts: b for b in bars}


def decide(schedule, index):
    return s.decide(index, "SPY", schedule, len(schedule) - 1, time.monotonic() + 60)


@pytest.mark.parametrize("count", (42, 78))
@pytest.mark.parametrize("signal", (5, 11, 35))
@pytest.mark.parametrize("cost", s.COSTS)
def test_semi_hourly_next_open_exit_open_actual_fees(count, signal, cost, tmp_path):
    schedule, index = context(count=count, signal=signal)
    d = decide(schedule, index)
    assert d.status == "selected" and d.at == d.opening + (signal + 1) * s.STEP
    path = s.orb.complete_path(index, "SPY", d.opening, d.closing)
    out = s.h30.Outcome(path[signal + 1:])
    obs = s.h30.Observation(at=d.at, signal=d.signal, features=())
    assert out.bars[0].start_ts == d.at
    assert out.bars[-1].start_ts == d.closing - s.STEP
    assert s.sessions.payoff(obs, out, cost, EmergencyStore(tmp_path / "emergency.json")) == (
        Decimal(2), Decimal(100 * cost / 10000).quantize(Decimal(".0001")) +
        Decimal(102 * cost / 10000).quantize(Decimal(".0001")))


def test_strict_close_first_signal_not_touch_or_non_cut_and_no_reentry():
    schedule, index = context(signal=4)
    opening = schedule[-1][0]
    for offset, price in ((5, 100), (11, 102), (17, 103)):
        at = opening + offset * s.STEP
        index[at] = replace(index[at], close=Decimal(price), high=Decimal(110))
    d = decide(schedule, index)
    assert d.signal == index[opening + 11 * s.STEP]
    assert d.at == opening + 12 * s.STEP


@pytest.mark.parametrize("count,last", ((42, 35), (78, 71)))
def test_last_fixed_cut_is_strictly_before_exit(count, last):
    schedule, index = context(count=count, signal=last)
    assert decide(schedule, index).at == schedule[-1][0] + (last + 1) * s.STEP
    schedule, index = context(count=count, signal=count - 2)
    assert decide(schedule, index).status == "no_breakout"


@pytest.mark.parametrize("kind", ("prices", "complete", "missing"))
@pytest.mark.parametrize("historical", (False, True))
def test_future_prices_and_finality_never_change_decision(kind, historical):
    schedule, index = context()
    before = decide(schedule, index)
    opening = schedule[-2 if historical else -1][0]
    for i in range(6, 78):
        at = opening + i * s.STEP
        if kind == "missing":
            del index[at]
        elif kind == "complete":
            index[at] = replace(index[at], complete=False)
        else:
            index[at] = replace(index[at], open=Decimal(200), high=Decimal(210),
                                low=Decimal(190), close=Decimal(205), volume=Decimal(99999))
    assert decide(schedule, index) == before


def test_only_current_and_history_completed_prefixes_are_looked_up():
    schedule, index = context()
    allowed = {o + i * s.STEP for o, _ in schedule[-15:] for i in range(6)}

    class Prefix(dict):
        def get(self, key):
            assert key in allowed
            return super().get(key)

    assert decide(schedule, Prefix(index)).status == "selected"


@pytest.mark.parametrize("historical", (False, True))
@pytest.mark.parametrize("kind", ("missing", "incomplete", "unaligned", "identity"))
def test_first_prefix_gap_is_explicit_unavailable_never_skips_calendar_day(historical, kind):
    schedule, index = context()
    opening = schedule[8 if historical else -1][0]
    at = opening + 3 * s.STEP
    if kind == "missing":
        del index[at]
    else:
        kw = {"complete": False} if kind == "incomplete" else (
            {"start_ts": at + timedelta(minutes=1)} if kind == "unaligned" else {"symbol": "QQQ"})
        index[at] = replace(index[at], **kw)
    d = decide(schedule, index)
    assert d.status == ("history_unavailable" if historical else "current_unavailable")
    assert d.cutoff == schedule[-1][0] + 6 * s.STEP
    assert d.signal is None


def test_exactly_fourteen_scheduled_sessions_no_substitution_or_extra_older_day():
    schedule, index = context()
    # The fifteenth earlier available day is deliberately huge and must be unread.
    index[schedule[0][0]] = replace(index[schedule[0][0]], open=Decimal(1000), high=Decimal(1001))
    assert decide(schedule, index).status == "selected"
    missing = schedule[8][0]
    index = {t: b for t, b in index.items() if not missing <= t < missing + 78 * s.STEP}
    assert decide(schedule, index).status == "history_unavailable"
    schedule, index = context(history_count=13)
    assert decide(schedule, index).status == "history_unavailable"


def test_prefix_scan_stops_first_later_gap_before_subsequent_signal():
    schedule, index = context(signal=17)
    opening = schedule[-1][0]
    del index[opening + 8 * s.STEP]
    d = decide(schedule, index)
    assert d.status == "current_unavailable" and d.cutoff == opening + 12 * s.STEP


def test_real_calendar_dst_and_early_close_same_elapsed_not_wall_clock():
    dates = (datetime(2025, 2, 14, tzinfo=UTC), datetime(2025, 3, 10, tzinfo=UTC),
             datetime(2025, 11, 28, tzinfo=UTC))
    calendar = s.sessions.regular_sessions([replace(day()[0], start_ts=d) for d in dates])
    by_date = {o.date(): (o, c) for o, c in calendar}
    assert by_date[datetime(2025, 3, 7).date()][0].hour == 14
    assert by_date[dates[1].date()][0].hour == 13
    for date in dates[1:]:
        pos = next(i for i, (o, _) in enumerate(calendar) if o.date() == date.date())
        index = {}
        for i, (o, c) in enumerate(calendar[pos - 14:pos + 1]):
            index.update({b.start_ts: b for b in day(o, count=(c - o) // s.STEP,
                                                    signal=5 if i == 14 else None)})
        d = s.decide(index, "SPY", calendar, pos, time.monotonic() + 60)
        assert d.at == calendar[pos][0] + 6 * s.STEP
    o, c = by_date[dates[-1].date()]
    assert (c - o) // s.STEP == 42
    assert s.orb.folds(calendar) == (calendar[len(calendar) // 2:3 * len(calendar) // 4],
                                    calendar[3 * len(calendar) // 4:])


def test_short_historical_session_cannot_be_filled_from_neighbor_or_tail():
    schedule, index = context(signal=47)
    schedule = list(schedule)
    o, _ = schedule[8]
    schedule[8] = (o, o + 42 * s.STEP)
    d = decide(tuple(schedule), index)
    assert d.status == "history_unavailable" and d.cutoff == d.opening + 42 * s.STEP + 6 * s.STEP


@pytest.fixture(scope="module")
def source():
    schedule, bars = [], []
    for i in range(80):
        o = OPEN + timedelta(days=i)
        n = 42 if i % 10 == 0 else 78
        schedule.append((o, o + n * s.STEP))
        bars.extend(day(o, count=n, signal=5 if i % 2 == 0 else None,
                        exit_price="102" if i % 2 == 0 else "99"))
    return tuple(schedule), tuple(bars)


def run(source, replay=fast_payoff):
    schedule, bars = source
    return s.compare(((symbol, tuple(replace(b, symbol=symbol) for b in bars))
                      for symbol in s.SYMBOLS), None, time.monotonic() + 60, HASH,
                     schedule=schedule, replay=replay)


@pytest.fixture(scope="module")
def result(source):
    return run(source)


def test_all_four_fold_decisions_frozen_before_any_outcome_mask(source, monkeypatch):
    calls = []
    original = s.decide

    def decision(*args):
        calls.append((args[1], args[3]))
        return original(*args)

    def score(*args):
        assert calls == [(symbol, i) for symbol in s.SYMBOLS for i in range(40, 80)]
        raise RuntimeError("bounded synthetic stop")

    monkeypatch.setattr(s, "decide", decision)
    monkeypatch.setattr(s, "compare_fold", score)
    with pytest.raises(RuntimeError, match="bounded synthetic stop"):
        run(source)


def test_control_pool_mean_includes_nonsignal_days_and_matches_duration_numeric_fees(result):
    assert result["status"] == "complete" and len(result["cells"]) == 12
    assert result["conclusion"] == "recipe_not_killed"
    for f in result["folds"]:
        assert f["counts"]["observed"] == 20 and f["counts"]["selected_observed"] == 10
        assert f["control_pool_sizes"] == [
            dict(session_bars=42, entry_offset_bars=6, sessions=2),
            dict(session_bars=78, entry_offset_bars=6, sessions=18)]
    for c in result["cells"]:
        expected_gross = Decimal(4) + Decimal(8) * Decimal(6) / Decimal(18)
        assert Decimal(c["band"]["gross_dollars"]) == 20
        assert Decimal(c["band"]["fees_dollars"]) == Decimal(".202") * c["cost_bps_per_side"]
        assert abs(Decimal(c["matched_long"]["gross_dollars"]) - expected_gross) < Decimal("1e-20")
        cost = Decimal(c["cost_bps_per_side"])
        expected_fees = 2 * Decimal(".0202") * cost + 8 * (
            8 * Decimal(".0202") + 10 * Decimal(".0199")) * cost / 18
        assert abs(Decimal(c["matched_long"]["fees_dollars"]) - expected_fees) < Decimal("1e-20")
        assert all(Decimal(v) == 0 for v in c["cash"].values())
    for i in range(0, 12, 3):
        assert len({c["decision_sha256"] for c in result["cells"][i:i + 3]}) == 1


@pytest.mark.parametrize("kind", ("missing", "incomplete"))
def test_common_postdecision_mask_changes_neither_actions_nor_costs(source, result, kind):
    schedule, bars = source
    at = schedule[42][1] - s.STEP
    changed = tuple(b for b in bars if b.start_ts != at) if kind == "missing" else tuple(
        replace(b, complete=False) if b.start_ts == at else b for b in bars)
    after = run((schedule, changed))
    for before, new in zip(result["folds"], after["folds"], strict=True):
        assert before["decision_sha256"] == new["decision_sha256"]
        if new["fold"] == 1:
            assert new["counts"]["selected"] == 10
            assert new["counts"]["selected_observed"] == 9
            assert new["counts"]["selected_censored"] == 1
            assert new["counts"]["censored"] == 1
            assert before["outcome_mask_sha256"] != new["outcome_mask_sha256"]


@pytest.mark.parametrize("kind", ("complete", "trades"))
def test_low_support_is_input_unavailable_not_global_hypothesis_rejection(source, kind):
    schedule, bars = source
    if kind == "complete":
        missing = {schedule[i][1] - s.STEP for i in range(40, 50)}
        bars = tuple(b for b in bars if b.start_ts not in missing)
    else:
        bars = tuple(replace(b, close=b.open) for b in bars)
    result = run((schedule, bars))
    assert result["status"] == "input_unavailable" and result["cells"] == []
    assert result["conclusion"] == "insufficient_support" and len(result["folds"]) == 4


@pytest.mark.parametrize("group", range(4))
@pytest.mark.parametrize("metric", ("net", "increment"))
@pytest.mark.parametrize("value", ("0", "-1"))
def test_primary_kill_each_symbol_fold_no_cost_rescue(result, group, metric, value):
    cells = copy.deepcopy(result["cells"])
    c = cells[group * 3 + 1]
    if metric == "net":
        c["band"]["net_bps_sum"] = value
    else:
        c["paired_net_bps_delta"] = value
    assert s.conclusion(cells) == "recipe_killed"


@pytest.mark.parametrize("defect", ("duplicate", "reversed", "identity", "deadline", "symbols"))
def test_source_identity_order_and_deadline_fail(source, defect):
    schedule, bars = source
    if defect == "duplicate":
        bars = (*bars[:1], *bars)
    elif defect == "reversed":
        bars = bars[::-1]
    elif defect == "identity":
        bars = (replace(bars[0], timeframe=Timeframe.M1), *bars[1:])
    with pytest.raises(ValueError):
        s.compare((("SPY", bars),), None, 0 if defect == "deadline" else time.monotonic() + 60,
                  HASH, schedule=schedule, replay=fast_payoff)


def test_nonfinite_prefix_price_is_not_silently_an_abstention():
    schedule, index = context()
    at = schedule[-1][0]
    index[at] = replace(index[at])
    object.__setattr__(index[at], "open", Decimal("NaN"))
    with pytest.raises(ValueError, match="finite"):
        decide(schedule, index)


@pytest.mark.parametrize("defect", ("private", "pin", "flag", "count", "partial", "metric",
                                  "delta", "cash", "conclusion", "pool", "action", "boolean",
                                  "gross", "fees", "bps"))
def test_summary_math_identity_finiteness_and_crosscost_tamper(result, defect):
    r = copy.deepcopy(result)
    if defect == "private":
        r["raw_rows"] = "PRIVATE"
    elif defect == "pin":
        r["contract_sha256"] = "wrong"
    elif defect == "flag":
        r["training"] = 0
    elif defect == "count":
        r["folds"][0]["counts"]["selected"] -= 1
    elif defect == "partial":
        r["cells"].pop()
    elif defect == "metric":
        r["cells"][0]["band"]["fees_dollars"] = "NaN"
    elif defect == "delta":
        r["cells"][0]["paired_net_bps_delta"] = "NaN"
    elif defect == "cash":
        r["cells"][0]["cash"]["gross_dollars"] = "1"
    elif defect == "conclusion":
        r["conclusion"] = "promoted"
    elif defect == "pool":
        r["folds"][0]["control_pool_sizes"][0]["sessions"] = True
    elif defect == "action":
        r["cells"][0]["decision_sha256"] = HASH
    elif defect == "boolean":
        r["cells"][0]["fold"] = True
    else:
        c = r["cells"][1]
        m = c["band"]
        field = {"gross": "gross_dollars", "fees": "fees_dollars", "bps": "net_bps_sum"}[defect]
        m[field] = "0" if defect == "fees" else str(Decimal(m[field]) + 1)
        if defect == "bps":
            m[field] = str(Decimal(r["cells"][0]["band"][field]) + 1)
        m["net_dollars"] = str(Decimal(m["gross_dollars"]) - Decimal(m["fees_dollars"]))
        c["paired_net_bps_delta"] = str(Decimal(m["net_bps_sum"]) -
                                        Decimal(c["matched_long"]["net_bps_sum"]))
    with pytest.raises(ValueError):
        s.validate_result(r, HASH)


def receipt():
    return s.h30.encode(dict(
        schema_version="firstrate-free-intraday-normalization-receipt-v1", status="completed",
        permitted_interpretation="source_isolated_retrospective_mechanics_only",
        normalizations=[dict(symbol=symbol, market="US", timeframe="1m",
                             canonical_market_data_relative_path=f"synthetic/{symbol}.csv",
                             canonical_sha256="sha256:" + pin, bar_count=rows,
                             timestamp_set_equal=True, emitted_timestamp_set_sha256=HASH)
                        for symbol, (pin, rows) in s.orb.SOURCE_PINS.items()]))


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    path = tmp_path / s.h30.RECEIPT
    path.parent.mkdir(parents=True)
    path.write_bytes(receipt())
    calls = []
    monkeypatch.setattr(s.h30, "register_frozen_campaign", lambda **kw: calls.append(kw))
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: pytest.fail("real load forbidden"))
    return tmp_path, calls


def test_metadata_only_freeze_is_single_attempt_pins_entire_recipe(frozen, monkeypatch):
    root, calls = frozen
    original = Path.read_bytes

    def guarded(path):
        assert path.suffix != ".csv"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    before = s.h30.encode(s.orb.contract(receipt()))
    pin = s.freeze(root)
    output = s.verify(root, pin)
    payload = json.loads((output / "contract.json").read_bytes())
    assert payload["budget"] == dict(cpu_seconds=300, cpu_threads=1, memory_gib=2, network="none",
                                     fits=0, gpu=0, weights=0, holdout=0, promotion=0, cells=12,
                                     retries=0, max_m1_rows_per_symbol=250000,
                                     max_source_bytes=134217728)
    assert payload["code_sha256"][s.HELPER] == s.HELPER_HASH
    assert payload["fees_bps_per_side"] == [1, 3, 5] and all(payload[f] is False for f in s.FLAGS)
    assert payload["minimums"] == dict(complete_sessions_per_symbol_fold=16,
                                       scored_band_trades_per_symbol_fold=8)
    assert "SCHEDULED" in payload["history"] and "not author-paper reproduction" in (
        payload["interpretation"])
    assert "not a deployable strategy" in payload["control_limits"]
    assert calls[0]["trial_family"] == s.FAMILY and calls[0]["holdout_access"] == "none"
    assert s.h30.encode(s.orb.contract(receipt())) == before  # Old globals/defaults are unchanged.
    with pytest.raises(FileExistsError):
        s.freeze(root)


@pytest.mark.parametrize("defect", ("pin", "receipt", "recipe", "code", "helper"))
def test_contract_receipt_source_and_code_tamper(frozen, monkeypatch, defect):
    root, _ = frozen
    pin = s.freeze(root)
    if defect == "receipt":
        path = root / s.h30.RECEIPT
        data = json.loads(path.read_bytes())
        data["normalizations"][0]["canonical_sha256"] = HASH
        path.write_bytes(s.h30.encode(data))
    elif defect == "recipe":
        monkeypatch.setattr(s, "SECONDS", 301)
    elif defect in ("code", "helper"):
        original = Path.read_bytes

        def changed(path):
            raw = original(path)
            return raw + b"tamper" if path == s.REPO / (s.HELPER if defect == "helper"
                                                       else s.CODE[0]) else raw

        monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError):
        s.verify(root, HASH if defect == "pin" else pin)


def test_repo_root_rejected_before_receipt_read_and_no_writes(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("must reject before reads"))
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "forbidden")


def test_worker_suppresses_failure_never_loads_and_cannot_overwrite(tmp_path, monkeypatch):
    def fail(*_):
        raise ValueError("PRIVATE")

    monkeypatch.setattr(s, "verify", fail)
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: pytest.fail("load forbidden"))
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path, HASH, path)
    assert json.loads(path.read_bytes()) == s.failure(HASH, "runtime_or_invariant_failure")
    assert "PRIVATE" not in path.read_text()
    with pytest.raises(FileExistsError):
        s.worker(tmp_path, tmp_path, HASH, path)


def test_worker_verifies_contract_before_load_and_after_compare_deadline(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(s, "verify", lambda *_: calls.append("verify"))
    monkeypatch.setattr(s.importlib.metadata, "version", lambda *_: "5.4.0")
    monkeypatch.setattr(s.h30, "within", lambda *_: tmp_path / "receipt.json")
    (tmp_path / "receipt.json").write_bytes(b"synthetic")
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: calls.append("load"))

    def exhausted(*_):
        calls.append("compare")
        raise s.h30.StudyFailure("budget_exhausted")

    monkeypatch.setattr(s, "compare", exhausted)
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path, HASH, path)
    assert calls == ["verify", "load", "compare"]
    assert json.loads(path.read_bytes())["status"] == "failed_all_cells"


@pytest.mark.parametrize("defect", (None, "hash", "replay"))
def test_exact_readonly_readback_reconstructs_summary_math(tmp_path, monkeypatch, result, defect):
    r = copy.deepcopy(result)
    r["job"] = None
    raw = s.h30.encode(r)
    (tmp_path / "summary.json").write_bytes(raw)
    (tmp_path / "receipt.json").write_bytes(b"synthetic")
    monkeypatch.setattr(s, "verify", lambda *_: tmp_path)
    monkeypatch.setattr(s.h30, "within", lambda *_: tmp_path / "receipt.json")
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: ())
    monkeypatch.setattr(s, "compare", lambda *_: result if defect != "replay" else {})
    if defect:
        with pytest.raises(ValueError):
            s.readback(tmp_path, tmp_path, HASH, HASH if defect == "hash" else s.h30.digest(raw))
    else:
        assert s.readback(tmp_path, tmp_path, HASH, s.h30.digest(raw))["status"] == "verified"
        assert (tmp_path / "summary.json").read_bytes() == raw


@pytest.mark.parametrize("mode", ("complete", "timeout", "nonzero", "invalid", "failed"))
def test_generic_supervisor_single_attempt_receipts(tmp_path, monkeypatch, result, mode):
    runner = runpy.run_path(str(s.REPO / "scripts/run_firstrate_position_policy.py"))
    g = runner["main"].__globals__
    g["study"] = s
    monkeypatch.setattr(s, "verify", lambda *_: tmp_path)
    registered = []
    g["register_campaign_outcome"] = lambda **kw: registered.append(kw)

    def supervise(target, arguments, **kw):
        assert target is s.worker and kw["seconds"] == 300
        candidate = copy.deepcopy(result) if mode != "failed" else (
            s.failure(HASH, "runtime_or_invariant_failure"))
        if mode == "invalid":
            candidate["raw"] = "PRIVATE"
        arguments[-1].write_bytes(s.h30.encode(candidate))
        return dict(timed_out=mode == "timeout", exit_code=1 if mode == "nonzero" else 0)

    g["runpy"] = SimpleNamespace(run_path=lambda *_: {"supervise": supervise})
    args = SimpleNamespace(artifact_root=tmp_path, market_data_root=tmp_path,
                           contract_sha256=HASH)
    response = runner["dispatch"](args)
    assert response["status"] == ("complete" if mode == "complete" else "failed_all_cells")
    raw = (tmp_path / "summary.json").read_bytes()
    assert "PRIVATE" not in raw.decode() and len(registered) == 1
    with pytest.raises(FileExistsError):
        runner["dispatch"](args)
    assert (tmp_path / "summary.json").read_bytes() == raw
    assert not list(tmp_path.glob("cpu-job-*"))


def test_runner_is_thin_isolated_binding_does_not_mutate_old_module(monkeypatch):
    wrapper = runpy.run_path(str(s.REPO / "scripts/run_firstrate_time_of_day_band.py"))
    captured = []
    old = s.orb.NAME

    def main(argv):
        captured.append((main.__globals__["study"], argv))
        return 7

    monkeypatch.setitem(wrapper["main"].__globals__, "runpy",
                        SimpleNamespace(run_path=lambda *_: {"main": main}))
    assert wrapper["main"](["synthetic"]) == 7
    assert captured == [(s, ["synthetic"])] and s.orb.NAME == old


def linger():
    time.sleep(10)


def test_existing_hard_deadline_supervisor_reaps_owned_synthetic_child():
    supervisor = runpy.run_path(str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    job = supervisor["supervise"](linger, (), seconds=0.1, name="synthetic-band-deadline")
    assert job["timed_out"] is True and job["exit_code"] is not None
    assert job["pid"] not in {p.pid for p in multiprocessing.active_children()}


def test_emergency_controls_remain_authoritative_in_synthetic_replay(tmp_path):
    calendar, index = context()
    d = decide(calendar, index)
    path = s.orb.complete_path(index, "SPY", d.opening, d.closing)
    obs = s.h30.Observation(at=d.at, signal=d.signal, features=())
    emergency = EmergencyStore(tmp_path / "emergency.json")
    emergency.stop_new_orders("synthetic bounded test")
    with pytest.raises(ValueError, match="roundtrip_rejected"):
        s.sessions.payoff(obs, s.h30.Outcome(path[6:]), 3, emergency)


@pytest.mark.parametrize("expired", (False, True))
def test_worker_postchecks_contract_and_deadline(tmp_path, monkeypatch, result, expired):
    calls = []
    monkeypatch.setattr(s, "verify", lambda *_: calls.append("verify"))
    monkeypatch.setattr(s.importlib.metadata, "version", lambda *_: "5.4.0")
    monkeypatch.setattr(s.h30, "within", lambda *_: tmp_path / "receipt.json")
    (tmp_path / "receipt.json").write_bytes(b"synthetic")
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: calls.append("load"))
    monkeypatch.setattr(s, "compare", lambda *_: calls.append("compare") or result)
    if expired:
        monkeypatch.setattr(s, "SECONDS", 0)
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path, HASH, path)
    assert calls == ["verify", "load", "compare", "verify"]
    expected = "failed_all_cells" if expired else "complete"
    assert json.loads(path.read_bytes())["status"] == expected


def test_started_attempt_without_summary_is_not_retried(tmp_path, monkeypatch):
    runner = runpy.run_path(str(s.REPO / "scripts/run_firstrate_position_policy.py"))
    runner["dispatch"].__globals__["study"] = s
    monkeypatch.setattr(s, "verify", lambda *_: tmp_path)
    (tmp_path / "started.json").write_bytes(b"preserved failed attempt")
    args = SimpleNamespace(artifact_root=tmp_path, market_data_root=tmp_path, contract_sha256=HASH)
    with pytest.raises(FileExistsError):
        runner["dispatch"](args)
    assert not (tmp_path / "summary.json").exists()
    assert (tmp_path / "started.json").read_bytes() == b"preserved failed attempt"


@pytest.mark.parametrize("control", (None, "stopped", "malformed"))
def test_real_synthetic_readback_rebuilds_actions_pools_fees_without_rewriting_receipts(
    frozen, monkeypatch, source, result, control,
):
    root, _ = frozen
    pin = s.freeze(root)
    output = s.verify(root, pin)
    r = copy.deepcopy(result)
    r.update(contract_sha256=pin, job=None)
    raw = s.h30.encode(r)
    (output / "summary.json").write_bytes(raw)
    calendar, bars = source
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: calendar)
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: (
        (symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.SYMBOLS))
    if control == "stopped":
        EmergencyStore(output / "emergency.json").stop_new_orders("synthetic replay stop")
    elif control == "malformed":
        (output / "emergency.json").write_bytes(b"invalid synthetic control")
    originals = {(output / "summary.json"): raw,
                 (output / "contract.json"): (output / "contract.json").read_bytes(),
                 (root / s.h30.RECEIPT): (root / s.h30.RECEIPT).read_bytes()}
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    original_open = Path.open

    def archive_read_only(path, mode="r", *args, **kwargs):
        if path.is_relative_to(output) and any(flag in mode for flag in "wax+"):
            pytest.fail("readback wrote into immutable archive")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", archive_read_only)
    if control is None:
        assert s.readback(root, root, pin, s.h30.digest(raw))["status"] == "verified"
    else:
        with pytest.raises(ValueError, match="roundtrip_rejected"):
            s.readback(root, root, pin, s.h30.digest(raw))
    assert all(path.read_bytes() == expected for path, expected in originals.items())
    after = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert after == before


def test_existing_source_loader_rejects_wrong_bytes_before_parsing(tmp_path):
    path = tmp_path / "synthetic" / "SPY.csv"
    path.parent.mkdir()
    path.write_bytes(b"synthetic bad source, not a retained market dataset")
    with pytest.raises(ValueError, match="source_hash"):
        next(s.h30.load_streams(tmp_path, receipt(), time.monotonic() + 60))


@pytest.mark.parametrize("kind", ("directory", "symlink"))
def test_readback_rejects_unsafe_archived_control_before_replay(
    tmp_path, monkeypatch, result, kind,
):
    raw = s.h30.encode(dict(result, job=None))
    (tmp_path / "summary.json").write_bytes(raw)
    (tmp_path / "receipt.json").write_bytes(b"synthetic")
    control = tmp_path / "emergency.json"
    if kind == "directory":
        control.mkdir()
    else:
        control.write_bytes(b"synthetic")
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == control or original(p))
    monkeypatch.setattr(s, "verify", lambda *_: tmp_path)
    monkeypatch.setattr(s.h30, "within", lambda *_: tmp_path / "receipt.json")
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: ())
    monkeypatch.setattr(s, "compare", lambda *_: pytest.fail("unsafe control reached replay"))
    with pytest.raises(ValueError, match="replay_control_invalid"):
        s.readback(tmp_path, tmp_path, HASH, s.h30.digest(raw))


def test_prior_session_must_close_no_later_than_current_open():
    calendar, index = context()
    calendar = list(calendar)
    prior = calendar[-2][0]
    calendar[-2] = (prior, calendar[-1][0] + s.STEP)
    assert decide(tuple(calendar), index).status == "history_unavailable"
    calendar[-2] = (prior, calendar[-1][0])
    assert decide(tuple(calendar), index).status == "selected"
