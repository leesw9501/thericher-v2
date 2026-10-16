"""Finite, versioned native-minute input for frozen cross-sectional experts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
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


class FoundationOwner:
    """Exclusive custody for this collector's ledger and immutable page namespace."""

    def __init__(self, market_root: Path) -> None:
        self.path = Path(market_root) / "owner.lock.d"
        self.identity: tuple[int, int] | None = None
        self.document = dict(pid=os.getpid(), nonce=uuid.uuid4().hex, version=VERSION)
        self.published = False

    def require_held(self) -> None:
        current = self.path.stat(follow_symlinks=False)
        if (
            self.identity != (current.st_dev, current.st_ino)
            or not stat.S_ISDIR(current.st_mode)
            or getattr(current, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValueError("foundation_lease_identity_changed")
        if self.published:
            marker = self.path / "owner.json"
            info = marker.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                or json.loads(marker.read_bytes()) != self.document
            ):
                raise ValueError("foundation_lease_owner_changed")

    def __enter__(self) -> FoundationOwner:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.mkdir()
        current = self.path.stat(follow_symlinks=False)
        self.identity = (current.st_dev, current.st_ino)
        try:
            atomic_json(self.path / "owner.json", self.document)
            self.published = True
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        self.require_held()
        for name in ("owner.json", "owner.json.pending"):
            path = self.path / name
            if path.exists():
                if path.is_symlink() or not path.is_file():
                    raise ValueError("foundation_lease_file_changed")
                path.unlink()
        self.path.rmdir()
        self.identity = None


class FoundationLedger:
    def __init__(
        self,
        *,
        artifact_root: Path,
        market_root: Path,
        targets: Sequence[tuple[str, str]],
        sessions: Sequence[Mapping[str, str]],
        owner: FoundationOwner,
        normal_cap: int = 600,
        retry_cap: int = 2,
    ) -> None:
        if tuple(s for s, _ in targets) != COHORT or len(set(targets)) != len(COHORT):
            raise ValueError("foundation requires the exact ordered FirstRate20 cohort")
        if not 1 <= normal_cap <= 600 or not 0 <= retry_cap <= 2:
            raise ValueError("foundation request caps are invalid")
        self.artifact_root, self.market_root = Path(artifact_root), Path(market_root)
        if owner.path.parent != self.market_root:
            raise ValueError("foundation_owner_scope_mismatch")
        owner.require_held()
        self.owner = owner
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
        self.owner.require_held()
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
        self.owner.require_held()
        persisted = json.loads((self.artifact_root / "cursor.json").read_bytes())
        if self.state["pending"] is not None or persisted["pending"] is not None:
            raise ValueError("foundation_pending_unknown")
        failed = None
        if method == "POST":
            if retry or query is not None:
                raise ValueError("foundation_wire_scope")
            if self.state["POST"] >= 1:
                raise ValueError("foundation_auth_cap")
        elif method == "GET" and query is not None:
            if self.state["GET"] >= self.normal_cap + self.retry_cap:
                raise ValueError("foundation_GET_cap")
            if retry:
                if self.state["retry"] >= self.retry_cap:
                    raise ValueError("foundation_retry_cap")
                failed = next(reversed(self.state.get("failed_attempts", [])), None)
                if (
                    failed is None
                    or failed["query"] != query_document(query)
                    or failed["GET"] != self.state["GET"]
                    or failed["reason"] != "transport_failure"
                    or failed.get("retry_started")
                    or next(reversed(persisted.get("failed_attempts", [])), None) != failed
                ):
                    raise ValueError("foundation_exact_failed_attempt_required")
                self.state["retry"] += 1
            else:
                if self.state["normal_GET"] >= self.normal_cap:
                    raise ValueError("foundation_normal_GET_cap")
                self.state["normal_GET"] += 1
        else:
            raise ValueError("foundation_wire_scope")
        self.state[method] += 1
        if failed is not None:
            failed["retry_started"] = self.state["GET"]
        self.state["pending"] = dict(
            method=method,
            query=query_document(query) if query else None,
            attempt=self.state[method],
        )
        self.save()

    def authentication_completed(self) -> None:
        if self.state["pending"] is None or self.state["pending"]["method"] != "POST":
            raise ValueError("foundation_pending_POST_required")
        self.state["authenticated_POST"] = self.state["POST"]
        self.state["pending"] = None
        self.save()

    def _require_pending_GET(self, query: KisPaperHistoricalMinuteQuery) -> None:
        pending = self.state["pending"]
        if (
            pending is None
            or pending["method"] != "GET"
            or pending["query"] != query_document(query)
        ):
            raise ValueError("foundation_pending_exact_GET_required")

    def retain_raw(self, body: bytes) -> dict[str, str]:
        pending = self.state["pending"]
        if pending is None or pending["method"] != "GET":
            raise ValueError("foundation_pending_GET_required")
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
        self._require_pending_GET(query)
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
        self.state["pending"] = None
        self.save()

    def reject(
        self,
        query: KisPaperHistoricalMinuteQuery,
        reason: str,
        raw: Mapping[str, str] | None,
        *,
        retryable: bool = False,
    ) -> None:
        if self.state["pending"] is not None or retryable:
            self._require_pending_GET(query)
        outcome = dict(
            query=query_document(query),
            raw=raw,
            accepted=False,
            reason=reason,
            capture_utc=datetime.now(UTC).isoformat(),
            GET=self.state["GET"],
        )
        if retryable:
            if reason != "transport_failure":
                raise ValueError("foundation_technical_retry_only")
            self.state.setdefault("failed_attempts", []).append(outcome)
        else:
            self.state["pages"].append(outcome)
            self.state["cursors"][query.symbol].update(
                status="exact_cursor_failed", failed_key=query.continuation_key
            )
        self.state["pending"] = None
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
                retryable = (
                    reason == "transport_failure"
                    and attempt == 0
                    and ledger.state["retry"] < ledger.retry_cap
                )
                ledger.reject(query, reason, raw_failure(), retryable=retryable)
                if retryable:
                    continue
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
