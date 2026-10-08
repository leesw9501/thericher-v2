"""Finite owned Paper target advance using the existing book and order lifecycle.

Caller owns session/input/control selection and actual dispatch. Checkpoints are
private immutable proposals, not a new ledger, scheduler or execution permission.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from thericher_v2.contracts import require_utc

from . import kis_paper_budget_strategy as budget
from . import kis_paper_canary as canary
from . import kis_paper_portfolio_execute as execution
from .kis_paper_portfolio_plan import (
    _replay_scope,
    _states,
    build_kis_paper_portfolio_plan,
    reconcile_kis_paper_portfolio_plan,
)
from .kis_paper_portfolio_preview import SYMBOLS, _covariance, project_kis_paper_portfolio_preview
from .kis_paper_quote import derive_kis_paper_marketable_limit
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_readonly import KisPaperConfig, KisPaperPortfolioPreviewReads


def _check(value, reason):
    if not value:
        raise _RecoveryRequired(reason)


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioCycleOutcome:
    status: str
    reason: str
    stage: str
    leg_count: int = 0
    cycle_ref: str | None = None

    def safe_payload(self):
        return dict(
            kind="kis_paper_portfolio_cycle_v1",
            status=self.status,
            reason=self.reason,
            stage=self.stage,
            leg_count=self.leg_count,
            limitation="gross_owned_basis_not_fees_settlement_or_profit",
        )


@contextmanager
def _shared(root):
    for name in (".session_execution", ".canary_execution"):
        execution._unlinked(root / ("." + name + ".lock"))
    with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
        with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
            yield


def _record(path, value):
    execution._unlinked(path)
    existing = budget._read_json(path)
    _check(existing is None or existing == value, "cycle_checkpoint_conflict")
    if existing is None:
        budget._atomic_json(path, value)
    _check(budget._read_json(path) == value, "cycle_checkpoint_invalid")


def _project(root, binding, at):
    owners = budget._owners(binding)
    states = _states(root, binding)
    replayed, proofs = _replay_scope(binding, states)
    projection = budget.project_kis_paper_portfolio_budget(
        basis=budget._basis(binding),
        expected_basis_ref=binding["basis_ref"],
        owners=tuple(o for o, _ in owners),
        expected_owner_refs={o.owner_ref: ref for o, ref in owners},
        states=replayed,
        as_of=at,
        cancellation_proofs=proofs,
    )
    return states, replayed, proofs, projection


def _prefix(root, initial, stages, at):
    current = budget._load_binding(root, initial["account_ref"])
    _check(current is not None, "cycle_book_missing")
    expected = copy.deepcopy(initial)
    allowed = set()
    for stage in stages:
        if stage is None:
            continue
        _check(
            type(stage) is dict
            and set(stage) == {"parent", "proposed", "ref"}
            and stage["ref"]
            == "sha256:" + budget._digest({k: v for k, v in stage.items() if k != "ref"}),
            "cycle_checkpoint_invalid",
        )
        parent, proposed = stage["parent"], stage["proposed"]
        # Each retained proposal extends only this exact previously owned book.
        p = copy.deepcopy(parent)
        for run in allowed:
            p["terminal_evidence"].pop(run, None)
        _check(p == expected, "cycle_checkpoint_invalid")
        _check(
            len(proposed["portfolio"]["plans"]) == len(parent["portfolio"]["plans"]) + 1,
            "cycle_checkpoint_invalid",
        )
        plan = proposed["portfolio"]["plans"][-1]
        candidate = copy.deepcopy(parent)
        candidate["portfolio"]["plans"].append(plan)
        for owner, _ in budget._owners(candidate):
            if owner.owner_ref.startswith("portfolio-"):
                candidate["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
        _check(
            candidate == proposed
            and plan["parent_binding_ref"] == "sha256:" + budget._digest(parent),
            "cycle_checkpoint_invalid",
        )
        # A crash may leave the immutable proposal before its atomic reservation.
        if current == parent:
            break
        allowed.update(plan["states"])
        expected = copy.deepcopy(proposed)
        for run in allowed:
            expected["terminal_evidence"].pop(run, None)
    normalized = copy.deepcopy(current)
    for run in allowed:
        normalized["terminal_evidence"].pop(run, None)
    _check(normalized == expected, "cycle_book_changed")
    _project(root, current, at)
    return current


def _reserve(root, stage, at):
    """Restore the exact pre-reservation proposal, never regenerate quote terms."""
    with _shared(root):
        current = budget._load_binding(root, stage["parent"]["account_ref"])
        if current == stage["parent"]:
            _project(root, stage["proposed"], at)
            budget._atomic_json(root / budget.BUDGET_FILE, stage["proposed"])
            _check(budget._load_binding(root) == stage["proposed"], "cycle_checkpoint_invalid")
        else:
            _stage_book(current, stage)


def _stage_book(binding, stage):
    normalized = copy.deepcopy(binding)
    expected = copy.deepcopy(stage["proposed"])
    for run in expected["portfolio"]["plans"][-1]["states"]:
        normalized["terminal_evidence"].pop(run, None)
        expected["terminal_evidence"].pop(run, None)
    _check(normalized == expected, "cycle_book_changed")


def _stage(parent, proposed):
    result = dict(parent=copy.deepcopy(parent), proposed=copy.deepcopy(proposed))
    return result | {"ref": "sha256:" + budget._digest(result)}


def _terms(root, stage, side, contract, targets, at):
    if stage is None:
        return
    plan = stage["proposed"]["portfolio"]["plans"][-1]
    _check(
        plan["request_id"] == "portfolio-" + side + "-" + budget._digest(contract)
        and plan["input_ref"] == contract["input_ref"],
        "cycle_checkpoint_invalid",
    )
    projection = _project(root, stage["parent"], at)[-1]
    inventory = {s.symbol: s.quantity for s in projection.stocks_by_instrument}
    expected = {
        s: max(
            Decimal(0),
            (inventory[s] - targets[s]) if side == "sell" else (targets[s] - inventory[s]),
        )
        for s in SYMBOLS
    }
    seeds = budget._portfolio_seed_states(stage["proposed"])
    actual = {s: Decimal(0) for s in SYMBOLS}
    for run in plan["states"]:
        intent = seeds[run].intent
        _check(intent.side == side, "cycle_checkpoint_invalid")
        actual[intent.symbol] = intent.quantity
    _check(actual == expected, "cycle_checkpoint_invalid")


def _proof(root, binding, plan, intent):
    return execution.KisPaperPortfolioExecutionBinding(
        state_root=root.resolve(),
        account_ref=binding["account_ref"],
        basis_ref=binding["basis_ref"],
        owner_refs=tuple((o.owner_ref, ref) for o, ref in budget._owners(binding)),
        binding_ref="sha256:" + budget._digest(binding),
        request_id=plan["request_id"],
        parent_binding_ref=plan["parent_binding_ref"],
        input_ref=plan["input_ref"],
        plan_ref="sha256:" + budget._digest(plan),
        run_id=intent.run_id,
        intent_ref=intent.fingerprint,
    )


def _step(root, stage, side, paths, client, clock):
    _reserve(root, stage, require_utc(clock()))
    with _shared(root):
        binding = budget._load_binding(root)
        _stage_book(binding, stage)
        plan = stage["proposed"]["portfolio"]["plans"][-1]
        _, replayed, proofs, _ = _project(root, binding, require_utc(clock()))
        seeds = budget._portfolio_seed_states(binding)
        intents = tuple(
            seeds[run].intent
            for symbol in SYMBOLS
            for run in plan["states"]
            if seeds[run].intent.symbol == symbol
        )
        _check(all(i.side == side for i in intents), "cycle_checkpoint_invalid")
        pending = [
            i for i in intents if not budget._terminal(replayed[i.run_id], proofs.get(i.run_id))
        ]
    if pending:
        intent = pending[0]
        operation = (
            execution.execute_kis_paper_portfolio_sell
            if side == "sell"
            else execution.execute_kis_paper_portfolio_buy
        )
        operation(
            proof=_proof(root, binding, plan, intent),
            state_root=root,
            client=client,
            clock=clock,
            execute=True,
            **paths,
        )
        return KisPaperPortfolioCycleOutcome("pending", "exact_leg_advanced", side, len(intents))
    result = reconcile_kis_paper_portfolio_plan(
        state_root=root,
        repository_root=paths["repository_root"],
        artifact_root=paths["artifact_root"],
        expected_account_ref=binding["account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(binding)},
        request_id=plan["request_id"],
        expected_plan_ref="sha256:" + budget._digest(plan),
        as_of=require_utc(clock()),
    )
    _check(result.status == "reconciled", "cycle_terminal_unproven")
    _check(
        all(
            replayed[i.run_id].cumulative_fill is not None
            and replayed[i.run_id].cumulative_fill.quantity == i.quantity
            for i in intents
        ),
        "cycle_terminal_incomplete",
    )
    return None


def advance_kis_paper_portfolio_cycle(
    *,
    state_root: Path,
    repository_root: Path,
    artifact_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    expected_binding_ref: str,
    session_id: str,
    input_ref: str,
    control_ref: str,
    weights_by_symbol: Mapping[str, Decimal],
    covariance_by_symbol: Mapping[str, Mapping[str, Decimal]],
    target_as_of: datetime,
    reads_factory: Callable[[], KisPaperPortfolioPreviewReads] | None = None,
    client: canary.KisPaperCanaryClient | None = None,
    execution_control_path: Path = canary.DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    execute: bool = False,
    expected_cycle_ref: str | None = None,
) -> KisPaperPortfolioCycleOutcome:
    """At most one exact leg per call; never polls, resets or loads credentials.

    Existing baseline-SPY reductions remain separately owned. A fresh post-SELL
    BUY preview must match the frozen whole-share target; otherwise this exact
    cycle yields without resizing. Unknown outcomes recover their original leg.
    """
    _check(type(execute) is bool, "cycle_execute_invalid")
    if not execute:
        return KisPaperPortfolioCycleOutcome("inert", "execution_not_requested", "none")
    _check(
        type(session_id) is str and budget._QQQ_ENTRY_REQUEST_ID.fullmatch(session_id),
        "cycle_session_invalid",
    )
    _check(
        all(
            type(ref) is str and budget._SHA.fullmatch(ref)
            for ref in (expected_basis_ref, expected_binding_ref, input_ref, control_ref)
        ),
        "cycle_reference_invalid",
    )
    _check(isinstance(client, canary.KisPaperCanaryClient), "portfolio_client_invalid")
    _check(callable(reads_factory) and callable(clock), "cycle_reads_factory_invalid")
    config = replace(client._config)
    _check(
        type(config) is KisPaperConfig
        and budget._digest([config.base_url, config.account_number, config.account_product_code])
        == expected_account_ref,
        "account_binding_mismatch",
    )
    _check(
        isinstance(weights_by_symbol, Mapping)
        and set(weights_by_symbol) == set(SYMBOLS)
        and all(
            type(w) is Decimal and w.is_finite() and 0 <= w <= 1 for w in weights_by_symbol.values()
        )
        and sum(map(Fraction, weights_by_symbol.values())) <= 1,
        "cycle_control_invalid",
    )
    _covariance(covariance_by_symbol)
    contract = dict(
        session_id=session_id,
        account_ref=expected_account_ref,
        basis_ref=expected_basis_ref,
        owner_refs=dict(expected_owner_refs),
        binding_ref=expected_binding_ref,
        input_ref=input_ref,
        control_ref=control_ref,
        target_as_of=require_utc(target_as_of).isoformat(),
        weights={s: str(weights_by_symbol[s]) for s in SYMBOLS},
        covariance={s: {t: str(covariance_by_symbol[s][t]) for t in SYMBOLS} for s in SYMBOLS},
    )
    root = Path(state_root)
    paths = dict(
        repository_root=Path(repository_root),
        artifact_root=Path(artifact_root),
        runtime_projection_path=Path(runtime_projection_path),
        paper_account_snapshot_path=Path(paper_account_snapshot_path),
        emergency_state_path=Path(emergency_state_path),
        execution_control_path=Path(execution_control_path),
    )
    for path in (root, *paths.values()):
        execution._unlinked(path)
    budget._validate_paths(
        root.resolve(),
        paths["repository_root"],
        paths["artifact_root"],
        paths["runtime_projection_path"],
        paths["paper_account_snapshot_path"],
        paths["emergency_state_path"],
        paths["execution_control_path"],
    )
    key = budget._digest([expected_account_ref, expected_basis_ref, session_id])
    directory = root / ".portfolio_cycles" / key
    for name in ("cycle.json", "buy.json", ".advance", "..advance.lock"):
        execution._unlinked(directory / name)
    # This lock serializes this cycle only. Native operations take their own
    # shared locks; nesting the OS-backed shared locks would deadlock.
    with canary.exclusive_kis_paper_canary_state_lock(directory / ".advance"):
        record = budget._read_json(directory / "cycle.json")
        buy = budget._read_json(directory / "buy.json")
        reads = None
        if record is None:
            _check(buy is None and expected_cycle_ref is None, "cycle_checkpoint_invalid")
            with _shared(root):
                binding = budget._load_binding(root, expected_account_ref)
                _check(
                    binding is not None
                    and binding["version"] == 3
                    and binding["legacy_spy"] is None
                    and binding["basis_ref"] == expected_basis_ref
                    and "sha256:" + budget._digest(binding) == expected_binding_ref
                    and {o.owner_ref: ref for o, ref in budget._owners(binding)}
                    == dict(expected_owner_refs),
                    "cycle_custody_mismatch",
                )
            reads = reads_factory()
            at = require_utc(clock())
            states, replayed, proofs, projection = _project(root, binding, at)
            _check(
                all(
                    budget._terminal(s, proofs.get(run)) and run in binding["terminal_evidence"]
                    for run, s in replayed.items()
                    if s.intent.symbol in SYMBOLS
                ),
                "portfolio_pending_identity",
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
            _check(
                preview.reason in {"preview_only", "incumbent_target_mismatch"}
                and preview.target_quantities is not None,
                "cycle_reads_or_target_unavailable",
            )
            execution._book(reads.snapshot, projection, config, at)
            inventory = {s.symbol: s.quantity for s in projection.stocks_by_instrument}
            owned = {
                s.symbol: s.quantity
                for s in projection.stocks_by_owner
                if s.owner_ref.startswith("portfolio-")
            }
            reductions = {
                s: max(Decimal(0), inventory[s] - q)
                for s, q in zip(SYMBOLS, preview.target_quantities, strict=True)
            }
            if any(reductions[s] > owned.get(s, Decimal(0)) for s in SYMBOLS):
                return KisPaperPortfolioCycleOutcome(
                    "unavailable", "baseline_reduction_required", "sell"
                )
            record = dict(
                contract=contract,
                initial=binding,
                sell=None,
                targets={
                    s: str(q) for s, q in zip(SYMBOLS, preview.target_quantities, strict=True)
                },
            )
            if any(reductions.values()):
                result = execution.build_kis_paper_portfolio_sell_plan(
                    binding=binding,
                    states=states,
                    expected_account_ref=expected_account_ref,
                    expected_basis_ref=expected_basis_ref,
                    expected_owner_refs=expected_owner_refs,
                    expected_binding_ref=expected_binding_ref,
                    request_id="portfolio-sell-" + budget._digest(contract),
                    input_ref=input_ref,
                    reductions_by_symbol=reductions,
                    limits_by_symbol={
                        row.symbol: derive_kis_paper_marketable_limit(
                            row.quote, side="sell", observed_at=at
                        )
                        for row in reads.instruments
                        if reductions[row.symbol]
                    },
                    as_of=at,
                    valid_until=at + budget._ORDER_LIFETIME,
                )
                record["sell"] = _stage(binding, result.binding)
            record["ref"] = "sha256:" + budget._digest(record)
            with _shared(root):
                _check(budget._load_binding(root) == binding, "cycle_book_changed")
                _record(directory / "cycle.json", record)
        _check(
            type(record) is dict
            and set(record) == {"contract", "initial", "targets", "sell", "ref"}
            and record["contract"] == contract
            and record["ref"]
            == "sha256:" + budget._digest({k: v for k, v in record.items() if k != "ref"})
            and (expected_cycle_ref is None or expected_cycle_ref == record["ref"]),
            "cycle_contract_conflict",
        )
        sell = record["sell"]
        initial = record["initial"]
        _check(
            "sha256:" + budget._digest(initial) == expected_binding_ref, "cycle_checkpoint_invalid"
        )
        targets = {s: Decimal(record["targets"][s]) for s in SYMBOLS}
        _check(
            set(record["targets"]) == set(SYMBOLS)
            and all(
                q.is_finite() and q >= 0 and q == q.to_integral_value() for q in targets.values()
            ),
            "cycle_checkpoint_invalid",
        )
        binding = _prefix(root, initial, (sell, buy), require_utc(clock()))
        for side, stage in (("sell", sell), ("buy", buy)):
            _terms(root, stage, side, contract, targets, require_utc(clock()))
        if sell is not None and buy is None:
            pending = _step(root, sell, "sell", paths, client, clock)
            if pending is not None:
                return replace(pending, cycle_ref=record["ref"])
            binding = _prefix(root, initial, (sell,), require_utc(clock()))
        if buy is not None:
            pending = _step(root, buy, "buy", paths, client, clock)
            if pending is not None:
                return replace(pending, cycle_ref=record["ref"])
            binding = _prefix(root, initial, (sell, buy), require_utc(clock()))
        if reads is None:
            reads = reads_factory()
        _check(type(reads) is KisPaperPortfolioPreviewReads, "cycle_reads_or_target_unavailable")
        at = require_utc(clock())
        states, _, _, projection = _project(root, binding, at)
        execution._book(reads.snapshot, projection, config, at)
        inventory = {s.symbol: s.quantity for s in projection.stocks_by_instrument}
        if all(inventory[s] == targets[s] for s in SYMBOLS):
            with _shared(root):
                _check(budget._load_binding(root) == binding, "cycle_book_changed")
            return KisPaperPortfolioCycleOutcome(
                "complete", "no_target_delta", "none", cycle_ref=record["ref"]
            )
        _check(buy is None, "cycle_target_unreached")
        _check(all(inventory[s] <= targets[s] for s in SYMBOLS), "cycle_terminal_incomplete")
        refs = {o.owner_ref: ref for o, ref in budget._owners(binding)}
        preview = project_kis_paper_portfolio_preview(
            binding=binding,
            states=states,
            expected_account_ref=expected_account_ref,
            expected_basis_ref=expected_basis_ref,
            expected_owner_refs=refs,
            reads=reads,
            weights_by_symbol=weights_by_symbol,
            covariance_by_symbol=covariance_by_symbol,
            target_as_of=target_as_of,
            as_of=at,
        )
        if preview.target_quantities != tuple(targets[s] for s in SYMBOLS):
            return KisPaperPortfolioCycleOutcome(
                "unavailable", "target_quantization_changed", "buy", cycle_ref=record["ref"]
            )
        _check(preview.status == "preview_feasible", "cycle_buy_unavailable")
        result = build_kis_paper_portfolio_plan(
            binding=binding,
            states=states,
            expected_account_ref=expected_account_ref,
            expected_basis_ref=expected_basis_ref,
            expected_owner_refs=refs,
            expected_binding_ref="sha256:" + budget._digest(binding),
            request_id="portfolio-buy-" + budget._digest(contract),
            input_ref=input_ref,
            reads=reads,
            weights_by_symbol=weights_by_symbol,
            covariance_by_symbol=covariance_by_symbol,
            target_as_of=target_as_of,
            as_of=at,
            valid_until=at + budget._ORDER_LIFETIME,
        )
        _check(result.status == "prepared", "cycle_buy_unavailable")
        buy = _stage(binding, result.binding)
        with _shared(root):
            _check(budget._load_binding(root) == binding, "cycle_book_changed")
            _record(directory / "buy.json", buy)
        pending = _step(root, buy, "buy", paths, client, clock)
        return replace(pending, cycle_ref=record["ref"])
