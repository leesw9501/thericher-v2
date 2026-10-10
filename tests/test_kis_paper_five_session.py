from __future__ import annotations

import hashlib
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution.kis_paper_budget_strategy import _stock_identity
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
    project_five_session_cohort,
)
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioBudgetError,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
)
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument

D = Decimal
NY = ZoneInfo("America/New_York")
ACCOUNT = "a" * 64
BASIS = KisPaperPortfolioBudgetBasis(ACCOUNT, D(10000), D(1000), datetime(2026, 10, 1, tzinfo=UTC))
DECISION = "decision:sha256:" + "d" * 64


def cohort(dates=("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16")):
    opens = tuple(
        datetime.fromisoformat(day + "T09:30").replace(tzinfo=NY).astimezone(UTC) for day in dates
    )
    closes = tuple(
        datetime.fromisoformat(day + "T16:00").replace(tzinfo=NY).astimezone(UTC) for day in dates
    )
    return KisPaperFiveSessionCohort(
        KisPaperStockInstrument("SYN", "ref:" + "b" * 64),
        DECISION,
        "sha256:" + "c" * 64,
        "sha256:" + "e" * 64,
        opens,
        closes,
        opens[0] + timedelta(minutes=10),
        closes[-1] - timedelta(minutes=10),
    )


def state(
    contract,
    run="entry",
    *,
    sell=False,
    quantity="2",
    filled=None,
    remaining=None,
    phase="submitted",
    unavailable=False,
    at=None,
    category=None,
):
    at = at or (contract.exit_due if sell else contract.session_opens[0])
    if not sell:
        identity = _stock_identity(
            {
                "account_ref": ACCOUNT,
                "basis_ref": BASIS.fingerprint,
                "stocks": {
                    contract.instrument.symbol: {
                        "exchange": "NASD",
                        "instrument_binding_ref": contract.instrument.binding_ref,
                    }
                },
            },
            contract.instrument.symbol,
            contract.entry_request_id,
            "buy",
        )
        run, client_id, decision_id = "bk-" + identity, "stock-" + identity, "stock-" + identity
    else:
        client_id, decision_id = "synthetic-" + run, "synthetic-exit-" + run
    intent = KisPaperCanaryIntent(
        run,
        client_id,
        decision_id,
        contract.instrument.symbol,
        "NASD",
        D(quantity),
        D(10),
        at,
        at + timedelta(seconds=30),
        "sell" if sell else "buy",
    )
    submitted = phase in {"submitted", "cancelled", "cancel_started"}
    attempted = phase != "intent_recorded"
    order_at = at + timedelta(seconds=1) if attempted else None
    order_id = "SYN-" + hashlib.sha256(run.encode()).hexdigest()[:20] if submitted else None
    fill = (
        None
        if filled is None
        else KisPaperCumulativeFill(
            fill_identity_ref(
                raw_order_id=order_id,
                order_at=order_at,
                symbol=intent.symbol,
                exchange="NASD",
                side=intent.side,
                quantity=intent.quantity,
            ),
            intent.quantity,
            D(filled),
            D(filled) * D(10),
            at + timedelta(seconds=2),
            None if remaining is None else D(remaining),
        )
    )
    updated = at + timedelta(seconds=40)
    return KisPaperCanaryState(
        intent,
        phase,
        updated,
        "reconciliation_unresolved",
        broker_order_id=order_id,
        submitted_at=order_at if submitted else None,
        submission_started_at=order_at,
        submit_response_category=category,
        cumulative_fill=fill,
        fill_observation_status="unavailable"
        if unavailable
        else "available"
        if fill
        else "not_observed",
        fill_observed_at=updated if unavailable else fill.observed_at if fill else None,
    )


def reference(value):
    return KisPaperPortfolioStateRef(value.intent.run_id, value.intent.fingerprint)


def project(
    contract=None,
    entry=None,
    exits=(),
    *,
    now=None,
    input_status="ready",
    other=(),
    proofs=None,
    custody=None,
    **changes,
):
    contract = contract or cohort()
    values = (() if entry is None else (entry,)) + exits
    own_refs = tuple(reference(value) for value in values)
    owner = KisPaperPortfolioOwnerBinding(
        contract.owner_ref, ACCOUNT, "SYN", "NASD", own_refs, contract.instrument.binding_ref
    )
    others = tuple(group[0] for group in other)
    states = {value.intent.run_id: value for value in values}
    states.update({value.intent.run_id: value for _, values in other for value in values})
    arguments = dict(
        cohort=contract,
        expected_cohort_ref=contract.fingerprint,
        custody=custody
        or KisPaperFiveSessionCustody(
            None if entry is None else reference(entry), tuple(reference(value) for value in exits)
        ),
        basis=BASIS,
        expected_basis_ref=BASIS.fingerprint,
        owners=(owner,) + others,
        expected_owner_refs={value.owner_ref: value.fingerprint for value in (owner,) + others},
        states=states,
        as_of=now or contract.exit_due + timedelta(minutes=1),
        input_status=input_status,
        cancellation_proofs=proofs,
    )
    arguments.update(changes)
    return project_five_session_cohort(**arguments)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("cohort projection must be pure")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def test_entry_is_only_ready_in_first_window_with_current_input():
    contract = cohort()
    assert (
        project(contract, now=contract.session_opens[0] - timedelta(seconds=1)).status == "deferred"
    )
    assert project(contract, now=contract.session_opens[0]).status == "entry_ready"
    assert (
        project(contract, now=contract.session_opens[0], input_status="unavailable").reason
        == "input_unavailable"
    )
    assert project(contract, now=contract.entry_window_end).reason == "entry_window_elapsed"


@pytest.mark.parametrize(
    "phase", ["intent_recorded", "submission_started", "outcome_unknown", "submitted"]
)
def test_pending_exact_entry_is_never_a_substitute_after_restart_or_input_loss(phase):
    contract = cohort()
    entry = state(contract, phase=phase)
    if phase == "intent_recorded":
        entry = replace(entry, updated_at=entry.intent.created_at + timedelta(seconds=5))
    restored = KisPaperCanaryState.from_dict(entry.to_dict())
    result = project(
        contract,
        restored,
        input_status="unavailable",
        now=(
            entry.intent.created_at + timedelta(seconds=6) if phase == "intent_recorded" else None
        ),
    )
    assert result.status == "reconcile"
    assert result.pending == reference(entry)
    assert result.reason == "entry_recovery_pending"
    assert "SYN" not in str(result.safe_payload())


def test_expired_unsubmitted_entry_closes_no_fill_without_resubmission():
    contract = cohort()
    entry = state(contract, phase="intent_recorded")
    result = project(contract, entry)
    assert (result.status, result.reason, result.owned_quantity) == (
        "closed",
        "entry_terminal_no_fill",
        0,
    )


@pytest.mark.parametrize("index", range(4))
def test_entry_order_ttl_never_becomes_a_day_flat_exit(index):
    contract = cohort()
    result = project(
        contract,
        state(contract, filled="2", remaining="0"),
        now=contract.session_closes[index],
        input_status="unavailable",
    )
    assert (result.status, result.owned_quantity) == ("hold", D(2))


def test_fifth_session_exit_survives_stale_model_input_and_missed_clock():
    contract = cohort()
    entry = state(contract, filled="2", remaining="0", unavailable=True)
    for at in (contract.exit_due, contract.session_closes[-1] + timedelta(days=3)):
        result = project(contract, entry, now=at, input_status="unavailable")
        assert (result.status, result.owned_quantity) == ("exit_ready", D(2))


def test_partial_entry_reconciles_until_residual_is_terminal():
    contract = cohort()
    entry = state(contract, filled="1", remaining="1")
    result = project(contract, entry)
    assert result.status == "reconcile" and result.owned_quantity == 1
    cancelled_partial = replace(
        entry,
        cumulative_fill=replace(entry.cumulative_fill, remaining_quantity=D(0)),
        phase="cancelled",
    )
    result = project(contract, cancelled_partial)
    assert result.status == "exit_ready" and result.owned_quantity == 1


def test_partial_exit_recovery_and_exact_remaining_quantity():
    contract = cohort()
    entry = state(contract, filled="2", remaining="0")
    partial = state(contract, "exit", sell=True, filled="1", remaining="1")
    result = project(contract, entry, (partial,))
    assert (result.status, result.reason, result.owned_quantity) == (
        "reconcile",
        "exit_recovery_pending",
        D(1),
    )
    assert result.pending == reference(partial)
    terminal = replace(
        partial,
        cumulative_fill=replace(partial.cumulative_fill, remaining_quantity=D(0)),
        phase="cancelled",
    )
    assert project(contract, entry, (terminal,)).status == "exit_ready"
    last = state(
        contract,
        "exit-residual",
        sell=True,
        quantity="1",
        filled="1",
        remaining="0",
        at=contract.exit_due + timedelta(seconds=50),
    )
    result = project(
        contract, entry, (terminal, last), now=contract.exit_due + timedelta(minutes=2)
    )
    assert (result.status, result.reason, result.owned_quantity) == ("closed", "owned_flat", D(0))


def test_full_sell_link_is_required_for_flat_not_elapsed_time():
    contract = cohort()
    entry = state(contract, filled="2", remaining="0")
    unknown = state(contract, "exit", sell=True, phase="outcome_unknown")
    assert (
        project(contract, entry, (unknown,), now=contract.exit_due + timedelta(days=20)).status
        == "reconcile"
    )
    filled = state(contract, "exit", sell=True, filled="2", remaining="0")
    restored = tuple(KisPaperCanaryState.from_dict(value.to_dict()) for value in (entry, filled))
    assert project(contract, restored[0], (restored[1],)).status == "closed"


def test_zero_cancel_requires_independent_exact_proof():
    contract = cohort()
    entry = state(contract, filled="0", remaining="0", phase="cancelled")
    assert project(contract, entry).status == "reconcile"
    proof = KisPaperExecutionObservation(
        2, True, "available", entry.current_fill, entry.fill_observed_at, True
    )
    assert project(contract, entry, proofs={entry.intent.run_id: proof}).status == "closed"


def test_provider_rejection_is_not_replaced_by_a_new_entry():
    entry = state(cohort(), phase="rejected", category="provider_rejected")
    assert project(entry=entry).reason == "entry_terminal_no_fill"


def other_group(contract, *, same_symbol=True, phase="submitted", filled="1", run="other"):
    other_contract = replace(
        contract,
        instrument=KisPaperStockInstrument("SYN" if same_symbol else "OTH", "ref:" + "f" * 64),
    )
    other_state = state(
        other_contract, run, phase=phase, filled=filled, remaining=None if filled is None else "0"
    )
    owner = KisPaperPortfolioOwnerBinding(
        other_contract.owner_ref,
        ACCOUNT,
        other_contract.instrument.symbol,
        "NASD",
        (reference(other_state),),
        other_contract.instrument.binding_ref,
    )
    return owner, (other_state,)


@pytest.mark.parametrize("entry", [False, True])
@pytest.mark.parametrize("phase,filled", [("submitted", "1"), ("outcome_unknown", None)])
def test_same_symbol_foreign_inventory_or_pending_owner_is_never_adopted_or_sold(
    entry, phase, filled
):
    contract = cohort()
    result = project(
        contract,
        state(contract, filled="2", remaining="0") if entry else None,
        other=(other_group(contract, phase=phase, filled=filled),),
    )
    assert (result.status, result.reason) == ("reconcile", "exclusive_instrument_conflict")
    assert result.owned_quantity is None


def test_unknown_other_symbol_does_not_create_global_pause():
    contract = cohort()
    result = project(
        contract,
        state(contract, filled="2", remaining="0"),
        other=(other_group(contract, same_symbol=False, phase="outcome_unknown", filled=None),),
    )
    assert result.status == "exit_ready" and result.owned_quantity == 2


def test_cleared_custody_or_added_same_owner_intent_cannot_duplicate_buy():
    contract = cohort()
    entry = state(contract, phase="outcome_unknown")
    assert (
        project(contract, entry, custody=KisPaperFiveSessionCustody()).reason
        == "cohort_custody_mismatch"
    )
    unrelated = state(contract, "unrelated", sell=True, filled="0", remaining="0")
    assert (
        project(
            contract,
            state(contract, filled="2", remaining="0"),
            (unrelated,),
            custody=KisPaperFiveSessionCustody(
                reference(state(contract, filled="2", remaining="0"))
            ),
        ).reason
        == "cohort_custody_mismatch"
    )


def test_wrong_entry_decision_or_early_sell_never_prepares_exit():
    contract = cohort()
    entry = state(contract, filled="2", remaining="0")
    bad = replace(entry, intent=replace(entry.intent, decision_id="other-decision"))
    assert project(contract, bad).reason == "entry_contract_mismatch"
    early = state(
        contract, "early", sell=True, filled="1", remaining="0", at=contract.session_opens[1]
    )
    assert project(contract, entry, (early,)).reason == "exit_contract_mismatch"


def test_missing_state_or_changed_basis_is_invalid_not_flat():
    contract = cohort()
    entry = state(contract, filled="2", remaining="0")
    with pytest.raises(KisPaperPortfolioBudgetError, match="referenced_state_missing"):
        project(contract, entry, states={})
    with pytest.raises(KisPaperPortfolioBudgetError, match="basis_binding_mismatch"):
        project(contract, entry, expected_basis_ref="sha256:" + "f" * 64)


def test_frozen_calendar_preserves_dst_and_holiday_sessions_not_five_civil_days():
    dst = cohort(("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"))
    assert dst.session_opens[0].hour == 13 and dst.session_opens[-1].hour == 14
    assert (
        project(dst, state(dst, filled="2", remaining="0"), now=dst.session_closes[3]).status
        == "hold"
    )
    assert project(dst, state(dst, filled="2", remaining="0")).status == "exit_ready"
    holiday = cohort(("2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30", "2026-12-01"))
    early_closes = list(holiday.session_closes)
    early_closes[2] -= timedelta(hours=3)
    holiday = replace(holiday, session_closes=tuple(early_closes))
    assert (
        project(
            holiday, state(holiday, filled="2", remaining="0"), now=holiday.session_closes[2]
        ).status
        == "hold"
    )
    assert holiday.exit_due.date().isoformat() == "2026-12-01"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("calendar_ref", "missing"),
        ("entry_decision_id", "arbitrary"),
        ("session_opens", ()),
        ("entry_window_end", datetime(2026, 1, 1, tzinfo=UTC)),
        ("exit_due", datetime(2026, 10, 16, 19, tzinfo=UTC)),
    ],
)
def test_invalid_contract_is_rejected_without_private_values(field, bad):
    with pytest.raises(ValueError):
        replace(cohort(), **{field: bad})


def test_changed_contract_reference_and_duplicate_custody_are_rejected():
    with pytest.raises(ValueError, match="cohort_binding_mismatch"):
        project(expected_cohort_ref="sha256:" + "f" * 64)
    entry = reference(state(cohort(), filled="2", remaining="0"))
    with pytest.raises(ValueError, match="cohort_custody_duplicate"):
        KisPaperFiveSessionCustody(entry, (entry,))
