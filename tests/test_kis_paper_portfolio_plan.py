from __future__ import annotations

import builtins
import copy
import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_preview import ACCOUNT, NOW, _reads, _scope, _state
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryStateStore,
    _conflicts_with_owned_spy_cycle,
)
from thericher_v2.execution.kis_paper_portfolio_plan import (
    build_kis_paper_portfolio_plan,
    reconcile_kis_paper_portfolio_plan,
    reserve_kis_paper_portfolio_plan,
)
from thericher_v2.execution.kis_paper_portfolio_preview import project_kis_paper_portfolio_preview
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_readonly import KisPaperPosition

D = Decimal


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("source-free ownership tests cannot access provider or credentials")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", deny)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", deny)


def _arguments(*states):
    inputs = _scope(*states)
    inputs.update(
        request_id="synthetic-portfolio-1",
        input_ref="sha256:" + "d" * 64,
        expected_binding_ref="sha256:" + budget._digest(inputs["binding"]),
        valid_until=NOW + timedelta(minutes=5),
    )
    return inputs


def _combined(arguments, result):
    return dict(arguments["states"]) | budget._portfolio_seed_states(result.binding)


def _persist(tmp_path, arguments):
    root = tmp_path / "p"
    root.mkdir()
    budget._atomic_json(root / budget.BUDGET_FILE, arguments["binding"])
    for state in arguments["states"].values():
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
    return dict(
        state_root=root,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
        **{key: value for key, value in arguments.items() if key not in {"binding", "states"}},
    )


def test_pure_joint_whole_share_plan_preserves_original_basis_and_incumbent(monkeypatch):
    arguments = _arguments(_state())
    original = copy.deepcopy(arguments)
    monkeypatch.setattr(builtins, "open", lambda *a, **k: pytest.fail("pure builder cannot do I/O"))
    result = build_kis_paper_portfolio_plan(**arguments)
    assert arguments == original
    assert result.status == "prepared"
    assert [(i.symbol, i.quantity, i.limit_price) for i in result.intents] == [
        ("SPY", D(2), D(100)),
        ("TLT", D(3), D(100)),
        ("GLD", D(3), D(100)),
    ]
    assert result.reservation == 800
    assert result.binding["version"] == 3
    assert {key: value for key, value in result.binding.items() if key != "portfolio"} == (
        arguments["binding"] | {"version": 3}
    )
    assert result.binding["spy_owner_ref"] == original["binding"]["spy_owner_ref"]
    assert result.binding["qqq"] == original["binding"]["qqq"]
    payload = json.dumps(result.safe_payload()) + repr(result)
    assert "800" not in payload and ACCOUNT not in payload and result.plan_ref not in payload
    assert result.safe_payload()["new_submits"] == 0


def test_v2_preview_unchanged_and_v3_pending_is_never_feasible():
    arguments = _arguments(_state())
    fields = {
        key: value
        for key, value in arguments.items()
        if key not in {"request_id", "input_ref", "expected_binding_ref", "valid_until"}
    }
    before = project_kis_paper_portfolio_preview(**fields)
    assert before.status == "preview_feasible"
    result = build_kis_paper_portfolio_plan(**arguments)
    fields.update(
        binding=result.binding,
        states=_combined(arguments, result),
        expected_owner_refs={owner.owner_ref: pin for owner, pin in budget._owners(result.binding)},
    )
    after = project_kis_paper_portfolio_preview(**fields)
    assert (after.status, after.reason) == ("unreachable", "pending_identity")
    assert after.shared_reservations == result.reservation and after.pending_count == 3


def test_named_input_permutation_and_three_restarts_are_exact():
    arguments = _arguments(_state())
    initial = build_kis_paper_portfolio_plan(**arguments)
    permuted = copy.deepcopy(arguments)
    for field in ("weights_by_symbol", "covariance_by_symbol"):
        permuted[field] = dict(reversed(list(permuted[field].items())))
    assert build_kis_paper_portfolio_plan(**permuted) == initial
    retry = {
        **arguments,
        "binding": initial.binding,
        "states": _combined(arguments, initial),
        "reads": None,
        "as_of": NOW + timedelta(hours=2),
    }
    for _ in range(3):
        result = build_kis_paper_portfolio_plan(**copy.deepcopy(retry))
        assert result.status == "replayed"
        assert result.intents == initial.intents and result.binding == initial.binding
        assert result.plan_ref == initial.plan_ref and result.reservation == initial.reservation


@pytest.mark.parametrize(
    "change", ["account", "basis", "owners", "parent", "input", "request", "expiry"]
)
def test_invalid_custody_and_identity_do_not_create_a_plan(change):
    arguments = _arguments(_state())
    if change == "account":
        arguments["expected_account_ref"] = "b" * 64
    elif change == "basis":
        arguments["expected_basis_ref"] = "sha256:" + "b" * 64
    elif change == "owners":
        arguments["expected_owner_refs"] = {}
    elif change == "parent":
        arguments["expected_binding_ref"] = "sha256:" + "b" * 64
    elif change == "input":
        arguments["input_ref"] = True
    elif change == "request":
        arguments["request_id"] = "../escape"
    else:
        arguments["valid_until"] = NOW + timedelta(minutes=6)
    try:
        result = build_kis_paper_portfolio_plan(**arguments)
    except _RecoveryRequired:
        return
    assert result.status == "unavailable" and result.binding is None


@pytest.mark.parametrize("change", ["input_ref", "expected_binding_ref", "expected_owner_refs"])
def test_same_request_cannot_be_replaced_or_reset(change):
    arguments = _arguments(_state())
    initial = build_kis_paper_portfolio_plan(**arguments)
    arguments.update(binding=initial.binding, states=_combined(arguments, initial))
    arguments[change] = {} if change == "expected_owner_refs" else "sha256:" + "b" * 64
    with pytest.raises(_RecoveryRequired, match="portfolio_request_conflict"):
        build_kis_paper_portfolio_plan(**arguments)


@pytest.mark.parametrize(
    "failure", ["foreign", "stale", "missing", "pending", "risk", "incumbent", "funds"]
)
def test_unreachable_or_unavailable_never_reserves(failure):
    arguments = _arguments(_state())
    if failure == "foreign":
        arguments["reads"] = _reads(
            extra=(KisPaperPosition("TLT", "NASD", "USD", D(1), D(100), D(100), NOW),)
        )
    elif failure == "stale":
        arguments["as_of"] = NOW + timedelta(minutes=3)
    elif failure == "missing":
        arguments["reads"] = None
    elif failure == "pending":
        arguments = _arguments(_state(), _state(2, pending=True))
    elif failure == "risk":
        arguments["covariance_by_symbol"]["SPY"]["SPY"] = D(1)
    elif failure == "incumbent":
        arguments["weights_by_symbol"] = dict(SPY=D(0), TLT=D(0), GLD=D(0))
    else:
        arguments["reads"] = _reads(funds=D(700))
    result = build_kis_paper_portfolio_plan(**arguments)
    assert result.status in {"unreachable", "unavailable"}
    assert result.binding is None and not result.intents


def test_atomic_shared_reservation_and_restart_without_order_files(tmp_path):
    arguments = _arguments(_state())
    call = _persist(tmp_path, arguments)
    initial = reserve_kis_paper_portfolio_plan(**call)
    assert initial.status == "reserved"
    root = call["state_root"]
    assert not list(root.glob("bp-*.json"))
    raw = (root / budget.BUDGET_FILE).read_bytes()
    assert budget.project_budget(root, budget._load_binding(root), as_of=NOW).reserved_buys == 800
    assert (
        budget.project_budget(
            root, budget._load_binding(root), qqq_cycle_id="synthetic-unit", as_of=NOW
        ).reserved_buys
        == 800
    )
    for _ in range(3):
        replay = reserve_kis_paper_portfolio_plan(**{**call, "reads": None})
        assert replay.status == "replayed" and replay.intents == initial.intents
        assert (root / budget.BUDGET_FILE).read_bytes() == raw


@pytest.mark.parametrize("after_replace", [False, True])
def test_interrupted_atomic_write_has_no_partial_batch_or_duplicate(
    tmp_path, monkeypatch, after_replace
):
    arguments = _arguments(_state())
    call = _persist(tmp_path, arguments)
    atomic = budget._atomic_json
    before = (call["state_root"] / budget.BUDGET_FILE).read_bytes()

    def fail(path, payload):
        if after_replace:
            atomic(path, payload)
        raise OSError("synthetic interruption")

    monkeypatch.setattr(budget, "_atomic_json", fail)
    with pytest.raises(OSError):
        reserve_kis_paper_portfolio_plan(**call)
    retained = budget._load_binding(call["state_root"])
    assert retained["version"] == (3 if after_replace else 2)
    if not after_replace:
        assert (call["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    monkeypatch.setattr(budget, "_atomic_json", atomic)
    recovered = reserve_kis_paper_portfolio_plan(**call)
    assert recovered.status == ("replayed" if after_replace else "reserved")
    assert len(recovered.binding["portfolio"]["plans"]) == 1


def test_concurrent_same_request_reserves_once(tmp_path):
    call = _persist(tmp_path, _arguments(_state()))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve_kis_paper_portfolio_plan(**call), range(2)))
    assert sorted(result.status for result in results) == ["replayed", "reserved"]
    assert results[0].intents == results[1].intents
    assert (
        budget.project_budget(call["state_root"], results[0].binding, as_of=NOW).reserved_buys
        == 800
    )


@pytest.mark.parametrize(
    "corruption", ["extra_state", "duplicate_json", "owner", "seed", "duplicate_plan"]
)
def test_closed_shape_and_unbound_state_fail_without_dropping_reservations(tmp_path, corruption):
    call = _persist(tmp_path, _arguments(_state()))
    result = reserve_kis_paper_portfolio_plan(**call)
    root, binding = call["state_root"], copy.deepcopy(result.binding)
    if corruption == "extra_state":
        budget._atomic_json(root / ("bp-" + "f" * 64 + ".json"), {})
    elif corruption == "duplicate_json":
        path = root / budget.BUDGET_FILE
        path.write_text(
            path.read_text().replace('"version":3', '"version":2,"version":3'), encoding="utf-8"
        )
    else:
        if corruption == "owner":
            binding["portfolio"]["owner_refs"]["TLT"] = "sha256:" + "f" * 64
        elif corruption == "seed":
            seed = next(iter(binding["portfolio"]["plans"][0]["states"].values()))
            seed["phase"] = "rejected"
        else:
            binding["portfolio"]["plans"].append(copy.deepcopy(binding["portfolio"]["plans"][0]))
        budget._atomic_json(root / budget.BUDGET_FILE, binding)
    with pytest.raises((_RecoveryRequired, ValueError)):
        budget._load_binding(root)


def test_exact_partial_fill_and_later_unavailable_preserve_cost_and_remaining(tmp_path):
    call = _persist(tmp_path, _arguments(_state()))
    result = reserve_kis_paper_portfolio_plan(**call)
    intent = next(i for i in result.intents if i.symbol == "TLT")
    synthetic = _state(9, symbol="QQQ", requested="3", filled="1", remaining="2")
    from thericher_v2.execution.kis_paper_fill_accounting import fill_identity_ref

    fill = replace(
        synthetic.cumulative_fill,
        identity_ref=fill_identity_ref(
            raw_order_id=synthetic.broker_order_id,
            order_at=NOW,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side="buy",
            quantity=intent.quantity,
        ),
        observed_at=NOW + timedelta(seconds=1),
    )
    current = replace(
        synthetic,
        intent=intent,
        updated_at=NOW + timedelta(seconds=2),
        submission_started_at=NOW,
        submitted_at=NOW,
        cumulative_fill=fill,
        fill_observed_at=fill.observed_at,
    )
    root = call["state_root"]
    budget._atomic_json(root / (intent.run_id + ".json"), current.to_dict())
    first = budget.project_budget(root, result.binding, as_of=NOW + timedelta(seconds=2))
    assert first.entry_cost == 120 and first.reserved_buys == 700
    unavailable = replace(
        current,
        updated_at=NOW + timedelta(seconds=3),
        fill_observation_status="unavailable",
        fill_observed_at=NOW + timedelta(seconds=3),
    )
    budget._atomic_json(root / (intent.run_id + ".json"), unavailable.to_dict())
    assert budget.project_budget(root, result.binding, as_of=unavailable.updated_at) == first
    replay = reserve_kis_paper_portfolio_plan(
        **{**call, "as_of": unavailable.updated_at, "reads": None}
    )
    assert replay.status == "replayed" and replay.intents == result.intents


def test_bare_canary_cannot_dispatch_prepared_portfolio_identity(tmp_path):
    call = _persist(tmp_path, _arguments(_state()))
    result = reserve_kis_paper_portfolio_plan(**call)
    for intent in result.intents:
        assert budget.conflicts_with_budget_strategy(
            call["state_root"], intent.run_id, intent.symbol
        )
    assert not budget.conflicts_with_budget_strategy(call["state_root"], "unrelated", "IWM")


def test_zero_incremental_control_is_no_intent_and_v2_bytes_unchanged(tmp_path):
    arguments = _arguments()
    arguments["reads"] = _reads(spy=D(0))
    arguments["weights_by_symbol"] = dict(SPY=D(0), TLT=D(0), GLD=D(0))
    call = _persist(tmp_path, arguments)
    before = (call["state_root"] / budget.BUDGET_FILE).read_bytes()
    result = reserve_kis_paper_portfolio_plan(**call)
    assert result.status == "no_intent" and result.reason == "no_incremental_buy"
    assert (call["state_root"] / budget.BUDGET_FILE).read_bytes() == before


def test_missing_current_basis_cannot_create_or_adopt_an_account(tmp_path):
    call = _persist(tmp_path, _arguments(_state()))
    (call["state_root"] / budget.BUDGET_FILE).unlink()
    with pytest.raises(_RecoveryRequired):
        reserve_kis_paper_portfolio_plan(**call)


def test_realized_gross_loss_does_not_replenish_original_capital():
    from test_kis_paper_portfolio_budget import _owner, _project
    from test_kis_paper_portfolio_budget import _state as filled_state

    buy = filled_state("buy-loss", filled="1", gross="60", remaining="0")
    sell = filled_state("sell-loss", side="sell", filled="1", gross="40", index=1)
    projection = _project(_owner("owner", buy, sell))
    assert projection.entry_cost == 0 and projection.remaining_cap == 1000
    assert projection.gross_cash == projection.remaining_gross_cash == 980
    pending = filled_state("later-buy", quantity="10", limit="99", phase="intent_recorded", index=2)
    with pytest.raises(ValueError, match="aggregate_gross_cash_exceeded"):
        _project(_owner("owner", buy, sell, pending))


def test_v3_incremental_plan_uses_gross_cash_after_owned_qqq_loss():
    from thericher_v2.execution.kis_paper_fill_accounting import fill_identity_ref

    buy, sell = _state(1, symbol="QQQ"), _state(2, symbol="QQQ")
    sell_intent = replace(sell.intent, side="sell")
    sell_fill = replace(
        sell.cumulative_fill,
        gross_amount=D(40),
        identity_ref=fill_identity_ref(
            raw_order_id=sell.broker_order_id,
            order_at=sell.submission_started_at,
            symbol="QQQ",
            exchange="NASD",
            side="sell",
            quantity=D(1),
        ),
    )
    sell = replace(sell, intent=sell_intent, cumulative_fill=sell_fill)
    arguments = _arguments(buy, sell)
    binding = arguments["binding"]
    binding.update(basis_usd="1000", allocated_usd="100")
    binding["basis_ref"] = budget._basis(binding).fingerprint
    arguments.update(
        expected_basis_ref=binding["basis_ref"],
        expected_binding_ref="sha256:" + budget._digest(binding),
        reads=_reads(spy=D(0), prices=(D(1), D(1), D(1))),
        weights_by_symbol=dict(SPY=D(1), TLT=D(0), GLD=D(0)),
    )
    result = build_kis_paper_portfolio_plan(**arguments)
    assert result.status == "prepared" and result.reservation == 80
    assert [(i.symbol, i.quantity) for i in result.intents] == [("SPY", D(80))]
    assert result.binding["allocated_usd"] == "100" and result.binding["qqq"] == binding["qqq"]


@pytest.mark.parametrize("phase", ["intent_recorded", "submission_started", "outcome_unknown"])
def test_missing_materialized_state_is_scoped_unknown_not_seed_replacement(tmp_path, phase):
    call = _persist(tmp_path, _arguments(_state()))
    result = reserve_kis_paper_portfolio_plan(**call)
    intent = result.intents[0]
    store = KisPaperCanaryStateStore(call["state_root"] / (intent.run_id + ".json"))
    store.record_intent(intent, cancel_after_submit=False, now=NOW)
    if phase != "intent_recorded":
        store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="submission_started",
            reason_code="submit_transport_unknown",
            now=NOW,
            submission_started_at=NOW,
        )
    if phase == "outcome_unknown":
        store.transition(
            intent,
            expected=frozenset({"submission_started"}),
            phase=phase,
            reason_code="submit_transport_unknown",
            now=NOW,
        )
    store.path.unlink()
    retained = (call["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired, match="portfolio_materialized_state_missing"):
        reserve_kis_paper_portfolio_plan(**call)
    with pytest.raises(_RecoveryRequired, match="portfolio_materialized_state_missing"):
        reserve_kis_paper_portfolio_plan(**{**call, "request_id": "different-request"})
    assert (call["state_root"] / budget.BUDGET_FILE).read_bytes() == retained
    assert result.reservation == 800 and len(result.binding["portfolio"]["plans"]) == 1


@pytest.mark.parametrize("nested", [False, True])
def test_state_duplicate_keys_rejected_before_typed_parse(tmp_path, nested):
    state = _state()
    path = tmp_path / "state.json"
    text = json.dumps(state.to_dict(), separators=(",", ":"))
    needle = '"quantity":"1"' if nested else '"phase":"submitted"'
    text = text.replace(needle, needle + "," + needle)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(KisPaperCanaryError) as caught:
        KisPaperCanaryStateStore(path).read()
    assert caught.value.code == "state_invalid"


def test_tlt_gld_guard_is_connected_and_not_a_global_v3_hold(tmp_path):
    arguments = _arguments(_state())
    arguments["weights_by_symbol"] = dict(SPY=D("0.33"), TLT=D("0.33"), GLD=D(0))
    call = _persist(tmp_path, arguments)
    result = reserve_kis_paper_portfolio_plan(**call)
    tlt = next(intent for intent in result.intents if intent.symbol == "TLT")
    assert _conflicts_with_owned_spy_cycle(call["state_root"], tlt)
    unrelated = replace(tlt, symbol="GLD", exchange="AMEX", run_id="unrelated")
    assert not _conflicts_with_owned_spy_cycle(call["state_root"], unrelated)


@pytest.mark.parametrize("unknown", [False, True])
def test_exact_terminal_reconciliation_releases_only_proven_residuals(tmp_path, unknown):
    call = _persist(tmp_path, _arguments(_state()))
    result = reserve_kis_paper_portfolio_plan(**call)
    root = call["state_root"]
    for index, intent in enumerate(result.intents):
        store = KisPaperCanaryStateStore(root / (intent.run_id + ".json"))
        store.record_intent(intent, cancel_after_submit=False, now=NOW)
        if unknown and index == 0:
            store.transition(
                intent,
                expected=frozenset({"intent_recorded"}),
                phase="submission_started",
                reason_code="submit_transport_unknown",
                now=NOW,
                submission_started_at=NOW,
            )
            store.transition(
                intent,
                expected=frozenset({"submission_started"}),
                phase="outcome_unknown",
                reason_code="submit_transport_unknown",
                now=NOW,
            )
        else:
            store.transition(
                intent,
                expected=frozenset({"intent_recorded"}),
                phase="rejected",
                reason_code="submit_rejected",
                submit_response_category="provider_rejected",
                now=NOW,
            )
    reconcile = dict(
        state_root=root,
        repository_root=call["repository_root"],
        artifact_root=call["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=call["expected_basis_ref"],
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(result.binding)},
        request_id=call["request_id"],
        expected_plan_ref=result.plan_ref,
        as_of=NOW,
    )
    after = reconcile_kis_paper_portfolio_plan(**reconcile)
    assert after.status == ("pending" if unknown else "reconciled")
    projection = budget.project_budget(root, after.binding, as_of=NOW)
    assert projection.reserved_buys == (200 if unknown else 0)
    assert projection.entry_cost == 60 and projection.gross_cash == 940
    raw = (root / budget.BUDGET_FILE).read_bytes()
    assert reconcile_kis_paper_portfolio_plan(**reconcile) == after
    assert (root / budget.BUDGET_FILE).read_bytes() == raw
    assert after.binding["basis_ref"] == result.binding["basis_ref"]
    assert after.binding["portfolio"] == result.binding["portfolio"]


def test_pre_submit_expiry_requires_exact_materialized_no_attempt_state(tmp_path):
    call = _persist(tmp_path, _arguments(_state()))
    result = reserve_kis_paper_portfolio_plan(**call)
    at = NOW + timedelta(minutes=5)
    reconcile = dict(
        state_root=call["state_root"],
        repository_root=call["repository_root"],
        artifact_root=call["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=call["expected_basis_ref"],
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(result.binding)},
        request_id=call["request_id"],
        expected_plan_ref=result.plan_ref,
        as_of=at,
    )
    pending = reconcile_kis_paper_portfolio_plan(**reconcile)
    assert pending.status == "pending"
    assert budget.project_budget(call["state_root"], pending.binding, as_of=at).reserved_buys == 800
    for intent in result.intents:
        store = KisPaperCanaryStateStore(call["state_root"] / (intent.run_id + ".json"))
        store.record_intent(intent, cancel_after_submit=False, now=NOW)
        store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="intent_recorded",
            reason_code="intent_expired",
            now=at,
        )
    closed = reconcile_kis_paper_portfolio_plan(**reconcile)
    assert closed.status == "reconciled"
    assert budget.project_budget(call["state_root"], closed.binding, as_of=at).reserved_buys == 0


def test_portfolio_only_spy_inventory_blocks_unrelated_canary_sell_without_global_hold(tmp_path):
    from thericher_v2.execution.kis_paper_fill_accounting import fill_identity_ref

    arguments = _arguments()
    arguments["weights_by_symbol"] = dict(SPY=D("0.33"), TLT=D(0), GLD=D(0))
    call = _persist(tmp_path, arguments)
    result = reserve_kis_paper_portfolio_plan(**call)
    intent = result.intents[0]
    root = call["state_root"]
    store = KisPaperCanaryStateStore(root / (intent.run_id + ".json"))
    store.record_intent(intent, cancel_after_submit=False, now=NOW)
    synthetic = _state(9, requested="3", filled="3", remaining="0")
    fill = replace(
        synthetic.cumulative_fill,
        gross_amount=D(300),
        observed_at=NOW,
        identity_ref=fill_identity_ref(
            raw_order_id=synthetic.broker_order_id,
            order_at=NOW,
            symbol="SPY",
            exchange="AMEX",
            side="buy",
            quantity=D(3),
        ),
    )
    current = replace(
        synthetic,
        intent=intent,
        updated_at=NOW,
        submission_started_at=NOW,
        submitted_at=NOW,
        cumulative_fill=fill,
        fill_observed_at=NOW,
    )
    budget._atomic_json(store.path, current.to_dict())
    closed = reconcile_kis_paper_portfolio_plan(
        state_root=root,
        repository_root=call["repository_root"],
        artifact_root=call["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=call["expected_basis_ref"],
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(result.binding)},
        request_id=call["request_id"],
        expected_plan_ref=result.plan_ref,
        as_of=NOW,
    )
    projection = budget.project_budget(root, closed.binding, as_of=NOW)
    assert projection.quantity == 0 and projection.reserved_buys == 0
    assert projection.aggregate_quantity == 3
    unrelated = replace(intent, run_id="unrelated", side="sell")
    assert budget.conflicts_with_budget_strategy(root, unrelated.run_id, "SPY")
    assert _conflicts_with_owned_spy_cycle(root, unrelated)
    assert not budget.conflicts_with_budget_strategy(root, "unrelated", "TLT")
    assert not budget.conflicts_with_budget_strategy(root, "unrelated", "GLD")
    assert not budget.conflicts_with_budget_strategy(root, "unrelated", "IWM")
