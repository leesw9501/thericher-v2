"""Synthetic monthly activity, shared-NAV, causal input and immutable lifecycle checks."""

import copy
import json
import runpy
import socket
import time
from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import federal_reserve_h15 as board
from thericher_v2.research import board_yield_curve_monthly_policy as s


def forbidden(*_args, **_kwargs):
    pytest.fail("actual source/network/credential/registry access forbidden")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(s.base, "load_adjusted", forbidden)
    monkeypatch.setattr(board, "read_federal_reserve_h15_snapshot", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(s, "check_metadata", forbidden)
    monkeypatch.setattr(s, "register_contract", forbidden)
    monkeypatch.setattr(s, "register_campaign_outcome", forbidden)


@pytest.fixture
def sample(monkeypatch):
    rows, snapshot, skeleton = s.synthetic_inputs()
    monkeypatch.setattr(s, "calendar_schedule", lambda: skeleton["plan"]["schedule"])
    monkeypatch.setattr(s, "runtime_identity", lambda: {
        "python": "3.12.14", "numpy": "2.5.1", "calendar": "5.4.0",
    })
    contract = s.proposed_contract()
    return SimpleNamespace(rows=rows, snapshot=snapshot, contract=contract,
                           pin=s.digest(s.encode(contract)))


def evaluate(sample, *, rows=None, snapshot=None, **kwargs):
    return s.evaluate(sample.rows if rows is None else rows,
                      sample.snapshot if snapshot is None else snapshot,
                      sample.contract, sample.pin, deadline=time.monotonic() + 30, **kwargs)


def decisions(sample):
    return s.board_decisions(sample.contract["plan"], sample.snapshot)


def test_static_contract_and_zero_source_smoke():
    cfg = s.configuration()
    assert cfg["cells"] == 24 and cfg["costs_per_side_bps"] == ["2.5", "5", "10"]
    assert (cfg["resource"]["evaluation_seconds"]
            == cfg["resource"]["readonly_replay_seconds"] == 120)
    assert cfg["resource"]["python"] == "3.12.14" and cfg["resource"]["cpu_limit"] == 2
    assert cfg["resource"]["memory_bytes"] == 2 * 1024**3 and cfg["resource"]["network"] == "none"
    assert cfg["rate_selection"]["older_invalid_fallback"] is False
    assert cfg["predictive_fits"] == cfg["parameter_searches"] == 0 and cfg["gpu"] is False
    smoke = s.synthetic_smoke()
    assert smoke["status"] == "synthetic_smoke_passed" and smoke["cells"] == 24
    assert smoke["actual_source_reads"] == smoke["actual_fits"] == 0


def test_data_pins_code_and_adjusted_source(sample):
    source = sample.contract["source"]
    assert source["board"]["sha256"] == dict(board.SNAPSHOT_SHA256)
    assert len(source["board"]["sha256"]) == 5
    assert source["etf"]["raw_sha256"] == dict(s.etf.RAW_SHA256)
    assert "src/thericher_v2/research/three_asset_nav.py" in sample.contract["code_sha256"]
    assert "src/thericher_v2/data/tiingo_eod.py" in sample.contract["code_sha256"]


def test_calendar_previous_close_and_canonical_utc(sample):
    plan = sample.contract["plan"]
    schedule = plan["schedule"]
    for period in plan["periods"]:
        assert period["months"][0]["index"] == period["bounds"][0]
        for item in period["months"]:
            assert item["decision_at"] == schedule[item["index"] - 1]["close_at"]
    changed = copy.deepcopy(schedule)
    changed[0]["close_at"] = changed[0]["close_at"].replace("T", " ").replace("+00:00", "Z")
    assert s.build_plan(changed) == plan  # Parse/normalize, never compare raw clock strings.


@pytest.mark.parametrize("key,value", [
    ("open_at", "2001-12-31T14:30:00+01:00"),
    ("close_at", "2001-12-31T21:00:00"),
    ("close_at", "2002-01-01T21:00:00+00:00"),
    ("close_at", "2001-12-31T13:30:00+00:00"),
])
def test_calendar_rejects_wrong_offset_date_and_order(sample, key, value):
    schedule = copy.deepcopy(sample.contract["plan"]["schedule"])
    schedule[0][key] = value
    with pytest.raises(ValueError, match="calendar_clocks"):
        s.build_plan(schedule)


def test_train_activity_weights_sessions_not_months(sample):
    plan = sample.contract["plan"]
    sequence = list(decisions(sample))
    months = plan["periods"][0]["months"]
    assert len(months) == 3
    by_index = {item["index"]: value for item, value in zip(months, (1, 0, 1), strict=True)}
    sequence = tuple(replace(row, exposure=Decimal(by_index[row.index]))
                     if row.index in by_index else row for row in sequence)
    activity = s.train_activity(plan, sequence)
    assert activity.scheduled_sessions == activity.available_sessions == 5
    assert activity.fraction == Decimal("0.6")  # 2+1 active scheduled sessions, not 2/3 months.
    assert "0.6" not in repr(activity)
    assert all("exposure" not in repr(row) for row in sequence)


@pytest.mark.parametrize("value", [Decimal(0), Decimal(1)])
def test_train_all_cash_and_all_invested_are_valid(sample, value):
    sequence = tuple(replace(row, exposure=value) for row in decisions(sample))
    activity = s.train_activity(sample.contract["plan"], sequence)
    assert activity.fraction == value and activity.available_sessions == activity.scheduled_sessions


def test_missing_train_keeps_whole_denominator_and_all_cells_unavailable(sample):
    empty = board.H15Snapshot((), ())
    result = evaluate(sample, snapshot=empty)
    assert result["matching"]["scheduled_sessions"] == 5
    assert result["matching"]["available_sessions"] == 0
    assert result["matching"]["fraction"] is None and len(result["cells"]) == 24
    assert all(row["status"] == "input_unavailable" for row in result["cells"])
    assert result["criterion"] == "input_unavailable"


def test_one_missing_train_month_is_not_reduced_denominator(sample):
    seq = list(decisions(sample))
    seq[0] = replace(seq[0], exposure=None)
    activity = s.train_activity(sample.contract["plan"], seq)
    assert activity.scheduled_sessions == 5 and activity.available_sessions == 3
    assert activity.fraction is None


@pytest.mark.parametrize("ten", [Decimal(0), Decimal(1)])
def test_nonpositive_slope_zero_activity_is_not_input_failure(sample, ten):
    snapshot = replace(sample.snapshot, ten_year=tuple(
        replace(row, yield_percent=ten) for row in sample.snapshot.ten_year))
    result = evaluate(sample, snapshot=snapshot)
    assert Decimal(result["matching"]["fraction"]) == 0
    assert result["status"] == "complete" and result["criterion"] == "rejected"
    assert all(Decimal(row["final_nav"]) == 1 for row in result["cells"]
               if row["policy"] in {"yield_curve", "cash", "train_activity_matched"})


def test_macro_actions_and_activity_are_sealed_before_price_parse(sample):
    sequence = []
    def seal(value):
        assert value["available_sessions"] == value["scheduled_sessions"]
        assert "all_macro_targets_sha256" in value and "decision_sha256" not in value
        sequence.append("sealed")
    def loader():
        assert sequence == ["sealed"]
        sequence.append("prices")
        return sample.rows
    result = s.evaluate(loader, sample.snapshot, sample.contract, sample.pin,
                        deadline=time.monotonic() + 30, seal=seal)
    assert sequence == ["sealed", "prices"] and result["status"] == "complete"


def test_threshold_strict_zero_no_outcome_dependent_epsilon(sample):
    for slope, wanted in ((Decimal(0), Decimal(0)), (Decimal("1e-100"), Decimal(1))):
        seq = s.prepare_decisions(sample.contract["plan"], lambda _, slope=slope: slope)
        assert all(row.exposure == wanted for row in seq)


@pytest.mark.parametrize("fraction", [
    Decimal(0), Decimal(1), Decimal("0.6"), Decimal("0.123456789"),
])
def test_exact_thirds_and_cash_under_hostile_context(fraction):
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        weights = s.equal_weight(fraction)
    assert sum(map(Fraction, weights), Fraction()) == Fraction(fraction)
    assert all(Fraction(value) >= 0 for value in weights)
    assert weights[:2] == (weights[0],) * 2


@pytest.mark.parametrize("fraction", [Decimal("-0.1"), Decimal("1.1"), Decimal("NaN"),
                                     Decimal("1e-46"), 1])
def test_no_target_clipping_or_hidden_quantization(fraction):
    with pytest.raises(ValueError, match="target_"):
        s.equal_weight(fraction)


def test_actual_shared_ledger_replay_24_cells_and_safe_projection(sample):
    result = evaluate(sample)
    assert result["criterion"] == "rejected" and len(result["cells"]) == 24
    assert all(row["status"] == "complete" for row in result["cells"])
    for cell in result["cells"]:
        if cell["policy"] == "cash":
            assert Decimal(cell["final_nav"]) == 1 and Decimal(cell["utility"]) == 0
        elif cell["policy"] in {"equal_weight", "train_activity_matched"}:
            with localcontext() as context:
                context.prec = 50
                fraction = (Decimal(1) if cell["policy"] == "equal_weight"
                            else Decimal(result["matching"]["fraction"]))
                cost = Decimal(cell["cost_bps"]) / 10000
                expected = (1 - fraction * cost) / (1 + fraction * cost)
                assert abs(Decimal(cell["final_nav"]) - expected) < Decimal("1e-40")
    safe = s.safe_result(result)
    assert set(safe) == {"status", "criterion", "cells", "contract_sha256", "result_sha256"}
    assert not {"matching", "input_facts", "utility", "final_nav"}.intersection(safe)


def test_same_actions_costs_one_nav_reset_per_period(sample, monkeypatch):
    calls = []
    original = s.base.replay_joint
    def replay(rows, days, bounds, actions, cost, *, deadline):
        calls.append((tuple(bounds), copy.deepcopy(actions), cost))
        return original(rows, days, bounds, actions, cost, deadline=deadline)
    monkeypatch.setattr(s.base, "replay_joint", replay)
    result = evaluate(sample)
    assert len(calls) == 24
    for period in range(2):
        for policy in range(4):
            indices = [period * 12 + cost * 4 + policy for cost in range(3)]
            assert all(calls[index][1] == calls[indices[0]][1] for index in indices)
    assert all(Decimal(row["final_nav"]) == 1 for row in result["cells"] if row["policy"] == "cash")


def test_hostile_context_campaign_exact(sample):
    normal = evaluate(sample)
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        hostile = evaluate(sample)
    assert s.encode(hostile) == s.encode(normal)


def test_one_comparison_mark_gap_local_full_period_no_day_drop(sample):
    rows = dict(sample.rows)
    plan = sample.contract["plan"]
    missing_day = plan["days"][plan["periods"][1]["bounds"][0]]
    rows["QQQ"] = tuple(row for row in rows["QQQ"] if row.session_date.isoformat() != missing_day)
    result = evaluate(sample, rows=rows)
    assert result["input_facts"][0]["missing_marks"] == 1
    assert all(c["status"] == "input_unavailable" for c in result["cells"][:12])
    assert all(c["status"] == "complete" for c in result["cells"][12:])
    assert result["criterion"] == "input_unavailable"


def test_future_mark_support_never_changes_existing_period(sample):
    period = sample.contract["plan"]["periods"][1]
    days = sample.contract["plan"]["days"]
    original = s.prepare_marks(sample.rows, period, days)
    stop = days[period["bounds"][1] - 1]
    removed = {symbol: tuple(r for r in stream if r.session_date.isoformat() <= stop)
               for symbol, stream in sample.rows.items()}
    assert s.prepare_marks(removed, period, days) == original
    changed = {symbol: tuple(SimpleNamespace(**{
        **{key: getattr(row, key) for key in ("symbol", "session_date", "adj_open", "adj_high",
                                           "adj_low", "adj_close")},
        "adj_close": Decimal("NaN"),
    }) if row.session_date.isoformat() > stop else row for row in stream)
               for symbol, stream in sample.rows.items()}
    assert s.prepare_marks(changed, period, days) == original


def test_future_macro_mutations_do_not_change_train_or_first_decision(sample):
    seq = decisions(sample)
    last_train = sample.contract["plan"]["periods"][0]["months"][-1]["index"]
    later = tuple(replace(row, exposure=None) if row.index > last_train else row for row in seq)
    assert (s.train_activity(sample.contract["plan"], later)
            == s.train_activity(sample.contract["plan"], seq))
    at = seq[0].decision_at
    future = at.date() + timedelta(days=30000)
    changed = board.H15Snapshot(
        (*sample.snapshot.two_year, board.H15Observation(future, Decimal("NaN"))),
        (*sample.snapshot.ten_year, board.H15Observation(future, Decimal("Infinity"))),
    )
    assert s.board_decisions(sample.contract["plan"], changed) == seq


def test_per_asset_price_scale_does_not_create_independent_capital(sample):
    original = evaluate(sample)
    scaled = {}
    for symbol, factor in zip(s.SYMBOLS, (Decimal(2), Decimal(3), Decimal(5)), strict=True):
        scaled[symbol] = tuple(replace(row, adj_open=row.adj_open * factor,
                                     adj_high=row.adj_high * factor,
                                     adj_low=row.adj_low * factor, adj_close=row.adj_close * factor)
                              for row in sample.rows[symbol])
    result = evaluate(sample, rows=scaled)
    for left, right in zip(original["cells"], result["cells"], strict=True):
        for metric in ("final_nav", "utility", "fees_initial_nav", "turnover_initial_nav"):
            assert abs(Decimal(left[metric]) - Decimal(right[metric])) < Decimal("1e-40")


def winning_cells(sample):
    result = evaluate(sample)
    cells = result["cells"]
    for cell in cells:
        cell["final_nav"], cell["utility"] = (
            ("2", "1") if cell["policy"] == "yield_curve" else ("1", "0"))
    return cells


def test_strongest_kill_needs_both_unrounded_metrics_and_all_controls(sample):
    cells = winning_cells(sample)
    assert s.primary_kill(cells) == "development_survivor_non_promoting"
    for period in (p[0] for p in s.PERIODS):
        for policy in s.POLICIES[1:]:
            for metric in ("final_nav", "utility"):
                bad = copy.deepcopy(cells)
                row = next(r for r in bad if r["period"] == period and r["policy"] == policy
                           and r["cost_bps"] == "10")
                row[metric] = "1.9999999999" if metric == "final_nav" else "0.9999999999"
                assert s.primary_kill(bad) == "rejected"  # Strict >1e-10, never rounded display.


def test_kill_requires_positive_growth_and_no_missing_cell(sample):
    cells = winning_cells(sample)
    cells[0]["status"] = "input_unavailable"
    assert s.primary_kill(cells) == "input_unavailable"
    cells = winning_cells(sample)
    for row in cells:
        row["final_nav"] = "0.9" if row["policy"] == "yield_curve" else "0.8"
    assert s.primary_kill(cells) == "rejected"
    with pytest.raises(ValueError, match="cell_matrix"):
        s.primary_kill(cells[:-1])


def test_timeout_and_failure_are_categorical(sample):
    with pytest.raises(ValueError, match="hard_timeout"):
        s.evaluate(sample.rows, sample.snapshot, sample.contract, sample.pin, deadline=0)
    result = s.failure(sample.pin, "source_input", "private raw body 999")
    assert result["reason_code"] == "runtime_or_source_fault"
    assert "private" not in s.encode(result).decode()
    s.validate_result(result, sample.contract, sample.pin)


def load_runner():
    return runpy.run_path(str(s.REPO / "scripts/run_board_yield_curve_monthly_policy.py"))


def test_cli_static_and_synthetic_never_load_source(capsys):
    main = load_runner()["main"]
    assert main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "static_plan"
    assert main(["--smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["actual_source_reads"] == 0


@pytest.mark.parametrize("args", [
    ["--run"], ["--verify", "--contract-sha256", "sha256:" + "a" * 64],
    ["--plan", "--result-sha256", "a"],
])
def test_cli_requires_exact_pins(args):
    with pytest.raises(SystemExit):
        load_runner()["main"](args)


def prepare_lifecycle(tmp_path, sample, monkeypatch):
    root = tmp_path / "artifacts"
    output = root / "research" / s.NAME
    output.mkdir(parents=True)
    s.atomic_new(output / "precommit.json", sample.contract)
    monkeypatch.setattr(s, "check_metadata", lambda *_: None)
    monkeypatch.setattr(s, "register_contract", lambda *_: None)
    monkeypatch.setattr(s.base, "load_adjusted", lambda *_: sample.rows)
    monkeypatch.setattr(board, "read_federal_reserve_h15_snapshot", lambda *_: sample.snapshot)
    module = load_runner()
    runner = module["dispatch"]
    def inline(target, arguments, *, seconds):
        assert 0 < seconds <= 120
        target(*arguments)
        return dict(timed_out=False, exit_code=0)
    runner.__globals__["supervise"] = inline
    return root, output, runner


def test_registry_failure_recovery_idempotent_and_bytes_immutable(tmp_path, sample, monkeypatch):
    root, output, runner = prepare_lifecycle(tmp_path, sample, monkeypatch)
    def failure(**_):
        raise OSError("append failure")
    monkeypatch.setattr(s, "register_campaign_outcome", failure)
    with pytest.raises(OSError, match="append failure"):
        runner(root, tmp_path / "market", sample.pin)
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    result_pin = s.digest(original["summary.json"])
    appends = {}
    def append(**kwargs):
        key = (kwargs["contract_hash"], kwargs["outcome_reference_sha256"])
        appends.setdefault(key, SimpleNamespace(record_sha256="sha256:" + "a" * 64))
        return appends[key]
    monkeypatch.setattr(s, "register_campaign_outcome", append)
    for _ in range(2):
        restored = s.recover_registry(root, tmp_path / "market", sample.pin,
                                      result_sha256=result_pin, deadline=time.monotonic() + 30)
        assert restored["attempt_artifact_writes"] == restored["fits"] == restored["searches"] == 0
    assert len(appends) == 1
    assert {path.name: path.read_bytes() for path in output.iterdir()} == original
    with pytest.raises(ValueError, match="attempt_already_exists"):
        runner(root, tmp_path / "market", sample.pin)


def test_exact_readback_rejects_changed_input_and_wrong_result_pin(tmp_path, sample, monkeypatch):
    root, output, runner = prepare_lifecycle(tmp_path, sample, monkeypatch)
    monkeypatch.setattr(s, "register_campaign_outcome", lambda **_: None)
    safe = runner(root, tmp_path / "market", sample.pin)
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    replayed = s.readback(root, tmp_path / "market", sample.pin,
                         result_sha256=safe["result_sha256"], deadline=time.monotonic() + 30)
    assert replayed["replay"] == "exact" and replayed["writes"] == 0
    assert {path.name: path.read_bytes() for path in output.iterdir()} == original
    with pytest.raises(ValueError, match="result_hash"):
        s.readback(root, tmp_path / "market", sample.pin, result_sha256="sha256:" + "0" * 64,
                   deadline=time.monotonic() + 30)
    monkeypatch.setattr(board, "read_federal_reserve_h15_snapshot",
                        lambda *_: board.H15Snapshot((), ()))
    with pytest.raises(ValueError, match="train_activity_changed"):
        s.readback(root, tmp_path / "market", sample.pin,
                   result_sha256=safe["result_sha256"], deadline=time.monotonic() + 30)


def test_freeze_hashes_only_and_no_replacement(tmp_path, sample, monkeypatch):
    monkeypatch.setattr(s, "check_metadata", lambda *_: None)
    monkeypatch.setattr(s, "register_contract", lambda *_: None)
    root, market = tmp_path / "artifacts", tmp_path / "market"
    pin = s.freeze(root, market)
    assert pin == sample.pin
    with pytest.raises(FileExistsError):
        s.freeze(root, market)
    with pytest.raises(ValueError, match="outside"):
        s.freeze(s.REPO, market)


def test_bounded_readback_has_separate_budget_and_only_ipc(monkeypatch):
    module = load_runner()
    operation = module["bounded_readback"]
    def supervisor(target, arguments, *, seconds):
        assert seconds == 120 and target is s.readback_entry
        arguments[-1].send(dict(status="complete", writes=0, fits=0))
        return dict(timed_out=False, exit_code=0)
    operation.__globals__["supervise"] = supervisor
    result = operation("verify", Path("not-read"), Path("not-read"), "pin", "result-pin")
    assert result == dict(status="complete", writes=0, fits=0)


def test_hard_timeout_preserves_terminal_and_registry_only_recovery(tmp_path, sample, monkeypatch):
    root, output, runner = prepare_lifecycle(tmp_path, sample, monkeypatch)
    runner.__globals__["supervise"] = lambda *_args, **_kwargs: {
        "timed_out": True, "exit_code": -15,
    }
    appends = []
    def append(**kwargs):
        appends.append(kwargs)
        return SimpleNamespace(record_sha256="sha256:" + "a" * 64)
    monkeypatch.setattr(s, "register_campaign_outcome", append)
    safe = runner(root, tmp_path / "market", sample.pin)
    assert safe["status"] == "failed" and safe["reason_code"] == "hard_timeout"
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    recovered = s.recover_registry(root, tmp_path / "market", sample.pin,
                                   result_sha256=safe["result_sha256"],
                                   deadline=time.monotonic() + 30)
    assert recovered["attempt_artifact_writes"] == 0
    assert recovered["replay"] == "failure_binding_only"
    assert all(row == appends[0] for row in appends)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == original


def prepare_failed_bundle(tmp_path, sample, monkeypatch, *, phase, reason, worker=None,
                          start_pin=None):
    root, output, _ = prepare_lifecycle(tmp_path, sample, monkeypatch)
    s.atomic_new(output / "started.json", {
        "contract_sha256": sample.pin if start_pin is None else start_pin,
    })
    result = s.failure(sample.pin, phase, reason)
    if worker is not None:
        s.atomic_new(output / "worker-result.json", result if worker == "matching" else worker)
    if phase == "dispatch":
        result["dispatch_worker_binding"] = s.dispatch_worker_binding(output)
    s.atomic_new(output / "summary.json", result)
    # Failure binding must never parse sources, evaluate paths or create partial results.
    monkeypatch.setattr(s.base, "load_adjusted", forbidden)
    monkeypatch.setattr(board, "read_federal_reserve_h15_snapshot", forbidden)
    monkeypatch.setattr(s, "evaluate", forbidden)
    return root, output, s.digest(s.encode(result))


def test_failure_matching_worker_binding_without_numeric_work(tmp_path, sample, monkeypatch):
    root, output, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="source_input", reason="runtime_or_source_fault",
        worker="matching")
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    read = s.readback(root, tmp_path / "market", sample.pin,
                      result_sha256=result_pin, deadline=time.monotonic() + 30)
    assert read["status"] == "failed" and read["replay"] == "failure_binding_only"
    assert read["fits"] == read["searches"] == read["writes"] == read["cells"] == 0
    appends = []
    def append(**kwargs):
        appends.append(kwargs)
        return SimpleNamespace(record_sha256="sha256:" + "a" * 64)
    monkeypatch.setattr(s, "register_campaign_outcome", append)
    for _ in range(2):
        recovered = s.recover_registry(root, tmp_path / "market", sample.pin,
                                      result_sha256=result_pin, deadline=time.monotonic() + 30)
        assert recovered["replay"] == "failure_binding_only"
        assert (recovered["fits"] == recovered["searches"]
                == recovered["attempt_artifact_writes"] == 0)
    assert appends[0] == appends[1]
    assert appends[0]["outcome_class"] == "non_promoting_failed"
    assert appends[0]["outcome_reference_sha256"] == result_pin
    assert {path.name: path.read_bytes() for path in output.iterdir()} == original


@pytest.mark.parametrize("reason", [
    "hard_timeout", "worker_failed", "worker_result_invalid", "execution_preempted",
])
def test_dispatch_failure_without_worker_is_binding_only(tmp_path, sample, monkeypatch, reason):
    root, output, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="dispatch", reason=reason)
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    read = s.readback(root, tmp_path / "market", sample.pin,
                      result_sha256=result_pin, deadline=time.monotonic() + 30)
    assert read["reason_code"] == reason and read["replay"] == "failure_binding_only"
    assert not (output / "worker-result.json").exists()
    assert {path.name: path.read_bytes() for path in output.iterdir()} == original


def test_failed_worker_mismatch_cannot_readback_or_append(tmp_path, sample, monkeypatch):
    root, _, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="source_input", reason="runtime_or_source_fault",
        worker=s.failure(sample.pin, "evaluate", "hard_timeout"))
    for operation in (s.readback, s.recover_registry):
        with pytest.raises(ValueError, match="worker_summary_binding"):
            operation(root, tmp_path / "market", sample.pin,
                      result_sha256=result_pin, deadline=time.monotonic() + 30)


@pytest.mark.parametrize("phase,reason", [
    ("source_input", "source_hash_mismatch"), ("evaluate", "hard_timeout"),
    ("dispatch", "runtime_or_source_fault"),
])
def test_no_worker_disallows_arbitrary_failure(tmp_path, sample, monkeypatch, phase, reason):
    root, _, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase=phase, reason=reason)
    for operation in (s.readback, s.recover_registry):
        with pytest.raises(ValueError, match="failure_worker_missing"):
            operation(root, tmp_path / "market", sample.pin,
                      result_sha256=result_pin, deadline=time.monotonic() + 30)


def test_failed_binding_keeps_exact_start_and_result_pins(tmp_path, sample, monkeypatch):
    root, _, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="dispatch", reason="hard_timeout")
    with pytest.raises(ValueError, match="result_hash"):
        s.readback(root, tmp_path / "market", sample.pin,
                   result_sha256="sha256:" + "0" * 64, deadline=time.monotonic() + 30)
    second_root, _, second_pin = prepare_failed_bundle(
        tmp_path / "other", sample, monkeypatch, phase="dispatch", reason="hard_timeout",
        start_pin="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="attempt_binding"):
        s.readback(second_root, tmp_path / "market", sample.pin,
                   result_sha256=second_pin, deadline=time.monotonic() + 30)
    assert result_pin == second_pin


@pytest.mark.parametrize("component", ["metadata", "runtime", "contract"])
def test_failure_binding_revalidates_frozen_environment(tmp_path, sample, monkeypatch, component):
    root, _, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="dispatch", reason="hard_timeout")
    if component == "metadata":
        def changed(*_):
            raise ValueError("source_hash_mismatch")
        monkeypatch.setattr(s, "check_metadata", changed)
        expected = "source_hash_mismatch"
    elif component == "runtime":
        monkeypatch.setattr(s, "runtime_identity", lambda: {"python": "other"})
        expected = "contract_changed"
    else:
        sample.contract["config"]["cells"] = 99
        monkeypatch.setattr(s, "configuration", lambda: sample.contract["config"])
        expected = "contract_changed"
    with pytest.raises(ValueError, match=expected):
        s.readback(root, tmp_path / "market", sample.pin,
                   result_sha256=result_pin, deadline=time.monotonic() + 30)


@pytest.mark.parametrize("value", ["sha256:" + "g" * 64, "a" * 64, None, 4])
def test_full_macro_action_hash_must_have_sha256_shape(sample, value):
    result = evaluate(sample)
    result["matching"]["all_macro_targets_sha256"] = value
    with pytest.raises(ValueError, match="action_hash"):
        s.validate_result(result, sample.contract, sample.pin)


@pytest.mark.parametrize("field,value,reason", [
    ("sessions", 0, "cell_sessions"), ("sessions", True, "cell_sessions"),
    ("trades", -1, "cell_trades"), ("trades", 10000, "cell_trades"),
    ("trades", 0.0, "cell_trades"),
    ("daily_path_sha256", "sha256:" + "z" * 64, "cell_path_hash"),
    ("daily_path_sha256", None, "cell_path_hash"),
])
def test_completed_cell_counts_and_path_hash_shape(sample, field, value, reason):
    result = evaluate(sample)
    result["cells"][0][field] = value
    with pytest.raises(ValueError, match=reason):
        s.validate_result(result, sample.contract, sample.pin)


@pytest.mark.parametrize("mode", ["--verify", "--recover-registry"])
def test_cli_accepts_valid_failed_binding_not_numeric_success(capsys, mode):
    main = load_runner()["main"]
    main.__globals__["bounded_readback"] = lambda *_: {
        "status": "failed", "replay": "failure_binding_only", "cells": 0,
    }
    assert main([mode, "--contract-sha256", "sha256:" + "a" * 64,
                 "--result-sha256", "sha256:" + "b" * 64]) == 0
    projected = json.loads(capsys.readouterr().out)
    assert projected["status"] == "failed" and projected["replay"] == "failure_binding_only"


@pytest.mark.parametrize("timed_out,exit_code,reason", [
    (True, 0, "hard_timeout"), (False, 7, "worker_failed"),
])
def test_supervisor_failure_after_worker_write_is_hash_bound(
    tmp_path, sample, monkeypatch, timed_out, exit_code, reason,
):
    root, output, runner = prepare_lifecycle(tmp_path, sample, monkeypatch)
    reaped = []
    original_binding = s.dispatch_worker_binding
    def binding(path):
        assert reaped == [True]
        return original_binding(path)
    def supervisor(target, arguments, *, seconds):
        target(*arguments)  # Synthetic complete worker result exists before supervisor failure.
        reaped.append(True)
        return dict(timed_out=timed_out, exit_code=exit_code)
    runner.__globals__["supervise"] = supervisor
    monkeypatch.setattr(s, "dispatch_worker_binding", binding)
    appends = []
    def append(**kwargs):
        appends.append(kwargs)
        return SimpleNamespace(record_sha256="sha256:" + "a" * 64)
    monkeypatch.setattr(s, "register_campaign_outcome", append)
    projected = runner(root, tmp_path / "market", sample.pin)
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    summary = json.loads(original["summary.json"])
    assert summary["reason_code"] == reason and summary["status"] == "failed"
    assert summary["dispatch_worker_binding"] == {
        "status": "present", "sha256": s.digest(original["worker-result.json"]),
    }
    assert original["summary.json"] != original["worker-result.json"]
    assert json.loads(original["worker-result.json"])["status"] == "complete"
    monkeypatch.setattr(s.base, "load_adjusted", forbidden)
    monkeypatch.setattr(board, "read_federal_reserve_h15_snapshot", forbidden)
    monkeypatch.setattr(s, "evaluate", forbidden)
    for _ in range(2):
        read = s.readback(root, tmp_path / "market", sample.pin,
                          result_sha256=projected["result_sha256"], deadline=time.monotonic() + 30)
        assert read["replay"] == "failure_binding_only" and read["cells"] == 0
        recovery = s.recover_registry(root, tmp_path / "market", sample.pin,
                                      result_sha256=projected["result_sha256"],
                                      deadline=time.monotonic() + 30)
        assert recovery["status"] == "failed" and recovery["attempt_artifact_writes"] == 0
    assert all(item == appends[0] for item in appends)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == original


@pytest.mark.parametrize("payload", [b"{invalid-json", b"\xff", b"{}\n", b" { } \n"])
def test_malformed_worker_is_hash_bound_without_parsing_during_readback(
    tmp_path, sample, monkeypatch, payload,
):
    root, output, runner = prepare_lifecycle(tmp_path, sample, monkeypatch)
    def supervisor(*_args, **_kwargs):
        with (output / "worker-result.json").open("xb") as handle:
            handle.write(payload)
        return dict(timed_out=False, exit_code=0)
    runner.__globals__["supervise"] = supervisor
    monkeypatch.setattr(s, "register_campaign_outcome", lambda **_: None)
    projected = runner(root, tmp_path / "market", sample.pin)
    summary = json.loads((output / "summary.json").read_bytes())
    assert projected["reason_code"] == "worker_result_invalid"
    assert summary["dispatch_worker_binding"] == {"status": "present", "sha256": s.digest(payload)}
    assert "worker_bytes" not in summary and "raw_body" not in summary
    monkeypatch.setattr(s, "evaluate", forbidden)
    read = s.readback(root, tmp_path / "market", sample.pin,
                      result_sha256=projected["result_sha256"], deadline=time.monotonic() + 30)
    assert read["status"] == "failed" and read["replay"] == "failure_binding_only"


@pytest.mark.parametrize("mutation", ["changed", "missing", "added"])
def test_dispatch_binding_rejects_later_worker_mutation_before_registry_append(
    tmp_path, sample, monkeypatch, mutation,
):
    root, output, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="dispatch", reason="hard_timeout",
        worker=None if mutation == "added" else {"status": "unrelated_worker_payload"})
    worker = output / "worker-result.json"
    read = s.readback(root, tmp_path / "market", sample.pin,
                      result_sha256=result_pin, deadline=time.monotonic() + 30)
    assert read["replay"] == "failure_binding_only"
    if mutation == "changed":
        worker.write_bytes(b"changed synthetic worker bytes")
    elif mutation == "missing":
        worker.unlink()
    else:
        s.atomic_new(worker, {"status": "later_added_worker"})
    for operation in (s.readback, s.recover_registry):
        with pytest.raises(ValueError, match="dispatch_worker_changed"):
            operation(root, tmp_path / "market", sample.pin,
                      result_sha256=result_pin, deadline=time.monotonic() + 30)


def test_recovery_rechecks_worker_hash_before_registry_write(tmp_path, sample, monkeypatch):
    root, output, result_pin = prepare_failed_bundle(
        tmp_path, sample, monkeypatch, phase="dispatch", reason="hard_timeout")
    original = s.readback
    def after_readback(*args, **kwargs):
        read = original(*args, **kwargs)
        s.atomic_new(output / "worker-result.json", {"status": "changed_after_reader"})
        return read
    monkeypatch.setattr(s, "readback", after_readback)
    with pytest.raises(ValueError, match="dispatch_worker_changed"):
        s.recover_registry(root, tmp_path / "market", sample.pin,
                           result_sha256=result_pin, deadline=time.monotonic() + 30)


@pytest.mark.parametrize("binding", [
    {"status": "present", "sha256": "sha256:" + "g" * 64},
    {"status": "present", "sha256": None}, {"status": "absent", "sha256": "sha256:" + "a" * 64},
    {"status": "unknown", "sha256": None}, None,
])
def test_dispatch_binding_hash_and_absence_shape(sample, binding):
    result = s.failure(sample.pin, "dispatch", "hard_timeout")
    result["dispatch_worker_binding"] = binding
    with pytest.raises(ValueError, match="dispatch_worker_binding"):
        s.validate_result(result, sample.contract, sample.pin)


def test_dispatch_missing_binding_is_not_inferred_absence(sample):
    result = s.failure(sample.pin, "dispatch", "hard_timeout")
    with pytest.raises(ValueError, match="dispatch_worker_binding"):
        s.validate_result(result, sample.contract, sample.pin)


def test_complete_result_still_requires_exact_worker_summary(tmp_path, sample, monkeypatch):
    root, output, runner = prepare_lifecycle(tmp_path, sample, monkeypatch)
    monkeypatch.setattr(s, "register_campaign_outcome", lambda **_: None)
    projected = runner(root, tmp_path / "market", sample.pin)
    (output / "worker-result.json").write_bytes(b"different worker bytes")
    monkeypatch.setattr(s, "evaluate", forbidden)
    with pytest.raises(ValueError, match="worker_summary_binding"):
        s.readback(root, tmp_path / "market", sample.pin,
                   result_sha256=projected["result_sha256"], deadline=time.monotonic() + 30)
