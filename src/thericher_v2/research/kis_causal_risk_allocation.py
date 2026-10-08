"""One parent-frozen, KIS raw-price monthly capped-risk development comparison.

Only the existing offline KIS binder performs source IO. Pure covariance and
simplex arithmetic do not invoke their historical Tiingo loaders. Past selection
is causal by each decision, not physical target-isolated byte IO. Parent owns
source freezing, containment and custody; this worker has no model or GPU path.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np

from thericher_v2.research import joint_portfolio_covariance as covariance
from thericher_v2.research import kis_cross_asset_monthly_momentum as base
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research import tiingo_quarterly_joint_allocation as solver
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable

NAME = "kis-causal-risk-allocation-development-v1"
REPO = Path(__file__).resolve().parents[3]
SECONDS = VERIFY_SECONDS = 120
CANDIDATES = ("candidate",)
RISK_POLICIES = ("candidate", "inverse_volatility", "equal_thirds")
POLICIES = RISK_POLICIES + ("cash", "buyhold")
COSTS = base.COSTS
RUNTIME = dict(base.RUNTIME, numpy="2.5.1")
CODE = tuple(dict.fromkeys(base.CORE + tuple("src/thericher_v2/" + p for p in (
    "research/kis_causal_risk_allocation.py", "research/joint_portfolio_covariance.py",
    "research/tiingo_quarterly_joint_allocation.py", "research/tiingo_month_start_development.py",
    "research/campaign_registry.py", "research/__init__.py", "data/__init__.py",
    "data/tiingo_adjusted_etf_daily.py", "data/tiingo_etf_daily.py", "data/tiingo_eod.py",
    "serialization.py"))))
ARTIFACTS = ("started.json", "actions.json")
PHASES = ("source_input", "prepare", "decision_seal", "forward_input", "evaluate", "validate")
require, encode, digest = base.require, base.encode, base.digest


def configuration():
    return dict(name=NAME, image=base.IMAGE, runtime=dict(RUNTIME),
        symbols=list(base.INSTRUMENT_ORDER), policies=list(POLICIES), cells=30,
        input_commitment_sha256=base.INPUT_PIN, calendar_sha256=base.CALENDAR_PIN,
        dev_views=[["2024-01-02", "2024-12-31"], ["2025-01-02", "2026-09-30"]],
        geometry=dict(monthly_entries=33, valuation_days=689, view_days=[252, 437]),
        covariance="253 scheduled past raw CLOSEs/252 simple returns; Decimal50 ratios "
                   "then float64; existing population Gram covariance, ddof0",
        allocation="existing seven-face simplex solver receives UNSHRUNK covariance; "
                   "solver0.9*C+0.1*diag(C); existing45dp normalization/last-positive residual",
        inverse_volatility="inverse sqrt of same shrunk diagonal; zero diagonal: normalized "
                           "equal weight among zero-variance assets; all-zero equal thirds",
        equal_thirds="existing normalized three ones,45dp/last-positive residual",
        cap="sqrt(252*w'C_shrunk*w); exposure=min(1,.10/vol), zero vol=>1; "
            "same risk ceiling NOT identical attained risk or risk-matched alpha",
        target_numeric="each sleeve multiplied Decimal50 HALF_EVEN; exact residual cash "
                       "at sufficient precision; no leverage/short/outcome normalization",
        cap_diagnostics="forecast volatility before/after scaling; leverage_cap_binding "
                        "iff uncapped exposure>1 (includes zero vol); risk_reduced iff vol>.10",
        timing="33 first scheduled monthly OPENs; immediately prior scheduled CLOSE; "
               "all actions sealed before forward numeric marks; no future-support mask",
        accounting="three_asset_nav.replay; NAV1 once/policy/cost; monthly OPEN rebalance, "
                   "overnight/continuous quantities across views; final CLOSE exit ONLY; "
                   "Decimal50 HALF_EVEN actual-notional fees; cash earns0",
        costs_bps_side=[str(c) for c in COSTS],
        utility="252*(mean daily log-5*population variance)",
        risk="sqrt(252*population daily-log variance); within-view maximum drawdown "
             "against single initial NAV1 running peak carried across both views",
        kill="10bps BOTH views candidate growth>0 and>cash; utility>inverse_volatility "
             "and equal_thirds by>.001; annual logvol<=.15; running-peak drawdown<=.25; "
             "buyhold opportunity-cost reference, not mandatory wealth dominance",
        missing="required past/mark gaps invalidate this study, "
                "no older substitution/date deletion",
        seconds=SECONDS, verify_seconds=VERIFY_SECONDS, cpu=2, memory_bytes=2 * 1024**3,
        network="none", actual_fits=0, gpu=False, holdout_access="none", paper_input=False,
        grade="RAW_PRICE_ONLY_SEEN_SOURCE_DEVELOPMENT",
        sources=["https://www.anderson.ucla.edu/documents/areas/adm/"
                 "Volatility%20Managed%20Portfolios.pdf",
                 "https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00327"],
        limitations=["mechanism inspiration, not paper replication/ETF alpha",
                     "MODP0 opaque; splits/dividends/TR not applied", "chunk vintages differ",
                     "PIT/finality/decision-time availability not observed",
                     "ideal fractional fills",
                     "33 overlapping-context monthly decisions, independence not claimed",
                     "seen DEV; no holdout/deployment/Paper qualification"],
        lineage=["joint-etf-quarterly-allocation-development-v1",
                 "kis-cross-asset-monthly-momentum-development-v1",
                 "kis-cross-asset-daily-risk-development-v1"],
        readback="exact_economic/past_action_binding; zero fit/inference/search/write")


@dataclass(frozen=True, slots=True)
class StudyPlan:
    sessions: tuple = field(repr=False)
    dates: tuple[date, ...]
    entry_indices: tuple[int, ...]
    block_cut: int

    def record(self):
        return dict(valuation_dates=[d.isoformat() for d in self.dates], block_cut=self.block_cut,
            entries=[dict(entry_date=self.sessions[i].session_date.isoformat(),
                entry_at=self.sessions[i].open_at.isoformat(),
                decision_at=self.sessions[i - 1].close_at.isoformat(),
                history_dates=[s.session_date.isoformat() for s in self.sessions[i - 253:i]])
                for i in self.entry_indices])


def build_plan(sessions=None):
    sessions = base.calendar_sessions() if sessions is None else sessions
    require(type(sessions) is tuple and bool(sessions), "calendar_scope")
    for s in sessions:
        require(type(s) is base.CrossAssetSession, "calendar_type")
        s.__post_init__()
    require(all(a.session_date < b.session_date and a.close_at < b.open_at
                for a, b in zip(sessions, sessions[1:], strict=False)), "calendar_order")
    dev = tuple(i for i, s in enumerate(sessions)
                if date(2024, 1, 2) <= s.session_date <= date(2026, 9, 30))
    require(bool(dev) and dev == tuple(range(dev[0], dev[-1] + 1)), "dev_calendar")
    entries = tuple(i for i in dev if (
                    sessions[i].session_date.year, sessions[i].session_date.month)
                    != (sessions[i - 1].session_date.year, sessions[i - 1].session_date.month))
    dates = tuple(sessions[i].session_date for i in dev)
    cut = sum(d.year == 2024 for d in dates)
    require((len(entries), len(dates), cut) == (33, 689, 252)
            and dates[0] == date(2024, 1, 2) and dates[-1] == date(2026, 9, 30)
            and dates[cut - 1] == date(2024, 12, 31) and dates[cut] == date(2025, 1, 2)
            and entries[0] == dev[0] and all(i >= 253 for i in entries), "calendar_geometry")
    return StudyPlan(sessions, dates, entries, cut)


def required_past_dates(plan):
    return frozenset(s.session_date for i in plan.entry_indices for s in plan.sessions[i - 253:i])


def _selected_closes(rows_by_symbol, dates, vintage_ref):
    require(set(rows_by_symbol) == set(base.INSTRUMENT_ORDER), "source_symbols")
    require(type(vintage_ref) is str and bool(vintage_ref.strip()), "source_vintage")
    required, columns = frozenset(dates), []
    for symbol in base.INSTRUMENT_ORDER:
        rows = {}
        for row in rows_by_symbol[symbol]:
            day = getattr(row, "session_date", None)
            if day not in required:
                continue
            require(day not in rows, "required_session_duplicate")
            require(type(row) is base.PriceClose and row.symbol == symbol
                    and row.vintage_ref == vintage_ref, "required_row_binding")
            row.__post_init__()
            rows[day] = row.close
        require(set(rows) == required, "required_session_missing")
        columns.append(tuple(rows[d] for d in dates))
    return tuple(columns)


def covariance_from_closes(columns):
    require(len(columns) == 3 and all(len(c) == 253 for c in columns), "close_geometry")
    require(all(type(v) is Decimal and v.is_finite() and v > 0 for c in columns for v in c),
            "required_price")
    with localcontext(base.CONTEXT):
        values = tuple(tuple((b - a) / a for a, b in zip(c, c[1:], strict=False))
                       for c in columns)
    returns = np.asarray(values, dtype=np.float64).T
    require(returns.shape == (252, 3) and np.isfinite(returns).all()
            and (returns > -1).all()
            and all(original == 0 or converted != 0 for originals, converted_column
                    in zip(values, returns.T, strict=True)
                    for original, converted in zip(originals, converted_column, strict=True)),
            "returns_not_representable")
    return covariance._population_covariance(returns)


def scaled_target(weights, exposure):
    require(type(exposure) is Decimal and exposure.is_finite() and 0 <= exposure <= 1,
            "exposure")
    nav.ThreeAssetTarget(tuple(weights), Decimal(0))
    with localcontext(base.CONTEXT):
        scaled = tuple(w * exposure for w in weights)
    with localcontext(base.CONTEXT) as context:
        context.prec = max(100, max(-w.as_tuple().exponent for w in scaled) + 2)
        cash = 1 - sum(scaled, Decimal(0))
    return nav.ThreeAssetTarget(scaled, cash)


def risk_allocations(c):
    c = np.asarray(c, dtype=np.float64)
    candidate = solver.minimum_variance_weights(c)  # Solver itself shrinks; do not shrink twice.
    shrunk = .9 * c + .1 * np.diag(np.diag(c))
    diagonal = np.diag(shrunk)
    zeros = diagonal == 0
    inverse = (solver._normalized(tuple(Decimal(int(v)) for v in zeros)) if zeros.any() else
               solver._normalized(tuple(Decimal.from_float(float(1 / math.sqrt(v)))
                                        for v in diagonal)))
    equal = solver._normalized((Decimal(1),) * 3)
    targets, diagnostics = {}, {}
    for policy, weights in zip(RISK_POLICIES, (candidate, inverse, equal), strict=True):
        w = np.asarray(weights, dtype=np.float64)
        variance = float(w @ shrunk @ w)
        require(math.isfinite(variance) and variance >= 0, "risk_not_representable")
        vol = math.sqrt(252 * variance)
        require(math.isfinite(vol), "risk_not_representable")
        exposure = Decimal(1) if vol <= .10 else Decimal.from_float(.10 / vol)
        target = scaled_target(weights, exposure)
        scaled = np.asarray(target.weights3, dtype=np.float64)
        attained = math.sqrt(252 * float(scaled @ shrunk @ scaled))
        require(math.isfinite(attained), "risk_not_representable")
        targets[policy] = target
        diagnostics[policy] = dict(forecast_volatility=vol, exposure=str(exposure),
            attained_forecast_volatility=attained, leverage_cap_binding=vol < .10,
            risk_reduced=vol > .10)
    targets.update(cash=scaled_target(equal, Decimal(0)), buyhold=scaled_target(equal, Decimal(1)))
    return targets, diagnostics


def prepare_actions(rows_by_symbol, plan, vintage_ref, *, deadline=float("inf")):
    require(build_plan(plan.sessions) == plan, "plan_changed")
    actions = {p: [] for p in POLICIES}
    diagnostics, past = [], []
    for position, index in enumerate(plan.entry_indices):
        require(time.monotonic() < deadline, "compute_stop")
        dates = tuple(s.session_date for s in plan.sessions[index - 253:index])
        columns = _selected_closes(rows_by_symbol, dates, vintage_ref)
        targets, risk = risk_allocations(covariance_from_closes(columns))
        day = plan.sessions[index].session_date.isoformat()
        past.append(digest(encode([[str(v) for v in c] for c in columns])))
        diagnostics.append(dict(entry_date=day, policies=risk))
        for policy, target in targets.items():
            if policy != "buyhold" or position == 0:
                actions[policy].append([day, *map(str, target.weights3), str(target.cash_weight)])
    return dict(plan=plan.record(), vintage_ref=vintage_ref,
                past_input_sha256=digest(encode(past)), actions=actions, diagnostics=diagnostics)


def _metrics(daily, entering, peak, entries):
    result = base._metrics(daily, entering, entries)
    with localcontext(base.CONTEXT):
        logs = tuple(d.log_return for d in daily)
        mean = sum(logs, Decimal(0)) / len(logs)
        variance = sum((v - mean)**2 for v in logs) / len(logs)
        drawdown = Decimal(0)
        result["running_peak_entry"] = str(peak)
        for day in daily:
            peak = max(peak, day.nav)
            drawdown = max(drawdown, 1 - day.nav / peak)
        result.update(annual_log_volatility=str((252 * variance).sqrt()),
                      maximum_drawdown=str(drawdown), running_peak_exit=str(peak))
    result["entries"] = result.pop("months")
    return result, peak


def evaluate(days, actions, plan, *, deadline=float("inf")):
    require(build_plan(plan.sessions) == plan, "plan_changed")
    require(actions["plan"] == plan.record() and set(actions["actions"]) == set(POLICIES),
            "action_binding")
    require(tuple(d.date for d in days) == plan.dates, "forward_mark_gap")
    seal, cells = digest(encode(actions)), []
    for cost in COSTS:
        for policy in POLICIES:
            require(time.monotonic() < deadline, "compute_stop")
            rows = actions["actions"][policy]
            keys = [plan.sessions[i].session_date.isoformat() for i in plan.entry_indices]
            require([r[0] for r in rows] == (keys[:1] if policy == "buyhold" else keys),
                    "action_keys")
            targets = {date.fromisoformat(r[0]): nav.ThreeAssetTarget(
                tuple(Decimal(w) for w in r[1:4]), Decimal(r[4])) for r in rows}
            ledger = nav.replay(days, targets, cost)
            cut, peak = plan.block_cut, Decimal(1)
            for block, subset, entering in ((0, ledger.daily[:cut], Decimal(1)),
                                           (1, ledger.daily[cut:], ledger.daily[cut - 1].nav)):
                metrics, peak = _metrics(subset, entering, peak,
                                         sum(d.date in targets for d in subset))
                cells.append(dict(block=block, policy=policy, cost_bps=str(cost),
                                  status="complete", metrics=metrics))
    require(digest(encode(actions)) == seal, "action_changed")
    return cells


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    require(len(cells) == 30 and {(c["block"], c["policy"], c["cost_bps"]) for c in cells}
            == expected and all(c["status"] == "complete" for c in cells), "cell_matrix")
    with localcontext(base.CONTEXT):
        require(all(type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
            for c in cells for k in ("growth", "utility", "annual_log_volatility",
                                    "maximum_drawdown")), "cell_metrics")
        require(all(Decimal(c["metrics"]["annual_log_volatility"]) >= 0
                    and 0 <= Decimal(c["metrics"]["maximum_drawdown"]) <= 1 for c in cells),
                "cell_metrics")
        for block in (0, 1):
            group = {c["policy"]: c["metrics"] for c in cells
                     if c["block"] == block and c["cost_bps"] == "10"}
            own = group["candidate"]
            if (Decimal(own["growth"]) <= 0
                or Decimal(own["growth"]) <= Decimal(group["cash"]["growth"])
                or any(Decimal(own["utility"]) - Decimal(group[p]["utility"]) <= Decimal(".001")
                       for p in ("inverse_volatility", "equal_thirds"))
                or Decimal(own["annual_log_volatility"]) > Decimal(".15")
                or Decimal(own["maximum_drawdown"]) > Decimal(".25")):
                return dict(candidate="rejected")
    return dict(candidate="development_survivor")


def runtime_identity():
    return dict(base.runtime_identity(), numpy=importlib.metadata.version("numpy"))


def _root(root, artifact_root):
    root, artifact_root = Path(root).absolute(), Path(artifact_root).absolute()
    require(root == artifact_root / "research" / NAME and root.is_dir(), "study_root")
    base.reject_repo_artifact_path(root, REPO)
    return root


def read_contract(root, artifact_root, pin):
    root = _root(root, artifact_root)
    contract = base._json(root / "precommit.json", pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == runtime_identity() == RUNTIME, "runtime_identity")
    require(Path(contract["source_root"]).absolute() == REPO, "frozen_source_root")
    require(set(contract["code_sha256"]) >= set(CODE), "code_pins")
    for relative, expected in contract["code_sha256"].items():
        require(digest(base._read(base._relative(REPO, relative))) == expected, "code_changed")
    commitment = base._json(base._relative(artifact_root, base.INPUT_RELATIVE), base.INPUT_PIN)
    require(contract["input_commitment_sha256"] == base.INPUT_PIN
            and commitment["calendar_sha256"] == base.CALENDAR_PIN
            and commitment["kind"] == "kis-cross-asset-d1-price-only-input-v1"
            and commitment["no_date_fill"] is True, "input_identity")
    require(all(contract["code_sha256"].get(p) == h
                for p, h in commitment["source_pins"].items()), "producer_code_pins")
    return contract, commitment


def _artifacts(root):
    return {name: digest(base._read(root / name)) for name in ARTIFACTS if (root / name).exists()}


def load_past_closes(source, plan):
    dates = {d.isoformat() for d in required_past_dates(plan)}
    selected = base._selected(source, dates, ("close",))
    return {s: tuple(base.PriceClose(s, date.fromisoformat(d), base.INPUT_PIN, v["close"])
                     for d, v in sorted(selected[s].items())) for s in base.INSTRUMENT_ORDER}


def load_marks(source, plan):
    rows = base._selected(source, {d.isoformat() for d in plan.dates}, ("open", "close"))
    return tuple(nav.ThreeAssetDay(d,
        tuple(rows[s][d.isoformat()]["open"] for s in base.INSTRUMENT_ORDER),
        tuple(rows[s][d.isoformat()]["close"] for s in base.INSTRUMENT_ORDER)) for d in plan.dates)


def _safe(result):
    return {k: result[k] for k in ("status", "reason", "phase", "actual_fits", "fit_starts",
                                 "contract_sha256", "elapsed_seconds", "criterion")} | dict(
        cells=len(result["cells"]), result_sha256=digest(encode(result)),
        paper_input=False, holdout_access="none")


def run(root, market_root, artifact_root, pin):
    start = time.monotonic()
    deadline = start + SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    require(not _artifacts(root) and not (root / "worker-result.json").exists(), "attempt_exists")
    base.atomic_new(root / "started.json", dict(contract_sha256=pin, input_sha256=base.INPUT_PIN))
    result = dict(status="failed", reason="worker_failed", phase="source_input", actual_fits=0,
        fit_starts=0, contract_sha256=pin, elapsed_seconds=0, criterion={}, cells=[],
        artifact_sha256={}, resources={})
    try:
        source = base.load_committed_source(commitment, artifact_root, market_root,
                                             deadline=deadline)
        plan = build_plan(source.plan.sessions)
        require(plan.record() == contract["plan"], "plan_changed")
        result["phase"] = "prepare"
        actions = prepare_actions(load_past_closes(source, plan), plan, base.INPUT_PIN,
                                  deadline=deadline)
        result["phase"] = "decision_seal"
        base.atomic_new(root / "actions.json", actions)
        require(time.monotonic() < deadline, "compute_stop")
        result["phase"] = "forward_input"
        marks = load_marks(source, plan)
        result["phase"] = "evaluate"
        cells = evaluate(marks, actions, plan, deadline=deadline)
        result["phase"] = "validate"
        verdict = criterion(cells)
        require(base.load_committed_source(commitment, artifact_root, market_root,
                    deadline=deadline).files == source.files, "source_changed")
        require(time.monotonic() < deadline, "compute_stop")
        result.update(status="complete", reason=None, cells=cells, criterion=verdict)
    except Exception as error:
        unavailable = {"required_session_missing", "required_session_duplicate",
            "required_row_binding",
            "required_date_gap", "required_price", "price_close_invalid", "price_basis_invalid",
            "forward_mark_gap", "returns_not_representable", "covariance_not_representable",
            "covariance_not_psd", "risk_not_representable"}
        allowed = unavailable | {"compute_stop", "source_changed", "plan_changed",
                                 "allocation_not_representable"}
        code = str(error) if isinstance(error, (base.StudyFault, CrossAssetInputUnavailable,
            covariance.JointPortfolioInputUnavailable, nav.ThreeAssetNavError)) \
            and str(error) in allowed else "worker_failed"
        result.update(reason=code, status="input_unavailable" if code in unavailable else "failed")
    result.update(elapsed_seconds=time.monotonic() - start, artifact_sha256=_artifacts(root))
    base.atomic_new(root / "worker-result.json", result)
    return _safe(result)


def verify(root, market_root, artifact_root, pin, result_pin):
    deadline = time.monotonic() + VERIFY_SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    result = base._json(root / "worker-result.json", result_pin, canonical=True)
    require(set(result) == {"status", "reason", "phase", "actual_fits", "fit_starts",
        "contract_sha256", "elapsed_seconds", "criterion", "cells", "artifact_sha256", "resources"}
        and result["contract_sha256"] == pin and result["phase"] in PHASES
        and type(result["actual_fits"]) is int and type(result["fit_starts"]) is int
        and result["actual_fits"] == result["fit_starts"] == 0
        and type(result["elapsed_seconds"]) in (int, float)
        and math.isfinite(result["elapsed_seconds"]) and result["elapsed_seconds"] >= 0,
        "result_binding")
    require(result["artifact_sha256"] == _artifacts(root), "artifact_binding")
    require(base._json(root / "started.json", canonical=True) == dict(
        contract_sha256=pin, input_sha256=base.INPUT_PIN), "start_binding")
    if result["status"] in {"failed", "input_unavailable"}:
        require(result["reason"] is not None and result["cells"] == []
                and result["criterion"] == {}, "failure_binding")
        return _safe(result) | dict(replay="failure_binding_only", fits=0, inference=0,
                                   searches=0, writes=0)
    require(result["status"] == "complete" and result["reason"] is None
            and result["phase"] == "validate" and set(result["artifact_sha256"]) == set(ARTIFACTS),
            "complete_binding")
    source = base.load_committed_source(commitment, artifact_root, market_root, deadline=deadline)
    plan = build_plan(source.plan.sessions)
    require(plan.record() == contract["plan"], "plan_changed")
    actions = prepare_actions(load_past_closes(source, plan), plan, base.INPUT_PIN,
                              deadline=deadline)
    require(base._read(root / "actions.json") == encode(actions), "action_replay")
    cells = evaluate(load_marks(source, plan), actions, plan, deadline=deadline)
    require(encode(cells) == encode(result["cells"]) and criterion(cells) == result["criterion"],
            "numeric_replay")
    require(base.load_committed_source(commitment, artifact_root, market_root,
                deadline=deadline).files == source.files, "source_changed")
    require(time.monotonic() < deadline, "compute_stop")
    return _safe(result) | dict(replay="exact_economic/past_action_binding", fits=0,
                               inference=0, searches=0, writes=0)


def synthetic_smoke():
    plan = build_plan()
    rows = {s: tuple(base.PriceClose(s, d, "synthetic", Decimal(100))
                    for d in sorted(required_past_dates(plan))) for s in base.INSTRUMENT_ORDER}
    actions = prepare_actions(rows, plan, "synthetic")
    marks = tuple(nav.ThreeAssetDay(d, (Decimal(100),) * 3, (Decimal(100),) * 3)
                  for d in plan.dates)
    cells = evaluate(marks, actions, plan)
    require(len(cells) == 30 and criterion(cells) == dict(candidate="rejected"), "smoke_matrix")
    return dict(status="smoke_passed", monthly_entries=33, valuation_days=689, cells=30,
                actual_fits=0, fit_starts=0, actual_market_reads=0, gpu=False, paper_input=False)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("smoke", "run", "verify"))
    for name in ("root", "market-root", "artifact-root"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args(argv)
    bound = args.phase != "smoke"
    if any(bool(v) != bound for v in (args.root, args.market_root, args.artifact_root,
                                      args.contract_sha256)) or bool(args.result_sha256) != (
                                          args.phase == "verify"):
        parser.error("run/verify require roots+contract pin; "
                     "verify requires result pin; smoke none")
    try:
        result = (synthetic_smoke() if not bound else run(args.root, args.market_root,
            args.artifact_root, args.contract_sha256) if args.phase == "run" else verify(
                args.root, args.market_root, args.artifact_root, args.contract_sha256,
                args.result_sha256))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result["status"] in {"complete", "smoke_passed"} else 2
    except Exception:
        print(json.dumps(dict(status="failed", reason="study_unavailable")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
