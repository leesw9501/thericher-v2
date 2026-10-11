"""Portable complete SYN custody; no D: fixtures, numerical inputs or inference."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Context, localcontext
from pathlib import Path, PureWindowsPath

import pytest

import test_prospective_five_session_shadow_decision as dto_fixture
import test_prospective_five_session_shadow_link as link_fixture
from thericher_v2.contracts import decision_instrument_binding_ref
from thericher_v2.data import prospective_five_session_shadow_link as data_link
from thericher_v2.research import prospective_five_session_shadow_decision as restore
from thericher_v2.research import prospective_five_session_shadow_input as s
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

MONDAY = datetime(2026, 10, 19, 13, 35, tzinfo=UTC)
FRIDAY = datetime(2026, 10, 16, 21, 27, tzinfo=UTC)


@pytest.fixture
def chain(monkeypatch):
    # Existing portable fixtures provide all 512 ordered physical metadata pairs.
    docs, records, old, seal, read, calls = link_fixture.recovery_chain(
        link_fixture.chain.__wrapped__()
    )
    result, clocks, dto = dto_fixture.packet.__wrapped__(monkeypatch)
    metadata = docs["data"]["metadata"]
    old_key = metadata["keys"][200]
    metadata["keys"][200] = "MOCK/NAS"
    docs["manifest"]["source_chunks"][200]["key"] = "MOCK/NAS"
    for field in ("row_counts", "logical_record_sha256"):
        rows = docs["manifest"][field]
        rows["MOCK/NAS"] = rows.pop(old_key)
    monkeypatch.setattr(
        restore,
        "_IDENTITY",
        restore._sha(json.dumps(metadata["keys"], separators=(",", ":")).encode()),
    )
    instrument = decision_instrument_binding_ref(symbol="MOCK", market="US", decision_class="enter")
    metadata["prior_clocks"] = [{"close_ts": clocks["prior_close_at"].isoformat()}]
    metadata["future_clocks"] = [
        dict(
            open_ts=o.isoformat(),
            close_ts=c.isoformat(),
            decision_ts=(clocks["nominal_decision_at"].isoformat()),
        )
        for o, c in zip(clocks["session_opens"], clocks["session_closes"], strict=True)
    ]
    template = docs["template"]
    hosts = docs["data"]["source_pins"]
    for i in range(1, 28):
        host = f"C:/Users/Public/Documents/thericher-v2/src/synthetic{i}.py"
        alias = f"/data-source/synthetic{i}.py"
        hosts[host] = link_fixture.P
        template["pins"][alias] = link_fixture.P
        template["host_paths"][alias] = host
        template["data_source_paths"][host] = alias
        docs["job"]["source_pins"][host] = link_fixture.P
    template["pins"]["/worker/shadow_worker.py"] = s._WORKER_R3
    docs["job"]["source_pins"][template["host_paths"]["/worker/shadow_worker.py"]] = s._WORKER_R3
    data_raw = link_fixture.encode(docs["data"])
    dp = link_fixture.sha(data_raw)
    template.update(
        input_plan_sha256=dp, input_metadata_sha256=link_fixture.sha(link_fixture.encode(metadata))
    )
    traw = link_fixture.encode(template)
    docs["job"]["source_pins"].update(
        {
            link_fixture.path(data_link._DATA, "plan.json"): dp,
            link_fixture.path(data_link._R3_ROOT, "engine-template.json"): link_fixture.sha(traw),
        }
    )
    jraw = link_fixture.encode(docs["job"])
    controls = replace(
        old,
        job_bytes=jraw,
        data_plan_bytes=data_raw,
        engine_template_bytes=traw,
        job_sha=link_fixture.sha(jraw),
        data_plan_sha=dp,
        engine_template_sha=link_fixture.sha(traw),
    )
    for name in ("claim", "terminal", "handoff"):
        docs[name]["job_sha256"] = controls.job_sha
    docs["handoff"].update(
        plan_sha256=dp,
        source_pins_sha256=link_fixture.sha(link_fixture.encode(docs["job"]["source_pins"])),
    )
    docs["manifest"]["plan_sha256"] = dp
    for item in docs["manifest"]["source_chunks"]:
        cp = link_fixture.path(data_link._CACHE, *item["chunk"]["path"].split("/"))
        pp = link_fixture.path(data_link._CACHE, *item["physical_capture"]["path"].split("/"))
        chunk = json.loads(records[cp])
        chunk["code_revision"] = dp
        chunk["source"]["symbol"] = item["key"].split("/")[0]
        records[cp] = link_fixture.encode(chunk)
        item["chunk"]["sha256"] = link_fixture.sha(records[cp])
        physical = json.loads(records[pp])
        physical["manifest_sha256"] = item["chunk"]["sha256"]
        records[pp] = link_fixture.encode(physical)
        item["physical_capture"]["sha256"] = link_fixture.sha(records[pp])
    for path in tuple(records):
        if path.endswith(("runtime-contract.json", "started.json")):
            record = json.loads(records[path])
            record["plan_sha256"] = dp
            records[path] = link_fixture.encode(record)
    runtime_path = link_fixture.path(data_link._DATA, "runtime-contract.json")
    docs["worker"].update(
        plan_sha256=dp,
        eligible_count=200,
        runtime_contract_sha256=link_fixture.sha(records[runtime_path]),
    )
    docs["plan"].clear()
    docs["plan"].update(json.loads(traw))
    docs["result"].clear()
    docs["result"].update(
        result
        | dict(
            worker_sha256=s._WORKER_R3,
            input_plan_sha256=dp,
            input_metadata_sha256=template["input_metadata_sha256"],
            calendar26_sha256=metadata["calendar26_sha256"],
            source_count=len(template["pins"]),
            frame_sha256=link_fixture.P,
            input_captured_at=docs["manifest"]["captured_at_utc"],
            physical_capture_sha256=link_fixture.sha(
                link_fixture.encode(docs["manifest"]["physical_capture"])
            ),
        )
    )
    docs["terminal"].update(actual_completed_at_utc="2026-10-16T21:26:00+00:00")
    docs["terminal"]["engine"]["completed_at_utc"] = result["completed_at"]
    # Only synthetic control pins change. Production fixed pins remain untouched.
    monkeypatch.setattr(
        restore,
        "_FIXED_LINKS",
        restore._FIXED_LINKS
        | dict(
            input_plan_sha256=dp,
            input_metadata_sha256=template["input_metadata_sha256"],
            calendar26_sha256=metadata["calendar26_sha256"],
        ),
    )
    seal()
    r = docs["result"]
    campaign = "ref:" + r["plan_sha256"][7:]
    frame, manifest = r["frame_sha256"], r["input_manifest_sha256"]
    cohort_ref = dto_fixture.ref(
        dict(
            campaign=campaign,
            frame=frame[7:],
            input=manifest,
            model=dto.model_ref,
            sources=dto.source_pins,
            allocation=dto.allocation_ref,
            slot=dto.selected_slot,
            instrument=instrument,
        )
    )
    proposal_ref = dto_fixture.ref(
        dict(
            cohort=cohort_ref,
            completed=dto.inference_completed_at.isoformat(),
            valid_until=dto.entry_valid_until.isoformat(),
            target=format(dto.proposal.target_exposure, "f"),
        )
    )
    with localcontext(Context(prec=64, rounding=ROUND_DOWN)):
        proposal = replace(dto.proposal, proposal_id=proposal_ref, symbol="MOCK")
        receipt = receipt_from_target_exposure_proposal(
            proposal,
            references=(DecisionReceiptReferences(campaign, dto.model_ref, manifest, proposal_ref)),
        )
        dto = replace(
            dto,
            cohort_ref=cohort_ref,
            frame_ref=frame,
            input_manifest_ref=manifest,
            proposal_ref=proposal_ref,
            proposal=proposal,
            receipt=receipt,
            instrument_key="MOCK/NAS",
            instrument_binding_ref=instrument,
        )
    r["decision"] = json.loads(dto_fixture.encode(asdict(dto)))
    return docs, records, controls, seal, read, calls, dto


def load(chain, *, as_of=MONDAY, read=None, controls=None):
    chain[3]()
    return s.load_prospective_shadow_input(
        controls=controls or chain[2], as_of=as_of, read_metadata=read or chain[4]
    )


@pytest.mark.parametrize("at", [FRIDAY, MONDAY])
def test_complete_friday_capture_can_be_consumed_monday(chain, at):
    out = load(chain, as_of=at)
    assert out.status == "ready" and out.decision == chain[6]
    assert out.cohort.source_ref == out.link.input_manifest_ref.sha256
    assert out.cohort.fingerprint != out.decision.cohort_ref
    assert out.cohort.fingerprint.startswith("sha256:")
    assert out.decision.inference_completed_at.date() == FRIDAY.date()
    assert out.decision.nominal_decision_at.date() == MONDAY.date()
    assert len(out.link.expected_engine_links()) == 15 and len(out.link.metadata_links) == 1035
    assert len(chain[5]) <= 2100 and all(p.endswith(".json") for p in chain[5])
    assert not any("delivery-r3" in p or "bars.csv" in p for p in chain[5])
    with pytest.raises(FrozenInstanceError):
        out.status = "invalid"


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_context_is_local_for_restore_and_native_cohort(chain, precision):
    expected = load(chain)
    with localcontext() as context:
        context.prec = precision
        out = load(chain)
        assert context.prec == precision
    assert out.decision == expected.decision and out.cohort == expected.cohort


def test_missing_claim_reads_one_exact_path_and_sanitizes(chain):
    calls = []

    def missing(path, cap):
        calls.append((path, cap))
        raise FileNotFoundError("secret account or amount must not escape")

    out = load(chain, read=missing)
    assert out.status == "no_intent" and out.reason == "missing_shadow_claim"
    assert out.decision is out.cohort is out.link is None
    assert calls == [(s._CLAIM, 65536)] and "secret" not in repr(out)


def test_entry_expiry_does_not_renew_the_friday_decision(chain):
    out = load(chain, as_of=chain[6].entry_valid_until)
    assert out.status == "no_intent" and out.reason == "entry_window_closed"
    assert out.decision is out.cohort is None and out.link is not None


def test_verified_cash_veto_remains_typed_no_intent_without_substitution(chain):
    docs = chain[0]
    old = chain[6]
    cohort_ref = dto_fixture.ref(
        dict(
            campaign="ref:" + docs["result"]["plan_sha256"][7:],
            frame=old.frame_ref[7:],
            input=old.input_manifest_ref,
            model=old.model_ref,
            sources=old.source_pins,
            allocation=old.allocation_ref,
            slot=None,
            instrument=None,
        )
    )
    veto = replace(
        old,
        status="no_intent",
        reason="model_cash_veto",
        cohort_ref=cohort_ref,
        selected_slot=None,
        instrument_key=None,
        instrument_binding_ref=None,
        proposal=None,
        receipt=None,
        proposal_ref=None,
    )
    docs["result"].update(
        status=veto.status,
        reason=veto.reason,
        decision=json.loads(dto_fixture.encode(asdict(veto))),
    )
    out = load(chain)
    assert out.status == "no_intent" and out.reason == "model_cash_veto"
    assert out.decision == veto and out.cohort is None and out.link is not None


@pytest.mark.parametrize("failure", ["hash", "root", "worker", "expiry"])
def test_caller_control_pin_root_worker_and_clock_fail_before_reader(chain, failure):
    controls = chain[2]
    if failure == "hash":
        controls = replace(controls, job_sha="sha256:" + "0" * 64)
    elif failure == "root":
        controls = replace(controls, expected_delivery_root=data_link._ROOT)
    else:
        template = json.loads(controls.engine_template_bytes)
        if failure == "worker":
            template["pins"]["/worker/shadow_worker.py"] = link_fixture.P
        else:
            template["entry_valid_until"] = "2026-10-19T22:30:00+09:00"
        raw = link_fixture.encode(template)
        controls = replace(
            controls, engine_template_bytes=raw, engine_template_sha=link_fixture.sha(raw)
        )
    out = load(chain, controls=controls)
    assert out.status == "no_intent" and out.reason == "controls_invalid"
    assert chain[5] == []


@pytest.mark.parametrize(
    "record,field,value",
    [
        ("terminal", "status", "retained_failure"),
        ("claim", "output_root", data_link._R3_ROOT + "/runtime/" + "1" * 32),
        ("worker", "eligible_count", 513),
        ("result", "worker_sha256", link_fixture.P),
        ("result", "sources_reattested", False),
        ("result", "input_metadata_sha256", link_fixture.P),
    ],
)
def test_chain_mutations_do_not_select_another_target(chain, record, field, value):
    chain[0][record][field] = value
    out = load(chain)
    assert out.status == "no_intent" and out.cohort is None
    assert not any("delivery-r3" in p for p in chain[5])


def test_manifest_order_failure_is_not_a_subset_replacement(chain):
    chain[0]["manifest"]["source_chunks"].reverse()
    assert load(chain).reason == "shadow_chain_invalid"


@pytest.mark.parametrize(
    "name,version",
    [
        ("proposal", 2),
        ("proposal", 3),
        ("receipt", 2),
        ("receipt", 3),
    ],
)
def test_schema1_only_after_exact_data_chain(chain, name, version):
    chain[0]["result"]["decision"][name]["schema_version"] = version
    out = load(chain)
    assert out.status == "no_intent" and out.reason == "shadow_result_invalid"


def test_duplicate_json_and_post_verification_changed_result_rejected(chain):
    chain[3]()
    result_path = str(
        PureWindowsPath(chain[0]["claim"]["output_root"]) / "engine-output/result.json"
    )
    seen = 0

    def read(path, cap):
        nonlocal seen
        raw = chain[4](path, cap)
        if path == result_path:
            seen += 1
            if seen == 3:
                return raw[:-1] + b',"status":"prepared"}'
        return raw

    out = load(chain, read=read)
    assert out.status == "no_intent" and out.reason == "shadow_result_invalid"


@pytest.mark.parametrize(
    "path",
    [
        "C:/Users/User/.env",
        "D:/private/account.json",
        s._R3_ROOT + "/runtime/receipt.json",
        s._CACHE + "/view/bars.csv.gz",
        s._CACHE + "/view/../manifest.json",
    ],
)
def test_native_reader_rejects_unrelated_or_raw_paths_without_open(path):
    with pytest.raises(s.ShadowInputError, match="metadata_path"):
        s.read_shadow_metadata(path, 4096)


def test_native_reader_bounded_source_only_file(monkeypatch, tmp_path):
    target = tmp_path / "metadata.json"
    target.write_bytes(b'{"synthetic":true}')
    monkeypatch.setattr(s, "Path", lambda _: target)
    assert s.read_shadow_metadata(s._CLAIM, 64) == b'{"synthetic":true}'
    with pytest.raises(s.ShadowInputError, match="metadata_size"):
        s.read_shadow_metadata(s._CLAIM, 4)
    with pytest.raises(s.ShadowInputError, match="metadata_cap"):
        s.read_shadow_metadata(s._CLAIM, True)


def test_import_does_not_load_model_numeric_or_provider_modules():
    root = str(Path(__file__).resolve().parents[1] / "src")
    script = (
        f"import sys; sys.path.insert(0, {root!r}); "
        "import thericher_v2.research.prospective_five_session_shadow_input; "
        "assert not any(m in sys.modules for m in "
        "('torch','numpy','sklearn','pickle','thericher_v2.research.five_session_tree',"
        "'thericher_v2.execution.kis_paper'))"
    )
    run = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, timeout=10, check=False
    )
    assert run.returncode == 0 and run.stdout == b"" and run.stderr == b""
