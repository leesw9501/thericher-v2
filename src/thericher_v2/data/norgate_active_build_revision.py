"""Compare one active Norgate build with the immutable fixed-trio D1 source.

The probe is deliberately target-free.  It reattests the frozen SPY/QQQ/IWM
raw-D1 development source, reads the same bounded raw-D1 window through the
optional Windows Norgate host adapter, and persists only aggregate evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_d1_diagnostic_source import (
    VerifiedNorgateD1Panel,
    load_verified_norgate_d1_diagnostic_panel,
)
from thericher_v2.data.norgate_daily import (
    NorgateClientUnavailableError,
    NorgateLocalUpdaterUnavailableError,
    NorgateMalformedResponseError,
    NorgateRawDailyBarProvider,
    NorgateUnavailableError,
)
from thericher_v2.data.norgate_trial_raw_d1 import (
    DEFAULT_MARKET_DATA_ROOT,
    FIXED_NORGATE_TRIAL_SYMBOLS,
)
from thericher_v2.data.provider import BarQuery

NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID = "norgate-active-build-revision-probe-v1"
DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/norgate-active-build-revision-v1"
)
FROZEN_NORGATE_FIXED_TRIO_D1_SNAPSHOT_DIR = (
    Path("D:/market_data/us_equities/norgate_trial/local_d1_etf")
    / "snapshot=local-d1-20260802-r3-norgate-trial-raw-d1-r2"
)
FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH = (
    "sha256:efa1b14ff60c6a107688179617d428546de68ca1d1756c62292e1206e15c58e7"
)
FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH = (
    "sha256:7f30253d035f248889849b7a9a5933cdc41b2f2525b405690ef653ca69a33d45"
)

_RECEIPT_FILE = "receipt.json"
_SAFE_RUN_LABEL = re.compile(r"[a-z0-9][a-z0-9-]{0,79}", re.ASCII)
_STATUSES = {"matching", "revision_detected", "input_unavailable"}
_INPUT_UNAVAILABLE_REASONS = {
    "active_client_unavailable",
    "active_local_source_unavailable",
    "active_reader_nonrepeatable",
    "active_response_malformed",
    "active_source_unavailable",
}


class NorgateActiveBuildRevisionError(RuntimeError):
    """Raised when a bounded active-build revision probe cannot be completed."""


class _ActiveReaderNonrepeatable(NorgateActiveBuildRevisionError):
    """Raised when two identical active-reader requests disagree."""


class _DailyBarProvider(Protocol):
    def get_bars(self, query: BarQuery) -> list[Bar]:
        """Return source-local D1 bars for one bounded query."""


FixedPanelLoader = Callable[..., VerifiedNorgateD1Panel]


@dataclass(frozen=True, slots=True)
class NorgateActiveBuildRevisionEvidence:
    """Aggregate comparison evidence for one fixed reference symbol."""

    symbol: str
    reference_bar_count: int
    active_bar_count: int
    divergent_bar_count: int

    def __post_init__(self) -> None:
        if (
            self.symbol not in FIXED_NORGATE_TRIAL_SYMBOLS
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (
                    self.reference_bar_count,
                    self.active_bar_count,
                    self.divergent_bar_count,
                )
            )
            or self.divergent_bar_count
            > max(self.reference_bar_count, self.active_bar_count)
        ):
            raise ValueError("Norgate active-build revision evidence is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "reference_bar_count": self.reference_bar_count,
            "active_bar_count": self.active_bar_count,
            "divergent_bar_count": self.divergent_bar_count,
        }


@dataclass(frozen=True, slots=True)
class NorgateActiveBuildRevisionResult:
    """A source-safe handle for one immutable external probe receipt."""

    receipt_dir: Path
    receipt_sha256: str
    status: str
    reason: str
    reference_dataset_hash: str
    reference_manifest_hash: str
    active_response_hash: str | None
    reference_bar_count: int
    active_bar_count: int
    divergent_bar_count: int
    evidence: tuple[NorgateActiveBuildRevisionEvidence, ...]

    def __post_init__(self) -> None:
        if (
            self.status not in _STATUSES
            or not _is_sha256(self.receipt_sha256)
            or not _is_sha256(self.reference_dataset_hash)
            or not _is_sha256(self.reference_manifest_hash)
            or (
                self.active_response_hash is not None
                and not _is_sha256(self.active_response_hash)
            )
            or (self.status == "input_unavailable" and self.active_response_hash is not None)
            or (self.status != "input_unavailable" and self.active_response_hash is None)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (
                    self.reference_bar_count,
                    self.active_bar_count,
                    self.divergent_bar_count,
                )
            )
            or self.divergent_bar_count
            > max(self.reference_bar_count, self.active_bar_count)
            or (self.status == "input_unavailable" and self.evidence)
            or (
                self.status != "input_unavailable"
                and tuple(item.symbol for item in self.evidence) != FIXED_NORGATE_TRIAL_SYMBOLS
            )
        ):
            raise ValueError("Norgate active-build revision result is invalid")
        try:
            _validate_outcome(
                status=self.status,
                reason=self.reason,
                compared_symbol_count=len(self.evidence),
                reference_bar_count=self.reference_bar_count,
                active_bar_count=self.active_bar_count,
                divergent_bar_count=self.divergent_bar_count,
                active_response_hash=self.active_response_hash,
                evidence=self.evidence,
            )
        except NorgateActiveBuildRevisionError as exc:
            raise ValueError("Norgate active-build revision result is invalid") from exc

    def safe_payload(self) -> dict[str, object]:
        """Return the result without source paths, dates, bars, or credentials."""

        return {
            "probe_id": NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID,
            "receipt_sha256": self.receipt_sha256,
            "status": self.status,
            "reason": self.reason,
            "reference_dataset_hash": self.reference_dataset_hash,
            "reference_manifest_hash": self.reference_manifest_hash,
            "active_response_sha256": self.active_response_hash,
            "reference_bar_count": self.reference_bar_count,
            "active_bar_count": self.active_bar_count,
            "divergent_bar_count": self.divergent_bar_count,
            "per_symbol": [item.safe_payload() for item in self.evidence],
        }


def build_norgate_active_build_revision_receipt(
    *,
    destination: Path,
    artifact_root: Path = DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT,
    repo_root: Path | None = None,
    active_provider: _DailyBarProvider | None = None,
    fixed_panel_loader: FixedPanelLoader = load_verified_norgate_d1_diagnostic_panel,
) -> NorgateActiveBuildRevisionResult:
    """Compare the active host build to the fixed raw-D1 development contract.

    The only default provider is the optional Windows host reader.  No rows,
    timestamps, paths, or exception text are retained in the receipt.
    """

    root, target = _validate_new_destination(
        destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    panel = fixed_panel_loader(
        FROZEN_NORGATE_FIXED_TRIO_D1_SNAPSHOT_DIR,
        expected_dataset_hash=FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
        expected_manifest_hash=FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
        market_data_root=DEFAULT_MARKET_DATA_ROOT,
        repo_root=repo_root,
    )
    reference = _validate_fixed_reference_panel(panel)
    provider = active_provider or NorgateRawDailyBarProvider()
    reference_bar_count = sum(len(reference[symbol]) for symbol in FIXED_NORGATE_TRIAL_SYMBOLS)

    try:
        evidence, active_response_hash = _compare_active_build(reference, provider)
    except _ActiveReaderNonrepeatable:
        status, reason, evidence, active_response_hash = (
            "input_unavailable",
            "active_reader_nonrepeatable",
            (),
            None,
        )
    except NorgateMalformedResponseError:
        status, reason, evidence, active_response_hash = (
            "input_unavailable",
            "active_response_malformed",
            (),
            None,
        )
    except NorgateClientUnavailableError:
        status, reason, evidence, active_response_hash = (
            "input_unavailable",
            "active_client_unavailable",
            (),
            None,
        )
    except NorgateLocalUpdaterUnavailableError:
        status, reason, evidence, active_response_hash = (
            "input_unavailable",
            "active_local_source_unavailable",
            (),
            None,
        )
    except NorgateUnavailableError:
        status, reason, evidence, active_response_hash = (
            "input_unavailable",
            "active_source_unavailable",
            (),
            None,
        )
    except NorgateActiveBuildRevisionError:
        status, reason, evidence, active_response_hash = (
            "input_unavailable",
            "active_response_malformed",
            (),
            None,
        )
    else:
        divergent_bar_count = sum(item.divergent_bar_count for item in evidence)
        status = "matching" if divergent_bar_count == 0 else "revision_detected"
        reason = (
            "active_build_matches_frozen_contract"
            if status == "matching"
            else "bar_level_divergence_detected"
        )

    active_bar_count = sum(item.active_bar_count for item in evidence)
    divergent_bar_count = sum(item.divergent_bar_count for item in evidence)
    receipt = _receipt_document(
        status=status,
        reason=reason,
        reference_bar_count=reference_bar_count,
        active_bar_count=active_bar_count,
        divergent_bar_count=divergent_bar_count,
        active_response_hash=active_response_hash,
        evidence=evidence,
    )
    _write_receipt(target, _json_bytes(receipt), root=root)
    return verify_norgate_active_build_revision_receipt(
        target,
        artifact_root=root,
        repo_root=repo_root,
    )


def verify_norgate_active_build_revision_receipt(
    receipt_dir: Path,
    *,
    artifact_root: Path = DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT,
    repo_root: Path | None = None,
) -> NorgateActiveBuildRevisionResult:
    """Reattach a source-safe receipt without loading Norgate or raw bars."""

    root, directory = _validate_existing_receipt_dir(
        receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    if {entry.name for entry in directory.iterdir()} != {_RECEIPT_FILE}:
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt files are invalid")
    contents = _read_regular_file(directory / _RECEIPT_FILE)
    return _result_from_document(
        directory,
        _json_object(contents),
        receipt_sha256=_sha256(contents),
        artifact_root=root,
    )


def _validate_fixed_reference_panel(panel: VerifiedNorgateD1Panel) -> dict[str, tuple[Bar, ...]]:
    if not isinstance(panel, VerifiedNorgateD1Panel):
        raise NorgateActiveBuildRevisionError("Norgate fixed reference panel is invalid")
    source = panel.source_result
    if (
        source.dataset_hash != FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH
        or source.manifest_hash != FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH
        or source.row_count <= 0
        or source.common_session_count <= 0
        or len(panel.common_sessions) != source.common_session_count
    ):
        raise NorgateActiveBuildRevisionError("Norgate fixed reference identity is invalid")

    reference: dict[str, tuple[Bar, ...]] = {}
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        bars = tuple(panel.bars_by_symbol.get(symbol, ()))
        _validate_series(bars, symbol=symbol)
        if tuple(bar.start_ts.date() for bar in bars) != panel.common_sessions:
            raise NorgateActiveBuildRevisionError("Norgate fixed reference geometry is invalid")
        reference[symbol] = bars
    if sum(len(reference[symbol]) for symbol in FIXED_NORGATE_TRIAL_SYMBOLS) != source.row_count:
        raise NorgateActiveBuildRevisionError("Norgate fixed reference row count is invalid")
    return reference


def _compare_active_build(
    reference: Mapping[str, tuple[Bar, ...]],
    provider: _DailyBarProvider,
) -> tuple[tuple[NorgateActiveBuildRevisionEvidence, ...], str]:
    active_by_symbol = _read_stable_active_responses(reference, provider)
    evidence: list[NorgateActiveBuildRevisionEvidence] = []
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        reference_bars = reference[symbol]
        active_bars = active_by_symbol[symbol]
        evidence.append(
            NorgateActiveBuildRevisionEvidence(
                symbol=symbol,
                reference_bar_count=len(reference_bars),
                active_bar_count=len(active_bars),
                divergent_bar_count=_divergent_bar_count(reference_bars, active_bars),
            )
        )
    return tuple(evidence), _active_response_hash(active_by_symbol)


def _read_stable_active_responses(
    reference: Mapping[str, tuple[Bar, ...]],
    provider: _DailyBarProvider,
) -> dict[str, tuple[Bar, ...]]:
    active_by_symbol: dict[str, tuple[Bar, ...]] = {}
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        reference_bars = reference[symbol]
        query = BarQuery(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=reference_bars[0].start_ts,
            end_ts=reference_bars[-1].start_ts + Timeframe.D1.duration,
        )
        first = tuple(provider.get_bars(query))
        _validate_series(
            first,
            symbol=symbol,
            start=query.start_ts,
            end=query.end_ts,
            allow_empty=True,
        )
        second = tuple(provider.get_bars(query))
        _validate_series(
            second,
            symbol=symbol,
            start=query.start_ts,
            end=query.end_ts,
            allow_empty=True,
        )
        if first != second:
            raise _ActiveReaderNonrepeatable("Norgate active reader is nonrepeatable")
        active_by_symbol[symbol] = first
    return active_by_symbol


def _validate_series(
    bars: Sequence[Bar],
    *,
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    allow_empty: bool = False,
) -> None:
    if not bars and not allow_empty:
        raise NorgateActiveBuildRevisionError("Norgate active D1 response is malformed")
    previous: datetime | None = None
    for bar in bars:
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo is None
            or bar.start_ts.utcoffset() != UTC.utcoffset(bar.start_ts)
            or bar.start_ts.time() != datetime.min.time()
            or (start is not None and bar.start_ts < start)
            or (end is not None and bar.start_ts >= end)
            or (previous is not None and bar.start_ts <= previous)
        ):
            raise NorgateActiveBuildRevisionError("Norgate active D1 response is malformed")
        previous = bar.start_ts


def _divergent_bar_count(reference: Sequence[Bar], active: Sequence[Bar]) -> int:
    reference_by_start = {bar.start_ts: bar for bar in reference}
    active_by_start = {bar.start_ts: bar for bar in active}
    return sum(
        reference_by_start.get(start_ts) != active_by_start.get(start_ts)
        for start_ts in reference_by_start.keys() | active_by_start.keys()
    )


def _active_response_hash(active_by_symbol: Mapping[str, Sequence[Bar]]) -> str:
    payload = {
        "symbols": [
            {
                "symbol": symbol,
                "bars": [
                    [
                        bar.symbol,
                        bar.market,
                        bar.timeframe.value,
                        bar.start_ts.isoformat(),
                        _canonical_decimal(bar.open),
                        _canonical_decimal(bar.high),
                        _canonical_decimal(bar.low),
                        _canonical_decimal(bar.close),
                        _canonical_decimal(bar.volume),
                        bar.complete,
                    ]
                    for bar in active_by_symbol[symbol]
                ],
            }
            for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
        ]
    }
    return _sha256(_json_bytes(payload))


def _canonical_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _receipt_document(
    *,
    status: str,
    reason: str,
    reference_bar_count: int,
    active_bar_count: int,
    divergent_bar_count: int,
    active_response_hash: str | None,
    evidence: Sequence[NorgateActiveBuildRevisionEvidence],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "norgate_active_build_revision_receipt",
        "probe_id": NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID,
        "reference": {
            "dataset_hash": FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
            "manifest_hash": FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
            "symbols": list(FIXED_NORGATE_TRIAL_SYMBOLS),
            "timeframe": Timeframe.D1.value,
            "reference_bar_count": reference_bar_count,
        },
        "active_reader": {
            "access": "local_windows_host_only",
            "provider": "norgate_host_optional_raw_daily",
            "requested_adjustment_setting": "NONE",
            "padding_setting": "NONE",
            "active_response_sha256": active_response_hash,
        },
        "outcome": {
            "status": status,
            "reason": reason,
            "compared_symbol_count": len(evidence),
            "active_bar_count": active_bar_count,
            "divergent_bar_count": divergent_bar_count,
            "per_symbol": [item.safe_payload() for item in evidence],
        },
        "target_free_integrity": {
            "bar_level_divergence_is_categorical": True,
            "normalization_performed": False,
            "target_or_label_computed": False,
            "raw_ohlcv_persisted": False,
            "session_dates_persisted": False,
            "source_paths_persisted": False,
            "receipt_written_under_artifact_root": True,
        },
        "scope": {
            "model_training_allowed": False,
            "gpu_appointment_allowed": False,
            "paper_input_allowed": False,
            "promotion_allowed": False,
        },
    }


def _validate_new_destination(
    destination: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = _ensure_external_artifact_root(artifact_root, repo_root=repo_root)
    target = Path(destination).resolve(strict=False)
    if target.parent != root or target.name != _receipt_dir_name(target.name):
        raise NorgateActiveBuildRevisionError(
            "Norgate active-build receipt destination must stay under artifact root"
        )
    if target.exists() or target.is_symlink():
        raise FileExistsError("Norgate active-build receipt destination already exists")
    return root, target


def _validate_existing_receipt_dir(
    receipt_dir: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = _existing_external_artifact_root(artifact_root, repo_root=repo_root)
    directory = Path(receipt_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt is unavailable")
    resolved_directory = directory.resolve(strict=True)
    if (
        resolved_directory.parent != root
        or resolved_directory.name != _receipt_dir_name(resolved_directory.name)
    ):
        raise NorgateActiveBuildRevisionError(
            "Norgate active-build receipt must stay under artifact root"
        )
    return root, resolved_directory


def _ensure_external_artifact_root(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise NorgateActiveBuildRevisionError("Norgate active-build artifact root is unavailable")
    _validate_external_artifact_root(root.resolve(strict=False), repo_root=repo_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise NorgateActiveBuildRevisionError(
            "Norgate active-build artifact root is unavailable"
        ) from exc
    if root.is_symlink() or not resolved.is_dir():
        raise NorgateActiveBuildRevisionError("Norgate active-build artifact root is unavailable")
    _validate_external_artifact_root(resolved, repo_root=repo_root)
    return resolved


def _existing_external_artifact_root(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(artifact_root)
    if root.is_symlink() or not root.is_dir():
        raise NorgateActiveBuildRevisionError("Norgate active-build artifact root is unavailable")
    resolved = root.resolve(strict=True)
    _validate_external_artifact_root(resolved, repo_root=repo_root)
    return resolved


def _validate_external_artifact_root(root: Path, *, repo_root: Path | None) -> None:
    repository = _repository_root(repo_root)
    container_repository = Path("/app").resolve()
    container_artifacts = container_repository / "model_artifacts"
    is_container_mount = repository == container_repository and (
        root == container_artifacts or root.is_relative_to(container_artifacts)
    )
    if (root == repository or root.is_relative_to(repository)) and not is_container_mount:
        raise NorgateActiveBuildRevisionError(
            "Norgate active-build receipts must stay outside the Git workspace"
        )


def _repository_root(repo_root: Path | None) -> Path:
    repository = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if repository.is_symlink() or not repository.is_dir():
        raise NorgateActiveBuildRevisionError("Norgate active-build repository root is invalid")
    return repository.resolve(strict=True)


def _write_receipt(target: Path, contents: bytes, *, root: Path) -> None:
    staging = root / f".{target.name}.staging-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        (staging / _RECEIPT_FILE).write_bytes(contents)
        if staging.is_symlink() or not staging.resolve(strict=True).is_relative_to(root):
            raise NorgateActiveBuildRevisionError("Norgate active-build receipt staging is invalid")
        os.rename(staging, target)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _result_from_document(
    receipt_dir: Path,
    document: Mapping[str, object],
    *,
    receipt_sha256: str,
    artifact_root: Path,
) -> NorgateActiveBuildRevisionResult:
    expected_keys = {
        "schema_version",
        "kind",
        "probe_id",
        "reference",
        "active_reader",
        "outcome",
        "target_free_integrity",
        "scope",
    }
    if set(document) != expected_keys:
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt schema is invalid")
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "norgate_active_build_revision_receipt"
        or document.get("probe_id") != NORGATE_ACTIVE_BUILD_REVISION_PROBE_ID
    ):
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt identity is invalid")
    reference = _mapping(document.get("reference"), "reference")
    reader = _mapping(document.get("active_reader"), "active reader")
    outcome = _mapping(document.get("outcome"), "outcome")
    integrity = _mapping(document.get("target_free_integrity"), "integrity")
    scope = _mapping(document.get("scope"), "scope")
    _validate_reference_document(reference)
    active_response_hash = _validate_reader_document(reader)
    _validate_integrity_document(integrity)
    _validate_scope_document(scope)
    status = _nonempty_text(outcome.get("status"), "outcome status")
    reason = _nonempty_text(outcome.get("reason"), "outcome reason")
    if status not in _STATUSES:
        raise NorgateActiveBuildRevisionError("Norgate active-build outcome status is invalid")
    evidence = _evidence_from_document(outcome.get("per_symbol"), status=status)
    compared_symbol_count = _nonnegative_int(
        outcome.get("compared_symbol_count"), "compared symbol count"
    )
    active_bar_count = _nonnegative_int(outcome.get("active_bar_count"), "active bar count")
    divergent_bar_count = _nonnegative_int(
        outcome.get("divergent_bar_count"), "divergent bar count"
    )
    reference_bar_count = _nonnegative_int(
        reference.get("reference_bar_count"), "reference bar count"
    )
    _validate_outcome(
        status=status,
        reason=reason,
        compared_symbol_count=compared_symbol_count,
        reference_bar_count=reference_bar_count,
        active_bar_count=active_bar_count,
        divergent_bar_count=divergent_bar_count,
        active_response_hash=active_response_hash,
        evidence=evidence,
    )
    if not receipt_dir.is_relative_to(artifact_root):
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt escapes artifact root")
    return NorgateActiveBuildRevisionResult(
        receipt_dir=receipt_dir,
        receipt_sha256=receipt_sha256,
        status=status,
        reason=reason,
        reference_dataset_hash=_sha256_text(reference.get("dataset_hash"), "dataset hash"),
        reference_manifest_hash=_sha256_text(reference.get("manifest_hash"), "manifest hash"),
        active_response_hash=active_response_hash,
        reference_bar_count=reference_bar_count,
        active_bar_count=active_bar_count,
        divergent_bar_count=divergent_bar_count,
        evidence=evidence,
    )


def _validate_reference_document(reference: Mapping[str, object]) -> None:
    if set(reference) != {
        "dataset_hash",
        "manifest_hash",
        "symbols",
        "timeframe",
        "reference_bar_count",
    }:
        raise NorgateActiveBuildRevisionError("Norgate active-build reference is invalid")
    if (
        _sha256_text(reference.get("dataset_hash"), "dataset hash")
        != FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH
        or _sha256_text(reference.get("manifest_hash"), "manifest hash")
        != FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH
        or reference.get("symbols") != list(FIXED_NORGATE_TRIAL_SYMBOLS)
        or reference.get("timeframe") != Timeframe.D1.value
        or _nonnegative_int(reference.get("reference_bar_count"), "reference bar count") <= 0
    ):
        raise NorgateActiveBuildRevisionError("Norgate active-build reference is invalid")


def _validate_reader_document(reader: Mapping[str, object]) -> str | None:
    expected = {
        "access": "local_windows_host_only",
        "provider": "norgate_host_optional_raw_daily",
        "requested_adjustment_setting": "NONE",
        "padding_setting": "NONE",
    }
    if set(reader) != {*expected, "active_response_sha256"}:
        raise NorgateActiveBuildRevisionError("Norgate active-build reader is invalid")
    if {key: reader[key] for key in expected} != expected:
        raise NorgateActiveBuildRevisionError("Norgate active-build reader is invalid")
    response_hash = reader.get("active_response_sha256")
    if response_hash is None:
        return None
    return _sha256_text(response_hash, "active response hash")


def _validate_integrity_document(integrity: Mapping[str, object]) -> None:
    expected = {
        "bar_level_divergence_is_categorical": True,
        "normalization_performed": False,
        "target_or_label_computed": False,
        "raw_ohlcv_persisted": False,
        "session_dates_persisted": False,
        "source_paths_persisted": False,
        "receipt_written_under_artifact_root": True,
    }
    if dict(integrity) != expected:
        raise NorgateActiveBuildRevisionError("Norgate active-build integrity is invalid")


def _validate_scope_document(scope: Mapping[str, object]) -> None:
    expected = {
        "model_training_allowed": False,
        "gpu_appointment_allowed": False,
        "paper_input_allowed": False,
        "promotion_allowed": False,
    }
    if dict(scope) != expected:
        raise NorgateActiveBuildRevisionError("Norgate active-build scope is invalid")


def _evidence_from_document(
    value: object,
    *,
    status: str,
) -> tuple[NorgateActiveBuildRevisionEvidence, ...]:
    if not isinstance(value, list):
        raise NorgateActiveBuildRevisionError("Norgate active-build evidence is invalid")
    if status == "input_unavailable":
        if value:
            raise NorgateActiveBuildRevisionError("Norgate active-build evidence is invalid")
        return ()
    if len(value) != len(FIXED_NORGATE_TRIAL_SYMBOLS):
        raise NorgateActiveBuildRevisionError("Norgate active-build evidence is invalid")
    result: list[NorgateActiveBuildRevisionEvidence] = []
    for expected_symbol, item in zip(FIXED_NORGATE_TRIAL_SYMBOLS, value, strict=True):
        mapping = _mapping(item, "evidence item")
        if set(mapping) != {
            "symbol",
            "reference_bar_count",
            "active_bar_count",
            "divergent_bar_count",
        }:
            raise NorgateActiveBuildRevisionError("Norgate active-build evidence is invalid")
        evidence = NorgateActiveBuildRevisionEvidence(
            symbol=_nonempty_text(mapping.get("symbol"), "evidence symbol"),
            reference_bar_count=_nonnegative_int(
                mapping.get("reference_bar_count"), "evidence reference count"
            ),
            active_bar_count=_nonnegative_int(
                mapping.get("active_bar_count"), "evidence active count"
            ),
            divergent_bar_count=_nonnegative_int(
                mapping.get("divergent_bar_count"), "evidence divergence count"
            ),
        )
        if evidence.symbol != expected_symbol:
            raise NorgateActiveBuildRevisionError("Norgate active-build evidence order is invalid")
        result.append(evidence)
    return tuple(result)


def _validate_outcome(
    *,
    status: str,
    reason: str,
    compared_symbol_count: int,
    reference_bar_count: int,
    active_bar_count: int,
    divergent_bar_count: int,
    active_response_hash: str | None,
    evidence: Sequence[NorgateActiveBuildRevisionEvidence],
) -> None:
    if status == "input_unavailable":
        if (
            reason not in _INPUT_UNAVAILABLE_REASONS
            or compared_symbol_count != 0
            or active_bar_count != 0
            or divergent_bar_count != 0
            or active_response_hash is not None
            or evidence
        ):
            raise NorgateActiveBuildRevisionError("Norgate active-build outcome is invalid")
        return
    if (
        compared_symbol_count != len(FIXED_NORGATE_TRIAL_SYMBOLS)
        or sum(item.reference_bar_count for item in evidence) != reference_bar_count
        or sum(item.active_bar_count for item in evidence) != active_bar_count
        or sum(item.divergent_bar_count for item in evidence) != divergent_bar_count
        or active_response_hash is None
    ):
        raise NorgateActiveBuildRevisionError("Norgate active-build outcome is invalid")
    if status == "matching" and (
        reason != "active_build_matches_frozen_contract" or divergent_bar_count != 0
    ):
        raise NorgateActiveBuildRevisionError("Norgate active-build outcome is invalid")
    if status == "revision_detected" and (
        reason != "bar_level_divergence_detected" or divergent_bar_count <= 0
    ):
        raise NorgateActiveBuildRevisionError("Norgate active-build outcome is invalid")


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt is unavailable")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise NorgateActiveBuildRevisionError(
            "Norgate active-build receipt is unavailable"
        ) from exc


def _json_object(contents: bytes) -> dict[str, object]:
    try:
        value = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt is invalid") from exc
    if not isinstance(value, dict):
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt is invalid")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise NorgateActiveBuildRevisionError(f"Norgate active-build {label} is invalid")
    return value


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NorgateActiveBuildRevisionError(f"Norgate active-build {label} is invalid")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise NorgateActiveBuildRevisionError(f"Norgate active-build {label} is invalid")
    return value


def _sha256_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not _is_sha256(value):
        raise NorgateActiveBuildRevisionError(f"Norgate active-build {label} is invalid")
    return value


def _is_sha256(value: str) -> bool:
    return re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _receipt_dir_name(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("revision-"):
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt label is invalid")
    return f"revision-{_run_label(value.removeprefix('revision-'))}"


def _run_label(value: str) -> str:
    if not isinstance(value, str) or _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise NorgateActiveBuildRevisionError("Norgate active-build receipt label is invalid")
    return value


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
