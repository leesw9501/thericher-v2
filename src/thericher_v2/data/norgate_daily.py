"""Host-only raw daily bars from an installed Norgate Data client.

This adapter intentionally leaves Norgate data in process.  It is not a
catalog, cache, Docker bridge, or research-data promotion path.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.provider import BarQuery, filter_bars

_REQUIRED_FIELDS = ("Date", "Open", "High", "Low", "Close", "Volume")


class NorgateUnavailableError(RuntimeError):
    """Raised when the host-only Norgate client cannot serve a daily query."""


class NorgateClientUnavailableError(NorgateUnavailableError):
    """Raised when the optional official Norgate Python client is absent."""


class NorgateLocalUpdaterUnavailableError(NorgateUnavailableError):
    """Raised when the installed local Norgate service cannot serve a query."""


class NorgateMalformedResponseError(NorgateUnavailableError, ValueError):
    """Raised when a local Norgate response violates the bounded D1 contract."""


def _load_norgatedata() -> Any:
    try:
        return importlib.import_module("norgatedata")
    except ModuleNotFoundError as exc:
        raise NorgateClientUnavailableError(
            "Norgate Python client is unavailable; use the host-only norgate-host extra"
        ) from exc


@dataclass(frozen=True)
class NorgateRawDailyBarProvider:
    """Map one bounded raw US daily query to engine-native ``Bar`` values.

    Norgate session dates do not carry an intraday timestamp in this adapter.
    They are labeled as UTC midnight only to match the existing ``D1`` ``Bar``
    convention; that label is not a claim about exchange-session timing.
    """

    market: str = "US"
    client_loader: Callable[[], Any] = field(
        default=_load_norgatedata,
        repr=False,
        compare=False,
    )
    platform_name: str = field(default=sys.platform, repr=False, compare=False)

    def __post_init__(self) -> None:
        market = self.market.strip().upper()
        if market != "US":
            raise ValueError("Norgate raw-daily provider supports only US market")
        object.__setattr__(self, "market", market)

    def get_bars(self, query: BarQuery) -> list[Bar]:
        self._validate_query(query)
        client, adjustment, padding = self._load_client()
        assert query.start_ts is not None
        assert query.end_ts is not None
        try:
            rows = client.price_timeseries(
                query.symbol,
                stock_price_adjustment_setting=adjustment,
                padding_setting=padding,
                start_date=query.start_ts.date().isoformat(),
                end_date=(query.end_ts - timedelta(days=1)).date().isoformat(),
                timeseriesformat="numpy-recarray",
                interval="D",
            )
        except Exception as exc:
            raise NorgateLocalUpdaterUnavailableError(
                "Norgate local updater or daily data is unavailable"
            ) from exc
        try:
            return filter_bars(_map_rows(rows, query), query)
        except ValueError as exc:
            raise NorgateMalformedResponseError("Norgate daily response is malformed") from exc

    def _validate_query(self, query: BarQuery) -> None:
        if self.platform_name != "win32":
            raise NorgateUnavailableError("Norgate raw-daily provider requires Windows")
        if query.market != self.market:
            raise ValueError("Norgate raw-daily provider supports only US queries")
        if query.timeframe != Timeframe.D1:
            raise ValueError("Norgate raw-daily provider supports only 1d queries")
        if not query.symbol:
            raise ValueError("Norgate raw-daily provider requires a symbol")
        if query.start_ts is None or query.end_ts is None:
            raise ValueError("Norgate raw-daily provider requires bounded dates")
        if not _is_utc_midnight(query.start_ts) or not _is_utc_midnight(query.end_ts):
            raise ValueError("Norgate raw-daily provider requires UTC-midnight bounds")

    def _load_client(self) -> tuple[Any, Any, Any]:
        try:
            client = self.client_loader()
            adjustment = client.StockPriceAdjustmentType.NONE
            padding = client.PaddingType.NONE
        except NorgateClientUnavailableError:
            raise
        except ModuleNotFoundError as exc:
            raise NorgateClientUnavailableError(
                "Norgate Python client is unavailable; use the host-only norgate-host extra"
            ) from exc
        except Exception as exc:
            raise NorgateLocalUpdaterUnavailableError(
                "Norgate local updater or daily data is unavailable"
            ) from exc
        return client, adjustment, padding


def _is_utc_midnight(value: datetime) -> bool:
    return value.tzinfo == UTC and (
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
    ) == (0, 0, 0, 0)


def _map_rows(rows: Any, query: BarQuery) -> list[Bar]:
    fields = tuple(getattr(getattr(rows, "dtype", None), "names", ()) or ())
    if not fields:
        raise ValueError("Norgate daily response must use numpy-recarray fields")
    missing = [field_name for field_name in _REQUIRED_FIELDS if field_name not in fields]
    if missing:
        raise ValueError("Norgate daily response is missing required OHLCV fields")

    assert query.start_ts is not None
    assert query.end_ts is not None
    bars: list[Bar] = []
    previous_start: datetime | None = None
    for row in rows:
        start_ts = datetime.combine(
            _session_date(_row_value(row, "Date")),
            datetime.min.time(),
            UTC,
        )
        if start_ts < query.start_ts or start_ts >= query.end_ts:
            raise ValueError("Norgate daily response is outside the requested window")
        if previous_start is not None and start_ts <= previous_start:
            raise ValueError("Norgate daily response must be strictly ordered")
        bars.append(
            Bar(
                symbol=query.symbol,
                market=query.market,
                timeframe=Timeframe.D1,
                start_ts=start_ts,
                open=str(_row_value(row, "Open")),
                high=str(_row_value(row, "High")),
                low=str(_row_value(row, "Low")),
                close=str(_row_value(row, "Close")),
                volume=str(_row_value(row, "Volume")),
            )
        )
        previous_start = start_ts
    return bars


def _row_value(row: Any, field_name: str) -> Any:
    try:
        return row[field_name]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("Norgate daily response has an unreadable OHLCV field") from exc


def _session_date(value: Any) -> date:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bytes):
        value = value.decode("ascii")
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValueError("Norgate daily response has an invalid session date") from exc
    raise ValueError("Norgate daily response has an invalid session date")
