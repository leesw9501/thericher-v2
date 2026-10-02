"""Pure, private aggregate replay for explicitly owned SPY/QQQ Paper intents.

This is NOT deployed authoritative cap enforcement. The caller must verify the
account and owner bindings, supply their independently frozen expected digests,
and supply one latest state per referenced intent in causal owner-ledger order.
Digests check consistency, not broker provenance or permission. No account
snapshot is accepted and no persistence, broker request, or logging occurs here.

Stored positive cumulative fills remain facts after a later unavailable read.
Observation timestamps are read times, not execution ordering. Replay prefixes
use intent creation order; they do not reconstruct historical buying power or
prove call-time ownership. Costs use exact rational arithmetic internally, with
non-terminating displayed costs rounded up and remaining capital rounded down.
Fees, settled cash, sale proceeds, and net PnL are not projected.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, DecimalException, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from .kis_paper_fill_accounting import KisPaperCumulativeFill, KisPaperExecutionObservation

PORTFOLIO_ALLOCATION_FRACTION = Decimal("0.10")
_INSTRUMENTS = (("SPY", "AMEX"), ("QQQ", "NASD"))
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_ACCOUNT = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,80}")
_US_EASTERN = ZoneInfo("America/New_York")


class KisPaperPortfolioBudgetError(ValueError):
    """Categorical input/replay failure, containing no private values."""


def _check(condition: bool, category: str) -> None:
    if not condition:
        raise KisPaperPortfolioBudgetError(category)


def _text(value: object, pattern: re.Pattern[str], category: str) -> None:
    _check(type(value) is str and pattern.fullmatch(value) is not None, category)


def _amount(value: object, *, positive: bool = False, whole: bool = False) -> None:
    _check(
        type(value) is Decimal
        and value.is_finite()
        and not value.is_signed()
        and (value > 0 if positive else value >= 0)
        and (not whole or value == value.to_integral_value()),
        "numeric_field_invalid",
    )


def _time(value: object) -> datetime:
    _check(type(value) is datetime, "timestamp_invalid")
    try:
        return require_utc(value)
    except (ValueError, TypeError, AttributeError):
        raise KisPaperPortfolioBudgetError("timestamp_invalid") from None


def _digest(payload: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
    )


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioBudgetBasis:
    account_ref: str
    basis_usd: Decimal
    allocated_usd: Decimal
    frozen_at: datetime

    def __post_init__(self) -> None:
        _text(self.account_ref, _ACCOUNT, "account_binding_invalid")
        _amount(self.basis_usd, positive=True)
        _amount(self.allocated_usd, positive=True)
        _time(self.frozen_at)
        _check(
            Fraction(self.allocated_usd) == Fraction(self.basis_usd) / 10,
            "allocation_not_initial_tenth",
        )

    @property
    def fingerprint(self) -> str:
        return _digest(
            [
                "kis_paper_portfolio_basis_v1",
                self.account_ref,
                str(self.basis_usd),
                str(self.allocated_usd),
                self.frozen_at.isoformat(),
            ]
        )


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioStateRef:
    run_id: str
    intent_ref: str

    def __post_init__(self) -> None:
        _text(self.run_id, _IDENTIFIER, "state_reference_invalid")
        _text(self.intent_ref, _HASH, "intent_reference_invalid")


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioOwnerBinding:
    owner_ref: str
    account_ref: str
    symbol: str
    exchange: str
    state_refs: tuple[KisPaperPortfolioStateRef, ...]

    def __post_init__(self) -> None:
        _text(self.owner_ref, _IDENTIFIER, "owner_binding_invalid")
        _text(self.account_ref, _ACCOUNT, "account_binding_invalid")
        _check(
            type(self.symbol) is str
            and type(self.exchange) is str
            and (self.symbol, self.exchange) in _INSTRUMENTS,
            "instrument_invalid",
        )
        _check(type(self.state_refs) is tuple, "state_references_not_frozen")
        for reference in self.state_refs:
            _check(type(reference) is KisPaperPortfolioStateRef, "state_reference_invalid")
            replace(reference)

    @property
    def fingerprint(self) -> str:
        return _digest(
            [
                "kis_paper_portfolio_owner_v1",
                self.owner_ref,
                self.account_ref,
                self.symbol,
                self.exchange,
                [[reference.run_id, reference.intent_ref] for reference in self.state_refs],
            ]
        )


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioStock:
    owner_ref: str | None
    symbol: str
    exchange: str
    quantity: Decimal
    entry_cost: Decimal
    reserved_buys: Decimal


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioBudgetProjection:
    basis_usd: Decimal
    allocated_usd: Decimal
    stocks_by_owner: tuple[KisPaperPortfolioStock, ...]
    stocks_by_instrument: tuple[KisPaperPortfolioStock, ...]
    entry_cost: Decimal
    reserved_buys: Decimal
    remaining_cap: Decimal


def _validated_fill(value: object) -> KisPaperCumulativeFill:
    _check(type(value) is KisPaperCumulativeFill, "fill_invalid")
    _text(value.identity_ref, _HASH, "fill_identity_invalid")
    _amount(value.requested_quantity, positive=True, whole=True)
    _amount(value.quantity, whole=True)
    _amount(value.gross_amount)
    if value.remaining_quantity is not None:
        _amount(value.remaining_quantity, whole=True)
    _time(value.observed_at)
    try:
        return replace(value)
    except (ValueError, TypeError, AttributeError, DecimalException):
        raise KisPaperPortfolioBudgetError("fill_fact_invalid") from None


def _validated_state(value: object, as_of: datetime) -> KisPaperCanaryState:
    _check(type(value) is KisPaperCanaryState, "state_invalid")
    intent = value.intent
    _check(type(intent) is KisPaperCanaryIntent, "intent_invalid")
    _amount(intent.quantity, positive=True, whole=True)
    _amount(intent.limit_price, positive=True)
    _check(
        type(intent.schema_version) is int
        and intent.schema_version == SCHEMA_VERSION
        and type(value.schema_version) is int
        and value.schema_version == SCHEMA_VERSION,
        "schema_invalid",
    )
    for item in (intent.created_at, intent.valid_until, value.updated_at):
        _time(item)
    for item in (value.submission_started_at, value.submitted_at, value.fill_observed_at):
        if item is not None:
            _time(item)
    fill = value.cumulative_fill
    if fill is not None:
        fill = _validated_fill(fill)
    try:
        # Revalidate typed facts without mutating the caller's frozen objects.
        state = replace(
            value,
            intent=replace(intent),
            cumulative_fill=fill,
        )
    except (ValueError, TypeError, AttributeError, DecimalException):
        raise KisPaperPortfolioBudgetError("state_fact_invalid") from None
    _check(intent.created_at <= state.updated_at <= as_of, "state_time_invalid")
    _check(
        state.submitted_at is None or state.submitted_at <= state.updated_at,
        "state_time_invalid",
    )
    if state.phase == "intent_recorded":
        _check(
            state.submission_started_at is None
            and state.submitted_at is None
            and state.broker_order_id is None
            and fill is None,
            "unsubmitted_state_conflict",
        )
    if state.phase == "rejected":
        _check(
            state.broker_order_id is None and state.submitted_at is None and fill is None,
            "rejected_state_conflict",
        )
    return state


def _cancel_proof(state: KisPaperCanaryState, proof: object) -> None:
    _check(type(proof) is KisPaperExecutionObservation, "cancel_proof_invalid")
    try:
        fill = None if proof.fill is None else _validated_fill(proof.fill)
        if proof.observed_at is not None:
            _time(proof.observed_at)
        validated = replace(proof, fill=fill)
    except (ValueError, TypeError, AttributeError, DecimalException):
        raise KisPaperPortfolioBudgetError("cancel_proof_invalid") from None
    _check(
        state.phase == "cancelled"
        and validated.cancellation_confirmed
        and validated.status == "available"
        and validated.same_day_order_id_seen
        and validated.fill is not None
        and validated.fill == state.current_fill
        and validated.observed_at == state.fill_observed_at,
        "cancel_proof_mismatch",
    )


def _broker_reference(state: KisPaperCanaryState, account_ref: str) -> str | None:
    if state.broker_order_id is None:
        return None
    order_at = state.submission_started_at or state.submitted_at
    _check(order_at is not None, "broker_order_date_missing")
    identifier = state.broker_order_id
    # Positive ASCII numeric padding aliases are already matched by KIS history.
    if identifier.isascii() and identifier.isdecimal() and int(identifier) > 0:
        identifier = identifier.lstrip("0")
    return _digest(
        [account_ref, _time(order_at).astimezone(_US_EASTERN).date().isoformat(), identifier]
    )


def _released_buy(state: KisPaperCanaryState, cancellation_confirmed: bool) -> bool:
    if state.phase == "intent_recorded":
        return state.updated_at >= state.intent.valid_until
    if state.phase == "rejected":
        return state.submit_response_category == "provider_rejected"
    # Only an exact zero-fill cancellation proof releases a cancelled residual.
    # Partial-cancel residuals without a supported proof remain conservative.
    return cancellation_confirmed


def _decimal(value: Fraction, *, rounding: str = ROUND_CEILING) -> Decimal:
    numerator, denominator = Decimal(value.numerator), Decimal(value.denominator)
    with localcontext() as context:
        context.prec = max(
            64, len(numerator.as_tuple().digits) + len(denominator.as_tuple().digits) + 4
        )
        context.rounding = rounding
        return numerator / denominator


def project_kis_paper_portfolio_budget(
    *,
    basis: KisPaperPortfolioBudgetBasis,
    expected_basis_ref: str,
    owners: tuple[KisPaperPortfolioOwnerBinding, ...],
    expected_owner_refs: Mapping[str, str],
    states: Mapping[str, KisPaperCanaryState],
    as_of: datetime,
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None,
) -> KisPaperPortfolioBudgetProjection:
    """Replay one supplied scope; reject duplicate intents rather than deduplicate.

    Expected references must come from caller-verified frozen custody, not be
    regenerated to accept a reset. Each owner binds one instrument and ordered
    references; every supplied state is referenced exactly once. Account proof
    cannot be derived from a canary state, which carries no account identity.
    No missing/absent/unavailable read or unknown phase is terminal evidence.
    """
    _check(type(basis) is KisPaperPortfolioBudgetBasis, "basis_invalid")
    replace(basis)
    _text(expected_basis_ref, _HASH, "basis_reference_invalid")
    _check(basis.fingerprint == expected_basis_ref, "basis_binding_mismatch")
    at = _time(as_of)
    _check(_time(basis.frozen_at) <= at, "basis_time_invalid")
    _check(type(owners) is tuple, "owners_not_frozen")
    _check(isinstance(states, Mapping), "states_invalid")
    _check(isinstance(expected_owner_refs, Mapping), "owner_proofs_invalid")
    proofs = {} if cancellation_proofs is None else cancellation_proofs
    _check(isinstance(proofs, Mapping), "cancel_proofs_invalid")
    owner_ids, run_ids, intent_ids, client_ids, decision_ids, fill_ids, broker_refs = (
        set() for _ in range(7)
    )
    events = []
    for owner in owners:
        _check(type(owner) is KisPaperPortfolioOwnerBinding, "owner_binding_invalid")
        replace(owner)
        _check(owner.owner_ref not in owner_ids, "duplicate_owner")
        owner_ids.add(owner.owner_ref)
        _check(owner.account_ref == basis.account_ref, "account_binding_mismatch")
        expected = expected_owner_refs.get(owner.owner_ref)
        _text(expected, _HASH, "owner_reference_invalid")
        _check(owner.fingerprint == expected, "owner_binding_mismatch")
        previous = None
        for reference in owner.state_refs:
            _check(reference.run_id not in run_ids, "duplicate_state_reference")
            run_ids.add(reference.run_id)
            _check(reference.run_id in states, "referenced_state_missing")
            state = _validated_state(states[reference.run_id], at)
            intent = state.intent
            _check(
                intent.run_id == reference.run_id and intent.fingerprint == reference.intent_ref,
                "intent_binding_mismatch",
            )
            _check(
                (intent.symbol, intent.exchange) == (owner.symbol, owner.exchange),
                "owner_instrument_mismatch",
            )
            order_at = state.submission_started_at or state.submitted_at or intent.created_at
            ordered_at = (intent.created_at, order_at)
            _check(
                previous is None or (ordered_at[0] >= previous[0] and ordered_at[1] >= previous[1]),
                "owner_order_invalid",
            )
            previous = ordered_at
            for identifier, seen in (
                (intent.fingerprint, intent_ids),
                (intent.client_order_id, client_ids),
                (intent.decision_id, decision_ids),
            ):
                _check(identifier not in seen, "duplicate_intent_identity")
                seen.add(identifier)
            broker_ref = _broker_reference(state, basis.account_ref)
            if broker_ref is not None:
                _check(broker_ref not in broker_refs, "broker_order_alias")
                broker_refs.add(broker_ref)
            if state.cumulative_fill is not None:
                identity = state.cumulative_fill.identity_ref
                _check(identity not in fill_ids, "duplicate_fill_identity")
                fill_ids.add(identity)
            if reference.run_id in proofs:
                _cancel_proof(state, proofs[reference.run_id])
            events.append((ordered_at, len(events), owner.owner_ref, state))
    _check(set(expected_owner_refs) == owner_ids, "owner_proof_scope_mismatch")
    _check(set(states) == run_ids, "state_scope_mismatch")
    _check(set(proofs) <= run_ids, "cancel_proof_scope_mismatch")

    # Owner-local average entry cost never includes another owner's sale proceeds.
    ledger = {owner.owner_ref: [Fraction(0), Fraction(0), Fraction(0)] for owner in owners}
    allocated = Fraction(basis.allocated_usd)
    for _, _, owner_ref, state in sorted(events):
        intent, fill = state.intent, state.cumulative_fill
        filled = Fraction(0) if fill is None else Fraction(fill.quantity)
        amount = Fraction(0) if fill is None else Fraction(fill.gross_amount)
        quantity, cost, reserved = ledger[owner_ref]
        requested, limit = Fraction(intent.quantity), Fraction(intent.limit_price)
        if intent.side == "buy":
            _check(amount <= filled * limit, "buy_fill_limit_conflict")
            quantity += filled
            cost += amount
            if not _released_buy(state, intent.run_id in proofs):
                reserved += (requested - filled) * limit
        else:
            _check(requested <= quantity, "unowned_sell")
            if filled:
                cost = cost * (quantity - filled) / quantity
                quantity -= filled
        ledger[owner_ref] = [quantity, cost, reserved]
        _check(
            sum((row[1] + row[2] for row in ledger.values()), Fraction(0)) <= allocated,
            "aggregate_budget_exceeded",
        )

    def stock(owner_ref, symbol, exchange, values):
        return KisPaperPortfolioStock(owner_ref, symbol, exchange, *map(_decimal, values))

    by_owner = tuple(
        stock(owner.owner_ref, owner.symbol, owner.exchange, ledger[owner.owner_ref])
        for owner in owners
    )
    by_instrument = tuple(
        stock(
            None,
            symbol,
            exchange,
            [
                sum(
                    (
                        ledger[owner.owner_ref][index]
                        for owner in owners
                        if (owner.symbol, owner.exchange) == (symbol, exchange)
                    ),
                    Fraction(0),
                )
                for index in range(3)
            ],
        )
        for symbol, exchange in _INSTRUMENTS
    )
    cost = sum((row[1] for row in ledger.values()), Fraction(0))
    reserved = sum((row[2] for row in ledger.values()), Fraction(0))
    return KisPaperPortfolioBudgetProjection(
        basis.basis_usd,
        basis.allocated_usd,
        by_owner,
        by_instrument,
        _decimal(cost),
        _decimal(reserved),
        _decimal(allocated - cost - reserved, rounding=ROUND_FLOOR),
    )
