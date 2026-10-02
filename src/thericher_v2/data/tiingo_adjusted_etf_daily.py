"""Offline adjusted marks from the fixed August9 Tiingo ETF snapshot.

This revised, non-PIT source supports provider-adjusted marks only. It supplies
no historical availability, execution, broker-parity or preprocessing claim.
Dividend cash and split factors must not be applied again to these marks.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from .tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    _read_snapshot_file,
    _sha256,
    _validate_existing_snapshot,
    load_verified_tiingo_etf_d1_snapshot,
    normalize_tiingo_etf_d1_response,
)

SNAPSHOT_RELATIVE_PATH = Path(
    "us_equities/tiingo_etf_daily/canonical/snapshot=20260809T163557Z-tiingo-etf-d1-r1"
)
DATASET_ID = "us_equities.tiingo_etf_daily.snapshot=20260809T163557Z-tiingo-etf-d1-r1"
DATASET_SHA256 = "sha256:becc3e4b0ed4610da9325de3e6b88d1f24f869199d3d81a285b60b1b340df0aa"
MANIFEST_SHA256 = "sha256:4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2"
RAW_SHA256: Mapping[str, str] = MappingProxyType(
    {
        "SPY": "sha256:20663908257f2bbd1c3f58d4882d0f2ddb5417f0232c5e4eba798bebc9b948d1",
        "QQQ": "sha256:e656fdadb140c06dd6228f8a87ccd092f3217a5f763f68a984e74c197e6c5554",
        "IWM": "sha256:e01df2cb4a4efd3a9006d6d0327022fdb081ddfd6e08ef6da0b72364248eb2b4",
    }
)
_ADJUSTED_FIELDS = ("adjOpen", "adjHigh", "adjLow", "adjClose")


@dataclass(frozen=True, slots=True)
class AdjustedEtfRow:
    """One provider-adjusted session mark; numeric values stay out of repr."""

    symbol: str
    session_date: date
    adj_open: Decimal = field(repr=False)
    adj_high: Decimal = field(repr=False)
    adj_low: Decimal = field(repr=False)
    adj_close: Decimal = field(repr=False)

    def __post_init__(self) -> None:
        values = (self.adj_open, self.adj_high, self.adj_low, self.adj_close)
        if (
            self.symbol not in TIINGO_ETF_D1_SYMBOLS
            or type(self.session_date) is not date
            or any(
                not isinstance(value, Decimal) or not value.is_finite() or value <= 0
                for value in values
            )
        ):
            raise ValueError("adjusted ETF row is invalid")
        if self.adj_high < max(values) or self.adj_low > min(values):
            raise ValueError("adjusted ETF OHLC geometry is invalid")


def load_verified_adjusted_etf_snapshot(
    snapshot_directory: Path,
    *,
    market_data_root: Path,
    repo_root: Path,
) -> Mapping[str, tuple[AdjustedEtfRow, ...]]:
    """Reattest the fixed source and expose immutable in-memory adjusted marks.

    UTC-midnight dates are session labels, not observed market-time clocks.
    No credentials, network, output files or mutable canonical views are used.
    """

    try:
        _unlinked_path(Path(market_data_root))
        _unlinked_path(Path(snapshot_directory))
        root, market_root = _validate_existing_snapshot(
            snapshot_directory, market_data_root=market_data_root, repo_root=repo_root
        )
        if root != market_root / SNAPSHOT_RELATIVE_PATH:
            raise ValueError("adjusted ETF snapshot identity is invalid")
        sources = (
            root / "manifest.json",
            root / "ohlcv_1d.csv.gz",
            *(root / "raw" / f"{symbol}.json" for symbol in TIINGO_ETF_D1_SYMBOLS),
        )
        for path in sources:
            _unlinked_file(path)

        verified = load_verified_tiingo_etf_d1_snapshot(
            root,
            dataset_id=DATASET_ID,
            expected_dataset_hash=DATASET_SHA256,
            expected_manifest_hash=MANIFEST_SHA256,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
        if set(verified.rows_by_symbol) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("adjusted ETF canonical identity is invalid")
        result = {}
        for symbol in TIINGO_ETF_D1_SYMBOLS:
            path = root / "raw" / f"{symbol}.json"
            _unlinked_file(path)
            raw = _read_snapshot_file(root, path, symbol)
            _unlinked_file(path)
            if _sha256(raw) != RAW_SHA256[symbol]:
                raise ValueError("adjusted ETF raw identity is invalid")
            canonical = verified.rows_by_symbol[symbol]
            result[symbol] = _adjusted_rows(symbol, raw, canonical)
        for path in sources:
            _unlinked_file(path)
        return MappingProxyType(result)
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
        raise ValueError("adjusted ETF snapshot verification failed") from None


def _adjusted_rows(symbol: str, raw: bytes, canonical) -> tuple[AdjustedEtfRow, ...]:
    payload = json.loads(
        raw.decode("utf-8"),
        parse_float=Decimal,
        parse_int=Decimal,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(payload, list) or not payload or len(payload) != len(canonical):
        raise ValueError("adjusted ETF row count is invalid")
    rows = []
    previous = None
    for item, original in zip(payload, canonical, strict=True):
        if not isinstance(item, dict):
            raise ValueError("adjusted ETF row shape is invalid")
        session = original.session_date
        if (
            original.symbol != symbol
            or type(session) is not date
            or item.get("date") != f"{session.isoformat()}T00:00:00.000Z"
            or (previous is not None and session <= previous)
            or any(item[key] != symbol for key in ("symbol", "ticker") if key in item)
        ):
            raise ValueError("adjusted ETF session identity is invalid")
        rows.append(
            AdjustedEtfRow(
                symbol, session, *(_positive_decimal(item.get(key)) for key in _ADJUSTED_FIELDS)
            )
        )
        previous = session
    # Recheck the raw stream too: the upstream verifier deliberately drops adjusted fields.
    if normalize_tiingo_etf_d1_response(symbol=symbol, raw_response=raw) != tuple(canonical):
        raise ValueError("adjusted ETF canonical stream differs")
    return tuple(rows)


def _positive_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("adjusted ETF numeric field is invalid")
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("adjusted ETF numeric field is invalid")
    return number


def _reject_constant(_value: str):
    raise ValueError("adjusted ETF JSON constant is invalid")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("adjusted ETF JSON field is duplicated")
        result[key] = value
    return result


def _unlinked_path(path: Path) -> None:
    if ".." in path.parts:
        raise ValueError("adjusted ETF path is invalid")
    absolute = path.absolute()
    for entry in (*reversed(absolute.parents), absolute):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ) or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
            raise ValueError("adjusted ETF source links are not allowed")


def _unlinked_file(path: Path) -> None:
    _unlinked_path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("adjusted ETF source must be a regular file")
