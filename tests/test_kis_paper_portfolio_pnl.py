from __future__ import annotations

import builtins
import json
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from pathlib import Path
from unittest.mock import Mock

import pytest

from thericher_v2.execution import kis_paper_portfolio_pnl as module
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioBudgetError,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
)

D = Decimal
START = datetime(2026, 1, 5, 15, tzinfo=UTC)
AS_OF = START + timedelta(days=1)
ACCOUNT = "a" * 64
BASIS = KisPaperPortfolioBudgetBasis(ACCOUNT, D("10000"), D("1000"), START)


def state(
    run,
    *,
    side="buy",
    quantity="1",
    amount="100",
    filled="full",
    index=0,
    observed_seconds=2,
    symbol="SPY",
    phase="submitted",
    observation="available",
    category=None,
    expired=False,
    remaining=None,
):
    at = START + timedelta(minutes=index)
    intent = KisPaperCanaryIntent(
        run,
        "client-" + run,
        "decision-" + run,
        symbol,
        "AMEX" if symbol in {"SPY", "GLD"} else "NASD",
        D(quantity),
        D("500"),
        at,
        at + timedelta(seconds=20),
        side,
    )
    if filled == "full":
        filled = quantity if phase == "submitted" else None
    attempted = phase != "intent_recorded"
    known = phase in {"submitted", "cancel_started", "cancelled"} or filled is not None
    raw = "SYNTHETIC-" + run if known else None
    order_at = at + timedelta(seconds=1) if attempted else None
    observed_at = at + timedelta(seconds=observed_seconds)
    updated = max(at + timedelta(seconds=30 if expired else 5), observed_at)
    fill = (
        None
        if filled is None
        else KisPaperCumulativeFill(
            fill_identity_ref(
                raw_order_id=raw,
                order_at=order_at,
                symbol=symbol,
                exchange=intent.exchange,
                side=side,
                quantity=intent.quantity,
            ),
            intent.quantity,
            D(filled),
            D(amount),
            observed_at,
            None if remaining is None else D(remaining),
        )
    )
    status = observation if fill is not None or observation != "available" else "not_observed"
    return KisPaperCanaryState(
        intent,
        phase,
        updated,
        "reconciliation_unresolved",
        broker_order_id=raw,
        submission_started_at=order_at,
        submitted_at=order_at if known else None,
        submit_response_category=category,
        cumulative_fill=fill,
        fill_observation_status=status,
        fill_observed_at=(observed_at if status == "available" else updated)
        if status != "not_observed"
        else None,
    )


def owner(name, *states, symbol="SPY"):
    return KisPaperPortfolioOwnerBinding(
        name,
        ACCOUNT,
        symbol,
        "AMEX" if symbol in {"SPY", "GLD"} else "NASD",
        tuple(KisPaperPortfolioStateRef(s.intent.run_id, s.intent.fingerprint) for s in states),
    ), states


def arguments(*groups, **changes):
    kwargs = dict(
        basis=BASIS,
        expected_basis_ref=BASIS.fingerprint,
        owners=tuple(o for o, _ in groups),
        expected_owner_refs={o.owner_ref: o.fingerprint for o, _ in groups},
        states={s.intent.run_id: s for _, states in groups for s in states},
        as_of=AS_OF,
    )
    kwargs.update(changes)
    return kwargs


def project(*groups, **changes):
    return module.project_kis_paper_portfolio_pnl(**arguments(*groups, **changes))


def roundtrip(name="owner", *, buy="100", sell="120", symbol="SPY"):
    return owner(
        name,
        state(name + "-buy", amount=buy, symbol=symbol),
        state(name + "-sell", side="sell", amount=sell, index=1, symbol=symbol),
        symbol=symbol,
    )


def assert_identity(result):
    assert (
        result.gross_cash_usd + result.remaining_entry_cost_usd - result.allocated_usd
        == result.gross_realized_usd
    )
    assert (
        sum((row.gross_realized_usd for row in result.owners), Fraction(0))
        == result.gross_realized_usd
    )


def test_validation_is_first_and_rounded_budget_output_is_not_used(monkeypatch):
    real = module.project_kis_paper_portfolio_budget
    validate = Mock(side_effect=lambda **kwargs: (real(**kwargs), object())[1])
    monkeypatch.setattr(module, "project_kis_paper_portfolio_budget", validate)
    result = project(roundtrip())
    validate.assert_called_once()
    assert result.gross_realized_usd == 20
    assert_identity(result)


@pytest.mark.parametrize("groups", [(), (owner("empty"),)])
def test_empty_owned_scope_is_no_realized_fills_not_observed_zero_profit(groups):
    result = project(*groups)
    assert result.status == "no_realized_fills"
    assert result.gross_realized_usd == 0
    assert result.safe_payload()["gross_pnl_sign"] == "not_observed"
    assert_identity(result)


@pytest.mark.parametrize("amount,sign", [("120", "positive"), ("80", "negative"), ("100", "zero")])
def test_complete_roundtrip_sign_is_gross_only(amount, sign):
    result = project(roundtrip(sell=amount))
    assert result.gross_realized_usd == Fraction(D(amount)) - 100
    safe = result.safe_payload()
    assert safe["status"] == "gross_realized_observed" and safe["gross_pnl_sign"] == sign
    assert safe["fees"] == safe["settled_cash"] == safe["net_pnl"] == "not_observed"
    assert_identity(result)


def test_average_cost_not_fifo_partial_inventory_sell():
    group = owner(
        "owner",
        state("first", quantity="2", amount="180"),
        state("second", amount="150", index=1),
        state("sell", side="sell", amount="200", index=2),
    )
    result = project(group)
    row = result.owners[0]
    assert (row.quantity, row.remaining_entry_cost_usd, row.gross_realized_usd) == (2, 220, 90)
    assert row.gross_realized_usd != 110  # FIFO would release the first 90-unit entry.
    assert_identity(result)


def test_partial_sell_rational_basis_is_exact_not_rounded_native_display():
    result = project(
        owner(
            "owner",
            state("buy", quantity="3", amount="100"),
            state("sell", side="sell", amount="50", index=1),
        )
    )
    row = result.owners[0]
    assert row.remaining_entry_cost_usd == Fraction(200, 3)
    assert row.gross_realized_usd == Fraction(50, 3)
    assert result.gross_cash_usd == 950
    assert_identity(result)


@pytest.mark.parametrize("precision,rounding", [(1, ROUND_UP), (2, ROUND_DOWN), (7, ROUND_UP)])
def test_hostile_decimal_context_does_not_change_exact_projection(precision, rounding):
    kwargs = arguments(
        owner(
            "owner",
            state("buy", quantity="3", amount="100"),
            state("sell", side="sell", amount="50", index=1),
        )
    )
    expected = module.project_kis_paper_portfolio_pnl(**kwargs)
    with localcontext() as context:
        context.prec, context.rounding = precision, rounding
        context.traps[Inexact] = context.traps[Rounded] = True
        assert module.project_kis_paper_portfolio_pnl(**kwargs) == expected


def test_same_instrument_two_owners_never_share_average_cost():
    first = roundtrip("first", buy="100", sell="150")
    second = owner(
        "second",
        state("second-buy", quantity="2", amount="600"),
        state("second-sell", side="sell", amount="250", index=1),
    )
    result = project(first, second)
    assert [row.gross_realized_usd for row in result.owners] == [50, -50]
    assert result.owners[1].remaining_entry_cost_usd == 300
    assert result.safe_payload()["gross_pnl_sign"] == "zero"
    assert_identity(result)


def test_cross_instrument_observation_overlap_does_not_make_owner_chronology_ambiguous():
    spy = roundtrip("spy")
    tlt = roundtrip("tlt", symbol="TLT", buy="200", sell="190")
    result = project(spy, tlt)
    assert result.status == "gross_realized_observed" and result.gross_realized_usd == 10
    assert_identity(result)


@pytest.mark.parametrize(
    "phase",
    [
        "submission_started",
        "outcome_unknown",
        "submitted",
        "cancel_started",
        "cancelled",
        "rejected",
        "intent_recorded",
    ],
)
def test_pending_or_unknown_amounts_are_not_zero_profit(phase):
    unknown = state("pending", phase=phase, observation="not_observed", filled=None)
    result = project(owner("owner", unknown))
    assert result.status == "incomplete" and result.gross_realized_usd is None
    assert result.owners[0].gross_realized_usd is None
    assert result.safe_payload()["pending_intent_count"] == 1
    assert result.safe_payload()["gross_pnl_sign"] == "not_observed"


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_positive_partial_cumulative_request_cannot_be_a_complete_pnl(side):
    partial = state("partial", side=side, quantity="2", filled="1", amount="90", index=1)
    states = (partial,) if side == "buy" else (state("buy", quantity="2", amount="100"), partial)
    result = project(owner("owner", *states))
    assert result.owners[0].reasons == ("pending_amounts",)
    assert result.gross_cash_usd is None and result.remaining_entry_cost_usd is None


@pytest.mark.parametrize(
    "phase,category", [("intent_recorded", None), ("rejected", "provider_rejected")]
)
def test_definitive_no_submit_is_no_realized_fills(phase, category):
    never = state(
        "never",
        phase=phase,
        category=category,
        expired=True,
        observation="not_observed",
        filled=None,
    )
    result = project(owner("owner", never))
    assert result.status == "no_realized_fills"
    assert result.safe_payload()["pending_intent_count"] == 0
    assert result.safe_payload()["gross_pnl_sign"] == "not_observed"


def test_zero_fill_cancel_requires_exact_native_proof():
    cancelled = state("cancel", phase="cancelled", filled="0", amount="0", remaining="0")
    group = owner("owner", cancelled)
    assert project(group).status == "incomplete"
    proof = KisPaperExecutionObservation(
        2, True, "available", cancelled.current_fill, cancelled.fill_observed_at, True
    )
    result = project(group, cancellation_proofs={cancelled.intent.run_id: proof})
    assert result.status == "no_realized_fills" and result.gross_realized_usd == 0


@pytest.mark.parametrize("observation", ["absent", "unavailable"])
def test_retained_final_fill_survives_later_nonconflicting_read(observation):
    buy = state("buy", quantity="2", amount="200")
    buy = replace(
        buy, updated_at=AS_OF, fill_observed_at=AS_OF, fill_observation_status=observation
    )
    result = project(owner("owner", buy, state("sell", side="sell", amount="120", index=1)))
    assert result.status == "gross_realized_observed" and result.gross_realized_usd == 20
    assert buy.current_fill is None
    assert result.owners[0].chronology == "serialized_opposite_side_blocks"


@pytest.mark.parametrize(
    "observation", ["ambiguous", "identity_mismatch", "fields_invalid", "conflict"]
)
def test_conflicting_final_fill_withholds_sign(observation):
    result = project(
        owner("owner", state("buy", observation=observation), state("sell", side="sell", index=1))
    )
    assert result.owners[0].reasons == ("fill_conflict",)
    assert result.safe_payload()["gross_pnl_sign"] == "not_observed"


@pytest.mark.parametrize("late_seconds", [61, 180])
def test_late_final_observation_cannot_produce_an_actual_realized_sign(late_seconds):
    result = project(
        owner(
            "owner",
            state("buy", quantity="2", amount="200", observed_seconds=late_seconds),
            state("sell", side="sell", amount="120", index=1),
        )
    )
    assert result.status == "incomplete"
    assert result.owners[0].reasons == ("ambiguous_fill_chronology",)
    assert result.gross_realized_usd is None


def test_observed_exactly_at_next_positive_creation_is_eligible():
    result = project(
        owner(
            "owner",
            state("buy", quantity="2", amount="200", observed_seconds=60),
            state("sell", side="sell", amount="120", index=1),
        )
    )
    assert result.status == "gross_realized_observed" and result.gross_realized_usd == 20
    assert result.owners[0].chronology == "serialized_opposite_side_blocks"


def test_sign_flip_conservation_is_not_average_cost_execution_chronology():
    group = owner(
        "owner",
        state("first-buy", amount="100"),
        state("late-buy", amount="200", index=1, observed_seconds=120),
        state("sell", side="sell", amount="140", index=2),
    )
    native = module.project_kis_paper_portfolio_budget(**arguments(group))
    snapshot_pnl = native.gross_cash + native.entry_cost - native.allocated_usd
    assert snapshot_pnl == -10
    assert D(140) - D(100) == 40  # Feasible BUY1 -> SELL -> BUY2 ordering flips the sign.
    result = project(group)
    assert result.owners[0].reasons == ("ambiguous_fill_chronology",)
    assert result.owners[0].chronology == "unavailable"
    assert result.owners[0].gross_realized_usd is None
    assert result.safe_payload()["gross_pnl_sign"] == "not_observed"


def test_every_order_in_prior_side_block_must_be_final_before_opposite_creation():
    result = project(
        owner(
            "owner",
            state("first-buy", amount="100", observed_seconds=150),
            state("second-buy", amount="200", index=1),
            state("sell", side="sell", amount="140", index=2),
        )
    )
    assert result.owners[0].reasons == ("ambiguous_fill_chronology",)
    assert result.gross_realized_usd is None


def test_same_side_overlap_is_eligible_if_all_totals_precede_opposite_block():
    result = project(
        owner(
            "owner",
            state("first-buy", amount="100", observed_seconds=80),
            state("second-buy", amount="200", index=1),
            state("sell", side="sell", amount="140", index=2),
        )
    )
    assert result.owners[0].chronology == "serialized_opposite_side_blocks"
    assert result.gross_realized_usd == -10
    assert result.safe_payload()["serialized_owner_count"] == 1
    assert_identity(result)


def test_interleaved_partial_amount_cannot_use_flat_cashflow_exception():
    result = project(
        owner(
            "owner",
            state("buy", quantity="2", filled="1", amount="100"),
            state("sell", side="sell", amount="140", index=1),
        )
    )
    assert result.owners[0].reasons == ("pending_amounts",)
    assert result.owners[0].chronology == "unavailable"
    assert result.safe_payload()["flat_cashflow_owner_count"] == 0
    assert result.gross_realized_usd is None


def test_known_closed_flat_cashflow_is_sequence_independent_without_per_sale_claim():
    result = project(
        owner(
            "owner",
            state("first-buy", amount="100"),
            state("late-buy", amount="200", index=1, observed_seconds=120),
            state("first-sell", side="sell", amount="140", index=2),
            state("last-sell", side="sell", amount="170", index=3),
        )
    )
    row = result.owners[0]
    assert row.chronology == "closed_flat_cashflow"
    assert row.quantity == row.remaining_entry_cost_usd == 0
    assert row.gross_realized_usd == row.sell_gross_usd - row.buy_gross_usd == 10
    assert result.safe_payload()["flat_cashflow_owner_count"] == 1
    assert result.safe_payload()["serialized_owner_count"] == 0
    assert not hasattr(row, "per_sale_pnl")
    assert_identity(result)


def test_ambiguous_owner_is_scoped_not_a_hold_on_unrelated_complete_owner():
    good = roundtrip("good")
    ambiguous = owner(
        "ambiguous",
        state("first-buy", amount="100"),
        state("late-buy", amount="200", index=1, observed_seconds=120),
        state("sell", side="sell", amount="140", index=2),
    )
    result = project(good, ambiguous)
    assert result.owners[0] == project(good).owners[0]
    assert result.owners[0].gross_realized_usd == 20
    assert result.owners[1].gross_realized_usd is None
    safe = result.safe_payload()
    assert safe["incomplete_owner_count"] == safe["flat_cashflow_owner_count"] == 1
    assert safe["status"] == "incomplete" and safe["gross_pnl_sign"] == "not_observed"


def test_incomplete_owner_does_not_hide_independently_complete_owner():
    good = roundtrip("good")
    pending = owner(
        "pending", state("pending-buy", phase="outcome_unknown", observation="not_observed")
    )
    result = project(good, pending)
    assert result.owners[0].gross_realized_usd == 20
    assert result.owners[1].gross_realized_usd is None
    assert (
        result.status == "incomplete" and result.safe_payload()["gross_pnl_sign"] == "not_observed"
    )


@pytest.mark.parametrize(
    "change,category",
    [
        ("duplicate_owner", "duplicate_owner"),
        ("duplicate_state", "duplicate_state_reference"),
        ("wrong_basis", "basis_binding_mismatch"),
        ("wrong_owner", "owner_binding_mismatch"),
        ("missing_state", "referenced_state_missing"),
        ("extra_state", "state_scope_mismatch"),
    ],
)
def test_native_binding_failures_are_not_repaired_or_deduplicated(change, category):
    group = roundtrip()
    kwargs = arguments(group)
    if change == "duplicate_owner":
        kwargs["owners"] += kwargs["owners"]
    elif change == "duplicate_state":
        o = group[0]
        duplicate = replace(o, state_refs=o.state_refs + o.state_refs[:1])
        kwargs["owners"] = (duplicate,)
        kwargs["expected_owner_refs"] = {o.owner_ref: duplicate.fingerprint}
    elif change == "wrong_basis":
        kwargs["expected_basis_ref"] = "sha256:" + "f" * 64
    elif change == "wrong_owner":
        kwargs["expected_owner_refs"][group[0].owner_ref] = "sha256:" + "f" * 64
    elif change == "missing_state":
        kwargs["states"].pop(group[1][0].intent.run_id)
    else:
        kwargs["states"]["extra"] = state("extra", index=2)
    with pytest.raises(KisPaperPortfolioBudgetError, match=category):
        module.project_kis_paper_portfolio_pnl(**kwargs)


def test_oversell_rejected_by_native_replay_first():
    group = owner(
        "owner", state("buy"), state("sell", side="sell", quantity="2", amount="200", index=1)
    )
    with pytest.raises(KisPaperPortfolioBudgetError, match="unowned_sell"):
        project(group)


def test_duplicate_fill_binding_is_rejected_by_native_replay():
    first = state("one")
    second_intent = replace(
        first.intent, run_id="two", client_order_id="client-two", decision_id="decision-two"
    )
    second = replace(first, intent=second_intent)
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_alias"):
        project(owner("owner", first, second))


def test_restart_serialized_latest_states_never_add_cumulative_snapshots():
    group = roundtrip()
    expected = project(group)
    restored = tuple(KisPaperCanaryState.from_dict(s.to_dict()) for s in group[1])
    for _ in range(3):
        assert project(owner("owner", *restored)) == expected
    assert expected.safe_payload()["positive_fill_count"] == 2


def test_partial_to_final_replay_uses_latest_total_once():
    partial = state("buy", quantity="2", filled="1", amount="90")
    assert project(owner("owner", partial)).status == "incomplete"
    final_fill = replace(
        partial.cumulative_fill,
        quantity=D(2),
        gross_amount=D(190),
        observed_at=START + timedelta(seconds=3),
    )
    final = replace(partial, cumulative_fill=final_fill, fill_observed_at=final_fill.observed_at)
    result = project(
        owner("owner", final, state("sell", side="sell", quantity="2", amount="210", index=1))
    )
    assert result.gross_realized_usd == 20 and result.owners[0].buy_gross_usd == 190


def test_no_io_no_credential_reads_no_mutation(tmp_path, monkeypatch):
    group = roundtrip()
    kwargs = arguments(group)
    before = tuple(s.to_dict() for s in group[1])

    def forbidden(*args, **kwargs):
        pytest.fail("pure accounting performed I/O")

    with monkeypatch.context() as patch:
        for obj, name in (
            (builtins, "open"),
            (Path, "open"),
            (Path, "read_bytes"),
            (Path, "write_bytes"),
            (socket, "create_connection"),
            (urllib.request, "urlopen"),
        ):
            patch.setattr(obj, name, forbidden)
        result = module.project_kis_paper_portfolio_pnl(**kwargs)
    assert result.gross_realized_usd == 20
    assert tuple(s.to_dict() for s in group[1]) == before
    assert list(tmp_path.iterdir()) == []


def test_safe_payload_is_categorical_counts_only_and_repr_hides_private_values():
    result = project(roundtrip("private-owner", buy="123.456", sell="234.567"))
    safe = result.safe_payload()
    assert set(safe) == {
        "kind",
        "source",
        "status",
        "reasons",
        "owner_count",
        "incomplete_owner_count",
        "serialized_owner_count",
        "flat_cashflow_owner_count",
        "intent_count",
        "positive_fill_count",
        "sell_fill_count",
        "pending_intent_count",
        "gross_pnl_sign",
        "accounting",
        "chronology",
        "fees",
        "settled_cash",
        "net_pnl",
        "limitation",
    }
    assert all(type(v) in {str, int, list} for v in safe.values())
    text = json.dumps(safe) + repr(result) + repr(result.owners[0])
    for private in (
        "private-owner",
        "123.456",
        "234.567",
        ACCOUNT,
        "SYNTHETIC-",
        "decision-",
        "client-",
    ):
        assert private not in text
    assert safe["fees"] != "0" and safe["net_pnl"] == "not_observed"
    with pytest.raises(FrozenInstanceError):
        result.gross_realized_usd = Fraction(999)


def test_projection_constructor_rejects_nonconserving_or_incomplete_numeric_claim():
    result = project(roundtrip())
    with pytest.raises(ValueError, match="portfolio_pnl_identity_invalid"):
        replace(result, gross_realized_usd=Fraction(999))
    with pytest.raises(ValueError, match="owner_pnl_identity_invalid"):
        replace(result.owners[0], gross_realized_usd=Fraction(999))
    with pytest.raises(ValueError, match="incomplete_owner_pnl_has_amounts"):
        replace(result.owners[0], reasons=("pending_amounts",), chronology="unavailable")


def test_constructor_cannot_label_open_inventory_as_closed_flat_cashflow():
    result = project(
        owner(
            "owner",
            state("buy", quantity="2", amount="200"),
            state("sell", side="sell", amount="140", index=1),
        )
    )
    with pytest.raises(ValueError, match="owner_pnl_identity_invalid"):
        replace(result.owners[0], chronology="closed_flat_cashflow")
    with pytest.raises(ValueError, match="owner_pnl_chronology_invalid"):
        replace(result.owners[0], chronology="unavailable")
