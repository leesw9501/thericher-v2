"""Bounded D1 stability measurements for the private KIS Paper SPY head.

This observer compares one retained prior-session row from an already verified
daily-head snapshot with one separately timed virtual-Paper ``dailyprice``
response.  It is deliberately not a data qualification or consumer bridge:
its receipts retain only categorical status, scope bindings, timestamps, and
hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, Literal, Protocol
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_paper_daily_spy_head import (
    KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
    KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
    KisPaperDailySpyHeadSnapshot,
    load_verified_kis_paper_daily_spy_head,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_KIND = "kis_paper_daily_spy_d1_stability_observer"
KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_VERSION = "v1"
KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_PARTS = (
    "data",
    "kis-paper-daily-spy-d1-stability-observer",
    "v1",
)
KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS = 10
KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)
_OBSERVER_LOCK_FILENAME = ".d1-stability-observer.lock"

_KOREA_TZ = ZoneInfo("Asia/Seoul")
_EASTERN_TZ = ZoneInfo("America/New_York")
_WINDOW_START = time(23, 15)
_WINDOW_END = time(23, 20)
_MINIMUM_SNAPSHOT_AGE = timedelta(minutes=15)
_MAXIMUM_SNAPSHOT_AGE = timedelta(minutes=90)
_SAFE_SCOPE = {
    "provider": "kis_open_api_virtual_paper",
    "endpoint": "dailyprice",
    "symbol": KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
    "exchange": KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
    "adjustment_mode": "MODP=0_unadjusted",
}
_RECEIPT_ID = re.compile(
    r"d1-stability-[0-9]{8}T[0-9]{6}Z-(?:attempt-[0-9]{2}|nonattempt)-[0-9a-f]{12}"
)

ObserverStatus = Literal["stable", "changed", "unavailable", "outside_window"]


class KisPaperDailySpyStabilityObserverError(RuntimeError):
    """A source-safe failure from the isolated D1 stability observer."""


class _DailyPageClient(Protocol):
    def ensure_authenticated(self) -> None: ...

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage: ...


SnapshotLoader = Callable[..., KisPaperDailySpyHeadSnapshot]
DailyClientFactory = Callable[[], _DailyPageClient]


@dataclass(frozen=True, slots=True)
class KisPaperDailySpyStabilityObservation:
    """One source-safe D1 stability result without raw market values."""

    receipt_id: str
    status: ObserverStatus
    reason: str | None
    observer_observed_at: datetime
    snapshot_observed_at: datetime | None
    snapshot_age_bucket: str
    dataset_hash: str | None
    retained_session: date | None
    snapshot_row_sha256: str | None
    response_row_sha256: str | None
    dailyprice_get_count: int
    attempt_ordinal: int | None
    evidence_path: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observer_observed_at",
            require_utc(self.observer_observed_at, "observer_observed_at"),
        )
        if self.snapshot_observed_at is not None:
            object.__setattr__(
                self,
                "snapshot_observed_at",
                require_utc(self.snapshot_observed_at, "snapshot_observed_at"),
            )
        if not _RECEIPT_ID.fullmatch(self.receipt_id):
            raise ValueError("daily stability receipt identifier is invalid")
        if self.status not in {"stable", "changed", "unavailable", "outside_window"}:
            raise ValueError("daily stability status is invalid")
        if self.reason is not None and not _is_reason(self.reason):
            raise ValueError("daily stability reason is invalid")
        if self.snapshot_age_bucket not in {
            "not_observed",
            "future",
            "under_15_minutes",
            "15_to_90_minutes",
            "over_90_minutes",
        }:
            raise ValueError("daily stability age bucket is invalid")
        for value in (self.dataset_hash, self.snapshot_row_sha256, self.response_row_sha256):
            if value is not None and not _is_sha256_reference(value):
                raise ValueError("daily stability hash is invalid")
        if self.retained_session is not None and type(self.retained_session) is not date:
            raise ValueError("daily stability retained session is invalid")
        if self.dailyprice_get_count not in {0, 1}:
            raise ValueError("daily stability request count is invalid")
        if self.dailyprice_get_count == 1:
            if (
                type(self.attempt_ordinal) is not int
                or not 1
                <= self.attempt_ordinal
                <= KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS
            ):
                raise ValueError("daily stability attempt ordinal is invalid")
        elif self.attempt_ordinal is not None:
            raise ValueError("daily stability non-attempt ordinal is invalid")
        if self.status == "stable":
            if (
                self.dailyprice_get_count != 1
                or self.snapshot_row_sha256 is None
                or self.response_row_sha256 != self.snapshot_row_sha256
                or self.dataset_hash is None
                or self.retained_session is None
            ):
                raise ValueError("daily stability stable result is invalid")
        if self.status == "changed":
            if (
                self.dailyprice_get_count != 1
                or self.snapshot_row_sha256 is None
                or self.response_row_sha256 is None
                or self.response_row_sha256 == self.snapshot_row_sha256
                or self.dataset_hash is None
                or self.retained_session is None
            ):
                raise ValueError("daily stability changed result is invalid")
        if self.status == "outside_window" and self.dailyprice_get_count != 0:
            raise ValueError("daily stability outside-window result is invalid")
        if self.evidence_path is not None and self.evidence_path.suffix != ".json":
            raise ValueError("daily stability evidence path is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Render the receipt contract without rows, prices, or request material."""

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_KIND,
            "version": KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_VERSION,
            "receipt_id": self.receipt_id,
            "status": self.status,
            "reason": self.reason,
            "measurement": {
                "campaign": "d1_stability_v1",
                "attempt_ordinal": self.attempt_ordinal,
                "maximum_valid_attempts": KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS,
                "observer_observed_at_utc": _utc_marker(self.observer_observed_at),
                "snapshot_observed_at_utc": (
                    None
                    if self.snapshot_observed_at is None
                    else _utc_marker(self.snapshot_observed_at)
                ),
                "snapshot_age_reference": "observer_observed_at_minus_snapshot_observed_at",
                "snapshot_age_bucket": self.snapshot_age_bucket,
                "task_window": "kst_weekday_2315_to_2320",
            },
            "scope": dict(_SAFE_SCOPE),
            "snapshot": {
                "dataset_hash": self.dataset_hash,
                "retained_session": (
                    None if self.retained_session is None else self.retained_session.isoformat()
                ),
                "prior_session_row_sha256": self.snapshot_row_sha256,
            },
            "response": {
                "prior_session_row_sha256": self.response_row_sha256,
            },
            "provider_finality": "not_observed",
            "virtual_paper_only": True,
            "nontransferable_to_live": True,
            "limits": {
                "dailyprice_get_count": self.dailyprice_get_count,
                "retry_count": 0,
                "foreground_waited": False,
            },
        }
        payload["receipt_sha256"] = _sha256(_canonical_json(payload))
        return payload


@dataclass(frozen=True, slots=True)
class _SnapshotBinding:
    dataset_hash: str
    retained_session: date
    snapshot_observed_at: datetime
    prior_session_row_sha256: str


def observe_kis_paper_daily_spy_stability(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    artifact_root: Path | str = KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_ROOT,
    repository_root: Path | str,
    observed_at: datetime,
    client_factory: DailyClientFactory,
    snapshot_loader: SnapshotLoader = load_verified_kis_paper_daily_spy_head,
) -> KisPaperDailySpyStabilityObservation:
    """Write one bounded categorical measurement when the exact task window is open.

    The client is intentionally created only after the task window and the
    existing head's complete scope/timing binding are known.  This prevents an
    unavailable cache, expired snapshot, or out-of-window invocation from
    performing a KIS request.
    """

    observed = require_utc(observed_at, "observed_at")
    directory = _ensure_receipt_directory(
        artifact_root=Path(artifact_root), repository_root=Path(repository_root)
    )
    with _try_exclusive_observer_lock(directory.parent / _OBSERVER_LOCK_FILENAME) as locked:
        if not locked:
            return _result(
                observed_at=observed,
                status="unavailable",
                reason="observer_lock_held",
            )
        return _observe_locked(
            cache_root=Path(cache_root),
            artifact_root=Path(artifact_root),
            repository_root=Path(repository_root),
            observed_at=observed,
            client_factory=client_factory,
            snapshot_loader=snapshot_loader,
            directory=directory,
        )


def _observe_locked(
    *,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime,
    client_factory: DailyClientFactory,
    snapshot_loader: SnapshotLoader,
    directory: Path,
) -> KisPaperDailySpyStabilityObservation:
    """Run the one-request study while its receipt ledger is exclusively held."""

    try:
        attempt_count = _count_dailyprice_attempt_receipts(
            directory=directory,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
    except KisPaperDailySpyStabilityObserverError:
        return _result(
            observed_at=observed_at,
            status="unavailable",
            reason="receipt_ledger_invalid",
        )
    if attempt_count >= KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS:
        return _result(
            observed_at=observed_at,
            status="unavailable",
            reason="observation_budget_exhausted",
        )
    if not _inside_observer_window(observed_at):
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="outside_window",
                reason="observer_window_outside",
            ),
            directory=directory,
        )

    try:
        binding = _load_snapshot_binding(
            cache_root=cache_root,
            repository_root=repository_root,
            snapshot_loader=snapshot_loader,
        )
    except (KisPaperDailySpyStabilityObserverError, OSError, ValueError):
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="unavailable",
                reason="snapshot_unavailable",
            ),
            directory=directory,
        )

    age_bucket = _snapshot_age_bucket(
        observed_at=observed_at,
        snapshot_observed_at=binding.snapshot_observed_at,
    )
    common_kwargs: dict[str, object] = {
        "snapshot_observed_at": binding.snapshot_observed_at,
        "snapshot_age_bucket": age_bucket,
        "dataset_hash": binding.dataset_hash,
        "retained_session": binding.retained_session,
        "snapshot_row_sha256": binding.prior_session_row_sha256,
    }
    if age_bucket != "15_to_90_minutes":
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="unavailable",
                reason="snapshot_age_outside_window",
                **common_kwargs,
            ),
            directory=directory,
        )
    if binding.retained_session >= observed_at.astimezone(_EASTERN_TZ).date():
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="unavailable",
                reason="retained_session_not_prior",
                **common_kwargs,
            ),
            directory=directory,
        )

    expected_query = KisPaperDailyQuery(
        symbol=KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
        exchange=KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
        by_date=observed_at.astimezone(_EASTERN_TZ).strftime("%Y%m%d"),
        approved_symbol_exchanges={
            KIS_PAPER_DAILY_SPY_HEAD_SYMBOL: frozenset({KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE})
        },
    )
    try:
        client = client_factory()
    except (KisPaperMarketDataError, OSError, ValueError):
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="unavailable",
                reason="dailyprice_client_unavailable",
                **common_kwargs,
            ),
            directory=directory,
        )
    try:
        client.ensure_authenticated()
    except (KisPaperMarketDataError, OSError, ValueError):
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="unavailable",
                reason="dailyprice_auth_unavailable",
                **common_kwargs,
            ),
            directory=directory,
        )

    # The client increments its one-page budget immediately before dispatching
    # the GET.  From this call onward the bounded campaign owns one attempt.
    attempt_ordinal = attempt_count + 1
    attempt_kwargs = {
        **common_kwargs,
        "attempt_ordinal": attempt_ordinal,
    }
    try:
        page = client.fetch_daily_raw_page(expected_query)
        response_row_sha256 = _filtered_response_row_sha256(
            page=page,
            expected_query=expected_query,
            retained_session=binding.retained_session,
        )
    except (KisPaperDailySpyStabilityObserverError, KisPaperMarketDataError, OSError, ValueError):
        return _persist_receipt(
            _result(
                observed_at=observed_at,
                status="unavailable",
                reason="dailyprice_response_unavailable",
                dailyprice_get_count=1,
                **attempt_kwargs,
            ),
            directory=directory,
        )

    if response_row_sha256 == binding.prior_session_row_sha256:
        result = _result(
            observed_at=observed_at,
            status="stable",
            dailyprice_get_count=1,
            response_row_sha256=response_row_sha256,
            **attempt_kwargs,
        )
    else:
        result = _result(
            observed_at=observed_at,
            status="changed",
            reason="prior_session_row_changed",
            dailyprice_get_count=1,
            response_row_sha256=response_row_sha256,
            **attempt_kwargs,
        )
    return _persist_receipt(result, directory=directory)


def validate_kis_paper_daily_spy_stability_receipt(
    receipt_path: Path | str,
    *,
    artifact_root: Path | str = KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_ROOT,
    repository_root: Path | str,
) -> KisPaperDailySpyStabilityObservation:
    """Validate a stored source-safe receipt without a client or credentials."""

    directory = _existing_receipt_directory(
        artifact_root=Path(artifact_root), repository_root=Path(repository_root)
    )
    candidate = Path(receipt_path)
    if candidate.is_symlink() or not candidate.is_file():
        raise KisPaperDailySpyStabilityObserverError("receipt_unavailable")
    resolved = candidate.resolve(strict=True)
    if resolved.parent != directory:
        raise KisPaperDailySpyStabilityObserverError("receipt_outside_namespace")
    return _validate_receipt_file(resolved)


def _load_snapshot_binding(
    *,
    cache_root: Path,
    repository_root: Path,
    snapshot_loader: SnapshotLoader,
) -> _SnapshotBinding:
    snapshot = snapshot_loader(cache_root=cache_root, repository_root=repository_root)
    if not isinstance(snapshot, KisPaperDailySpyHeadSnapshot):
        raise KisPaperDailySpyStabilityObserverError("snapshot_type_invalid")
    if (
        type(snapshot.last_session) is not date
        or not snapshot.dataset_id
        or not _is_sha256_reference(snapshot.dataset_hash)
        or not snapshot.bars
    ):
        raise KisPaperDailySpyStabilityObserverError("snapshot_identity_invalid")
    observed_at = require_utc(snapshot.collected_at, "snapshot_collected_at")
    retained_bar = snapshot.bars[-1]
    if (
        not isinstance(retained_bar, Bar)
        or retained_bar.symbol != KIS_PAPER_DAILY_SPY_HEAD_SYMBOL
        or retained_bar.market != "US"
        or retained_bar.timeframe is not Timeframe.D1
        or not retained_bar.complete
        or retained_bar.start_ts.date() != snapshot.last_session
    ):
        raise KisPaperDailySpyStabilityObserverError("snapshot_session_invalid")
    return _SnapshotBinding(
        dataset_hash=snapshot.dataset_hash,
        retained_session=snapshot.last_session,
        snapshot_observed_at=observed_at,
        prior_session_row_sha256=_bar_row_sha256(retained_bar),
    )


def _filtered_response_row_sha256(
    *,
    page: KisPaperDailyRawPage,
    expected_query: KisPaperDailyQuery,
    retained_session: date,
) -> str:
    if not isinstance(page, KisPaperDailyRawPage) or not isinstance(
        page.page.query, KisPaperDailyQuery
    ):
        raise KisPaperDailySpyStabilityObserverError("dailyprice_response_invalid")
    query = page.page.query
    if (
        query.symbol != expected_query.symbol
        or query.exchange != expected_query.exchange
        or query.by_date != expected_query.by_date
        or query.adjustment_mode != "0"
        or query.continuation is not None
        or query.approved_symbol_exchanges != expected_query.approved_symbol_exchanges
    ):
        raise KisPaperDailySpyStabilityObserverError("dailyprice_scope_invalid")
    filtered = tuple(row for row in page.rows if _row_session(row) == retained_session)
    if len(filtered) != 1:
        raise KisPaperDailySpyStabilityObserverError("dailyprice_prior_session_unavailable")
    return _daily_row_sha256(filtered[0])


def _inside_observer_window(observed_at: datetime) -> bool:
    local = require_utc(observed_at, "observed_at").astimezone(_KOREA_TZ)
    local_time = local.timetz().replace(tzinfo=None)
    return local.weekday() < 5 and _WINDOW_START <= local_time < _WINDOW_END


def _snapshot_age_bucket(*, observed_at: datetime, snapshot_observed_at: datetime) -> str:
    age = require_utc(observed_at, "observed_at") - require_utc(
        snapshot_observed_at, "snapshot_observed_at"
    )
    if age < timedelta(0):
        return "future"
    if age < _MINIMUM_SNAPSHOT_AGE:
        return "under_15_minutes"
    if age <= _MAXIMUM_SNAPSHOT_AGE:
        return "15_to_90_minutes"
    return "over_90_minutes"


def _result(
    *,
    observed_at: datetime,
    status: ObserverStatus,
    reason: str | None = None,
    snapshot_observed_at: datetime | None = None,
    snapshot_age_bucket: str = "not_observed",
    dataset_hash: str | None = None,
    retained_session: date | None = None,
    snapshot_row_sha256: str | None = None,
    response_row_sha256: str | None = None,
    dailyprice_get_count: int = 0,
    attempt_ordinal: int | None = None,
) -> KisPaperDailySpyStabilityObservation:
    attempt_marker = "nonattempt" if attempt_ordinal is None else f"attempt-{attempt_ordinal:02d}"
    receipt_id = (
        f"d1-stability-{require_utc(observed_at, 'observed_at').strftime('%Y%m%dT%H%M%SZ')}-"
        f"{attempt_marker}-{uuid.uuid4().hex[:12]}"
    )
    return KisPaperDailySpyStabilityObservation(
        receipt_id=receipt_id,
        status=status,
        reason=reason,
        observer_observed_at=observed_at,
        snapshot_observed_at=snapshot_observed_at,
        snapshot_age_bucket=snapshot_age_bucket,
        dataset_hash=dataset_hash,
        retained_session=retained_session,
        snapshot_row_sha256=snapshot_row_sha256,
        response_row_sha256=response_row_sha256,
        dailyprice_get_count=dailyprice_get_count,
        attempt_ordinal=attempt_ordinal,
    )


def _persist_receipt(
    observation: KisPaperDailySpyStabilityObservation,
    *,
    directory: Path,
) -> KisPaperDailySpyStabilityObservation:
    target = directory / f"{observation.receipt_id}.json"
    payload = _canonical_json(observation.safe_payload())
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise KisPaperDailySpyStabilityObserverError("receipt_identity_conflict") from error
    return replace(observation, evidence_path=target)


def _ensure_receipt_directory(*, artifact_root: Path, repository_root: Path) -> Path:
    return ensure_external_artifact_directory(
        artifact_root,
        repository_root,
        *KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_PARTS,
    )


def _existing_receipt_directory(*, artifact_root: Path, repository_root: Path) -> Path:
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise KisPaperDailySpyStabilityObserverError("artifact_root_unavailable")
    root = artifact_root.resolve(strict=True)
    _assert_external_artifact_root(root, repository_root)
    directory = root.joinpath(*KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_PARTS)
    if directory.is_symlink() or not directory.is_dir():
        raise KisPaperDailySpyStabilityObserverError("receipt_namespace_unavailable")
    resolved = directory.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise KisPaperDailySpyStabilityObserverError("receipt_namespace_invalid")
    return resolved


@contextmanager
def _try_exclusive_observer_lock(path: Path) -> Iterator[bool]:
    """Claim the finite receipt ledger without waiting behind another observer."""

    if path.is_symlink():
        raise KisPaperDailySpyStabilityObserverError("observer_lock_invalid")
    with path.open("a+b") as handle:
        if not _try_lock(handle):
            yield False
            return
        try:
            yield True
        finally:
            _unlock(handle)


def _try_lock(handle: BinaryIO) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(handle: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _assert_external_artifact_root(artifact_root: Path, repository_root: Path) -> None:
    repository = repository_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = docker_repository / "model_artifacts"
    if repository == docker_repository and (
        artifact_root == docker_artifacts or artifact_root.is_relative_to(docker_artifacts)
    ):
        return
    if artifact_root == repository or artifact_root.is_relative_to(repository):
        raise KisPaperDailySpyStabilityObserverError("artifact_root_inside_repository")


def _count_dailyprice_attempt_receipts(
    *,
    directory: Path,
    artifact_root: Path,
    repository_root: Path,
) -> int:
    _assert_external_artifact_root(directory.resolve(strict=True), repository_root)
    observations: list[KisPaperDailySpyStabilityObservation] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise KisPaperDailySpyStabilityObserverError("receipt_ledger_invalid")
        observation = validate_kis_paper_daily_spy_stability_receipt(
            path,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
        observations.append(observation)
    attempts = [
        observation
        for observation in observations
        if observation.dailyprice_get_count == 1
    ]
    ordinals = sorted(observation.attempt_ordinal for observation in attempts)
    if ordinals != list(range(1, len(attempts) + 1)):
        raise KisPaperDailySpyStabilityObserverError("receipt_ledger_invalid")
    if len(attempts) > KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS:
        raise KisPaperDailySpyStabilityObserverError("receipt_ledger_invalid")
    return len(attempts)


def _validate_receipt_file(path: Path) -> KisPaperDailySpyStabilityObservation:
    payload = _json_mapping(_read_regular_file(path), "receipt")
    expected_keys = {
        "schema_version",
        "kind",
        "version",
        "receipt_id",
        "status",
        "reason",
        "measurement",
        "scope",
        "snapshot",
        "response",
        "provider_finality",
        "virtual_paper_only",
        "nontransferable_to_live",
        "limits",
        "receipt_sha256",
    }
    if set(payload) != expected_keys:
        raise KisPaperDailySpyStabilityObserverError("receipt_schema_invalid")
    receipt_hash = payload.pop("receipt_sha256")
    if not _is_sha256_reference(receipt_hash) or receipt_hash != _sha256(_canonical_json(payload)):
        raise KisPaperDailySpyStabilityObserverError("receipt_hash_invalid")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_KIND
        or payload.get("version") != KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_VERSION
        or payload.get("provider_finality") != "not_observed"
        or payload.get("virtual_paper_only") is not True
        or payload.get("nontransferable_to_live") is not True
    ):
        raise KisPaperDailySpyStabilityObserverError("receipt_schema_invalid")
    measurement = _mapping(payload.get("measurement"), "receipt_measurement")
    scope = _mapping(payload.get("scope"), "receipt_scope")
    snapshot = _mapping(payload.get("snapshot"), "receipt_snapshot")
    response = _mapping(payload.get("response"), "receipt_response")
    limits = _mapping(payload.get("limits"), "receipt_limits")
    if set(measurement) != {
        "campaign",
        "attempt_ordinal",
        "maximum_valid_attempts",
        "observer_observed_at_utc",
        "snapshot_observed_at_utc",
        "snapshot_age_reference",
        "snapshot_age_bucket",
        "task_window",
    } or (
        measurement.get("campaign") != "d1_stability_v1"
        or measurement.get("maximum_valid_attempts")
        != KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS
        or measurement.get("snapshot_age_reference")
        != "observer_observed_at_minus_snapshot_observed_at"
        or measurement.get("task_window") != "kst_weekday_2315_to_2320"
    ):
        raise KisPaperDailySpyStabilityObserverError("receipt_measurement_invalid")
    if scope != _SAFE_SCOPE:
        raise KisPaperDailySpyStabilityObserverError("receipt_scope_invalid")
    if set(snapshot) != {
        "dataset_hash",
        "retained_session",
        "prior_session_row_sha256",
    } or set(response) != {
        "prior_session_row_sha256",
    } or set(limits) != {"dailyprice_get_count", "retry_count", "foreground_waited"}:
        raise KisPaperDailySpyStabilityObserverError("receipt_schema_invalid")
    if limits.get("retry_count") != 0 or limits.get("foreground_waited") is not False:
        raise KisPaperDailySpyStabilityObserverError("receipt_limits_invalid")
    observer_observed_at = _parse_utc(measurement.get("observer_observed_at_utc"))
    snapshot_observed_at_value = measurement.get("snapshot_observed_at_utc")
    snapshot_observed_at = (
        None
        if snapshot_observed_at_value is None
        else _parse_utc(snapshot_observed_at_value)
    )
    retained_session_value = snapshot.get("retained_session")
    retained_session = (
        None
        if retained_session_value is None
        else _iso_date(retained_session_value, "retained_session")
    )
    return KisPaperDailySpyStabilityObservation(
        receipt_id=_text(payload.get("receipt_id"), "receipt_id"),
        status=_text(payload.get("status"), "status"),
        reason=_optional_reason(payload.get("reason")),
        observer_observed_at=observer_observed_at,
        snapshot_observed_at=snapshot_observed_at,
        snapshot_age_bucket=_text(measurement.get("snapshot_age_bucket"), "snapshot_age_bucket"),
        dataset_hash=_optional_hash(snapshot.get("dataset_hash")),
        retained_session=retained_session,
        snapshot_row_sha256=_optional_hash(snapshot.get("prior_session_row_sha256")),
        response_row_sha256=_optional_hash(response.get("prior_session_row_sha256")),
        dailyprice_get_count=_int(limits.get("dailyprice_get_count"), "dailyprice_get_count"),
        attempt_ordinal=_optional_int(measurement.get("attempt_ordinal"), "attempt_ordinal"),
        evidence_path=path,
    )


def _bar_row_sha256(bar: Bar) -> str:
    return _ohlcv_row_sha256(
        session=bar.start_ts.date(),
        open_value=bar.open,
        high_value=bar.high,
        low_value=bar.low,
        close_value=bar.close,
        volume_value=bar.volume,
    )


def _daily_row_sha256(row: KisPaperDailyRawRow) -> str:
    return _ohlcv_row_sha256(
        session=_row_session(row),
        open_value=row.open,
        high_value=row.high,
        low_value=row.low,
        close_value=row.clos,
        volume_value=row.tvol,
    )


def _ohlcv_row_sha256(
    *,
    session: date,
    open_value: Decimal | str,
    high_value: Decimal | str,
    low_value: Decimal | str,
    close_value: Decimal | str,
    volume_value: Decimal | str,
) -> str:
    return _sha256(
        _canonical_json(
            {
                "session_date": session.isoformat(),
                "open": _normalized_decimal_text(open_value),
                "high": _normalized_decimal_text(high_value),
                "low": _normalized_decimal_text(low_value),
                "close": _normalized_decimal_text(close_value),
                "volume": _normalized_decimal_text(volume_value),
            }
        )
    )


def _normalized_decimal_text(value: Decimal | str) -> str:
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise KisPaperDailySpyStabilityObserverError("dailyprice_response_invalid") from error
    if not decimal.is_finite():
        raise KisPaperDailySpyStabilityObserverError("dailyprice_response_invalid")
    return format(decimal.normalize(), "f")


def _row_session(row: KisPaperDailyRawRow) -> date:
    try:
        return datetime.strptime(row.xymd, "%Y%m%d").date()
    except ValueError as error:
        raise KisPaperDailySpyStabilityObserverError("dailyprice_response_invalid") from error


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise KisPaperDailySpyStabilityObserverError("receipt_or_snapshot_unavailable")
    try:
        return path.read_bytes()
    except OSError as error:
        raise KisPaperDailySpyStabilityObserverError("receipt_or_snapshot_unavailable") from error


def _json_mapping(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise KisPaperDailySpyStabilityObserverError("timestamp_invalid")
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp")
    except (TypeError, ValueError) as error:
        raise KisPaperDailySpyStabilityObserverError("timestamp_invalid") from error


def _iso_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid") from error


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid")
    return value


def _int(value: object, label: str) -> int:
    if type(value) is not int:
        raise KisPaperDailySpyStabilityObserverError(f"{label}_invalid")
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _int(value, label)


def _optional_hash(value: object) -> str | None:
    if value is None:
        return None
    if not _is_sha256_reference(value):
        raise KisPaperDailySpyStabilityObserverError("receipt_hash_value_invalid")
    return value


def _optional_reason(value: object) -> str | None:
    if value is None:
        return None
    if not _is_reason(value):
        raise KisPaperDailySpyStabilityObserverError("receipt_reason_invalid")
    return value


def _is_reason(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.isascii()
        and value.replace("_", "").isalnum()
    )


def _is_sha256_reference(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")
