"""Durable request pacing for private KIS Paper market-data workers.

The gate stores only categorical timing state under the external market-data
root.  It never receives credentials, response bodies, account facts, or raw
market rows.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY = "collection-control-v1"
KIS_PAPER_MARKET_DATA_RATE_STATE_FILENAME = "request-rate.json"
KIS_PAPER_MARKET_DATA_RATE_LOCK_FILENAME = "request-rate.lock"
KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS = 1.0
KIS_PAPER_MARKET_DATA_RATE_LIMIT_BACKOFF_SECONDS = 60.0
KIS_PAPER_MARKET_DATA_TOKEN_STATE_FILENAME = "token-request.json"
KIS_PAPER_MARKET_DATA_TOKEN_LOCK_FILENAME = "token-request.lock"
KIS_PAPER_MARKET_DATA_TOKEN_MIN_REQUEST_INTERVAL_SECONDS = 300.0
KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON = "token_request_not_due"
_SCHEMA_VERSION = 1
_TOKEN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class KisPaperMarketDataRateGateSnapshot:
    """Sanitized durable timing facts for one private market-data app pair."""

    last_request_started_at_utc: datetime | None
    retry_not_before_utc: datetime | None
    last_rate_limit_at_utc: datetime | None


@dataclass(frozen=True)
class KisPaperMarketDataTokenStartGateSnapshot:
    """Sanitized token-request timing facts shared by short-lived workers."""

    last_token_request_started_at_utc: datetime | None
    next_token_request_not_before_utc: datetime | None


class KisPaperMarketDataRateGate:
    """Serialize request starts across Docker workers sharing one data root."""

    def __init__(
        self,
        *,
        control_root: Path,
        minimum_request_interval_seconds: float = (
            KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
        ),
        rate_limit_backoff_seconds: float = KIS_PAPER_MARKET_DATA_RATE_LIMIT_BACKOFF_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = time.sleep,
        on_request_started: Callable[[datetime], None] | None = None,
    ) -> None:
        if not _is_positive_finite(minimum_request_interval_seconds):
            raise ValueError("market-data request interval must be positive")
        if not _is_positive_finite(rate_limit_backoff_seconds):
            raise ValueError("market-data rate-limit backoff must be positive")
        self._control_root = Path(control_root)
        self._minimum_request_interval = timedelta(seconds=float(minimum_request_interval_seconds))
        self._rate_limit_backoff = timedelta(seconds=float(rate_limit_backoff_seconds))
        self._clock = clock
        self._sleeper = sleeper
        self._on_request_started = on_request_started

    def wait_for_request_slot(self) -> None:
        """Block only until this one external request may start safely."""

        while True:
            with self._locked_state() as state:
                now = _require_utc(self._clock())
                due = _next_request_due(
                    state=state,
                    minimum_interval=self._minimum_request_interval,
                )
                if due is None or now >= due:
                    state["last_request_started_at_utc"] = _format_utc(now)
                    _write_state(self._state_path(), state)
                    if self._on_request_started is not None:
                        self._on_request_started(now)
                    return
                delay = (due - now).total_seconds()
            self._sleeper(max(delay, 0.001))

    def record_rate_limit(self) -> None:
        """Persist a shared bounded cooldown after a categorical limit response."""

        with self._locked_state() as state:
            now = _require_utc(self._clock())
            requested_retry = now + self._rate_limit_backoff
            current_retry = _parse_optional_utc(state.get("retry_not_before_utc"))
            retry_at = max(requested_retry, current_retry or requested_retry)
            state["last_rate_limit_at_utc"] = _format_utc(now)
            state["retry_not_before_utc"] = _format_utc(retry_at)
            _write_state(self._state_path(), state)

    def snapshot(self) -> KisPaperMarketDataRateGateSnapshot:
        with self._locked_state() as state:
            return KisPaperMarketDataRateGateSnapshot(
                last_request_started_at_utc=_parse_optional_utc(
                    state.get("last_request_started_at_utc")
                ),
                retry_not_before_utc=_parse_optional_utc(state.get("retry_not_before_utc")),
                last_rate_limit_at_utc=_parse_optional_utc(state.get("last_rate_limit_at_utc")),
            )

    @contextmanager
    def _locked_state(self) -> Iterator[dict[str, object]]:
        root = self._control_root
        if root.is_symlink():
            raise ValueError("market-data rate control root is invalid")
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("market-data rate control root is invalid")
        with _exclusive_lock(root / KIS_PAPER_MARKET_DATA_RATE_LOCK_FILENAME):
            yield _read_state(self._state_path())

    def _state_path(self) -> Path:
        path = self._control_root / KIS_PAPER_MARKET_DATA_RATE_STATE_FILENAME
        if path.is_symlink():
            raise ValueError("market-data rate state is invalid")
        return path


class KisPaperMarketDataTokenStartGate:
    """Atomically reserve a spaced KIS Paper token request without sleeping."""

    def __init__(
        self,
        *,
        control_root: Path,
        minimum_request_interval_seconds: float = (
            KIS_PAPER_MARKET_DATA_TOKEN_MIN_REQUEST_INTERVAL_SECONDS
        ),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not _is_positive_finite(minimum_request_interval_seconds):
            raise ValueError("market-data token interval must be positive")
        self._control_root = Path(control_root)
        self._minimum_request_interval = timedelta(seconds=float(minimum_request_interval_seconds))
        self._clock = clock

    def claim_token_request_start(self) -> bool:
        """Return whether this worker may start a token POST now.

        A false result has no network side effect. The owner should yield to
        another lane or its next schedule rather than sleeping for the interval.
        """

        with self._locked_state() as state:
            now = _require_utc(self._clock())
            due = _next_token_request_due(
                state=state,
                minimum_interval=self._minimum_request_interval,
            )
            if due is not None and now < due:
                return False
            state["last_token_request_started_at_utc"] = _format_utc(now)
            _write_state(self._state_path(), state)
            return True

    def token_request_is_due(self) -> bool:
        """Return whether a token POST could start now without reserving it.

        Callers use this inexpensive pre-check to avoid entering the ordinary
        request pacing wait when another short-lived worker has already claimed
        the five-minute token window.  ``claim_token_request_start`` remains
        the atomic decision immediately before the actual request.
        """

        with self._locked_state() as state:
            due = _next_token_request_due(
                state=state,
                minimum_interval=self._minimum_request_interval,
            )
            return due is None or _require_utc(self._clock()) >= due

    def snapshot(self) -> KisPaperMarketDataTokenStartGateSnapshot:
        with self._locked_state() as state:
            last_started = _parse_optional_utc(state.get("last_token_request_started_at_utc"))
            return KisPaperMarketDataTokenStartGateSnapshot(
                last_token_request_started_at_utc=last_started,
                next_token_request_not_before_utc=(
                    None if last_started is None else last_started + self._minimum_request_interval
                ),
            )

    @contextmanager
    def _locked_state(self) -> Iterator[dict[str, object]]:
        root = self._control_root
        if root.is_symlink():
            raise ValueError("market-data token control root is invalid")
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("market-data token control root is invalid")
        with _exclusive_lock(root / KIS_PAPER_MARKET_DATA_TOKEN_LOCK_FILENAME):
            yield _read_token_state(self._state_path())

    def _state_path(self) -> Path:
        path = self._control_root / KIS_PAPER_MARKET_DATA_TOKEN_STATE_FILENAME
        if path.is_symlink():
            raise ValueError("market-data token state is invalid")
        return path


def _is_positive_finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("market-data rate clock must return UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return _require_utc(value).isoformat().replace("+00:00", "Z")


def _parse_optional_utc(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("market-data rate state is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("market-data rate state is invalid") from error
    return _require_utc(parsed)


def _next_request_due(
    *,
    state: dict[str, object],
    minimum_interval: timedelta,
) -> datetime | None:
    last_request = _parse_optional_utc(state.get("last_request_started_at_utc"))
    retry_not_before = _parse_optional_utc(state.get("retry_not_before_utc"))
    candidates = [
        item
        for item in (
            retry_not_before,
            last_request and last_request + minimum_interval,
        )
        if item
    ]
    return max(candidates) if candidates else None


def _next_token_request_due(
    *,
    state: dict[str, object],
    minimum_interval: timedelta,
) -> datetime | None:
    last_started = _parse_optional_utc(state.get("last_token_request_started_at_utc"))
    return None if last_started is None else last_started + minimum_interval


def _initial_state() -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "last_request_started_at_utc": None,
        "retry_not_before_utc": None,
        "last_rate_limit_at_utc": None,
    }


def _initial_token_state() -> dict[str, object]:
    return {
        "schema_version": _TOKEN_SCHEMA_VERSION,
        "last_token_request_started_at_utc": None,
    }


def _read_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return _initial_state()
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("market-data rate state is invalid") from error
    if not isinstance(decoded, dict) or decoded.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("market-data rate state is invalid")
    expected = set(_initial_state())
    if set(decoded) != expected:
        raise ValueError("market-data rate state is invalid")
    for key in (
        "last_request_started_at_utc",
        "retry_not_before_utc",
        "last_rate_limit_at_utc",
    ):
        _parse_optional_utc(decoded.get(key))
    return dict(decoded)


def _read_token_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return _initial_token_state()
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("market-data token state is invalid") from error
    if not isinstance(decoded, dict) or decoded.get("schema_version") != _TOKEN_SCHEMA_VERSION:
        raise ValueError("market-data token state is invalid")
    if set(decoded) != set(_initial_token_state()):
        raise ValueError("market-data token state is invalid")
    _parse_optional_utc(decoded.get("last_token_request_started_at_utc"))
    return dict(decoded)


def _write_state(path: Path, state: dict[str, object]) -> None:
    payload = json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}.stage")
    try:
        with staging.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    if path.is_symlink():
        raise ValueError("market-data rate lock is invalid")
    with path.open("a+b") as handle:
        _lock(handle)
        try:
            yield
        finally:
            _unlock(handle)


def _lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock(handle: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
