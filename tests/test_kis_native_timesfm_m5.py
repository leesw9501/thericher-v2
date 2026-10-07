from __future__ import annotations

import copy
import json
import socket
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import kis_native_timesfm_m5 as study


@pytest.fixture(scope="module")
def plan():
    days = tuple(day for i in range(36)
                 if (session := us_equity_2026_session(day := date(2026, 8, 28)
                                                       + timedelta(days=i))) is not None
                 and session.kind == "regular")
    return study.build_plan(days, tuple(us_equity_2026_session(d).window for d in days))


@pytest.fixture(scope="module")
def bars(plan):
    return {symbol: tuple(
        Bar(symbol, "US", Timeframe.M1, slot.session.open_ts + i * study.MINUTE,
            Decimal(100), Decimal(100), Decimal(100), Decimal(100), Decimal(0))
        for slot in plan[::3] for i in range(390)) for symbol in study.SYMBOLS}


@pytest.fixture(scope="module")
def prepared(bars, plan):
    return study.prepare_inputs(bars, plan)


def _points(prepared, qqq=21.0, spy=0.0):
    return [[0.0] * 7 + [qqq if i % 2 == 0 else spy] for i in prepared.ready_rows]


def _seal(prepared, **kwargs):
    return study.seal_decisions(prepared, _points(prepared, **kwargs))


def _change(bars, symbol, predicate, transformation=None):
    return bars | {symbol: tuple(
        transformation(b) if transformation is not None else b
        for b in bars[symbol] if transformation is not None or not predicate(b))}


def test_static_configuration_and_no_tiingo_imports():
    config = study.configuration()
    assert config["cells"] == 30 and config["seconds"] == 300
    assert config["actual_fits"] == 0 and not config["paper_input"]
    assert config["holdout_access"] == "none"
    source = Path(study.__file__).read_text(encoding="utf-8")
    assert "tiingo" not in source.lower()
    assert "GpuFileLock(" not in source and "register_frozen_campaign(" not in source


def test_exact_geometry_and_input_order(plan, prepared):
    assert len(plan) == 75 and len(prepared.ready_rows) == 150
    assert not prepared.unavailable_blocks
    assert all(len(c) == 24 and c[-1] == 0 for c in prepared.contexts)
    assert all(c == (Decimal(0), Decimal(0)) for c in prepared.controls)
    for index, slot in enumerate(plan):
        assert (slot.decision_at.astimezone(study.EASTERN).hour,
                slot.decision_at.astimezone(study.EASTERN).minute) == study.CLOCKS[index % 3]
        last_open = slot.decision_at - 5 * study.MINUTE
        assert last_open + 2 * 5 * study.MINUTE == slot.entry_at  # point[1]
        assert last_open + 8 * 5 * study.MINUTE == slot.exit_at  # point[7]
        assert slot.exit_at - slot.entry_at == 30 * study.MINUTE


@pytest.mark.parametrize("origin,utc_hour", [(date(2026, 3, 1), 16), (date(2026, 10, 25), 15)])
def test_dst_calendar_conversion(origin, utc_hour):
    days = tuple(origin + timedelta(days=i) for i in range(25))
    sessions = tuple(SessionWindow(
        datetime.combine(d, clock_time(9, 30), study.EASTERN).astimezone(UTC),
        datetime.combine(d, clock_time(16), study.EASTERN).astimezone(UTC)) for d in days)
    slots = study.build_plan(days, sessions)
    assert slots[0].decision_at.hour == utc_hour
    assert slots[-3].decision_at.hour != utc_hour


@pytest.mark.parametrize("bad", ["short", "duplicate", "reverse", "early_close", "wrong_open"])
def test_bad_plan_never_drops_dates(plan, bad):
    days = tuple(s.session_date for s in plan[::3])
    sessions = tuple(s.session for s in plan[::3])
    if bad == "short":
        days, sessions = days[:-1], sessions[:-1]
    elif bad == "duplicate":
        days = days[:-1] + (days[-2],)
    elif bad == "reverse":
        days, sessions = days[::-1], sessions[::-1]
    else:
        first = sessions[0]
        sessions = (SessionWindow(first.open_ts + (study.MINUTE if bad == "wrong_open" else
                                                   timedelta(0)),
                                  first.close_ts - (180 * study.MINUTE if bad == "early_close"
                                                     else timedelta(0))),) + sessions[1:]
    with pytest.raises(study.StudyFault):
        study.build_plan(days, sessions)


@pytest.mark.parametrize("value,long", [(19.999, False), (20.0, False), (20.001, True),
                                        (-100.0, False), (100.0, True)])
def test_log_bps_strict_threshold_and_unconditional_bypass(prepared, value, long):
    seal = _seal(prepared, qqq=value, spy=value)
    assert seal.targets[0][0] == ((Decimal(".5"),) * 2 if long else (Decimal(0),) * 2)
    assert seal.targets[1][0] == (Decimal(0),) * 2
    assert seal.targets[2][0] == (Decimal(".5"),) * 2
    assert seal.targets[3][0] == seal.targets[4][0] == (Decimal(0),) * 2


def test_p7_minus_p1_not_other_point_or_expm1(prepared):
    points = _points(prepared)
    for row in points:
        row[0], row[1], row[7] = 9999.0, 100.0, 120.0
    seal = study.seal_decisions(prepared, points)
    assert all(t == (Decimal(0), Decimal(0)) for t in seal.targets[0])


@pytest.mark.parametrize("control_index", [0, 1])
@pytest.mark.parametrize("value,long", [(Decimal("20"), False), (Decimal("20.0001"), True)])
def test_naive_controls_same_log_threshold(prepared, control_index, value, long):
    control = [Decimal(0), Decimal(0)]
    control[control_index] = value
    changed = replace(prepared, controls=tuple(tuple(control) for _ in range(150)))
    seal = _seal(changed)
    expected = (Decimal(".5"),) * 2 if long else (Decimal(0),) * 2
    assert seal.targets[3 + control_index][0] == expected


@pytest.mark.parametrize("kind", ["short", "horizon", "nan", "inf", "bool", "string"])
def test_invalid_forecast_fails_not_flat(prepared, kind):
    points = _points(prepared)
    if kind == "short":
        points.pop()
    elif kind == "horizon":
        points[0].pop()
    else:
        points[0][7] = {"nan": float("nan"), "inf": float("inf"),
                        "bool": True, "string": "21"}[kind]
    with pytest.raises(study.StudyFault, match="forecast"):
        study.seal_decisions(prepared, points)


@pytest.mark.parametrize("clock_index", [0, 1, 2])
@pytest.mark.parametrize("symbol", study.SYMBOLS)
@pytest.mark.parametrize("mutation", ["remove", "prices", "support"])
def test_all_current_future_mutations_leave_earlier_context_and_action(
    bars, plan, prepared, clock_index, symbol, mutation,
):
    decision = plan[clock_index].decision_at
    if mutation == "remove":
        changed = _change(bars, symbol, lambda b: b.start_ts >= decision)
    else:
        def alter(bar):
            if bar.start_ts < decision:
                return bar
            if mutation == "prices":
                return replace(bar, open=Decimal(200), high=Decimal(200), low=Decimal(200),
                               close=Decimal(200))
            return replace(bar, symbol="IWM", complete=False)
        changed = _change(bars, symbol, lambda _: False, alter)
    after = study.prepare_inputs(changed, plan)
    before_seal, after_seal = _seal(prepared), _seal(after)
    indices = (2 * clock_index, 2 * clock_index + 1)
    assert all(after.contexts[i] == prepared.contexts[i]
               and after.controls[i] == prepared.controls[i] for i in indices)
    assert all(a[clock_index] == b[clock_index]
               for a, b in zip(before_seal.targets, after_seal.targets, strict=True))


@pytest.mark.parametrize("symbol", study.SYMBOLS)
@pytest.mark.parametrize("bad", ["missing", "duplicate", "incomplete", "wrong_symbol"])
def test_required_past_gap_unavailable_without_earlier_future_mask(bars, plan, symbol, bad):
    at = plan[1].decision_at - study.MINUTE
    if bad == "missing":
        changed = _change(bars, symbol, lambda b: b.start_ts == at)
    elif bad == "duplicate":
        item = next(b for b in bars[symbol] if b.start_ts == at)
        changed = bars | {symbol: tuple(sorted(bars[symbol] + (item,), key=lambda b: b.start_ts))}
    else:
        changed = _change(bars, symbol, lambda _: False, lambda b: replace(
            b, complete=False) if b.start_ts == at and bad == "incomplete" else replace(
                b, symbol="IWM") if b.start_ts == at else b)
    prepared = study.prepare_inputs(changed, plan)
    assert prepared.contexts[:2] == ((0.0,) * 24,) * 2
    assert prepared.contexts[2:4] == (None, None)
    assert prepared.unavailable_blocks == (0,)
    seal = _seal(prepared)
    assert seal.targets[0][0] == (Decimal(".5"), Decimal(0))
    assert all(t[1] is None for t in seal.targets)
    cells = study.evaluate_sealed(changed, seal)
    assert len(cells) == 30
    assert {c["reason"] for c in cells if c["block"] == 0} == {"past_input_unavailable"}
    assert {c["reason"] for c in cells if c["block"] == 1} == {"prior_block_unavailable"}


@pytest.mark.parametrize("symbol", study.SYMBOLS)
@pytest.mark.parametrize("which", ["entry_at", "exit_at"])
@pytest.mark.parametrize("block", [0, 1])
def test_mark_gap_separate_from_past_input_and_no_date_filter(bars, plan, prepared, symbol, which,
                                                            block):
    slot = plan[35 if block == 0 else 74]
    at = getattr(slot, which)
    changed = _change(bars, symbol, lambda b: b.start_ts == at)
    after = study.prepare_inputs(changed, plan)
    assert after == prepared
    seal = _seal(after)
    cells = study.evaluate_sealed(changed, seal)
    assert len(cells) == 30 and study.criterion(cells) == "input_unavailable"
    assert {c["reason"] for c in cells if c["block"] == block} == {"forward_mark_unavailable"}
    if block == 1:
        original = study.evaluate_sealed(bars, seal)
        assert cells[:15] == original[:15]
    else:
        assert {c["reason"] for c in cells if c["block"] == 1} == {"prior_block_unavailable"}


def test_model_inputs_and_control_formula(bars, plan):
    at = plan[0].decision_at
    def alter(bar):
        if bar.start_ts >= at:
            return bar
        i = int((bar.start_ts - plan[0].session.open_ts) / study.MINUTE)
        value = Decimal(100) + Decimal(i) / 10
        return replace(bar, open=value, high=value, low=value, close=value)
    changed = _change(bars, "QQQ", lambda _: False, alter)
    prepared = study.prepare_inputs(changed, plan)
    opens = tuple(Decimal(100) + Decimal(i) / 10 for i in range(0, 120, 5))
    with localcontext(study.DECIMAL_CONTEXT):
        logs = tuple(10000 * (b / a).ln() for a, b in zip(opens, opens[1:], strict=False))
        assert prepared.controls[0] == (sum(logs) / 23 * 6, logs[-1] * 6)
    assert prepared.contexts[0][0] < 0 and prepared.contexts[0][-1] == 0
    assert prepared.contexts[1] == (0.0,) * 24


def test_shared_continuous_capital_and_analytic_cost(bars, prepared):
    cells = study.evaluate_sealed(bars, _seal(prepared))
    assert len(cells) == 30 and study.criterion(cells) == "rejected"
    with localcontext(study.DECIMAL_CONTEXT):
        for cost in study.COSTS:
            f = cost / 10000
            for policy, exposure in (("timesfm", Decimal(".5")),
                                     ("unconditional_long", Decimal(1))):
                first, second = [c["metrics"] for c in cells if c["policy"] == policy
                                 and c["cost_bps"] == str(cost)]
                factor = (1 - f * exposure) / (1 + f * exposure)
                assert abs(Decimal(first["nav"]) - factor ** 36) < Decimal("1e-38")
                assert second["entering_nav"] == first["nav"]
                assert abs(Decimal(second["nav"]) - factor ** 75) < Decimal("1e-38")
                assert abs(Decimal(second["growth"]) - (factor ** 39 - 1)) < Decimal("1e-38")
                assert first["sessions"] == 12 and second["sessions"] == 13
        cash = [c["metrics"] for c in cells if c["policy"] == "cash"]
        assert all(Decimal(c["growth"]) == 0 and Decimal(c["utility"]) == 0
                   and c["trades"] == 0 for c in cash)


def test_second_block_ledger_receives_first_capital_and_units(bars, prepared, monkeypatch):
    original, observations = study.replay, []
    def observe(*args, **kwargs):
        value = original(*args, **kwargs)
        observations.append((kwargs["initial_cash"], value))
        return value
    monkeypatch.setattr(study, "replay", observe)
    study.evaluate_sealed(bars, _seal(prepared))
    assert len(observations) == 30
    for first, second in zip(observations[:15], observations[15:], strict=True):
        assert first[0] == 1 and second[0] == first[1].final_nav
        if first[1].total_fees:
            assert second[1].slots[0].pre_nav < 1
            assert second[1].slots[0].fills[0].quantity < first[1].slots[0].fills[0].quantity


def test_actions_and_accounting_invariant_to_scale_order_decimal_context(bars, plan, prepared):
    scaled = {symbol: tuple(replace(b, open=b.open * scale, high=b.high * scale,
                                   low=b.low * scale, close=b.close * scale) for b in values)
              for symbol, values, scale in (("SPY", bars["SPY"], Decimal(7)),
                                            ("QQQ", bars["QQQ"], Decimal(".3")))}
    with localcontext() as context:
        context.prec = 6
        second = study.prepare_inputs(scaled, plan)
        seal = _seal(second)
        actual = study.evaluate_sealed(scaled, seal)
    original = study.evaluate_sealed(bars, _seal(prepared))
    assert second.input_sha256 == prepared.input_sha256
    assert seal.sha256 == _seal(prepared).sha256
    with localcontext(study.DECIMAL_CONTEXT):
        for a, b in zip(actual, original, strict=True):
            assert tuple(a[key] for key in ("block", "policy", "cost_bps")) == tuple(
                b[key] for key in ("block", "policy", "cost_bps"))
            for key in ("nav", "growth", "utility", "fees", "traded_notional"):
                # Bounds accumulated 1e-40 quantity dust at these synthetic prices.
                difference = abs(Decimal(a["metrics"][key]) - Decimal(b["metrics"][key]))
                assert difference < Decimal("1e-34")


def test_immutable_private_records_and_defensive_prediction_copy(prepared):
    points = _points(prepared)
    seal = study.seal_decisions(prepared, points)
    before = seal.sha256
    points[0][7] = 0
    assert seal.sha256 == before
    assert "Decimal" not in repr(prepared) and "21.0" not in repr(seal)
    with pytest.raises(FrozenInstanceError):
        seal.targets = ()


def test_seal_verified_before_any_payoff_lookup(bars, prepared, monkeypatch):
    seal = _seal(prepared)
    bad = replace(seal, targets=((None,) * 75,) + seal.targets[1:])
    def forbidden(*_args):
        pytest.fail("marks accessed before seal verification")
    monkeypatch.setattr(study, "_marks", forbidden)
    with pytest.raises(study.StudyFault, match="action_seal_changed"):
        study.evaluate_sealed(bars, bad)


@pytest.mark.parametrize("bad", ["missing_cell", "duplicate_cell"])
def test_matrix_identity_rejected(bars, prepared, bad):
    cells = list(study.evaluate_sealed(bars, _seal(prepared)))
    cells.pop() if bad == "missing_cell" else cells.__setitem__(-1, cells[0])
    with pytest.raises(study.StudyFault, match="cell_matrix"):
        study.criterion(cells)


def test_strong_kill_both_metrics_blocks_no_rounding_rescue():
    cells = [dict(block=b, policy=p, cost_bps=str(c), status="complete", reason=None,
                  metrics=dict(growth=".1" if p == "timesfm" else "0",
                               utility=".1" if p == "timesfm" else "0", trades=1))
             for b in (0, 1) for c in study.COSTS for p in study.POLICIES]
    assert study.criterion(cells) == "development_survivor"
    for key in ("growth", "utility"):
        changed = copy.deepcopy(cells)
        cell = next(c for c in changed if c["block"] == 1 and c["cost_bps"] == "10"
                    and c["policy"] == "timesfm")
        cell["metrics"][key] = "0.0000000001"
        assert study.criterion(changed) == "rejected"


def _table(rows):
    return dict(columns=list(rows[0]), rows=[list(row.values()) for row in rows])


@pytest.fixture
def bundle(tmp_path, bars, plan, monkeypatch):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    output = root / "research" / study.NAME
    output.mkdir(parents=True)
    market.mkdir()
    marker = market / "fixture.bin"
    marker.write_bytes(b"synthetic-only")
    marker_pin = study.digest(marker.read_bytes())
    source_rows = [dict(session_date=slot.session_date.isoformat(), symbol=symbol, exchange="NAS",
                        cache_root_market_relative=f"fixture/{slot.session_date}/{symbol}",
                        index_sha256="sha256:" + "a" * 64,
                        catalog_dataset_hash="sha256:" + "b" * 64)
                   for slot in plan[::3] for symbol in study.SYMBOLS]
    commitment = dict(
        sessions=_table([dict(session_date=s.session_date.isoformat(),
                              open_utc=s.session.open_ts.isoformat().replace("+00:00", "Z"),
                              close_utc=s.session.close_ts.isoformat().replace("+00:00", "Z"),
                              expected_regular_m1_count=390) for s in plan[::3]]),
        sources=_table(source_rows), snapshots=_table([
            dict(source_ordinal=i % 50, manifest_path_market_relative="fixture.bin",
                 manifest_sha256=marker_pin, raw_path_market_relative="fixture.bin",
                 raw_sha256=marker_pin) for i in range(51)]), loader_source_pins={},
    )
    study.atomic_new(output / "input-commitment.json", commitment)
    input_pin = study.digest((output / "input-commitment.json").read_bytes())
    monkeypatch.setattr(study, "INPUT_PIN", input_pin)
    paths = ("src/thericher_v2/research/kis_native_timesfm_m5.py",
             "src/thericher_v2/research/timesfm_local.py",
             "src/thericher_v2/research/paired_completed_context.py",
             "src/thericher_v2/research/clock_portfolio_nav.py")
    contract = dict(name=study.NAME, config=study.configuration(), runtime=study.RUNTIME,
                    input_commitment_sha256=input_pin,
                    code_sha256={p: study.digest((study.REPO / p).read_bytes()) for p in paths})
    precommit = output / "precommit.json"
    study.atomic_new(precommit, contract)
    pin = study.digest(precommit.read_bytes())
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    import thericher_v2.data.kis_paper_intraday as loader
    def catalog(**kwargs):
        assert kwargs["expected_index_metadata_sha256"] == "sha256:" + "a" * 64
        day = date.fromisoformat(kwargs["cache_root"].parent.name)
        symbol = kwargs["symbol"]
        return SimpleNamespace(dataset_hash="sha256:" + "b" * 64,
                               bars=tuple(b for b in bars[symbol] if b.start_ts.date() == day))
    monkeypatch.setattr(loader, "load_verified_kis_paper_private_intraday_catalog", catalog)
    return SimpleNamespace(root=root, market=market, output=output, precommit=precommit,
                           pin=pin, commitment=commitment)


def test_exact_table_commitment_and_market_relative_loader(bundle, bars):
    _, commitment, plan = study.read_contract(bundle.precommit, bundle.pin, bundle.market)
    assert len(plan) == 75
    loaded = study.load_committed_bars(commitment, bundle.market)
    assert loaded == bars


@pytest.mark.parametrize("bad", ["missing_date", "wrong_open", "wrong_count", "duplicate_date"])
def test_commitment_schedule_no_replacement(bundle, bad):
    value = copy.deepcopy(bundle.commitment)
    if bad == "missing_date":
        value["sessions"]["rows"].pop()
    elif bad == "duplicate_date":
        value["sessions"]["rows"][-1][0] = value["sessions"]["rows"][-2][0]
    else:
        value["sessions"]["rows"][0][1 if bad == "wrong_open" else 3] = (
            "2026-08-28T13:31:00Z" if bad == "wrong_open" else 389)
    with pytest.raises(study.StudyFault):
        study.commitment_plan(value)


@pytest.mark.parametrize("bad", ["duplicate", "wrong_symbol", "wrong_hash", "missing", "escape"])
def test_catalog_partition_hash_and_relative_scope(bundle, bad):
    value = copy.deepcopy(bundle.commitment)
    rows = value["sources"]["rows"]
    if bad == "duplicate":
        rows[-1] = rows[0]
    elif bad == "missing":
        rows.pop()
    elif bad == "wrong_symbol":
        rows[0][1] = "IWM"
    elif bad == "wrong_hash":
        rows[0][-1] = "sha256:" + "c" * 64
    else:
        rows[0][3] = "../escape"
    with pytest.raises(study.StudyFault):
        study.load_committed_bars(value, bundle.market)


def _fake_inference(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, reset_peak_memory_stats=lambda: None,
                             synchronize=lambda: None, max_memory_allocated=lambda: 123),
        use_deterministic_algorithms=lambda value: None,
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import thericher_v2.research.timesfm_local as local
    def forecast(directory, pins, contexts, horizon, device):
        calls.append((directory, pins, contexts, horizon, device))
        assert len(contexts) <= 150 and all(len(row) == 24 for row in contexts)
        return [[0.0] * 7 + [21.0] for _ in contexts], None
    monkeypatch.setattr(local, "forecast_timesfm_2p5", forecast)
    return calls


def test_one_fake_batch_seal_before_payoff_and_exact_all_ro_readback(bundle, monkeypatch):
    calls = _fake_inference(monkeypatch)
    original = study._marks
    def marks(*args):
        assert (bundle.output / "actions.json").exists()
        return original(*args)
    monkeypatch.setattr(study, "_marks", marks)
    def no_network(*_args, **_kwargs):
        pytest.fail("network not part of this campaign")
    monkeypatch.setattr(socket, "create_connection", no_network)
    value = study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)
    assert value["status"] == "complete" and value["cells"] == 30
    assert len(calls) == 1 and len(calls[0][2]) == 150 and calls[0][3:] == (8, "cuda")
    before = {p.name: p.read_bytes() for p in bundle.output.iterdir()}
    replay = study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                                value["result_sha256"])
    assert replay["replay"] == "exact" and replay["inference_calls_readback"] == 0
    assert len(calls) == 1 and before == {p.name: p.read_bytes() for p in bundle.output.iterdir()}
    with pytest.raises(study.StudyFault, match="attempt_already_exists"):
        study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)


def test_worker_failure_binding_and_no_raw_error(bundle, monkeypatch):
    def fail(*_args):
        raise ValueError("synthetic-private-error-12345")
    monkeypatch.setattr(study, "load_committed_bars", fail)
    result = study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)
    assert result["status"] == "failed" and result["phase"] == "source_input"
    assert result["reason"] == "worker_failed" and result["inference_calls"] == 0
    assert "12345" not in json.dumps(result)
    verified = study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                                   result["result_sha256"])
    assert verified["replay"] == "failure_binding_only"


def test_readback_rejects_mutated_actions(bundle, monkeypatch):
    _fake_inference(monkeypatch)
    result = study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)
    actions = bundle.output / "actions.json"
    actions.write_bytes(actions.read_bytes() + b" ")
    with pytest.raises(study.StudyFault, match="artifact_hash"):
        study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                            result["result_sha256"])


@pytest.mark.parametrize("mutation", ["inference_calls", "status", "phase", "elapsed_seconds"])
def test_readback_rejects_semantically_wrong_rehashed_result(bundle, monkeypatch, mutation):
    _fake_inference(monkeypatch)
    study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)
    path = bundle.output / "worker-result.json"
    value = json.loads(path.read_bytes())
    value[mutation] = {"inference_calls": 2, "status": "input_unavailable",
                       "phase": "source_input", "elapsed_seconds": -1}[mutation]
    path.write_bytes(study.encode(value))
    with pytest.raises(study.StudyFault):
        study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                            study.digest(path.read_bytes()))


def test_failure_binding_rejects_later_action_file(bundle, monkeypatch):
    def fail(*_args):
        raise ValueError("synthetic failure")
    monkeypatch.setattr(study, "load_committed_bars", fail)
    result = study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)
    (bundle.output / "actions.json").write_bytes(b"later synthetic bytes")
    with pytest.raises(study.StudyFault, match="failure_action_binding"):
        study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                            result["result_sha256"])


def test_partial_action_write_failure_retains_exact_byte_binding(bundle, monkeypatch):
    _fake_inference(monkeypatch)
    original = study.atomic_new
    def partial(path, value):
        if Path(path).name == "actions.json":
            Path(path).write_bytes(b'{"synthetic_partial":')
            raise OSError("synthetic write interruption")
        original(path, value)
    monkeypatch.setattr(study, "atomic_new", partial)
    result = study.run_campaign(bundle.precommit, bundle.pin, bundle.root, bundle.market)
    assert result["status"] == "failed" and result["phase"] == "decision_seal"
    replay = study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                                 result["result_sha256"])
    assert replay["replay"] == "failure_binding_only"
    (bundle.output / "actions.json").write_bytes(b"changed")
    with pytest.raises(study.StudyFault, match="failure_action_binding"):
        study.verify_result(bundle.precommit, bundle.pin, bundle.root, bundle.market,
                            result["result_sha256"])


@pytest.mark.parametrize("arguments", [["--precommit", "unused"],
                                        ["--contract-sha256", "unused"],
                                        ["--run"], ["--verify"],
                                        ["--smoke", "--result-sha256", "unused"]])
def test_cli_requires_exact_mode_bindings(arguments):
    with pytest.raises(SystemExit):
        study.main(arguments)


def test_no_model_weight_cpu_smoke_and_static_cli(monkeypatch, capsys):
    def no_model(*_args, **_kwargs):
        pytest.fail("synthetic smoke must not call model inference")
    import thericher_v2.research.timesfm_local as local
    monkeypatch.setattr(local, "forecast_timesfm_2p5", no_model)
    assert study.main(["--smoke"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert all(value[key] == 0 for key in (
        "actual_fits", "model_inference_calls", "actual_source_reads"))
    assert study.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "static_plan"


def test_input_deadline_is_categorical(bars, plan):
    with pytest.raises(study.StudyFault, match="compute_stop"):
        study.prepare_inputs(bars, plan, deadline=0)
