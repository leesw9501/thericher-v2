"""Single-run KIS virtual-paper reader that publishes a sanitized local snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import UUID, uuid4

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_readonly import (
    DEFAULT_KIS_PAPER_ARTIFACT_ROOT,
    KisHttpTransport,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    UrllibKisHttpTransport,
    load_kis_paper_config_from_environment,
    validate_kis_paper_readonly_diagnostic,
)
from thericher_v2.execution.paper_account_snapshot import (
    PAPER_ACCOUNT_SNAPSHOT_TTL,
    PaperAccountOpenOrder,
    PaperAccountOrderableForeignFunds,
    PaperAccountPosition,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
    paper_account_snapshot_digest,
    read_paper_account_snapshot,
    write_paper_account_snapshot,
)

DEFAULT_RUNTIME_SNAPSHOT_PATH = Path("runtime/state/paper_account_snapshot.json")
_OBSERVER_INVOCATION_ID_ENV = "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID"
_OBSERVER_EVIDENCE_KIND = "kis_paper_snapshot_observer"
_OBSERVER_EVIDENCE_PARTS = ("execution", "kis-paper-snapshot-observer")
_OBSERVER_BRIDGE_EVIDENCE_PARTS = ("execution", "kis-paper-console-bridge")
_REASON_CODE_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses msvcrt below.
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX uses fcntl above.
    msvcrt = None  # type: ignore[assignment]


@dataclass(frozen=True)
class KisPaperConsoleBridgeOutcome:
    status: Literal["complete", "unavailable", "busy"]
    reason_code: str | None
    observed_at: datetime
    snapshot_path: Path
    evidence_path: Path | None
    observer_evidence_path: Path | None = None
    diagnostic: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.status == "complete" and self.reason_code is not None:
            raise ValueError("complete bridge outcome cannot have a reason")
        if self.status == "unavailable" and self.reason_code is None:
            raise ValueError("unavailable bridge outcome requires a reason")
        if self.status == "busy" and self.reason_code != "refresh_busy":
            raise ValueError("busy bridge outcome requires refresh_busy")
        if self.status == "complete" and self.diagnostic:
            raise ValueError("complete bridge outcome cannot have a diagnostic")
        if self.status == "busy" and (self.diagnostic or self.evidence_path is not None):
            raise ValueError("busy bridge outcome cannot have evidence")
        if self.status == "busy" and self.observer_evidence_path is not None:
            raise ValueError("busy bridge outcome cannot have observer evidence")
        if self.status != "busy" and self.evidence_path is None:
            raise ValueError("bridge outcome requires evidence")
        if self.diagnostic:
            validate_kis_paper_readonly_diagnostic(self.diagnostic)
        object.__setattr__(self, "diagnostic", dict(self.diagnostic))


def run_kis_paper_console_bridge(
    *,
    environment: Mapping[str, str],
    runtime_snapshot_path: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperConsoleBridgeOutcome:
    """Publish one snapshot while holding the shared runtime refresh lock."""

    started_at = require_utc(clock(), "clock")
    with _exclusive_runtime_snapshot_refresh_lock(runtime_snapshot_path) as acquired:
        if not acquired:
            return KisPaperConsoleBridgeOutcome(
                status="busy",
                reason_code="refresh_busy",
                observed_at=started_at,
                snapshot_path=runtime_snapshot_path,
                evidence_path=None,
            )
        observer_invocation_id = _observer_invocation_id_from_environment(environment)
        return _run_locked_kis_paper_console_bridge(
            environment=environment,
            runtime_snapshot_path=runtime_snapshot_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            transport=transport,
            clock=clock,
            started_at=started_at,
            observer_invocation_id=observer_invocation_id,
        )


def _run_locked_kis_paper_console_bridge(
    *,
    environment: Mapping[str, str],
    runtime_snapshot_path: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None,
    clock: Callable[[], datetime],
    started_at: datetime,
    observer_invocation_id: str | None,
) -> KisPaperConsoleBridgeOutcome:
    """Publish unavailable before credential I/O, then replace it with the result."""

    write_paper_account_snapshot(
        PaperAccountSnapshot.unavailable(
            observed_at=started_at,
            reason_code="refresh_in_progress",
        ),
        runtime_snapshot_path,
    )
    diagnostic: Mapping[str, str] = {}
    try:
        config = load_kis_paper_config_from_environment(environment)
        source_snapshot = KisPaperReadOnlyClient(
            config=config,
            transport=transport or UrllibKisHttpTransport(),
        ).snapshot()
        final_snapshot = paper_account_snapshot_from_kis_readonly(
            source_snapshot,
            observed_at=require_utc(clock(), "clock"),
        )
    except KisPaperReadOnlyError as error:
        diagnostic = error.diagnostic
        final_snapshot = PaperAccountSnapshot.unavailable(
            observed_at=require_utc(clock(), "clock"),
            reason_code=error.code,
        )
    except Exception:
        final_snapshot = PaperAccountSnapshot.unavailable(
            observed_at=require_utc(clock(), "clock"),
            reason_code="unexpected_failure",
        )

    snapshot_digest = write_paper_account_snapshot(final_snapshot, runtime_snapshot_path)
    evidence_path = write_kis_paper_console_bridge_evidence(
        final_snapshot,
        snapshot_digest=snapshot_digest,
        artifact_root=artifact_root,
        repository_root=repository_root,
        diagnostic=diagnostic,
        observer_invocation_id=observer_invocation_id,
    )
    observer_evidence_path = None
    if observer_invocation_id is not None:
        observer_evidence_path = write_kis_paper_snapshot_observer_evidence(
            status=final_snapshot.status,
            observed_at=final_snapshot.observed_at,
            reason_code=final_snapshot.reason_code,
            observer_invocation_id=observer_invocation_id,
            bridge_evidence_path=evidence_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
    return KisPaperConsoleBridgeOutcome(
        status=final_snapshot.status,
        reason_code=final_snapshot.reason_code,
        observed_at=final_snapshot.observed_at,
        snapshot_path=runtime_snapshot_path,
        evidence_path=evidence_path,
        observer_evidence_path=observer_evidence_path,
        diagnostic=diagnostic,
    )


@contextmanager
def _exclusive_runtime_snapshot_refresh_lock(runtime_snapshot_path: Path) -> Iterator[bool]:
    """Hold one advisory lock for every bridge writer sharing the runtime volume."""

    lock_path = runtime_snapshot_path.with_name(
        f".{runtime_snapshot_path.name}.refresh.lock"
    )
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
    except OSError:
        yield False
        return
    try:
        try:
            acquired = _try_lock_file(handle)
        except OSError:
            yield False
            return
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            _unlock_file(handle)
    finally:
        handle.close()


def _try_lock_file(handle: BinaryIO) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[union-attr]
        except BlockingIOError:
            return False
        return True
    if msvcrt is not None:
        handle.seek(0)
        handle.write(b"\0")
        handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[union-attr]
        except OSError:
            return False
        return True
    raise OSError("runtime_snapshot_lock_unsupported")


def _unlock_file(handle: BinaryIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[union-attr]
    elif msvcrt is not None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[union-attr]


def write_kis_paper_console_bridge_evidence(
    snapshot: PaperAccountSnapshot,
    *,
    snapshot_digest: str,
    artifact_root: Path,
    repository_root: Path,
    diagnostic: Mapping[str, str] | None = None,
    observer_invocation_id: str | None = None,
) -> Path:
    """Persist an immutable fact-minimized result outside the repository."""

    resolved_root = _resolve_permitted_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
        create=True,
    )
    destination_directory = _artifact_namespace_directory(
        artifact_root=resolved_root,
        parts=_OBSERVER_BRIDGE_EVIDENCE_PARTS,
        create=True,
    )
    destination = destination_directory / (
        f"{snapshot.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{snapshot.status}.json"
    )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_console_bridge",
        "status": snapshot.status,
        "observed_at": snapshot.observed_at.isoformat(),
        "expires_at": snapshot.expires_at.isoformat(),
        "paper_only": True,
        "submit_capability": False,
        "runtime_snapshot_sha256": snapshot_digest,
    }
    if observer_invocation_id is not None:
        payload["observer_invocation_id"] = _validated_observer_invocation_id(
            observer_invocation_id
        )
    if snapshot.status == "unavailable":
        payload["reason_code"] = snapshot.reason_code
        if diagnostic:
            validate_kis_paper_readonly_diagnostic(diagnostic)
            payload["diagnostic"] = dict(diagnostic)
    elif diagnostic:
        raise ValueError("complete bridge evidence cannot have a diagnostic")
    else:
        assert snapshot.orderable_foreign_funds is not None
        assert snapshot.reference_orderability is not None
        payload["facts"] = {
            "orderable_foreign_funds_currency": snapshot.orderable_foreign_funds.currency,
            "reference_orderability_currency": snapshot.reference_orderability.currency,
            "position_count": len(snapshot.positions),
            "open_order_count": len(snapshot.open_orders),
        }
    _write_immutable_json(destination, payload)
    return destination


def write_kis_paper_snapshot_observer_evidence(
    *,
    status: Literal["complete", "unavailable"],
    observed_at: datetime,
    reason_code: str | None,
    observer_invocation_id: str,
    bridge_evidence_path: Path,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Bind one marker-present observer result to its finalized bridge receipt."""

    if status not in {"complete", "unavailable"}:
        raise ValueError("observer evidence status is invalid")
    normalized_observed_at = require_utc(observed_at, "observed_at")
    invocation_id = _validated_observer_invocation_id(observer_invocation_id)
    normalized_reason_code = _validated_observer_reason_code(status, reason_code)
    resolved_root = _resolve_permitted_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
        create=True,
    )
    bridge_relative_path, bridge_sha256 = _bridge_evidence_reference(
        bridge_evidence_path=bridge_evidence_path,
        artifact_root=resolved_root,
    )
    bridge_path = _bridge_evidence_path_from_relative(
        bridge_relative_path=bridge_relative_path,
        artifact_root=resolved_root,
    )
    _validate_bridge_evidence_contract(
        bridge_path=bridge_path,
        status=status,
        observed_at=normalized_observed_at,
        observer_invocation_id=invocation_id,
        reason_code=normalized_reason_code,
    )
    destination_directory = _observer_evidence_directory(resolved_root, create=True)
    destination = destination_directory / (
        f"{normalized_observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{invocation_id}-{status}.json"
    )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": _OBSERVER_EVIDENCE_KIND,
        "status": status,
        "observed_at": normalized_observed_at.isoformat(),
        "scope": "read_only",
        "submit_capability": False,
        "observer_invocation_id": invocation_id,
        "bridge_evidence": {
            "relative_path": bridge_relative_path,
            "sha256": bridge_sha256,
        },
    }
    if normalized_reason_code is not None:
        payload["reason_code"] = normalized_reason_code
    _write_immutable_json(destination, payload)
    return destination


def read_kis_paper_snapshot_observer_evidence(
    *,
    evidence_path: Path,
    artifact_root: Path,
    repository_root: Path,
) -> dict[str, object]:
    """Return a validated fact-minimized observer receipt without account contents."""

    resolved_root = _resolve_permitted_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
        create=False,
    )
    expected_directory = _observer_evidence_directory(resolved_root, create=False)
    _assert_no_link_or_reparse_ancestors(evidence_path.absolute())
    if _path_is_link_or_reparse_point(evidence_path) or not evidence_path.is_file():
        raise ValueError("observer evidence path is unavailable")
    resolved_evidence_path = evidence_path.resolve(strict=True)
    if resolved_evidence_path.parent != expected_directory:
        raise ValueError("observer evidence path is outside its namespace")
    try:
        payload = json.loads(resolved_evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("observer evidence is unreadable") from error
    if not isinstance(payload, dict):
        raise ValueError("observer evidence must be an object")

    status = payload.get("status")
    if status not in {"complete", "unavailable"}:
        raise ValueError("observer evidence status is invalid")
    expected_keys = {
        "schema_version",
        "kind",
        "status",
        "observed_at",
        "scope",
        "submit_capability",
        "observer_invocation_id",
        "bridge_evidence",
    }
    if status == "unavailable":
        expected_keys.add("reason_code")
    if set(payload) != expected_keys:
        raise ValueError("observer evidence shape is invalid")
    if (
        payload["schema_version"] != SCHEMA_VERSION
        or payload["kind"] != _OBSERVER_EVIDENCE_KIND
        or payload["scope"] != "read_only"
        or payload["submit_capability"] is not False
    ):
        raise ValueError("observer evidence contract is invalid")
    observed_at = _parse_utc_timestamp(payload["observed_at"], "observer observed_at")
    invocation_id = _validated_observer_invocation_id(payload["observer_invocation_id"])
    reason_code = _validated_observer_reason_code(status, payload.get("reason_code"))
    bridge_evidence = payload["bridge_evidence"]
    if not isinstance(bridge_evidence, dict) or set(bridge_evidence) != {
        "relative_path",
        "sha256",
    }:
        raise ValueError("observer bridge evidence reference is invalid")
    bridge_relative_path = bridge_evidence["relative_path"]
    bridge_sha256 = bridge_evidence["sha256"]
    if not isinstance(bridge_relative_path, str) or not isinstance(bridge_sha256, str):
        raise ValueError("observer bridge evidence reference is invalid")
    bridge_path = _bridge_evidence_path_from_relative(
        bridge_relative_path=bridge_relative_path,
        artifact_root=resolved_root,
    )
    if hashlib.sha256(bridge_path.read_bytes()).hexdigest() != bridge_sha256:
        raise ValueError("observer bridge evidence digest does not match")
    _validate_bridge_evidence_contract(
        bridge_path=bridge_path,
        status=status,
        observed_at=observed_at,
        observer_invocation_id=invocation_id,
        reason_code=reason_code,
    )
    result: dict[str, object] = {
        "status": status,
        "observed_at": observed_at.isoformat(),
        "scope": "read_only",
        "submit_capability": False,
        "observer_invocation_id": invocation_id,
        "bridge_evidence_path": bridge_relative_path,
    }
    if reason_code is not None:
        result["reason_code"] = reason_code
    return result


def _observer_evidence_directory(artifact_root: Path, *, create: bool = True) -> Path:
    return _artifact_namespace_directory(
        artifact_root=artifact_root,
        parts=_OBSERVER_EVIDENCE_PARTS,
        create=create,
    )


def _bridge_evidence_reference(
    *, bridge_evidence_path: Path, artifact_root: Path
) -> tuple[str, str]:
    bridge_path = _bridge_evidence_path_from_relative(
        bridge_relative_path=_relative_artifact_path(bridge_evidence_path, artifact_root),
        artifact_root=artifact_root,
    )
    return bridge_path.relative_to(artifact_root).as_posix(), hashlib.sha256(
        bridge_path.read_bytes()
    ).hexdigest()


def _relative_artifact_path(path: Path, artifact_root: Path) -> str:
    _assert_no_link_or_reparse_ancestors(path.absolute())
    if _path_is_link_or_reparse_point(path) or not path.is_file():
        raise ValueError("bridge evidence path is unavailable")
    resolved_path = path.resolve(strict=True)
    try:
        return resolved_path.relative_to(artifact_root).as_posix()
    except ValueError as error:
        raise ValueError("bridge evidence path is outside the artifact root") from error


def _bridge_evidence_path_from_relative(*, bridge_relative_path: str, artifact_root: Path) -> Path:
    relative_path = Path(bridge_relative_path)
    if (
        relative_path.is_absolute()
        or relative_path.parts[:2] != _OBSERVER_BRIDGE_EVIDENCE_PARTS
        or len(relative_path.parts) != 3
    ):
        raise ValueError("bridge evidence path is outside its namespace")
    expected_root = _artifact_namespace_directory(
        artifact_root=artifact_root,
        parts=_OBSERVER_BRIDGE_EVIDENCE_PARTS,
        create=False,
    )
    candidate = expected_root / relative_path.name
    if _path_is_link_or_reparse_point(candidate) or not candidate.is_file():
        raise ValueError("bridge evidence path is unavailable")
    resolved_candidate = candidate.resolve(strict=True)
    if resolved_candidate.parent != expected_root:
        raise ValueError("bridge evidence path is outside its namespace")
    return resolved_candidate


def _validated_observer_reason_code(
    status: Literal["complete", "unavailable"], reason_code: object
) -> str | None:
    if status == "complete":
        if reason_code is not None:
            raise ValueError("complete observer evidence cannot have a reason")
        return None
    if not isinstance(reason_code, str) or _REASON_CODE_PATTERN.fullmatch(reason_code) is None:
        raise ValueError("observer reason code is invalid")
    return reason_code


def _parse_utc_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is invalid") from error
    return require_utc(parsed, field_name)


def _validate_bridge_evidence_contract(
    *,
    bridge_path: Path,
    status: Literal["complete", "unavailable"],
    observed_at: datetime,
    observer_invocation_id: str,
    reason_code: str | None,
) -> None:
    try:
        payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("bridge evidence is unreadable") from error
    if not isinstance(payload, dict):
        raise ValueError("bridge evidence must be an object")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_paper_console_bridge"
        or payload.get("status") != status
        or payload.get("paper_only") is not True
        or payload.get("submit_capability") is not False
        or _parse_utc_timestamp(payload.get("observed_at"), "bridge observed_at") != observed_at
        or payload.get("observer_invocation_id") != observer_invocation_id
    ):
        raise ValueError("bridge evidence contract is invalid")
    expected_keys = {
        "schema_version",
        "kind",
        "status",
        "observed_at",
        "expires_at",
        "paper_only",
        "submit_capability",
        "runtime_snapshot_sha256",
        "observer_invocation_id",
    }
    if status == "complete":
        expected_keys.add("facts")
    else:
        expected_keys.add("reason_code")
        if "diagnostic" in payload:
            expected_keys.add("diagnostic")
    if set(payload) != expected_keys:
        raise ValueError("bridge evidence contract is invalid")
    _parse_utc_timestamp(payload.get("expires_at"), "bridge expires_at")
    if status == "unavailable" and payload.get("reason_code") != reason_code:
        raise ValueError("bridge evidence contract is invalid")
    if status == "complete" and "reason_code" in payload:
        raise ValueError("bridge evidence contract is invalid")


def _write_immutable_json(destination: Path, payload: Mapping[str, object]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    temporary = destination.parent / f".{uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise ValueError("evidence already exists") from error
    finally:
        temporary.unlink(missing_ok=True)


def _observer_invocation_id_from_environment(environment: Mapping[str, str]) -> str | None:
    value = environment.get(_OBSERVER_INVOCATION_ID_ENV)
    if value is None or value == "":
        return None
    return _validated_observer_invocation_id(value)


def _validated_observer_invocation_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError) as error:
        raise ValueError("observer invocation id must be a UUIDv4") from error
    canonical = str(parsed)
    if parsed.version != 4 or value != canonical:
        raise ValueError("observer invocation id must be a canonical UUIDv4")
    return canonical


def recover_kis_paper_console_bridge_evidence(
    *,
    runtime_snapshot_path: Path,
    artifact_root: Path,
    repository_root: Path,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperConsoleBridgeOutcome:
    """Record a missing artifact from a fresh sanitized runtime snapshot without KIS I/O."""

    current = read_paper_account_snapshot(
        runtime_snapshot_path,
        now=require_utc(clock(), "clock"),
    )
    if current.status != "available" or current.snapshot is None:
        raise ValueError("snapshot_not_recoverable")
    snapshot = current.snapshot
    evidence_path = write_kis_paper_console_bridge_evidence(
        snapshot,
        snapshot_digest=paper_account_snapshot_digest(snapshot),
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return KisPaperConsoleBridgeOutcome(
        status="complete",
        reason_code=None,
        observed_at=snapshot.observed_at,
        snapshot_path=runtime_snapshot_path,
        evidence_path=evidence_path,
    )


def paper_account_snapshot_from_kis_readonly(
    source: KisPaperReadOnlySnapshot,
    *,
    observed_at: datetime,
) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        status="complete",
        observed_at=observed_at,
        expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
        orderable_foreign_funds=PaperAccountOrderableForeignFunds(
            currency=source.cash.currency,
            amount=source.cash.available_cash,
        ),
        reference_orderability=PaperAccountReferenceOrderability(
            currency=source.orderable_funds.currency,
            orderable_funds=source.orderable_funds.orderable_funds,
            reference_exchange=source.orderable_funds.reference_exchange,
            reference_symbol=source.orderable_funds.reference_symbol,
        ),
        positions=tuple(
            PaperAccountPosition(
                exchange=position.exchange,
                symbol=position.symbol,
                currency=position.currency,
                quantity=position.quantity,
            )
            for position in source.positions
        ),
        open_orders=tuple(
            PaperAccountOpenOrder(
                exchange=order.exchange,
                symbol=order.symbol,
                currency=order.currency,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.remaining_quantity,
            )
            for order in source.open_orders.orders
        ),
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    if not _is_within(artifact_root, repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


def _resolve_permitted_artifact_root(
    *, artifact_root: Path, repository_root: Path, create: bool
) -> Path:
    lexical_root = artifact_root.absolute()
    _assert_no_link_or_reparse_ancestors(lexical_root)
    if create:
        lexical_root.mkdir(parents=True, exist_ok=True)
    if _path_is_link_or_reparse_point(lexical_root) or not lexical_root.is_dir():
        raise ValueError("artifact root is unavailable")
    _assert_no_link_or_reparse_ancestors(lexical_root)
    resolved_root = lexical_root.resolve(strict=True)
    if not _is_permitted_artifact_root(resolved_root, repository_root.resolve()):
        raise ValueError("artifact_root_inside_repository")
    return resolved_root


def _artifact_namespace_directory(
    *, artifact_root: Path, parts: tuple[str, ...], create: bool
) -> Path:
    directory = artifact_root.joinpath(*parts)
    _assert_no_link_or_reparse_ancestors(directory)
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if _path_is_link_or_reparse_point(directory) or not directory.is_dir():
        raise ValueError("artifact namespace is unavailable")
    _assert_no_link_or_reparse_ancestors(directory)
    resolved_directory = directory.resolve(strict=True)
    try:
        relative_parts = resolved_directory.relative_to(artifact_root).parts
    except ValueError as error:
        raise ValueError("artifact namespace is outside the artifact root") from error
    if relative_parts != parts:
        raise ValueError("artifact namespace is outside the artifact root")
    return resolved_directory


def _assert_no_link_or_reparse_ancestors(path: Path) -> None:
    absolute_path = path.absolute()
    current = Path(absolute_path.anchor)
    for part in absolute_path.parts[1:]:
        current = current / part
        if current.exists() or _path_is_link_or_reparse_point(current):
            if _path_is_link_or_reparse_point(current):
                raise ValueError("artifact path contains a link or reparse point")


def _path_is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return callable(is_junction) and bool(is_junction())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish one KIS paper console snapshot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--recover-evidence", action="store_true")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(
            os.environ.get("THERICHER_MODEL_ARTIFACT_ROOT", DEFAULT_KIS_PAPER_ARTIFACT_ROOT)
        ),
    )
    parser.add_argument(
        "--runtime-snapshot",
        type=Path,
        default=Path(
            os.environ.get(
                "THERICHER_PAPER_ACCOUNT_SNAPSHOT_PATH",
                DEFAULT_RUNTIME_SNAPSHOT_PATH,
            )
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.recover_evidence:
        outcome = recover_kis_paper_console_bridge_evidence(
            runtime_snapshot_path=arguments.runtime_snapshot,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
        )
    elif not arguments.execute:
        print(json.dumps({"status": "dry_run", "submit_capability": False}, sort_keys=True))
        return 0
    else:
        outcome = run_kis_paper_console_bridge(
            environment=os.environ,
            runtime_snapshot_path=arguments.runtime_snapshot,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
        )
    observer_evidence = None
    if outcome.observer_evidence_path is not None:
        observer_evidence = read_kis_paper_snapshot_observer_evidence(
            evidence_path=outcome.observer_evidence_path,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
        )
    print(
        json.dumps(
            {
                "status": outcome.status,
                "reason_code": outcome.reason_code,
                "observed_at": outcome.observed_at.isoformat(),
                "evidence_path": (
                    str(outcome.evidence_path)
                    if outcome.evidence_path is not None
                    else None
                ),
                "observer_evidence_path": (
                    str(outcome.observer_evidence_path)
                    if outcome.observer_evidence_path is not None
                    else None
                ),
                "observer_invocation_id": (
                    observer_evidence["observer_invocation_id"]
                    if observer_evidence is not None
                    else None
                ),
                "scope": "read_only",
                "account_snapshot_complete": outcome.status == "complete",
            },
            sort_keys=True,
        )
    )
    return 0 if outcome.status in {"complete", "busy"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
