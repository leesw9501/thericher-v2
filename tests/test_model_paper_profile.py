"""Native synthetic bank/recovery tests for the separate provisional NAS profile."""

import copy
from dataclasses import fields
from datetime import date, timedelta
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
from test_model_paper_proposal import PIN, prepared
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research.model_paper_proposal import ModelPaperInput

D = Decimal


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


def record(h):
    return cycle.budget._read_json(h["root"] / cycle.model_paper_pointer(h["data"].policy_ref))


class SyntheticClient(legacy.NativeSyntheticStockClient):
    def submit_limit(self, intent, **_kwargs):
        h = self.h
        state = cycle.canary.KisPaperCanaryStateStore(h["root"] / (intent.run_id + ".json")).read()
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
            raise cycle.canary.KisPaperCanaryError("submit_transport_unknown")
        return True, h["orders"][intent.run_id]["id"]


@pytest.fixture
def h(tmp_path):
    result = legacy.h.__wrapped__(tmp_path)
    result["data"] = prepared()
    result["now"] = result["data"].entry_session.open_ts + timedelta(minutes=30)

    def factory(instrument):
        result["factories"] += 1
        return SyntheticClient(result, instrument)

    result["call"].update(
        client_factory=factory,
        profile=cycle.StockCycleProfile.MODEL_PROPOSAL_NAS,
        expected_input_ref=result["data"].input_ref,
        expected_policy_ref=result["data"].policy_ref,
    )
    return result


def run(h, **changes):
    return cycle.run_kis_paper_current_stock_cycle(**(h["call"] | changes))


def visit_all(h, **changes):
    results = []
    for _ in range(len(h["data"].targets) + 2):
        result = run(h, **changes)
        results.append(result)
        if result.status not in {"advanced", "no_intent"}:
            break
    return results


def test_full25_codec_and_native_entries_exits_keep_old_pointers_and_bank(h):
    markers = []
    for name in (cycle.POINTER, cycle.CURRENT20_POINTER):
        path = h["root"] / name
        path.write_bytes(b'{"synthetic_untouched":true}')
        markers.append(path)
    results = visit_all(h)
    assert [r.status for r in results] == ["advanced"] * 3 + ["hold"]
    assert {i.symbol for i in h["submits"]} == {"AAPL", "AMD", "AMZN"}
    assert {i.quantity for i in h["submits"]} == {D(5)}
    active = record(h)["active"]
    retained = cycle._unpack(active["model_input"])
    assert type(retained) is ModelPaperInput and retained == h["data"]
    assert len(retained.metadata.rows) == 25
    assert all(
        r.route.endswith("/NYS")
        for r in retained.metadata.rows
        if r.eligibility == "UNSUPPORTED_VENUE"
    )
    h["now"] = h["data"].metadata.exit_not_before + timedelta(minutes=1)
    assert (
        visit_all(h, target_loader=lambda: pytest.fail("exit_must_not_reload"))[-1].status
        == "complete"
    )
    assert len(h["submits"]) == 6 and all(i.side == "sell" for i in h["submits"][3:])
    bound = cycle.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert bound[key] == h["initial"][key]
    assert set(bound["stocks"]) == {"AAPL", "AMD", "AMZN"}
    assert all(p.read_bytes() == b'{"synthetic_untouched":true}' for p in markers)
    assert (
        run(h, target_loader=lambda: pytest.fail("completed_point_must_not_reload")).status
        == "complete"
    )


def test_zero_eligible_is_no_intent_and_no_bank_or_owner_mutation(h):
    h["data"] = prepared(selected=(8, 9, 10, 11, 12))
    before = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    result = run(h, expected_input_ref=h["data"].input_ref)
    assert result.status == "no_intent" and result.reason == "native_risk_no_intent"
    assert not h["submits"] and h["factories"] == 0 and record(h) is None
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == before


def test_new_profile_uses_trusted_preclose_exit_not_just_fifth_date(h):
    assert visit_all(h)[-1].status == "hold"
    h["now"] = h["data"].exit_session.open_ts + timedelta(minutes=10)
    assert run(h).status == "hold" and len(h["submits"]) == 3
    h["now"] = h["data"].metadata.exit_not_before - timedelta(seconds=1)
    assert run(h).status == "hold" and len(h["submits"]) == 3
    h["now"] += timedelta(seconds=1)
    assert (
        run(h, target_loader=lambda: pytest.fail("exit_must_use_retained_timing")).status
        == "advanced"
    )
    assert len(h["submits"]) == 4 and h["submits"][-1].side == "sell"


def test_unknown_request_recovery_precedes_loader_and_cannot_refresh_input_or_reservation(h):
    h["unknown"] = True
    assert run(h).status == "pending"
    pending = copy.deepcopy(record(h)["pending"])
    bank = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    h["now"] += timedelta(days=2)
    for _ in range(2):
        assert (
            run(h, target_loader=lambda: pytest.fail("pending_must_not_reload")).status == "pending"
        )
    assert len(h["submits"]) == 1
    assert record(h)["pending"]["arguments"] == pending["arguments"]
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == bank
    result = run(
        h,
        expected_input_ref=PIN,
        client_factory=lambda _: pytest.fail("changed_point_before_client"),
    )
    assert result.status == "unavailable" and len(h["submits"]) == 1


@pytest.mark.parametrize(
    "fault", ["profile", "owner", "input", "request", "targets", "entry", "exit"]
)
def test_cross_profile_and_exact_request_codec_drift_rejected_before_client(h, fault):
    h["unknown"] = True
    assert run(h).status == "pending"
    saved = record(h)
    if fault == "profile":
        saved["profile"] = cycle.StockCycleProfile.CURRENT20_EQUALRANK4.value
    elif fault == "owner":
        saved["owner_key"] = PIN
    elif fault == "input":
        saved["pending"]["arguments"]["input_ref"] = PIN
    elif fault == "request":
        saved["pending"]["arguments"]["request_id"] = "nas-foreign-request"
    elif fault == "targets":
        saved["active"]["targets"] = cycle._pack(())
    else:
        saved["active"][fault + "_session"] = cycle._pack(
            h["data"].entry_session if fault == "exit" else h["data"].exit_session
        )
    cycle._save(h["root"] / cycle.model_paper_pointer(h["data"].policy_ref), saved)
    assert (
        run(h, client_factory=lambda _: pytest.fail("drift_before_client")).status == "unavailable"
    )
    assert len(h["submits"]) == 1


@pytest.mark.parametrize("fault", ["stale", "foreign", "late_funds"])
def test_existing_native_quote_inventory_and_funds_checks_still_decide(h, fault):
    h[fault] = True
    visit_all(h)
    assert not h["submits"]


def test_distinct_profile_never_adopts_registered_owner_or_replaces_missing_stock(h):
    assert visit_all(h)[-1].status == "hold"
    old_pointer = h["root"] / cycle.model_paper_pointer(h["data"].policy_ref)
    before_old = old_pointer.read_bytes()
    bank = (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()
    h["data"] = prepared(policy=PIN)
    h["call"].update(expected_input_ref=h["data"].input_ref, expected_policy_ref=PIN)
    assert [r.status for r in visit_all(h)] == ["no_intent"] * 3 + ["hold"]
    assert len(h["submits"]) == 3 and record(h)["owners"] == {}
    assert record(h)["active"]["entries_done"] == ["AAPL", "AMD", "AMZN"]
    assert old_pointer.read_bytes() == before_old
    assert (h["root"] / cycle.budget.BUDGET_FILE).read_bytes() == bank


def test_same_profile_repeat_point_only_after_own_exact_flat_and_preserves_history(h):
    assert visit_all(h)[-1].status == "hold"
    old_input = h["data"].input_ref
    h["now"] = h["data"].metadata.exit_not_before + timedelta(minutes=1)
    assert visit_all(h)[-1].status == "complete"
    plans = {s: dict(v["plans"]) for s, v in record(h)["owners"].items()}
    h["data"] = prepared(entry=date(2026, 10, 26))
    h["now"] = h["data"].entry_session.open_ts + timedelta(minutes=30)
    h["call"]["expected_input_ref"] = h["data"].input_ref
    assert visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 9 and old_input in record(h)["completed"]
    assert all(set(v) <= set(record(h)["owners"][s]["plans"]) for s, v in plans.items())


def test_legacy_native_codec_fields_and_default_admission_unchanged(tmp_path):
    original = legacy.h.__wrapped__(tmp_path)
    value = original["data"]
    assert cycle._unpack(cycle._pack(value.targets)) == value.targets
    assert [f.name for f in fields(cycle.CurrentStockCycleInput)] == [
        "targets",
        "entry_session",
        "exit_session",
        "input_ref",
        "policy_ref",
        "profile",
    ]
    assert cycle._validate_input(value, original["now"]) == value
    with pytest.raises(cycle._CycleFault):
        cycle._validate_input(prepared(), original["now"])
    with pytest.raises(cycle._CycleFault):
        cycle._validate_input(value, original["now"], cycle.StockCycleProfile.MODEL_PROPOSAL_NAS)
    with pytest.raises(cycle._CycleFault, match="cycle_ten_targets_required"):
        cycle._validate_input(legacy.replace(value, targets=value.targets[:3]), original["now"])
