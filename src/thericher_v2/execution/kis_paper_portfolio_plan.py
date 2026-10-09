"""Joint whole-share BUY preparation, with no provider or submission route.

V3 keeps the original basis and owners. The one atomic shared binding contains
initial canary states for every leg, so an interrupted batch cannot lose a
reservation or require replacement identities. Later exact canary state files
take precedence; an unavailable observation never erases cumulative fills.
Gross limit reservations are not fee, settled-cash or net-PnL accounting.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import require_utc

from . import kis_paper_budget_strategy as budget
from .kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    exclusive_kis_paper_canary_state_lock,
)
from .kis_paper_fill_accounting import KisPaperExecutionObservation
from .kis_paper_portfolio_preview import project_kis_paper_portfolio_preview
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_readonly import KisPaperPortfolioPreviewReads


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioPlan:
    status: str
    reason: str
    binding: dict | None = None
    intents: tuple[KisPaperCanaryIntent, ...] = ()
    plan_ref: str | None = None
    reservation: Decimal | None = None

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_portfolio_plan_v1",
            "status": self.status,
            "reason": self.reason,
            "buy_leg_count": len(self.intents),
            "new_submits": 0,
            "limitation": "gross_limit_reservation_not_fees_settlement_or_execution_permission",
        }


def _check(condition, reason):
    if not condition:
        raise _RecoveryRequired(reason)


def _plan_result(binding, plan, status):
    states = budget._portfolio_seed_states(binding)
    intents = tuple(
        states[run_id].intent
        for symbol, _ in budget._PORTFOLIO_INSTRUMENTS
        for run_id in plan["states"]
        if states[run_id].intent.symbol == symbol
    )
    total = sum((Fraction(i.quantity) * Fraction(i.limit_price) for i in intents), Fraction(0))
    return KisPaperPortfolioPlan(
        status,
        "exact_identity_reused" if status == "replayed" else "joint_reservation_prepared",
        binding,
        intents,
        "sha256:" + budget._digest(plan),
        budget._exact_decimal(total),
    )


def build_kis_paper_portfolio_plan(
    *,
    binding: Mapping[str, object],
    states: Mapping[str, KisPaperCanaryState],
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    expected_binding_ref: str,
    request_id: str,
    input_ref: str,
    reads: KisPaperPortfolioPreviewReads | None,
    weights_by_symbol: Mapping[str, Decimal] | None,
    covariance_by_symbol: Mapping[str, Mapping[str, Decimal]] | None,
    target_as_of: datetime,
    as_of: datetime,
    valid_until: datetime,
) -> KisPaperPortfolioPlan:
    """Pure proposal. Expected pins come from independent caller custody.

    An exact retry uses its original parent binding/input pins and returns the
    original intents even after quote expiry. It is replay, not a fresh sizing
    or permission check. A different input under that request is a conflict.
    """
    _check(
        type(request_id) is str and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(request_id),
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
        and (binding["version"], set(binding))
        in ((2, budget._V2_KEYS), (3, budget._V3_KEYS), (4, budget._V4_KEYS)),
        "portfolio_binding_invalid",
    )
    _check(
        binding["account_ref"] == expected_account_ref
        and binding["basis_ref"] == expected_basis_ref
        and budget._basis(binding).fingerprint == expected_basis_ref
        and binding["legacy_spy"] is None,
        "portfolio_custody_mismatch",
    )
    at = require_utc(as_of)
    owners = budget._owners(binding)
    actual_refs = {owner.owner_ref: ref for owner, ref in owners}
    _check(all(owner.fingerprint == ref for owner, ref in owners), "portfolio_owner_mismatch")
    if binding["version"] in {3, 4}:
        for plan in binding["portfolio"]["plans"]:
            if plan["request_id"] == request_id:
                original_refs = {
                    key: value
                    for key, value in actual_refs.items()
                    if not key.startswith("portfolio-")
                }
                if binding["version"] == 4:
                    parent = copy.deepcopy(dict(binding))
                    parent["portfolio"]["plans"].remove(plan)
                    for run in plan["states"]:
                        parent["terminal_evidence"].pop(run, None)
                    for owner, _ in budget._owners(parent):
                        if owner.owner_ref.startswith("portfolio-"):
                            parent["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
                    original_refs = {owner.owner_ref: ref for owner, ref in budget._owners(parent)}
                    if "sha256:" + budget._digest(parent) != plan["parent_binding_ref"]:
                        original_refs = None
                _check(
                    plan["input_ref"] == input_ref
                    and plan["parent_binding_ref"] == expected_binding_ref
                    and (
                        expected_owner_refs == actual_refs
                        or (original_refs is not None and expected_owner_refs == original_refs)
                    ),
                    "portfolio_request_conflict",
                )
                replayed, proofs = _replay_scope(binding, states)
                budget.project_kis_paper_portfolio_budget(
                    basis=budget._basis(binding),
                    expected_basis_ref=expected_basis_ref,
                    owners=tuple(owner for owner, _ in owners),
                    expected_owner_refs=actual_refs,
                    states=replayed,
                    as_of=at,
                    cancellation_proofs=proofs,
                )
                return _plan_result(copy.deepcopy(dict(binding)), plan, "replayed")
    _check(
        "sha256:" + budget._digest(binding) == expected_binding_ref,
        "portfolio_parent_binding_mismatch",
    )
    preview = project_kis_paper_portfolio_preview(
        binding=binding,
        states=states,
        expected_account_ref=expected_account_ref,
        expected_basis_ref=expected_basis_ref,
        expected_owner_refs=expected_owner_refs,
        reads=reads,
        weights_by_symbol=weights_by_symbol,
        covariance_by_symbol=covariance_by_symbol,
        target_as_of=target_as_of,
        as_of=at,
    )
    if preview.status != "preview_feasible":
        return KisPaperPortfolioPlan(preview.status, preview.reason)
    until = require_utc(valid_until)
    _check(at < until <= at + timedelta(minutes=5), "portfolio_validity_invalid")
    seeds = {}
    for row, quantity in zip(reads.instruments, preview.additional_quantities, strict=True):
        if quantity == 0:
            continue
        identity = budget._digest(
            [expected_account_ref, expected_basis_ref, request_id, row.symbol]
        )
        intent = KisPaperCanaryIntent(
            "bp-" + identity,
            "portfolio-" + identity,
            "portfolio-" + identity,
            row.symbol,
            row.exchange,
            quantity,
            row.buy_limit,
            at,
            until,
            price_contract_ref="sha256:"
            + budget._digest([input_ref, row.symbol, str(row.buy_limit)]),
        )
        seed = KisPaperCanaryState(intent, "intent_recorded", at, "preview")
        seeds[intent.run_id] = seed.to_dict()
    if not seeds:
        return KisPaperPortfolioPlan("no_intent", "no_incremental_buy")
    updated = copy.deepcopy(dict(binding))
    if updated["version"] == 2:
        updated.update(
            version=3,
            portfolio={
                "owner_refs": {s: None for s, _ in budget._PORTFOLIO_INSTRUMENTS},
                "plans": [],
            },
        )
    plan = {
        "request_id": request_id,
        "input_ref": input_ref,
        "parent_binding_ref": expected_binding_ref,
        "states": seeds,
    }
    updated["portfolio"]["plans"].append(plan)
    for owner, _ in budget._owners(updated):
        if owner.owner_ref.startswith("portfolio-"):
            updated["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    combined = dict(states) | {
        run: KisPaperCanaryState.from_dict(payload) for run, payload in seeds.items()
    }
    replayed, proofs = _replay_scope(updated, combined)
    budget.project_kis_paper_portfolio_budget(
        basis=budget._basis(updated),
        expected_basis_ref=expected_basis_ref,
        owners=tuple(owner for owner, _ in budget._owners(updated)),
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(updated)},
        states=replayed,
        as_of=at,
        cancellation_proofs=proofs,
    )
    return _plan_result(updated, plan, "prepared")


def _replay_scope(binding, states):
    replayed, proofs = dict(states), {}
    _check(
        all(
            not record["closed"] or record["run_id"] in binding["terminal_evidence"]
            for record in binding["orders"] + binding["qqq"]["orders"]
        ),
        "portfolio_terminal_unproven",
    )
    for run_id, payload in binding["terminal_evidence"].items():
        retained, proof = budget._retained_terminal(states[run_id], payload)
        _check(budget._terminal(retained, proof), "portfolio_terminal_unproven")
        replayed[run_id] = retained
        if proof is not None:
            proofs[run_id] = proof
    return replayed, proofs


def _states(root, binding):
    return {
        reference.run_id: budget._state(
            root,
            {"run_id": reference.run_id, "intent_ref": reference.intent_ref},
            symbol=owner.symbol,
            exchange=owner.exchange,
            binding=binding,
        )
        for owner, _ in budget._owners(binding)
        for reference in owner.state_refs
    }


def reserve_kis_paper_portfolio_plan(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    **arguments,
) -> KisPaperPortfolioPlan:
    """Atomic reservation only. Never materializes order files or calls a broker.

    All current budget writers share these locks and replay the same V3 owners.
    Parent owns any actual private invocation; tests use isolated synthetic roots.
    """
    root = Path(state_root)
    _check(
        not any(path.is_symlink() or path.is_junction() for path in (root, *root.parents)),
        "private_root_invalid",
    )
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root))
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, arguments["expected_account_ref"])
            _check(binding is not None, "portfolio_existing_basis_required")
            result = build_kis_paper_portfolio_plan(
                binding=binding, states=_states(root, binding), **arguments
            )
            if result.status != "prepared":
                return result
            budget._atomic_json(root / budget.BUDGET_FILE, result.binding)
            retained = budget._load_binding(root, arguments["expected_account_ref"])
            _check(retained == result.binding, "portfolio_reservation_readback_mismatch")
            budget.project_budget(root, retained, as_of=arguments["as_of"])
            return KisPaperPortfolioPlan(
                "reserved",
                "joint_reservation_persisted",
                retained,
                result.intents,
                result.plan_ref,
                result.reservation,
            )


def reconcile_kis_paper_portfolio_plan(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    request_id: str,
    expected_plan_ref: str,
    as_of: datetime,
    cancellation_proofs: Mapping[str, KisPaperExecutionObservation] | None = None,
) -> KisPaperPortfolioPlan:
    """Retain exact terminal canary facts, never query, cancel or release unknowns.

    Closing means owned-state evidence, not fresh broker/account reconciliation.
    Completion, exact provider rejection and proven pre-submit expiry use the
    existing terminal predicates. Cancellation needs its exact typed proof.
    """
    root = Path(state_root)
    _check(
        not any(path.is_symlink() or path.is_junction() for path in (root, *root.parents)),
        "private_root_invalid",
    )
    budget._validate_paths(root.resolve(), Path(repository_root), Path(artifact_root))
    at = require_utc(as_of)
    with exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            binding = budget._load_binding(root, expected_account_ref)
            _check(
                binding is not None
                and binding["version"] in {3, 4}
                and binding["basis_ref"] == expected_basis_ref,
                "portfolio_custody_mismatch",
            )
            _check(
                {owner.owner_ref: ref for owner, ref in budget._owners(binding)}
                == expected_owner_refs,
                "portfolio_owner_mismatch",
            )
            plan = next(
                (p for p in binding["portfolio"]["plans"] if p["request_id"] == request_id), None
            )
            _check(
                plan is not None and "sha256:" + budget._digest(plan) == expected_plan_ref,
                "portfolio_request_conflict",
            )
            states = _states(root, binding)
            proofs = {} if cancellation_proofs is None else cancellation_proofs
            _check(
                isinstance(proofs, Mapping) and set(proofs) <= set(plan["states"]),
                "portfolio_proof_scope_invalid",
            )
            updated = copy.deepcopy(binding)
            for run_id in plan["states"]:
                state = budget._validated_portfolio_state(states[run_id], at)
                observation = proofs.get(run_id)
                if observation is not None:
                    _check(
                        type(observation) is KisPaperExecutionObservation,
                        "portfolio_terminal_unproven",
                    )
                    budget._terminal_payload(state, observation)
                    _check(budget._terminal(state, observation), "portfolio_terminal_unproven")
                if run_id not in updated["terminal_evidence"] and budget._terminal(
                    state, observation
                ):
                    updated["terminal_evidence"][run_id] = budget._terminal_payload(
                        state, observation
                    )
            # The canonical replay revalidates cancellation/fill links before persistence.
            budget.project_budget(root, updated, as_of=at)
            if updated != binding:
                budget._atomic_json(root / budget.BUDGET_FILE, updated)
                _check(
                    budget._load_binding(root, expected_account_ref) == updated,
                    "portfolio_reservation_readback_mismatch",
                )
            closed = all(run_id in updated["terminal_evidence"] for run_id in plan["states"])
            result = _plan_result(updated, plan, "prepared")
            return KisPaperPortfolioPlan(
                "reconciled" if closed else "pending",
                "exact_terminal_states_retained" if closed else "terminal_evidence_incomplete",
                updated,
                result.intents,
                result.plan_ref,
                result.reservation,
            )
