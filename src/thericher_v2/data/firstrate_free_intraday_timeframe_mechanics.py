"""Source-safe timeframe mechanics for normalized FirstRate free M1 bars."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import LocalCsvBarProvider, bar_to_record
from thericher_v2.data.provider import BarQuery
from thericher_v2.data.resample import resample_bars

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_NORMALIZATION_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/firstrate-free-intraday-source-local-normalization-v1.json"
)
_MECHANICS_MANIFEST_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/firstrate-free-intraday-source-local-timeframe-mechanics-v1.json"
)
_REQUIRED_SYMBOLS = ("SPY", "QQQ")
_TARGET_TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)
_NORMALIZATION_SCHEMA_VERSION = "firstrate-free-intraday-normalization-receipt-v1"
_MECHANICS_SCHEMA_VERSION = "firstrate-free-intraday-source-local-timeframe-mechanics-v1"
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True)
class FirstRateCanonicalSpec:
    """Safe identity for one normalized FirstRate M1 CSV."""

    symbol: str
    market: str
    canonical_market_data_relative_path: Path
    canonical_sha256: str
    bar_count: int
    emitted_timestamp_set_sha256: str


def build_firstrate_source_local_timeframe_mechanics(
    *,
    market_data_root: Path | str,
    artifact_root: Path | str,
    normalization_receipt_path: Path | str | None = None,
    mechanics_manifest_path: Path | str | None = None,
) -> dict[str, object]:
    """Validate in-memory source-local resampling and write only aggregates."""

    resolved_market_data_root = _require_external_root(
        market_data_root, field_name="market_data_root"
    )
    resolved_artifact_root = _require_external_root(artifact_root, field_name="artifact_root")
    resolved_normalization_path = _path_within_root(
        resolved_artifact_root,
        normalization_receipt_path
        or resolved_artifact_root / _NORMALIZATION_RECEIPT_RELATIVE_PATH,
        field_name="normalization_receipt_path",
    )
    resolved_manifest_path = _path_within_root(
        resolved_artifact_root,
        mechanics_manifest_path
        or resolved_artifact_root / _MECHANICS_MANIFEST_RELATIVE_PATH,
        field_name="mechanics_manifest_path",
    )

    normalization_bytes = resolved_normalization_path.read_bytes()
    specs = _parse_normalization_receipt(normalization_bytes)
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
        _validate_source_bars(source_bars, spec)
        timeframes = [
            _timeframe_payload(source_bars, timeframe) for timeframe in _TARGET_TIMEFRAMES
        ]
        symbols.append(
            {
                "symbol": spec.symbol,
                "market": spec.market,
                "canonical_market_data_relative_path": (
                    spec.canonical_market_data_relative_path.as_posix()
                ),
                "canonical_sha256": spec.canonical_sha256,
                "canonical_hash_matches_normalization_receipt": True,
                "source_bar_count": len(source_bars),
                "source_timestamp_set_sha256": spec.emitted_timestamp_set_sha256,
                "source_timestamps_strictly_ordered_unique": True,
                "source_bars_complete": True,
                "timeframes": timeframes,
            }
        )

    payload: dict[str, object] = {
        "schema_version": _MECHANICS_SCHEMA_VERSION,
        "receipt_id": "firstrate-free-intraday-source-local-timeframe-mechanics-v1",
        "status": "completed",
        "normalization_receipt": {
            "relative_to_artifact_root": True,
            "path": _relative_posix(resolved_artifact_root, resolved_normalization_path),
            "sha256": _sha256(normalization_bytes),
        },
        "symbols": symbols,
        "resampling_contract": {
            "source_timeframe": Timeframe.M1.value,
            "target_timeframes": [timeframe.value for timeframe in _TARGET_TIMEFRAMES],
            "bucket_anchor": "utc_epoch",
            "bucket_retention": "complete_unique_contiguous_source_minutes_only",
            "reindex_or_fill": False,
            "resampled_bars_persisted": False,
        },
        "safety": {
            "credentials_read": False,
            "network_access": False,
            "kis_or_broker_called": False,
            "raw_market_rows_retained_in_manifest": False,
            "market_data_written_outside_market_data_root": False,
            "git_tracked_files_changed": False,
        },
        "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
        "limitations": [
            "source_timestamp_semantics_unverified",
            "session_coverage_not_assessed",
            "no_kis_parity",
            "decision_time_availability_not_observed",
            "provider_finality_not_observed",
            "not_a_model_campaign_or_paper_input",
        ],
    }
    _write_or_verify(resolved_manifest_path, payload)
    return {
        "status": "completed",
        "manifest_path_relative_to_artifact_root": _relative_posix(
            resolved_artifact_root, resolved_manifest_path
        ),
        "symbols": symbols,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--normalization-receipt", type=Path)
    parser.add_argument("--mechanics-manifest", type=Path)
    args = parser.parse_args(argv)
    result = build_firstrate_source_local_timeframe_mechanics(
        market_data_root=args.market_data_root,
        artifact_root=args.artifact_root,
        normalization_receipt_path=args.normalization_receipt,
        mechanics_manifest_path=args.mechanics_manifest,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


def parse_firstrate_normalization_receipt(
    payload_bytes: bytes,
) -> tuple[FirstRateCanonicalSpec, ...]:
    """Parse the source-local normalization receipt for another offline consumer."""

    return _parse_normalization_receipt(payload_bytes)


def validate_firstrate_canonical_bars(
    bars: list[Bar], spec: FirstRateCanonicalSpec
) -> None:
    """Reattest one canonical FirstRate stream without accessing a provider."""

    _validate_source_bars(bars, spec)


def _parse_normalization_receipt(payload_bytes: bytes) -> tuple[FirstRateCanonicalSpec, ...]:
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("normalization receipt is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("normalization receipt must be an object")
    if payload.get("schema_version") != _NORMALIZATION_SCHEMA_VERSION:
        raise ValueError("normalization receipt schema version is unexpected")
    if payload.get("status") != "completed":
        raise ValueError("normalization receipt status is unexpected")
    if payload.get("permitted_interpretation") != "source_isolated_retrospective_mechanics_only":
        raise ValueError("normalization receipt interpretation is unexpected")
    normalizations = payload.get("normalizations")
    if not isinstance(normalizations, list):
        raise ValueError("normalization receipt normalizations must be a list")

    specs: dict[str, FirstRateCanonicalSpec] = {}
    for normalization in normalizations:
        if not isinstance(normalization, dict):
            raise ValueError("normalization receipt item must be an object")
        symbol = normalization.get("symbol")
        market = normalization.get("market")
        canonical_path = normalization.get("canonical_market_data_relative_path")
        canonical_sha256 = normalization.get("canonical_sha256")
        bar_count = normalization.get("bar_count")
        timestamp_set_sha256 = normalization.get("emitted_timestamp_set_sha256")
        if not isinstance(symbol, str) or symbol not in _REQUIRED_SYMBOLS:
            raise ValueError("normalization receipt symbol is unexpected")
        if symbol in specs:
            raise ValueError("normalization receipt has duplicate symbols")
        if market != "US" or normalization.get("timeframe") != Timeframe.M1.value:
            raise ValueError("normalization receipt stream identity is unexpected")
        if normalization.get("timestamp_set_equal") is not True:
            raise ValueError("normalization receipt timestamp-set equality is missing")
        if not isinstance(canonical_path, str):
            raise ValueError("normalization receipt canonical path is invalid")
        if not isinstance(canonical_sha256, str) or not _is_sha256(canonical_sha256):
            raise ValueError("normalization receipt canonical hash is invalid")
        if not isinstance(timestamp_set_sha256, str) or not _is_sha256(timestamp_set_sha256):
            raise ValueError("normalization receipt timestamp-set hash is invalid")
        if not isinstance(bar_count, int) or bar_count <= 0:
            raise ValueError("normalization receipt bar count is invalid")
        specs[symbol] = FirstRateCanonicalSpec(
            symbol=symbol,
            market=market,
            canonical_market_data_relative_path=_relative_path(
                canonical_path, field_name="canonical path"
            ),
            canonical_sha256=canonical_sha256,
            bar_count=bar_count,
            emitted_timestamp_set_sha256=timestamp_set_sha256,
        )
    if set(specs) != set(_REQUIRED_SYMBOLS):
        raise ValueError("normalization receipt must contain exactly SPY and QQQ")
    return tuple(specs[symbol] for symbol in _REQUIRED_SYMBOLS)


def _validate_source_bars(bars: list[Bar], spec: FirstRateCanonicalSpec) -> None:
    if len(bars) != spec.bar_count:
        raise ValueError("canonical provider row count does not match normalization receipt")
    if not bars or any(not bar.complete for bar in bars):
        raise ValueError("canonical provider has incomplete source bars")
    if any(
        bar.symbol != spec.symbol
        or bar.market != spec.market
        or bar.timeframe != Timeframe.M1
        for bar in bars
    ):
        raise ValueError("canonical provider stream identity is invalid")
    timestamps = tuple(bar.start_ts for bar in bars)
    if timestamps != tuple(sorted(set(timestamps))):
        raise ValueError("canonical provider timestamps are not strictly ordered and unique")
    if _timestamp_set_sha256(timestamps) != spec.emitted_timestamp_set_sha256:
        raise ValueError("canonical provider timestamp set does not match normalization receipt")


def _timeframe_payload(source_bars: list[Bar], timeframe: Timeframe) -> dict[str, object]:
    ordered_source_bars = sorted(source_bars, key=lambda bar: bar.start_ts)
    bars = resample_bars(ordered_source_bars, timeframe)
    timestamps = tuple(bar.start_ts for bar in bars)
    source_timestamps = {bar.start_ts for bar in ordered_source_bars}
    if timestamps != tuple(sorted(set(timestamps))):
        raise RuntimeError("resampled timestamps are not strictly ordered and unique")
    if any(not bar.complete or bar.timeframe != timeframe for bar in bars):
        raise RuntimeError("resampled bars are not complete at the requested timeframe")
    if not set(timestamps).issubset(source_timestamps):
        raise RuntimeError("resampled bars contain a timestamp not present in the source")
    _validate_resampled_ohlcv(ordered_source_bars, bars, timeframe)
    return {
        "timeframe": timeframe.value,
        "bar_count": len(bars),
        "bar_content_sha256": _bar_content_sha256(bars),
        "timestamp_set_sha256": _timestamp_set_sha256(timestamps),
        "timestamps_strictly_ordered_unique": True,
        "bars_complete": True,
        "output_timestamps_are_source_starts": True,
        "bucket_retention": "complete_unique_contiguous_source_minutes_only",
        "ohlcv_aggregation_verified": True,
        "non_emitted_bucket_interpretation": "not_emitted_from_observed_source_set",
    }


def _validate_resampled_ohlcv(
    source_bars: list[Bar],
    resampled_bars: list[Bar],
    timeframe: Timeframe,
) -> None:
    if timeframe == Timeframe.M1:
        if tuple(resampled_bars) != tuple(source_bars):
            raise RuntimeError("M1 resampling changed the complete unique source stream")
        return

    source_by_timestamp = {bar.start_ts: bar for bar in source_bars}
    source_duration = Timeframe.M1.duration
    expected_count = int(timeframe.duration // source_duration)
    for bar in resampled_bars:
        bucket = tuple(
            source_by_timestamp.get(bar.start_ts + source_duration * offset)
            for offset in range(expected_count)
        )
        if any(source is None for source in bucket):
            raise RuntimeError("resampled bar was emitted from an incomplete source bucket")
        source_bucket = tuple(source for source in bucket if source is not None)
        if (
            bar.symbol != source_bucket[0].symbol
            or bar.market != source_bucket[0].market
            or bar.open != source_bucket[0].open
            or bar.high != max(source.high for source in source_bucket)
            or bar.low != min(source.low for source in source_bucket)
            or bar.close != source_bucket[-1].close
            or bar.volume != sum((source.volume for source in source_bucket), Decimal("0"))
        ):
            raise RuntimeError("resampled OHLCV does not match its source bucket")


def _bar_content_sha256(bars: Iterable[Bar]) -> str:
    payload = [bar_to_record(bar) for bar in bars]
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return _sha256(encoded)


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
            raise ValueError("timeframe mechanics manifest conflicts with existing evidence")
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
