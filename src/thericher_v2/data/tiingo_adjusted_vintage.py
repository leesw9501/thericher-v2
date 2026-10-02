"""Offline provider-adjusted marks from one explicitly pinned Tiingo vintage.

Use this one mapping for all feature context, return anchors and payoffs; never
splice adjusted marks from another vintage. Revised marks are not historical
PIT, availability, finality or broker-parity evidence. Do not add dividend cash
or split factors again. No output files, credentials or network are used.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import InvalidOperation
from pathlib import Path
from types import MappingProxyType

from .tiingo_adjusted_etf_daily import (
    AdjustedEtfRow,
    _adjusted_rows,
    _unlinked_file,
    _unlinked_path,
)
from .tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    _read_snapshot_file,
    _require_sha256,
    _sha256,
    _validate_existing_snapshot,
    load_verified_tiingo_etf_d1_snapshot,
)


def load_verified_adjusted_etf_vintage(
    snapshot_directory: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    expected_raw_hashes: Mapping[str, str],
    market_data_root: Path,
    repo_root: Path,
) -> Mapping[str, tuple[AdjustedEtfRow, ...]]:
    """Verify one caller-bound snapshot and expose immutable Decimal marks.

    There is no default vintage or fallback to the frozen August9 snapshot.
    UTC-midnight labels identify sessions, not observed availability clocks.
    Coverage requirements and exclusive consumer use remain caller-owned.
    """

    try:
        if not isinstance(expected_raw_hashes, Mapping):
            raise ValueError("adjusted vintage raw pins are invalid")
        raw_pins = dict(expected_raw_hashes)
        if set(raw_pins) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("adjusted vintage raw pin scope is invalid")
        for pin in raw_pins.values():
            _require_sha256(pin, "adjusted vintage raw hash")

        _unlinked_path(Path(market_data_root))
        _unlinked_path(Path(snapshot_directory))
        root, market_root = _validate_existing_snapshot(
            snapshot_directory, market_data_root=market_data_root, repo_root=repo_root
        )
        if root.parent != market_root / "us_equities" / "tiingo_etf_daily" / "canonical":
            raise ValueError("adjusted vintage snapshot location is invalid")
        sources = (
            root / "manifest.json",
            root / "ohlcv_1d.csv.gz",
            *(root / "raw" / f"{symbol}.json" for symbol in TIINGO_ETF_D1_SYMBOLS),
        )
        for path in sources:
            _unlinked_file(path)

        verified = load_verified_tiingo_etf_d1_snapshot(
            root,
            dataset_id=dataset_id,
            expected_dataset_hash=expected_dataset_hash,
            expected_manifest_hash=expected_manifest_hash,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
        if (
            set(verified.rows_by_symbol) != set(TIINGO_ETF_D1_SYMBOLS)
            or dict(verified.snapshot.raw_hashes) != raw_pins
        ):
            raise ValueError("adjusted vintage source binding differs")
        result = {}
        for symbol in TIINGO_ETF_D1_SYMBOLS:
            path = root / "raw" / f"{symbol}.json"
            _unlinked_file(path)
            raw = _read_snapshot_file(root, path, symbol)
            _unlinked_file(path)
            if _sha256(raw) != raw_pins[symbol]:
                raise ValueError("adjusted vintage raw binding differs")
            result[symbol] = _adjusted_rows(symbol, raw, verified.rows_by_symbol[symbol])
        for path in sources:
            _unlinked_file(path)
        return MappingProxyType(result)
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
        raise ValueError("adjusted ETF vintage verification failed") from None
