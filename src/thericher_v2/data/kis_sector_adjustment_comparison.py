"""Pure fixed-sector CLOSE diagnostic, not adjustment/TR/PIT qualification.

Caller owns response/query/source/time binding. Native daily DTOs imply GUBN0;
response continuation availability is allowed, but no continuation query is.
Repeated MODP0 pages must have identical canonical OHLCV strings by date.
MODP1 numerical equality ignores formatting; its pre-event half-cent signature
is empirical, not a claim about the provider's rounding or adjustment policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from fractions import Fraction

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_MAX_ROWS,
    SCHEMA_VERSION,
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
)

SYMBOLS = ("XLK", "XLE")
ANCHOR = "20251205"
PRE_TARGET = "20251204"
_FIELDS = ("open", "high", "low", "clos", "tvol")
_HALF_CENT = Fraction(1, 200)
_STATUSES = (
    "unchanged",
    "consistent_with_half_split_signature",
    "changed_other_pattern",
    "input_unavailable",
    "nonrepeatable",
)
_REASONS = (
    "six_page_tuple_required",
    "page_invalid",
    "query_invalid",
    "row_invalid",
    "date_invalid",
    "duplicate_date",
    "event_dates_missing",
    "page_bounds_invalid",
    "date_sets_mismatch",
    "raw_canonical_changed",
)


class _Invalid(ValueError):
    """Fixed categories only; input values are never attached to the exception."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise _Invalid(reason)


@dataclass(frozen=True, slots=True)
class KisSectorAdjustmentComparison:
    symbol: str
    status: str
    reason: str | None = None
    date_count: int = 0
    pre_event_count: int = 0
    post_event_count: int = 0
    changed_close_count: int = 0
    half_signature_count: int = 0
    post_changed_count: int = 0
    raw_repeatable: bool | None = None

    def __post_init__(self) -> None:
        _require(
            type(self.symbol) is str
            and self.symbol in SYMBOLS
            and type(self.status) is str
            and self.status in _STATUSES
            and (self.reason is None or type(self.reason) is str and self.reason in _REASONS)
            and (self.raw_repeatable is None or type(self.raw_repeatable) is bool),
            "result_invalid",
        )
        counts = (
            self.date_count,
            self.pre_event_count,
            self.post_event_count,
            self.changed_close_count,
            self.half_signature_count,
            self.post_changed_count,
        )
        _require(
            all(type(v) is int and 0 <= v <= KIS_PAPER_DAILY_MAX_ROWS for v in counts)
            and self.pre_event_count + self.post_event_count == self.date_count
            and self.changed_close_count <= self.date_count
            and self.half_signature_count <= self.pre_event_count
            and self.post_changed_count <= self.post_event_count,
            "result_invalid",
        )

    def safe_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "kind": "kis_sector_adjustment_comparison_v1",
            "symbol": self.symbol,
            "status": self.status,
            "reason": self.reason,
            "date_count": self.date_count,
            "pre_event_count": self.pre_event_count,
            "post_event_count": self.post_event_count,
            "changed_close_count": self.changed_close_count,
            "half_signature_count": self.half_signature_count,
            "post_changed_count": self.post_changed_count,
            "raw_repeatable": self.raw_repeatable,
            "split_methodology_proven": False,
            "dividend_total_return_PIT_finality_claimed": False,
        }


def _number(text: object) -> Fraction:
    _require(type(text) is str and bool(text) and text == text.strip(), "row_invalid")
    try:
        with localcontext():
            value = Decimal(text)
    except DecimalException:
        raise _Invalid("row_invalid") from None
    _require(value.is_finite(), "row_invalid")
    return Fraction(value)


def _page(raw: object, symbol: str, mode: str) -> dict[str, tuple[str, ...]]:
    _require(type(raw) is KisPaperDailyRawPage, "page_invalid")
    metadata = raw.page
    _require(type(metadata) is KisPaperDailyPage, "page_invalid")
    query = metadata.query
    _require(
        type(query) in (KisPaperDailyQuery, KisPaperDailyAdjustmentProbeQuery)
        and query.symbol == symbol
        and query.exchange == "AMS"
        and query.by_date == ANCHOR
        and query.continuation is None
        and query.adjustment_mode == mode
        and "AMS" in query.approved_symbol_exchanges.get(symbol, ()),
        "query_invalid",
    )
    _require(
        type(raw.rows) is tuple
        and type(metadata.row_count) is int
        and 2 <= metadata.row_count == len(raw.rows) <= KIS_PAPER_DAILY_MAX_ROWS
        and metadata.required_ohlcv_fields_present is True
        and type(metadata.schema_version) is int
        and metadata.schema_version == SCHEMA_VERSION
        and type(metadata.continuation_available) is bool
        and metadata.continuation_value in (None, "F")
        and metadata.continuation_available == (metadata.continuation_value == "F"),
        "page_invalid",
    )
    rows = {}
    for row in raw.rows:
        _require(type(row) is KisPaperDailyRawRow, "row_invalid")
        day = row.xymd
        _require(
            type(day) is str and len(day) == 8 and day.isascii() and day.isdigit(),
            "date_invalid",
        )
        parsed = date(int(day[:4]), int(day[4:6]), int(day[6:]))
        _require(parsed.strftime("%Y%m%d") == day and day <= ANCHOR, "date_invalid")
        _require(day not in rows, "duplicate_date")
        _require(
            type(row.schema_version) is int and row.schema_version == SCHEMA_VERSION, "row_invalid"
        )
        texts = tuple(getattr(row, field) for field in _FIELDS)
        opening, high, low, close, volume = tuple(_number(text) for text in texts)
        _require(
            min(opening, high, low, close) > 0
            and volume >= 0
            and high >= max(opening, close)
            and low <= min(opening, close),
            "row_invalid",
        )
        rows[day] = texts
    _require({PRE_TARGET, ANCHOR} <= rows.keys(), "event_dates_missing")
    _require(
        metadata.oldest_date == min(rows) and metadata.newest_date == max(rows),
        "page_bounds_invalid",
    )
    return rows


def _compare(pages: tuple[object, ...], symbol: str) -> KisSectorAdjustmentComparison:
    try:
        first, adjusted, repeated = tuple(
            _page(page, symbol, mode) for page, mode in zip(pages, ("0", "1", "0"), strict=True)
        )
        _require(first.keys() == adjusted.keys() == repeated.keys(), "date_sets_mismatch")
        days = sorted(first)
        pre = [day for day in days if day < ANCHOR]
        post = [day for day in days if day >= ANCHOR]
        counts = dict(date_count=len(days), pre_event_count=len(pre), post_event_count=len(post))
        if first != repeated:
            return KisSectorAdjustmentComparison(
                symbol, "nonrepeatable", "raw_canonical_changed", **counts, raw_repeatable=False
            )
        raw_close = {day: _number(first[day][3]) for day in days}
        changed_close = {day: _number(adjusted[day][3]) for day in days}
        changed = sum(raw_close[day] != changed_close[day] for day in days)
        half_matches = sum(
            abs(changed_close[day] - raw_close[day] / 2) <= _HALF_CENT for day in pre
        )
        post_changed = sum(raw_close[day] != changed_close[day] for day in post)
        status = (
            "unchanged"
            if not changed
            else "consistent_with_half_split_signature"
            if half_matches == len(pre) and not post_changed
            else "changed_other_pattern"
        )
        return KisSectorAdjustmentComparison(
            symbol,
            status,
            **counts,
            changed_close_count=changed,
            half_signature_count=half_matches,
            post_changed_count=post_changed,
            raw_repeatable=True,
        )
    except _Invalid as error:
        reason = str(error)
    except (ValueError, TypeError, AttributeError, KeyError, DecimalException, OverflowError):
        reason = "page_invalid"
    return KisSectorAdjustmentComparison(symbol, "input_unavailable", reason)


def compare_kis_sector_adjustment_pages(
    pages: tuple[KisPaperDailyRawPage, ...],
) -> tuple[KisSectorAdjustmentComparison, KisSectorAdjustmentComparison]:
    """Exactly XLK/AMS0,1,0 then XLE/AMS0,1,0; no I/O or input mutation.

    A malformed symbol's triple is unavailable without invalidating the other
    symbol. An invalid outer tuple is unavailable for both. Caller supplies
    source hashes separately: these native DTOs carry no response-body hash.
    """
    if type(pages) is not tuple or len(pages) != 6:
        return tuple(
            KisSectorAdjustmentComparison(symbol, "input_unavailable", "six_page_tuple_required")
            for symbol in SYMBOLS
        )
    return _compare(pages[:3], "XLK"), _compare(pages[3:], "XLE")
