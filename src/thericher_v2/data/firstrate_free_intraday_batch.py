"""Source-safe batch runner for staged FirstRate free intraday archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from thericher_v2.data.firstrate_free_intraday import (
    FirstRateFreeIntradayNormalization,
    normalize_firstrate_free_intraday_zip,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_ACQUISITION_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/firstrate-free-intraday-20260819-spy-qqq-r1.json"
)
_NORMALIZATION_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/firstrate-free-intraday-source-local-normalization-v1.json"
)
_CANONICAL_RELATIVE_DIRECTORY = Path("us_equities/firstrate_free_intraday/canonical")
_REQUIRED_SYMBOLS = ("SPY", "QQQ")
_ACQUISITION_SCHEMA_VERSION = "firstrate-free-intraday-acquisition-receipt-v1"
_NORMALIZATION_SCHEMA_VERSION = "firstrate-free-intraday-normalization-receipt-v1"
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True)
class FirstRateFreeIntradayArchiveSpec:
    """Safe archive identity carried from the staged acquisition receipt."""

    symbol: str
    market_data_relative_path: Path
    expected_archive_sha256: str
    source_entry_name: str


def normalize_staged_firstrate_free_intraday_archives(
    *,
    market_data_root: Path | str,
    artifact_root: Path | str,
    acquisition_receipt_path: Path | str | None = None,
    normalization_receipt_path: Path | str | None = None,
) -> dict[str, object]:
    """Normalize the two staged archives and write one source-safe receipt.

    The receipt contains identities and aggregates only. It never receives CSV
    rows, prices, timestamps, credentials, provider responses, or broker data.
    """

    resolved_market_data_root = _require_external_root(
        market_data_root, field_name="market_data_root"
    )
    resolved_artifact_root = _require_external_root(artifact_root, field_name="artifact_root")
    resolved_acquisition_path = _path_within_root(
        resolved_artifact_root,
        acquisition_receipt_path or resolved_artifact_root / _ACQUISITION_RECEIPT_RELATIVE_PATH,
        field_name="acquisition_receipt_path",
    )
    resolved_normalization_path = _path_within_root(
        resolved_artifact_root,
        normalization_receipt_path
        or resolved_artifact_root / _NORMALIZATION_RECEIPT_RELATIVE_PATH,
        field_name="normalization_receipt_path",
    )

    acquisition_bytes = resolved_acquisition_path.read_bytes()
    specs = _parse_acquisition_receipt(acquisition_bytes)
    normalizations: list[dict[str, object]] = []
    for spec in specs:
        archive_path = _path_within_root(
            resolved_market_data_root,
            spec.market_data_relative_path,
            field_name="archive_path",
        )
        canonical_relative_path = _CANONICAL_RELATIVE_DIRECTORY / f"{spec.symbol}_1m.csv"
        canonical_path = _path_within_root(
            resolved_market_data_root,
            canonical_relative_path,
            field_name="canonical_path",
        )
        result = normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=spec.expected_archive_sha256,
            symbol=spec.symbol,
            output_csv_path=canonical_path,
            market="US",
        )
        _validate_written_output(canonical_path, result)
        normalizations.append(
            _normalization_payload(
                result=result,
                archive_relative_path=spec.market_data_relative_path,
                canonical_relative_path=canonical_relative_path,
            )
        )

    payload: dict[str, object] = {
        "schema_version": _NORMALIZATION_SCHEMA_VERSION,
        "receipt_id": "firstrate-free-intraday-source-local-normalization-v1",
        "status": "completed",
        "source_acquisition_receipt": {
            "relative_to_artifact_root": True,
            "path": _relative_posix(resolved_artifact_root, resolved_acquisition_path),
            "sha256": _sha256(acquisition_bytes),
        },
        "normalizations": normalizations,
        "safety": {
            "credentials_read": False,
            "network_access": False,
            "kis_or_broker_called": False,
            "raw_market_rows_retained_in_receipt": False,
            "market_data_written_outside_market_data_root": False,
            "git_tracked_files_changed": False,
        },
        "quality": {
            "timezone_conversion": "America/New_York -> UTC",
            "reindex_or_fill": False,
            "timestamp_set_rule": "emitted_must_equal_decoded_source_timestamp_set",
            "session_coverage": "not_assessed",
            "source_timestamp_semantics": "unverified",
        },
        "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
        "limitations": [
            "no_kis_parity",
            "decision_time_availability_not_observed",
            "provider_finality_not_observed",
            "source_gaps_are_not_session_coverage_evidence",
            "not_a_model_campaign_or_paper_input",
        ],
    }
    _write_or_verify(resolved_normalization_path, payload)
    return {
        "status": "completed",
        "receipt_path_relative_to_artifact_root": _relative_posix(
            resolved_artifact_root, resolved_normalization_path
        ),
        "normalizations": normalizations,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--acquisition-receipt", type=Path)
    parser.add_argument("--normalization-receipt", type=Path)
    args = parser.parse_args(argv)
    result = normalize_staged_firstrate_free_intraday_archives(
        market_data_root=args.market_data_root,
        artifact_root=args.artifact_root,
        acquisition_receipt_path=args.acquisition_receipt,
        normalization_receipt_path=args.normalization_receipt,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


def _parse_acquisition_receipt(
    payload_bytes: bytes,
) -> tuple[FirstRateFreeIntradayArchiveSpec, ...]:
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("acquisition receipt is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("acquisition receipt must be an object")
    if payload.get("schema_version") != _ACQUISITION_SCHEMA_VERSION:
        raise ValueError("acquisition receipt schema version is unexpected")
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("provider") != "FirstRate Data":
        raise ValueError("acquisition receipt provider is unexpected")
    if payload.get("permitted_interpretation") != "source_isolated_retrospective_mechanics_only":
        raise ValueError("acquisition receipt interpretation is unexpected")
    archives = payload.get("archives")
    if not isinstance(archives, list):
        raise ValueError("acquisition receipt archives must be a list")

    specs: dict[str, FirstRateFreeIntradayArchiveSpec] = {}
    for archive in archives:
        if not isinstance(archive, dict):
            raise ValueError("acquisition receipt archive must be an object")
        symbol = archive.get("symbol")
        relative_path = archive.get("market_data_relative_path")
        expected_sha256 = archive.get("sha256")
        entry_name = archive.get("archive_entry_name")
        if not isinstance(symbol, str) or symbol not in _REQUIRED_SYMBOLS:
            raise ValueError("acquisition receipt archive symbol is unexpected")
        if symbol in specs:
            raise ValueError("acquisition receipt has duplicate symbols")
        if archive.get("archive_file_count") != 1 or archive.get("archive_paths_safe") is not True:
            raise ValueError("acquisition receipt archive shape is unexpected")
        if not isinstance(relative_path, str):
            raise ValueError("acquisition receipt archive path is invalid")
        if not isinstance(expected_sha256, str) or not _is_sha256(expected_sha256):
            raise ValueError("acquisition receipt archive hash is invalid")
        expected_entry_name = f"{symbol}_1min_firstratedata.csv"
        if entry_name != expected_entry_name:
            raise ValueError("acquisition receipt archive entry is unexpected")
        specs[symbol] = FirstRateFreeIntradayArchiveSpec(
            symbol=symbol,
            market_data_relative_path=_relative_path(relative_path, field_name="archive path"),
            expected_archive_sha256=expected_sha256,
            source_entry_name=expected_entry_name,
        )
    if set(specs) != set(_REQUIRED_SYMBOLS):
        raise ValueError("acquisition receipt must contain exactly SPY and QQQ")
    return tuple(specs[symbol] for symbol in _REQUIRED_SYMBOLS)


def _normalization_payload(
    *,
    result: FirstRateFreeIntradayNormalization,
    archive_relative_path: Path,
    canonical_relative_path: Path,
) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "market": result.market,
        "timeframe": "1m",
        "archive_market_data_relative_path": archive_relative_path.as_posix(),
        "archive_sha256": result.input_sha256,
        "archive_hash_matches_acquisition_receipt": True,
        "archive_entry_name": result.source_entry_name,
        "canonical_market_data_relative_path": canonical_relative_path.as_posix(),
        "canonical_sha256": result.output_sha256,
        "bar_count": result.bar_count,
        "decoded_timestamp_set_sha256": result.decoded_timestamp_set_sha256,
        "emitted_timestamp_set_sha256": result.emitted_timestamp_set_sha256,
        "timestamp_set_equal": True,
    }


def _validate_written_output(
    path: Path, result: FirstRateFreeIntradayNormalization) -> None:
    observed_hash = _sha256(path.read_bytes())
    if observed_hash != result.output_sha256:
        raise RuntimeError("canonical output hash changed before receipt write")
    if result.decoded_timestamp_set_sha256 != result.emitted_timestamp_set_sha256:
        raise RuntimeError("canonical timestamp-set equality is not established")


def _require_external_root(value: Path | str, *, field_name: str) -> Path:
    root = Path(value).resolve(strict=False)
    if root.is_relative_to(_REPO_ROOT):
        raise ValueError(f"{field_name} must stay outside Git")
    return root


def _path_within_root(root: Path, value: Path | str, *, field_name: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = (root / candidate).resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field_name} must stay under its external root")
    return resolved


def _relative_path(value: str, *, field_name: str) -> Path:
    if "\\" in value:
        raise ValueError(f"{field_name} must use a relative POSIX path")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise ValueError(f"{field_name} must be a safe relative path")
    return Path(*parsed.parts)


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_or_verify(destination: Path, payload: dict[str, object]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("normalization receipt conflicts with existing evidence")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _is_sha256(value: str) -> bool:
    return (
        value.startswith(_SHA256_PREFIX)
        and len(value) == len(_SHA256_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )


def _sha256(payload: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    main()
