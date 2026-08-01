"""Offline capture of one fresh KIS Paper SPY prospective observation.

The KIS collector owns credentials, transport, and cache mutation.  This
module deliberately owns none of those concerns: it consumes one already
verified local ``SPY/AMS/1m`` catalog and materializes only a source-safe
receipt after the fixed 15:30 America/New_York decision boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, require_utc
from thericher_v2.data.kis_paper_intraday import (
    load_verified_kis_paper_private_intraday_catalog,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.models.prospective_spy_intraday_observation import (
    ProspectiveSpyIntradayObservationReceipt,
    observe_prospective_spy_intraday_baseline,
)
from thericher_v2.models.prospective_spy_intraday_session import (
    ProspectiveSpyIntradaySessionInputError,
    build_prospective_spy_intraday_session_record,
)

KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_KIND = "kis_paper_prospective_spy_capture"
KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_SCHEMA_ID = "kis-paper-prospective-spy-capture-v1"
KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_TARGET = "SPY/AMS/1m"
KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_ARTIFACT_DIR = (
    "kis-paper-prospective-spy-capture-v1"
)
_EASTERN = ZoneInfo("America/New_York")
_DECISION_TIME = time(15, 30)
_NOT_YET_OBSERVED_REASONS = frozenset(
    {
        "calendar_unavailable",
        "not_current_eastern_session",
        "regular_session_unavailable",
        "before_decision_cutoff",
        "verified_source_unavailable",
        "cutoff_coverage_incomplete",
    }
)

CaptureStatus = Literal["captured", "not_yet_observed"]


@dataclass(frozen=True, slots=True)
class KisPaperProspectiveSpyCaptureResult:
    """One capture attempt whose serialization deliberately excludes source rows."""

    status: CaptureStatus
    session_date: date
    observed_at: datetime
    cutoff: datetime | None
    reason: str | None
    receipt: ProspectiveSpyIntradayObservationReceipt | None = field(repr=False)
    artifact_path: Path | None = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"captured", "not_yet_observed"}:
            raise ValueError("prospective SPY capture status is invalid")
        if type(self.session_date) is not date:
            raise ValueError("prospective SPY capture session date is invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.cutoff is not None:
            object.__setattr__(self, "cutoff", require_utc(self.cutoff, "cutoff"))
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("prospective SPY capture schema version is invalid")
        if self.status == "captured":
            if self.reason is not None or self.receipt is None or self.artifact_path is None:
                raise ValueError("captured prospective SPY result is incomplete")
            if self.cutoff != self.receipt.cutoff:
                raise ValueError("captured prospective SPY result cutoff is invalid")
        else:
            if (
                self.reason not in _NOT_YET_OBSERVED_REASONS
                or self.receipt is not None
                or self.artifact_path is not None
            ):
                raise ValueError("not-yet-observed prospective SPY result is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return observability facts without bars, paths, or execution state."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_KIND,
            "schema_id": KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_SCHEMA_ID,
            "provider": "KIS Open API virtual paper",
            "target": {
                "symbol": "SPY",
                "exchange": "AMS",
                "market": "US",
                "timeframe": "1m",
            },
            "session_date": self.session_date.isoformat(),
            "observed_at": _utc_marker(self.observed_at),
            "cutoff": None if self.cutoff is None else _utc_marker(self.cutoff),
            "status": self.status,
            "reason": self.reason,
            "receipt": None if self.receipt is None else self.receipt.to_payload(),
        }


def capture_kis_paper_prospective_spy_observation(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    repo_root: Path | str,
    session_date: date,
    observed_at: datetime,
) -> KisPaperProspectiveSpyCaptureResult:
    """Capture one same-day SPY receipt from a verified local KIS Paper cache.

    A capture is intentionally same-Eastern-date only.  That prevents an old
    historical cache session from being reclassified as a prospective event
    after this runner was introduced.  A later worker can retry the current
    session until midnight Eastern without creating a second receipt.
    """

    if type(session_date) is not date:
        raise ValueError("session_date must be a date")
    observed = require_utc(observed_at, "observed_at")
    try:
        session = us_equity_2026_session(session_date)
    except ValueError:
        return _not_yet_observed(
            session_date=session_date,
            observed_at=observed,
            cutoff=None,
            reason="calendar_unavailable",
        )
    if session is None or session.kind != "regular":
        return _not_yet_observed(
            session_date=session_date,
            observed_at=observed,
            cutoff=None if session is None else _decision_cutoff(session_date),
            reason="regular_session_unavailable",
        )

    cutoff = _decision_cutoff(session_date)
    if observed.astimezone(_EASTERN).date() != session_date:
        return _not_yet_observed(
            session_date=session_date,
            observed_at=observed,
            cutoff=cutoff,
            reason="not_current_eastern_session",
        )
    if observed < cutoff:
        return _not_yet_observed(
            session_date=session_date,
            observed_at=observed,
            cutoff=cutoff,
            reason="before_decision_cutoff",
        )

    repository = Path(repo_root).resolve(strict=False)
    try:
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=Path(cache_root),
            repo_root=repository,
            symbol="SPY",
            exchange="AMS",
        )
    except (OSError, ValueError):
        return _not_yet_observed(
            session_date=session_date,
            observed_at=observed,
            cutoff=cutoff,
            reason="verified_source_unavailable",
        )

    source_bars = tuple(
        bar
        for bar in catalog.bars
        if session.window.open_ts <= bar.start_ts < cutoff and bar.end_ts <= cutoff
    )
    source_contract_hash = _source_contract_hash(
        catalog_dataset_id=catalog.dataset_id,
        selected_bar_content_sha256=_selected_bar_content_sha256(source_bars),
        session_date=session_date,
        session_open_ts=session.window.open_ts,
        session_close_ts=session.window.close_ts,
        cutoff=cutoff,
    )
    try:
        record = build_prospective_spy_intraday_session_record(
            source_bars,
            session=session.window,
            cutoff=cutoff,
            source_contract_hash=source_contract_hash,
        )
    except ProspectiveSpyIntradaySessionInputError:
        return _not_yet_observed(
            session_date=session_date,
            observed_at=observed,
            cutoff=cutoff,
            reason="cutoff_coverage_incomplete",
        )

    receipt = observe_prospective_spy_intraday_baseline(record).receipt
    destination = _receipt_destination(
        artifact_root=Path(artifact_root),
        repo_root=repository,
        session_date=session_date,
    )
    _write_or_verify(destination, (receipt.canonical_json() + "\n").encode("utf-8"))
    return KisPaperProspectiveSpyCaptureResult(
        status="captured",
        session_date=session_date,
        observed_at=observed,
        cutoff=cutoff,
        reason=None,
        receipt=receipt,
        artifact_path=destination,
    )


def _not_yet_observed(
    *,
    session_date: date,
    observed_at: datetime,
    cutoff: datetime | None,
    reason: str,
) -> KisPaperProspectiveSpyCaptureResult:
    return KisPaperProspectiveSpyCaptureResult(
        status="not_yet_observed",
        session_date=session_date,
        observed_at=observed_at,
        cutoff=cutoff,
        reason=reason,
        receipt=None,
        artifact_path=None,
    )


def _decision_cutoff(session_date: date) -> datetime:
    return datetime.combine(session_date, _DECISION_TIME, _EASTERN).astimezone(UTC)


def _source_contract_hash(
    *,
    catalog_dataset_id: str,
    selected_bar_content_sha256: str,
    session_date: date,
    session_open_ts: datetime,
    session_close_ts: datetime,
    cutoff: datetime,
) -> str:
    return "sha256:" + _sha256_json(
        {
            "kind": "kis-paper-prospective-spy-source-contract-v1",
            "target": KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_TARGET,
            "catalog_dataset_id": catalog_dataset_id,
            "selected_bar_content_sha256": selected_bar_content_sha256,
            "session_date": session_date.isoformat(),
            "session_open_ts": _utc_marker(session_open_ts),
            "session_close_ts": _utc_marker(session_close_ts),
            "cutoff": _utc_marker(cutoff),
        }
    )


def _selected_bar_content_sha256(source_bars: tuple[Bar, ...]) -> str:
    """Bind the full decision-session source without a mutable whole-cache hash."""

    payload = {
        "kind": "kis-paper-prospective-spy-selected-source-bars-v1",
        "bars": [
            {
                "symbol": bar.symbol,
                "market": bar.market,
                "timeframe": bar.timeframe.value,
                "start_ts": _utc_marker(bar.start_ts),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "complete": bar.complete,
            }
            for bar in source_bars
        ],
    }
    return "sha256:" + _sha256_json(payload)


def _receipt_destination(
    *,
    artifact_root: Path,
    repo_root: Path,
    session_date: date,
) -> Path:
    root = _external_artifact_root(artifact_root, repo_root)
    capture_root = root / KIS_PAPER_PROSPECTIVE_SPY_CAPTURE_ARTIFACT_DIR
    session_root = capture_root / session_date.isoformat()
    _ensure_real_directory(capture_root)
    _ensure_real_directory(session_root)
    destination = session_root / "receipt.json"
    if destination.exists() and destination.is_symlink():
        raise ValueError("prospective SPY receipt destination is invalid")
    resolved_destination = destination.resolve(strict=False)
    if not resolved_destination.is_relative_to(root):
        raise ValueError("prospective SPY receipt destination is invalid")
    return destination


def _external_artifact_root(artifact_root: Path, repo_root: Path) -> Path:
    root = artifact_root.resolve(strict=False)
    repository = repo_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    mounted_artifacts = repository == docker_repository and root.is_relative_to(docker_artifacts)
    if root.is_relative_to(repository) and not mounted_artifacts:
        raise ValueError("prospective SPY artifact root must stay outside Git")
    if root.exists() and root.is_symlink():
        raise ValueError("prospective SPY artifact root is invalid")
    _ensure_real_directory(root)
    return root.resolve(strict=False)


def _ensure_real_directory(path: Path) -> None:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("prospective SPY artifact directory is invalid")
    path.mkdir(parents=True, exist_ok=True)


def _write_or_verify(destination: Path, encoded: bytes) -> None:
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("prospective SPY receipt identity conflicts with existing evidence")
        return
    staging = destination.with_name(
        f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.stage"
    )
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def _sha256_json(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")
