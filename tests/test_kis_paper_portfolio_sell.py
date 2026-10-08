from __future__ import annotations

import copy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG, SyntheticPaperClient, _leg
from test_kis_paper_portfolio_execute import harness as harness
from test_kis_paper_portfolio_execute import (
    no_actual_provider_or_credentials as no_actual_provider_or_credentials,
)
from test_kis_paper_portfolio_preview import _reads
from test_kis_paper_portfolio_preview import _scope as preview_arguments
from test_kis_paper_portfolio_preview import _state as historical_state
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_execute as execute
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_plan import (
    _states,
    build_kis_paper_portfolio_plan,
    reconcile_kis_paper_portfolio_plan,
)
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_readonly import (
    KisHttpResponse,
    KisPaperOpenOrder,
    KisPaperPosition,
)

D = Decimal


class SellClient(SyntheticPaperClient):
    """Native SELL request/response mapping with synthetic account and fills."""

    def __init__(self, previous):
        super().__init__(previous.root)
        self.orders = copy.deepcopy(previous.orders)
        self.funds = self.exact_funds = previous.funds
        self.now = previous.now
        self._transport = self
        self._access_token = "synthetic-token"
        self.wire = []
        self.intent = None

    def snapshot(self):
        base = super().snapshot()
        totals, opens = {}, []
        for order in self.orders.values():
            intent = order["intent"]
            key = intent.symbol, intent.exchange
            totals[key] = totals.get(key, D(0)) + order["filled"] * (
                1 if intent.side == "buy" else -1
            )
            if order["remaining"]:
                opens.append(
                    KisPaperOpenOrder(
                        canary._redacted_open_order_reference(order["id"]),
                        *key,
                        "USD",
                        intent.side,
                        intent.quantity,
                        order["filled"],
                        order["remaining"],
                        intent.limit_price,
                        self.now,
                    )
                )
        positions = tuple(
            KisPaperPosition(s, ex, "USD", q, D(100), q * 100, self.now)
            for (s, ex), q in totals.items()
            if q
        )
        if self.foreign:
            positions += (KisPaperPosition("QQQ", "NASD", "USD", D(1), D(100), D(100), self.now),)
        if self.duplicate_position:
            positions += positions[:1]
        return replace(
            base, positions=positions, open_orders=replace(base.open_orders, orders=tuple(opens))
        )

    def request(self, request):
        intent = self.intent
        assert request.method == "POST"
        assert request.url == CONFIG.base_url + canary.KIS_PAPER_US_BUY_LIMIT_ORDER_PATH
        assert request.headers["tr_id"] == canary.KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID
        assert request.json_body["PDNO"] == intent.symbol
        assert request.json_body["OVRS_EXCG_CD"] == intent.exchange
        assert D(request.json_body["ORD_QTY"]) == intent.quantity
        assert D(request.json_body["OVRS_ORD_UNPR"]) == intent.limit_price
        canary.validate_kis_paper_canary_request(request)
        self.wire.append(request)
        order_id = str(200 + len(self.wire))
        filled = D(1) if self.partial else intent.quantity
        self.orders[intent.run_id] = dict(
            intent=intent, id=order_id, filled=filled, remaining=intent.quantity - filled
        )
        self.funds += filled * intent.limit_price
        if self.unknown:
            raise canary.KisPaperCanaryError("submit_transport_unknown")
        return KisHttpResponse.from_payload({"rt_cd": "0", "output": {"ODNO": order_id}})

    def submit_limit(self, intent, **kwargs):
        assert intent.side == "sell"
        state = canary.KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.intent == intent and state.phase == "submission_started"
        assert (
            budget._portfolio_seed_states(budget._load_binding(self.root))[intent.run_id].intent
            == intent
        )
        self.submits.append(intent)
        self.intent = intent
        return canary.KisPaperCanaryClient.submit_limit(self, intent, **kwargs)

    def reconcile(self, state, *, now):
        order = self.orders.get(state.intent.run_id)
        known = order is not None and order["id"] == state.broker_order_id
        observation = None
        if known:
            fill = (
                None
                if self.history_unavailable
                else KisPaperCumulativeFill(
                    fill_identity_ref(
                        raw_order_id=order["id"],
                        order_at=state.submission_started_at,
                        symbol=state.intent.symbol,
                        exchange=state.intent.exchange,
                        side=state.intent.side,
                        quantity=state.intent.quantity,
                    ),
                    state.intent.quantity,
                    order["filled"],
                    order["filled"] * state.intent.limit_price,
                    now,
                    order["remaining"],
                )
            )
            observation = KisPaperExecutionObservation(
                1,
                True,
                "unavailable" if fill is None else "available",
                fill,
                now,
            )
        return canary.KisPaperCanaryReconciliation(
            snapshot=self.snapshot(),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["remaining"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )


@pytest.fixture
def owned(harness):
    for symbol in ("SPY", "TLT", "GLD"):
        execute.execute_kis_paper_portfolio_buy(**_leg(harness, symbol))
    proof = harness["proof"]
    result = reconcile_kis_paper_portfolio_plan(
        state_root=harness["state_root"],
        repository_root=harness["repository_root"],
        artifact_root=harness["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=proof.basis_ref,
        expected_owner_refs=dict(proof.owner_refs),
        request_id=proof.request_id,
        expected_plan_ref=proof.plan_ref,
        as_of=harness["client"].now,
    )
    assert result.status == "reconciled"
    client = SellClient(harness["client"])
    return {**harness, "client": client, "clock": lambda: client.now}


def arguments(call, **updates):
    binding = budget._load_binding(call["state_root"])
    return (
        dict(
            expected_account_ref=ACCOUNT,
            expected_basis_ref=binding["basis_ref"],
            expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(binding)},
            expected_binding_ref="sha256:" + budget._digest(binding),
            request_id="portfolio-sell-synthetic-session",
            input_ref="sha256:" + "e" * 64,
            reductions_by_symbol={"SPY": D(2), "TLT": D(1), "GLD": D(1)},
            limits_by_symbol={"SPY": D(80), "TLT": D(80), "GLD": D(80)},
            as_of=call["client"].now,
            valid_until=call["client"].now + timedelta(minutes=5),
        )
        | updates
    )


def build(call, **updates):
    binding = budget._load_binding(call["state_root"])
    return execute.build_kis_paper_portfolio_sell_plan(
        binding=binding,
        states=_states(call["state_root"], binding),
        **arguments(call, **updates),
    )


def reserve(call, **updates):
    pins = arguments(call, **updates)
    result = execute.reserve_kis_paper_portfolio_sell_plan(
        state_root=call["state_root"],
        repository_root=call["repository_root"],
        artifact_root=call["artifact_root"],
        **pins,
    )
    return result, pins


def leg(call, result, pins, symbol="SPY"):
    intent = next(i for i in result.intents if i.symbol == symbol)
    proof = execute.KisPaperPortfolioExecutionBinding(
        state_root=call["state_root"].resolve(),
        account_ref=ACCOUNT,
        basis_ref=pins["expected_basis_ref"],
        owner_refs=tuple((o.owner_ref, ref) for o, ref in budget._owners(result.binding)),
        binding_ref="sha256:" + budget._digest(result.binding),
        request_id=pins["request_id"],
        parent_binding_ref=pins["expected_binding_ref"],
        input_ref=pins["input_ref"],
        plan_ref=result.plan_ref,
        run_id=intent.run_id,
        intent_ref=intent.fingerprint,
    )
    return {**call, "proof": proof}


def state(call):
    path = call["state_root"] / (call["proof"].run_id + ".json")
    return canary.KisPaperCanaryStateStore(path).read() if path.exists() else None


def close(call):
    return execute.reconcile_kis_paper_portfolio_sell_plan(
        proof=call["proof"],
        state_root=call["state_root"],
        repository_root=call["repository_root"],
        artifact_root=call["artifact_root"],
        as_of=call["client"].now,
    )


def test_default_inert_and_zero_delta_has_no_intents_or_book_rewrite(owned, monkeypatch):
    root = owned["state_root"]
    before = (root / budget.BUDGET_FILE).read_bytes()
    result, _ = reserve(
        owned,
        reductions_by_symbol=dict.fromkeys(("SPY", "TLT", "GLD"), D(0)),
        limits_by_symbol=None,
        valid_until=None,
    )
    assert result.status == "no_intent" and not result.intents
    assert (root / budget.BUDGET_FILE).read_bytes() == before
    monkeypatch.setattr(
        budget, "_load_binding", lambda *a, **kw: pytest.fail("inert must not read")
    )
    assert execute.execute_kis_paper_portfolio_sell(**{**owned, "execute": False}) is None


def test_all_three_native_sells_and_gross_loss_preserve_shared_original_basis(owned):
    original = budget._load_binding(owned["state_root"])
    result, pins = reserve(owned)
    assert result.status == "reserved" and len(result.intents) == 3
    assert result.safe_payload()["sell_leg_count"] == 3
    assert "buy_leg_count" not in result.safe_payload()
    assert result.binding["basis_ref"] == original["basis_ref"]
    assert result.binding["orders"] == original["orders"]
    assert result.binding["qqq"] == original["qqq"]
    original_ids = {i.intent.run_id for i in budget._portfolio_seed_states(original).values()}
    assert not original_ids & {i.run_id for i in result.intents}
    reserved_book = (owned["state_root"] / budget.BUDGET_FILE).read_bytes()
    for symbol in ("SPY", "TLT", "GLD"):
        call = leg(owned, result, pins, symbol)
        outcome = execute.execute_kis_paper_portfolio_sell(**call)
        assert outcome.phase == "submitted"
        assert state(call).current_fill.quantity == state(call).intent.quantity
    assert not owned["client"].limit_reads
    assert len(owned["client"].wire) == 3
    assert (owned["state_root"] / budget.BUDGET_FILE).read_bytes() == reserved_book
    projection = execute._scope(owned["state_root"], call["proof"], owned["client"].now)[-1]
    assert projection.entry_cost == D(500)
    assert projection.remaining_gross_cash == D(420)
    assert projection.reserved_buys == 0
    assert {
        s.symbol: s.quantity
        for s in projection.stocks_by_owner
        if s.owner_ref.startswith("portfolio-")
    } == {
        "SPY": D(1),
        "TLT": D(2),
        "GLD": D(2),
    }
    completed = close(call)
    assert completed.status == "reconciled" and completed.plan_ref == result.plan_ref
    assert (
        close(
            {
                **call,
                "proof": replace(
                    call["proof"], binding_ref="sha256:" + budget._digest(completed.binding)
                ),
            }
        ).status
        == "reconciled"
    )


@pytest.mark.parametrize("symbol", ["SPY", "TLT", "GLD"])
def test_exact_retry_retains_terms_and_never_submits_twice(owned, symbol):
    result, pins = reserve(owned)
    call = leg(owned, result, pins, symbol)
    execute.execute_kis_paper_portfolio_sell(**call)
    original = state(call).intent
    owned["client"].now += timedelta(minutes=10)
    for _ in range(2):
        execute.execute_kis_paper_portfolio_sell(**call)
    replay = execute.build_kis_paper_portfolio_sell_plan(
        binding=result.binding,
        states=_states(owned["state_root"], result.binding),
        **{
            **pins,
            "as_of": owned["client"].now,
            "reductions_by_symbol": None,
            "limits_by_symbol": None,
            "valid_until": None,
        },
    )
    assert replay.status == "replayed" and original in replay.intents
    assert owned["client"].submits == [original]


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_account_ref", "0" * 64),
        ("expected_basis_ref", "sha256:" + "0" * 64),
        ("expected_owner_refs", {}),
        ("expected_binding_ref", "sha256:" + "0" * 64),
        ("request_id", "synthetic-portfolio"),
        ("reductions_by_symbol", {"SPY": D(4), "TLT": D(0), "GLD": D(0)}),
        ("reductions_by_symbol", {"SPY": True, "TLT": D(0), "GLD": D(0)}),
        ("reductions_by_symbol", {"SPY": D(".5"), "TLT": D(0), "GLD": D(0)}),
        ("reductions_by_symbol", {"QQQ": D(1)}),
        ("limits_by_symbol", {"SPY": D("NaN"), "TLT": D(1), "GLD": D(1)}),
        ("valid_until", None),
    ],
)
def test_bad_fresh_terms_reject_before_persistence_or_network(owned, field, value):
    root = owned["state_root"]
    before = (root / budget.BUDGET_FILE).read_bytes()
    with pytest.raises((_RecoveryRequired, ValueError, TypeError)):
        reserve(owned, **{field: value})
    assert (root / budget.BUDGET_FILE).read_bytes() == before
    assert not owned["client"].submits and not owned["client"].limit_reads


@pytest.mark.parametrize("change", ["quantity", "limit", "expiry", "input", "bool"])
def test_retained_request_cannot_rescale_reprice_or_extend_expiry(owned, change):
    result, pins = reserve(owned)
    modified = copy.deepcopy(pins)
    if change == "quantity":
        modified["reductions_by_symbol"]["SPY"] = D(1)
    elif change == "limit":
        modified["limits_by_symbol"]["SPY"] += 1
    elif change == "expiry":
        modified["valid_until"] += timedelta(seconds=1)
    elif change == "input":
        modified["input_ref"] = "sha256:" + "f" * 64
    else:
        modified["reductions_by_symbol"]["TLT"] = True
    before = (owned["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired):
        execute.reserve_kis_paper_portfolio_sell_plan(
            state_root=owned["state_root"],
            repository_root=owned["repository_root"],
            artifact_root=owned["artifact_root"],
            **modified,
        )
    assert (owned["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert not owned["client"].submits


@pytest.mark.parametrize("unknown", [False, True])
def test_partial_unknown_sell_retains_cash_and_fresh_account_conflicts(owned, unknown):
    result, pins = reserve(owned)
    call = leg(owned, result, pins)
    owned["client"].partial, owned["client"].unknown = True, unknown
    execute.execute_kis_paper_portfolio_sell(**call)
    assert len(owned["client"].wire) == 1
    before = budget.project_budget(owned["state_root"], result.binding, as_of=owned["client"].now)
    assert before.remaining_gross_cash == (D(100) if unknown else D(180))
    assert close(call).status == "pending"
    execute.execute_kis_paper_portfolio_sell(**call)
    with pytest.raises(_RecoveryRequired, match="pre_submit_ownership_changed"):
        execute.execute_kis_paper_portfolio_sell(**leg(owned, result, pins, "TLT"))
    assert len(owned["client"].wire) == 1
    control = preview_arguments()
    buy = build_kis_paper_portfolio_plan(
        binding=result.binding,
        states=_states(owned["state_root"], result.binding),
        expected_account_ref=ACCOUNT,
        expected_basis_ref=pins["expected_basis_ref"],
        expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(result.binding)},
        expected_binding_ref="sha256:" + budget._digest(result.binding),
        request_id="fresh-buy-must-not-use-pending-sale",
        input_ref="sha256:" + "d" * 64,
        reads=replace(_reads(), account_ref=ACCOUNT, snapshot=owned["client"].snapshot()),
        weights_by_symbol=control["weights_by_symbol"],
        covariance_by_symbol=control["covariance_by_symbol"],
        target_as_of=control["target_as_of"],
        as_of=owned["client"].now,
        valid_until=owned["client"].now + timedelta(minutes=5),
    )
    assert buy.status != "prepared" and not buy.intents
    with pytest.raises(_RecoveryRequired, match="portfolio_pending_identity"):
        build(owned, request_id="portfolio-sell-another-session")


def _unknown_without_wire(call, intent):
    store = canary.KisPaperCanaryStateStore(call["state_root"] / (intent.run_id + ".json"))
    at = call["client"].now
    store.record_intent(intent, cancel_after_submit=False, now=at)
    store.transition(
        intent,
        expected=frozenset({"intent_recorded"}),
        phase="submission_started",
        reason_code="preview",
        now=at,
        submission_started_at=at,
    )
    store.transition(
        intent,
        expected=frozenset({"submission_started"}),
        phase="outcome_unknown",
        reason_code="submit_transport_unknown",
        now=at,
    )


@pytest.mark.parametrize("unknown", [False, True])
def test_distinct_instrument_sell_does_not_wait_for_unrelated_pending_owner(owned, unknown):
    pending, _ = reserve(
        owned,
        reductions_by_symbol={"SPY": D(0), "TLT": D(0), "GLD": D(1)},
        limits_by_symbol={"GLD": D(80)},
    )
    if unknown:
        _unknown_without_wire(owned, pending.intents[0])
    result, pins = reserve(
        owned,
        request_id="portfolio-sell-independent-tlt",
        reductions_by_symbol={"SPY": D(0), "TLT": D(1), "GLD": D(0)},
        limits_by_symbol={"TLT": D(80)},
    )
    outcome = execute.execute_kis_paper_portfolio_sell(**leg(owned, result, pins, "TLT"))
    assert outcome.phase == "submitted"
    assert [intent.symbol for intent in owned["client"].submits] == ["TLT"]
    assert not owned["client"].limit_reads


def test_same_plan_unrelated_unknown_leg_does_not_hold_matching_owned_sell(owned):
    result, pins = reserve(
        owned,
        reductions_by_symbol={"SPY": D(0), "TLT": D(1), "GLD": D(1)},
        limits_by_symbol={"TLT": D(80), "GLD": D(80)},
    )
    _unknown_without_wire(owned, next(i for i in result.intents if i.symbol == "GLD"))
    outcome = execute.execute_kis_paper_portfolio_sell(**leg(owned, result, pins, "TLT"))
    assert outcome.phase == "submitted"
    assert [intent.symbol for intent in owned["client"].submits] == ["TLT"]


def test_unrelated_unattempted_buys_do_not_hold_fully_observed_owned_sell(harness):
    execute.execute_kis_paper_portfolio_buy(**_leg(harness, "TLT"))
    proof = harness["proof"]
    reconcile_kis_paper_portfolio_plan(
        state_root=harness["state_root"],
        repository_root=harness["repository_root"],
        artifact_root=harness["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=proof.basis_ref,
        expected_owner_refs=dict(proof.owner_refs),
        request_id=proof.request_id,
        expected_plan_ref=proof.plan_ref,
        as_of=harness["client"].now,
    )
    client = SellClient(harness["client"])
    call = {**harness, "client": client, "clock": lambda: client.now}
    result, pins = reserve(
        call,
        reductions_by_symbol={"SPY": D(0), "TLT": D(1), "GLD": D(0)},
        limits_by_symbol={"TLT": D(80)},
    )
    outcome = execute.execute_kis_paper_portfolio_sell(**leg(call, result, pins, "TLT"))
    assert outcome.phase == "submitted"
    assert [intent.symbol for intent in client.submits] == ["TLT"]


def test_same_instrument_unknown_still_blocks_a_distinct_sell(owned):
    pending, _ = reserve(
        owned,
        reductions_by_symbol={"SPY": D(0), "TLT": D(1), "GLD": D(0)},
        limits_by_symbol={"TLT": D(80)},
    )
    _unknown_without_wire(owned, pending.intents[0])
    with pytest.raises(_RecoveryRequired, match="portfolio_pending_identity"):
        build(
            owned,
            request_id="portfolio-sell-conflicting-tlt",
            reductions_by_symbol={"SPY": D(0), "TLT": D(1), "GLD": D(0)},
            limits_by_symbol={"TLT": D(80)},
        )


@pytest.mark.parametrize("failure", ["foreign", "duplicate_position", "incomplete", "stale"])
def test_fresh_account_must_match_all_aggregate_owned_positions(owned, failure):
    result, pins = reserve(owned)
    setattr(owned["client"], failure, True)
    with pytest.raises((_RecoveryRequired, ValueError)):
        execute.execute_kis_paper_portfolio_sell(**leg(owned, result, pins))
    assert not owned["client"].wire
    assert state(leg(owned, result, pins)).submission_started_at is None


def test_baseline_spy_is_reconciled_in_aggregate_but_never_sold_as_portfolio(owned):
    binding = budget._load_binding(owned["state_root"])
    baseline = historical_state(30)
    budget._atomic_json(
        owned["state_root"] / (baseline.intent.run_id + ".json"), baseline.to_dict()
    )
    binding["orders"].append(
        dict(run_id=baseline.intent.run_id, intent_ref=baseline.intent.fingerprint, closed=True)
    )
    binding["terminal_evidence"][baseline.intent.run_id] = budget._terminal_payload(baseline)
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    budget._atomic_json(owned["state_root"] / budget.BUDGET_FILE, binding)
    owned["client"].orders[baseline.intent.run_id] = dict(
        intent=baseline.intent, id=baseline.broker_order_id, filled=D(1), remaining=D(0)
    )
    with pytest.raises(_RecoveryRequired, match="portfolio_owned_quantity_exceeded"):
        build(
            owned,
            reductions_by_symbol={"SPY": D(4), "TLT": D(0), "GLD": D(0)},
            limits_by_symbol={"SPY": D(80)},
        )
    result, pins = reserve(owned)
    execute.execute_kis_paper_portfolio_sell(**leg(owned, result, pins))
    call = leg(owned, result, pins)
    projected = execute._scope(owned["state_root"], call["proof"], owned["client"].now)[-1]
    spy = {s.owner_ref: s.quantity for s in projected.stocks_by_owner if s.symbol == "SPY"}
    assert spy == {"spy-baseline": D(1), "portfolio-spy": D(1)}


def test_sell_proof_cannot_use_buy_api_or_bare_guard_and_missing_state_never_reseeds(owned):
    result, pins = reserve(owned)
    call = leg(owned, result, pins)
    with pytest.raises(_RecoveryRequired, match="portfolio_side_mismatch"):
        execute.execute_kis_paper_portfolio_buy(**call)
    assert state(call) is None
    assert not execute.allows_kis_paper_portfolio_execution(
        call["state_root"],
        call["proof"].run_id,
        "SPY",
        call["proof"],
    )
    execute.execute_kis_paper_portfolio_sell(**call)
    (call["state_root"] / (call["proof"].run_id + ".json")).unlink()
    with pytest.raises(_RecoveryRequired, match="portfolio_materialized_state_missing"):
        execute.execute_kis_paper_portfolio_sell(**call)
    assert len(owned["client"].wire) == 1


def test_pre_reservation_crash_proposal_and_reserved_seed_restart_are_exact(owned, monkeypatch):
    proposal = build(owned)
    original = budget._atomic_json
    monkeypatch.setattr(
        budget, "_atomic_json", lambda *a, **kw: (_ for _ in ()).throw(OSError("synthetic"))
    )
    with pytest.raises(OSError):
        reserve(owned)
    monkeypatch.setattr(budget, "_atomic_json", original)
    result, pins = reserve(owned)
    assert result.intents == proposal.intents and result.plan_ref == proposal.plan_ref
    before = (owned["state_root"] / budget.BUDGET_FILE).read_bytes()
    replay = execute.reserve_kis_paper_portfolio_sell_plan(
        state_root=owned["state_root"],
        repository_root=owned["repository_root"],
        artifact_root=owned["artifact_root"],
        **pins,
    )
    assert replay.status == "replayed" and replay.intents == proposal.intents
    assert (owned["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert not owned["client"].wire


@pytest.mark.parametrize(
    "field",
    [
        "account_ref",
        "basis_ref",
        "owner_refs",
        "binding_ref",
        "parent_binding_ref",
        "input_ref",
        "plan_ref",
        "intent_ref",
    ],
)
def test_sell_independent_proof_pins_reject_before_materialization(owned, field):
    result, pins = reserve(owned)
    call = leg(owned, result, pins)
    wrong = (
        "0" * 64
        if field == "account_ref"
        else ()
        if field == "owner_refs"
        else "sha256:" + "0" * 64
    )
    call["proof"] = replace(call["proof"], **{field: wrong})
    before = (owned["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired):
        execute.execute_kis_paper_portfolio_sell(**call)
    assert not list(owned["state_root"].glob("bp-" + call["proof"].run_id[3:] + ".json"))
    assert (owned["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert not owned["client"].wire


@pytest.mark.parametrize(
    "field,value",
    [
        ("side", "buy"),
        ("symbol", "QQQ"),
        ("exchange", "NYSE"),
        ("price_contract_ref", "sha256:" + "0" * 64),
    ],
)
def test_retained_seed_rejects_wrong_side_symbol_venue_or_price_binding(owned, field, value):
    proposal = build(owned)
    binding = copy.deepcopy(proposal.binding)
    plan = binding["portfolio"]["plans"][-1]
    run = next(iter(plan["states"]))
    seed = canary.KisPaperCanaryState.from_dict(plan["states"][run])
    seed = replace(seed, intent=replace(seed.intent, **{field: value}))
    plan["states"][run] = seed.to_dict()
    with pytest.raises(_RecoveryRequired, match="portfolio_plan_invalid"):
        budget._portfolio_seed_states(binding)


def test_pending_sell_is_visible_to_existing_spy_qqq_writer_predicate(owned):
    result, pins = reserve(owned)
    assert budget._other_owned_intent_pending(owned["state_root"], result.binding, "bs-" + "f" * 64)
    assert budget._other_owned_intent_pending(owned["state_root"], result.binding, "bq-" + "f" * 64)
    for symbol in ("SPY", "TLT", "GLD"):
        assert budget.conflicts_with_budget_strategy(owned["state_root"], "foreign-canary", symbol)
        execute.execute_kis_paper_portfolio_sell(**leg(owned, result, pins, symbol))
    assert not budget._other_owned_intent_pending(
        owned["state_root"], result.binding, "bs-" + "f" * 64
    )


def test_terminal_sale_later_unavailable_retains_only_proven_observed_proceeds(owned):
    result, pins = reserve(owned)
    for symbol in ("SPY", "TLT", "GLD"):
        call = leg(owned, result, pins, symbol)
        execute.execute_kis_paper_portfolio_sell(**call)
    closed = close(call)
    owned["client"].history_unavailable = True
    owned["client"].now += timedelta(minutes=10)
    call["proof"] = replace(call["proof"], binding_ref="sha256:" + budget._digest(closed.binding))
    execute.execute_kis_paper_portfolio_sell(**call)
    projection = budget.project_budget(
        owned["state_root"], closed.binding, as_of=owned["client"].now
    )
    assert projection.remaining_gross_cash == D(420)
    assert close(call).status == "reconciled"
    assert len(owned["client"].wire) == 3
