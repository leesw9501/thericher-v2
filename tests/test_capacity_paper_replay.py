from __future__ import annotations

import socket
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.research.capacity_paper_replay import CapacityPaperReplay, CapacityProposal
from thericher_v2.state import Event, EventStore

D = Decimal
T = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


def _replay(root: Path, *, fee="0", slip="0", balance="1000") -> CapacityPaperReplay:
    return CapacityPaperReplay(
        event_store=EventStore(root / "state.sqlite", root / "events.jsonl"),
        emergency_store=EmergencyStore(root / "emergency.json"),
        initial_balance=D(balance),
        fee_bps=D(fee),
        slippage_bps=D(slip),
    )


def _proposal(lot="a", *, available=0, entry=1, exit=6, quantity="1", reserve="60"):
    return CapacityProposal(
        lot_id=lot,
        cohort_id=f"cohort-{lot}",
        market="US",
        symbol="QQQ",
        quantity=D(quantity),
        max_entry_cost=D(reserve),
        available_at=T + timedelta(minutes=available),
        entry_at=T + timedelta(minutes=entry),
        exit_at=T + timedelta(minutes=exit),
    )


def _bar(minute: int, price="60", *, symbol="QQQ", complete=True) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=T + timedelta(minutes=minute),
        open=D(price),
        high=D(price),
        low=D(price),
        close=D(price),
        volume=D("100"),
        complete=complete,
    )


def _pair(minute, price="60"):
    return dict(signal_bar=_bar(minute - 1), execution_bar=_bar(minute, price))


def _snapshot(replay, minute, marks=None):
    return replay.snapshot(at=T + timedelta(minutes=minute), marks=marks)


def _fills(replay):
    return [e for e in replay.broker.event_store.iter_events() if e.event_type == "fill"]


def test_overlapping_cohorts_share_one_original_b10(tmp_path):
    replay = _replay(tmp_path / "shared")
    assert replay.reserve(_proposal()).status == "reserved"
    assert replay.reserve(_proposal()).status == "reserved"
    assert replay.reserve(_proposal("b")).status == "capacity_blocked"
    snap = _snapshot(replay, 0)
    assert snap.envelope == 100
    assert snap.pending_reservations == 60
    assert snap.available_capacity == 40
    fill = replay.enter("a", **_pair(1)).fill
    assert fill is not None and fill.source == "local_paper"
    snap = _snapshot(replay, 1)
    assert (snap.open_basis, snap.pending_reservations, snap.cash) == (60, 0, 940)
    assert snap.available_capacity == 40
    assert replay.enter("b", **_pair(1)).status == "capacity_blocked"
    assert len(_fills(replay)) == 1
    # The old independently funded interpretation would wrongly admit both.
    for cohort in ("a", "b"):
        independent = _replay(tmp_path / cohort)
        assert independent.reserve(_proposal(cohort)).status == "reserved"
        assert independent.enter(cohort, **_pair(1)).fill is not None


def test_reservation_becomes_actual_all_in_basis_once(tmp_path):
    replay = _replay(tmp_path, fee="10", slip="20")
    replay.reserve(_proposal(reserve="70"))
    fill = replay.enter("a", **_pair(1)).fill
    assert fill is not None
    assert fill.price == D("60.1200")
    assert fill.fee == D("0.0601")
    snap = _snapshot(replay, 1)
    assert snap.open_basis == fill.notional + fill.fee == D("60.1801")
    assert snap.pending_reservations == 0
    assert snap.available_capacity == D("39.8199")
    replay.exit("a", **_pair(6, "50"))
    snap = _snapshot(replay, 6)
    assert snap.realized_pnl == D("49.8501") - D("60.1801")
    assert snap.realized_losses == -snap.realized_pnl
    assert snap.cash == D("1000") + snap.realized_pnl
    assert snap.available_capacity == 100 - snap.realized_losses


def test_profits_do_not_expand_or_refill_loss_debits(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    replay.enter("a", **_pair(1))
    replay.exit("a", **_pair(6, "90"))
    assert _snapshot(replay, 6).cash == 1030
    assert _snapshot(replay, 6).available_capacity == 100
    replay.reserve(_proposal("b", available=6, entry=7, exit=8))
    replay.enter("b", **_pair(7))
    replay.exit("b", **_pair(8, "40"))
    snap = _snapshot(replay, 8)
    assert (snap.cash, snap.realized_pnl, snap.realized_losses) == (1010, 10, 20)
    assert snap.available_capacity == 80
    assert (
        replay.reserve(_proposal("c", available=8, entry=9, exit=10, reserve="81")).status
        == "capacity_blocked"
    )


def test_unknown_entry_retains_reservation_until_explicit_safe_cancel(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    assert replay.enter("a", signal_bar=_bar(0), execution_bar=None).status == "quote_unknown"
    assert replay.enter("a", **_pair(1, "70")).status == "reservation_exceeded"
    assert not _fills(replay)
    assert _snapshot(replay, 5).pending_reservations == 60
    replay = _replay(tmp_path)
    assert _snapshot(replay, 5).pending_reservations == 60
    assert replay.cancel("a", at=T + timedelta(minutes=5)).status == "canceled"
    assert _snapshot(replay, 5).available_capacity == 100
    assert replay.enter("a", **_pair(1)).status == "canceled"


def test_unknown_inputs_never_become_trades_or_zero_nav(tmp_path):
    replay = _replay(tmp_path)
    unknown = replace(_proposal(), input_known=False)
    assert replay.reserve(unknown).status == "input_unknown"
    assert replay.enter("a", **_pair(1)).status == "input_unknown"
    assert not _fills(replay)
    assert _snapshot(replay, 1).lots[0].status == "input_unknown"


def test_unknown_exit_preserves_owned_lot_and_unknown_mtm(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    replay.enter("a", **_pair(1))
    assert replay.exit("a", signal_bar=None, execution_bar=None).status == "quote_unknown"
    snap = _snapshot(replay, 6)
    assert snap.nav is None
    assert snap.unknown_marks == (("US", "QQQ"),)
    assert snap.open_basis == 60
    assert snap.lots[0].realized_pnl is None
    assert _snapshot(replay, 6, {("US", "QQQ"): _bar(5, "50")}).nav == 990
    for bar in (_bar(4), _bar(6), _bar(5, symbol="SPY"), _bar(5, complete=False)):
        assert _snapshot(replay, 6, {("US", "QQQ"): bar}).nav is None


def test_same_symbol_exit_attribution_is_owned_lot_not_native_fifo(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal("a", reserve="30", exit=8))
    replay.reserve(_proposal("b", quantity="2", reserve="60", exit=6))
    replay.enter("a", **_pair(1, "20"))
    replay.enter("b", **_pair(1, "30"))
    replay.exit("b", **_pair(6, "25"))
    snap = _snapshot(replay, 6)
    assert [(lot.status, lot.entry_cost, lot.realized_pnl) for lot in snap.lots] == [
        ("open", D("20"), None),
        ("closed", D("60"), D("-10")),
    ]
    assert replay.broker.account().quantity(market="US", symbol="QQQ") == 1
    assert snap.available_capacity == 70
    assert replay.exit("b", **_pair(6, "25")).status == "filled"
    assert len(_fills(replay)) == 3
    with pytest.raises(ValueError, match="no owned proposal"):
        replay.exit("foreign", **_pair(6))
    replay.exit("a", **_pair(8, "22"))
    assert _snapshot(replay, 8).realized_pnl == -8


def test_restart_and_duplicate_actions_do_not_duplicate_events(tmp_path):
    replay = _replay(tmp_path)
    proposal = _proposal()
    replay.reserve(proposal)
    replay.enter("a", **_pair(1))
    before = [e.to_record() for e in replay.broker.event_store.iter_events()]
    restarted = _replay(tmp_path)
    assert restarted.reserve(proposal).status == "open"
    assert restarted.enter("a", **_pair(1)).status == "filled"
    assert [e.to_record() for e in restarted.broker.event_store.iter_events()] == before
    with pytest.raises(ValueError, match="does not match"):
        restarted.enter("a", **_pair(1, "59"))
    with pytest.raises(ValueError, match="identity changed"):
        restarted.reserve(replace(proposal, cohort_id="other"))
    with pytest.raises(ValueError, match="config"):
        _replay(tmp_path, fee="1")


@pytest.mark.parametrize("failure_stage", ["fill", "local_paper_portfolio_snapshot"])
def test_restart_after_native_acceptance_or_fill_interruption(tmp_path, monkeypatch, failure_stage):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    append = replay.broker.event_store.append

    def fail(event):
        if event.event_type == failure_stage:
            raise RuntimeError("invented interruption")
        return append(event)

    monkeypatch.setattr(replay.broker.event_store, "append", fail)
    with pytest.raises(RuntimeError, match="invented interruption"):
        replay.enter("a", **_pair(1))
    restarted = _replay(tmp_path)
    interrupted = _snapshot(restarted, 1)
    assert interrupted.pending_reservations + interrupted.open_basis == 60
    assert restarted.enter("a", **_pair(1)).status == "filled"
    assert len(_fills(restarted)) == 1
    assert _snapshot(restarted, 1).pending_reservations == 0
    assert _snapshot(restarted, 1).open_basis == 60


def test_foreign_inventory_and_unbound_local_orders_rejected(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    replay.broker.event_store.append(
        Event(
            event_type="fill",
            created_at=T,
            payload=dict(
                source="local_paper",
                client_order_id="foreign",
                market="US",
                symbol="QQQ",
                side="buy",
                quantity="1",
                price="1",
                fee="0",
            ),
        )
    )
    with pytest.raises(ValueError, match="unbound"):
        _replay(tmp_path)


def test_clock_and_incomplete_pair_fail_closed_before_native_submit(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    for pair in (
        _pair(2),
        dict(signal_bar=_bar(0), execution_bar=_bar(1, complete=False)),
        dict(signal_bar=_bar(0, symbol="SPY"), execution_bar=_bar(1)),
        dict(signal_bar=_bar(-1), execution_bar=_bar(1)),
        dict(signal_bar=_bar(0), execution_bar=replace(_bar(1), timeframe=Timeframe.M5)),
    ):
        assert replay.enter("a", **pair).status == "quote_unknown"
    assert not _fills(replay)
    replay.enter("a", **_pair(1))
    with pytest.raises(ValueError, match="chronological"):
        replay.reserve(_proposal("backdated"))
    with pytest.raises(ValueError, match="future replay state"):
        _snapshot(replay, 0)


def test_terminal_native_rejection_keeps_reservation_until_explicit_cancel(tmp_path):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())
    # An actual native rejection, not a mocked financial return.
    emergency_path = tmp_path / "emergency.json"
    emergency_path.write_text("not valid emergency state", encoding="ascii")
    result = replay.enter("a", **_pair(1))
    assert result.status == "emergency_stop_active"
    before = len(list(replay.broker.event_store.iter_events()))
    assert replay.enter("a", **_pair(1)).status == "native_order_closed"
    assert len(list(replay.broker.event_store.iter_events())) == before
    assert _snapshot(replay, 1).pending_reservations == 60
    replay.cancel("a", at=T + timedelta(minutes=1))
    assert _snapshot(replay, 1).available_capacity == 100


def test_pending_native_order_can_be_explicitly_canceled_after_restart(tmp_path, monkeypatch):
    replay = _replay(tmp_path)
    replay.reserve(_proposal())

    def interruption(*args, **kwargs):
        raise RuntimeError("before fill")

    monkeypatch.setattr(replay.broker, "fill_next_bar", interruption)
    with pytest.raises(RuntimeError, match="before fill"):
        replay.enter("a", **_pair(1))
    replay = _replay(tmp_path)
    replay.cancel("a", at=T + timedelta(minutes=1))
    assert _snapshot(replay, 1).pending_reservations == 0
    assert not _fills(replay)


@pytest.mark.parametrize("field,value", [("fee", "10000"), ("slip", "10000")])
def test_cost_contract_cannot_make_sale_proceeds_negative(tmp_path, field, value):
    with pytest.raises(ValueError, match="costs below"):
        _replay(tmp_path, **{field: value})


def test_deterministic_replay_of_frozen_stream(tmp_path):
    def run(root):
        replay = _replay(root, fee="10", slip="10")
        replay.reserve(_proposal(reserve="65"))
        replay.enter("a", **_pair(1))
        replay.exit("a", **_pair(6, "61"))
        return _snapshot(replay, 6), [
            e.to_record() for e in replay.broker.event_store.iter_events()
        ]

    assert run(tmp_path / "first") == run(tmp_path / "second")


def test_invented_bar_proposal_real_local_fill_never_network_or_credentials(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/credential access forbidden")

    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path.name.startswith(".env") or "credential" in path.name.lower():
            forbidden()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "open", guarded_open)
    replay = _replay(tmp_path)
    assert replay.reserve(_proposal()).status == "reserved"
    entry = replay.enter("a", **_pair(1))
    exit = replay.exit("a", **_pair(6, "61"))
    assert entry.fill is not None and exit.fill is not None
    assert entry.fill.source == exit.fill.source == "local_paper"
    assert _snapshot(replay, 6).nav == 1001


@pytest.mark.parametrize("kwargs", [dict(quantity="0"), dict(reserve="NaN")])
def test_invalid_proposal_values_rejected(kwargs):
    with pytest.raises((ValueError, ArithmeticError)):
        _proposal(**kwargs)
