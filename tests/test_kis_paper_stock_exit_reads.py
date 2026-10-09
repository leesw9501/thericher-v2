"""Synthetic cash-free exit observations/recovery; no private or provider IO."""

from __future__ import annotations

import socket
import traceback
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_readonly_stock_preview import INSTRUMENT, FakeTransport, account_ref, client, config
from thericher_v2.execution import kis_paper_stock_readonly as stock
from thericher_v2.execution import kis_readonly as old
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryIntent,
    KisPaperCanaryState,
)
from thericher_v2.execution.kis_paper_fill_accounting import KisPaperExecutionObservation
from thericher_v2.execution.kis_paper_quote import derive_kis_paper_marketable_limit
from thericher_v2.execution.kis_paper_stock_canary import KisPaperStockCanaryClient


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("exit_reads_cannot_use_credentials_funds_or_actual_wire")

    for obj, name in (
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (urllib.request.OpenerDirector, "open"),
        (urllib.request, "urlopen"),
        (old, "load_kis_paper_config"),
        (old, "load_kis_paper_config_from_environment"),
        (old.KisPaperReadOnlyClient, "_cash_and_orderable_funds"),
        (old.KisPaperReadOnlyClient, "snapshot"),
    ):
        monkeypatch.setattr(obj, name, denied)


class ExitTransport(FakeTransport):
    account_fault = ""

    def request(self, request):
        tr_id = request.headers.get("tr_id")
        if tr_id == old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            pytest.fail("funds_not_in_exit_protocol")
        if tr_id not in {
            old.KIS_PAPER_BALANCE_ENDPOINT.tr_id,
            old.KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
        }:
            return super().request(request)
        old.validate_kis_paper_readonly_request(request)
        self.requests.append(request)
        is_balance = tr_id == old.KIS_PAPER_BALANCE_ENDPOINT.tr_id
        output = "output1" if is_balance else "output"
        payload = {"rt_cd": "0", output: []}
        headers = {}
        if self.account_fault == "invalid_header":
            headers["tr_cont"] = "UNKNOWN"
        elif self.account_fault == "missing_cursor":
            headers["tr_cont"] = "M"
        elif self.account_fault == "endless":
            headers["tr_cont"] = "M"
            payload.update(ctx_area_fk200="synthetic-fk", ctx_area_nk200="synthetic-nk")
        elif self.account_fault == "duplicate":
            return old.KisHttpResponse(200, {}, b'{"rt_cd":"0","output":[],"output":[]}')
        elif self.account_fault == "rejected":
            payload = {"rt_cd": "1", "msg1": "synthetic-private-message"}
        if is_balance and self.account_fault not in {"endless", "missing_cursor", "rejected"}:
            row = dict(
                ovrs_cblc_qty="2",
                ovrs_excg_cd="NASD",
                pchs_avg_pric="95",
                now_pric2="100",
                ovrs_pdno=INSTRUMENT.symbol,
                tr_crcy_cd="USD",
            )
            if (
                self.account_fault == "conflicting_balance"
                and request.query["OVRS_EXCG_CD"] == "NYSE"
            ):
                row["ovrs_cblc_qty"] = "3"
            payload[output] = [row]
        return old.KisHttpResponse.from_payload(payload, headers=headers)


def exit_reads(value, transport, **changes):
    return value.stock_exit_snapshot(
        **(
            dict(
                instrument=INSTRUMENT,
                expected_account_ref=account_ref(value),
                clock=lambda: transport.now,
            )
            | changes
        )
    )


def test_exit_account_and_bid_without_cash_funds_one_token():
    transport = ExitTransport()
    value = client(transport)
    result = exit_reads(value, transport)
    assert type(result) is stock.KisPaperStockExitReads
    assert type(result.snapshot) is stock.KisPaperStockExitAccountSnapshot
    assert result.positions == result.snapshot.positions
    assert result.open_orders == result.snapshot.open_orders.orders == ()
    assert len(result.positions) == 1 and result.positions[0].quantity == 2
    assert result.snapshot.open_orders.complete is True
    assert derive_kis_paper_marketable_limit(
        result.quote, side="sell", observed_at=result.completed_at
    ) == Decimal("99.99")
    assert len(transport.requests) == 7
    assert all("ITEM_CD" not in r.query for r in transport.requests)
    assert sum(r.method == "POST" for r in transport.requests) == 1
    assert {
        r.query.get("OVRS_EXCG_CD")
        for r in transport.requests
        if r.headers.get("tr_id") == old.KIS_PAPER_BALANCE_ENDPOINT.tr_id
    } == set(old.KIS_PAPER_US_EXCHANGES)
    exit_reads(value, transport)
    assert sum(r.method == "POST" for r in transport.requests) == 1
    assert not hasattr(result.snapshot, "cash") and not hasattr(result, "orderable")
    assert INSTRUMENT.symbol not in repr(result) and account_ref(value) not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.account_ref = "b" * 64


@pytest.mark.parametrize("change", ["account", "instrument", "tampered_instrument"])
def test_scope_invalid_before_token(change):
    transport = ExitTransport()
    changes = {"expected_account_ref": "b" * 64} if change == "account" else {"instrument": None}
    if change == "tampered_instrument":
        instrument = replace(INSTRUMENT)
        object.__setattr__(instrument, "binding_ref", "wrong")
        changes = {"instrument": instrument}
    with pytest.raises(old.KisPaperReadOnlyError):
        exit_reads(client(transport), transport, **changes)
    assert transport.requests == []


@pytest.mark.parametrize(
    "fault",
    ["invalid_header", "missing_cursor", "endless", "duplicate", "rejected", "conflicting_balance"],
)
def test_incomplete_or_conflicting_account_does_not_return_partial(fault):
    transport = ExitTransport()
    transport.account_fault = fault
    with pytest.raises(old.KisPaperReadOnlyError):
        exit_reads(client(transport), transport)
    assert not any("/quotations/" in r.url for r in transport.requests)
    assert len(transport.requests) <= 1 + old.MAX_KIS_PAPER_BALANCE_PAGES


@pytest.mark.parametrize("kind", ["age", "tick", "continuation"])
def test_quote_scoped_unavailable(kind):
    transport = ExitTransport()
    if kind == "age":
        transport.quote_age = 121
    elif kind == "tick":
        transport.bad_tick = True
    else:
        transport.quote_continuation = "M"
    with pytest.raises(old.KisPaperReadOnlyError):
        exit_reads(client(transport), transport)


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_ref", "private"),
        ("elapsed_seconds", float("nan")),
        ("elapsed_seconds", True),
        ("snapshot", None),
        ("quote", None),
    ],
)
def test_exit_dto_revalidates(field, value):
    transport = ExitTransport()
    result = exit_reads(client(transport), transport)
    with pytest.raises(old.KisPaperReadOnlyError):
        replace(result, **{field: value})


def test_completion_time_rechecks_stale_account_and_quote():
    transport = ExitTransport()
    result = exit_reads(client(transport), transport)
    with pytest.raises(old.KisPaperReadOnlyError, match="stock_snapshot_stale"):
        replace(result, completed_at=result.completed_at + timedelta(seconds=121))
    with pytest.raises(old.KisPaperReadOnlyError):
        replace(result, completed_at=result.started_at - timedelta(seconds=1))


def test_canary_delegates_exit_and_keeps_token_after_failure():
    transport = ExitTransport()
    value = KisPaperStockCanaryClient(config=config(), transport=transport, instrument=INSTRUMENT)
    value.stock_exit_snapshot(expected_account_ref=account_ref(value), clock=lambda: transport.now)
    assert value._access_token == "synthetic-token"
    transport.quote_age = 121
    with pytest.raises(old.KisPaperReadOnlyError):
        value.stock_exit_snapshot(
            expected_account_ref=account_ref(value), clock=lambda: transport.now
        )
    assert value._access_token == "synthetic-token"
    assert sum(r.method == "POST" for r in transport.requests) == 1


def test_error_causes_do_not_expose_provider_messages():
    transport = ExitTransport()
    transport.account_fault = "rejected"
    with pytest.raises(old.KisPaperReadOnlyError) as caught:
        exit_reads(client(transport), transport)
    assert caught.value.__suppress_context__ is True
    assert "synthetic-private-message" not in "".join(traceback.format_exception(caught.value))


def test_canary_first_account_failure_retains_token():
    transport = ExitTransport()
    transport.account_fault = "rejected"
    value = KisPaperStockCanaryClient(config=config(), transport=transport, instrument=INSTRUMENT)
    with pytest.raises(old.KisPaperReadOnlyError):
        value.stock_exit_snapshot(
            expected_account_ref=account_ref(value), clock=lambda: transport.now
        )
    assert value._access_token == "synthetic-token"
    transport.account_fault = ""
    value.stock_exit_snapshot(expected_account_ref=account_ref(value), clock=lambda: transport.now)
    assert sum(r.method == "POST" for r in transport.requests) == 1


@pytest.mark.parametrize("fault", ["incomplete_orders", "duplicate_positions", "clock"])
def test_minimal_snapshot_rejects_tampered_completeness_and_clock(fault):
    transport = ExitTransport()
    snapshot = exit_reads(client(transport), transport).snapshot
    if fault == "incomplete_orders":
        orders = replace(snapshot.open_orders)
        object.__setattr__(orders, "complete", False)
        changes = {"open_orders": orders}
    elif fault == "duplicate_positions":
        changes = {"positions": snapshot.positions + snapshot.positions}
    else:
        changes = {"captured_at": snapshot.captured_at + timedelta(seconds=1)}
    with pytest.raises(old.KisPaperReadOnlyError):
        replace(snapshot, **changes)


def test_account_transport_exception_has_no_sensitive_cause():
    class FailingTransport(ExitTransport):
        def request(self, request):
            if request.method == "GET":
                raise OSError("synthetic-private-message")
            return super().request(request)

    transport = FailingTransport()
    with pytest.raises(old.KisPaperReadOnlyError, match="transport_failure") as caught:
        exit_reads(client(transport), transport)
    assert "synthetic-private-message" not in "".join(traceback.format_exception(caught.value))


def sell_state(transport, phase="intent_recorded", broker_id=None):
    at = transport.now - timedelta(seconds=30)
    intent = KisPaperCanaryIntent(
        "synthetic-exit",
        "synthetic-client",
        "synthetic-decision",
        INSTRUMENT.symbol,
        "NASD",
        Decimal(2),
        Decimal("99.99"),
        at,
        at + timedelta(minutes=5),
        "sell",
    )
    return KisPaperCanaryState(
        intent,
        phase,
        transport.now,
        "preview",
        broker_order_id=broker_id,
        submission_started_at=at + timedelta(seconds=1) if phase != "intent_recorded" else None,
        submitted_at=at + timedelta(seconds=1) if broker_id else None,
    )


def test_sell_reconciliation_is_account_only_no_quote_or_funds():
    transport = ExitTransport()
    transport.quote_age = 10000
    value = KisPaperStockCanaryClient(config=config(), transport=transport, instrument=INSTRUMENT)
    result = value.reconcile(sell_state(transport), now=transport.now)
    assert result.status == "clean" and result.account_status == "available"
    assert type(result.snapshot) is stock.KisPaperStockExitAccountSnapshot
    assert result.position_count == 1 and result.open_order_count == 0
    assert len(transport.requests) == 5
    assert value._access_token == "synthetic-token"


def test_sell_reconciliation_preserves_exact_execution_call(monkeypatch):
    transport = ExitTransport()
    value = KisPaperStockCanaryClient(config=config(), transport=transport, instrument=INSTRUMENT)
    state = sell_state(transport, "submitted", "SYNTHETIC-ORDER")
    seen = []
    observation = KisPaperExecutionObservation(
        status="unavailable",
        observed_at=transport.now,
        row_count=0,
        same_day_order_id_seen=True,
    )

    def observe(reader, broker_id, **arguments):
        seen.append((broker_id, arguments))
        return observation

    monkeypatch.setattr(stock.KisPaperStockReadOnlyClient, "observe_order_execution", observe)
    result = value.reconcile(state, now=transport.now)
    assert result.execution is observation and result.matching_ccnl is True
    assert seen[0][0] == state.broker_order_id
    assert seen[0][1] == dict(
        order_at=state.submission_started_at,
        observed_at=transport.now,
        symbol=INSTRUMENT.symbol,
        exchange="NASD",
        side="sell",
        quantity=Decimal(2),
    )


def test_sell_idless_recovery_uses_same_exact_scope(monkeypatch):
    transport = ExitTransport()
    value = KisPaperStockCanaryClient(config=config(), transport=transport, instrument=INSTRUMENT)
    state = sell_state(transport, "outcome_unknown")
    seen = []

    def history(reader, **arguments):
        seen.append(arguments)
        return old.KisPaperIdlessHistoryObservation("absent", 0, 0)

    monkeypatch.setattr(stock.KisPaperStockReadOnlyClient, "inspect_idless_order_history", history)
    result = value.reconcile(state, now=transport.now)
    assert result.status == "unresolved" and result.recovered_broker_order_id is None
    assert seen[0]["side"] == "sell" and seen[0]["quantity"] == 2
    assert seen[0]["order_at"] == state.submission_started_at


def test_buy_reconciliation_keeps_legacy_delegate(monkeypatch):
    transport = ExitTransport()
    value = KisPaperStockCanaryClient(config=config(), transport=transport, instrument=INSTRUMENT)
    state = sell_state(transport)
    state = replace(state, intent=replace(state.intent, side="buy"))
    marker = object()
    monkeypatch.setattr(KisPaperCanaryClient, "reconcile", lambda *a, **kw: marker)
    assert value.reconcile(state, now=transport.now) is marker
    assert transport.requests == []
