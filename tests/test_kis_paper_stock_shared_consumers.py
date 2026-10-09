from __future__ import annotations

import copy
import socket
import subprocess
import urllib.request
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_plan import _arguments
from test_kis_paper_portfolio_preview import ACCOUNT, NOW, _reads, _scope
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_execute as execute
from thericher_v2.execution import kis_paper_spy_fill_cycle as spy_cycle
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_plan import (
    build_kis_paper_portfolio_plan,
    reserve_kis_paper_portfolio_plan,
)
from thericher_v2.execution.kis_paper_portfolio_preview import project_kis_paper_portfolio_preview
from thericher_v2.execution.kis_readonly import (
    KisPaperConfig,
    KisPaperPosition,
    KisPaperReadOnlyClient,
)

D = Decimal
INSTRUMENT_REF = "ref:" + "c" * 64
CONFIG = KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01")


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("synthetic shared consumers cannot call providers, credentials or Docker")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(KisPaperReadOnlyClient, "snapshot", deny)
    monkeypatch.setattr(canary.KisPaperCanaryClient, "submit_limit", deny)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", deny)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", deny)


def _refresh(arguments):
    binding = arguments["binding"]
    arguments["expected_owner_refs"] = {
        owner.owner_ref: pin for owner, pin in budget._owners(binding)
    }
    arguments["expected_binding_ref"] = "sha256:" + budget._digest(binding)
    return arguments


def _v4(*, include_stock=True):
    arguments = _arguments()
    binding = arguments["binding"]
    binding.update(
        version=4,
        portfolio={
            "owner_refs": {symbol: "sha256:" + "0" * 64 for symbol in ("SPY", "TLT", "GLD")},
            "plans": [],
        },
        stocks={},
    )
    if include_stock:
        binding["stocks"]["AAPL"] = dict(
            exchange="NASD",
            instrument_binding_ref=INSTRUMENT_REF,
            owner_ref="sha256:" + "0" * 64,
            plans=[],
        )
        request, input_ref = "synthetic-stock-1", "sha256:" + "e" * 64
        parent_ref = "sha256:" + budget._digest(binding)
        identity = budget._stock_identity(binding, "AAPL", request, "buy")
        intent = canary.KisPaperCanaryIntent(
            "bk-" + identity,
            "stock-" + identity,
            "stock-" + identity,
            "AAPL",
            "NASD",
            D(2),
            D(100),
            NOW - timedelta(minutes=1),
            NOW + timedelta(minutes=1),
            price_contract_ref=budget._stock_price_ref(binding, "AAPL", input_ref, D(100), "buy"),
        )
        seed = canary.KisPaperCanaryState(intent, "intent_recorded", intent.created_at, "preview")
        binding["stocks"]["AAPL"]["plans"].append(
            dict(
                request_id=request,
                input_ref=input_ref,
                parent_binding_ref=parent_ref,
                states={intent.run_id: seed.to_dict()},
            )
        )
        arguments["states"][intent.run_id] = seed
    for owner, _ in budget._owners(binding):
        if owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
        elif owner.stock_binding_ref is not None:
            binding["stocks"][owner.symbol]["owner_ref"] = owner.fingerprint
    return _refresh(arguments)


def _preview(arguments):
    return project_kis_paper_portfolio_preview(
        **{
            key: value
            for key, value in arguments.items()
            if key not in {"request_id", "input_ref", "expected_binding_ref", "valid_until"}
        }
    )


def _projection(arguments):
    return budget.project_shared_budget(
        **{
            key: arguments[key]
            for key in (
                "binding",
                "states",
                "expected_account_ref",
                "expected_basis_ref",
                "expected_owner_refs",
                "as_of",
            )
        }
    )


def _filled_stock(arguments):
    seed = next(iter(arguments["states"].values()))
    intent = seed.intent
    submitted = intent.created_at + timedelta(seconds=1)
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id="SYNTHETIC-STOCK",
            order_at=submitted,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side="buy",
            quantity=intent.quantity,
        ),
        intent.quantity,
        D(2),
        D(180),
        submitted + timedelta(seconds=1),
        D(0),
    )
    state = replace(
        seed,
        phase="submitted",
        updated_at=fill.observed_at,
        reason_code="reconciliation_clean",
        broker_order_id="SYNTHETIC-STOCK",
        submission_started_at=submitted,
        submitted_at=submitted,
        cumulative_fill=fill,
        fill_observation_status="available",
        fill_observed_at=fill.observed_at,
    )
    arguments["states"][intent.run_id] = state
    arguments["binding"]["terminal_evidence"][intent.run_id] = budget._terminal_payload(state)
    arguments["reads"] = _reads(
        spy=D(0),
        extra=(KisPaperPosition("AAPL", "NASD", "USD", D(2), D(90), D(180), NOW),),
    )
    snapshot = arguments["reads"].snapshot
    arguments["reads"] = replace(
        arguments["reads"],
        snapshot=replace(
            snapshot,
            identity=replace(snapshot.identity, masked_account=CONFIG.masked_account_identity),
        ),
    )
    return _refresh(arguments)


def test_v4_stock_reservation_reduces_trio_nav_without_global_pending_block():
    arguments = _v4()
    before = copy.deepcopy(arguments)
    result = _preview(arguments)
    assert (result.status, result.reason) == ("preview_feasible", "preview_only")
    assert result.pending_count == 1 and result.shared_reservations == 200
    assert result.provisional_risk_nav == 800 and result.target_quantities == (D(2), D(2), D(2))
    assert result.proposed_reservation == 600
    projection = _projection(arguments)
    assert projection.allocated_usd == 1000 and projection.remaining_cap == 800
    assert projection.remaining_gross_cash == 800
    assert arguments == before


def test_pure_trio_plan_keeps_v4_stock_seed_original_bank_and_all_owner_replay():
    arguments = _v4()
    before = copy.deepcopy(arguments)
    result = build_kis_paper_portfolio_plan(**arguments)
    assert result.status == "prepared" and result.reservation == 600
    assert result.binding["version"] == 4
    for field in ("stocks", "basis_ref", "basis_usd", "allocated_usd", "spy_owner_ref", "qqq"):
        assert result.binding[field] == before["binding"][field]
    assert [(i.symbol, i.quantity) for i in result.intents] == [("SPY", 2), ("TLT", 2), ("GLD", 2)]
    combined = dict(arguments, binding=result.binding, states=budget._seed_states(result.binding))
    _refresh(combined)
    projection = _projection(combined)
    assert (projection.reserved_buys, projection.remaining_cap) == (800, 200)
    assert projection.basis_usd == 10000 and projection.allocated_usd == 1000
    assert (_preview(combined).reason, _preview(combined).pending_count) == ("pending_identity", 4)
    assert arguments == before


def test_atomic_synthetic_trio_reservation_keeps_registered_stock_on_restart(tmp_path):
    arguments = _v4()
    original = copy.deepcopy(arguments["binding"])
    root = tmp_path / "private"
    budget._atomic_json(root / budget.BUDGET_FILE, original)
    result = reserve_kis_paper_portfolio_plan(
        state_root=root,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
        **{key: value for key, value in arguments.items() if key not in {"binding", "states"}},
    )
    assert result.status == "reserved" and result.binding["version"] == 4
    assert result.binding["stocks"] == original["stocks"]
    retained = budget._load_binding(root, ACCOUNT)
    assert retained == result.binding and retained["basis_ref"] == original["basis_ref"]
    for _ in range(3):
        projection = budget.project_budget(root, retained, as_of=NOW)
        assert projection.entry_cost == 0 and projection.reserved_buys == 800
    assert not list(root.glob("bk-*.json")) and not list(root.glob("bp-*.json"))


def test_registered_stock_holdings_match_both_preview_and_execution_book():
    arguments = _filled_stock(_v4())
    projection = _projection(arguments)
    result = _preview(arguments)
    assert result.status == "preview_feasible" and result.shared_entry_cost == 180
    assert result.provisional_risk_nav == 820
    assert projection.stocks_by_instrument[-1].quantity == 2
    assert execute._book(arguments["reads"].snapshot, projection, CONFIG, NOW) == D(10000)


@pytest.mark.parametrize("observation", ["unavailable", "conflict"])
def test_partial_unknown_stock_keeps_cost_and_residual_funding_without_trio_pause(observation):
    arguments = _filled_stock(_v4())
    run, state = next(iter(arguments["states"].items()))
    arguments["states"][run] = replace(
        state,
        phase="outcome_unknown",
        updated_at=NOW,
        reason_code="reconciliation_unresolved",
        cumulative_fill=replace(
            state.cumulative_fill, quantity=D(1), gross_amount=D(90), remaining_quantity=D(1)
        ),
        fill_observation_status=observation,
        fill_observed_at=NOW,
    )
    arguments["binding"]["terminal_evidence"].pop(run)
    snapshot = arguments["reads"].snapshot
    arguments["reads"] = replace(
        arguments["reads"],
        snapshot=replace(snapshot, positions=(replace(snapshot.positions[0], quantity=D(1)),)),
    )
    _refresh(arguments)
    before = copy.deepcopy(arguments)
    for _ in range(3):
        result = _preview(copy.deepcopy(arguments))
        assert (result.status, result.reason) == ("preview_feasible", "preview_only")
        assert result.shared_entry_cost == 90 and result.shared_reservations == 100
        assert result.provisional_risk_nav == 810 and result.proposed_reservation == 600
        assert _projection(arguments).remaining_cap == 810
    assert arguments == before


@pytest.mark.parametrize("change", ["missing", "quantity", "venue", "duplicate"])
def test_registered_stock_broker_book_cannot_be_adopted_or_substituted(change):
    arguments = _filled_stock(_v4())
    snapshot = arguments["reads"].snapshot
    position = snapshot.positions[0]
    positions = {
        "missing": (),
        "quantity": (replace(position, quantity=D(3)),),
        "venue": (replace(position, exchange="AMEX"),),
        "duplicate": (position, position),
    }[change]
    arguments["reads"] = replace(
        arguments["reads"], snapshot=replace(snapshot, positions=positions)
    )
    result = _preview(arguments)
    assert (result.status, result.reason) == ("unavailable", "inventory_mismatch")
    with pytest.raises(spy_cycle._RecoveryRequired, match="pre_submit_ownership_changed"):
        execute._book(arguments["reads"].snapshot, _projection(arguments), CONFIG, NOW)


def test_execution_book_rejects_unmanaged_foreign_holding_without_adoption():
    arguments = _filled_stock(_v4())
    snapshot = arguments["reads"].snapshot
    foreign = KisPaperPosition("MSFT", "NASD", "USD", D(1), D(100), D(100), NOW)
    with pytest.raises(spy_cycle._RecoveryRequired, match="pre_submit_ownership_changed"):
        execute._book(
            replace(snapshot, positions=snapshot.positions + (foreign,)),
            _projection(arguments),
            CONFIG,
            NOW,
        )


def test_canary_hook_delegates_registered_stock_to_real_shared_budget(tmp_path, monkeypatch):
    arguments = _v4()
    root = tmp_path / "private"
    budget._atomic_json(root / budget.BUDGET_FILE, arguments["binding"])
    monkeypatch.setattr(spy_cycle, "conflicts_with_active_spy_fill_cycle", lambda *args: False)
    original = budget.conflicts_with_budget_strategy
    calls = []

    def recorded(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(budget, "conflicts_with_budget_strategy", recorded)
    seed = next(iter(arguments["states"].values()))
    intent = replace(seed.intent, run_id="unrelated-stock")
    assert canary._conflicts_with_owned_spy_cycle(root, intent) is True
    assert calls == [(root, "unrelated-stock", "AAPL")]
    assert canary._conflicts_with_owned_spy_cycle(root, replace(intent, symbol="MSFT")) is False


def test_missing_stock_state_never_turns_its_reservation_into_free_capacity():
    arguments = _v4()
    arguments["states"] = {}
    result = _preview(arguments)
    assert (result.status, result.reason) == ("unavailable", "state_scope_invalid")
    plan = build_kis_paper_portfolio_plan(**arguments)
    assert plan.status == "unavailable" and plan.binding is None


def test_empty_v4_stock_registry_preserves_legacy_trio_preview_exactly():
    assert _preview(_v4(include_stock=False)) == project_kis_paper_portfolio_preview(**_scope())
