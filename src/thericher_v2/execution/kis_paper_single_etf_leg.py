"""Opt-in SPY/AMEX leg in the original canonical Paper bank.

Builders are pure. Reservation uses the existing account locks and portfolio
seed codec. One immutable request control records the exact entry and H20 exit
duty before the bank seed is persisted. No client, credentials or scheduler is
created here; an admitted SingleOwnerContext/BankLeg/NativeBridge supplies the
existing effect-time guard and native portfolio executor.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import require_utc
from thericher_v2.data.us_equity_session import us_equity_2026_session

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from .kis_paper_portfolio_execute import (
    KisPaperPortfolioExecutionBinding,
    build_kis_paper_portfolio_sell_plan,
)
from .kis_paper_portfolio_plan import _replay_scope, _states
from .kis_paper_quote import KisPaperSpyLimitInput, derive_kis_paper_marketable_limit
from .kis_paper_stock_plan import _amount, _buy_limit, _typed
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPortfolioPreviewInstrument,
    KisPaperPortfolioPreviewReads,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

_SCHEMA = "kis_paper_single_etf_open20_v1"


class SingleEtfLegError(ValueError):
    """Closed contract error; never include a private value in its message."""


def _need(ok, code):
    if not ok:
        raise SingleEtfLegError(code)


def _ref(value):
    _need(type(value) is str and budget._SHA.fullmatch(value), "reference_invalid")


def _hash(value):
    return "sha256:" + budget._digest(value)


def single_etf_h20_sessions(entry_date: date):
    """OPEN[e+20] means twenty-one inclusive official sessions, not H5/20 CLOSE."""
    _need(type(entry_date) is date and entry_date.year == 2026, "calendar_scope_invalid")
    sessions = []
    for offset in range(70):
        day = entry_date + timedelta(days=offset)
        _need(day.year == 2026, "calendar_scope_invalid")
        session = us_equity_2026_session(day)
        if session is not None:
            sessions.append(session.window)
            if len(sessions) == 21:
                break
    _need(
        len(sessions) == 21 and us_equity_2026_session(entry_date) is not None,
        "calendar_sessions_invalid",
    )
    return tuple(sessions)


@dataclass(frozen=True, repr=False)
class SingleEtfLegContract:
    """Separately adopted operational input; never rewrites producer authority.

    References bind the caller's exact source/proposal/model/input/policy. Their
    external provenance and actual release remain with the existing host guard.
    This initial canonical path supports SPY only; no QQQ substitution occurs.
    """

    request_id: str
    account_ref: str
    basis_ref: str
    source_ref: str
    proposal_ref: str
    model_ref: str
    input_ref: str
    policy_ref: str
    symbol: str
    action: str
    target_exposure: Decimal
    point_available_at: datetime
    entry_date: date
    entry_starts_at: datetime
    entry_ends_at: datetime
    exit_window_seconds: int

    def __post_init__(self):
        _need(
            type(self.request_id) is str
            and self.request_id.startswith("single-etf-")
            and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(self.request_id),
            "request_invalid",
        )
        _need(
            type(self.account_ref) is str
            and len(self.account_ref) == 64
            and all(c in "0123456789abcdef" for c in self.account_ref),
            "account_invalid",
        )
        for value in (
            self.basis_ref,
            self.source_ref,
            self.proposal_ref,
            self.model_ref,
            self.input_ref,
            self.policy_ref,
        ):
            _ref(value)
        _need(
            self.symbol == "SPY" and self.action in {"enter", "abstain"}, "single_etf_not_supported"
        )
        exposure = _amount(self.target_exposure)
        _need(
            exposure <= Fraction(1, 10) and (self.action != "abstain" or exposure == 0),
            "exposure_invalid",
        )
        windows = single_etf_h20_sessions(self.entry_date)
        for name in ("point_available_at", "entry_starts_at", "entry_ends_at"):
            object.__setattr__(self, name, require_utc(getattr(self, name)))
        _need(
            self.point_available_at <= self.entry_starts_at
            and windows[0].open_ts
            <= self.entry_starts_at
            < self.entry_ends_at
            <= windows[0].close_ts,
            "entry_window_invalid",
        )
        _need(
            type(self.exit_window_seconds) is int
            and self.exit_window_seconds > 0
            and self.exit_ends_at <= windows[-1].close_ts,
            "exit_window_invalid",
        )

    @property
    def exit_starts_at(self):
        return single_etf_h20_sessions(self.entry_date)[-1].open_ts

    @property
    def exit_ends_at(self):
        return self.exit_starts_at + timedelta(seconds=self.exit_window_seconds)

    def to_dict(self):
        return {
            name: (
                value.isoformat()
                if isinstance(value, (date, datetime))
                else str(value)
                if type(value) is Decimal
                else value
            )
            for name, value in vars(self).items()
        }

    @property
    def fingerprint(self):
        return _hash(self.to_dict())


@dataclass(frozen=True, repr=False)
class SingleEtfLegPlan:
    status: str
    reason: str
    binding: dict | None = None
    control: dict | None = None
    intents: tuple[canary.KisPaperCanaryIntent, ...] = ()
    plan_ref: str | None = None

    def safe_payload(self):
        return dict(
            kind=_SCHEMA,
            status=self.status,
            reason=self.reason,
            leg_count=len(self.intents),
            new_submits=0,
            limitation="native_reservation_not_acceptance_fill_settlement_or_pnl",
        )


def _scope(binding, states, contract, owner_refs, at):
    _need(type(contract) is SingleEtfLegContract, "contract_invalid")
    replace(contract)
    _need(
        isinstance(binding, Mapping)
        and binding.get("version") in {2, 3, 4}
        and binding.get("account_ref") == contract.account_ref
        and binding.get("basis_ref") == contract.basis_ref
        and budget._basis(binding).fingerprint == contract.basis_ref
        and binding.get("legacy_spy") is None,
        "original_custody_invalid",
    )
    owners = budget._owners(binding)
    _need(
        isinstance(owner_refs, Mapping)
        and {o.owner_ref: pin for o, pin in owners} == owner_refs
        and all(o.fingerprint == pin for o, pin in owners),
        "owner_scope_changed",
    )
    _need(
        isinstance(states, Mapping)
        and set(states) == {r.run_id for o, _ in owners for r in o.state_refs},
        "state_scope_invalid",
    )
    replayed, proofs = _replay_scope(binding, states)
    projection = budget.project_kis_paper_portfolio_budget(
        basis=budget._basis(binding),
        expected_basis_ref=contract.basis_ref,
        owners=tuple(o for o, _ in owners),
        expected_owner_refs=owner_refs,
        states=replayed,
        as_of=at,
        cancellation_proofs=proofs,
    )
    return replayed, proofs, projection


def _plans(binding):
    return binding.get("portfolio", {}).get("plans", [])


def _find(binding, request_id):
    found = [p for p in _plans(binding) if p["request_id"] == request_id]
    _need(len(found) <= 1, "request_conflict")
    return found[0] if found else None


def _append(binding, plan, states, contract, at):
    updated = copy.deepcopy(dict(binding))
    if updated["version"] == 2:
        updated.update(
            version=3,
            portfolio=dict(
                owner_refs={s: None for s, _ in budget._PORTFOLIO_INSTRUMENTS}, plans=[]
            ),
        )
    updated["portfolio"]["plans"].append(copy.deepcopy(plan))
    for owner, _ in budget._owners(updated):
        if owner.owner_ref.startswith("portfolio-"):
            updated["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    combined = dict(states) | budget._portfolio_seed_states(updated)
    # Materialized states always take precedence over immutable initial seeds.
    combined.update(states)
    _scope(updated, combined, contract, {o.owner_ref: p for o, p in budget._owners(updated)}, at)
    return updated


def _account(reads, contract, projection, at, *, buy):
    _typed(reads, KisPaperPortfolioPreviewReads, "reads_invalid")
    _need(
        reads.account_ref == contract.account_ref and len(reads.instruments) == 1,
        "account_binding_changed",
    )
    snapshot, row = reads.snapshot, reads.instruments[0]
    _typed(snapshot, KisPaperReadOnlySnapshot, "reads_invalid")
    _typed(row, KisPaperPortfolioPreviewInstrument, "reads_invalid")
    _typed(snapshot.identity, KisPaperAccountIdentity, "reads_invalid")
    _typed(snapshot.open_orders, KisPaperOpenOrdersSnapshot, "reads_invalid")
    _need(
        (row.symbol, row.exchange) == ("SPY", "AMEX") and snapshot.open_orders.complete is True,
        "account_incomplete",
    )
    _typed(row.quote, KisPaperSpyLimitInput, "quote_invalid")
    times = [
        reads.started_at,
        reads.completed_at,
        snapshot.captured_at,
        snapshot.identity.captured_at,
        snapshot.open_orders.captured_at,
        row.quote.quoted_at,
    ]
    _need(
        contract.point_available_at <= reads.started_at <= reads.completed_at <= at,
        "reads_clock_invalid",
    )
    expected = sum(
        (
            Fraction(s.quantity)
            for s in projection.stocks_by_instrument
            if (s.symbol, s.exchange) == ("SPY", "AMEX")
        ),
        Fraction(0),
    )
    seen = []
    for position in snapshot.positions:
        _typed(position, KisPaperPosition, "position_invalid")
        times.append(position.captured_at)
        if position.symbol == "SPY":
            _need(
                position.exchange == "AMEX" and position.currency == "USD",
                "target_inventory_mismatch",
            )
            seen.append(_amount(position.quantity, whole=True))
    _need(len(seen) <= 1 and sum(seen, Fraction(0)) == expected, "target_inventory_mismatch")
    for order in snapshot.open_orders.orders:
        times.append(order.captured_at)
        _need(order.symbol != "SPY", "target_order_pending")
    if buy:
        _typed(row.cash, KisPaperCashSnapshot, "funds_invalid")
        _typed(row.orderable, KisPaperOrderableFundsSnapshot, "funds_invalid")
        _need(
            row.cash.currency == row.orderable.currency == "USD"
            and (
                row.orderable.reference_symbol,
                row.orderable.reference_exchange,
                row.orderable.reference_price,
            )
            == ("SPY", "AMEX", row.buy_limit),
            "orderability_binding_changed",
        )
        times.extend((row.cash.captured_at, row.orderable.captured_at))
    _need(
        all(timedelta(0) <= at - require_utc(t) <= timedelta(seconds=120) for t in times),
        "reads_stale",
    )
    return row


def _control(contract, plan, binding, *, phase):
    return dict(
        schema=_SCHEMA,
        phase=phase,
        contract=contract.to_dict(),
        contract_ref=contract.fingerprint,
        plan=copy.deepcopy(plan),
        plan_ref=_hash(plan),
        prior_plan_refs=[_hash(p) for p in _plans(binding)],
        exit_at=contract.exit_starts_at.isoformat(),
        exit_until=contract.exit_ends_at.isoformat(),
    )


def _checked_control(control, contract, phase):
    _need(
        type(control) is dict
        and set(control)
        == {
            "schema",
            "phase",
            "contract",
            "contract_ref",
            "plan",
            "plan_ref",
            "prior_plan_refs",
            "exit_at",
            "exit_until",
        }
        and control["schema"] == _SCHEMA
        and control["phase"] == phase
        and control["contract"] == contract.to_dict()
        and control["contract_ref"] == contract.fingerprint
        and control["plan_ref"] == _hash(control["plan"])
        and control["exit_at"] == contract.exit_starts_at.isoformat()
        and control["exit_until"] == contract.exit_ends_at.isoformat(),
        "control_binding_changed",
    )
    plan = control["plan"]
    _need(
        plan["input_ref"] == contract.fingerprint and len(plan["states"]) == 1,
        "control_plan_changed",
    )
    seed = canary.KisPaperCanaryState.from_dict(next(iter(plan["states"].values())))
    expected_request = contract.request_id if phase == "entry" else _exit_request(contract)
    start, end = (
        (contract.entry_starts_at, contract.entry_ends_at)
        if phase == "entry"
        else (contract.exit_starts_at, contract.exit_ends_at)
    )
    _need(
        plan["request_id"] == expected_request
        and (seed.intent.symbol, seed.intent.exchange, seed.intent.side)
        == ("SPY", "AMEX", "buy" if phase == "entry" else "sell")
        and start <= seed.intent.created_at < seed.intent.valid_until <= end
        and seed.intent.valid_until <= seed.intent.created_at + budget._ORDER_LIFETIME
        and seed
        == canary.KisPaperCanaryState(
            seed.intent, "intent_recorded", seed.intent.created_at, "preview"
        ),
        "control_seed_changed",
    )
    return plan


def _result(binding, control, status, reason):
    plan = control["plan"]
    seeds = budget._portfolio_seed_states(binding)
    intents = tuple(seeds[run].intent for run in plan["states"])
    return SingleEtfLegPlan(
        status,
        reason,
        copy.deepcopy(dict(binding)),
        copy.deepcopy(control),
        intents,
        control["plan_ref"],
    )


def _history(binding, control):
    prefix = []
    for plan in _plans(binding):
        if plan["request_id"] == control["plan"]["request_id"]:
            break
        prefix.append(_hash(plan))
    _need(prefix == control["prior_plan_refs"], "prior_plan_history_changed")


def build_single_etf_entry_plan(
    *,
    binding,
    states,
    contract,
    expected_owner_refs,
    expected_binding_ref,
    reads=None,
    as_of,
    control=None,
):
    """One pure canonical reservation; a retained request never sizes again."""
    at = require_utc(as_of)
    replayed, proofs, projection = _scope(binding, states, contract, expected_owner_refs, at)
    _ref(expected_binding_ref)
    retained = _find(binding, contract.request_id)
    if control is not None:
        original = _checked_control(control, contract, "entry")
        _history(binding, control)
        _need(
            original["request_id"] == contract.request_id
            and original["parent_binding_ref"] == expected_binding_ref,
            "request_conflict",
        )
        if retained is not None:
            _need(retained == original, "request_conflict")
            return _result(binding, control, "replayed", "exact_entry_identity_retained")
        _need(_hash(binding) == expected_binding_ref, "staged_parent_changed")
        updated = _append(binding, original, states, contract, at)
        return _result(updated, control, "prepared", "staged_entry_identity_retained")
    _need(retained is None, "exit_duty_missing")
    _need(_hash(binding) == expected_binding_ref, "parent_binding_changed")
    _need(contract.entry_starts_at <= at < contract.entry_ends_at, "entry_window_closed")
    if contract.action != "enter" or contract.target_exposure == 0:
        return SingleEtfLegPlan("no_intent", "no_entry_signal")
    owner = "portfolio-spy"
    owned = next((s for s in projection.stocks_by_owner if s.owner_ref == owner), None)
    for original_owner, _ in budget._owners(binding):
        if original_owner.owner_ref == owner:
            _need(
                all(
                    budget._terminal(replayed[r.run_id], proofs.get(r.run_id))
                    for r in original_owner.state_refs
                ),
                "same_owner_pending",
            )
    row = _account(reads, contract, projection, at, buy=True)
    limit = _buy_limit(row.quote)
    _need(_amount(row.buy_limit, positive=True) == limit, "buy_limit_changed")
    target = Fraction(budget._basis(binding).basis_usd) * Fraction(contract.target_exposure)
    quantity_target = target // limit
    quantity_owned = Fraction(0) if owned is None else Fraction(owned.quantity)
    reserved = Fraction(projection.reserved_buys)
    capacity = min(
        Fraction(projection.remaining_cap),
        Fraction(projection.remaining_gross_cash),
        max(Fraction(0), _amount(row.cash.available_cash) - reserved),
        max(Fraction(0), _amount(row.orderable.orderable_funds) - reserved),
    )
    quantity = int(min(max(Fraction(0), quantity_target - quantity_owned), capacity // limit))
    if quantity == 0:
        return SingleEtfLegPlan("no_intent", "whole_share_capacity_or_target_satisfied")
    until = min(contract.entry_ends_at, at + budget._ORDER_LIFETIME)
    identity = budget._digest(
        [contract.account_ref, contract.basis_ref, contract.request_id, "SPY"]
    )
    price = budget._exact_decimal(limit)
    intent = canary.KisPaperCanaryIntent(
        "bp-" + identity,
        "portfolio-" + identity,
        "portfolio-" + identity,
        "SPY",
        "AMEX",
        Decimal(quantity),
        price,
        at,
        until,
        price_contract_ref=_hash([contract.fingerprint, "SPY", str(price)]),
    )
    plan = dict(
        request_id=contract.request_id,
        input_ref=contract.fingerprint,
        parent_binding_ref=expected_binding_ref,
        states={
            intent.run_id: canary.KisPaperCanaryState(
                intent, "intent_recorded", at, "preview"
            ).to_dict()
        },
    )
    duty = _control(contract, plan, binding, phase="entry")
    return _result(
        _append(binding, plan, states, contract, at),
        duty,
        "prepared",
        "canonical_entry_and_H20_duty_prepared",
    )


def _exit_request(contract):
    return "portfolio-sell-" + budget._digest([_SCHEMA, contract.fingerprint])


def _lot_interference(binding, contract):
    after_entry = False
    for plan in _plans(binding):
        if plan["request_id"] == contract.request_id:
            after_entry = True
            continue
        if after_entry and plan["request_id"] != _exit_request(contract):
            _need(
                not any(
                    p["intent"]["symbol"] == "SPY" and p["intent"].get("side", "buy") == "sell"
                    for p in plan["states"].values()
                ),
                "same_owner_lot_interference",
            )


def build_single_etf_exit_plan(
    *,
    binding,
    states,
    contract,
    entry_control,
    expected_owner_refs,
    expected_binding_ref,
    reads=None,
    as_of,
    control=None,
):
    """Prepare only this entry lot; unknown entry/foreign same-owner sales defer."""
    at = require_utc(as_of)
    replayed, proofs, projection = _scope(binding, states, contract, expected_owner_refs, at)
    entry = _checked_control(entry_control, contract, "entry")
    _history(binding, entry_control)
    _need(_find(binding, contract.request_id) == entry, "entry_binding_changed")
    run = next(iter(entry["states"]))
    state = replayed[run]
    _need(
        state.intent == canary.KisPaperCanaryState.from_dict(entry["states"][run]).intent,
        "entry_identity_changed",
    )
    request = _exit_request(contract)
    if control is not None:
        plan = _checked_control(control, contract, "exit")
        _history(binding, control)
        _need(
            plan["request_id"] == request and plan["parent_binding_ref"] == expected_binding_ref,
            "request_conflict",
        )
        existing = _find(binding, request)
        if existing is not None:
            _need(existing == plan, "request_conflict")
            return _result(binding, control, "replayed", "exact_exit_identity_retained")
        _need(_hash(binding) == expected_binding_ref, "staged_parent_changed")
        return _result(
            _append(binding, plan, states, contract, at),
            control,
            "prepared",
            "staged_exit_identity_retained",
        )
    _need(_find(binding, request) is None, "exit_control_missing")
    _need(_hash(binding) == expected_binding_ref, "parent_binding_changed")
    _need(contract.exit_starts_at <= at < contract.exit_ends_at, "exit_window_closed")
    _need(budget._terminal(state, proofs.get(run)), "entry_outcome_unknown")
    fill = state.current_fill
    if fill is None or fill.quantity == 0:
        return SingleEtfLegPlan("no_intent", "no_verified_owned_entry_fill")
    _lot_interference(binding, contract)
    row = _account(reads, contract, projection, at, buy=False)
    price = derive_kis_paper_marketable_limit(row.quote, side="sell", observed_at=at)
    reductions = {s: Decimal(0) for s, _ in budget._PORTFOLIO_INSTRUMENTS}
    reductions["SPY"] = fill.quantity
    result = build_kis_paper_portfolio_sell_plan(
        binding=binding,
        states=states,
        expected_account_ref=contract.account_ref,
        expected_basis_ref=contract.basis_ref,
        expected_owner_refs=expected_owner_refs,
        expected_binding_ref=expected_binding_ref,
        request_id=request,
        input_ref=contract.fingerprint,
        reductions_by_symbol=reductions,
        limits_by_symbol={"SPY": price},
        as_of=at,
        valid_until=min(contract.exit_ends_at, at + budget._ORDER_LIFETIME),
    )
    _need(result.status == "prepared", "native_exit_not_prepared")
    plan = _find(result.binding, request)
    return _result(
        result.binding,
        _control(contract, plan, binding, phase="exit"),
        "prepared",
        "exact_owned_H20_exit_prepared",
    )


def _ordinary(path):
    _need(
        not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
        "private_path_invalid",
    )
    if path.is_file():
        _need(path.stat().st_nlink == 1, "private_path_invalid")


def _control_path(root, contract, phase):
    return root / (".single-etf-" + budget._digest(contract.request_id) + "-" + phase + ".json")


def reserve_single_etf_leg(
    *,
    state_root,
    repository_root,
    artifact_root,
    contract,
    phase,
    expected_owner_refs,
    expected_binding_ref,
    as_of,
    reads=None,
):
    """Persist duty/control FIRST then the existing bank seed, with exact resume.

    No broker operation is exposed. A pre-bank crash leaves a staged control,
    which can resume only its original parent; it is never silently resized.
    """
    _need(phase in {"entry", "exit"}, "phase_invalid")
    root = Path(state_root)
    _ordinary(root)
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root))
    path = _control_path(root, contract, phase)
    _ordinary(path)
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            _ordinary(path)
            _ordinary(root / budget.BUDGET_FILE)
            binding = budget._load_binding(root, contract.account_ref)
            _need(binding is not None, "existing_bank_required")
            states = _states(root, binding)
            control = budget._read_json(path)
            args = dict(
                binding=binding,
                states=states,
                contract=contract,
                expected_owner_refs=expected_owner_refs,
                expected_binding_ref=expected_binding_ref,
                as_of=as_of,
                reads=reads,
                control=control,
            )
            if phase == "entry":
                result = build_single_etf_entry_plan(**args)
            else:
                entry_path = _control_path(root, contract, "entry")
                _ordinary(entry_path)
                result = build_single_etf_exit_plan(
                    **args, entry_control=budget._read_json(entry_path)
                )
            if result.status != "prepared":
                return result
            if control is None:
                budget._atomic_json(path, result.control)
            _need(budget._read_json(path) == result.control, "control_readback_changed")
            budget._atomic_json(root / budget.BUDGET_FILE, result.binding)
            retained = budget._load_binding(root, contract.account_ref)
            _need(retained == result.binding, "bank_readback_changed")
            budget.project_budget(root, retained, as_of=as_of)
            return replace(result, status="reserved", reason="duty_and_canonical_seed_persisted")


def single_etf_execution_binding(
    *,
    state_root,
    contract,
    phase,
    expected_control_ref,
    expected_binding_ref,
    expected_owner_refs,
    as_of,
):
    """Bind an existing native executor; the host must repeat its effect guard.

    No release is implied. The existing NativeBridge must check this binding,
    original window/control and relevant ownership immediately before each wire.
    Unknown attempted requests may use exact native recovery after the window;
    fresh intent_recorded requests may not start outside it.
    """
    _need(phase in {"entry", "exit"}, "phase_invalid")
    root, at = Path(state_root), require_utc(as_of)
    path = _control_path(root, contract, phase)
    _ordinary(path)
    control = budget._read_json(path)
    _need(_hash(control) == expected_control_ref, "control_ref_changed")
    plan = _checked_control(control, contract, phase)
    binding = budget._load_binding(root, contract.account_ref)
    _need(
        _hash(binding) == expected_binding_ref and _find(binding, plan["request_id"]) == plan,
        "bank_binding_changed",
    )
    states = _states(root, binding)
    replayed, proofs, _ = _scope(binding, states, contract, expected_owner_refs, at)
    _history(binding, control)
    if phase == "exit":
        entry_path = _control_path(root, contract, "entry")
        _ordinary(entry_path)
        entry = _checked_control(budget._read_json(entry_path), contract, "entry")
        _need(_find(binding, contract.request_id) == entry, "entry_binding_changed")
        original = replayed[next(iter(entry["states"]))]
        _need(
            budget._terminal(original, proofs.get(original.intent.run_id))
            and original.current_fill is not None,
            "entry_outcome_unknown",
        )
        seed = next(iter(plan["states"].values()))
        _need(
            canary.KisPaperCanaryState.from_dict(seed).intent.quantity
            <= original.current_fill.quantity,
            "owned_entry_quantity_changed",
        )
    run = next(iter(plan["states"]))
    state = states[run]
    if state.phase == "intent_recorded":
        if phase == "exit":
            _lot_interference(binding, contract)
        start, end = (
            (contract.entry_starts_at, contract.entry_ends_at)
            if phase == "entry"
            else (contract.exit_starts_at, contract.exit_ends_at)
        )
        _need(start <= at < end and at < state.intent.valid_until, "effect_window_closed")
    return KisPaperPortfolioExecutionBinding(
        state_root=root.resolve(),
        account_ref=contract.account_ref,
        basis_ref=contract.basis_ref,
        owner_refs=tuple(sorted(expected_owner_refs.items())),
        binding_ref=expected_binding_ref,
        request_id=plan["request_id"],
        parent_binding_ref=plan["parent_binding_ref"],
        input_ref=contract.fingerprint,
        plan_ref=control["plan_ref"],
        run_id=run,
        intent_ref=state.intent.fingerprint,
    )
