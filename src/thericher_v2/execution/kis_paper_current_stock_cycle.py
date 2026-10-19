"""Owned frozen-model Paper visits over native stock custody and order APIs.

No model loading, credentials, client creation, scheduler or replacement basket.
The private checkpoint retains native dataclasses, not a second order ledger.
Caller attests immutable target bytes and official entry/fifth-session clocks.
Late actual entry is an operational baseline, not research OPEN parity.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from pathlib import Path
from types import CodeType, FunctionType, ModuleType

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.current_nas_frozen_rank_target import (
    FEATURE_SCHEMA_ID,
    FrozenScoreMetadata,
    PreparedTarget,
)
from thericher_v2.research.current20_paper_candidate import (
    ENTRY_NOT_BEFORE,
    EXIT_NOT_BEFORE,
    Current20PaperCalendar,
    Current20PaperMetadata,
    Current20PaperTarget,
    validate_current20_targets,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from . import kis_paper_stock_canary as stock_canary
from . import kis_paper_stock_execute as execution
from . import kis_paper_stock_exit_plan as exits
from . import kis_paper_stock_plan as entries
from .kis_paper_portfolio_execute import _unlinked
from .kis_paper_portfolio_plan import _replay_scope, _states
from .kis_paper_quote import KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE, KisPaperSpyLimitInput
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_paper_stock_canary import KisPaperStockCanaryClient
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
    KisPaperStockPreviewReads,
)
from .kis_paper_stock_session_recovery import plan_stock_session_recovery
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
)

POINTER = ".current-nas-stock-cycle.json"
CURRENT20_POINTER = ".current20-equalrank4-paper-20261018-v1.json"


class StockCycleProfile(Enum):
    LEGACY_NAS = "legacy_nas"
    CURRENT20_EQUALRANK4 = "current20-equalrank4-paper-20261018-v1"


_STATUSES = frozenset(
    {"inert", "hold", "no_intent", "pending", "advanced", "complete", "unavailable"}
)
_READONLY_REASONS = {
    "quote_timestamp_unavailable": "cycle_quote_timestamp_unavailable",
    "quote_timestamp_invalid": "cycle_quote_timestamp_invalid",
    "quote_timestamp_stale": "cycle_quote_timestamp_stale",
    "quote_tick_invalid": "cycle_quote_tick_invalid",
    "quote_bid_ask_invalid": "cycle_quote_bid_ask_invalid",
}
_REASONS = frozenset(
    {
        "execution_not_requested",
        "await_declared_exit",
        "outside_declared_session",
        "native_risk_no_intent",
        "cycle_target_quote_unavailable",
        "cycle_readonly_snapshot_unavailable",
        *_READONLY_REASONS.values(),
        "exact_request_retained",
        "native_leg_closed",
        "policy_owned_flat",
        "already_completed",
        "native_recovery_required",
        "cycle_reference_invalid",
        "cycle_value_invalid",
        "cycle_checkpoint_invalid",
        "cycle_existing_basis_required",
        "cycle_basis_changed",
        "cycle_client_unavailable",
        "cycle_client_invalid",
        "cycle_account_changed",
        "cycle_owner_missing",
        "cycle_foreign_stock_registration",
        "cycle_input_invalid",
        "cycle_session_invalid",
        "cycle_ten_targets_required",
        "cycle_target_invalid",
        "cycle_target_duplicate",
        "cycle_target_clock_invalid",
        "cycle_input_binding_mismatch",
        "cycle_receipt_invalid",
        "cycle_reservation_missing",
        "cycle_request_changed",
        "cycle_reservation_changed",
        "cycle_retained_quote_stale",
        "cycle_configuration_invalid",
        "cycle_target_unavailable",
        "cycle_policy_changed",
        "cycle_never_reserved_retired",
        "cycle_retirement_unproven",
        "cycle_retired_request_restored",
        "cycle_owned_not_flat",
    }
)
_TYPES = {
    cls.__name__: cls
    for cls in (
        PreparedTarget,
        Current20PaperTarget,
        Current20PaperMetadata,
        Current20PaperCalendar,
        TargetExposureProposal,
        ResearchDecisionReceipt,
        FrozenScoreMetadata,
        SessionWindow,
        KisPaperStockInstrument,
        KisPaperStockPreviewReads,
        KisPaperStockExitReads,
        KisPaperStockExitAccountSnapshot,
        KisPaperSpyLimitInput,
        KisPaperReadOnlySnapshot,
        KisPaperAccountIdentity,
        KisPaperCashSnapshot,
        KisPaperOpenOrder,
        KisPaperOpenOrdersSnapshot,
        KisPaperOrderableFundsSnapshot,
        KisPaperPosition,
    )
}


class _CycleFault(_RecoveryRequired):
    pass


def _check(ok, category):
    if not ok:
        raise _CycleFault(category)


def _pin(value):
    _check(type(value) is str and budget._SHA.fullmatch(value), "cycle_reference_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class CurrentStockCycleInput:
    targets: tuple[PreparedTarget, ...] | tuple[Current20PaperTarget, ...]
    entry_session: SessionWindow
    exit_session: SessionWindow
    input_ref: str
    policy_ref: str
    profile: StockCycleProfile = StockCycleProfile.LEGACY_NAS


@dataclass(frozen=True, slots=True, repr=False)
class CurrentStockCycleOutcome:
    status: str
    reason: str
    leg_count: int = 0

    def safe_payload(self):
        valid = self.status in _STATUSES and self.reason in _REASONS
        return dict(
            status=self.status if valid else "unavailable",
            reason=self.reason if valid else "native_recovery_required",
            leg_count=self.leg_count
            if type(self.leg_count) is int and 0 <= self.leg_count <= 1
            else 0,
        )


def _pack(value):
    """Sealed native-value codec for crash-exact private reservation arguments."""
    if type(value).__name__ in _TYPES and type(value) is _TYPES[type(value).__name__]:
        return {
            "type": type(value).__name__,
            "value": {field.name: _pack(getattr(value, field.name)) for field in fields(value)},
        }
    if type(value) in (datetime, Decimal, Fraction, tuple):
        tag = type(value).__name__
        item = (
            value.isoformat()
            if tag == "datetime"
            else str(value)
            if tag in {"Decimal", "Fraction"}
            else [_pack(v) for v in value]
        )
        return dict(type=tag, value=item)
    if type(value) is dict:
        return {key: _pack(item) for key, item in value.items()}
    _check(value is None or type(value) in (str, int, float, bool), "cycle_value_invalid")
    return value


def _unpack(value):
    if type(value) is not dict:
        return value
    if set(value) == {"type", "value"}:
        tag, item = value["type"], value["value"]
        if tag == "datetime":
            return require_utc(datetime.fromisoformat(item))
        if tag in {"Decimal", "Fraction"}:
            return (Decimal if tag == "Decimal" else Fraction)(item)
        if tag == "tuple":
            return tuple(_unpack(v) for v in item)
        _check(tag in _TYPES, "cycle_value_invalid")
        return _TYPES[tag](**{key: _unpack(v) for key, v in item.items()})
    return {key: _unpack(item) for key, item in value.items()}


@contextmanager
def _shared(root):
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            yield


def _save(path, record):
    record["ref"] = "sha256:" + budget._digest({k: v for k, v in record.items() if k != "ref"})
    budget._atomic_json(path, record)
    _check(budget._read_json(path) == record, "cycle_checkpoint_invalid")


def _book(root, account, basis=None):
    binding = budget._load_binding(root, account)
    _check(binding is not None and binding["version"] in {3, 4}, "cycle_existing_basis_required")
    _check(basis is None or binding["basis_ref"] == basis, "cycle_basis_changed")
    return binding


def _refs(binding):
    return {owner.owner_ref: ref for owner, ref in budget._owners(binding)}


def _client(factory, instrument, account):
    _check(callable(factory), "cycle_client_unavailable")
    client = factory(instrument)
    _check(
        isinstance(client, KisPaperStockCanaryClient)
        and client.instrument == instrument
        and type(client._config) is KisPaperConfig,
        "cycle_client_invalid",
    )
    config = replace(client._config)
    _check(
        budget._digest([config.base_url, config.account_number, config.account_product_code])
        == account,
        "cycle_account_changed",
    )
    return client


def _projection(root, binding, at):
    states = _states(root, binding)
    replayed, proofs = _replay_scope(binding, states)
    projection = budget.project_shared_budget(
        binding=binding,
        states=states,
        expected_account_ref=binding["account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=_refs(binding),
        as_of=at,
    )
    return states, replayed, proofs, projection


def _owned_registry(record, binding):
    for symbol, owned in record["owners"].items():
        entry = binding.get("stocks", {}).get(symbol)
        if entry is None:
            _check(
                record["pending"] is not None and record["pending"]["symbol"] == symbol,
                "cycle_owner_missing",
            )
            continue
        _check(
            entry["instrument_binding_ref"] == owned["instrument_binding_ref"],
            "cycle_foreign_stock_registration",
        )
        _check(
            all(
                owned["plans"].get(plan["request_id"]) == "sha256:" + budget._digest(plan)
                for plan in entry["plans"]
            ),
            "cycle_foreign_stock_registration",
        )
        expected = set(owned["plans"])
        if record["pending"] is not None and record["pending"]["symbol"] == symbol:
            expected.discard(record["pending"]["arguments"]["request_id"])
        _check(expected <= {p["request_id"] for p in entry["plans"]}, "cycle_owner_missing")


def _validate_input(value, at, profile=StockCycleProfile.LEGACY_NAS):
    _check(type(value) is CurrentStockCycleInput, "cycle_input_invalid")
    _check(value.profile is profile, "cycle_input_invalid")
    _pin(value.input_ref)
    _pin(value.policy_ref)
    _check(
        type(value.entry_session) is SessionWindow and type(value.exit_session) is SessionWindow,
        "cycle_session_invalid",
    )
    opened, closed = value.entry_session.open_ts, value.entry_session.close_ts
    if profile is StockCycleProfile.CURRENT20_EQUALRANK4:
        _check(ENTRY_NOT_BEFORE <= at < closed, "cycle_session_invalid")
        try:
            validate_current20_targets(value, at)
        except (ValueError, TypeError, AttributeError, KeyError):
            raise _CycleFault("cycle_target_invalid") from None
        return value
    _check(
        opened <= at < closed
        and closed < value.exit_session.open_ts
        and value.exit_session.close_ts <= opened + timedelta(days=14),
        "cycle_session_invalid",
    )
    _check(type(value.targets) is tuple and len(value.targets) == 10, "cycle_ten_targets_required")
    symbols, slots = set(), set()
    metadata = None
    for target in value.targets:
        _check(
            type(target) is PreparedTarget and type(target.slot) is int and 0 <= target.slot < 512,
            "cycle_target_invalid",
        )
        p, receipt = target.proposal, target.receipt
        _check(
            type(p) is TargetExposureProposal and type(receipt) is ResearchDecisionReceipt,
            "cycle_target_invalid",
        )
        _check(p.symbol not in symbols and target.slot not in slots, "cycle_target_duplicate")
        symbols.add(p.symbol)
        slots.add(target.slot)
        _check(
            p.market == "US"
            and p.action == "enter"
            and p.input_status == "ready"
            and p.feature_schema_id == FEATURE_SCHEMA_ID
            and p.confidence == Decimal(0)
            and p.target_exposure == Decimal(".005")
            and target.research_weight == Decimal(".05")
            and p.decided_at <= at < p.valid_until <= closed
            and opened < p.valid_until
            and type(target.mean_ordinal_rank) is Fraction,
            "cycle_target_invalid",
        )
        _check(type(target.metadata) is FrozenScoreMetadata, "cycle_target_invalid")
        target.metadata.__post_init__()
        _check(
            target.metadata.feature_window_end == p.feature_window_end < opened
            and target.metadata.score_first_available_at <= p.decided_at,
            "cycle_target_clock_invalid",
        )
        metadata = target.metadata if metadata is None else metadata
        _check(target.metadata == metadata, "cycle_input_binding_mismatch")
        refs = DecisionReceiptReferences(
            receipt.campaign_ref,
            receipt.model_ref,
            receipt.input_manifest_ref,
            receipt.proposal_ref,
        )
        _check(
            receipt_from_target_exposure_proposal(p, references=refs) == receipt,
            "cycle_receipt_invalid",
        )
        KisPaperStockInstrument(p.symbol, receipt.instrument_binding_ref)
    return value


def _proof(root, binding, pending):
    args = _unpack(pending["arguments"])
    instrument = args["instrument"]
    entry = binding.get("stocks", {}).get(instrument.symbol)
    _check(entry is not None, "cycle_reservation_missing")
    plan = next((p for p in entry["plans"] if p["request_id"] == args["request_id"]), None)
    _check(
        plan is not None and "sha256:" + budget._digest(plan) == pending["plan_ref"],
        "cycle_request_changed",
    )
    _check(len(plan["states"]) == 1, "cycle_request_changed")
    seed = canary.KisPaperCanaryState.from_dict(next(iter(plan["states"].values())))
    proof = execution.KisPaperStockExecutionBinding(
        state_root=root,
        instrument=instrument,
        account_ref=binding["account_ref"],
        basis_ref=binding["basis_ref"],
        owner_refs=tuple(_refs(binding).items()),
        binding_ref="sha256:" + budget._digest(binding),
        request_id=plan["request_id"],
        parent_binding_ref=plan["parent_binding_ref"],
        input_ref=plan["input_ref"],
        plan_ref=pending["plan_ref"],
        run_id=seed.intent.run_id,
        intent_ref=seed.intent.fingerprint,
        side=pending["side"],
    )
    return proof, seed


def _request_absent(root, binding, pending):
    args = _unpack(pending["arguments"])
    seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
    plan = dict(
        request_id=args["request_id"],
        input_ref=args["input_ref"],
        parent_binding_ref=args["expected_binding_ref"],
        states={seed.intent.run_id: pending["seed"]},
    )
    _check("sha256:" + budget._digest(plan) == pending["plan_ref"], "cycle_retirement_unproven")
    plans = list(binding["portfolio"]["plans"])
    plans.extend(p for entry in binding.get("stocks", {}).values() for p in entry["plans"])
    _check(
        not any(
            p["request_id"] == args["request_id"] or seed.intent.run_id in p["states"]
            for p in plans
        )
        and all(
            ref.run_id != seed.intent.run_id
            for owner, _ in budget._owners(binding)
            for ref in owner.state_refs
        ),
        "cycle_retirement_unproven",
    )
    path = root / (seed.intent.run_id + ".json")
    _unlinked(path)
    _unlinked(path.with_name("." + path.name + ".lock"))
    _check(not path.exists(), "cycle_retirement_unproven")
    return path


def _retired_absent(root, record):
    with _shared(root):
        binding = _book(root, record["account_ref"], record["basis_ref"])
        for retired in record.get("retired", []):
            try:
                _request_absent(root, binding, retired["pending"])
            except _CycleFault:
                raise _CycleFault("cycle_retired_request_restored") from None


def _retire_never_reserved(root, record, clock, pointer=None):
    """Retire only the journal, never a canonical reservation or order state."""
    pending = record["pending"]
    args = _unpack(pending["arguments"])
    with _shared(root):
        binding = _book(root, record["account_ref"], record["basis_ref"])
        parent_changed = "sha256:" + budget._digest(binding) != args["expected_binding_ref"]
        at = require_utc(clock())
        if not parent_changed and at < args["valid_until"]:
            return False
        _check(pending.get("reservation_confirmed") is False, "cycle_retirement_unproven")
        path = _request_absent(root, binding, pending)
        with canary.exclusive_kis_paper_canary_state_lock(path):
            _request_absent(root, binding, pending)
            _projection(root, binding, at)
            symbol = pending["symbol"]
            owned = record["owners"][symbol]
            _check(
                owned["plans"].pop(args["request_id"]) == pending["plan_ref"],
                "cycle_retirement_unproven",
            )
            if not owned["plans"]:
                _check(symbol not in binding.get("stocks", {}), "cycle_retirement_unproven")
                del record["owners"][symbol]
            record.setdefault("retired", []).append(
                dict(
                    pending=pending,
                    at=at.isoformat(),
                    canonical_binding_ref="sha256:" + budget._digest(binding),
                    reason="parent_changed_no_reservation"
                    if parent_changed
                    else "expired_no_reservation",
                )
            )
            if pending["side"] == "buy":
                record["active"]["entries_done"].append(symbol)
            record["pending"] = None
            _save(pointer if pointer is not None else root / POINTER, record)
            return True


def _current_exit_session(at, earliest):
    if at < earliest.open_ts:
        return None
    official = us_equity_2026_session(at.astimezone(US_EQUITY_EASTERN).date())
    if official is None or not official.window.open_ts <= at < official.window.close_ts:
        return None
    return official.window


def _completed_flat(root, record, at):
    """Validate retained native ownership, never claim a fresh broker snapshot."""
    with _shared(root):
        binding = _book(root, record["account_ref"], record["basis_ref"])
        _owned_registry(record, binding)
        _, replayed, proofs, projection = _projection(root, binding, at)
        owner_ids = {
            budget._stock_owner_id(v["instrument_binding_ref"]) for v in record["owners"].values()
        }
        stocks = [s for s in projection.stocks_by_owner if s.owner_ref in owner_ids]
        _check(
            {s.owner_ref for s in stocks} == owner_ids and all(s.quantity == 0 for s in stocks),
            "cycle_owned_not_flat",
        )
        _check(
            all(
                ref.run_id in binding["terminal_evidence"]
                and budget._terminal(replayed[ref.run_id], proofs.get(ref.run_id))
                for owner, _ in budget._owners(binding)
                if owner.owner_ref in owner_ids
                for ref in owner.state_refs
            ),
            "cycle_owned_not_flat",
        )


def _recover(record, root, paths, client_factory, clock, pointer=None):
    pending = record["pending"]
    args = _unpack(pending["arguments"])
    binding = _book(root, record["account_ref"], record["basis_ref"])
    _owned_registry(record, binding)
    plans = binding.get("stocks", {}).get(pending["symbol"], {}).get("plans", [])
    if not any(p["request_id"] == args["request_id"] for p in plans):
        if _retire_never_reserved(root, record, clock, pointer):
            return CurrentStockCycleOutcome("no_intent", "cycle_never_reserved_retired", 1)
        reserve = (
            entries.reserve_kis_paper_stock_plan
            if pending["side"] == "buy"
            else exits.reserve_kis_paper_stock_exit_plan
        )
        result = reserve(
            **{k: paths[k] for k in ("state_root", "repository_root", "artifact_root")}, **args
        )
        _check(result.plan_ref == pending["plan_ref"], "cycle_reservation_changed")
        binding = _book(root, record["account_ref"], record["basis_ref"])
    proof, seed = _proof(root, binding, pending)
    pending["reservation_confirmed"] = True
    _save(pointer if pointer is not None else root / POINTER, record)
    _, states, state, projection = execution._scope(root, proof, require_utc(clock()))
    session = _unpack(pending["session"])
    directive = plan_stock_session_recovery(
        proof=proof,
        seed=seed,
        state=state,
        session_open=session.open_ts,
        session_close=session.close_ts,
        as_of=require_utc(clock()),
    )
    if directive.action == "expired_unsubmitted":
        with _shared(root):
            at = require_utc(clock())
            _, _, state, _ = execution._scope(root, proof, at)
            _check(
                state.intent == seed.intent
                and state.phase == "intent_recorded"
                and state.submission_started_at is None
                and state.submitted_at is None
                and state.broker_order_id is None
                and state.cumulative_fill is None
                and at >= state.intent.valid_until,
                "cycle_request_changed",
            )
            store = canary.KisPaperCanaryStateStore(root / (proof.run_id + ".json"))
            store.record_intent(seed.intent, cancel_after_submit=False, now=at)
            store.transition(
                seed.intent,
                expected=frozenset({"intent_recorded"}),
                phase="intent_recorded",
                reason_code="intent_expired",
                now=at,
            )
    else:
        if state.phase == "intent_recorded":
            _check(
                require_utc(clock()) - args["reads"].quote.quoted_at
                <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
                "cycle_retained_quote_stale",
            )
        client = _client(client_factory, proof.instrument, proof.account_ref)
        execution._client_account(client, proof)
        operation = (
            execution.execute_kis_paper_stock_buy
            if proof.side == "buy"
            else execution.execute_kis_paper_stock_sell
        )
        operation(proof=proof, client=client, clock=clock, execute=True, **paths)
        # This is a connected native visit, never an offline observe reader.
        with _shared(root):
            binding = _book(root, record["account_ref"], record["basis_ref"])
            proof, seed = _proof(root, binding, pending)
            _, _, state, projection = execution._scope(root, proof, require_utc(clock()))
            observation_started = require_utc(clock())
            rec = client.reconcile(state, now=observation_started)
            store = canary.KisPaperCanaryStateStore(root / (proof.run_id + ".json"))
            state = canary._record_reconciliation_fill(
                store, state, rec, observed_at=require_utc(clock())
            )
            reads = (
                client.stock_preview_snapshot(expected_account_ref=proof.account_ref, clock=clock)
                if proof.side == "buy"
                else client.stock_exit_snapshot(expected_account_ref=proof.account_ref, clock=clock)
            )
            # This composite read spans the real reconciliation and quote calls;
            # keep its exact account snapshot, not a later unrelated observation.
            reads = replace(reads, snapshot=rec.snapshot, started_at=observation_started)
            _, _, state, projection = execution._scope(root, proof, require_utc(clock()))
            directive = plan_stock_session_recovery(
                proof=proof,
                seed=seed,
                state=state,
                session_open=session.open_ts,
                session_close=session.close_ts,
                as_of=require_utc(clock()),
                reads=reads,
                reconciliation=rec,
                projection=projection,
            )
            if directive.action == "cancel_exact_expired" and pending["visited"]:
                state, rec = canary._cancel_submitted_canary(
                    client=client,
                    state_store=store,
                    state=state,
                    reconciliation=rec,
                    observed_at=require_utc(clock()),
                )
            pending["visited"] = True
            observation = rec.execution
            proofs = (
                {proof.run_id: observation}
                if observation is not None and budget._terminal(state, observation)
                else {}
            )
    if directive.action == "expired_unsubmitted":
        proofs = {}
    binding = _book(root, record["account_ref"], record["basis_ref"])
    proof, _ = _proof(root, binding, pending)
    reconcile = (
        entries.reconcile_kis_paper_stock_plan
        if proof.side == "buy"
        else exits.reconcile_kis_paper_stock_exit_plan
    )
    result = reconcile(
        **{k: paths[k] for k in ("state_root", "repository_root", "artifact_root")},
        expected_account_ref=proof.account_ref,
        expected_basis_ref=proof.basis_ref,
        expected_owner_refs=dict(proof.owner_refs),
        expected_binding_ref=proof.parent_binding_ref,
        request_id=proof.request_id,
        input_ref=proof.input_ref,
        instrument=proof.instrument,
        expected_plan_ref=proof.plan_ref,
        as_of=require_utc(clock()),
        cancellation_proofs=proofs,
    )
    if result.status == "reconciled":
        if proof.side == "buy":
            record["active"]["entries_done"].append(pending["symbol"])
        record["pending"] = None
    return CurrentStockCycleOutcome(
        "pending" if record["pending"] else "advanced",
        "exact_request_retained" if record["pending"] else "native_leg_closed",
        1,
    )


def run_kis_paper_current_stock_cycle(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    execution_control_path: Path,
    expected_account_ref: str,
    expected_input_ref: str | None = None,
    expected_policy_ref: str | None = None,
    target_loader: Callable[[], CurrentStockCycleInput] | None = None,
    client_factory: Callable | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    execute: bool = False,
    profile: StockCycleProfile = StockCycleProfile.LEGACY_NAS,
    first_failure_sink: Callable[[dict], None] | None = None,
) -> CurrentStockCycleOutcome:
    """One pending leg/visit; exact retained recovery precedes target_loader.

    Operational exit eligibility starts at declared fifth-session OPEN, not
    research fifth-CLOSE parity. After exact pending recovery, new owned SELLs
    use the current local official 2026 regular session until policy-owned flat.
    No new BUY follows entry close; no pending identity/TTL is renewed.
    Optional paired input/policy identity hints are not permission: they avoid
    loading expired targets only for a natively revalidated completed flat cycle.
    """
    if execute is False:
        return CurrentStockCycleOutcome("inert", "execution_not_requested")
    leg_count = 0
    try:
        _check(type(execute) is bool and callable(clock), "cycle_configuration_invalid")
        _check(type(profile) is StockCycleProfile, "cycle_input_invalid")
        current20 = profile is StockCycleProfile.CURRENT20_EQUALRANK4
        if current20:
            _pin(expected_input_ref)
            _pin(expected_policy_ref)
        root = Path(state_root)
        paths = dict(
            state_root=root,
            repository_root=Path(repository_root),
            artifact_root=Path(artifact_root),
            runtime_projection_path=Path(runtime_projection_path),
            paper_account_snapshot_path=Path(paper_account_snapshot_path),
            emergency_state_path=Path(emergency_state_path),
            execution_control_path=Path(execution_control_path),
        )
        for path in paths.values():
            _unlinked(path)
        root = root.resolve()
        paths["state_root"] = root
        budget._validate_paths(
            root,
            paths["repository_root"],
            paths["artifact_root"],
            paths["runtime_projection_path"],
            paths["paper_account_snapshot_path"],
            paths["emergency_state_path"],
            paths["execution_control_path"],
        )
        pointer = root / (CURRENT20_POINTER if current20 else POINTER)
        lock = root / (".current20_equalrank4_worker" if current20 else ".current_nas_stock_worker")
        for path in (pointer, lock.with_name("." + lock.name + ".lock")):
            _unlinked(path)
        with canary.exclusive_kis_paper_canary_state_lock(lock):
            record = budget._read_json(pointer)
            packed_paths = {k: str(v.resolve()) for k, v in paths.items()}
            binding = _book(root, expected_account_ref)
            if record is not None:
                _check(
                    record.get("profile") == profile.value
                    if current20 else "profile" not in record,
                    "cycle_checkpoint_invalid",
                )
                _check(
                    record["ref"]
                    == "sha256:" + budget._digest({k: v for k, v in record.items() if k != "ref"})
                    and record["paths"] == packed_paths
                    and record["account_ref"] == expected_account_ref
                    and record["basis_ref"] == binding["basis_ref"],
                    "cycle_checkpoint_invalid",
                )
                if current20:
                    _check(
                        record["policy_ref"] == expected_policy_ref
                        and record.get("input_ref") == expected_input_ref
                        and (record["active"] is None
                             or record["active"]["input_ref"] == expected_input_ref)
                        and (record["pending"] is None
                             or _unpack(record["pending"]["arguments"])["input_ref"]
                             == expected_input_ref),
                        "cycle_input_binding_mismatch",
                    )
                _owned_registry(record, binding)
                _retired_absent(root, record)
                if record["pending"] is not None:
                    leg_count = 1
                    result = (
                        _recover(record, root, paths, client_factory, clock, pointer)
                        if current20 else _recover(record, root, paths, client_factory, clock)
                    )
                    _save(pointer, record)
                    return result
            at = require_utc(clock())
            if expected_input_ref is not None or expected_policy_ref is not None:
                _pin(expected_input_ref)
                _pin(expected_policy_ref)
                if (
                    record is not None
                    and record["active"] is None
                    and expected_input_ref in record["completed"]
                    and expected_policy_ref == record["policy_ref"]
                ):
                    _completed_flat(root, record, at)
                    return CurrentStockCycleOutcome("complete", "already_completed")
            if record is None or record["active"] is None:
                _check(callable(target_loader), "cycle_target_unavailable")
                value = target_loader()
                _check(type(value) is CurrentStockCycleInput, "cycle_input_invalid")
                _check(
                    expected_input_ref is None
                    or (
                        value.input_ref == expected_input_ref
                        and value.policy_ref == expected_policy_ref
                    ),
                    "cycle_input_binding_mismatch",
                )
                if record is not None and value.input_ref in record["completed"]:
                    _check(value.policy_ref == record["policy_ref"], "cycle_policy_changed")
                    _completed_flat(root, record, at)
                    return CurrentStockCycleOutcome("complete", "already_completed")
                value = _validate_input(value, at, profile)
                if record is None:
                    record = dict(
                        version=1,
                        paths=packed_paths,
                        account_ref=expected_account_ref,
                        basis_ref=binding["basis_ref"],
                        policy_ref=value.policy_ref,
                        owners={},
                        active=None,
                        completed=[],
                        pending=None,
                    )
                    if current20:
                        record.update(profile=profile.value, input_ref=value.input_ref)
                _check(record["policy_ref"] == value.policy_ref, "cycle_policy_changed")
                if value.input_ref in record["completed"]:
                    _completed_flat(root, record, at)
                    return CurrentStockCycleOutcome("complete", "already_completed")
                _check(
                    current20 or all(
                        t.proposal.symbol not in binding.get("stocks", {})
                        or t.proposal.symbol in record["owners"]
                        for t in value.targets
                    ),
                    "cycle_foreign_stock_registration",
                )
                record["active"] = dict(
                    input_ref=value.input_ref,
                    targets=_pack(value.targets),
                    entry_session=_pack(value.entry_session),
                    exit_session=_pack(value.exit_session),
                    entries_done=[],
                    exit_attempts=0,
                )
                _save(pointer, record)
            active = record["active"]
            targets = _unpack(active["targets"])
            entry_session, exit_session = (
                _unpack(active[k]) for k in ("entry_session", "exit_session")
            )
            exit_eligible = EXIT_NOT_BEFORE if current20 else exit_session.open_ts
            side = "sell" if at >= exit_eligible else "buy"
            session = _current_exit_session(at, exit_session) if side == "sell" else entry_session
            if side == "buy" and at >= entry_session.close_ts:
                return CurrentStockCycleOutcome("hold", "await_declared_exit")
            if session is None or not session.open_ts <= at < session.close_ts:
                return CurrentStockCycleOutcome("hold", "outside_declared_session")
            binding = _book(root, expected_account_ref, record["basis_ref"])
            _owned_registry(record, binding)
            states, _, _, projection = _projection(root, binding, at)
            quantities = {
                s.symbol: s.quantity
                for s in projection.stocks_by_owner
                if s.owner_ref
                in {
                    budget._stock_owner_id(v["instrument_binding_ref"])
                    for v in record["owners"].values()
                }
            }
            candidates = [
                t
                for t in targets
                if (
                    t.proposal.symbol not in active["entries_done"]
                    if side == "buy"
                    else quantities.get(t.proposal.symbol, Decimal(0)) > 0
                )
            ]
            if not candidates:
                if side == "buy":
                    return CurrentStockCycleOutcome("hold", "await_declared_exit")
                record["completed"].append(active["input_ref"])
                record["active"] = None
                _save(pointer, record)
                return CurrentStockCycleOutcome("complete", "policy_owned_flat")
            target = candidates[0]
            instrument = KisPaperStockInstrument(
                target.proposal.symbol, target.receipt.instrument_binding_ref
            )
            if side == "buy" and current20 and (
                (instrument.symbol in binding.get("stocks", {})
                 and instrument.symbol not in record["owners"])
                or projection.remaining_cap <= 0 or projection.remaining_gross_cash <= 0
            ):
                # Exclude, never adopt, replace, reweight or create a new bank.
                active["entries_done"].append(instrument.symbol)
                _save(pointer, record)
                return CurrentStockCycleOutcome("no_intent", "native_risk_no_intent")
            _check(
                instrument.symbol not in binding.get("stocks", {})
                or instrument.symbol in record["owners"],
                "cycle_foreign_stock_registration",
            )
            client = _client(client_factory, instrument, expected_account_ref)
            proposal, receipt = target.proposal, target.receipt
            if side == "sell":
                proposal = replace(
                    proposal,
                    proposal_id=proposal.proposal_id + "-exit",
                    action="exit",
                    target_exposure=Decimal(0),
                    decided_at=at,
                    valid_until=session.close_ts,
                )
                receipt = receipt_from_target_exposure_proposal(
                    proposal,
                    references=DecisionReceiptReferences(
                        receipt.campaign_ref,
                        receipt.model_ref,
                        receipt.input_manifest_ref,
                        receipt.proposal_ref,
                    ),
                )
            try:
                reads = (
                    client.stock_preview_snapshot(
                        expected_account_ref=expected_account_ref, clock=clock
                    )
                    if side == "buy"
                    else client.stock_exit_snapshot(
                        expected_account_ref=expected_account_ref, clock=clock
                    )
                )
            except KisPaperReadOnlyError as error:
                if side != "buy" or error.code != "quote_timestamp_unavailable":
                    raise
                # No plan or reservation exists here. Keep the basket, not a substitute.
                _check(record["pending"] is None, "cycle_checkpoint_invalid")
                active["entries_done"].append(instrument.symbol)
                _save(pointer, record)
                return CurrentStockCycleOutcome("no_intent", "cycle_target_quote_unavailable")
            at = require_utc(clock())
            args = dict(
                expected_account_ref=expected_account_ref,
                expected_basis_ref=binding["basis_ref"],
                expected_owner_refs=_refs(binding),
                expected_binding_ref="sha256:" + budget._digest(binding),
                request_id=("current20-" if current20 else "nas-")
                + budget._digest(
                    [
                        record["policy_ref"],
                        active["input_ref"],
                        instrument.binding_ref,
                        side,
                        active["exit_attempts"],
                        session.open_ts.isoformat(),
                    ]
                ),
                input_ref=active["input_ref"],
                instrument=instrument,
                proposal=proposal,
                receipt=receipt,
                reads=reads,
                as_of=at,
                valid_until=min(
                    proposal.valid_until, at + budget._ORDER_LIFETIME, session.close_ts
                ),
            )
            if side == "sell":
                args["expected_masked_account"] = client._config.masked_account_identity
            build = (
                entries.build_kis_paper_stock_plan
                if side == "buy"
                else exits.build_kis_paper_stock_exit_plan
            )
            result = build(binding=binding, states=states, **args)
            if result.status != "prepared":
                if side == "buy":
                    active["entries_done"].append(instrument.symbol)
                    _save(pointer, record)
                return CurrentStockCycleOutcome("no_intent", "native_risk_no_intent")
            owner = record["owners"].setdefault(
                instrument.symbol, dict(instrument_binding_ref=instrument.binding_ref, plans={})
            )
            owner["plans"][args["request_id"]] = result.plan_ref
            record["pending"] = dict(
                symbol=instrument.symbol,
                side=side,
                plan_ref=result.plan_ref,
                arguments=_pack(args),
                session=_pack(session),
                visited=False,
                reservation_confirmed=False,
                seed=budget._stock_seed_states(result.binding)[result.intents[0].run_id].to_dict(),
            )
            if side == "sell":
                active["exit_attempts"] += 1
            _save(pointer, record)
            leg_count = 1
            outcome = (
                _recover(record, root, paths, client_factory, clock, pointer)
                if current20 else _recover(record, root, paths, client_factory, clock)
            )
            _save(pointer, record)
            return outcome
    except _CycleFault as error:
        return CurrentStockCycleOutcome("unavailable", str(error), leg_count)
    except KisPaperReadOnlyError as error:
        return CurrentStockCycleOutcome(
            "unavailable",
            _READONLY_REASONS.get(error.code, "cycle_readonly_snapshot_unavailable"),
            leg_count,
        )
    except Exception as error:
        if first_failure_sink is not None:
            try:
                first_failure_sink(_first_failure_diagnostic(error))
            except Exception:
                pass
        return CurrentStockCycleOutcome("unavailable", "native_recovery_required", leg_count)


_FIRST_FAILURE_ERRORS = (
    (TypeError, "type_error"),
    (ValueError, "value_error"),
    (KeyError, "key_error"),
    (IndexError, "index_error"),
    (AttributeError, "attribute_error"),
    (RuntimeError, "runtime_error"),
    (OSError, "os_error"),
    (FileNotFoundError, "file_not_found"),
    (PermissionError, "permission_error"),
    (TimeoutError, "timeout_error"),
    (ZeroDivisionError, "zero_division"),
    (AssertionError, "assertion_error"),
)
_FIRST_FAILURE_CATEGORIES = frozenset({"unknown", *(v for _, v in _FIRST_FAILURE_ERRORS)})
_FIRST_FAILURE_MODULES = frozenset(
    {
        __name__,
        *(module.__name__ for module in (budget, canary, execution, exits, entries, stock_canary)),
        "scripts.run_kis_paper_current_stock_cycle_worker",
        "scripts.run_current20_paper_candidate_worker",
    }
)


def safe_current_stock_first_failure(value):
    """Closed side-channel metadata only; never part of the native outcome ABI."""
    if not (
        type(value) is dict
        and set(value) in ({"kind", "error_category"}, {"kind", "error_category", "frame"})
        and value["kind"] == "current-stock-first-failure-v1"
        and type(value["error_category"]) is str
        and value["error_category"] in _FIRST_FAILURE_CATEGORIES
    ):
        raise ValueError("first_failure_invalid")
    result = dict(kind="current-stock-first-failure-v1", error_category=value["error_category"])
    if "frame" in value:
        frame = value["frame"]
        if not (
            type(frame) is dict
            and set(frame) == {"module", "line"}
            and type(frame["module"]) is str
            and frame["module"] in _FIRST_FAILURE_MODULES
            and type(frame["line"]) is int
            and 1 <= frame["line"] <= 1_000_000
        ):
            raise ValueError("first_failure_invalid")
        result["frame"] = dict(module=frame["module"], line=frame["line"])
    return result


def _first_failure_diagnostic(error):
    """Category plus deepest trusted source location available, not arbitrary throw sites."""
    result = dict(
        kind="current-stock-first-failure-v1",
        error_category=next(
            (category for cls, category in _FIRST_FAILURE_ERRORS if type(error) is cls),
            "unknown",
        ),
    )
    # Use original traceback objects, never formatting, source text or exception attributes.
    codes, namespaces = _first_failure_sources()
    trace = BaseException.__traceback__.__get__(error)
    frame = None
    for _ in range(32):
        if trace is None:
            if frame is not None:
                result["frame"] = frame
            break
        module = codes.get(trace.tb_frame.f_code)
        if module is not None and trace.tb_frame.f_globals is namespaces[module]:
            line = trace.tb_lineno
            if type(line) is int and 1 <= line <= 1_000_000:
                frame = dict(module=module, line=line)
        trace = trace.tb_next
    return result


def _first_failure_sources():
    codes, namespaces = {}, {}
    sources = [(__name__, globals(), __file__, None)] + [
        (module.__name__, vars(module), module.__file__, None)
        for module in (budget, canary, execution, exits, entries, stock_canary)
    ]
    # Fixed aliases only, including the normal script entry point; never scan modules.
    for stem, aliases in (
        (
            "run_kis_paper_current_stock_cycle_worker",
            (
                "__main__",
                "current20_native_stock_worker_helpers",
                "scripts.run_kis_paper_current_stock_cycle_worker",
            ),
        ),
        (
            "run_current20_paper_candidate_worker",
            ("__main__", "scripts.run_current20_paper_candidate_worker"),
        ),
    ):
        expected = Path(__file__).resolve().parents[3] / "scripts" / (stem + ".py")
        for alias in aliases:
            module = sys.modules.get(alias)
            if type(module) is not ModuleType:
                continue
            namespace = vars(module)
            filename = namespace.get("__file__")
            if type(filename) is str and Path(filename).resolve() == expected:
                # Match code against this fixed public script, not a supplied filename.
                try:
                    with expected.open("rb") as stream:
                        source = stream.read(131073)
                    if len(source) > 131072:
                        continue
                    pending = [compile(source, filename, "exec", dont_inherit=True)]
                    allowed = set()
                    while pending:
                        code = pending.pop()
                        allowed.add(code)
                        pending.extend(c for c in code.co_consts if type(c) is CodeType)
                except (OSError, SyntaxError, ValueError):
                    continue
                sources.append(("scripts." + stem, namespace, filename, allowed))
                break

    def add(code, name):
        codes[code] = name
        for constant in code.co_consts:
            if type(constant) is CodeType:
                add(constant, name)

    for name, namespace, filename, allowed in sources:
        namespaces[name] = namespace
        values = list(namespace.values())
        for value in tuple(values):
            if type(value) is type:
                # Inspect raw dictionaries, never invoke class/property descriptors.
                for member in vars(value).values():
                    if type(member) in (staticmethod, classmethod):
                        values.append(member.__func__)
                    elif type(member) is FunctionType:
                        values.append(member)
        for value in values:
            if (
                type(value) is FunctionType
                and value.__globals__ is namespace
                and value.__code__.co_filename == filename
                and (allowed is None or value.__code__ in allowed)
            ):
                add(value.__code__, name)
    return codes, namespaces
