"""Shared-capacity LOCAL replay for Engine's frozen dated proposal streams.

The caller supplies chronological entry/exit Bar pairs and exact-clock marks;
this module does not acquire data, select models, or change broker risk. One
dedicated EventStore is one synthetic account, not one account per cohort.
Loss debits are cumulative negative *closed-lot* PnL (profits never refill them).
LocalPaperBroker retains its next-bar, rounding, emergency and offline semantics.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

from thericher_v2.contracts import Bar, OrderIntent, Timeframe, positive, require_utc
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.local_paper import LocalPaperBroker, LocalPaperFill
from thericher_v2.state import Event, EventStore

_ZERO = Decimal("0")
_PREFIX = "capacity_replay_"


@dataclass(frozen=True)
class CapacityProposal:
    """One immutable long-only lot; reservation includes entry fees/slippage.

    Quantity and maximum all-in cost are frozen by the caller, not sized from
    future prices here. Unknown inputs cannot become an implicit cash signal.
    """

    lot_id: str
    cohort_id: str
    market: str
    symbol: str
    quantity: Decimal
    max_entry_cost: Decimal
    available_at: datetime
    entry_at: datetime
    exit_at: datetime
    input_known: bool = True

    def __post_init__(self) -> None:
        for name in ("lot_id", "cohort_id", "market", "symbol"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("market", "symbol"):
            object.__setattr__(self, name, getattr(self, name).upper())
        for name in ("quantity", "max_entry_cost"):
            value = positive(getattr(self, name), name)
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        for name in ("available_at", "entry_at", "exit_at"):
            object.__setattr__(self, name, require_utc(getattr(self, name), name))
        if not self.available_at <= self.entry_at < self.exit_at:
            raise ValueError("require available_at <= entry_at < exit_at")
        if not isinstance(self.input_known, bool):
            raise ValueError("input_known must be boolean")


@dataclass(frozen=True)
class CapacityLot:
    proposal: CapacityProposal
    status: str
    entry_cost: Decimal = _ZERO
    realized_pnl: Decimal | None = None


@dataclass(frozen=True)
class CapacitySnapshot:
    cash: Decimal
    envelope: Decimal
    open_basis: Decimal
    pending_reservations: Decimal
    realized_losses: Decimal
    realized_pnl: Decimal
    available_capacity: Decimal
    nav: Decimal | None
    unknown_marks: tuple[tuple[str, str], ...]
    lots: tuple[CapacityLot, ...]
    source: str = "local_paper"


@dataclass(frozen=True)
class CapacityAction:
    status: str
    fill: LocalPaperFill | None = None


def _payload(proposal: CapacityProposal) -> dict[str, object]:
    result = asdict(proposal)
    for key, value in result.items():
        if isinstance(value, Decimal):
            result[key] = str(value.normalize())
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


def _proposal(payload: dict[str, object]) -> CapacityProposal:
    values = dict(payload)
    for key in ("quantity", "max_entry_cost"):
        values[key] = Decimal(str(values[key]))
    for key in ("available_at", "entry_at", "exit_at"):
        values[key] = datetime.fromisoformat(str(values[key]))
    return CapacityProposal(**values)


def _order(proposal: CapacityProposal, side: str) -> OrderIntent:
    digest = hashlib.sha256(proposal.lot_id.encode()).hexdigest()
    return OrderIntent(
        client_order_id=f"capacity-{digest}-{side}",
        decision_id=proposal.cohort_id,
        market=proposal.market,
        symbol=proposal.symbol,
        side=side,
        quantity=proposal.quantity,
        limit_price=None,
        created_at=proposal.entry_at if side == "buy" else proposal.exit_at,
    )


class CapacityPaperReplay:
    """Single-writer research adapter using the existing append-only local log.

    Call reserve in availability order, then enter/exit in clock order (exit
    before entry when simultaneous). Reconstruct on restart with the same log
    and config. An unknown entry keeps its reservation; only explicit cancel
    releases a definitely unfilled lot. No late exit/price substitution occurs.
    Large offline runs can use EventStore(rebuild_sqlite_on_append=False);
    the JSONL events, not SQLite views or cached portfolio snapshots, own state.
    """

    def __init__(
        self,
        *,
        event_store: EventStore,
        emergency_store: EmergencyStore,
        initial_balance: Decimal,
        fee_bps: Decimal,
        slippage_bps: Decimal,
    ) -> None:
        self.broker = LocalPaperBroker(
            event_store=event_store,
            emergency_store=emergency_store,
            starting_cash=positive(initial_balance, "initial_balance"),
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
        values = (self.broker.starting_cash, self.broker.fee_bps, self.broker.slippage_bps)
        if any(not value.is_finite() for value in values) or any(
            value >= 10000 for value in values[1:]
        ):
            raise ValueError("finite costs below 10000 bps required")
        self.envelope = self.broker.starting_cash / Decimal("10")
        config = dict(
            zip(
                ("initial_balance", "fee_bps", "slippage_bps"),
                (str(value.normalize()) for value in values),
                strict=True,
            )
        )
        events = list(event_store.iter_events())
        if not events:
            # Bind on first proposal, not to wall-clock time (replay is historical).
            self._config = config
        elif events[0].event_type != _PREFIX + "config" or events[0].payload != {
            "source": "local_paper",
            **config,
        }:
            raise ValueError("dedicated local replay log/config required")
        else:
            self._config = config
        self._state()

    def _append(self, kind: str, at: datetime, **payload: object) -> None:
        self.broker.event_store.append(
            Event(
                event_type=_PREFIX + kind,
                created_at=at,
                payload={"source": "local_paper", **payload},
            )
        )

    def _chronological(self, at: datetime) -> None:
        require_utc(at)
        events = list(self.broker.event_store.iter_events())
        if events and at < max(event.created_at for event in events):
            raise ValueError("new replay effects must be chronological")

    def _state(self) -> tuple[dict[str, CapacityLot], dict[str, Event]]:
        proposals: dict[str, tuple[CapacityProposal, str]] = {}
        fills: dict[str, Event] = {}
        canceled: set[str] = set()
        events = list(self.broker.event_store.iter_events())
        for event in events:
            if event.payload.get("source") != "local_paper":
                raise ValueError("foreign source in dedicated replay log")
            if event.event_type == _PREFIX + "proposal":
                proposal = _proposal(event.payload["proposal"])
                if proposal.lot_id in proposals:
                    raise ValueError("duplicate proposal in replay log")
                proposals[proposal.lot_id] = (proposal, str(event.payload["status"]))
            elif event.event_type == _PREFIX + "cancel":
                canceled.add(str(event.payload["lot_id"]))
        if canceled - proposals.keys():
            raise ValueError("cancellation has no owned proposal")
        expected = {
            _order(p, side).client_order_id: _order(p, side)
            for p, status in proposals.values()
            if status == "reserved"
            for side in ("buy", "sell")
        }
        for event in events:
            if event.event_type in {_PREFIX + "config", _PREFIX + "proposal", _PREFIX + "cancel"}:
                continue
            if event.event_type == "local_paper_portfolio_snapshot":
                continue  # Derived only; account/lot balances come from actual fills.
            order = expected.get(str(event.payload.get("client_order_id")))
            if order is None:
                raise ValueError("unbound local order/fill; foreign inventory is not adopted")
            if (
                event.payload.get("market"),
                event.payload.get("symbol"),
                event.payload.get("side"),
                Decimal(str(event.payload.get("quantity"))),
            ) != (
                order.market,
                order.symbol,
                order.side,
                order.quantity,
            ):
                raise ValueError("local order/fill does not match frozen lot")
            if event.event_type == "fill":
                if order.client_order_id in fills or event.created_at != order.created_at:
                    raise ValueError("duplicate or mistimed local fill")
                fills[order.client_order_id] = event
            elif event.event_type not in {
                "local_paper_order_accepted",
                "local_paper_order_rejected",
                "local_paper_order_canceled",
            }:
                raise ValueError("unsupported event in dedicated replay log")
            elif (
                event.payload.get("decision_id") != order.decision_id
                or event.payload.get("created_at") != order.created_at.isoformat()
                or event.payload.get("limit_price") is not None
                or event.payload.get("valid_until") is not None
            ):
                raise ValueError("local order identity does not match frozen lot")
        lots = {}
        for key, (proposal, status) in proposals.items():
            buy = fills.get(_order(proposal, "buy").client_order_id)
            sell = fills.get(_order(proposal, "sell").client_order_id)
            cost = _ZERO if buy is None else self._value(buy, buying=True)
            pnl = None if sell is None else self._value(sell, buying=False) - cost
            if cost > proposal.max_entry_cost:
                raise ValueError("recorded entry exceeds frozen reservation")
            if sell is not None and buy is None:
                raise ValueError("exit has no owned entry")
            if key in canceled:
                if buy is not None:
                    raise ValueError("cannot cancel an owned lot")
                status = "canceled"
            elif sell is not None:
                status = "closed"
            elif buy is not None:
                status = "open"
            lots[key] = CapacityLot(proposal, status, cost, pnl)
        return lots, fills

    @staticmethod
    def _value(event: Event, *, buying: bool) -> Decimal:
        payload = event.payload
        notional = Decimal(str(payload["quantity"])) * Decimal(str(payload["price"]))
        fee = Decimal(str(payload["fee"]))
        return notional + fee if buying else notional - fee

    def snapshot(
        self,
        *,
        at: datetime,
        marks: Mapping[tuple[str, str], Bar] | None = None,
    ) -> CapacitySnapshot:
        require_utc(at)
        events = list(self.broker.event_store.iter_events())
        if events and at < max(event.created_at for event in events):
            raise ValueError("snapshot cannot use a future replay state")
        lots, _ = self._state()
        account = self.broker.account()
        basis = sum((lot.entry_cost for lot in lots.values() if lot.status == "open"), _ZERO)
        pending = sum(
            (lot.proposal.max_entry_cost for lot in lots.values() if lot.status == "reserved"),
            _ZERO,
        )
        pnl = sum(
            (lot.realized_pnl for lot in lots.values() if lot.realized_pnl is not None), _ZERO
        )
        losses = sum(
            (
                max(-lot.realized_pnl, _ZERO)
                for lot in lots.values()
                if lot.realized_pnl is not None
            ),
            _ZERO,
        )
        available = max(
            _ZERO, min(self.envelope - basis - pending - losses, account.cash - pending)
        )
        nav = account.cash
        unknown = []
        for position in account.positions:
            key = (position.market, position.symbol)
            bar = (marks or {}).get(key)
            if (
                bar is None
                or not bar.complete
                or not bar.close.is_finite()
                or bar.end_ts != at
                or (bar.market, bar.symbol) != key
            ):
                unknown.append(key)
            else:
                nav += position.quantity * bar.close
        return CapacitySnapshot(
            account.cash,
            self.envelope,
            basis,
            pending,
            losses,
            pnl,
            available,
            None if unknown else nav,
            tuple(unknown),
            tuple(lots[key] for key in sorted(lots)),
        )

    def reserve(self, proposal: CapacityProposal) -> CapacityAction:
        lots, _ = self._state()
        if proposal.lot_id in lots:
            lot = lots[proposal.lot_id]
            if lot.proposal != proposal:
                raise ValueError("frozen proposal identity changed")
            return CapacityAction(lot.status)
        self._chronological(proposal.available_at)
        status = "input_unknown" if not proposal.input_known else "reserved"
        if (
            status == "reserved"
            and proposal.max_entry_cost
            > self.snapshot(
                at=proposal.available_at,
            ).available_capacity
        ):
            status = "capacity_blocked"
        if not list(self.broker.event_store.iter_events()):
            self._append("config", proposal.available_at, **self._config)
        self._append("proposal", proposal.available_at, proposal=_payload(proposal), status=status)
        return CapacityAction(status)

    def cancel(self, lot_id: str, *, at: datetime) -> CapacityAction:
        lots, _ = self._state()
        lot = lots[lot_id]
        if lot.status == "canceled":
            return CapacityAction("canceled")
        if lot.status != "reserved":
            raise ValueError("only an unfilled reserved lot can be canceled")
        self._chronological(at)
        order_id = _order(lot.proposal, "buy").client_order_id
        history = [
            e
            for e in self.broker.event_store.iter_events()
            if e.payload.get("client_order_id") == order_id
        ]
        if history and history[-1].event_type == "local_paper_order_accepted":
            self.broker.cancel_order(order_id, canceled_at=at)
        self._append("cancel", at, lot_id=lot_id)
        return CapacityAction("canceled")

    def enter(
        self,
        lot_id: str,
        *,
        signal_bar: Bar | None,
        execution_bar: Bar | None,
    ) -> CapacityAction:
        return self._execute(lot_id, "buy", signal_bar, execution_bar)

    def exit(
        self,
        lot_id: str,
        *,
        signal_bar: Bar | None,
        execution_bar: Bar | None,
    ) -> CapacityAction:
        return self._execute(lot_id, "sell", signal_bar, execution_bar)

    def _execute(
        self,
        lot_id: str,
        side: str,
        signal: Bar | None,
        execution: Bar | None,
    ) -> CapacityAction:
        lots, fills = self._state()
        if lot_id not in lots:
            raise ValueError("no owned proposal")
        lot = lots[lot_id]
        order = _order(lot.proposal, side)
        recorded = order.client_order_id in fills
        required = "reserved" if side == "buy" else "open"
        if not recorded and lot.status != required:
            return CapacityAction("no_owned_lot" if side == "sell" else lot.status)
        if signal is None or execution is None:
            return CapacityAction("quote_unknown")
        if (
            not signal.complete
            or not execution.complete
            or not execution.open.is_finite()
            or execution.start_ts != order.created_at
            or signal.end_ts > order.created_at
            or execution.timeframe != signal.timeframe
            or (signal.timeframe != Timeframe.D1 and signal.end_ts != execution.start_ts)
            or (signal.market, signal.symbol) != (order.market, order.symbol)
            or (execution.market, execution.symbol) != (order.market, order.symbol)
        ):
            return CapacityAction("quote_unknown")
        if not recorded:
            self._chronological(order.created_at)
            if side == "buy":
                # Same fixed quantization as LocalPaper; actual fill is still native.
                price = (execution.open * (1 + self.broker.slippage_bps / 10000)).quantize(
                    Decimal("0.0001")
                )
                notional = price * order.quantity
                cost = notional + (notional * self.broker.fee_bps / 10000).quantize(
                    Decimal("0.0001")
                )
                if cost > lot.proposal.max_entry_cost:
                    return CapacityAction("reservation_exceeded")
        history = [
            e
            for e in self.broker.event_store.iter_events()
            if e.payload.get("client_order_id") == order.client_order_id
        ]
        if (
            not recorded
            and history
            and history[-1].event_type
            in {
                "local_paper_order_rejected",
                "local_paper_order_canceled",
            }
        ):
            return CapacityAction("native_order_closed")
        accepted = any(e.event_type == "local_paper_order_accepted" for e in history)
        if not accepted:
            result = self.broker.submit_order(order)
            if result.status != "accepted":
                return CapacityAction(result.reason)
        result = self.broker.fill_next_bar(
            order.client_order_id,
            signal_bar=signal,
            execution_bar=execution,
        )
        return CapacityAction(
            "filled" if result.fill is not None else result.order_result.reason, result.fill
        )
