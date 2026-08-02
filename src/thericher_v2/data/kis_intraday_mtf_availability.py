"""Offline availability receipt for causal KIS intraday multi-timeframe inputs.

This leaf reads already verified KIS Paper minute catalogs only.  It keeps raw
bars in memory, writes source-safe aggregate evidence outside Git, and has no
provider, credential, broker, model, target, or GPU behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

from .kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog

KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID = "kis-intraday-mtf-availability-receipt-v1"
KIS_INTRADAY_MTF_AVAILABILITY_ARTIFACT_DIRECTORY = (
    "kis-intraday-mtf-availability-receipt-v1"
)
KIS_INTRADAY_MTF_AVAILABILITY_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
KIS_INTRADAY_MTF_AVAILABILITY_CUTOFF = time(15, 30)
KIS_INTRADAY_MTF_AVAILABILITY_LOOKBACKS = (
    (Timeframe.M1, 30),
    (Timeframe.M5, 6),
    (Timeframe.M10, 3),
    (Timeframe.H1, 2),
    (Timeframe.H3, 2),
)
KIS_INTRADAY_MTF_AVAILABILITY_PREFIX_MINUTES = 360

_EASTERN = ZoneInfo("America/New_York")
_SHA256_PREFIX = "sha256:"
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}/1m"
    for symbol, exchange in KIS_INTRADAY_MTF_AVAILABILITY_TARGETS
)


AvailabilityStatus = Literal[
    "qualified_for_prospective_input",
    "input_unavailable",
]


@dataclass(frozen=True, slots=True)
class KisIntradayMtfSourceIdentity:
    """One verified local KIS catalog identity without a path or source rows."""

    target_key: str
    dataset_id: str
    dataset_hash: str

    def __post_init__(self) -> None:
        if (
            self.target_key not in _TARGET_KEYS
            or not self.dataset_id
            or not _is_sha256(self.dataset_hash)
        ):
            raise ValueError("KIS intraday MTF source identity is invalid")

    def safe_payload(self) -> dict[str, str]:
        return {
            "target_key": self.target_key,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
        }


@dataclass(frozen=True, slots=True)
class KisIntradayMtfAvailabilityContract:
    """Immutable source identities and geometry before any availability result."""

    source_identities: tuple[KisIntradayMtfSourceIdentity, ...]
    code_revision: str
    contract_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        sources = tuple(self.source_identities)
        object.__setattr__(self, "source_identities", sources)
        if (
            len(sources) != len(_TARGET_KEYS)
            or tuple(source.target_key for source in sources) != _TARGET_KEYS
            or not _is_sha256(self.code_revision)
            or not _is_sha256(self.contract_sha256)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS intraday MTF availability contract is invalid")
        if self.contract_sha256 != _contract_sha256(
            source_identities=sources,
            code_revision=self.code_revision,
        ):
            raise ValueError("KIS intraday MTF availability contract hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
            "source": {
                "provider": "KIS Open API virtual paper local cache",
                "targets": [source.safe_payload() for source in self.source_identities],
                "source_mix": "none",
            },
            "geometry": _geometry_payload(),
            "code_revision": self.code_revision,
            "contract_sha256": self.contract_sha256,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class KisIntradayMtfTargetAvailability:
    """Aggregate per-target input availability; eligible dates stay in memory."""

    source: KisIntradayMtfSourceIdentity
    regular_session_count: int
    cutoff_prefix_complete_count: int
    available_session_counts: tuple[tuple[Timeframe, int], ...]
    all_timeframes_available_count: int
    _eligible_session_dates: tuple[date, ...] = field(repr=False)

    def __post_init__(self) -> None:
        available = tuple(self.available_session_counts)
        eligible_dates = tuple(self._eligible_session_dates)
        object.__setattr__(self, "available_session_counts", available)
        object.__setattr__(self, "_eligible_session_dates", eligible_dates)
        expected_timeframes = tuple(
            timeframe for timeframe, _ in KIS_INTRADAY_MTF_AVAILABILITY_LOOKBACKS
        )
        if (
            tuple(timeframe for timeframe, _ in available) != expected_timeframes
            or self.regular_session_count < 0
            or self.cutoff_prefix_complete_count < 0
            or self.all_timeframes_available_count < 0
            or self.cutoff_prefix_complete_count > self.regular_session_count
            or self.all_timeframes_available_count != len(eligible_dates)
            or tuple(sorted(eligible_dates)) != eligible_dates
            or len(set(eligible_dates)) != len(eligible_dates)
            or any(count < 0 or count > self.cutoff_prefix_complete_count for _, count in available)
            or self.all_timeframes_available_count
            > min((count for _, count in available), default=0)
        ):
            raise ValueError("KIS intraday MTF target availability is invalid")

    @property
    def eligible_session_dates(self) -> frozenset[date]:
        """Expose dates only to the in-memory aligner, never to the receipt."""

        return frozenset(self._eligible_session_dates)

    def safe_payload(self) -> dict[str, object]:
        return {
            "source": self.source.safe_payload(),
            "regular_session_count": self.regular_session_count,
            "cutoff_prefix_complete_count": self.cutoff_prefix_complete_count,
            "available_session_counts": {
                timeframe.value: count for timeframe, count in self.available_session_counts
            },
            "all_timeframes_available_count": self.all_timeframes_available_count,
        }


@dataclass(frozen=True, slots=True)
class KisIntradayMtfAvailabilityReceipt:
    """Source-safe terminal result of one frozen local-cache materialization."""

    contract_sha256: str
    status: AvailabilityStatus
    reason: str | None
    targets: tuple[KisIntradayMtfTargetAvailability, ...]
    common_aligned_session_count: int
    receipt_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        targets = tuple(self.targets)
        object.__setattr__(self, "targets", targets)
        if (
            not _is_sha256(self.contract_sha256)
            or self.status not in {"qualified_for_prospective_input", "input_unavailable"}
            or tuple(target.source.target_key for target in targets) != _TARGET_KEYS
            or self.common_aligned_session_count < 0
            or not _is_sha256(self.receipt_sha256)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS intraday MTF availability receipt is invalid")
        expected_reason = (
            None
            if self.common_aligned_session_count
            else "insufficient_contiguous_intraday_session_coverage"
        )
        expected_status: AvailabilityStatus = (
            "qualified_for_prospective_input"
            if self.common_aligned_session_count
            else "input_unavailable"
        )
        if self.status != expected_status or self.reason != expected_reason:
            raise ValueError("KIS intraday MTF availability terminal category is invalid")
        if self.common_aligned_session_count > min(
            target.all_timeframes_available_count for target in targets
        ):
            raise ValueError("KIS intraday MTF aligned count is invalid")
        expected_hash = _receipt_sha256(
            contract_sha256=self.contract_sha256,
            status=self.status,
            reason=self.reason,
            targets=targets,
            common_aligned_session_count=self.common_aligned_session_count,
        )
        if self.receipt_sha256 != expected_hash:
            raise ValueError("KIS intraday MTF availability receipt hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
            "contract_sha256": self.contract_sha256,
            "status": self.status,
            "reason": self.reason,
            "targets": [target.safe_payload() for target in self.targets],
            "common_aligned_session_count": self.common_aligned_session_count,
            "receipt_sha256": self.receipt_sha256,
            "scope": {
                "prospective_input_only": True,
                "model_or_strategy_result": False,
                "target_or_return_opened": False,
                "pnl_calculated": False,
                "paper_or_broker_action": False,
                "gpu_used": False,
                "raw_market_data_written": False,
                "raw_market_data_persisted": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisIntradayMtfAvailabilityRun:
    """External precommit and receipt paths for one immutable run label."""

    contract: KisIntradayMtfAvailabilityContract
    receipt: KisIntradayMtfAvailabilityReceipt
    run_directory: Path
    precommit_path: Path
    precommit_sha256: str
    summary_path: Path
    summary_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.precommit_sha256)
            or not _is_sha256(self.summary_sha256)
            or self.precommit_path.parent != self.run_directory
            or self.summary_path.parent != self.run_directory
            or self.precommit_path.name != "precommit.json"
            or self.summary_path.name != "summary.json"
        ):
            raise ValueError("KIS intraday MTF availability run is invalid")


def load_kis_intraday_mtf_availability_catalogs(
    *,
    cache_root: Path | str,
    repo_root: Path | str,
) -> dict[str, CatalogedBars]:
    """Load exactly the two verified KIS-native minute streams with no I/O route."""

    root = Path(cache_root)
    repository = Path(repo_root)
    return {
        _target_key(symbol, exchange): load_verified_kis_paper_private_intraday_catalog(
            cache_root=root,
            repo_root=repository,
            symbol=symbol,
            exchange=exchange,
        )
        for symbol, exchange in KIS_INTRADAY_MTF_AVAILABILITY_TARGETS
    }


def freeze_kis_intraday_mtf_availability_contract(
    catalogs: Mapping[str, CatalogedBars],
    *,
    code_revision: str,
) -> KisIntradayMtfAvailabilityContract:
    """Freeze verified source identities and geometry before availability inspection."""

    _require_sha256(code_revision, "code_revision")
    identities = tuple(
        _source_identity(target_key=target_key, catalog=_catalog_for_target(catalogs, target_key))
        for target_key in _TARGET_KEYS
    )
    return KisIntradayMtfAvailabilityContract(
        source_identities=identities,
        code_revision=code_revision,
        contract_sha256=_contract_sha256(
            source_identities=identities,
            code_revision=code_revision,
        ),
    )


def materialize_kis_intraday_mtf_availability(
    contract: KisIntradayMtfAvailabilityContract,
    catalogs: Mapping[str, CatalogedBars],
) -> KisIntradayMtfAvailabilityReceipt:
    """Build aggregate causal availability from the exact frozen local catalogs."""

    if not isinstance(contract, KisIntradayMtfAvailabilityContract):
        raise TypeError("KIS intraday MTF contract is invalid")
    targets = tuple(
        _materialize_target(
            source=source,
            catalog=_catalog_for_frozen_source(catalogs, source),
        )
        for source in contract.source_identities
    )
    common_dates = set(targets[0].eligible_session_dates)
    for target in targets[1:]:
        common_dates.intersection_update(target.eligible_session_dates)
    common_count = len(common_dates)
    status: AvailabilityStatus = (
        "qualified_for_prospective_input" if common_count else "input_unavailable"
    )
    reason = None if common_count else "insufficient_contiguous_intraday_session_coverage"
    return KisIntradayMtfAvailabilityReceipt(
        contract_sha256=contract.contract_sha256,
        status=status,
        reason=reason,
        targets=targets,
        common_aligned_session_count=common_count,
        receipt_sha256=_receipt_sha256(
            contract_sha256=contract.contract_sha256,
            status=status,
            reason=reason,
            targets=targets,
            common_aligned_session_count=common_count,
        ),
    )


def run_kis_intraday_mtf_availability_receipt(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    repo_root: Path | str,
    run_label: str,
    code_revision: str,
    expected_dataset_hashes: Mapping[str, str] | None = None,
) -> KisIntradayMtfAvailabilityRun:
    """Freeze and materialize one external, idempotent availability receipt."""

    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("KIS intraday MTF run label is invalid")
    catalogs = load_kis_intraday_mtf_availability_catalogs(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    _require_expected_dataset_hashes(catalogs, expected_dataset_hashes)
    contract = freeze_kis_intraday_mtf_availability_contract(
        catalogs,
        code_revision=code_revision,
    )
    run_directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "data",
        KIS_INTRADAY_MTF_AVAILABILITY_ARTIFACT_DIRECTORY,
        run_label,
    )
    precommit_path, precommit_sha256 = _write_immutable_json(
        run_directory,
        "precommit.json",
        contract.safe_payload(),
    )
    receipt = materialize_kis_intraday_mtf_availability(contract, catalogs)
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
        "precommit_sha256": precommit_sha256,
        "receipt": receipt.safe_payload(),
    }
    summary_path, summary_sha256 = _write_immutable_json(
        run_directory,
        "summary.json",
        summary_payload,
    )
    return KisIntradayMtfAvailabilityRun(
        contract=contract,
        receipt=receipt,
        run_directory=run_directory,
        precommit_path=precommit_path,
        precommit_sha256=precommit_sha256,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
    )


def _source_identity(*, target_key: str, catalog: CatalogedBars) -> KisIntradayMtfSourceIdentity:
    symbol, exchange, _ = target_key.split("/")
    expected_dataset_id = (
        f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1"
    )
    if catalog.dataset_id != expected_dataset_id:
        raise ValueError("KIS intraday MTF catalog identity is invalid")
    return KisIntradayMtfSourceIdentity(
        target_key=target_key,
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
    )


def _catalog_for_target(catalogs: Mapping[str, CatalogedBars], target_key: str) -> CatalogedBars:
    if not isinstance(catalogs, Mapping) or set(catalogs) != set(_TARGET_KEYS):
        raise ValueError("KIS intraday MTF catalogs are invalid")
    catalog = catalogs[target_key]
    if not isinstance(catalog, CatalogedBars):
        raise TypeError("KIS intraday MTF catalog is invalid")
    return catalog


def _catalog_for_frozen_source(
    catalogs: Mapping[str, CatalogedBars],
    source: KisIntradayMtfSourceIdentity,
) -> CatalogedBars:
    catalog = _catalog_for_target(catalogs, source.target_key)
    observed = _source_identity(target_key=source.target_key, catalog=catalog)
    if observed != source:
        raise ValueError("KIS intraday MTF source identity changed")
    return catalog


def _materialize_target(
    *,
    source: KisIntradayMtfSourceIdentity,
    catalog: CatalogedBars,
) -> KisIntradayMtfTargetAvailability:
    session_dates = sorted(
        {
            bar.start_ts.astimezone(_EASTERN).date()
            for bar in catalog.bars
        }
    )
    regular_session_count = 0
    prefix_complete_count = 0
    available_counts = {timeframe: 0 for timeframe, _ in KIS_INTRADAY_MTF_AVAILABILITY_LOOKBACKS}
    eligible_dates: list[date] = []
    for session_date in session_dates:
        try:
            session = us_equity_2026_session(session_date)
        except ValueError:
            # The receipt's calendar contract is deliberately limited to the
            # current 2026 cache scope. An added out-of-scope row cannot turn
            # into an unqualified session or invalidate the known scope.
            continue
        if session is None or session.kind != "regular":
            continue
        regular_session_count += 1
        cutoff = _session_cutoff(session.window)
        prefix = _complete_causal_prefix(
            catalog.bars,
            expected_symbol=source.target_key.split("/", maxsplit=1)[0],
            session=session.window,
            cutoff=cutoff,
        )
        if prefix is None:
            continue
        prefix_complete_count += 1
        available = _available_timeframes(prefix, session=session.window, cutoff=cutoff)
        for timeframe, is_available in available.items():
            available_counts[timeframe] += int(is_available)
        if all(available.values()):
            eligible_dates.append(session_date)
    return KisIntradayMtfTargetAvailability(
        source=source,
        regular_session_count=regular_session_count,
        cutoff_prefix_complete_count=prefix_complete_count,
        available_session_counts=tuple(
            (timeframe, available_counts[timeframe])
            for timeframe, _ in KIS_INTRADAY_MTF_AVAILABILITY_LOOKBACKS
        ),
        all_timeframes_available_count=len(eligible_dates),
        _eligible_session_dates=tuple(eligible_dates),
    )


def _complete_causal_prefix(
    bars: Sequence[Bar],
    *,
    expected_symbol: str,
    session: SessionWindow,
    cutoff: datetime,
) -> tuple[Bar, ...] | None:
    source = tuple(
        bar
        for bar in bars
        if session.open_ts <= bar.start_ts < cutoff
    )
    if not source:
        return None
    expected_starts = tuple(
        session.open_ts + timedelta(minutes=offset)
        for offset in range(KIS_INTRADAY_MTF_AVAILABILITY_PREFIX_MINUTES)
    )
    starts = tuple(bar.start_ts for bar in source)
    if (
        len(source) != len(expected_starts)
        or len(set(starts)) != len(starts)
        or set(starts) != set(expected_starts)
        or any(
            bar.timeframe != Timeframe.M1
            or not bar.complete
            or bar.end_ts > cutoff
            or bar.symbol != expected_symbol
            or bar.market != "US"
            for bar in source
        )
    ):
        return None
    return tuple(sorted(source, key=lambda bar: bar.start_ts))


def _available_timeframes(
    prefix: tuple[Bar, ...],
    *,
    session: SessionWindow,
    cutoff: datetime,
) -> dict[Timeframe, bool]:
    availability: dict[Timeframe, bool] = {}
    for timeframe, lookback in KIS_INTRADAY_MTF_AVAILABILITY_LOOKBACKS:
        resampled = resample_session_bars(prefix, timeframe, session=session)
        before_cutoff_skips = tuple(
            timestamp
            for timestamp in resampled.skipped_bucket_starts
            if timestamp < cutoff
        )
        completed = tuple(bar for bar in resampled.bars if bar.end_ts <= cutoff)
        tail = completed[-lookback:]
        availability[timeframe] = (
            not before_cutoff_skips
            and len(tail) == lookback
            and tail[-1].end_ts == cutoff
            and all(bar.complete and bar.timeframe == timeframe for bar in tail)
        )
    return availability


def _session_cutoff(session: SessionWindow) -> datetime:
    local_open = session.open_ts.astimezone(_EASTERN)
    return local_open.replace(
        hour=KIS_INTRADAY_MTF_AVAILABILITY_CUTOFF.hour,
        minute=KIS_INTRADAY_MTF_AVAILABILITY_CUTOFF.minute,
        second=0,
        microsecond=0,
    ).astimezone(session.open_ts.tzinfo)


def _contract_sha256(
    *,
    source_identities: Sequence[KisIntradayMtfSourceIdentity],
    code_revision: str,
) -> str:
    return _sha256(
        {
            "receipt_id": KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
            "sources": [source.safe_payload() for source in source_identities],
            "geometry": _geometry_payload(),
            "code_revision": code_revision,
        }
    )


def _receipt_sha256(
    *,
    contract_sha256: str,
    status: AvailabilityStatus,
    reason: str | None,
    targets: Sequence[KisIntradayMtfTargetAvailability],
    common_aligned_session_count: int,
) -> str:
    return _sha256(
        {
            "receipt_id": KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
            "contract_sha256": contract_sha256,
            "status": status,
            "reason": reason,
            "targets": [target.safe_payload() for target in targets],
            "common_aligned_session_count": common_aligned_session_count,
        }
    )


def _geometry_payload() -> dict[str, object]:
    return {
        "session": "weekday_regular_0930_1600_america_new_york",
        "decision_cutoff": "15:30 America/New_York",
        "source_timeframe": Timeframe.M1.value,
        "causal_prefix_minute_count": KIS_INTRADAY_MTF_AVAILABILITY_PREFIX_MINUTES,
        "tail_lookbacks": {
            timeframe.value: lookback
            for timeframe, lookback in KIS_INTRADAY_MTF_AVAILABILITY_LOOKBACKS
        },
    }


def _require_expected_dataset_hashes(
    catalogs: Mapping[str, CatalogedBars],
    expected_dataset_hashes: Mapping[str, str] | None,
) -> None:
    if expected_dataset_hashes is None:
        return
    if set(expected_dataset_hashes) != set(_TARGET_KEYS):
        raise ValueError("KIS intraday MTF expected source identities are invalid")
    for target_key in _TARGET_KEYS:
        expected_hash = expected_dataset_hashes[target_key]
        _require_sha256(expected_hash, "expected_dataset_hash")
        if _catalog_for_target(catalogs, target_key).dataset_hash != expected_hash:
            raise ValueError("KIS intraday MTF expected source identity changed")


def _write_immutable_json(
    directory: Path,
    filename: Literal["precommit.json", "summary.json"],
    payload: Mapping[str, object],
) -> tuple[Path, str]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("KIS intraday MTF artifact directory is invalid")
    destination = directory / filename
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("KIS intraday MTF artifact destination is invalid")
    encoded = _canonical_json(payload)
    digest = _sha256_bytes(encoded)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("KIS intraday MTF immutable artifact conflicts")
        return destination, digest
    staging = directory / f".{filename}.{uuid.uuid4().hex}.stage"
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination, digest


def _target_key(symbol: str, exchange: str) -> str:
    return f"{symbol}/{exchange}/1m"


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    return encoded.encode("utf-8")


def _sha256(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(_canonical_json(payload))


def _sha256_bytes(payload: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(_SHA256_PREFIX)
        and len(value) == len(_SHA256_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )
