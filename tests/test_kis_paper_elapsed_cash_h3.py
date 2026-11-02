"""Native CASH-H3 lifecycle on invented state and clients; actual wire forbidden."""

import copy
import socket
import subprocess
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_weight_cycle as old_weights
import test_model_paper_profile as model
import test_paper_account_session as account
from test_kis_paper_current_stock_cycle_worker import CONFIG, w
from test_model_paper_elapsed_cash_h3 import point, stock_rows
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as core

PROFILE = core.StockCycleProfile.MODEL_WEIGHTS_NAS_CASH_ELAPSED_H3


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)

    def deny(*args, **kwargs):
        pytest.fail("cash_h3_actual_effect_forbidden")

    for owner, name in (
        (socket.socket, "connect"),
        (urllib.request.OpenerDirector, "open"),
        (w.readonly, "load_kis_paper_config"),
        (subprocess, "Popen"),
    ):
        monkeypatch.setattr(owner, name, deny)


@pytest.fixture
def h(tmp_path):
    state = old_weights.h.__wrapped__(tmp_path)
    old_weights.bind(state, point(), PROFILE)
    state["now"] = state["data"].entry_session.close_ts - timedelta(minutes=4)
    state["configured"] = []
    state["call"]["configure_cash_h3"] = lambda value, side, session: state["configured"].append(
        side
    )
    return state


def forbidden(*args, **kwargs):
    pytest.fail("retained_request_must_not_load_cash_or_replace_input")


@pytest.mark.parametrize("seconds", [-1, 300, 301])
def test_before_or_after_entry_band_has_zero_buy_and_no_reservation(h, seconds):
    h["now"] = h["data"].entry_session.close_ts - timedelta(minutes=5) + timedelta(seconds=seconds)
    before = old_weights.bank_bytes(h)
    result = old_weights.run(h)
    assert result.status == "unavailable" and result.leg_count == 0
    assert h["submits"] == [] and h["factories"] == 0
    assert old_weights.bank_bytes(h) == before and old_weights.record(h) is None


def test_fresh_allcash_or_unsupported_only_has_no_client_intent_or_reservation(h):
    for rows in (
        stock_rows(),
        stock_rows([*([Decimal(0)] * 8), Decimal(".5"), *([Decimal(0)] * 8)]),
    ):
        value = point(rows)
        old_weights.bind(h, value, PROFILE)
        h["now"] = value.entry_session.close_ts - timedelta(minutes=4)
        before = old_weights.bank_bytes(h)
        assert old_weights.run(h, client_factory=forbidden).status == "no_intent"
        assert old_weights.record(h) is None and old_weights.bank_bytes(h) == before
        assert h["submits"] == [] and h["configured"] == []


def test_unknown_timeout_keeps_one_exact_request_before_expired_or_cash_loader(h):
    h["unknown"] = True
    assert old_weights.run(h).status == "pending"
    retained = copy.deepcopy(old_weights.record(h)["pending"])
    before = old_weights.bank_bytes(h)
    h["now"] = h["data"].exit_session.close_ts + timedelta(days=1)
    for _ in range(2):
        assert old_weights.run(h, target_loader=forbidden).status == "pending"
    assert len(h["submits"]) == 1
    assert old_weights.record(h)["pending"]["arguments"] == retained["arguments"]
    assert old_weights.bank_bytes(h) == before


def test_actual_timeout_after_attempt_has_one_request_and_no_resubmit(h, monkeypatch):
    original = model.SyntheticClient.submit_limit

    def timeout(client, intent, **kwargs):
        original(client, intent, **kwargs)
        raise TimeoutError

    monkeypatch.setattr(model.SyntheticClient, "submit_limit", timeout)
    failures = []
    outcome = old_weights.run(h, first_failure_sink=failures.append)
    assert outcome.status == "unavailable" and outcome.reason == "native_recovery_required"
    assert failures[0]["error_category"] == "timeout_error"
    pending = copy.deepcopy(old_weights.record(h)["pending"])
    h["now"] = h["data"].entry_session.close_ts + timedelta(days=1)
    assert old_weights.run(h, target_loader=forbidden).status in {"advanced", "pending"}
    assert len(h["submits"]) == 1
    retained = old_weights.record(h)["pending"]
    assert retained is None or retained["arguments"] == pending["arguments"]


def test_first_exit_waits_last15_and_later_owned_sell_and_restart_reconcile(h):
    assert old_weights.run(h).status == "advanced"
    assert h["submits"][0].side == "buy"
    h["now"] = h["data"].metadata.exit_not_before - timedelta(seconds=1)
    assert old_weights.run(h, target_loader=forbidden).status == "hold"
    assert len(h["submits"]) == 1
    h["now"] = us_equity_2026_session(date(2026, 11, 6)).window.open_ts + timedelta(minutes=1)
    assert old_weights.run(h, target_loader=forbidden).status == "advanced"
    assert [intent.side for intent in h["submits"]] == ["buy", "sell"]
    assert old_weights.run(h, target_loader=forbidden).status == "complete"
    assert (
        old_weights.run(h, target_loader=forbidden, client_factory=forbidden).status == "complete"
    )


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_real_worker_budget_rechecks_window_after_pacing_with_zero_late_posts(tmp_path, side):
    value = point()
    at = value.entry_session.close_ts if side == "buy" else value.exit_session.close_ts
    state = dict(now=at - timedelta(seconds=1), mono=0.0)
    limits = w.RequestBudget(
        control_root=tmp_path / "clock", clock=lambda: state["now"], monotonic=lambda: state["mono"]
    )
    limits.configure_cash_h3(value, side)

    def pace():
        state["now"] += timedelta(seconds=2)
        state["mono"] += 2

    limits.rate.wait_for_request_slot = pace
    request = w.readonly.KisHttpRequest(
        "POST",
        CONFIG.base_url + core.canary.KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
        {
            "tr_id": (
                core.canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
                if side == "buy"
                else core.canary.KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID
            )
        },
    )
    with pytest.raises(ValueError, match="cash_h3_fresh_"):
        limits.start(request, None)
    assert limits.calls[side + "_posts"] == 0


def test_worker_budget_allows_reconcile_get_and_cancel_after_entry_expiry(tmp_path):
    value = point()
    limits = w.RequestBudget(
        control_root=tmp_path / "clock",
        clock=lambda: value.exit_session.open_ts,
        monotonic=lambda: 0.0,
    )
    limits.configure_cash_h3(value, "buy")
    limits.rate.wait_for_request_slot = lambda: None
    limits.start(w.readonly.KisHttpRequest("GET", CONFIG.base_url + "/invented-read", {}), None)
    limits.start(
        w.readonly.KisHttpRequest(
            "POST", CONFIG.base_url + core.canary.KIS_PAPER_US_CANCEL_PATH, {}
        ),
        None,
    )
    assert limits.calls["get_requests"] == limits.calls["cancel_posts"] == 1


@pytest.fixture
def ah(tmp_path, monkeypatch):
    state = account.h.__wrapped__(tmp_path, monkeypatch)
    old_weights.bind(state, point(), PROFILE)
    state["now"] = state["data"].entry_session.close_ts - timedelta(minutes=4)
    return state


def test_existing_account_session_routes_new_profile_and_never_quotes_cash(ah):
    result = account.visit(ah)
    assert result["stop"] == "yield_after_first_native_leg"
    assert result["calls"]["buy_posts"] == 1
    assert ah["tokens"] == 1 and ah["wires"] == 1
    assert all(client.instrument.symbol != "CASH" for client in ah["clients"])
    assert all(intent.symbol != "CASH" for intent in ah["submits"])


def test_account_session_allcash_uses_no_budget_or_client(ah):
    old_weights.bind(ah, point(stock_rows()), PROFILE)
    ah["now"] = ah["data"].entry_session.close_ts - timedelta(minutes=4)
    before = old_weights.bank_bytes(ah)
    result = account.visit(ah)
    assert result["stop"] == "empty_original_basket"
    assert not any(result["calls"].values())
    assert ah["clients"] == [] and ah["submits"] == []
    assert old_weights.bank_bytes(ah) == before


def test_real_account_worker_pacing_crosses_close_without_buy_and_keeps_exact_pending(
    ah, monkeypatch
):
    def pace(_gate):
        if ah["limits"] and ah["limits"][0].calls["get_requests"] >= 2:
            account.advance(ah, 301)

    monkeypatch.setattr(w.KisPaperMarketDataRateGate, "wait_for_request_slot", pace)
    with pytest.raises(ValueError, match="deadline_closed"):
        account.visit(ah)
    assert ah["limits"][0].calls["buy_posts"] == 0 and ah["wires"] == 0
    assert ah["submits"] == []
    assert old_weights.record(ah)["pending"] is not None
    pending = copy.deepcopy(old_weights.record(ah)["pending"])
    monkeypatch.setattr(w.KisPaperMarketDataRateGate, "wait_for_request_slot", lambda _gate: None)
    result = account.visit(ah, item=account.cohort(ah, mode="recovery"), loader=forbidden)
    assert result["stop"] == "initial_pending_recovery_once"
    assert result["calls"]["buy_posts"] == 0 and ah["submits"] == []
    retained = old_weights.record(ah)["pending"]
    assert retained is None or retained["arguments"] == pending["arguments"]


def test_worker_injection_routes_new_profile_without_using_legacy_cash_h5(monkeypatch, tmp_path):
    value = point()
    seen = {}

    def fake_cycle(**kwargs):
        seen.update(kwargs)
        return core.CurrentStockCycleOutcome("no_intent", "native_risk_no_intent")

    monkeypatch.setattr(core, "run_kis_paper_current_stock_cycle", fake_cycle)
    monkeypatch.setattr(w, "CONTROL", tmp_path / "control")
    result = w.run(
        CONFIG,
        execute=True,
        profile=PROFILE,
        target_loader=lambda: value,
        expected_input_ref=value.input_ref,
        expected_policy_ref=value.policy_ref,
    )
    assert result["status"] == "no_intent" and seen["profile"] is PROFILE
    assert callable(seen["configure_cash_h3"]) and "configure_early_exit" not in seen
    assert core.run_kis_paper_current_stock_cycle is fake_cycle


def test_exact_entry_start_and_first_exit_eligibility_boundaries_are_inclusive(h):
    h["now"] = h["data"].entry_session.close_ts - timedelta(minutes=5)
    assert old_weights.run(h).status == "advanced"
    h["now"] = h["data"].metadata.exit_not_before
    assert old_weights.run(h, target_loader=forbidden).status == "advanced"
    assert [intent.side for intent in h["submits"]] == ["buy", "sell"]


def test_native_expired_pending_buy_recovers_before_cash_then_later_owned_sell(h):
    h["partial"] = True
    assert old_weights.run(h).status == "pending"
    original = copy.deepcopy(old_weights.record(h)["pending"])
    h["now"] = h["data"].metadata.exit_not_before
    # Exact terminal evidence for the accepted partial BUY, not a guessed
    # acknowledgement for an unresolved submit with no broker reference.
    h["orders"][h["submits"][0].run_id].update(remaining=Decimal(0), cancelled=True)
    h["partial"] = False
    cash = point(stock_rows())
    loaded = []

    def fresh_cash():
        loaded.append(True)
        return cash

    assert old_weights.run(h, target_loader=fresh_cash).status == "advanced"
    assert loaded == [] and len(h["submits"]) == 1
    assert old_weights.record(h)["pending"] is None
    assert core._unpack(original["arguments"])["input_ref"] == h["data"].input_ref
    assert old_weights.run(h, target_loader=forbidden).status == "advanced"
    assert [intent.side for intent in h["submits"]] == ["buy", "sell"]
    assert h["configured"] == ["buy", "buy", "sell"]


def test_new_account_invocations_recover_expired_buy_then_configure_sell_independently(ah):
    ah["partial"] = True
    first = account.visit(ah)
    assert first["stop"] == "yield_after_first_native_leg" and first["pending"]
    initial_pending = copy.deepcopy(old_weights.record(ah)["pending"])
    ah["now"] = ah["data"].metadata.exit_not_before
    ah["orders"][ah["submits"][0].run_id].update(remaining=Decimal(0), cancelled=True)
    ah["partial"] = False
    cash = point(stock_rows())
    loads = []

    def fresh_cash():
        loads.append(True)
        return cash

    recovery = account.visit(ah, item=account.cohort(ah, mode="recovery"), loader=fresh_cash)
    assert recovery["stop"] == "initial_pending_recovery_once"
    assert recovery["calls"]["buy_posts"] == recovery["calls"]["sell_posts"] == 0
    assert ah["limits"][-1].cash_h3_side == "buy"
    assert loads == [] and len(ah["submits"]) == 1
    assert old_weights.record(ah)["pending"] is None
    assert core._unpack(initial_pending["arguments"])["input_ref"] == ah["data"].input_ref
    account.advance(ah, 61)
    sell = account.visit(ah, item=account.cohort(ah, mode="exit"), loader=forbidden)
    assert sell["stop"] == "yield_after_first_native_leg"
    assert sell["calls"]["sell_posts"] == 1 and sell["calls"]["buy_posts"] == 0
    assert ah["limits"][-1].cash_h3_side == "sell"
    assert [intent.side for intent in ah["submits"]] == ["buy", "sell"]
