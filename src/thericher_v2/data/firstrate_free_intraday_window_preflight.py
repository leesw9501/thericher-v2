"""Target-free FirstRate source-local feature-window geometry preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.firstrate_free_intraday_timeframe_mechanics import (
    FirstRateCanonicalSpec,
    parse_firstrate_normalization_receipt,
    validate_firstrate_canonical_bars,
)
from thericher_v2.data.local import LocalCsvBarProvider, bar_to_record
from thericher_v2.data.provider import BarQuery
from thericher_v2.data.resample import resample_bars

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DEFAULT_MECHANICS_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/"
    "firstrate-free-intraday-source-local-timeframe-mechanics-v1.json"
)
_DEFAULT_PREFLIGHT_MANIFEST_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/"
    "firstrate-free-intraday-source-local-window-preflight-v1.json"
)
_MECHANICS_SCHEMA_VERSION = "firstrate-free-intraday-source-local-timeframe-mechanics-v1"
_PREFLIGHT_SCHEMA_VERSION = "firstrate-free-intraday-source-local-window-preflight-v1"
_SHA256_PREFIX = "sha256:"
_WINDOW_MATRIX: tuple[tuple[Timeframe, tuple[int, ...]], ...] = (
    (Timeframe.M1, (30, 60, 120, 240)),
    (Timeframe.M5, (12, 24, 48)),
    (Timeframe.M10, (6, 12, 24)),
    (Timeframe.H1, (3, 6, 12)),
    (Timeframe.H3, (2, 4, 8)),
)
_REQUIRED_SYMBOLS = ("SPY", "QQQ")


@dataclass(frozen=True)
class TimeframeMechanicsEvidence:
    """Source-safe reattachment facts for one previously verified timeframe."""

    bar_count: int
    bar_content_sha256: str
    timestamp_set_sha256: str


def build_firstrate_source_local_window_preflight(
    *,
    market_data_root: Path | str,
    artifact_root: Path | str,
    mechanics_receipt_path: Path | str | None = None,
    preflight_manifest_path: Path | str | None = None,
) -> dict[str, object]:
    """Write aggregate window geometry after independently reattesting parents."""

    resolved_market_data_root = _require_external_root(
        market_data_root, field_name="market_data_root"
    )
    resolved_artifact_root = _require_external_root(artifact_root, field_name="artifact_root")
    resolved_mechanics_path = _path_within_root(
        resolved_artifact_root,
        mechanics_receipt_path
        or resolved_artifact_root / _DEFAULT_MECHANICS_RECEIPT_RELATIVE_PATH,
        field_name="mechanics_receipt_path",
    )
    resolved_manifest_path = _path_within_root(
        resolved_artifact_root,
        preflight_manifest_path
        or resolved_artifact_root / _DEFAULT_PREFLIGHT_MANIFEST_RELATIVE_PATH,
        field_name="preflight_manifest_path",
    )

    mechanics_bytes = resolved_mechanics_path.read_bytes()
    mechanics_payload = _decode_json(mechanics_bytes, field_name="timeframe mechanics receipt")
    normalization_reference = _normalization_reference(mechanics_payload)
    resolved_normalization_path = _path_within_root(
        resolved_artifact_root,
        normalization_reference["path"],
        field_name="normalization_receipt_path",
    )
    normalization_bytes = resolved_normalization_path.read_bytes()
    if _sha256(normalization_bytes) != normalization_reference["sha256"]:
        raise ValueError("normalization receipt hash does not match timeframe mechanics receipt")
    specs = parse_firstrate_normalization_receipt(normalization_bytes)
    mechanics = _parse_timeframe_mechanics_receipt(
        mechanics_payload,
        normalization_receipt_sha256=_sha256(normalization_bytes),
        specs=specs,
    )

    symbols: list[dict[str, object]] = []
    for spec in specs:
        canonical_path = _path_within_root(
            resolved_market_data_root,
            spec.canonical_market_data_relative_path,
            field_name="canonical_path",
        )
        if _sha256(canonical_path.read_bytes()) != spec.canonical_sha256:
            raise ValueError("canonical CSV hash does not match normalization receipt")
        source_bars = LocalCsvBarProvider(canonical_path).get_bars(
            BarQuery(symbol=spec.symbol, market=spec.market, timeframe=Timeframe.M1)
        )
        validate_firstrate_canonical_bars(source_bars, spec)
        timeframes: list[dict[str, object]] = []
        for timeframe, lookbacks in _WINDOW_MATRIX:
            bars = resample_bars(source_bars, timeframe)
            evidence = mechanics[spec.symbol][timeframe]
            _validate_resampled_bars(
                bars,
                timeframe=timeframe,
                evidence=evidence,
            )
            timeframes.append(
                {
                    "timeframe": timeframe.value,
                    "mechanics_bar_count": evidence.bar_count,
                    "mechanics_bar_content_sha256": evidence.bar_content_sha256,
                    "mechanics_timestamp_set_sha256": evidence.timestamp_set_sha256,
                    "cells": _window_cells(bars, timeframe=timeframe, lookbacks=lookbacks),
                }
            )
        symbols.append(
            {
                "symbol": spec.symbol,
                "market": spec.market,
                "canonical_market_data_relative_path": (
                    spec.canonical_market_data_relative_path.as_posix()
                ),
                "canonical_sha256": spec.canonical_sha256,
                "timeframes": timeframes,
            }
        )

    matrix_contract = _matrix_contract()
    payload: dict[str, object] = {
        "schema_version": _PREFLIGHT_SCHEMA_VERSION,
        "receipt_id": "firstrate-free-intraday-source-local-window-preflight-v1",
        "status": "completed",
        "parents": {
            "normalization_receipt": {
                "relative_to_artifact_root": True,
                "path": _relative_posix(resolved_artifact_root, resolved_normalization_path),
                "sha256": _sha256(normalization_bytes),
            },
            "timeframe_mechanics_receipt": {
                "relative_to_artifact_root": True,
                "path": _relative_posix(resolved_artifact_root, resolved_mechanics_path),
                "sha256": _sha256(mechanics_bytes),
            },
        },
        "window_matrix": matrix_contract,
        "window_matrix_sha256": _sha256_json(matrix_contract),
        "symbols": symbols,
        "safety": {
            "credentials_read": False,
            "network_access": False,
            "kis_or_broker_called": False,
            "raw_market_rows_retained_in_manifest": False,
            "feature_values_retained_in_manifest": False,
            "labels_retained_in_manifest": False,
            "predictions_or_weights_retained_in_manifest": False,
            "resampled_bars_retained_in_manifest": False,
            "market_data_written_outside_market_data_root": False,
            "git_tracked_files_changed": False,
        },
        "permitted_interpretation": "source_isolated_target_free_window_geometry_only",
        "limitations": [
            "source_timestamp_semantics_unverified",
            "session_coverage_not_assessed",
            "no_kis_parity",
            "decision_time_availability_not_observed",
            "provider_finality_not_observed",
            "no_label_prediction_model_selection_or_paper_input",
        ],
    }
    _write_or_verify(resolved_manifest_path, payload)
    return {
        "status": "completed",
        "manifest_path_relative_to_artifact_root": _relative_posix(
            resolved_artifact_root, resolved_manifest_path
        ),
        "symbol_count": len(symbols),
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--mechanics-receipt", type=Path)
    parser.add_argument("--preflight-manifest", type=Path)
    args = parser.parse_args(argv)
    result = build_firstrate_source_local_window_preflight(
        market_data_root=args.market_data_root,
        artifact_root=args.artifact_root,
        mechanics_receipt_path=args.mechanics_receipt,
        preflight_manifest_path=args.preflight_manifest,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


def _normalization_reference(payload: dict[str, object]) -> dict[str, str]:
    reference = payload.get("normalization_receipt")
    if not isinstance(reference, dict):
        raise ValueError("timeframe mechanics normalization receipt reference is invalid")
    path = reference.get("path")
    sha256 = reference.get("sha256")
    if reference.get("relative_to_artifact_root") is not True or not isinstance(path, str):
        raise ValueError("timeframe mechanics normalization receipt path is invalid")
    if not _is_sha256(sha256):
        raise ValueError("timeframe mechanics normalization receipt hash is invalid")
    _relative_path(path, field_name="normalization receipt path")
    return {"path": path, "sha256": sha256}


def _parse_timeframe_mechanics_receipt(
    payload: dict[str, object],
    *,
    normalization_receipt_sha256: str,
    specs: tuple[FirstRateCanonicalSpec, ...],
) -> dict[str, dict[Timeframe, TimeframeMechanicsEvidence]]:
    if (
        payload.get("schema_version") != _MECHANICS_SCHEMA_VERSION
        or payload.get("receipt_id")
        != "firstrate-free-intraday-source-local-timeframe-mechanics-v1"
        or payload.get("status") != "completed"
        or payload.get("permitted_interpretation")
        != "source_isolated_retrospective_mechanics_only"
    ):
        raise ValueError("timeframe mechanics receipt identity is unexpected")
    if _normalization_reference(payload)["sha256"] != normalization_receipt_sha256:
        raise ValueError("timeframe mechanics normalization receipt binding is invalid")
    _validate_resampling_contract(payload.get("resampling_contract"))
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError("timeframe mechanics symbols are invalid")

    parsed: dict[str, dict[Timeframe, TimeframeMechanicsEvidence]] = {}
    specs_by_symbol = {spec.symbol: spec for spec in specs}
    for symbol_payload in symbols:
        if not isinstance(symbol_payload, dict):
            raise ValueError("timeframe mechanics symbol is invalid")
        symbol = symbol_payload.get("symbol")
        spec = specs_by_symbol.get(symbol) if isinstance(symbol, str) else None
        if spec is None or symbol in parsed:
            raise ValueError("timeframe mechanics symbol binding is invalid")
        if (
            symbol_payload.get("market") != spec.market
            or symbol_payload.get("canonical_market_data_relative_path")
            != spec.canonical_market_data_relative_path.as_posix()
            or symbol_payload.get("canonical_sha256") != spec.canonical_sha256
            or symbol_payload.get("source_bar_count") != spec.bar_count
            or symbol_payload.get("source_timestamp_set_sha256")
            != spec.emitted_timestamp_set_sha256
            or symbol_payload.get("canonical_hash_matches_normalization_receipt") is not True
            or symbol_payload.get("source_timestamps_strictly_ordered_unique") is not True
            or symbol_payload.get("source_bars_complete") is not True
        ):
            raise ValueError("timeframe mechanics canonical binding is invalid")
        timeframe_payloads = symbol_payload.get("timeframes")
        if not isinstance(timeframe_payloads, list):
            raise ValueError("timeframe mechanics timeframes are invalid")
        evidence: dict[Timeframe, TimeframeMechanicsEvidence] = {}
        for item in timeframe_payloads:
            if not isinstance(item, dict):
                raise ValueError("timeframe mechanics timeframe item is invalid")
            try:
                timeframe = Timeframe(item.get("timeframe"))
            except (TypeError, ValueError) as error:
                raise ValueError("timeframe mechanics timeframe is invalid") from error
            if timeframe not in _matrix_timeframes() or timeframe in evidence:
                raise ValueError("timeframe mechanics timeframe is unexpected")
            bar_count = item.get("bar_count")
            bar_content_sha256 = item.get("bar_content_sha256")
            timestamp_set_sha256 = item.get("timestamp_set_sha256")
            if (
                not isinstance(bar_count, int)
                or bar_count < 0
                or not _is_sha256(bar_content_sha256)
                or not _is_sha256(timestamp_set_sha256)
                or item.get("timestamps_strictly_ordered_unique") is not True
                or item.get("bars_complete") is not True
                or item.get("output_timestamps_are_source_starts") is not True
                or item.get("bucket_retention")
                != "complete_unique_contiguous_source_minutes_only"
                or item.get("ohlcv_aggregation_verified") is not True
                or item.get("non_emitted_bucket_interpretation")
                != "not_emitted_from_observed_source_set"
            ):
                raise ValueError("timeframe mechanics evidence is invalid")
            evidence[timeframe] = TimeframeMechanicsEvidence(
                bar_count=bar_count,
                bar_content_sha256=bar_content_sha256,
                timestamp_set_sha256=timestamp_set_sha256,
            )
        if tuple(evidence) != _matrix_timeframes():
            raise ValueError("timeframe mechanics timeframe matrix is incomplete")
        parsed[symbol] = evidence
    if tuple(parsed) != _REQUIRED_SYMBOLS:
        raise ValueError("timeframe mechanics symbols are incomplete")
    return parsed


def _validate_resampling_contract(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("timeframe mechanics resampling contract is invalid")
    if (
        value.get("source_timeframe") != Timeframe.M1.value
        or value.get("target_timeframes")
        != [timeframe.value for timeframe in _matrix_timeframes()]
        or value.get("bucket_anchor") != "utc_epoch"
        or value.get("bucket_retention")
        != "complete_unique_contiguous_source_minutes_only"
        or value.get("reindex_or_fill") is not False
        or value.get("resampled_bars_persisted") is not False
    ):
        raise ValueError("timeframe mechanics resampling contract is unexpected")


def _validate_resampled_bars(
    bars: list[Bar],
    *,
    timeframe: Timeframe,
    evidence: TimeframeMechanicsEvidence,
) -> None:
    if len(bars) != evidence.bar_count:
        raise ValueError("resampled bar count does not match timeframe mechanics receipt")
    if any(bar.timeframe != timeframe or not bar.complete for bar in bars):
        raise ValueError("resampled bars are not complete at the declared timeframe")
    timestamps = tuple(bar.start_ts for bar in bars)
    if timestamps != tuple(sorted(set(timestamps))):
        raise ValueError("resampled timestamps are not strictly ordered and unique")
    if _timestamp_set_sha256(timestamps) != evidence.timestamp_set_sha256:
        raise ValueError("resampled timestamp set does not match timeframe mechanics receipt")
    if _bar_content_sha256(bars) != evidence.bar_content_sha256:
        raise ValueError("resampled bar content does not match timeframe mechanics receipt")


def _window_cells(
    bars: list[Bar], *, timeframe: Timeframe, lookbacks: tuple[int, ...]
) -> list[dict[str, object]]:
    if not lookbacks or tuple(sorted(set(lookbacks))) != lookbacks or any(
        lookback <= 0 for lookback in lookbacks
    ):
        raise ValueError("window lookbacks must be ordered unique positive integers")
    contiguous_count = 0
    previous_start: datetime | None = None
    counts = {lookback: 0 for lookback in lookbacks}
    hashers = {lookback: hashlib.sha256() for lookback in lookbacks}
    for bar in bars:
        if bar.timeframe != timeframe:
            raise ValueError("window bars have an unexpected timeframe")
        if not bar.complete:
            contiguous_count = 0
        elif previous_start is None or bar.start_ts - previous_start != timeframe.duration:
            contiguous_count = 1
        else:
            contiguous_count += 1
        if bar.complete:
            for lookback in lookbacks:
                if contiguous_count >= lookback:
                    counts[lookback] += 1
                    hashers[lookback].update(f"{bar.end_ts.isoformat()}\n".encode())
        previous_start = bar.start_ts
    return [
        {
            "window_size_bars": lookback,
            "eligible_window_count": counts[lookback],
            "eligible_end_timestamp_set_sha256": _SHA256_PREFIX
            + hashers[lookback].hexdigest(),
            "every_eligible_window_complete_and_strictly_contiguous": True,
        }
        for lookback in lookbacks
    ]


def _matrix_contract() -> dict[str, object]:
    return {
        "ordered_timeframes": [timeframe.value for timeframe in _matrix_timeframes()],
        "windows_by_timeframe": [
            {"timeframe": timeframe.value, "window_sizes_bars": list(lookbacks)}
            for timeframe, lookbacks in _WINDOW_MATRIX
        ],
        "window_eligibility": {
            "all_bars_complete": True,
            "adjacent_start_delta_equals_declared_timeframe": True,
            "reindex_or_fill": False,
            "rejected_window_interpretation": "source_local_geometry_only",
            "window_end_definition": "last_bar_end_ts",
        },
    }


def _matrix_timeframes() -> tuple[Timeframe, ...]:
    return tuple(timeframe for timeframe, _ in _WINDOW_MATRIX)


def _decode_json(payload_bytes: bytes, *, field_name: str) -> dict[str, object]:
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field_name} is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{field_name} must be an object")
    return payload


def _bar_content_sha256(bars: Iterable[Bar]) -> str:
    payload = [bar_to_record(bar) for bar in bars]
    return _sha256_json(payload)


def _timestamp_set_sha256(timestamps: Iterable[datetime]) -> str:
    values = tuple(timestamps)
    if values != tuple(sorted(set(values))):
        raise ValueError("timestamps must be strictly ordered and unique")
    encoded = "".join(f"{timestamp.isoformat()}\n" for timestamp in values).encode("utf-8")
    return _sha256(encoded)


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
            raise ValueError("window preflight manifest conflicts with existing evidence")
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


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(_SHA256_PREFIX)
        and len(value) == len(_SHA256_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return _sha256(encoded)


def _sha256(payload: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    main()
