"""Sanitized read model and HTML view for the local paper console."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path

from thericher_v2.data.market_data_freshness_runtime import (
    MarketDataFreshnessRuntimeSnapshot,
    read_market_data_freshness_runtime,
)
from thericher_v2.execution.emergency import EmergencyStore, PaperExecutionControlStore
from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    replay_local_paper_realized_pnl,
)
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

_QQQ_RECEIPT_KEYS = frozenset(
    {
        "kind",
        "source",
        "currency",
        "status",
        "gross_pnl_sign",
        "matched_fill_count",
        "roundtrip_count",
        "owned_flat",
        "fees",
        "settled_cash",
        "net_pnl",
        "observed_at",
        "broker_calls",
        "paper_only",
        "read_only_private_state",
        "current_account_binding_matches",
        "canonical_cycle_id",
        "private_input_bundle_sha256",
        "independent_signed_cashflow_replay_matches",
        "restart_replays",
        "source_outcomes",
        "projector_sha256",
        "replay_source_sha256",
        "source_hashes_unchanged_from_predispatch",
        "code_sha256",
        "limitation",
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
QQQ_GROSS_ACCOUNTING_CYCLE_ID = (
    "qqq-unit-108e0e99872a0aac8d13d5bee4fcb6e28b83298fb29e0c41125ec808c34e3381"
)
_KST = timezone(timedelta(hours=9), name="KST")
_OPERATION_RUNS = {
    "h20": (
        "H20",
        "SPY",
        "artifact:execution/current-h20-reader-parent-completion-20261101-v1/actual-once/RESULT.json",
    ),
    "googl": (
        "GOOGL",
        "GOOGL",
        "artifact:execution/current-us19-unit-reader-binding-repair-20261101-v1/actual-once/RESULT.json",
    ),
    "h3": ("H3", "AMD", None),
}
_OPERATION_VALUES = {
    "status": frozenset({"scheduled", "unknown", "validated", "invalid", "unavailable"}),
    "submit": frozenset({"unknown", "not_observed", "attempted", "accepted", "rejected"}),
    "fill": frozenset({"unknown", "not_observed", "confirmed"}),
    "inventory": frozenset({"unknown", "owned", "flat"}),
}
_OPERATION_REASONS = {
    "not_configured": "운영 결과 연결 설정 확인",
    "projection_missing": "공개 상태 투영 미수신 · 게시 경로 확인",
    "projection_unavailable": "공개 상태 투영 읽기 불가 · 게시 경로·권한 확인",
    "projection_stale": "이전 관측만 존재 · 최신 증거 확인",
    "projection_invalid": "상태 투영 검증 실패 · 게시자 점검",
    "public_reader_unavailable": "결과 판독기 사용 불가 · 실행 담당 점검",
    "public_evidence_missing": "연결된 결과 미수신 · 예정된 판독 결과 확인",
    "public_evidence_invalid": "결과 근거 검증 실패 · 실행 담당 점검",
    "public_evidence_withheld": "근거 판정 보류 · 미확인 요청 조정 필요",
    "host_published_public_outcome": "공개 판독 결과 · 호스트 게시; 현재 상태 재확인 필요",
    "historical_public_outcome": "과거 공개 판독 결과 · 접수·체결 기록 보존, 현재 보유 미확인",
    "h3_installation_retained": "진입·청산 정의 설치 근거 보존 · 금융 결과 미확인",
    "h3_future_outcome_unknown": "향후 실행 결과 미수신 · 실패 또는 무주문 근거 아님",
    "h3_host_diagnostic_unknown_finance": "호스트 실행 진단만 관측 · 제출·체결·보유 미확인",
    "h3_technical_fault_unknown_finance": "호스트 기술 실패 기록 · 금융 효과는 미확인",
}
_STATUS_LABELS = {
    "unknown": "미확인",
    "available": "관측 있음",
    "unavailable": "사용 불가",
    "reference_only": "참고값만 있음",
    "scheduled": "예약 정의",
    "validated": "공개 판독 결과",
    "invalid": "검증 실패",
    "not_observed": "관측되지 않음",
    "attempted": "제출 시도",
    "accepted": "접수 확인",
    "rejected": "거절 확인",
    "confirmed": "연결 체결 확인",
    "owned": "소유 보유 관측",
    "flat": "소유 잔고 없음 관측",
}


@dataclass(frozen=True)
class QqqGrossAccountingReceipt:
    status: str
    gross_pnl_sign: str
    matched_fill_count: int
    roundtrip_count: int
    observed_at: str
    receipt_sha256: str
    source: str = "kis_paper"
    instrument: str = "QQQ"
    currency: str = "USD"
    fees: str = "not_observed"
    settled_cash: str = "not_observed"
    net_pnl: str = "not_observed"


def _receipt_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate_receipt_key")
    return result


def read_qqq_gross_accounting_receipt(
    path: Path | None,
    expected_sha256: str | None,
    *,
    now: datetime | None = None,
) -> tuple[str, QqqGrossAccountingReceipt | None]:
    """Read a pinned historical receipt, never private fills or current account state."""
    if path is None and expected_sha256 is None:
        return "unknown", None
    try:
        if (
            path is None
            or not isinstance(expected_sha256, str)
            or _SHA256.fullmatch(expected_sha256) is None
            or path.is_symlink()
            or not path.is_file()
        ):
            return "unavailable", None
        with path.open("rb") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
            return "unavailable", None
        payload = json.loads(raw, object_pairs_hook=_receipt_object)
        if not isinstance(payload, dict) or set(payload) != _QQQ_RECEIPT_KEYS:
            return "unavailable", None
        fixed = {
            "kind": "kis_paper_qqq_gross_roundtrip_replay_v1",
            "source": "kis_paper",
            "currency": "USD",
            "status": "gross_realized_observed",
            "fees": "not_observed",
            "settled_cash": "not_observed",
            "net_pnl": "not_observed",
            "limitation": "gross_only_single_roundtrip_not_strategy_profitability",
        }
        true_fields = (
            "paper_only",
            "owned_flat",
            "read_only_private_state",
            "current_account_binding_matches",
            "independent_signed_cashflow_replay_matches",
            "source_hashes_unchanged_from_predispatch",
        )
        if (
            any(payload[key] != value for key, value in fixed.items())
            or any(payload[key] is not True for key in true_fields)
            or payload["broker_calls"] is not False
            or payload["gross_pnl_sign"] not in ("positive", "negative", "zero")
            or any(
                type(payload[key]) is not int or payload[key] != value
                for key, value in (
                    ("matched_fill_count", 2),
                    ("roundtrip_count", 1),
                    ("restart_replays", 3),
                )
            )
            or payload["canonical_cycle_id"] != QQQ_GROSS_ACCOUNTING_CYCLE_ID
        ):
            return "unavailable", None
        hashes = [
            payload[key]
            for key in ("private_input_bundle_sha256", "projector_sha256", "replay_source_sha256")
        ]
        code = payload["code_sha256"]
        sources = payload["source_outcomes"]
        if (
            not isinstance(code, dict)
            or not code
            or not isinstance(sources, list)
            or len(sources) != 2
            or any(
                not isinstance(item, dict)
                or set(item) != {"path", "sha256"}
                or not isinstance(item["path"], str)
                or not item["path"]
                for item in sources
            )
        ):
            return "unavailable", None
        hashes.extend(code.values())
        hashes.extend(item["sha256"] for item in sources)
        if (
            any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in hashes)
            or len({item["sha256"] for item in sources}) != 2
            or len({item["path"] for item in sources}) != 2
        ):
            return "unavailable", None
        observed = datetime.fromisoformat(payload["observed_at"])
        current = now or datetime.now(UTC)
        if (
            observed.utcoffset() != timedelta(0)
            or current.utcoffset() is None
            or observed > current
        ):
            return "unavailable", None
        # Receipt age does not expire a closed cycle; owned_flat is deliberately not projected.
        return "available", QqqGrossAccountingReceipt(
            status=payload["status"],
            gross_pnl_sign=payload["gross_pnl_sign"],
            matched_fill_count=payload["matched_fill_count"],
            roundtrip_count=payload["roundtrip_count"],
            observed_at=observed.isoformat(),
            receipt_sha256=expected_sha256,
        )
    except (OSError, TypeError, ValueError, RecursionError):
        return "unavailable", None


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
    pause_buys: bool
    pause_sells: bool
    execution_control_reason: str
    execution_control_updated_at: str
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
    paper_canary_reconciliation_reason_code: str | None = None
    paper_canary_account_status: str = "unknown"
    paper_canary_observed_at: str | None = None
    paper_canary: PaperCanaryRuntimeSnapshot | None = None
    market_data_freshness_status: str = "unknown"
    market_data_freshness: MarketDataFreshnessRuntimeSnapshot | None = None
    qqq_gross_accounting_status: str = "unknown"
    qqq_gross_accounting: QqqGrossAccountingReceipt | None = None
    operations_snapshot: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = to_jsonable(self)
        assert isinstance(payload, dict)
        payload["paper_account"] = (
            None if self.paper_account is None else self.paper_account.to_dict()
        )
        payload["operations_snapshot"] = _safe_operations(
            self.operations_snapshot, now=self.heartbeat_utc
        )
        return payload


@dataclass(frozen=True)
class _LocalPaperProjection:
    status: str
    fill_count: int
    cash: str | None
    cash_snapshot_at: str | None
    realized_pnl_text: str
    positions: tuple[DashboardPosition, ...]
    fills: tuple[DashboardFill, ...]


def build_snapshot(
    event_store: EventStore,
    emergency_store: EmergencyStore,
    mode: str = "off",
    *,
    execution_control_store: PaperExecutionControlStore | None = None,
    paper_account_snapshot_path: Path | None = None,
    paper_canary_runtime_path: Path | None = None,
    market_data_freshness_path: Path | None = None,
    qqq_gross_receipt_path: Path | None = None,
    qqq_gross_receipt_sha256: str | None = None,
    operations_snapshot: dict[str, object] | None = None,
    now: datetime | None = None,
) -> DashboardSnapshot:
    current_time = now or datetime.now(UTC)
    emergency = emergency_store.read()
    execution_control = (
        execution_control_store
        if execution_control_store is not None
        else PaperExecutionControlStore(
            emergency_store.path.with_name("paper_execution_control.json")
        )
    ).read()
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
            realized_pnl_text="Unavailable",
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

    market_data_freshness_read = read_market_data_freshness_runtime(
        market_data_freshness_path,
        now=current_time,
    )
    accounting_status, accounting = read_qqq_gross_accounting_receipt(
        qqq_gross_receipt_path,
        qqq_gross_receipt_sha256,
        now=current_time,
    )

    return DashboardSnapshot(
        mode=mode,
        heartbeat_utc=current_time.isoformat(),
        status=status,
        stop_new_orders=emergency.stop_new_orders,
        cancel_open_orders_requested=emergency.cancel_open_orders_requested,
        emergency_reason=emergency.reason,
        emergency_updated_at=emergency.updated_at.isoformat(),
        pause_buys=execution_control.pause_buys,
        pause_sells=execution_control.pause_sells,
        execution_control_reason=execution_control.reason,
        execution_control_updated_at=execution_control.updated_at.isoformat(),
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
        local_paper_pnl_status=local_paper.realized_pnl_text,
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
        paper_canary_reconciliation_reason_code=(
            None if paper_canary is None else paper_canary.reconciliation_reason_code
        ),
        paper_canary_account_status=(
            "unknown" if paper_canary is None else paper_canary.account_status
        ),
        paper_canary_observed_at=(
            None if paper_canary is None else paper_canary.observed_at.isoformat()
        ),
        paper_canary=paper_canary,
        market_data_freshness_status=market_data_freshness_read.status,
        market_data_freshness=market_data_freshness_read.snapshot,
        qqq_gross_accounting_status=accounting_status,
        qqq_gross_accounting=accounting,
        operations_snapshot=_safe_operations(operations_snapshot, now=current_time.isoformat()),
    )


def render_dashboard(snapshot: DashboardSnapshot, *, form_nonce: str = "") -> str:
    """Render a compact, local-only operational view from a sanitized snapshot."""

    buy_state = "일시정지 요청 · Paused" if snapshot.pause_buys else "정지 요청 없음"
    sell_state = "일시정지 요청 · Paused" if snapshot.pause_sells else "정지 요청 없음"
    buy_action = "resume-buys" if snapshot.pause_buys else "pause-buys"
    buy_label = "매수 정지 해제 · Resume buys" if snapshot.pause_buys else "매수 정지 · Pause buys"
    buy_class = "" if snapshot.pause_buys else "danger"
    sell_action = "resume-sells" if snapshot.pause_sells else "pause-sells"
    sell_label = (
        "매도 정지 해제 · Resume sells" if snapshot.pause_sells else "매도 정지 · Pause sells"
    )
    sell_class = "" if snapshot.pause_sells else "danger"
    paper_account_details = _paper_account_details(
        snapshot.paper_account,
        status=snapshot.paper_account_status,
        observed_at=snapshot.paper_account_observed_at,
        now=snapshot.heartbeat_utc,
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TheRicher v2 | Paper 운영</title>
  <style>
    :root {{
      color-scheme: light;
      --canvas: #f7f8f8;
      --surface: #ffffff;
      --ink: #18222d;
      --muted: #56616b;
      --line: #d8dee4;
      --green: #16794d;
      --green-soft: #e8f5ed;
      --amber: #795300;
      --amber-soft: #fff4d6;
      --red: #b42318;
      --red-soft: #fff0ee;
    }}
    * {{ box-sizing: border-box; letter-spacing: 0; }}
    html {{ scroll-padding-top: 12px; }}
    body {{
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
        "Malgun Gothic", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 20px 24px 36px; }}
    .topbar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 2px solid var(--ink);
      padding-bottom: 14px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: 22px; font-weight: 700; }}
    h2 {{ font-size: 15px; font-weight: 700; }}
    h3 {{ font-size: 14px; font-weight: 700; }}
    a {{ color: inherit; text-underline-offset: 3px; }}
    a:hover {{ color: var(--green); }}
    :focus-visible {{ outline: 3px solid #14664a; outline-offset: 3px; }}
    .skip-link {{ position: absolute; top: -100px; left: 12px; }}
    .skip-link:focus {{ top: 8px; padding: 12px; background: var(--surface); z-index: 2; }}
    .navigation {{ display: flex; flex-wrap: wrap; gap: 8px 24px; padding: 10px 0; }}
    .navigation a {{ padding: 5px 0; font-size: 13px; }}
    .refresh {{ display: inline-flex; align-items: center; gap: 6px; padding: 8px 0; }}
    .refresh-icon {{ font-size: 22px; line-height: 1; }}
    time {{ display: inline-block; font-variant-numeric: tabular-nums; }}
    time small {{ display: block; font-size: 11px; color: var(--muted); }}
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
    .state-ready {{ color: var(--ink); }}
    .state-paused {{ color: var(--red); }}
    .state-unknown {{ color: var(--amber); }}
    .section {{ border-bottom: 1px solid var(--line); padding: 20px 0; }}
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
      min-height: 44px;
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
    .scope {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
    .overview {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border-block: 1px solid var(--line);
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
    .table-wrap {{ max-width: 100%; overflow-x: auto; overscroll-behavior-x: contain; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--surface); }}
    caption {{ text-align: left; padding: 8px 10px; font-size: 12px; color: var(--muted); }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 12px; font-weight: 650; white-space: nowrap; }}
    td.numeric, th.numeric {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tbody tr:hover {{ background: #f1f5f3; }}
    td, .metric, .overview > div {{ overflow-wrap: anywhere; }}
    .notice {{
      border-left: 3px solid var(--amber);
      background: var(--amber-soft);
      padding: 10px 12px;
    }}
    .tag {{
      display: inline-block;
      border-radius: 3px;
      padding: 2px 7px;
      font-size: 12px;
      font-weight: 650;
    }}
    .tag-local {{ background: var(--green-soft); color: var(--green); }}
    .tag-unknown {{ background: var(--amber-soft); color: var(--amber); }}
    .tag-danger {{ background: var(--red-soft); color: var(--red); }}
    .receipt-hash {{ overflow-wrap: anywhere; }}
    .run-list, .timeline {{ list-style: none; margin: 0; padding: 0; }}
    .run {{ padding: 12px 0; border-top: 1px solid var(--line); }}
    .run-header {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }}
    .run-header .tag {{ margin-left: auto; }}
    .timeline {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 20px; margin: 12px 0; }}
    .timeline li {{ border-top: 2px solid var(--line); padding-top: 6px; min-width: 0; }}
    .timeline .label {{ display: block; font-size: 12px; margin-bottom: 3px; }}
    .run-facts {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px 20px; margin: 10px 0; }}
    .run-facts dt {{ color: var(--muted); font-size: 12px; }}
    .run-facts dd {{ margin: 3px 0 0; }}
    .followup {{ font-size: 13px; border-left: 3px solid var(--amber); padding-left: 10px; }}
    .evidence {{ margin-top: 8px; font-size: 12px; color: var(--muted); }}
    .evidence summary {{ cursor: pointer; padding: 6px 0; }}
    .evidence code {{ display: block; overflow-wrap: anywhere; padding: 6px 0; }}
    .clock {{ font-size: 12px; }}
    @media (max-width: 760px) {{
      .shell {{ padding: 12px; }}
      .topbar, .section-header {{ align-items: start; flex-direction: column; gap: 6px; }}
      .meta {{ text-align: left; }}
      .status-band, .overview {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .two-column {{ grid-template-columns: 1fr; }}
      .metric, .overview > div {{ padding: 10px; border-bottom: 1px solid var(--line); }}
      .metric:nth-child(even), .overview > div:nth-child(even) {{ border-right: 0; }}
      .metric:nth-last-child(-n+2), .overview > div:nth-last-child(-n+2) {{ border-bottom: 0; }}
      .timeline {{ gap: 10px; }}
      .timeline time {{ font-size: 12px; }}
      .run-facts {{ gap: 8px; }}
      .run-header .tag {{ margin-left: 0; }}
      .navigation {{ gap: 4px 18px; }}
      table {{ min-width: 460px; }}
      .facts-table {{ min-width: 0; }}
    }}
    @media (max-width: 480px) {{
      .timeline {{ grid-template-columns: 1fr; gap: 8px; }}
      .timeline li {{ display: grid; grid-template-columns: minmax(86px, 0.65fr) minmax(0, 1fr);
        gap: 10px; border-top-width: 1px; padding-top: 8px; align-items: baseline; }}
      .timeline .label {{ margin-bottom: 0; }}
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#operations-heading">실행 현황으로 건너뛰기</a>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>TheRicher v2</h1>
        <p class="subtitle">Paper 운영 <span class="scope">· Local paper console</span></p>
      </div>
      <div class="meta">
        <p>화면 생성 {_clock(snapshot.heartbeat_utc)}</p>
        <a class="refresh" href="/" title="화면 새로고침 · Refresh snapshot">
          <span class="refresh-icon" aria-hidden="true">↻</span>새로고침</a>
      </div>
    </header>
    <nav class="navigation" aria-label="운영 섹션">
      <a href="#operations-heading">KIS 실행</a><a href="#broker-heading">계좌 관측</a>
      <a href="#safety-heading">실행 제어</a><a href="#local-heading">로컬 시뮬레이터</a>
      <a href="#data-heading">시장 데이터</a>
    </nav>

    <section class="status-band" aria-label="저장된 제어 상태 · Control state">
      <div class="metric">
        <span class="metric-label">비상 신규주문 차단 요청</span>
        <span class="metric-value {_state_class(snapshot.stop_new_orders)}">
          {"차단 요청 있음" if snapshot.stop_new_orders else "차단 요청 없음"}</span>
      </div>
      <div class="metric">
        <span class="metric-label">계좌 관측 경과 · Snapshot age</span>
        <span class="metric-value">{_snapshot_age(snapshot)}</span>
      </div>
      <div class="metric">
        <span class="metric-label">모델 매수 제어 · Buys</span>
        <span class="metric-value {_state_class(snapshot.pause_buys)}">{buy_state}</span>
      </div>
      <div class="metric">
        <span class="metric-label">모델 매도 제어 · Sells</span>
        <span class="metric-value {_state_class(snapshot.pause_sells)}">{sell_state}</span>
      </div>
    </section>

    {_operations_details(snapshot)}

    <section class="section" aria-labelledby="broker-heading">
      <div class="section-header">
        <h2 id="broker-heading" tabindex="-1">KIS Paper 계좌 · KIS broker state</h2>
        {_status_badge(snapshot.paper_account_status)}
      </div>
      <p class="scope">source: kis_paper · 계좌 전체 관측; 프로젝트 소유 판정과 별개</p>
      <div class="table-wrap" tabindex="0" role="region" aria-label="KIS 계좌 사실 상태">
        <table class="facts-table">
          <caption>계좌 사실 · Account facts</caption>
          <thead><tr><th scope="col">관측 항목</th><th scope="col">상태</th></tr></thead>
          <tbody>
            <tr><td>계좌 보유 · KIS holdings</td>
              <td>{_status_badge(snapshot.kis_holdings_status)}</td></tr>
            <tr><td>가격 · KIS price quotes</td>
              <td>{_status_badge(snapshot.kis_prices_status)}</td></tr>
            <tr><td>종목별 주문가능 참고 · KIS reference orderability</td>
              <td>{_status_badge(snapshot.kis_buying_power_status)}</td></tr>
            <tr><td>계좌 미체결 · KIS open orders</td>
              <td>{_status_badge(snapshot.kis_open_orders_status)}</td></tr>
          </tbody>
        </table>
      </div>
      {paper_account_details}
      <details class="evidence">
        <summary>기존 Canary 관측</summary>
        <p>Virtual-paper canary: {_text(snapshot.paper_canary_status)} ·
          Canary reconciliation: {_text(snapshot.paper_canary_reconciliation_status)}</p>
        {_paper_canary_details(snapshot)}
      </details>
    </section>

    <section class="section" aria-labelledby="safety-heading">
      <div class="section-header">
        <h2 id="safety-heading" tabindex="-1">실행 제어 · Execution controls</h2>
        <span class="scope">저장된 요청 · Local state only</span>
      </div>
      <div class="actions">
        <form method="post" action="/controls/{buy_action}">
          <input type="hidden" name="csrf" value="{_text(form_nonce)}">
          <button class="{buy_class}" type="submit">{buy_label}</button>
        </form>
        <form method="post" action="/controls/{sell_action}">
          <input type="hidden" name="csrf" value="{_text(form_nonce)}">
          <button class="{sell_class}" type="submit">{sell_label}</button>
        </form>
        <form method="post" action="/emergency/stop-new-orders">
          <input type="hidden" name="csrf" value="{_text(form_nonce)}">
          <button class="danger" type="submit">신규주문 차단 요청 · Pause new entries</button>
        </form>
      </div>
      <p class="scope">
        실행기 반영: 미확인 · consumer ack unknown. 실행기 소비 확인: 미수신.
        제어 요청 저장 ≠ 모든 실행기 반영. 미확인 주문·예약금은 유지됩니다.
        미체결 취소 요청:
        {"있음 · 결과 미확인" if snapshot.cancel_open_orders_requested else "없음"}.
      </p>
      <details class="evidence"><summary>제어 변경 기록</summary>
        <p>방향 제어: {_text(snapshot.execution_control_reason)} ·
          {_clock(snapshot.execution_control_updated_at)}</p>
        <p>비상 제어: {_text(snapshot.emergency_reason)} ·
          {_clock(snapshot.emergency_updated_at)}</p>
      </details>
    </section>

    <section class="section" aria-labelledby="local-heading">
      <div class="section-header">
        <h2 id="local-heading" tabindex="-1">로컬 시뮬레이터 · Local paper replay</h2>
        <span class="scope">source: local_paper · KIS 주문·체결 아님</span>
      </div>
      <div class="overview">
        <div>
          <span class="label">시뮬레이터 현금 · Simulator cash snapshot</span>
          <strong>{_optional_text(snapshot.local_paper_cash)}</strong>
        </div>
        <div>
          <span class="label">로컬 보유 · Positions</span>
          <strong>{_optional_count(snapshot.position_count)}</strong>
        </div>
        <div>
          <span class="label">로컬 체결 · Local fills</span>
          <strong>{_optional_count(snapshot.local_paper_fill_count)}</strong>
        </div>
        <div>
          <span class="label">로컬 실현손익 · Realized PnL</span>
          <strong>{_local_pnl_text(snapshot.local_paper_pnl_status)}</strong>
        </div>
      </div>
      <p class="scope">
        현금 관측 {_clock(snapshot.local_paper_cash_snapshot_at)} ·
        {_text(snapshot.local_paper_status)}
      </p>
    </section>

    <section class="section two-column" aria-label="Local paper positions and decisions">
      <div>
        <div class="section-header">
          <h2>로컬 보유 · Local positions</h2><span class="meta">로컬 체결 재생 기준</span>
        </div>
        {_positions_table(snapshot.local_positions, unavailable=_replay_unavailable(snapshot))}
      </div>
      <div>
        <div class="section-header">
          <h2>기록된 제안 · Recorded decisions</h2>
          <span class="meta">{_decision_count_label(snapshot.latest_decision_count)}</span>
        </div>
        {_decisions_table(snapshot.latest_decisions, unavailable=_replay_unavailable(snapshot))}
      </div>
    </section>

    <section class="section" aria-labelledby="fills-heading">
      <div class="section-header">
        <h2 id="fills-heading">최근 로컬 체결 · Recent local fills</h2>
        <span class="meta">source: local_paper</span>
      </div>
      <div class="table-wrap" tabindex="0" role="region" aria-label="최근 로컬 체결">
        {_fills_table(snapshot.local_paper_fills, unavailable=_replay_unavailable(snapshot))}
      </div>
    </section>

    {_qqq_gross_accounting_details(snapshot)}

    <section class="section" aria-labelledby="data-heading">
      <div class="section-header">
        <h2 id="data-heading" tabindex="-1">시장 데이터 관측 · Market data freshness</h2>
        <span class="tag {_paper_account_tag(snapshot.market_data_freshness_status)}">
          {_text(snapshot.market_data_freshness_status)}
        </span>
      </div>
      <div class="table-wrap" tabindex="0" role="region" aria-label="시장 데이터 관측">
        {_market_data_freshness_table(snapshot.market_data_freshness)}
      </div>
    </section>
    <footer class="scope">설정 모드: {_text(snapshot.mode)} ·
      로컬 재생: {_text(snapshot.status)} · KIS 순손익: 미관측 · not_observed</footer>
  </main>
</body>
</html>"""


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None or not 1 < parsed.year < 9999:
            return None
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _clock(value: object) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return '<span class="empty">미확인 · unknown</span>'
    local = parsed.astimezone(_KST)
    return (
        f'<time datetime="{_text(parsed.isoformat())}">'
        f"{local:%Y-%m-%d %H:%M} KST<small>{parsed:%Y-%m-%d %H:%M} UTC</small></time>"
    )


def _snapshot_age(snapshot: DashboardSnapshot) -> str:
    observed = _parse_time(snapshot.paper_account_observed_at)
    current = _parse_time(snapshot.heartbeat_utc)
    if observed is None or current is None or observed > current:
        return "미확인 · unknown"
    seconds = int((current - observed).total_seconds())
    if seconds < 60:
        return f"{seconds}초 경과"
    if seconds < 3600:
        return f"{seconds // 60}분 {seconds % 60}초 경과"
    return f"{seconds // 3600}시간 {(seconds % 3600) // 60}분 경과"


def _status_badge(value: object) -> str:
    code = value if isinstance(value, str) and value in _STATUS_LABELS else "unknown"
    style = "tag-unknown"
    if code in {"invalid", "rejected", "unavailable"}:
        style = "tag-danger"
    elif code in {"available", "validated", "confirmed"}:
        style = "tag-local"
    return (
        f'<span class="tag {style}">{_STATUS_LABELS[code]} · <span lang="en">{code}</span></span>'
    )


def _safe_operations(value: object, *, now: str | None = None) -> dict[str, object] | None:
    """Project allowlisted public display contracts; never follow evidence pointers."""
    if not isinstance(value, dict):
        return None
    observed = _parse_time(value.get("observed_at"))
    current = _parse_time(now)
    supplied = value.get("runs")
    if (
        observed is None
        or (current is not None and observed > current)
        or not isinstance(supplied, list)
        or len(supplied) > 16
    ):
        return None
    runs = []
    for key, (label, symbol, pointer) in _OPERATION_RUNS.items():
        matches = [item for item in supplied if isinstance(item, dict) and item.get("key") == key]
        raw = matches[0] if len(matches) == 1 and matches[0].get("symbol") == symbol else {}
        run: dict[str, object] = {"key": key, "label": label, "symbol": symbol}
        for field in ("entry_due_at", "read_due_at", "exit_due_at", "evidence_at"):
            parsed = _parse_time(raw.get(field))
            if field == "evidence_at" and parsed is not None and parsed > observed:
                parsed = None
            run[field] = None if parsed is None else parsed.isoformat()
        run["evidence_pointer"] = pointer if raw.get("evidence_pointer") == pointer else None
        for field, allowed in _OPERATION_VALUES.items():
            code = raw.get(field)
            run[field] = code if isinstance(code, str) and code in allowed else "unknown"
        reason = raw.get("reason_code")
        run["reason_code"] = (
            reason if isinstance(reason, str) and reason in _OPERATION_REASONS else None
        )
        if run["status"] == "validated" and (
            run["evidence_at"] is None
            or run["evidence_pointer"] is None
            or reason
            not in (
                None,
                "host_published_public_outcome",
                "historical_public_outcome",
            )
        ):
            run["status"] = "invalid"
            run["reason_code"] = "public_evidence_invalid"
        evidence = _parse_time(run["evidence_at"])
        if run["status"] == "validated" and (
            reason == "historical_public_outcome"
            or ((current or observed) - observed).total_seconds() > 300
            or (evidence is not None and ((current or observed) - evidence).total_seconds() > 300)
        ):
            run["inventory"] = "unknown"
            run["reason_code"] = "historical_public_outcome"
        if run["status"] != "validated":
            for field in ("submit", "fill", "inventory"):
                run[field] = "unknown"
            if run["reason_code"] in (
                None,
                "host_published_public_outcome",
                "historical_public_outcome",
            ):
                run["reason_code"] = "public_evidence_missing"
        if key == "h3":
            # Installed definitions and host diagnostics cannot prove financial facts.
            invalid = (
                run["status"] != "unknown"
                or any(
                    raw.get(field, "unknown") != "unknown"
                    for field in ("submit", "fill", "inventory")
                )
                or any(
                    raw.get(field) is not None
                    for field in ("read_due_at", "evidence_at", "evidence_pointer")
                )
                or _parse_time(raw.get("entry_due_at"))
                not in (
                    None,
                    _parse_time("2026-11-03T20:55:00Z"),
                )
                or _parse_time(raw.get("exit_due_at"))
                not in (
                    None,
                    _parse_time("2026-11-06T20:45:00Z"),
                )
            )
            run.update(
                status="invalid" if invalid else "unknown",
                submit="unknown",
                fill="unknown",
                inventory="unknown",
                read_due_at=None,
                evidence_at=None,
                evidence_pointer=None,
                entry_due_at="2026-11-03T20:55:00+00:00",
                exit_due_at="2026-11-06T20:45:00+00:00",
            )
            if invalid:
                run["reason_code"] = "public_evidence_invalid"
            elif run["reason_code"] in (None, "public_evidence_missing"):
                run["reason_code"] = "h3_future_outcome_unknown"
        runs.append(run)
    return {"observed_at": observed.isoformat(), "runs": runs}


def _operations_details(snapshot: DashboardSnapshot) -> str:
    operations = _safe_operations(snapshot.operations_snapshot, now=snapshot.heartbeat_utc)
    runs = [] if operations is None else operations["runs"]
    rows = []
    for index, (key, (label, symbol, _)) in enumerate(_OPERATION_RUNS.items()):
        display_label = "US19" if key == "googl" else label
        run = runs[index] if runs else {}
        reason = run.get("reason_code", "not_configured")
        followup = _OPERATION_REASONS.get(reason, "관측 근거 확인됨 · 현재 상태는 재확인 필요")
        stages = "".join(
            f'<li><span class="label">{name}</span>{_clock(run.get(field))}</li>'
            for field, name in (
                ("entry_due_at", "진입 시작 · Entry"),
                ("read_due_at", "결과 판독 · Read trigger"),
                ("exit_due_at", "청산 시작 · Exit"),
            )
            if key != "h3" or field != "read_due_at"
        )
        h3_scope = (
            '<p class="scope">첫 종목 한정 · First instrument only. '
            "정의 설치 근거 보존 · 금융 실행과 별개. 판독 예약 시각 미확인.</p>"
            if key == "h3"
            else ""
        )
        facts = "".join(
            f"<div><dt>{name}</dt><dd>{_status_badge(run.get(field))}</dd></div>"
            for field, name in (
                ("submit", "기록된 주문 제출 · Submit"),
                ("fill", "기록된 연결 체결 · Fill"),
                ("inventory", "소유 보유 관측 · Inventory"),
            )
        )
        rows.append(f"""
        <li class="run" data-run="{key}">
          <div class="run-header"><h3>{display_label} · {symbol}</h3>
            {_status_badge(run.get("status"))}</div>
          {h3_scope}
          <ol class="timeline" aria-label="{display_label} 예약 시각">{stages}</ol>
          <dl class="run-facts">{facts}</dl>
          <p class="followup">{_text(followup)}</p>
          <details class="evidence"><summary>관측 근거 · Evidence</summary>
            <p>근거 관측 {_clock(run.get("evidence_at"))}</p>
            <code>{_text(run.get("evidence_pointer") or "미수신 · unknown")}</code>
            <p>사유: {_text(reason or "없음")}</p>
          </details>
        </li>""")
    return f"""
    <section class="section" aria-labelledby="operations-heading">
      <div class="section-header">
        <h2 id="operations-heading" tabindex="-1">KIS Paper 실행 현황</h2>
        <span class="scope">source: kis_paper · 모의투자</span>
      </div>
      <p class="scope">예약 시각 ≠ 제출·체결. 접수·체결은 근거에 연결된 과거 기록.
        보유는 근거 관측 당시 기준, 현재 재확인 아님.</p>
      <ol class="run-list">{"".join(rows)}</ol>
      <p class="scope">상태 투영 관측
        {_clock(None if operations is None else operations["observed_at"])}</p>
    </section>"""


def _local_pnl_text(value: str) -> str:
    return _text(
        {"Unavailable": "미관측 · Unavailable", "No closed local fills": "청산 체결 없음"}.get(
            value, value
        )
    )


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


def _qqq_gross_accounting_details(snapshot: DashboardSnapshot) -> str:
    receipt = snapshot.qqq_gross_accounting
    details = _status_badge(snapshot.qqq_gross_accounting_status)
    if receipt is not None:
        details = f"""
      <div class="overview">
        <div><span class="label">과거 총손익 부호 · Gross sign</span>
          <strong>{_text(receipt.gross_pnl_sign)}</strong></div>
        <div><span class="label">연결 체결 · Matched fills</span>
          <strong>{receipt.matched_fill_count}</strong></div>
        <div><span class="label">완료 왕복 · Closed round trips</span>
          <strong>{receipt.roundtrip_count}</strong></div>
        <div><span class="label">순손익 · Net PnL</span>
          <strong>{_text(receipt.net_pnl)}</strong></div>
      </div>
      <p class="scope">과거 청산 사이클 관측 {_clock(receipt.observed_at)}.
        수수료: 미관측 · {_text(receipt.fees)}.
        결제 현금: 미관측 · {_text(receipt.settled_cash)}.</p>
      <p class="scope receipt-hash">Receipt SHA256: {_text(receipt.receipt_sha256)}</p>"""
    return f"""
    <section class="section" aria-labelledby="qqq-accounting-heading">
      <div class="section-header">
        <h2 id="qqq-accounting-heading">과거 QQQ 총손익 · Historical QQQ gross accounting</h2>
        <span class="tag {_paper_account_tag(snapshot.qqq_gross_accounting_status)}">
          {_text(snapshot.qqq_gross_accounting_status)}</span>
      </div>
      <p class="scope">과거 단일 왕복 총손익만 확인 · 현재 보유·전략 수익성 근거 아님</p>
      {details}
    </section>"""


def _paper_canary_details(snapshot: DashboardSnapshot) -> str:
    canary = snapshot.paper_canary
    if canary is None:
        return ""
    return f"""
      <p class="scope">
        Canary 관측 {_clock(snapshot.paper_canary_observed_at)}.
        계좌 사실: {_text(snapshot.paper_canary_account_status)}.
        Reconciliation detail: {_optional_text(snapshot.paper_canary_reconciliation_reason_code)}.
        보유 기록: {canary.position_count}. 미체결 기록: {canary.open_order_count}.
      </p>"""


def _market_data_freshness_table(snapshot: MarketDataFreshnessRuntimeSnapshot | None) -> str:
    if snapshot is None:
        return '<p class="empty">미확인 · <span lang="en">unknown</span></p>'
    rows = "".join(
        f"<tr><td>{_text(item.collection_mode)}</td><td>{_text(item.stream)}</td>"
        f"<td>{_text(item.cache_status)}</td>"
        f"<td>{_text(item.latest_collection_outcome)}</td>"
        f"<td>{_clock(_datetime_text(item.last_observed_at_utc))}</td>"
        f'<td class="numeric">{item.retained_chunk_count}</td>'
        f'<td class="numeric">{item.partial_chunk_count}</td>'
        f"<td>{_optional_text(item.detail_code)}</td></tr>"
        for item in snapshot.streams
    )
    return f"""
      <table>
        <caption>수집 스트림별 마지막 관측</caption>
        <thead>
          <tr><th scope="col">수집 모드</th><th scope="col">Stream</th>
          <th scope="col">캐시</th><th scope="col">최근 결과</th>
          <th scope="col">관측 시각</th><th scope="col" class="numeric">보존</th>
          <th scope="col" class="numeric">부분</th><th scope="col">사유 코드</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>"""


def _datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _paper_account_details(
    account: PaperAccountSnapshot | None,
    *,
    status: str,
    observed_at: str | None,
    now: str,
) -> str:
    if account is None:
        message = (
            "계좌 관측 미수신 · No fresh KIS paper snapshot"
            if status == "unknown"
            else "계좌 관측 사용 불가 · KIS snapshot unavailable"
        )
        return f'<p class="notice">{_text(message)} · 읽기 전용 관측기와 수집 결과 확인 필요</p>'
    assert account.orderable_foreign_funds is not None
    assert account.reference_orderability is not None
    return f"""
      <div class="overview">
        <div>
          <span class="label">주문가능 외화 · KIS orderable foreign funds</span>
          <strong>
            {_text(account.orderable_foreign_funds.amount)}
            {_text(account.orderable_foreign_funds.currency)}
          </strong>
        </div>
        <div>
          <span class="label">종목별 참고값 · Reference orderability</span>
          <strong>
            {_text(account.reference_orderability.orderable_funds)}
            {_text(account.reference_orderability.currency)}
          </strong>
        </div>
        <div>
          <span class="label">계좌 보유 기록 · Account position records</span>
          <strong>{len(account.positions)}</strong>
        </div>
        <div>
          <span class="label">계좌 미체결 기록 · Account open order records</span>
          <strong>{len(account.open_orders)}</strong>
        </div>
      </div>
      <p class="scope">
        관측 {_clock(observed_at)} · 유효 기한 {_clock(account.expires_at.isoformat())}.
        주문가능 외화는 결제 현금·계좌 평가액·증거금·일반 매수여력이 아닙니다
        (not settled cash, account equity, margin capacity, or general buying power).
        종목별 참고값:
        {_text(account.reference_orderability.reference_exchange)}
        {_text(account.reference_orderability.reference_symbol)}.
        현재 시각 {_clock(now)}. 가격·평가손익·순손익: 미관측.
      </p>
      <div class="two-column">
        <div>
          <div class="section-header"><h3>계좌 보유 · KIS account positions</h3></div>
          {_paper_positions_table(account)}
        </div>
        <div>
          <div class="section-header"><h3>계좌 미체결 · KIS account open orders</h3></div>
          {_paper_open_orders_table(account)}
        </div>
      </div>"""


def _paper_positions_table(account: PaperAccountSnapshot) -> str:
    rows = "".join(
        f"<tr><td>{_text(item.exchange)}</td><td>{_text(item.symbol)}</td>"
        f'<td class="numeric">{_text(item.quantity)}</td><td>{_text(item.currency)}</td></tr>'
        for item in account.positions
    )
    if not rows:
        rows = _empty_row(4, "관측된 계좌 보유 없음 · No verified KIS positions")
    return (
        '<div class="table-wrap" tabindex="0" role="region" aria-label="KIS 계좌 보유">'
        "<table><caption>계좌 전체 보유 · 프로젝트 소유 여부 별도 확인</caption>"
        '<thead><tr><th scope="col">거래소</th><th scope="col">종목</th>'
        '<th scope="col" class="numeric">수량</th><th scope="col">통화</th></tr>'
        "</thead><tbody>"
        f"{rows}</tbody></table></div>"
    )


def _paper_open_orders_table(account: PaperAccountSnapshot) -> str:
    rows = "".join(
        f"<tr><td>{_text(item.exchange)}</td><td>{_text(item.symbol)}</td>"
        f"<td>{_side_text(item.side)}</td>"
        f'<td class="numeric">{_text(item.remaining_quantity)}</td></tr>'
        for item in account.open_orders
    )
    if not rows:
        rows = _empty_row(4, "관측된 계좌 미체결 없음 · No verified KIS open orders")
    return (
        '<div class="table-wrap" tabindex="0" role="region" aria-label="KIS 계좌 미체결">'
        "<table><caption>계좌 전체 미체결 · 체결 확정 근거 아님</caption>"
        '<thead><tr><th scope="col">거래소</th><th scope="col">종목</th>'
        '<th scope="col">방향</th><th scope="col" class="numeric">잔여 수량</th>'
        "</tr></thead><tbody>"
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
    realized_pnl = replay_local_paper_realized_pnl(local_events)
    projected_positions = tuple(
        DashboardPosition(market=market, symbol=symbol, quantity=_decimal_text(quantity))
        for (market, symbol), quantity in sorted(positions.items())
        if quantity != 0
    )
    if not local_events:
        status = "no_local_paper_activity"
        realized_pnl_text = "Unavailable"
    elif cash is None:
        status = "local_paper_replayed_cash_unavailable"
    else:
        status = "local_paper_replayed"
    if local_events:
        realized_pnl_text = (
            "No closed local fills"
            if realized_pnl.closed_segment_count == 0
            else _decimal_text(realized_pnl.realized_after_cost_pnl)
        )
    return _LocalPaperProjection(
        status=status,
        fill_count=len(fills),
        cash=cash,
        cash_snapshot_at=cash_snapshot_at,
        realized_pnl_text=realized_pnl_text,
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
        rows = _empty_row(3, "로컬 재생 불가 · Local replay unavailable")
    else:
        rows = "".join(
            f"<tr><td>{_text(position.market)}</td><td>{_text(position.symbol)}</td>"
            f'<td class="numeric">{_text(position.quantity)}</td></tr>'
            for position in positions or ()
        )
        if not rows:
            rows = _empty_row(3, "로컬 보유 없음 · No local positions")
    return (
        '<div class="table-wrap" tabindex="0" role="region" aria-label="로컬 보유">'
        "<table><caption>source: local_paper</caption>"
        '<thead><tr><th scope="col">시장</th><th scope="col">종목</th>'
        '<th scope="col" class="numeric">수량</th></tr></thead><tbody>'
        f"{rows}</tbody></table></div>"
    )


def _decisions_table(
    decisions: tuple[DashboardDecision, ...] | None,
    *,
    unavailable: bool,
) -> str:
    if unavailable:
        rows = _empty_row(7, "로컬 재생 불가 · Local replay unavailable")
    else:
        rows = "".join(
            f"<tr><td>{_text(decision.source)}</td><td>{_text(decision.market)}</td>"
            f"<td>{_text(decision.symbol)}</td><td>{_side_text(decision.action)}</td>"
            f'<td class="numeric">{_text(decision.confidence)}</td>'
            f'<td class="numeric">{_text(decision.expected_edge_bps)}</td>'
            f"<td>{_clock(decision.decided_at)}</td></tr>"
            for decision in decisions or ()
        )
        if not rows:
            rows = _empty_row(7, "기록된 제안 없음 · No decisions recorded")
    return (
        '<div class="table-wrap" tabindex="0" role="region" aria-label="기록된 모델 제안">'
        "<table><caption>모델 제안 · 주문 접수·체결과 별개</caption>"
        '<thead><tr><th scope="col">출처</th><th scope="col">시장</th>'
        '<th scope="col">종목</th><th scope="col">제안</th>'
        '<th scope="col" class="numeric">신뢰도</th>'
        '<th scope="col" class="numeric">예상 우위 bps</th>'
        '<th scope="col">제안 시각</th></tr></thead><tbody>'
        f"{rows}</tbody></table></div>"
    )


def _fills_table(
    fills: tuple[DashboardFill, ...] | None,
    *,
    unavailable: bool,
) -> str:
    if unavailable:
        rows = _empty_row(7, "로컬 재생 불가 · Local replay unavailable")
    else:
        rows = "".join(
            f"<tr><td>{_clock(fill.filled_at)}</td><td>{_text(fill.market)}</td>"
            f"<td>{_text(fill.symbol)}</td><td>{_side_text(fill.side)}</td>"
            f'<td class="numeric">{_text(fill.quantity)}</td>'
            f'<td class="numeric">{_text(fill.price)}</td>'
            f'<td class="numeric">{_text(fill.fee)}</td></tr>'
            for fill in fills or ()
        )
        if not rows:
            rows = _empty_row(7, "로컬 체결 없음 · No local fills")
    return (
        "<table><caption>source: local_paper · 시뮬레이터 체결</caption>"
        '<thead><tr><th scope="col">체결 시각</th><th scope="col">시장</th>'
        '<th scope="col">종목</th><th scope="col">방향</th>'
        '<th scope="col" class="numeric">수량</th><th scope="col" class="numeric">로컬 가격</th>'
        '<th scope="col" class="numeric">로컬 수수료</th></tr></thead><tbody>'
        f"{rows}</tbody></table>"
    )


def _empty_row(colspan: int, message: str) -> str:
    return f'<tr><td class="empty" colspan="{colspan}">{_text(message)}</td></tr>'


def _optional_text(value: str | None) -> str:
    return _text(value if value is not None else "미관측 · Unavailable")


def _optional_decimal(value: Decimal | None) -> str:
    return _text(value if value is not None else "No limit")


def _optional_count(value: int | None) -> str:
    return _text(value if value is not None else "미확인 · Unavailable")


def _decision_count_label(value: int | None) -> str:
    return "미확인 · Unavailable" if value is None else f"{value}건 기록"


def _side_text(value: str) -> str:
    return _text(
        {"buy": "매수 · buy", "sell": "매도 · sell", "hold": "보류 · hold"}.get(value, value)
    )


def _replay_unavailable(snapshot: DashboardSnapshot) -> bool:
    return snapshot.status == "local_monitor_degraded"


def _state_class(is_paused: bool) -> str:
    return "state-paused" if is_paused else "state-ready"


def _text(value: object) -> str:
    return escape(str(value), quote=True)
