"""Stock BUY sizing and exact reservation in the original shared Paper budget.

The caller attests source/account custody and supplies the complete canonical
owner scope. Typed sequential reads cannot prove the virtual host, atomic broker
state, listing rights, fees, settlement, or execution permission. Builders are
pure; reservation/reconciliation use the existing canonical binding and locks.
No provider, submission, cancellation or credential path is present here.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, DecimalException, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, TargetExposureProposal, require_utc
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

from . import kis_paper_budget_strategy as budget
from .kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_fill_accounting import KisPaperExecutionObservation
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioBudgetError,
    KisPaperPortfolioBudgetProjection,
    KisPaperPortfolioOwnerBinding,
    project_kis_paper_portfolio_budget,
)
from .kis_paper_portfolio_plan import _replay_scope, _states
from .kis_paper_quote import KisPaperQuoteError, KisPaperSpyLimitInput
from .kis_paper_spy_fill_cycle import _RecoveryRequired
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


@dataclass(frozen=True, repr=False)
class KisPaperStockPlan:
    status: str
    reason: str
    binding: dict | None = None
    intents: tuple[KisPaperCanaryIntent, ...] = ()
    plan_ref: str | None = None
    reservation: Decimal | None = None

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_stock_plan_v1",
            "status": self.status,
            "reason": self.reason,
            "buy_leg_count": len(self.intents),
            "new_submits": 0,
            "limitation": "gross_limit_reservation_not_fees_settlement_or_execution_permission",
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


def _plan_check(condition: bool, reason: str) -> None:
    if not condition:
        raise _RecoveryRequired(reason)


def _plan_scope(
    binding,
    states,
    *,
    expected_account_ref,
    expected_basis_ref,
    expected_owner_refs,
    instrument,
    as_of,
):
    _plan_check(
        isinstance(binding, Mapping)
        and type(binding.get("version")) is int
        and (binding["version"], set(binding)) in ((3, budget._V3_KEYS), (4, budget._V4_KEYS))
        and binding["legacy_spy"] is None,
        "stock_custody_mismatch",
    )
    try:
        _typed(instrument, KisPaperStockInstrument, "instrument_invalid")
    except (ValueError, TypeError, AttributeError):
        raise _RecoveryRequired("stock_instrument_invalid") from None
    _plan_check(
        budget._STOCK_SYMBOL.fullmatch(instrument.symbol) is not None
        and instrument.symbol not in {"SPY", "QQQ", "TLT", "GLD"}
        and instrument.order_exchange == "NASD",
        "stock_instrument_invalid",
    )
    budget.project_shared_budget(
        binding=binding,
        states=states,
        expected_account_ref=expected_account_ref,
        expected_basis_ref=expected_basis_ref,
        expected_owner_refs=expected_owner_refs,
        as_of=as_of,
    )
    registry = binding.get("stocks", {})
    _plan_check(not registry or set(registry) == {instrument.symbol}, "stock_registry_conflict")
    entry = registry.get(instrument.symbol)
    if entry is not None:
        _plan_check(
            (entry["exchange"], entry["instrument_binding_ref"])
            == ("NASD", instrument.binding_ref),
            "stock_instrument_binding_mismatch",
        )
    return entry


def _request_pins(request_id, input_ref, expected_binding_ref):
    _plan_check(
        type(request_id) is str and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(request_id),
        "stock_request_invalid",
    )
    _plan_check(
        all(
            type(ref) is str and budget._SHA.fullmatch(ref)
            for ref in (input_ref, expected_binding_ref)
        ),
        "stock_reference_invalid",
    )


def _exact_plan(entry, request_id, input_ref, expected_binding_ref):
    plan = next((p for p in entry["plans"] if p["request_id"] == request_id), None)
    if plan is not None:
        _plan_check(
            plan["input_ref"] == input_ref and plan["parent_binding_ref"] == expected_binding_ref,
            "stock_request_conflict",
        )
    return plan


def _stock_plan_result(binding, plan, status, reason):
    seeds = budget._stock_seed_states(binding)
    intents = tuple(seeds[run].intent for run in plan["states"])
    _plan_check(len(intents) == 1 and intents[0].side == "buy", "stock_plan_invalid")
    reservation = budget._exact_decimal(
        sum((Fraction(i.quantity) * Fraction(i.limit_price) for i in intents), Fraction(0))
    )
    return KisPaperStockPlan(
        status, reason, binding, intents, "sha256:" + budget._digest(plan), reservation
    )


def _retry_owner_refs(binding, expected_refs, request_id, input_ref, parent_ref, instrument):
    # Original owner pins are reusable only if the complete original parent can
    # still be reconstructed. A changed book instead needs current owner pins.
    if not isinstance(binding, Mapping) or binding.get("version") != 4:
        return expected_refs
    if type(instrument) is not KisPaperStockInstrument:
        return expected_refs
    _plan_check(set(binding) == budget._V4_KEYS, "stock_custody_mismatch")
    current = {owner.owner_ref: ref for owner, ref in budget._owners(binding)}
    entry = binding.get("stocks", {}).get(instrument.symbol)
    if entry is None:
        return expected_refs
    plan = _exact_plan(entry, request_id, input_ref, parent_ref)
    if plan is None:
        return expected_refs
    if expected_refs == current:
        return expected_refs
    _plan_check(
        entry["instrument_binding_ref"] == instrument.binding_ref,
        "stock_instrument_binding_mismatch",
    )
    parent = copy.deepcopy(dict(binding))
    parent["stocks"][instrument.symbol]["plans"].remove(plan)
    for run in plan["states"]:
        parent["terminal_evidence"].pop(run, None)
    owner_id = budget._stock_owner_id(instrument.binding_ref)
    parent["stocks"][instrument.symbol]["owner_ref"] = next(
        owner.fingerprint for owner, _ in budget._owners(parent) if owner.owner_ref == owner_id
    )
    candidates = [copy.deepcopy(parent)]
    if not parent["stocks"][instrument.symbol]["plans"]:
        parent["stocks"].pop(instrument.symbol)
        candidates.append(copy.deepcopy(parent))
        parent.pop("stocks")
        parent["version"] = 3
        candidates.append(parent)
    for candidate in candidates:
        if (
            "sha256:" + budget._digest(candidate) == parent_ref
            and {owner.owner_ref: ref for owner, ref in budget._owners(candidate)} == expected_refs
        ):
            return current
    return expected_refs


def build_kis_paper_stock_plan(
    *,
    binding: Mapping[str, object],
    states: Mapping[str, KisPaperCanaryState],
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    expected_binding_ref: str,
    request_id: str,
    input_ref: str,
    instrument: KisPaperStockInstrument,
    proposal: TargetExposureProposal | None,
    receipt: ResearchDecisionReceipt | None,
    reads: KisPaperStockPreviewReads | None,
    as_of: datetime,
    valid_until: datetime,
) -> KisPaperStockPlan:
    """Pure BUY plan; a retry replays its seed, never its current market inputs.

    Expected owner pins attest the complete current scope. The parent pin on an
    existing request remains its original pin, even after unrelated book changes.
    A fresh request alone requires the current binding hash and current sizing.
    """
    _request_pins(request_id, input_ref, expected_binding_ref)
    at = require_utc(as_of)
    scope_refs = _retry_owner_refs(
        binding, expected_owner_refs, request_id, input_ref, expected_binding_ref, instrument
    )
    entry = _plan_scope(
        binding,
        states,
        expected_account_ref=expected_account_ref,
        expected_basis_ref=expected_basis_ref,
        expected_owner_refs=scope_refs,
        instrument=instrument,
        as_of=at,
    )
    if entry is not None:
        plan = _exact_plan(entry, request_id, input_ref, expected_binding_ref)
        if plan is not None:
            return _stock_plan_result(
                copy.deepcopy(dict(binding)), plan, "replayed", "exact_identity_reused"
            )
    _plan_check(
        not any(p["request_id"] == request_id for p in binding["portfolio"]["plans"]),
        "stock_request_conflict",
    )
    _plan_check(
        "sha256:" + budget._digest(binding) == expected_binding_ref,
        "stock_parent_binding_mismatch",
    )
    updated = copy.deepcopy(dict(binding))
    if updated["version"] == 3:
        updated.update(version=4, stocks={})
    if entry is None:
        updated["stocks"][instrument.symbol] = {
            "exchange": "NASD",
            "instrument_binding_ref": instrument.binding_ref,
            "owner_ref": "sha256:" + "0" * 64,
            "plans": [],
        }
    entry = updated["stocks"][instrument.symbol]
    owner_id = budget._stock_owner_id(instrument.binding_ref)
    entry["owner_ref"] = next(
        owner.fingerprint for owner, _ in budget._owners(updated) if owner.owner_ref == owner_id
    )
    owners = budget._owners(updated)
    replayed, proofs = _replay_scope(updated, states)
    sized = size_kis_paper_stock_target(
        proposal=proposal,
        receipt=receipt,
        instrument=instrument,
        basis=budget._basis(updated),
        expected_basis_ref=expected_basis_ref,
        owners=tuple(owner for owner, _ in owners),
        expected_owner_refs={owner.owner_ref: ref for owner, ref in owners},
        states=replayed,
        stock_owner_ref=owner_id,
        reads=reads,
        as_of=at,
        cancellation_proofs=proofs,
    )
    if sized.status != "sized":
        return KisPaperStockPlan("no_intent", sized.reason)
    until = require_utc(valid_until)
    _plan_check(
        at < until <= min(proposal.valid_until, at + budget._ORDER_LIFETIME),
        "stock_validity_invalid",
    )
    identity = budget._stock_identity(updated, instrument.symbol, request_id, "buy")
    intent = KisPaperCanaryIntent(
        "bk-" + identity,
        "stock-" + identity,
        "stock-" + identity,
        instrument.symbol,
        "NASD",
        sized.quantity,
        sized.limit_price,
        at,
        until,
        price_contract_ref=budget._stock_price_ref(
            updated, instrument.symbol, input_ref, sized.limit_price, "buy"
        ),
    )
    seed = KisPaperCanaryState(intent, "intent_recorded", at, "preview")
    plan = {
        "request_id": request_id,
        "input_ref": input_ref,
        "parent_binding_ref": expected_binding_ref,
        "states": {intent.run_id: seed.to_dict()},
    }
    entry["plans"].append(plan)
    entry["owner_ref"] = next(
        owner.fingerprint for owner, _ in budget._owners(updated) if owner.owner_ref == owner_id
    )
    budget.project_shared_budget(
        binding=updated,
        states=dict(states) | {intent.run_id: seed},
        expected_account_ref=expected_account_ref,
        expected_basis_ref=expected_basis_ref,
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(updated)},
        as_of=at,
    )
    return _stock_plan_result(updated, plan, "prepared", "stock_reservation_prepared")


def _private_root(state_root, repository_root, artifact_root):
    root = Path(state_root)
    _plan_check(
        not any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)),
        "private_root_invalid",
    )
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root))
    return root


def reserve_kis_paper_stock_plan(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    **arguments,
) -> KisPaperStockPlan:
    """Persist only the canonical seed reservation, not an order-state file."""
    root = _private_root(state_root, repository_root, artifact_root)
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, arguments["expected_account_ref"])
            _plan_check(binding is not None, "stock_existing_basis_required")
            result = build_kis_paper_stock_plan(
                binding=binding, states=_states(root, binding), **arguments
            )
            if result.status != "prepared":
                return result
            budget._atomic_json(root / budget.BUDGET_FILE, result.binding)
            retained = budget._load_binding(root, arguments["expected_account_ref"])
            _plan_check(retained == result.binding, "stock_reservation_readback_mismatch")
            budget.project_shared_budget(
                binding=retained,
                states=_states(root, retained),
                expected_account_ref=arguments["expected_account_ref"],
                expected_basis_ref=arguments["expected_basis_ref"],
                expected_owner_refs={
                    owner.owner_ref: ref for owner, ref in budget._owners(retained)
                },
                as_of=arguments["as_of"],
            )
            return replace(
                result, status="reserved", reason="stock_reservation_persisted", binding=retained
            )


def reconcile_kis_paper_stock_plan(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    expected_binding_ref: str,
    input_ref: str,
    instrument: KisPaperStockInstrument,
    request_id: str,
    expected_plan_ref: str,
    as_of: datetime,
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None,
) -> KisPaperStockPlan:
    """Retain exact terminal facts; no broker call or release of unknowns."""
    _request_pins(request_id, input_ref, expected_binding_ref)
    root = _private_root(state_root, repository_root, artifact_root)
    at = require_utc(as_of)
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, expected_account_ref)
            states = {} if binding is None else _states(root, binding)
            entry = _plan_scope(
                binding,
                states,
                expected_account_ref=expected_account_ref,
                expected_basis_ref=expected_basis_ref,
                expected_owner_refs=expected_owner_refs,
                instrument=instrument,
                as_of=at,
            )
            _plan_check(entry is not None, "stock_request_conflict")
            plan = _exact_plan(entry, request_id, input_ref, expected_binding_ref)
            _plan_check(
                plan is not None and "sha256:" + budget._digest(plan) == expected_plan_ref,
                "stock_request_conflict",
            )
            proofs = {} if cancellation_proofs is None else cancellation_proofs
            _plan_check(
                isinstance(proofs, Mapping) and set(proofs) <= set(plan["states"]),
                "stock_proof_scope_invalid",
            )
            updated = copy.deepcopy(binding)
            for run in plan["states"]:
                state = budget._validated_portfolio_state(states[run], at)
                observation = proofs.get(run)
                if observation is not None:
                    _plan_check(
                        type(observation) is KisPaperExecutionObservation, "stock_terminal_unproven"
                    )
                    budget._terminal_payload(state, observation)
                    _plan_check(budget._terminal(state, observation), "stock_terminal_unproven")
                if run not in updated["terminal_evidence"] and budget._terminal(state, observation):
                    updated["terminal_evidence"][run] = budget._terminal_payload(state, observation)
            budget.project_shared_budget(
                binding=updated,
                states=states,
                expected_account_ref=expected_account_ref,
                expected_basis_ref=expected_basis_ref,
                expected_owner_refs=expected_owner_refs,
                as_of=at,
            )
            if updated != binding:
                budget._atomic_json(root / budget.BUDGET_FILE, updated)
                _plan_check(
                    budget._load_binding(root, expected_account_ref) == updated,
                    "stock_reservation_readback_mismatch",
                )
            closed = all(run in updated["terminal_evidence"] for run in plan["states"])
            return _stock_plan_result(
                updated,
                plan,
                "reconciled" if closed else "pending",
                "exact_terminal_states_retained" if closed else "terminal_evidence_incomplete",
            )
