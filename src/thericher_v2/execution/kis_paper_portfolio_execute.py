"""Execute retained V3 BUY or portfolio-owned SELL through the Paper lifecycle.

No strategy selection, credential loading, replacement identity or CLI.
SELL preparation appends seeds to the existing shared binding under its locks.
Caller custody pins are required; replayed sale proceeds are not buying power.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import require_utc

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from .kis_paper_portfolio_plan import _replay_scope, _states, reconcile_kis_paper_portfolio_plan
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
        binding is not None and binding["version"] in {3, 4} and binding["legacy_spy"] is None,
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
    unattempted owned seed can pass; recovery never needs this new-submit hook.
    """
    try:
        _, _, state, projection = _scope(Path(root), proof)
        return bool(
            (state.intent.run_id, state.intent.symbol) == (run_id, symbol)
            and state.intent.side in {"buy", "sell"}
            and (
                state.intent.side == "buy"
                or _owned_sell_quantity(projection, state.intent) >= state.intent.quantity
            )
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
            if other.intent.symbol not in {"SPY", "QQQ", "TLT", "GLD"}:
                continue
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
            _check(intent.side == "buy", "portfolio_side_mismatch")
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


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioSellPlan:
    status: str
    reason: str
    binding: dict | None = None
    intents: tuple[canary.KisPaperCanaryIntent, ...] = ()
    plan_ref: str | None = None

    def safe_payload(self):
        return {
            "kind": "kis_paper_portfolio_sell_plan_v1",
            "status": self.status,
            "reason": self.reason,
            "sell_leg_count": len(self.intents),
            "new_submits": 0,
            "limitation": "owned_gross_proceeds_not_fees_or_settled_cash",
        }


def _owned_sell_quantity(projection, intent):
    owner = "portfolio-" + intent.symbol.lower()
    matches = [
        stock
        for stock in projection.stocks_by_owner
        if (stock.owner_ref, stock.symbol, stock.exchange)
        == (owner, intent.symbol, intent.exchange)
    ]
    _check(len(matches) == 1, "portfolio_owner_mismatch")
    return matches[0].quantity


def build_kis_paper_portfolio_sell_plan(
    *,
    binding,
    states,
    expected_account_ref,
    expected_basis_ref,
    expected_owner_refs,
    expected_binding_ref,
    request_id,
    input_ref,
    reductions_by_symbol=None,
    limits_by_symbol=None,
    as_of,
    valid_until=None,
) -> KisPaperPortfolioSellPlan:
    """Pure exact owner-local reduction proposal; no snapshot/funding claim.

    Fresh quotes/limits belong to caller preparation. Exact retries may omit
    quantities/limits/expiry, or supply the unchanged original terms. The
    original session/input/control can be bound in request_id/input_ref.
    """
    _check(
        type(request_id) is str
        and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(request_id)
        and request_id.startswith("portfolio-sell-"),
        "portfolio_request_invalid",
    )
    _check(
        all(
            type(ref) is str and budget._SHA.fullmatch(ref)
            for ref in (expected_binding_ref, input_ref)
        ),
        "portfolio_reference_invalid",
    )
    _check(
        isinstance(binding, Mapping)
        and type(binding.get("version")) is int
        and (binding["version"], set(binding)) in ((3, budget._V3_KEYS), (4, budget._V4_KEYS))
        and binding["legacy_spy"] is None,
        "portfolio_custody_mismatch",
    )
    _check(
        binding["account_ref"] == expected_account_ref
        and binding["basis_ref"] == expected_basis_ref
        and budget._basis(binding).fingerprint == expected_basis_ref,
        "portfolio_custody_mismatch",
    )
    _check(type(as_of) is datetime, "portfolio_validity_invalid")
    at = require_utc(as_of)
    owners = budget._owners(binding)
    refs = {owner.owner_ref: ref for owner, ref in owners}
    _check(all(owner.fingerprint == ref for owner, ref in owners), "portfolio_owner_mismatch")
    _check(
        isinstance(states, Mapping)
        and set(states) == {ref.run_id for owner, _ in owners for ref in owner.state_refs},
        "portfolio_state_scope_invalid",
    )
    replayed, proofs = _replay_scope(binding, states)
    projection = budget.project_kis_paper_portfolio_budget(
        basis=budget._basis(binding),
        expected_basis_ref=expected_basis_ref,
        owners=tuple(owner for owner, _ in owners),
        expected_owner_refs=refs,
        states=replayed,
        as_of=at,
        cancellation_proofs=proofs,
    )
    symbols = {s for s, _ in budget._PORTFOLIO_INSTRUMENTS}
    if reductions_by_symbol is not None:
        _check(
            isinstance(reductions_by_symbol, Mapping)
            and set(reductions_by_symbol) == symbols
            and all(
                type(q) is Decimal and q.is_finite() and q >= 0 and q == q.to_integral_value()
                for q in reductions_by_symbol.values()
            ),
            "portfolio_reductions_invalid",
        )
    if limits_by_symbol is not None:
        _check(
            isinstance(limits_by_symbol, Mapping)
            and all(
                type(p) is Decimal
                and p.is_finite()
                and p > 0
                and p.as_tuple().exponent >= -8
                and p.adjusted() < 23
                for p in limits_by_symbol.values()
            ),
            "portfolio_limits_invalid",
        )
    if valid_until is not None:
        _check(type(valid_until) is datetime, "portfolio_validity_invalid")
        valid_until = require_utc(valid_until)
    plan = next((p for p in binding["portfolio"]["plans"] if p["request_id"] == request_id), None)
    if plan is not None:
        seeds = budget._portfolio_seed_states(binding)
        intents = tuple(
            seeds[run].intent
            for symbol, _ in budget._PORTFOLIO_INSTRUMENTS
            for run in plan["states"]
            if seeds[run].intent.symbol == symbol
        )
        _check(
            all(i.side == "sell" for i in intents)
            and plan["input_ref"] == input_ref
            and plan["parent_binding_ref"] == expected_binding_ref,
            "portfolio_request_conflict",
        )
        parent = copy.deepcopy(dict(binding))
        parent["portfolio"]["plans"].remove(plan)
        for run in plan["states"]:
            parent["terminal_evidence"].pop(run, None)
        for owner, _ in budget._owners(parent):
            if owner.owner_ref.startswith("portfolio-"):
                parent["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
        parent_refs = {owner.owner_ref: ref for owner, ref in budget._owners(parent)}
        _check(
            expected_owner_refs == refs
            or (
                expected_owner_refs == parent_refs
                and "sha256:" + budget._digest(parent) == expected_binding_ref
            ),
            "portfolio_owner_mismatch",
        )
        original_quantities = {s: Decimal(0) for s, _ in budget._PORTFOLIO_INSTRUMENTS}
        original_quantities.update({i.symbol: i.quantity for i in intents})
        _check(
            reductions_by_symbol is None or reductions_by_symbol == original_quantities,
            "portfolio_request_conflict",
        )
        _check(
            limits_by_symbol is None
            or limits_by_symbol == {i.symbol: i.limit_price for i in intents},
            "portfolio_request_conflict",
        )
        _check(
            valid_until is None or all(valid_until == i.valid_until for i in intents),
            "portfolio_request_conflict",
        )
        return KisPaperPortfolioSellPlan(
            "replayed",
            "exact_identity_reused",
            copy.deepcopy(dict(binding)),
            intents,
            "sha256:" + budget._digest(plan),
        )
    _check(expected_owner_refs == refs, "portfolio_owner_mismatch")
    _check(
        "sha256:" + budget._digest(binding) == expected_binding_ref,
        "portfolio_parent_binding_mismatch",
    )
    _check(reductions_by_symbol is not None, "portfolio_reductions_invalid")
    active = {s for s, q in reductions_by_symbol.items() if q > 0}
    if not active:
        return KisPaperPortfolioSellPlan("no_intent", "no_owned_reduction")
    targets = {(s, ex) for s, ex in budget._PORTFOLIO_INSTRUMENTS if s in active}
    _check(
        all(
            run in binding["terminal_evidence"] and budget._terminal(state, proofs.get(run))
            for run, state in replayed.items()
            if (state.intent.symbol, state.intent.exchange) in targets
        ),
        "portfolio_pending_identity",
    )
    _check(
        isinstance(limits_by_symbol, Mapping) and set(limits_by_symbol) == active,
        "portfolio_limits_invalid",
    )
    _check(valid_until is not None, "portfolio_validity_invalid")
    until = require_utc(valid_until)
    _check(at < until <= at + budget._ORDER_LIFETIME, "portfolio_validity_invalid")
    seeds = {}
    for symbol, exchange in budget._PORTFOLIO_INSTRUMENTS:
        if symbol not in active:
            continue
        owner = "portfolio-" + symbol.lower()
        identity = budget._digest(
            [expected_account_ref, expected_basis_ref, request_id, symbol, "sell", owner]
        )
        price = limits_by_symbol[symbol]
        intent = canary.KisPaperCanaryIntent(
            "bp-" + identity,
            "portfolio-" + identity,
            "portfolio-" + identity,
            symbol,
            exchange,
            reductions_by_symbol[symbol],
            price,
            at,
            until,
            side="sell",
            price_contract_ref="sha256:"
            + budget._digest([input_ref, symbol, str(price), "sell", owner]),
        )
        _check(
            intent.quantity <= _owned_sell_quantity(projection, intent),
            "portfolio_owned_quantity_exceeded",
        )
        seeds[intent.run_id] = canary.KisPaperCanaryState(
            intent, "intent_recorded", at, "preview"
        ).to_dict()
    updated = copy.deepcopy(dict(binding))
    plan = dict(
        request_id=request_id,
        input_ref=input_ref,
        parent_binding_ref=expected_binding_ref,
        states=seeds,
    )
    updated["portfolio"]["plans"].append(plan)
    for owner, _ in budget._owners(updated):
        if owner.owner_ref.startswith("portfolio-"):
            updated["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    combined = dict(states) | {
        run: canary.KisPaperCanaryState.from_dict(payload) for run, payload in seeds.items()
    }
    new_owners = budget._owners(updated)
    budget.project_kis_paper_portfolio_budget(
        basis=budget._basis(updated),
        expected_basis_ref=expected_basis_ref,
        owners=tuple(owner for owner, _ in new_owners),
        expected_owner_refs={owner.owner_ref: ref for owner, ref in new_owners},
        states=_replay_scope(updated, combined)[0],
        as_of=at,
        cancellation_proofs=proofs,
    )
    return KisPaperPortfolioSellPlan(
        "prepared",
        "owned_reduction_prepared",
        updated,
        tuple(canary.KisPaperCanaryState.from_dict(p).intent for p in seeds.values()),
        "sha256:" + budget._digest(plan),
    )


def reserve_kis_paper_portfolio_sell_plan(
    *, state_root, repository_root, artifact_root, **arguments
):
    """Persist all SELL seeds under the existing shared locks before any wire."""
    root = Path(state_root)
    _unlinked(root)
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root))
    for name in (".session_execution", ".canary_execution"):
        _unlinked(root / ("." + name + ".lock"))
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, arguments["expected_account_ref"])
            _check(binding is not None, "portfolio_existing_basis_required")
            result = build_kis_paper_portfolio_sell_plan(
                binding=binding, states=_states(root, binding), **arguments
            )
            if result.status == "prepared":
                budget._atomic_json(root / budget.BUDGET_FILE, result.binding)
                _check(
                    budget._load_binding(root, arguments["expected_account_ref"]) == result.binding,
                    "portfolio_reservation_readback_mismatch",
                )
                budget.project_budget(root, result.binding, as_of=arguments["as_of"])
                return replace(result, status="reserved", reason="owned_reduction_persisted")
            return result


def execute_kis_paper_portfolio_sell(
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
    """One retained owner-only SELL; no BUY/funds request, replacement or resize."""
    _check(type(execute) is bool, "portfolio_execute_invalid")
    if not execute:
        return None
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
    _check(type(proof) is KisPaperPortfolioExecutionBinding, "portfolio_proof_invalid")
    for path in (root, proof.state_root, Path(repository_root), Path(artifact_root), *paths):
        _unlinked(path)
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root), *paths)
    _client_account(client, proof)

    def at():
        return canary._canary_now(now=now, clock=clock)

    def permitted(reconciliation, submit_at):
        config = _client_account(client, proof)
        binding, states, state, projection = _scope(root, proof, submit_at)
        _check(
            state.intent.side == "sell" and state.phase == "intent_recorded",
            "portfolio_side_mismatch",
        )
        _check(
            state.intent.quantity <= _owned_sell_quantity(projection, state.intent),
            "portfolio_owned_quantity_exceeded",
        )
        own_plan = next(
            p for p in binding["portfolio"]["plans"] if p["request_id"] == proof.request_id
        )
        for other in states.values():
            if (other.intent.symbol, other.intent.exchange) != (
                state.intent.symbol,
                state.intent.exchange,
            ):
                continue
            retained, cancellation = other, None
            evidence = binding["terminal_evidence"].get(other.intent.run_id)
            if evidence is not None:
                retained, cancellation = budget._retained_terminal(other, evidence)
            _check(
                budget._terminal(retained, cancellation)
                or (
                    other.intent.run_id in own_plan["states"]
                    and other.intent.side == "sell"
                    and other.phase == "intent_recorded"
                    and other.submission_started_at is None
                ),
                "portfolio_pending_identity",
            )
        _book(reconciliation.snapshot, projection, config, submit_at)
        return True

    for name in (".session_execution", ".canary_execution"):
        _unlinked(root / ("." + name + ".lock"))
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            _, _, state, projection = _scope(root, proof, at())
            intent = state.intent
            _check(intent.side == "sell", "portfolio_side_mismatch")
            if state.phase == "intent_recorded":
                _check(
                    intent.quantity <= _owned_sell_quantity(projection, intent),
                    "portfolio_owned_quantity_exceeded",
                )
            path = root / (intent.run_id + ".json")
            _unlinked(path.with_name("." + path.name + ".lock"))
            canary.KisPaperCanaryStateStore(path).record_intent(
                intent, cancel_after_submit=False, now=at()
            )
            return canary._run_kis_paper_canary(
                decision=canary.KisPaperCanarySellDecision(
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
                state_path=path,
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


def reconcile_kis_paper_portfolio_sell_plan(
    *, proof, state_root, repository_root, artifact_root, as_of, cancellation_proofs=None
):
    """Use the existing terminal custody loop; never query or infer proceeds."""
    binding, _, _, _ = _scope(Path(state_root), proof, as_of)
    plan = next(p for p in binding["portfolio"]["plans"] if p["request_id"] == proof.request_id)
    seeds = budget._portfolio_seed_states(binding)
    _check(
        all(seeds[run].intent.side == "sell" for run in plan["states"]), "portfolio_side_mismatch"
    )
    result = reconcile_kis_paper_portfolio_plan(
        state_root=state_root,
        repository_root=repository_root,
        artifact_root=artifact_root,
        expected_account_ref=proof.account_ref,
        expected_basis_ref=proof.basis_ref,
        expected_owner_refs=dict(proof.owner_refs),
        request_id=proof.request_id,
        expected_plan_ref=proof.plan_ref,
        as_of=as_of,
        cancellation_proofs=cancellation_proofs,
    )
    return KisPaperPortfolioSellPlan(
        result.status, result.reason, result.binding, result.intents, result.plan_ref
    )
