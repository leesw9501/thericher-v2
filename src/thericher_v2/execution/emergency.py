"""Local emergency-state persistence.

This module does not call a broker. It records operator intent so the future
execution adapter can block new orders or cancel open orders.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.contracts import EmergencyState
from thericher_v2.serialization import to_jsonable

_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(json.dumps(to_jsonable(state), indent=2, sort_keys=True))
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
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
