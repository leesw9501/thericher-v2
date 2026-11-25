"""Exact native NET25 recovery with invented custody and no order wire."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

import test_kis_paper_current_stock_cycle as stock_fixture
import test_model_paper_net25_open_elapsed3 as net25
from test_kis_paper_weight_cycle import bank_bytes, record, run
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import kis_readonly as readonly
from thericher_v2.execution.net25_pending_reconciliation import (
    _ReadOnlyTransport,
    reconcile_net25_pending_request,
)
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.execution.paper_account_session import PaperAccountCohort


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    stock_fixture.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path):
    return net25.h.__wrapped__(tmp_path)


def denied(*_args, **_kwargs):
    pytest.fail("reconciliation attempted forbidden broker/account setup or effect")


def recover(h, *, make=denied, pending_ref=None, admissible=lambda: True):
    value, at = h["data"], h["now"]
    original = record(h)
    slot = PaperRoundSlot(
        "invented-closed-host",
        "exit",
        at,
        at + timedelta(minutes=1),
        value.input_ref,
        value.policy_ref,
    )
    cohort = PaperAccountCohort(
        slot, "sha256:" + "b" * 64, h["initial"]["basis_ref"], net25.NATIVE, "recovery"
    )
    return reconcile_net25_pending_request(
        cohort=cohort,
        paths={k: v for k, v in h["call"].items() if k.endswith(("_path", "_root"))},
        account_ref=original["account_ref"],
        expected_pending_ref=pending_ref or "sha256:" + core.budget._digest(original["pending"]),
        admissible=admissible,
        clock=lambda: at,
        make_credentials_and_transport=make,
    )


def no_order_paths(monkeypatch):
    for module, name in (
        (core, "_recover"),
        (core.entries, "reserve_kis_paper_stock_plan"),
        (core.exits, "reserve_kis_paper_stock_exit_plan"),
        (core.execution, "execute_kis_paper_stock_buy"),
        (core.execution, "execute_kis_paper_stock_sell"),
        (core.canary, "_cancel_submitted_canary"),
    ):
        monkeypatch.setattr(module, name, denied)


def test_unconfirmed_create_cannot_reserve_or_touch_wire(h, monkeypatch):
    with monkeypatch.context() as patch:

        def crash(**_):
            raise RuntimeError("invented_capture_interrupt")

        patch.setattr(core.entries, "reserve_kis_paper_stock_plan", crash)
        assert run(h).status == "unavailable"
    no_order_paths(monkeypatch)
    before, pending = bank_bytes(h), record(h)["pending"]
    assert recover(h).reason == "unreserved_not_expired"
    assert record(h)["pending"] == pending and bank_bytes(h) == before and not h["submits"]
    with pytest.raises(core._CycleFault, match="cycle_request_changed"):
        recover(h, pending_ref="sha256:" + "f" * 64)
    h["now"] += timedelta(minutes=15)
    assert recover(h).reason == "never_reserved_retired"
    assert record(h)["pending"] is None and bank_bytes(h) == before and not h["submits"]


def test_cancellable_partial_order_is_observed_but_not_cancelled(h, monkeypatch):
    h["partial"] = True
    assert run(h).status == "pending"
    original_bank, original_pending = bank_bytes(h), record(h)["pending"]
    h["now"] += timedelta(minutes=15)
    no_order_paths(monkeypatch)
    reads = []

    def observe(self, state, *, now):
        reads.append(True)
        old = h["call"]["client_factory"](self.instrument)
        return old.reconcile(state, now=now)

    monkeypatch.setattr(core.KisPaperStockCanaryClient, "reconcile", observe)

    def make(_):
        return stock_fixture.CONFIG, SimpleNamespace(request=denied)

    outcome = recover(h, make=make)
    assert outcome.status == "pending" and reads == [True]
    assert record(h)["pending"] == original_pending and bank_bytes(h) == original_bank
    assert len(h["submits"]) == 1 and not h["cancels"]


def test_exact_local_terminal_reconciles_after_journal_write_interrupt(h, monkeypatch):
    with monkeypatch.context() as patch:

        def crash(**_):
            raise RuntimeError("invented_before_plan_write")

        patch.setattr(core.entries, "reconcile_kis_paper_stock_plan", crash)
        assert run(h).status == "unavailable"
    no_order_paths(monkeypatch)
    pending = record(h)["pending"]
    assert pending is not None and len(h["submits"]) == 1
    with monkeypatch.context() as patch:

        def failed_save(*_):
            raise OSError("invented_after_plan_write")

        patch.setattr(core, "_save", failed_save)
        with pytest.raises(OSError, match="after_plan_write"):
            recover(h)
    canon = bank_bytes(h)
    assert record(h)["pending"] == pending
    result = recover(h)
    assert result.status == "reconciled" and result.token_attempts == result.get_attempts == 0
    assert record(h)["pending"] is None and bank_bytes(h) == canon and len(h["submits"]) == 1


@pytest.mark.parametrize("endpoint", ["order", "order-rvsecncl", "wrong-GET", "live-token"])
def test_wire_filter_denies_order_and_nonpaper_routes(endpoint):
    base = readonly.KIS_PAPER_BASE_URL
    if endpoint == "live-token":
        url, method = "https://openapi.koreainvestment.com:9443/oauth2/tokenP", "POST"
    else:
        url = base + "/uapi/overseas-stock/v1/trading/" + endpoint
        method = "GET" if endpoint == "wrong-GET" else "POST"
    transport = _ReadOnlyTransport(SimpleNamespace(request=denied), denied)
    with pytest.raises(readonly.KisPaperReadOnlyError):
        transport.request(readonly.KisHttpRequest(method=method, url=url, headers={}))


def test_wire_filter_passes_one_exact_token_and_does_not_retry():
    calls = []
    req = readonly.KisHttpRequest(
        method="POST",
        url=readonly.KIS_PAPER_BASE_URL + readonly.KIS_PAPER_TOKEN_PATH,
        headers={"content-type": "application/json", "accept": "application/json"},
        json_body={
            "grant_type": "client_credentials",
            "appkey": "invented",
            "appsecret": "invented",
        },
    )
    wire = _ReadOnlyTransport(SimpleNamespace(request=calls.append), lambda: None)
    wire.request(req)
    with pytest.raises(readonly.KisPaperReadOnlyError, match="token_request_not_due"):
        wire.request(req)
    assert calls == [req] and wire.token_attempts == 1
