"""Offline verified input boundary for the first prospective KIS observation."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe, require_utc
from thericher_v2.data.kis_paper_intraday import (
    load_verified_kis_paper_private_intraday_catalog,
    prepare_kis_paper_intraday_feature_input,
    raw_bar_end_is_complete,
)
from thericher_v2.data.kis_paper_intraday_index_metadata import (
    KisPaperPrivateIntradayV1RetainedChunkMetadata,
    sha256_kis_paper_private_intraday_v1_index_bytes,
    validate_kis_paper_private_intraday_v1_index_metadata,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME,
)
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_CACHE_VERSION,
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    KIS_INTRADAY_PROSPECTIVE_HEAD_OBSERVATION_ID,
    KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES,
    KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
    KisIntradayProspectiveHeadObservationContract,
)

_HEAD_TARGET_KEY = "QQQ/NAS/1m"
_HEAD_EXPECTED_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
_PREPARATION_FILENAMES = frozenset({"precommit.json", "planning-receipt.json"})
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_VERIFIED_INPUT_CAPABILITY = object()


@dataclass(frozen=True, slots=True)
class KisIntradayProspectiveObservationInput:
    """Separate, selected KIS streams for one offline research consumer.

    The catalogs remain in-memory inputs for Research. ``safe_payload`` is the
    only serialization surface and deliberately excludes bars, prices, paths,
    preparation artifacts, and provider credentials.
    """

    historical_catalog: CatalogedBars
    prospective_catalog: CatalogedBars
    historical_session_dates: tuple[date, ...]
    prospective_session_dates: tuple[date, ...]
    historical_input_hash: str
    prospective_input_hash: str
    contract_hash: str
    precommit_hash: str
    artifact_slot_id: str
    selected_rows_fingerprint_sha256: str
    head_index_metadata_sha256: str
    input_hash: str
    schema_version: int = SCHEMA_VERSION
    _verification_capability: object = field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        object.__setattr__(self, "historical_session_dates", tuple(self.historical_session_dates))
        object.__setattr__(self, "prospective_session_dates", tuple(self.prospective_session_dates))
        if self._verification_capability is not _VERIFIED_INPUT_CAPABILITY:
            raise ValueError("prospective observation input requires the verified Data loader")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("prospective observation input schema is invalid")
        if self.historical_session_dates != (
            KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
        ):
            raise ValueError("prospective observation historical sessions are invalid")
        _validate_selected_catalog(
            catalog=self.historical_catalog,
            session_dates=self.historical_session_dates,
        )
        _validate_selected_catalog(
            catalog=self.prospective_catalog,
            session_dates=self.prospective_session_dates,
        )
        if (
            self.historical_input_hash
            != _catalog_feature_input_hash(
                catalog=self.historical_catalog,
                session_dates=self.historical_session_dates,
            )
            or self.prospective_input_hash
            != _catalog_feature_input_hash(
                catalog=self.prospective_catalog,
                session_dates=self.prospective_session_dates,
            )
        ):
            raise ValueError("prospective observation input identity is invalid")
        if (
            len(self.prospective_session_dates)
            != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
        ):
            raise ValueError("prospective observation prospective sessions are invalid")
        for value, field_name in (
            (self.historical_input_hash, "historical_input_hash"),
            (self.prospective_input_hash, "prospective_input_hash"),
            (self.contract_hash, "contract_hash"),
            (self.precommit_hash, "precommit_hash"),
            (self.artifact_slot_id, "artifact_slot_id"),
            (self.selected_rows_fingerprint_sha256, "selected_rows_fingerprint_sha256"),
            (self.head_index_metadata_sha256, "head_index_metadata_sha256"),
            (self.input_hash, "input_hash"),
        ):
            _require_sha256(value, field_name)
        expected_input_hash = _input_hash(
            historical_input_hash=self.historical_input_hash,
            prospective_input_hash=self.prospective_input_hash,
            contract_hash=self.contract_hash,
            precommit_hash=self.precommit_hash,
            artifact_slot_id=self.artifact_slot_id,
            selected_rows_fingerprint_sha256=self.selected_rows_fingerprint_sha256,
            head_index_metadata_sha256=self.head_index_metadata_sha256,
            historical_session_dates=self.historical_session_dates,
            prospective_session_dates=self.prospective_session_dates,
        )
        if self.input_hash != expected_input_hash:
            raise ValueError("prospective observation input identity is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return only selected stream identities, dates, and opaque hashes."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_intraday_prospective_observation_input",
            "observation_id": KIS_INTRADAY_PROSPECTIVE_HEAD_OBSERVATION_ID,
            "contract_hash": self.contract_hash,
            "precommit_hash": self.precommit_hash,
            "artifact_slot_id": self.artifact_slot_id,
            "selected_rows_fingerprint_sha256": self.selected_rows_fingerprint_sha256,
            "head_index_metadata_sha256": self.head_index_metadata_sha256,
            "historical": _safe_stream_payload(
                catalog=self.historical_catalog,
                session_dates=self.historical_session_dates,
                input_hash=self.historical_input_hash,
            ),
            "prospective": _safe_stream_payload(
                catalog=self.prospective_catalog,
                session_dates=self.prospective_session_dates,
                input_hash=self.prospective_input_hash,
            ),
            "input_hash": self.input_hash,
        }


@dataclass(frozen=True, slots=True)
class KisIntradayProspectiveObservationPreparation:
    """Read-only identity returned after pair and head-metadata verification."""

    selected_session_dates: tuple[date, ...]
    contract_hash: str
    precommit_hash: str
    artifact_slot_id: str
    selected_rows_fingerprint_sha256: str
    head_index_metadata_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_session_dates", tuple(self.selected_session_dates))
        _selected_session_dates([item.isoformat() for item in self.selected_session_dates])
        for value, field_name in (
            (self.contract_hash, "contract_hash"),
            (self.precommit_hash, "precommit_hash"),
            (self.artifact_slot_id, "artifact_slot_id"),
            (self.selected_rows_fingerprint_sha256, "selected_rows_fingerprint_sha256"),
            (self.head_index_metadata_sha256, "head_index_metadata_sha256"),
        ):
            _require_sha256(value, field_name)
        if self.artifact_slot_id != _artifact_slot_id(
            contract_hash=self.contract_hash,
            selected_session_dates=self.selected_session_dates,
        ):
            raise ValueError("prospective observation preparation pair is invalid")


@dataclass(frozen=True, slots=True)
class _HeadSelection:
    session_dates: tuple[date, ...]
    selected_rows_fingerprint_sha256: str


def _verified_observation_input(**kwargs: object) -> KisIntradayProspectiveObservationInput:
    """Construct the capability-bound input after Data verifies both cache reads."""

    return KisIntradayProspectiveObservationInput(
        **kwargs,
        _verification_capability=_VERIFIED_INPUT_CAPABILITY,
    )


def load_kis_intraday_prospective_observation_input(
    *,
    historical_cache_root: Path | str,
    head_cache_root: Path | str,
    preparation_dir: Path | str,
    repo_root: Path | str,
) -> KisIntradayProspectiveObservationInput:
    """Open only pair-bound, complete KIS cache streams for future Research.

    Preparation artifacts and head-index metadata are verified before either
    raw-cache loader runs. This function is local-only: it reads neither
    credentials nor network state and creates no files.
    """

    repository = Path(repo_root).resolve()
    preparation = verify_kis_intraday_prospective_observation_preparation(
        head_cache_root=head_cache_root,
        preparation_dir=preparation_dir,
        repo_root=repository,
    )
    head_root = _external_cache_root(
        cache_root=Path(head_cache_root),
        repo_root=repository,
    )

    historical_root = _external_cache_root(
        cache_root=Path(historical_cache_root),
        repo_root=repository,
    )
    if historical_root == head_root:
        raise ValueError("prospective observation streams must use separate cache roots")

    historical_source = load_verified_kis_paper_private_intraday_catalog(
        cache_root=historical_root,
        repo_root=repository,
        symbol="QQQ",
        exchange="NAS",
    )
    historical = prepare_kis_paper_intraday_feature_input(
        historical_source,
        session_dates=KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    )
    prospective_source = load_verified_kis_paper_private_intraday_catalog(
        cache_root=head_root,
        repo_root=repository,
        symbol="QQQ",
        exchange="NAS",
    )
    prospective = prepare_kis_paper_intraday_feature_input(
        prospective_source,
        session_dates=preparation.selected_session_dates,
    )
    try:
        final_preparation = verify_kis_intraday_prospective_observation_preparation(
            head_cache_root=head_root,
            preparation_dir=preparation_dir,
            repo_root=repository,
        )
    except ValueError as error:
        raise ValueError(
            "prospective observation source metadata changed during cache read"
        ) from error
    if final_preparation != preparation:
        raise ValueError("prospective observation source metadata changed during cache read")
    input_hash = _input_hash(
        historical_input_hash=historical.input_hash,
        prospective_input_hash=prospective.input_hash,
        contract_hash=final_preparation.contract_hash,
        precommit_hash=final_preparation.precommit_hash,
        artifact_slot_id=final_preparation.artifact_slot_id,
        selected_rows_fingerprint_sha256=final_preparation.selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=final_preparation.head_index_metadata_sha256,
        historical_session_dates=historical.session_dates,
        prospective_session_dates=prospective.session_dates,
    )
    return _verified_observation_input(
        historical_catalog=historical.catalog,
        prospective_catalog=prospective.catalog,
        historical_session_dates=historical.session_dates,
        prospective_session_dates=prospective.session_dates,
        historical_input_hash=historical.input_hash,
        prospective_input_hash=prospective.input_hash,
        contract_hash=final_preparation.contract_hash,
        precommit_hash=final_preparation.precommit_hash,
        artifact_slot_id=final_preparation.artifact_slot_id,
        selected_rows_fingerprint_sha256=final_preparation.selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=final_preparation.head_index_metadata_sha256,
        input_hash=input_hash,
    )


def verify_kis_intraday_prospective_observation_preparation(
    *,
    head_cache_root: Path | str,
    preparation_dir: Path | str,
    repo_root: Path | str,
) -> KisIntradayProspectiveObservationPreparation:
    """Verify a pair-bound head selection without opening either raw cache.

    This public boundary reads only the immutable preparation pair and head
    index metadata. It returns no paths, bar rows, prices, credentials, or
    artifact handles, so callers can verify readiness before opening a cache.
    """

    repository = Path(repo_root).resolve()
    preparation = _load_preparation_pair(
        preparation_dir=Path(preparation_dir),
        repo_root=repository,
    )
    head_root = _external_cache_root(
        cache_root=Path(head_cache_root),
        repo_root=repository,
    )
    head_selection = _inspect_head_selection(
        head_cache_root=head_root,
        repo_root=repository,
    )
    # The pair retains its full-index hash as preparation-time provenance. Only
    # the frozen first-five QQQ selection must remain stable across later appends.
    if (
        preparation.selected_session_dates != head_selection.session_dates
        or preparation.selected_rows_fingerprint_sha256
        != head_selection.selected_rows_fingerprint_sha256
    ):
        raise ValueError("prospective observation preparation does not match source metadata")
    return preparation


def _load_preparation_pair(
    *,
    preparation_dir: Path,
    repo_root: Path,
) -> KisIntradayProspectiveObservationPreparation:
    directory = _external_preparation_dir(preparation_dir=preparation_dir, repo_root=repo_root)
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise ValueError("prospective observation preparation pair is invalid") from error
    if (
        frozenset(entry.name for entry in entries) != _PREPARATION_FILENAMES
        or len(entries) != len(_PREPARATION_FILENAMES)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise ValueError("prospective observation preparation pair is invalid")
    precommit = _read_json_file(directory / "precommit.json")
    receipt = _read_json_file(directory / "planning-receipt.json")
    return _validate_preparation_pair(precommit=precommit, receipt=receipt)


def _validate_preparation_pair(
    *,
    precommit: Mapping[str, object],
    receipt: Mapping[str, object],
) -> KisIntradayProspectiveObservationPreparation:
    expected_precommit_keys = {
        "schema_version",
        "kind",
        "status",
        "prepared_at_utc",
        "contract",
        "contract_hash",
        "head_index",
        "selected_session_dates",
        "artifact_slot_id",
        "selected_rows_fingerprint_sha256",
        "precommit_hash",
    }
    expected_receipt_keys = {
        "schema_version",
        "kind",
        "status",
        "prepared_at_utc",
        "contract_hash",
        "artifact_slot_id",
        "selected_session_dates",
        "selected_rows_fingerprint_sha256",
        "precommit_hash",
        "next_consumer_contract",
    }
    if set(precommit) != expected_precommit_keys or set(receipt) != expected_receipt_keys:
        raise ValueError("prospective observation preparation pair is invalid")

    contract = KisIntradayProspectiveHeadObservationContract()
    selected_dates = _selected_session_dates(precommit.get("selected_session_dates"))
    selected_date_strings = [item.isoformat() for item in selected_dates]
    contract_hash = precommit.get("contract_hash")
    declared_precommit_hash = precommit.get("precommit_hash")
    selected_rows_fingerprint_sha256 = precommit.get("selected_rows_fingerprint_sha256")
    if (
        precommit.get("schema_version") != SCHEMA_VERSION
        or precommit.get("kind") != "kis_intraday_prospective_head_observation_precommit"
        or precommit.get("status") != "prepared"
        or precommit.get("contract") != contract.to_payload()
        or contract_hash != contract.contract_hash
        or not isinstance(declared_precommit_hash, str)
        or not isinstance(selected_rows_fingerprint_sha256, str)
    ):
        raise ValueError("prospective observation preparation pair is invalid")
    _require_sha256(declared_precommit_hash, "precommit_hash")
    _require_sha256(selected_rows_fingerprint_sha256, "selected_rows_fingerprint_sha256")
    _validate_utc_marker(precommit.get("prepared_at_utc"))
    head_index_metadata_sha256 = _validate_head_index_binding(precommit.get("head_index"))
    expected_slot_id = _artifact_slot_id(
        contract_hash=contract.contract_hash,
        selected_session_dates=selected_dates,
    )
    if precommit.get("artifact_slot_id") != expected_slot_id:
        raise ValueError("prospective observation preparation pair is invalid")
    precommit_without_hash = dict(precommit)
    precommit_without_hash.pop("precommit_hash")
    if declared_precommit_hash != _sha256_payload(precommit_without_hash):
        raise ValueError("prospective observation preparation pair is invalid")

    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("kind") != "kis_intraday_prospective_head_observation_planning_receipt"
        or receipt.get("status") != "prepared"
        or receipt.get("prepared_at_utc") != precommit.get("prepared_at_utc")
        or receipt.get("contract_hash") != contract.contract_hash
        or receipt.get("artifact_slot_id") != expected_slot_id
        or receipt.get("selected_session_dates") != selected_date_strings
        or receipt.get("selected_rows_fingerprint_sha256") != selected_rows_fingerprint_sha256
        or receipt.get("precommit_hash") != declared_precommit_hash
        or receipt.get("next_consumer_contract")
        != {
            "historical_development_prefix_session_count": len(
                KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
            ),
            "prospective_session_receipts_required": (
                KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            ),
        }
    ):
        raise ValueError("prospective observation preparation pair is invalid")
    return KisIntradayProspectiveObservationPreparation(
        selected_session_dates=selected_dates,
        contract_hash=contract.contract_hash,
        precommit_hash=declared_precommit_hash,
        artifact_slot_id=expected_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=head_index_metadata_sha256,
    )


def _inspect_head_selection(*, head_cache_root: Path, repo_root: Path) -> _HeadSelection:
    root = _external_cache_root(cache_root=head_cache_root, repo_root=repo_root)
    version_root = root / KIS_INTRADAY_PROSPECTIVE_HEAD_CACHE_VERSION
    if (
        KIS_INTRADAY_PROSPECTIVE_HEAD_CACHE_VERSION
        != KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
        or version_root.is_symlink()
    ):
        raise ValueError("prospective observation source metadata is invalid")
    index = _read_json_file(version_root / KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME)
    try:
        metadata = validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_HEAD_EXPECTED_TARGETS,
        )
    except ValueError as error:
        raise ValueError("prospective observation source metadata is invalid") from error
    qqq_target = next(
        (
            target
            for target in metadata.targets
            if target.target_key == _HEAD_TARGET_KEY
        ),
        None,
    )
    if qqq_target is None:
        raise ValueError("prospective observation source metadata is invalid")
    complete_dates, first_seen_fingerprints = _complete_regular_sessions(
        qqq_target.retained_chunks
    )
    selected_dates = complete_dates[:KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT]
    if len(selected_dates) != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT:
        raise ValueError("prospective observation source metadata is unavailable")
    return _HeadSelection(
        session_dates=selected_dates,
        selected_rows_fingerprint_sha256=_selected_rows_fingerprint_sha256(
            first_seen_fingerprints=first_seen_fingerprints,
            selected_session_dates=selected_dates,
        ),
    )


def _complete_regular_sessions(
    chunks: tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...],
) -> tuple[tuple[date, ...], dict[str, str]]:
    first_seen_completion: dict[str, bool] = {}
    first_seen_fingerprints: dict[str, str] = {}
    try:
        for chunk in chunks:
            for row_key, fingerprint in chunk.rows:
                if row_key in first_seen_completion:
                    if first_seen_fingerprints[row_key] != fingerprint:
                        raise ValueError("prospective observation source metadata is invalid")
                    continue
                first_seen_fingerprints[row_key] = fingerprint
                first_seen_completion[row_key] = raw_bar_end_is_complete(
                    start_ts=_korea_timestamp_to_utc(row_key),
                    collected_at=chunk.collected_at,
                )
        completed_row_keys = frozenset(
            row_key for row_key, complete in first_seen_completion.items() if complete
        )
        candidate_dates = sorted(
            {
                _korea_timestamp_to_utc(row_key).date()
                for row_key in completed_row_keys
                if _korea_timestamp_to_utc(row_key).date()
                > KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1]
            }
        )
    except ValueError as error:
        raise ValueError("prospective observation source metadata is invalid") from error

    complete_dates: list[date] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        expected_keys = frozenset(
            _korea_timestamp_key(
                session.window.open_ts + Timeframe.M1.duration * minute_offset
            )
            for minute_offset in range(KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES)
        )
        if expected_keys.issubset(completed_row_keys):
            complete_dates.append(session_date)
    return tuple(complete_dates), first_seen_fingerprints


def _selected_rows_fingerprint_sha256(
    *,
    first_seen_fingerprints: Mapping[str, str],
    selected_session_dates: tuple[date, ...],
) -> str:
    selected_rows: dict[str, str] = {}
    try:
        for session_date in selected_session_dates:
            session = us_equity_2026_session(session_date)
            if session is None or session.kind != "regular":
                raise ValueError("prospective observation source metadata is invalid")
            for minute_offset in range(KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES):
                row_key = _korea_timestamp_key(
                    session.window.open_ts + Timeframe.M1.duration * minute_offset
                )
                selected_rows[row_key] = first_seen_fingerprints[row_key]
    except (KeyError, ValueError) as error:
        raise ValueError("prospective observation source metadata is invalid") from error
    return _sha256_payload({"selected_rows": selected_rows})


def _external_preparation_dir(*, preparation_dir: Path, repo_root: Path) -> Path:
    if preparation_dir.is_symlink():
        raise ValueError("prospective observation preparation pair is invalid")
    try:
        directory = preparation_dir.resolve()
    except OSError as error:
        raise ValueError("prospective observation preparation pair is invalid") from error
    if not directory.is_dir() or not _is_external_to_repository(directory, repo_root=repo_root):
        raise ValueError("prospective observation preparation pair is invalid")
    return directory


def _external_cache_root(*, cache_root: Path, repo_root: Path) -> Path:
    if cache_root.is_symlink():
        raise ValueError("prospective observation cache root is invalid")
    try:
        root = cache_root.resolve()
    except OSError as error:
        raise ValueError("prospective observation cache root is invalid") from error
    if not _is_external_to_repository(root, repo_root=repo_root, allow_market_data_mount=True):
        raise ValueError("prospective observation cache root is invalid")
    return root


def _is_external_to_repository(
    value: Path,
    *,
    repo_root: Path,
    allow_market_data_mount: bool = False,
) -> bool:
    repository = repo_root.resolve()
    if not value.is_relative_to(repository):
        return True
    docker_repository = Path("/app").resolve()
    if os.name == "nt" or repository != docker_repository:
        return False
    mount_name = "market_data" if allow_market_data_mount else "model_artifacts"
    return value.is_relative_to((docker_repository / mount_name).resolve())


def _read_json_file(path: Path) -> Mapping[str, object]:
    value, _ = _read_json_file_with_sha256(path)
    return value


def _read_json_file_with_sha256(path: Path) -> tuple[Mapping[str, object], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("prospective observation preparation pair is invalid")
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prospective observation preparation pair is invalid") from error
    if not isinstance(value, Mapping):
        raise ValueError("prospective observation preparation pair is invalid")
    return value, sha256_kis_paper_private_intraday_v1_index_bytes(payload)


def _selected_session_dates(value: object) -> tuple[date, ...]:
    if (
        not isinstance(value, list)
        or len(value) != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
    ):
        raise ValueError("prospective observation preparation pair is invalid")
    try:
        dates = tuple(date.fromisoformat(item) for item in value if isinstance(item, str))
    except ValueError as error:
        raise ValueError("prospective observation preparation pair is invalid") from error
    if (
        len(dates) != len(value)
        or dates != tuple(sorted(dates))
        or len(set(dates)) != len(dates)
        or any(
            item <= KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1]
            or (session := us_equity_2026_session(item)) is None
            or session.kind != "regular"
            for item in dates
        )
    ):
        raise ValueError("prospective observation preparation pair is invalid")
    return dates


def _validate_head_index_binding(value: object) -> str:
    if not isinstance(value, Mapping) or set(value) != {
        "status",
        "metadata_sha256",
        "target_key",
    }:
        raise ValueError("prospective observation preparation pair is invalid")
    if (
        value.get("status") != "available"
        or value.get("target_key") != _HEAD_TARGET_KEY
        or not isinstance(value.get("metadata_sha256"), str)
    ):
        raise ValueError("prospective observation preparation pair is invalid")
    metadata_sha256 = value["metadata_sha256"]
    _require_sha256(metadata_sha256, "head_index.metadata_sha256")
    return metadata_sha256


def _validate_utc_marker(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("prospective observation preparation pair is invalid")
    try:
        require_utc(datetime.fromisoformat(value), "prepared_at_utc")
    except ValueError as error:
        raise ValueError("prospective observation preparation pair is invalid") from error


def _artifact_slot_id(*, contract_hash: str, selected_session_dates: tuple[date, ...]) -> str:
    return _sha256_payload(
        {
            "contract_hash": contract_hash,
            "selected_session_dates": [item.isoformat() for item in selected_session_dates],
            "target_key": _HEAD_TARGET_KEY,
        }
    )


def _input_hash(
    *,
    historical_input_hash: str,
    prospective_input_hash: str,
    contract_hash: str,
    precommit_hash: str,
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
    head_index_metadata_sha256: str,
    historical_session_dates: tuple[date, ...],
    prospective_session_dates: tuple[date, ...],
) -> str:
    return _sha256_payload(
        {
            "kind": "kis_intraday_prospective_observation_input_v1",
            "historical_input_hash": historical_input_hash,
            "prospective_input_hash": prospective_input_hash,
            "contract_hash": contract_hash,
            "precommit_hash": precommit_hash,
            "artifact_slot_id": artifact_slot_id,
            "selected_rows_fingerprint_sha256": selected_rows_fingerprint_sha256,
            "head_index_metadata_sha256": head_index_metadata_sha256,
            "historical_session_dates": [item.isoformat() for item in historical_session_dates],
            "prospective_session_dates": [item.isoformat() for item in prospective_session_dates],
        }
    )


def _safe_stream_payload(
    *,
    catalog: CatalogedBars,
    session_dates: tuple[date, ...],
    input_hash: str,
) -> dict[str, object]:
    return {
        "catalog_dataset_id": catalog.dataset_id,
        "catalog_dataset_hash": catalog.dataset_hash,
        "session_dates": [item.isoformat() for item in session_dates],
        "input_hash": input_hash,
    }


def _catalog_feature_input_hash(
    *,
    catalog: CatalogedBars,
    session_dates: tuple[date, ...],
) -> str:
    return _sha256_payload(
        {
            "kind": "kis_paper_private_intraday_feature_input_v1",
            "selected_catalog_id": catalog.dataset_id,
            "selected_catalog_hash": catalog.dataset_hash,
            "session_dates": [item.isoformat() for item in session_dates],
            "session_windows": [
                {
                    "open_ts": session.window.open_ts.isoformat(),
                    "close_ts": session.window.close_ts.isoformat(),
                }
                for session_date in session_dates
                if (session := us_equity_2026_session(session_date)) is not None
            ],
        }
    )


def _validate_selected_catalog(*, catalog: CatalogedBars, session_dates: tuple[date, ...]) -> None:
    if not isinstance(catalog, CatalogedBars):
        raise ValueError("prospective observation selected catalog is invalid")
    if not catalog.dataset_id.startswith("kis.paper.private.intraday.qqq.nas.m1."):
        raise ValueError("prospective observation selected catalog is invalid")
    expected_starts: list[datetime] = []
    for session_date in session_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            raise ValueError("prospective observation selected catalog is invalid")
        expected_starts.extend(
            session.window.open_ts + Timeframe.M1.duration * offset
            for offset in range(KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES)
        )
    if (
        len(catalog.bars) != len(expected_starts)
        or tuple(bar.start_ts for bar in catalog.bars) != tuple(expected_starts)
        or any(
            bar.symbol != "QQQ"
            or bar.market != "US"
            or bar.timeframe is not Timeframe.M1
            or not bar.complete
            for bar in catalog.bars
        )
    ):
        raise ValueError("prospective observation selected catalog is invalid")


def _korea_timestamp_to_utc(row_key: str) -> datetime:
    return datetime.strptime(row_key, "%Y%m%dT%H%M%S").replace(tzinfo=_KOREA_TZ).astimezone(UTC)


def _korea_timestamp_key(timestamp: datetime) -> str:
    return require_utc(timestamp, "timestamp").astimezone(_KOREA_TZ).strftime("%Y%m%dT%H%M%S")


def _require_sha256(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")
    prefix, separator, digest = value.partition(":")
    if (
        prefix != "sha256"
        or separator != ":"
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
