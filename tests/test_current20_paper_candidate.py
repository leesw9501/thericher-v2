"""Synthetic native custody/transport only; no real account, Task or model."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research import current20_paper_candidate as candidate
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

D = Decimal
PIN = "sha256:" + "f" * 64
AT = datetime(2026, 10, 19, 15, 10, tzinfo=UTC)
SYN_SLOTS = (0, 1, 2, 3, 4)
DECISION = datetime(2026, 10, 18, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


def calendar():
    day, sessions = date(2026, 10, 19), []
    while day <= date(2026, 11, 17):
        s = us_equity_2026_session(day)
        if s is not None:
            sessions.append(s.window)
        day += timedelta(days=1)
    return candidate.Current20PaperCalendar(PIN, candidate.FEATURE_CLOSE, tuple(sessions))


def prepared():
    c = calendar()
    metadata = candidate.Current20PaperMetadata(PIN, c, SYN_SLOTS, DECISION)
    refs = DecisionReceiptReferences(
        "ref:" + PIN[7:],
        "ref:" + candidate.BUNDLE_SHA256,
        metadata.input_ref,
        "ref:" + metadata.input_ref[7:],
    )
    targets = []
    for slot in SYN_SLOTS:
        p = TargetExposureProposal(
            candidate.CANDIDATE_ID + "-" + str(slot),
            candidate.STOCK_KEYS[slot].split("/")[0],
            "US",
            "enter",
            D(".005"),
            D(0),
            candidate.FEATURE_SCHEMA_ID,
            "ready",
            DECISION,
            c.sessions[0].close_ts,
            candidate.FEATURE_CLOSE,
            "provisional_frozen_equalrank4",
        )
        targets.append(
            candidate.Current20PaperTarget(
                slot,
                D(".2"),
                p,
                receipt_from_target_exposure_proposal(p, references=refs),
                metadata,
            )
        )
    return cycle.CurrentStockCycleInput(
        tuple(targets),
        c.sessions[0],
        c.sessions[-1],
        metadata.input_ref,
        PIN,
        cycle.StockCycleProfile.CURRENT20_EQUALRANK4,
    )


class SyntheticClient(legacy.NativeSyntheticStockClient):
    def submit_limit(self, intent, **_kwargs):
        h = self.h
        state = canary.KisPaperCanaryStateStore(h["root"] / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started" and state.intent == intent
        saved = record(h)
        assert saved["pending"]["plan_ref"] in saved["owners"][intent.symbol]["plans"].values()
        h["submits"].append(intent)
        filled = D(1) if h["partial"] else intent.quantity
        h["orders"][intent.run_id] = dict(
            intent=intent,
            id=str(100 + len(h["submits"])),
            filled=filled,
            remaining=intent.quantity - filled,
            cancelled=False,
        )
        if h["unknown"]:
            raise canary.KisPaperCanaryError("submit_transport_unknown")
        return True, h["orders"][intent.run_id]["id"]


@pytest.fixture
def h(tmp_path):
    result = legacy.h.__wrapped__(tmp_path)
    result["data"], result["now"] = prepared(), AT
    clients = {}

    def factory(instrument):
        if instrument not in clients:
            result["factories"] += 1
            clients[instrument] = SyntheticClient(result, instrument)
        return clients[instrument]

    result["call"].update(
        client_factory=factory,
        expected_input_ref=result["data"].input_ref,
        expected_policy_ref=result["data"].policy_ref,
    )
    return result


def run(h, **changes):
    return candidate.run_current20_paper_visit(**(h["call"] | changes))


def record(h):
    return cycle.budget._read_json(h["root"] / cycle.CURRENT20_POINTER)


def test_native_json_exact_pins_no_model_arrays_and_roundtrip():
    value = prepared()
    payload = candidate.serialize_current20_paper_input(value)
    pin = hashlib.sha256(payload).hexdigest()
    assert candidate.load_current20_paper_input(payload, expected_sha256=pin) == value
    with pytest.raises(ValueError, match="pin_mismatch"):
        candidate.load_current20_paper_input(payload + b" ", expected_sha256=pin)
    assert b"numpy" not in payload and b"torch" not in payload
    assert sum(t.proposal.target_exposure for t in value.targets) == D(".025")
    assert tuple(t.slot for t in value.targets) == SYN_SLOTS


def test_new_profile_five_entries_five_exits_and_legacy_pointer_untouched(h):
    old = h["root"] / cycle.POINTER
    old.write_bytes(b'{"synthetic_legacy_marker":true}')
    before = old.read_bytes()
    results = run(h)
    assert len(results) == 6 and [r.status for r in results] == ["advanced"] * 5 + ["hold"]
    assert len(h["submits"]) == 5 and {i.quantity for i in h["submits"]} == {D(5)}
    assert h["factories"] == 5
    h["now"] = datetime(2026, 11, 17, 15, 10, tzinfo=UTC)
    assert (
        run(h, target_loader=lambda: pytest.fail("exit_needs_no_future_collector"))[-1].status
        == "complete"
    )
    assert len(h["submits"]) == 10 and all(i.side == "sell" for i in h["submits"][5:])
    assert old.read_bytes() == before
    bound = cycle.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert bound[key] == h["initial"][key]


def test_legacy_default_still_requires_ten_nas_targets_and_14day_bound(tmp_path):
    original = legacy.h.__wrapped__(tmp_path)
    value = original["data"]
    assert cycle._validate_input(value, original["now"]) == value
    for changed in (
        replace(value, targets=value.targets[:5]),
        replace(
            value,
            exit_session=replace(
                value.exit_session,
                open_ts=value.entry_session.open_ts + timedelta(days=20),
                close_ts=value.entry_session.close_ts + timedelta(days=20),
            ),
        ),
        prepared(),
    ):
        with pytest.raises(cycle._CycleFault):
            cycle._validate_input(changed, original["now"])
    assert cycle.POINTER == ".current-nas-stock-cycle.json"


@pytest.mark.parametrize("fault", ["stale", "foreign", "late_funds"])
def test_native_fresh_quote_foreign_inventory_and_buyingpower_still_decide(h, fault):
    h[fault] = True
    run(h)
    assert not h["submits"]


def test_unknown_submit_stops_wake_and_exact_recovery_after_entry_never_resubmits(h):
    h["unknown"] = True
    assert [r.status for r in run(h)] == ["pending"]
    pending = copy.deepcopy(record(h)["pending"])
    h["now"] += timedelta(days=2)
    for _ in range(2):
        assert (
            run(h, target_loader=lambda: pytest.fail("unknown_must_not_reload"))[0].status
            == "pending"
        )
    assert len(h["submits"]) == 1
    assert record(h)["pending"]["arguments"] == pending["arguments"]


@pytest.mark.parametrize("fault", ["profile", "input", "request"])
def test_foreign_pointer_or_pending_request_drift_rejected_before_factory(h, fault):
    h["unknown"] = True
    run(h)
    saved = record(h)
    if fault == "profile":
        saved.pop("profile")
    elif fault == "input":
        saved["pending"]["arguments"]["input_ref"] = "sha256:" + "1" * 64
    else:
        saved["pending"]["arguments"]["request_id"] = "foreign-request"
    cycle._save(h["root"] / cycle.CURRENT20_POINTER, saved)
    before = len(h["submits"])
    result = run(h, client_factory=lambda _: pytest.fail("drift_must_precede_client"))
    assert len(result) == 1 and result[0].status == "unavailable"
    assert len(h["submits"]) == before


def test_foreign_registered_target_excluded_without_adoption_or_backup(h):
    assert run(h)[-1].status == "hold"
    first = copy.deepcopy(record(h))
    (h["root"] / cycle.CURRENT20_POINTER).unlink()
    results = run(h)
    assert len(h["submits"]) == 5 and all(r.status in {"no_intent", "hold"} for r in results)
    assert record(h)["owners"] == {} and len(record(h)["active"]["entries_done"]) == 5
    assert len(first["owners"]) == 5


def test_expired_source_never_rebound_to_new_entry_and_no_early_exit(h):
    run(h)
    count = len(h["submits"])
    h["now"] = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)
    assert run(h)[-1].reason == "await_declared_exit" and len(h["submits"]) == count
    (h["root"] / cycle.CURRENT20_POINTER).unlink()
    assert run(h)[0].status == "unavailable" and len(h["submits"]) == count


def test_calendar_dst_exact_source_window_and_not_21_full_held_sessions():
    c = calendar()
    assert len(c.sessions[:-1]) == 21
    assert c.sessions[0].open_ts.hour == 13 and c.sessions[-1].open_ts.hour == 14
    assert (
        sum(
            AT <= s.open_ts and s.close_ts <= datetime(2026, 11, 17, 15, 10, tzinfo=UTC)
            for s in c.sessions
        )
        == 20
    )
    with pytest.raises(ValueError):
        replace(c, sessions=c.sessions[1:])


@pytest.mark.parametrize("fault", ["schema", "target", "decision", "slot", "expiry", "identity"])
def test_no_legacy_schema_larger_weight_backdating_rerank_or_expiry_renewal(fault):
    value = prepared()
    first = value.targets[0]
    if fault == "slot":
        first = replace(first, slot=1)
    else:
        edits = dict(
            schema={"feature_schema_id": "current-nas-frozen5-fixed-ordinal-mean-top10-sleeve-v1"},
            target={"target_exposure": D(".01")},
            decision={"decided_at": candidate.PUBLICATION - timedelta(seconds=1)},
            expiry={"valid_until": value.exit_session.close_ts},
            identity={"proposal_id": "foreign-proposal"},
        )
        first = replace(first, proposal=replace(first.proposal, **edits[fault]))
    with pytest.raises(cycle._CycleFault):
        cycle._validate_input(
            replace(value, targets=(first,) + value.targets[1:]), AT, value.profile
        )


def test_inert_before_state_or_callbacks(h):
    assert run(h, execute=False)[0].status == "inert"
    assert record(h) is None and not h["submits"] and h["loads"] == 0


def test_wrong_contract_and_source_pins_fail_without_decoding():
    with pytest.raises(ValueError, match="pin_mismatch"):
        candidate.prepare_current20_paper_candidate(
            contract_bytes=b"{}",
            expected_contract_sha256="0" * 64,
            bundle_bytes=b"{}",
            weights_bytes=b"",
            calendar=calendar(),
            decided_at=AT,
        )


def test_zero_same_shared_bank_skips_all_without_clients_or_canonical_mutation(h):
    binding = cycle.budget._load_binding(h["root"])
    order = binding["qqq"]["orders"][0]
    path = h["root"] / (order["run_id"] + ".json")
    state = canary.KisPaperCanaryState.from_dict(cycle.budget._read_json(path))
    state = replace(state, intent=replace(state.intent, quantity=D(1), limit_price=D(940)))
    order["intent_ref"] = state.intent.fingerprint
    cycle.budget._atomic_json(path, state.to_dict())
    binding["qqq"]["owner_ref"] = next(
        o.fingerprint for o, _ in cycle.budget._owners(binding) if o.symbol == "QQQ"
    )
    cycle.budget._atomic_json(h["root"] / cycle.budget.BUDGET_FILE, binding)
    assert cycle._projection(h["root"], binding, h["now"])[-1].remaining_cap == 0
    before = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    results = run(h, client_factory=lambda _: pytest.fail("empty_bank_must_precede_client"))
    assert [r.status for r in results] == ["no_intent"] * 5 + ["hold"]
    assert not h["submits"] and record(h)["owners"] == {}
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == before


@pytest.mark.parametrize("stage", ["before_reserve", "after_reserve"])
def test_new_pointer_crash_recovery_retains_original_native_request(h, monkeypatch, stage):
    original = cycle.entries.reserve_kis_paper_stock_plan

    def crash(**arguments):
        if stage == "after_reserve":
            original(**arguments)
        raise RuntimeError("synthetic_crash")

    with monkeypatch.context() as patch:
        patch.setattr(cycle.entries, "reserve_kis_paper_stock_plan", crash)
        assert run(h)[0].status == "unavailable"
    pending = copy.deepcopy(record(h)["pending"])
    assert not (h["root"] / cycle.POINTER).exists()
    # One exact recovered leg, then terminate this wake before a new leg.
    calls = 0

    def factory(instrument):
        nonlocal calls
        calls += 1
        if instrument.symbol != pending["symbol"]:
            raise RuntimeError("stop_after_exact_recovery")
        return SyntheticClient(h, instrument)

    run(h, client_factory=factory, target_loader=lambda: pytest.fail("no_reload"))
    assert len(h["submits"]) == 1 and not (h["root"] / cycle.POINTER).exists()
    args = cycle._unpack(pending["arguments"])
    intent = h["submits"][0]
    assert intent.created_at == args["as_of"] and intent.valid_until == args["valid_until"]
    assert intent.limit_price == args["reads"].buy_limit and calls >= 1


def test_never_enter_or_exit_before_exact_operational_instants(h):
    h["now"] = candidate.ENTRY_NOT_BEFORE - timedelta(seconds=1)
    assert run(h)[0].status == "unavailable" and not h["submits"]
    h["now"] = candidate.ENTRY_NOT_BEFORE
    run(h)
    count = len(h["submits"])
    h["now"] = candidate.EXIT_NOT_BEFORE - timedelta(seconds=1)
    assert run(h)[-1].reason == "await_declared_exit" and len(h["submits"]) == count


def test_entire_oct19_session_not_arbitrary_25minute_signal_cutoff():
    value = prepared()
    assert cycle._validate_input(value, AT + timedelta(minutes=26), value.profile) == value
    assert all(t.proposal.valid_until == value.entry_session.close_ts for t in value.targets)
    with pytest.raises(cycle._CycleFault):
        cycle._validate_input(value, value.entry_session.close_ts, value.profile)


def test_json_loader_needs_exact_pinned_profile_not_copied_nas_input():
    payload = json.loads(candidate.serialize_current20_paper_input(prepared()))
    payload["profile"] = cycle.StockCycleProfile.LEGACY_NAS.value
    raw = json.dumps(payload).encode()
    with pytest.raises(ValueError, match="profile_invalid"):
        candidate.load_current20_paper_input(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
