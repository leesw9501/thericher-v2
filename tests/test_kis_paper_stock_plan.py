"""Synthetic pure sizing boundaries; no private data, clients, or provider calls."""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_UP,
    Context,
    Decimal,
    Inexact,
    Rounded,
    getcontext,
    localcontext,
)
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2 import contracts
from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_stock_plan import size_kis_paper_stock_target
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.execution.kis_paper_stock_readonly import KisPaperStockPreviewReads
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

D = Decimal
AT = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
START = AT - timedelta(days=1)
ACCOUNT = "a" * 64
SYMBOL = "SYNSTOCK"
REFS = DecisionReceiptReferences(
    "ref:" + "b" * 64, "ref:" + "c" * 64, "sha256:" + "d" * 64, "ref:" + "e" * 64
)


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("external_call_forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", blocked)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config_from_environment", blocked)


def _state(
    run,
    *,
    symbol="SPY",
    quantity="1",
    limit="100",
    filled=None,
    gross="0",
    side="buy",
    phase="submitted",
    index=0,
):
    at = START + timedelta(minutes=index)
    intent = KisPaperCanaryIntent(
        run,
        "client-" + run,
        "decision-" + run,
        symbol,
        "AMEX" if symbol == "SPY" else "NASD",
        D(quantity),
        D(limit),
        at,
        at + timedelta(seconds=20),
        side,
    )
    order_at = at + timedelta(seconds=1)
    known = filled is not None or phase in {"submitted", "cancelled"}
    order_id = "SYNTHETIC-" + run if known else None
    fill = (
        None
        if filled is None
        else KisPaperCumulativeFill(
            fill_identity_ref(
                raw_order_id=order_id,
                order_at=order_at,
                symbol=symbol,
                exchange=intent.exchange,
                side=side,
                quantity=intent.quantity,
            ),
            intent.quantity,
            D(filled),
            D(gross),
            at + timedelta(seconds=2),
            D(int(Fraction(intent.quantity) - Fraction(D(filled)))),
        )
    )
    return KisPaperCanaryState(
        intent,
        phase,
        at + timedelta(seconds=5),
        "reconciliation_unresolved",
        broker_order_id=order_id,
        submission_started_at=order_at if phase != "intent_recorded" else None,
        submitted_at=order_at if known else None,
        cumulative_fill=fill,
        fill_observation_status="available" if fill else "not_observed",
        fill_observed_at=fill.observed_at if fill else None,
    )


def _owner(name, states=(), *, symbol="SPY", binding=None):
    return KisPaperPortfolioOwnerBinding(
        name,
        ACCOUNT,
        symbol,
        "AMEX" if symbol == "SPY" else "NASD",
        tuple(KisPaperPortfolioStateRef(s.intent.run_id, s.intent.fingerprint) for s in states),
        binding,
    )


def _arguments(
    *,
    price="10",
    cash="1000",
    funds="1000",
    owned=(),
    others=(),
    broker_quantity=None,
    action="enter",
    target=".01",
    **changes,
):
    proposal = TargetExposureProposal(
        "original-proposal",
        SYMBOL,
        "US",
        action,
        D(target),
        D(0),
        "frozen-schema",
        "ready",
        AT - timedelta(minutes=5),
        AT + timedelta(hours=1),
        START,
        "original-reason",
    )
    receipt = receipt_from_target_exposure_proposal(proposal, references=REFS)
    instrument = KisPaperStockInstrument(SYMBOL, receipt.instrument_binding_ref)
    owner = _owner("stock", owned, symbol=SYMBOL, binding=instrument.binding_ref)
    basis = KisPaperPortfolioBudgetBasis(ACCOUNT, D(10000), D(1000), START)
    owners = (owner, *(o for o, _ in others))
    states = {s.intent.run_id: s for s in (*owned, *(s for _, group in others for s in group))}
    money = KisPaperCashSnapshot("USD", D(cash), AT)
    orderable = KisPaperOrderableFundsSnapshot("USD", D(funds), "NASD", SYMBOL, D(price), AT)
    snapshot_cash = KisPaperCashSnapshot("USD", D("0"), AT)
    legacy_funds = KisPaperOrderableFundsSnapshot("USD", D("0"), "NASD", "QQQ", D("1"), AT)
    positions = (
        ()
        if broker_quantity is None
        else (KisPaperPosition(SYMBOL, "NASD", "USD", D(broker_quantity), D(price), D(price), AT),)
    )
    snapshot = KisPaperReadOnlySnapshot(
        KisPaperAccountIdentity("****0000-**", AT),
        snapshot_cash,
        legacy_funds,
        positions,
        KisPaperOpenOrdersSnapshot((), AT),
        AT,
    )
    quote = KisPaperSpyLimitInput(D(price), 4, D(".0001"), AT, D(price), D(price))
    reads = KisPaperStockPreviewReads(
        ACCOUNT,
        instrument,
        snapshot,
        quote,
        D(price),
        money,
        orderable,
        AT,
        AT,
        0.0,
    )
    result = dict(
        proposal=proposal,
        receipt=receipt,
        instrument=instrument,
        basis=basis,
        expected_basis_ref=basis.fingerprint,
        owners=owners,
        expected_owner_refs={o.owner_ref: o.fingerprint for o in owners},
        states=states,
        stock_owner_ref="stock",
        reads=reads,
        as_of=AT,
    )
    result.update(changes)
    return result


def _tamper(value, field, replacement):
    value = copy.deepcopy(value)
    object.__setattr__(value, field, replacement)
    return value


def test_one_percent_of_original_total_not_one_percent_of_allocated_bank():
    args = _arguments()
    result = size_kis_paper_stock_target(**args)
    assert result.status == "sized"
    assert result.target_quantity == result.quantity == 10
    assert result.limit_price == 10
    assert result.projection.basis_usd == 10000
    assert result.projection.allocated_usd == 1000
    assert args["proposal"].confidence == 0


@pytest.mark.parametrize("precision", [2, 6, 28, 80])
@pytest.mark.parametrize("price,expected", [("33.3333", 3), ("33.3334", 2), ("100.0001", 0)])
def test_fractional_cent_target_floors_ignore_decimal_context(precision, price, expected):
    args = _arguments(price=price)
    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_UP
        result = size_kis_paper_stock_target(**args)
    assert result.quantity == result.target_quantity == expected
    assert result.status == ("sized" if expected else "no_intent")
    assert Fraction(result.quantity) * Fraction(result.limit_price) <= 100


@pytest.mark.parametrize("kind", ["cap", "cash", "funds", "gross_cash"])
@pytest.mark.parametrize("remaining,expected", [("29.9999", 2), ("30", 3), ("30.0001", 3)])
def test_each_capacity_boundary_floors_exactly(kind, remaining, expected):
    if kind == "cap":
        # Finite subtraction in a high-precision test setup, not production sizing.
        used = D(1000) - D(remaining)
        state = _state("other", limit=str(used), filled="1", gross=str(used))
        args = _arguments(others=((_owner("spy", (state,)), (state,)),))
    elif kind == "gross_cash":
        buy = _state("other", limit="900", filled="1", gross="900")
        sell = _state("sale", side="sell", limit=remaining, filled="1", gross=remaining, index=1)
        pending = _state("pending", limit="100", phase="outcome_unknown", index=2)
        group = (buy, sell, pending)
        args = _arguments(others=((_owner("spy", group), group),))
    else:
        args = _arguments(**{kind: remaining})
    result = size_kis_paper_stock_target(**args)
    assert result.status == "sized" and result.quantity == expected
    assert result.target_quantity == 10


def test_other_lane_unknown_partial_fill_consumes_capacity_without_global_hold():
    partial = _state("partial", quantity="10", limit="99", filled="3", gross="290")
    partial = replace(
        partial,
        phase="outcome_unknown",
        fill_observation_status="unavailable",
        fill_observed_at=partial.updated_at,
    )
    args = _arguments(others=((_owner("spy", (partial,)), (partial,)),))
    result = size_kis_paper_stock_target(**args)
    assert result.status == "sized" and result.quantity == 1
    assert result.projection.entry_cost == 290
    assert result.projection.reserved_buys == 693
    assert result.projection.remaining_cap == 17


@pytest.mark.parametrize("field", ["cash", "funds"])
@pytest.mark.parametrize("phase", ["intent_recorded", "outcome_unknown"])
@pytest.mark.parametrize(
    "provider_free,expected",
    [("0", 0), ("99.9999", 0), ("100", 0), ("149.9999", 4), ("150", 5), ("200", 10)],
)
def test_provider_free_funds_reserve_other_owner_pending_buys(
    field, phase, provider_free, expected
):
    pending = _state("reserved-etf", limit="100", phase=phase)
    if phase == "intent_recorded":
        pending = replace(
            pending,
            intent=replace(
                pending.intent,
                created_at=AT - timedelta(seconds=5),
                valid_until=AT + timedelta(seconds=15),
            ),
            updated_at=AT,
        )
    args = _arguments(
        others=((_owner("spy", (pending,)), (pending,)),),
        **{field: provider_free},
    )
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        result = size_kis_paper_stock_target(**args)
    assert result.projection.reserved_buys == 100
    assert result.projection.remaining_cap == result.projection.remaining_gross_cash == 900
    assert result.quantity == expected and result.target_quantity == 10
    assert result.status == ("sized" if expected else "no_intent")
    assert Fraction(result.quantity) * Fraction(result.limit_price) <= max(
        Fraction(0),
        Fraction(D(provider_free)) - 100,
    )


@pytest.mark.parametrize("reserved,expected", [("100", 10), ("950", 5)])
def test_bank_limited_sizing_does_not_deduct_reservations_twice(reserved, expected):
    pending = _state("reserved-etf", limit=reserved, phase="outcome_unknown")
    args = _arguments(others=((_owner("spy", (pending,)), (pending,)),))
    result = size_kis_paper_stock_target(**args)
    assert result.quantity == expected
    assert result.projection.remaining_cap == 1000 - D(reserved)


@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown", "submitted"])
def test_stock_owner_unknown_submission_is_scoped_no_intent(phase):
    state = _state("stock", symbol=SYMBOL, phase=phase)
    result = size_kis_paper_stock_target(**_arguments(owned=(state,)))
    assert result.status == "no_intent" and result.reason == "stock_owner_pending"
    assert result.projection.reserved_buys == 100


def test_partial_stock_reservation_is_not_target_capacity():
    state = _state("stock", symbol=SYMBOL, quantity="5", limit="10", filled="2", gross="20")
    result = size_kis_paper_stock_target(**_arguments(owned=(state,), broker_quantity="2"))
    assert result.status == "no_intent" and result.reason == "stock_owner_pending"
    assert result.projection.reserved_buys == 30


@pytest.mark.parametrize("quantity,expected", [("3", 7), ("10", 0), ("11", 0)])
def test_only_known_owned_quantity_deducted_and_no_automatic_sale(quantity, expected):
    state = _state(
        "stock",
        symbol=SYMBOL,
        quantity=quantity,
        limit="5",
        filled=quantity,
        gross=str(D(quantity) * 5),
    )
    result = size_kis_paper_stock_target(**_arguments(owned=(state,), broker_quantity=quantity))
    assert result.quantity == expected and result.target_quantity == 10
    assert result.status == ("sized" if expected else "no_intent")


def test_exact_cancellation_proof_releases_only_its_stock_residual():
    state = _state(
        "stock", symbol=SYMBOL, quantity="5", limit="10", filled="0", gross="0", phase="cancelled"
    )
    state = replace(state, cumulative_fill=replace(state.cumulative_fill, remaining_quantity=D(0)))
    proof = KisPaperExecutionObservation(
        row_count=2,
        same_day_order_id_seen=True,
        status="available",
        fill=state.current_fill,
        observed_at=state.fill_observed_at,
        cancellation_confirmed=True,
    )
    args = _arguments(owned=(state,))
    assert size_kis_paper_stock_target(**args).status == "no_intent"
    result = size_kis_paper_stock_target(**args, cancellation_proofs={"stock": proof})
    assert result.quantity == 10 and result.projection.reserved_buys == 0


def test_partial_cancel_without_supported_proof_stays_reserved():
    state = _state(
        "stock", symbol=SYMBOL, quantity="5", limit="10", filled="2", gross="20", phase="cancelled"
    )
    result = size_kis_paper_stock_target(**_arguments(owned=(state,), broker_quantity="2"))
    assert result.reason == "stock_owner_pending" and result.projection.reserved_buys == 30


@pytest.mark.parametrize(
    "action,target", [("hold", ".01"), ("reduce", ".01"), ("abstain", "0"), ("exit", "0")]
)
def test_non_entry_never_reinterpreted_as_buy(action, target):
    result = size_kis_paper_stock_target(**_arguments(action=action, target=target))
    assert result.status == "no_intent" and result.quantity == 0


@pytest.mark.parametrize("target", [".10", ".10000000000000000001"])
def test_target_cannot_exceed_original_allocation_fraction(target):
    result = size_kis_paper_stock_target(**_arguments(target=target))
    assert result.status == ("sized" if target == ".10" else "no_intent")


@pytest.mark.parametrize(
    "change",
    [
        "receipt_target",
        "receipt_clock",
        "receipt_source",
        "account",
        "instrument",
        "owner",
        "basis",
        "owner_pin",
    ],
)
def test_wrong_receipt_account_source_and_frozen_pins(change):
    args = _arguments()
    if change.startswith("receipt_"):
        if change == "receipt_source":
            args["receipt"] = _tamper(args["receipt"], "input_manifest_ref", "sha256:" + "f" * 64)
        else:
            changed = replace(
                args["proposal"],
                **(
                    {"target_exposure": D(".02")}
                    if change == "receipt_target"
                    else {"valid_until": AT}
                ),
            )
            args["receipt"] = receipt_from_target_exposure_proposal(changed, references=REFS)
    elif change == "account":
        args["reads"] = replace(args["reads"], account_ref="f" * 64)
    elif change == "instrument":
        args["instrument"] = KisPaperStockInstrument("OTHER", args["instrument"].binding_ref)
    elif change == "owner":
        owner = replace(args["owners"][0], stock_binding_ref="ref:" + "f" * 64)
        args.update(owners=(owner,), expected_owner_refs={"stock": owner.fingerprint})
    elif change == "basis":
        args["expected_basis_ref"] = "sha256:" + "f" * 64
    else:
        args["expected_owner_refs"] = {"stock": "sha256:" + "f" * 64}
    result = size_kis_paper_stock_target(**args)
    assert result.status == "no_intent" and result.quantity == 0


@pytest.mark.parametrize("field", ["reference_symbol", "reference_exchange", "reference_price"])
def test_exact_stock_limit_funds_not_legacy_qqq_fallback(field):
    args = _arguments()
    wrong = {"reference_symbol": "QQQ", "reference_exchange": "NYSE", "reference_price": D("11")}
    args["reads"] = replace(
        args["reads"], orderable=replace(args["reads"].orderable, **{field: wrong[field]})
    )
    assert size_kis_paper_stock_target(**args).reason == "orderability_binding_mismatch"


@pytest.mark.parametrize("age,expected", [(120, "sized"), (121, "no_intent"), (-1, "no_intent")])
@pytest.mark.parametrize("field", ["quote", "cash", "orderable", "snapshot"])
def test_every_observation_clock_bounded_without_future_tolerance(age, expected, field):
    args = _arguments()
    row = getattr(args["reads"], field)
    clock = "quoted_at" if field == "quote" else "captured_at"
    args["reads"] = replace(
        args["reads"], **{field: replace(row, **{clock: AT - timedelta(seconds=age)})}
    )
    assert size_kis_paper_stock_target(**args).status == expected


def test_original_ttl_expires_at_boundary_no_renewal():
    args = _arguments()
    result = size_kis_paper_stock_target(**args)
    assert result.status == "sized"
    args["as_of"] = args["proposal"].valid_until
    result = size_kis_paper_stock_target(**args)
    assert result.reason == "proposal_not_current"
    assert args["proposal"].valid_until == AT + timedelta(hours=1)


def test_foreign_target_inventory_is_neither_adopted_nor_sold():
    result = size_kis_paper_stock_target(**_arguments(broker_quantity="1"))
    assert result.reason == "target_inventory_mismatch" and result.quantity == 0


@pytest.mark.parametrize("symbol", [SYMBOL, "SPY"])
def test_target_open_order_only_scopes_its_own_sizing(symbol):
    args = _arguments()
    order = KisPaperOpenOrder(
        "open-synthetic", symbol, "NASD", "USD", "buy", D(1), D(0), D(1), D(10), AT
    )
    args["reads"] = replace(
        args["reads"],
        snapshot=replace(
            args["reads"].snapshot, open_orders=KisPaperOpenOrdersSnapshot((order,), AT)
        ),
    )
    result = size_kis_paper_stock_target(**args)
    assert result.status == ("no_intent" if symbol == SYMBOL else "sized")


def test_tick_limit_recomputed_and_mismatch_rejected():
    args = _arguments(price="10.01")
    args["reads"] = replace(
        args["reads"], quote=KisPaperSpyLimitInput(D("10"), 2, D(".01"), AT, D("10"), D("10.0001"))
    )
    assert size_kis_paper_stock_target(**args).quantity == 9
    args["reads"] = replace(args["reads"], buy_limit=D("10.0001"))
    assert size_kis_paper_stock_target(**args).reason == "buy_limit_mismatch"


def test_pure_call_does_not_mutate_inputs_touch_files_or_create_execution_objects(monkeypatch):
    args = _arguments()
    before = copy.deepcopy(args)

    def forbidden(*_args, **_kwargs):
        pytest.fail("pure_call_attempted_io")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(Path, "write_bytes", forbidden)
        patch.setattr(os, "open", forbidden)
        patch.setattr(os, "getenv", forbidden)
        patch.setattr(kis_readonly.KisPaperReadOnlyClient, "__init__", forbidden)
        result = size_kis_paper_stock_target(**args)
    assert args == before and result.status == "sized"
    assert set(result.safe_payload()) == {"kind", "status", "reason", "limitation"}
    assert all(type(value) is str for value in result.safe_payload().values())
    assert SYMBOL not in repr(result) and ACCOUNT not in repr(result)
    assert str(result.quantity) not in str(result.safe_payload())
    assert not hasattr(result, "intents") and not hasattr(result, "binding")
    with pytest.raises(FrozenInstanceError):
        result.quantity = D(1)


def test_hostile_decimal_context_does_not_change_replay_floors_or_context():
    buy = _state("other", quantity="3", limit="100", filled="3", gross="299.9999")
    sell = _state("sale", side="sell", quantity="1", limit="100", filled="1", gross="100", index=1)
    group = (buy, sell)
    args = _arguments(price="33.3333", others=((_owner("spy", group), group),))
    with localcontext() as context:
        context.clear_flags()
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = context.traps[Rounded] = True
        result = size_kis_paper_stock_target(**args)
        assert context.prec == 2 and context.traps[Inexact] and not context.flags[Inexact]
        assert context.rounding == ROUND_UP and context.traps[Rounded]
        assert not any(context.flags.values())
    assert result.status == "sized" and result.quantity == 3


@pytest.mark.parametrize("signals", [(), (Inexact,), (Rounded,), (Inexact, Rounded)])
def test_hostile_decimal_fixture_preserves_preexisting_ambient_context(signals):
    with localcontext() as ambient:
        ambient.clear_flags()
        for signal in signals:
            ambient.flags[signal] = True
        before = (ambient.prec, ambient.rounding, dict(ambient.traps), dict(ambient.flags))
        test_hostile_decimal_context_does_not_change_replay_floors_or_context()
        assert (ambient.prec, ambient.rounding, dict(ambient.traps), dict(ambient.flags)) == before


def test_multiple_owned_target_owners_reconcile_but_are_not_adopted_by_selected_owner():
    state = _state("other-stock", symbol=SYMBOL, quantity="3", limit="5", filled="3", gross="15")
    args = _arguments(broker_quantity="3")
    other = _owner("other-stock", (state,), symbol=SYMBOL, binding=args["instrument"].binding_ref)
    args["owners"] += (other,)
    args["expected_owner_refs"][other.owner_ref] = other.fingerprint
    args["states"][state.intent.run_id] = state
    result = size_kis_paper_stock_target(**args)
    assert result.quantity == 10
    args["reads"] = replace(args["reads"], snapshot=replace(args["reads"].snapshot, positions=()))
    assert size_kis_paper_stock_target(**args).reason == "target_inventory_mismatch"


@pytest.mark.parametrize("field,value", [("symbol", "bad symbol"), ("binding_ref", "fake-secret")])
def test_tampered_instrument_returns_categorical_no_intent(field, value):
    args = _arguments()
    args["instrument"] = _tamper(args["instrument"], field, value)
    result = size_kis_paper_stock_target(**args)
    assert result.status == "no_intent" and value not in str(result.safe_payload())


@pytest.mark.parametrize("field", ["cash", "funds"])
def test_zero_exact_funding_returns_no_intent(field):
    result = size_kis_paper_stock_target(**_arguments(**{field: "0"}))
    assert result.reason == "whole_share_capacity_zero" and result.quantity == 0
    assert result.target_quantity == 10


def test_duplicate_target_position_is_not_deduplicated_or_adopted():
    state = _state("stock", symbol=SYMBOL, quantity="2", limit="5", filled="2", gross="10")
    args = _arguments(owned=(state,), broker_quantity="1")
    snapshot = args["reads"].snapshot
    args["reads"] = replace(
        args["reads"], snapshot=replace(snapshot, positions=snapshot.positions * 2)
    )
    assert size_kis_paper_stock_target(**args).reason == "duplicate_target_position"


@pytest.mark.parametrize(
    "field,value", [("exchange", "NYSE"), ("currency", "KRW"), ("quantity", D(".5"))]
)
def test_target_position_requires_exact_venue_currency_whole_quantity(field, value):
    args = _arguments(broker_quantity="1")
    snapshot = args["reads"].snapshot
    position = replace(snapshot.positions[0], **{field: value})
    args["reads"] = replace(args["reads"], snapshot=replace(snapshot, positions=(position,)))
    assert size_kis_paper_stock_target(**args).status == "no_intent"


def test_incomplete_account_and_future_proposal_are_scoped_unavailable():
    args = _arguments()
    snapshot = args["reads"].snapshot
    args["reads"] = replace(
        args["reads"],
        snapshot=_tamper(snapshot, "open_orders", _tamper(snapshot.open_orders, "complete", False)),
    )
    assert size_kis_paper_stock_target(**args).status == "no_intent"
    args = _arguments()
    args["as_of"] = args["proposal"].decided_at - timedelta(seconds=1)
    assert size_kis_paper_stock_target(**args).reason == "proposal_not_current"


def _decimal_context_state(context):
    return context.prec, context.rounding, dict(context.traps), dict(context.flags)


@pytest.mark.parametrize("price,expected", [("50", 1), ("10", 9)])
@pytest.mark.parametrize(
    "receipt_precision,replay_precision,rounding",
    [
        (2, 28, ROUND_FLOOR),
        (28, 2, ROUND_CEILING),
        (80, 2, ROUND_HALF_EVEN),
        (2, 80, ROUND_CEILING),
        (28, 80, ROUND_HALF_EVEN),
        (80, 28, ROUND_FLOOR),
    ],
)
def test_exact_target_binding_context_receipt_and_unwrapped_stock_sizing(
    price, expected, receipt_precision, replay_precision, rounding
):
    target = "0.009997500624843789052736"
    ambient_before = _decimal_context_state(getcontext())
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        args = _arguments(target=target, price=price)
        legacy_marker = format(D(target).normalize(), "f")
    legacy_payload = {
        "kind": "decision_target_binding_v1",
        "symbol": SYMBOL,
        "market": "US",
        "decision_class": "enter",
        "target_exposure": legacy_marker,
    }
    legacy_ref = (
        "ref:"
        + hashlib.sha256(
            json.dumps(
                legacy_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ).encode("ascii")
        ).hexdigest()
    )
    assert args["receipt"].target_binding_ref == legacy_ref
    persisted_bytes = args["receipt"].canonical_json()
    persisted_id = args["receipt"].decision_id
    with localcontext(Context(prec=receipt_precision, rounding=rounding)) as context:
        context.traps[Inexact] = context.traps[Rounded] = True
        context.flags[Inexact] = True
        before = _decimal_context_state(context)
        restored = replace(args["proposal"])
        receipt = receipt_from_target_exposure_proposal(restored, references=REFS)
        assert _decimal_context_state(context) == before
    assert restored == args["proposal"] and receipt == args["receipt"]
    args["receipt"] = receipt
    frozen = copy.deepcopy(args)
    with localcontext(Context(prec=replay_precision, rounding=rounding)) as context:
        context.traps[Inexact] = context.traps[Rounded] = True
        context.flags[Rounded] = True
        before = _decimal_context_state(context)
        # No caller precision wrapper around sizing or its receipt replay.
        result = size_kis_paper_stock_target(**args)
        assert _decimal_context_state(context) == before
    assert result.status == "sized"
    assert result.quantity == result.target_quantity == expected
    assert Fraction(result.quantity) * Fraction(result.limit_price) <= (
        Fraction(args["basis"].basis_usd) * Fraction(args["proposal"].target_exposure)
    )
    assert args == frozen
    assert args["receipt"].canonical_json() == persisted_bytes
    assert args["receipt"].decision_id == persisted_id
    assert _decimal_context_state(getcontext()) == ambient_before


@pytest.mark.parametrize("precision", [2, 28, 80])
@pytest.mark.parametrize("rounding", [ROUND_FLOOR, ROUND_CEILING])
def test_distinct_exact_target_binding_context_cannot_substitute_receipt(precision, rounding):
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        below = _arguments(target="0.009999999999999999999999")
        at = _arguments(target="0.010000000000000000000000")
    frozen_below, frozen_at = copy.deepcopy(below), copy.deepcopy(at)
    with localcontext(Context(prec=precision, rounding=rounding)) as context:
        context.traps[Inexact] = context.traps[Rounded] = True
        before = _decimal_context_state(context)
        below_receipt = receipt_from_target_exposure_proposal(below["proposal"], references=REFS)
        at_receipt = receipt_from_target_exposure_proposal(at["proposal"], references=REFS)
        assert below_receipt.target_binding_ref != at_receipt.target_binding_ref
        assert below_receipt.decision_id != at_receipt.decision_id
        assert size_kis_paper_stock_target(**below).quantity == 9
        assert size_kis_paper_stock_target(**at).quantity == 10
        rejected = size_kis_paper_stock_target(**(at | {"receipt": below_receipt}))
        assert _decimal_context_state(context) == before
    assert (rejected.status, rejected.reason) == ("no_intent", "receipt_proposal_mismatch")
    assert below == frozen_below and at == frozen_at


@pytest.mark.parametrize(
    "target,reason,quantity",
    [
        ("0", "non_entry_proposal", 0),
        (".10", "whole_share_buy_sized", 100),
        ("1", "target_exceeds_shared_allocation", 0),
    ],
)
def test_legal_target_binding_context_preserves_existing_stock_allocation(target, reason, quantity):
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        args = _arguments(target=target, action="abstain" if target == "0" else "enter")
    frozen = copy.deepcopy(args)
    for precision, rounding in ((2, ROUND_FLOOR), (28, ROUND_HALF_EVEN), (80, ROUND_CEILING)):
        with localcontext(Context(prec=precision, rounding=rounding)) as context:
            before = _decimal_context_state(context)
            receipt = receipt_from_target_exposure_proposal(args["proposal"], references=REFS)
            result = size_kis_paper_stock_target(**args)
            assert _decimal_context_state(context) == before
        assert receipt == args["receipt"] and result.quantity == quantity
        assert result.reason == reason
        assert result.status == ("sized" if reason == "whole_share_buy_sized" else "no_intent")
    assert args == frozen


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_legacy_rounded_long_target_receipt_is_not_rebound_or_substituted(monkeypatch, precision):
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        args = _arguments(target="0.009997500624843789052736815796051")
    exact_receipt = args["receipt"]
    original_marker = contracts._decimal_marker

    def old_marker(value):
        return "0" if value == 0 else format(value.normalize(), "f")

    with monkeypatch.context() as patch:
        patch.setattr(contracts, "_decimal_marker", old_marker)
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
            legacy_receipt = receipt_from_target_exposure_proposal(
                args["proposal"], references=REFS
            )
    assert contracts._decimal_marker is original_marker
    assert legacy_receipt.target_binding_ref != exact_receipt.target_binding_ref
    assert legacy_receipt.decision_id != exact_receipt.decision_id
    args["receipt"] = legacy_receipt
    frozen = copy.deepcopy(args)
    legacy_bytes, legacy_id = legacy_receipt.canonical_json(), legacy_receipt.decision_id
    with localcontext(Context(prec=precision, rounding=ROUND_CEILING)) as context:
        context.traps[Inexact] = context.traps[Rounded] = True
        before = _decimal_context_state(context)
        result = size_kis_paper_stock_target(**args)
        assert _decimal_context_state(context) == before
    assert (result.status, result.reason) == ("no_intent", "receipt_proposal_mismatch")
    assert result.quantity == 0 and args == frozen
    assert args["receipt"].canonical_json() == legacy_bytes
    assert args["receipt"].decision_id == legacy_id
    assert contracts._decimal_marker is original_marker
