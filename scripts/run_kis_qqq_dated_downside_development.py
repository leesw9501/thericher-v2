"""One source-pinned CPU development attempt; parent owns mounts and dispatch."""

from __future__ import annotations

import importlib.metadata
import json
import runpy
import signal
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from thericher_v2.data import kis_paper_intraday as data  # noqa: E402
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN  # noqa: E402
from thericher_v2.execution.kis_private_intraday_backfill import (  # noqa: E402
    _validate_dated_qqq_state,
    kis_paper_qqq_dated_session_cache_root,
)
from thericher_v2.research import kis_qqq_dated_downside_development as r  # noqa: E402
from thericher_v2.research.campaign_registry import (  # noqa: E402
    register_campaign_outcome,
    register_frozen_campaign,
)

h = SimpleNamespace(
    **runpy.run_path(str(REPO / "scripts/run_tiingo_monthly_frozen_policy_readback.py"))
)
NAME, SECONDS = r.NAME, 120
INDEX_LIMIT = 8 * 1024**2
STAGES = ("cpu_smoke", "load", "prepare", "fit", "evaluate", "validate", "dispatch")
CODE = tuple(
    dict.fromkeys(
        (
            *h.CODE,
            "scripts/run_kis_qqq_dated_downside_development.py",
            "src/thericher_v2/research/kis_qqq_dated_downside_development.py",
            "src/thericher_v2/research/kis_equal_minute_resolution.py",
            "src/thericher_v2/research/kis_intraday_window_matrix.py",
            "src/thericher_v2/research/campaign_registry.py",
            "src/thericher_v2/contracts.py",
            "src/thericher_v2/data/kis_paper_intraday.py",
            "src/thericher_v2/data/kis_paper_intraday_index_metadata.py",
            "src/thericher_v2/data/local.py",
            "src/thericher_v2/data/resample.py",
            "src/thericher_v2/data/us_equity_session.py",
            "src/thericher_v2/execution/kis_market_data.py",
            "src/thericher_v2/execution/kis_private_intraday_backfill.py",
        )
    )
)
encode, digest, require, atomic = h.encode, h.digest, h.require, h.study.atomic_new


def configuration():
    return dict(r.configuration(), index_metadata_max_bytes=INDEX_LIMIT, image=h.IMAGE)


def runtime():
    versions = h.runtime_constraints()
    versions.update({p: importlib.metadata.version(p) for p in ("scikit-learn", "threadpoolctl")})
    major, minor = versions["scikit-learn"].split(".")[:2]
    require(major == "1" and int(minor) >= 7, "sklearn_runtime")
    return versions


def paths(artifacts, inputs):
    for root in (artifacts, inputs):
        h._unlinked_path(root)
        require(root.is_dir() and not root.resolve().is_relative_to(REPO), "external_root")
    require(
        not artifacts.resolve().is_relative_to(inputs.resolve())
        and not inputs.resolve().is_relative_to(artifacts.resolve()),
        "root_overlap",
    )
    output = artifacts / "research" / NAME
    h._unlinked_path(output.parent)
    require(output.parent.is_dir(), "research_root")
    if output.exists() or output.is_symlink():
        h._unlinked_path(output)
    return output


def source_metadata(inputs, pins, *, target=("QQQ", "NAS")):
    require(type(target) is tuple and target in (("QQQ", "NAS"), ("SPY", "AMS")), "target")
    require(
        type(pins) is dict
        and set(pins) == {str(d) for d in r.DATES}
        and all(h._hash(p) for p in pins.values()),
        "date_index_pins",
    )
    sources = []
    for day in r.DATES:
        relative = kis_paper_qqq_dated_session_cache_root(day, target=target).name
        root = inputs / relative / "v1"
        raw = h._read(root / "index.json", limit=INDEX_LIMIT)
        require(digest(raw) == pins[str(day)], "index_changed")
        index = json.loads(raw, object_pairs_hook=h._object, parse_constant=h._invalid_constant)
        metadata = data.validate_kis_paper_private_intraday_v1_index_metadata(
            index, expected_targets=(target,)
        )
        retained = metadata.targets[0]
        require(bool(retained.retained_chunks), "source_empty")
        observation = max(c.collected_at for c in retained.retained_chunks)
        _validate_dated_qqq_state(index, session_date=day, observed_at=observation, target=target)
        lineage, manifests, observed = [], {}, {}
        previous_minimum = None
        for chunk in retained.retained_chunks:
            instants = tuple(data._korea_timestamp_key_to_utc(stamp) for stamp, _ in chunk.rows)
            local = tuple(t.astimezone(US_EQUITY_EASTERN) for t in instants)
            require(
                all(
                    t.date() == day
                    and t.second == 0
                    and f"{day:%Y%m%d}000000"
                    < t.strftime("%Y%m%d%H%M%S")
                    <= chunk.input_cursor["keyb"]
                    for t in local
                )
                and all(t + r.MINUTE <= chunk.collected_at for t in instants)
                and chunk.output_cursor["keyb"]
                == (min(instants) - r.MINUTE).astimezone(US_EQUITY_EASTERN).strftime("%Y%m%d%H%M%S")
                and (previous_minimum is None or max(instants) < previous_minimum),
                "dated_chunk_frontier",
            )
            previous_minimum = min(instants)
            if not data._is_consumable_retained_chunk(
                outcome=chunk.outcome, reason=chunk.reason, conflict_origin=chunk.conflict_origin
            ):
                continue
            for (_stamp, fingerprint), instant in zip(chunk.rows, instants, strict=True):
                prior = observed.setdefault(instant, [fingerprint, False])
                require(prior[0] == fingerprint, "metadata_overlap_conflict")
                prior[1] |= data.raw_bar_end_is_complete(
                    start_ts=instant, collected_at=chunk.collected_at
                )
        session = r.us_equity_2026_session(day).window
        expected = {session.open_ts + i * r.MINUTE for i in range(390)}
        regular = {t for t in observed if session.open_ts <= t < session.close_ts}
        require(
            regular == expected and all(observed[t][1] for t in expected), "metadata_session_scope"
        )
        for chunk in index["targets"][0]["chunks"]:
            if chunk.get(
                "raw_market_data_retained"
            ) is not True or not data._is_consumable_retained_chunk(
                outcome=chunk.get("outcome"),
                reason=chunk.get("reason"),
                conflict_origin=chunk.get("conflict_origin"),
            ):
                continue
            path, manifest_pin, raw_pin = data._chunk_paths(root=root, chunk=chunk)
            manifest = h._json(path, manifest_pin)
            _, declared_raw = data._validate_manifest(
                manifest=manifest,
                target=data.KisPaperPrivateIntradayTarget(*target),
                chunk=chunk,
            )
            require(declared_raw == raw_pin, "manifest_raw_binding")
            rel = path.relative_to(root.resolve()).as_posix()
            require(rel not in manifests, "duplicate_manifest")
            manifests[rel] = dict(manifest_sha256=manifest_pin, raw_sha256=raw_pin)
            lineage.append(dict(manifest_hash=manifest_pin, raw_sha256=raw_pin))
        require(bool(lineage), "source_empty")
        sources.append(
            dict(
                date=str(day),
                root=relative,
                index_sha256=pins[str(day)],
                dataset_id=f"kis.paper.private.intraday.{target[0].lower()}.{target[1].lower()}.m1.v1",
                dataset_sha256=data._dataset_hash(index_bytes=raw, lineage=lineage),
                manifests=manifests,
            )
        )
    return sources


def proposed(inputs, pins):
    return dict(
        name=NAME,
        config=configuration(),
        runtime=runtime(),
        sources=source_metadata(inputs, pins),
        code_sha256={p: digest(h._read(REPO / p)) for p in CODE},
    )


def freeze(artifacts, inputs, pins):
    output = paths(artifacts, inputs)
    contract = proposed(inputs, pins)
    output.mkdir()
    h._unlinked_path(output)
    atomic(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["sources"])),
        split_hash=digest(encode(configuration())),
        cost_model_hash=digest(encode(r.COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=artifacts,
        repo_root=REPO,
    )
    return pin


def verify_contract(artifacts, inputs, pin):
    require(h._hash(pin), "contract_pin")
    output = paths(artifacts, inputs)
    contract = h._json(output / "precommit.json", pin)
    h._fields(contract, ("name", "config", "runtime", "sources", "code_sha256"))
    require(type(contract["sources"]) is list and len(contract["sources"]) == 20, "source_count")
    pins = {s["date"]: s["index_sha256"] for s in contract["sources"]}
    require(encode(contract) == encode(proposed(inputs, pins)), "contract_changed")
    return output, contract


def load_panel(inputs, contract):
    windows, catalogs = (), {}
    for source in contract["sources"]:
        day = date.fromisoformat(source["date"])
        catalog = data.load_verified_kis_paper_private_intraday_catalog(
            cache_root=inputs / source["root"],
            repo_root=REPO,
            symbol="QQQ",
            exchange="NAS",
            expected_index_metadata_sha256=source["index_sha256"],
        )
        require(
            catalog.dataset_id == source["dataset_id"]
            and catalog.dataset_hash == source["dataset_sha256"],
            "dataset_changed",
        )
        prepared = data.prepare_kis_paper_intraday_feature_input(catalog, session_dates=(day,))
        windows += r.build_windows(prepared)
        catalogs[day] = prepared.catalog
    r.check_cohort(windows)
    return windows, catalogs


def payoffs(windows, catalogs, dates):
    return tuple(
        r.gross_bps(w, catalogs[w.key.session_date]) for w in windows if w.key.session_date in dates
    )


def cohort_hash(windows):
    return digest(
        encode([[w.key.dataset_id, w.key.dataset_hash, w.key.cutoff.isoformat()] for w in windows])
    )


def failure(pin, phase, stage, counts="unobserved"):
    return dict(
        name=NAME,
        contract_sha256=pin,
        phase=phase,
        status="failed",
        failure_stage=stage,
        fits_started=counts,
    )


def validate_result(value, pin, phase):
    complete = value.get("status") == "complete"
    extra = ("smoke",) if phase == "cpu-smoke" else ("cohort_sha256", "evaluation")
    h._fields(
        value,
        (
            "name",
            "contract_sha256",
            "phase",
            "status",
            "fits_started",
            *(extra if complete else ("failure_stage",)),
        ),
    )
    require(
        value["name"] == NAME
        and value["contract_sha256"] == pin
        and value["phase"] == phase
        and phase in ("cpu-smoke", "cpu")
        and value["status"] in ("complete", "failed"),
        "result_binding",
    )
    counts = value["fits_started"]
    if not complete:
        require(
            type(value["failure_stage"]) is str and value["failure_stage"] in STAGES,
            "failure_stage",
        )
        if counts == "unobserved":
            return
    h._fields(counts, ("linear", "downside"))
    require(all(type(n) is int and 0 <= n <= 1 for n in counts.values()), "fit_counts")
    if not complete:
        return
    if phase == "cpu-smoke":
        require(
            counts == dict(linear=0, downside=0)
            and encode(value["smoke"])
            == encode(
                dict(synthetic_windows=80, synthetic_fits=4, actual_fits=0, cells=18, verified=True)
            ),
            "smoke_shape",
        )
    else:
        require(
            counts == dict(linear=1, downside=1) and h._hash(value["cohort_sha256"]),
            "complete_fits",
        )
        h._fields(value["evaluation"], ("daily", "cells", "descriptive"))
        require(
            type(value["evaluation"]["cells"]) is list and len(value["evaluation"]["cells"]) == 18,
            "cell_count",
        )


def verify_cpu(value, inputs, contract):
    windows, catalogs = load_panel(inputs, contract)
    require(value["cohort_sha256"] == cohort_hash(windows), "cohort_binding")
    r.verify_evaluation(
        windows,
        payoffs(windows, catalogs, r.TRAIN),
        payoffs(windows, catalogs, r.COMPARISON),
        value["evaluation"],
    )


def readback(artifacts, inputs, pin, summary_pin):
    require(h._hash(summary_pin), "summary_pin")
    output, contract = verify_contract(artifacts, inputs, pin)
    value = h._json(output / "cpu-summary.json", summary_pin)
    validate_result(value, pin, "cpu")
    if value["status"] == "complete":
        verify_cpu(value, inputs, contract)
        verify_contract(artifacts, inputs, pin)
    return dict(
        status="verified_" + value["status"],
        contract_sha256=pin,
        summary_sha256=summary_pin,
        cells=18 if value["status"] == "complete" else 0,
    )


def worker(artifacts, inputs, pin, phase, deadline):
    output, _ = verify_contract(artifacts, inputs, pin)
    require(h._json(output / (phase + "-started.json")) == dict(contract_sha256=pin), "attempt")
    counts, stage = dict(linear=0, downside=0), "cpu_smoke"
    try:
        if phase == "cpu-smoke":
            result = dict(smoke=r.cpu_smoke(deadline))
        else:
            stage = "load"
            _, contract = verify_contract(artifacts, inputs, pin)
            windows, catalogs = load_panel(inputs, contract)
            stage = "prepare"
            train = payoffs(windows, catalogs, r.TRAIN)
            stage = "fit"
            actions = r.fit_actions(windows, train, counts, deadline)
            stage = "evaluate"
            gross = payoffs(windows, catalogs, r.COMPARISON)
            evaluation = r.aggregate(windows, gross, actions)
            r.verify_evaluation(windows, train, gross, evaluation)
            result = dict(cohort_sha256=cohort_hash(windows), evaluation=evaluation)
        stage = "validate"
        result.update(
            name=NAME, contract_sha256=pin, phase=phase, status="complete", fits_started=counts
        )
        validate_result(result, pin, phase)
        verify_contract(artifacts, inputs, pin)
        require(time.monotonic() < deadline, "hard_timeout")
    except Exception:
        result = failure(pin, phase, stage, counts)
    atomic(output / (phase + "-worker.json"), result)


def dispatch(artifacts, inputs, pin, phase, smoke_pin=None):
    deadline = time.monotonic() + SECONDS
    output, _ = verify_contract(artifacts, inputs, pin)
    allowed = {"precommit.json"}
    if phase == "cpu":
        require(h._hash(smoke_pin), "smoke_pin")
        smoke = h._json(output / "cpu-smoke-summary.json", smoke_pin)
        validate_result(smoke, pin, "cpu-smoke")
        require(smoke["status"] == "complete", "smoke_incomplete")
        allowed |= {"cpu-smoke-started.json", "cpu-smoke-worker.json", "cpu-smoke-summary.json"}
    require(
        phase in ("cpu-smoke", "cpu") and {p.name for p in output.iterdir()} == allowed,
        "single_attempt",
    )
    supervisor = runpy.run_path(str(REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))[
        "supervise"
    ]
    atomic(output / (phase + "-started.json"), dict(contract_sha256=pin))
    result = failure(pin, phase, "dispatch")
    try:
        require(time.monotonic() < deadline, "hard_timeout")
        job = supervisor(
            worker,
            (artifacts, inputs, pin, phase, deadline),
            seconds=deadline - time.monotonic(),
            name=NAME + "-" + phase,
        )
        candidate = h._json(output / (phase + "-worker.json"))
        validate_result(candidate, pin, phase)
        result["fits_started"] = candidate["fits_started"]
        require(
            job["timed_out"] is False and type(job["exit_code"]) is int and job["exit_code"] == 0,
            "worker_failed",
        )
        _, contract = verify_contract(artifacts, inputs, pin)
        if phase == "cpu" and candidate["status"] == "complete":
            verify_cpu(candidate, inputs, contract)
            verify_contract(artifacts, inputs, pin)
        require(
            {p.name for p in output.iterdir()}
            == allowed | {phase + "-started.json", phase + "-worker.json"}
            and time.monotonic() < deadline,
            "output_changed",
        )
        result = candidate
    except (Exception, KeyboardInterrupt):
        pass
    validate_result(result, pin, phase)
    atomic(output / (phase + "-summary.json"), result)
    if phase == "cpu":
        register_campaign_outcome(
            contract_hash=pin,
            outcome_class="non_promoting_completed"
            if result["status"] == "complete"
            else "non_promoting_failed",
            outcome_reference_sha256=digest(encode(result)),
            artifact_root=artifacts,
            repo_root=REPO,
        )
    return dict(
        status=result["status"],
        phase=phase,
        contract_sha256=pin,
        summary_sha256=digest(encode(result)),
        fits_started=result["fits_started"],
        cells=18 if phase == "cpu" and result["status"] == "complete" else 0,
    )


def main(argv=None):
    try:
        parser = h._Parser(description=__doc__, allow_abbrev=False)
        mode = parser.add_mutually_exclusive_group()
        for flag in ("freeze", "cpu-smoke", "cpu", "verify"):
            mode.add_argument("--" + flag, action="store_true")
        parser.add_argument("--artifact-root", type=Path, default=Path("/artifacts"))
        parser.add_argument("--input-root", type=Path, default=Path("/input"))
        parser.add_argument("--index-pins", type=Path)
        parser.add_argument("--contract-sha256")
        parser.add_argument("--smoke-summary-sha256")
        parser.add_argument("--summary-sha256")
        args = parser.parse_args(argv)
        if not any((args.freeze, args.cpu_smoke, args.cpu, args.verify)):
            result = dict(
                status="preview",
                cells=18,
                fits=2,
                gpu=False,
                image=h.IMAGE,
                wall_seconds=120,
                cpu_threads=2,
                memory_bytes=2 * 1024**3,
                network="none",
            )
        else:
            require(
                (args.freeze and args.index_pins is not None and args.contract_sha256 is None)
                or (not args.freeze and args.index_pins is None and h._hash(args.contract_sha256)),
                "mode_arguments",
            )
            require(
                (args.cpu and h._hash(args.smoke_summary_sha256))
                or (not args.cpu and args.smoke_summary_sha256 is None),
                "smoke_arguments",
            )
            require(
                (args.verify and h._hash(args.summary_sha256))
                or (not args.verify and args.summary_sha256 is None),
                "summary_arguments",
            )
            if args.freeze:
                result = dict(
                    status="frozen_metadata_only",
                    contract_sha256=freeze(
                        args.artifact_root, args.input_root, h._json(args.index_pins)
                    ),
                )
            elif args.verify:
                result = readback(
                    args.artifact_root, args.input_root, args.contract_sha256, args.summary_sha256
                )
            else:
                previous = signal.signal(signal.SIGTERM, h._interrupt)
                try:
                    result = dispatch(
                        args.artifact_root,
                        args.input_root,
                        args.contract_sha256,
                        "cpu-smoke" if args.cpu_smoke else "cpu",
                        args.smoke_summary_sha256,
                    )
                finally:
                    signal.signal(signal.SIGTERM, previous)
    except (Exception, KeyboardInterrupt):
        result = dict(status="unavailable", raw_error_suppressed=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    return (
        0
        if result["status"] in ("preview", "frozen_metadata_only", "complete", "verified_complete")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
