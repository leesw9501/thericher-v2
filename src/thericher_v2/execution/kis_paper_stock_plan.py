"""Pure stock BUY sizing against the original shared Paper budget.

The caller attests source/account custody and supplies the complete canonical
owner scope. Typed sequential reads cannot prove the virtual host, atomic broker
state, listing rights, fees, settlement, or execution permission. No identities,
intents, reservations, or private state are created here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, DecimalException, localcontext
from fractions import Fraction
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, TargetExposureProposal, require_utc
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

from .kis_paper_canary import KisPaperCanaryState
from .kis_paper_fill_accounting import KisPaperExecutionObservation
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioBudgetError,
    KisPaperPortfolioBudgetProjection,
    KisPaperPortfolioOwnerBinding,
    project_kis_paper_portfolio_budget,
)
from .kis_paper_quote import KisPaperQuoteError, KisPaperSpyLimitInput
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_readonly import KisPaperStockPreviewReads
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)


@dataclass(frozen=True, repr=False)
class KisPaperStockSizing:
    status: Literal["sized", "no_intent"]
    reason: str
    quantity: Decimal = Decimal(0)
    target_quantity: Decimal | None = None
    limit_price: Decimal | None = None
    projection: KisPaperPortfolioBudgetProjection | None = None

    def safe_payload(self) -> dict[str, str]:
        return {
            "kind": "kis_paper_stock_sizing_v1",
            "status": self.status,
            "reason": self.reason,
            "limitation": "gross_sizing_not_fees_settlement_or_execution_permission",
        }


class _Unavailable(ValueError):
    pass


def _check(condition: bool, category: str) -> None:
    if not condition:
        raise _Unavailable(category)


def _amount(value: object, *, positive: bool = False, whole: bool = False) -> Fraction:
    _check(
        type(value) is Decimal
        and value.is_finite()
        and not value.is_signed()
        and (value > 0 if positive else value >= 0),
        "numeric_field_invalid",
    )
    result = Fraction(value)
    _check(not whole or result.denominator == 1, "quantity_not_whole")
    return result


def _time(value: object) -> datetime:
    _check(type(value) is datetime, "timestamp_invalid")
    return require_utc(value)


def _typed(value: object, expected: type, category: str) -> None:
    _check(type(value) is expected, category)
    with localcontext(_context([getattr(value, field.name) for field in fields(value)])):
        _check(replace(value) == value, category)
    if hasattr(value, "schema_version"):
        _check(
            type(value.schema_version) is int and value.schema_version == SCHEMA_VERSION,
            "schema_invalid",
        )


def _context(values: list[object]) -> Context:
    decimals = [v for v in values if type(v) is Decimal and v.is_finite()]
    precision = max(
        64,
        max((v.adjusted() for v in decimals), default=0)
        - min((v.as_tuple().exponent for v in decimals), default=0)
        + 4,
    )
    return Context(prec=precision, Emin=MIN_EMIN, Emax=MAX_EMAX)


def _buy_limit(quote: KisPaperSpyLimitInput) -> Fraction:
    _typed(quote, KisPaperSpyLimitInput, "quote_invalid")
    _check(type(quote.decimal_places) is int, "quote_invalid")
    _amount(quote.last, positive=True)
    tick = _amount(quote.tick_size, positive=True)
    bid = _amount(quote.best_bid, positive=True)
    ask = _amount(quote.best_ask, positive=True)
    _check(bid <= ask, "quote_invalid")
    scale = Fraction(1, 10**quote.decimal_places)
    _check((tick / scale).denominator == 1, "quote_tick_invalid")
    ticks = ask / tick
    return ((ticks.numerator + ticks.denominator - 1) // ticks.denominator) * tick


def _pending(state: KisPaperCanaryState, proofs: Mapping[str, object]) -> bool:
    if state.phase == "intent_recorded":
        return state.updated_at < state.intent.valid_until
    if state.phase == "rejected":
        return state.submit_response_category != "provider_rejected"
    if state.phase == "cancelled" and state.intent.run_id in proofs:
        return False  # The shared replay already validated the exact cancellation.
    if state.phase == "submitted":
        return state.cumulative_fill is None or state.cumulative_fill.status != "filled"
    return True


def size_kis_paper_stock_target(
    *,
    proposal: TargetExposureProposal,
    receipt: ResearchDecisionReceipt,
    instrument: KisPaperStockInstrument,
    basis: KisPaperPortfolioBudgetBasis,
    expected_basis_ref: str,
    owners: tuple[KisPaperPortfolioOwnerBinding, ...],
    expected_owner_refs: Mapping[str, str],
    states: Mapping[str, KisPaperCanaryState],
    stock_owner_ref: str,
    reads: KisPaperStockPreviewReads,
    as_of: datetime,
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None,
) -> KisPaperStockSizing:
    """Size only an original eligible enter; never reinterpret hold/reduce as BUY.

    Target weight is of total original basis, not its allocated tenth. Expected
    pins must come from caller-verified custody, not this replay. Receipt replay
    checks its original references/clocks, not external research-source truth.
    Other lanes' unknown outcomes consume their reservations without pausing this
    owner. Exact target holdings must match all same-instrument owned inventory;
    only this owner's quantity is deducted from this owner's target.
    """
    projection = None
    target_quantity = None
    limit_price = None
    try:
        at = _time(as_of)
        # Constructors also perform Decimal arithmetic. Isolate those validations
        # while the shared ledger and every sizing floor use exact Fractions.
        values = [basis.basis_usd, basis.allocated_usd]
        for state in states.values():
            values.extend((state.intent.quantity, state.intent.limit_price))
            if state.cumulative_fill is not None:
                values.extend(
                    getattr(state.cumulative_fill, f.name) for f in fields(state.cumulative_fill)
                )
        with localcontext(_context(values)):
            projection = project_kis_paper_portfolio_budget(
                basis=basis,
                expected_basis_ref=expected_basis_ref,
                owners=owners,
                expected_owner_refs=expected_owner_refs,
                states=states,
                as_of=at,
                cancellation_proofs=cancellation_proofs,
            )
        _typed(proposal, TargetExposureProposal, "proposal_invalid")
        _typed(receipt, ResearchDecisionReceipt, "receipt_invalid")
        _amount(proposal.target_exposure)
        _amount(proposal.confidence)
        original = receipt_from_target_exposure_proposal(
            proposal,
            references=DecisionReceiptReferences(
                receipt.campaign_ref,
                receipt.model_ref,
                receipt.input_manifest_ref,
                receipt.proposal_ref,
            ),
        )
        _check(receipt == original, "receipt_proposal_mismatch")
        _check(proposal.decided_at <= at < proposal.valid_until, "proposal_not_current")
        if proposal.action != "enter":
            return KisPaperStockSizing(
                "no_intent",
                "exit_not_implemented" if proposal.action == "exit" else "non_entry_proposal",
                projection=projection,
            )
        _typed(instrument, KisPaperStockInstrument, "instrument_invalid")
        _check(
            proposal.symbol == instrument.symbol
            and proposal.market == instrument.market == "US"
            and instrument.order_exchange == "NASD"
            and receipt.instrument_binding_ref == instrument.binding_ref,
            "instrument_binding_mismatch",
        )
        target = Fraction(proposal.target_exposure)
        _check(
            target <= Fraction(basis.allocated_usd) / Fraction(basis.basis_usd),
            "target_exceeds_shared_allocation",
        )
        _check(type(stock_owner_ref) is str, "stock_owner_invalid")
        selected = [owner for owner in owners if owner.owner_ref == stock_owner_ref]
        _check(len(selected) == 1, "stock_owner_missing")
        owner = selected[0]
        _check(
            (owner.symbol, owner.exchange, owner.stock_binding_ref)
            == (instrument.symbol, "NASD", instrument.binding_ref),
            "stock_owner_binding_mismatch",
        )
        _typed(reads, KisPaperStockPreviewReads, "reads_invalid")
        _check(reads.account_ref == basis.account_ref, "account_binding_mismatch")
        _typed(reads.instrument, KisPaperStockInstrument, "instrument_invalid")
        _check(reads.instrument == instrument, "read_instrument_mismatch")
        _check(
            proposal.decided_at <= _time(reads.started_at) <= _time(reads.completed_at) <= at,
            "read_clock_invalid",
        )
        snapshot = reads.snapshot
        for value, kind in (
            (snapshot, KisPaperReadOnlySnapshot),
            (snapshot.identity, KisPaperAccountIdentity),
            (snapshot.open_orders, KisPaperOpenOrdersSnapshot),
            (snapshot.cash, KisPaperCashSnapshot),
            (snapshot.orderable_funds, KisPaperOrderableFundsSnapshot),
            (reads.cash, KisPaperCashSnapshot),
            (reads.orderable, KisPaperOrderableFundsSnapshot),
        ):
            _typed(value, kind, "reads_invalid")
        _check(snapshot.open_orders.complete is True, "account_incomplete")
        limit = _buy_limit(reads.quote)
        _check(_amount(reads.buy_limit, positive=True) == limit, "buy_limit_mismatch")
        limit_price = reads.buy_limit
        funds = reads.orderable
        _check(
            (funds.reference_symbol, funds.reference_exchange) == (instrument.symbol, "NASD")
            and _amount(funds.reference_price, positive=True) == limit,
            "orderability_binding_mismatch",
        )
        _check(reads.cash.currency == funds.currency == "USD", "currency_invalid")
        cash = _amount(reads.cash.available_cash)
        available = _amount(funds.orderable_funds)
        times = [
            reads.started_at,
            reads.completed_at,
            reads.quote.quoted_at,
            reads.cash.captured_at,
            funds.captured_at,
            snapshot.captured_at,
            snapshot.identity.captured_at,
            snapshot.cash.captured_at,
            snapshot.orderable_funds.captured_at,
            snapshot.open_orders.captured_at,
        ]
        broker_quantity = Fraction(0)
        target_rows = 0
        for position in snapshot.positions:
            _typed(position, KisPaperPosition, "position_invalid")
            times.append(position.captured_at)
            if position.symbol == instrument.symbol:
                target_rows += 1
                _check(
                    position.exchange == "NASD" and position.currency == "USD",
                    "position_binding_mismatch",
                )
                broker_quantity += _amount(position.quantity, whole=True)
        _check(target_rows <= 1, "duplicate_target_position")
        target_open = False
        for order in snapshot.open_orders.orders:
            _typed(order, KisPaperOpenOrder, "open_order_invalid")
            times.append(order.captured_at)
            target_open |= order.symbol == instrument.symbol
        _check(
            all(timedelta(0) <= at - _time(t) <= timedelta(seconds=120) for t in times),
            "reads_stale",
        )
        owned = next(row for row in projection.stocks_by_owner if row.owner_ref == stock_owner_ref)
        all_owned = sum(
            (
                Fraction(row.quantity)
                for row in projection.stocks_by_owner
                if (row.symbol, row.exchange) == (instrument.symbol, "NASD")
            ),
            Fraction(0),
        )
        _check(broker_quantity == all_owned, "target_inventory_mismatch")
        _check(not target_open, "target_open_order_pending")
        proofs = {} if cancellation_proofs is None else cancellation_proofs
        _check(
            owned.reserved_buys == 0
            and not any(_pending(states[ref.run_id], proofs) for ref in owner.state_refs),
            "stock_owner_pending",
        )
        target_quantity = Decimal((Fraction(basis.basis_usd) * target) // limit)
        additional = max(Fraction(0), Fraction(target_quantity) - Fraction(owned.quantity))
        # Provider funds do not account for every persisted, unsubmitted BUY.
        # The bank fields are already net of this same canonical reservation.
        reserved = Fraction(projection.reserved_buys)
        capacity = min(
            Fraction(projection.remaining_cap),
            Fraction(projection.remaining_gross_cash),
            max(Fraction(0), available - reserved),
            max(Fraction(0), cash - reserved),
        )
        quantity = Decimal(int(min(additional, capacity // limit)))
        reason = "target_already_satisfied" if additional == 0 else "whole_share_capacity_zero"
        return KisPaperStockSizing(
            "sized" if quantity else "no_intent",
            "whole_share_buy_sized" if quantity else reason,
            quantity,
            target_quantity,
            limit_price,
            projection,
        )
    except _Unavailable as error:
        reason = str(error)
    except KisPaperPortfolioBudgetError:
        reason = "shared_budget_invalid"
    except (ValueError, TypeError, AttributeError, KeyError, DecimalException, KisPaperQuoteError):
        reason = "typed_input_invalid"
    return KisPaperStockSizing(
        "no_intent",
        reason,
        target_quantity=target_quantity,
        limit_price=limit_price,
        projection=projection,
    )
