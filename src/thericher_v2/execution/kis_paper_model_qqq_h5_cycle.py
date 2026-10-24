"""Inert-by-default QQQ-H5 adapter preparation for ONE pinned model input.

Uses the existing generic Paper Canary client/lifecycle, V4 book and lock order.
No credential loader, client construction, driver, CLI or task installation.
The injected evidence provider is a TRUSTED adapter dependency: its independently
pinned source must attest stable custody and ongoing retirement/exclusion of all
legacy QQQ issuers, and obtain fresh native quote/orderability/account reads.
Matching hashes or caller-supplied projections alone do not establish that fact.

The private write-ahead record precedes seed materialization, which precedes book
publication. Only exact parent + exact nonsent seed may finish publication. A
durable possible-wire marker precedes native submission; recovery never resends
such a request, releases its reservation or substitutes a newer intent.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import require_utc
from thericher_v2.research.kis_paper_canary_intent import (
    KisPaperCanaryBuyDecision,
    KisPaperCanarySellDecision,
)

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from . import kis_paper_model_qqq_h5 as core
from .emergency import EmergencyStore, PaperExecutionControlStore
from .kis_paper_portfolio_execute import _unlinked
from .kis_paper_portfolio_plan import _states
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_paper_spy_fill_cycle import _RecoveryRequired, _validate_paths
from .kis_paper_stock_canary import KisPaperStockCanaryClient
from .kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
    KisPaperStockPreviewReads,
)
from .kis_readonly import KisPaperConfig, KisPaperReadOnlySnapshot

_SCHEMA = "qqq-h5-native-cycle-preparation-v1"
_HELD = threading.local()


def _check(ok, reason):
    if not ok:
        raise _RecoveryRequired(reason)


@dataclass(frozen=True, repr=False, kw_only=True)
class QqqH5CyclePins:
    account_ref: str
    basis_ref: str
    cycle_id: str
    input_ref: str
    policy_ref: str
    execution_source_ref: str
    provider_source_ref: str
    writer_source_ref: str
    writer_membership_ref: str
    legacy_sources: tuple[str, ...]

    def __post_init__(self):
        _check(
            type(self.account_ref) is str
            and len(self.account_ref) == 64
            and all(c in "0123456789abcdef" for c in self.account_ref),
            "qqq_h5_cycle_account_invalid",
        )
        for name in (
            "basis_ref",
            "input_ref",
            "policy_ref",
            "execution_source_ref",
            "provider_source_ref",
            "writer_source_ref",
            "writer_membership_ref",
        ):
            core._pin(getattr(self, name))
        _check(
            type(self.cycle_id) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", self.cycle_id),
            "qqq_h5_cycle_id_invalid",
        )
        _check(
            type(self.legacy_sources) is tuple
            and len(set(self.legacy_sources)) == len(self.legacy_sources),
            "qqq_h5_cycle_sources_invalid",
        )
        for source in self.legacy_sources:
            core._pin(source)


@dataclass(frozen=True, repr=False, kw_only=True)
class QqqH5CyclePaths:
    state_root: Path
    repository_root: Path
    artifact_root: Path
    runtime_projection_path: Path
    paper_account_snapshot_path: Path
    emergency_state_path: Path
    execution_control_path: Path


@dataclass(frozen=True, repr=False)
class QqqH5EvidenceRequest:
    """Custody recovery needs no quote/funds; native reconciliation owns account/history."""

    input_ref: str
    policy_ref: str
    binding_ref: str
    custody_ref: str
    side: str
    purpose: Literal["pre_submit", "custody_reconcile"]
    observed_at: datetime


@dataclass(frozen=True, repr=False)
class QqqH5CycleEvidence:
    provider_source_ref: str
    writer_boundary: core.QqqH5WriterBoundary
    reads: KisPaperStockPreviewReads | KisPaperStockExitReads | None = None


@dataclass(frozen=True)
class QqqH5CycleOutcome:
    status: str
    reason: str
    next_due: datetime | None = None

    @property
    def runtime_authorized(self):
        """Source preparation/opt-in is not deployment or actual host proof."""
        return False


@contextmanager
def _shared(root):
    _check(getattr(_HELD, "root", None) is None, "qqq_h5_cycle_recursive_visit")
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            _HELD.root = root.resolve()
            try:
                yield
            finally:
                _HELD.root = None


@contextmanager
def _require_shared(root):
    # The native callback is synchronous inside _shared. Reopening the same
    # Windows byte lock on a second handle deadlocks even with Python's RLock.
    _check(getattr(_HELD, "root", None) == root.resolve(), "qqq_h5_cycle_locks_not_held")
    yield


def _ordinary(path):
    _unlinked(path)
    if path.exists():
        info = path.stat()
        _check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "qqq_h5_cycle_file_invalid")


def _paths(paths, pins):
    _check(type(paths) is QqqH5CyclePaths, "qqq_h5_cycle_paths_invalid")
    values = tuple(vars(paths).values())
    _check(
        all(isinstance(p, Path) and p.is_absolute() for p in values), "qqq_h5_cycle_paths_invalid"
    )
    for path in values:
        _unlinked(path)
    _validate_paths(
        paths.state_root,
        paths.repository_root,
        paths.artifact_root,
        paths.runtime_projection_path,
        paths.paper_account_snapshot_path,
        paths.emergency_state_path,
        paths.execution_control_path,
    )
    for path in values[3:]:
        _ordinary(path)
    _check(len({p.resolve() for p in values[3:]}) == 4, "qqq_h5_cycle_path_alias")
    pointer = paths.state_root / ("h5qqq-" + pins.input_ref[7:] + ".json")
    _ordinary(pointer)
    _ordinary(paths.state_root / budget.BUDGET_FILE)
    return pointer


def _owner_refs(binding):
    return {o.owner_ref: ref for o, ref in budget._owners(binding)}


def _book(root, pins, at, *, extra=()):
    _ordinary(root / budget.BUDGET_FILE)
    binding = budget._load_binding(root, pins.account_ref)
    _check(
        binding is not None
        and binding["version"] == 4
        and binding["basis_ref"] == pins.basis_ref
        and binding["qqq"]["cycle_id"] == pins.cycle_id,
        "qqq_h5_cycle_book_identity_changed",
    )
    expected = {r["run_id"] for r in binding["qqq"]["orders"]} | set(extra)
    for path in root.glob("bq-*.json"):
        _ordinary(path)
        _check(path.stem in expected, "qqq_h5_cycle_unbound_qqq_state")
    for owner, _ in budget._owners(binding):
        for ref in owner.state_refs:
            _ordinary(root / (ref.run_id + ".json"))
    states = _states(root, binding)
    projection, replayed, proofs = core._scope(
        binding,
        states,
        pins.account_ref,
        pins.basis_ref,
        _owner_refs(binding),
        core._ref(binding),
        at,
    )
    return binding, states, projection, replayed, proofs


def _journal(record, pins):
    payload = core._canonical(record["journal"])
    journal = core.load_qqq_h5_journal(payload, expected_sha256=hashlib.sha256(payload).hexdigest())
    _check(
        (
            journal.account_ref,
            journal.basis_ref,
            journal.cycle_id,
            journal.input_ref,
            journal.policy_ref,
            journal.execution_source_ref,
        )
        == (
            pins.account_ref,
            pins.basis_ref,
            pins.cycle_id,
            pins.input_ref,
            pins.policy_ref,
            pins.execution_source_ref,
        ),
        "qqq_h5_cycle_journal_identity_changed",
    )
    return journal


def _load(pointer, pins):
    _ordinary(pointer)
    if not pointer.exists():
        return None
    payload = pointer.read_bytes()
    record = json.loads(payload, object_pairs_hook=budget._unique_budget_keys)
    _check(
        type(record) is dict
        and set(record) == {"schema", "pins_ref", "journal", "pending", "status", "ref"}
        and record["schema"] == _SCHEMA
        and record["pins_ref"] == core._ref(vars(pins))
        and record["status"] in {"active", "no_intent", "closed"}
        and record["ref"] == core._ref({k: v for k, v in record.items() if k != "ref"})
        and core._canonical(record) == payload,
        "qqq_h5_cycle_record_invalid",
    )
    journal = _journal(record, pins)
    pending = record["pending"]
    if pending is not None:
        _check(
            record["status"] == "active"
            and type(pending) is dict
            and set(pending) == {"parent", "proposed", "seed", "wire_started_at"},
            "qqq_h5_cycle_pending_invalid",
        )
        seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
        _check(
            seed.phase == "intent_recorded"
            and seed.submission_started_at is None
            and not seed.cancel_after_submit
            and seed
            == canary.KisPaperCanaryState(
                seed.intent, "intent_recorded", seed.intent.created_at, "preview"
            ),
            "qqq_h5_cycle_seed_invalid",
        )
        linked = journal.exits[-1] if seed.intent.side == "sell" else journal.entry
        _check(
            linked is not None
            and linked.run_id == seed.intent.run_id
            and linked.intent_ref == seed.intent.fingerprint,
            "qqq_h5_cycle_pending_identity_changed",
        )
        expected = copy.deepcopy(pending["parent"])
        expected["qqq"]["orders"].append(
            dict(run_id=linked.run_id, intent_ref=linked.intent_ref, closed=False)
        )
        expected["qqq"]["owner_ref"] = next(
            o.fingerprint for o, _ in budget._owners(expected) if o.owner_ref == journal.owner_id
        )
        _check(expected == pending["proposed"], "qqq_h5_cycle_proposal_changed")
        if pending["wire_started_at"] is not None:
            anchor = require_utc(datetime.fromisoformat(pending["wire_started_at"]))
            _check(
                seed.intent.created_at <= anchor < seed.intent.valid_until,
                "qqq_h5_cycle_marker_clock_invalid",
            )
    return record


def _save(pointer, record):
    _ordinary(pointer)
    record["ref"] = core._ref({k: v for k, v in record.items() if k != "ref"})
    budget._atomic_json(pointer, record)
    _check(pointer.read_bytes() == core._canonical(record), "qqq_h5_cycle_write_unverified")


def _evidence(provider, pins, value, binding, states, side, at, *, purpose, clock, pointer, record):
    _check(purpose in {"pre_submit", "custody_reconcile"}, "qqq_h5_cycle_evidence_purpose_invalid")
    evidence = provider(
        QqqH5EvidenceRequest(
            pins.input_ref,
            pins.policy_ref,
            core._ref(binding),
            core.qqq_h5_custody_ref(binding, states),
            side,
            purpose,
            at,
        )
    )
    completed_at = require_utc(clock())
    _check(completed_at >= at, "qqq_h5_cycle_provider_clock_regressed")
    _check(
        type(evidence) is QqqH5CycleEvidence
        and evidence.provider_source_ref == pins.provider_source_ref,
        "qqq_h5_cycle_evidence_source_changed",
    )
    boundary = evidence.writer_boundary
    _check(
        type(boundary) is core.QqqH5WriterBoundary
        and boundary.source_ref == pins.writer_source_ref
        and boundary.membership_ref == pins.writer_membership_ref
        and boundary.legacy_sources == pins.legacy_sources,
        "qqq_h5_cycle_writer_source_changed",
    )
    # The request attests this exact parent, not a book or journal changed
    # during synchronous IO. Never backdate completed provider facts.
    current = _book(pointer.parent, pins, completed_at)
    _check(
        _load(pointer, pins) == record and current[0] == binding and current[1] == states,
        "qqq_h5_cycle_provider_custody_changed",
    )
    core._writers(boundary, boundary.reference, current[0], current[1], value, completed_at)
    if purpose == "pre_submit":
        core._typed(
            evidence.reads,
            KisPaperStockPreviewReads if side == "buy" else KisPaperStockExitReads,
            "qqq_h5_cycle_market_reads_required",
        )
    return evidence, completed_at, current


def _client(client, pins):
    # Stock SELL snapshots require a stock-registry execution proof, not QQQ V4.
    _check(
        isinstance(client, canary.KisPaperCanaryClient)
        and not isinstance(client, KisPaperStockCanaryClient)
        and type(client._config) is KisPaperConfig,
        "qqq_h5_cycle_native_client_required",
    )
    config = replace(client._config)
    _check(
        budget._digest([config.base_url, config.account_number, config.account_product_code])
        == pins.account_ref,
        "qqq_h5_cycle_client_account_changed",
    )
    return config


def _stage(pointer, pins, plan, parent):
    record = dict(
        schema=_SCHEMA,
        pins_ref=core._ref(vars(pins)),
        journal=json.loads(core.serialize_qqq_h5_journal(plan.journal)),
        pending=None,
        status="active",
    )
    if plan.seed is not None:
        record["pending"] = dict(
            parent=parent, proposed=plan.binding, seed=plan.seed.to_dict(), wire_started_at=None
        )
    elif plan.status in {"no_intent", "closed"}:
        record["status"] = plan.status
    _save(pointer, record)
    return _load(pointer, pins)


def _nonsent(state, seed, at):
    return (
        state.intent == seed.intent
        and state.phase == "intent_recorded"
        and not state.cancel_after_submit
        and state.submission_started_at is None
        and state.submitted_at is None
        and state.broker_order_id is None
        and state.cumulative_fill is None
        and state.fill_observed_at is None
        and state.fill_observation_status == "not_observed"
        and state.submit_upstream_code is None
        and state.submit_response_category is None
        and seed.intent.created_at <= state.updated_at <= at
    )


def _materialize(pointer, record, pins, paths, value, at):
    """Finish only our self-identifying transaction; never rebase a stale book."""
    pending = record["pending"]
    seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
    root = paths.state_root
    binding, states, _, _, _ = _book(root, pins, at, extra=(seed.intent.run_id,))
    path = root / (seed.intent.run_id + ".json")
    _ordinary(path)
    store = canary.KisPaperCanaryStateStore(path)
    current = store.read()
    if binding == pending["parent"]:
        _check(pending["wire_started_at"] is None, "qqq_h5_cycle_wire_without_reservation")
        _check(current is None or current == seed, "qqq_h5_cycle_orphan_seed_changed")
        combined = dict(states) | {seed.intent.run_id: seed}
        proposed = pending["proposed"]
        projection, replayed, proofs = core._scope(
            proposed,
            combined,
            pins.account_ref,
            pins.basis_ref,
            _owner_refs(proposed),
            core._ref(proposed),
            at,
        )
        core._cohort(value, _journal(record, pins), proposed, replayed, proofs, projection)
        materialized = store.record_intent(
            seed.intent, cancel_after_submit=False, now=seed.updated_at
        )
        _check(materialized == seed and store.read() == seed, "qqq_h5_cycle_orphan_seed_changed")
        # No bank write if another owner or a fault changed the exact parent.
        _check(
            budget._load_binding(root, pins.account_ref) == pending["parent"],
            "qqq_h5_cycle_parent_changed",
        )
        budget._atomic_json(root / budget.BUDGET_FILE, proposed)
        _check(
            budget._load_binding(root, pins.account_ref) == proposed,
            "qqq_h5_cycle_reservation_unverified",
        )
    else:
        # Intervening non-QQQ writes are not rolled back. They may coexist with
        # an already published exact QQQ cohort, but cannot complete publication.
        closed = copy.deepcopy(pending["proposed"]["qqq"])
        closed["orders"][-1]["closed"] = True
        _check(
            binding["qqq"] in (pending["proposed"]["qqq"], closed), "qqq_h5_cycle_parent_changed"
        )
        _check(
            current is not None and current.intent == seed.intent,
            "qqq_h5_cycle_reserved_seed_missing_or_changed",
        )
    binding, states, projection, replayed, proofs = _book(root, pins, at)
    core._cohort(value, _journal(record, pins), binding, replayed, proofs, projection)
    current = states[seed.intent.run_id]
    _check(
        current.intent == seed.intent and not current.cancel_after_submit,
        "qqq_h5_cycle_state_changed",
    )
    return binding, current


def _prewire(pointer, expected_ref, paths, pins, value, provider, client, clock, rec, at):
    with _require_shared(paths.state_root):
        record = _load(pointer, pins)
        _check(
            record is not None and record["ref"] == expected_ref,
            "qqq_h5_cycle_prewire_journal_changed",
        )
        pending = record["pending"]
        seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
        binding, states, projection, replayed, proofs = _book(paths.state_root, pins, at)
        _check(binding["qqq"] == pending["proposed"]["qqq"], "qqq_h5_cycle_prewire_qqq_changed")
        state = states[seed.intent.run_id]
        _check(
            _nonsent(state, seed, at) and pending["wire_started_at"] is None,
            "qqq_h5_cycle_prewire_state_changed",
        )
        evidence, at, current = _evidence(
            provider,
            pins,
            value,
            binding,
            states,
            seed.intent.side,
            at,
            purpose="pre_submit",
            clock=clock,
            pointer=pointer,
            record=record,
        )
        binding, states, projection, replayed, proofs = current
        journal = _journal(record, pins)
        target, quantity, _ = core._cohort(value, journal, binding, replayed, proofs, projection)
        _check(
            is_us_equity_regular_session_window(at)
            and seed.intent.created_at <= at < seed.intent.valid_until,
            "qqq_h5_cycle_prewire_expired",
        )
        if seed.intent.side == "sell":
            _check(
                journal.exit_not_before <= at < journal.exit_close
                and Fraction(seed.intent.quantity) <= quantity,
                "qqq_h5_cycle_prewire_unowned_or_early_exit",
            )
        _check(
            type(rec.snapshot) is KisPaperReadOnlySnapshot and rec.account_status == "available",
            "qqq_h5_cycle_native_snapshot_unavailable",
        )
        config = _client(client, pins)
        price, available = core._book_reads(
            evidence.reads,
            target,
            projection,
            pins.account_ref,
            config.masked_account_identity,
            at,
            seed.intent.side,
        )
        native_snapshot = rec.snapshot
        if seed.intent.side == "sell":
            native_snapshot = KisPaperStockExitAccountSnapshot(
                rec.snapshot.identity,
                rec.snapshot.positions,
                rec.snapshot.open_orders,
                rec.snapshot.captured_at,
            )
        core._book_reads(
            # This combined check includes the earlier native snapshot; the
            # provider's own observation times remain unchanged above.
            replace(
                evidence.reads,
                snapshot=native_snapshot,
                started_at=min(evidence.reads.started_at, native_snapshot.captured_at),
            ),
            target,
            projection,
            pins.account_ref,
            config.masked_account_identity,
            at,
            seed.intent.side,
        )
        _check(price == seed.intent.limit_price, "qqq_h5_cycle_prewire_limit_changed")
        _check(
            seed.intent.valid_until <= evidence.reads.quote.quoted_at + core._MAX_AGE,
            "qqq_h5_cycle_prewire_quote_ttl_changed",
        )
        if seed.intent.side == "buy":
            _check(
                Fraction(projection.reserved_buys)
                <= min(
                    available,
                    Fraction(rec.snapshot.cash.available_cash),
                    Fraction(rec.snapshot.orderable_funds.orderable_funds),
                ),
                "qqq_h5_cycle_prewire_funds_changed",
            )
        emergency = EmergencyStore(paths.emergency_state_path).read()
        controls = PaperExecutionControlStore(paths.execution_control_path).read()
        _check(
            not emergency.blocks_new_orders
            and not (controls.pause_buys if seed.intent.side == "buy" else controls.pause_sells),
            "qqq_h5_cycle_prewire_control_changed",
        )
        _check(
            _load(pointer, pins) == record
            and budget._load_binding(paths.state_root, pins.account_ref) == binding
            and _states(paths.state_root, binding) == states,
            "qqq_h5_cycle_prewire_custody_changed",
        )
        pending["wire_started_at"] = at.isoformat()
        _save(pointer, record)
        return True


def _visit(pointer, record, pins, paths, value, provider, client, clock):
    binding, state = _materialize(pointer, record, pins, paths, value, require_utc(clock()))
    pending = record["pending"]
    if state.phase != "intent_recorded" or pending["wire_started_at"] is not None:
        _evidence(
            provider,
            pins,
            value,
            binding,
            _states(paths.state_root, binding),
            state.intent.side,
            require_utc(clock()),
            purpose="custody_reconcile",
            clock=clock,
            pointer=pointer,
            record=record,
        )
    if pending["wire_started_at"] is not None and state.phase == "intent_recorded":
        # The marker may precede a crash before native submission_started. That
        # ambiguous request is reconciliation-only, not proof of a safe resend.
        anchor = require_utc(datetime.fromisoformat(pending["wire_started_at"]))
        at = max(require_utc(clock()), state.updated_at, anchor)
        state = canary.KisPaperCanaryStateStore(
            paths.state_root / (state.intent.run_id + ".json")
        ).transition(
            state.intent,
            expected=frozenset({"intent_recorded"}),
            phase="submission_started",
            reason_code="preview",
            now=at,
            submission_started_at=anchor,
        )
    intent = state.intent
    decision_type = (
        KisPaperCanaryBuyDecision if intent.side == "buy" else KisPaperCanarySellDecision
    )
    outcome = canary._run_kis_paper_canary(
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
        environment={},
        state_path=paths.state_root / (intent.run_id + ".json"),
        runtime_projection_path=paths.runtime_projection_path,
        paper_account_snapshot_path=paths.paper_account_snapshot_path,
        emergency_state_path=paths.emergency_state_path,
        artifact_root=paths.artifact_root,
        repository_root=paths.repository_root,
        execute=True,
        cancel_after_submit=False,
        client=client,
        clock=clock,
        execution_control_path=paths.execution_control_path,
        require_existing_state=True,
        price_contract_ref=intent.price_contract_ref,
        submit_permitted=is_us_equity_regular_session_window,
        submit_reconciliation_check=lambda rec, at: _prewire(
            pointer, record["ref"], paths, pins, value, provider, client, clock, rec, at
        ),
    )
    record = _load(pointer, pins)
    binding, states, _, _, _ = _book(paths.state_root, pins, require_utc(clock()))
    state = states[intent.run_id]
    observation = outcome.reconciliation.execution
    if not budget._terminal(state, observation):
        return QqqH5CycleOutcome("pending", "exact_request_retained")
    # Terminal evidence closes only this exact linked row. No inferred absence,
    # unknown outcome release or modifications of any other owner's rows.
    candidate = copy.deepcopy(binding)
    try:
        row = next(r for r in candidate["qqq"]["orders"] if r["run_id"] == intent.run_id)
        if intent.run_id not in candidate["terminal_evidence"]:
            candidate["terminal_evidence"][intent.run_id] = budget._terminal_payload(
                state, observation
            )
        row["closed"] = True
        core._scope(
            candidate,
            states,
            pins.account_ref,
            pins.basis_ref,
            _owner_refs(candidate),
            core._ref(candidate),
            require_utc(clock()),
        )
    except (
        _RecoveryRequired,
        ValueError,
        TypeError,
        KeyError,
        ArithmeticError,
        canary.KisPaperCanaryError,
    ):
        return QqqH5CycleOutcome("held", "terminal_evidence_unrepresentable")
    _check(
        budget._load_binding(paths.state_root, pins.account_ref) == binding
        and _states(paths.state_root, binding) == states,
        "qqq_h5_cycle_terminal_parent_changed",
    )
    budget._atomic_json(paths.state_root / budget.BUDGET_FILE, candidate)
    _check(
        budget._load_binding(paths.state_root, pins.account_ref) == candidate,
        "qqq_h5_cycle_terminal_unverified",
    )
    _book(paths.state_root, pins, require_utc(clock()))
    record["pending"] = None
    _save(pointer, record)
    return QqqH5CycleOutcome(
        "advanced", "exact_request_terminal", _journal(record, pins).exit_not_before
    )


def run_qqq_h5_cycle(
    *,
    pins: QqqH5CyclePins,
    paths: QqqH5CyclePaths,
    value,
    phase: str,
    evidence_provider: Callable | None = None,
    client: canary.KisPaperCanaryClient | None = None,
    clock: Callable[[], datetime] | None = None,
    execute: bool = False,
) -> QqqH5CycleOutcome:
    """At most ONE native request visit; never a polling/controller loop.

    ``execute`` opts into the injected integration; it is not a boundary proof.
    Deployment/source qualification and the actual provider remain Parent work.
    Every possible pending request is recovered before evaluating a new phase.
    Exceptions retain their exact staged files/reservations; there is no rollback.
    """
    _check(type(execute) is bool, "qqq_h5_cycle_execute_invalid")
    if not execute:
        return QqqH5CycleOutcome("inert", "runtime_adapter_not_adopted")
    _check(type(pins) is QqqH5CyclePins, "qqq_h5_cycle_pins_invalid")
    replace(pins)
    _check(
        phase in {"entry", "exit"} and callable(clock) and callable(evidence_provider),
        "qqq_h5_cycle_dependencies_required",
    )
    target = core._input(value)
    _check(
        (value.input_ref, value.policy_ref) == (pins.input_ref, pins.policy_ref),
        "qqq_h5_cycle_input_changed",
    )
    config = _client(client, pins)
    pointer = _paths(paths, pins)
    with _shared(paths.state_root):
        at = require_utc(clock())
        record = _load(pointer, pins)
        if record is not None and record["pending"] is not None:
            return _visit(pointer, record, pins, paths, value, evidence_provider, client, clock)
        binding, states, projection, replayed, proofs = _book(paths.state_root, pins, at)
        if record is not None and record["status"] in {"closed", "no_intent"}:
            return QqqH5CycleOutcome(record["status"], "sealed_local_cycle")
        if record is None and phase == "exit":
            return QqqH5CycleOutcome("no_intent", "no_journal_no_inventory_adoption")
        if record is None and not value.entry_session.open_ts <= at < value.entry_session.close_ts:
            return QqqH5CycleOutcome("not_due", "outside_entry_window", value.entry_session.open_ts)
        if record is not None:
            journal = _journal(record, pins)
            _, quantity, pending = core._cohort(
                value, journal, binding, replayed, proofs, projection
            )
            _check(not pending, "qqq_h5_cycle_pending_journal_missing")
            if phase == "entry":
                return QqqH5CycleOutcome("hold", "entry_already_bound", journal.exit_not_before)
            if quantity and at < journal.exit_not_before:
                return QqqH5CycleOutcome("hold", "before_h5_exit", journal.exit_not_before)
            if quantity and at >= journal.exit_close:
                return QqqH5CycleOutcome("held", "expired_exit_no_substitute")
        side = "buy" if record is None else "sell"
        evidence, at, current = _evidence(
            evidence_provider,
            pins,
            value,
            binding,
            states,
            side,
            at,
            purpose="pre_submit",
            clock=clock,
            pointer=pointer,
            record=record,
        )
        binding, states, _, _, _ = current
        args = dict(
            value=value,
            binding=binding,
            states=states,
            expected_account_ref=pins.account_ref,
            expected_basis_ref=pins.basis_ref,
            expected_owner_refs=_owner_refs(binding),
            expected_binding_ref=core._ref(binding),
            writer_boundary=evidence.writer_boundary,
            expected_writer_ref=evidence.writer_boundary.reference,
            reads=evidence.reads,
            expected_masked_account=config.masked_account_identity,
            as_of=at,
            valid_until=min(
                at + timedelta(seconds=60),
                target.proposal.valid_until if side == "buy" else value.exit_session.close_ts,
            ),
        )
        plan = (
            core.plan_qqq_h5_entry(execution_source_ref=pins.execution_source_ref, **args)
            if record is None
            else core.plan_qqq_h5_exit(journal=journal, **args)
        )
        _check(
            _load(pointer, pins) == record
            and budget._load_binding(paths.state_root, pins.account_ref) == binding
            and _states(paths.state_root, binding) == states,
            "qqq_h5_cycle_parent_changed",
        )
        record = _stage(pointer, pins, plan, binding)
        if record["pending"] is None:
            return QqqH5CycleOutcome(plan.status, plan.reason)
        return _visit(pointer, record, pins, paths, value, evidence_provider, client, clock)
