"""One bounded visit to a deterministic Paper SPY buy-one/sell-one baseline.

This is execution evidence, not a profit strategy. Canary state remains the
only order/fill ledger; the private binding owns identity, not an execution phase.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException
from pathlib import Path

from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN
from thericher_v2.research.kis_paper_canary_intent import (
    KisPaperCanaryBuyDecision,
    KisPaperCanarySellDecision,
)

from .emergency import (
    DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    EmergencyStore,
    PaperExecutionControlStore,
)
from .kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryStateStore,
    UrllibKisPaperCanaryTransport,
    _cancel_submitted_canary,
    _is_permitted_artifact_root,
    _record_reconciliation_fill,
    _redacted_open_order_reference,
    _run_kis_paper_canary,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_quote import (
    KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
    KisPaperQuoteError,
    derive_kis_paper_marketable_limit,
)
from .kis_paper_session import (
    DEFAULT_KIS_PAPER_SESSION_VALID_SECONDS,
    _is_safe_session_id,
    _session_now,
    is_us_equity_regular_session_window,
)
from .kis_readonly import (
    KisHttpTransport,
    KisPaperConfig,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    load_kis_paper_config_from_environment,
)


@dataclass(frozen=True, repr=False)
class KisPaperSpyFillCycleOutcome:
    status: str
    reason_code: str
    observed_at: datetime
    entry_gross_cashflow: Decimal | None = None
    exit_gross_cashflow: Decimal | None = None

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": self.observed_at.isoformat(),
            "paper_only": True,
            "gross_cashflow": "available"
            if self.entry_gross_cashflow is not None and self.exit_gross_cashflow is not None
            else "not_observed",
            "fees": "not_observed",
            "settled_cash": "not_observed",
            "net_pnl": "not_observed",
        }


class _RecoveryRequired(RuntimeError):
    pass


def run_kis_paper_spy_fill_cycle(
    *,
    cycle_id: str,
    environment: Mapping[str, str],
    state_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
) -> KisPaperSpyFillCycleOutcome:
    """Visit one date-independent cycle; only ``pending`` requests another visit.

    ``state_root`` must be the existing shared canary root, never a per-cycle
    directory. Preview and closed-session calls perform no I/O or credential reads.
    Gross per-leg flows are private outcome attributes, not settled cash or PnL.
    """

    def at():
        return _session_now(now=now, clock=clock)

    observed_at = at()
    if not _is_safe_session_id(cycle_id):
        raise ValueError("cycle_id is invalid")
    if not execute:
        return KisPaperSpyFillCycleOutcome("preview", "preview", observed_at)
    if not is_us_equity_regular_session_window(observed_at):
        return KisPaperSpyFillCycleOutcome("not_due", "outside_regular_session", observed_at)
    try:
        mode = environment.get("THERICHER_MODE", "off")
        if isinstance(mode, str) and mode.strip().lower() == "kis_live":
            raise _RecoveryRequired("live_mode_unavailable")
        # Validate even injected clients before locks, private reads, or broker I/O.
        config = load_kis_paper_config_from_environment(environment)
        if client is not None:
            injected = client._config
            checked = KisPaperConfig(
                injected.app_key,
                injected.app_secret,
                injected.account_number,
                injected.account_product_code,
                injected.base_url,
            )
            if checked != config:
                raise _RecoveryRequired("account_binding_mismatch")
        client = client or KisPaperCanaryClient(
            config=config, transport=transport or UrllibKisPaperCanaryTransport()
        )
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
        binding = _binding(cycle_id, config)
        binding_path = root / ".spy_fill_cycles" / (_digest(cycle_id) + ".json")
        active_path = root / ".spy_fill_active.json"
        stores = {
            side: KisPaperCanaryStateStore(root / (binding[side + "_run_id"] + ".json"))
            for side in ("buy", "sell")
        }
        states = {}

        def result(status, reason):
            return KisPaperSpyFillCycleOutcome(
                status,
                reason,
                at(),
                *[
                    None if states.get(side) is None else states[side].gross_cashflow_contribution
                    for side in ("buy", "sell")
                ],
            )

        def run_leg(side, *, permitted=None):
            state = states[side]
            intent = state.intent
            decision_type = (
                KisPaperCanaryBuyDecision if side == "buy" else KisPaperCanarySellDecision
            )
            outcome = _run_kis_paper_canary(
                decision=decision_type(
                    decision_id=intent.decision_id,
                    symbol="SPY",
                    exchange="AMEX",
                    quantity=Decimal(1),
                    limit_price=intent.limit_price,
                    decision_as_of=intent.created_at,
                    valid_until=intent.valid_until,
                ),
                run_id=intent.run_id,
                environment=environment,
                state_path=stores[side].path,
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
            states[side] = stores[side].read()
            return outcome.reconciliation

        # Lock order and roots are exactly those used by the existing session/canary.
        with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
            with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
                active = _read_json(active_path)
                active_identity = {
                    "cycle_ref": _digest(cycle_id),
                    "account_ref": binding["account_ref"],
                }
                other_active = active is not None and active != active_identity
                saved = _read_json(binding_path)
                if other_active and saved is None:
                    raise _RecoveryRequired("another_cycle_unresolved")
                if active is not None and saved is None:
                    raise _RecoveryRequired("cycle_binding_missing")
                if saved is not None:
                    if (
                        not isinstance(saved, dict)
                        or set(saved) != set(binding)
                        or any(
                            saved[key] != value
                            for key, value in binding.items()
                            if key not in {"buy_intent_ref", "sell_intent_ref"}
                        )
                    ):
                        raise _RecoveryRequired("cycle_binding_mismatch")
                    binding = saved
                for side, store in stores.items():
                    states[side] = store.read()
                    _validate_leg(states[side], binding, side, saved is not None)
                if states["sell"] is not None and states["buy"] is None:
                    raise _RecoveryRequired("leg_binding_mismatch")
                if other_active and not all(_filled(state) for state in states.values()):
                    raise _RecoveryRequired("another_cycle_unresolved")

                reconciliations = {}
                for side, state in states.items():
                    if state is not None:
                        if state.phase == "intent_recorded":
                            reconciliations[side] = client.reconcile(state, now=at())
                        else:
                            reconciliations[side] = run_leg(side)
                # Known-order containment precedes fill/position contradiction checks.
                emergency = EmergencyStore(emergency_state_path).read()
                for side, rec in reconciliations.items():
                    state = states[side]
                    order_at = state.submission_started_at or state.submitted_at
                    expired = order_at is not None and (
                        at() - order_at > timedelta(seconds=DEFAULT_KIS_PAPER_SESSION_VALID_SECONDS)
                        or at().astimezone(US_EQUITY_EASTERN).date()
                        != order_at.astimezone(US_EQUITY_EASTERN).date()
                    )
                    if (expired or emergency.cancel_open_orders_requested) and _own_open(
                        state, rec.snapshot
                    ):
                        if state.phase != "submitted":
                            state = stores[side].transition(
                                state.intent,
                                expected=frozenset({state.phase}),
                                phase="submitted",
                                reason_code="reconciliation_unresolved",
                                now=at(),
                            )
                        state, rec = _cancel_submitted_canary(
                            client=client,
                            state_store=stores[side],
                            state=state,
                            reconciliation=rec,
                            observed_at=at(),
                        )
                        states[side] = _record_reconciliation_fill(
                            stores[side], state, rec, observed_at=at()
                        )
                        # A cancellation/fill race is resolved on the next visit, never guessed.
                        return result("pending", "cancellation_reconciled")

                snapshot = client.snapshot()
                position, open_orders = _spy_book(snapshot, at(), config)
                entry, exit_state = states["buy"], states["sell"]
                if (
                    exit_state is None
                    and position == 0
                    and not open_orders
                    and _entry_not_submitted(entry, at())
                ):
                    if not other_active:
                        active_path.unlink(missing_ok=True)
                    return result("no_intent", "entry_not_submitted")
                awaiting_history = False
                for state in states.values():
                    if state is not None and state.phase != "intent_recorded":
                        if _awaiting_history(state, snapshot, at(), config):
                            awaiting_history = True
                        else:
                            _require_current_fill(state, at())
                if awaiting_history:
                    return result("pending", "awaiting_fill_observation")
                if exit_state is not None and _filled(exit_state):
                    if not _filled(entry) or position != 0 or open_orders:
                        raise _RecoveryRequired("closure_contradiction")
                    if not other_active:
                        active_path.unlink(missing_ok=True)
                    return result("complete", "exact_fills_flat")
                if entry is not None and not _filled(entry) and not open_orders and position == 0:
                    if entry.phase == "cancelled" and exit_state is None:
                        active_path.unlink(missing_ok=True)
                        return result("cancelled", "entry_unfilled_flat")

                side = "sell" if _filled(entry) else "buy"
                expected_position = Decimal(1) if side == "sell" else Decimal(0)
                if position != expected_position:
                    raise _RecoveryRequired("position_contradiction")
                current = states[side]
                if open_orders:
                    if (
                        current is not None
                        and _own_open(current, snapshot)
                        and len(open_orders) == 1
                    ):
                        return result("pending", "own_order_open")
                    raise _RecoveryRequired("foreign_or_conflicting_open_order")
                if current is not None and current.phase != "intent_recorded":
                    raise _RecoveryRequired("leg_outcome_unresolved")
                if emergency.blocks_new_orders:
                    return result("no_intent", "emergency_stop_new_orders")
                if current is not None and at() >= current.intent.valid_until:
                    raise _RecoveryRequired("exit_not_submitted_expired")
                control = PaperExecutionControlStore(execution_control_path).read()
                if control.pause_buys if side == "buy" else control.pause_sells:
                    return result("no_intent", f"pause_{side}s_active")

                quote = client.fetch_spy_limit_input(observed_at=at())
                price = derive_kis_paper_marketable_limit(quote, side=side, observed_at=at())
                if saved is None:
                    _atomic_json(binding_path, binding)
                if active is None:
                    _atomic_json(
                        active_path,
                        {"cycle_ref": _digest(cycle_id), "account_ref": binding["account_ref"]},
                    )
                if current is None:
                    decision_type = (
                        KisPaperCanaryBuyDecision if side == "buy" else KisPaperCanarySellDecision
                    )
                    decision = decision_type(
                        decision_id="decision-" + binding[side + "_run_id"],
                        symbol="SPY",
                        exchange="AMEX",
                        quantity=Decimal(1),
                        limit_price=price,
                        decision_as_of=min(at(), quote.quoted_at),
                        valid_until=quote.quoted_at + KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
                    )
                    current = stores[side].record_intent(
                        KisPaperCanaryIntent.from_decision(
                            decision, run_id=binding[side + "_run_id"]
                        ),
                        cancel_after_submit=False,
                        now=at(),
                    )
                    states[side] = current
                binding[side + "_intent_ref"] = current.intent.fingerprint
                _atomic_json(binding_path, binding)

                def permitted(submit_at):
                    if not is_us_equity_regular_session_window(submit_at):
                        return False
                    fresh_price = derive_kis_paper_marketable_limit(
                        quote, side=side, observed_at=at()
                    )
                    if fresh_price != current.intent.limit_price:
                        raise _RecoveryRequired("unsubmitted_price_changed")
                    if side == "sell":
                        rec = client.reconcile(states["buy"], now=at())
                        states["buy"] = _record_reconciliation_fill(
                            stores["buy"], states["buy"], rec, observed_at=at()
                        )
                        _require_current_fill(states["buy"], at())
                        if not _filled(states["buy"]):
                            raise _RecoveryRequired("entry_fill_unavailable")
                    quantity, orders = _spy_book(client.snapshot(), at(), config)
                    if quantity != expected_position or orders:
                        raise _RecoveryRequired("pre_submit_ownership_changed")
                    return True

                rec = run_leg(side, permitted=permitted)
                current = states[side]
                if current.phase == "intent_recorded":
                    # No entry POST means no cycle-owned inventory to reserve on worker exit.
                    if side == "buy" and states["sell"] is None:
                        active_path.unlink(missing_ok=True)
                    return result("no_intent", "submission_not_started")
                if _awaiting_history(current, rec.snapshot, at(), config):
                    return result("pending", "awaiting_fill_observation")
                _require_current_fill(current, at())
                if side == "sell" and _filled(current):
                    quantity, orders = _spy_book(client.snapshot(), at(), config)
                    _require_current_fill(states["buy"], at())
                    if quantity != 0 or orders:
                        raise _RecoveryRequired("closure_contradiction")
                    active_path.unlink(missing_ok=True)
                    return result("complete", "exact_fills_flat")
                if _filled(current) or _own_open(current, rec.snapshot):
                    return result("pending", "next_leg" if _filled(current) else "own_order_open")
                raise _RecoveryRequired("leg_outcome_unresolved")
    except _RecoveryRequired as error:
        return KisPaperSpyFillCycleOutcome("recovery_required", str(error), at())
    except (
        KisPaperCanaryError,
        KisPaperReadOnlyError,
        KisPaperQuoteError,
        OSError,
        ValueError,
        TypeError,
        DecimalException,
    ):
        return KisPaperSpyFillCycleOutcome("recovery_required", "evidence_unavailable", at())


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def conflicts_with_active_spy_fill_cycle(state_root: Path, run_id: str, symbol: str) -> bool:
    """Check an exact SPY new-intent conflict; caller holds the shared canary lock.

    Existing reconciliation/cancellation must not call this predicate. No binding
    means no cycle conflict; a malformed/unreadable binding affects only SPY.
    """
    if symbol != "SPY":
        return False
    try:
        active = _read_json(state_root / ".spy_fill_active.json")
        if active is None:
            return False
        if not isinstance(active, dict) or set(active) != {"cycle_ref", "account_ref"}:
            return True
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in active.values()
        ):
            return True
        return run_id not in {f"sf-{active['cycle_ref']}-b", f"sf-{active['cycle_ref']}-s"}
    except (OSError, ValueError, TypeError):
        return True


def _binding(cycle_id, config) -> dict:
    digest = _digest(cycle_id)
    return {
        "kind": "kis_paper_spy_fill_cycle_v1",
        "cycle_id": cycle_id,
        "account_ref": _digest(
            ["kis_paper", config.base_url, config.account_number, config.account_product_code]
        ),
        "buy_run_id": f"sf-{digest}-b",
        "sell_run_id": f"sf-{digest}-s",
        "initial_flat": True,
        "buy_intent_ref": None,
        "sell_intent_ref": None,
    }


def _validate_leg(state, binding, side, bound):
    ref = binding[side + "_intent_ref"]
    if state is None:
        if ref is not None:
            raise _RecoveryRequired("leg_state_missing")
        return
    intent = state.intent
    if not bound or (
        intent.run_id != binding[side + "_run_id"]
        or intent.client_order_id != "canary-" + intent.run_id
        or intent.decision_id != "decision-" + intent.run_id
        or (intent.symbol, intent.exchange, intent.side, intent.quantity)
        != ("SPY", "AMEX", side, 1)
        or state.cancel_after_submit
        or (
            state.phase == "intent_recorded"
            and any(
                value is not None
                for value in (
                    state.broker_order_id,
                    state.submission_started_at,
                    state.submitted_at,
                    state.cumulative_fill,
                )
            )
        )
        or (ref is not None and ref != intent.fingerprint)
        or (
            ref is None
            and (state.phase != "intent_recorded" or state.submission_started_at is not None)
        )
    ):
        raise _RecoveryRequired("leg_binding_mismatch")


def _require_current_fill(state, now):
    fill = state.current_fill
    if (
        fill is None
        or not timedelta(0) <= now - fill.observed_at <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
    ):
        raise _RecoveryRequired("current_fill_unavailable")


def _entry_not_submitted(state, now):
    if state is None or any(
        value is not None
        for value in (state.broker_order_id, state.submitted_at, state.cumulative_fill)
    ):
        return False
    if state.phase == "intent_recorded":
        return state.submission_started_at is None and now >= state.intent.valid_until
    return state.phase == "rejected" and state.submit_response_category == "provider_rejected"


def _filled(state):
    return state is not None and state.current_fill is not None and state.current_fill.quantity == 1


def _awaiting_history(state, snapshot, now, config):
    if state.fill_observation_status not in {"not_observed", "absent", "unavailable"}:
        return False
    if (
        snapshot is None
        or state.broker_order_id is None
        or (state.submission_started_at or state.submitted_at) is None
    ):
        return False
    position, orders = _spy_book(snapshot, now, config)
    if position not in {0, 1}:
        raise _RecoveryRequired("position_contradiction")
    if orders and (len(orders) != 1 or not _own_open(state, snapshot)):
        raise _RecoveryRequired("foreign_or_conflicting_open_order")
    # Absence after open-order removal is not a fill or a zero-fill observation.
    return True


def _spy_book(snapshot: KisPaperReadOnlySnapshot, now, config):
    times = [
        snapshot.captured_at,
        snapshot.identity.captured_at,
        snapshot.open_orders.captured_at,
        snapshot.cash.captured_at,
        snapshot.orderable_funds.captured_at,
    ]
    times.extend(item.captured_at for item in (*snapshot.positions, *snapshot.open_orders.orders))
    if (
        snapshot.identity.masked_account != config.masked_account_identity
        or not snapshot.open_orders.complete
        or any(
            not timedelta(seconds=-5) <= now - value <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
            for value in times
        )
    ):
        raise _RecoveryRequired("snapshot_unavailable")
    positions = [item for item in snapshot.positions if item.symbol == "SPY"]
    if len(positions) > 1 or any(
        item.exchange != "AMEX" or item.currency != "USD" for item in positions
    ):
        raise _RecoveryRequired("position_contradiction")
    return sum((item.quantity for item in positions), Decimal(0)), [
        item for item in snapshot.open_orders.orders if item.symbol == "SPY"
    ]


def _own_open(state, snapshot):
    if snapshot is None or state.broker_order_id is None:
        return False
    return any(
        order.order_reference == _redacted_open_order_reference(state.broker_order_id)
        and (order.symbol, order.exchange, order.currency, order.side, order.requested_quantity)
        == ("SPY", "AMEX", "USD", state.intent.side, 1)
        and order.limit_price == state.intent.limit_price
        for order in snapshot.open_orders.orders
    )


def _validate_paths(root, repository_root, artifact_root, *public_paths):
    repo = repository_root.resolve()
    docker_private = root == repo / "private" / "canary" and (repo / "private").is_mount()
    if (
        root.is_relative_to(repo)
        and root != repo / "runtime" / "private" / "kis_paper_canary"
        and not docker_private
    ):
        raise _RecoveryRequired("private_root_invalid")
    if not _is_permitted_artifact_root(artifact_root.resolve(), repo):
        raise _RecoveryRequired("artifact_root_invalid")
    if any(path.resolve().is_relative_to(root) for path in public_paths):
        raise _RecoveryRequired("private_root_invalid")
    if root.is_relative_to(artifact_root.resolve()) or artifact_root.resolve().is_relative_to(root):
        raise _RecoveryRequired("private_root_invalid")


def _read_json(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("cycle binding must be an object")
        return payload
    except FileNotFoundError:
        return None


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".binding-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
