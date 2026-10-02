"""Six later ETF-month windows, frozen numeric policies, no fitting or promotion.

Parent owns the exact pinned Docker image, read-only source/data/parent mounts
and this study's writable sibling directory. Freeze reads metadata only. Run
requires offline Docker CPU confinement and reserves one immutable attempt.
"""

from __future__ import annotations

import argparse
import json
import re
import runpy
import signal
import socket
import stat
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402

from thericher_v2.data.tiingo_adjusted_etf_daily import (  # noqa: E402
    _unlinked_file,
    _unlinked_path,
)
from thericher_v2.data.tiingo_adjusted_vintage import (  # noqa: E402
    load_verified_adjusted_etf_vintage,
)
from thericher_v2.research import tiingo_monthly_net_utility_development as study  # noqa: E402

NAME = "tiingo-monthly-frozen-policy-aug-sep-2026-v1"
REPO = study.REPO
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
PARENT_CONTRACT = "sha256:e3499c501a0c494b3766cb868385780ab6a478e9084e03dfcc5469956a1c1941"
PARENT_SUMMARY = "sha256:ccbece56af83c34c9b7df0563172ff89e38490904372b0824b0104fc123f483c"
SYMBOLS, ARCHITECTURES = study.SYMBOLS, study.ARCHITECTURES
MONTHS, COSTS, POLICIES = ("2026-08", "2026-09"), study.COSTS, study.POLICIES
SECONDS, MEMORY_BYTES = 120, 2 * 1024**3
CODE = tuple(
    dict.fromkeys(
        (
            *study.CODE,
            "src/thericher_v2/data/tiingo_adjusted_vintage.py",
            "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py",
            "scripts/run_tiingo_monthly_frozen_policy_readback.py",
        )
    )
)
METRICS = study.METRICS
encode, digest, require = study.encode, study.digest, study.require


def configuration():
    return dict(
        symbols=list(SYMBOLS),
        months=list(MONTHS),
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        cells=126,
        matched_checks=36,
        train=list(study.TRAIN),
        training_months=132,
        fits=0,
        new_weights=0,
        feature=study.configuration()["feature"],
        timing="independent month OPEN NAV1; one target; final CLOSE liquidation; no month carry",
        calibration="recover original-vintage TRAIN constants; exact parent risk hashes; no refit",
        matched_control="same predicted initial exposure, independent constant-action replay",
        matched_interpretation="identity only, not predictive value or an additional policy",
        numeric="existing Decimal50 ledger and NumPy utility; output12dp",
        budget=dict(
            seconds=SECONDS,
            cpu_threads=2,
            memory_bytes=MEMORY_BYTES,
            gpu=False,
            forward_calls=36,
            replay_calls=171,
            attempts=1,
        ),
        image=IMAGE,
        scope=study.configuration()["scope"],
        limitations=[
            "tiny revised non-PIT development",
            "no independent holdout or selection",
            "no portfolio, Paper, execution parity or profitability qualification",
        ],
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_field")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("invalid_json_number")


def _read(path, limit=2 * 1024**2):
    _unlinked_path(path.parent)
    _unlinked_file(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "file_identity")
    raw = study._read(path, limit)
    after = path.lstat()
    require(
        (before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink)
        == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink),
        "file_changed",
    )
    return raw


def _json(path, pin=None):
    raw = _read(path)
    require(pin is None or digest(raw) == pin, "metadata_hash")
    return json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_constant)


def _fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), "closed_fields")


def _hash(value):
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _paths(artifact_root, market_data_root):
    for root in (artifact_root, market_data_root):
        _unlinked_path(root)
        require(root.is_dir(), "external_root")
    artifacts, market = artifact_root.resolve(), market_data_root.resolve()
    repo = REPO.resolve()
    require(
        not artifacts.is_relative_to(repo)
        and not market.is_relative_to(repo)
        and not artifacts.is_relative_to(market)
        and not market.is_relative_to(artifacts),
        "external_root_overlap",
    )
    research = artifacts / "research"
    _unlinked_path(research)
    require(research.is_dir(), "research_root")
    parent, output = research / study.NAME, research / NAME
    _unlinked_path(parent)
    if output.exists():
        _unlinked_path(output)
    return parent, output


def runtime_constraints():
    """Container metadata only; parent attests the image digest at invocation."""
    versions = study.runtime_versions()
    require(
        versions["torch"] == "2.7.0+cu128" and versions["pandas-market-calendars"] == "5.4.0",
        "pinned_runtime",
    )
    require(Path("/.dockerenv").is_file(), "Docker_required")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    require(quota != "max" and 0 < int(quota) <= 2 * int(period), "CPU_confinement")
    memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    require(memory != "max" and 0 < int(memory) <= MEMORY_BYTES, "memory_confinement")
    require(Path("/sys/fs/cgroup/memory.swap.max").read_text().strip() == "0", "swap_confinement")
    require({name for _, name in socket.if_nameindex()} == {"lo"}, "network_none_required")
    return versions


def calendar_days():
    import pandas_market_calendars as calendars

    return [
        t.date().isoformat()
        for t in calendars.get_calendar("NYSE")
        .schedule(start_date="2025-07-01", end_date="2026-10-01")
        .index
    ]


def build_plan(days):
    require(
        type(days) is list
        and days
        and all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days)
        and all(a < b for a, b in zip(days, days[1:], strict=False)),
        "calendar",
    )
    require(days[0] == "2025-07-01" and days[-1] == "2026-10-01", "calendar_bracket")
    segments = []
    for month in MONTHS:
        indices = [i for i, d in enumerate(days) if d[:7] == month]
        require(bool(indices), "calendar_month_missing")
        a, b = indices[0], indices[-1] + 1
        require(
            a >= 253 and b < len(days) and days[a - 1][:7] != month and days[b][:7] != month,
            "calendar_month_context",
        )
        segments.append(dict(month=month, bounds=[a, b], support=days[a - 253 : b]))
    return dict(days=days, windows=segments)


def parent_metadata(parent):
    contract = _json(parent / "precommit.json", PARENT_CONTRACT)
    header = study.header(contract, PARENT_CONTRACT)
    require(
        all(digest(_read(REPO / path)) == pin for path, pin in contract["code_sha256"].items()),
        "parent_code_changed",
    )
    summary = _json(parent / "summary.json", PARENT_SUMMARY)
    require(
        summary["status"] == "complete" and all(summary[k] == v for k, v in header.items()),
        "parent_result_binding",
    )
    models = summary["models"]
    require(type(models) is list and len(models) == 2, "parent_models")
    for architecture, model in zip(ARCHITECTURES, models, strict=True):
        _fields(
            model, ("architecture", "file", "weights_sha256", "epochs", "seed", "reconstructed")
        )
        require(
            model["architecture"] == architecture
            and model["file"] == f"weights-{architecture}.npz"
            and _hash(model["weights_sha256"])
            and type(model["epochs"]) is int
            and model["epochs"] == 128
            and type(model["seed"]) is int
            and model["seed"] == 101
            and model["reconstructed"] is True,
            "parent_model_binding",
        )
    groups = summary["groups"]
    require(
        [(g["symbol"], g["period"]) for g in groups]
        == [(s, p) for s in SYMBOLS for p, _, _ in study.PERIODS],
        "parent_groups",
    )
    risks = {}
    for group in groups:
        require(
            group["status"] == "evaluated"
            and group["train"]["months"] == 132
            and group["train"]["missing"] == group["train"]["invalid"] == 0,
            "parent_training_binding",
        )
        _fields(group["risk_sha256"], ARCHITECTURES)
        require(
            all(_hash(v) for v in group["risk_sha256"].values())
            and risks.setdefault(group["symbol"], group["risk_sha256"]) == group["risk_sha256"],
            "parent_risk_binding",
        )
    lineage = dict(
        contract_sha256=PARENT_CONTRACT,
        summary_sha256=PARENT_SUMMARY,
        models=models,
        risk_sha256=risks,
        source=contract["source"],
        training_plan_sha256=digest(encode([contract["plan"]["days"], contract["plan"]["train"]])),
    )
    return lineage, contract


def vintage_metadata(market, snapshot, pin):
    require(
        type(snapshot) is str
        and re.fullmatch(r"snapshot=20[0-9]{6}T[0-9]{6}Z-tiingo-etf-d1-r1", snapshot) is not None
        and _hash(pin),
        "vintage_identity",
    )
    relative = "us_equities/tiingo_etf_daily/canonical/" + snapshot
    manifest = _json(market / relative / "manifest.json", pin)
    require(
        manifest["kind"] == "tiingo_etf_raw_d1_snapshot"
        and manifest["version"] == "tiingo-etf-d1-r1"
        and manifest["immutable_snapshot"] is True
        and manifest["symbols"] == list(SYMBOLS)
        and manifest["dataset_id"] == "us_equities.tiingo_etf_daily." + snapshot
        and manifest["requested_window"] == dict(start="2025-07-01", end="2026-09-30")
        and _hash(manifest["dataset_hash"]),
        "vintage_metadata",
    )
    raw = manifest["files"]["raw_sources"]
    require(
        type(raw) is list
        and [r["symbol"] for r in raw] == list(SYMBOLS)
        and all(r["filename"] == r["symbol"] + ".json" and _hash(r["sha256"]) for r in raw),
        "vintage_raw_pins",
    )
    coverage = manifest["per_symbol"]
    _fields(coverage, SYMBOLS)
    require(
        all(
            type(c["session_count"]) is int
            and c["session_count"] >= 253
            and c["first_session"] <= "2025-07-01"
            and c["last_session"] == "2026-09-30"
            for c in coverage.values()
        ),
        "vintage_coverage_metadata",
    )
    return dict(
        snapshot=relative,
        dataset_id=manifest["dataset_id"],
        dataset_sha256=manifest["dataset_hash"],
        manifest_sha256=pin,
        raw_sha256={r["symbol"]: r["sha256"] for r in raw},
    )


def freeze(artifact_root, market_data_root, snapshot, manifest_pin):
    runtime = runtime_constraints()
    parent, output = _paths(artifact_root, market_data_root)
    lineage, parent_contract = parent_metadata(parent)
    require(encode(runtime) == encode(parent_contract["runtime"]), "parent_runtime")
    vintage = vintage_metadata(market_data_root, snapshot, manifest_pin)
    contract = dict(
        name=NAME,
        config=configuration(),
        runtime=runtime,
        parent=lineage,
        vintage=vintage,
        plan=build_plan(calendar_days()),
        code_sha256={p: digest(_read(REPO / p)) for p in CODE},
    )
    output.mkdir(exist_ok=True)
    _unlinked_path(output)
    require(not any(output.iterdir()), "freeze_output_not_empty")
    study.atomic_new(output / "precommit.json", contract)
    return digest(encode(contract))


def verify(artifact_root, market_data_root, pin):
    require(_hash(pin), "contract_pin")
    runtime = runtime_constraints()
    parent, output = _paths(artifact_root, market_data_root)
    contract = _json(output / "precommit.json", pin)
    _fields(contract, ("name", "config", "runtime", "parent", "vintage", "plan", "code_sha256"))
    lineage, parent_contract = parent_metadata(parent)
    require(
        contract["name"] == NAME
        and encode(contract["config"]) == encode(configuration())
        and encode(contract["runtime"]) == encode(runtime)
        and encode(contract["runtime"]) == encode(parent_contract["runtime"])
        and encode(contract["parent"]) == encode(lineage),
        "contract_binding",
    )
    require(encode(contract["plan"]) == encode(build_plan(calendar_days())), "calendar_changed")
    require(
        set(contract["code_sha256"]) == set(CODE)
        and all(digest(_read(REPO / p)) == value for p, value in contract["code_sha256"].items()),
        "code_changed",
    )
    _fields(
        contract["vintage"],
        ("snapshot", "dataset_id", "dataset_sha256", "manifest_sha256", "raw_sha256"),
    )
    source = contract["vintage"]
    require(
        source
        == vintage_metadata(
            market_data_root, Path(source["snapshot"]).name, source["manifest_sha256"]
        ),
        "vintage_changed",
    )
    return output, contract, parent_contract


def _tick(counts, field, amount, deadline):
    require(time.monotonic() < deadline, "hard_timeout")
    require(type(amount) is int and amount > 0, "compute_increment")
    require(
        counts[field] + amount <= {"forward_calls": 36, "replay_calls": 171}[field],
        "compute_budget",
    )
    counts[field] += amount


def _load_source(market, source):
    return load_verified_adjusted_etf_vintage(
        market / source["snapshot"],
        dataset_id=source["dataset_id"],
        expected_dataset_hash=source["dataset_sha256"],
        expected_manifest_hash=source["manifest_sha256"],
        expected_raw_hashes=source["raw_sha256"],
        market_data_root=market,
        repo_root=REPO,
    )


def _predict(torch, model, arrays, counts, deadline):
    _tick(counts, "forward_calls", 1, deadline)
    return study.predict(torch, model, arrays)


def _replay(rows, days, bounds, actions, cost, counts, deadline):
    _tick(counts, "replay_calls", 1, deadline)
    return study.monthly.replay(rows, days, bounds, actions, cost, deadline=deadline)


def _counts():
    return dict(forward_calls=0, replay_calls=0, fits=0, new_weights=0, gpu=False)


def _base(contract, pin):
    return dict(
        name=NAME,
        contract_sha256=pin,
        criterion="descriptive_only_no_selection",
        scope=contract["config"]["scope"],
        runtime=contract["runtime"],
    )


def failure(contract, pin, reason, counts=None):
    require(
        reason
        in {
            "hard_timeout",
            "worker_failed",
            "worker_result_invalid",
            "execution_preempted",
            "runtime_or_invariant_failure",
        },
        "failure_reason",
    )
    return dict(
        _base(contract, pin),
        status="failed",
        reason=reason,
        compute=dict(_counts() if counts is None else counts),
        models=[],
        groups=[],
        cells=[],
        matched_checks=[],
    )


@study.monthly._decimal
def evaluate(torch, old_rows, new_rows, parent, contract, parent_contract, pin, counts, deadline):
    old_plan = dict(
        days=parent_contract["plan"]["days"], train=parent_contract["plan"]["train"], periods=[]
    )
    prepared = study.prepare(old_rows, old_plan)
    require(
        all(
            prepared[s, "TRAIN"]["arrays"] is not None
            and prepared[s, "TRAIN"]["facts"]["months"] == 132
            for s in SYMBOLS
        ),
        "TRAIN_gap",
    )
    plan, windows, rows = contract["plan"], {}, {}
    calendar = tuple(date.fromisoformat(d) for d in plan["days"])
    require(set(new_rows) == set(SYMBOLS), "new_symbol_scope")
    for symbol in SYMBOLS:
        rows[symbol] = {r.session_date.isoformat(): r for r in new_rows[symbol]}
        for window in plan["windows"]:
            record = study.inputs.build_adjusted_monthly_policy_inputs(
                new_rows[symbol],
                symbol=symbol,
                calendar=calendar,
                month_bounds=tuple(window["bounds"]),
            )
            windows[symbol, window["month"]] = study.math.prepare_monthly_utility_arrays((record,))
    predictions, training = {}, {}
    for model in contract["parent"]["models"]:
        architecture = model["architecture"]
        values = study.read_weights(parent / model["file"], architecture, model["weights_sha256"])
        first = study.rebuild_policy(torch, values, architecture)
        second = study.rebuild_policy(torch, values, architecture)
        for symbol in SYMBOLS:
            arrays = prepared[symbol, "TRAIN"]["arrays"]
            first_train = _predict(torch, first, arrays, counts, deadline)
            recovered = _predict(torch, second, arrays, counts, deadline)
            require(np.allclose(first_train, recovered, rtol=0, atol=1e-6), "TRAIN_reconstruction")
            training[architecture, symbol] = recovered
            for month in MONTHS:
                arrays = windows[symbol, month]
                a = _predict(torch, first, arrays, counts, deadline)
                b = _predict(torch, second, arrays, counts, deadline)
                require(np.allclose(a, b, rtol=0, atol=1e-6), "action_reconstruction")
                predictions[architecture, symbol, month] = Decimal(str(float(b[0])))
    # The pinned helper has exactly three passive and six managed TRAIN replays.
    _tick(counts, "replay_calls", 9, deadline)
    risks = study.risk_constants(prepared, old_plan, training, deadline=deadline)
    require(
        all(
            risks[s][a] is not None
            and digest(encode(str(risks[s][a]))) == contract["parent"]["risk_sha256"][s][a]
            for s in SYMBOLS
            for a in ARCHITECTURES
        ),
        "TRAIN_risk_changed",
    )
    groups, cells, checks = [], [], []
    for symbol in SYMBOLS:
        for window in plan["windows"]:
            month, bounds = window["month"], window["bounds"]
            groups.append(
                dict(
                    symbol=symbol,
                    month=month,
                    months=1,
                    sessions=bounds[1] - bounds[0],
                    training_months=132,
                    inputs_sha256=digest(encode([pin, symbol, window])),
                    risk_sha256=contract["parent"]["risk_sha256"][symbol],
                )
            )
            weights = {a: predictions[a, symbol, month] for a in ARCHITECTURES}
            weights.update({"riskmatched_" + a: risks[symbol][a] for a in ARCHITECTURES})
            weights.update(fixed_half=Decimal(".5"), always_long=Decimal(1), cash=Decimal(0))
            for cost in COSTS:
                batch, scores = [], {}
                for policy in POLICIES:
                    actions = {bounds[0]: weights[policy]}
                    score = _replay(
                        rows[symbol], plan["days"], bounds, actions, cost, counts, deadline
                    )
                    scores[policy] = score
                    cell = dict(
                        symbol=symbol,
                        month=month,
                        policy=policy,
                        cost_per_side_bps=cost,
                        action_sha256=digest(
                            encode([[plan["days"][bounds[0]], str(weights[policy].normalize())]])
                        ),
                        trades=score["trades"],
                        **{k: study.number(score[k]) for k in METRICS[:5]},
                    )
                    cell["net_utility"] = study.number(
                        Decimal(
                            str(
                                study.math.numpy_net_utility(
                                    np.asarray([float(v) for v in score["navs"]], dtype=np.float64)
                                )
                            )
                        )
                    )
                    batch.append(cell)
                for cell in batch:
                    for field, control in zip(METRICS[6:], batch[2:6], strict=True):
                        cell[field] = study.number(
                            Decimal(cell["final_nav"]) - Decimal(control["final_nav"])
                        )
                cells.extend(batch)
                for architecture in ARCHITECTURES:
                    constant = _replay(
                        rows[symbol],
                        plan["days"],
                        bounds,
                        dict.fromkeys([bounds[0]], weights[architecture]),
                        cost,
                        counts,
                        deadline,
                    )
                    require(constant == scores[architecture], "matched_identity")
                    reference = study.math.numpy_monthly_nav(
                        np.asarray([float(weights[architecture])]),
                        windows[symbol, month],
                        cost_bps=float(cost),
                    )
                    require(
                        np.allclose(
                            reference, [float(v) for v in constant["navs"]], rtol=1e-10, atol=1e-10
                        ),
                        "NumPy_ledger_parity",
                    )
                    cell = next(c for c in batch if c["policy"] == architecture)
                    checks.append(
                        dict(
                            symbol=symbol,
                            month=month,
                            architecture=architecture,
                            cost_per_side_bps=cost,
                            action_sha256=cell["action_sha256"],
                            status="passed",
                            exposure_matched=True,
                            turnover_matched=True,
                            cost_matched=True,
                            numpy_parity=True,
                        )
                    )
    result = dict(
        _base(contract, pin),
        status="complete",
        compute=dict(counts),
        models=contract["parent"]["models"],
        groups=groups,
        cells=cells,
        matched_checks=checks,
    )
    validate_result(result, contract, pin)
    return result


def _numeric(value):
    require(type(value) is str, "numeric_type")
    number = Decimal(value)
    require(number.is_finite(), "numeric_finite")
    return number


def validate_result(result, contract, pin):
    base = _base(contract, pin)
    _fields(
        result,
        (
            *base,
            "status",
            "compute",
            "models",
            "groups",
            "cells",
            "matched_checks",
            *(("reason",) if result.get("status") == "failed" else ()),
        ),
    )
    require(all(encode(result[k]) == encode(v) for k, v in base.items()), "result_binding")
    compute = result["compute"]
    _fields(compute, _counts())
    require(
        type(compute["gpu"]) is bool
        and not compute["gpu"]
        and all(
            type(compute[k]) is int and 0 <= compute[k] <= maximum
            for k, maximum in (
                ("forward_calls", 36),
                ("replay_calls", 171),
                ("fits", 0),
                ("new_weights", 0),
            )
        ),
        "compute_counts",
    )
    if result["status"] == "failed":
        require(
            encode(result) == encode(failure(contract, pin, result["reason"], compute)),
            "failure_shape",
        )
        return
    require(
        result["status"] == "complete"
        and compute["forward_calls"] == 36
        and compute["replay_calls"] == 171
        and encode(result["models"]) == encode(contract["parent"]["models"]),
        "complete_binding",
    )
    groups = [(s, m) for s in SYMBOLS for m in MONTHS]
    require([(g["symbol"], g["month"]) for g in result["groups"]] == groups, "group_matrix")
    for group in result["groups"]:
        window = next(w for w in contract["plan"]["windows"] if w["month"] == group["month"])
        expected = dict(
            symbol=group["symbol"],
            month=group["month"],
            months=1,
            sessions=window["bounds"][1] - window["bounds"][0],
            training_months=132,
            inputs_sha256=digest(encode([pin, group["symbol"], window])),
            risk_sha256=contract["parent"]["risk_sha256"][group["symbol"]],
        )
        require(encode(group) == encode(expected), "group_binding")
    cells = result["cells"]
    require(
        [(c["symbol"], c["month"], c["cost_per_side_bps"], c["policy"]) for c in cells]
        == [(s, m, c, p) for s, m in groups for c in COSTS for p in POLICIES],
        "cell_matrix",
    )
    paths, prior, by_key = {}, {}, {}
    for i, cell in enumerate(cells):
        _fields(
            cell,
            ("symbol", "month", "cost_per_side_bps", "policy", "action_sha256", "trades", *METRICS),
        )
        key = cell["symbol"], cell["month"], cell["policy"]
        require(
            _hash(cell["action_sha256"])
            and paths.setdefault(key, cell["action_sha256"]) == cell["action_sha256"],
            "cost_changes_actions",
        )
        values = {k: _numeric(cell[k]) for k in METRICS}
        nav, fees, turnover = (
            values["final_nav"],
            values["fees_initial_nav"],
            values["turnover_initial_nav"],
        )
        tolerance = Decimal("3e-11") * (1 + nav + fees + turnover)
        require(
            nav > 0
            and 0 <= values["max_close_drawdown"] <= 1
            and values["daily_return_std"] >= 0
            and fees >= 0
            and turnover >= 0
            and type(cell["trades"]) is int
            and 0 <= cell["trades"] <= 2,
            "metric_domain",
        )
        require(
            abs(fees - Decimal(cell["cost_per_side_bps"]) / 10000 * turnover) <= tolerance
            and nav <= prior.get(key, nav) + tolerance,
            "fee_cost_identity",
        )
        prior[key] = nav
        if cell["policy"] == "cash":
            require(
                nav == 1 and all(values[k] == 0 for k in METRICS[1:6]) and cell["trades"] == 0,
                "cash_identity",
            )
        start = i - i % len(POLICIES)
        for field, control in zip(METRICS[6:], cells[start + 2 : start + 6], strict=True):
            require(
                abs(nav - _numeric(control["final_nav"]) - values[field]) <= tolerance,
                "reference_consistency",
            )
        by_key[cell["symbol"], cell["month"], cell["cost_per_side_bps"], cell["policy"]] = cell
    checks = result["matched_checks"]
    require(
        [(c["symbol"], c["month"], c["cost_per_side_bps"], c["architecture"]) for c in checks]
        == [(s, m, c, a) for s, m in groups for c in COSTS for a in ARCHITECTURES],
        "check_matrix",
    )
    for check in checks:
        key = check["symbol"], check["month"], check["cost_per_side_bps"], check["architecture"]
        require(
            encode(check)
            == encode(
                dict(
                    symbol=key[0],
                    month=key[1],
                    cost_per_side_bps=key[2],
                    architecture=key[3],
                    action_sha256=by_key[key]["action_sha256"],
                    status="passed",
                    exposure_matched=True,
                    turnover_matched=True,
                    cost_matched=True,
                    numpy_parity=True,
                )
            ),
            "check_binding",
        )


def worker(artifact_root, market_data_root, pin, path, deadline):
    output, contract, parent_contract = verify(artifact_root, market_data_root, pin)
    require(
        path == output / "worker-result.json"
        and not path.exists()
        and not (output / "summary.json").exists(),
        "worker_path",
    )
    require(_json(output / "started.json") == dict(contract_sha256=pin), "attempt_binding")
    require(
        {p.name for p in output.iterdir()} == {"precommit.json", "started.json"}, "worker_directory"
    )
    counts = _counts()
    try:
        import torch

        require(str(torch.__version__) == contract["runtime"]["torch"], "Torch_runtime")
        torch.set_num_threads(2)
        torch.use_deterministic_algorithms(True)
        require(torch.get_num_threads() == 2, "Torch_threads")
        require(time.monotonic() < deadline, "hard_timeout")
        old_rows = _load_source(market_data_root, contract["parent"]["source"])
        new_rows = _load_source(market_data_root, contract["vintage"])
        parent, _ = _paths(artifact_root, market_data_root)
        result = evaluate(
            torch, old_rows, new_rows, parent, contract, parent_contract, pin, counts, deadline
        )
        verify(artifact_root, market_data_root, pin)
        for model in contract["parent"]["models"]:
            study.read_weights(
                parent / model["file"], model["architecture"], model["weights_sha256"]
            )
        require(
            {p.name for p in output.iterdir()} == {"precommit.json", "started.json"},
            "worker_directory",
        )
        require(time.monotonic() < deadline, "hard_timeout")
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure", counts)
    study.atomic_new(path, result)


def supervise(target, arguments, *, seconds):
    require(0 < seconds <= SECONDS, "supervisor_budget")
    existing = runpy.run_path(str(REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    return existing["supervise"](target, arguments, seconds=seconds, name=NAME)


def dispatch(artifact_root, market_data_root, pin):
    deadline = time.monotonic() + SECONDS
    output, contract, _ = verify(artifact_root, market_data_root, pin)
    require({p.name for p in output.iterdir()} == {"precommit.json"}, "attempt_already_exists")
    study.atomic_new(output / "started.json", dict(contract_sha256=pin))
    result = failure(contract, pin, "worker_failed")
    try:
        path = output / "worker-result.json"
        job = supervise(
            worker,
            (artifact_root, market_data_root, pin, path, deadline),
            seconds=deadline - time.monotonic(),
        )
        require(type(job["timed_out"]) is bool, "supervisor_result")
        if job["timed_out"]:
            result = failure(contract, pin, "hard_timeout")
        elif type(job["exit_code"]) is int and job["exit_code"] == 0:
            candidate = _json(path)
            validate_result(candidate, contract, pin)
            verify(artifact_root, market_data_root, pin)
            parent, _ = _paths(artifact_root, market_data_root)
            for model in contract["parent"]["models"]:
                study.read_weights(
                    parent / model["file"], model["architecture"], model["weights_sha256"]
                )
            require(
                {p.name for p in output.iterdir()}
                == {"precommit.json", "started.json", "worker-result.json"},
                "output_directory",
            )
            require(time.monotonic() < deadline, "hard_timeout")
            result = candidate
    except KeyboardInterrupt:
        result = failure(contract, pin, "execution_preempted")
    except Exception:
        result = failure(contract, pin, "worker_result_invalid")
    study.atomic_new(output / "summary.json", result)
    return dict(
        status=result["status"],
        contract_sha256=pin,
        summary_sha256=digest(encode(result)),
        cells=len(result["cells"]),
        matched_checks=len(result["matched_checks"]),
        fits=0,
        new_weights=0,
        gpu=False,
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_arguments")


def _interrupt(*_args):
    raise KeyboardInterrupt


def main(argv=None):
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--freeze", action="store_true")
        mode.add_argument("--run", action="store_true")
        parser.add_argument("--artifact-root", type=Path, default=Path("/artifacts"))
        parser.add_argument("--market-data-root", type=Path, default=Path("/market"))
        parser.add_argument("--vintage-snapshot")
        parser.add_argument("--vintage-manifest-sha256")
        parser.add_argument("--contract-sha256")
        args = parser.parse_args(argv)
        if not args.freeze and not args.run:
            result = dict(
                status="preview",
                image=IMAGE,
                windows=6,
                cells=126,
                matched_checks=36,
                fits=0,
                new_weights=0,
                gpu=False,
                wall_seconds=120,
                cpu_threads=2,
                memory_bytes=MEMORY_BYTES,
                network="none",
            )
        else:
            require(
                (
                    args.freeze
                    and args.vintage_snapshot
                    and args.vintage_manifest_sha256
                    and args.contract_sha256 is None
                )
                or (
                    args.run
                    and args.contract_sha256
                    and args.vintage_snapshot is None
                    and args.vintage_manifest_sha256 is None
                ),
                "mode_arguments",
            )
            previous = signal.signal(signal.SIGTERM, _interrupt)
            try:
                result = (
                    dict(
                        status="frozen_metadata_only",
                        contract_sha256=freeze(
                            args.artifact_root,
                            args.market_data_root,
                            args.vintage_snapshot,
                            args.vintage_manifest_sha256,
                        ),
                    )
                    if args.freeze
                    else dispatch(args.artifact_root, args.market_data_root, args.contract_sha256)
                )
            finally:
                signal.signal(signal.SIGTERM, previous)
    except (Exception, KeyboardInterrupt):
        result = dict(status="dispatch_unavailable", raw_error_suppressed=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] in {"preview", "frozen_metadata_only", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
