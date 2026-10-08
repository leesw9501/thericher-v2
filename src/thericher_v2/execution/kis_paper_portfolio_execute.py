"""Execute one retained V3 BUY leg through the existing Paper canary lifecycle.

No sizing, credential loading, binding rewrite, replacement identity or CLI.
Caller custody pins are required; replayed sale proceeds are not buying power.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import require_utc

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from .kis_paper_portfolio_plan import _replay_scope, _states
from .kis_paper_quote import KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_readonly import (
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlySnapshot,
)


def _check(condition, reason):
    if not condition:
        raise _RecoveryRequired(reason)


def _unlinked(path):
    _check(
        not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
        "private_root_invalid",
    )


@dataclass(frozen=True, repr=False, kw_only=True)
class KisPaperPortfolioExecutionBinding:
    """Independent caller pins, not a boolean exception to the ownership guard."""

    state_root: Path
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

    def __post_init__(self):
        _check(
            isinstance(self.state_root, Path) and self.state_root.is_absolute(),
            "portfolio_root_pin_invalid",
        )
        _check(
            type(self.account_ref) is str
            and len(self.account_ref) == 64
            and all(c in "0123456789abcdef" for c in self.account_ref),
            "account_binding_mismatch",
        )
        _check(
            type(self.request_id) is str
            and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(self.request_id),
            "portfolio_request_invalid",
        )
        _check(
            type(self.run_id) is str and budget._PORTFOLIO_RUN_ID.fullmatch(self.run_id),
            "portfolio_intent_mismatch",
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
            "portfolio_owner_mismatch",
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
            "portfolio_reference_invalid",
        )


def _scope(root, proof, as_of=None):
    _check(type(proof) is KisPaperPortfolioExecutionBinding, "portfolio_proof_invalid")
    replace(proof)
    _unlinked(root)
    _unlinked(proof.state_root)
    _check(root.resolve() == proof.state_root.resolve(), "portfolio_root_mismatch")
    binding = budget._load_binding(root, proof.account_ref)
    _check(
        binding is not None and binding["version"] == 3 and binding["legacy_spy"] is None,
        "portfolio_custody_mismatch",
    )
    _check("sha256:" + budget._digest(binding) == proof.binding_ref, "portfolio_binding_mismatch")
    _check(
        binding["basis_ref"] == proof.basis_ref
        and budget._basis(binding).fingerprint == proof.basis_ref,
        "portfolio_custody_mismatch",
    )
    owners = budget._owners(binding)
    _check(
        {owner.owner_ref: ref for owner, ref in owners} == dict(proof.owner_refs),
        "portfolio_owner_mismatch",
    )
    plan = next(
        (p for p in binding["portfolio"]["plans"] if p["request_id"] == proof.request_id), None
    )
    _check(
        plan is not None
        and "sha256:" + budget._digest(plan) == proof.plan_ref
        and plan["parent_binding_ref"] == proof.parent_binding_ref
        and plan["input_ref"] == proof.input_ref
        and proof.run_id in plan["states"],
        "portfolio_request_conflict",
    )
    seeds = budget._portfolio_seed_states(binding)
    seed = seeds[proof.run_id]
    _check(seed.intent.fingerprint == proof.intent_ref, "portfolio_intent_mismatch")
    _check(
        seed.intent.created_at
        < seed.intent.valid_until
        <= seed.intent.created_at + budget._ORDER_LIFETIME,
        "portfolio_validity_invalid",
    )
    states = _states(root, binding)
    state = states[proof.run_id]
    _check(
        state.intent == seed.intent and not state.cancel_after_submit, "portfolio_intent_mismatch"
    )
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


def allows_kis_paper_portfolio_execution(root, run_id, symbol, proof) -> bool:
    """Shared-guard hook; bare canary callers still have no portfolio exception.

    The caller holds the canonical canary lock. Only a materialized, exact
    unattempted BUY seed can pass; recovery never needs this new-submit hook.
    """
    try:
        _, _, state, _ = _scope(Path(root), proof)
        return bool(
            (state.intent.run_id, state.intent.symbol) == (run_id, symbol)
            and state.intent.side == "buy"
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


def bind_kis_paper_portfolio_execution_intent(root, requested_intent, proof):
    """Preserve the retained portfolio client identity, never resize or reissue.

    Called only by the typed internal-canary hook under the same root lock.
    Every other requested field, including the original clock and price pin,
    must exactly match the independently pinned seed.
    """
    _, _, state, _ = _scope(Path(root), proof)
    _check(type(requested_intent) is canary.KisPaperCanaryIntent, "portfolio_intent_mismatch")
    _check(
        requested_intent.client_order_id == "canary-" + proof.run_id
        and replace(requested_intent, client_order_id=state.intent.client_order_id) == state.intent,
        "portfolio_intent_mismatch",
    )
    return state.intent


def _client_account(client, proof):
    _check(isinstance(client, canary.KisPaperCanaryClient), "portfolio_client_invalid")
    config = client._config
    _check(type(config) is KisPaperConfig, "portfolio_client_invalid")
    replace(config)
    _check(
        budget._digest([config.base_url, config.account_number, config.account_product_code])
        == proof.account_ref,
        "account_binding_mismatch",
    )
    return config


def _fresh(times, at):
    _check(
        all(
            timedelta(seconds=-5) <= at - require_utc(t) <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
            for t in times
        ),
        "snapshot_unavailable",
    )


def _funds(cash, funds, at):
    _check(
        type(cash) is KisPaperCashSnapshot and type(funds) is KisPaperOrderableFundsSnapshot,
        "buying_power_unavailable",
    )
    replace(cash)
    replace(funds)
    _check(cash.currency == funds.currency == "USD", "funds_currency_mismatch")
    _check(
        all(
            type(v) is Decimal and v.is_finite() and v >= 0
            for v in (cash.available_cash, funds.orderable_funds)
        ),
        "buying_power_unavailable",
    )
    _fresh((cash.captured_at, funds.captured_at), at)
    return min(cash.available_cash, funds.orderable_funds)


def _book(snapshot, projection, config, at):
    _check(type(snapshot) is KisPaperReadOnlySnapshot, "snapshot_unavailable")
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
    _check(not snapshot.open_orders.orders, "pre_submit_ownership_changed")
    expected = {(s.symbol, s.exchange): s.quantity for s in projection.stocks_by_instrument}
    seen = set()
    for position in snapshot.positions:
        key = (position.symbol, position.exchange)
        _check(
            key in expected
            and key not in seen
            and position.currency == "USD"
            and type(position.quantity) is Decimal
            and position.quantity.is_finite()
            and position.quantity == expected[key],
            "pre_submit_ownership_changed",
        )
        seen.add(key)
    _check(
        all(quantity == 0 or key in seen for key, quantity in expected.items()),
        "pre_submit_ownership_changed",
    )
    return _funds(snapshot.cash, snapshot.orderable_funds, at)


def execute_kis_paper_portfolio_buy(
    *,
    proof: KisPaperPortfolioExecutionBinding,
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
) -> canary.KisPaperCanaryOutcome | None:
    """One exact leg, at most one submission, with original-expiry recovery.

    Default is inert. A supplied Paper client owns the existing transport;
    this adapter never loads credentials or creates a provider. Caller must
    provide independently retained pins, not regenerate them from this read.
    """
    _check(type(execute) is bool, "portfolio_execute_invalid")
    if not execute:
        return None
    _check(type(proof) is KisPaperPortfolioExecutionBinding, "portfolio_proof_invalid")
    root = Path(state_root)
    paths = (
        Path(runtime_projection_path),
        Path(paper_account_snapshot_path),
        Path(emergency_state_path),
        Path(execution_control_path),
    )
    for path in (root, proof.state_root, Path(repository_root), Path(artifact_root), *paths):
        _unlinked(path)
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root), *paths)
    _check(root.resolve() == proof.state_root.resolve(), "portfolio_root_mismatch")
    _client_account(client, proof)

    def at():
        return canary._canary_now(now=now, clock=clock)

    def permitted(reconciliation, submit_at):
        config = _client_account(client, proof)
        binding, states, state, projection = _scope(root, proof, submit_at)
        for other in states.values():
            retained, cancellation = other, None
            evidence = binding["terminal_evidence"].get(other.intent.run_id)
            if evidence is not None:
                retained, cancellation = budget._retained_terminal(other, evidence)
            _check(
                budget._terminal(retained, cancellation)
                or (
                    other.intent.side == "buy"
                    and other.phase == "intent_recorded"
                    and other.submission_started_at is None
                ),
                "portfolio_pending_identity",
            )
        available = _book(reconciliation.snapshot, projection, config, submit_at)
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
        _client_account(client, proof)
        _, _, retained, current = _scope(root, proof, checked_at)
        available = min(
            available,
            _book(
                reconciliation.snapshot,
                current,
                _client_account(client, proof),
                checked_at,
            ),
        )
        _check(
            retained.intent == intent and retained.phase == "intent_recorded",
            "portfolio_intent_mismatch",
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
                decision=canary.KisPaperCanaryBuyDecision(
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
                portfolio_execution=proof,
            )
