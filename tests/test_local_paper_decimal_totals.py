"""Fractional FIFO grouped totals must reconcile without changing recorded fills."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, getcontext, localcontext

import pytest

from thericher_v2.contracts import OrderIntent
from thericher_v2.execution.local_paper import (
    replay_local_paper_account,
    replay_local_paper_decision_pnl,
    replay_local_paper_realized_pnl,
)
from thericher_v2.state import Event, EventStore


def _events(rows):
    events = []
    clock = datetime(2026, 5, 18, 14, tzinfo=UTC)
    for i, (symbol, side, quantity, price, fee, decision) in enumerate(rows):
        when = clock + timedelta(minutes=i)
        order = OrderIntent(
            client_order_id=f"fractional-{i}",
            symbol=symbol,
            market="US",
            side=side,
            quantity=quantity,
            limit_price=None,
            decision_id=decision,
            created_at=when,
        )
        payload = {
            "source": "local_paper",
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "market": order.market,
            "side": order.side,
            "quantity": str(order.quantity),
            "decision_id": order.decision_id,
            "created_at": when.isoformat(),
        }
        events.append(
            Event(
                event_type="local_paper_order_accepted",
                created_at=when,
                payload=payload,
                seq=2 * i + 1,
            )
        )
        events.append(
            Event(
                event_type="fill",
                created_at=when,
                payload=payload | {"price": str(price), "fee": str(fee)},
                seq=2 * i + 2,
            )
        )
    return tuple(events)


def test_grouped_repeating_fractional_regression():
    # Same five-symbol, 10 -> 100, nonzero-fee P2 fixture as the frozen external reproducer.
    with localcontext() as context:
        context.prec = 50
        quantity = Decimal(1) / (1 + Decimal(".0005") * Decimal(".5")) * Decimal(".1") / 10
        rows = [
            (
                f"SYN{i}",
                "buy",
                quantity,
                Decimal(10),
                quantity * 10 * Decimal(".0005"),
                "grouped-entry",
            )
            for i in range(5)
        ]
        rows += [
            (
                f"SYN{i}",
                "sell",
                quantity,
                Decimal(100),
                quantity * 100 * Decimal(".0005"),
                "grouped-exit",
            )
            for i in range(5)
        ]
        events = _events(rows)
        aggregate = replay_local_paper_realized_pnl(events)
        result = replay_local_paper_decision_pnl(events)
        assert result.aggregate == aggregate
        assert len(result.closed_segments) == 5
        for total in (
            *result.entry_decision_totals,
            *result.exit_decision_totals,
            *result.decision_pair_totals,
        ):
            assert total.realized_after_cost_pnl == total.gross_pnl - total.fee_total
            assert total.realized_after_cost_pnl != aggregate.realized_after_cost_pnl
        assert aggregate.realized_after_cost_pnl == sum(
            (segment.realized_after_cost_pnl for segment in result.closed_segments), Decimal(0)
        )


def _partial_history(quantity):
    return _events(
        [
            ("SYNA", "buy", quantity * 3, Decimal(10), quantity / 5, "entry-a"),
            ("SYNA", "buy", quantity * 2, Decimal(11), quantity / 7, "entry-b"),
            ("SYNA", "sell", quantity * 2, Decimal(12), quantity / 11, "exit-a"),
            ("SYNA", "sell", quantity * 2, Decimal(13), quantity / 13, "exit-a"),
            ("SYNA", "sell", quantity / 2, Decimal(9), quantity / 17, "exit-b"),
            ("SYNB", "buy", quantity, Decimal(100), quantity / 23, "entry-a"),
            ("SYNB", "sell", quantity / 2, Decimal(101), quantity / 29, "exit-b"),
        ]
    )


def _assert_total(total, segments):
    gross, fees, quantity = Decimal(0), Decimal(0), Decimal(0)
    for segment in segments:
        gross += segment.gross_pnl
        fees = fees + segment.entry_fee + segment.exit_fee
        quantity += segment.quantity
    assert total.closed_segment_count == len(segments)
    assert total.closed_quantity == quantity
    assert total.gross_pnl == gross
    assert total.fee_total == fees
    assert total.realized_after_cost_pnl == gross - fees


@pytest.mark.parametrize("precision", [9, 28, 50])
@pytest.mark.parametrize("rounding", [ROUND_HALF_EVEN, ROUND_DOWN])
@pytest.mark.parametrize("scale", ["1e-12", "1", "1e20"])
def test_partial_FIFO_multi_decision_role_and_pair_totals(precision, rounding, scale):
    previous = getcontext().copy()
    with localcontext() as context:
        context.prec, context.rounding = precision, rounding
        events = _partial_history(Decimal(scale) / 3)
        before = tuple((event.event_type, dict(event.payload), event.seq) for event in events)
        aggregate = replay_local_paper_realized_pnl(events)
        result = replay_local_paper_decision_pnl(events)
        assert result.aggregate == aggregate
        assert result == replay_local_paper_decision_pnl(reversed(events))
        assert len(result.closed_segments) == 5
        assert result.aggregate.open_quantity > 0
        assert result.aggregate.local_paper_fill_count == 7
        assert [total.decision_id for total in result.entry_decision_totals] == [
            "entry-a",
            "entry-b",
        ]
        assert [total.decision_id for total in result.exit_decision_totals] == ["exit-a", "exit-b"]
        assert len(result.decision_pair_totals) == 4
        for segment in result.closed_segments:
            assert segment.gross_pnl - segment.entry_fee - segment.exit_fee == (
                segment.realized_after_cost_pnl
            )
            assert segment.entry_fee > 0 and segment.exit_fee > 0
            assert segment.market == "US" and segment.entry_filled_at < segment.exit_filled_at
        for total in result.entry_decision_totals:
            _assert_total(
                total,
                [s for s in result.closed_segments if s.entry_decision_id == total.decision_id],
            )
        for total in result.exit_decision_totals:
            _assert_total(
                total,
                [s for s in result.closed_segments if s.exit_decision_id == total.decision_id],
            )
        for total in result.decision_pair_totals:
            _assert_total(
                total,
                [
                    s
                    for s in result.closed_segments
                    if (s.entry_decision_id, s.exit_decision_id)
                    == (total.entry_decision_id, total.exit_decision_id)
                ],
            )
        assert (
            tuple((event.event_type, dict(event.payload), event.seq) for event in events) == before
        )
    assert getcontext().prec == previous.prec and getcontext().rounding == previous.rounding
    assert getcontext().traps == previous.traps and getcontext().flags == previous.flags


@pytest.mark.parametrize(
    "field", ["entry_decision_totals", "exit_decision_totals", "decision_pair_totals"]
)
def test_tampered_totals_still_rejected_exactly(field):
    with localcontext() as context:
        context.prec = 50
        result = replay_local_paper_decision_pnl(_partial_history(Decimal(1) / 3))
        totals = getattr(result, field)
        with pytest.raises(ValueError, match="does not reconcile fees"):
            replace(
                totals[0],
                realized_after_cost_pnl=totals[0].realized_after_cost_pnl + Decimal("1e-40"),
            )
        changed = replace(
            totals[0],
            gross_pnl=totals[0].gross_pnl + 1,
            realized_after_cost_pnl=totals[0].gross_pnl + 1 - totals[0].fee_total,
        )
        with pytest.raises(ValueError, match="totals do not reconcile"):
            replace(result, **{field: (changed, *totals[1:])})


def test_account_cash_and_durable_events_unchanged(tmp_path):
    with localcontext() as context:
        context.prec = 50
        events = _partial_history(Decimal(1) / 3)
        store = EventStore(
            tmp_path / "synthetic.sqlite",
            tmp_path / "synthetic.jsonl",
            rebuild_sqlite_on_append=False,
        )
        for event in events:
            store.append(event)
        cash_before = replay_local_paper_account(store, starting_cash=Decimal(10000))
        bytes_before = store.jsonl_path.read_bytes()
        result = replay_local_paper_decision_pnl(store.iter_events())
        assert result.aggregate == replay_local_paper_realized_pnl(store.iter_events())
        restored = EventStore(store.db_path, store.jsonl_path, rebuild_sqlite_on_append=False)
        assert replay_local_paper_account(restored, starting_cash=Decimal(10000)) == cash_before
        assert store.jsonl_path.read_bytes() == bytes_before
        assert result == replay_local_paper_decision_pnl(restored.iter_events())


def test_empty_projection_unchanged():
    result = replay_local_paper_decision_pnl(())
    assert result.aggregate == replay_local_paper_realized_pnl(())
    assert result.closed_segments == result.entry_decision_totals == ()
    assert result.exit_decision_totals == result.decision_pair_totals == ()
