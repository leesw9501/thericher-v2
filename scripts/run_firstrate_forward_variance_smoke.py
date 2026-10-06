"""Freeze, run and reproduce one source/hash-bound target/input-only smoke."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from thericher_v2.contracts import Timeframe
from thericher_v2.data.firstrate_free_intraday_timeframe_mechanics import (
    parse_firstrate_normalization_receipt,
    validate_firstrate_canonical_bars,
)
from thericher_v2.data.local import LocalCsvBarProvider, bar_to_record
from thericher_v2.data.provider import BarQuery
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.forward_variance_smoke import (
    MINUTE,
    SYMBOLS,
    build_variance_smoke_case,
)
from thericher_v2.research.paired_completed_context import build_paired_completed_context

STUDY = "firstrate-forward-variance-target-input-smoke-20261006-v1"
PARENT_HASH = "sha256:a6559daab618ef3bdf208574a4da7984a3bc9f28d3d7d27e1229f15c99c18e09"
NORMALIZATION_HASH = "sha256:374fc885b831b6a2aea59526e25f918ebe568414b018b621452c02d608f988be"
DATE_HASH = "sha256:adcb51614f5ea08ddf02773444be6833d997861aeb700260d05f229febdd05e3"
IMAGE = "sha256:846a900b8e1488f5018fecee2024276fe8fd33a3235c0fef4232298b96b4616f"
SOURCES = {
    "QQQ": "sha256:27a6f601d41b7a96d38db663cc63c821471d511bbb196a88021acf81b8d92c3c",
    "SPY": "sha256:db797f4355dc3cd82113730e1689ee0750226b16568687d86b6ca3e407053777",
}
CANONICAL = "us_equities/firstrate_free_intraday/canonical/"
CODE = (
    "scripts/run_firstrate_forward_variance_smoke.py",
    "src/thericher_v2/research/forward_variance_smoke.py",
    "src/thericher_v2/research/intraday_variance_targets.py",
    "src/thericher_v2/research/paired_completed_context.py",
    "src/thericher_v2/research/firstrate_session_research.py",
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/market/resample.py",
    "src/thericher_v2/data/local.py",
    "src/thericher_v2/data/provider.py",
    "src/thericher_v2/data/resample.py",
    "src/thericher_v2/data/firstrate_free_intraday_timeframe_mechanics.py",
)
REPO = Path(__file__).resolve().parents[1]


class SmokeFault(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise SmokeFault(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_hash(path):
    with path.open("rb") as handle:
        return "sha256:" + hashlib.file_digest(handle, "sha256").hexdigest()


def regular_sessions(bars):
    # Same calendar geometry as the pinned legacy helper, without its execution imports.
    import pandas_market_calendars as calendars

    require(bool(bars), "empty_source")
    dates = [bar.start_ts.date() for bar in bars]
    schedule = calendars.get_calendar("NYSE").schedule(start_date=min(dates), end_date=max(dates))
    return tuple(
        (row.market_open.to_pydatetime(), row.market_close.to_pydatetime())
        for row in schedule.itertuples()
    )


def contract(code_pins):
    return {
        "study": STUDY,
        "grade": "revised_seen_development_target_input_preparation_only",
        "lineage_precommit_sha256": PARENT_HASH,
        "normalization_sha256": NORMALIZATION_HASH,
        "source_sha256": SOURCES,
        "scheduled_dates": 251,
        "scheduled_date_set_sha256": DATE_HASH,
        "calendar": "pandas-market-calendars==5.4.0 NYSE",
        "decisions": "one per scheduled day: min(open+150min, scheduled close-10min)",
        "input": "own/peer past120 completed M1 bars ending at decision; no future mask",
        "target": "one60min sum squared adjacent log OPEN differences; decision+1 entry",
        "target_availability": "61 exact complete M1 bars; final bar END at decision+62min",
        "missingness": "separate paired-input and symbol target outcomes on ALL scheduled keys; "
        "session/key/completion shortfalls only, no fill/drop/global future-completeness mask; "
        "unexpected identity/value/hash/geometry fault kills only this smoke",
        "splits": "none; no fit, selection, holdout access or predictive evaluation",
        "artifact_root": "D:/thericher-v2/model-artifacts/research/" + STUDY,
        "retention": "source-safe counts, categorical scheduled outcomes, separate commitments; "
        "no raw market rows, labels, predictions, prices or weights",
        "compute": {
            "cpu": 2,
            "seconds": 120,
            "memory_bytes": 2147483648,
            "network": "none",
            "inputs": "read_only",
            "image": IMAGE,
        },
        "kill_tests": [
            "exact lineage/normalization/source/code/calendar pins before and after",
            "every input equals prefix-only input and survives future removal",
            "first available plus five inherited edge dates: future value/completion "
            "edits preserve past input; target-only slice preserves target; "
            "missing/incomplete forward bar fails target, not input",
            "every available target has exact horizon/entry/end/available geometry",
            "all-RO replay exactly reproduces independent input/target commitments",
        ],
        "mutation_dates": ["2022-11-25", "2023-07-03", "2022-11-07", "2023-03-13", "2023-06-05"],
        "prohibited": {
            "fits": 0,
            "gpu": False,
            "selection": False,
            "holdout": False,
            "performance_claim": False,
            "paper_claim": False,
            "broker_calls": 0,
        },
        "limitations": [
            "seen/revised historical source; no independent replication",
            "inherited vendor timestamp/start convention assumed, not qualified",
            "corporate actions, finality and historical availability unproved",
            "251 shared session blocks, not502 independent ETF observations",
            "physical source parsing is not target-isolated; no predictive metrics",
        ],
        "code_sha256": code_pins,
    }


def check_metadata(lineage, normalization):
    require(digest(lineage.read_bytes()) == PARENT_HASH, "lineage_hash_mismatch")
    parent = json.loads(lineage.read_bytes())
    require(parent["scheduled_date_set_sha256"] == DATE_HASH, "scheduled_pin_mismatch")
    require(digest(normalization.read_bytes()) == NORMALIZATION_HASH, "normalization_hash_mismatch")
    specs = parse_firstrate_normalization_receipt(normalization.read_bytes())
    for spec in specs:
        relative = CANONICAL + spec.symbol + "_1m.csv"
        require(
            spec.canonical_market_data_relative_path.as_posix() == relative
            and spec.canonical_sha256 == SOURCES[spec.symbol]
            and spec.bar_count <= 250000,
            "normalization_source_binding",
        )
        require(
            parent["source_and_code_sha256"]["/market/" + relative] == SOURCES[spec.symbol],
            "lineage_source_binding",
        )
    for relative in CODE:
        old = parent["source_and_code_sha256"].get("/app/" + relative)
        if old is not None:
            require(file_hash(REPO / relative) == old, "inherited_code_changed")
    return specs


def check_pins(plan, market, lineage, normalization):
    require(
        plan == contract(plan["code_sha256"]) and set(plan["code_sha256"]) == set(CODE),
        "contract_changed",
    )
    specs = check_metadata(lineage, normalization)
    for relative, pin in plan["code_sha256"].items():
        require(file_hash(REPO / relative) == pin, "code_hash_mismatch")
    for spec in specs:
        path = market / spec.canonical_market_data_relative_path
        require(path.stat().st_size <= 134217728, "source_size_limit")
        require(file_hash(path) == SOURCES[spec.symbol], "source_hash_mismatch")
    return specs


def write_once(path, value):
    with path.open("xb") as handle:
        handle.write(encode(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def freeze(root, market, lineage, normalization):
    plan = contract({relative: file_hash(REPO / relative) for relative in CODE})
    check_pins(plan, market, lineage, normalization)
    root.mkdir(parents=True, exist_ok=False)
    write_once(root / "contract.json", plan)
    return {
        "status": "frozen_before_source_value_parse",
        "contract_sha256": file_hash(root / "contract.json"),
        "targets": 0,
    }


def compute(plan, market, lineage, normalization, deadline):
    def budget():
        require(time.monotonic() < deadline, "compute_stop")

    require(importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version")
    specs = check_pins(plan, market, lineage, normalization)
    source_counts, calendars, streams = {}, [], {}
    for spec in specs:
        budget()
        values = LocalCsvBarProvider(market / spec.canonical_market_data_relative_path).get_bars(
            BarQuery(symbol=spec.symbol, market="US", timeframe=Timeframe.M1)
        )
        validate_firstrate_canonical_bars(values, spec)
        source_counts[spec.symbol] = len(values)
        calendars.append(regular_sessions(values))
        streams[spec.symbol] = values
    require(calendars[0] == calendars[1], "source_calendar_mismatch")
    sessions = tuple(SessionWindow(*pair) for pair in calendars[0])
    dates = [session.open_ts.date().isoformat() for session in sessions]
    require(
        len(dates) == 251 and digest(("\n".join(dates) + "\n").encode()) == DATE_HASH,
        "scheduled_calendar_changed",
    )
    lookup = {session.open_ts.date(): session for session in sessions}
    grouped = {symbol: {day: [] for day in lookup} for symbol in SYMBOLS}
    for symbol, values in streams.items():
        for bar in values:
            session = lookup.get(bar.start_ts.date())
            if session is not None and session.open_ts <= bar.start_ts < session.close_ts:
                grouped[symbol][bar.start_ts.date()].append(bar)
    del streams, values
    input_counts, target_counts = Counter(), {symbol: Counter() for symbol in SYMBOLS}
    cross_counts, outcomes = Counter(), []
    input_hash, target_hash = hashlib.sha256(), hashlib.sha256()
    checks = Counter()
    exercised = False
    for session, day in zip(sessions, dates, strict=True):
        budget()
        pair = tuple(tuple(grouped[symbol][session.open_ts.date()]) for symbol in SYMBOLS)
        case = build_variance_smoke_case(*pair, session=session)
        input_counts[case.input_status] += 1
        input_payload = None
        if case.context is not None:
            context = case.context
            require(
                context.history_start == case.decision_at - 120 * MINUTE
                and context.completed_through == case.decision_at,
                "input_geometry",
            )
            input_payload = [
                [bar_to_record(bar) for bar in values]
                for values in (context.own_bars, context.peer_bars)
            ]
            args = dict(
                own_symbol="QQQ",
                peer_symbol="SPY",
                session=session,
                observed_at=case.decision_at,
                timeframe=Timeframe.M1,
                context_bars=120,
            )
            for start in (session.open_ts, context.history_start):
                prefix = tuple(
                    tuple(bar for bar in values if start <= bar.start_ts < case.decision_at)
                    for values in pair
                )
                require(
                    build_paired_completed_context(*prefix, **args) == context,
                    "future_dependent_input",
                )
                checks["prefix_and_future_removal"] += 1
        input_hash.update(encode([day, case.input_status, input_payload]))
        row = {"scheduled_date": day, "input_status": case.input_status, "targets": {}}
        for support in case.targets:
            target_counts[support.symbol][support.status] += 1
            cross_counts[case.input_status + "/" + support.symbol + "/" + support.status] += 1
            row["targets"][support.symbol] = support.status
            target = support.target
            payload = None
            if target is not None:
                require(
                    target.target_start == case.decision_at + MINUTE
                    and target.target_end == case.decision_at + 61 * MINUTE
                    and target.available_at == case.decision_at + 62 * MINUTE
                    and target.available_at <= session.close_ts,
                    "target_geometry",
                )
                payload = target.realized_variance.hex()
            target_hash.update(encode([day, support.symbol, support.status, payload]))
        outcomes.append(row)
        if not exercised or day in plan["mutation_dates"]:
            if case.context is not None:
                changed = tuple(
                    tuple(
                        replace(
                            bar,
                            open=bar.open * 3,
                            high=bar.high * 3,
                            low=bar.low * 3,
                            close=bar.close * 3,
                            volume=bar.volume * 7,
                            complete=False,
                        )
                        if bar.start_ts >= case.decision_at
                        else bar
                        for bar in values
                    )
                    for values in pair
                )
                mutated = build_variance_smoke_case(*changed, session=session)
                require(
                    mutated.context == case.context and mutated.input_status == case.input_status,
                    "future_mutation_changed_input",
                )
                checks["future_value_completion"] += 1
                for index, support in enumerate(case.targets):
                    if support.target is None:
                        continue
                    target_only = tuple(
                        tuple(
                            bar
                            for bar in values
                            if case.decision_at < bar.start_ts < case.decision_at + 62 * MINUTE
                        )
                        for values in pair
                    )
                    target_case = build_variance_smoke_case(*target_only, session=session)
                    require(target_case.targets[index] == support, "past_dependent_target")
                    checks["target_only"] += 1
                    for incomplete in (False, True):
                        edited = list(pair)
                        start = support.target.target_start
                        edited[index] = tuple(
                            replace(bar, complete=False)
                            if incomplete and bar.start_ts == start
                            else bar
                            for bar in pair[index]
                            if incomplete or bar.start_ts != start
                        )
                        missing = build_variance_smoke_case(*edited, session=session)
                        require(
                            missing.context == case.context
                            and missing.targets[index].status == "required_forward_m1_shortfall",
                            "target_missingness_changed_input",
                        )
                        checks["forward_missing_incomplete"] += 1
                exercised = True
    require(exercised, "no_available_input_mutation_case")
    budget()
    check_pins(plan, market, lineage, normalization)
    budget()
    return {
        "status": "target_input_smoke_verified",
        "grade": plan["grade"],
        "source_counts": source_counts,
        "regular_m1_counts": {
            symbol: sum(map(len, grouped[symbol].values())) for symbol in SYMBOLS
        },
        "scheduled_shared_days": len(dates),
        "paired_inputs": dict(input_counts),
        "targets": {symbol: dict(counts) for symbol, counts in target_counts.items()},
        "input_target_cross_counts": dict(cross_counts),
        "outcomes": outcomes,
        "input_commit_sha256": "sha256:" + input_hash.hexdigest(),
        "target_commit_sha256": "sha256:" + target_hash.hexdigest(),
        "mutation_checks": dict(checks),
        "raw_values_retained": False,
        "qualification": False,
        **plan["prohibited"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run", "verify"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    try:
        allowed = (Path("D:/thericher-v2/model-artifacts/research") / STUDY).resolve()
        allowed_roots = (allowed,) if os.name == "nt" else (Path("/study").resolve(),)
        require(args.artifact_root.resolve() in allowed_roots, "artifact_root_outside_scope")
        if args.mode == "freeze":
            result = freeze(args.artifact_root, args.market_root, args.lineage, args.normalization)
        else:
            raw = (args.artifact_root / "contract.json").read_bytes()
            plan = json.loads(raw)
            result = compute(
                plan, args.market_root, args.lineage, args.normalization, started + 120
            )
            result["contract_sha256"] = digest(raw)
            if args.mode == "run":
                write_once(args.artifact_root / "result.json", result)
            else:
                require(
                    json.loads((args.artifact_root / "result.json").read_bytes()) == result,
                    "readback_mismatch",
                )
            result = {key: value for key, value in result.items() if key != "outcomes"}
            result["status"] = "verified_all_ro" if args.mode == "verify" else result["status"]
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, SmokeFault) else "source_or_contract_reader_fault"
        print(
            json.dumps(
                {
                    "status": "input_unavailable",
                    "reason": reason,
                    "target_pass": False,
                    "raw_error_suppressed": True,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
