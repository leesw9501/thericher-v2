"""Aggregate virtual-cash sizing for the existing SPY daily strategy.

The private binding holds funding and references, not a second fill ledger.
All quantities/costs are replayed from the existing exact canary states.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal, DecimalException
from pathlib import Path

from thericher_v2.contracts import require_utc
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt
from thericher_v2.research.kis_paper_canary_intent import (
    KisPaperCanaryBuyDecision,
    KisPaperCanarySellDecision,
)

from .emergency import DEFAULT_PAPER_EXECUTION_CONTROL_STATE, PaperExecutionControlStore
from .kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryStateStore,
    UrllibKisPaperCanaryTransport,
    _cancel_submitted_canary,
    _record_reconciliation_fill,
    _run_kis_paper_canary,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_quote import (
    KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
    KisPaperQuoteError,
    derive_kis_paper_marketable_limit,
)
from .kis_paper_session import _session_now, is_us_equity_regular_session_window
from .kis_paper_spy_fill_cycle import (
    _atomic_json,
    _digest,
    _failure_category,
    _read_json,
    _RecoveryRequired,
    _spy_book,
    _validate_paths,
    conflicts_with_active_spy_fill_cycle,
)
from .kis_readonly import (
    KisPaperConfig,
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)
from .paper_decision_bridge import (
    KisPaperLimitProof,
    PaperDecisionExecutionBinding,
    prepare_kis_paper_decision,
)

BUDGET_FILE = ".spy_strategy_budget.json"
BUDGET_FRACTION = Decimal("0.10")
_RUN_ID = re.compile(r"bs-[0-9a-f]{64}")
_SHA = re.compile(r"sha256:[0-9a-f]{64}")
_ORDER_LIFETIME = timedelta(minutes=5)
_FAILURE_DIAGNOSTIC_CATEGORIES = {
    "stage": frozenset(
        {
            "paths", "config", "ownership", "new_input", "controls", "account",
            "quote", "prepare", "persist", "reconcile", "order",
        }
    ),
    "category": frozenset(
        {
            "canary_error", "readonly_error", "quote_error", "io_error",
            "decimal_error", "validation_error", "recovery_required",
        }
    ),
}
_FAILURE_CODES = frozenset(
    {
        "config_missing", "config_account_invalid", "config_product_invalid",
        "paper_host_required", "auth_rejected", "auth_response_invalid",
        "access_token_invalid", "transport_failure", "redirect_rejected",
        "request_not_allowlisted", "response_invalid", "balance_rejected",
        "balance_response_incomplete", "balance_response_duplicate",
        "balance_pagination_incomplete", "orderable_funds_rejected",
        "orderable_funds_response_incomplete", "open_orders_rejected",
        "open_orders_response_incomplete", "open_orders_response_duplicate",
        "open_orders_pagination_incomplete", "ccnl_response_incomplete",
        "ccnl_pagination_incomplete", "quote_rejected", "quote_response_incomplete",
        "quote_response_blank", "quote_timestamp_invalid", "quote_timestamp_stale",
        "quote_tick_invalid", "quote_scale_mismatch", "quote_limit_invalid",
        "quote_bid_ask_invalid", "state_invalid", "state_intent_mismatch",
        "state_transition_invalid", "state_submission_time_invalid",
        "recovery_state_missing", "recovery_run_id_mismatch",
        "recovery_phase_not_reconcilable", "recovery_evidence_collision",
    }
)
_DAILY_RECEIPT_DIAGNOSTIC_CATEGORIES = {
    "failed_predicate": frozenset(
        {"input_status", "decision_class", "future_decision", "expired_validity"}
    ),
    "input_status": frozenset(
        {
            "ready",
            "missing",
            "stale",
            "incomplete",
            "duplicate",
            "non_contiguous",
            "misaligned",
            "future",
            "unqualified",
        }
    ),
    "decision_class": frozenset({"enter", "exit", "abstain"}),
    "reason_class": frozenset(
        {
            "eligible_enter",
            "eligible_exit",
            "input_unavailable",
            "model_abstain",
            "non_entry_proposal",
        }
    ),
}


@dataclass(frozen=True)
class KisPaperBudgetOutcome:
    status: str
    reason_code: str
    observed_at: datetime
    daily_receipt_diagnostic: Mapping[str, str] | None = None
    failure_diagnostic: Mapping[str, str] | None = None

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": "kis_paper_spy_budget_strategy",
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": self.observed_at.isoformat(),
            "paper_only": True,
            "allocation_fraction": "0.10",
            "decision_use": "existing_baseline_direction_only",
            "basis": "provisional_usd_orderable_funds_not_settled_cash",
            "net_pnl": "not_observed",
        }
        if (
            self.status == "no_intent"
            and self.reason_code == "daily_receipt_not_eligible"
            and self.daily_receipt_diagnostic is not None
        ):
            diagnostic = {}
            for key, categories in _DAILY_RECEIPT_DIAGNOSTIC_CATEGORIES.items():
                value = self.daily_receipt_diagnostic.get(key)
                diagnostic[key] = (
                    value if isinstance(value, str) and value in categories else "unrecognized"
                )
            payload["daily_receipt_diagnostic"] = diagnostic
        if self.failure_diagnostic is not None:
            diagnostic = {}
            for key, categories in _FAILURE_DIAGNOSTIC_CATEGORIES.items():
                value = self.failure_diagnostic.get(key)
                diagnostic[key] = (
                    value if isinstance(value, str) and value in categories else "unrecognized"
                )
            code = self.failure_diagnostic.get("code")
            if isinstance(code, str) and code in _FAILURE_CODES:
                diagnostic["code"] = code
            payload["failure_diagnostic"] = diagnostic
        return payload


def _failure_diagnostic(stage: str, error: Exception) -> dict[str, str]:
    diagnostic = {
        "stage": stage,
        "category": (
            "recovery_required"
            if isinstance(error, _RecoveryRequired)
            else _failure_category(error).value
        ),
    }
    # Only local typed codes are eligible; never inspect messages, causes or broker diagnostics.
    if isinstance(error, (KisPaperCanaryError, KisPaperReadOnlyError, KisPaperQuoteError)):
        code = error.code
        if isinstance(code, str) and code in _FAILURE_CODES:
            diagnostic["code"] = code
    return diagnostic


@dataclass(frozen=True, repr=False)
class BudgetProjection:
    quantity: Decimal
    entry_cost: Decimal
    reserved_buys: Decimal


def _load_binding(root: Path, account_ref: str | None = None):
    path = root / BUDGET_FILE
    if path.is_symlink():
        raise _RecoveryRequired("budget_binding_invalid")
    binding = _read_json(path)
    if binding is None:
        if any(root.glob("bs-*.json")):
            raise _RecoveryRequired("budget_binding_missing")
        return None
    if (
        set(binding) != {"version", "account_ref", "basis_usd", "allocated_usd", "at", "orders"}
        or binding["version"] != 1
        or not isinstance(binding["account_ref"], str)
        or re.fullmatch(r"[0-9a-f]{64}", binding["account_ref"]) is None
        or (account_ref is not None and binding["account_ref"] != account_ref)
    ):
        raise _RecoveryRequired("budget_binding_invalid")
    basis, allocated = _money(binding["basis_usd"]), _money(binding["allocated_usd"])
    require_utc(datetime.fromisoformat(binding["at"]))
    if (
        basis <= 0
        or allocated != basis * BUDGET_FRACTION
        or not isinstance(binding["orders"], list)
    ):
        raise _RecoveryRequired("budget_binding_invalid")
    seen = set()
    for record in binding["orders"]:
        if (
            not isinstance(record, dict)
            or set(record) != {"run_id", "intent_ref", "closed"}
            or not isinstance(record["run_id"], str)
            or _RUN_ID.fullmatch(record["run_id"]) is None
            or not isinstance(record["intent_ref"], str)
            or _SHA.fullmatch(record["intent_ref"]) is None
            or type(record["closed"]) is not bool
            or record["run_id"] in seen
        ):
            raise _RecoveryRequired("budget_binding_invalid")
        seen.add(record["run_id"])
    if any(not row["closed"] for row in binding["orders"][:-1]):
        raise _RecoveryRequired("budget_binding_invalid")
    return binding


def _money(value):
    if not isinstance(value, str):
        raise _RecoveryRequired("budget_binding_invalid")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise _RecoveryRequired("budget_binding_invalid")
    return number


def _state(root, record):
    state = KisPaperCanaryStateStore(root / (record["run_id"] + ".json")).read()
    if (
        state is None
        or state.intent.fingerprint != record["intent_ref"]
        or state.intent.run_id != record["run_id"]
        or (state.intent.symbol, state.intent.exchange) != ("SPY", "AMEX")
    ):
        raise _RecoveryRequired("budget_intent_mismatch")
    return state


def project_budget(root: Path, binding) -> BudgetProjection:
    """Recompute entry cost and reservations; no snapshot is added twice."""
    quantity = cost = reserved = Decimal(0)
    for record in binding["orders"]:
        state = _state(root, record)
        fill = state.cumulative_fill
        filled = Decimal(0) if fill is None else fill.quantity
        amount = Decimal(0) if fill is None else fill.gross_amount
        if record["closed"] and not (
            state.phase == "rejected"
            or (
                state.phase == "intent_recorded"
                and state.submission_started_at is None
                and state.updated_at >= state.intent.valid_until
            )
            or (
                fill is not None
                and (filled == state.intent.quantity or fill.remaining_quantity == 0)
            )
        ):
            raise _RecoveryRequired("closed_order_evidence_missing")
        if state.intent.side == "buy":
            if amount > filled * state.intent.limit_price + Decimal("0.01"):
                raise _RecoveryRequired("fill_limit_contradiction")
            quantity += filled
            cost += amount
            if not record["closed"]:
                reserved += (state.intent.quantity - filled) * state.intent.limit_price
        else:
            if filled > quantity:
                raise _RecoveryRequired("unowned_sell_fill")
            # The entire position is one strategy lot; partial exits release
            # its actual entry cost, never sale proceeds or the old buy limit.
            if filled:
                cost = Decimal(0) if filled == quantity else cost * (quantity - filled) / quantity
                quantity -= filled
    if cost + reserved > _money(binding["allocated_usd"]):
        raise _RecoveryRequired("budget_exceeded")
    return BudgetProjection(quantity, cost, reserved)


def conflicts_with_budget_strategy(root: Path, run_id: str, symbol: str) -> bool:
    """Shared new-intent conflict only; recovery/cancellation bypass this check."""
    if symbol != "SPY":
        return False
    try:
        binding = _load_binding(root)
        if binding is None:
            return _RUN_ID.fullmatch(run_id) is not None
        projection = project_budget(root, binding)
        pending = [row for row in binding["orders"] if not row["closed"]]
        if pending and pending[0]["run_id"] == run_id:
            return False
        # An orphan/closed budget intent cannot be dispatched outside its owner.
        return bool(pending or projection.quantity or _RUN_ID.fullmatch(run_id))
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        DecimalException,
        KisPaperCanaryError,
        _RecoveryRequired,
    ):
        return True


def run_kis_paper_budget_strategy(
    *,
    receipt_loader: Callable[[datetime], ResearchDecisionReceipt],
    environment: Mapping[str, str],
    state_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    transport=None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    session_id: str | None = None,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
) -> KisPaperBudgetOutcome:
    def at():
        return _session_now(now=now, clock=clock)

    observed_at = at()
    session_id = session_id or f"budget-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", session_id) is None:
        raise ValueError("budget session identity invalid")
    if not execute:
        return KisPaperBudgetOutcome("preview", "preview", observed_at)
    paths_valid = False
    failure_stage = "config"

    def result(status, reason, *, daily_receipt_diagnostic=None, failure_diagnostic=None):
        nonlocal failure_stage
        failure_stage = "persist"
        outcome = KisPaperBudgetOutcome(
            status, reason, at(), daily_receipt_diagnostic, failure_diagnostic
        )
        destination = (
            artifact_root / "execution" / "kis-paper-spy-budget" / session_id / "outcome.json"
        )
        _atomic_json(destination, outcome.safe_payload())
        return outcome

    try:
        if environment.get("THERICHER_MODE", "off").strip().lower() == "kis_live":
            return KisPaperBudgetOutcome("recovery_required", "live_mode_unavailable", observed_at)
        failure_stage = "paths"
        root = state_root.resolve()
        _validate_paths(
            root,
            repository_root,
            artifact_root,
            runtime_projection_path,
            paper_account_snapshot_path,
            emergency_state_path,
            execution_control_path,
        )
        paths_valid = True
        if (
            not is_us_equity_regular_session_window(observed_at)
            and not (root / BUDGET_FILE).exists()
        ):
            return result("not_due", "outside_regular_session")
        failure_stage = "config"
        config = load_kis_paper_config_from_environment(environment)
        if client is not None:
            supplied = client._config
            if (
                KisPaperConfig(
                    supplied.app_key,
                    supplied.app_secret,
                    supplied.account_number,
                    supplied.account_product_code,
                    supplied.base_url,
                )
                != config
            ):
                raise _RecoveryRequired("account_binding_mismatch")
        client = client or KisPaperCanaryClient(
            config=config, transport=transport or UrllibKisPaperCanaryTransport()
        )
        account_ref = _digest([config.base_url, config.account_number, config.account_product_code])

        def run_intent(state, *, permitted=None):
            nonlocal failure_stage
            failure_stage = "order" if state.phase == "intent_recorded" else "reconcile"
            intent = state.intent
            decision_type = (
                KisPaperCanaryBuyDecision if intent.side == "buy" else KisPaperCanarySellDecision
            )
            return _run_kis_paper_canary(
                decision=decision_type(
                    decision_id=intent.decision_id,
                    symbol=intent.symbol,
                    exchange=intent.exchange,
                    quantity=intent.quantity,
                    limit_price=intent.limit_price,
                    decision_as_of=intent.created_at,
                    valid_until=intent.valid_until,
                ),
                run_id=intent.run_id,
                environment=environment,
                state_path=root / (intent.run_id + ".json"),
                runtime_projection_path=runtime_projection_path,
                paper_account_snapshot_path=paper_account_snapshot_path,
                emergency_state_path=emergency_state_path,
                artifact_root=artifact_root,
                repository_root=repository_root,
                execute=True,
                cancel_after_submit=False,
                client=client,
                now=now,
                clock=clock,
                submit_permitted=permitted,
                execution_control_path=execution_control_path,
                require_existing_state=True,
                price_contract_ref=intent.price_contract_ref,
            )

        def fresh_book():
            nonlocal failure_stage
            previous_stage = failure_stage
            failure_stage = "account"
            snapshot = client.snapshot()
            quantity, opens = _spy_book(snapshot, at(), config)
            if snapshot.cash.currency != "USD" or snapshot.orderable_funds.currency != "USD":
                raise _RecoveryRequired("funds_currency_mismatch")
            funds = min(snapshot.cash.available_cash, snapshot.orderable_funds.orderable_funds)
            failure_stage = previous_stage
            return quantity, opens, funds

        def permitted(binding, state):
            def check(submit_at):
                nonlocal failure_stage
                previous_stage = failure_stage
                if not is_us_equity_regular_session_window(submit_at):
                    return False
                failure_stage = "ownership"
                owned = project_budget(root, binding)
                quantity, opens, funds = fresh_book()
                if opens or quantity != owned.quantity:
                    raise _RecoveryRequired("pre_submit_ownership_changed")
                if state.intent.side == "buy":
                    if state.intent.quantity * state.intent.limit_price > funds:
                        raise _RecoveryRequired("buying_power_changed")
                elif state.intent.quantity > owned.quantity:
                    raise _RecoveryRequired("unowned_sell")
                failure_stage = previous_stage
                return True

            return check

        def finish_order(binding, record, reconciliation):
            nonlocal failure_stage
            failure_stage = "reconcile"
            state = _state(root, record)
            store = KisPaperCanaryStateStore(root / (state.intent.run_id + ".json"))
            if state.phase == "rejected" or (
                state.phase == "intent_recorded"
                and state.submission_started_at is None
                and at() >= state.intent.valid_until
            ):
                record["closed"] = True
                failure_stage = "persist"
                _atomic_json(root / BUDGET_FILE, binding)
                return result("no_intent", "order_not_submitted_or_rejected")
            order_at = state.submission_started_at or state.submitted_at
            if (
                order_at is not None
                and at() - order_at >= _ORDER_LIFETIME
                and reconciliation.matching_open_order
                and state.broker_order_id is not None
                and is_us_equity_regular_session_window(at())
            ):
                failure_stage = "persist"
                if state.phase != "submitted":
                    state = store.transition(
                        state.intent,
                        expected=frozenset({state.phase}),
                        phase="submitted",
                        reason_code="reconciliation_unresolved",
                        now=at(),
                    )
                failure_stage = "order"
                state, reconciliation = _cancel_submitted_canary(
                    client=client,
                    state_store=store,
                    state=state,
                    reconciliation=reconciliation,
                    observed_at=at(),
                )
                failure_stage = "persist"
                _record_reconciliation_fill(store, state, reconciliation, observed_at=at())
                return result("pending", "own_order_cancellation_observed")
            failure_stage = "ownership"
            projection = project_budget(root, binding)
            quantity, opens, _funds = fresh_book()
            failure_stage = "reconcile"
            fill = state.current_fill
            if fill is None:
                return result("pending", "exact_fill_unavailable")
            if not timedelta(0) <= at() - fill.observed_at <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE:
                return result("pending", "exact_fill_not_current")
            if quantity != projection.quantity:
                return result("pending", "position_fill_not_aligned")
            if opens:
                return result("pending", "order_still_open")
            if fill.quantity != state.intent.quantity and fill.remaining_quantity != 0:
                return result("pending", "remaining_quantity_unresolved")
            record["closed"] = True
            failure_stage = "persist"
            _atomic_json(root / BUDGET_FILE, binding)
            return result("order_complete", "exact_order_and_position_reconciled")

        failure_stage = "ownership"
        with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
            with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
                binding = _load_binding(root, account_ref)
                if (
                    binding is not None
                    and binding["orders"]
                    and not binding["orders"][-1]["closed"]
                ):
                    record = binding["orders"][-1]
                    state = _state(root, record)
                    outcome = run_intent(state, permitted=permitted(binding, state))
                    recovered = finish_order(binding, record, outcome.reconciliation)
                    if not record["closed"] or state.phase == "intent_recorded":
                        return recovered
                if not is_us_equity_regular_session_window(at()):
                    return result("not_due", "outside_regular_session")
                # A stale/absent new signal cannot bypass recovery of a previous order.
                failure_stage = "new_input"
                try:
                    receipt = receipt_loader(at())
                except (OSError, ValueError) as error:
                    return result(
                        "no_intent", "daily_input_unavailable",
                        failure_diagnostic=_failure_diagnostic(failure_stage, error),
                    )
                receipt_checked_at = None
                if (
                    receipt.input_status != "ready"
                    or receipt.decision_class not in {"enter", "exit"}
                    or not receipt.decided_at <= (receipt_checked_at := at()) < receipt.valid_until
                ):
                    # Report the first failed predicate using its original clock sample.
                    return result(
                        "no_intent",
                        "daily_receipt_not_eligible",
                        daily_receipt_diagnostic={
                            "failed_predicate": (
                                "input_status"
                                if receipt.input_status != "ready"
                                else "decision_class"
                                if receipt.decision_class not in {"enter", "exit"}
                                else "future_decision"
                                if receipt_checked_at < receipt.decided_at
                                else "expired_validity"
                            ),
                            "input_status": receipt.input_status,
                            "decision_class": receipt.decision_class,
                            "reason_class": receipt.reason_class,
                        },
                    )
                side = "buy" if receipt.decision_class == "enter" else "sell"
                failure_stage = "controls"
                controls = PaperExecutionControlStore(execution_control_path).read()
                if controls.pause_buys if side == "buy" else controls.pause_sells:
                    return result("no_intent", f"pause_{side}s_active")
                quantity, opens, funds = fresh_book()
                failure_stage = "ownership"
                projection = (
                    BudgetProjection(Decimal(0), Decimal(0), Decimal(0))
                    if binding is None
                    else project_budget(root, binding)
                )
                if quantity != projection.quantity or opens:
                    return result("no_intent", "existing_inventory_or_order_conflict")
                if (side == "buy" and quantity > 0) or (side == "sell" and quantity == 0):
                    return result("no_intent", "target_already_satisfied")
                run_id = "bs-" + hashlib.sha256(receipt.decision_id.encode()).hexdigest()
                if conflicts_with_active_spy_fill_cycle(root, run_id, "SPY"):
                    return result("no_intent", "owned_intent_conflict")
                if binding is not None and any(
                    row["run_id"] == run_id for row in binding["orders"]
                ):
                    return result("no_intent", "decision_already_processed")
                if binding is None:
                    if funds <= 0:
                        return result("no_intent", "buying_power_unavailable")
                    binding = {
                        "version": 1,
                        "account_ref": account_ref,
                        "basis_usd": str(funds),
                        "allocated_usd": str(funds * BUDGET_FRACTION),
                        "at": at().isoformat(),
                        "orders": [],
                    }
                    failure_stage = "persist"
                    _atomic_json(root / BUDGET_FILE, binding)
                failure_stage = "quote"
                quote = client.fetch_spy_limit_input(observed_at=at())
                price = derive_kis_paper_marketable_limit(quote, side=side, observed_at=at())
                failure_stage = "prepare"
                room = (
                    _money(binding["allocated_usd"])
                    - projection.entry_cost
                    - projection.reserved_buys
                )
                shares = (
                    (min(room, funds) / price).to_integral_value(rounding=ROUND_FLOOR)
                    if side == "buy"
                    else projection.quantity
                )
                if shares <= 0:
                    return result("no_intent", "budget_below_one_share")
                proof_ref = "sha256:" + _digest(
                    [receipt.decision_id, side, str(price), quote.quoted_at.isoformat()]
                )
                prepared = prepare_kis_paper_decision(
                    receipt,
                    binding=PaperDecisionExecutionBinding(
                        proposal_ref=receipt.proposal_ref,
                        symbol="SPY",
                        exchange="AMEX",
                        quantity=shares,
                    ),
                    limit_proof=KisPaperLimitProof(
                        receipt_id=receipt.decision_id,
                        price_contract_ref=proof_ref,
                        symbol="SPY",
                        exchange="AMEX",
                        limit_price=price,
                        observed_at=quote.quoted_at,
                        valid_until=quote.quoted_at + KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
                        final_limit_tick_valid=True,
                    ),
                    as_of=at(),
                )
                if prepared.status != "ready":
                    return result("no_intent", "receipt_binding_mismatch")
                # Retain the safe immutable decision, not its underlying price rows.
                failure_stage = "persist"
                decision_path = (
                    artifact_root
                    / "execution"
                    / "kis-paper-spy-budget"
                    / "decisions"
                    / (receipt.decision_id.removeprefix("decision:sha256:") + ".json")
                )
                if decision_path.exists():
                    if json.loads(decision_path.read_text()) != receipt.to_payload():
                        raise _RecoveryRequired("decision_evidence_mismatch")
                else:
                    _atomic_json(decision_path, receipt.to_payload())
                store = KisPaperCanaryStateStore(root / (run_id + ".json"))
                failure_stage = "ownership"
                state = store.read()
                if state is not None:
                    # A crash may leave a never-submitted intent before its binding.
                    # Never adopt an orphan with a possible broker side effect.
                    if state.phase != "intent_recorded" or state.submission_started_at is not None:
                        raise _RecoveryRequired("orphan_intent_requires_reconciliation")
                    if state.intent.decision_id != prepared.kis_paper_decision.decision_id:
                        raise _RecoveryRequired("budget_intent_mismatch")
                    if (state.intent.symbol, state.intent.exchange, state.intent.side) != (
                        "SPY",
                        "AMEX",
                        side,
                    ):
                        raise _RecoveryRequired("budget_intent_mismatch")
                    if state.intent.quantity * state.intent.limit_price > min(room, funds):
                        raise _RecoveryRequired("orphan_budget_conflict")
                else:
                    failure_stage = "persist"
                    state = store.record_intent(
                        KisPaperCanaryIntent.from_decision(
                            prepared.kis_paper_decision,
                            run_id=run_id,
                            price_contract_ref=prepared.price_contract_ref,
                        ),
                        cancel_after_submit=False,
                        now=at(),
                    )
                record = {"run_id": run_id, "intent_ref": state.intent.fingerprint, "closed": False}
                binding["orders"].append(record)
                failure_stage = "persist"
                _atomic_json(root / BUDGET_FILE, binding)
                failure_stage = "ownership"
                project_budget(root, binding)
                outcome = run_intent(state, permitted=permitted(binding, state))
                return finish_order(binding, record, outcome.reconciliation)
    except _RecoveryRequired as error:
        # These internal exception codes are fixed literals, never broker text.
        failure = KisPaperBudgetOutcome(
            "recovery_required", str(error), at(),
            failure_diagnostic=_failure_diagnostic(failure_stage, error),
        )
    except (
        KisPaperCanaryError,
        KisPaperReadOnlyError,
        KisPaperQuoteError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        DecimalException,
    ) as error:
        failure = KisPaperBudgetOutcome(
            "recovery_required", "evidence_unavailable", at(),
            failure_diagnostic=_failure_diagnostic(failure_stage, error),
        )
    if paths_valid:
        try:
            return result(
                failure.status, failure.reason_code,
                failure_diagnostic=failure.failure_diagnostic,
            )
        except (OSError, ValueError):
            pass
    return failure
