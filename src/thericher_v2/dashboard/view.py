"""Sanitized read model and HTML view for the local paper console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path

from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE
from thericher_v2.execution.paper_account_snapshot import (
    PaperAccountSnapshot,
    read_paper_account_snapshot,
)
from thericher_v2.execution.paper_canary_runtime import (
    PaperCanaryRuntimeSnapshot,
    read_paper_canary_runtime,
)
from thericher_v2.serialization import to_jsonable
from thericher_v2.state.event_log import Event, EventStore


@dataclass(frozen=True)
class DashboardPosition:
    market: str
    symbol: str
    quantity: str


@dataclass(frozen=True)
class DashboardFill:
    market: str
    symbol: str
    side: str
    quantity: str
    price: str
    fee: str
    filled_at: str


@dataclass(frozen=True)
class DashboardDecision:
    source: str
    market: str
    symbol: str
    action: str
    confidence: str
    expected_edge_bps: str
    decided_at: str


@dataclass(frozen=True)
class DashboardSnapshot:
    mode: str
    heartbeat_utc: str
    status: str
    stop_new_orders: bool
    cancel_open_orders_requested: bool
    emergency_reason: str
    emergency_updated_at: str
    position_count: int | None
    latest_decision_count: int | None
    cash_by_currency: dict[str, str]
    message: str
    local_paper_status: str
    local_paper_fill_count: int | None
    local_paper_cash: str | None
    local_paper_cash_snapshot_at: str | None
    local_paper_pnl_status: str
    local_positions: tuple[DashboardPosition, ...] | None
    local_paper_fills: tuple[DashboardFill, ...] | None
    latest_decisions: tuple[DashboardDecision, ...] | None
    kis_holdings_status: str = "unknown"
    kis_prices_status: str = "unknown"
    kis_buying_power_status: str = "unknown"
    kis_open_orders_status: str = "unknown"
    paper_account_status: str = "unknown"
    paper_account_observed_at: str | None = None
    paper_account: PaperAccountSnapshot | None = None
    paper_canary_status: str = "unknown"
    paper_canary_reconciliation_status: str = "unknown"
    paper_canary_account_status: str = "unknown"
    paper_canary_observed_at: str | None = None
    paper_canary: PaperCanaryRuntimeSnapshot | None = None

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


@dataclass(frozen=True)
class _LocalPaperProjection:
    status: str
    fill_count: int
    cash: str | None
    cash_snapshot_at: str | None
    positions: tuple[DashboardPosition, ...]
    fills: tuple[DashboardFill, ...]


def build_snapshot(
    event_store: EventStore,
    emergency_store: EmergencyStore,
    mode: str = "off",
    *,
    paper_account_snapshot_path: Path | None = None,
    paper_canary_runtime_path: Path | None = None,
    now: datetime | None = None,
) -> DashboardSnapshot:
    current_time = now or datetime.now(UTC)
    emergency = emergency_store.read()
    try:
        events = tuple(sorted(event_store.iter_events(), key=lambda event: event.seq))
        local_paper = _project_local_paper(events)
        decisions = _project_latest_decisions(events)
        status = "local_monitor_only"
        message = "Local paper monitor only."
    except (ArithmeticError, KeyError, OSError, TypeError, ValueError):
        local_paper = _LocalPaperProjection(
            status="local_paper_replay_unavailable",
            fill_count=0,
            cash=None,
            cash_snapshot_at=None,
            positions=(),
            fills=(),
        )
        decisions = ()
        status = "local_monitor_degraded"
        message = "Local replay is unavailable."

    paper_account_read = read_paper_account_snapshot(
        paper_account_snapshot_path,
        now=current_time,
    )
    paper_account = paper_account_read.snapshot
    paper_statuses = _paper_account_statuses(paper_account_read.status)
    if paper_account_read.status == "available":
        message = f"{message} Fresh KIS paper facts are read-only."
    elif paper_account_read.status == "unavailable":
        message = f"{message} KIS paper facts are unavailable."
    else:
        message = f"{message} KIS paper facts are unknown."

    paper_canary_read = read_paper_canary_runtime(
        paper_canary_runtime_path,
        now=current_time,
    )
    paper_canary = paper_canary_read.snapshot
    if paper_canary_read.status == "available":
        message = f"{message} KIS virtual-paper canary is {paper_canary.status}."
    elif paper_canary_read.status == "unavailable":
        message = f"{message} KIS virtual-paper canary state is unavailable."

    return DashboardSnapshot(
        mode=mode,
        heartbeat_utc=current_time.isoformat(),
        status=status,
        stop_new_orders=emergency.stop_new_orders,
        cancel_open_orders_requested=emergency.cancel_open_orders_requested,
        emergency_reason=emergency.reason,
        emergency_updated_at=emergency.updated_at.isoformat(),
        position_count=None if status == "local_monitor_degraded" else len(local_paper.positions),
        latest_decision_count=None if status == "local_monitor_degraded" else len(decisions),
        cash_by_currency={},
        message=message,
        local_paper_status=local_paper.status,
        local_paper_fill_count=(
            None if status == "local_monitor_degraded" else local_paper.fill_count
        ),
        local_paper_cash=local_paper.cash,
        local_paper_cash_snapshot_at=local_paper.cash_snapshot_at,
        local_paper_pnl_status="unavailable",
        local_positions=None if status == "local_monitor_degraded" else local_paper.positions,
        local_paper_fills=None if status == "local_monitor_degraded" else local_paper.fills,
        latest_decisions=None if status == "local_monitor_degraded" else decisions,
        kis_holdings_status=paper_statuses["holdings"],
        kis_prices_status=paper_statuses["prices"],
        kis_buying_power_status=paper_statuses["reference_orderability"],
        kis_open_orders_status=paper_statuses["open_orders"],
        paper_account_status=paper_account_read.status,
        paper_account_observed_at=(
            None if paper_account is None else paper_account.observed_at.isoformat()
        ),
        paper_account=paper_account,
        paper_canary_status=(
            paper_canary.status if paper_canary is not None else paper_canary_read.status
        ),
        paper_canary_reconciliation_status=(
            "unknown" if paper_canary is None else paper_canary.reconciliation_status
        ),
        paper_canary_account_status=(
            "unknown" if paper_canary is None else paper_canary.account_status
        ),
        paper_canary_observed_at=(
            None if paper_canary is None else paper_canary.observed_at.isoformat()
        ),
        paper_canary=paper_canary,
    )


def render_dashboard(snapshot: DashboardSnapshot, *, form_nonce: str = "") -> str:
    """Render a compact, local-only operational view from a sanitized snapshot."""

    safety_state = "Paused" if snapshot.stop_new_orders else "Ready"
    cancellation_state = "Requested" if snapshot.cancel_open_orders_requested else "Not requested"
    paper_account_details = _paper_account_details(
        snapshot.paper_account,
        status=snapshot.paper_account_status,
        observed_at=snapshot.paper_account_observed_at,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TheRicher v2 Local Paper Console</title>
  <style>
    :root {{
      color-scheme: light;
      --canvas: #f6f7f8;
      --surface: #ffffff;
      --ink: #18222d;
      --muted: #63707d;
      --line: #d8dee4;
      --green: #16794d;
      --green-soft: #e8f5ed;
      --amber: #986600;
      --amber-soft: #fff4d6;
      --red: #b42318;
      --red-soft: #fff0ee;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    .shell {{ max-width: 1320px; margin: 0 auto; padding: 20px 24px 36px; }}
    .topbar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 2px solid var(--ink);
      padding-bottom: 14px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: 22px; font-weight: 700; }}
    h2 {{ font-size: 15px; font-weight: 700; }}
    .subtitle, .meta, .empty {{ color: var(--muted); }}
    .subtitle {{ margin-top: 2px; }}
    .meta {{ font-size: 12px; text-align: right; }}
    .status-band {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }}
    .metric {{ padding: 14px 16px; border-right: 1px solid var(--line); }}
    .metric:last-child {{ border-right: 0; }}
    .metric-label {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric-value {{ display: block; margin-top: 3px; font-weight: 700; }}
    .state-ready {{ color: var(--green); }}
    .state-paused {{ color: var(--red); }}
    .state-unknown {{ color: var(--amber); }}
    .section {{ border-bottom: 1px solid var(--line); padding: 22px 0; }}
    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 10px;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    form {{ margin: 0; }}
    button {{
      min-height: 34px;
      border: 1px solid var(--ink);
      border-radius: 4px;
      background: var(--surface);
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      font-weight: 650;
      padding: 6px 10px;
    }}
    button:hover {{ background: #edf1f4; }}
    .danger {{ border-color: var(--red); color: var(--red); }}
    .scope {{ color: var(--muted); font-size: 12px; }}
    .overview {{
      display: grid;
      grid-template-columns: 1.4fr repeat(3, minmax(0, 1fr));
      border: 1px solid var(--line);
      background: var(--surface);
    }}
    .overview > div {{ border-right: 1px solid var(--line); padding: 12px 14px; }}
    .overview > div:last-child {{ border-right: 0; }}
    .overview .label {{ display: block; color: var(--muted); font-size: 12px; }}
    .overview strong {{ display: block; margin-top: 3px; }}
    .two-column {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 24px;
    }}
    .two-column > div {{ min-width: 0; }}
    .table-wrap {{ max-width: 100%; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--surface); }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 12px; font-weight: 650; white-space: nowrap; }}
    td.numeric, th.numeric {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    .notice {{
      border-left: 3px solid var(--amber);
      background: var(--amber-soft);
      padding: 10px 12px;
    }}
    .tag {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      font-weight: 650;
    }}
    .tag-local {{ background: var(--green-soft); color: var(--green); }}
    .tag-unknown {{ background: var(--amber-soft); color: var(--amber); }}
    @media (max-width: 760px) {{
      .shell {{ padding: 16px; }}
      .topbar, .section-header {{ align-items: start; flex-direction: column; gap: 6px; }}
      .meta {{ text-align: left; }}
      .status-band, .overview, .two-column {{ grid-template-columns: 1fr; }}
      .metric, .overview > div {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .metric:last-child, .overview > div:last-child {{ border-bottom: 0; }}
      table {{ min-width: 540px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>TheRicher v2</h1>
        <p class="subtitle">Local paper console</p>
      </div>
      <p class="meta">Snapshot rendered {_text(snapshot.heartbeat_utc)}</p>
    </header>

    <section class="status-band" aria-label="Runtime status">
      <div class="metric">
        <span class="metric-label">Configured mode</span>
        <span class="metric-value">{_text(snapshot.mode)}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Monitor</span>
        <span class="metric-value">{_text(snapshot.status)}</span>
      </div>
      <div class="metric">
        <span class="metric-label">New entries</span>
        <span class="metric-value {_state_class(snapshot.stop_new_orders)}">{safety_state}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Cancellation</span>
        <span class="metric-value">{cancellation_state}</span>
      </div>
    </section>

    <section class="section" aria-labelledby="safety-heading">
      <div class="section-header">
        <h2 id="safety-heading">Local safety state</h2>
        <span class="scope">Local state only</span>
      </div>
      <div class="actions">
        <form method="post" action="/emergency/stop-new-orders">
          <input type="hidden" name="csrf" value="{_text(form_nonce)}">
          <button class="danger" type="submit">Pause new entries</button>
        </form>
        <form method="post" action="/emergency/cancel-open-orders">
          <input type="hidden" name="csrf" value="{_text(form_nonce)}">
          <button type="submit">Request local cancellation</button>
        </form>
      </div>
      <p class="scope">
        Reason: {_text(snapshot.emergency_reason)}. Updated {_text(snapshot.emergency_updated_at)}.
      </p>
    </section>

    <section class="section" aria-labelledby="local-heading">
      <div class="section-header">
        <h2 id="local-heading">Local paper replay</h2>
        <span class="tag tag-local">{_text(snapshot.local_paper_status)}</span>
      </div>
      <div class="overview">
        <div>
          <span class="label">Simulator cash snapshot</span>
          <strong>{_optional_text(snapshot.local_paper_cash)}</strong>
        </div>
        <div>
          <span class="label">Positions</span>
          <strong>{_optional_count(snapshot.position_count)}</strong>
        </div>
        <div>
          <span class="label">Local fills</span>
          <strong>{_optional_count(snapshot.local_paper_fill_count)}</strong>
        </div>
        <div>
          <span class="label">Realized PnL</span>
          <strong>{_text(snapshot.local_paper_pnl_status)}</strong>
        </div>
      </div>
      <p class="scope">
        Cash snapshot evidence: {_optional_text(snapshot.local_paper_cash_snapshot_at)}
      </p>
    </section>

    <section class="section two-column" aria-label="Local paper positions and decisions">
      <div>
        <div class="section-header">
          <h2>Local positions</h2><span class="meta">Replayed fills only</span>
        </div>
        {_positions_table(snapshot.local_positions, unavailable=_replay_unavailable(snapshot))}
      </div>
      <div>
        <div class="section-header">
          <h2>Recorded decisions</h2>
          <span class="meta">{_decision_count_label(snapshot.latest_decision_count)}</span>
        </div>
        {_decisions_table(snapshot.latest_decisions, unavailable=_replay_unavailable(snapshot))}
      </div>
    </section>

    <section class="section" aria-labelledby="fills-heading">
      <div class="section-header">
        <h2 id="fills-heading">Recent local fills</h2>
        <span class="meta">source: local_paper</span>
      </div>
      <div class="table-wrap">
        {_fills_table(snapshot.local_paper_fills, unavailable=_replay_unavailable(snapshot))}
      </div>
    </section>

    <section class="section" aria-labelledby="broker-heading">
      <div class="section-header">
        <h2 id="broker-heading">KIS broker state</h2>
        <span class="tag {_paper_account_tag(snapshot.paper_account_status)}">
          {_text(snapshot.paper_account_status)}
        </span>
      </div>
      <div class="notice">{_text(snapshot.message)}</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Fact</th><th>Status</th></tr></thead>
          <tbody>
            <tr>
              <td>KIS holdings</td>
              <td class="state-unknown">{_text(snapshot.kis_holdings_status)}</td>
            </tr>
            <tr>
              <td>KIS price quotes</td>
              <td class="state-unknown">{_text(snapshot.kis_prices_status)}</td>
            </tr>
            <tr>
              <td>KIS reference orderability</td>
              <td class="state-unknown">{_text(snapshot.kis_buying_power_status)}</td>
            </tr>
            <tr>
              <td>KIS open orders</td>
              <td class="state-unknown">{_text(snapshot.kis_open_orders_status)}</td>
            </tr>
            <tr>
              <td>Virtual-paper canary</td>
              <td class="state-unknown">{_text(snapshot.paper_canary_status)}</td>
            </tr>
            <tr>
              <td>Canary reconciliation</td>
              <td class="state-unknown">{_text(snapshot.paper_canary_reconciliation_status)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {paper_account_details}
      {_paper_canary_details(snapshot)}
    </section>
  </main>
</body>
</html>"""


def _paper_account_statuses(status: str) -> dict[str, str]:
    if status == "available":
        return {
            "holdings": "available",
            "prices": "unknown",
            "reference_orderability": "reference_only",
            "open_orders": "available",
        }
    if status == "unavailable":
        return {
            "holdings": "unavailable",
            "prices": "unavailable",
            "reference_orderability": "unavailable",
            "open_orders": "unavailable",
        }
    return {
        "holdings": "unknown",
        "prices": "unknown",
        "reference_orderability": "unknown",
        "open_orders": "unknown",
    }


def _paper_account_tag(status: str) -> str:
    return "tag-local" if status == "available" else "tag-unknown"


def _paper_canary_details(snapshot: DashboardSnapshot) -> str:
    canary = snapshot.paper_canary
    if canary is None:
        return ""
    return f"""
      <p class="scope">
        Canary observed {_optional_text(snapshot.paper_canary_observed_at)}.
        Account facts: {_text(snapshot.paper_canary_account_status)}.
        Positions: {canary.position_count}. Open orders: {canary.open_order_count}.
      </p>"""


def _paper_account_details(
    account: PaperAccountSnapshot | None,
    *,
    status: str,
    observed_at: str | None,
) -> str:
    if account is None:
        message = (
            "No fresh KIS paper snapshot"
            if status == "unknown"
            else "KIS snapshot unavailable"
        )
        return f'<p class="scope">{_text(message)}</p>'
    assert account.orderable_foreign_funds is not None
    assert account.reference_orderability is not None
    return f"""
      <div class="overview">
        <div>
          <span class="label">KIS orderable foreign funds</span>
          <strong>
            {_text(account.orderable_foreign_funds.amount)}
            {_text(account.orderable_foreign_funds.currency)}
          </strong>
        </div>
        <div>
          <span class="label">Reference orderability</span>
          <strong>
            {_text(account.reference_orderability.orderable_funds)}
            {_text(account.reference_orderability.currency)}
          </strong>
        </div>
        <div>
          <span class="label">Verified positions</span>
          <strong>{len(account.positions)}</strong>
        </div>
        <div>
          <span class="label">Verified open orders</span>
          <strong>{len(account.open_orders)}</strong>
        </div>
      </div>
      <p class="scope">
        Observed {_optional_text(observed_at)}. Orderable foreign funds are not
        settled cash, account equity, margin capacity, or general buying power.
        Reference orderability is for
        {_text(account.reference_orderability.reference_exchange)}
        {_text(account.reference_orderability.reference_symbol)} at
        {_text(account.reference_orderability.reference_price)}; it is not general buying power.
      </p>
      <div class="two-column">
        <div>
          <div class="section-header"><h2>KIS positions</h2></div>
          {_paper_positions_table(account)}
        </div>
        <div>
          <div class="section-header"><h2>KIS open orders</h2></div>
          {_paper_open_orders_table(account)}
        </div>
      </div>"""


def _paper_positions_table(account: PaperAccountSnapshot) -> str:
    rows = "".join(
        f"<tr><td>{_text(item.exchange)}</td><td>{_text(item.symbol)}</td>"
        f"<td class=\"numeric\">{_text(item.quantity)}</td><td>{_text(item.currency)}</td></tr>"
        for item in account.positions
    )
    if not rows:
        rows = _empty_row(4, "No verified KIS positions")
    return (
        "<div class=\"table-wrap\"><table><thead><tr><th>Exchange</th><th>Symbol</th>"
        "<th class=\"numeric\">Quantity</th><th>Currency</th></tr></thead><tbody>"
        f"{rows}</tbody></table></div>"
    )


def _paper_open_orders_table(account: PaperAccountSnapshot) -> str:
    rows = "".join(
        f"<tr><td>{_text(item.exchange)}</td><td>{_text(item.symbol)}</td>"
        f"<td>{_text(item.side)}</td><td class=\"numeric\">{_text(item.remaining_quantity)}</td>"
        f"<td class=\"numeric\">{_optional_decimal(item.limit_price)}</td></tr>"
        for item in account.open_orders
    )
    if not rows:
        rows = _empty_row(5, "No verified KIS open orders")
    return (
        "<div class=\"table-wrap\"><table><thead><tr><th>Exchange</th><th>Symbol</th>"
        "<th>Side</th><th class=\"numeric\">Remaining</th>"
        "<th class=\"numeric\">Limit</th></tr></thead><tbody>"
        f"{rows}</tbody></table></div>"
    )


def _project_local_paper(events: tuple[Event, ...]) -> _LocalPaperProjection:
    local_events = tuple(
        event for event in events if event.payload.get("source") == LOCAL_PAPER_SOURCE
    )
    fills: list[DashboardFill] = []
    positions: dict[tuple[str, str], Decimal] = {}
    latest_fill_seq = 0
    latest_snapshot: Event | None = None

    for event in local_events:
        if event.event_type == "local_paper_portfolio_snapshot":
            latest_snapshot = event
        if event.event_type != "fill":
            continue
        fill = _dashboard_fill(event)
        latest_fill_seq = event.seq
        key = (fill.market, fill.symbol)
        quantity = Decimal(fill.quantity)
        positions[key] = positions.get(key, Decimal("0")) + (
            quantity if fill.side == "buy" else -quantity
        )
        if positions[key] < 0:
            raise ValueError("local paper replay contains a negative position")
        fills.append(fill)

    cash, cash_snapshot_at = _snapshot_cash(latest_snapshot, latest_fill_seq)
    projected_positions = tuple(
        DashboardPosition(market=market, symbol=symbol, quantity=_decimal_text(quantity))
        for (market, symbol), quantity in sorted(positions.items())
        if quantity != 0
    )
    if not local_events:
        status = "no_local_paper_activity"
    elif cash is None:
        status = "local_paper_replayed_cash_unavailable"
    else:
        status = "local_paper_replayed"
    return _LocalPaperProjection(
        status=status,
        fill_count=len(fills),
        cash=cash,
        cash_snapshot_at=cash_snapshot_at,
        positions=projected_positions,
        fills=tuple(reversed(fills[-12:])),
    )


def _dashboard_fill(event: Event) -> DashboardFill:
    payload = event.payload
    market = str(payload["market"]).upper()
    symbol = str(payload["symbol"]).upper()
    side = str(payload["side"]).lower()
    quantity = _positive_decimal(payload["quantity"], "quantity")
    price = _nonnegative_decimal(payload["price"], "price")
    fee = _nonnegative_decimal(payload.get("fee", "0"), "fee")
    if not market or not symbol or side not in {"buy", "sell"}:
        raise ValueError("invalid local paper fill")
    return DashboardFill(
        market=market,
        symbol=symbol,
        side=side,
        quantity=_decimal_text(quantity),
        price=_decimal_text(price),
        fee=_decimal_text(fee),
        filled_at=event.created_at.isoformat(),
    )


def _snapshot_cash(snapshot: Event | None, latest_fill_seq: int) -> tuple[str | None, str | None]:
    if snapshot is None or snapshot.seq < latest_fill_seq:
        return None, None
    return (
        _decimal_text(_nonnegative_decimal(snapshot.payload["cash"], "cash")),
        snapshot.created_at.isoformat(),
    )


def _project_latest_decisions(events: tuple[Event, ...]) -> tuple[DashboardDecision, ...]:
    latest: dict[tuple[str, str], DashboardDecision] = {}
    for event in events:
        if event.event_type != "ensemble_decision":
            continue
        payload = event.payload
        market = str(payload.get("market", "")).upper()
        symbol = str(payload.get("symbol", "")).upper()
        if not market or not symbol:
            continue
        latest[(market, symbol)] = DashboardDecision(
            source=str(payload.get("source", "unknown")),
            market=market,
            symbol=symbol,
            action=str(payload.get("action", "unknown")),
            confidence=str(payload.get("confidence", "unknown")),
            expected_edge_bps=str(payload.get("expected_edge_bps", "unknown")),
            decided_at=str(payload.get("decided_at", event.created_at.isoformat())),
        )
    return tuple(latest[key] for key in sorted(latest))


def _positive_decimal(value: object, field: str) -> Decimal:
    result = _nonnegative_decimal(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _nonnegative_decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a decimal") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return result


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _positions_table(
    positions: tuple[DashboardPosition, ...] | None,
    *,
    unavailable: bool,
) -> str:
    if unavailable:
        rows = _empty_row(3, "Local replay unavailable")
    else:
        rows = "".join(
            f"<tr><td>{_text(position.market)}</td><td>{_text(position.symbol)}</td>"
            f"<td class=\"numeric\">{_text(position.quantity)}</td></tr>"
            for position in positions or ()
        )
        if not rows:
            rows = _empty_row(3, "No local positions")
    return (
        "<div class=\"table-wrap\"><table><thead><tr><th>Market</th><th>Symbol</th>"
        "<th class=\"numeric\">Quantity</th></tr></thead><tbody>"
        f"{rows}</tbody></table></div>"
    )


def _decisions_table(
    decisions: tuple[DashboardDecision, ...] | None,
    *,
    unavailable: bool,
) -> str:
    if unavailable:
        rows = _empty_row(6, "Local replay unavailable")
    else:
        rows = "".join(
            f"<tr><td>{_text(decision.source)}</td><td>{_text(decision.market)}</td>"
            f"<td>{_text(decision.symbol)}</td><td>{_text(decision.action)}</td>"
            f"<td class=\"numeric\">{_text(decision.confidence)}</td>"
            f"<td class=\"numeric\">{_text(decision.expected_edge_bps)}</td></tr>"
            for decision in decisions or ()
        )
        if not rows:
            rows = _empty_row(6, "No decisions recorded")
    return (
        "<div class=\"table-wrap\"><table><thead><tr><th>Source</th><th>Market</th>"
        "<th>Symbol</th><th>Action</th><th class=\"numeric\">Confidence</th>"
        "<th class=\"numeric\">Expected edge bps</th></tr></thead><tbody>"
        f"{rows}</tbody></table></div>"
    )


def _fills_table(
    fills: tuple[DashboardFill, ...] | None,
    *,
    unavailable: bool,
) -> str:
    if unavailable:
        rows = _empty_row(7, "Local replay unavailable")
    else:
        rows = "".join(
            f"<tr><td>{_text(fill.filled_at)}</td><td>{_text(fill.market)}</td>"
            f"<td>{_text(fill.symbol)}</td><td>{_text(fill.side)}</td>"
            f"<td class=\"numeric\">{_text(fill.quantity)}</td>"
            f"<td class=\"numeric\">{_text(fill.price)}</td>"
            f"<td class=\"numeric\">{_text(fill.fee)}</td></tr>"
            for fill in fills or ()
        )
        if not rows:
            rows = _empty_row(7, "No local fills")
    return (
        "<table><thead><tr><th>Filled at</th><th>Market</th><th>Symbol</th><th>Side</th>"
        "<th class=\"numeric\">Quantity</th><th class=\"numeric\">Price</th>"
        "<th class=\"numeric\">Fee</th></tr></thead><tbody>"
        f"{rows}</tbody></table>"
    )


def _empty_row(colspan: int, message: str) -> str:
    return f"<tr><td class=\"empty\" colspan=\"{colspan}\">{_text(message)}</td></tr>"


def _optional_text(value: str | None) -> str:
    return _text(value if value is not None else "Unavailable")


def _optional_decimal(value: Decimal | None) -> str:
    return _text(value if value is not None else "No limit")


def _optional_count(value: int | None) -> str:
    return _text(value if value is not None else "Unavailable")


def _decision_count_label(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value} tracked"


def _replay_unavailable(snapshot: DashboardSnapshot) -> bool:
    return snapshot.status == "local_monitor_degraded"


def _state_class(is_paused: bool) -> str:
    return "state-paused" if is_paused else "state-ready"


def _text(value: object) -> str:
    return escape(str(value), quote=True)
