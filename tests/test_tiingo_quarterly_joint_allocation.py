"""Synthetic fixed-plan allocation, matching, shared-cash adapter and replay tests."""

import copy
import json
import runpy
import socket
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data import tiingo_adjusted_etf_daily as data
from thericher_v2.research import three_asset_nav as ledger
from thericher_v2.research import tiingo_quarterly_joint_allocation as s


def forbidden(*_args, **_kwargs):
    pytest.fail("source/network/credential access forbidden in synthetic tests")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(s, "load_adjusted", forbidden)
    monkeypatch.setattr(data, "load_verified_adjusted_etf_snapshot", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(s.base, "verify_metadata", lambda *_: None)
    monkeypatch.setattr(
        s, "runtime_identity", lambda: dict(python="3.12.15", numpy="2.5.1", calendar="5.4.0")
    )


def weekdays(start, stop):
    days = []
    while start <= stop:
        if start.weekday() < 5:
            days.append(start)
        start += timedelta(days=1)
    return days


@pytest.fixture
def sample(monkeypatch):
    dates = (
        weekdays(date(2000, 12, 1), date(2002, 4, 4))
        + weekdays(date(2013, 1, 2), date(2013, 4, 4))
        + weekdays(date(2020, 1, 2), date(2020, 4, 6))
    )
    schedule = [
        dict(
            session_date=d.isoformat(),
            open_at=datetime(d.year, d.month, d.day, 14, 30, tzinfo=UTC).isoformat(),
        )
        for d in dates
    ]
    monkeypatch.setattr(s, "calendar_schedule", lambda: schedule)
    rows = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for symbol in s.SYMBOLS:
            stream, price = [], Decimal(100)
            for i, day in enumerate(dates):
                opened = price * (1 + Decimal(i % 7 - 3) / 10000)
                closed = opened * (1 + Decimal(i % 11 - 4) / 1000)
                stream.append(
                    data.AdjustedEtfRow(
                        symbol, day, opened, max(opened, closed), min(opened, closed), closed
                    )
                )
                price = closed
            rows[symbol] = tuple(stream)
    contract = s.proposed_contract()
    return SimpleNamespace(
        rows=rows, contract=contract, pin=s.digest(s.encode(contract)), schedule=schedule
    )


def deadline():
    return time.monotonic() + 30


def evaluate(sample, rows=None, **kwargs):
    return s.evaluate(
        sample.rows if rows is None else rows,
        sample.contract,
        sample.pin,
        deadline=deadline(),
        **kwargs,
    )


def training_spec(sample):
    return sample.contract["plan"]["periods"][0]["decisions"][0]


def test_fixed_contract_rules_lineage_and_30_cells(sample):
    cfg = sample.contract["config"]
    assert cfg["train"] == ["2002-01-01", "2012-12-31"]
    assert cfg["costs_per_side_bps"] == ["2.5", "5", "10"]
    assert cfg["cells"] == 30 and cfg["budget"]["wall_seconds"] == 600
    assert cfg["scope"]["holdout_access"] == "none"
    assert cfg["budget"]["gpu"] is False and cfg["weights_retained"] is False
    assert cfg["prior_families"] == [
        "tiingo-adjusted-monthly-holding-development-v1",
        "firstrate-paired-allocation-development-20261005-v1",
    ]
    assert sample.contract["source"]["raw_sha256"] == dict(data.RAW_SHA256)
    result = evaluate(sample)
    assert result["status"] == "complete" and len(result["cells"]) == 30
    assert result["criterion"] == "rejected"  # Identical assets cannot improve over controls.
    assert result["matching"]["status"] == "matched"
    assert Decimal(result["matching"]["invested_fraction"]) == 1
    assert all(c["status"] == "evaluated" for c in result["cells"])
    assert not {"navs", "returns", "prices", "weights"}.intersection(result)
    safe = s.safe_result(result)
    assert set(safe) == {"status", "criterion", "cells", "contract_sha256", "result_sha256"}
    assert "invested_fraction" not in s.encode(safe).decode()


def test_schedule_no_future_mask_actual_open_and_exact_past_keys(sample):
    plan = sample.contract["plan"]
    for period in plan["periods"]:
        assert len(period["decisions"]) == 2
        for spec in period["decisions"]:
            assert len(spec["scheduled_dates"]) == 253
            assert spec["scheduled_dates"] == plan["days"][spec["index"] - 253 : spec["index"]]
            assert spec["scheduled_dates"][-1] < spec["session_date"]
            assert spec["decision_at"] == sample.schedule[spec["index"]]["open_at"]


@pytest.mark.parametrize("bad", ["order", "open", "fields", "support", "past"])
def test_bad_calendar_rejected_not_repaired(sample, bad):
    schedule = copy.deepcopy(sample.schedule)
    if bad == "order":
        schedule[5], schedule[6] = schedule[6], schedule[5]
    elif bad == "open":
        schedule[0]["open_at"] = "2000-12-01T14:30:00"
    elif bad == "fields":
        schedule[0]["available"] = True
    elif bad == "support":
        schedule = schedule[:-100]
    else:
        schedule = schedule[200:]
    with pytest.raises(ValueError, match="calendar_"):
        s.build_plan(schedule)


@pytest.mark.parametrize(
    "diag,expected",
    [
        ((1, 2, 4), (4 / 7, 2 / 7, 1 / 7)),
        ((1, 1, 1), (1 / 3, 1 / 3, 1 / 3)),
        ((0, 1, 4), (1, 0, 0)),
        ((0, 0, 1), (0.5, 0.5, 0)),
        ((0, 0, 0), (1 / 3, 1 / 3, 1 / 3)),
    ],
)
def test_minvar_diagonal_zero_ties_and_exact_fraction_simplex(diag, expected):
    weights = s.minimum_variance_weights(np.diag(diag))
    assert np.allclose(tuple(map(float, weights)), expected, rtol=0, atol=1e-14)
    assert sum(map(Fraction, weights)) == 1
    assert all(w >= 0 for w in weights)


def test_minvar_fixed_diagonal_shrinkage_changes_correlations_only():
    c = np.array([[1, 0.8, 0.4], [0.8, 3, 0.2], [0.4, 0.2, 2.0]])
    shrunk = 0.9 * c + 0.1 * np.diag(np.diag(c))
    expected = np.linalg.solve(shrunk, np.ones(3))
    expected /= expected.sum()
    actual = tuple(map(float, s.minimum_variance_weights(c)))
    assert np.allclose(actual, expected, rtol=0, atol=1e-14)
    assert np.allclose(
        tuple(map(float, s.minimum_variance_weights(c * 1e-200))), actual, rtol=0, atol=1e-14
    )


def test_minvar_active_boundary_beats_dense_feasible_grid():
    c = np.array([[1, 2.5, 0.2], [2.5, 9, 1], [0.2, 1, 2]])
    w = np.asarray(tuple(map(float, s.minimum_variance_weights(c))))
    shrunk = 0.9 * c + 0.1 * np.diag(np.diag(c))
    score = w @ shrunk @ w
    for a in range(41):
        for b in range(41 - a):
            p = np.array([a, b, 40 - a - b]) / 40
            assert score <= p @ shrunk @ p + 1e-12


@pytest.mark.parametrize(
    "c",
    [
        [[1, 2], [2, 1]],
        [[1, 2, 0], [2, 1, 0], [0, 0, 1]],
        [[1, 0.1, 0], [0.2, 1, 0], [0, 0, 1]],
        [[1, 0, 0], [0, float("nan"), 0], [0, 0, 1]],
        [[-1, 0, 0], [0, 1, 0], [0, 0, 1]],
    ],
)
def test_minvar_invalid_matrix_no_optimizer_fallback(c):
    with pytest.raises(ValueError, match="covariance_"):
        s.minimum_variance_weights(c)


@pytest.mark.parametrize(
    "scores,expected",
    [
        (("1", "2", "3"), ("1", "2", "3")),
        (("3", "1", "1"), ("3", "1.5", "1.5")),
        (("0", "0", "0"), ("2", "2", "2")),
        (("-3", "-2", "-1"), ("1", "2", "3")),
    ],
)
def test_average_tie_ranks_remain_fully_invested_even_negative(scores, expected):
    weights = s.momentum_rank_weights(tuple(map(Decimal, scores)))
    assert weights == s._normalized(tuple(map(Decimal, expected)))
    assert sum(map(Fraction, weights)) == 1


@pytest.mark.parametrize("symbol", s.SYMBOLS)
@pytest.mark.parametrize(
    "mutation",
    [
        "current_price",
        "current_support",
        "future_price",
        "future_support",
        "future_duplicate",
        "mapping_order",
    ],
)
def test_current_future_mutations_do_not_change_allocation_or_availability(
    sample, symbol, mutation
):
    spec = training_spec(sample)
    base = s.quarter_allocation(sample.rows, spec)
    rows = dict(sample.rows)
    cut = date.fromisoformat(spec["session_date"])
    if mutation.endswith("support"):
        rows[symbol] = tuple(
            r
            for r in rows[symbol]
            if r.session_date < cut or (mutation == "current_support" and r.session_date > cut)
        )
    elif mutation == "mapping_order":
        rows = dict(reversed(list(rows.items())))
    elif mutation == "future_duplicate":
        rows[symbol] += (rows[symbol][-1],)
    else:
        rows[symbol] = tuple(
            replace(
                r,
                adj_open=r.adj_open * 100,
                adj_high=r.adj_high * 100,
                adj_low=r.adj_low * 100,
                adj_close=r.adj_close * 100,
            )
            if (
                (r.session_date == cut and mutation == "current_price")
                or (r.session_date > cut and mutation == "future_price")
            )
            else r
            for r in rows[symbol]
        )
    assert s.quarter_allocation(rows, spec) == base
    assert base.safe_facts()["status"] == "ready" and "0." not in repr(base)


@pytest.mark.parametrize("symbol", s.SYMBOLS)
def test_past_gap_unavailable_without_renumbering(sample, symbol):
    spec = training_spec(sample)
    gone = date.fromisoformat(spec["scheduled_dates"][110])
    rows = dict(sample.rows)
    rows[symbol] = tuple(r for r in rows[symbol] if r.session_date != gone)
    with pytest.raises(s.JointPortfolioInputUnavailable, match="required_session_missing"):
        s.quarter_allocation(rows, spec)
    assert sample.contract["plan"] == s.build_plan(sample.schedule)


def test_momentum_excludes_exact_latest_21_returns(sample):
    spec = training_spec(sample)
    rows = dict(sample.rows)
    required = set(map(date.fromisoformat, spec["scheduled_dates"]))
    target = date.fromisoformat(spec["scheduled_dates"][231])
    # Latest 21 closes may change covariance but cannot change the rank score.
    original = s.quarter_allocation(rows, spec)
    rows["QQQ"] = tuple(
        replace(
            r,
            adj_open=r.adj_open * 2,
            adj_high=r.adj_high * 2,
            adj_low=r.adj_low * 2,
            adj_close=r.adj_close * 2,
        )
        if r.session_date in required and r.session_date > target
        else r
        for r in rows["QQQ"]
    )
    assert s.quarter_allocation(rows, spec).momentum == original.momentum
    rows["QQQ"] = tuple(
        replace(
            r,
            adj_open=r.adj_open * 2,
            adj_high=r.adj_high * 2,
            adj_low=r.adj_low * 2,
            adj_close=r.adj_close * 2,
        )
        if r.session_date == target
        else r
        for r in rows["QQQ"]
    )
    assert s.quarter_allocation(rows, spec).momentum[1] > original.momentum[1]


def test_bisection_handles_decreasing_and_nonmonotone_callback():
    for callback in (lambda c: 1 - c, lambda c: c + Decimal(".1") * c * (1 - c)):
        result = s.match_beta(Decimal(".3"), callback)
        assert result.status == "matched" and result.iterations == 64
        assert abs(callback(result.fraction) - Decimal(".3")) <= s.TOL
        assert "fraction" not in result.safe_facts() and "0.3" not in repr(result)


def test_nonendpoint_64_bisections_use_exact_cash_target_after_45dp_search_points():
    points = []

    def basket_beta(c):
        with localcontext() as ctx:
            ctx.prec = 50
            weights = s._scaled_equal_weight(c)
            total = sum(weights, Decimal(0))
            target = ledger.ThreeAssetTarget(weights, 1 - total)
            assert sum(map(Fraction, target.weights3)) + Fraction(target.cash_weight) == 1
            assert total == c.quantize(s.WEIGHT_QUANTUM)
            points.append(c)
            return total

    result = s.match_beta(Decimal(".3"), basket_beta)
    assert result.status == "matched" and result.iterations == 64
    assert len(points) == 67  # Endpoints +64 search probes +final lattice residual.
    with localcontext() as ctx:
        ctx.prec = 50
        assert any(c != c.quantize(s.WEIGHT_QUANTUM) for c in points)
        assert abs(result.fraction - Decimal(".3")) <= s.TOL


def test_nonendpoint_matching_through_actual_synthetic_ledger_and_restored_replay(
    sample, monkeypatch
):
    rows = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for coefficient, symbol in enumerate(s.SYMBOLS, start=1):
            price, stream = Decimal(100), []
            for i, original in enumerate(sample.rows[symbol]):
                closing = price * (1 + Decimal(coefficient) * Decimal(i % 11 - 4) / 10000)
                stream.append(
                    data.AdjustedEtfRow(
                        symbol,
                        original.session_date,
                        price,
                        max(price, closing),
                        min(price, closing),
                        closing,
                    )
                )
                price = closing
            rows[symbol] = tuple(stream)
    result = evaluate(sample, rows)
    matching = result["matching"]
    assert matching["status"] == "matched" and matching["iterations"] == 64
    fraction = Decimal(matching["invested_fraction"])
    assert 0 < fraction < 1
    restored = s.BetaMatch(fraction, "matched", None, 64)
    monkeypatch.setattr(s, "match_beta", forbidden)
    assert s.encode(evaluate(sample, rows, frozen_match=restored)) == s.encode(result)


def test_matching_unbracketed_interior_root_is_not_an_outcome_fallback():
    result = s.match_beta(Decimal(".25"), lambda c: (c - Decimal(".5")) ** 2)
    assert result.fraction == 0  # Endpoint equality is eligible.
    result = s.match_beta(Decimal(".1"), lambda c: (c - Decimal(".5")) ** 2)
    assert result.status == "comparison_unresolved" and result.reason == "beta_not_bracketed"


def test_discontinuous_match_residual_fails_without_clipping():
    result = s.match_beta(Decimal(".5"), lambda c: Decimal(int(c >= Decimal(".3"))))
    assert result.fraction is None and result.reason == "beta_residual_exceeded"
    assert result.residual_probe is not None
    assert result.safe_facts()["residual_probe_sha256"] == s.digest(
        s.encode(str(result.residual_probe))
    )


@pytest.mark.parametrize(
    "fraction", ["0", "1", ".3", ".123456789012345678901234567890123456789012345"]
)
def test_scaled_basket_targets_satisfy_exact_fraction_cash_contract(fraction):
    c = Decimal(fraction)
    weights = s._scaled_equal_weight(c)
    with localcontext() as ctx:
        ctx.prec = 50
        target = ledger.ThreeAssetTarget(weights, 1 - c)
    assert sum(map(Fraction, target.weights3)) + Fraction(target.cash_weight) == 1


@pytest.mark.parametrize(
    "fraction",
    [
        "0.0000000000000142108547152020037174224853515625",
        ".12345678901234567890123456789012345678901234567890",
        "0.99999999999999999999999999999999999999999999999999",
    ],
)
def test_precision_repair_keeps_target_lattice_and_exact_cash_for_deep_probes(fraction):
    c = Decimal(fraction)
    with localcontext() as ctx:
        ctx.prec = 50
        effective = c.quantize(s.WEIGHT_QUANTUM)
        weights = s._scaled_equal_weight(c)
        target = ledger.ThreeAssetTarget(weights, 1 - effective)
        assert sum(map(Fraction, weights)) == Fraction(effective)
        assert sum(map(Fraction, weights)) + Fraction(target.cash_weight) == 1


@pytest.mark.parametrize(
    "value", [Decimal("-.01"), Decimal("1.01"), Decimal("NaN"), Decimal("Infinity"), 0.3]
)
def test_precision_repair_does_not_clip_out_of_domain_fraction(value):
    with pytest.raises(ValueError, match="matched_fraction"):
        s._scaled_equal_weight(value)


def test_beta_identical_aligned_returns_and_flat_reference_failure():
    values = tuple(map(Decimal, (".1", "-.05", ".03")))
    assert s.beta(values, values) == 1
    assert s.beta((Decimal(0),) * 3, values) == 0
    with pytest.raises(ValueError, match="beta_alignment"):
        s.beta(values[:-1], values)
    with pytest.raises(ValueError, match="beta_reference_zero_variance"):
        s.beta(values, (Decimal(0),) * 3)


def test_utility_initial_fee_final_existing_observation_population_variance():
    with localcontext() as ctx:
        ctx.prec = 50
        navs = (Decimal(".99"), Decimal("1.05"), Decimal("1.02"))
        logs = (navs[0].ln(), (navs[1] / navs[0]).ln(), (navs[2] / navs[1]).ln())
        mean = sum(logs) / 3
        expected = 252 * (mean - 5 * sum((v - mean) ** 2 for v in logs) / 3)
        assert abs(s.utility(navs) - expected) < Decimal("1e-48")
        assert abs(sum(logs) - navs[-1].ln()) < Decimal("1e-48")


def test_adapter_shared_cash_reset_bounds_initial_and_final_fees(sample):
    plan = sample.contract["plan"]
    prepared = s.prepare_inputs(sample.rows, plan, deadline=deadline())
    for inputs, period in zip(prepared, plan["periods"], strict=True):
        raw = s.replay_joint(
            inputs.rows,
            plan["days"],
            period["bounds"],
            inputs.actions["equal_weight"],
            "10",
            deadline=deadline(),
        )
        checked = s.checked_path(raw, inputs.facts["sessions"], "10")
        assert checked.fees > 0 and checked.trades <= inputs.facts["quarters"] + 1
        with localcontext() as ctx:
            ctx.prec = 50
            assert abs(checked.fees - checked.turnover / 1000) < s.EPS
            first = period["bounds"][0]
            ratio = (
                inputs.rows["SPY"][plan["days"][first]].adj_close
                / inputs.rows["SPY"][plan["days"][first]].adj_open
            )
            assert abs(checked.navs[0] - ratio / Decimal("1.001")) < s.EPS


def test_unresolved_matching_does_not_suppress_other_comparisons(sample, monkeypatch):
    monkeypatch.setattr(
        s,
        "calibrate",
        lambda *a, **kw: s.BetaMatch(None, "comparison_unresolved", "beta_not_bracketed", 0),
    )
    result = evaluate(sample)
    assert result["status"] == "input_unavailable"
    assert result["criterion"] == "input_unavailable"
    for cell in result["cells"]:
        assert cell["status"] == (
            "input_unavailable" if cell["policy"] == s.POLICIES[-1] else "evaluated"
        )


def test_future_payoff_gap_not_a_past_feature_mask_and_only_affected_fold(sample):
    rows = dict(sample.rows)
    future_day = date(2020, 4, 3)
    rows["QQQ"] = tuple(r for r in rows["QQQ"] if r.session_date != future_day)
    prepared = s.prepare_inputs(rows, sample.contract["plan"], deadline=deadline())
    assert prepared[-1].facts["missing_marks"] == 1
    assert all(q["status"] == "ready" for q in prepared[-1].facts["inputs"])
    result = evaluate(sample, rows)
    assert all(c["status"] == "evaluated" for c in result["cells"] if c["period"] == "2013-2019")
    assert all(
        c["status"] == "input_unavailable" for c in result["cells"] if c["period"] == "2020-2026-07"
    )


def test_before_ledger_any_outcome_full_fixed_coverage_prepared(sample, monkeypatch):
    calls = []
    original = s.prepare_inputs

    def prepare(*args, **kwargs):
        ready = original(*args, **kwargs)
        calls.append(tuple(p.period for p in ready))
        return ready

    monkeypatch.setattr(s, "prepare_inputs", prepare)

    def replay(*args, **kwargs):
        assert calls == [("TRAIN", "2013-2019", "2020-2026-07")]
        return s.replay_joint(*args, **kwargs)

    evaluate(sample, ledger_replay=replay)


@pytest.mark.parametrize("mutate", ["extra", "matrix", "cost_target", "availability", "utility"])
def test_strict_result_projection_rejects_tamper(sample, mutate):
    result = evaluate(sample)
    if mutate == "extra":
        result["raw_price"] = "private"
    elif mutate == "matrix":
        result["coverage"][0]["covariance"] = [[1]]
    elif mutate == "cost_target":
        result["cells"][5]["action_sha256"] = "sha256:" + "0" * 64
    elif mutate == "availability":
        result["coverage"][1]["missing_marks"] = 1
    else:
        result["criterion"] = "supported_with_limits"
    with pytest.raises(ValueError):
        s.validate_result(result, sample.contract, sample.pin)


def result_with_advantage(nav, gain):
    return [
        dict(
            period=p,
            cost_per_side_bps="10",
            policy=policy,
            status="evaluated",
            final_nav=str(Decimal(1) + nav if policy == "blend" else Decimal(1)),
            utility=str(gain if policy == "blend" else Decimal(0)),
        )
        for p, _, _ in s.PERIODS
        for policy in s.POLICIES
    ]


def test_strong_kill_both_periods_nav_and_utility_tol_components():
    assert s.verdict(result_with_advantage(2 * s.TOL, 2 * s.TOL)) == "supported_with_limits"
    assert s.verdict(result_with_advantage(s.TOL, 2 * s.TOL)) == "rejected"
    assert s.verdict(result_with_advantage(2 * s.TOL, s.TOL)) == "rejected"
    cells = result_with_advantage(2 * s.TOL, 2 * s.TOL)
    cells[-3]["utility"] = str(3 * s.TOL)  # Second period minvar beats blend.
    assert s.verdict(cells) == "rejected"


def test_frozen_contract_immutable_no_market_values_before_fsync(sample, tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    calls = []

    def register(**kwargs):
        frozen = root / "research" / s.ARTIFACT_NAME / "precommit.json"
        assert frozen.is_file() and frozen.read_bytes() == s.encode(sample.contract)
        calls.append(kwargs)

    monkeypatch.setattr(s.base, "register_frozen_campaign", register)
    pin = s.freeze(root, tmp_path / "data")
    assert pin == sample.pin and len(calls) == 1
    s.verify(root, tmp_path / "data", pin)
    with pytest.raises(FileExistsError):
        s.freeze(root, tmp_path / "data")
    with pytest.raises(FileExistsError):
        s.atomic_new(root / "research" / s.ARTIFACT_NAME / "precommit.json", {})
    assert calls[0]["holdout_access"] == "none" and calls[0]["trial_family"] == s.NAME


def test_r2_keeps_same_family_budget_and_preserves_failed_v1_directory(
    sample, tmp_path, monkeypatch
):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    original = root / "research" / s.NAME
    original.mkdir(parents=True)
    (original / "summary.json").write_bytes(b'{"status":"failed"}\n')
    (original / "precommit.json").write_bytes(b'{"original":"retained"}\n')
    before = snapshot_files(original)
    entries = []
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **kw: entries.append(kw))
    pin = s.freeze(root, market)
    output, contract = s.verify(root, market, pin)
    assert output == root / "research" / (s.NAME + "-r2")
    assert snapshot_files(original) == before
    assert entries[0]["trial_family"] == s.NAME
    repair = contract["config"]["technical_repair"]
    assert repair["artifact_name"] == s.ARTIFACT_NAME and not repair["fresh_budget"]
    assert repair["family_wall_seconds"] == contract["config"]["budget"]["wall_seconds"] == 600
    assert repair["attempt_wall_seconds"] == s.SECONDS == 570
    assert Decimal(repair["prior_recorded_seconds"]) + s.SECONDS <= s.FAMILY_SECONDS
    assert contract["config"]["costs_per_side_bps"] == ["2.5", "5", "10"]
    assert not repair["comparison_outcomes_observed"]


def test_verify_readonly_missing_directory_is_not_created(sample, tmp_path):
    root = tmp_path / "absent"
    with pytest.raises(ValueError, match="artifact_missing"):
        s.verify(root, tmp_path / "data", sample.pin)
    assert not root.exists()


def test_repo_artifact_root_rejected_without_writes(sample):
    with pytest.raises(ValueError, match="outside"):
        s._output(s.REPO)


def test_immutable_worker_and_readback_skip_matching_search(sample, tmp_path, monkeypatch):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **_: None)
    pin = s.freeze(root, market)
    output = root / "research" / s.ARTIFACT_NAME
    s.atomic_new(output / "started.json", dict(contract_sha256=pin))
    monkeypatch.setattr(s, "load_adjusted", lambda *_: sample.rows)
    s.run_worker(root, market, pin, output / "worker-result.json", deadline())
    result = json.loads((output / "worker-result.json").read_bytes())
    assert result["status"] == "complete"
    s.atomic_new(output / "summary.json", result)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    monkeypatch.setattr(s, "match_beta", forbidden)
    monkeypatch.setattr(s, "atomic_new", forbidden)
    replayed = s.readback(
        root, market, pin, result_sha256=s.digest(s.encode(result)), deadline=deadline()
    )
    assert replayed["replay"] == "exact" and replayed["refits"] == replayed["writes"] == 0
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()} == before
    with pytest.raises(ValueError, match="worker_path"):
        s.run_worker(root, market, pin, output / "worker-result.json", deadline())
    with pytest.raises(ValueError, match="result_hash"):
        s.readback(root, market, pin, result_sha256="sha256:" + "0" * 64, deadline=deadline())


def launcher():
    return runpy.run_path(str(s.REPO / "scripts/run_tiingo_quarterly_joint_allocation.py"))


def test_default_cli_static_no_file_source_calendar_registry_or_signal(monkeypatch, capsys):
    cli = launcher()
    monkeypatch.setattr(s, "freeze", forbidden)
    monkeypatch.setattr(s, "calendar_schedule", forbidden)
    monkeypatch.setattr(s, "proposed_contract", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert cli["main"]([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "static_plan"


@pytest.mark.parametrize(
    "args",
    [
        ["--run"],
        ["--verify"],
        ["--freeze", "--contract-sha256", "x"],
        ["--plan", "--result-sha256", "x"],
        ["--verify", "--contract-sha256", "x"],
        ["--recover-registry"],
        ["--recover-registry", "--contract-sha256", "x"],
        ["--recover-registry", "--result-sha256", "x"],
        ["--run", "--contract-sha256", "x", "--result-sha256", "y"],
    ],
)
def test_cli_requires_exact_contract_and_result_identity(args):
    with pytest.raises(SystemExit) as exc:
        launcher()["main"](args)
    assert exc.value.code == 2


def test_cli_failure_suppresses_exception_body(monkeypatch, capsys):
    def fail(*args):
        raise ValueError("private-provider-value")

    monkeypatch.setattr(s, "freeze", fail)
    assert launcher()["main"](["--freeze"]) == 1
    assert "private-provider-value" not in capsys.readouterr().out


@pytest.mark.parametrize("job_status", ["complete", "timeout", "bad_result", "crashed"])
def test_runner_single_owned_attempt_budget_and_registry(sample, tmp_path, monkeypatch, job_status):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **_: None)
    pin = s.freeze(root, market)
    output = root / "research" / s.ARTIFACT_NAME
    cli = launcher()
    outcomes = []
    cli["dispatch"].__globals__["register_campaign_outcome"] = lambda **kw: outcomes.append(kw)

    def supervise(target, args, *, seconds):
        assert 0 < seconds <= 600
        assert target is s.worker_entry
        assert args[:3] == (root, market, pin)
        assert json.loads((output / "started.json").read_bytes()) == {"contract_sha256": pin}
        if job_status == "timeout":
            return {"timed_out": True, "exit_code": None}
        if job_status == "crashed":
            return {"timed_out": False, "exit_code": 1}
        result = evaluate(sample)
        if job_status == "bad_result":
            result["cells"][0]["raw_price"] = "forbidden"
        s.atomic_new(args[3], result)
        return {"timed_out": False, "exit_code": 0}

    cli["dispatch"].__globals__["supervise"] = supervise
    result = cli["dispatch"](root, market, pin)
    assert len(outcomes) == 1
    assert result["status"] == ("complete" if job_status == "complete" else "failed")
    assert outcomes[0]["outcome_reference_sha256"] == result["result_sha256"]
    assert set(result) == {"status", "criterion", "cells", "contract_sha256", "result_sha256"}
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(ValueError, match="attempt_already_exists"):
        cli["dispatch"](root, market, pin)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_numeric_classes_and_rules_ignore_ambient_decimal_context(sample):
    reference = s.quarter_allocation(sample.rows, training_spec(sample))
    navs = tuple(map(Decimal, (".99", "1.02", "1.01")))
    score = s.utility(navs)
    with localcontext() as ctx:
        ctx.prec = 6
        assert s.quarter_allocation(sample.rows, training_spec(sample)) == reference
        assert s.utility(navs) == score
        assert sum(map(Fraction, s._scaled_equal_weight(Decimal(".3")))) == Fraction(3, 10)
        assert ctx.prec == 6


@pytest.mark.parametrize("bad", ["returns", "fee", "final", "count"])
def test_adapter_numeric_path_contract_is_independently_checked(sample, bad):
    plan = sample.contract["plan"]
    inputs = s.prepare_inputs(sample.rows, plan, deadline=deadline())[0]
    bounds = plan["periods"][0]["bounds"]
    raw = s.replay_joint(
        inputs.rows, plan["days"], bounds, inputs.actions["equal_weight"], "10", deadline=deadline()
    )
    if bad == "returns":
        raw["returns"] = (Decimal(".123"), *raw["returns"][1:])
    elif bad == "fee":
        raw["fees_initial_nav"] += Decimal(".001")
    elif bad == "final":
        raw["final_nav"] += Decimal(".001")
    else:
        raw["navs"] = raw["navs"][:-1]
    with pytest.raises(ValueError, match="ledger_"):
        s.checked_path(raw, inputs.facts["sessions"], "10")


def test_worker_checks_exact_start_binding_before_value_loader(sample, tmp_path, monkeypatch):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **_: None)
    pin = s.freeze(root, market)
    output = root / "research" / s.ARTIFACT_NAME
    s.atomic_new(output / "started.json", {"contract_sha256": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="attempt_binding"):
        s.run_worker(root, market, pin, output / "worker-result.json", deadline())
    assert not (output / "worker-result.json").exists()


def test_deadline_prevents_ready_input_work_without_wait(sample):
    with pytest.raises(ValueError, match="hard_timeout"):
        s.prepare_inputs(sample.rows, sample.contract["plan"], deadline=0)


def test_parent_bounded_cli_verify_requires_exact_result_pin(monkeypatch, capsys):
    calls = []

    def verify(root, market, pin, *, result_sha256, deadline):
        calls.append((pin, result_sha256, deadline))
        return {"status": "complete", "replay": "exact", "refits": 0, "writes": 0}

    monkeypatch.setattr(s, "readback", verify)
    assert launcher()["main"](["--verify", "--contract-sha256", "c", "--result-sha256", "r"]) == 0
    assert calls[0][:2] == ("c", "r")
    assert "invested_fraction" not in capsys.readouterr().out


def snapshot_files(root):
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def registry_records(root):
    return [
        json.loads(line) for path in root.glob("*.jsonl") for line in path.read_bytes().splitlines()
    ]


@pytest.fixture
def stranded(sample, tmp_path, monkeypatch):
    """Real synthetic registry, with failure injected after immutable publication."""
    root, market = tmp_path / "artifacts", tmp_path / "market"
    pin = s.freeze(root, market)
    output = root / "research" / s.ARTIFACT_NAME
    cli = launcher()
    monkeypatch.setattr(s, "load_adjusted", lambda *_: sample.rows)

    def supervise(target, args, *, seconds):
        assert target is s.worker_entry and 0 < seconds <= s.SECONDS
        target(*args)
        return {"timed_out": False, "exit_code": 0}

    def append_failure(**_):
        assert (output / "summary.json").is_file()
        assert (output / "worker-result.json").read_bytes() == (
            output / "summary.json"
        ).read_bytes()
        raise RuntimeError("synthetic post-summary append failure")

    cli["dispatch"].__globals__["supervise"] = supervise
    cli["dispatch"].__globals__["register_campaign_outcome"] = append_failure
    with pytest.raises(RuntimeError, match="post-summary"):
        cli["dispatch"](root, market, pin)
    result = json.loads((output / "summary.json").read_bytes())
    assert result["status"] == "complete" and result["matching"]["status"] == "matched"
    registry = root / "_control" / "ledger"
    records = registry_records(registry)
    assert len(records) == 1 and records[0]["record_type"] == "campaign_frozen"
    monkeypatch.setattr(s, "match_beta", forbidden)
    monkeypatch.setattr(s, "worker_entry", forbidden)
    monkeypatch.setattr(s, "atomic_new", forbidden)
    return SimpleNamespace(
        root=root,
        market=market,
        pin=pin,
        output=output,
        registry=registry,
        result_pin=s.digest((output / "summary.json").read_bytes()),
        cli=cli,
    )


def recover(p):
    return s.recover_registry(
        p.root, p.market, p.pin, result_sha256=p.result_pin, deadline=deadline()
    )


def test_post_summary_append_failure_recovers_only_original_outcome_idempotently(stranded):
    p = stranded
    attempt_before = snapshot_files(p.output)
    frozen_before = snapshot_files(p.registry)
    with pytest.raises(ValueError, match="attempt_already_exists"):
        p.cli["dispatch"](p.root, p.market, p.pin)
    first = recover(p)
    assert first["recovery"] == "registry_only" and first["replay"] == "exact"
    assert first["refits"] == first["attempt_artifact_writes"] == 0
    assert first["contract_sha256"] == p.pin and first["result_sha256"] == p.result_pin
    assert snapshot_files(p.output) == attempt_before
    assert all(
        snapshot_files(p.registry)[key][0].startswith(value[0])
        for key, value in frozen_before.items()
    )
    records = registry_records(p.registry)
    outcomes = [r for r in records if r["record_type"] == "campaign_outcome"]
    assert len(records) == 2 and len(outcomes) == 1
    assert outcomes[0]["campaign_contract_hash"] == p.pin
    assert outcomes[0]["outcome_reference_sha256"] == p.result_pin
    assert outcomes[0]["outcome_class"] == "non_promoting_completed"
    root_before_repeat = snapshot_files(p.root)
    assert recover(p) == first
    assert snapshot_files(p.root) == root_before_repeat


@pytest.mark.parametrize("failure_position", ["before_append", "after_append"])
def test_registry_recovery_append_failure_is_retryable_without_artifact_reset(
    stranded, monkeypatch, failure_position
):
    p = stranded
    original_append = s.register_campaign_outcome
    attempts_before = snapshot_files(p.output)

    def fail(**kwargs):
        if failure_position == "after_append":
            original_append(**kwargs)
        raise RuntimeError("synthetic registry response failure")

    monkeypatch.setattr(s, "register_campaign_outcome", fail)
    with pytest.raises(RuntimeError, match="registry response"):
        recover(p)
    assert snapshot_files(p.output) == attempts_before
    monkeypatch.setattr(s, "register_campaign_outcome", original_append)
    first = recover(p)
    snapshot = snapshot_files(p.root)
    assert recover(p) == first
    assert snapshot_files(p.root) == snapshot
    outcomes = registry_records(p.registry)
    assert sum(r["record_type"] == "campaign_outcome" for r in outcomes) == 1


@pytest.mark.parametrize("fault", ["contract", "result", "worker", "replay"])
def test_registry_recovery_rejects_unbound_or_changed_evidence_before_append(
    stranded, sample, monkeypatch, fault
):
    p = stranded
    contract_pin, result_pin = p.pin, p.result_pin
    if fault == "contract":
        contract_pin = "sha256:" + "0" * 64
    elif fault == "result":
        result_pin = "sha256:" + "0" * 64
    elif fault == "worker":
        (p.output / "worker-result.json").write_bytes(b"{}\n")
    else:
        rows = dict(sample.rows)
        rows["SPY"] = (
            *rows["SPY"][:-1],
            replace(
                rows["SPY"][-1],
                adj_open=rows["SPY"][-1].adj_open * 2,
                adj_high=rows["SPY"][-1].adj_high * 2,
                adj_low=rows["SPY"][-1].adj_low * 2,
                adj_close=rows["SPY"][-1].adj_close * 2,
            ),
        )
        monkeypatch.setattr(s, "load_adjusted", lambda *_: rows)
    before = snapshot_files(p.root)
    monkeypatch.setattr(s, "register_campaign_outcome", forbidden)
    with pytest.raises(ValueError):
        s.recover_registry(
            p.root, p.market, contract_pin, result_sha256=result_pin, deadline=deadline()
        )
    assert snapshot_files(p.root) == before


def test_cli_registry_recovery_routes_exact_pins_without_fresh_dispatch(monkeypatch, capsys):
    calls = []

    def recovery(root, market, pin, *, result_sha256, deadline):
        calls.append((root, market, pin, result_sha256, deadline))
        return dict(
            status="complete", recovery="registry_only", refits=0, attempt_artifact_writes=0
        )

    monkeypatch.setattr(s, "recover_registry", recovery)
    monkeypatch.setattr(s, "readback", forbidden)
    monkeypatch.setattr(s, "freeze", forbidden)
    cli = launcher()
    cli["main"].__globals__["dispatch"] = forbidden
    assert (
        cli["main"](["--recover-registry", "--contract-sha256", "c", "--result-sha256", "r"]) == 0
    )
    assert calls[0][2:4] == ("c", "r")
    assert calls[0][4] > time.monotonic()
    assert json.loads(capsys.readouterr().out)["recovery"] == "registry_only"
