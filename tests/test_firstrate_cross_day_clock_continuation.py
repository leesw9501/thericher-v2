from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import firstrate_cross_day_clock_continuation as study


def dates():
    return tuple(date(2022, 1, 1) + timedelta(days=i) for i in range(251))


def row(day=None, *, symbol="QQQ", clock=10, same="11", pooled="9", eligible=True):
    day = day or dates()[20]
    at = datetime.combine(day, time(clock), study.EASTERN).astimezone(UTC)
    return study.ClockDecision(day, symbol, clock, at, at + study.MINUTE,
                               at + 31 * study.MINUTE, eligible,
                               Decimal(same) if eligible else None,
                               Decimal(pooled) if eligible else None)


def activity():
    return study.freeze_train_activity(
        tuple(row(d, symbol=symbol, clock=clock, same="11" if i % 2 else "9")
              for i, d in enumerate(dates()[:160])
              for symbol in study.SYMBOLS for clock in study.CLOCKS), dates())


def test_plan_has_no_io_models_gpu_or_source(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("plan performed IO")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(study, "source_helpers", forbidden)
    assert study.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "plan", "study": study.NAME, "actual_fits": 0,
        "gpu": False, "broker_calls": 0,
    }


def test_contract_has_one_fixed_six_policy_matrix_and_no_fit():
    plan = study.contract({"source": "sha256:" + "a" * 64})
    assert plan["split"] == {"TRAIN": 160, "embargo": 1, "comparison": 90, "halves": [45, 45]}
    assert plan["policies"] == list(study.POLICIES)
    assert plan["matrix"]["cells"] == 54
    assert plan["cost_bps_side"] == ["1", "2.5", "5"]
    assert plan["compute"]["seconds"] == 120
    assert plan["actual_fits"] == 0 and not plan["gpu"] and not plan["paper_input"]
    assert plan["code_sha256"] == {"source": "sha256:" + "a" * 64}


@pytest.mark.parametrize("same,selected", [("-100", False), ("0", False), ("10", False),
                                            ("10.000000000001", True), ("100", True)])
def test_strict_fixed_ten_bps_threshold(same, selected):
    assert study.target_fraction(row(same=same), "same_clock", activity()) == (
        Decimal("0.5") if selected else Decimal(0))


@pytest.mark.parametrize("policy", study.POLICIES)
def test_common_past_unavailability_flattens_every_policy(policy):
    assert study.target_fraction(row(eligible=False), policy, activity()) == 0


def test_pooled_uses_own_feature_not_same_clock():
    assert study.target_fraction(row(same="100", pooled="10"), "pooled", activity()) == 0
    assert study.target_fraction(
        row(same="-100", pooled="11"), "pooled", activity()) == Decimal("0.5")


def test_train_matching_uses_only_eligible_counts_and_not_later_decisions():
    ds = dates()
    training = (row(ds[20], same="11"), row(ds[21], same="9"), row(ds[22], eligible=False))
    original = study.freeze_train_activity(training, ds)
    later = (row(ds[160], same="999"), row(ds[161], same="999"))
    changed = study.freeze_train_activity(training + later, ds)
    assert original == changed
    assert original.counts["same_clock", "QQQ", 10] == (1, 2)
    assert original.fractions["same_clock", "QQQ", 10] == Decimal("0.5")
    assert study.target_fraction(row(), "same_clock_matched", original) == Decimal("0.25")
    assert original.fractions["same_clock", "SPY", 10] is None
    assert study.target_fraction(row(symbol="SPY"), "same_clock_matched", original) is None
    with pytest.raises(TypeError):
        original.fractions["same_clock", "QQQ", 10] = Decimal(1)


def test_no_renormalization_when_other_etf_is_flat():
    state = activity()
    qqq = study.target_fraction(row(), "same_clock", state)
    spy = study.target_fraction(row(symbol="SPY", same="-100"), "same_clock", state)
    assert (qqq, spy, 1 - qqq - spy) == (Decimal("0.5"), Decimal(0), Decimal("0.5"))


def test_activity_and_targets_do_not_depend_on_ambient_decimal_precision():
    rows = (row(dates()[20]), row(dates()[21], same="0"), row(dates()[22], same="0"))
    expected = study.freeze_train_activity(rows, dates())
    with localcontext() as context:
        context.prec = 3
        changed = study.freeze_train_activity(rows, dates())
        value = study.target_fraction(row(), "same_clock_matched", changed)
    assert changed == expected
    assert value == study.target_fraction(row(), "same_clock_matched", expected)


def test_feature_and_activity_values_are_hidden_from_repr():
    decision = row(same="98765", pooled="54321")
    assert "98765" not in repr(decision) and "54321" not in repr(decision)
    assert repr(activity()) == "TrainActivity()"


@pytest.mark.parametrize("edit", [dict(symbol="IWM"), dict(clock=11), dict(eligible=1),
                                  dict(same_clock_bps=Decimal("NaN")),
                                  dict(pooled_bps=None), dict(entry_at=datetime.now(UTC)),
                                  dict(decision_at=datetime(2022, 1, 1))])
def test_invalid_decisions_fail_categorically(edit):
    with pytest.raises(study.ClockFault):
        replace(row(), **edit)


def test_duplicate_decision_key_is_rejected():
    with pytest.raises(study.ClockFault, match="decision_keys"):
        study.freeze_train_activity((row(), row()), dates())


def test_daily_metrics_keep_flat_days_and_global_population_variance():
    marks = (Decimal(1), Decimal("1.1"), Decimal("1.1"), Decimal("1.21"))
    expected = study.daily_metrics(marks, initial_nav=Decimal(1))
    with localcontext() as context:
        context.prec = 50
        growth = Decimal("1.1").ln()
        assert expected["utility"] == 252 * (growth / 2 - 5 * growth**2 / 4)
    assert expected["net_growth"] == Decimal("0.21")
    assert study.daily_metrics((Decimal(1),) * 45, initial_nav=Decimal(1)) == {
        "net_growth": Decimal(0), "utility": Decimal(0)}


def metrics():
    return {(policy, "5", half): {
                "net_growth": Decimal("0.1") if policy == "same_clock" else Decimal(0),
                "utility": Decimal("0.2") if policy == "same_clock" else Decimal(0),
                "trades": 10 if policy == "same_clock" else 0}
            for half in ("first45", "last45")
            for policy in ("same_clock", "cash", "pooled", "same_clock_matched")}


def test_kill_requires_both_halves_and_all_predeclared_controls():
    assert study.primary_kill(metrics()) == "development_criterion_met"
    for half in ("first45", "last45"):
        for policy in ("cash", "pooled", "same_clock_matched"):
            changed = metrics()
            changed[policy, "5", half]["utility"] = Decimal("0.2")
            assert study.primary_kill(changed) == "rejected"


@pytest.mark.parametrize("field,value", [("net_growth", Decimal(0)), ("trades", 0),
                                         ("utility", Decimal("1e-11"))])
def test_zero_activity_nonpositive_growth_or_tiny_increment_fails(field, value):
    changed = metrics()
    changed["same_clock", "5", "last45"][field] = value
    assert study.primary_kill(changed) == "rejected"


def test_missing_primary_input_is_not_zero_pnl_or_a_success():
    changed = metrics()
    del changed["pooled", "5", "last45"]
    assert study.primary_kill(changed) == "input_unavailable"


def test_better_other_cost_cannot_rescue_primary():
    changed = metrics()
    changed["same_clock", "5", "last45"]["net_growth"] = Decimal("-0.1")
    changed["same_clock", "1", "last45"] = {
        "net_growth": Decimal(100), "utility": Decimal(100), "trades": 100}
    assert study.primary_kill(changed) == "rejected"


def test_write_once_never_overwrites_an_immutable_record(tmp_path):
    path = tmp_path / "contract.json"
    study.write_once(path, {"status": "frozen"})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        study.write_once(path, {"status": "replacement"})
    assert path.read_bytes() == original


def source_cases(*, early=None):
    eastern = ZoneInfo("America/New_York")
    sessions, grouped = [], {symbol: {} for symbol in study.SYMBOLS}
    for index, day in enumerate(dates()):
        opened = datetime.combine(day, time(9, 30), eastern).astimezone(UTC)
        closed = datetime.combine(day, time(13 if index == early else 16), eastern).astimezone(UTC)
        sessions.append(SessionWindow(opened, closed))
        for symbol in study.SYMBOLS:
            bars = []
            for clock in study.CLOCKS:
                at = datetime.combine(day, time(clock), eastern).astimezone(UTC)
                for offset in (1, 31):
                    if at + (offset + 1) * study.MINUTE > closed:
                        continue
                    price = Decimal(100) + (Decimal(".2") if offset == 31 else Decimal(0))
                    bars.append(Bar(symbol=symbol, market="US", timeframe=Timeframe.M1,
                                    start_ts=at + offset * study.MINUTE, open=price, high=price,
                                    low=price, close=price, volume=Decimal(1), complete=True))
            grouped[symbol][day] = tuple(bars)
    return tuple(sessions), grouped


def test_adapter_uses_exact_prior_dates_and_common_three_clock_input():
    sessions, grouped = source_cases()
    rows, missing = study.prepare_decisions(sessions, grouped)
    assert len(rows) == 251 * 6
    assert missing == {"history_boundary_shortfall": 20 * 6}
    assert all(not r.eligible for r in rows if r.session_date < dates()[20])
    assert all(r.eligible and r.same_clock_bps == 20 and r.pooled_bps == 20
               for r in rows if r.session_date >= dates()[20])
    assert all(r.entry_at == r.decision_at + study.MINUTE
               and r.exit_at == r.entry_at + 30 * study.MINUTE for r in rows)


@pytest.mark.parametrize("mutation", ["remove", "incomplete", "price", "unrelated_past_missing"])
def test_current_future_support_values_and_whole_session_mask_do_not_change_input(mutation):
    sessions, grouped = source_cases()
    original, _ = study.prepare_decisions(sessions, grouped)
    today = dates()[161]
    edited = {symbol: {} for symbol in study.SYMBOLS}
    for symbol in study.SYMBOLS:
        for day, bars in grouped[symbol].items():
            edited[symbol][day] = (
                () if mutation == "remove" and day >= today else
                tuple(replace(b, complete=False) for b in bars)
                if mutation == "incomplete" and day >= today else
                tuple(replace(b, open=b.open * 100, high=b.high * 100,
                              low=b.low * 100, close=b.close * 100) for b in bars)
                if mutation == "price" and day >= today else bars)
    changed, _ = study.prepare_decisions(sessions, edited)
    assert tuple(r for r in original if r.session_date <= today) == tuple(
        r for r in changed if r.session_date <= today)
    assert study.freeze_train_activity(original, dates()) == study.freeze_train_activity(
        changed, dates())


def test_one_required_past_clock_gap_is_scoped_and_not_replaced_by_older_date():
    sessions, grouped = source_cases()
    gap = dates()[150]
    grouped["QQQ"][gap] = grouped["QQQ"][gap][1:]
    rows, missing = study.prepare_decisions(sessions, grouped)
    today = [r for r in rows if r.session_date == dates()[161]]
    assert all(not r.eligible for r in today if r.symbol == "QQQ")
    assert all(r.eligible for r in today if r.symbol == "SPY")
    assert missing["required_endpoint_missing"] == 20 * 3


def test_early_close_excludes_current_clock_and_preserves_exact_prior_geometry_shortfall():
    sessions, grouped = source_cases(early=100)
    rows, missing = study.prepare_decisions(sessions, grouped)
    assert all(r.clock != 14 for r in rows if r.session_date == dates()[100])
    assert all(not r.eligible for r in rows if dates()[101] <= r.session_date <= dates()[120])
    assert all(r.eligible for r in rows if r.session_date == dates()[121])
    assert missing["required_clock_geometry_unsupported"] == 20 * 6


def test_mark_shortfall_does_not_rewrite_decisions_or_activity():
    sessions, grouped = source_cases()
    decisions, _ = study.prepare_decisions(sessions, grouped)
    state = study.freeze_train_activity(decisions, dates())
    original_hash = study.decision_commitment(decisions, state)
    grouped["QQQ"][dates()[161]] = grouped["QQQ"][dates()[161]][1:]
    _, missing = study.opportunities(decisions, grouped, dates()[161:])
    assert missing == {"required_forward_endpoint": 1}
    assert study.decision_commitment(decisions, state) == original_hash


def test_six_policy_three_cost_replay_carries_one_shared_account_and_keeps_flat_days():
    sessions, grouped = source_cases()
    decisions, _ = study.prepare_decisions(sessions, grouped)
    state = study.freeze_train_activity(decisions, dates())
    ops, missing = study.opportunities(decisions, grouped, dates()[161:])
    assert not missing
    metrics, paths = study.evaluate(decisions, state, ops[:3], dates()[161:])
    assert len(metrics) == 54 and len(paths) == 18
    assert study.primary_kill(metrics) == "rejected"
    for (policy, _, half), value in metrics.items():
        assert value["daily_count"] == (90 if half == "continuous90" else 45)
        if half == "last45" or policy == "cash":
            assert value["net_growth"] == 0 and value["trades"] == 0
        assert abs(sum(flow["net_pnl"] for flow in value["asset_cashflow"].values())
                   - value["net_growth"]) <= study.TOL


def test_missing_train_matching_denominator_cannot_become_zero_matched_control():
    sessions, grouped = source_cases()
    decisions, _ = study.prepare_decisions(sessions, grouped)
    state = study.freeze_train_activity((), dates())
    ops, _ = study.opportunities(decisions, grouped, dates()[161:])
    metrics, _ = study.evaluate(decisions, state, ops[:1], dates()[161:])
    assert len(metrics) == 36
    assert study.primary_kill(metrics) == "input_unavailable"


def test_freeze_flushes_contract_before_registry_and_never_loads_values(tmp_path, monkeypatch):
    root = tmp_path / "study"
    seen = []
    monkeypatch.setattr(study, "file_hash", lambda path: "sha256:" + "a" * 64)
    monkeypatch.setattr(study, "check_pins", lambda *args: seen.append("pins"))

    def register(plan, actual_root, base):
        assert actual_root == root
        assert root.joinpath("contract.json").read_bytes() == study.encode(plan) + b"\n"
        seen.append("registered")

    monkeypatch.setattr(study, "register", register)
    first = study.freeze(root, None, None, None, tmp_path)
    original = root.joinpath("contract.json").read_bytes()
    second = study.freeze(root, None, None, None, tmp_path)
    assert first == second and root.joinpath("contract.json").read_bytes() == original
    assert seen == ["pins", "registered", "pins", "registered"]


def test_synthetic_smoke_has_no_actual_source_registry_or_gpu(monkeypatch, capsys):
    monkeypatch.setattr(study, "source_helpers", lambda: pytest.fail("actual source"))
    monkeypatch.setattr(study, "register", lambda *a: pytest.fail("registry"))
    assert study.main(["smoke"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "synthetic_cpu_smoke_passed", "synthetic_cells": 54,
        "actual_fits": 0, "actual_source_reads": 0, "registry_writes": 0, "gpu": False,
    }


def synthetic_cli(tmp_path, monkeypatch):
    root = tmp_path / "study"
    root.mkdir()
    study.write_once(root / "contract.json", study.contract({}))
    pin = study.file_hash(root / "contract.json")
    monkeypatch.setattr(study, "check_scope", lambda *a: None)
    monkeypatch.setattr(study, "check_pins", lambda *a: None)
    monkeypatch.setattr(study, "register", lambda *a: None)
    args = ["--artifact-root", str(root), "--artifact-base", str(tmp_path / "artifacts"),
            "--market-root", str(tmp_path / "market"), "--lineage", str(tmp_path / "lineage"),
            "--normalization", str(tmp_path / "normalization"), "--contract-sha256", pin]

    def compute(*a, seal, phase, **kwargs):
        phase("evaluate")
        seal({"actions_sha256": "sha256:" + "a" * 64})
        return {"status": "non_promoting_completed", "classification": "rejected",
                "cells": 54, "actual_fits": 0, "gpu": False}

    monkeypatch.setattr(study, "compute", compute)
    return root, args


def test_all_ro_verify_preserves_all_attempt_artifact_bytes(tmp_path, monkeypatch, capsys):
    root, args = synthetic_cli(tmp_path, monkeypatch)
    monkeypatch.setattr(study, "append_outcome", lambda *a: None)
    assert study.main(["run", *args]) == 0
    capsys.readouterr()
    snapshot = {p.name: p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr(study, "write_once", lambda *a: pytest.fail("verification write"))
    monkeypatch.setattr(study, "append_outcome", lambda *a: pytest.fail("verification registry"))
    result_pin = study.file_hash(root / "result.json")
    assert study.main(["verify", *args, "--result-sha256", result_pin]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified_all_ro"
    assert {p.name: p.read_bytes() for p in root.iterdir()} == snapshot


def test_post_result_registry_failure_recovers_idempotently_without_artifact_rewrite(
    tmp_path, monkeypatch, capsys,
):
    root, args = synthetic_cli(tmp_path, monkeypatch)

    def append_failure(*args):
        raise RuntimeError("synthetic private exception text")

    monkeypatch.setattr(study, "append_outcome", append_failure)
    assert study.main(["run", *args]) == 1
    output = capsys.readouterr().out
    assert "synthetic private exception text" not in output
    assert json.loads(output)["phase"] == "registry"
    result = json.loads(root.joinpath("result.json").read_bytes())
    assert result["status"] == "non_promoting_completed"
    snapshot = {p.name: p.read_bytes() for p in root.iterdir()}
    result_pin = study.file_hash(root / "result.json")
    appended = set()

    def recovered(actual_root, base, contract_pin, result):
        assert actual_root == root and result["classification"] == "rejected"
        appended.add((contract_pin, study.file_hash(root / "result.json")))

    monkeypatch.setattr(study, "append_outcome", recovered)
    monkeypatch.setattr(study, "write_once", lambda *a: pytest.fail("recovery rewrote artifact"))
    for _ in range(2):
        assert study.main(["recover-registry", *args, "--result-sha256", result_pin]) == 0
        assert {p.name: p.read_bytes() for p in root.iterdir()} == snapshot
    assert len(appended) == 1


def test_owned_exception_publishes_immutable_categorical_failed_terminal(
    tmp_path, monkeypatch, capsys,
):
    root, args = synthetic_cli(tmp_path, monkeypatch)
    outcomes = []
    monkeypatch.setattr(study, "append_outcome", lambda *a: outcomes.append(a[-1]["status"]))

    def fail(*a, phase, **kwargs):
        phase("source_input")
        raise ValueError("synthetic private source body")

    monkeypatch.setattr(study, "compute", fail)
    assert study.main(["run", *args]) == 1
    assert "synthetic private source body" not in capsys.readouterr().out
    result = json.loads(root.joinpath("result.json").read_bytes())
    assert result["status"] == "non_promoting_failed" and result["phase"] == "source_input"
    assert outcomes == ["non_promoting_failed"]
    original = root.joinpath("result.json").read_bytes()
    result_pin = study.file_hash(root / "result.json")
    monkeypatch.setattr(study, "compute", lambda *a, **k: pytest.fail("failed result rerun"))
    assert study.main(["verify", *args, "--result-sha256", result_pin]) == 0
    assert root.joinpath("result.json").read_bytes() == original


def test_existing_attempt_is_not_rerun_or_overwritten(tmp_path, monkeypatch, capsys):
    root, args = synthetic_cli(tmp_path, monkeypatch)
    study.write_once(root / "attempt.json", {"status": "unknown_owned_attempt"})
    original = root.joinpath("attempt.json").read_bytes()
    monkeypatch.setattr(study, "compute", lambda *a, **k: pytest.fail("second actual evaluation"))
    assert study.main(["run", *args]) == 1
    assert root.joinpath("attempt.json").read_bytes() == original
    assert not root.joinpath("result.json").exists()
    capsys.readouterr()


@pytest.mark.parametrize("reason,expected", [
    (study.ClockFault("compute_stop"), "compute_stop"),
    (ValueError("private raw value"), "runtime_or_source_fault"),
    (study.ClockFault("private raw value"), "runtime_or_source_fault"),
])
def test_failure_reason_is_locally_allowlisted_only(reason, expected):
    result = study.failure_result("evaluate", reason, "sha256:" + "a" * 64)
    assert result["reason"] == expected and "private raw value" not in json.dumps(result)
