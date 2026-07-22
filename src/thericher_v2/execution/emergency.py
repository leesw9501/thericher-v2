"""Local emergency and directional-control persistence.

This module does not call a broker. It records local operator intent for the
execution paths that consume it.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.contracts import EmergencyState
from thericher_v2.serialization import to_jsonable

_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
DEFAULT_PAPER_EXECUTION_CONTROL_STATE = Path("runtime/paper_execution_control.json")
_PAPER_EXECUTION_CONTROL_REASONS = frozenset(
    {
        "default_clear",
        "dashboard_pause_buys",
        "dashboard_resume_buys",
        "dashboard_pause_sells",
        "dashboard_resume_sells",
        "execution_control_unreadable_or_malformed",
    }
)


@dataclass(frozen=True)
class PaperExecutionControlState:
    """Directional, local-only model controls distinct from an emergency stop."""

    pause_buys: bool
    pause_sells: bool
    reason: str
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.pause_buys, bool) or not isinstance(self.pause_sells, bool):
            raise ValueError("paper execution control flags are invalid")
        if self.reason not in _PAPER_EXECUTION_CONTROL_REASONS:
            raise ValueError("paper execution control reason is invalid")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("paper execution control timestamp must include a timezone")
        object.__setattr__(self, "updated_at", self.updated_at.astimezone(UTC))


def _lock_for(path: Path) -> threading.RLock:
    resolved_path = path.resolve()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved_path, threading.RLock())


@contextmanager
def _exclusive_path_lock(path: Path) -> Iterator[None]:
    """Serialize state transitions across threads and processes in one runtime."""

    with _lock_for(path):
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            _acquire_file_lock(lock_file)
            try:
                yield
            finally:
                _release_file_lock(lock_file)


def _acquire_file_lock(lock_file: object) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0, os.SEEK_END)  # type: ignore[attr-defined]
        if lock_file.tell() == 0:  # type: ignore[attr-defined]
            lock_file.write(b"\0")  # type: ignore[attr-defined]
            lock_file.flush()  # type: ignore[attr-defined]
        lock_file.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]


def _release_file_lock(lock_file: object) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


class EmergencyStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> EmergencyState:
        try:
            with _exclusive_path_lock(self.path):
                return self._read_unlocked()
        except OSError:
            return _fail_closed_state()

    def _read_unlocked(self) -> EmergencyState:
        try:
            contents = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _default_clear_state()
        except OSError:
            return _fail_closed_state()
        try:
            payload = json.loads(contents)
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("stop_new_orders"), bool)
                or not isinstance(payload.get("cancel_open_orders_requested"), bool)
                or not isinstance(payload.get("reason", ""), str)
                or not isinstance(payload.get("updated_at"), str)
            ):
                raise ValueError("invalid emergency state")
            updated_at = datetime.fromisoformat(payload["updated_at"])
            if updated_at.tzinfo is None or updated_at.utcoffset() is None:
                raise ValueError("emergency state timestamp must include a timezone")
            return EmergencyState(
                stop_new_orders=payload["stop_new_orders"],
                cancel_open_orders_requested=payload["cancel_open_orders_requested"],
                reason=payload.get("reason", ""),
                updated_at=updated_at.astimezone(UTC),
            )
        except (OSError, TypeError, ValueError):
            return _fail_closed_state()

    def write(self, state: EmergencyState) -> EmergencyState:
        with _exclusive_path_lock(self.path):
            return self._write_unlocked(state)

    def _write_unlocked(self, state: EmergencyState) -> EmergencyState:
        _write_json_atomically(self.path, state)
        return state

    def stop_new_orders(self, reason: str) -> EmergencyState:
        with _exclusive_path_lock(self.path):
            current = self._read_unlocked()
            return self._write_unlocked(
                EmergencyState(
                    stop_new_orders=True,
                    cancel_open_orders_requested=current.cancel_open_orders_requested,
                    reason=reason,
                    updated_at=datetime.now(UTC),
                )
            )

    def request_cancel_open_orders(self, reason: str) -> EmergencyState:
        with _exclusive_path_lock(self.path):
            current = self._read_unlocked()
            return self._write_unlocked(
                EmergencyState(
                    stop_new_orders=current.stop_new_orders,
                    cancel_open_orders_requested=True,
                    reason=reason,
                    updated_at=datetime.now(UTC),
                )
            )

    def clear(self, reason: str) -> EmergencyState:
        with _exclusive_path_lock(self.path):
            return self._write_unlocked(
                EmergencyState(
                    stop_new_orders=False,
                    cancel_open_orders_requested=False,
                    reason=reason,
                    updated_at=datetime.now(UTC),
                )
            )


class PaperExecutionControlStore:
    """Persist buy/sell pauses without changing emergency-stop semantics."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> PaperExecutionControlState:
        try:
            with _exclusive_path_lock(self.path):
                return self._read_unlocked()
        except OSError:
            return _fail_closed_paper_execution_control_state()

    def _read_unlocked(self) -> PaperExecutionControlState:
        try:
            contents = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _default_paper_execution_control_state()
        except OSError:
            return _fail_closed_paper_execution_control_state()
        try:
            payload = json.loads(contents)
            if (
                not isinstance(payload, dict)
                or frozenset(payload) != {"pause_buys", "pause_sells", "reason", "updated_at"}
                or not isinstance(payload["pause_buys"], bool)
                or not isinstance(payload["pause_sells"], bool)
                or not isinstance(payload["reason"], str)
                or not isinstance(payload["updated_at"], str)
            ):
                raise ValueError("invalid paper execution control state")
            return PaperExecutionControlState(
                pause_buys=payload["pause_buys"],
                pause_sells=payload["pause_sells"],
                reason=payload["reason"],
                updated_at=datetime.fromisoformat(payload["updated_at"]),
            )
        except (OSError, TypeError, ValueError):
            return _fail_closed_paper_execution_control_state()

    def set_pause_buys(self, paused: bool) -> PaperExecutionControlState:
        if type(paused) is not bool:
            raise TypeError("paused must be a bool")
        with _exclusive_path_lock(self.path):
            current = self._read_unlocked()
            return self._write_unlocked(
                PaperExecutionControlState(
                    pause_buys=paused,
                    pause_sells=current.pause_sells,
                    reason="dashboard_pause_buys" if paused else "dashboard_resume_buys",
                    updated_at=datetime.now(UTC),
                )
            )

    def set_pause_sells(self, paused: bool) -> PaperExecutionControlState:
        if type(paused) is not bool:
            raise TypeError("paused must be a bool")
        with _exclusive_path_lock(self.path):
            current = self._read_unlocked()
            return self._write_unlocked(
                PaperExecutionControlState(
                    pause_buys=current.pause_buys,
                    pause_sells=paused,
                    reason="dashboard_pause_sells" if paused else "dashboard_resume_sells",
                    updated_at=datetime.now(UTC),
                )
            )

    def _write_unlocked(self, state: PaperExecutionControlState) -> PaperExecutionControlState:
        _write_json_atomically(self.path, state)
        return state


def _default_clear_state() -> EmergencyState:
    return EmergencyState(
        stop_new_orders=False,
        cancel_open_orders_requested=False,
        reason="default_clear",
        updated_at=datetime.now(UTC),
    )


def _fail_closed_state() -> EmergencyState:
    return EmergencyState(
        stop_new_orders=True,
        cancel_open_orders_requested=False,
        reason="emergency_state_unreadable_or_malformed",
        updated_at=datetime.now(UTC),
    )


def _default_paper_execution_control_state() -> PaperExecutionControlState:
    return PaperExecutionControlState(
        pause_buys=False,
        pause_sells=False,
        reason="default_clear",
        updated_at=datetime.now(UTC),
    )


def _fail_closed_paper_execution_control_state() -> PaperExecutionControlState:
    return PaperExecutionControlState(
        pause_buys=True,
        pause_sells=True,
        reason="execution_control_unreadable_or_malformed",
        updated_at=datetime.now(UTC),
    )


def _write_json_atomically(path: Path, state: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(json.dumps(to_jsonable(state), indent=2, sort_keys=True))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
