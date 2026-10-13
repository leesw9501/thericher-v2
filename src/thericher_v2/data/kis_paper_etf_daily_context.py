"""Bounded current ETF intake and clock-independent replay for native Paper controls.

Only ``collect_daily_contexts`` acquires data, using caller-supplied Paper config.
Replay is offline and grants no current-intent eligibility. UTC-midnight Bar labels
are nominal provider dates, not publication times or New York session instants.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import kis_market_data as native
from thericher_v2.execution import kis_market_data_rate_gate as gates
from thericher_v2.execution import kis_private_daily_collector as storage

VERSION = "kis-paper-etf-daily-context-v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPO = os.name != "nt" and REPOSITORY_ROOT == Path("/app")
_MARKET_ROOT = Path("/app/market_data") if _DOCKER_REPO else Path("D:/market_data")
_MODEL_ROOT = (
    Path("/app/model_artifacts") if _DOCKER_REPO else Path("D:/thericher-v2/model-artifacts")
)
CACHE_ROOT = _MARKET_ROOT / "us_equities/kis_paper_private/etf-daily-context-v1"
ARTIFACT_ROOT = _MODEL_ROOT / "data/etf-daily-context-v1"
CONTROL_ROOT = CACHE_ROOT.parent / gates.KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
ETF_VENUES = MappingProxyType({"SPY": "AMS", "QQQ": "NAS", "TLT": "NAS", "GLD": "AMS"})
_SCOPE = MappingProxyType({symbol: frozenset({venue}) for symbol, venue in ETF_VENUES.items()})
_NY = ZoneInfo("America/New_York")
_COLUMNS = ("symbol", "exchange", "session_date", "open", "high", "low", "close", "volume")
_QUALIFICATIONS = (
    "source_observed_MODP0",
    "historical_point_in_time_not_qualified",
    "provider_finality_unknown",
    "corporate_actions_unverified",
    "provider_date_nominal_UTC_midnight_not_session_instant",
    "availability_post_source_publication_not_provider_close",
)
_FAILURES = frozenset(
    {
        "invalid_contract",
        "invalid_paths",
        "owner_busy",
        "storage_floor",
        "calendar_invalid",
        "daily_duplicate_conflict",
        "cursor_not_advancing",
        "completed_sessions_missing",
        "deadline_exceeded",
        "request_not_allowlisted",
        "token_request_not_due",
        "request_not_due",
        "rate_limited",
        "transport_failure",
        "auth_rejected",
        "auth_response_invalid",
        "daily_response_invalid",
        "daily_response_rejected",
        "response_invalid",
        "redirect_rejected",
        "hash_mismatch",
        "archive_invalid",
        "unexpected_failure",
        "config_missing",
        "paper_host_required",
    }
)


class DailyContextError(ValueError):
    """A source-safe categorical failure, never a company permission gate."""

    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in _FAILURES else "unexpected_failure"
        super().__init__(self.reason)


def _require(condition: bool, reason: str = "invalid_contract") -> None:
    if not condition:
        raise DailyContextError(reason)


def _utc(value: object) -> datetime:
    _require(type(value) is datetime and value.utcoffset() == timedelta(0))
    return value


def _sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(c in "0123456789abcdef" for c in value[7:])
    )


def _json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=lambda item: item.isoformat(),
        )
        + "\n"
    ).encode("ascii")


@dataclass(frozen=True)
class CompletedSession:
    provider_date: date
    calendar_close_utc: datetime

    def __post_init__(self) -> None:
        _require(type(self.provider_date) is date)
        _utc(self.calendar_close_utc)
        _require(self.calendar_close_utc.astimezone(_NY).date() == self.provider_date)


def completed_sessions(captured_at_utc: datetime) -> tuple[CompletedSession, ...]:
    """Freeze exactly253 prior NYSE dates; calendar closure is not provider finality."""
    import pandas_market_calendars as calendars

    now = _utc(captured_at_utc)
    current = now.astimezone(_NY).date()
    _require(version("pandas_market_calendars") == "5.4.0", "calendar_invalid")
    schedule = calendars.get_calendar("NYSE").schedule(current - timedelta(days=550), current)
    sessions = tuple(
        CompletedSession(label.date(), close.to_pydatetime())
        for label, close in schedule["market_close"].items()
        if label.date() < current and close.to_pydatetime() < now
    )[-253:]
    _require(len(sessions) == 253, "calendar_invalid")
    return sessions


@dataclass(frozen=True)
class DailyContextReceipt:
    """One immutable acquisition/availability contract for a full or partial snapshot."""

    symbol: str
    exchange: str
    captured_at_utc: datetime
    observed_at_utc: datetime
    first_available_at_utc: datetime
    excluded_current_us_date: date
    calendar: tuple[CompletedSession, ...]
    provider_dates: tuple[date, ...]
    raw_relative_path: str
    raw_sha256: str
    raw_size_bytes: int
    source_sha256: str
    page_count: int
    duplicate_count: int
    outside_window_count: int
    next_cursor: str | None
    source_code_sha256: tuple[tuple[str, str], ...]
    token_interval_seconds: int
    kind: str = VERSION
    calendar_version: str = "pandas_market_calendars:5.4.0/NYSE"
    qualifications: tuple[str, ...] = _QUALIFICATIONS

    def __post_init__(self) -> None:
        _require(self.kind == VERSION and ETF_VENUES.get(self.symbol) == self.exchange)
        _require(self.calendar_version == "pandas_market_calendars:5.4.0/NYSE")
        _require(self.qualifications == _QUALIFICATIONS)
        _require(
            type(self.token_interval_seconds) is int and self.token_interval_seconds in {60, 300}
        )
        _require(
            _utc(self.captured_at_utc)
            <= _utc(self.observed_at_utc)
            <= _utc(self.first_available_at_utc)
        )
        _require(
            type(self.excluded_current_us_date) is date
            and self.excluded_current_us_date == self.captured_at_utc.astimezone(_NY).date()
        )
        _require(type(self.calendar) is tuple and len(self.calendar) == 253)
        _require(all(type(s) is CompletedSession for s in self.calendar))
        for session in self.calendar:
            session.__post_init__()
        dates = tuple(s.provider_date for s in self.calendar)
        _require(dates == tuple(sorted(set(dates))))
        _require(
            all(
                s.provider_date < self.excluded_current_us_date
                and s.calendar_close_utc < self.captured_at_utc
                for s in self.calendar
            )
        )
        _require(type(self.provider_dates) is tuple and 0 < len(self.provider_dates) <= 253)
        _require(all(type(d) is date for d in self.provider_dates))
        _require(self.provider_dates == tuple(sorted(set(self.provider_dates))))
        _require(set(self.provider_dates) <= set(dates))
        _require(
            all(
                type(n) is int and n >= 0
                for n in (
                    self.raw_size_bytes,
                    self.page_count,
                    self.duplicate_count,
                    self.outside_window_count,
                )
            )
        )
        _require(0 < self.raw_size_bytes <= 1_000_000 and 1 <= self.page_count <= 4)
        _require(_is_sha(self.raw_sha256) and _is_sha(self.source_sha256))
        _require(type(self.raw_relative_path) is str)
        path = Path(self.raw_relative_path)
        _require(not path.is_absolute() and ".." not in path.parts and len(path.parts) == 2)
        _require(path.suffix == ".gz")
        _require(
            self.next_cursor is None
            or (
                type(self.next_cursor) is str
                and datetime.strptime(self.next_cursor, "%Y%m%d").strftime("%Y%m%d")
                == self.next_cursor
            )
        )
        _require(type(self.source_code_sha256) is tuple and bool(self.source_code_sha256))
        _require(
            all(
                type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str and _is_sha(pair[1])
                for pair in self.source_code_sha256
            )
        )
        _require(len({pair[0] for pair in self.source_code_sha256}) == len(self.source_code_sha256))

    @property
    def complete_253(self) -> bool:
        return self.provider_dates == tuple(s.provider_date for s in self.calendar)

    def source_document(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("first_available_at_utc")
        payload.pop("source_sha256")
        return payload

    def document(self) -> dict[str, object]:
        return dict(
            self.source_document(),
            source_sha256=self.source_sha256,
            first_available_at_utc=self.first_available_at_utc.isoformat(),
        )


@dataclass(frozen=True)
class DailyObservation:
    provider_date: date
    bar: Bar = field(repr=False)

    def __post_init__(self) -> None:
        _require(type(self.provider_date) is date and type(self.bar) is Bar)
        _require(
            self.bar.market == "US"
            and self.bar.timeframe is Timeframe.D1
            and self.bar.complete
            and self.bar.start_ts == datetime.combine(self.provider_date, datetime.min.time(), UTC)
        )


@dataclass(frozen=True)
class DailyContext:
    receipt: DailyContextReceipt
    receipt_sha256: str
    observations: tuple[DailyObservation, ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require(type(self.receipt) is DailyContextReceipt and _is_sha(self.receipt_sha256))
        _require(type(self.observations) is tuple and len(self.observations) in {2, 21, 253})
        _require(
            all(
                type(o) is DailyObservation and o.bar.symbol == self.receipt.symbol
                for o in self.observations
            )
        )
        _require(
            tuple(o.provider_date for o in self.observations)
            == self.receipt.provider_dates[-len(self.observations) :]
        )

    @property
    def bars(self) -> tuple[Bar, ...]:
        return tuple(o.bar for o in self.observations)

    def safe_payload(self) -> dict[str, object]:
        return dict(
            kind=VERSION,
            symbol=self.receipt.symbol,
            exchange=self.receipt.exchange,
            row_count=len(self.observations),
            complete_253=self.receipt.complete_253,
            first_session=self.observations[0].provider_date.isoformat(),
            last_session=self.observations[-1].provider_date.isoformat(),
            first_available_at_utc=self.receipt.first_available_at_utc.isoformat(),
            receipt_sha256=self.receipt_sha256,
            qualifications=list(self.receipt.qualifications),
        )


@dataclass(frozen=True)
class DailyCollectionResult:
    status: str
    reason: str | None
    receipts: tuple[tuple[Path, str], ...]
    token_posts: int
    daily_gets: int
    next_due_utc: datetime | None
    http_start_gaps_seconds: tuple[float, ...]

    def safe_payload(self) -> dict[str, object]:
        return dict(
            status=self.status,
            reason=self.reason,
            token_posts=self.token_posts,
            daily_gets=self.daily_gets,
            next_due_utc=self.next_due_utc.isoformat() if self.next_due_utc else None,
            receipts=[dict(path=str(p), sha256=h) for p, h in self.receipts],
            http_start_gaps_seconds=list(self.http_start_gaps_seconds),
            pacing_basis="final_opener_delegate_boundary_not_socket_wire_measurement",
        )


class _PacedOpener:
    """Final pacing and token claim after native request construction/validation."""

    def __init__(
        self,
        delegate: object,
        *,
        recheck: Callable[[], None],
        rate_gate: gates.KisPaperMarketDataRateGate,
        token_gate: gates.KisPaperMarketDataTokenStartGate,
        monotonic: Callable[[], float],
        sleeper: Callable[[float], None],
        deadline: float,
    ) -> None:
        self.delegate, self.recheck, self.rate_gate = delegate, recheck, rate_gate
        self.token_gate = token_gate
        self.monotonic, self.sleeper, self.deadline = monotonic, sleeper, deadline
        self.starts: list[float] = []
        self.last_start: float | None = None
        self.token_posts = self.daily_gets = 0

    def open(self, request: object, *, timeout: float) -> object:
        token = request.get_method() == "POST"
        _require((token and self.token_posts == 0) or (not token and self.daily_gets < 16))
        if token and not self.token_gate.token_request_is_due():
            raise DailyContextError("token_request_not_due")
        self.rate_gate.wait_for_request_slot()
        self.recheck()
        if self.last_start is not None:
            delay = max(0.0, 1.25 - (self.monotonic() - self.last_start))
            if delay:
                self.sleeper(delay)
        remaining = self.deadline - self.monotonic()
        _require(remaining > 0, "deadline_exceeded")
        timeout = min(timeout, remaining)
        if token:
            if not self.token_gate.claim_token_request_start():
                raise DailyContextError("token_request_not_due")
            self.token_posts += 1
        else:
            self.daily_gets += 1
        self.last_start = self.monotonic()
        try:
            return self.delegate.open(request, timeout=timeout)
        finally:
            self.starts.append(self.last_start)


class _DailyOnlyTransport(native.UrllibKisPaperMarketDataTransport):
    def request(self, request: native.KisMarketDataRequest) -> native.KisMarketDataResponse:
        _require(request.daily_adjustment_modes is None, "request_not_allowlisted")
        native._validate_request(request, daily_symbol_exchanges=_SCOPE)
        _require(
            urlsplit(request.url).path
            in {native.KIS_PAPER_TOKEN_PATH, native.KIS_PAPER_DAILY_PATH},
            "request_not_allowlisted",
        )
        result = super().request(request)
        if native._response_is_rate_limited(result):
            self._opener.rate_gate.record_rate_limit()
        return result


def _external(path: Path, repository_root: Path, mount_name: str | None = None) -> Path:
    path = Path(path).absolute()
    _require(
        not any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)()
            for p in (path, *path.parents)
        ),
        "invalid_paths",
    )
    resolved = path.resolve()
    repository = Path(repository_root).resolve()
    if resolved.is_relative_to(repository):
        # Standard Docker external binds are lexically under /app, not Git data.
        # The launcher owns read-only rootfs and host-source/mount attestation;
        # a mere directory named market_data/model_artifacts does not qualify.
        names = (mount_name,) if mount_name else ("market_data", "model_artifacts")
        mounted_external = (
            os.name != "nt"
            and repository == Path("/app")
            and any(
                name in {"market_data", "model_artifacts"}
                and (repository / name).is_mount()
                and resolved.is_relative_to(repository / name)
                for name in names
            )
        )
        _require(mounted_external, "invalid_paths")
    return resolved


@contextmanager
def _owned_cache(root: Path) -> Iterator[Path]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".collector.lock.d"
    try:
        lock.mkdir()
    except FileExistsError:
        raise DailyContextError("owner_busy") from None
    try:
        yield lock
    finally:
        lock.rmdir()


def _source_pins() -> tuple[tuple[str, str], ...]:
    # Record the required native leaf origins, never mutable whole-checkout pins.
    return tuple(
        (name, _sha(Path(path).read_bytes()))
        for name, path in (
            (VERSION, __file__),
            ("native_market_data", native.__file__),
            ("native_token_gate", gates.__file__),
            ("native_daily_storage", storage.__file__),
            ("native_bar", REPOSITORY_ROOT / "src/thericher_v2/contracts.py"),
        )
    )


def collect_daily_contexts(
    config: native.KisPaperMarketDataConfig,
    *,
    cache_root: Path = CACHE_ROOT,
    artifact_root: Path = ARTIFACT_ROOT,
    control_root: Path = CONTROL_ROOT,
    repository_root: Path = REPOSITORY_ROOT,
    token_interval_seconds: int = 300,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    before_http: Callable[[], None] = lambda: None,
) -> DailyCollectionResult:
    """One client, <=1 token POST, <=4 pages/name and <=16 daily GETs, no retries.

    Data defaults to300s; explicit60s joins the observer's documented issuance
    floor. Neither choice resets shared timing or persists a token. A120s worker
    deadline stops new starts; each native socket timeout is capped by remaining
    time (not a guarantee against OS suspension or arbitrarily slow body trickle).
    A held claim has no TTL reclamation. Existing/frozen namespaces are untouched.
    """
    _require(type(config) is native.KisPaperMarketDataConfig)
    _require(type(token_interval_seconds) is int and token_interval_seconds in {60, 300})
    cache = _external(cache_root, repository_root, "market_data")
    artifacts = _external(artifact_root, repository_root, "model_artifacts")
    control = _external(control_root, repository_root, "market_data")
    _require(
        cache.name == CACHE_ROOT.name and artifacts.name == ARTIFACT_ROOT.name, "invalid_paths"
    )
    _require(
        not artifacts.is_relative_to(cache)
        and not cache.is_relative_to(artifacts)
        and control == cache.parent / gates.KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
        "invalid_paths",
    )
    receipts: list[tuple[Path, str]] = []
    opener = None
    next_due = None
    full_count = 0
    reason = None
    try:
        with _owned_cache(cache) as lock:
            _require(
                not storage.private_daily_cache_would_cross_free_space_floor(
                    cache_root=cache, repo_root=repository_root, projected_bytes=2_000_000
                ),
                "storage_floor",
            )
            captured = _utc(clock())
            calendar = completed_sessions(captured)
            pins = _source_pins()
            run = uuid.uuid4().hex
            raw_root, evidence_root = cache / run, artifacts / run
            raw_root.mkdir()
            evidence_root.mkdir(parents=True)
            deadline = monotonic() + 120

            def bounded_sleep(delay: float) -> None:
                _require(math.isfinite(delay) and 0 <= delay <= 2, "request_not_due")
                _require(monotonic() + delay < deadline, "deadline_exceeded")
                sleeper(delay)

            token_gate = gates.KisPaperMarketDataTokenStartGate(
                control_root=control,
                minimum_request_interval_seconds=token_interval_seconds,
                clock=clock,
            )
            rate_gate = gates.KisPaperMarketDataRateGate(
                control_root=control, clock=clock, sleeper=bounded_sleep
            )

            def recheck() -> None:
                before_http()
                _require(lock.is_dir() and not lock.is_symlink(), "owner_busy")
                _require(monotonic() < deadline, "deadline_exceeded")
                _require(
                    _utc(clock()).astimezone(_NY).date() == captured.astimezone(_NY).date(),
                    "calendar_invalid",
                )

            # Only this leaf defers the claim until final opener pacing/rechecks.
            transport = _DailyOnlyTransport(token_start_gate=None)
            opener = _PacedOpener(
                transport._opener,
                recheck=recheck,
                rate_gate=rate_gate,
                token_gate=token_gate,
                monotonic=monotonic,
                sleeper=bounded_sleep,
                deadline=deadline,
            )
            transport._opener = opener
            client = native.KisPaperMarketDataClient(
                config=config, transport=transport, max_daily_page_attempts=16
            )
            client.ensure_authenticated()
            for symbol, exchange in ETF_VENUES.items():
                rows: dict[str, native.KisPaperDailyRawRow] = {}
                duplicates = 0
                cursor = captured.astimezone(_NY).strftime("%Y%m%d")
                continuation = None
                baseline_published = False
                expected = {s.provider_date.strftime("%Y%m%d") for s in calendar}
                for page_count in range(1, 5):
                    recheck()
                    query = native.KisPaperDailyQuery(
                        symbol, cursor, continuation, exchange, _SCOPE
                    )
                    page = client.fetch_daily_raw_page(query)
                    _require(monotonic() < deadline, "deadline_exceeded")
                    _require(page.page.query == query, "daily_response_invalid")
                    for row in page.rows:
                        try:
                            datetime.strptime(row.xymd, "%Y%m%d")
                        except ValueError:
                            raise DailyContextError("daily_response_invalid") from None
                    rows, count = storage._merge_daily_rows(rows, page.rows)
                    duplicates += count
                    observed = _utc(clock())
                    retained = tuple(rows[d] for d in sorted(expected & rows.keys()))
                    outside = len(rows.keys() - expected)
                    oldest = min(rows) if rows else None
                    next_cursor = None
                    if oldest is not None:
                        next_cursor = (
                            datetime.strptime(oldest, "%Y%m%d").date() - timedelta(days=1)
                        ).strftime("%Y%m%d")
                    publication = dict(
                        raw_root=raw_root,
                        evidence_root=evidence_root,
                        symbol=symbol,
                        exchange=exchange,
                        captured=captured,
                        observed=observed,
                        calendar=calendar,
                        pins=pins,
                        pages=page_count,
                        duplicates=duplicates,
                        outside=outside,
                        cursor=next_cursor,
                        token_interval=token_interval_seconds,
                        clock=clock,
                    )
                    if (
                        symbol == "SPY"
                        and not baseline_published
                        and all(d in rows for d in sorted(expected)[-2:])
                    ):
                        receipts.append(
                            _publish(
                                rows=tuple(rows[d] for d in sorted(expected)[-2:]),
                                name="SPY-baseline2",
                                **publication,
                            )
                        )
                        baseline_published = True
                    if len(retained) == 253 or page_count == 4 or not page.rows:
                        if retained:
                            receipts.append(
                                _publish(
                                    rows=retained,
                                    name=symbol,
                                    **publication,
                                )
                            )
                        full_count += int(len(retained) == 253)
                        break
                    _require(
                        next_cursor is not None and next_cursor < cursor, "cursor_not_advancing"
                    )
                    cursor, continuation = next_cursor, page.page.continuation_value
    except Exception as error:
        reason = _safe_reason(error)
        if reason == "token_request_not_due":
            try:
                next_due = token_gate.snapshot().next_token_request_not_before_utc
            except (ValueError, OSError):
                pass  # Busy/corrupt state is not cleared or guessed due.
        elif reason in {"rate_limited", "request_not_due"}:
            try:
                rate = rate_gate.snapshot()
                token = token_gate.snapshot()
                due = [
                    d
                    for d in (
                        rate.retry_not_before_utc,
                        rate.last_request_started_at_utc + timedelta(seconds=1)
                        if rate.last_request_started_at_utc
                        else None,
                        token.next_token_request_not_before_utc,
                    )
                    if d is not None
                ]
                next_due = max(due) if due else None
            except (ValueError, OSError):
                pass
    status = "complete" if full_count == 4 and reason is None else "incomplete"
    return DailyCollectionResult(
        status,
        reason or ("completed_sessions_missing" if status == "incomplete" else None),
        tuple(receipts),
        opener.token_posts if opener else 0,
        opener.daily_gets if opener else 0,
        next_due,
        tuple(b - a for a, b in zip(opener.starts, opener.starts[1:], strict=False))
        if opener
        else (),
    )


def _safe_reason(error: Exception) -> str:
    if isinstance(
        error,
        (
            DailyContextError,
            native.KisPaperMarketDataError,
            storage.KisPaperPrivateDailyCollectorError,
        ),
    ):
        reason = str(error)
        return reason if reason in _FAILURES else "unexpected_failure"
    return "unexpected_failure"


def _publish(
    *,
    rows: tuple[native.KisPaperDailyRawRow, ...],
    name: str,
    raw_root: Path,
    evidence_root: Path,
    symbol: str,
    exchange: str,
    captured: datetime,
    observed: datetime,
    calendar: tuple[CompletedSession, ...],
    pins: tuple[tuple[str, str], ...],
    pages: int,
    duplicates: int,
    outside: int,
    cursor: str | None,
    token_interval: int,
    clock: Callable[[], datetime],
) -> tuple[Path, str]:
    payload = storage._compressed_raw_daily_csv(rows, symbol=symbol, exchange=exchange)
    storage._validate_compressed_raw_daily_csv(
        payload, expected_rows=rows, symbol=symbol, exchange=exchange
    )
    raw_path = raw_root / f"{name}.csv.gz"
    storage._write_bytes_and_sync(raw_path, payload)
    _require(_sha(raw_path.read_bytes()) == _sha(payload), "hash_mismatch")
    base = DailyContextReceipt(
        symbol,
        exchange,
        captured,
        observed,
        observed,
        captured.astimezone(_NY).date(),
        calendar,
        tuple(datetime.strptime(r.xymd, "%Y%m%d").date() for r in rows),
        f"{raw_root.name}/{raw_path.name}",
        _sha(payload),
        len(payload),
        "sha256:" + "0" * 64,
        pages,
        duplicates,
        outside,
        cursor,
        pins,
        token_interval,
    )
    target = evidence_root / name
    target.mkdir()
    source = _json(base.source_document())
    source_path = target / "source.json"
    storage._write_bytes_and_sync(source_path, source)
    _require(source_path.read_bytes() == source, "hash_mismatch")
    # Availability is sampled AFTER both raw and source metadata are durably published.
    receipt = DailyContextReceipt(
        **{**base.__dict__, "source_sha256": _sha(source), "first_available_at_utc": _utc(clock())}
    )
    encoded = _json(receipt.document())
    path = target / "receipt.json"
    storage._write_bytes_and_sync(path, encoded)
    return path, _sha(encoded)


def read_daily_context(
    receipt_path: Path,
    expected_receipt_sha256: str,
    *,
    cache_root: Path = CACHE_ROOT,
    required_count: int = 253,
    repository_root: Path = REPOSITORY_ROOT,
) -> DailyContext:
    """Replay a pinned source with native Bars; no current clock/calendar/auth/IO writes.

    ``required_count`` selects2/21/253 consecutive tail sessions from retained
    facts. Missing input fails; dates and original availability are never shifted.
    """
    _require(type(required_count) is int and required_count in {2, 21, 253})
    _require(_is_sha(expected_receipt_sha256))
    cache = _external(cache_root, repository_root, "market_data")
    path = _external(receipt_path, repository_root, "model_artifacts")
    try:
        _require(path.stat().st_size <= 100_000, "archive_invalid")
        encoded = path.read_bytes()
        _require(_sha(encoded) == expected_receipt_sha256, "hash_mismatch")
        document = json.loads(encoded)
        receipt = _parse_receipt(document)
        source = _external(
            path.with_name("source.json"), repository_root, "model_artifacts"
        ).read_bytes()
        _require(
            _sha(source) == receipt.source_sha256 and source == _json(receipt.source_document()),
            "hash_mismatch",
        )
        raw_path = _external(cache / receipt.raw_relative_path, repository_root, "market_data")
        _require(raw_path.is_relative_to(cache), "invalid_paths")
        _require(raw_path.stat().st_size == receipt.raw_size_bytes, "hash_mismatch")
        packed = raw_path.read_bytes()
        _require(_sha(packed) == receipt.raw_sha256, "hash_mismatch")
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as handle:
            text = handle.read(1_000_001)
        _require(len(text) <= 1_000_000, "archive_invalid")
        reader = csv.DictReader(io.StringIO(text.decode("ascii")))
        _require(tuple(reader.fieldnames or ()) == _COLUMNS, "archive_invalid")
        observations = []
        for row in reader:
            _require(set(row) == set(_COLUMNS), "archive_invalid")
            _require(
                row["symbol"] == receipt.symbol and row["exchange"] == receipt.exchange,
                "archive_invalid",
            )
            provider_date = date.fromisoformat(row["session_date"])
            raw = native.KisPaperDailyRawRow(
                provider_date.strftime("%Y%m%d"),
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
            )
            bar = Bar(
                receipt.symbol,
                "US",
                Timeframe.D1,
                datetime.combine(provider_date, datetime.min.time(), UTC),
                raw.open,
                raw.high,
                raw.low,
                raw.clos,
                raw.tvol,
            )
            observations.append(DailyObservation(provider_date, bar))
        _require(
            tuple(o.provider_date for o in observations) == receipt.provider_dates,
            "archive_invalid",
        )
        tail = tuple(s.provider_date for s in receipt.calendar[-required_count:])
        _require(receipt.provider_dates[-required_count:] == tail, "completed_sessions_missing")
        return DailyContext(receipt, expected_receipt_sha256, tuple(observations[-required_count:]))
    except DailyContextError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        native.KisPaperMarketDataError,
    ):
        raise DailyContextError("archive_invalid") from None


def _parse_receipt(document: object) -> DailyContextReceipt:
    _require(type(document) is dict, "archive_invalid")
    values = dict(document)
    for name in ("captured_at_utc", "observed_at_utc", "first_available_at_utc"):
        _require(type(values[name]) is str, "archive_invalid")
        values[name] = datetime.fromisoformat(values[name])
    values["excluded_current_us_date"] = date.fromisoformat(values["excluded_current_us_date"])
    values["provider_dates"] = tuple(date.fromisoformat(d) for d in values["provider_dates"])
    values["calendar"] = tuple(
        CompletedSession(
            date.fromisoformat(s["provider_date"]), datetime.fromisoformat(s["calendar_close_utc"])
        )
        for s in values["calendar"]
    )
    values["source_code_sha256"] = tuple(tuple(p) for p in values["source_code_sha256"])
    values["qualifications"] = tuple(values["qualifications"])
    return DailyContextReceipt(**values)
