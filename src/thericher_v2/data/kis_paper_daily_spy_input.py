"""Point-in-time local input attestation for the narrow KIS-native SPY D1 lane.

The KIS daily cache labels sessions but does not prove when a provider made a
final daily row public.  This module therefore makes only the smaller claim it
can prove: a row became available to this decision source after its full local
hash attestation completed.  The resulting record is external evidence, not a
permission latch; a new source identity simply receives its own record.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc

from .kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KisPaperPrivateDailyCatalog,
    load_kis_paper_private_daily_catalog,
)

KIS_PAPER_DAILY_SPY_INPUT_SCHEMA_ID = "kis-paper-daily-spy-input-v1"
KIS_PAPER_DAILY_SPY_TARGET_KEY = "SPY/AMS/MODP=0"
KIS_PAPER_DAILY_SPY_DATA_VENUE = "AMS"
KIS_PAPER_DAILY_SPY_AVAILABILITY_ROOT = Path(
    r"D:\thericher-v2\model-artifacts\_control\kis-paper-daily-spy-input-availability-v1"
)
_AVAILABILITY_LOCKS: dict[Path, threading.RLock] = {}
_AVAILABILITY_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class KisPaperDailySpyInput:
    """Two verified D1 bars plus an immutable local-availability manifest."""

    bars: tuple[Bar, Bar]
    catalog_dataset_id: str
    catalog_dataset_hash: str
    last_consumed_session: date
    first_available_at: datetime
    input_manifest_ref: str
    availability_record_path: Path
    schema_id: str = KIS_PAPER_DAILY_SPY_INPUT_SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(
            self,
            "first_available_at",
            require_utc(self.first_available_at, "first_available_at"),
        )
        if len(self.bars) != 2:
            raise ValueError("daily SPY input requires exactly two bars")
        if any(
            bar.symbol != "SPY"
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            for bar in self.bars
        ):
            raise ValueError("daily SPY input bars are incompatible")
        if self.bars[-1].start_ts.date() != self.last_consumed_session:
            raise ValueError("daily SPY input last session is incompatible")
        if not self.catalog_dataset_id:
            raise ValueError("daily SPY input dataset id is required")
        _require_sha256_reference(self.catalog_dataset_hash, "catalog_dataset_hash")
        _require_sha256_reference(self.input_manifest_ref, "input_manifest_ref")
        if self.schema_id != KIS_PAPER_DAILY_SPY_INPUT_SCHEMA_ID:
            raise ValueError("daily SPY input schema is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("daily SPY input schema version is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return identity and timing facts without daily prices or filesystem detail."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_spy_input",
            "schema_id": self.schema_id,
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "market": "US",
            "symbol": "SPY",
            "data_venue": KIS_PAPER_DAILY_SPY_DATA_VENUE,
            "cadence": "1d",
            "source_adjustment_mode": KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
            "source_timestamp_semantics": "session_label_only",
            "catalog_dataset_id": self.catalog_dataset_id,
            "catalog_dataset_hash": self.catalog_dataset_hash,
            "last_consumed_session": self.last_consumed_session.isoformat(),
            "first_available_at": _utc_marker(self.first_available_at),
            "availability_basis": "local_hash_attestation_after_verified_load",
            "completed_bar_rule": "decision_at_strictly_after_first_available_at",
            "input_manifest_ref": self.input_manifest_ref,
        }


def load_kis_paper_daily_spy_input(
    *,
    cache_root: Path | str,
    availability_root: Path | str = KIS_PAPER_DAILY_SPY_AVAILABILITY_ROOT,
    repository_root: Path | str | None = None,
    attested_at: datetime | None = None,
) -> KisPaperDailySpyInput:
    """Re-attest the SPY-only cache and expose one local point-in-time input.

    This is offline: it does not read credentials, environment variables, or
    network state.  A first encounter writes only an opaque availability fact
    outside Git; repeated loads of the same verified source reuse that fact.
    """

    catalog = load_kis_paper_private_daily_catalog(
        cache_root,
        target_keys=(KIS_PAPER_DAILY_SPY_TARGET_KEY,),
        repo_root=repository_root,
    )
    return attest_kis_paper_daily_spy_input(
        catalog,
        availability_root=availability_root,
        repository_root=repository_root,
        attested_at=attested_at,
    )


def attest_kis_paper_daily_spy_input(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    availability_root: Path | str = KIS_PAPER_DAILY_SPY_AVAILABILITY_ROOT,
    repository_root: Path | str | None = None,
    attested_at: datetime | None = None,
) -> KisPaperDailySpyInput:
    """Attach durable local availability to an already verified SPY-only catalog."""

    bars = _validated_spy_bars(catalog)
    return attest_kis_paper_daily_spy_bars(
        bars=bars,
        catalog_dataset_id=catalog.dataset_id,
        catalog_dataset_hash=catalog.dataset_hash,
        availability_root=availability_root,
        repository_root=repository_root,
        attested_at=attested_at,
    )


def attest_kis_paper_daily_spy_bars(
    *,
    bars: tuple[Bar, ...],
    catalog_dataset_id: str,
    catalog_dataset_hash: str,
    availability_root: Path | str = KIS_PAPER_DAILY_SPY_AVAILABILITY_ROOT,
    repository_root: Path | str | None = None,
    attested_at: datetime | None = None,
) -> KisPaperDailySpyInput:
    """Attach local availability to one verified, single-source SPY D1 stream."""

    verified_bars = _validated_spy_input_bars(bars)
    if not isinstance(catalog_dataset_id, str) or not catalog_dataset_id:
        raise ValueError("daily SPY input dataset id is required")
    _require_sha256_reference(catalog_dataset_hash, "catalog_dataset_hash")
    last_session = verified_bars[-1].start_ts.date()
    first_available_at, availability_record_path = _attest_first_available_at(
        catalog_dataset_id=catalog_dataset_id,
        catalog_dataset_hash=catalog_dataset_hash,
        last_consumed_session=last_session,
        availability_root=Path(availability_root),
        repository_root=None if repository_root is None else Path(repository_root),
        attested_at=attested_at,
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_input_manifest",
        "schema_id": KIS_PAPER_DAILY_SPY_INPUT_SCHEMA_ID,
        "provider": "KIS Open API virtual paper",
        "endpoint": "dailyprice",
        "market": "US",
        "symbol": "SPY",
        "data_venue": KIS_PAPER_DAILY_SPY_DATA_VENUE,
        "cadence": "1d",
        "source_adjustment_mode": KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        "source_timestamp_semantics": "session_label_only",
        "catalog_dataset_id": catalog_dataset_id,
        "catalog_dataset_hash": catalog_dataset_hash,
        "last_consumed_session": last_session.isoformat(),
        "first_available_at": _utc_marker(first_available_at),
        "availability_basis": "local_hash_attestation_after_verified_load",
        "completed_bar_rule": "decision_at_strictly_after_first_available_at",
    }
    return KisPaperDailySpyInput(
        bars=(verified_bars[-2], verified_bars[-1]),
        catalog_dataset_id=catalog_dataset_id,
        catalog_dataset_hash=catalog_dataset_hash,
        last_consumed_session=last_session,
        first_available_at=first_available_at,
        input_manifest_ref=_sha256_reference(manifest),
        availability_record_path=availability_record_path,
    )


def _validated_spy_bars(catalog: KisPaperPrivateDailyCatalog) -> tuple[Bar, ...]:
    if not isinstance(catalog, KisPaperPrivateDailyCatalog):
        raise TypeError("daily SPY input requires a KIS private daily catalog")
    if tuple(catalog.bars_by_symbol) != ("SPY",) or len(catalog.common_sessions) < 2:
        raise ValueError("daily SPY input requires a SPY-only catalog with two sessions")
    stream = catalog.bars_by_symbol["SPY"]
    bars = tuple(stream.bars)
    if (
        stream.dataset_id != catalog.dataset_id
        or stream.dataset_hash != catalog.dataset_hash
        or len(bars) != len(catalog.common_sessions)
        or tuple(bar.start_ts.date() for bar in bars) != catalog.common_sessions
        or any(
            bar.symbol != "SPY"
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            for bar in bars
        )
    ):
        raise ValueError("daily SPY catalog is incompatible")
    return bars


def _validated_spy_input_bars(bars: tuple[Bar, ...]) -> tuple[Bar, ...]:
    resolved = tuple(bars)
    if len(resolved) < 2:
        raise ValueError("daily SPY input requires at least two bars")
    if any(
        bar.symbol != "SPY"
        or bar.market != "US"
        or bar.timeframe is not Timeframe.D1
        or not bar.complete
        for bar in resolved
    ):
        raise ValueError("daily SPY input bars are incompatible")
    sessions = tuple(bar.start_ts.date() for bar in resolved)
    if sessions != tuple(sorted(sessions)) or len(set(sessions)) != len(sessions):
        raise ValueError("daily SPY input sessions are invalid")
    return resolved


def _attest_first_available_at(
    *,
    catalog_dataset_id: str,
    catalog_dataset_hash: str,
    last_consumed_session: date,
    availability_root: Path,
    repository_root: Path | None,
    attested_at: datetime | None,
) -> tuple[datetime, Path]:
    root = _prepare_availability_root(availability_root, repository_root)
    identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_spy_input_availability",
        "catalog_dataset_id": catalog_dataset_id,
        "catalog_dataset_hash": catalog_dataset_hash,
        "symbol": "SPY",
        "data_venue": KIS_PAPER_DAILY_SPY_DATA_VENUE,
        "last_consumed_session": last_consumed_session.isoformat(),
    }
    identity_ref = _sha256_reference(identity)
    record_path = root / f"{identity_ref.removeprefix('sha256:')}.json"
    with _exclusive_availability_lock(record_path):
        if record_path.exists():
            return _read_availability_record(record_path, identity=identity), record_path

        first_available_at = require_utc(
            attested_at if attested_at is not None else datetime.now(UTC),
            "attested_at",
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_daily_spy_input_availability",
            "identity": identity,
            "first_available_at": _utc_marker(first_available_at),
        }
        encoded = (
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_or_verify(record_path, encoded)
        return _read_availability_record(record_path, identity=identity), record_path


def _prepare_availability_root(root: Path, repository_root: Path | None) -> Path:
    if root.is_symlink():
        raise ValueError("daily SPY availability root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve()
    if repository_root is not None:
        repository = repository_root.resolve()
        mounted_root = repository / "model_artifacts"
        mounted_artifacts = mounted_root.is_mount() and resolved.is_relative_to(mounted_root)
        if resolved.is_relative_to(repository) and not mounted_artifacts:
            raise ValueError("daily SPY availability evidence must stay outside Git")
    return resolved


def _read_availability_record(path: Path, *, identity: dict[str, object]) -> datetime:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("daily SPY availability evidence is invalid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_paper_daily_spy_input_availability"
        or payload.get("identity") != identity
        or not isinstance(payload.get("first_available_at"), str)
    ):
        raise ValueError("daily SPY availability evidence is invalid")
    try:
        return require_utc(
            datetime.fromisoformat(str(payload["first_available_at"]).replace("Z", "+00:00")),
            "first_available_at",
        )
    except ValueError as error:
        raise ValueError("daily SPY availability evidence is invalid") from error


def _write_or_verify(path: Path, encoded: bytes) -> None:
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("daily SPY availability identity conflicts with existing evidence")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


@contextmanager
def _exclusive_availability_lock(path: Path) -> Iterator[None]:
    """Serialize first-availability evidence without making it a work gate."""

    resolved = path.resolve()
    with _AVAILABILITY_LOCKS_GUARD:
        lock = _AVAILABILITY_LOCKS.setdefault(resolved, threading.RLock())
    with lock:
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _sha256_reference(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256_reference(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be a sha256 reference")


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")
