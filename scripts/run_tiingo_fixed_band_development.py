"""One fixed-band, continuous-fold CPU comparison; no tuning, weights or Paper input."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

from thericher_v2.data.tiingo_adjusted_etf_daily import _unlinked_path  # noqa: E402
from thericher_v2.research import tiingo_monthly_holding_development as h  # noqa: E402

NAME = "tiingo-fixed-band-continuous-development-v1"
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
SECONDS = 180
COSTS = ("0", "2.5", "5", "10")
POLICIES = ("vol_managed", "vol_band", "train_risk_matched", "risk_band", "always_long", "cash")
CODE = tuple(dict.fromkeys((*h.CODE, "scripts/run_tiingo_fixed_band_development.py")))
METRICS = ("final_nav", "max_close_drawdown", "fees_initial_nav", "turnover_initial_nav")


def configuration():
    return dict(
        symbols=list(h.SYMBOLS),
        train=list(h.TRAIN),
        periods=[list(p) for p in h.PERIODS],
        costs_per_side_bps=list(COSTS),
        policies=list(POLICIES),
        cells=144,
        center="Existing prior22 variance target; TRAIN-only median and risk control",
        band="fixed half-width0.1 clipped[0,1]; clamp actual predecision owned stock/NAV",
        timing="continuous capital within each fold; monthly OPEN decisions; final CLOSE exit",
        fees="existing actual-notional post-fee Decimal50 ledger; terminal liquidation included",
        budget=dict(
            seconds=SECONDS, cpu_threads=1, memory_bytes=2 * 1024**3, attempts=1, gpu=False
        ),
        strongest_kill=(
            "nonpositive mean stress paired NAV gain or turnover saving; "
            "not positive after dropping each ETF"
        ),
        fits=0,
        selection=False,
        weights_retained=False,
        holdout_access="none",
        image=IMAGE,
        reference="https://arxiv.org/abs/2103.01775",
        limitations=[
            "seen revised non-PIT surviving ETFs; not independent evaluation",
            "option-hedging mechanism adaptation, not replication or alpha evidence",
            "band changes exposure as well as fees; controls are not exposure-matched",
            "centers are cost-independent, realized band decisions are not",
            "adjusted-mark proxy; no broker parity, Paper or profitability qualification",
        ],
    )


def output_root(artifacts):
    root = h.base.ensure_external_artifact_directory(artifacts, h.REPO, "research") / NAME
    if root.exists() or root.is_symlink():
        _unlinked_path(root)
    return root


def check_market_root(market):
    _unlinked_path(market)
    h.require(
        market.is_dir() and not market.resolve().is_relative_to(h.REPO.resolve()),
        "external_market_root",
    )


def freeze(artifacts, market):
    check_market_root(market)
    h.base.verify_metadata(artifacts, market)
    config, source = configuration(), h.source_identity()
    contract = dict(
        name=NAME,
        config=config,
        source=source,
        plan=h.build_plan(h.calendar_days()),
        code_sha256={p: h.digest((h.REPO / p).read_bytes()) for p in CODE},
    )
    root = output_root(artifacts)
    root.mkdir()
    _unlinked_path(root)
    h.atomic_new(root / "precommit.json", contract)
    pin = h.digest(h.encode(contract))
    h.base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=h.digest(h.encode(source)),
        split_hash=h.digest(h.encode(contract["plan"])),
        cost_model_hash=h.digest(h.encode(COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=artifacts,
        repo_root=h.REPO,
    )
    return pin


def verify_contract(artifacts, market, pin):
    check_market_root(market)
    root = output_root(artifacts)
    raw = h._read(root / "precommit.json")
    h.require(h.digest(raw) == pin, "contract_binding")
    contract = json.loads(raw)
    h.require(
        set(contract) == {"name", "config", "source", "plan", "code_sha256"}, "contract_fields"
    )
    h.require(
        contract["name"] == NAME and contract["config"] == configuration(), "configuration_changed"
    )
    h.require(contract["source"] == h.source_identity(), "source_changed")
    h.require(contract["plan"] == h.build_plan(contract["plan"]["days"]), "plan_changed")
    h.require(set(contract["code_sha256"]) == set(CODE), "source_pin_fields")
    h.require(
        all(h.digest((h.REPO / p).read_bytes()) == v for p, v in contract["code_sha256"].items()),
        "code_changed",
    )
    h.base.verify_metadata(artifacts, market)
    return root, contract


def evaluate(rows_by_symbol, plan, *, deadline):
    cells, calibrations = [], []
    days = plan["days"]
    for symbol in h.SYMBOLS:
        rows = {r.session_date.isoformat(): r for r in rows_by_symbol[symbol]}
        vref, risk, facts = h.calibrate(rows, plan, deadline=deadline)
        h.require(vref is not None and risk is not None, "TRAIN_input_unavailable")
        calibrations.append(dict(symbol=symbol, **facts))
        for period in plan["periods"]:
            bounds = period["bounds"]
            h.require(h.gaps(rows, days, bounds) == (0, 0), "comparison_input_unavailable")
            centers = h.targets(rows, days, bounds, vref)
            risk_centers = {i: risk for i in h.month_indices(days, bounds)}
            for cost in COSTS:
                for policy in POLICIES:
                    actions = centers if policy.startswith("vol_") else risk_centers
                    if policy in {"always_long", "cash"}:
                        actions = {bounds[0]: Decimal(int(policy == "always_long"))}
                    result = h.replay(
                        rows,
                        days,
                        bounds,
                        actions,
                        cost,
                        deadline=deadline,
                        target_transform=h.fixed_band_target if policy.endswith("_band") else None,
                    )
                    cells.append(
                        dict(
                            symbol=symbol,
                            period=period["period"],
                            policy=policy,
                            cost_per_side_bps=cost,
                            trades=result["trades"],
                            center_sha256=h.digest(
                                h.encode({str(i): str(v) for i, v in actions.items()})
                            ),
                            **{m: h.number(result[m]) for m in METRICS},
                        )
                    )
    return dict(status="development_complete", calibrations=calibrations, cells=cells)


@h._decimal
def validate_cells(result):
    cells = result["cells"]
    h.require(len(cells) == 144, "cell_count")
    expected = [
        (s, p[0], c, n) for s in h.SYMBOLS for p in h.PERIODS for c in COSTS for n in POLICIES
    ]
    h.require(
        [(c["symbol"], c["period"], c["cost_per_side_bps"], c["policy"]) for c in cells]
        == expected,
        "cell_matrix",
    )
    centers = {}
    for cell in cells:
        values = {m: Decimal(cell[m]) for m in METRICS}
        h.require(all(v.is_finite() for v in values.values()), "nonfinite_metric")
        h.require(
            values["final_nav"] > 0 and 0 <= values["max_close_drawdown"] < 1, "metric_domain"
        )
        fees, traded = values["fees_initial_nav"], values["turnover_initial_nav"]
        h.require(
            fees >= 0 and traded >= 0 and type(cell["trades"]) is int and cell["trades"] >= 0,
            "trade_domain",
        )
        tolerance = Decimal("3e-11") * (1 + fees + traded)
        h.require(
            abs(fees - Decimal(cell["cost_per_side_bps"]) * traded / 10000) <= tolerance,
            "fee_identity",
        )
        key = cell["symbol"], cell["period"], cell["policy"]
        h.require(
            centers.setdefault(key, cell["center_sha256"]) == cell["center_sha256"],
            "cost_changes_centers",
        )
        if cell["policy"] == "cash":
            h.require(
                values["final_nav"] == 1 and fees == traded == cell["trades"] == 0, "cash_identity"
            )


@h._decimal
def paired_facts(result):
    by_key = {
        (c["symbol"], c["period"], c["cost_per_side_bps"], c["policy"]): c for c in result["cells"]
    }
    deltas = []
    for symbol in h.SYMBOLS:
        for period, *_ in h.PERIODS:
            plain = by_key[symbol, period, "10", "vol_managed"]
            band = by_key[symbol, period, "10", "vol_band"]
            deltas.append(
                (
                    symbol,
                    Decimal(band["final_nav"]) - Decimal(plain["final_nav"]),
                    Decimal(plain["turnover_initial_nav"]) - Decimal(band["turnover_initial_nav"]),
                )
            )
    mean_nav = sum(d[1] for d in deltas) / len(deltas)
    mean_saving = sum(d[2] for d in deltas) / len(deltas)
    leave_one = [sum(d[1] for d in deltas if d[0] != s) / 4 for s in h.SYMBOLS]
    return dict(
        mean_stress_paired_nav_delta=h.number(mean_nav),
        mean_stress_turnover_saving=h.number(mean_saving),
        minimum_leave_one_etf_out_nav_delta=h.number(min(leave_one)),
        kill_applied=mean_nav <= 0 or mean_saving <= 0 or min(leave_one) <= 0,
        interpretation="descriptive six overlapping ETF/fold pairs; no significance or selection",
    )


def runtime():
    h.require(Path("/.dockerenv").is_file(), "Docker_required")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    h.require(quota != "max" and 0 < int(quota) <= int(period), "CPU_confinement")
    memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    h.require(memory != "max" and 0 < int(memory) <= 2 * 1024**3, "memory_confinement")


def run(artifacts, market, pin):
    runtime()
    root, contract = verify_contract(artifacts, market, pin)
    h.atomic_new(root / "started.json", {"contract_sha256": pin})
    started = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
    signal.alarm(SECONDS)
    try:
        rows = h.load_adjusted(market / h.base.SNAPSHOT, market)
        result = evaluate(rows, contract["plan"], deadline=started + SECONDS)
        validate_cells(result)
        result["paired"] = paired_facts(result)
        verify_contract(artifacts, market, pin)
        result.update(contract_sha256=pin, elapsed_seconds=round(time.monotonic() - started, 3))
        h.atomic_new(root / "summary.json", result)
    finally:
        signal.alarm(0)
    return dict(
        status=result["status"],
        cells=len(result["cells"]),
        fits=0,
        gpu=False,
        elapsed_seconds=result["elapsed_seconds"],
        paired=result["paired"],
        summary_sha256=h.digest(h._read(root / "summary.json")),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run", "verify"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--market-data-root", type=Path, required=True)
    parser.add_argument("--contract-hash")
    parser.add_argument("--summary-hash")
    args = parser.parse_args(argv)
    try:
        if args.mode == "freeze":
            result = dict(
                status="frozen", contract_sha256=freeze(args.artifact_root, args.market_data_root)
            )
        elif args.mode == "run":
            result = run(args.artifact_root, args.market_data_root, args.contract_hash)
        else:
            root, _ = verify_contract(args.artifact_root, args.market_data_root, args.contract_hash)
            raw = h._read(root / "summary.json")
            h.require(
                args.summary_hash is not None and h.digest(raw) == args.summary_hash,
                "summary_binding",
            )
            result = json.loads(raw)
            h.require(result["contract_sha256"] == args.contract_hash, "result_binding")
            validate_cells(result)
            h.require(result["paired"] == paired_facts(result), "paired_binding")
            result = dict(
                status="verified",
                cells=144,
                summary_sha256=h.digest(raw),
            )
    except Exception:
        print(json.dumps(dict(status="failed", reason="runtime_or_invariant_failure")))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
