"""Finite, versioned native-minute input for frozen cross-sectional experts."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .kis_market_data import (
    KisPaperHistoricalMinuteQuery,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    _validate_historical_minute_page,
)

VERSION = "current20-stock-intraday-foundation-v1"
ET = ZoneInfo("America/New_York")
COHORT = (
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "TSLA",
    "AMD",
    "GOOGL",
    "META",
    "JPM",
    "JNJ",
    "XOM",
    "PG",
    "KO",
    "HD",
    "V",
    "DIS",
    "UNH",
)


def file_ref(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    with pending.open("w", encoding="ascii") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def query_document(query: KisPaperHistoricalMinuteQuery) -> dict[str, Any]:
    return dict(
        symbol=query.symbol,
        exchange=query.exchange,
        minute_interval=1,
        key=query.continuation_key,
        PINC=int(query.include_previous_day),
        NEXT=query.continuation_next,
    )


def query_identity(query: KisPaperHistoricalMinuteQuery) -> str:
    return json.dumps(query_document(query), sort_keys=True, separators=(",", ":"))


def prior_regular_key(key: str, sessions: Sequence[Mapping[str, str]]) -> str:
    """Keep explicit lookup labels within known regular sessions; never fill gaps."""
    stamp = datetime.strptime(key, "%Y%m%d%H%M%S").replace(tzinfo=ET)
    for session in reversed(sessions):
        opening = datetime.fromisoformat(session["open_utc"]).astimezone(ET)
        closing = datetime.fromisoformat(session["close_utc"]).astimezone(ET)
        if stamp >= opening:
            return min(stamp, closing - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")
    raise ValueError("calendar_bound_reached")


class FoundationLedger:
    def __init__(
        self,
        *,
        artifact_root: Path,
        market_root: Path,
        targets: Sequence[tuple[str, str]],
        sessions: Sequence[Mapping[str, str]],
        normal_cap: int = 600,
        retry_cap: int = 2,
    ) -> None:
        if tuple(s for s, _ in targets) != COHORT or len(set(targets)) != len(COHORT):
            raise ValueError("foundation requires the exact ordered FirstRate20 cohort")
        if not 1 <= normal_cap <= 600 or not 0 <= retry_cap <= 2:
            raise ValueError("foundation request caps are invalid")
        self.artifact_root, self.market_root = Path(artifact_root), Path(market_root)
        self.targets, self.sessions = tuple(targets), list(sessions)
        self.scope = {s: frozenset({v}) for s, v in targets}
        self.normal_cap, self.retry_cap = normal_cap, retry_cap
        calendar_digest = hashlib.sha256(
            json.dumps(self.sessions, sort_keys=True).encode()
        ).hexdigest()
        path = self.artifact_root / "cursor.json"
        if path.exists():
            self.state = json.loads(path.read_bytes())
            if (
                self.state["version"] != VERSION
                or self.state["targets"] != [list(t) for t in targets]
                or self.state["normal_cap"] != normal_cap
                or self.state["retry_cap"] != retry_cap
                or self.state["calendar_sha256"] != calendar_digest
                or self.state["pending"] is not None
            ):
                raise ValueError("foundation resume contract or pending request mismatch")
        else:
            self.state = dict(
                version=VERSION,
                calendar_sha256=calendar_digest,
                targets=[list(t) for t in targets],
                normal_cap=normal_cap,
                retry_cap=retry_cap,
                GET=0,
                POST=0,
                retry=0,
                normal_GET=0,
                pending=None,
                pages=[],
                completed={},
                cursors={
                    s: dict(head_done=False, key=None, status="pending_head") for s, _ in targets
                },
                venue_calibration={},
                next_due=None,
                status="prepared",
            )
            self.save()

    def save(self) -> None:
        atomic_json(self.artifact_root / "cursor.json", self.state)

    def query(self, symbol: str, key: str | None = None) -> KisPaperHistoricalMinuteQuery:
        return KisPaperHistoricalMinuteQuery(
            symbol=symbol,
            exchange=next(v for s, v in self.targets if s == symbol),
            include_previous_day=key is not None,
            continuation_next="1" if key else None,
            continuation_key=key,
            approved_symbol_exchanges=self.scope,
        )

    def begin_wire(
        self, method: str, *, query: KisPaperHistoricalMinuteQuery | None, retry: bool = False
    ) -> None:
        if method == "POST":
            if self.state["POST"] >= 1:
                raise ValueError("foundation_auth_cap")
        elif method == "GET" and query is not None:
            if self.state["GET"] >= self.normal_cap + self.retry_cap:
                raise ValueError("foundation_GET_cap")
            if retry:
                if self.state["retry"] >= self.retry_cap:
                    raise ValueError("foundation_retry_cap")
                self.state["retry"] += 1
            else:
                if self.state["normal_GET"] >= self.normal_cap:
                    raise ValueError("foundation_normal_GET_cap")
                self.state["normal_GET"] += 1
        else:
            raise ValueError("foundation_wire_scope")
        self.state[method] += 1
        self.state["pending"] = dict(method=method, query=query_document(query) if query else None)
        self.save()

    def wire_finished(self) -> None:
        self.state["pending"] = None
        self.save()

    def retain_raw(self, body: bytes) -> dict[str, str]:
        if len(body) > 262144:
            raise ValueError("foundation_response_size")
        path = self.market_root / "responses" / f"page-{self.state['GET']:06d}.body"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        return file_ref(path)

    def accept(
        self,
        query: KisPaperHistoricalMinuteQuery,
        page: KisPaperMinutePage,
        raw: Mapping[str, str],
        capture_utc: str,
        *,
        calibration: bool = False,
    ) -> None:
        if page.query != query:
            raise ValueError("foundation_page_query_mismatch")
        _validate_historical_minute_page(page)
        stamps = [r.exchange_date + r.exchange_time for r in page.bars]
        key = None
        if stamps:
            try:
                key = prior_regular_key(
                    (
                        datetime.strptime(min(stamps), "%Y%m%d%H%M%S") - timedelta(minutes=1)
                    ).strftime("%Y%m%d%H%M%S"),
                    self.sessions,
                )
            except ValueError as error:
                if str(error) != "calendar_bound_reached":
                    raise
            if (
                query.continuation_key is not None
                and key is not None
                and key >= query.continuation_key
            ):
                raise ValueError("foundation_no_progress")
        native = self.market_root / "native-pages" / f"page-{self.state['GET']:06d}.json"
        if native.exists():
            raise ValueError("foundation_page_exists")
        atomic_json(native, [r.as_document() for r in page.bars])
        metadata = dict(
            query=query_document(query),
            raw=dict(raw),
            native=file_ref(native),
            capture_utc=capture_utc,
            bars=len(stamps),
            oldest=min(stamps) if stamps else None,
            newest=max(stamps) if stamps else None,
            next_regular_key=key,
            continuation_signal=page.continuation_signal,
            accepted=True,
            calibration=calibration,
        )
        self.state["pages"].append(metadata)
        self.state["completed"][query_identity(query)] = len(self.state["pages"]) - 1
        if not calibration:
            self.state["cursors"][query.symbol].update(
                head_done=True,
                key=key,
                status=("open" if key else "calendar_scope_complete")
                if stamps
                else "exact_cursor_empty",
            )
        self.save()

    def reject(
        self, query: KisPaperHistoricalMinuteQuery, reason: str, raw: Mapping[str, str] | None
    ) -> None:
        self.state["pages"].append(
            dict(
                query=query_document(query),
                raw=raw,
                accepted=False,
                reason=reason,
                capture_utc=datetime.now(UTC).isoformat(),
            )
        )
        self.state["cursors"][query.symbol].update(
            status="exact_cursor_failed", failed_key=query.continuation_key
        )
        self.save()


def run_foundation(
    ledger: FoundationLedger,
    fetch: Callable[
        [KisPaperHistoricalMinuteQuery, bool], tuple[KisPaperMinutePage, dict[str, str], str]
    ],
    raw_failure: Callable[[], dict[str, str] | None],
    check: Callable[[], None],
    *,
    prior_close_key: str,
) -> None:
    """Fixed empirical witnesses, all heads, then finite RTH-prioritized rounds."""

    def collect(query: KisPaperHistoricalMinuteQuery, calibration: bool = False) -> bool:
        identity = query_identity(query)
        if identity in ledger.state["completed"]:
            page = ledger.state["pages"][ledger.state["completed"][identity]]
            if not calibration:
                ledger.state["cursors"][query.symbol].update(
                    key=page["next_regular_key"],
                    status=("open" if page["next_regular_key"] else "calendar_scope_complete")
                    if page["bars"]
                    else "exact_cursor_empty",
                )
                ledger.save()
            return bool(page["bars"])
        for attempt in range(2):
            check()
            try:
                page, raw, capture = fetch(query, bool(attempt))
                ledger.accept(query, page, raw, capture, calibration=calibration)
                return bool(page.bars)
            except KisPaperMarketDataError as error:
                reason = str(error)
                if (
                    reason == "transport_failure"
                    and attempt == 0
                    and ledger.state["retry"] < ledger.retry_cap
                ):
                    continue
                ledger.reject(query, reason, raw_failure())
                return False
        return False

    if "NAS" not in ledger.state["venue_calibration"]:
        ledger.state["venue_calibration"]["NAS"] = collect(
            ledger.query("AAPL", prior_close_key), True
        )
        ledger.save()
    for symbol, _ in ledger.targets:
        if not ledger.state["cursors"][symbol]["head_done"]:
            collect(ledger.query(symbol))
    for venue, symbol in (("NYS", "JPM"), ("AMS", "SPY")):
        if venue not in ledger.state["venue_calibration"]:
            ledger.state["venue_calibration"][venue] = collect(
                ledger.query(symbol, prior_close_key), True
            )
            ledger.save()
    for _ in range(ledger.normal_cap):
        progressed = False
        for symbol, venue in ledger.targets:
            cursor = ledger.state["cursors"][symbol]
            if (
                cursor["status"] != "open"
                or not ledger.state["venue_calibration"].get(venue)
                or ledger.state["normal_GET"] >= ledger.normal_cap
            ):
                continue
            collect(ledger.query(symbol, cursor["key"]))
            progressed = True
        if not progressed:
            break
    ledger.state["status"] = "closed_finite_capture"
    ledger.save()


def observed_coverage(ledger: FoundationLedger) -> dict[str, Any]:
    sessions = {
        datetime.fromisoformat(s["open_utc"]).astimezone(ET).strftime("%Y%m%d"): s
        for s in ledger.sessions
    }
    result: dict[str, Any] = {}
    for symbol, _ in ledger.targets:
        rows: dict[str, dict[str, str]] = {}
        conflicts: set[str] = set()
        for page in ledger.state["pages"]:
            if not page["accepted"] or page["query"]["symbol"] != symbol:
                continue
            native = Path(page["native"]["path"])
            if file_ref(native)["sha256"] != page["native"]["sha256"]:
                raise ValueError("foundation_native_hash_mismatch")
            for row in json.loads(native.read_bytes()):
                key = row["xymd"] + row["xhms"]
                if key in rows and rows[key] != row:
                    conflicts.add(key)
                rows[key] = row
        regular: dict[str, list[datetime]] = {}
        for key in sorted(rows):
            session = sessions.get(key[:8])
            if session is None or key in conflicts:
                continue
            stamp = datetime.strptime(key, "%Y%m%d%H%M%S").replace(tzinfo=ET)
            if (
                datetime.fromisoformat(session["open_utc"])
                <= stamp
                < datetime.fromisoformat(session["close_utc"])
            ):
                regular.setdefault(key[:8], []).append(stamp)
        longest, gaps = 0, 0
        counts = {}
        for day, stamps in regular.items():
            run = 0
            previous = None
            for stamp in stamps:
                contiguous = previous is not None and stamp - previous == timedelta(minutes=1)
                if previous is not None and not contiguous:
                    gaps += int((stamp - previous).total_seconds() // 60) - 1
                run = run + 1 if contiguous else 1
                longest = max(longest, run)
                previous = stamp
            counts[day] = len(stamps)
        result[symbol] = dict(
            native_labels=len(rows),
            regular_labels=sum(counts.values()),
            regular_session_counts=counts,
            longest_contiguous_regular_labels=longest,
            observed_internal_gaps=gaps,
            conflicting_label_versions=len(conflicts),
            label_context30=longest >= 30,
            label_context120=longest >= 120,
            label_context300=longest >= 300,
            transfer_ready=False,
        )
    return result
