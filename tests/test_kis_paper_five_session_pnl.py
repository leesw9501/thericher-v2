from __future__ import annotations

import builtins
import json
import socket
from dataclasses import replace
from datetime import timedelta
from decimal import Context, Decimal, Inexact, Rounded, localcontext
from fractions import Fraction

import pytest

from test_kis_paper_five_session import ACCOUNT, BASIS, cohort, reference, state
from thericher_v2.execution.kis_paper_budget_strategy import _stock_identity
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryState
from thericher_v2.execution.kis_paper_five_session import KisPaperFiveSessionCustody
from thericher_v2.execution.kis_paper_five_session_pnl import (
    KisPaperFiveSessionAccountingSnapshot as Snapshot,
)
from thericher_v2.execution.kis_paper_five_session_pnl import (
    KisPaperFiveSessionCloseInput as Close,
)
from thericher_v2.execution.kis_paper_five_session_pnl import (
    KisPaperFiveSessionCloseMark as Mark,
)
from thericher_v2.execution.kis_paper_five_session_pnl import (
    KisPaperFiveSessionFeeReceipt as Fee,
)
from thericher_v2.execution.kis_paper_five_session_pnl import (
    project_five_session_pnl,
)
from thericher_v2.execution.kis_paper_portfolio_budget import KisPaperPortfolioOwnerBinding
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument

D = Decimal
SOURCE = "sha256:" + "f" * 64


def exit_state(c, *, index=0, quantity="2", filled="2", price="11", phase="submitted"):
    identity = _stock_identity(
        {
            "account_ref": ACCOUNT,
            "basis_ref": BASIS.fingerprint,
            "stocks": {
                "SYN": {
                    "exchange": "NASD",
                    "instrument_binding_ref": c.instrument.binding_ref,
                }
            },
        },
        "SYN",
        "five-exit-" + c.fingerprint[7:] + "-" + str(index),
        "sell",
    )
    s = state(c, "exit-" + str(index), sell=True, quantity=quantity, filled=filled, phase=phase)
    intent = replace(
        s.intent,
        run_id="bk-" + identity,
        client_order_id="stock-" + identity,
        decision_id="stock-" + identity,
    )
    fill = (
        None
        if s.cumulative_fill is None
        else replace(s.cumulative_fill, gross_amount=D(filled) * D(price))
    )
    return replace(s, intent=intent, cumulative_fill=fill)


def custody(values):
    return KisPaperFiveSessionCustody(
        None if not values else reference(values[0]), tuple(reference(s) for s in values[1:])
    )


def snapshot(c, values=(), *, at=None, fees=None, other=(), **changes):
    owned = custody(values)
    own = KisPaperPortfolioOwnerBinding(
        c.owner_ref, ACCOUNT, "SYN", "NASD", owned.state_refs, c.instrument.binding_ref
    )
    owners = (own,) + tuple(o for o, _ in other)
    states = {s.intent.run_id: s for s in values}
    states.update({s.intent.run_id: s for _, rows in other for s in rows})
    args = dict(
        cohort_ref=c.fingerprint,
        custody=owned,
        basis=BASIS,
        expected_basis_ref=BASIS.fingerprint,
        owners=owners,
        expected_owner_refs={o.owner_ref: o.fingerprint for o in owners},
        states=states,
        as_of=at or c.session_closes[-1] + timedelta(seconds=1),
        source_ref=SOURCE,
        fees=fees,
    )
    args.update(changes)
    return Snapshot(**args)


def fee(c, s, amount="0.02", *, at=None, **changes):
    f = s.cumulative_fill
    args = dict(
        cohort_ref=c.fingerprint,
        state_ref=reference(s),
        fill_identity_ref=f.identity_ref,
        fill_quantity=f.quantity,
        fill_gross_usd=f.gross_amount,
        fee_usd=D(amount),
        source_ref=SOURCE,
        observed_at=at or s.updated_at,
    )
    args.update(changes)
    return Fee(**args)


def mark(c, index, price="12", **changes):
    args = dict(
        cohort_ref=c.fingerprint,
        calendar_ref=c.calendar_ref,
        instrument=c.instrument,
        close_at=c.session_closes[index],
        price_usd=D(price),
        source_ref=SOURCE,
        observed_at=c.session_closes[index],
    )
    args.update(changes)
    return Mark(**args)


def project(c, current, closes=None, **changes):
    args = dict(
        cohort=c,
        expected_cohort_ref=c.fingerprint,
        expected_custody=current.custody,
        snapshot=current,
        closes=closes or tuple(Close(t) for t in c.session_closes),
    )
    args.update(changes)
    return project_five_session_pnl(**args)


def full_history(*, fees=False):
    c = cohort()
    entry, sell = state(c, filled="2"), exit_state(c)
    entry_fees = (fee(c, entry),) if fees else None
    all_fees = (fee(c, entry), fee(c, sell, "0.03")) if fees else None
    closes = tuple(
        Close(t, snapshot(c, (entry,), at=t, fees=entry_fees), mark(c, i))
        for i, t in enumerate(c.session_closes[:-1])
    ) + (
        Close(
            c.session_closes[-1], snapshot(c, (entry, sell), at=c.session_closes[-1], fees=all_fees)
        ),
    )
    return c, snapshot(c, (entry, sell), fees=all_fees), closes


def test_five_independent_closes_use_owned_gross_not_shared_cash_or_nav():
    c, current, closes = full_history()
    out = project(c, current, closes)
    for p in out.closes[:4]:
        assert p.retained_quantity == 2
        assert p.remaining_entry_cost_usd == 20 and p.gross_realized_usd == 0
        assert p.marked_value_usd == 24 and p.gross_unrealized_usd == p.gross_total_usd == 4
        assert p.fee_status == "not_observed" and p.net_pnl_usd is None
    assert out.current.gross_realized_usd == out.current.gross_total_usd == 2
    assert out.current.retained_quantity == 0
    assert out.current.chronology == "closed_flat_cashflow"
    assert not hasattr(out, "nav") and not hasattr(out.current, "cash")


def test_exact_fee_coverage_and_final_flat_without_mark():
    c, current, closes = full_history(fees=True)
    out = project(c, current, closes)
    assert out.closes[0].fees_usd == Fraction(1, 50)
    assert out.closes[0].net_pnl_usd == Fraction(199, 50)
    assert out.current.fees_usd == Fraction(1, 20)
    assert out.current.net_pnl_usd == Fraction(39, 20)
    assert out.closes[-1].valuation_status == "complete"


def test_restart_and_repeated_cumulative_snapshots_are_not_added():
    c, current, closes = full_history(fees=True)
    restored = replace(
        current,
        states={
            run: KisPaperCanaryState.from_dict(s.to_dict()) for run, s in current.states.items()
        },
    )
    a, b = project(c, current, closes), project(c, restored, closes)
    assert a == b
    assert b.current.positive_fill_count == 2 and b.current.gross_realized_usd == 2


def test_snapshot_copies_mappings_and_nested_state_dtos():
    c = cohort()
    entry = state(c, filled="2")
    states = {entry.intent.run_id: entry}
    snap = snapshot(c, (entry,), states=states)
    states.clear()
    assert snap.states[entry.intent.run_id] is not entry
    assert snap.states[entry.intent.run_id].intent is not entry.intent
    with pytest.raises(TypeError):
        snap.states[entry.intent.run_id] = entry
    with pytest.raises(TypeError):
        snap.expected_owner_refs[c.owner_ref] = SOURCE


def test_same_instrument_other_cohort_cannot_replace_entry():
    c = cohort()
    other = replace(c, entry_decision_id="decision:sha256:" + "9" * 64)
    snap = snapshot(c, (state(other, filled="2"),))
    assert other.owner_ref == c.owner_ref
    with pytest.raises(ValueError, match="request_identity"):
        project(c, snap)


def test_exact_expected_custody_not_generated_from_supplied_state():
    c, snap, _ = full_history()
    with pytest.raises(ValueError, match="custody_mismatch"):
        project(c, snap, expected_custody=KisPaperFiveSessionCustody(snap.custody.entry))
    refs = dict(snap.expected_owner_refs)
    refs[c.owner_ref] = SOURCE
    with pytest.raises(ValueError, match="owner_binding_mismatch"):
        project(c, replace(snap, expected_owner_refs=refs))


def test_fifth_flat_state_cannot_reconstruct_first_four_closes():
    c, current, _ = full_history()
    for t in c.session_closes[:4]:
        with pytest.raises(ValueError, match="snapshot_after_close"):
            Close(t, current)
    forged_clock = replace(current, as_of=c.session_closes[0])
    slots = (Close(c.session_closes[0], forged_clock, mark(c, 0)),) + tuple(
        Close(t) for t in c.session_closes[1:]
    )
    with pytest.raises(ValueError, match="state_time_invalid"):
        project(c, current, slots)


def test_late_partial_fill_and_cancel_cannot_backcast():
    c = cohort()
    entry = state(c, filled="1", quantity="2")
    late = c.session_closes[0] + timedelta(seconds=1)
    fill = replace(entry.cumulative_fill, observed_at=late)
    entry = replace(
        entry, phase="cancelled", cumulative_fill=fill, fill_observed_at=late, updated_at=late
    )
    current = snapshot(c, (entry,))
    backcast = replace(current, as_of=c.session_closes[0])
    slots = (Close(c.session_closes[0], backcast, mark(c, 0)),) + tuple(
        Close(t) for t in c.session_closes[1:]
    )
    with pytest.raises(ValueError, match="state_time_invalid"):
        project(c, current, slots)


def test_held_missing_close_is_unavailable_not_zero_or_censored():
    c, snap, slots = full_history()
    slots = (replace(slots[0], mark=None),) + slots[1:]
    out = project(c, snap, slots)
    first = out.closes[0]
    assert len(out.closes) == 5 and first.retained_quantity == 2
    assert first.gross_realized_usd == 0 and first.remaining_entry_cost_usd == 20
    assert first.valuation_status == "mark_missing" and first.gross_total_usd is None
    assert out.current.gross_realized_usd == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("close_at", "clock"),
        ("cohort_ref", "sha256:" + "0" * 64),
        ("calendar_ref", "sha256:" + "0" * 64),
        ("instrument", KisPaperStockInstrument("ALT", "ref:" + "0" * 64)),
        ("observed_at", "future"),
    ],
)
def test_wrong_mark_binding_is_not_used(field, value):
    c, snap, slots = full_history()
    if value == "clock":
        value = c.session_closes[0] - timedelta(seconds=1)
    if value == "future":
        value = snap.as_of + timedelta(seconds=1)
    slots = (replace(slots[0], mark=replace(slots[0].mark, **{field: value})),) + slots[1:]
    with pytest.raises(ValueError, match="mark_binding"):
        project(c, snap, slots)


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_nonfinite_or_nonpositive_mark_never_rounded_to_valid(price):
    with pytest.raises(ValueError, match="amount_invalid"):
        mark(cohort(), 0, price)


def test_wrong_close_count_clock_and_source_are_rejected():
    c, snap, slots = full_history()
    with pytest.raises(ValueError, match="contract_invalid"):
        project(c, snap, slots[:-1])
    with pytest.raises(ValueError, match="close_clock"):
        project(c, snap, tuple(reversed(slots)))
    with pytest.raises(ValueError, match="source_invalid"):
        replace(snap, source_ref="private-shaped-not-a-hash")


def test_unobserved_and_incomplete_fees_never_become_zero():
    c, snap, slots = full_history(fees=True)
    out = project(c, replace(snap, fees=None), slots)
    assert out.current.fee_status == "not_observed" and out.current.net_pnl_usd is None
    out = project(c, replace(snap, fees=snap.fees[:1]), slots)
    assert out.current.fee_status == "incomplete" and out.current.fees_usd is None
    assert out.current.gross_realized_usd == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("fill_quantity", D(1)),
        ("fill_gross_usd", D(19)),
        ("fill_identity_ref", "sha256:" + "0" * 64),
        ("cohort_ref", "sha256:" + "0" * 64),
    ],
)
def test_fee_receipt_exact_positive_fill_coverage(field, value):
    c, snap, slots = full_history(fees=True)
    bad = replace(snap.fees[0], **{field: value})
    with pytest.raises(ValueError, match="fee_binding"):
        project(c, replace(snap, fees=(bad, snap.fees[1])), slots)


def test_duplicate_and_late_fee_receipts_rejected_without_summing():
    c, snap, slots = full_history(fees=True)
    with pytest.raises(ValueError, match="fee_binding"):
        project(c, replace(snap, fees=snap.fees + (snap.fees[0],)), slots)
    late = replace(
        slots[0].snapshot.fees[0], observed_at=c.session_closes[0] + timedelta(seconds=1)
    )
    slots = (replace(slots[0], snapshot=replace(slots[0].snapshot, fees=(late,))),) + slots[1:]
    with pytest.raises(ValueError, match="fee_binding"):
        project(c, snap, slots)


def test_partial_unknown_entry_and_exit_do_not_claim_gross_completeness():
    c = cohort()
    entry = state(c, quantity="3", filled="3")
    sell = exit_state(c, quantity="3", filled="1")
    out = project(c, snapshot(c, (entry, sell)))
    assert out.current.retained_quantity == 2
    assert out.current.accounting_status == "incomplete"
    assert out.current.gross_realized_usd is out.current.net_pnl_usd is None
    unknown = state(c, phase="outcome_unknown")
    assert project(c, snapshot(c, (unknown,))).current.retained_quantity == 0
    assert project(c, snapshot(c, (unknown,))).current.accounting_status == "incomplete"


def test_compound_foreign_partial_unknown_missing_mark_no_fees():
    c = cohort()
    entry = state(c, filled="2")
    sell = exit_state(c, filled="1")
    foreign_contract = replace(c, instrument=KisPaperStockInstrument("SYN", "ref:" + "8" * 64))
    foreign = state(foreign_contract, filled="1", quantity="1")
    owner = KisPaperPortfolioOwnerBinding(
        foreign_contract.owner_ref,
        ACCOUNT,
        "SYN",
        "NASD",
        (reference(foreign),),
        foreign_contract.instrument.binding_ref,
    )
    current = snapshot(c, (entry, sell), other=((owner, (foreign,)),))
    slots = tuple(
        Close(t, snapshot(c, (entry,), at=t, other=((owner, (foreign,)),)))
        for t in c.session_closes[:4]
    ) + (Close(c.session_closes[-1], replace(current, as_of=c.session_closes[-1])),)
    out = project(c, current, slots)
    assert out.current.accounting_status == "unavailable"
    assert out.current.retained_quantity is out.current.net_pnl_usd is None
    assert out.current.fee_status == "not_observed" and len(out.closes) == 5
    assert out.closes[0].valuation_status == "unavailable"
    assert current.states[foreign.intent.run_id] == foreign


def test_cumulative_regression_and_missing_retained_fill_fail():
    c, snap, slots = full_history()
    entry = next(iter(snap.states.values()))
    reset = replace(
        entry, cumulative_fill=None, fill_observation_status="not_observed", fill_observed_at=None
    )
    with pytest.raises(ValueError, match="snapshot_regression"):
        project(c, snapshot(c, (reset,)), slots[:4] + (Close(c.session_closes[-1]),))


def test_future_closes_unavailable_not_a_prediction():
    c = cohort()
    s = snapshot(c, (state(c, filled="2"),), at=c.session_closes[0])
    slots = (Close(c.session_closes[0], s, mark(c, 0)),) + tuple(
        Close(t) for t in c.session_closes[1:]
    )
    out = project(c, s, slots)
    assert [p.valuation_status for p in out.closes] == ["complete"] + ["not_due"] * 4


def test_older_entry_snapshot_cannot_value_fifth_close_or_drop_other_four_rows():
    c, snap, slots = full_history()
    stale = Close(c.session_closes[-1], slots[0].snapshot, mark(c, 4))
    out = project(c, snap, slots[:4] + (stale,))
    assert [p.valuation_status for p in out.closes] == ["complete"] * 4 + ["stale_snapshot"]
    assert out.closes[-1].gross_total_usd is out.closes[-1].retained_quantity is None
    assert out.current.gross_realized_usd == 2


def test_close_bound_snapshot_still_cannot_omit_known_preclose_exit():
    c, snap, slots = full_history()
    omitted = replace(slots[0].snapshot, as_of=c.session_closes[-1])
    out = project(c, snap, slots[:4] + (Close(c.session_closes[-1], omitted, mark(c, 4)),))
    assert out.closes[-1].valuation_status == "custody_incomplete"
    assert out.closes[-1].gross_total_usd is None
    assert all(p.valuation_status == "complete" for p in out.closes[:4])


def test_old_nofill_state_not_forward_filled_against_known_later_entry():
    c = cohort()
    old = snapshot(c, (), at=c.session_opens[0] - timedelta(seconds=1))
    entry = state(c, filled="2")
    current = snapshot(c, (entry,))
    out = project(
        c, current, tuple(Close(t, old, mark(c, i)) for i, t in enumerate(c.session_closes))
    )
    assert all(
        p.valuation_status == "stale_snapshot" and p.gross_total_usd is None for p in out.closes
    )


def test_late_final_observation_cannot_prove_open_owner_realized_split():
    c = cohort()
    entry = state(c, quantity="3", filled="3")
    late = c.exit_due + timedelta(seconds=20)
    entry = replace(
        entry,
        cumulative_fill=replace(entry.cumulative_fill, observed_at=late),
        fill_observed_at=late,
        updated_at=late,
    )
    sell = exit_state(c, quantity="1", filled="1")
    out = project(c, snapshot(c, (entry, sell)))
    assert out.current.retained_quantity == 2
    assert out.current.accounting_status == "incomplete"
    assert out.current.chronology == "unavailable"
    assert out.current.gross_realized_usd is None


def test_fee_regression_is_not_a_new_profitable_total():
    c, snap, slots = full_history(fees=True)
    lowered = replace(snap.fees[0], fee_usd=D("0.01"))
    with pytest.raises(ValueError, match="fee_regression"):
        project(c, replace(snap, fees=(lowered, snap.fees[1])), slots)


def test_unrelated_unknown_spy_does_not_hide_complete_cohort_gross():
    c, snap, slots = full_history()
    spy_contract = replace(c, instrument=KisPaperStockInstrument("SPY", "ref:" + "8" * 64))
    unknown = state(spy_contract, phase="outcome_unknown")
    owner = KisPaperPortfolioOwnerBinding(
        spy_contract.owner_ref,
        ACCOUNT,
        "SPY",
        "NASD",
        (reference(unknown),),
        spy_contract.instrument.binding_ref,
    )
    own = tuple(snap.states.values())
    current = snapshot(c, own, other=((owner, (unknown,)),))
    out = project(c, current, slots)
    assert out.current.accounting_status == "complete" and out.current.gross_realized_usd == 2
    assert current.basis == BASIS and current.states[unknown.intent.run_id] == unknown


def test_exact_fraction_arithmetic_independent_of_decimal_traps():
    c, snap, slots = full_history(fees=True)
    expected = project(c, snap, slots)
    for precision in (2, 7, 50):
        with localcontext(Context(prec=precision)) as ctx:
            ctx.traps[Inexact] = ctx.traps[Rounded] = True
            assert project(c, snap, slots) == expected
            assert ctx.prec == precision and ctx.traps[Inexact] and ctx.traps[Rounded]


def test_no_io_and_safe_payload_no_private_facts(monkeypatch):
    c, snap, slots = full_history(fees=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("projection attempted I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    out = project(c, snap, slots)
    payload = json.dumps(out.safe_payload())
    for secret in (c.fingerprint, c.owner_ref, ACCOUNT, SOURCE, "gross_realized_usd", "price_usd"):
        assert secret not in payload and secret not in repr(out) and secret not in repr(snap)
    assert out.safe_payload()["settled_cash"] == "not_observed"
