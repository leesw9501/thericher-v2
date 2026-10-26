"""Invented native journals and transport only; no real bank, credentials or wire."""

import copy
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_weight_cycle as weights
import test_model_paper_profile as model
from test_kis_paper_current_stock_cycle_worker import w
from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG
from test_model_paper_weights import ModelPaperWeightRow, metadata, prepared
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.execution.paper_account_session import PaperAccountCohort

SOURCE = "sha256:" + "a" * 64


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)

    def deny(*args, **kwargs):
        pytest.fail("actual_credentials_or_wire_forbidden")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(w.readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


@pytest.fixture
def h(tmp_path, monkeypatch):
    state = weights.h.__wrapped__(tmp_path)
    state.update(mono=0.0, tokens=0, wires=0, clients=[], limits=[], quote_skip=set(),
                 owner_checks=0, source_checks=0)
    state["paths"] = {k: v for k, v in state["call"].items()
                      if k.endswith("_path") or k.endswith("_root")}
    factory = w.client_factory

    class Transport:
        def __init__(self, *, instrument, limits):
            self.instrument, self.limits = instrument, limits
            state["limits"].append(limits)

        def request(self, request):
            assert request.url.endswith(w.readonly.KIS_PAPER_TOKEN_PATH)
            self.limits.start(request, None)
            state["tokens"] += 1
            return w.readonly.KisHttpResponse.from_payload({"access_token": "invented-only"})

    class Client(w.KisPaperStockCanaryClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.h = state
            state["clients"].append(self)

        def get(self):
            self._transport.limits.start(w.readonly.KisHttpRequest(
                "GET", CONFIG.base_url + "/invented-read", {}), None)

        def snapshot(self, **kwargs):
            return legacy.NativeSyntheticStockClient.snapshot(self, **kwargs)

        def stock_preview_snapshot(self, **kwargs):
            self.get()
            if self.instrument.symbol in state["quote_skip"]:
                raise core.KisPaperReadOnlyError("quote_timestamp_unavailable")
            return legacy.NativeSyntheticStockClient.stock_preview_snapshot(self, **kwargs)

        def stock_exit_snapshot(self, **kwargs):
            self.get()
            return legacy.NativeSyntheticStockClient.stock_exit_snapshot(self, **kwargs)

        def orderable_funds_at_limit(self, **kwargs):
            self.get()
            return legacy.NativeSyntheticStockClient.orderable_funds_at_limit(self, **kwargs)

        def submit_limit(self, intent, **kwargs):
            self._transport.limits.start(w.readonly.KisHttpRequest(
                "POST", CONFIG.base_url + core.canary.KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
                {"tr_id": (core.canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
                           if intent.side == "buy"
                           else core.canary.KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID)}), None)
            state["wires"] += 1
            return model.SyntheticClient.submit_limit(self, intent, **kwargs)

        def reconcile(self, order_state, **kwargs):
            self.get()
            return legacy.NativeSyntheticStockClient.reconcile(self, order_state, now=state["now"])

        def cancel_order(self, intent, **kwargs):
            self._transport.limits.start(w.readonly.KisHttpRequest(
                "POST", CONFIG.base_url + core.canary.KIS_PAPER_US_CANCEL_PATH, {}), None)
            return legacy.NativeSyntheticStockClient.cancel_order(self, intent, **kwargs)

    def create_factory(config, limits):
        state["factories"] += 1
        return factory(config, limits)

    monkeypatch.setattr(w, "OwnedTransport", Transport)
    monkeypatch.setattr(w, "KisPaperStockCanaryClient", Client)
    monkeypatch.setattr(w, "client_factory", create_factory)
    return state


def advance(h, seconds):
    h["mono"] += seconds
    h["now"] += timedelta(seconds=seconds)


def cohort(h, *, mode="entry", **changes):
    start, end = h["data"].entry_session.open_ts, h["data"].entry_session.close_ts
    if mode != "entry":
        start, end = h["now"], h["now"] + timedelta(minutes=5)
    value = PaperAccountCohort(
        PaperRoundSlot("invented-owned-cohort", "entry" if mode == "entry" else "exit",
                       start, end, h["data"].input_ref, h["data"].policy_ref),
        SOURCE, h["initial"]["basis_ref"], h["call"]["profile"], mode,
    )
    return replace(value, **changes)


def visit(h, *, item=None, loader=None, owner=None, source=None, **kwargs):
    def owned():
        h["owner_checks"] += 1
        return None if owner is None else owner()

    def pinned():
        h["source_checks"] += 1
        return None if source is None else source()

    return w.run_account_session(
        CONFIG, execute=True, cohort=cohort(h) if item is None else item,
        paths=h["paths"], target_loader=h["call"]["target_loader"] if loader is None else loader,
        owner_ready=owned, source_ready=pinned, control_root=h["root"].parent / "timing",
        deadline=kwargs.pop("deadline", h["now"] + timedelta(seconds=180)),
        clock=lambda: h["now"], monotonic=lambda: h["mono"],
        sleeper=lambda seconds: advance(h, seconds), **kwargs,
    )


def forbidden():
    pytest.fail("retained_input_must_not_reload")


def reserve_foreign(h, target):
    instrument = core.KisPaperStockInstrument(target.proposal.symbol,
                                             target.receipt.instrument_binding_ref)
    binding = core.budget._load_binding(h["root"])
    reads = legacy.NativeSyntheticStockClient(h, instrument).stock_preview_snapshot(
        expected_account_ref=ACCOUNT, clock=lambda: h["now"])
    plan = core.entries.reserve_kis_paper_stock_plan(
        **{k: h["paths"][k] for k in ("state_root", "repository_root", "artifact_root")},
        expected_account_ref=ACCOUNT, expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=core._refs(binding),
        expected_binding_ref="sha256:" + core.budget._digest(binding),
        request_id="invented-foreign", input_ref=h["data"].input_ref,
        instrument=instrument, proposal=target.proposal, receipt=target.receipt,
        reads=reads, as_of=h["now"], valid_until=h["now"] + timedelta(minutes=5),
    )
    assert plan.status == "reserved"
    return plan.plan_ref


def test_foreign_then_quote_skip_reaches_one_effect_with_one_shared_resource(h):
    rows = (
        ModelPaperWeightRow(0, "AAPL/NAS", True, Decimal(".5")),
        ModelPaperWeightRow(1, "MSFT/NAS", True, Decimal(".25")),
        ModelPaperWeightRow(2, "AMZN/NAS", True, Decimal(".25")),
    )
    weights.bind(h, prepared(metadata(rows)))
    original = h["data"]
    foreign = reserve_foreign(h, original.targets[0])
    h["quote_skip"].add(original.targets[1].proposal.symbol)
    result = visit(h)
    assert result["stop"] == "yield_after_first_native_leg"
    assert result["native_calls"] == 3 and result["skipped"] == 2
    assert h["factories"] == h["tokens"] == h["wires"] == 1
    assert len({id(v) for v in h["limits"]}) == 1
    assert result["calls"]["buy_posts"] == result["calls"]["token_posts"] == 1
    saved = weights.record(h)
    assert original.targets[0].proposal.symbol not in saved["owners"]
    assert all(foreign not in v["plans"].values() for v in saved["owners"].values())
    assert core._unpack(saved["active"]["model_input"]) == original
    assert result["outer_debits"] == 0
    assert h["owner_checks"] > result["native_calls"]


def test_positive_reconciled_first_leg_still_stops_before_second_target(h):
    result = visit(h)
    assert result["native"]["status"] == "advanced"
    assert result["native_calls"] == h["wires"] == 1
    assert result["stop"] == "yield_after_first_native_leg" and not result["pending"]
    assert len(weights.record(h)["active"]["entries_done"]) == 1
    assert "invented-only" not in json.dumps(result)
    assert result["fees"] == result["net_pnl"] == "not_observed"


def test_prefix_restart_uses_retained_basket_and_same_original_basis(h):
    h["quote_skip"].update(t.proposal.symbol for t in h["data"].targets)
    before = weights.bank_bytes(h)
    first = visit(h, max_native_calls=1)
    assert first["cursor"] == 1 and first["native_calls"] == 1
    assert weights.bank_bytes(h) == before
    advance(h, 61)
    second = visit(h, loader=forbidden, max_native_calls=1)
    assert second["cursor"] == 2 and second["native_calls"] == 1
    assert h["loads"] == 1 and not h["submits"]
    assert weights.bank_bytes(h) == before


def test_unknown_retained_recovery_precedes_expired_loader_without_resubmit(h):
    h["unknown"] = True
    first = visit(h)
    retained = copy.deepcopy(weights.record(h)["pending"])
    bank = weights.bank_bytes(h)
    assert first["pending"] and h["wires"] == 1
    h["now"] = h["data"].entry_session.close_ts + timedelta(days=1)
    advance(h, 61)
    second = visit(h, item=cohort(h, mode="recovery"), loader=forbidden)
    assert second["stop"] == "initial_pending_recovery_once"
    assert second["pending"] and second["native_calls"] == 1
    assert h["wires"] == 1 and second["calls"]["buy_posts"] == 0
    assert weights.record(h)["pending"]["arguments"] == retained["arguments"]
    assert weights.bank_bytes(h) == bank


def test_recovery_without_pending_is_inert_and_does_not_load_or_create_resources(h):
    result = visit(h, item=cohort(h, mode="recovery"), loader=forbidden)
    assert result["stop"] == "no_retained_pending"
    assert result["native_calls"] == h["factories"] == h["tokens"] == 0


def test_exit_before_declared_exit_never_seeds_a_fresh_buy(h):
    visit(h)
    before = weights.pointer(h).read_bytes(), weights.bank_bytes(h)
    old_tokens, old_wires = h["tokens"], h["wires"]
    result = visit(h, item=cohort(h, mode="exit"), loader=forbidden)
    assert result["stop"] == "await_declared_exit" and result["native_calls"] == 0
    assert (weights.pointer(h).read_bytes(), weights.bank_bytes(h)) == before
    assert (h["tokens"], h["wires"]) == (old_tokens, old_wires)


def test_early_profile_later_day_unknown_buy_recovery_keeps_exact_request(h):
    from test_kis_paper_h20_early_exit import PROFILE, point

    weights.bind(h, point(), PROFILE)
    h["unknown"] = True
    first = visit(h)
    retained = copy.deepcopy(weights.record(h)["pending"])
    bank = weights.bank_bytes(h)
    assert first["pending"] and h["wires"] == 1
    h["now"] = h["data"].entry_session.close_ts + timedelta(days=1)
    advance(h, 61)
    result = visit(h, item=cohort(h, mode="recovery"), loader=forbidden)
    assert result["pending"] and result["stop"] == "initial_pending_recovery_once"
    assert h["wires"] == 1 and result["calls"]["buy_posts"] == 0
    assert weights.record(h)["pending"]["arguments"] == retained["arguments"]
    assert weights.bank_bytes(h) == bank


@pytest.mark.parametrize("change", ["input", "policy", "basis", "source", "cursor", "paths"])
def test_exact_retained_binding_and_cursor_mismatch_reject_before_wire(h, change):
    h["quote_skip"].update(t.proposal.symbol for t in h["data"].targets)
    visit(h, max_native_calls=1)
    advance(h, 61)
    item = cohort(h)
    if change in {"input", "policy"}:
        item = replace(item, slot=replace(item.slot, **{change + "_ref": "sha256:" + "9" * 64}))
    elif change == "basis":
        item = replace(item, basis_ref="sha256:" + "9" * 64)
    elif change == "source":
        with pytest.raises(ValueError, match="admission_denied"):
            visit(h, source=lambda: False, loader=forbidden)
        return
    elif change == "cursor":
        saved = weights.record(h)
        saved["active"]["entries_done"] = [h["data"].targets[1].proposal.symbol]
        core._save(weights.pointer(h), saved)
    else:
        h["paths"] = h["paths"] | {"runtime_projection_path": h["root"].parent / "other.json"}
    old_wires, old_tokens = h["wires"], h["tokens"]
    with pytest.raises((ValueError, core._CycleFault)):
        visit(h, item=item, loader=h["call"]["target_loader"] if change == "policy" else forbidden)
    assert (h["wires"], h["tokens"]) == (old_wires, old_tokens)


def test_deadline_crossed_during_pacing_prevents_wire_and_retains_unknown(h, monkeypatch):
    issued_deadline = h["now"] + timedelta(seconds=60)
    original = w.KisPaperMarketDataRateGate.wait_for_request_slot

    def pace(gate):
        original(gate)
        if h["limits"] and h["limits"][0].calls["get_requests"] >= 2:
            h["now"] = issued_deadline

    monkeypatch.setattr(w.KisPaperMarketDataRateGate, "wait_for_request_slot", pace)
    with pytest.raises(ValueError, match="deadline_closed"):
        visit(h, deadline=issued_deadline)
    assert h["wires"] == 0
    saved = weights.record(h)
    assert saved["pending"] is not None and not saved["active"]["entries_done"]


def test_one_http_budget_is_not_reset_across_skipped_targets(h, monkeypatch):
    h["quote_skip"].update(t.proposal.symbol for t in h["data"].targets)
    original = w.RequestBudget._check

    def check(limits, key):
        original(limits, key)
        if key == "get_requests" and limits.calls[key] >= 1:
            raise w.canary.KisPaperCanaryError("request_budget_exhausted")

    monkeypatch.setattr(w.RequestBudget, "_check", check)
    result = visit(h)
    assert result["native_calls"] == 2 and result["skipped"] == 1
    assert result["native"]["status"] == "unavailable" and h["wires"] == 0
    assert h["factories"] == h["tokens"] == result["calls"]["get_requests"] == 1


def test_owner_guard_after_delay_cannot_be_replaced_by_proposal(h):
    with pytest.raises(ValueError, match="admission_denied"):
        visit(h, owner=lambda: False, loader=forbidden)
    assert h["tokens"] == h["wires"] == h["factories"] == 0


def test_last_pre_wire_owner_callback_cannot_roll_clock_before_slot(h):
    item = cohort(h)
    h["quote_skip"].update(t.proposal.symbol for t in h["data"].targets)
    armed = False
    checks = 0

    def owner():
        nonlocal checks
        if armed:
            checks += 1
            if checks == 4:
                h["now"] = item.slot.starts_at - timedelta(seconds=1)

    visit(h, item=item, owner=owner)
    limits = h["limits"][0]
    before = dict(limits.calls)
    armed = True
    request = w.readonly.KisHttpRequest("GET", CONFIG.base_url + "/invented-read", {})
    with pytest.raises(ValueError, match="deadline_closed"):
        limits.start(request, None)
    assert checks == 4 and limits.calls == before and h["wires"] == 0


@pytest.mark.parametrize("stage", ["initial", "after_admission"])
def test_direct_native_api_enforces_slot_start_before_any_custody_or_callbacks(
    h, monkeypatch, stage
):
    from thericher_v2.execution import paper_account_session as session

    item = cohort(h)
    start = h["now"] + (timedelta(seconds=10) if stage == "initial" else timedelta(0))
    item = replace(item, slot=replace(item.slot, starts_at=start))
    admitted = []

    def admit():
        admitted.append(True)
        h["now"] = start - timedelta(seconds=1)

    def untouched(*args, **kwargs):
        pytest.fail("pre_slot_native_api_touched_custody_or_financial_callbacks")

    monkeypatch.setattr(session, "_snapshot", untouched)
    monkeypatch.setattr(core, "run_kis_paper_current_stock_cycle", untouched)
    with pytest.raises(session.PaperAccountSessionError, match="deadline_closed"):
        session.run_native_account_session(
            cohort=item, paths=h["paths"], expected_account_ref=ACCOUNT,
            target_loader=untouched, client_factory=untouched, configure_early_exit=untouched,
            admit=admit, deadline=start + timedelta(seconds=60),
            clock=lambda: h["now"], monotonic=lambda: h["mono"],
        )
    assert len(admitted) == (0 if stage == "initial" else 1)
    assert h["loads"] == h["factories"] == h["tokens"] == h["wires"] == 0
