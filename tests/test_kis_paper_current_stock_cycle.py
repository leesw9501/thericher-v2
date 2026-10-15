"""Synthetic native stock cycle; no actual credentials, account or network."""

from __future__ import annotations

import copy
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from test_current_nas_frozen_rank_target import AT, SESSION, _panel, _prepare
from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG
from test_kis_paper_portfolio_preview import _scope, _state
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.emergency import EmergencyStore, PaperExecutionControlStore
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_stock_canary import KisPaperStockCanaryClient
from thericher_v2.execution.kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
    KisPaperStockPreviewReads,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

D = Decimal
PIN = "sha256:" + "d" * 64
EXIT = replace(
    SESSION,
    open_ts=SESSION.open_ts + timedelta(days=3),
    close_ts=SESSION.close_ts + timedelta(days=3),
)


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("synthetic_cycle_cannot_use_wire_or_credentials")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", denied)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", denied)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config_from_environment", denied)


class NativeSyntheticStockClient(KisPaperStockCanaryClient):
    def __init__(self, h, instrument):
        super().__init__(config=CONFIG, transport=None, instrument=instrument)
        self.h = h

    def snapshot(self, *, exit_only=False):
        h, at = self.h, self.h["now"]
        positions, opens, inventory = [], [], {}
        for order in h["orders"].values():
            i = order["intent"]
            sign = D(1) if i.side == "buy" else D(-1)
            inventory[i.symbol] = inventory.get(i.symbol, D(0)) + sign * order["filled"]
            if order["remaining"]:
                opens.append(
                    KisPaperOpenOrder(
                        canary._redacted_open_order_reference(order["id"]),
                        i.symbol,
                        "NASD",
                        "USD",
                        i.side,
                        i.quantity,
                        order["filled"],
                        order["remaining"],
                        i.limit_price,
                        at,
                    )
                )
        if h["foreign"]:
            inventory[self.instrument.symbol] = inventory.get(self.instrument.symbol, D(0)) + 1
        for symbol, quantity in inventory.items():
            if quantity:
                positions.append(
                    KisPaperPosition(symbol, "NASD", "USD", quantity, D(10), quantity * D(10), at)
                )
        identity = KisPaperAccountIdentity(CONFIG.masked_account_identity, at)
        opened = KisPaperOpenOrdersSnapshot(tuple(opens), at, True)
        if exit_only:
            return KisPaperStockExitAccountSnapshot(identity, tuple(positions), opened, at)
        return KisPaperReadOnlySnapshot(
            identity,
            KisPaperCashSnapshot("USD", h["funds"], at),
            KisPaperOrderableFundsSnapshot(
                "USD", h["funds"], "NASD", self.instrument.symbol, D(10), at
            ),
            tuple(positions),
            opened,
            at,
        )

    def stock_preview_snapshot(self, *, expected_account_ref, clock):
        h, at = self.h, clock()
        quote_at = at - timedelta(seconds=121) if h["stale"] else at
        return KisPaperStockPreviewReads(
            expected_account_ref,
            self.instrument,
            self.snapshot(),
            KisPaperSpyLimitInput(D(10), 4, D(".0001"), quote_at, D(10), D(10)),
            D(10),
            KisPaperCashSnapshot("USD", h["funds"], at),
            KisPaperOrderableFundsSnapshot(
                "USD", h["funds"], "NASD", self.instrument.symbol, D(10), at
            ),
            at,
            at,
            0.0,
        )

    def stock_exit_snapshot(self, *, expected_account_ref, clock):
        at = clock()
        return KisPaperStockExitReads(
            expected_account_ref,
            self.instrument,
            self.snapshot(exit_only=True),
            KisPaperSpyLimitInput(D(10), 4, D(".0001"), at, D(10), D(10)),
            at,
            at,
            0.0,
        )

    def orderable_funds_at_limit(self, *, symbol, exchange, limit_price):
        h, at = self.h, self.h["now"]
        h["funds_reads"] += 1
        funds = D(0) if h["late_funds"] else h["funds"]
        return (
            KisPaperCashSnapshot("USD", funds, at),
            KisPaperOrderableFundsSnapshot("USD", funds, exchange, symbol, limit_price, at),
        )

    def submit_limit(self, intent, **_kwargs):
        h = self.h
        state = canary.KisPaperCanaryStateStore(h["root"] / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started" and state.intent == intent
        record = budget._read_json(h["root"] / cycle.POINTER)
        assert record["pending"]["plan_ref"] in record["owners"][intent.symbol]["plans"].values()
        h["submits"].append(intent)
        filled = D(1) if h["partial"] else intent.quantity
        h["orders"][intent.run_id] = dict(
            intent=intent,
            id=str(100 + len(h["submits"])),
            filled=filled,
            remaining=intent.quantity - filled,
            cancelled=False,
        )
        if h["unknown"]:
            raise canary.KisPaperCanaryError("submit_transport_unknown")
        return True, h["orders"][intent.run_id]["id"]

    def reconcile(self, state, *, now):
        h = self.h
        order = h["orders"].get(state.intent.run_id)
        known = order is not None and order["id"] == state.broker_order_id
        observation = None
        if known:
            fill = KisPaperCumulativeFill(
                fill_identity_ref(
                    raw_order_id=order["id"],
                    order_at=state.submission_started_at,
                    symbol=state.intent.symbol,
                    exchange="NASD",
                    side=state.intent.side,
                    quantity=state.intent.quantity,
                ),
                state.intent.quantity,
                order["filled"],
                order["filled"] * state.intent.limit_price,
                now,
                order["remaining"],
            )
            zero_cancel = bool(order["cancelled"] and order["filled"] == 0)
            observation = KisPaperExecutionObservation(
                2 if zero_cancel else 1, True, "available", fill, now, zero_cancel
            )
        return canary.KisPaperCanaryReconciliation(
            snapshot=self.snapshot(exit_only=state.intent.side == "sell"),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["remaining"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )

    def cancel_order(self, intent, *, broker_order_id):
        h = self.h
        state = canary.KisPaperCanaryStateStore(h["root"] / (intent.run_id + ".json")).read()
        assert state.phase == "cancel_started" and state.intent == intent
        h["cancels"].append(intent)
        if h["cancel_unknown"]:
            raise canary.KisPaperCanaryError("cancel_transport_unknown")
        h["orders"][intent.run_id].update(remaining=D(0), cancelled=True)
        return True


@pytest.fixture
def h(tmp_path):
    root = tmp_path / "p"
    historical = _scope(_state(1), _state(2, symbol="QQQ", pending=True))
    binding = historical["binding"]
    binding.update(
        version=3, portfolio=dict(owner_refs=dict.fromkeys(("SPY", "TLT", "GLD")), plans=[])
    )
    binding["account_ref"] = ACCOUNT
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    for owner, _ in budget._owners(binding):
        if owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    for state in historical["states"].values():
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
    data = cycle.CurrentStockCycleInput(
        _prepare(valid_until=SESSION.close_ts), SESSION, EXIT, PIN, "sha256:" + "e" * 64
    )
    result = dict(
        root=root,
        now=AT,
        orders={},
        submits=[],
        cancels=[],
        funds=D(1000),
        stale=False,
        partial=False,
        unknown=False,
        cancel_unknown=False,
        late_funds=False,
        foreign=False,
        funds_reads=0,
        loads=0,
        factories=0,
        data=data,
        initial=copy.deepcopy(binding),
    )

    def loader():
        result["loads"] += 1
        return result["data"]

    def factory(instrument):
        result["factories"] += 1
        return NativeSyntheticStockClient(result, instrument)

    result["call"] = dict(
        state_root=root,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "control.json",
        expected_account_ref=ACCOUNT,
        target_loader=loader,
        client_factory=factory,
        clock=lambda: result["now"],
        execute=True,
    )
    return result


def run(h, **changes):
    return cycle.run_kis_paper_current_stock_cycle(**(h["call"] | changes))


def record(h):
    return budget._read_json(h["root"] / cycle.POINTER)


def test_default_inert_before_callbacks_or_state(h):
    assert run(h, execute=False).safe_payload() == dict(
        status="inert", reason="execution_not_requested", leg_count=0
    )
    assert h["loads"] == h["factories"] == 0 and record(h) is None


def test_zero_quote_skips_only_unreserved_target_and_restart_continues_fixed_basket(h, monkeypatch):
    first, second = h["data"].targets[:2]
    original = NativeSyntheticStockClient.stock_preview_snapshot
    before = (h["root"] / budget.BUDGET_FILE).read_bytes()

    def preview(client, **arguments):
        if client.instrument.symbol == first.proposal.symbol:
            raise kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")
        return original(client, **arguments)

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", preview)
    assert run(h).safe_payload() == dict(
        status="no_intent", reason="cycle_target_quote_unavailable", leg_count=0
    )
    saved = record(h)
    assert saved["active"]["entries_done"] == [first.proposal.symbol]
    assert cycle._unpack(saved["active"]["targets"]) == h["data"].targets
    assert saved["pending"] is None and saved["owners"] == {}
    assert (h["root"] / budget.BUDGET_FILE).read_bytes() == before
    assert h["submits"] == []

    run(h, target_loader=lambda: pytest.fail("active_identity_must_not_reload_targets"))
    assert len(h["submits"]) == 1
    assert h["submits"][0].symbol == second.proposal.symbol
    assert record(h)["active"]["input_ref"] == h["data"].input_ref


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("quote_timestamp_invalid", "cycle_quote_timestamp_invalid"),
        ("quote_timestamp_stale", "cycle_quote_timestamp_stale"),
        ("quote_tick_invalid", "cycle_quote_tick_invalid"),
        ("quote_bid_ask_invalid", "cycle_quote_bid_ask_invalid"),
        ("auth_rejected", "cycle_readonly_snapshot_unavailable"),
        ("not_a_public_error_sensitive_marker", "cycle_readonly_snapshot_unavailable"),
    ],
)
def test_other_readonly_failures_do_not_skip_or_expose_values(h, monkeypatch, code, reason):
    def denied(*_args, **_kwargs):
        raise kis_readonly.KisPaperReadOnlyError(code)

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", denied)
    before = (h["root"] / budget.BUDGET_FILE).read_bytes()
    result = run(h)
    assert result.safe_payload() == dict(status="unavailable", reason=reason, leg_count=0)
    assert record(h)["active"]["entries_done"] == []
    assert record(h)["pending"] is None and h["submits"] == []
    assert (h["root"] / budget.BUDGET_FILE).read_bytes() == before
    assert "sensitive_marker" not in repr(result.safe_payload())


def test_pending_unknown_is_not_skipped_by_unavailable_quote(h, monkeypatch):
    h["unknown"] = True
    assert run(h).status == "pending"
    pending = copy.deepcopy(record(h)["pending"])
    before = (h["root"] / budget.BUDGET_FILE).read_bytes()

    def unavailable(*_args, **_kwargs):
        raise kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(NativeSyntheticStockClient, "reconcile", unavailable)
    result = run(h, target_loader=lambda: pytest.fail("pending_must_not_load_new_targets"))
    assert result.status == "unavailable" and result.reason == "cycle_quote_timestamp_unavailable"
    assert record(h)["pending"]["arguments"] == pending["arguments"]
    assert record(h)["active"]["entries_done"] == []
    assert (h["root"] / budget.BUDGET_FILE).read_bytes() == before
    assert len(h["submits"]) == 1


def test_sell_quote_unavailable_never_retires_owned_inventory(h, monkeypatch):
    for _ in range(10):
        run(h)
    assert len(h["submits"]) == 10
    before = copy.deepcopy(record(h))
    h["now"] = EXIT.open_ts + timedelta(seconds=1)

    def unavailable(*_args, **_kwargs):
        raise kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_exit_snapshot", unavailable)
    result = run(h)
    assert result.status == "unavailable" and result.reason == "cycle_quote_timestamp_unavailable"
    assert record(h)["active"] == before["active"]
    assert record(h)["owners"] == before["owners"]
    assert len(h["submits"]) == 10


def test_two_sessions_ten_frozen_entries_then_only_owned_exits(h):
    for _ in range(10):
        result = run(h)
        assert result.status == "advanced", result.safe_payload()
        assert result.leg_count == 1
    assert len(h["submits"]) == 10 and h["loads"] == 1
    assert {i.quantity for i in h["submits"]} == {D(5)}
    assert run(h).status == "hold"
    h["now"] = EXIT.close_ts - timedelta(minutes=4)
    for _ in range(10):
        result = run(h)
        assert result.status == "advanced", result.safe_payload()
    assert len(h["submits"]) == 20 and h["loads"] == 1
    assert all(i.side == "sell" and i.quantity == 5 for i in h["submits"][10:])
    assert run(h).status == "complete"
    assert run(h).safe_payload()["reason"] == "already_completed"
    current = budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert current[key] == h["initial"][key]


@pytest.mark.parametrize("stage", ["before_reserve", "after_reserve", "after_materialize"])
def test_crash_journal_replays_same_native_request_without_data(h, monkeypatch, stage):
    if stage == "after_materialize":
        original = canary.KisPaperCanaryStateStore.record_intent

        def crash(self, *args, **kwargs):
            original(self, *args, **kwargs)
            raise RuntimeError("invented_crash")

        owner, name = canary.KisPaperCanaryStateStore, "record_intent"
    else:
        original = cycle.entries.reserve_kis_paper_stock_plan

        def crash(**args):
            if stage == "after_reserve":
                original(**args)
            raise RuntimeError("invented_crash")

        owner, name = cycle.entries, "reserve_kis_paper_stock_plan"
    with monkeypatch.context() as patch:
        patch.setattr(owner, name, crash)
        assert run(h).status == "unavailable"
    pending = copy.deepcopy(record(h)["pending"])
    result = run(h, target_loader=lambda: pytest.fail("recovery_must_not_load_data"))
    assert result.status == "advanced", result.safe_payload()
    assert len(h["submits"]) == 1
    intent = h["submits"][0]
    args = cycle._unpack(pending["arguments"])
    assert intent.created_at == args["as_of"] and intent.valid_until == args["valid_until"]
    assert intent.limit_price == args["reads"].buy_limit


def test_expired_reserved_seed_is_locally_terminal_without_client_or_new_data(h, monkeypatch):
    original = cycle.entries.reserve_kis_paper_stock_plan

    def crash(**args):
        original(**args)
        raise RuntimeError("invented_crash")

    with monkeypatch.context() as patch:
        patch.setattr(cycle.entries, "reserve_kis_paper_stock_plan", crash)
        run(h)
    pending = copy.deepcopy(record(h)["pending"])
    h["now"] += timedelta(days=1)
    result = run(
        h,
        target_loader=lambda: pytest.fail("no_data"),
        client_factory=lambda _: pytest.fail("expiry_needs_no_client"),
    )
    assert result.status == "advanced", result.safe_payload()
    binding = budget._load_binding(h["root"])
    plan = next(p for e in binding["stocks"].values() for p in e["plans"])
    seed = next(iter(plan["states"].values()))
    assert (
        canary.KisPaperCanaryState.from_dict(seed).intent.valid_until
        == cycle._unpack(pending["arguments"])["valid_until"]
    )
    assert h["submits"] == []


def test_unknown_submit_retains_request_reservation_and_does_not_reload_or_resubmit(h):
    h["unknown"] = True
    first = run(h)
    assert first.status == "pending", first.safe_payload()
    pending = copy.deepcopy(record(h)["pending"])
    h["now"] += timedelta(days=1)
    for _ in range(2):
        assert run(h, target_loader=lambda: pytest.fail("no_data")).status == "pending"
    assert len(h["submits"]) == 1
    assert record(h)["pending"]["arguments"] == pending["arguments"]
    binding = budget._load_binding(h["root"])
    # The expired unrelated QQQ reservation still consumes 100 of the SAME bank.
    assert cycle._projection(h["root"], binding, h["now"])[-1].reserved_buys == 150


def test_partial_unknown_cancel_stays_pending_then_exit_uses_only_filled_quantity(h):
    h["partial"] = True
    assert run(h).status == "pending"
    original = h["submits"][0]
    h["now"] += timedelta(minutes=6)
    h["cancel_unknown"] = True
    assert run(h, target_loader=lambda: pytest.fail("no_data")).status == "pending"
    assert len(h["cancels"]) == 1 and len(h["submits"]) == 1
    assert record(h)["pending"] is not None
    h["cancel_unknown"] = False
    # An unknown cancel is not retry permission. Later exact broker evidence
    # establishes the original request's terminal partial fill.
    h["orders"][original.run_id].update(remaining=D(0), cancelled=True)
    assert run(h).status == "advanced"
    assert len(h["submits"]) == 1 and h["submits"][0] == original
    h["now"] = EXIT.close_ts - timedelta(minutes=4)
    h["partial"] = False
    # Canonical terminal evidence closes only the residual; sell only the owned fill.
    result = run(h)
    assert result.status == "advanced" and result.leg_count == 1 and len(h["submits"]) == 2
    assert h["submits"][-1].side == "sell" and h["submits"][-1].quantity == 1
    assert record(h)["pending"] is None
    binding = budget._load_binding(h["root"])
    projection = cycle._projection(h["root"], binding, h["now"])[-1]
    owned = next(s for s in projection.stocks_by_instrument if s.symbol == original.symbol)
    assert owned.quantity == 0
    # The unknown QQQ reservation and conservative partial-BUY debit are untouched.
    assert projection.reserved_buys == 140


@pytest.mark.parametrize("fault", ["stale", "foreign", "late_funds"])
def test_native_quote_inventory_and_call_time_funds_remain_authoritative(h, fault):
    h[fault] = True
    result = run(h)
    assert result.status in {"no_intent", "unavailable"}
    assert h["submits"] == []


@pytest.mark.parametrize("control", ["emergency", "pause_buy"])
def test_native_emergency_or_pause_never_submits(h, control):
    if control == "emergency":
        EmergencyStore(h["call"]["emergency_state_path"]).stop_new_orders("synthetic")
    else:
        PaperExecutionControlStore(h["call"]["execution_control_path"]).set_pause_buys(True)
    result = run(h)
    assert result.status == "pending", result.safe_payload()
    assert h["submits"] == []


def test_known_foreign_same_stock_native_registration_rejected_without_adoption(h):
    assert run(h).status == "advanced"
    original = (h["root"] / budget.BUDGET_FILE).read_bytes()
    (h["root"] / cycle.POINTER).unlink()
    result = run(h)
    assert result.reason == "cycle_foreign_stock_registration"
    assert (h["root"] / budget.BUDGET_FILE).read_bytes() == original
    assert len(h["submits"]) == 1


def test_missing_targets_wrong_session_or_nonfixed_weight_rejected_without_client(h):
    value = h["data"]
    for invalid in (
        replace(value, targets=value.targets[:-1]),
        replace(value, entry_session=EXIT),
        replace(
            value,
            targets=(
                replace(
                    value.targets[0],
                    proposal=replace(value.targets[0].proposal, target_exposure=D(".01")),
                ),
            )
            + value.targets[1:],
        ),
    ):
        h["data"] = invalid
        assert run(h).status == "unavailable"
    assert h["factories"] == 0


def test_source_safe_payload_never_echoes_arbitrary_callback_or_native_text():
    result = cycle.CurrentStockCycleOutcome("private-symbol", "sha256:private", True)
    assert result.safe_payload() == dict(
        status="unavailable", reason="native_recovery_required", leg_count=0
    )


def test_later_foreign_registration_for_a_frozen_selected_name_is_rejected(h):
    assert run(h).status == "advanced"
    target = h["data"].targets[1]
    other = replace(h["data"], targets=(target,) + h["data"].targets[2:] + (h["data"].targets[0],))
    # Use the native builder exactly as another owner would, without our policy map.
    instrument = cycle.KisPaperStockInstrument(
        target.proposal.symbol, target.receipt.instrument_binding_ref
    )
    binding = budget._load_binding(h["root"])
    reads = NativeSyntheticStockClient(h, instrument).stock_preview_snapshot(
        expected_account_ref=ACCOUNT, clock=h["call"]["clock"]
    )
    result = cycle.entries.reserve_kis_paper_stock_plan(
        state_root=h["root"],
        repository_root=h["call"]["repository_root"],
        artifact_root=h["call"]["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=cycle._refs(binding),
        expected_binding_ref="sha256:" + budget._digest(binding),
        request_id="foreign-policy-request",
        input_ref=other.input_ref,
        instrument=instrument,
        proposal=target.proposal,
        receipt=target.receipt,
        reads=reads,
        as_of=h["now"],
        valid_until=h["now"] + timedelta(minutes=5),
    )
    assert result.status == "reserved"
    assert run(h).reason == "cycle_foreign_stock_registration"
    assert len(h["submits"]) == 1


def test_wrong_account_factory_fails_before_any_native_preview(h, monkeypatch):
    def factory(instrument):
        client = NativeSyntheticStockClient(h, instrument)
        client._config = replace(CONFIG, account_number="87654321")
        return client

    with monkeypatch.context() as patch:
        patch.setattr(
            NativeSyntheticStockClient,
            "stock_preview_snapshot",
            lambda *_a, **_k: pytest.fail("wrong_account_must_not_read"),
        )
        assert run(h, client_factory=factory).reason == "cycle_account_changed"
    assert h["submits"] == []


def test_risk_rejection_does_not_retry_or_replace_frozen_basket(h):
    h["funds"] = D(0)
    assert run(h).status == "no_intent"
    assert record(h)["active"]["entries_done"] == [h["data"].targets[0].proposal.symbol]
    h["funds"] = D(1000)
    assert run(h, target_loader=lambda: pytest.fail("basket_must_stay_frozen")).status == "advanced"
    assert h["submits"][0].symbol == h["data"].targets[1].proposal.symbol


def test_outside_exit_window_retains_owned_inventory_without_rollover_or_force(h):
    assert run(h).status == "advanced"
    h["now"] = EXIT.close_ts + timedelta(seconds=1)
    result = run(h, target_loader=lambda: pytest.fail("no_rollover"))
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert record(h)["active"] is not None and len(h["submits"]) == 1


def test_first_fifth_session_open_can_start_owned_exit_without_data_reload(h):
    assert run(h).status == "advanced"
    h["now"] = EXIT.open_ts - timedelta(microseconds=1)
    assert run(h, target_loader=lambda: pytest.fail("no_data")).status == "hold"
    h["now"] = EXIT.open_ts
    result = run(h, target_loader=lambda: pytest.fail("no_data"))
    assert result.status == "advanced", result.safe_payload()
    assert len(h["submits"]) == 2 and h["submits"][-1].side == "sell"
    assert h["submits"][-1].created_at == EXIT.open_ts
    assert h["submits"][-1].valid_until == EXIT.open_ts + timedelta(minutes=5)


def test_missed_fifth_window_uses_next_official_session_only(h):
    assert run(h).status == "advanced"

    def denied():
        pytest.fail("owned_exit_must_not_reload_data")

    h["now"] = EXIT.close_ts + timedelta(seconds=1)
    assert run(h, target_loader=denied).status == "hold"
    next_session = cycle.us_equity_2026_session((EXIT.open_ts + timedelta(days=1)).date()).window
    h["now"] = next_session.open_ts - timedelta(microseconds=1)
    assert run(h, target_loader=denied).status == "hold"
    h["now"] = next_session.open_ts
    assert run(h, target_loader=denied).status == "advanced"
    sell = h["submits"][-1]
    assert sell.side == "sell" and sell.quantity == 5
    assert sell.created_at == next_session.open_ts and sell.valid_until <= next_session.close_ts
    assert h["loads"] == 1


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 10, 17, 15, tzinfo=UTC),
        datetime(2026, 10, 18, 15, tzinfo=UTC),
        datetime(2026, 11, 26, 15, tzinfo=UTC),
    ],
)
def test_weekends_and_official_closed_days_hold_owned_inventory(h, at):
    assert run(h).status == "advanced"
    h["now"] = at
    result = run(
        h,
        target_loader=lambda: pytest.fail("no_data"),
        client_factory=lambda _: pytest.fail("closed_day_must_not_create_client"),
    )
    assert result.status == "hold" and record(h)["active"] is not None
    assert len(h["submits"]) == 1


def test_partial_sell_terminal_then_later_session_exits_only_remaining_owned(h):
    assert run(h).status == "advanced"
    h["now"] = EXIT.open_ts
    h["partial"] = True
    assert run(h).status == "pending"
    first = h["submits"][-1]
    pending = copy.deepcopy(record(h)["pending"])
    assert first.side == "sell" and first.quantity == 5
    assert cycle._unpack(pending["session"]) == EXIT
    # A subsequent exact terminal partial observation closes only this request.
    h["orders"][first.run_id].update(remaining=D(0), cancelled=True)
    h["now"] = EXIT.close_ts + timedelta(seconds=1)
    assert run(h, target_loader=lambda: pytest.fail("no_data")).status == "advanced"
    assert len(h["submits"]) == 2 and record(h)["pending"] is None
    assert run(h).status == "hold"
    h["partial"] = False
    h["now"] = EXIT.open_ts + timedelta(days=1)
    assert run(h, target_loader=lambda: pytest.fail("no_data")).status == "advanced"
    second = h["submits"][-1]
    assert second.side == "sell" and second.quantity == 4
    assert second.run_id != first.run_id and second.valid_until > first.valid_until
    assert (
        second.created_at == h["now"]
        and first.valid_until == cycle._unpack(pending["arguments"])["valid_until"]
    )


def test_expired_unknown_during_later_eligible_session_never_renews_identity(h):
    h["unknown"] = True
    assert run(h).status == "pending"
    pending = copy.deepcopy(record(h)["pending"])
    h["now"] = EXIT.open_ts + timedelta(days=1)
    for _ in range(2):
        assert run(h, target_loader=lambda: pytest.fail("pending_before_data")).status == "pending"
    assert len(h["submits"]) == 1
    assert record(h)["pending"]["arguments"] == pending["arguments"]
    assert record(h)["pending"]["session"] == pending["session"]


def test_materialized_unattempted_expiry_transitions_native_state_and_closes(h, monkeypatch):
    original = canary.KisPaperCanaryStateStore.record_intent

    def crash(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("invented_after_materialization")

    with monkeypatch.context() as patch:
        patch.setattr(canary.KisPaperCanaryStateStore, "record_intent", crash)
        assert run(h).status == "unavailable"
    pending = copy.deepcopy(record(h)["pending"])
    seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
    h["now"] = SESSION.close_ts + timedelta(seconds=1)

    def no_data():
        pytest.fail("expiry_must_not_load_data")

    def no_client(_):
        pytest.fail("expiry_must_not_create_client")

    assert run(h, target_loader=no_data, client_factory=no_client).status == "advanced"
    current = canary.KisPaperCanaryStateStore(h["root"] / (seed.intent.run_id + ".json")).read()
    assert current.intent == seed.intent and current.reason_code == "intent_expired"
    assert current.updated_at >= current.intent.valid_until and record(h)["pending"] is None
    assert run(h, target_loader=no_data, client_factory=no_client).status == "hold"
    assert h["submits"] == []


def _reconcile_unrelated_qqq(h):
    binding = budget._load_binding(h["root"])
    run_id = binding["qqq"]["orders"][0]["run_id"]
    store = canary.KisPaperCanaryStateStore(h["root"] / (run_id + ".json"))
    state = store.read()
    state = store.transition(
        state.intent,
        expected=frozenset({"intent_recorded"}),
        phase="intent_recorded",
        reason_code="intent_expired",
        now=h["now"],
    )
    binding["terminal_evidence"][run_id] = budget._terminal_payload(state)
    budget._atomic_json(h["root"] / budget.BUDGET_FILE, binding)
    return (h["root"] / budget.BUDGET_FILE).read_bytes()


@pytest.mark.parametrize("expired", [False, True])
def test_changed_parent_never_reserved_leg_retires_only_journal_without_rebind(
    h, monkeypatch, expired
):
    with monkeypatch.context() as patch:
        patch.setattr(
            cycle.entries,
            "reserve_kis_paper_stock_plan",
            lambda **_k: (_ for _ in ()).throw(RuntimeError("before_reserve")),
        )
        assert run(h).status == "unavailable"
    pending = copy.deepcopy(record(h)["pending"])
    if expired:
        h["now"] += timedelta(minutes=6)
    canonical = _reconcile_unrelated_qqq(h)
    result = run(
        h,
        target_loader=lambda: pytest.fail("no_data"),
        client_factory=lambda _: pytest.fail("retirement_needs_no_client"),
    )
    assert result.status == "no_intent" and result.reason == "cycle_never_reserved_retired"
    retained = record(h)
    assert retained["pending"] is None and retained["owners"] == {}
    assert retained["retired"][0]["pending"] == pending
    assert (h["root"] / budget.BUDGET_FILE).read_bytes() == canonical
    assert h["submits"] == []


def test_physically_present_state_prevents_never_reserved_retirement(h, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(
            cycle.entries,
            "reserve_kis_paper_stock_plan",
            lambda **_k: (_ for _ in ()).throw(RuntimeError("before_reserve")),
        )
        run(h)
    pending = copy.deepcopy(record(h)["pending"])
    seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
    _reconcile_unrelated_qqq(h)
    budget._atomic_json(h["root"] / (seed.intent.run_id + ".json"), pending["seed"])
    result = run(
        h,
        target_loader=lambda: pytest.fail("no_data"),
        client_factory=lambda _: pytest.fail("no_client"),
    )
    assert result.status == "unavailable" and record(h)["pending"] == pending


def test_real_partial_reservation_survives_unrelated_parent_change(h):
    h["partial"] = True
    assert run(h).status == "pending"
    pending = copy.deepcopy(record(h)["pending"])
    _reconcile_unrelated_qqq(h)
    h["now"] += timedelta(minutes=6)
    h["cancel_unknown"] = True
    assert run(h, target_loader=lambda: pytest.fail("no_data")).status == "pending"
    assert record(h)["pending"]["arguments"] == pending["arguments"]
    assert not record(h).get("retired") and len(h["submits"]) == 1


def test_retirement_tombstone_rejects_restored_state_without_data_or_client(h, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(
            cycle.entries,
            "reserve_kis_paper_stock_plan",
            lambda **_k: (_ for _ in ()).throw(RuntimeError("before_reserve")),
        )
        run(h)
    pending = copy.deepcopy(record(h)["pending"])
    _reconcile_unrelated_qqq(h)
    assert run(h).reason == "cycle_never_reserved_retired"
    seed = canary.KisPaperCanaryState.from_dict(pending["seed"])
    budget._atomic_json(h["root"] / (seed.intent.run_id + ".json"), pending["seed"])
    result = run(
        h,
        target_loader=lambda: pytest.fail("no_data"),
        client_factory=lambda _: pytest.fail("no_client"),
    )
    # The unchanged native book loader rejects unbound stock state even earlier
    # than the tombstone checker; neither guard may adopt or revive it.
    assert result.status == "unavailable" and result.reason == "native_recovery_required"
    assert record(h)["retired"][0]["pending"] == pending and h["submits"] == []


def test_local_official_calendar_dst_early_close_and_scope_fail_closed():
    before_dst_open = datetime(2026, 11, 2, 14, 29, tzinfo=UTC)
    assert cycle._current_exit_session(before_dst_open, EXIT) is None
    after_dst_open = before_dst_open + timedelta(minutes=1)
    assert cycle._current_exit_session(after_dst_open, EXIT).open_ts == after_dst_open
    early = cycle._current_exit_session(datetime(2026, 11, 27, 17, 59, tzinfo=UTC), EXIT)
    assert early.close_ts == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert cycle._current_exit_session(early.close_ts, EXIT) is None
    with pytest.raises(ValueError):
        cycle._current_exit_session(datetime(2027, 1, 4, 15, tzinfo=UTC), EXIT)


def _finish_one_owned_stock(h):
    assert run(h).status == "advanced"
    h["now"] = EXIT.open_ts
    assert run(h).status == "advanced"
    assert run(h).status == "complete" and record(h)["active"] is None


def test_completed_identity_hints_skip_expired_loader_and_client(h):
    _finish_one_owned_stock(h)
    h["now"] = EXIT.close_ts + timedelta(days=2)

    def expired_loader():
        pytest.fail("expired_targets_must_not_be_loaded_after_flat")

    def no_client(_):
        pytest.fail("completed_cycle_needs_no_client")

    result = run(
        h,
        target_loader=expired_loader,
        client_factory=no_client,
        expected_input_ref=h["data"].input_ref,
        expected_policy_ref=h["data"].policy_ref,
    )
    assert result.safe_payload() == dict(status="complete", reason="already_completed", leg_count=0)


def test_different_hint_loads_and_cannot_claim_old_completed_input(h):
    _finish_one_owned_stock(h)
    loads = h["loads"]
    result = run(
        h, expected_input_ref="sha256:" + "f" * 64, expected_policy_ref=h["data"].policy_ref
    )
    assert result.status == "unavailable" and result.reason == "cycle_input_binding_mismatch"
    assert h["loads"] == loads + 1 and len(h["submits"]) == 2


def test_future_hint_loads_new_input_and_preserves_normal_entry_validation(h):
    _finish_one_owned_stock(h)
    delta = timedelta(days=4)
    panel = _panel()
    metadata = replace(
        panel.metadata,
        **{
            name: getattr(panel.metadata, name) + delta
            for name in (
                "feature_window_end",
                "data_first_available_at",
                "input_asof",
                "inference_completed_at",
                "score_first_available_at",
            )
        },
    )
    session = replace(SESSION, open_ts=SESSION.open_ts + delta, close_ts=SESSION.close_ts + delta)
    h["now"] = AT + delta
    targets = _prepare(
        replace(panel, metadata=metadata),
        decided_at=h["now"],
        valid_until=session.close_ts,
        intended_session=session,
        latest_completed_close=metadata.feature_window_end,
    )
    h["data"] = replace(
        h["data"],
        targets=targets,
        entry_session=session,
        exit_session=replace(EXIT, open_ts=EXIT.open_ts + delta, close_ts=EXIT.close_ts + delta),
        input_ref="sha256:" + "f" * 64,
    )
    loads = h["loads"]
    result = run(
        h, expected_input_ref=h["data"].input_ref, expected_policy_ref=h["data"].policy_ref
    )
    assert result.status == "advanced", result.safe_payload()
    assert h["loads"] == loads + 1 and len(h["submits"]) == 3
    assert h["submits"][-1].side == "buy" and h["submits"][-1].created_at == h["now"]


def test_pending_recovery_ignores_future_hints_and_preserves_original_request(h):
    h["unknown"] = True
    assert run(h).status == "pending"
    pending = copy.deepcopy(record(h)["pending"])
    h["now"] = EXIT.open_ts + timedelta(days=1)
    result = run(
        h,
        expected_input_ref="sha256:" + "f" * 64,
        expected_policy_ref="sha256:" + "a" * 64,
        target_loader=lambda: pytest.fail("pending_before_future_data"),
    )
    assert result.status == "pending" and len(h["submits"]) == 1
    assert record(h)["pending"]["arguments"] == pending["arguments"]


def test_completed_hint_replays_whole_book_and_rejects_late_contradiction(h):
    _finish_one_owned_stock(h)
    binding = budget._load_binding(h["root"])
    run_id = binding["qqq"]["orders"][0]["run_id"]
    store = canary.KisPaperCanaryStateStore(h["root"] / (run_id + ".json"))
    state = store.read()
    store.transition(
        state.intent,
        expected=frozenset({"intent_recorded"}),
        phase="intent_recorded",
        reason_code="intent_expired",
        now=h["now"] + timedelta(days=1),
    )
    result = run(
        h,
        expected_input_ref=h["data"].input_ref,
        expected_policy_ref=h["data"].policy_ref,
        target_loader=lambda: pytest.fail("whole_book_validation_before_loader"),
        client_factory=lambda _: pytest.fail("no_client"),
    )
    assert result.status == "unavailable" and len(h["submits"]) == 2
