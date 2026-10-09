"""Exact-owned stock EXIT seeds in the existing canonical V4 Paper bank.

The builder is pure. Reservation and reconciliation reuse canonical locks and
storage, never a broker or credential path. Caller-attested source/account pins
check consistency, not provenance, atomic broker state, settlement or net PnL.
An explicit strategy EXIT is required; this module does not choose an exit.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    decision_instrument_binding_ref,
    receipt_from_target_exposure_proposal,
)

from . import kis_paper_budget_strategy as budget
from .kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_fill_accounting import KisPaperCumulativeFill, KisPaperExecutionObservation
from .kis_paper_portfolio_budget import KisPaperPortfolioBudgetProjection
from .kis_paper_portfolio_plan import _replay_scope, _states
from .kis_paper_quote import KisPaperQuoteError, KisPaperSpyLimitInput
from .kis_paper_stock_plan import (
    _amount,
    _check,
    _context,
    _exact_plan,
    _plan_check,
    _plan_scope,
    _private_root,
    _request_pins,
    _retry_owner_refs,
    _time,
    _typed,
    _Unavailable,
)
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
)
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperPosition,
    KisPaperReadOnlyError,
)


@dataclass(frozen=True, repr=False)
class KisPaperStockExitPlan:
    status: str
    reason: str
    binding: dict | None = None
    intents: tuple[KisPaperCanaryIntent, ...] = ()
    plan_ref: str | None = None
    reservation: Decimal = Decimal(0)
    projection: KisPaperPortfolioBudgetProjection | None = None
    owned_quantity: Decimal | None = None

    def safe_payload(self) -> dict[str, str]:
        return {
            "kind": "kis_paper_stock_exit_plan_v1",
            "status": self.status,
            "reason": self.reason,
            "inventory": (
                "unavailable"
                if self.owned_quantity is None
                else "owned_flat"
                if self.owned_quantity == 0
                else "owned_remaining"
            ),
            "limitation": "gross_owned_lifecycle_not_settlement_net_pnl_or_execution_permission",
        }


def _values(states, reads=None):
    values = []
    if isinstance(states, Mapping):
        for state in states.values():
            if type(state) is KisPaperCanaryState:
                for value in (state.intent, state.cumulative_fill):
                    if type(value) in (KisPaperCanaryIntent, KisPaperCumulativeFill):
                        values.extend(getattr(value, f.name) for f in fields(value))
    if type(reads) is KisPaperStockExitReads:
        if type(reads.quote) is KisPaperSpyLimitInput:
            values.extend(getattr(reads.quote, f.name) for f in fields(reads.quote))
        if type(reads.snapshot) is KisPaperStockExitAccountSnapshot:
            for rows in (
                reads.snapshot.positions,
                getattr(reads.snapshot.open_orders, "orders", ()),
            ):
                if type(rows) is tuple:
                    for row in rows:
                        if type(row) in (KisPaperPosition, KisPaperOpenOrder):
                            values.extend(getattr(row, f.name) for f in fields(row))
    return values


def _owned(projection, instrument):
    owner_id = budget._stock_owner_id(instrument.binding_ref)
    return next(row for row in projection.stocks_by_owner if row.owner_ref == owner_id)


def _result(binding, plan, status, reason, projection, instrument):
    seeds = budget._stock_seed_states(binding)
    intents = tuple(seeds[run].intent for run in plan["states"])
    _plan_check(len(intents) == 1 and intents[0].side == "sell", "stock_exit_plan_invalid")
    return KisPaperStockExitPlan(
        status,
        reason,
        binding,
        intents,
        "sha256:" + budget._digest(plan),
        projection=projection,
        owned_quantity=_owned(projection, instrument).quantity,
    )


def _fresh_exit(
    proposal,
    receipt,
    reads,
    instrument,
    expected_account_ref,
    expected_masked_account,
    projection,
    binding,
    states,
    at,
):
    _typed(proposal, TargetExposureProposal, "proposal_invalid")
    _typed(receipt, ResearchDecisionReceipt, "receipt_invalid")
    _check(proposal.action == receipt.decision_class == "exit", "explicit_exit_required")
    _check(_amount(proposal.target_exposure) == 0, "exit_target_not_zero")
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
    _check(
        proposal.symbol == instrument.symbol
        and proposal.market == instrument.market == "US"
        and instrument.binding_ref
        == decision_instrument_binding_ref(
            symbol=instrument.symbol,
            market="US",
            decision_class="enter",
        ),
        "entry_instrument_binding_mismatch",
    )
    _typed(reads, KisPaperStockExitReads, "reads_invalid")
    _typed(reads.instrument, KisPaperStockInstrument, "instrument_invalid")
    _check(reads.instrument == instrument, "read_instrument_mismatch")
    _check(reads.account_ref == expected_account_ref, "account_binding_mismatch")
    snapshot = reads.snapshot
    for value, kind in (
        (snapshot, KisPaperStockExitAccountSnapshot),
        (snapshot.identity, KisPaperAccountIdentity),
        (snapshot.open_orders, KisPaperOpenOrdersSnapshot),
    ):
        _typed(value, kind, "reads_invalid")
    _check(
        type(expected_masked_account) is str
        and re.fullmatch(r"\*{4}[0-9]{4}-\*{2}", expected_masked_account) is not None
        and snapshot.identity.masked_account == expected_masked_account,
        "account_identity_mismatch",
    )
    _check(snapshot.open_orders.complete is True, "account_incomplete")
    _check(
        proposal.decided_at
        <= _time(reads.started_at)
        <= snapshot.captured_at
        <= _time(reads.completed_at)
        <= at,
        "read_clock_invalid",
    )
    times = [
        reads.started_at,
        reads.completed_at,
        snapshot.captured_at,
        snapshot.identity.captured_at,
        snapshot.open_orders.captured_at,
        reads.quote.quoted_at,
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
    for order in snapshot.open_orders.orders:
        _typed(order, KisPaperOpenOrder, "open_order_invalid")
        times.append(order.captured_at)
        _check(order.symbol != instrument.symbol, "target_open_order_pending")
    _check(
        proposal.decided_at <= reads.quote.quoted_at <= reads.completed_at
        and all(timedelta(0) <= at - _time(t) <= timedelta(seconds=120) for t in times),
        "reads_stale",
    )
    owned = _owned(projection, instrument)
    total_owned = sum(
        (
            Fraction(row.quantity)
            for row in projection.stocks_by_owner
            if (row.symbol, row.exchange) == (instrument.symbol, "NASD")
        ),
        Fraction(0),
    )
    _check(broker_quantity == total_owned, "target_inventory_mismatch")
    replayed, proofs = _replay_scope(binding, states)
    owner = next(
        o
        for o, _ in budget._owners(binding)
        if o.owner_ref == budget._stock_owner_id(instrument.binding_ref)
    )
    _check(
        not any(
            not budget._terminal(replayed[ref.run_id], proofs.get(ref.run_id))
            for ref in owner.state_refs
        ),
        "stock_owner_pending",
    )
    quantity = _amount(owned.quantity, whole=True)
    _check(quantity <= broker_quantity, "owned_exit_oversell")
    _typed(reads.quote, KisPaperSpyLimitInput, "quote_invalid")
    _check(type(reads.quote.decimal_places) is int, "quote_invalid")
    bid = _amount(reads.quote.best_bid, positive=True)
    ask = _amount(reads.quote.best_ask, positive=True)
    tick = _amount(reads.quote.tick_size, positive=True)
    _check(bid <= ask, "quote_invalid")
    _check(
        (tick / Fraction(1, 10**reads.quote.decimal_places)).denominator == 1, "quote_tick_invalid"
    )
    limit = (bid // tick) * tick
    _check(limit > 0, "quote_limit_zero")
    return owned.quantity, budget._exact_decimal(limit)


def build_kis_paper_stock_exit_plan(
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
    reads: KisPaperStockExitReads | None,
    as_of: datetime,
    valid_until: datetime,
    expected_masked_account: str | None = None,
) -> KisPaperStockExitPlan:
    """Pure whole-owner SELL; exact retries reuse the original seed and clocks.

    A fresh build requires caller-attested masked identity plus account digest.
    ENTRY custody stays unchanged while the separate receipt binds EXIT/zero.
    Unknown actions of another instrument do not pause this owner's lifecycle.
    """
    _request_pins(request_id, input_ref, expected_binding_ref)
    at = require_utc(as_of)
    with localcontext(_context(_values(states, reads))):
        scope_refs = _retry_owner_refs(
            binding,
            expected_owner_refs,
            request_id,
            input_ref,
            expected_binding_ref,
            instrument,
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
        _plan_check(
            binding["version"] == 4 and entry is not None, "stock_exit_existing_owner_required"
        )
        projection = budget.project_shared_budget(
            binding=binding,
            states=states,
            expected_account_ref=expected_account_ref,
            expected_basis_ref=expected_basis_ref,
            expected_owner_refs=scope_refs,
            as_of=at,
        )
        plan = _exact_plan(entry, request_id, input_ref, expected_binding_ref)
        if plan is not None:
            return _result(
                copy.deepcopy(dict(binding)),
                plan,
                "replayed",
                "exact_identity_reused",
                projection,
                instrument,
            )
        _plan_check(
            not any(p["request_id"] == request_id for p in binding["portfolio"]["plans"]),
            "stock_request_conflict",
        )
        _plan_check(
            "sha256:" + budget._digest(binding) == expected_binding_ref,
            "stock_parent_binding_mismatch",
        )
        try:
            quantity, limit = _fresh_exit(
                proposal,
                receipt,
                reads,
                instrument,
                expected_account_ref,
                expected_masked_account,
                projection,
                binding,
                states,
                at,
            )
        except (
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            DecimalException,
            KisPaperReadOnlyError,
            KisPaperQuoteError,
        ) as error:
            reason = str(error) if type(error) is _Unavailable else "typed_input_invalid"
            return KisPaperStockExitPlan(
                "no_intent",
                reason,
                projection=projection,
                owned_quantity=_owned(projection, instrument).quantity,
            )
        if quantity == 0:
            return KisPaperStockExitPlan(
                "no_intent", "stock_owner_flat", projection=projection, owned_quantity=quantity
            )
        until = require_utc(valid_until)
        _plan_check(
            at < until <= min(proposal.valid_until, at + budget._ORDER_LIFETIME),
            "stock_validity_invalid",
        )
        updated = copy.deepcopy(dict(binding))
        identity = budget._stock_identity(updated, instrument.symbol, request_id, "sell")
        intent = KisPaperCanaryIntent(
            "bk-" + identity,
            "stock-" + identity,
            "stock-" + identity,
            instrument.symbol,
            "NASD",
            quantity,
            limit,
            at,
            until,
            "sell",
            price_contract_ref=budget._stock_price_ref(
                updated,
                instrument.symbol,
                input_ref,
                limit,
                "sell",
            ),
        )
        seed = KisPaperCanaryState(intent, "intent_recorded", at, "preview")
        plan = {
            "request_id": request_id,
            "input_ref": input_ref,
            "parent_binding_ref": expected_binding_ref,
            "states": {intent.run_id: seed.to_dict()},
        }
        entry = updated["stocks"][instrument.symbol]
        entry["plans"].append(plan)
        entry["owner_ref"] = next(
            o.fingerprint
            for o, _ in budget._owners(updated)
            if o.owner_ref == budget._stock_owner_id(instrument.binding_ref)
        )
        projection = budget.project_shared_budget(
            binding=updated,
            states=dict(states) | {intent.run_id: seed},
            expected_account_ref=expected_account_ref,
            expected_basis_ref=expected_basis_ref,
            expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(updated)},
            as_of=at,
        )
        return _result(
            updated, plan, "prepared", "stock_exit_reservation_prepared", projection, instrument
        )


def reserve_kis_paper_stock_exit_plan(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    **arguments,
) -> KisPaperStockExitPlan:
    """Persist one canonical SELL seed under the existing shared writer locks."""
    root = _private_root(state_root, repository_root, artifact_root)
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, arguments["expected_account_ref"])
            _plan_check(binding is not None, "stock_existing_basis_required")
            result = build_kis_paper_stock_exit_plan(
                binding=binding,
                states=_states(root, binding),
                **arguments,
            )
            if result.status != "prepared":
                return result
            budget._atomic_json(root / budget.BUDGET_FILE, result.binding)
            retained = budget._load_binding(root, arguments["expected_account_ref"])
            _plan_check(retained == result.binding, "stock_reservation_readback_mismatch")
            with localcontext(_context(_values(_states(root, retained)))):
                budget.project_shared_budget(
                    binding=retained,
                    states=_states(root, retained),
                    expected_account_ref=arguments["expected_account_ref"],
                    expected_basis_ref=arguments["expected_basis_ref"],
                    expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(retained)},
                    as_of=arguments["as_of"],
                )
            return replace(
                result,
                status="reserved",
                reason="stock_exit_reservation_persisted",
                binding=retained,
            )


def reconcile_kis_paper_stock_exit_plan(
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
) -> KisPaperStockExitPlan:
    """Retain exact terminal facts, independently reporting current owned inventory.

    A closed partial SELL can leave inventory. Unknown outcomes remain pending;
    no broker query, resubmission, cancellation, or flat-account claim is made.
    """
    _request_pins(request_id, input_ref, expected_binding_ref)
    root = _private_root(state_root, repository_root, artifact_root)
    at = require_utc(as_of)
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, expected_account_ref)
            states = {} if binding is None else _states(root, binding)
            with localcontext(_context(_values(states))):
                entry = _plan_scope(
                    binding,
                    states,
                    expected_account_ref=expected_account_ref,
                    expected_basis_ref=expected_basis_ref,
                    expected_owner_refs=expected_owner_refs,
                    instrument=instrument,
                    as_of=at,
                )
                _plan_check(
                    binding["version"] == 4 and entry is not None,
                    "stock_exit_existing_owner_required",
                )
                plan = _exact_plan(entry, request_id, input_ref, expected_binding_ref)
                _plan_check(
                    plan is not None and "sha256:" + budget._digest(plan) == expected_plan_ref,
                    "stock_request_conflict",
                )
                seeds = budget._stock_seed_states(binding)
                _plan_check(
                    len(plan["states"]) == 1
                    and all(seeds[run].intent.side == "sell" for run in plan["states"]),
                    "stock_exit_plan_invalid",
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
                            type(observation) is KisPaperExecutionObservation,
                            "stock_terminal_unproven",
                        )
                        budget._terminal_payload(state, observation)
                        _plan_check(budget._terminal(state, observation), "stock_terminal_unproven")
                    if run not in updated["terminal_evidence"] and budget._terminal(
                        state, observation
                    ):
                        updated["terminal_evidence"][run] = budget._terminal_payload(
                            state, observation
                        )
                projection = budget.project_shared_budget(
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
                return _result(
                    updated,
                    plan,
                    "reconciled" if closed else "pending",
                    "exact_terminal_states_retained" if closed else "terminal_evidence_incomplete",
                    projection,
                    instrument,
                )
