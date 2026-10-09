"""Pure exact-request recovery routing, not execution permission or broker I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, DecimalException, localcontext
from fractions import Fraction
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from . import kis_paper_portfolio_budget as portfolio
from .kis_paper_quote import KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
from .kis_paper_stock_execute import KisPaperStockExecutionBinding
from .kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
    KisPaperStockPreviewReads,
)
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

RecoveryAction = Literal[
    "submit_exact_seed",
    "expired_unsubmitted",
    "await_original_session",
    "reconcile_unknown",
    "reconcile_open",
    "cancel_exact_expired",
    "reconcile_owned",
    "remaining_owned_exit",
    "terminal_owned_flat",
]


@dataclass(frozen=True, repr=False)
class StockSessionRecoveryDirective:
    action: RecoveryAction
    reason: str
    request_id: str
    intent: canary.KisPaperCanaryIntent
    intent_ref: str
    as_of: datetime
    outstanding_quantity: Decimal | None = None
    retained_fill_quantity: Decimal | None = None
    remaining_owned_exit_quantity: Decimal | None = None

    @property
    def original_valid_until(self) -> datetime:
        return self.intent.valid_until

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_stock_session_recovery_v1",
            "action": self.action,
            "reason": self.reason,
            "reservation_effect": "unchanged",
            "limitation": "exact_request_routing_not_execution_permission_or_current_pnl",
        }


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _whole(value: object) -> Fraction:
    _check(type(value) is Decimal and value.is_finite() and value >= 0, "quantity_invalid")
    result = Fraction(value)
    _check(result.denominator == 1, "quantity_invalid")
    return result


def _typed(value: object, expected: type) -> None:
    _check(type(value) is expected, "observation_invalid")
    if hasattr(value, "schema_version"):
        _check(
            type(value.schema_version) is int and value.schema_version == SCHEMA_VERSION,
            "schema_invalid",
        )
    _check(replace(value) == value, "observation_invalid")


def _snapshot(reads, proof, state, at):
    if reads is None:
        return None
    _check(type(reads) in {KisPaperStockPreviewReads, KisPaperStockExitReads}, "reads_invalid")
    _check(
        type(reads.account_ref) is str
        and type(reads.instrument) is type(proof.instrument)
        and reads.account_ref == proof.account_ref
        and reads.instrument == proof.instrument,
        "reads_binding_mismatch",
    )
    snapshot = reads.snapshot
    expected = (
        KisPaperStockExitAccountSnapshot
        if type(reads) is KisPaperStockExitReads
        else KisPaperReadOnlySnapshot
    )
    _typed(snapshot, expected)
    _typed(snapshot.identity, KisPaperAccountIdentity)
    _typed(snapshot.open_orders, KisPaperOpenOrdersSnapshot)
    _check(snapshot.open_orders.complete is True, "open_orders_incomplete")
    _check(type(snapshot.positions) is tuple, "positions_invalid")
    times = [snapshot.captured_at, snapshot.identity.captured_at, snapshot.open_orders.captured_at]
    for rows, expected in (
        (snapshot.positions, KisPaperPosition),
        (snapshot.open_orders.orders, KisPaperOpenOrder),
    ):
        for row in rows:
            _typed(row, expected)
            times.append(row.captured_at)
    _check(
        len({(p.exchange, p.symbol) for p in snapshot.positions}) == len(snapshot.positions),
        "positions_duplicate",
    )
    _check(
        all(
            state.intent.created_at <= require_utc(t) <= at
            and at - t <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
            for t in times
        ),
        "observation_stale_or_future",
    )
    _check(
        require_utc(reads.started_at) <= snapshot.captured_at <= reads.completed_at <= at,
        "reads_time_invalid",
    )
    return snapshot


def _exact_open(snapshot, state):
    if snapshot is None or state.broker_order_id is None:
        return None
    reference = canary._redacted_open_order_reference(state.broker_order_id)
    matches = [o for o in snapshot.open_orders.orders if o.order_reference == reference]
    _check(len(matches) <= 1, "open_identity_ambiguous")
    if not matches:
        return None
    order = matches[0]
    intent = state.intent
    _check(
        (order.symbol, order.exchange, order.side, order.currency)
        == (intent.symbol, intent.exchange, intent.side, "USD")
        and order.requested_quantity == intent.quantity
        and order.limit_price == intent.limit_price,
        "open_identity_mismatch",
    )
    for value in (order.requested_quantity, order.filled_quantity, order.remaining_quantity):
        _whole(value)
    if state.cumulative_fill is not None:
        _check(order.filled_quantity >= state.cumulative_fill.quantity, "open_fill_regressed")
    return order


def _observed_fill(reconciliation, snapshot, state, at):
    if reconciliation is None:
        return None
    _typed(reconciliation, canary.KisPaperCanaryReconciliation)
    _check(
        type(reconciliation.matching_open_order) is bool
        and type(reconciliation.matching_ccnl) is bool
        and type(reconciliation.ccnl_row_count) is int
        and reconciliation.ccnl_row_count >= 0,
        "reconciliation_invalid",
    )
    if reconciliation.execution is None:
        return None
    observation = reconciliation.execution
    _typed(observation, canary.KisPaperExecutionObservation)
    if observation.fill is None:
        return None
    fill = portfolio._validated_fill(observation.fill)
    _check(
        state.current_fill == fill
        and state.fill_observed_at == observation.observed_at == fill.observed_at
        and state.intent.created_at <= fill.observed_at <= at
        and at - fill.observed_at <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
        "fill_binding_or_time_mismatch",
    )
    if (
        snapshot is None
        or reconciliation.snapshot != snapshot
        or reconciliation.account_status != "available"
        or not reconciliation.matching_ccnl
        or any(
            t < fill.observed_at
            for t in (
                snapshot.captured_at,
                snapshot.identity.captured_at,
                snapshot.open_orders.captured_at,
                *(p.captured_at for p in snapshot.positions),
                *(o.captured_at for o in snapshot.open_orders.orders),
            )
        )
    ):
        return None
    return fill


def _owned_quantity(projection, proof, snapshot):
    if projection is None or snapshot is None:
        return None
    _typed(projection, portfolio.KisPaperPortfolioBudgetProjection)
    owner = budget._stock_owner_id(proof.instrument.binding_ref)
    rows = [s for s in projection.stocks_by_owner if s.owner_ref == owner]
    _check(len(rows) == 1 and owner in dict(proof.owner_refs), "owner_projection_mismatch")
    stock = rows[0]
    identity = (proof.instrument.symbol, "NASD")
    _check((stock.symbol, stock.exchange) == identity, "owner_instrument_mismatch")
    quantity = _whole(stock.quantity)
    totals = [s for s in projection.stocks_by_instrument if (s.symbol, s.exchange) == identity]
    _check(len(totals) == 1, "instrument_projection_mismatch")
    total = _whole(totals[0].quantity)
    _check(
        sum(
            (
                _whole(s.quantity)
                for s in projection.stocks_by_owner
                if (s.symbol, s.exchange) == identity
            ),
            Fraction(0),
        )
        == total
        and quantity <= total,
        "projection_quantity_mismatch",
    )
    positions = [p for p in snapshot.positions if p.symbol == identity[0]]
    _check(
        all((p.symbol, p.exchange, p.currency) == (*identity, "USD") for p in positions)
        and sum((_whole(p.quantity) for p in positions), Fraction(0)) == total,
        "broker_owned_quantity_mismatch",
    )
    return stock.quantity


def plan_stock_session_recovery(
    *,
    proof: KisPaperStockExecutionBinding,
    seed: canary.KisPaperCanaryState,
    state: canary.KisPaperCanaryState,
    session_open: datetime,
    session_close: datetime,
    as_of: datetime,
    reconciliation: canary.KisPaperCanaryReconciliation | None = None,
    projection: portfolio.KisPaperPortfolioBudgetProjection | None = None,
    reads: KisPaperStockPreviewReads | KisPaperStockExitReads | None = None,
) -> StockSessionRecoveryDirective:
    """Route one caller-bound persisted request without changing its TTL or book.

    The caller supplies already verified custody, complete all-owner replay and
    account-bound reads. This function neither loads nor persists those facts.
    Even an EXIT directive constructs no replacement order or decision.
    """
    at, opened, closed = (require_utc(t) for t in (as_of, session_open, session_close))
    _check(opened < closed, "session_invalid")
    _check(
        type(seed) is canary.KisPaperCanaryState and type(state) is canary.KisPaperCanaryState,
        "state_invalid",
    )
    # Isolate validation/identity normalization from ambient Decimal flags/traps.
    values = [getattr(getattr(s, "intent", None), "quantity", None) for s in (seed, state)]
    precision = max([128, *(len(v.as_tuple().digits) + 8 for v in values if type(v) is Decimal)])
    with localcontext(Context(prec=precision, Emin=MIN_EMIN, Emax=MAX_EMAX)):
        try:
            _typed(proof, KisPaperStockExecutionBinding)
            seed = portfolio._validated_state(seed, at)
            state = portfolio._validated_state(state, at)
            intent = seed.intent
            _check(seed.phase == "intent_recorded", "seed_not_original")
            _check(
                state.intent == intent
                and intent.fingerprint == proof.intent_ref
                and intent.run_id == proof.run_id
                and (intent.symbol, intent.exchange, intent.side)
                == (proof.instrument.symbol, "NASD", proof.side),
                "request_binding_mismatch",
            )
            _check(
                opened - budget._ORDER_LIFETIME <= intent.created_at < closed
                and opened < intent.valid_until <= closed
                and intent.valid_until <= intent.created_at + budget._ORDER_LIFETIME,
                "original_session_mismatch",
            )
            snapshot = _snapshot(reads, proof, state, at)
            order = _exact_open(snapshot, state)
            fill = _observed_fill(reconciliation, snapshot, state, at)
            attempted = state.submission_started_at is not None or state.submitted_at is not None
            terminal = (
                attempted
                and state.phase == "rejected"
                and state.submit_response_category == "provider_rejected"
            ) or (
                attempted
                and fill is not None
                and order is None
                and reconciliation.matching_open_order is False
                and budget._terminal(state, reconciliation.execution)
            )
            remaining = _owned_quantity(projection, proof, snapshot) if terminal else None
            outstanding = None if order is None else order.remaining_quantity
            local_filled = state.current_fill is not None and state.current_fill.status == "filled"
            if terminal:
                if remaining is None:
                    action, reason = "reconcile_owned", "terminal_order_not_current_inventory"
                elif remaining > 0:
                    action, reason = "remaining_owned_exit", "closed_order_retained_owned_quantity"
                else:
                    action, reason = "terminal_owned_flat", "complete_broker_owned_reconciliation"
            elif state.phase == "intent_recorded":
                if at >= intent.valid_until:
                    action, reason = "expired_unsubmitted", "original_ttl_expired_no_attempt"
                elif at < opened:
                    action, reason = "await_original_session", "original_session_not_open"
                elif snapshot is not None and any(
                    (o.symbol, o.exchange) == (intent.symbol, intent.exchange)
                    for o in snapshot.open_orders.orders
                ):
                    action, reason = "reconcile_unknown", "exact_instrument_overlap"
                else:
                    action, reason = "submit_exact_seed", "original_unattempted_seed_within_ttl"
            elif local_filled:
                action, reason = "reconcile_owned", "recorded_fill_not_current_inventory"
            elif state.phase in {"submission_started", "outcome_unknown", "cancel_started"}:
                action, reason = "reconcile_unknown", "exact_attempt_outcome_not_terminal"
            elif state.phase == "submitted":
                if not attempted:
                    action, reason = "reconcile_unknown", "original_attempt_time_unknown"
                elif (
                    at >= intent.valid_until
                    and attempted
                    and order is not None
                    and fill is not None
                    and reconciliation.matching_open_order is True
                ):
                    action, reason = "cancel_exact_expired", "attempted_exact_positive_outstanding"
                else:
                    action, reason = "reconcile_open", "exact_order_requires_current_observation"
            else:
                action, reason = "reconcile_unknown", "terminal_phase_without_complete_evidence"
            return StockSessionRecoveryDirective(
                action,
                reason,
                proof.request_id,
                intent,
                proof.intent_ref,
                at,
                outstanding,
                None if state.cumulative_fill is None else state.cumulative_fill.quantity,
                remaining,
            )
        except (TypeError, AttributeError, DecimalException):
            raise ValueError("recovery_fact_invalid") from None
