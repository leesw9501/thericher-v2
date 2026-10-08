"""Source-free causal allocation, continuous accounting and immutable replay proofs."""

from __future__ import annotations

import ast
import csv
import gzip
import io
import json
from dataclasses import replace
from datetime import date
from decimal import ROUND_DOWN, Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import kis_causal_risk_allocation as study

D = Decimal


@pytest.fixture(scope="module")
def plan():
    # Only public calendar dates, never actual market values.
    return study.build_plan()


@pytest.fixture(scope="module")
def rows(plan):
    return {s: tuple(study.base.PriceClose(s, d, "synthetic", D(100))
                     for d in sorted(study.required_past_dates(plan)))
            for s in study.base.INSTRUMENT_ORDER}


@pytest.fixture(scope="module")
def actions(rows, plan):
    return study.prepare_actions(rows, plan, "synthetic")


@pytest.fixture(scope="module")
def days(plan):
    return tuple(study.nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in plan.dates)


@pytest.fixture(scope="module")
def cells(days, actions, plan):
    return study.evaluate(days, actions, plan)


def test_static_parent_interface():
    config = study.configuration()
    assert config["costs_bps_side"] == ["2.5", "5", "10"]
    assert "final CLOSE exit ONLY" in config["accounting"]
    assert config["actual_fits"] == 0 and config["gpu"] is False
    assert study.RUNTIME == {"python": "3.12.14", "pandas-market-calendars": "5.4.0",
                             "numpy": "2.5.1"}
    assert study.CANDIDATES == ("candidate",)
    assert len(study.CODE) == len(set(study.CODE))
    code = (study.REPO / "src/thericher_v2/research/kis_causal_risk_allocation.py").read_text()
    tree = ast.parse(code)
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any("torch" in (m or "") or "safetensors" in (m or "") for m in imports)
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "minimum_variance_weights" in calls and "_population_covariance" in calls
    assert not calls & {"fit", "forecast", "getenv", "load_dotenv", "post"}


def test_exact_calendar_and_early_close(plan):
    record = plan.record()
    assert len(record["entries"]) == 33 and len(plan.dates) == 689 and plan.block_cut == 252
    first, last = record["entries"][0], record["entries"][-1]
    assert first["history_dates"][0] == "2022-12-28"
    assert first["history_dates"][-1] == "2023-12-29"
    assert last["history_dates"][0] == "2025-08-28"
    assert last["history_dates"][-1] == "2026-08-31"
    assert all(len(e["history_dates"]) == 253 and e["history_dates"][-1] < e["entry_date"]
               for e in record["entries"])
    dec = [e for e in record["entries"] if e["entry_date"][:7] in ("2024-12", "2025-12")]
    assert all(e["decision_at"].endswith("18:00:00+00:00") for e in dec)
    opens = {e["entry_at"][11:16] for e in record["entries"]}
    assert opens == {"13:30", "14:30"}
    assert "sessions=" not in repr(plan)


def test_calendar_gap_and_forged_plan_rejected(plan, rows):
    index = next(i for i, s in enumerate(plan.sessions) if s.session_date == date(2024, 3, 4))
    with pytest.raises(study.base.StudyFault, match="calendar_geometry"):
        study.build_plan(plan.sessions[:index] + plan.sessions[index + 1:])
    with pytest.raises(study.base.StudyFault, match="plan_changed"):
        study.prepare_actions(rows, replace(plan, block_cut=251), "synthetic")


def test_simple_population_covariance_and_price_scale():
    columns = tuple(tuple(D(100 + ((i * (j + 3)) % (11 + j))) for i in range(253))
                    for j in range(3))
    with localcontext(study.base.CONTEXT):
        returns = np.asarray([[(c[i + 1] - c[i]) / c[i] for c in columns]
                              for i in range(252)], dtype=np.float64)
        scaled = tuple(tuple(v * D(j + 2) for v in c) for j, c in enumerate(columns))
    result = study.covariance_from_closes(columns)
    np.testing.assert_allclose(result, np.cov(returns, rowvar=False, ddof=0),
                               rtol=1e-13, atol=1e-17)
    assert result.shape == (3, 3) and np.array_equal(result, result.T)
    assert np.linalg.eigvalsh(result).min() >= -1e-15
    assert np.array_equal(result, study.covariance_from_closes(scaled))
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert np.array_equal(result, study.covariance_from_closes(columns))


@pytest.mark.parametrize("value", [D(0), D(-1), D("NaN"), D("Infinity"), 100])
def test_invalid_required_closes(value):
    columns = ((D(100),) * 252 + (value,), (D(100),) * 253, (D(100),) * 253)
    with pytest.raises(study.base.StudyFault, match="required_price"):
        study.covariance_from_closes(columns)


@pytest.mark.parametrize("symbol", study.base.INSTRUMENT_ORDER)
def test_required_gap_no_older_substitution(rows, plan, symbol):
    changed = dict(rows)
    changed[symbol] = rows[symbol][1:]
    with pytest.raises(study.base.StudyFault, match="required_session_missing"):
        study.prepare_actions(changed, plan, "synthetic")


@pytest.mark.parametrize("kind", ["duplicate", "vintage", "wrong_symbol"])
def test_required_binding_errors(rows, plan, kind):
    changed = dict(rows)
    first = rows["SPY"][0]
    changed["SPY"] = (rows["SPY"] + (first,) if kind == "duplicate" else
                      (replace(first, **({"vintage_ref": "other"} if kind == "vintage" else
                                         {"symbol": "TLT"})),) + rows["SPY"][1:])
    with pytest.raises(study.base.StudyFault, match="required_(session_duplicate|row_binding)"):
        study.prepare_actions(changed, plan, "synthetic")


def test_old_current_future_support_ignored_before_price_access(plan, rows, actions):
    class UnreadPrice:
        def __init__(self, day):
            self.session_date = day

        @property
        def close(self):
            pytest.fail("future price accessed")

    dates = tuple(s.session_date for s in plan.sessions[
        plan.entry_indices[0] - 253:plan.entry_indices[0]])
    before = study._selected_closes(rows, dates, "synthetic")
    changed = {s: tuple(reversed(v)) + (UnreadPrice(date(1900, 1, 1)),
                                      UnreadPrice(plan.dates[0]), UnreadPrice(date(2027, 1, 1)))
               for s, v in reversed(tuple(rows.items()))}
    assert study._selected_closes(changed, dates, "synthetic") == before
    # Current for the final decision and later support never affects any action.
    final = plan.sessions[plan.entry_indices[-1]].session_date
    changed = {s: v + (UnreadPrice(final), UnreadPrice(date(2027, 1, 1)))
               for s, v in rows.items()}
    assert study.prepare_actions(changed, plan, "synthetic") == actions
    assert "close=" not in repr(rows["SPY"][0])


def test_single_shrink_shared_matrix_and_exact_targets(monkeypatch):
    c = np.array([[.0001, .00002, .00001], [.00002, .0002, .00003],
                  [.00001, .00003, .0003]])
    original, calls = study.solver.minimum_variance_weights, []

    def capture(matrix):
        calls.append(matrix.copy())
        return original(matrix)

    monkeypatch.setattr(study.solver, "minimum_variance_weights", capture)
    targets, diagnostics = study.risk_allocations(c)
    assert len(calls) == 1 and np.array_equal(calls[0], c)
    shrunk = .9 * c + .1 * np.diag(np.diag(c))
    for p in study.RISK_POLICIES:
        target = targets[p]
        assert sum(map(Fraction, target.weights3), Fraction(target.cash_weight)) == 1
        assert target.cash_weight >= 0
        attained = np.sqrt(252 * np.asarray(target.weights3, float) @ shrunk @
                           np.asarray(target.weights3, float))
        assert attained == pytest.approx(diagnostics[p]["attained_forecast_volatility"])
        assert attained <= .10 + 1e-15
    assert targets["cash"].cash_weight == 1 and targets["buyhold"].cash_weight == 0


@pytest.mark.parametrize("diagonal,expected", [([0, 0, 0], None), ([0, .001, .002], (1, 0, 0)),
                                              ([0, 0, .002], (.5, .5, 0))])
def test_zero_variance_allocation(diagonal, expected):
    targets, facts = study.risk_allocations(np.diag(diagonal))
    equal = study.solver._normalized((D(1),) * 3)
    assert targets["inverse_volatility"].weights3 == (equal if expected is None else
                                                     tuple(map(D, expected)))
    assert targets["candidate"] == targets["inverse_volatility"]
    assert facts["candidate"]["leverage_cap_binding"] is True
    assert facts["candidate"]["risk_reduced"] is False


def test_same_ceiling_not_equal_attained_risk():
    targets, facts = study.risk_allocations(np.diag([.000001, .000004, .000009]))
    assert all(f["leverage_cap_binding"] for f in facts.values())
    assert len({f["attained_forecast_volatility"] for f in facts.values()}) > 1
    assert all(t.cash_weight == 0 for p, t in targets.items() if p in study.RISK_POLICIES)


def test_exact_residual_under_hostile_decimal():
    weights = study.solver._normalized((D(1), D(2), D(3)))
    exposure = D("0.00000000000000000000000000000000000000000000000001234567890123456789")
    expected = study.scaled_target(weights, exposure)
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.scaled_target(weights, exposure) == expected
    assert sum(map(Fraction, expected.weights3), Fraction(expected.cash_weight)) == 1


def test_actions_33_keys_and_cost_invariance(plan, actions, cells):
    assert [len(actions["actions"][p]) for p in study.POLICIES] == [33, 33, 33, 33, 1]
    assert len(actions["diagnostics"]) == 33
    assert len(cells) == 30 and study.criterion(cells) == {"candidate": "rejected"}
    assert all(c["metrics"]["days"] == (252 if c["block"] == 0 else 437) for c in cells)
    for policy in study.POLICIES:
        for cost in study.COSTS:
            a, b = [c["metrics"] for c in cells if c["policy"] == policy
                    and c["cost_bps"] == str(cost)]
            assert b["entering_nav"] == a["nav"]
            assert b["running_peak_entry"] == a["running_peak_exit"]
            assert a["entries"] == (1 if policy == "buyhold" else 12)
            assert b["entries"] == (0 if policy == "buyhold" else 21)
    assert actions["plan"] == plan.record()


def test_final_only_exit_and_continuous_buyhold(days, plan, actions, cells):
    row = actions["actions"]["buyhold"][0]
    target = study.nav.ThreeAssetTarget(tuple(D(v) for v in row[1:4]), D(row[4]))
    ledger = study.nav.replay(days, {plan.dates[0]: target}, D(10))
    assert all(not d.flat for d in ledger.daily[:-1]) and ledger.daily[-1].flat
    assert all(d.fees == 0 for d in ledger.daily[1:-1])
    assert ledger.daily[plan.block_cut].fees == 0
    metric = next(c["metrics"] for c in cells if c["policy"] == "buyhold" and
                  c["cost_bps"] == "10" and c["block"] == 1)
    assert metric["nav"] == str(ledger.final_nav)
    with localcontext(study.base.CONTEXT):
        ideal = (1 - D(".001")) / (1 + D(".001"))
        assert abs(ledger.final_nav - ideal) < D("1e-45")


def test_forward_mutations_never_revise_actions(days, actions, plan, cells):
    before = study.encode(actions)
    changed = tuple(replace(d, adj_close3=(D(101),) * 3) for d in days)
    assert study.evaluate(changed, actions, plan) != cells
    assert study.encode(actions) == before
    entries = {plan.sessions[i].session_date for i in plan.entry_indices}
    unrelated_open = tuple(replace(d, adj_open3=(D(200),) * 3) if d.date not in entries else d
                           for d in days)
    assert study.evaluate(unrelated_open, actions, plan) == cells


@pytest.mark.parametrize("kind", ["missing", "extra", "reorder"])
def test_forward_mark_gaps_not_cash_or_filter(days, actions, plan, kind):
    changed = (days[:-1] if kind == "missing" else days + (days[-1],)
               if kind == "extra" else days[::-1])
    with pytest.raises(study.base.StudyFault, match="forward_mark_gap"):
        study.evaluate(changed, actions, plan)


def test_annual_log_variance_and_running_peak_carry():
    def daily(day, value, log):
        return study.nav.ThreeAssetDaily(day, D(value), D(0), D(0), D(0), False, D(0), D(log))

    first = (daily(date(2024, 12, 30), "2", ".1"), daily(date(2024, 12, 31), "1.8", "-.1"))
    second = (daily(date(2025, 1, 2), "1.7", ".02"), daily(date(2025, 1, 3), "1.6", "-.02"))
    a, peak = study._metrics(first, D(1), D(1), 1)
    b, peak = study._metrics(second, D("1.8"), peak, 1)
    with localcontext(study.base.CONTEXT):
        assert D(b["annual_log_volatility"]) == (252 * D(".0004")).sqrt()
    assert D(a["maximum_drawdown"]) == D(".1")
    assert D(b["maximum_drawdown"]) == D(".2") and peak == 2
    assert b["running_peak_entry"] == "2"


def test_hostile_context_and_whole_asset_scale(days, actions, plan, cells):
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.evaluate(days, actions, plan) == cells
    scaled = tuple(replace(d, adj_open3=(D(200), D(300), D(400)),
                           adj_close3=(D(200), D(300), D(400))) for d in days)
    result = study.evaluate(scaled, actions, plan)
    with localcontext(study.base.CONTEXT):
        for before, after in zip(cells, result, strict=True):
            for key in ("nav", "growth", "utility", "fees", "traded_notional", "maximum_drawdown"):
                assert abs(D(before["metrics"][key]) - D(after["metrics"][key])) < D("1e-40")


def artificial_cells():
    return [dict(block=b, policy=p, cost_bps=str(c), status="complete", metrics=dict(
        growth="1e-12" if p == "candidate" else "0", utility=".002" if p == "candidate" else "0",
        annual_log_volatility=".15", maximum_drawdown=".25"))
        for b in (0, 1) for p in study.POLICIES for c in study.COSTS]


@pytest.mark.parametrize("key,value,expected", [
    ("growth", "0", "rejected"), ("growth", "1e-12", "development_survivor"),
    ("utility", ".001", "rejected"),
    ("utility", ".00100000000000000000001", "development_survivor"),
    ("annual_log_volatility", ".150000000000001", "rejected"),
    ("maximum_drawdown", ".250000000000001", "rejected")])
def test_exact_original_kill(key, value, expected):
    cells = artificial_cells()
    next(c for c in cells if c["block"] == 1 and c["policy"] == "candidate" and
         c["cost_bps"] == "10")["metrics"][key] = value
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.criterion(cells) == {"candidate": expected}


def test_no_old_wealth_dominance_or_cash_utility_kill():
    cells = artificial_cells()
    for cell in cells:
        if cell["policy"] in ("cash", "buyhold"):
            cell["metrics"]["utility"] = "100"
        if cell["policy"] == "buyhold":
            cell["metrics"]["growth"] = "100"
    assert study.criterion(cells) == {"candidate": "development_survivor"}
    next(c for c in cells if c["block"] == 0 and c["policy"] == "equal_thirds" and
         c["cost_bps"] == "10")["metrics"]["utility"] = ".002"
    assert study.criterion(cells) == {"candidate": "rejected"}


@pytest.mark.parametrize("kind", ["missing", "duplicate", "nan"])
def test_matrix_and_nonfinite_rejected(kind):
    cells = artificial_cells()
    if kind == "missing":
        cells.pop()
    elif kind == "duplicate":
        cells[-1] = cells[0]
    else:
        cells[-1]["metrics"]["utility"] = "NaN"
    with pytest.raises(study.base.StudyFault, match="cell_(matrix|metrics)"):
        study.criterion(cells)


def synthetic_source(plan):
    files = []
    dates = sorted(study.required_past_dates(plan) | frozenset(plan.dates))
    for symbol in study.base.INSTRUMENT_ORDER:
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(study.base.COLUMNS)
        writer.writerows((symbol, study.base.EXCHANGES[symbol], d.isoformat(), "100", "100",
                          "synthetic-private-chunk") for d in dates)
        files.append((symbol, gzip.compress(text.getvalue().encode(), mtime=0)))
    return study.base.SourceInputs(tuple(files), {}, SimpleNamespace(sessions=plan.sessions))


def test_numeric_close_selector_ignores_unused_open_future_support(plan):
    source = synthetic_source(plan)
    before = study.load_past_closes(source, plan)
    files = tuple((s, gzip.compress((gzip.decompress(raw).decode().replace(",100,100,", ",NaN,100,")
        + f"{s},{study.base.EXCHANGES[s]},2027-01-01,NaN,NaN,x\n").encode(), mtime=0))
        for s, raw in source.files)
    changed = replace(source, files=files)
    assert study.load_past_closes(changed, plan) == before
    with pytest.raises(study.base.StudyFault, match="required_price"):
        study.load_marks(changed, plan)


@pytest.fixture
def worker(tmp_path, monkeypatch, plan):
    artifact = tmp_path / "artifacts"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    contract = dict(plan=plan.record())
    study.base.atomic_new(root / "precommit.json", contract)
    pin = study.digest(study.encode(contract))
    source = synthetic_source(plan)
    monkeypatch.setattr(study, "read_contract", lambda *a: (contract, {}))
    monkeypatch.setattr(study.base, "load_committed_source", lambda *a, **k: source)
    return artifact, root, pin


def test_worker_action_seal_precedes_payoff_and_readback_ro(worker, monkeypatch):
    artifact, root, pin = worker
    original = study.load_marks

    def sealed_marks(source, plan):
        assert (root / "actions.json").is_file()
        return original(source, plan)

    monkeypatch.setattr(study, "load_marks", sealed_marks)
    result = study.run(root, artifact / "unused-market", artifact, pin)
    assert result["status"] == "complete" and result["phase"] == "validate"
    assert result["actual_fits"] == result["fit_starts"] == 0 and result["cells"] == 30
    assert result["criterion"] == {"candidate": "rejected"}
    assert "metrics" not in json.dumps(result) and "forecast_volatility" not in json.dumps(result)
    originals = {p.name: p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr(study.base, "atomic_new", lambda *a: pytest.fail("readback wrote"))
    replay = study.verify(root, artifact, artifact, pin, result["result_sha256"])
    assert replay["replay"] == "exact_economic/past_action_binding"
    assert replay["fits"] == replay["inference"] == replay["searches"] == replay["writes"] == 0
    assert originals == {p.name: p.read_bytes() for p in root.iterdir()}
    assert set(json.loads(originals["worker-result.json"])["artifact_sha256"]) == set(
        study.ARTIFACTS)


@pytest.mark.parametrize("phase,code", [("before_seal", "required_session_missing"),
                                       ("after_seal", "forward_mark_gap"),
                                       ("evaluate", "private price body")])
def test_failure_binding_and_no_overwrite(worker, monkeypatch, phase, code):
    artifact, root, pin = worker

    def fail(*a, **kw):
        raise study.base.StudyFault(code)

    monkeypatch.setattr(study, {"before_seal": "load_past_closes", "after_seal": "load_marks",
                               "evaluate": "evaluate"}[phase], fail)
    result = study.run(root, artifact, artifact, pin)
    assert result["cells"] == 0 and result["actual_fits"] == result["fit_starts"] == 0
    assert result["reason"] == ("worker_failed" if phase == "evaluate" else code)
    assert "private price body" not in json.dumps(result)
    originals = {p.name: p.read_bytes() for p in root.iterdir()}
    replay = study.verify(root, artifact, artifact, pin, result["result_sha256"])
    assert replay["replay"] == "failure_binding_only"
    assert originals == {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(study.base.StudyFault, match="attempt_exists"):
        study.run(root, artifact, artifact, pin)


@pytest.mark.parametrize("name", ["started.json", "actions.json", "worker-result.json"])
def test_retained_bytes_mutation_rejected(worker, name):
    artifact, root, pin = worker
    result = study.run(root, artifact, artifact, pin)
    (root / name).write_bytes(b"{}")
    with pytest.raises(study.base.StudyFault, match="artifact_(binding|hash)"):
        study.verify(root, artifact, artifact, pin, result["result_sha256"])


def test_read_contract_exact_code_runtime_input_and_host_archive(tmp_path, monkeypatch, plan):
    artifact, repo = tmp_path / "artifacts", tmp_path / "frozen-source"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    monkeypatch.setattr(study, "REPO", repo)
    code = {}
    for relative in study.CODE:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"source-free synthetic code")
        code[relative] = study.digest(path.read_bytes())
    commitment = dict(calendar_sha256=study.base.CALENDAR_PIN,
                      kind="kis-cross-asset-d1-price-only-input-v1", no_date_fill=True,
                      source_pins={study.CODE[0]: code[study.CODE[0]]})
    path = artifact / study.base.INPUT_RELATIVE
    path.parent.mkdir(parents=True)
    study.base.atomic_new(path, commitment)
    monkeypatch.setattr(study.base, "INPUT_PIN", study.digest(path.read_bytes()))
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    contract = dict(name=study.NAME, config=study.configuration(), runtime=dict(study.RUNTIME),
        source_root=str(repo), source_archive_root="D:/opaque/archive", code_sha256=code,
        input_commitment_sha256=study.base.INPUT_PIN, plan=plan.record())
    study.base.atomic_new(root / "precommit.json", contract)
    pin = study.digest(study.encode(contract))
    assert study.read_contract(root, artifact, pin) == (contract, commitment)
    monkeypatch.setattr(study, "runtime_identity", lambda: {})
    with pytest.raises(study.base.StudyFault, match="runtime_identity"):
        study.read_contract(root, artifact, pin)
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    (repo / study.CODE[-1]).write_bytes(b"changed")
    with pytest.raises(study.base.StudyFault, match="code_changed"):
        study.read_contract(root, artifact, pin)


def test_readback_rejects_rebound_but_forged_actions(worker):
    artifact, root, pin = worker
    result = study.run(root, artifact, artifact, pin)
    actions_path = root / "actions.json"
    actions = json.loads(actions_path.read_bytes())
    actions["actions"]["cash"][0][1] = ".5"
    actions_path.write_bytes(study.encode(actions))
    path = root / "worker-result.json"
    saved = json.loads(path.read_bytes())
    saved["artifact_sha256"]["actions.json"] = study.digest(actions_path.read_bytes())
    path.write_bytes(study.encode(saved))
    assert result["result_sha256"] != study.digest(path.read_bytes())
    with pytest.raises(study.base.StudyFault, match="action_replay"):
        study.verify(root, artifact, artifact, pin, study.digest(path.read_bytes()))


def test_synthetic_smoke_and_cli_no_market_io(monkeypatch, capsys, plan):
    monkeypatch.setattr(study.base, "calendar_sessions", lambda: plan.sessions)
    monkeypatch.setattr(study.base, "_read", lambda *a: pytest.fail("actual source read"))
    result = study.synthetic_smoke()
    assert result["cells"] == 30 and result["monthly_entries"] == 33
    assert result["actual_market_reads"] == result["actual_fits"] == result["fit_starts"] == 0
    monkeypatch.setattr(study, "synthetic_smoke", lambda: result)
    assert study.main(["--phase", "smoke"]) == 0
    assert json.loads(capsys.readouterr().out) == result
    with pytest.raises(SystemExit):
        study.main(["--phase", "run"])
    with pytest.raises(SystemExit):
        study.main(["--phase", "smoke", "--root", "D:/unused"])


def test_no_new_general_platform_or_freeze_entrypoint():
    assert not hasattr(study, "freeze_contract")
    assert not hasattr(study, "register_campaign_outcome")
    assert not hasattr(study, "GpuFileLock")
    assert study.ARTIFACTS == ("started.json", "actions.json")

