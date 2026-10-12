"""Exact synthetic R4 controls, using the existing full typed R3 custody fixture."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import ROUND_DOWN, Context, localcontext

import pytest

import test_prospective_five_session_shadow_decision as dto_fixture
import test_prospective_five_session_shadow_input as input_fixture
import test_prospective_five_session_shadow_link as link_fixture
from thericher_v2.data import prospective_five_session_shadow_link as link
from thericher_v2.research import prospective_five_session_paper_exchange as exchange
from thericher_v2.research import prospective_five_session_shadow_decision as decision
from thericher_v2.research import prospective_five_session_shadow_input as inputs
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

R4_WORKER = "sha256:" + "7" * 64


def refresh_decision(chain):
    docs, _, _, seal, _, _, old = chain
    seal()
    result = docs["result"]
    campaign = "ref:" + result["plan_sha256"][7:]
    manifest = result["input_manifest_sha256"]
    cohort_ref = dto_fixture.ref(
        dict(
            campaign=campaign,
            frame=result["frame_sha256"][7:],
            input=manifest,
            model=old.model_ref,
            sources=old.source_pins,
            allocation=old.allocation_ref,
            slot=old.selected_slot,
            instrument=old.instrument_binding_ref,
        )
    )
    proposal_ref = dto_fixture.ref(
        dict(
            cohort=cohort_ref,
            completed=old.inference_completed_at.isoformat(),
            valid_until=old.entry_valid_until.isoformat(),
            target=format(old.proposal.target_exposure, "f"),
        )
    )
    with localcontext(Context(prec=64, rounding=ROUND_DOWN)):
        proposal = replace(old.proposal, proposal_id=proposal_ref)
        receipt = receipt_from_target_exposure_proposal(
            proposal,
            references=DecisionReceiptReferences(campaign, old.model_ref, manifest, proposal_ref),
        )
        dto = replace(
            old,
            cohort_ref=cohort_ref,
            input_manifest_ref=manifest,
            proposal_ref=proposal_ref,
            proposal=proposal,
            receipt=receipt,
        )
    result["decision"] = json.loads(dto_fixture.encode(asdict(dto)))
    seal()
    return (*chain[:6], dto)


@pytest.fixture
def r4_chain(monkeypatch):
    chain = input_fixture.chain.__wrapped__(monkeypatch)
    docs, records, old, seal, read, calls, dto = chain
    job, template, data = (docs[n] for n in ("job", "template", "data"))
    for i, name in ((1, "common.py"), (2, "collect.py")):
        old_host = f"C:/Users/Public/Documents/thericher-v2/src/synthetic{i}.py"
        new_host = link_fixture.path(link._R4_PRODUCER, name)
        alias = template["data_source_paths"].pop(old_host)
        data["source_pins"].pop(old_host)
        job["source_pins"].pop(old_host)
        wanted = link._R4_SOURCE_PINS[name]
        data["source_pins"][new_host] = job["source_pins"][new_host] = wanted
        template["data_source_paths"][new_host] = alias
        template["host_paths"][alias] = new_host
        template["pins"][alias] = wanted
    guard = link_fixture.path(link._R4_ROOT, "shadow_clock_guard.py")
    job["source_pins"].pop(job["data"]["clock_guard_path"])
    job["data"]["clock_guard_path"] = guard
    job["source_pins"][guard] = link._R4_GUARD_SHA
    docs["terminal"]["clock_guard_sha256"] = link._R4_GUARD_SHA
    job["root"] = link._R4_ROOT
    job["source_pins"].pop(job["engine"]["template_path"])
    job["engine"]["template_path"] = link_fixture.path(link._R4_ROOT, "engine-template.json")
    data_raw = link_fixture.encode(data)
    dp = link_fixture.sha(data_raw)
    template["input_plan_sha256"] = dp
    template["pins"]["/worker/shadow_worker.py"] = R4_WORKER
    job["source_pins"][template["host_paths"]["/worker/shadow_worker.py"]] = R4_WORKER
    traw = link_fixture.encode(template)
    job["source_pins"].pop(link_fixture.path(link._DATA, "plan.json"))
    job["source_pins"].update(
        {
            link_fixture.path(link._R4_PRODUCER, "plan.json"): dp,
            job["engine"]["template_path"]: link_fixture.sha(traw),
        }
    )
    jraw = link_fixture.encode(job)
    controls = replace(
        old,
        job_bytes=jraw,
        data_plan_bytes=data_raw,
        engine_template_bytes=traw,
        job_sha=link_fixture.sha(jraw),
        data_plan_sha=dp,
        engine_template_sha=link_fixture.sha(traw),
        expected_delivery_root=link._R4_ROOT,
    )
    # Only the test's independently sealed synthetic allowlist changes, never incoming pins.
    monkeypatch.setattr(link, "_R4_PLAN_SHA", dp)
    monkeypatch.setattr(
        link,
        "_R4_BINDING",
        dict(
            job_sha=controls.job_sha,
            engine_template_sha=controls.engine_template_sha,
            worker_sha=R4_WORKER,
        ),
    )
    for name in ("claim", "terminal", "handoff"):
        docs[name]["job_sha256"] = controls.job_sha
    docs["handoff"].update(
        plan_sha256=dp, source_pins_sha256=link_fixture.sha(link_fixture.encode(job["source_pins"]))
    )
    docs["manifest"]["plan_sha256"] = dp
    for item in docs["manifest"]["source_chunks"]:
        cp = link_fixture.path(link._CACHE, *item["chunk"]["path"].split("/"))
        pp = link_fixture.path(link._CACHE, *item["physical_capture"]["path"].split("/"))
        chunk = json.loads(records[cp])
        chunk["code_revision"] = dp
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
    runtime = link_fixture.path(link._DATA, "runtime-contract.json")
    docs["worker"].update(
        plan_sha256=dp, runtime_contract_sha256=link_fixture.sha(records[runtime])
    )
    docs["plan"].clear()
    docs["plan"].update(json.loads(traw))
    docs["result"].update(worker_sha256=R4_WORKER, input_plan_sha256=dp)
    return refresh_decision((docs, records, controls, seal, read, calls, dto))


def test_r4_complete_typed_chain_preserves_original_claim_and_exposure(r4_chain):
    out = input_fixture.load(r4_chain)
    assert out.status == "ready" and out.decision == r4_chain[6]
    assert len(out.link.expected_engine_links()) == 15
    assert out.decision.proposal.target_exposure == r4_chain[6].proposal.target_exposure
    assert out.cohort.session_opens[0] == r4_chain[6].session_opens[0]
    assert out.cohort.entry_request_id.startswith("five-")
    assert out.decision.inference_completed_at == dto_fixture.INFERRED
    assert out.decision.entry_valid_until == r4_chain[6].entry_valid_until
    assert all(inputs._metadata_path(p).suffix == ".json" for p in r4_chain[5])
    assert not any("delivery-r4" in p or "bars.csv" in p for p in r4_chain[5])


@pytest.mark.parametrize("field", ["job_sha", "data_plan_sha", "engine_template_sha"])
def test_r4_caller_pin_is_not_an_allowlist_override(r4_chain, field):
    out = input_fixture.load(r4_chain, controls=replace(r4_chain[2], **{field: link_fixture.P}))
    assert out.status == "no_intent" and out.reason == "controls_invalid"
    assert r4_chain[5] == []


@pytest.mark.parametrize("field", ["collect.py", "common.py", "shadow_clock_guard.py"])
def test_r4_rehashed_job_cannot_bypass_fixed_producer_sources(r4_chain, monkeypatch, field):
    job = deepcopy(r4_chain[0]["job"])
    target = link_fixture.path(
        link._R4_ROOT if field == "shadow_clock_guard.py" else link._R4_PRODUCER, field
    )
    job["source_pins"][target] = link_fixture.P
    raw = link_fixture.encode(job)
    controls = replace(r4_chain[2], job_bytes=raw, job_sha=link_fixture.sha(raw))
    monkeypatch.setattr(link, "_R4_BINDING", {**link._R4_BINDING, "job_sha": controls.job_sha})
    out = input_fixture.load(r4_chain, controls=controls)
    assert out.status == "no_intent" and out.reason == "controls_invalid"
    assert r4_chain[5] == []


def test_r4_missing_expired_and_unknown_worker_remain_scoped(r4_chain):
    def missing(*_):
        raise FileNotFoundError("private synthetic body")

    out = input_fixture.load(r4_chain, read=missing)
    assert out.status == "no_intent" and out.reason == "missing_shadow_claim"
    out = input_fixture.load(r4_chain, as_of=r4_chain[6].entry_valid_until)
    assert out.status == "no_intent" and out.reason == "entry_window_closed"
    good = input_fixture.load(r4_chain)
    result = r4_chain[0]["result"]
    bad = {**result, "worker_sha256": link_fixture.P}
    raw = dto_fixture.encode(bad)
    expected = {
        **good.link.expected_engine_links(),
        "result_sha256": link_fixture.sha(raw),
        "worker_sha256": link_fixture.P,
    }
    with pytest.raises(decision.ShadowDecisionError, match="shadow_fixed_source"):
        decision.restore_prospective_shadow_decision(
            raw,
            expected_links=expected,
            identities=tuple(r4_chain[0]["data"]["metadata"]["keys"]),
            prior_close_at=good.decision.prior_close_at,
            nominal_decision_at=good.decision.nominal_decision_at,
            session_opens=good.decision.session_opens,
            session_closes=good.decision.session_closes,
            entry_valid_until=good.decision.entry_valid_until,
            as_of=input_fixture.MONDAY,
            expected_worker_sha256=link_fixture.P,
        )


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_r4_schema1_roundtrip_and_expired_retained_codec(r4_chain, monkeypatch, precision):
    loaded = input_fixture.load(r4_chain)
    metadata = r4_chain[0]["data"]["metadata"]
    for name, value in (
        ("_METADATA", loaded.link.expected_engine_links()["input_metadata_sha256"]),
        ("_CALENDAR", metadata["calendar26_sha256"]),
        ("_IDENTITY", exchange._sha(json.dumps(metadata["keys"], separators=(",", ":")).encode())),
    ):
        monkeypatch.setattr(exchange, name, value)
    dto = loaded.decision
    pins = exchange.PaperExchangePins(
        r4_chain[2].job_sha,
        "sha256:" + "f" * 64,
        exchange.SOURCE_PINS_R4,
        tuple(metadata["keys"]),
        metadata["calendar26_sha256"],
        dto.prior_close_at,
        dto.nominal_decision_at,
        dto.session_opens,
        dto.session_closes,
        dto.entry_valid_until,
    )
    baseline = exchange.encode_prospective_paper_exchange(loaded, pins=pins)
    with localcontext(Context(prec=precision, rounding=ROUND_DOWN)) as context:
        raw = exchange.encode_prospective_paper_exchange(loaded, pins=pins)
        out = exchange.restore_prospective_paper_exchange(
            raw,
            expected_sha256=exchange._sha(raw),
            pins=pins,
            as_of=dto.fifth_close,
        )
        assert context.prec == precision
    assert raw == baseline and json.loads(raw)["schema_version"] == 1
    assert out.decision == dto and out.cohort == loaded.cohort
    assert out.cohort.entry_request_id == loaded.cohort.entry_request_id
    assert out.restored_at > dto.entry_valid_until and len(out.links) == 15
    with pytest.raises(exchange.PaperExchangeError, match="exchange_sources"):
        exchange.restore_prospective_paper_exchange(
            raw,
            expected_sha256=exchange._sha(raw),
            pins=replace(pins, source_pins=exchange.SOURCE_PINS),
            as_of=input_fixture.MONDAY,
        )
