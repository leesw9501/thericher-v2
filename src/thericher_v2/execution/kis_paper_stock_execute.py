"""Exact, persisted stock orders through the existing virtual Paper lifecycle.

No credentials, strategy selection, new budget, replacement identity or CLI.
The caller supplies independently retained plan pins. Other owners keep their
worst-case reservations; their local recovery does not pause this stock owner.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, DecimalException
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import require_utc

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from .kis_paper_portfolio_execute import _fresh, _funds, _unlinked
from .kis_paper_portfolio_plan import _replay_scope, _states
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_readonly import KisPaperConfig, KisPaperReadOnlySnapshot


def _check(condition, reason):
    if not condition:
        raise _RecoveryRequired(reason)


@dataclass(frozen=True, repr=False, kw_only=True)
class KisPaperStockExecutionBinding:
    state_root: Path
    instrument: KisPaperStockInstrument
    account_ref: str
    basis_ref: str
    owner_refs: tuple[tuple[str, str], ...]
    binding_ref: str
    request_id: str
    parent_binding_ref: str
    input_ref: str
    plan_ref: str
    run_id: str
    intent_ref: str
    side: str = "buy"

    def __post_init__(self):
        _check(type(self.side) is str and self.side in {"buy", "sell"}, "stock_side_invalid")
        _check(
            isinstance(self.state_root, Path) and self.state_root.is_absolute(),
            "stock_root_pin_invalid",
        )
        _check(type(self.instrument) is KisPaperStockInstrument, "stock_instrument_invalid")
        replace(self.instrument)
        _check(
            type(self.account_ref) is str
            and len(self.account_ref) == 64
            and all(c in "0123456789abcdef" for c in self.account_ref),
            "account_binding_mismatch",
        )
        _check(
            type(self.request_id) is str
            and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(self.request_id),
            "stock_request_invalid",
        )
        _check(
            type(self.run_id) is str and budget._STOCK_RUN_ID.fullmatch(self.run_id),
            "stock_intent_mismatch",
        )
        _check(
            type(self.owner_refs) is tuple
            and all(
                type(row) is tuple
                and len(row) == 2
                and type(row[0]) is str
                and type(row[1]) is str
                and budget._SHA.fullmatch(row[1])
                for row in self.owner_refs
            )
            and len(dict(self.owner_refs)) == len(self.owner_refs),
            "stock_owner_mismatch",
        )
        _check(
            all(
                type(ref) is str and budget._SHA.fullmatch(ref)
                for ref in (
                    self.basis_ref,
                    self.binding_ref,
                    self.parent_binding_ref,
                    self.input_ref,
                    self.plan_ref,
                    self.intent_ref,
                )
            ),
            "stock_reference_invalid",
        )


def _scope(root, proof, as_of=None):
    _check(type(proof) is KisPaperStockExecutionBinding, "stock_proof_invalid")
    replace(proof)
    _unlinked(root)
    _unlinked(proof.state_root)
    _check(root.resolve() == proof.state_root.resolve(), "stock_root_mismatch")
    binding = budget._load_binding(root, proof.account_ref)
    _check(
        binding is not None and binding["version"] == 4 and binding["legacy_spy"] is None,
        "stock_custody_mismatch",
    )
    _check("sha256:" + budget._digest(binding) == proof.binding_ref, "stock_binding_mismatch")
    _check(
        binding["basis_ref"] == proof.basis_ref
        and budget._basis(binding).fingerprint == proof.basis_ref,
        "stock_custody_mismatch",
    )
    entry = binding["stocks"].get(proof.instrument.symbol)
    _check(
        entry is not None
        and entry["exchange"] == "NASD"
        and entry["instrument_binding_ref"] == proof.instrument.binding_ref,
        "stock_instrument_mismatch",
    )
    owners = budget._owners(binding)
    _check(
        {owner.owner_ref: ref for owner, ref in owners} == dict(proof.owner_refs),
        "stock_owner_mismatch",
    )
    plan = next((p for p in entry["plans"] if p["request_id"] == proof.request_id), None)
    _check(
        plan is not None
        and "sha256:" + budget._digest(plan) == proof.plan_ref
        and plan["parent_binding_ref"] == proof.parent_binding_ref
        and plan["input_ref"] == proof.input_ref
        and proof.run_id in plan["states"],
        "stock_request_conflict",
    )
    seed = budget._stock_seed_states(binding)[proof.run_id]
    _check(
        seed.intent.fingerprint == proof.intent_ref
        and (seed.intent.symbol, seed.intent.exchange, seed.intent.side)
        == (proof.instrument.symbol, "NASD", proof.side),
        "stock_intent_mismatch",
    )
    _check(
        seed.intent.created_at
        < seed.intent.valid_until
        <= seed.intent.created_at + budget._ORDER_LIFETIME,
        "stock_validity_invalid",
    )
    states = _states(root, binding)
    state = states[proof.run_id]
    _check(state.intent == seed.intent and not state.cancel_after_submit, "stock_intent_mismatch")
    replayed, proofs = _replay_scope(binding, states)
    at = (
        require_utc(as_of)
        if as_of is not None
        else max([datetime.fromisoformat(binding["at"])] + [s.updated_at for s in states.values()])
    )
    projection = budget.project_kis_paper_portfolio_budget(
        basis=budget._basis(binding),
        expected_basis_ref=proof.basis_ref,
        owners=tuple(owner for owner, _ in owners),
        expected_owner_refs=dict(proof.owner_refs),
        states=replayed,
        as_of=at,
        cancellation_proofs=proofs,
    )
    return binding, states, state, projection


def allows_kis_paper_stock_execution(root, run_id, symbol, proof) -> bool:
    """Only an exact materialized, unattempted canonical stock seed can submit."""
    try:
        _, _, state, _ = _scope(Path(root), proof)
        return bool(
            (state.intent.run_id, state.intent.symbol) == (run_id, symbol)
            and state.phase == "intent_recorded"
            and state.submission_started_at is None
            and (Path(root) / (run_id + ".json")).is_file()
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        DecimalException,
        canary.KisPaperCanaryError,
        _RecoveryRequired,
    ):
        return False


def bind_kis_paper_stock_execution_intent(root, requested_intent, proof):
    _, _, state, _ = _scope(Path(root), proof)
    _check(type(requested_intent) is canary.KisPaperCanaryIntent, "stock_intent_mismatch")
    _check(
        requested_intent.client_order_id == "canary-" + proof.run_id
        and replace(requested_intent, client_order_id=state.intent.client_order_id) == state.intent,
        "stock_intent_mismatch",
    )
    return state.intent


def _client_account(client, proof):
    from .kis_paper_stock_canary import KisPaperStockCanaryClient

    _check(isinstance(client, KisPaperStockCanaryClient), "stock_client_invalid")
    _check(client.instrument == proof.instrument, "stock_client_instrument_mismatch")
    config = client._config
    _check(type(config) is KisPaperConfig, "stock_client_invalid")
    replace(config)
    _check(
        budget._digest([config.base_url, config.account_number, config.account_product_code])
        == proof.account_ref,
        "account_binding_mismatch",
    )
    return config


def _stock_book(snapshot, projection, instrument, config, at, *, exit_only=False):
    from .kis_paper_stock_readonly import KisPaperStockExitAccountSnapshot

    expected_type = KisPaperStockExitAccountSnapshot if exit_only else KisPaperReadOnlySnapshot
    _check(type(snapshot) is expected_type, "snapshot_unavailable")
    if exit_only:
        _check(replace(snapshot) == snapshot, "snapshot_unavailable")
    _check(
        snapshot.identity.masked_account == config.masked_account_identity
        and snapshot.open_orders.complete is True,
        "snapshot_unavailable",
    )
    _fresh(
        (
            snapshot.captured_at,
            snapshot.identity.captured_at,
            snapshot.open_orders.captured_at,
            *(p.captured_at for p in snapshot.positions),
            *(o.captured_at for o in snapshot.open_orders.orders),
        ),
        at,
    )
    _check(
        not any(o.symbol == instrument.symbol for o in snapshot.open_orders.orders),
        "stock_target_open_order_pending",
    )
    positions = [p for p in snapshot.positions if p.symbol == instrument.symbol]
    expected = next(
        s.quantity
        for s in projection.stocks_by_instrument
        if (s.symbol, s.exchange) == (instrument.symbol, "NASD")
    )
    _check(
        len(positions) <= 1
        and all(
            p.exchange == "NASD"
            and p.currency == "USD"
            and type(p.quantity) is Decimal
            and p.quantity.is_finite()
            and p.quantity == expected
            for p in positions
        )
        and (expected == 0 or positions),
        "stock_target_inventory_mismatch",
    )
    return None if exit_only else _funds(snapshot.cash, snapshot.orderable_funds, at)


def _execute_kis_paper_stock(
    *,
    proof: KisPaperStockExecutionBinding,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    state_root: Path = canary.DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    execution_control_path: Path = canary.DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
    client: canary.KisPaperCanaryClient | None = None,
    execute: bool = False,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    side: str,
) -> canary.KisPaperCanaryOutcome | None:
    """One exact retained side; unknown outcomes never resubmit."""
    _check(type(execute) is bool, "stock_execute_invalid")
    if not execute:
        return None
    _check(type(proof) is KisPaperStockExecutionBinding, "stock_proof_invalid")
    _check(proof.side == side, "stock_side_mismatch")
    root = Path(state_root)
    paths = tuple(
        map(
            Path,
            (
                runtime_projection_path,
                paper_account_snapshot_path,
                emergency_state_path,
                execution_control_path,
            ),
        )
    )
    for path in (root, proof.state_root, Path(repository_root), Path(artifact_root), *paths):
        _unlinked(path)
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root), *paths)
    _check(root.resolve() == proof.state_root.resolve(), "stock_root_mismatch")
    _client_account(client, proof)

    def at():
        return canary._canary_now(now=now, clock=clock)

    def permitted(reconciliation, submit_at):
        config = _client_account(client, proof)
        _, _, state, projection = _scope(root, proof, submit_at)
        if side == "sell":
            from .kis_paper_stock_plan import _pending
            from .kis_paper_stock_readonly import KisPaperStockExitReads

            _stock_book(
                reconciliation.snapshot,
                projection,
                proof.instrument,
                config,
                submit_at,
                exit_only=True,
            )
            reads = client.stock_exit_snapshot(expected_account_ref=proof.account_ref, clock=at)
            _check(type(reads) is KisPaperStockExitReads, "snapshot_unavailable")
            _check(replace(reads) == reads, "snapshot_unavailable")
            _check(
                reads.account_ref == proof.account_ref and reads.instrument == proof.instrument,
                "stock_instrument_mismatch",
            )
            checked_at = at()
            binding, states, retained, current = _scope(root, proof, checked_at)
            _stock_book(
                reads.snapshot,
                current,
                proof.instrument,
                _client_account(client, proof),
                checked_at,
                exit_only=True,
            )
            _fresh((reads.started_at, reads.completed_at, reads.quote.quoted_at), checked_at)
            from .kis_paper_quote import derive_kis_paper_marketable_limit

            derive_kis_paper_marketable_limit(reads.quote, side="sell", observed_at=checked_at)
            owner_id = budget._stock_owner_id(proof.instrument.binding_ref)
            owner = next(o for o, _ in budget._owners(binding) if o.owner_ref == owner_id)
            _, cancellation_proofs = _replay_scope(binding, states)
            _check(
                not any(
                    ref.run_id != proof.run_id and _pending(states[ref.run_id], cancellation_proofs)
                    for ref in owner.state_refs
                ),
                "stock_owner_pending",
            )
            owned = next(s for s in current.stocks_by_owner if s.owner_ref == owner_id)
            _check(
                retained.intent == state.intent
                and retained.phase == "intent_recorded"
                and retained.intent.quantity <= owned.quantity,
                "stock_target_inventory_mismatch",
            )
            _check(is_us_equity_regular_session_window(checked_at), "outside_regular_session")
            _check(
                not canary.EmergencyStore(paths[2]).read().blocks_new_orders,
                "emergency_stop_new_orders",
            )
            _check(
                not canary.PaperExecutionControlStore(paths[3]).read().pause_sells,
                "pause_sells_active",
            )
            return True
        available = _stock_book(
            reconciliation.snapshot, projection, proof.instrument, config, submit_at
        )
        intent = state.intent
        cash, funds = client.orderable_funds_at_limit(
            symbol=intent.symbol,
            exchange=intent.exchange,
            limit_price=intent.limit_price,
        )
        checked_at = at()
        available = min(available, _funds(cash, funds, checked_at))
        _check(
            (funds.reference_symbol, funds.reference_exchange, funds.reference_price)
            == (intent.symbol, intent.exchange, intent.limit_price),
            "orderability_binding_mismatch",
        )
        _, _, retained, current = _scope(root, proof, checked_at)
        available = min(
            available,
            _stock_book(
                reconciliation.snapshot,
                current,
                proof.instrument,
                _client_account(client, proof),
                checked_at,
            ),
        )
        _check(
            retained.intent == intent and retained.phase == "intent_recorded",
            "stock_intent_mismatch",
        )
        _check(is_us_equity_regular_session_window(checked_at), "outside_regular_session")
        _check(
            not canary.EmergencyStore(paths[2]).read().blocks_new_orders,
            "emergency_stop_new_orders",
        )
        _check(
            not canary.PaperExecutionControlStore(paths[3]).read().pause_buys, "pause_buys_active"
        )
        _check(
            Fraction(available) >= Fraction(current.reserved_buys)
            and Fraction(available) >= Fraction(intent.quantity) * Fraction(intent.limit_price),
            "buying_power_changed",
        )
        return True

    for name in (".session_execution", ".canary_execution"):
        _unlinked(root / ("." + name + ".lock"))
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            _, _, state, _ = _scope(root, proof, at())
            intent = state.intent
            state_path = root / (intent.run_id + ".json")
            _unlinked(state_path.with_name("." + state_path.name + ".lock"))
            canary.KisPaperCanaryStateStore(state_path).record_intent(
                intent,
                cancel_after_submit=False,
                now=at(),
            )
            return canary._run_kis_paper_canary(
                decision=(
                    canary.KisPaperCanaryBuyDecision
                    if side == "buy"
                    else canary.KisPaperCanarySellDecision
                )(
                    decision_id=intent.decision_id,
                    symbol=intent.symbol,
                    exchange=intent.exchange,
                    quantity=intent.quantity,
                    limit_price=intent.limit_price,
                    decision_as_of=intent.created_at,
                    valid_until=intent.valid_until,
                ),
                run_id=intent.run_id,
                environment={},
                state_path=state_path,
                runtime_projection_path=paths[0],
                paper_account_snapshot_path=paths[1],
                emergency_state_path=paths[2],
                execution_control_path=paths[3],
                artifact_root=Path(artifact_root),
                repository_root=Path(repository_root),
                execute=True,
                cancel_after_submit=False,
                client=client,
                now=now,
                clock=clock,
                submit_permitted=is_us_equity_regular_session_window,
                submit_reconciliation_check=permitted,
                require_existing_state=True,
                price_contract_ref=intent.price_contract_ref,
                stock_execution=proof,
            )


def execute_kis_paper_stock_buy(**arguments) -> canary.KisPaperCanaryOutcome | None:
    """Existing exact BUY API; default inert and never accepts a SELL proof."""
    return _execute_kis_paper_stock(side="buy", **arguments)


def execute_kis_paper_stock_sell(**arguments) -> canary.KisPaperCanaryOutcome | None:
    """Explicit owned SELL API without a cash or buying-power dependency."""
    return _execute_kis_paper_stock(side="sell", **arguments)
