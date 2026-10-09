from __future__ import annotations

import copy
import json
import socket
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_preview import ACCOUNT, NOW, _scope, _state
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired

D = Decimal
REF = "ref:" + "c" * 64


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("synthetic stock binding tests cannot use credentials or broker")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", deny)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", deny)


def _binding(*states, quantity="2", price="100", stock=True, account=ACCOUNT):
    original = _scope(*states)["binding"]
    original["account_ref"] = account
    original["basis_ref"] = budget._basis(original).fingerprint
    original["spy_owner_ref"] = budget._owners(original)[0][0].fingerprint
    original["qqq"]["owner_ref"] = budget._owners(original)[1][0].fingerprint
    binding = copy.deepcopy(original)
    binding.update(
        version=3, portfolio={"owner_refs": dict.fromkeys(("SPY", "TLT", "GLD")), "plans": []}
    )
    for owner, _ in budget._owners(binding):
        if owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    binding.update(version=4, stocks={})
    if not stock:
        return binding, None
    entry = {
        "exchange": "NASD",
        "instrument_binding_ref": REF,
        "owner_ref": "sha256:" + "0" * 64,
        "plans": [],
    }
    binding["stocks"]["AAPL"] = entry
    request, input_ref = "synthetic-stock-1", "sha256:" + "d" * 64
    identity = budget._stock_identity(binding, "AAPL", request, "buy")
    intent = KisPaperCanaryIntent(
        "bk-" + identity,
        "stock-" + identity,
        "stock-" + identity,
        "AAPL",
        "NASD",
        D(quantity),
        D(price),
        NOW - timedelta(minutes=2),
        NOW + timedelta(minutes=1),
        price_contract_ref=budget._stock_price_ref(binding, "AAPL", input_ref, D(price), "buy"),
    )
    seed = KisPaperCanaryState(intent, "intent_recorded", intent.created_at, "preview")
    entry["plans"].append(
        {
            "request_id": request,
            "input_ref": input_ref,
            "parent_binding_ref": "sha256:" + budget._digest(original),
            "states": {intent.run_id: seed.to_dict()},
        }
    )
    entry["owner_ref"] = budget._owners(binding)[-1][0].fingerprint
    return binding, seed


def _pure(binding, states, *, as_of=NOW, **extra):
    return budget.project_shared_budget(
        binding=binding,
        states=states,
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: pin for owner, pin in budget._owners(binding)},
        as_of=as_of,
        **extra,
    )


def _persist(root, binding, *states):
    root.mkdir(exist_ok=True)
    (root / budget.BUDGET_FILE).write_text(json.dumps(binding), encoding="utf-8")
    for state in states:
        (root / (state.intent.run_id + ".json")).write_text(
            json.dumps(state.to_dict()), encoding="utf-8"
        )


def _submitted(seed, quantity="1", amount="80", *, unknown=False):
    started = seed.intent.created_at + timedelta(seconds=1)
    if unknown:
        return replace(
            seed,
            phase="outcome_unknown",
            updated_at=started,
            reason_code="submit_transport_unknown",
            submission_started_at=started,
        )
    observed = started + timedelta(seconds=1)
    order = "SYNTHETIC-STOCK-1"
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id=order,
            order_at=started,
            symbol=seed.intent.symbol,
            exchange=seed.intent.exchange,
            side=seed.intent.side,
            quantity=seed.intent.quantity,
        ),
        seed.intent.quantity,
        D(quantity),
        D(amount),
        observed,
        seed.intent.quantity - D(quantity),
    )
    return replace(
        seed,
        phase="submitted",
        reason_code="reconciliation_clean",
        updated_at=observed,
        submission_started_at=started,
        submitted_at=started,
        broker_order_id=order,
        cumulative_fill=fill,
        fill_observation_status="available",
        fill_observed_at=observed,
    )


def test_legacy_owner_and_basis_fingerprints_unchanged_with_stock():
    v4, seed = _binding(_state())
    v3 = {key: copy.deepcopy(value) for key, value in v4.items() if key != "stocks"}
    v3["version"] = 3
    assert budget._basis(v4).fingerprint == budget._basis(v3).fingerprint
    assert budget._owners(v4)[:-1] == budget._owners(v3)
    assert budget._portfolio_seed_states(v4) == {}
    assert budget._stock_seed_states(v4) == {seed.intent.run_id: seed}


def test_all_consumers_see_same_reservation_without_materialization(tmp_path):
    binding, seed = _binding()
    _persist(tmp_path, binding)
    before = copy.deepcopy(binding)
    for select in (
        {},
        {"qqq_cycle_id": binding["qqq"]["cycle_id"]},
        {"portfolio_symbol": "TLT"},
        {"stock_symbol": "AAPL"},
    ):
        result = budget.project_budget(
            tmp_path, budget._load_binding(tmp_path), as_of=NOW, **select
        )
        assert result.reserved_buys == 200
        assert result.remaining_gross_cash == 800
        assert result.entry_cost == 0 and result.quantity == 0
    assert binding == before
    assert not (tmp_path / (seed.intent.run_id + ".json")).exists()


def test_pure_replay_never_opens_files_or_store(monkeypatch):
    binding, seed = _binding(_state())
    states = {seed.intent.run_id: seed, _state().intent.run_id: _state()}
    monkeypatch.setattr(KisPaperCanaryStateStore, "read", lambda *a: pytest.fail("store read"))
    monkeypatch.setattr(budget, "_load_binding", lambda *a: pytest.fail("binding read"))
    original = copy.deepcopy((binding, states))
    result = _pure(binding, states)
    assert result.entry_cost == 60 and result.reserved_buys == 200
    assert result.remaining_gross_cash == 740
    assert (binding, states) == original


@pytest.mark.parametrize("mode", ["partial", "full", "unknown", "later_unavailable"])
def test_cumulative_stock_fills_and_unknown_reservations(mode, tmp_path):
    binding, seed = _binding()
    state = _submitted(seed, "2", "160") if mode == "full" else _submitted(seed)
    if mode == "unknown":
        state = _submitted(seed, unknown=True)
    elif mode == "later_unavailable":
        state = replace(
            state, updated_at=NOW, fill_observation_status="unavailable", fill_observed_at=NOW
        )
    _persist(tmp_path, binding, state)
    expected = (
        (D(0), D(0), D(200))
        if mode == "unknown"
        else ((D(2), D(160), D(0)) if mode == "full" else (D(1), D(80), D(100)))
    )
    for _ in range(3):
        observed = budget.project_budget(
            tmp_path, budget._load_binding(tmp_path), stock_symbol="AAPL", as_of=NOW
        )
        assert (observed.quantity, observed.entry_cost, observed.reserved_buys) == expected
    assert _pure(binding, {state.intent.run_id: state}).reserved_buys == expected[2]


@pytest.mark.parametrize(
    "field,value",
    [
        ("exchange", "NYSE"),
        ("exchange", "AMEX"),
        ("instrument_binding_ref", "sha256:" + "c" * 64),
        ("instrument_binding_ref", True),
        ("owner_ref", None),
        ("owner_ref", True),
        ("plans", {}),
        ("extra", False),
    ],
)
def test_strict_stock_registry_rejects_schema_drift(field, value):
    binding, _ = _binding()
    binding["stocks"]["AAPL"][field] = value
    with pytest.raises(_RecoveryRequired):
        budget._stock_seed_states(binding)


@pytest.mark.parametrize("symbol", ["aapl", "AAPL/", "QQQ", "SPY", "TLT", "GLD", True])
def test_registry_symbol_scope_exact(symbol):
    binding, _ = _binding()
    binding["stocks"] = {symbol: binding["stocks"].pop("AAPL")}
    with pytest.raises(_RecoveryRequired):
        budget._stock_seed_states(binding)


@pytest.mark.parametrize(
    "change",
    [
        "two_owners",
        "two_states",
        "duplicate_request",
        "input",
        "parent",
        "identity",
        "price_ref",
        "ttl",
        "attempted_seed",
        "symbol",
        "exchange",
    ],
)
def test_exact_seed_and_plan_identity_rejects_mutations(change):
    binding, seed = _binding()
    plan = binding["stocks"]["AAPL"]["plans"][0]
    if change == "two_owners":
        binding["stocks"]["MSFT"] = copy.deepcopy(binding["stocks"]["AAPL"])
    elif change == "two_states":
        plan["states"]["bk-" + "f" * 64] = seed.to_dict()
    elif change == "duplicate_request":
        binding["stocks"]["AAPL"]["plans"].append(copy.deepcopy(plan))
    elif change == "input":
        plan["input_ref"] = "sha256:" + "f" * 64
    elif change == "parent":
        plan["parent_binding_ref"] = False
    elif change == "identity":
        plan["request_id"] = "other"
    else:
        intent = seed.intent
        if change == "price_ref":
            intent = replace(intent, price_contract_ref="sha256:" + "f" * 64)
        elif change == "ttl":
            intent = replace(intent, valid_until=intent.created_at + timedelta(minutes=6))
        elif change == "symbol":
            intent = replace(intent, symbol="MSFT")
        elif change == "exchange":
            intent = replace(intent, exchange="NYSE")
        state = replace(seed, intent=intent)
        if change == "attempted_seed":
            state = _submitted(seed, unknown=True)
        plan["states"][seed.intent.run_id] = state.to_dict()
    with pytest.raises((_RecoveryRequired, ValueError)):
        budget._stock_seed_states(binding)


def test_missing_materialized_state_cannot_fall_back_to_seed(tmp_path):
    binding, seed = _binding()
    _persist(tmp_path, binding)
    (tmp_path / ("." + seed.intent.run_id + ".json.lock")).write_text("", encoding="utf-8")
    with pytest.raises(_RecoveryRequired, match="materialized_state_missing"):
        budget.project_budget(tmp_path, binding, as_of=NOW)


@pytest.mark.parametrize("version", [1, 2, 3])
def test_stock_files_cannot_hide_under_legacy_binding(version, tmp_path):
    binding, seed = _binding()
    keys = {1: budget._V1_KEYS, 2: budget._V2_KEYS, 3: budget._V3_KEYS}[version]
    legacy = {key: value for key, value in binding.items() if key in keys}
    legacy["version"] = version
    _persist(tmp_path, legacy, seed)
    with pytest.raises(_RecoveryRequired, match="stock_state_unbound"):
        budget._load_binding(tmp_path)


def test_v4_cannot_downgrade_and_empty_registry_is_valid(tmp_path, monkeypatch):
    binding, _ = _binding(stock=False)
    _persist(tmp_path, binding)
    assert budget._load_binding(tmp_path) == binding
    monkeypatch.setattr(budget, "_atomic_json", lambda *a: pytest.fail("unexpected migration"))
    assert (
        budget._migrate_binding(tmp_path, binding, None, binding["qqq"]["cycle_id"], as_of=NOW)
        is binding
    )
    wrong = binding | {"version": 3}
    _persist(tmp_path, wrong)
    with pytest.raises(_RecoveryRequired, match="budget_binding_invalid"):
        budget._load_binding(tmp_path)


def test_shared_cap_rejects_stock_plus_legacy_overcommit():
    binding, seed = _binding(_state(), quantity="10")
    with pytest.raises(ValueError, match="aggregate_budget_exceeded"):
        _pure(binding, {_state().intent.run_id: _state(), seed.intent.run_id: seed})


def test_terminal_expiry_releases_only_proven_never_started():
    binding, seed = _binding()
    late = seed.intent.valid_until + timedelta(seconds=1)
    expired = replace(seed, updated_at=late, reason_code="intent_expired")
    binding["terminal_evidence"][seed.intent.run_id] = budget._terminal_payload(expired)
    assert _pure(binding, {seed.intent.run_id: expired}, as_of=late).reserved_buys == 0
    attempted = _submitted(seed, unknown=True)
    with pytest.raises(_RecoveryRequired):
        _pure(binding, {seed.intent.run_id: attempted}, as_of=late)


def test_conflicts_are_stock_scoped_and_existing_etf_capacity_includes_stock(tmp_path):
    binding, seed = _binding()
    _persist(tmp_path, binding)
    assert budget.conflicts_with_budget_strategy(tmp_path, "bare-aapl", "AAPL")
    assert budget.conflicts_with_budget_strategy(tmp_path, "bare-spy", "SPY")
    assert not budget.conflicts_with_budget_strategy(tmp_path, "bare-msft", "MSFT")
    assert budget.conflicts_with_budget_strategy(tmp_path, seed.intent.run_id, "AAPL")


def test_disjoint_stock_unknown_does_not_become_baseline_sell_pause(tmp_path):
    binding, seed = _binding()
    _persist(tmp_path, binding, _submitted(seed, unknown=True))
    assert not budget._other_owned_intent_pending(tmp_path, binding, "bs-" + "a" * 64)


def test_unknown_qqq_custody_is_preserved_and_reserved(tmp_path):
    qqq = _state(symbol="QQQ", pending=True)
    qqq = replace(
        qqq,
        phase="outcome_unknown",
        reason_code="submit_transport_unknown",
        submission_started_at=qqq.intent.created_at,
        updated_at=NOW,
    )
    binding, seed = _binding(qqq)
    binding["qqq"]["orders"][0]["closed"] = False
    _persist(tmp_path, binding, qqq)
    before = copy.deepcopy(binding["qqq"])
    for select in (
        {},
        {"qqq_cycle_id": binding["qqq"]["cycle_id"]},
        {"portfolio_symbol": "GLD"},
        {"stock_symbol": "AAPL"},
    ):
        projection = budget.project_budget(tmp_path, binding, as_of=NOW, **select)
        assert projection.reserved_buys == 300 and projection.remaining_gross_cash == 700
    assert binding["qqq"] == before
    assert not budget._terminal(qqq)
    assert _pure(binding, {qqq.intent.run_id: qqq, seed.intent.run_id: seed}).reserved_buys == 300


@pytest.mark.parametrize("symbol", ["SPY", "QQQ"])
def test_existing_baseline_and_qqq_sizing_cannot_ignore_stock_reservation(
    symbol, tmp_path, monkeypatch
):
    from test_kis_paper_portfolio_budget_integration import ENV, Broker, receipt

    root = tmp_path / "state"
    root.mkdir()
    broker = Broker(root)
    broker.now = NOW
    config = broker._config
    account = budget._digest([config.base_url, config.account_number, config.account_product_code])
    binding, _ = _binding(quantity="10", account=account)
    _persist(root, binding)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", lambda *a: broker._config)
    outcome = budget.run_kis_paper_budget_strategy(
        receipt_loader=lambda at: receipt(at, symbol=symbol),
        environment=ENV,
        state_root=root,
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "snapshot.json",
        emergency_state_path=tmp_path / "emergency.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execution_control_path=tmp_path / "control.json",
        execute=True,
        client=broker,
        clock=lambda: NOW,
        **({"qqq_cycle_id": binding["qqq"]["cycle_id"]} if symbol == "QQQ" else {}),
    )
    assert outcome.status == "no_intent" and outcome.reason_code == "budget_below_one_share", {
        "status": outcome.status,
        "reason_code": outcome.reason_code,
        "failure_diagnostic": outcome.failure_diagnostic,
    }
    assert broker.submits == [] and broker.cancels == []
    assert budget._load_binding(root) == binding


def test_orphan_and_duplicate_stock_state_bindings_reject(tmp_path):
    binding, seed = _binding()
    _persist(tmp_path, binding)
    orphan = tmp_path / ("bk-" + "f" * 64 + ".json")
    orphan.write_text(json.dumps(seed.to_dict()), encoding="utf-8")
    with pytest.raises(_RecoveryRequired, match="stock_state_unbound"):
        budget._load_binding(tmp_path)


def test_duplicate_decoded_stock_keys_reject_before_replay(tmp_path):
    binding, _ = _binding()
    _persist(tmp_path, binding)
    text = json.dumps(binding)
    text = text.replace('"exchange": "NASD"', '"exchange": "NASD", "exchange": "NASD"')
    (tmp_path / budget.BUDGET_FILE).write_text(text, encoding="utf-8")
    with pytest.raises(_RecoveryRequired, match="budget_duplicate_key"):
        budget._load_binding(tmp_path)


@pytest.mark.parametrize(
    "change", ["missing", "extra", "foreign_account", "owner_pin", "basis_pin", "future_state"]
)
def test_pure_replay_requires_full_exact_custody(change):
    binding, seed = _binding()
    states = {seed.intent.run_id: seed}
    if change == "missing":
        states.clear()
    elif change == "extra":
        states["foreign"] = seed
    elif change == "foreign_account":
        binding["account_ref"] = "b" * 64
    elif change == "owner_pin":
        binding["stocks"]["AAPL"]["owner_ref"] = "sha256:" + "f" * 64
    elif change == "basis_pin":
        binding["basis_ref"] = "sha256:" + "f" * 64
    else:
        states[seed.intent.run_id] = replace(seed, updated_at=NOW + timedelta(seconds=1))
    with pytest.raises((_RecoveryRequired, ValueError)):
        _pure(binding, states)
