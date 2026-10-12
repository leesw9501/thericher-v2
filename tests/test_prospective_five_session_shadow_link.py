"""Synthetic metadata only: no provider, filesystem callback or numeric input."""

import hashlib
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import PureWindowsPath

import pytest

from thericher_v2.data import prospective_five_session_shadow_link as s


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


P = "sha256:" + "a" * 64


def path(root, *parts):
    return str(PureWindowsPath(root).joinpath(*parts))


@pytest.fixture
def chain():
    keys = [f"S{i:04d}/NAS" for i in range(512)]
    metadata = {
        "keys": keys,
        "original_target_keys": keys[:128],
        "scheduled_dates": ["2026-09-18"]
        + [f"2026-10-{i:02d}" for i in range(1, 20)]
        + ["2026-10-16"],
        "calendar26_sha256": P,
    }
    # Twenty-one exact synthetic slots; actual calendar is caller-frozen control.
    metadata["scheduled_dates"] = metadata["scheduled_dates"][:20] + ["2026-10-16"]
    hosts = {path("C:/Users/Public/Documents/thericher-v2", "src", "fixture.py"): P}
    data = {
        "kind": s._KIND,
        "cache_root": s._CACHE,
        "anchor": "20261016",
        "opportunity": {"not_before_utc": s._START, "end_utc": s._DATA_END},
        "metadata": metadata,
        "source_pins": hosts,
        "reference_inputs": {},
        "budget": {
            "worker_seconds": 900,
            "cleanup_seconds": 120,
            "publication_seconds": 180,
            "whole_seconds": 1200,
        },
        "limitations": ["synthetic"],
    }
    data_raw = encode(data)
    dp = sha(data_raw)
    aliases = {
        "/data-source/common.py": next(iter(hosts)),
        "/worker/shadow_worker.py": path(s._A, "worker.py"),
        "/dataset/manifest.json": path(s._CACHE, "view", "manifest.json"),
        "/dataset/bars.csv.gz": path(s._CACHE, "view", "bars.csv.gz"),
    }
    template = {
        "input_plan_sha256": dp,
        "input_metadata_sha256": sha(encode(metadata)),
        "runtime_image": P,
        "input_manifest_sha256": None,
        "fits": 0,
        "broker_calls": 0,
        "max_inference_calls": 1,
        "entry_valid_until": "2026-10-19T13:40:00+00:00",
        "pins": {k: None if k.startswith("/dataset/") else P for k in aliases},
        "host_paths": aliases,
        "data_source_paths": {next(iter(hosts)): "/data-source/common.py"},
    }
    template_raw = encode(template)
    sources = {
        **hosts,
        path(s._DATA, "plan.json"): dp,
        path(s._ROOT, "engine-template.json"): sha(template_raw),
        path(s._DATA, "guard.py"): P,
        path(s._A, "worker.py"): P,
    }
    job = {
        "kind": "prospective512_shadow_delivery_job_v1",
        "company_objective": s._GOAL,
        "root": s._ROOT,
        "start_utc": s._START,
        "end_utc": s._END,
        "broker_calls": 0,
        "private_bank_access": False,
        "existing_opportunities_changed": False,
        "source_pins": sources,
        "runtime_image": P,
        "data": {"clock_guard_path": path(s._DATA, "guard.py")},
        "engine": {"template_path": path(s._ROOT, "engine-template.json"), "fixed_inputs": {}},
    }
    job_raw = encode(job)
    controls = s.ShadowControls(
        job_raw, data_raw, template_raw, sha(job_raw), dp, sha(template_raw)
    )
    inv = "1" * 32
    out = path(s._ROOT, "runtime", inv)
    attempt = path(s._DATA, "attempt-" + "2" * 32)

    def clock(hm):
        return f"2026-10-16T{hm}:00+00:00"

    claim = {
        "job_sha256": controls.job_sha,
        "started_at_utc": clock("21:15"),
        "invocation_id": inv,
        "output_root": out,
        "terminal_receipt_path": path(out, "receipt.json"),
    }
    docs = {"claim": claim, "job": job, "data": data, "template": template}
    records = {}

    def put(p, value):
        raw = encode(value)
        records[p] = raw
        return sha(raw)

    chunks = []
    for i, key in enumerate(keys):
        physical = {
            "scope_started_at_utc": clock("21:15"),
            "requests": [
                {
                    "request_started_at_utc": clock("21:15"),
                    "response_completed_at_utc": clock("21:15"),
                    "transport_clock": {
                        "request_started_at_utc": clock("21:15"),
                        "response_completed_at_utc": clock("21:15"),
                    },
                }
            ],
            "chunk_write_started_at_utc": clock("21:15"),
            "chunk_write_completed_at_utc": None,
            "legacy_collected_at_semantics": "scope_start_not_response_completion",
        }
        chunk = {
            "kind": "kis_paper_private_daily_cache",
            "immutable_snapshot": True,
            "code_revision": dp,
            "collector_version": s._KIND,
            "collector_objective_id": s._KIND,
            "source": {
                "symbol": key.split("/")[0],
                "exchange": "NAS",
                "endpoint": "dailyprice",
                "adjustment_mode": "MODP=0_unadjusted",
            },
            "requested_date_bounds": {"initial_anchor_bymd": "20261016"},
            "requested_scope": {
                "floor_session": "2026-09-18",
                "anchor_session": "2026-10-16",
                "session_count": 21,
                "provider_continuation_preserved": True,
            },
            "physical_capture": deepcopy(physical),
            "collected_at_utc": clock("21:15"),
            "requests": {"accepted_pages": 1, "page_attempts": 1},
        }
        cp, pp = f"snapshot={i}/manifest.json", f"snapshot={i}/physical-capture.json"
        ch = put(path(s._CACHE, *cp.split("/")), chunk)
        physical.update(manifest_sha256=ch, chunk_write_completed_at_utc=clock("21:15"))
        ph = put(path(s._CACHE, *pp.split("/")), physical)
        chunks.append(
            {
                "key": key,
                "state": "full",
                "needed_rows": 21,
                "chunk": {"path": cp, "sha256": ch},
                "physical_capture": {"path": pp, "sha256": ph},
            }
        )
    manifest = {
        "kind": s._KIND,
        "plan_sha256": dp,
        "metadata": metadata,
        "source_pins": hosts,
        "source_chunks": chunks,
        "captured_at_utc": clock("21:16"),
        "physical_capture": {"meaning": "actual"},
        "availability": "assumed_not_observed",
        "row_counts": dict.fromkeys(keys, 21),
        "logical_record_sha256": dict.fromkeys(keys, P),
        "record_count": 10752,
        "grid_count": 10752,
        "no_key_filter_or_replacement": True,
        "limitations": ["synthetic"],
        "packed": {"path": "bars.csv.gz", "sha256": P, "size_bytes": 100},
    }
    epoch = datetime.fromisoformat(clock("21:15")).timestamp()
    runtime = {"kind": s._KIND, "plan_sha256": dp, "epoch": epoch, "budget": data["budget"]}
    rh = put(path(s._DATA, "runtime-contract.json"), runtime)
    started = {
        "kind": s._KIND,
        "plan_sha256": dp,
        "epoch": epoch,
        "started_at_utc": clock("21:15"),
        "phase": "source_preflight",
        "opportunity_end_utc": s._DATA_END,
    }
    put(path(attempt, "started.json"), started)
    worker = dict.fromkeys(s._WORKER_FIELDS, 0)
    worker.update(
        status="current_input_serialized",
        plan_sha256=dp,
        runtime_contract_sha256=rh,
        raw_stdout_retained=False,
        materialization_completed_at_utc=clock("21:17"),
        packed_sha256=P,
        target_count=512,
        calendar_count=21,
        grid_count=10752,
        record_count=10752,
        full_targets=512,
        sparse_targets=0,
        empty_targets=0,
        supported=True,
        eligible_count=512,
        frame_sha256="a" * 64,
        availability="assumed_not_observed",
        qualification=False,
        elapsed_seconds=120,
        cursor_sha256=P,
        position=512,
        daily_attempts=512,
        accepted_pages=512,
        categories={"requested_scope_complete": 512},
        next_due=None,
        delegate_starts=512,
        minimum_delegate_gap_seconds=1.25,
        first_page_needed_rows=10752,
        first_page_floor_targets=512,
        final_source_audit_passed=True,
    )
    direct = {
        **worker,
        "direct_receipt_path": path(attempt, "receipt.json"),
        "owned_tree": {
            "timed_out": False,
            "root_exit_code": 0,
            "root_reaped": True,
            "tree_reaped": True,
            "active_processes_after_reap": 0,
        },
        "worker_receipt_sha256": P,
        "whole_elapsed_seconds": 121,
    }
    handoff = {
        "kind": "prospective512_data_child_handoff_v1",
        "job_sha256": controls.job_sha,
        "plan_sha256": dp,
        "direct_receipt_path": path(attempt, "receipt.json"),
        "direct_receipt_sha256": P,
        "actual_started_at_utc": clock("21:15"),
        "actual_completed_at_utc": clock("21:18"),
        "source_pins_sha256": sha(encode(sources)),
    }
    plan = deepcopy(template)
    result = dict.fromkeys(s._RESULT_FIELDS, 0)
    result.update(
        status="prepared",
        reason="synthetic",
        phase="complete",
        fit_calls=0,
        broker_calls=0,
        inference_calls=1,
        shadow_only=True,
        worker_started_at=clock("21:18"),
        worker_sha256=P,
        source_count=len(plan["pins"]),
        data_source_count=1,
        input_plan_sha256=dp,
        input_metadata_sha256=sha(encode(metadata)),
        physical_capture_sha256=sha(encode(manifest["physical_capture"])),
        input_captured_at=manifest["captured_at_utc"],
        calendar26_sha256=P,
        identity_count=512,
        supported=True,
        eligible_count=512,
        original_eligible=128,
        added_eligible=384,
        frame_sha256=P,
        complete_prior21_count=512,
        inference_completed_at=clock("21:19"),
        decision={"opaque": True},
        sources_reattested=True,
        elapsed_seconds=60,
        completed_at=clock("21:19"),
        order_consumer=False,
        exposure_units="fraction_of_original_shared_basis",
        calendar_validation="Data_pinned_21plus5_not_regenerated_in_worker",
        availability="assumed_not_observed",
        raw_rows_retained=False,
        scores_retained=False,
        model_dump_retained=False,
    )
    terminal = {
        "status": "shadow_precommit_delivered",
        "job_sha256": controls.job_sha,
        "invocation_id": inv,
        "claim_sha256": P,
        "actual_started_at_utc": claim["started_at_utc"],
        "data_status": "input_ready",
        "broker_calls": 0,
        "fits": 0,
        "inference_calls": 1,
        "future_monday_runtime": "not_observed",
        "data": {
            "status": "input_ready",
            "completed_at_utc": worker["materialization_completed_at_utc"],
            "receipt_sha256": P,
            "inference_calls": 0,
        },
        "clock_guard_sha256": P,
        "inference_attempt_status": "worker_reported",
        "engine": {
            "status": "shadow_precommit_created",
            "completed_at_utc": result["completed_at"],
            "receipt_sha256": P,
            "inference_calls": 1,
        },
        "actual_completed_at_utc": clock("21:20"),
    }
    docs.update(
        manifest=manifest,
        worker=worker,
        direct=direct,
        handoff=handoff,
        plan=plan,
        result=result,
        terminal=terminal,
    )

    def seal():
        claim_raw = encode(claim)
        put(path(s._ROOT, "runtime", "opportunity.claim.json"), claim)
        mh = put(path(s._CACHE, "view", "manifest.json"), manifest)
        worker["manifest_sha256"] = mh
        direct.update(worker)
        direct["worker_receipt_sha256"] = put(path(attempt, "worker-receipt.json"), worker)
        dh = put(path(attempt, "receipt.json"), direct)
        handoff["direct_receipt_sha256"] = dh
        put(path(out, "data-process", "handoff.json"), handoff)
        plan["input_manifest_sha256"] = mh
        plan["pins"].update(
            {"/dataset/manifest.json": mh, "/dataset/bars.csv.gz": worker["packed_sha256"]}
        )
        eh = put(path(out, "engine-plan.json"), plan)
        put(path(out, "engine-attempt.claim.json"), {"plan_sha256": eh})
        result.update(
            plan_sha256=eh,
            input_manifest_sha256=mh,
            source_pins_sha256=sha(encode(plan["pins"])),
            source_chunks_sha256=sha(encode(manifest["source_chunks"])),
        )
        rr = put(path(out, "engine-output", "result.json"), result)
        terminal["claim_sha256"] = sha(claim_raw)
        terminal["data"]["receipt_sha256"] = dh
        terminal["engine"]["receipt_sha256"] = rr
        put(path(out, "receipt.json"), terminal)
        return claim_raw

    calls = []

    def read(p, cap):
        calls.append(p)
        assert p.endswith(".json") and PureWindowsPath(p).drive == "D:"
        raw = records[p]
        assert len(raw) <= cap
        return raw

    return docs, records, controls, seal, read, calls


def bind(chain):
    _, _, controls, seal, read, _ = chain
    return s.verify_shadow_link(
        seal(),
        controls=controls,
        read_metadata=read,
        observed_at=datetime(2026, 10, 16, 21, 21, tzinfo=UTC),
    )


def test_complete_exact_map_and_immutable_facts(chain):
    fact = bind(chain)
    expected = fact.expected_engine_links()
    assert len(expected) == 15
    assert expected["result_sha256"] == fact.engine_result_sha
    assert expected["plan_sha256"] == fact.engine_plan_sha
    expected["source_count"] = 999
    assert fact.expected_engine_links()["source_count"] == 4
    with pytest.raises(FrozenInstanceError):
        fact.job_sha = P
    assert len(fact.metadata_links) == 1035
    assert all(p.endswith(".json") for p in chain[-1])


@pytest.mark.parametrize(
    "record,key,value",
    [
        ("terminal", "status", "retained_failure"),
        ("terminal", "invocation_id", "3" * 32),
        ("terminal", "extra", 1),
        ("terminal", "inference_calls", True),
        ("terminal", "actual_completed_at_utc", "2026-10-16T21:46:00+00:00"),
        ("handoff", "source_pins_sha256", P),
        ("handoff", "extra", 1),
        ("handoff", "direct_receipt_path", path(s._DATA, "attempt-" + "3" * 32, "receipt.json")),
        ("claim", "output_root", path(s._ROOT, "runtime", "3" * 32)),
        ("manifest", "extra", 1),
        ("worker", "accepted_pages", True),
        ("worker", "final_source_audit_passed", False),
        ("worker", "packed_sha256", "sha256:" + "b" * 64),
        ("result", "inference_calls", 0),
        ("result", "extra", 1),
        ("result", "worker_started_at", "2026-10-16T21:14:00+00:00"),
        ("result", "inference_completed_at", "2026-10-16T21:46:00+00:00"),
        ("plan", "fits", 1),
    ],
)
def test_semantic_mutations_rejected_after_hash_rebinding(chain, record, key, value):
    chain[0][record][key] = value
    with pytest.raises(s.ShadowLinkError):
        bind(chain)


def test_reordered_identities_rejected(chain):
    chain[0]["manifest"]["source_chunks"].reverse()
    with pytest.raises(s.ShadowLinkError, match="identity_order"):
        bind(chain)


@pytest.mark.parametrize("failure", ["missing", "changed", "duplicate", "nan", "readback"])
def test_partial_changed_and_noncanonical_metadata(chain, failure):
    _, records, controls, seal, read, _ = chain
    raw = seal()
    terminal_path = path(s._ROOT, "runtime", "1" * 32, "receipt.json")
    if failure == "missing":
        del records[terminal_path]
    elif failure == "changed":
        records[terminal_path] = records[terminal_path].replace(
            b"worker_reported", b"worker_unknown!"
        )
    elif failure == "duplicate":
        records[terminal_path] = b'{"status":1,"status":2}'
    elif failure == "nan":
        records[terminal_path] = b'{"bad":NaN}'
    else:
        counts = {}
        base = read

        def read(p, cap):
            counts[p] = counts.get(p, 0) + 1
            value = base(p, cap)
            return value + b" " if counts[p] > 1 else value

    with pytest.raises(s.ShadowLinkError):
        s.verify_shadow_link(
            raw,
            controls=controls,
            read_metadata=read,
            observed_at=datetime(2026, 10, 16, 21, 21, tzinfo=UTC),
        )


def test_pinned_control_preflight_c_drive_and_traversal(chain):
    controls = chain[2]
    assert dict(s.validate_shadow_controls(controls))["source_count"] == 5
    bad = json.loads(controls.job_bytes)
    bad["source_pins"]["C:/Users/Public/Documents/../secret.py"] = P
    raw = encode(bad)
    new = s.ShadowControls(
        raw,
        controls.data_plan_bytes,
        controls.engine_template_bytes,
        sha(raw),
        controls.data_plan_sha,
        controls.engine_template_sha,
    )
    with pytest.raises(s.ShadowLinkError, match="path_invalid"):
        s.validate_shadow_controls(new)


def test_original_non_utc_entry_template_is_scoped_contradiction(chain):
    controls = chain[2]
    template = json.loads(controls.engine_template_bytes)
    template["entry_valid_until"] = "2026-10-19T22:30:00+09:00"
    traw = encode(template)
    job = json.loads(controls.job_bytes)
    job["source_pins"][path(s._ROOT, "engine-template.json")] = sha(traw)
    jraw = encode(job)
    new = s.ShadowControls(
        jraw, controls.data_plan_bytes, traw, sha(jraw), controls.data_plan_sha, sha(traw)
    )
    with pytest.raises(s.ShadowLinkError, match="clock_invalid"):
        s.validate_shadow_controls(new)


def test_pinned_copy_alias_preserves_original_c_source_identity(chain):
    controls = chain[2]
    template = json.loads(controls.engine_template_bytes)
    old = template["host_paths"]["/data-source/common.py"]
    newhost = path(s._A, "frozen", "fixture.py")
    template["host_paths"]["/data-source/common.py"] = newhost
    traw = encode(template)
    job = json.loads(controls.job_bytes)
    job["source_pins"].pop(old)
    job["source_pins"][newhost] = P
    job["source_pins"][path(s._ROOT, "engine-template.json")] = sha(traw)
    jraw = encode(job)
    new = s.ShadowControls(
        jraw, controls.data_plan_bytes, traw, sha(jraw), controls.data_plan_sha, sha(traw)
    )
    assert dict(s.validate_shadow_controls(new))["source_count"] == 5
    job["source_pins"][newhost] = "sha256:" + "b" * 64
    jraw = encode(job)
    bad = s.ShadowControls(
        jraw, controls.data_plan_bytes, traw, sha(jraw), controls.data_plan_sha, sha(traw)
    )
    with pytest.raises(s.ShadowLinkError, match="data_source_binding"):
        s.validate_shadow_controls(bad)


def recovery_chain(chain):
    """New controls, same exact original opportunity/attempt namespace."""
    docs, records, controls, seal, read, calls = chain
    job = deepcopy(docs["job"])
    oldtemplate = job["engine"]["template_path"]
    newtemplate = path(s._R3_ROOT, "engine-template.json")
    job["root"] = s._R3_ROOT
    job["engine"]["template_path"] = newtemplate
    job["source_pins"][newtemplate] = job["source_pins"].pop(oldtemplate)
    job["lineage"] = {
        "original_root": s._ROOT,
        "original_job_sha256": s._ORIGINAL_JOB_SHA,
        "original_installation_plan_sha256": s._ORIGINAL_INSTALLATION_SHA,
        "attempt_root": path(s._ROOT, "runtime"),
    }
    jobraw = encode(job)
    newcontrols = replace(
        controls, job_bytes=jobraw, job_sha=sha(jobraw), expected_delivery_root=s._R3_ROOT
    )
    docs["job"] = job
    for name in ("claim", "terminal", "handoff"):
        docs[name]["job_sha256"] = newcontrols.job_sha
    for name in ("claim", "terminal"):
        docs[name]["original_job_sha256"] = s._ORIGINAL_JOB_SHA
    docs["handoff"]["source_pins_sha256"] = sha(encode(job["source_pins"]))
    return docs, records, newcontrols, seal, read, calls


@pytest.fixture
def r3_chain(chain):
    return recovery_chain(chain)


def test_r3_chain_requires_explicit_caller_frozen_root(r3_chain):
    _, _, controls, seal, read, calls = r3_chain
    claimraw = seal()
    with pytest.raises(s.ShadowLinkError, match="job_scope"):
        s.verify_shadow_link(
            claimraw,
            controls=replace(controls, expected_delivery_root=s._ROOT),
            read_metadata=read,
            observed_at=datetime(2026, 10, 16, 21, 21, tzinfo=UTC),
        )
    assert calls == []
    fact = bind(r3_chain)
    assert fact.job_sha == controls.job_sha
    assert len(fact.expected_engine_links()) == 15
    assert fact.expected_engine_links()["result_sha256"] == fact.engine_result_sha
    runtime = PureWindowsPath(path(s._ROOT, "runtime"))
    assert any(PureWindowsPath(p).is_relative_to(runtime) for p in calls)
    assert not any(PureWindowsPath(p).is_relative_to(PureWindowsPath(s._R3_ROOT)) for p in calls)
    assert dict(s.validate_shadow_controls(controls))["expected_attempt_root"] == str(runtime)


@pytest.mark.parametrize(
    "change",
    ["missing", "extra", "oldroot", "oldjob", "oldplan", "attempt", "traversal", "source"],
)
def test_r3_control_lineage_kills_before_metadata_callback(r3_chain, change):
    docs, _, controls, _, _, calls = r3_chain
    job = deepcopy(docs["job"])
    lineage = job["lineage"]
    if change == "missing":
        job.pop("lineage")
    elif change == "extra":
        lineage["latest"] = True
    elif change == "oldroot":
        lineage["original_root"] = s._R3_ROOT
    elif change == "oldjob":
        lineage["original_job_sha256"] = P
    elif change == "oldplan":
        lineage["original_installation_plan_sha256"] = P
    elif change == "attempt":
        lineage["attempt_root"] = path(s._R3_ROOT, "runtime")
    elif change == "traversal":
        lineage["attempt_root"] = s._ROOT + "/../delivery-r2/runtime"
    else:
        host = next(iter(json.loads(controls.data_plan_bytes)["source_pins"]))
        job["source_pins"][host] = "sha256:" + "b" * 64
    raw = encode(job)
    with pytest.raises(s.ShadowLinkError):
        s.validate_shadow_controls(replace(controls, job_bytes=raw, job_sha=sha(raw)))
    assert calls == []


@pytest.mark.parametrize("record", ["claim", "terminal"])
@pytest.mark.parametrize("change", ["missing", "wrong", "extra"])
def test_r3_claim_terminal_original_job_binding(r3_chain, record, change):
    value = r3_chain[0][record]
    if change == "missing":
        value.pop("original_job_sha256")
    elif change == "wrong":
        value["original_job_sha256"] = P
    else:
        value["original_root"] = s._ROOT
    with pytest.raises(s.ShadowLinkError):
        bind(r3_chain)


def test_r3_source_root_cannot_replace_original_attempt_root(r3_chain):
    claim = r3_chain[0]["claim"]
    claim["output_root"] = path(s._R3_ROOT, "runtime", claim["invocation_id"])
    claim["terminal_receipt_path"] = path(claim["output_root"], "receipt.json")
    with pytest.raises(s.ShadowLinkError, match="claim_binding"):
        bind(r3_chain)


@pytest.mark.parametrize(
    "root",
    [
        f"{s._A}/research/{s._GOAL}/delivery-r5",
        f"{s._A}/research/other-objective/delivery-r3",
    ],
)
def test_unassigned_delivery_namespace_rejected_before_callback(chain, root):
    with pytest.raises(s.ShadowLinkError, match="delivery_root_invalid"):
        s.validate_shadow_controls(replace(chain[2], expected_delivery_root=root))
