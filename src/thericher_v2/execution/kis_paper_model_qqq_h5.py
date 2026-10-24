"""Pure L/LN QQQ-H5 plans in the existing V4 bank, never runtime authority.

No IO, client, lease acquisition or dispatch lives here. A future adapter must
verify the origin/stability of custody and writer evidence, persist the exact
journal/intent/reservation under the existing locks, and recheck before wire.
An invented caller projection can exercise these functions but cannot become
proof that legacy QQQ issuers are actually disabled.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

from thericher_v2.contracts import require_utc
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.model_paper_proposal import _canonical
from thericher_v2.research.model_paper_weights import ModelPaperWeightsInput

from . import kis_paper_budget_strategy as budget
from .kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from .kis_paper_current_stock_cycle import StockCycleProfile, _validate_model_input
from .kis_paper_portfolio_budget import KisPaperPortfolioStateRef
from .kis_paper_portfolio_plan import _replay_scope
from .kis_paper_quote import KisPaperSpyLimitInput, derive_kis_paper_marketable_limit
from .kis_paper_stock_plan import _amount, _context, _typed
from .kis_paper_stock_quote import KisPaperStockInstrument
from .kis_paper_stock_readonly import KisPaperStockExitReads, KisPaperStockPreviewReads
from .kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)
from .paper_decision_bridge import (
    KisPaperLimitProof,
    PaperDecisionExecutionBinding,
    prepare_kis_paper_decision,
)

_SCHEMA = "qqq-h5-pure-journal-v1"
_MAX_AGE = timedelta(seconds=120)


class QqqH5PlanningError(ValueError):
    """Categorical source-local invalidity, not an operational recovery result."""


def _need(ok, reason):
    if not ok:
        raise QqqH5PlanningError(reason)


def _pin(value):
    _need(type(value) is str and budget._SHA.fullmatch(value), "qqq_h5_reference_invalid")


def _ref(value):
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, repr=False)
class QqqH5WriterBoundary:
    """Source-bound projection to check, NOT an attested live-writer capability.

    The trusted adapter is intentionally absent. Its externally pinned evidence
    must cover actual named legacy QQQ issuers, not unrelated research actors.
    """

    source_ref: str
    custody_ref: str
    membership_ref: str
    observed_at: datetime
    excluded_until: datetime
    legacy_sources: tuple[str, ...]
    excluded_sources: tuple[str, ...]
    unresolved_sources: tuple[str, ...] = ()

    def __post_init__(self):
        for value in (self.source_ref, self.custody_ref, self.membership_ref):
            _pin(value)
        require_utc(self.observed_at)
        require_utc(self.excluded_until)
        for group in (self.legacy_sources, self.excluded_sources, self.unresolved_sources):
            _need(
                type(group) is tuple and len(group) == len(set(group)), "qqq_h5_writer_set_invalid"
            )
            for value in group:
                _pin(value)

    @property
    def reference(self):
        return _ref(asdict(self))


@dataclass(frozen=True, repr=False)
class QqqH5Journal:
    account_ref: str
    basis_ref: str
    cycle_id: str
    execution_source_ref: str
    input_ref: str
    policy_ref: str
    legacy_ref: str
    legacy: tuple[KisPaperPortfolioStateRef, ...]
    entry_open: datetime
    entry_close: datetime
    exit_open: datetime
    exit_close: datetime
    exit_not_before: datetime
    initial_writer_ref: str
    entry: KisPaperPortfolioStateRef | None = None
    exits: tuple[KisPaperPortfolioStateRef, ...] = ()

    def __post_init__(self):
        _need(
            type(self.account_ref) is str
            and len(self.account_ref) == 64
            and all(c in "0123456789abcdef" for c in self.account_ref),
            "qqq_h5_account_invalid",
        )
        for name in (
            "basis_ref",
            "execution_source_ref",
            "input_ref",
            "policy_ref",
            "legacy_ref",
            "initial_writer_ref",
        ):
            _pin(getattr(self, name))
        _need(
            type(self.cycle_id) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", self.cycle_id),
            "qqq_h5_cycle_invalid",
        )
        times = (
            self.entry_open,
            self.entry_close,
            self.exit_open,
            self.exit_close,
            self.exit_not_before,
        )
        for value in times:
            require_utc(value)
        _need(
            self.entry_open
            < self.entry_close
            < self.exit_open
            < self.exit_not_before
            < self.exit_close
            and self.exit_not_before == self.exit_close - timedelta(minutes=15),
            "qqq_h5_journal_clock_invalid",
        )
        _need(
            type(self.legacy) is tuple and type(self.exits) is tuple, "qqq_h5_journal_refs_invalid"
        )
        refs = (*self.legacy, *((self.entry,) if self.entry is not None else ()), *self.exits)
        for value in refs:
            _typed(value, KisPaperPortfolioStateRef, "qqq_h5_journal_refs_invalid")
            _need(budget._QQQ_RUN_ID.fullmatch(value.run_id), "qqq_h5_run_invalid")
        _need(len({r.run_id for r in refs}) == len(refs), "qqq_h5_duplicate_run")
        _need(self.entry is not None or not self.exits, "qqq_h5_exit_without_entry")

    @property
    def owner_id(self):
        return "qqq-" + budget._digest(self.cycle_id)

    @property
    def cohort_ref(self):
        immutable = asdict(self)
        for key in ("entry", "exits", "initial_writer_ref"):
            immutable.pop(key)
        return _ref(immutable)

    def request_id(self, side):
        _need(side in {"buy", "sell"}, "qqq_h5_side_invalid")
        index = 0 if side == "buy" else len(self.exits)
        return "qqq-h5-" + budget._digest([self.cohort_ref, side, index])


@dataclass(frozen=True, repr=False)
class QqqH5Plan:
    status: str
    reason: str
    journal: QqqH5Journal
    binding: Mapping | None = None
    seed: KisPaperCanaryState | None = None

    @property
    def runtime_authorized(self):
        return False


def _scope(
    binding,
    states,
    expected_account_ref,
    expected_basis_ref,
    expected_owner_refs,
    expected_binding_ref,
    at,
):
    _need(
        isinstance(binding, Mapping)
        and binding.get("version") == 4
        and set(binding) == budget._V4_KEYS,
        "qqq_h5_v4_required",
    )
    _need(_ref(binding) == expected_binding_ref, "qqq_h5_book_changed")
    _need(isinstance(states, Mapping), "qqq_h5_states_invalid")
    values = [budget._money(binding["basis_usd"]), budget._money(binding["allocated_usd"])]
    for state in states.values():
        _typed(state, KisPaperCanaryState, "qqq_h5_state_invalid")
        values.extend((state.intent.quantity, state.intent.limit_price))
        if state.cumulative_fill is not None:
            values.extend(
                getattr(state.cumulative_fill, f.name) for f in fields(state.cumulative_fill)
            )
    with localcontext(_context(values)):
        projection = budget.project_shared_budget(
            binding=binding,
            states=states,
            expected_account_ref=expected_account_ref,
            expected_basis_ref=expected_basis_ref,
            expected_owner_refs=expected_owner_refs,
            as_of=at,
        )
        replayed, proofs = _replay_scope(binding, states)
    return projection, replayed, proofs


def qqq_h5_custody_ref(binding, states):
    """Hash a supplied QQQ projection; this does not read or attest private custody."""
    qqq = binding["qqq"]
    return _ref(
        dict(
            account=binding["account_ref"],
            basis=binding["basis_ref"],
            qqq=qqq,
            states={r["run_id"]: states[r["run_id"]].to_dict() for r in qqq["orders"]},
            terminal={
                r["run_id"]: binding["terminal_evidence"].get(r["run_id"]) for r in qqq["orders"]
            },
        )
    )


def _writers(boundary, expected_ref, binding, states, value, at):
    _typed(boundary, QqqH5WriterBoundary, "qqq_h5_writer_projection_required")
    _pin(expected_ref)
    _need(boundary.reference == expected_ref, "qqq_h5_writer_pin_mismatch")
    _need(
        boundary.custody_ref == qqq_h5_custody_ref(binding, states),
        "qqq_h5_writer_custody_mismatch",
    )
    _need(
        set(boundary.legacy_sources) == set(boundary.excluded_sources)
        and not boundary.unresolved_sources,
        "qqq_h5_legacy_writers_unresolved",
    )
    _need(
        timedelta(0) <= at - boundary.observed_at <= _MAX_AGE
        and boundary.excluded_until >= max(value.exit_session.close_ts, at + _MAX_AGE),
        "qqq_h5_writer_exclusion_unqualified",
    )


def _input(value):
    _need(type(value) is ModelPaperWeightsInput, "qqq_h5_input_invalid")
    _validate_model_input(
        value, value.entry_session.open_ts, StockCycleProfile.MODEL_WEIGHTS_NAS_H5
    )
    _need(len(value.targets) == 1 and value.targets[0].route == "QQQ/NAS", "qqq_h5_only_qqq_target")
    return value.targets[0]


def _refs(records):
    return tuple(KisPaperPortfolioStateRef(r["run_id"], r["intent_ref"]) for r in records)


def _prefix_ref(binding, replayed, count):
    records = binding["qqq"]["orders"][:count]
    return _ref(
        dict(
            records=records,
            states={r["run_id"]: replayed[r["run_id"]].to_dict() for r in records},
            terminal={r["run_id"]: binding["terminal_evidence"].get(r["run_id"]) for r in records},
        )
    )


def admit_qqq_h5_boundary(
    *,
    value,
    execution_source_ref,
    binding,
    states,
    expected_account_ref,
    expected_basis_ref,
    expected_owner_refs,
    expected_binding_ref,
    writer_boundary,
    expected_writer_ref,
    as_of,
):
    """Check supplied terminal-flat/exclusion projections; no live-proof grant."""
    at = require_utc(as_of)
    _input(value)
    _pin(execution_source_ref)
    _need(value.entry_session.open_ts <= at < value.entry_session.close_ts, "qqq_h5_entry_not_due")
    projection, replayed, proofs = _scope(
        binding,
        states,
        expected_account_ref,
        expected_basis_ref,
        expected_owner_refs,
        expected_binding_ref,
        at,
    )
    _writers(writer_boundary, expected_writer_ref, binding, states, value, at)
    orders = binding["qqq"]["orders"]
    _need(
        all(
            r["closed"]
            and r["run_id"] in binding["terminal_evidence"]
            and budget._terminal(replayed[r["run_id"]], proofs.get(r["run_id"]))
            for r in orders
        ),
        "qqq_h5_legacy_request_unresolved",
    )
    owner = budget._owner_id(binding, binding["qqq"]["cycle_id"])
    owned = next(r for r in projection.stocks_by_owner if r.owner_ref == owner)
    _need(owned.quantity == 0 and owned.reserved_buys == 0, "qqq_h5_legacy_not_flat")
    return QqqH5Journal(
        expected_account_ref,
        expected_basis_ref,
        binding["qqq"]["cycle_id"],
        execution_source_ref,
        value.input_ref,
        value.policy_ref,
        _prefix_ref(binding, replayed, len(orders)),
        _refs(orders),
        value.entry_session.open_ts,
        value.entry_session.close_ts,
        value.exit_session.open_ts,
        value.exit_session.close_ts,
        value.metadata.exit_not_before,
        expected_writer_ref,
    )


def _book_reads(reads, target, projection, account, masked_account, at, side):
    kind = KisPaperStockPreviewReads if side == "buy" else KisPaperStockExitReads
    _typed(reads, kind, "qqq_h5_reads_invalid")
    _typed(reads.quote, KisPaperSpyLimitInput, "qqq_h5_quote_invalid")
    instrument = KisPaperStockInstrument("QQQ", target.receipt.instrument_binding_ref)
    _need(reads.account_ref == account and reads.instrument == instrument, "qqq_h5_reads_binding")
    snapshot = reads.snapshot
    _typed(snapshot.identity, KisPaperAccountIdentity, "qqq_h5_identity_invalid")
    _typed(snapshot.open_orders, KisPaperOpenOrdersSnapshot, "qqq_h5_orders_invalid")
    _need(
        snapshot.identity.masked_account == masked_account
        and snapshot.open_orders.complete is True,
        "qqq_h5_account_incomplete",
    )
    times = [
        reads.started_at,
        reads.completed_at,
        reads.quote.quoted_at,
        snapshot.captured_at,
        snapshot.identity.captured_at,
        snapshot.open_orders.captured_at,
    ]
    _need(reads.started_at <= reads.completed_at <= at, "qqq_h5_read_clock")
    if side == "buy":
        _need(target.proposal.decided_at <= reads.started_at, "qqq_h5_read_clock")
    quantity, found = Fraction(0), 0
    for position in snapshot.positions:
        _typed(position, KisPaperPosition, "qqq_h5_position_invalid")
        times.append(position.captured_at)
        if position.symbol == "QQQ":
            found += 1
            _need(
                position.exchange == "NASD" and position.currency == "USD", "qqq_h5_position_route"
            )
            quantity += _amount(position.quantity, whole=True)
    _need(found <= 1, "qqq_h5_duplicate_position")
    for order in snapshot.open_orders.orders:
        _typed(order, KisPaperOpenOrder, "qqq_h5_order_invalid")
        times.append(order.captured_at)
        _need(order.symbol != "QQQ", "qqq_h5_open_order_pending")
    owned = sum(
        (
            Fraction(r.quantity)
            for r in projection.stocks_by_owner
            if (r.symbol, r.exchange) == ("QQQ", "NASD")
        ),
        Fraction(0),
    )
    _need(quantity == owned, "qqq_h5_foreign_or_unknown_inventory")
    _need(
        type(reads.quote.best_bid) is Decimal and type(reads.quote.best_ask) is Decimal,
        "qqq_h5_book_prices_required",
    )
    with localcontext(
        _context(
            [reads.quote.last, reads.quote.tick_size, reads.quote.best_bid, reads.quote.best_ask]
        )
    ):
        price = derive_kis_paper_marketable_limit(reads.quote, side=side, observed_at=at)
    available = None
    if side == "buy":
        _typed(snapshot, KisPaperReadOnlySnapshot, "qqq_h5_snapshot_invalid")
        for money in (reads.cash, snapshot.cash):
            _typed(money, KisPaperCashSnapshot, "qqq_h5_cash_invalid")
            _need(money.currency == "USD", "qqq_h5_cash_currency")
            times.append(money.captured_at)
        for money in (reads.orderable, snapshot.orderable_funds):
            _typed(money, KisPaperOrderableFundsSnapshot, "qqq_h5_funds_invalid")
            _need(money.currency == "USD", "qqq_h5_funds_currency")
            times.append(money.captured_at)
        funds = reads.orderable
        _need(
            reads.cash.currency == funds.currency == "USD"
            and (funds.reference_symbol, funds.reference_exchange) == ("QQQ", "NASD")
            and _amount(funds.reference_price, positive=True) == _amount(price, positive=True)
            and _amount(reads.buy_limit, positive=True) == _amount(price, positive=True),
            "qqq_h5_funds_binding",
        )
        available = min(_amount(reads.cash.available_cash), _amount(funds.orderable_funds))
    _need(all(timedelta(0) <= at - require_utc(t) <= _MAX_AGE for t in times), "qqq_h5_reads_stale")
    return price, available


def _append(binding, states, journal, receipt, price, quantity, at, until, side, quote):
    request = journal.request_id(side)
    price_ref = _ref(
        [journal.cohort_ref, request, receipt.decision_id, side, str(price), quote.isoformat()]
    )
    prepared = prepare_kis_paper_decision(
        receipt,
        binding=PaperDecisionExecutionBinding(receipt.proposal_ref, "QQQ", "NASD", quantity),
        limit_proof=KisPaperLimitProof(
            receipt.decision_id, price_ref, "QQQ", "NASD", price, quote, until, True
        ),
        as_of=at,
    )
    _need(prepared.status == "ready", "qqq_h5_receipt_not_eligible")
    intent = KisPaperCanaryIntent.from_decision(
        prepared.kis_paper_decision,
        run_id="bq-" + budget._digest(request),
        price_contract_ref=price_ref,
    )
    seed = KisPaperCanaryState(intent, "intent_recorded", at, "preview")
    linked = KisPaperPortfolioStateRef(intent.run_id, intent.fingerprint)
    updated = (
        replace(journal, entry=linked)
        if side == "buy"
        else replace(journal, exits=(*journal.exits, linked))
    )
    proposed = copy.deepcopy(dict(binding))
    proposed["qqq"]["orders"].append(
        dict(run_id=intent.run_id, intent_ref=intent.fingerprint, closed=False)
    )
    proposed["qqq"]["owner_ref"] = next(
        o.fingerprint for o, _ in budget._owners(proposed) if o.owner_ref == journal.owner_id
    )
    combined = dict(states) | {intent.run_id: seed}
    _scope(
        proposed,
        combined,
        journal.account_ref,
        journal.basis_ref,
        {o.owner_ref: r for o, r in budget._owners(proposed)},
        _ref(proposed),
        at,
    )
    return QqqH5Plan("prepared", "pure_plan_runtime_adapter_required", updated, proposed, seed)


def plan_qqq_h5_entry(
    *,
    value,
    execution_source_ref,
    binding,
    states,
    expected_account_ref,
    expected_basis_ref,
    expected_owner_refs,
    expected_binding_ref,
    writer_boundary,
    expected_writer_ref,
    reads,
    expected_masked_account,
    as_of,
    valid_until,
):
    """One pure fresh plan; an adapter must never replan an existing journal."""
    at = require_utc(as_of)
    journal = admit_qqq_h5_boundary(
        value=value,
        execution_source_ref=execution_source_ref,
        binding=binding,
        states=states,
        expected_account_ref=expected_account_ref,
        expected_basis_ref=expected_basis_ref,
        expected_owner_refs=expected_owner_refs,
        expected_binding_ref=expected_binding_ref,
        writer_boundary=writer_boundary,
        expected_writer_ref=expected_writer_ref,
        as_of=at,
    )
    target = _input(value)
    _need(target.proposal.decided_at <= at < target.proposal.valid_until, "qqq_h5_proposal_expired")
    projection, _, _ = _scope(
        binding,
        states,
        expected_account_ref,
        expected_basis_ref,
        expected_owner_refs,
        expected_binding_ref,
        at,
    )
    price, funds = _book_reads(
        reads, target, projection, expected_account_ref, expected_masked_account, at, "buy"
    )
    reserved = Fraction(projection.reserved_buys)
    capacity = min(
        Fraction(projection.remaining_cap),
        Fraction(projection.remaining_gross_cash),
        max(Fraction(0), funds - reserved),
    )
    target_quantity = (
        Fraction(budget._money(binding["basis_usd"])) * Fraction(target.proposal.target_exposure)
    ) // Fraction(price)
    quantity = Decimal(int(min(target_quantity, capacity // Fraction(price))))
    if quantity == 0:
        return QqqH5Plan("no_intent", "whole_share_capacity_zero", journal)
    until = require_utc(valid_until)
    _need(
        at
        < until
        <= min(
            at + budget._ORDER_LIFETIME,
            target.proposal.valid_until,
            value.entry_session.close_ts,
            reads.quote.quoted_at + _MAX_AGE,
        ),
        "qqq_h5_validity_invalid",
    )
    return _append(
        binding,
        states,
        journal,
        target.receipt,
        price,
        quantity,
        at,
        until,
        "buy",
        reads.quote.quoted_at,
    )


def _cohort(value, journal, binding, replayed, proofs, projection):
    _typed(journal, QqqH5Journal, "qqq_h5_journal_invalid")
    target = _input(value)
    _need(
        (journal.input_ref, journal.policy_ref) == (value.input_ref, value.policy_ref)
        and (
            journal.entry_open,
            journal.entry_close,
            journal.exit_open,
            journal.exit_close,
            journal.exit_not_before,
        )
        == (
            value.entry_session.open_ts,
            value.entry_session.close_ts,
            value.exit_session.open_ts,
            value.exit_session.close_ts,
            value.metadata.exit_not_before,
        ),
        "qqq_h5_journal_input_changed",
    )
    _need(
        binding["account_ref"] == journal.account_ref
        and binding["basis_ref"] == journal.basis_ref
        and binding["qqq"]["cycle_id"] == journal.cycle_id,
        "qqq_h5_journal_owner_changed",
    )
    _need(journal.entry is not None, "qqq_h5_entry_not_recorded")
    own = ((journal.entry,) if journal.entry is not None else ()) + journal.exits
    _need(
        _refs(binding["qqq"]["orders"]) == journal.legacy + own, "qqq_h5_cohort_membership_changed"
    )
    _need(
        _prefix_ref(binding, replayed, len(journal.legacy)) == journal.legacy_ref,
        "qqq_h5_legacy_prefix_changed",
    )
    quantity, pending = Fraction(0), False
    for index, ref in enumerate(own):
        state = replayed[ref.run_id]
        intent = state.intent
        _need(
            intent.fingerprint == ref.intent_ref
            and (intent.symbol, intent.exchange) == ("QQQ", "NASD")
            and intent.side == ("buy" if index == 0 else "sell"),
            "qqq_h5_linked_intent_changed",
        )
        if index == 0:
            _need(
                intent.decision_id
                == "receipt-" + target.receipt.decision_id.removeprefix("decision:sha256:")
                and intent.run_id == "bq-" + budget._digest(journal.request_id("buy"))
                and journal.entry_open <= intent.created_at < journal.entry_close
                and Fraction(intent.quantity) * Fraction(intent.limit_price)
                <= Fraction(budget._money(binding["basis_usd"]))
                * Fraction(target.proposal.target_exposure),
                "qqq_h5_entry_identity_changed",
            )
        else:
            request = "qqq-h5-" + budget._digest([journal.cohort_ref, "sell", index - 1])
            _need(
                intent.run_id == "bq-" + budget._digest(request)
                and intent.created_at >= journal.exit_not_before
                and Fraction(intent.quantity) <= quantity,
                "qqq_h5_unowned_or_early_exit",
            )
        fill = (
            Fraction(0)
            if state.cumulative_fill is None
            else Fraction(state.cumulative_fill.quantity)
        )
        quantity += fill if index == 0 else -fill
        row = binding["qqq"]["orders"][len(journal.legacy) + index]
        pending |= not (row["closed"] and budget._terminal(state, proofs.get(ref.run_id)))
    owned = next(r for r in projection.stocks_by_owner if r.owner_ref == journal.owner_id)
    _need(
        quantity >= 0 and quantity == Fraction(owned.quantity), "qqq_h5_subset_inventory_mismatch"
    )
    return target, quantity, pending


def plan_qqq_h5_exit(
    *,
    value,
    journal,
    binding,
    states,
    expected_account_ref,
    expected_basis_ref,
    expected_owner_refs,
    expected_binding_ref,
    writer_boundary,
    expected_writer_ref,
    reads,
    expected_masked_account,
    as_of,
    valid_until,
):
    """Plan only the journal's terminal linked residual, never all-owner adoption."""
    at = require_utc(as_of)
    projection, replayed, proofs = _scope(
        binding,
        states,
        expected_account_ref,
        expected_basis_ref,
        expected_owner_refs,
        expected_binding_ref,
        at,
    )
    target, quantity, pending = _cohort(value, journal, binding, replayed, proofs, projection)
    _writers(writer_boundary, expected_writer_ref, binding, states, value, at)
    if pending:
        return QqqH5Plan("reconcile", "exact_linked_request_pending", journal)
    if quantity == 0:
        return QqqH5Plan("closed", "linked_owned_flat", journal)
    if at < journal.exit_not_before:
        return QqqH5Plan("hold", "before_h5_exit", journal)
    _need(journal.exit_open <= at < journal.exit_close, "qqq_h5_exit_not_due")
    price, _ = _book_reads(
        reads, target, projection, expected_account_ref, expected_masked_account, at, "sell"
    )
    until = require_utc(valid_until)
    _need(
        at
        < until
        <= min(at + budget._ORDER_LIFETIME, journal.exit_close, reads.quote.quoted_at + _MAX_AGE),
        "qqq_h5_validity_invalid",
    )
    proposal = replace(
        target.proposal,
        proposal_id=journal.request_id("sell"),
        action="exit",
        target_exposure=Decimal(0),
        decided_at=at,
        valid_until=until,
        reason="deterministic_h5_exact_qqq_cohort_exit_not_new_model_signal",
    )
    receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            target.receipt.campaign_ref,
            target.receipt.model_ref,
            target.receipt.input_manifest_ref,
            "ref:"
            + budget._digest([journal.cohort_ref, journal.request_id("sell"), "policy_exit"]),
        ),
    )
    return _append(
        binding,
        states,
        journal,
        receipt,
        price,
        Decimal(int(quantity)),
        at,
        until,
        "sell",
        reads.quote.quoted_at,
    )


def serialize_qqq_h5_journal(journal):
    _typed(journal, QqqH5Journal, "qqq_h5_journal_invalid")
    return _canonical(dict(schema=_SCHEMA, **asdict(journal)))


def load_qqq_h5_journal(payload, *, expected_sha256):
    """Strict in-memory journal parser; the adapter still owns file provenance."""
    _need(
        type(payload) is bytes
        and len(payload) <= 1024 * 1024
        and hashlib.sha256(payload).hexdigest() == expected_sha256,
        "qqq_h5_journal_pin_mismatch",
    )

    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "qqq_h5_duplicate_field")
            result[key] = value
        return result

    raw = json.loads(
        payload,
        object_pairs_hook=unique,
        parse_constant=lambda _: _need(False, "qqq_h5_nonfinite_json"),
    )
    _need(
        type(raw) is dict
        and raw.pop("schema", None) == _SCHEMA
        and set(raw) == {f.name for f in fields(QqqH5Journal)},
        "qqq_h5_journal_schema_invalid",
    )
    for key in ("entry_open", "entry_close", "exit_open", "exit_close", "exit_not_before"):
        raw[key] = require_utc(datetime.fromisoformat(raw[key]))

    def reference(item):
        _need(
            type(item) is dict and set(item) == {"run_id", "intent_ref"},
            "qqq_h5_journal_refs_invalid",
        )
        return KisPaperPortfolioStateRef(**item)

    for key in ("legacy", "exits"):
        _need(type(raw[key]) is list, "qqq_h5_journal_refs_invalid")
        raw[key] = tuple(reference(r) for r in raw[key])
    raw["entry"] = None if raw["entry"] is None else reference(raw["entry"])
    journal = QqqH5Journal(**raw)
    _need(serialize_qqq_h5_journal(journal) == payload, "qqq_h5_journal_not_canonical")
    return journal
