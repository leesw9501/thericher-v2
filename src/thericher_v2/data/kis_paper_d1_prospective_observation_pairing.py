"""Bounded QQQ/SPY D1 revision measurements through the KIS Paper data route."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON,
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
    KIS_PAPER_DAILY_PAIR_FORWARD_V2_CACHE_ROOT,
    KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY,
    KisPaperDailyPairForwardCacheError,
    KisPaperDailyPairForwardRow,
    load_verified_kis_paper_daily_pair_forward_cache,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError
from thericher_v2.execution.kis_paper_daily_nas_forward import (
    latest_completed_us_equity_d1_session,
)
from thericher_v2.execution.kis_paper_daily_pair_forward import (
    KisPaperDailyPairForwardError,
    KisPaperDailyPairForwardObservation,
    collect_kis_paper_daily_pair_forward_observation,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_KIND = (
    "kis_paper_d1_prospective_observation_pairing"
)
KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_VERSION = "v1"
KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS = (
    "data",
    "kis-paper-d1-prospective-observation-pairing",
    "v1",
)
KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)

_KOREA_TZ = ZoneInfo("Asia/Seoul")
_FIRST_TIME = time(8, 15)
_LATER_TIME = time(23, 20)
_ACTIVE_KST_WEEKDAYS = frozenset({1, 2, 3, 4, 5})  # Tuesday through Saturday.
_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}" for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
)
_STATE_FILENAME = "state.json"
_CURRENT_FILENAME = "current.json"
_RECEIPTS_DIRECTORY = "receipts"
_SAFE_RECEIPT_ID = re.compile(r"[A-Za-z0-9-]{1,160}", re.ASCII)
_SOURCE_CONTRACT = {
    "provider": "KIS Open API virtual paper",
    "endpoint": "dailyprice",
    "cache_identity": {
        "kind": KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY.kind,
        "version": KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY.version,
    },
    "targets": [
        {"symbol": symbol, "exchange": exchange}
        for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
    ],
    "adjustment_mode": "MODP=0_unadjusted",
}


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256 = (
    "sha256:" + hashlib.sha256(_canonical_json(_SOURCE_CONTRACT)).hexdigest()
)

PairingStatus = Literal[
    "first_recorded",
    "measurement_only_match",
    "disqualified",
    "input_unavailable",
    "not_due",
]
PairingStage = Literal["first", "later", "none"]
CacheLoader = Callable[..., object]
ObservationFetcher = Callable[..., KisPaperDailyPairForwardObservation]
ClientFactory = Callable[[], object]


class KisPaperD1ProspectiveObservationPairingError(RuntimeError):
    """A source-safe error from the isolated pairing worker."""


@dataclass(frozen=True, slots=True)
class KisPaperD1ProspectiveObservationPairingResult:
    """One safe scheduling result; all price-bearing values remain in memory."""

    status: PairingStatus
    reason: str | None
    stage: PairingStage
    observed_at: datetime
    next_due_at: datetime
    session_key: date | None = None
    first_observed_at: datetime | None = None
    first_row_hashes: Mapping[str, str] | None = None
    later_observed_at: datetime | None = None
    later_row_hashes: Mapping[str, str] | None = None
    first_receipt_id: str | None = None
    first_receipt_sha256: str | None = None
    receipt_sha256: str | None = None
    evidence_path: Path | None = None

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_KIND,
            "version": KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_VERSION,
            "status": self.status,
            "reason": self.reason,
            "stage": self.stage,
            "source_contract_sha256": (
                KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256
            ),
            "observed_at_utc": _utc_marker(self.observed_at),
            "session_key": None if self.session_key is None else self.session_key.isoformat(),
            "first_observation": _observation_payload(
                self.first_observed_at,
                self.first_row_hashes,
            ),
            "later_observation": _observation_payload(
                self.later_observed_at,
                self.later_row_hashes,
            ),
            "first_receipt_binding": _receipt_binding_payload(
                self.first_receipt_id,
                self.first_receipt_sha256,
            ),
            "next_due_at_utc": _utc_marker(self.next_due_at),
            "point_in_time_availability": "not_observed",
            "provider_finality": "not_observed",
            "measurement_only": True,
            "route_isolation": {
                "daily_market_data_only": True,
                "account_endpoints_used": False,
                "quote_endpoints_used": False,
                "order_endpoints_used": False,
                "live_endpoints_used": False,
            },
            "artifact_policy": {
                "raw_market_data_in_receipt": False,
                "credentials_in_receipt": False,
                "account_data_in_receipt": False,
                "repo_storage_allowed": False,
            },
        }


def run_kis_paper_d1_prospective_observation_pairing(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_PAIR_FORWARD_V2_CACHE_ROOT,
    artifact_root: Path | str = KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_ROOT,
    repository_root: Path | str,
    observed_at: datetime,
    client_factory: ClientFactory,
    cache_loader: CacheLoader = load_verified_kis_paper_daily_pair_forward_cache,
    observation_fetcher: ObservationFetcher = collect_kis_paper_daily_pair_forward_observation,
) -> KisPaperD1ProspectiveObservationPairingResult:
    """Execute one scheduled stage without mutating the v2 data cache."""

    observed = require_utc(observed_at, "observed_at")
    root = _artifact_root(Path(artifact_root), Path(repository_root))
    receipts = _receipt_directory(root)
    try:
        state = _load_state(root, observed)
    except KisPaperD1ProspectiveObservationPairingError:
        return _result(
            status="input_unavailable",
            reason="state_unavailable",
            stage="none",
            observed_at=observed,
            next_due_at=_next_first_due(observed),
        )
    stage = _scheduled_stage(observed)
    if stage == "none" or state["expected_stage"] != stage or observed < state["next_due_at"]:
        return _result(
            status="not_due",
            reason="next_due_owned",
            stage="none",
            observed_at=observed,
            next_due_at=state["next_due_at"],
            session_key=state["session_key"],
        )
    if stage == "first":
        return _first_stage(
            root=root,
            receipts=receipts,
            cache_root=Path(cache_root),
            repository_root=Path(repository_root),
            observed_at=observed,
            client_factory=client_factory,
            cache_loader=cache_loader,
            observation_fetcher=observation_fetcher,
        )
    return _later_stage(
        root=root,
        receipts=receipts,
        state=state,
        cache_root=Path(cache_root),
        repository_root=Path(repository_root),
        observed_at=observed,
        client_factory=client_factory,
        cache_loader=cache_loader,
        observation_fetcher=observation_fetcher,
    )


def validate_kis_paper_d1_prospective_observation_pairing_receipt(
    receipt_path: Path | str,
    *,
    artifact_root: Path | str = KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_ROOT,
    repository_root: Path | str,
) -> dict[str, object]:
    """Revalidate a source-safe receipt without network or credentials."""

    root = _existing_artifact_root(Path(artifact_root), Path(repository_root))
    receipts = root / _RECEIPTS_DIRECTORY
    path = Path(receipt_path)
    if path.is_symlink() or not path.is_file() or path.resolve().parent != receipts.resolve():
        raise KisPaperD1ProspectiveObservationPairingError("receipt_unavailable")
    return _read_receipt(path)


def read_current_kis_paper_d1_prospective_observation_pairing_outcome(
    *,
    artifact_root: Path | str = KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_ROOT,
    repository_root: Path | str,
) -> dict[str, object]:
    """Read only the hash-bound current outcome and its immutable receipts."""

    root = _existing_artifact_root(Path(artifact_root), Path(repository_root))
    receipts = root / _RECEIPTS_DIRECTORY
    if receipts.is_symlink() or not receipts.is_dir():
        raise KisPaperD1ProspectiveObservationPairingError("receipt_directory_unavailable")
    pointer = _read_current_pointer(root)
    receipt_id = pointer["receipt_id"]
    receipt_sha256 = pointer["receipt_sha256"]
    if not _is_receipt_id(receipt_id) or not _is_sha256(receipt_sha256):
        raise KisPaperD1ProspectiveObservationPairingError("current_pointer_invalid")
    try:
        receipt = _read_existing(receipts, receipt_id)
    except KisPaperD1ProspectiveObservationPairingError:
        receipt = None
    if (
        receipt is None
        or receipt.get("receipt_id") != receipt_id
        or receipt.get("receipt_sha256") != receipt_sha256
    ):
        raise KisPaperD1ProspectiveObservationPairingError("current_receipt_unavailable")
    for key in ("status", "stage", "session_key"):
        if pointer.get(key) != receipt.get(key):
            raise KisPaperD1ProspectiveObservationPairingError("current_pointer_invalid")
    if pointer.get("updated_at_utc") != receipt.get("observed_at_utc"):
        raise KisPaperD1ProspectiveObservationPairingError("current_pointer_invalid")
    _validate_later_receipt_binding(receipts, receipt)
    return receipt


def _first_stage(
    *,
    root: Path,
    receipts: Path,
    cache_root: Path,
    repository_root: Path,
    observed_at: datetime,
    client_factory: ClientFactory,
    cache_loader: CacheLoader,
    observation_fetcher: ObservationFetcher,
) -> KisPaperD1ProspectiveObservationPairingResult:
    session = latest_completed_us_equity_d1_session(observed_at)
    if session is None:
        return _close(
            root=root,
            receipts=receipts,
            result=_result(
                status="input_unavailable",
                reason="completed_session_unavailable",
                stage="first",
                observed_at=observed_at,
                next_due_at=_next_first_due(observed_at),
            ),
            receipt_id=_terminal_receipt_id("first", None, observed_at),
        )
    if not _cache_is_conflict_free(cache_root, repository_root, cache_loader):
        return _close(
            root=root,
            receipts=receipts,
            result=_result(
                status="input_unavailable",
                reason="cache_conflict_or_unavailable",
                stage="first",
                observed_at=observed_at,
                next_due_at=_next_first_due(observed_at),
                session_key=session,
            ),
            receipt_id=_terminal_receipt_id("first", session, observed_at),
        )
    receipt_id = _first_receipt_id(session)
    try:
        existing = _read_existing(receipts, receipt_id)
    except KisPaperD1ProspectiveObservationPairingError:
        return _close(
            root=root,
            receipts=receipts,
            result=_result(
                status="input_unavailable",
                reason="first_receipt_unavailable",
                stage="first",
                observed_at=observed_at,
                next_due_at=_next_first_due(observed_at),
                session_key=session,
            ),
            receipt_id=_terminal_receipt_id("first", session, observed_at),
        )
    if existing is not None:
        binding = _first_binding(existing, session)
        if binding is not None:
            next_due = _later_due(observed_at)
            result = _result_from_receipt(existing, receipts / f"{receipt_id}.json")
            _publish_current(root, receipt_id, result)
            _write_state(root, "later", next_due, session, receipt_id, existing["receipt_sha256"])
            return result
    try:
        observation = observation_fetcher(client_factory(), observed_at=observed_at)
        hashes = _row_hashes(observation, session)
    except (
        KisPaperDailyPairForwardError,
        KisPaperMarketDataError,
        KisPaperD1ProspectiveObservationPairingError,
        OSError,
        ValueError,
    ):
        return _close(
            root=root,
            receipts=receipts,
            result=_result(
                status="input_unavailable",
                reason="first_observation_unavailable",
                stage="first",
                observed_at=observed_at,
                next_due_at=_next_first_due(observed_at),
                session_key=session,
            ),
            receipt_id=_terminal_receipt_id("first", session, observed_at),
        )
    next_due = _later_due(observed_at)
    result = _persist(
        receipts,
        receipt_id,
        _result(
            status="first_recorded",
            reason=None,
            stage="first",
            observed_at=observed_at,
            next_due_at=next_due,
            session_key=session,
            first_observed_at=observed_at,
            first_row_hashes=hashes,
        ),
    )
    _publish_current(root, receipt_id, result)
    _write_state(root, "later", next_due, session, receipt_id, result.receipt_sha256)
    return result


def _later_stage(
    *,
    root: Path,
    receipts: Path,
    state: dict[str, object],
    cache_root: Path,
    repository_root: Path,
    observed_at: datetime,
    client_factory: ClientFactory,
    cache_loader: CacheLoader,
    observation_fetcher: ObservationFetcher,
) -> KisPaperD1ProspectiveObservationPairingResult:
    session = state["session_key"]
    receipt_id = state["first_receipt_id"]
    receipt_hash = state["first_receipt_sha256"]
    if (
        not isinstance(session, date)
        or not isinstance(receipt_id, str)
        or not _is_sha256(receipt_hash)
    ):
        return _terminal_failure(root, receipts, observed_at, None, "pair_state_incomplete")
    try:
        first = _read_existing(receipts, receipt_id)
    except KisPaperD1ProspectiveObservationPairingError:
        first = None
    binding = (
        None
        if first is None or first.get("receipt_sha256") != receipt_hash
        else _first_binding(first, session)
    )
    if binding is None:
        return _terminal_failure(root, receipts, observed_at, session, "first_receipt_unavailable")
    first_observed_at, first_hashes = binding
    later_id = _later_receipt_id(session, receipt_hash)
    try:
        existing = _read_existing(receipts, later_id)
    except KisPaperD1ProspectiveObservationPairingError:
        return _terminal_failure(
            root,
            receipts,
            observed_at,
            session,
            "later_receipt_invalid",
            first_observed_at,
            first_hashes,
            None,
            receipt_id,
            receipt_hash,
        )
    if existing is not None:
        try:
            result = _result_from_receipt(existing, receipts / f"{later_id}.json")
        except KisPaperD1ProspectiveObservationPairingError:
            return _terminal_failure(
                root,
                receipts,
                observed_at,
                session,
                "later_receipt_invalid",
                first_observed_at,
                first_hashes,
                None,
                receipt_id,
                receipt_hash,
            )
        if (
            result.session_key != session
            or result.first_row_hashes != first_hashes
            or result.first_receipt_id != receipt_id
            or result.first_receipt_sha256 != receipt_hash
        ):
            return _terminal_failure(
                root,
                receipts,
                observed_at,
                session,
                "later_receipt_invalid",
                first_observed_at,
                first_hashes,
                None,
                receipt_id,
                receipt_hash,
            )
        _publish_current(root, later_id, result)
        _write_state(root, "first", _next_first_due(observed_at), None, None, None)
        return result
    if not _cache_is_conflict_free(cache_root, repository_root, cache_loader):
        return _terminal_failure(
            root,
            receipts,
            observed_at,
            session,
            "cache_conflict_or_unavailable",
            first_observed_at,
            first_hashes,
            later_id,
            receipt_id,
            receipt_hash,
        )
    try:
        observation = observation_fetcher(client_factory(), observed_at=observed_at)
        later_hashes = _row_hashes(observation, session)
    except (
        KisPaperDailyPairForwardError,
        KisPaperMarketDataError,
        KisPaperD1ProspectiveObservationPairingError,
        OSError,
        ValueError,
    ):
        return _terminal_failure(
            root,
            receipts,
            observed_at,
            session,
            "later_observation_unavailable",
            first_observed_at,
            first_hashes,
            later_id,
            receipt_id,
            receipt_hash,
        )
    status: PairingStatus = "measurement_only_match"
    reason: str | None = None
    if later_hashes != first_hashes:
        status, reason = "disqualified", "identity_mismatch"
    return _close(
        root=root,
        receipts=receipts,
        result=_result(
            status=status,
            reason=reason,
            stage="later",
            observed_at=observed_at,
            next_due_at=_next_first_due(observed_at),
            session_key=session,
            first_observed_at=first_observed_at,
            first_row_hashes=first_hashes,
            later_observed_at=observed_at,
            later_row_hashes=later_hashes,
            first_receipt_id=receipt_id,
            first_receipt_sha256=receipt_hash,
        ),
        receipt_id=later_id,
    )


def _terminal_failure(
    root: Path,
    receipts: Path,
    observed_at: datetime,
    session: date | None,
    reason: str,
    first_observed_at: datetime | None = None,
    first_hashes: Mapping[str, str] | None = None,
    receipt_id: str | None = None,
    first_receipt_id: str | None = None,
    first_receipt_sha256: str | None = None,
) -> KisPaperD1ProspectiveObservationPairingResult:
    return _close(
        root=root,
        receipts=receipts,
        result=_result(
            status="input_unavailable",
            reason=reason,
            stage="later",
            observed_at=observed_at,
            next_due_at=_next_first_due(observed_at),
            session_key=session,
            first_observed_at=first_observed_at,
            first_row_hashes=first_hashes,
            first_receipt_id=first_receipt_id,
            first_receipt_sha256=first_receipt_sha256,
        ),
        receipt_id=receipt_id or _terminal_receipt_id("later", session, observed_at),
    )


def _close(
    *,
    root: Path,
    receipts: Path,
    result: KisPaperD1ProspectiveObservationPairingResult,
    receipt_id: str,
) -> KisPaperD1ProspectiveObservationPairingResult:
    persisted = _persist(receipts, receipt_id, result)
    _publish_current(root, receipt_id, persisted)
    _write_state(root, "first", persisted.next_due_at, None, None, None)
    return persisted


def _cache_is_conflict_free(
    cache_root: Path,
    repository_root: Path,
    cache_loader: CacheLoader,
) -> bool:
    try:
        cache = cache_loader(
            cache_root=cache_root,
            repo_root=repository_root,
            cache_identity=KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY,
        )
        states = cache.targets_by_key
        conflict_reason = KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON
        return tuple(states) == _TARGET_KEYS and all(
            states[key].last_reason != conflict_reason
            for key in _TARGET_KEYS
        )
    except (AttributeError, KisPaperDailyPairForwardCacheError, OSError, ValueError):
        return False


def _row_hashes(
    observation: KisPaperDailyPairForwardObservation,
    session: date,
) -> dict[str, str]:
    if (
        set(observation.rows_by_target) != set(_TARGET_KEYS)
        or observation.failure_reasons_by_target
    ):
        raise KisPaperD1ProspectiveObservationPairingError("observation_incomplete")
    hashes: dict[str, str] = {}
    for key in _TARGET_KEYS:
        rows = [row for row in observation.rows_by_target[key] if row.session_date == session]
        if len(rows) != 1:
            raise KisPaperD1ProspectiveObservationPairingError("session_row_unavailable")
        hashes[key] = _row_hash(rows[0])
    return hashes


def _row_hash(row: KisPaperDailyPairForwardRow) -> str:
    return "sha256:" + hashlib.sha256("\x1f".join(row.raw_record()).encode("utf-8")).hexdigest()


def _result(
    *,
    status: PairingStatus,
    reason: str | None,
    stage: PairingStage,
    observed_at: datetime,
    next_due_at: datetime,
    session_key: date | None = None,
    first_observed_at: datetime | None = None,
    first_row_hashes: Mapping[str, str] | None = None,
    later_observed_at: datetime | None = None,
    later_row_hashes: Mapping[str, str] | None = None,
    first_receipt_id: str | None = None,
    first_receipt_sha256: str | None = None,
) -> KisPaperD1ProspectiveObservationPairingResult:
    return KisPaperD1ProspectiveObservationPairingResult(
        status=status,
        reason=reason,
        stage=stage,
        observed_at=require_utc(observed_at, "observed_at"),
        next_due_at=require_utc(next_due_at, "next_due_at"),
        session_key=session_key,
        first_observed_at=first_observed_at,
        first_row_hashes=first_row_hashes,
        later_observed_at=later_observed_at,
        later_row_hashes=later_row_hashes,
        first_receipt_id=first_receipt_id,
        first_receipt_sha256=first_receipt_sha256,
    )


def _persist(
    receipts: Path,
    receipt_id: str,
    result: KisPaperD1ProspectiveObservationPairingResult,
) -> KisPaperD1ProspectiveObservationPairingResult:
    payload = result.safe_payload()
    payload["receipt_id"] = receipt_id
    payload["receipt_sha256"] = _sha256(payload)
    path = receipts / f"{receipt_id}.json"
    try:
        with path.open("xb") as handle:
            handle.write(_canonical_json(payload))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        payload = _read_existing(receipts, receipt_id)
        if payload is None:
            raise KisPaperD1ProspectiveObservationPairingError("receipt_unavailable") from None
    return _result_from_receipt(payload, path)


def _result_from_receipt(
    payload: Mapping[str, object],
    path: Path,
) -> KisPaperD1ProspectiveObservationPairingResult:
    first_observed_at, first_hashes = _receipt_observation(payload, "first_observation")
    later_observed_at, later_hashes = _receipt_observation(payload, "later_observation")
    first_receipt_id, first_receipt_sha256 = _receipt_binding(payload)
    status = payload.get("status")
    stage = payload.get("stage")
    if status not in {
        "first_recorded",
        "measurement_only_match",
        "disqualified",
        "input_unavailable",
    } or stage not in {"first", "later"}:
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    return KisPaperD1ProspectiveObservationPairingResult(
        status=status,
        reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
        stage=stage,
        observed_at=_parse_utc(payload.get("observed_at_utc")),
        next_due_at=_parse_utc(payload.get("next_due_at_utc")),
        session_key=_parse_date(payload.get("session_key")),
        first_observed_at=first_observed_at,
        first_row_hashes=first_hashes,
        later_observed_at=later_observed_at,
        later_row_hashes=later_hashes,
        first_receipt_id=first_receipt_id,
        first_receipt_sha256=first_receipt_sha256,
        receipt_sha256=_hash_text(payload.get("receipt_sha256")),
        evidence_path=path,
    )


def _first_binding(
    payload: Mapping[str, object],
    session: date,
) -> tuple[datetime, dict[str, str]] | None:
    if (
        payload.get("status") != "first_recorded"
        or _parse_date(payload.get("session_key")) != session
    ):
        return None
    observed_at, hashes = _receipt_observation(payload, "first_observation")
    return None if observed_at is None or hashes is None else (observed_at, hashes)


def _read_existing(receipts: Path, receipt_id: str) -> dict[str, object] | None:
    if not _is_receipt_id(receipt_id):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    path = receipts / f"{receipt_id}.json"
    if not path.exists():
        return None
    payload = _read_receipt(path)
    if payload.get("receipt_id") != receipt_id:
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    return payload


def _read_receipt(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise KisPaperD1ProspectiveObservationPairingError("receipt_unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid") from error
    if not isinstance(payload, dict):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    declared = payload.pop("receipt_sha256", None)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_KIND
        or payload.get("version") != KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_VERSION
        or payload.get("source_contract_sha256")
        != KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256
        or not _is_receipt_id(payload.get("receipt_id"))
        or not _is_sha256(declared)
        or declared != _sha256(payload)
    ):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    _parse_utc(payload.get("observed_at_utc"))
    _parse_utc(payload.get("next_due_at_utc"))
    _parse_date(payload.get("session_key"))
    first_observed_at, first_hashes = _receipt_observation(payload, "first_observation")
    _receipt_observation(payload, "later_observation")
    first_receipt_id, first_receipt_sha256 = _receipt_binding(payload)
    stage = payload.get("stage")
    if stage == "first" and (first_receipt_id is not None or first_receipt_sha256 is not None):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    if stage == "later" and first_observed_at is not None and first_hashes is not None and (
        first_receipt_id is None or first_receipt_sha256 is None
    ):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    payload["receipt_sha256"] = declared
    return payload


def _receipt_observation(
    payload: Mapping[str, object],
    key: str,
) -> tuple[datetime | None, dict[str, str] | None]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    observed_value = value.get("observed_at_utc")
    hashes = value.get("row_sha256")
    if observed_value is None and hashes is None:
        return None, None
    if observed_value is None or not isinstance(hashes, Mapping):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    parsed = {str(name): str(value) for name, value in hashes.items()}
    if tuple(parsed) != _TARGET_KEYS or any(not _is_sha256(value) for value in parsed.values()):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    return _parse_utc(observed_value), parsed


def _observation_payload(
    observed_at: datetime | None,
    hashes: Mapping[str, str] | None,
) -> dict[str, object]:
    return {
        "observed_at_utc": None if observed_at is None else _utc_marker(observed_at),
        "row_sha256": None if hashes is None else dict(hashes),
    }


def _receipt_binding_payload(
    receipt_id: str | None,
    receipt_sha256: str | None,
) -> dict[str, str | None]:
    if (receipt_id is None) != (receipt_sha256 is None):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_binding_invalid")
    if receipt_sha256 is not None and not _is_sha256(receipt_sha256):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_binding_invalid")
    return {"receipt_id": receipt_id, "receipt_sha256": receipt_sha256}


def _receipt_binding(payload: Mapping[str, object]) -> tuple[str | None, str | None]:
    value = payload.get("first_receipt_binding")
    if not isinstance(value, Mapping):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    receipt_id = value.get("receipt_id")
    receipt_sha256 = value.get("receipt_sha256")
    if receipt_id is None and receipt_sha256 is None:
        return None, None
    if not _is_receipt_id(receipt_id) or not _is_sha256(receipt_sha256):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    return receipt_id, receipt_sha256


def _validate_later_receipt_binding(
    receipts: Path,
    receipt: Mapping[str, object],
) -> None:
    if receipt.get("stage") != "later":
        return
    first_observed_at, first_hashes = _receipt_observation(receipt, "first_observation")
    first_receipt_id, first_receipt_sha256 = _receipt_binding(receipt)
    if first_observed_at is None or first_hashes is None:
        if first_receipt_id is not None or first_receipt_sha256 is not None:
            raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
        return
    if first_receipt_id is None or first_receipt_sha256 is None:
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    first = _read_existing(receipts, first_receipt_id)
    if (
        first is None
        or first.get("receipt_sha256") != first_receipt_sha256
        or first.get("status") != "first_recorded"
        or first.get("stage") != "first"
        or first.get("session_key") != receipt.get("session_key")
    ):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    first_time, first_hashes_from_receipt = _receipt_observation(first, "first_observation")
    if first_time != first_observed_at or first_hashes_from_receipt != first_hashes:
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")


def _publish_current(
    root: Path,
    receipt_id: str,
    result: KisPaperD1ProspectiveObservationPairingResult,
) -> None:
    if not _is_sha256(result.receipt_sha256):
        raise KisPaperD1ProspectiveObservationPairingError("receipt_invalid")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_KIND,
        "version": KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_VERSION,
        "record_type": "current_outcome_pointer",
        "source_contract_sha256": (
            KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256
        ),
        "receipt_id": receipt_id,
        "receipt_sha256": result.receipt_sha256,
        "status": result.status,
        "stage": result.stage,
        "session_key": None if result.session_key is None else result.session_key.isoformat(),
        "updated_at_utc": _utc_marker(result.observed_at),
    }
    payload["pointer_sha256"] = _sha256(payload)
    path = root / _CURRENT_FILENAME
    temporary = root / f".{_CURRENT_FILENAME}.tmp"
    with temporary.open("wb") as handle:
        handle.write(_canonical_json(payload))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_current_pointer(root: Path) -> dict[str, object]:
    path = root / _CURRENT_FILENAME
    if path.is_symlink() or not path.is_file():
        raise KisPaperD1ProspectiveObservationPairingError("current_pointer_unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperD1ProspectiveObservationPairingError("current_pointer_invalid") from error
    if not isinstance(payload, dict):
        raise KisPaperD1ProspectiveObservationPairingError("current_pointer_invalid")
    declared = payload.pop("pointer_sha256", None)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_KIND
        or payload.get("version") != KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_VERSION
        or payload.get("record_type") != "current_outcome_pointer"
        or payload.get("source_contract_sha256")
        != KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256
        or not _is_receipt_id(payload.get("receipt_id"))
        or not _is_sha256(payload.get("receipt_sha256"))
        or payload.get("status")
        not in {"first_recorded", "measurement_only_match", "disqualified", "input_unavailable"}
        or payload.get("stage") not in {"first", "later"}
        or not _is_sha256(declared)
        or declared != _sha256(payload)
    ):
        raise KisPaperD1ProspectiveObservationPairingError("current_pointer_invalid")
    _parse_utc(payload.get("updated_at_utc"))
    _parse_date(payload.get("session_key"))
    payload["pointer_sha256"] = declared
    return payload


def _load_state(root: Path, observed_at: datetime) -> dict[str, object]:
    path = root / _STATE_FILENAME
    if not path.exists():
        state = {
            "expected_stage": "first",
            "next_due_at": _first_due_at_or_after(observed_at),
            "session_key": None,
            "first_receipt_id": None,
            "first_receipt_sha256": None,
        }
        _write_state(root, **state)
        return state
    if path.is_symlink() or not path.is_file():
        raise KisPaperD1ProspectiveObservationPairingError("state_invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperD1ProspectiveObservationPairingError("state_invalid") from error
    if not isinstance(payload, dict) or payload.get("source_contract_sha256") != (
        KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256
    ):
        raise KisPaperD1ProspectiveObservationPairingError("state_invalid")
    stage = payload.get("expected_stage")
    if stage not in {"first", "later"}:
        raise KisPaperD1ProspectiveObservationPairingError("state_invalid")
    state = {
        "expected_stage": stage,
        "next_due_at": _parse_utc(payload.get("next_due_at_utc")),
        "session_key": _parse_date(payload.get("session_key")),
        "first_receipt_id": payload.get("first_receipt_id"),
        "first_receipt_sha256": payload.get("first_receipt_sha256"),
    }
    first_state_keys = ("session_key", "first_receipt_id", "first_receipt_sha256")
    if stage == "first" and any(state[key] is not None for key in first_state_keys):
        raise KisPaperD1ProspectiveObservationPairingError("state_invalid")
    return state


def _write_state(
    root: Path,
    expected_stage: Literal["first", "later"],
    next_due_at: datetime,
    session_key: date | None,
    first_receipt_id: str | None,
    first_receipt_sha256: str | None,
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_KIND,
        "version": KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_VERSION,
        "source_contract_sha256": (
            KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256
        ),
        "expected_stage": expected_stage,
        "next_due_at_utc": _utc_marker(next_due_at),
        "session_key": None if session_key is None else session_key.isoformat(),
        "first_receipt_id": first_receipt_id,
        "first_receipt_sha256": first_receipt_sha256,
    }
    path = root / _STATE_FILENAME
    temporary = root / f".{_STATE_FILENAME}.tmp"
    with temporary.open("wb") as handle:
        handle.write(_canonical_json(payload))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _artifact_root(artifact_root: Path, repository_root: Path) -> Path:
    return ensure_external_artifact_directory(
        artifact_root,
        repository_root,
        *KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS,
    )


def _existing_artifact_root(artifact_root: Path, repository_root: Path) -> Path:
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise KisPaperD1ProspectiveObservationPairingError("artifact_root_unavailable")
    root = artifact_root.resolve()
    repository = repository_root.resolve()
    allowed_container_mount = repository == Path("/app") and root.is_relative_to(
        Path("/app/model_artifacts")
    )
    if root.is_relative_to(repository) and not allowed_container_mount:
        raise KisPaperD1ProspectiveObservationPairingError("artifact_root_invalid")
    target = root.joinpath(*KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS)
    if target.is_symlink() or not target.is_dir():
        raise KisPaperD1ProspectiveObservationPairingError("artifact_root_unavailable")
    return target.resolve()


def _receipt_directory(root: Path) -> Path:
    path = root / _RECEIPTS_DIRECTORY
    path.mkdir(exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise KisPaperD1ProspectiveObservationPairingError("receipt_directory_invalid")
    return path.resolve()


def _scheduled_stage(observed_at: datetime) -> PairingStage:
    local = observed_at.astimezone(_KOREA_TZ)
    if local.weekday() not in _ACTIVE_KST_WEEKDAYS:
        return "none"
    if (local.hour, local.minute) == (_FIRST_TIME.hour, _FIRST_TIME.minute):
        return "first"
    if (local.hour, local.minute) == (_LATER_TIME.hour, _LATER_TIME.minute):
        return "later"
    return "none"


def _first_due_at_or_after(observed_at: datetime) -> datetime:
    local = observed_at.astimezone(_KOREA_TZ)
    candidate = datetime.combine(local.date(), _FIRST_TIME, tzinfo=_KOREA_TZ)
    if local.weekday() in _ACTIVE_KST_WEEKDAYS and (local.hour, local.minute) == (
        candidate.hour,
        candidate.minute,
    ):
        return candidate.astimezone(UTC)
    return _next_candidate(candidate, local).astimezone(UTC)


def _later_due(observed_at: datetime) -> datetime:
    local = observed_at.astimezone(_KOREA_TZ)
    due = datetime.combine(local.date(), _LATER_TIME, tzinfo=_KOREA_TZ)
    if due <= local:
        raise KisPaperD1ProspectiveObservationPairingError("later_due_invalid")
    return due.astimezone(UTC)


def _next_first_due(observed_at: datetime) -> datetime:
    local = observed_at.astimezone(_KOREA_TZ)
    candidate = datetime.combine(local.date(), _FIRST_TIME, tzinfo=_KOREA_TZ)
    return _next_candidate(candidate, local).astimezone(UTC)


def _next_candidate(candidate: datetime, local: datetime) -> datetime:
    while candidate <= local or candidate.weekday() not in _ACTIVE_KST_WEEKDAYS:
        candidate += timedelta(days=1)
    return candidate


def _first_receipt_id(session: date) -> str:
    return (
        f"first-{session:%Y%m%d}-"
        f"{KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_SOURCE_CONTRACT_SHA256[7:19]}"
    )


def _later_receipt_id(session: date, first_receipt_sha256: str) -> str:
    return f"later-{session:%Y%m%d}-{first_receipt_sha256[7:19]}"


def _terminal_receipt_id(
    stage: Literal["first", "later"],
    session: date | None,
    observed_at: datetime,
) -> str:
    key = "no-session" if session is None else session.strftime("%Y%m%d")
    return f"{stage}-{key}-terminal-{observed_at:%Y%m%dT%H%MZ}"


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise KisPaperD1ProspectiveObservationPairingError("timestamp_invalid")
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp")
    except ValueError as error:
        raise KisPaperD1ProspectiveObservationPairingError("timestamp_invalid") from error


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise KisPaperD1ProspectiveObservationPairingError("session_invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise KisPaperD1ProspectiveObservationPairingError("session_invalid") from error


def _sha256(value: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_text(value: object) -> str:
    if not _is_sha256(value):
        raise KisPaperD1ProspectiveObservationPairingError("hash_invalid")
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _is_receipt_id(value: object) -> bool:
    return isinstance(value, str) and _SAFE_RECEIPT_ID.fullmatch(value) is not None


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "timestamp").strftime("%Y-%m-%dT%H:%M:%SZ")
