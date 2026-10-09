"""One private allocation for the SPY baseline and an explicitly owned QQQ cycle.

The private binding holds funding and references, not a second fill ledger.
All quantities/costs are replayed from the existing exact canary states. This
does not govern bare canary calls or deploy a QQQ caller/schedule.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal, DecimalException
from fractions import Fraction
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
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
    UrllibKisPaperCanaryTransport,
    _cancel_submitted_canary,
    _record_reconciliation_fill,
    _run_kis_paper_canary,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_fill_accounting import KisPaperCumulativeFill, KisPaperExecutionObservation
from .kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
    project_kis_paper_portfolio_budget,
)
from .kis_paper_portfolio_budget import (
    _decimal as _exact_decimal,
)
from .kis_paper_portfolio_budget import (
    _validated_state as _validated_portfolio_state,
)
from .kis_paper_quote import (
    KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
    KisPaperQuoteError,
    derive_kis_paper_marketable_limit,
)
from .kis_paper_session import _session_now, is_us_equity_regular_session_window
from .kis_paper_spy_fill_cycle import (
    _atomic_json,
    _binding_identity,
    _digest,
    _failure_category,
    _load_successors,
    _read_json,
    _RecoveryRequired,
    _spy_book,
    _validate_leg,
    _validate_paths,
    conflicts_with_active_spy_fill_cycle,
)
from .kis_paper_spy_fill_cycle import (
    _binding as _cycle_binding,
)
from .kis_paper_spy_fill_cycle import (
    _validate_binding as _validate_cycle_binding,
)
from .kis_readonly import (
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOrderableFundsSnapshot,
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
_QQQ_RUN_ID = re.compile(r"bq-[0-9a-f]{64}")
_QQQ_ENTRY_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", re.ASCII)
_V1_KEYS = {"version", "account_ref", "basis_usd", "allocated_usd", "at", "orders"}
_V2_KEYS = _V1_KEYS | {"basis_ref", "spy_owner_ref", "qqq", "legacy_spy", "terminal_evidence"}
_V3_KEYS = _V2_KEYS | {"portfolio"}
_V4_KEYS = _V3_KEYS | {"stocks"}
_PORTFOLIO_INSTRUMENTS = (("SPY", "AMEX"), ("TLT", "NASD"), ("GLD", "AMEX"))
_PORTFOLIO_RUN_ID = re.compile(r"bp-[0-9a-f]{64}")
_STOCK_RUN_ID = re.compile(r"bk-[0-9a-f]{64}")
_STOCK_SYMBOL = re.compile(r"[A-Z]{1,10}", re.ASCII)
_STOCK_BINDING_REF = re.compile(r"ref:[0-9a-f]{64}")
_SHA = re.compile(r"sha256:[0-9a-f]{64}")
_ORDER_LIFETIME = timedelta(minutes=5)
_FAILURE_DIAGNOSTIC_CATEGORIES = {
    "stage": frozenset(
        {
            "paths",
            "config",
            "ownership",
            "new_input",
            "controls",
            "account",
            "quote",
            "prepare",
            "persist",
            "reconcile",
            "order",
        }
    ),
    "category": frozenset(
        {
            "canary_error",
            "readonly_error",
            "quote_error",
            "io_error",
            "decimal_error",
            "validation_error",
            "recovery_required",
        }
    ),
}
_FAILURE_CODES = frozenset(
    {
        "config_missing",
        "config_account_invalid",
        "config_product_invalid",
        "paper_host_required",
        "auth_rejected",
        "auth_response_invalid",
        "access_token_invalid",
        "transport_failure",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "balance_rejected",
        "balance_response_incomplete",
        "balance_response_duplicate",
        "balance_pagination_incomplete",
        "orderable_funds_rejected",
        "orderable_funds_response_incomplete",
        "open_orders_rejected",
        "open_orders_response_incomplete",
        "open_orders_response_duplicate",
        "open_orders_pagination_incomplete",
        "ccnl_response_incomplete",
        "ccnl_pagination_incomplete",
        "quote_rejected",
        "quote_response_incomplete",
        "quote_response_blank",
        "quote_timestamp_invalid",
        "quote_timestamp_stale",
        "quote_tick_invalid",
        "quote_scale_mismatch",
        "quote_limit_invalid",
        "quote_bid_ask_invalid",
        "state_invalid",
        "state_intent_mismatch",
        "state_transition_invalid",
        "state_submission_time_invalid",
        "recovery_state_missing",
        "recovery_run_id_mismatch",
        "recovery_phase_not_reconcilable",
        "recovery_evidence_collision",
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
    instrument: str | None = None
    exchange: str | None = None
    owned_cycle_ref: str | None = None

    def __post_init__(self):
        if (self.instrument, self.exchange, self.owned_cycle_ref) != (None, None, None) and (
            self.instrument != "QQQ"
            or self.exchange != "NASD"
            or not isinstance(self.owned_cycle_ref, str)
            or _SHA.fullmatch(self.owned_cycle_ref) is None
        ):
            raise ValueError("budget outcome scope invalid")

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
        if self.instrument is not None:
            payload.update(
                kind="kis_paper_qqq_unit_cycle",
                decision_use="owned_unit_cycle_receipt",
                instrument="QQQ",
                exchange="NASD",
                owned_cycle_ref=self.owned_cycle_ref,
            )
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
    gross_cash: Decimal | None = field(default=None, kw_only=True)
    remaining_gross_cash: Decimal | None = field(default=None, kw_only=True)
    aggregate_quantity: Decimal | None = field(default=None, kw_only=True)
    instrument_reserved_buys: Decimal | None = field(default=None, kw_only=True)


class KisPaperSpyOwnedInventoryError(ValueError):
    """Scoped categorical replay failure, never an execution permission state."""


@dataclass(frozen=True, repr=False)
class KisPaperSpyOwnedInventory(BudgetProjection):
    order_count: int
    matched_fill_count: int
    retained_fill_count: int

    def __post_init__(self):
        if (
            any(
                type(value) is not Decimal or not value.is_finite() or value < 0
                for value in (self.quantity, self.entry_cost, self.reserved_buys)
            )
            or any(
                type(value) is not int or value < 0
                for value in (self.order_count, self.matched_fill_count, self.retained_fill_count)
            )
            or not self.retained_fill_count <= self.matched_fill_count <= self.order_count
        ):
            raise KisPaperSpyOwnedInventoryError("spy_inventory_result_invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_spy_owned_inventory_replay_v1",
            "source": "kis_paper",
            "instrument": "SPY",
            "status": "known_owned_inventory" if self.quantity > 0 else "no_known_owned_inventory",
            "order_count": self.order_count,
            "matched_fill_count": self.matched_fill_count,
            "retained_fill_count": self.retained_fill_count,
            "limitation": "owned_state_attribution_not_current_broker_state_or_pnl",
        }


def _load_binding(root: Path, account_ref: str | None = None):
    path = root / BUDGET_FILE
    if path.is_symlink():
        raise _RecoveryRequired("budget_binding_invalid")
    try:
        binding = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_budget_keys
        )
    except FileNotFoundError:
        binding = None
    if binding is None:
        if any(
            any(root.glob(pattern))
            for pattern in ("bs-*.json", "bq-*.json", "bp-*.json", "bk-*.json")
        ):
            raise _RecoveryRequired("budget_binding_missing")
        return None
    if (
        not isinstance(binding, dict)
        or type(binding.get("version")) is not int
        or (binding["version"], set(binding))
        not in ((1, _V1_KEYS), (2, _V2_KEYS), (3, _V3_KEYS), (4, _V4_KEYS))
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
    _validate_orders(binding["orders"], _RUN_ID)
    if binding["version"] in {2, 3, 4}:
        qqq = binding["qqq"]
        if (
            not isinstance(qqq, dict)
            or set(qqq) != {"cycle_id", "owner_ref", "orders"}
            or not isinstance(qqq["cycle_id"], str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", qqq["cycle_id"]) is None
            or not isinstance(binding["terminal_evidence"], dict)
        ):
            raise _RecoveryRequired("budget_binding_invalid")
        _validate_orders(qqq["orders"], _QQQ_RUN_ID)
        if _basis(binding).fingerprint != binding["basis_ref"]:
            raise _RecoveryRequired("budget_binding_invalid")
        for owner, expected in _owners(binding):
            if owner.fingerprint != expected:
                raise _RecoveryRequired("budget_binding_invalid")
        referenced = {ref.run_id for owner, _ in _owners(binding) for ref in owner.state_refs}
        if not set(binding["terminal_evidence"]) <= referenced:
            raise _RecoveryRequired("budget_binding_invalid")
    seeds = _portfolio_seed_states(binding)
    if any(path.stem not in seeds or path.is_symlink() for path in root.glob("bp-*.json")):
        raise _RecoveryRequired("portfolio_state_unbound")
    stocks = _stock_seed_states(binding)
    if any(path.stem not in stocks or path.is_symlink() for path in root.glob("bk-*.json")):
        raise _RecoveryRequired("stock_state_unbound")
    return binding


def _unique_budget_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _RecoveryRequired("budget_duplicate_key")
        result[key] = value
    return result


def _portfolio_seed_states(binding):
    """Immutable initial canary facts, atomically reserved with the whole batch."""
    if binding["version"] not in {3, 4}:
        return {}
    portfolio = binding["portfolio"]
    if (
        type(portfolio) is not dict
        or set(portfolio) != {"owner_refs", "plans"}
        or type(portfolio["owner_refs"]) is not dict
        or set(portfolio["owner_refs"]) != {s for s, _ in _PORTFOLIO_INSTRUMENTS}
        or type(portfolio["plans"]) is not list
    ):
        raise _RecoveryRequired("portfolio_binding_invalid")
    seeds, requests = {}, set()
    for plan in portfolio["plans"]:
        if (
            type(plan) is not dict
            or set(plan) != {"request_id", "input_ref", "parent_binding_ref", "states"}
            or type(plan["request_id"]) is not str
            or _QQQ_ENTRY_REQUEST_ID.fullmatch(plan["request_id"]) is None
            or plan["request_id"] in requests
            or any(
                type(plan[key]) is not str or _SHA.fullmatch(plan[key]) is None
                for key in ("input_ref", "parent_binding_ref")
            )
            or type(plan["states"]) is not dict
            or not 1 <= len(plan["states"]) <= 3
        ):
            raise _RecoveryRequired("portfolio_plan_invalid")
        requests.add(plan["request_id"])
        symbols, clocks, sides = set(), set(), set()
        for run_id, payload in plan["states"].items():
            state = KisPaperCanaryState.from_dict(payload)
            intent = state.intent
            identity = _digest(
                [binding["account_ref"], binding["basis_ref"], plan["request_id"], intent.symbol]
            )
            price_parts = [plan["input_ref"], intent.symbol, str(intent.limit_price)]
            if intent.side == "sell":
                owner = "portfolio-" + intent.symbol.lower()
                identity = _digest(
                    [
                        binding["account_ref"],
                        binding["basis_ref"],
                        plan["request_id"],
                        intent.symbol,
                        "sell",
                        owner,
                    ]
                )
                price_parts.extend(("sell", owner))
            if intent.side not in {"buy", "sell"} or (
                intent.side == "sell" and not plan["request_id"].startswith("portfolio-sell-")
            ):
                raise _RecoveryRequired("portfolio_plan_invalid")
            if (
                run_id != "bp-" + identity
                or intent.run_id != run_id
                or intent.client_order_id != "portfolio-" + identity
                or intent.decision_id != "portfolio-" + identity
                or (intent.symbol, intent.exchange) not in _PORTFOLIO_INSTRUMENTS
                or intent.symbol in symbols
                or intent.price_contract_ref != "sha256:" + _digest(price_parts)
                or state
                != KisPaperCanaryState(intent, "intent_recorded", intent.created_at, "preview")
                or payload != state.to_dict()
                or run_id in seeds
            ):
                raise _RecoveryRequired("portfolio_plan_invalid")
            _validated_portfolio_state(state, state.updated_at)
            symbols.add(intent.symbol)
            clocks.add((intent.created_at, intent.valid_until))
            sides.add(intent.side)
            seeds[run_id] = state
        if len(clocks) != 1 or len(sides) != 1:
            raise _RecoveryRequired("portfolio_plan_invalid")
    return seeds


def _stock_owner_id(instrument_binding_ref):
    if (
        type(instrument_binding_ref) is not str
        or _STOCK_BINDING_REF.fullmatch(instrument_binding_ref) is None
    ):
        raise _RecoveryRequired("stock_binding_invalid")
    return "stock-" + instrument_binding_ref.removeprefix("ref:")


def _stock_identity(binding, symbol, request_id, side):
    entry = binding["stocks"][symbol]
    return _digest(
        [
            binding["account_ref"],
            binding["basis_ref"],
            request_id,
            symbol,
            entry["exchange"],
            entry["instrument_binding_ref"],
            side,
            _stock_owner_id(entry["instrument_binding_ref"]),
        ]
    )


def _stock_price_ref(binding, symbol, input_ref, limit_price, side):
    entry = binding["stocks"][symbol]
    return "sha256:" + _digest(
        [
            input_ref,
            symbol,
            entry["exchange"],
            entry["instrument_binding_ref"],
            str(limit_price),
            side,
            _stock_owner_id(entry["instrument_binding_ref"]),
        ]
    )


def _stock_seed_states(binding):
    """Parse one explicitly bound NASD owner; no IO, adoption or migration."""
    if binding["version"] != 4:
        return {}
    registry = binding["stocks"]
    if type(registry) is not dict or len(registry) > 1:
        raise _RecoveryRequired("stock_binding_invalid")
    seeds = {}
    requests = {p["request_id"] for p in binding["portfolio"]["plans"]}
    for symbol, entry in registry.items():
        if (
            type(symbol) is not str
            or _STOCK_SYMBOL.fullmatch(symbol) is None
            or symbol in {"SPY", "QQQ", "TLT", "GLD"}
            or type(entry) is not dict
            or set(entry) != {"exchange", "instrument_binding_ref", "owner_ref", "plans"}
            or entry["exchange"] != "NASD"
            or type(entry["owner_ref"]) is not str
            or _SHA.fullmatch(entry["owner_ref"]) is None
            or type(entry["plans"]) is not list
        ):
            raise _RecoveryRequired("stock_binding_invalid")
        _stock_owner_id(entry["instrument_binding_ref"])
        for plan in entry["plans"]:
            if (
                type(plan) is not dict
                or set(plan) != {"request_id", "input_ref", "parent_binding_ref", "states"}
                or type(plan["request_id"]) is not str
                or _QQQ_ENTRY_REQUEST_ID.fullmatch(plan["request_id"]) is None
                or plan["request_id"] in requests
                or any(
                    type(plan[key]) is not str or _SHA.fullmatch(plan[key]) is None
                    for key in ("input_ref", "parent_binding_ref")
                )
                or type(plan["states"]) is not dict
                or len(plan["states"]) != 1
            ):
                raise _RecoveryRequired("stock_plan_invalid")
            requests.add(plan["request_id"])
            for run, payload in plan["states"].items():
                state = KisPaperCanaryState.from_dict(payload)
                intent = state.intent
                identity = _stock_identity(binding, symbol, plan["request_id"], intent.side)
                if (
                    run != "bk-" + identity
                    or intent.run_id != run
                    or intent.client_order_id != "stock-" + identity
                    or intent.decision_id != "stock-" + identity
                    or (intent.symbol, intent.exchange) != (symbol, "NASD")
                    or intent.price_contract_ref
                    != _stock_price_ref(
                        binding, symbol, plan["input_ref"], intent.limit_price, intent.side
                    )
                    or not intent.created_at
                    < intent.valid_until
                    <= intent.created_at + _ORDER_LIFETIME
                    or state
                    != KisPaperCanaryState(intent, "intent_recorded", intent.created_at, "preview")
                    or payload != state.to_dict()
                    or run in seeds
                ):
                    raise _RecoveryRequired("stock_plan_invalid")
                _validated_portfolio_state(state, state.updated_at)
                seeds[run] = state
    return seeds


def _seed_states(binding):
    portfolio, stocks = _portfolio_seed_states(binding), _stock_seed_states(binding)
    if portfolio.keys() & stocks.keys():
        raise _RecoveryRequired("stock_state_duplicate")
    return portfolio | stocks


def _validate_orders(orders, pattern):
    if not isinstance(orders, list):
        raise _RecoveryRequired("budget_binding_invalid")
    seen = set()
    for record in orders:
        if (
            not isinstance(record, dict)
            or set(record) != {"run_id", "intent_ref", "closed"}
            or not isinstance(record["run_id"], str)
            or pattern.fullmatch(record["run_id"]) is None
            or not isinstance(record["intent_ref"], str)
            or _SHA.fullmatch(record["intent_ref"]) is None
            or type(record["closed"]) is not bool
            or record["run_id"] in seen
        ):
            raise _RecoveryRequired("budget_binding_invalid")
        seen.add(record["run_id"])
    if any(not row["closed"] for row in orders[:-1]):
        raise _RecoveryRequired("budget_binding_invalid")


def _money(value):
    if not isinstance(value, str):
        raise _RecoveryRequired("budget_binding_invalid")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise _RecoveryRequired("budget_binding_invalid")
    return number


def _decision_evidence_path(evidence_root, decision_id):
    if re.fullmatch(r"decision:sha256:[0-9a-f]{64}", decision_id) is None:
        raise _RecoveryRequired("decision_evidence_mismatch")
    return evidence_root / "decisions" / (decision_id.removeprefix("decision:sha256:") + ".json")


def _state(root, record, *, symbol="SPY", exchange="AMEX", binding=None):
    path = root / (record["run_id"] + ".json")
    if path.is_symlink():
        raise _RecoveryRequired("budget_state_invalid")
    seed = None if binding is None else _seed_states(binding).get(record["run_id"])
    if seed is not None and not path.exists():
        # A state-store lock survives materialization/attempts; a missing state
        # with that witness must never revert to an unmaterialized seed.
        if path.with_name("." + path.name + ".lock").exists():
            raise _RecoveryRequired("portfolio_materialized_state_missing")
        state = seed
    else:
        state = KisPaperCanaryStateStore(path).read()
    if (
        state is None
        or state.intent.fingerprint != record["intent_ref"]
        or state.intent.run_id != record["run_id"]
        or (state.intent.symbol, state.intent.exchange) != (symbol, exchange)
    ):
        raise _RecoveryRequired("budget_intent_mismatch")
    return state


def project_shared_budget(
    *,
    binding,
    states: Mapping[str, KisPaperCanaryState],
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    as_of: datetime,
):
    """Pure complete shared replay from caller-attested states; never touches a store."""
    if (
        not isinstance(binding, Mapping)
        or type(binding.get("version")) is not int
        or (binding["version"], set(binding)) not in ((2, _V2_KEYS), (3, _V3_KEYS), (4, _V4_KEYS))
        or binding["account_ref"] != expected_account_ref
        or binding["basis_ref"] != expected_basis_ref
        or not isinstance(states, Mapping)
    ):
        raise _RecoveryRequired("budget_binding_invalid")
    _validate_orders(binding["orders"], _RUN_ID)
    qqq = binding["qqq"]
    if (
        type(qqq) is not dict
        or set(qqq) != {"cycle_id", "owner_ref", "orders"}
        or type(qqq["cycle_id"]) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", qqq["cycle_id"]) is None
        or type(binding["terminal_evidence"]) is not dict
    ):
        raise _RecoveryRequired("budget_binding_invalid")
    _validate_orders(qqq["orders"], _QQQ_RUN_ID)
    owners = _owners(binding)
    expected = {owner.owner_ref: ref for owner, ref in owners}
    refs = {ref.run_id: ref for owner, _ in owners for ref in owner.state_refs}
    if (
        expected != expected_owner_refs
        or any(owner.fingerprint != ref for owner, ref in owners)
        or set(states) != set(refs)
        or not set(binding["terminal_evidence"]) <= set(refs)
        or any(
            row["closed"] and row["run_id"] not in binding["terminal_evidence"]
            for row in binding["orders"] + qqq["orders"]
        )
    ):
        raise _RecoveryRequired("budget_owner_scope_invalid")
    replayed, proofs = {}, {}
    at = require_utc(as_of)
    for run, state in states.items():
        state = _validated_portfolio_state(state, at)
        if state.intent.run_id != run or state.intent.fingerprint != refs[run].intent_ref:
            raise _RecoveryRequired("budget_intent_mismatch")
        evidence = binding["terminal_evidence"].get(run)
        if evidence is not None:
            state, proof = _retained_terminal(state, evidence)
            if proof is not None:
                proofs[run] = proof
        replayed[run] = state
    return project_kis_paper_portfolio_budget(
        basis=_basis(binding),
        expected_basis_ref=expected_basis_ref,
        owners=tuple(owner for owner, _ in owners),
        expected_owner_refs=expected_owner_refs,
        states=replayed,
        as_of=at,
        cancellation_proofs=proofs,
    )


def project_budget(
    root: Path,
    binding,
    *,
    qqq_cycle_id: str | None = None,
    as_of: datetime | None = None,
    portfolio_symbol: str | None = None,
    stock_symbol: str | None = None,
) -> BudgetProjection:
    """Recompute entry cost and reservations; no snapshot is added twice."""
    if stock_symbol is not None and (portfolio_symbol is not None or qqq_cycle_id is not None):
        raise _RecoveryRequired("stock_projection_scope_invalid")
    if binding["version"] in {2, 3, 4}:
        owners = _owners(binding)
        states, proofs = {}, {}
        legacy = binding["legacy_spy"]
        if legacy is not None:
            actual = _legacy_scope(root, legacy["account_ref"], legacy["cycle_id"])
            if actual != legacy | {"owner_ref": None}:
                raise _RecoveryRequired("legacy_custody_mismatch")
        for owner, _ in owners:
            for ref in owner.state_refs:
                state = _state(
                    root,
                    {"run_id": ref.run_id, "intent_ref": ref.intent_ref},
                    symbol=owner.symbol,
                    exchange=owner.exchange,
                    binding=binding,
                )
                if as_of is not None and state.updated_at > require_utc(as_of):
                    raise _RecoveryRequired("budget_state_not_current")
                evidence = binding["terminal_evidence"].get(ref.run_id)
                if evidence is not None:
                    state, proof = _retained_terminal(state, evidence)
                    if proof is not None:
                        proofs[ref.run_id] = proof
                states[ref.run_id] = state
        projection = project_kis_paper_portfolio_budget(
            basis=_basis(binding),
            expected_basis_ref=binding["basis_ref"],
            owners=tuple(owner for owner, _ in owners),
            expected_owner_refs={owner.owner_ref: expected for owner, expected in owners},
            states=states,
            as_of=as_of
            if as_of is not None
            else max(
                [datetime.fromisoformat(binding["at"])]
                + [state.updated_at for state in states.values()]
            ),
            cancellation_proofs=proofs,
        )
        if portfolio_symbol is not None and (
            binding["version"] not in {3, 4} or portfolio_symbol not in {"SPY", "TLT", "GLD"}
        ):
            raise _RecoveryRequired("portfolio_instrument_invalid")
        selected = (
            _owner_id(binding, qqq_cycle_id)
            if portfolio_symbol is None
            else ("portfolio-" + portfolio_symbol.lower())
        )
        if stock_symbol is not None:
            if binding["version"] != 4 or stock_symbol not in binding["stocks"]:
                raise _RecoveryRequired("stock_instrument_invalid")
            selected = _stock_owner_id(binding["stocks"][stock_symbol]["instrument_binding_ref"])
        quantity = next(
            stock.quantity for stock in projection.stocks_by_owner if stock.owner_ref == selected
        )
        records = binding["orders"] + binding["qqq"]["orders"]
        if any(
            row["closed"] and row["run_id"] not in binding["terminal_evidence"] for row in records
        ):
            raise _RecoveryRequired("closed_order_evidence_missing")
        instrument = stock_symbol or portfolio_symbol or ("SPY" if qqq_cycle_id is None else "QQQ")
        stock = next(
            stock for stock in projection.stocks_by_instrument if stock.symbol == instrument
        )
        return BudgetProjection(
            quantity,
            projection.entry_cost,
            projection.reserved_buys,
            gross_cash=projection.gross_cash,
            remaining_gross_cash=projection.remaining_gross_cash,
            aggregate_quantity=stock.quantity,
            instrument_reserved_buys=stock.reserved_buys,
        )
    if stock_symbol is not None:
        raise _RecoveryRequired("stock_instrument_invalid")
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


def project_spy_owned_inventory(
    *,
    binding: Mapping[str, object],
    states: Mapping[str, KisPaperCanaryState],
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_ref: str,
    as_of: datetime,
) -> KisPaperSpyOwnedInventory:
    """Pure V2 SPY ownership replay, without adopting legacy/account holdings.

    The caller owns strict duplicate-key JSON decoding, namespace provenance and
    independently frozen expected references. Supply every referenced SPY state
    exactly once, including closed history; no file/store/credential API is used.
    """
    try:
        if (
            not isinstance(binding, Mapping)
            or set(binding) != _V2_KEYS
            or type(binding["version"]) is not int
            or binding["version"] != 2
            or type(expected_account_ref) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_account_ref) is None
            or binding["account_ref"] != expected_account_ref
            or type(expected_basis_ref) is not str
            or _SHA.fullmatch(expected_basis_ref) is None
            or binding["basis_ref"] != expected_basis_ref
            or type(expected_owner_ref) is not str
            or _SHA.fullmatch(expected_owner_ref) is None
            or binding["spy_owner_ref"] != expected_owner_ref
            or not isinstance(states, Mapping)
            or type(as_of) is not datetime
        ):
            raise KisPaperSpyOwnedInventoryError("spy_inventory_binding_invalid")
        if binding["legacy_spy"] is not None:
            raise KisPaperSpyOwnedInventoryError("spy_inventory_legacy_scope_unsupported")
        at = require_utc(as_of)
        qqq = binding["qqq"]
        if (
            not isinstance(qqq, dict)
            or set(qqq) != {"cycle_id", "owner_ref", "orders"}
            or type(qqq["cycle_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", qqq["cycle_id"]) is None
            or not isinstance(binding["terminal_evidence"], dict)
        ):
            raise KisPaperSpyOwnedInventoryError("spy_inventory_binding_invalid")
        records = binding["orders"]
        _validate_orders(records, _RUN_ID)
        _validate_orders(qqq["orders"], _QQQ_RUN_ID)
        owners = _owners(binding)
        if any(owner.fingerprint != expected for owner, expected in owners):
            raise KisPaperSpyOwnedInventoryError("spy_inventory_owner_mismatch")
        referenced = {ref.run_id for owner, _ in owners for ref in owner.state_refs}
        terminal = binding["terminal_evidence"]
        if not set(terminal) <= referenced:
            raise KisPaperSpyOwnedInventoryError("spy_inventory_terminal_scope_invalid")
        if set(states) != {record["run_id"] for record in records}:
            raise KisPaperSpyOwnedInventoryError("spy_inventory_state_scope_invalid")
        replay_states, proofs = {}, {}
        matched = retained = 0
        for record in records:
            run_id = record["run_id"]
            current = _validated_portfolio_state(states[run_id], at)
            if (
                record["closed"] is not True
                or current.phase not in {"submitted", "cancelled", "rejected", "intent_recorded"}
                or current.fill_observation_status
                not in {"available", "unavailable", "absent", "not_observed"}
            ):
                raise KisPaperSpyOwnedInventoryError("spy_inventory_outcome_unresolved")
            evidence = terminal.get(run_id)
            state, proof = _retained_terminal(current, evidence)
            saved = KisPaperCanaryState.from_dict(evidence["state"])
            if (
                saved.phase not in {"submitted", "cancelled", "rejected", "intent_recorded"}
                or _digest(evidence["state"]) != _digest(saved.to_dict())
                or (saved.cumulative_fill is not None and saved.current_fill is None)
            ):
                raise KisPaperSpyOwnedInventoryError("spy_inventory_terminal_unproven")
            replay_states[run_id] = state
            if proof is not None:
                proofs[run_id] = proof
            if state.cumulative_fill is not None and state.cumulative_fill.quantity > 0:
                matched += 1
                retained += int(current.current_fill is None)
        spy_owner = owners[0][0]
        projection = project_kis_paper_portfolio_budget(
            basis=_basis(binding),
            expected_basis_ref=expected_basis_ref,
            owners=(spy_owner,),
            expected_owner_refs={spy_owner.owner_ref: expected_owner_ref},
            states=replay_states,
            as_of=at,
            cancellation_proofs=proofs,
        )
        stock = projection.stocks_by_owner[0]
        return KisPaperSpyOwnedInventory(
            stock.quantity, stock.entry_cost, stock.reserved_buys, len(records), matched, retained
        )
    except KisPaperSpyOwnedInventoryError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        DecimalException,
        _RecoveryRequired,
        KisPaperCanaryError,
    ):
        raise KisPaperSpyOwnedInventoryError("spy_inventory_input_invalid") from None


def _basis(binding):
    return KisPaperPortfolioBudgetBasis(
        binding["account_ref"],
        _money(binding["basis_usd"]),
        _money(binding["allocated_usd"]),
        datetime.fromisoformat(binding["at"]),
    )


def _owner_id(binding, qqq_cycle_id=None):
    if qqq_cycle_id is None:
        return "spy-baseline"
    if binding["version"] not in {2, 3, 4} or binding["qqq"]["cycle_id"] != qqq_cycle_id:
        raise _RecoveryRequired("qqq_owner_binding_mismatch")
    return "qqq-" + _digest(qqq_cycle_id)


def _orders(binding, qqq_cycle_id=None):
    if qqq_cycle_id is None:
        return binding["orders"]
    _owner_id(binding, qqq_cycle_id)
    return binding["qqq"]["orders"]


def _owner(binding, owner_id, symbol, exchange, orders, *, stock_binding_ref=None):
    extra = {} if stock_binding_ref is None else {"stock_binding_ref": stock_binding_ref}
    return KisPaperPortfolioOwnerBinding(
        owner_id,
        binding["account_ref"],
        symbol,
        exchange,
        tuple(KisPaperPortfolioStateRef(row["run_id"], row["intent_ref"]) for row in orders),
        **extra,
    )


def _owners(binding):
    owners = [
        (
            _owner(binding, "spy-baseline", "SPY", "AMEX", binding["orders"]),
            binding["spy_owner_ref"],
        )
    ]
    qqq = binding["qqq"]
    owners.append(
        (
            _owner(binding, _owner_id(binding, qqq["cycle_id"]), "QQQ", "NASD", qqq["orders"]),
            qqq["owner_ref"],
        )
    )
    legacy = binding["legacy_spy"]
    if legacy is not None:
        if not isinstance(legacy, dict) or set(legacy) != {
            "cycle_id",
            "cycle_ref",
            "account_ref",
            "binding_ref",
            "orders",
            "owner_ref",
        }:
            raise _RecoveryRequired("legacy_custody_mismatch")
        owners.append(
            (
                _owner(
                    binding, "legacy-spy-" + legacy["cycle_ref"], "SPY", "AMEX", legacy["orders"]
                ),
                legacy["owner_ref"],
            )
        )
    if binding["version"] in {3, 4}:
        seeds = _portfolio_seed_states(binding)
        for symbol, exchange in _PORTFOLIO_INSTRUMENTS:
            records = [
                {
                    "run_id": run_id,
                    "intent_ref": state.intent.fingerprint,
                    "closed": run_id in binding["terminal_evidence"],
                }
                for run_id, state in seeds.items()
                if state.intent.symbol == symbol
            ]
            owners.append(
                (
                    _owner(binding, "portfolio-" + symbol.lower(), symbol, exchange, records),
                    binding["portfolio"]["owner_refs"][symbol],
                )
            )
    if binding["version"] == 4:
        seeds = _stock_seed_states(binding)
        for symbol, entry in binding["stocks"].items():
            records = [
                {
                    "run_id": run,
                    "intent_ref": state.intent.fingerprint,
                    "closed": run in binding["terminal_evidence"],
                }
                for run, state in seeds.items()
                if state.intent.symbol == symbol
            ]
            owners.append(
                (
                    _owner(
                        binding,
                        _stock_owner_id(entry["instrument_binding_ref"]),
                        symbol,
                        "NASD",
                        records,
                        stock_binding_ref=entry["instrument_binding_ref"],
                    ),
                    entry["owner_ref"],
                )
            )
    return owners


def _other_owned_intent_pending(root, binding, run_id):
    if binding["version"] not in {2, 3, 4}:
        return False
    target = _seed_states(binding).get(run_id)
    target_symbol = (
        target.intent.symbol
        if target is not None
        else "SPY"
        if _RUN_ID.fullmatch(run_id)
        else "QQQ"
        if _QQQ_RUN_ID.fullmatch(run_id)
        else None
    )
    for owner, _ in _owners(binding):
        if owner.stock_binding_ref is not None and owner.symbol != target_symbol:
            # A disjoint stock reservation is cash evidence, not a blanket SELL pause.
            continue
        for ref in owner.state_refs:
            if ref.run_id == run_id:
                continue
            state = _state(
                root,
                {"run_id": ref.run_id, "intent_ref": ref.intent_ref},
                symbol=owner.symbol,
                exchange=owner.exchange,
                binding=binding,
            )
            proof = None
            evidence = binding["terminal_evidence"].get(ref.run_id)
            if evidence is not None:
                state, proof = _retained_terminal(state, evidence)
            if _terminal(state, proof):
                continue
            # Known, never-attempted BUYs already carry their full reservation.
            # SELLs have no quantity reservation; attempted orders need recovery.
            if not (
                state.intent.side == "buy"
                and state.phase == "intent_recorded"
                and state.submission_started_at is None
            ):
                return True
    return False


def _legacy_scope(root, account_ref, cycle_id=None):
    active = _read_json(root / ".spy_fill_active.json")
    if cycle_id is None:
        if active is None:
            return None
        if not isinstance(active, dict) or set(active) != {"cycle_ref", "account_ref"}:
            raise _RecoveryRequired("legacy_custody_mismatch")
        cycle_ref = active["cycle_ref"]
    else:
        cycle_ref = _digest(cycle_id)
    if not isinstance(cycle_ref, str) or re.fullmatch(r"[0-9a-f]{64}", cycle_ref) is None:
        raise _RecoveryRequired("legacy_custody_mismatch")
    saved = _read_json(root / ".spy_fill_cycles" / (cycle_ref + ".json"))
    if saved is None or (cycle_id is not None and saved["cycle_id"] != cycle_id):
        raise _RecoveryRequired("legacy_custody_mismatch")
    cycle_id = saved["cycle_id"]
    if _digest(cycle_id) != cycle_ref or (
        active is not None and active != {"cycle_ref": cycle_ref, "account_ref": account_ref}
    ):
        raise _RecoveryRequired("legacy_custody_mismatch")
    _validate_cycle_binding(saved, _binding_identity(cycle_id, account_ref))
    states, stores, orders = {}, {}, []
    for side in ("buy", "sell"):
        state = KisPaperCanaryStateStore(root / (saved[side + "_run_id"] + ".json")).read()
        _validate_leg(state, saved, side, True)
        states[side] = state
        if state is not None:
            if saved[side + "_intent_ref"] != state.intent.fingerprint:
                raise _RecoveryRequired("legacy_custody_mismatch")
            orders.append({"run_id": state.intent.run_id, "intent_ref": state.intent.fingerprint})
    successors = _load_successors(saved, root, stores, states)
    for intent in successors:
        if states[intent.run_id] is None:
            raise _RecoveryRequired("legacy_custody_mismatch")
        orders.append({"run_id": intent.run_id, "intent_ref": intent.fingerprint})
    return {
        "cycle_id": cycle_id,
        "cycle_ref": cycle_ref,
        "account_ref": account_ref,
        "binding_ref": "sha256:" + _digest(saved),
        "orders": orders,
        "owner_ref": None,
    }


def _terminal(state, proof=None):
    fill = state.cumulative_fill
    if state.phase == "rejected":
        return state.submit_response_category == "provider_rejected" and fill is None
    if state.phase == "intent_recorded":
        return state.submission_started_at is None and state.updated_at >= state.intent.valid_until
    if (
        fill is not None
        and fill.quantity > 0
        and (fill.quantity == state.intent.quantity or fill.remaining_quantity == 0)
    ):
        return True
    return (
        state.phase == "cancelled"
        and proof is not None
        and proof.cancellation_confirmed
        and proof.status == "available"
        and proof.fill == state.current_fill
        and proof.observed_at == state.fill_observed_at
    )


def _terminal_payload(state, observation=None):
    proof = observation if observation is not None and observation.cancellation_confirmed else None
    if not _terminal(state, proof):
        raise _RecoveryRequired("closed_order_evidence_missing")
    return {
        "state": state.to_dict(),
        "cancellation": None
        if proof is None
        else {
            "row_count": proof.row_count,
            "same_day_order_id_seen": proof.same_day_order_id_seen,
            "status": proof.status,
            "fill": proof.fill.to_dict(),
            "observed_at": proof.observed_at.isoformat(),
            "cancellation_confirmed": True,
        },
    }


def _qqq_rejected_entry(record, state, evidence) -> bool:
    """Require the exact retained facts of a submitted, rejected QQQ unit BUY."""
    if (
        not isinstance(record, dict)
        or set(record) != {"run_id", "intent_ref", "closed"}
        or record.get("closed") is not True
        or type(state) is not KisPaperCanaryState
        or (state.intent.symbol, state.intent.exchange, state.intent.side, state.intent.quantity)
        != ("QQQ", "NASD", "buy", Decimal(1))
        or record.get("run_id") != state.intent.run_id
        or record.get("intent_ref") != state.intent.fingerprint
        or state.phase != "rejected"
        or state.reason_code != "submit_rejected"
        or state.submit_response_category != "provider_rejected"
        or state.submission_started_at is None
        or state.broker_order_id is not None
        or state.submitted_at is not None
        or state.cumulative_fill is not None
        or not isinstance(evidence, dict)
        or set(evidence) != {"state", "cancellation"}
        or evidence["cancellation"] is not None
    ):
        return False
    try:
        return KisPaperCanaryState.from_dict(evidence["state"]) == state and _digest(
            evidence["state"]
        ) == _digest(state.to_dict())
    except (ValueError, TypeError, KeyError, AttributeError, DecimalException):
        return False


def _qqq_closed_unfilled_entry(record, state, evidence) -> bool:
    """A new tag may follow an exact rejection or expired never-sent BUY."""
    if _qqq_rejected_entry(record, state, evidence):
        return True
    if (
        not isinstance(record, dict)
        or set(record) != {"run_id", "intent_ref", "closed"}
        or record.get("closed") is not True
        or type(state) is not KisPaperCanaryState
        or (state.intent.symbol, state.intent.exchange, state.intent.side, state.intent.quantity)
        != ("QQQ", "NASD", "buy", Decimal(1))
        or record.get("run_id") != state.intent.run_id
        or record.get("intent_ref") != state.intent.fingerprint
        or state.phase != "intent_recorded"
        or state.reason_code != "intent_expired"
        or state.updated_at < state.intent.valid_until
        or state.cancel_after_submit
        or state.fill_observation_status != "not_observed"
        or any(
            value is not None
            for value in (
                state.submission_started_at,
                state.submitted_at,
                state.broker_order_id,
                state.cumulative_fill,
                state.fill_observed_at,
                state.submit_response_category,
                state.submit_upstream_code,
            )
        )
        or not isinstance(evidence, dict)
        or set(evidence) != {"state", "cancellation"}
        or evidence["cancellation"] is not None
    ):
        return False
    try:
        return KisPaperCanaryState.from_dict(evidence["state"]) == state and _digest(
            evidence["state"]
        ) == _digest(state.to_dict())
    except (ValueError, TypeError, KeyError, AttributeError, DecimalException):
        return False


def _qqq_filled_entry(records, states, terminal_evidence) -> KisPaperCanaryState | None:
    """Accept closed unfilled BUY prefix -> one filled BUY -> unit SELL suffix."""
    if len(records) != len(states):
        return None
    entry = None
    for record, state in zip(records, states, strict=True):
        if (
            type(state) is not KisPaperCanaryState
            or (state.intent.symbol, state.intent.exchange, state.intent.quantity)
            != ("QQQ", "NASD", Decimal(1))
            or record.get("run_id") != state.intent.run_id
            or record.get("intent_ref") != state.intent.fingerprint
        ):
            return None
        evidence = terminal_evidence.get(state.intent.run_id)
        if entry is not None:
            if state.intent.side != "sell":
                return None
            continue
        if _qqq_closed_unfilled_entry(record, state, evidence):
            continue
        if (
            state.intent.side != "buy"
            or record.get("closed") is not True
            or state.broker_order_id is None
            or (state.submission_started_at or state.submitted_at) is None
            or state.cumulative_fill is None
            or state.cumulative_fill.quantity != 1
        ):
            return None
        try:
            _retained_terminal(state, evidence)
        except (
            _RecoveryRequired,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            DecimalException,
        ):
            return None
        entry = state
    return entry


def _retained_terminal(current, payload):
    if not isinstance(payload, dict) or set(payload) != {"state", "cancellation"}:
        raise _RecoveryRequired("closed_order_evidence_missing")
    saved = KisPaperCanaryState.from_dict(payload["state"])
    proof = None
    if payload["cancellation"] is not None:
        raw = payload["cancellation"]
        if not isinstance(raw, dict) or set(raw) != {
            "row_count",
            "same_day_order_id_seen",
            "status",
            "fill",
            "observed_at",
            "cancellation_confirmed",
        }:
            raise _RecoveryRequired("closed_order_evidence_missing")
        proof = KisPaperExecutionObservation(
            **(
                raw
                | {
                    "fill": KisPaperCumulativeFill.from_dict(raw["fill"]),
                    "observed_at": datetime.fromisoformat(raw["observed_at"]),
                }
            )
        )
    if (
        not _terminal(saved, proof)
        or any(
            getattr(current, field) != getattr(saved, field)
            for field in ("intent", "broker_order_id", "submission_started_at", "submitted_at")
        )
        or current.updated_at < saved.updated_at
    ):
        raise _RecoveryRequired("closed_order_evidence_missing")
    if saved.cumulative_fill is not None:
        if current.cumulative_fill is None:
            raise _RecoveryRequired("closed_order_evidence_missing")
        current.cumulative_fill.advance(saved.cumulative_fill)
        if saved.cumulative_fill.remaining_quantity == 0 and (
            current.cumulative_fill.quantity != saved.cumulative_fill.quantity
            or current.cumulative_fill.gross_amount != saved.cumulative_fill.gross_amount
        ):
            raise _RecoveryRequired("closed_order_evidence_missing")
        if proof is not None and current.cumulative_fill.quantity != 0:
            raise _RecoveryRequired("closed_order_evidence_missing")
    elif current.cumulative_fill is not None or current.phase != saved.phase:
        raise _RecoveryRequired("closed_order_evidence_missing")
    # A dated cancellation fact survives a later unavailable read. Never rewrite
    # the live canary state or invent an observation timestamp to retain it.
    return (saved if proof is not None else current), proof


@dataclass(frozen=True, repr=False)
class KisPaperGrossRoundTrip:
    """Private exact cumulative cashflows, not fees, settled cash or net PnL."""

    buy_gross_usd: Decimal
    sell_gross_usd: Decimal
    gross_realized_usd: Decimal
    fill_refs: tuple[str, str]

    def __post_init__(self):
        if (
            any(
                type(value) is not Decimal or not value.is_finite()
                for value in (self.buy_gross_usd, self.sell_gross_usd, self.gross_realized_usd)
            )
            or self.buy_gross_usd <= 0
            or self.sell_gross_usd <= 0
            or Fraction(self.gross_realized_usd)
            != Fraction(self.sell_gross_usd) - Fraction(self.buy_gross_usd)
            or type(self.fill_refs) is not tuple
            or len(self.fill_refs) != 2
            or any(type(ref) is not str or _SHA.fullmatch(ref) is None for ref in self.fill_refs)
            or len(set(self.fill_refs)) != 2
        ):
            raise ValueError("gross_roundtrip_invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "source": "kis_paper",
            "currency": "USD",
            "status": "gross_realized_observed",
            "gross_pnl_sign": (
                "positive"
                if self.gross_realized_usd > 0
                else "negative"
                if self.gross_realized_usd < 0
                else "zero"
            ),
            "matched_fill_count": 2,
            "roundtrip_count": 1,
            "owned_flat": True,
            "fees": "not_observed",
            "settled_cash": "not_observed",
            "net_pnl": "not_observed",
        }


def project_qqq_unit_gross_pnl(
    *,
    binding: Mapping[str, object],
    states: Mapping[str, KisPaperCanaryState],
    cycle_id: str,
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_ref: str,
    as_of: datetime,
) -> KisPaperGrossRoundTrip:
    """Replay one caller-bound closed QQQ pair without IO or accumulating fills.

    Account proof comes from caller-verified custody, never from the fills.
    Each cumulative final state contributes once; reruns add nothing. Other
    owners are outside this projection, not silently reconciled by it.
    """
    if (
        not isinstance(binding, Mapping)
        or set(binding) != _V2_KEYS
        or type(binding["version"]) is not int
        or binding["version"] != 2
        or not isinstance(expected_account_ref, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_account_ref) is None
        or binding["account_ref"] != expected_account_ref
        or not isinstance(states, Mapping)
    ):
        raise ValueError("gross_roundtrip_binding_invalid")
    require_utc(as_of)
    basis = _basis(binding)
    if Fraction(basis.allocated_usd) != Fraction(basis.basis_usd) * Fraction(BUDGET_FRACTION):
        raise ValueError("gross_roundtrip_basis_invalid")
    owner_id = _owner_id(binding, cycle_id)
    records = _orders(binding, cycle_id)
    _validate_orders(records, _QQQ_RUN_ID)
    terminal = binding["terminal_evidence"]
    if (
        not isinstance(terminal, Mapping)
        or any(record["closed"] is not True for record in records)
        or set(states) != {record["run_id"] for record in records}
    ):
        raise ValueError("gross_roundtrip_incomplete")
    ordered = tuple(states[record["run_id"]] for record in records)
    entry = _qqq_filled_entry(records, ordered, terminal)
    if entry is None:
        raise ValueError("gross_roundtrip_entry_invalid")
    index = ordered.index(entry)
    if len(ordered) != index + 2:
        raise ValueError("gross_roundtrip_pair_invalid")
    exit_state = ordered[-1]
    if (
        exit_state.intent.side != "sell"
        or exit_state.broker_order_id is None
        or (exit_state.submission_started_at or exit_state.submitted_at) is None
        or exit_state.cumulative_fill is None
        or exit_state.cumulative_fill.quantity != 1
    ):
        raise ValueError("gross_roundtrip_exit_invalid")
    for state in ordered:
        if state.fill_observation_status in {"conflict", "identity_mismatch"}:
            raise ValueError("gross_roundtrip_fill_conflict")
        _retained_terminal(state, terminal.get(state.intent.run_id))
    owner = _owner(binding, owner_id, "QQQ", "NASD", records)
    replay = project_kis_paper_portfolio_budget(
        basis=basis,
        expected_basis_ref=expected_basis_ref,
        owners=(owner,),
        expected_owner_refs={owner_id: expected_owner_ref},
        states=states,
        as_of=as_of,
    )
    if (
        binding["basis_ref"] != expected_basis_ref
        or binding["qqq"]["owner_ref"] != expected_owner_ref
    ):
        raise ValueError("gross_roundtrip_custody_mismatch")
    if any(
        value != 0
        for value in (
            replay.stocks_by_owner[0].quantity,
            replay.entry_cost,
            replay.reserved_buys,
        )
    ):
        raise ValueError("gross_roundtrip_not_flat")
    buy, sell = entry.cumulative_fill, exit_state.cumulative_fill
    return KisPaperGrossRoundTrip(
        buy.gross_amount,
        sell.gross_amount,
        _exact_decimal(Fraction(sell.gross_amount) - Fraction(buy.gross_amount)),
        (buy.identity_ref, sell.identity_ref),
    )


def _migrate_binding(root, binding, config, qqq_cycle_id, *, as_of):
    if binding["version"] in {2, 3, 4}:
        _owner_id(binding, qqq_cycle_id)
        return binding
    legacy_account = _cycle_binding("unused", config)["account_ref"]
    legacy = _legacy_scope(root, legacy_account)
    migrated = binding | {
        "version": 2,
        "basis_ref": _basis(binding).fingerprint,
        "spy_owner_ref": None,
        "qqq": {"cycle_id": qqq_cycle_id, "owner_ref": None, "orders": []},
        "legacy_spy": legacy,
        "terminal_evidence": {},
    }
    for row in binding["orders"]:
        if row["closed"]:
            migrated["terminal_evidence"][row["run_id"]] = _terminal_payload(_state(root, row))
    migrated["spy_owner_ref"] = _owner(
        migrated, "spy-baseline", "SPY", "AMEX", binding["orders"]
    ).fingerprint
    migrated["qqq"]["owner_ref"] = _owner(
        migrated, _owner_id(migrated, qqq_cycle_id), "QQQ", "NASD", []
    ).fingerprint
    if legacy is not None:
        legacy["owner_ref"] = _owner(
            migrated, "legacy-spy-" + legacy["cycle_ref"], "SPY", "AMEX", legacy["orders"]
        ).fingerprint
    project_budget(root, migrated, qqq_cycle_id=qqq_cycle_id, as_of=as_of)
    _atomic_json(root / BUDGET_FILE, migrated)
    return migrated


def conflicts_with_budget_strategy(root: Path, run_id: str, symbol: str) -> bool:
    """Shared new-intent conflict only; recovery/cancellation bypass this check."""
    try:
        binding = _load_binding(root)
        stock_scope = (
            binding is not None and binding["version"] == 4 and symbol in binding["stocks"]
        )
        if symbol not in {"SPY", "TLT", "GLD"} and not stock_scope:
            return False
        if stock_scope:
            if _STOCK_RUN_ID.fullmatch(run_id):
                return True
            owned = project_budget(root, binding, stock_symbol=symbol)
            return bool(owned.quantity or owned.instrument_reserved_buys)
        if _PORTFOLIO_RUN_ID.fullmatch(run_id):
            # Prepared portfolio identities have no submission route in this package.
            return True
        if symbol in {"TLT", "GLD"}:
            if binding is None or binding["version"] not in {3, 4}:
                return False
            owned = project_budget(root, binding, portfolio_symbol=symbol)
            return bool(owned.quantity or owned.instrument_reserved_buys)
        if binding is None:
            return _RUN_ID.fullmatch(run_id) is not None
        projection = project_budget(root, binding)
        pending = [row for row in binding["orders"] if not row["closed"]]
        if pending and pending[0]["run_id"] == run_id:
            return False
        if binding["version"] in {3, 4} and projection.reserved_buys:
            return True
        # An orphan/closed budget intent cannot be dispatched outside its owner.
        quantity = (
            projection.aggregate_quantity if binding["version"] in {3, 4} else projection.quantity
        )
        return bool(pending or quantity or _RUN_ID.fullmatch(run_id))
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
    qqq_cycle_id: str | None = None,
    qqq_entry_request_id: str | None = None,
    spy_reduction_quantity: Decimal | None = None,
) -> KisPaperBudgetOutcome:
    """Run the SPY baseline or one explicitly bound QQQ/NASD unit cycle.

    QQQ requires its own instrument-bound enter/exit receipt from the caller.
    Both routes share the same allocation and locks; neither adopts positions.
    An explicit entry request identifies a BUY independently of refreshed receipts.
    SPY exits default to all baseline-owned shares; an explicit reduction is
    positive whole shares, never resized after its intent has been retained.
    """
    if spy_reduction_quantity is not None and (
        qqq_cycle_id is not None
        or not isinstance(spy_reduction_quantity, Decimal)
        or not spy_reduction_quantity.is_finite()
        or spy_reduction_quantity <= 0
        or spy_reduction_quantity != spy_reduction_quantity.to_integral_value()
    ):
        raise ValueError("SPY reduction quantity invalid")
    if qqq_cycle_id is not None and (
        not isinstance(qqq_cycle_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", qqq_cycle_id) is None
    ):
        raise ValueError("QQQ cycle identity invalid")
    if qqq_entry_request_id is not None and (
        qqq_cycle_id is None
        or not isinstance(qqq_entry_request_id, str)
        or _QQQ_ENTRY_REQUEST_ID.fullmatch(qqq_entry_request_id) is None
    ):
        raise ValueError("QQQ entry request identity invalid")
    symbol, exchange = ("SPY", "AMEX") if qqq_cycle_id is None else ("QQQ", "NASD")
    scope = (
        {}
        if qqq_cycle_id is None
        else {
            "instrument": "QQQ",
            "exchange": "NASD",
            "owned_cycle_ref": "sha256:" + _digest(qqq_cycle_id),
        }
    )
    evidence_root = artifact_root / "execution" / "kis-paper-spy-budget"
    if qqq_cycle_id is not None:
        evidence_root = (
            artifact_root / "execution" / "kis-paper-qqq-unit-cycle" / _digest(qqq_cycle_id)
        )

    def at():
        return _session_now(now=now, clock=clock)

    observed_at = at()
    session_id = session_id or f"budget-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", session_id) is None:
        raise ValueError("budget session identity invalid")
    if not execute:
        return KisPaperBudgetOutcome("preview", "preview", observed_at, **scope)
    paths_valid = False
    failure_stage = "config"

    def result(status, reason, *, daily_receipt_diagnostic=None, failure_diagnostic=None):
        nonlocal failure_stage
        failure_stage = "persist"
        outcome = KisPaperBudgetOutcome(
            status, reason, at(), daily_receipt_diagnostic, failure_diagnostic, **scope
        )
        destination = evidence_root / session_id / "outcome.json"
        _atomic_json(destination, outcome.safe_payload())
        return outcome

    try:
        if environment.get("THERICHER_MODE", "off").strip().lower() == "kis_live":
            return KisPaperBudgetOutcome(
                "recovery_required", "live_mode_unavailable", observed_at, **scope
            )
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

        def project(binding):
            return project_budget(
                root,
                binding,
                qqq_cycle_id=qqq_cycle_id,
                as_of=at() if binding["version"] in {2, 3, 4} else None,
            )

        def read_state(record):
            return _state(root, record, symbol=symbol, exchange=exchange)

        def check_reduction_quantity(state):
            if (
                spy_reduction_quantity is not None
                and state.intent.side == "sell"
                and state.intent.quantity != spy_reduction_quantity
            ):
                raise _RecoveryRequired("spy_reduction_quantity_mismatch")

        def retain_terminal(binding, state, observation=None):
            if binding["version"] in {2, 3, 4} and _terminal(state, observation):
                evidence = binding["terminal_evidence"]
                if state.intent.run_id not in evidence:
                    evidence[state.intent.run_id] = _terminal_payload(state, observation)

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
                submit_permitted=is_us_equity_regular_session_window,
                submit_reconciliation_check=permitted,
                execution_control_path=execution_control_path,
                require_existing_state=True,
                price_contract_ref=intent.price_contract_ref,
            )

        def fresh_book(snapshot=None):
            nonlocal failure_stage
            previous_stage = failure_stage
            failure_stage = "account"
            snapshot = client.snapshot() if snapshot is None else snapshot
            if qqq_cycle_id is None:
                quantity, opens = _spy_book(snapshot, at(), config)
            else:
                observed_at = at()
                times = [
                    snapshot.captured_at,
                    snapshot.identity.captured_at,
                    snapshot.open_orders.captured_at,
                    snapshot.cash.captured_at,
                    snapshot.orderable_funds.captured_at,
                ]
                times.extend(
                    item.captured_at for item in (*snapshot.positions, *snapshot.open_orders.orders)
                )
                if (
                    snapshot.identity.masked_account != config.masked_account_identity
                    or (not snapshot.open_orders.complete)
                    or any(
                        not timedelta(seconds=-5)
                        <= observed_at - value
                        <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
                        for value in times
                    )
                ):
                    raise _RecoveryRequired("snapshot_unavailable")
                positions = [item for item in snapshot.positions if item.symbol == "QQQ"]
                if len(positions) > 1 or any(
                    item.exchange != "NASD" or item.currency != "USD" for item in positions
                ):
                    raise _RecoveryRequired("position_contradiction")
                quantity = sum((item.quantity for item in positions), Decimal(0))
                opens = [item for item in snapshot.open_orders.orders if item.symbol == "QQQ"]
            if snapshot.cash.currency != "USD" or snapshot.orderable_funds.currency != "USD":
                raise _RecoveryRequired("funds_currency_mismatch")
            funds = min(snapshot.cash.available_cash, snapshot.orderable_funds.orderable_funds)
            failure_stage = previous_stage
            return quantity, opens, funds

        def permitted(binding, state):
            def check(reconciliation, submit_at):
                nonlocal failure_stage
                previous_stage = failure_stage
                if not is_us_equity_regular_session_window(submit_at):
                    return False
                failure_stage = "ownership"
                owned = project(binding)
                if (
                    qqq_cycle_id is None
                    and state.intent.side == "sell"
                    and _other_owned_intent_pending(root, binding, state.intent.run_id)
                ):
                    raise _RecoveryRequired("other_owned_intent_pending")
                if reconciliation.snapshot is None:
                    raise _RecoveryRequired("snapshot_unavailable")
                # Reuse the canary's just-read account, revalidating its timestamps.
                quantity, opens, funds = fresh_book(reconciliation.snapshot)
                book_quantity = (
                    owned.aggregate_quantity if binding["version"] in {3, 4} else owned.quantity
                )
                if opens or quantity != book_quantity:
                    raise _RecoveryRequired("pre_submit_ownership_changed")
                if state.intent.side == "buy":
                    if qqq_cycle_id is not None:
                        funds = min(funds, exact_qqq_funds(state.intent.limit_price))
                        if not all(
                            _qqq_closed_unfilled_entry(
                                row,
                                read_state(row),
                                binding["terminal_evidence"].get(row["run_id"]),
                            )
                            for row in _orders(binding, qqq_cycle_id)
                            if row["run_id"] != state.intent.run_id
                        ):
                            raise _RecoveryRequired("qqq_entry_history_not_rejected")
                    if state.intent.quantity * state.intent.limit_price > funds:
                        raise _RecoveryRequired("buying_power_changed")
                    if binding["version"] in {2, 3, 4} and owned.reserved_buys > funds:
                        raise _RecoveryRequired("buying_power_changed")
                elif state.intent.quantity > owned.quantity:
                    raise _RecoveryRequired("unowned_sell")
                failure_stage = previous_stage
                return True

            return check

        def exact_qqq_funds(price):
            nonlocal failure_stage
            previous_stage = failure_stage
            failure_stage = "account"
            cash, orderable = client.orderable_funds_at_limit(
                symbol="QQQ",
                exchange="NASD",
                limit_price=price,
            )
            observed_at = at()
            if (
                type(cash) is not KisPaperCashSnapshot
                or type(orderable) is not KisPaperOrderableFundsSnapshot
                or (cash.currency, orderable.currency) != ("USD", "USD")
                or (
                    orderable.reference_symbol,
                    orderable.reference_exchange,
                    orderable.reference_price,
                )
                != ("QQQ", "NASD", price)
                or any(
                    not timedelta(seconds=-5)
                    <= observed_at - value
                    <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
                    for value in (cash.captured_at, orderable.captured_at)
                )
            ):
                raise _RecoveryRequired("orderability_binding_mismatch")
            failure_stage = previous_stage
            return min(cash.available_cash, orderable.orderable_funds)

        def bind_order(binding, state):
            nonlocal failure_stage
            record = {
                "run_id": state.intent.run_id,
                "intent_ref": state.intent.fingerprint,
                "closed": False,
            }
            proposed = copy.deepcopy(binding)
            _orders(proposed, qqq_cycle_id).append(record)
            if proposed["version"] in {2, 3, 4}:
                owner = _owner(
                    proposed,
                    _owner_id(proposed, qqq_cycle_id),
                    symbol,
                    exchange,
                    _orders(proposed, qqq_cycle_id),
                )
                if qqq_cycle_id is None:
                    proposed["spy_owner_ref"] = owner.fingerprint
                else:
                    proposed["qqq"]["owner_ref"] = owner.fingerprint
            failure_stage = "ownership"
            project(proposed)
            failure_stage = "persist"
            _atomic_json(root / BUDGET_FILE, proposed)
            binding.clear()
            binding.update(proposed)
            failure_stage = "ownership"
            project(binding)
            return record

        def recover_qqq_orphan(binding, run_id):
            nonlocal failure_stage
            state = KisPaperCanaryStateStore(root / (run_id + ".json")).read()
            if (
                state is None
                or state.phase != "intent_recorded"
                or any(
                    value is not None
                    for value in (
                        state.submission_started_at,
                        state.broker_order_id,
                        state.submitted_at,
                        state.cumulative_fill,
                        state.submit_response_category,
                        state.submit_upstream_code,
                        state.fill_observed_at,
                    )
                )
                or state.cancel_after_submit
                or state.updated_at > at()
            ):
                raise _RecoveryRequired("orphan_intent_requires_reconciliation")
            intent = state.intent
            if (
                (intent.run_id, intent.symbol, intent.exchange, intent.side, intent.quantity)
                != (run_id, "QQQ", "NASD", "buy", Decimal(1))
                or re.fullmatch(r"receipt-[0-9a-f]{64}", intent.decision_id) is None
                or intent.price_contract_ref is None
            ):
                raise _RecoveryRequired("budget_intent_mismatch")
            receipt_id = "decision:sha256:" + intent.decision_id.removeprefix("receipt-")
            decision_path = _decision_evidence_path(evidence_root, receipt_id)
            if decision_path.is_symlink():
                raise _RecoveryRequired("decision_evidence_mismatch")
            payload = _read_json(decision_path)
            if payload is None:
                raise _RecoveryRequired("decision_evidence_mismatch")
            receipt = ResearchDecisionReceipt(
                **(
                    payload
                    | {
                        "decided_at": datetime.fromisoformat(payload["decided_at"]),
                        "valid_until": datetime.fromisoformat(payload["valid_until"]),
                    }
                )
            )
            if receipt.decision_id != receipt_id or _digest(payload) != _digest(
                receipt.to_payload()
            ):
                raise _RecoveryRequired("decision_evidence_mismatch")
            if qqq_entry_request_id is None and run_id != "bq-" + _digest(
                [qqq_cycle_id, receipt.decision_id]
            ):
                raise _RecoveryRequired("orphan_intent_requires_reconciliation")
            # Reattest the original bridge at creation, never refresh its price or TTL.
            prepared = prepare_kis_paper_decision(
                receipt,
                binding=PaperDecisionExecutionBinding(
                    proposal_ref=receipt.proposal_ref,
                    symbol="QQQ",
                    exchange="NASD",
                    quantity=Decimal(1),
                ),
                limit_proof=KisPaperLimitProof(
                    receipt_id=receipt.decision_id,
                    price_contract_ref=intent.price_contract_ref,
                    symbol="QQQ",
                    exchange="NASD",
                    limit_price=intent.limit_price,
                    observed_at=intent.created_at,
                    valid_until=intent.valid_until,
                    final_limit_tick_valid=True,
                ),
                as_of=intent.created_at,
            )
            if (
                prepared.status != "ready"
                or KisPaperCanaryIntent.from_decision(
                    prepared.kis_paper_decision,
                    run_id=run_id,
                    price_contract_ref=prepared.price_contract_ref,
                ).fingerprint
                != intent.fingerprint
            ):
                raise _RecoveryRequired("budget_intent_mismatch")
            if not all(
                _qqq_closed_unfilled_entry(
                    row, read_state(row), binding["terminal_evidence"].get(row["run_id"])
                )
                for row in _orders(binding, qqq_cycle_id)
            ):
                raise _RecoveryRequired("qqq_entry_history_not_rejected")
            projection = project(binding)
            quantity, opens, funds = fresh_book()
            book_quantity = (
                projection.aggregate_quantity
                if binding["version"] in {3, 4}
                else projection.quantity
            )
            if quantity != book_quantity or opens or projection.quantity != 0:
                raise _RecoveryRequired("pre_submit_ownership_changed")
            room = (
                _money(binding["allocated_usd"]) - projection.entry_cost - projection.reserved_buys
            )
            if binding["version"] in {2, 3, 4}:
                room = min(room, projection.remaining_gross_cash)
            available = (
                funds - projection.reserved_buys if binding["version"] in {2, 3, 4} else funds
            )
            if intent.quantity * intent.limit_price > min(room, available):
                raise _RecoveryRequired("orphan_budget_conflict")
            record = bind_order(binding, state)
            outcome = run_intent(state, permitted=permitted(binding, state))
            return finish_order(binding, record, outcome.reconciliation)

        def finish_order(binding, record, reconciliation):
            nonlocal failure_stage
            failure_stage = "reconcile"
            state = read_state(record)
            store = KisPaperCanaryStateStore(root / (state.intent.run_id + ".json"))
            if (
                state.phase == "rejected" and state.submit_response_category == "provider_rejected"
            ) or (
                state.phase == "intent_recorded"
                and state.submission_started_at is None
                and at() >= state.intent.valid_until
            ):
                record["closed"] = True
                retain_terminal(binding, state)
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
                if binding["version"] in {2, 3, 4}:
                    retain_terminal(binding, store.read(), reconciliation.execution)
                    _atomic_json(root / BUDGET_FILE, binding)
                return result("pending", "own_order_cancellation_observed")
            failure_stage = "ownership"
            retain_terminal(binding, state, reconciliation.execution)
            projection = project(binding)
            quantity, opens, _funds = fresh_book()
            failure_stage = "reconcile"
            fill = state.current_fill
            if fill is None:
                return result("pending", "exact_fill_unavailable")
            if not timedelta(0) <= at() - fill.observed_at <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE:
                return result("pending", "exact_fill_not_current")
            book_quantity = (
                projection.aggregate_quantity
                if binding["version"] in {3, 4}
                else projection.quantity
            )
            if quantity != book_quantity:
                return result("pending", "position_fill_not_aligned")
            if opens:
                return result("pending", "order_still_open")
            if fill.quantity != state.intent.quantity and fill.remaining_quantity != 0:
                return result("pending", "remaining_quantity_unresolved")
            if (
                binding["version"] in {2, 3, 4}
                and state.intent.run_id not in binding["terminal_evidence"]
            ):
                return result("pending", "remaining_quantity_unresolved")
            record["closed"] = True
            failure_stage = "persist"
            _atomic_json(root / BUDGET_FILE, binding)
            return result("order_complete", "exact_order_and_position_reconciled")

        failure_stage = "ownership"
        with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
            with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
                binding = _load_binding(root, account_ref)
                if binding is not None and qqq_cycle_id is not None:
                    binding = _migrate_binding(root, binding, config, qqq_cycle_id, as_of=at())
                if binding is not None and binding["version"] in {2, 3, 4}:
                    legacy = binding["legacy_spy"]
                    if (
                        legacy is not None
                        and legacy["account_ref"]
                        != _cycle_binding(legacy["cycle_id"], config)["account_ref"]
                    ):
                        raise _RecoveryRequired("account_binding_mismatch")
                    # Reattest the whole allocation, even when this owner's signal
                    # is missing or another owner's exact outcome remains unknown.
                    project(binding)
                records = [] if binding is None else _orders(binding, qqq_cycle_id)
                if binding is not None and records and not records[-1]["closed"]:
                    record = records[-1]
                    state = read_state(record)
                    check_reduction_quantity(state)
                    if (
                        qqq_cycle_id is None
                        and state.intent.side == "sell"
                        and state.phase == "intent_recorded"
                        and at() < state.intent.valid_until
                        and _other_owned_intent_pending(root, binding, state.intent.run_id)
                    ):
                        return result("no_intent", "other_owned_intent_pending")
                    outcome = run_intent(state, permitted=permitted(binding, state))
                    recovered = finish_order(binding, record, outcome.reconciliation)
                    if (
                        qqq_cycle_id is not None
                        or not record["closed"]
                        or state.phase == "intent_recorded"
                    ):
                        return recovered
                orphan_ids = set()
                if qqq_cycle_id is not None and binding is not None:
                    referenced = {row["run_id"] for row in records}
                    orphan_ids = {
                        path.stem
                        for path in root.glob("bq-*.json")
                        if _QQQ_RUN_ID.fullmatch(path.stem) and path.stem not in referenced
                    }
                    if orphan_ids:
                        if len(orphan_ids) != 1:
                            raise _RecoveryRequired("orphan_intent_requires_reconciliation")
                        run_id = next(iter(orphan_ids))
                        if qqq_entry_request_id is not None and run_id != "bq-" + _digest(
                            [qqq_cycle_id, "entry-request-v1", qqq_entry_request_id]
                        ):
                            raise _RecoveryRequired("orphan_intent_requires_reconciliation")
                        return recover_qqq_orphan(binding, run_id)
                if not is_us_equity_regular_session_window(at()):
                    return result("not_due", "outside_regular_session")
                # A stale/absent new signal cannot bypass recovery of a previous order.
                failure_stage = "new_input"
                try:
                    receipt = receipt_loader(at())
                except (OSError, ValueError) as error:
                    return result(
                        "no_intent",
                        "daily_input_unavailable",
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
                if spy_reduction_quantity is not None and side != "sell":
                    return result("no_intent", "spy_reduction_requires_exit")
                run_id = (
                    "bs-" + hashlib.sha256(receipt.decision_id.encode()).hexdigest()
                    if qqq_cycle_id is None
                    else "bq-" + _digest([qqq_cycle_id, "entry-request-v1", qqq_entry_request_id])
                    if side == "buy" and qqq_entry_request_id is not None
                    else "bq-" + _digest([qqq_cycle_id, receipt.decision_id])
                )
                if spy_reduction_quantity is not None:
                    for record in records:
                        if record["run_id"] == run_id:
                            check_reduction_quantity(read_state(record))
                            if record["closed"]:
                                return result("no_intent", "decision_already_processed")
                if (
                    qqq_cycle_id is None
                    and side == "sell"
                    and binding is not None
                    and _other_owned_intent_pending(root, binding, run_id)
                ):
                    return result("no_intent", "other_owned_intent_pending")
                failure_stage = "controls"
                controls = PaperExecutionControlStore(execution_control_path).read()
                if controls.pause_buys if side == "buy" else controls.pause_sells:
                    return result("no_intent", f"pause_{side}s_active")
                quantity, opens, funds = fresh_book()
                failure_stage = "ownership"
                projection = (
                    BudgetProjection(Decimal(0), Decimal(0), Decimal(0))
                    if binding is None
                    else project(binding)
                )
                book_quantity = (
                    projection.aggregate_quantity
                    if binding is not None and binding["version"] in {3, 4}
                    else projection.quantity
                )
                if quantity != book_quantity or opens:
                    return result("no_intent", "existing_inventory_or_order_conflict")
                if (
                    spy_reduction_quantity is not None
                    and spy_reduction_quantity > projection.quantity
                ):
                    return result("no_intent", "spy_reduction_exceeds_owned_quantity")
                if (side == "buy" and quantity > 0) or (side == "sell" and quantity == 0):
                    return result("no_intent", "target_already_satisfied")
                if conflicts_with_active_spy_fill_cycle(root, run_id, symbol):
                    return result("no_intent", "owned_intent_conflict")
                if binding is not None and any(row["run_id"] == run_id for row in records):
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
                    if qqq_cycle_id is not None:
                        binding = _migrate_binding(root, binding, config, qqq_cycle_id, as_of=at())
                        projection = project(binding)
                        records = _orders(binding, qqq_cycle_id)
                if qqq_cycle_id is not None:
                    if side == "buy" and records:
                        if qqq_entry_request_id is None:
                            return result("no_intent", "target_already_satisfied")
                        if not all(
                            _qqq_closed_unfilled_entry(
                                row,
                                read_state(row),
                                binding["terminal_evidence"].get(row["run_id"]),
                            )
                            for row in records
                        ):
                            return result("no_intent", "target_already_satisfied")
                    if side == "sell":
                        own_states = [read_state(row) for row in records]
                        if (
                            _qqq_filled_entry(
                                records,
                                own_states,
                                binding["terminal_evidence"],
                            )
                            is None
                        ):
                            raise _RecoveryRequired("unowned_sell")
                failure_stage = "quote"
                quote = (
                    client.fetch_spy_limit_input(observed_at=at())
                    if qqq_cycle_id is None
                    else client.fetch_qqq_limit_input(observed_at=at())
                )
                price = derive_kis_paper_marketable_limit(quote, side=side, observed_at=at())
                if qqq_cycle_id is not None and qqq_entry_request_id is not None and side == "buy":
                    funds = min(funds, exact_qqq_funds(price))
                failure_stage = "prepare"
                room = (
                    _money(binding["allocated_usd"])
                    - projection.entry_cost
                    - projection.reserved_buys
                )
                if binding["version"] in {2, 3, 4}:
                    room = min(room, projection.remaining_gross_cash)
                available = (
                    funds - projection.reserved_buys if binding["version"] in {2, 3, 4} else funds
                )
                shares = (
                    (min(room, available) / price).to_integral_value(rounding=ROUND_FLOOR)
                    if side == "buy"
                    else spy_reduction_quantity
                    if spy_reduction_quantity is not None
                    else projection.quantity
                )
                if qqq_cycle_id is not None:
                    shares = Decimal(1) if shares >= 1 else Decimal(0)
                if shares <= 0:
                    return result("no_intent", "budget_below_one_share")
                proof_ref = "sha256:" + _digest(
                    [receipt.decision_id, side, str(price), quote.quoted_at.isoformat()]
                )
                prepared = prepare_kis_paper_decision(
                    receipt,
                    binding=PaperDecisionExecutionBinding(
                        proposal_ref=receipt.proposal_ref,
                        symbol=symbol,
                        exchange=exchange,
                        quantity=shares,
                    ),
                    limit_proof=KisPaperLimitProof(
                        receipt_id=receipt.decision_id,
                        price_contract_ref=proof_ref,
                        symbol=symbol,
                        exchange=exchange,
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
                decision_path = _decision_evidence_path(evidence_root, receipt.decision_id)
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
                        symbol,
                        exchange,
                        side,
                    ):
                        raise _RecoveryRequired("budget_intent_mismatch")
                    check_reduction_quantity(state)
                    if (
                        side == "buy"
                        and (state.intent.quantity * state.intent.limit_price > min(room, funds))
                        or side == "sell"
                        and state.intent.quantity > projection.quantity
                    ):
                        raise _RecoveryRequired("orphan_budget_conflict")
                    if qqq_cycle_id is not None and state.intent.quantity != 1:
                        raise _RecoveryRequired("budget_intent_mismatch")
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
                record = bind_order(binding, state)
                outcome = run_intent(state, permitted=permitted(binding, state))
                return finish_order(binding, record, outcome.reconciliation)
    except _RecoveryRequired as error:
        # These internal exception codes are fixed literals, never broker text.
        failure = KisPaperBudgetOutcome(
            "recovery_required",
            str(error),
            at(),
            failure_diagnostic=_failure_diagnostic(failure_stage, error),
            **scope,
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
            "recovery_required",
            "evidence_unavailable",
            at(),
            failure_diagnostic=_failure_diagnostic(failure_stage, error),
            **scope,
        )
    if paths_valid:
        try:
            return result(
                failure.status,
                failure.reason_code,
                failure_diagnostic=failure.failure_diagnostic,
            )
        except (OSError, ValueError):
            pass
    return failure
