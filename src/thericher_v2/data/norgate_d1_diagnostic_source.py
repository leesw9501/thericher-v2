"""Offline-only diagnostic loader for one verified Norgate raw-D1 snapshot."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_trial_raw_d1 import (
    DEFAULT_MARKET_DATA_ROOT,
    FIXED_NORGATE_TRIAL_SYMBOLS,
    NorgateTrialRawD1Result,
    verify_norgate_trial_raw_d1_snapshot,
)

_DATA_FILE = "norgate_ohlcv_1d.csv.gz"
_DATA_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True, slots=True)
class VerifiedNorgateD1Panel:
    """A verified, in-memory diagnostic view of the fixed ETF daily panel."""

    source_result: NorgateTrialRawD1Result
    common_sessions: tuple[date, ...]
    bars_by_symbol: Mapping[str, tuple[Bar, ...]]


def load_verified_norgate_d1_diagnostic_panel(
    snapshot_dir: Path,
    *,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> VerifiedNorgateD1Panel:
    """Load one hash-attested local D1 panel without provider or environment access."""

    source_result = verify_norgate_trial_raw_d1_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    if source_result.dataset_hash != expected_dataset_hash:
        raise ValueError("Norgate D1 diagnostic dataset hash mismatch")
    if source_result.manifest_hash != expected_manifest_hash:
        raise ValueError("Norgate D1 diagnostic manifest hash mismatch")

    bars_by_symbol = _load_panel_rows(source_result)
    common_sessions = _validate_panel_rows(bars_by_symbol, source_result=source_result)
    return VerifiedNorgateD1Panel(
        source_result=source_result,
        common_sessions=common_sessions,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
    )


def _load_panel_rows(source_result: NorgateTrialRawD1Result) -> dict[str, tuple[Bar, ...]]:
    data_path = source_result.snapshot_dir / _DATA_FILE
    if data_path.is_symlink() or not data_path.resolve(strict=False).is_relative_to(
        source_result.snapshot_dir
    ):
        raise ValueError("Norgate D1 diagnostic raw data path is invalid")
    try:
        resolved_data_path = data_path.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError("Norgate D1 diagnostic raw data is unavailable") from exc
    if not resolved_data_path.is_file() or not resolved_data_path.is_relative_to(
        source_result.snapshot_dir
    ):
        raise ValueError("Norgate D1 diagnostic raw data path is invalid")
    try:
        data = resolved_data_path.read_bytes()
    except OSError as exc:
        raise ValueError("Norgate D1 diagnostic raw data is unavailable") from exc
    if f"sha256:{hashlib.sha256(data).hexdigest()}" != source_result.dataset_hash:
        raise ValueError("Norgate D1 diagnostic raw data hash mismatch")

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                if tuple(reader.fieldnames or ()) != _DATA_COLUMNS:
                    raise ValueError("Norgate D1 diagnostic CSV schema is invalid")
                source_rows = tuple(reader)
    except (EOFError, OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate D1 diagnostic raw data is invalid") from exc

    grouped: dict[str, list[Bar]] = {symbol: [] for symbol in FIXED_NORGATE_TRIAL_SYMBOLS}
    for row in source_rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Norgate D1 diagnostic CSV row is invalid")
        symbol = str(row["symbol"]).strip().upper()
        if symbol not in grouped:
            raise ValueError("Norgate D1 diagnostic symbols are invalid")
        grouped[symbol].append(_bar_from_row(symbol, row))
    return {symbol: tuple(grouped[symbol]) for symbol in FIXED_NORGATE_TRIAL_SYMBOLS}


def _bar_from_row(symbol: str, row: Mapping[str | None, str | None]) -> Bar:
    session = _session_date(row.get("date"))
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime.combine(session, datetime.min.time(), UTC),
        open=_decimal(row.get("open")),
        high=_decimal(row.get("high")),
        low=_decimal(row.get("low")),
        close=_decimal(row.get("close")),
        volume=_decimal(row.get("volume")),
        complete=True,
    )


def _validate_panel_rows(
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
    *,
    source_result: NorgateTrialRawD1Result,
) -> tuple[date, ...]:
    if tuple(bars_by_symbol) != FIXED_NORGATE_TRIAL_SYMBOLS:
        raise ValueError("Norgate D1 diagnostic symbols are incomplete")
    if any(not bars_by_symbol[symbol] for symbol in FIXED_NORGATE_TRIAL_SYMBOLS):
        raise ValueError("Norgate D1 diagnostic symbols are incomplete")

    common_sessions = _sessions_for(bars_by_symbol[FIXED_NORGATE_TRIAL_SYMBOLS[0]])
    if any(
        _sessions_for(bars_by_symbol[symbol]) != common_sessions
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS[1:]
    ):
        raise ValueError("Norgate D1 diagnostic sessions are not aligned")
    expected_row_count = len(common_sessions) * len(FIXED_NORGATE_TRIAL_SYMBOLS)
    if (
        len(common_sessions) != source_result.common_session_count
        or expected_row_count != source_result.row_count
    ):
        raise ValueError("Norgate D1 diagnostic rows are incomplete")
    return common_sessions


def _sessions_for(bars: tuple[Bar, ...]) -> tuple[date, ...]:
    sessions: list[date] = []
    previous: date | None = None
    for bar in bars:
        if (
            bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo is None
            or bar.start_ts.utcoffset() != UTC.utcoffset(bar.start_ts)
            or bar.start_ts.time() != datetime.min.time()
        ):
            raise ValueError("Norgate D1 diagnostic bar contract is invalid")
        session = bar.start_ts.date()
        if previous is not None and session <= previous:
            raise ValueError("Norgate D1 diagnostic sessions are not strictly increasing")
        sessions.append(session)
        previous = session
    return tuple(sessions)


def _session_date(value: str | None) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("Norgate D1 diagnostic session is invalid") from exc


def _decimal(value: str | None) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Norgate D1 diagnostic price is invalid") from exc
    if not result.is_finite():
        raise ValueError("Norgate D1 diagnostic price is invalid")
    return result
