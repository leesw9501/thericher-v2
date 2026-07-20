"""One bounded, metadata-only KIS paper raw-minute observation boundary.

This module intentionally does not qualify a KIS capability or feed a model. It
only prepares one separately named observation with a literal QQQ/NAS scope.
Raw bars remain local to the runner and never enter an artifact or control
ledger.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_market_data import (
    KisPaperMinuteCallCounts,
    KisPaperMinuteClient,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from .kis_minute_qualification import write_external_one_shot_summary

KIS_PAPER_RAW_MINUTE_OBSERVATION_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/execution/kis-paper-raw-minute-observation"
)
KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT = Path("D:/thericher-v2/model-artifacts/_control")
KIS_PAPER_RAW_MINUTE_OBSERVATION_VERSION = "kis-paper-raw-minute-observation-v1"
KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID = "kis-paper-raw-minute-observation-v1"
KIS_PAPER_RAW_MINUTE_OBSERVATION_EXCHANGE = "NAS"
KIS_PAPER_RAW_MINUTE_OBSERVATION_SYMBOL = "QQQ"
_NEW_YORK = ZoneInfo("America/New_York")
_SEOUL = ZoneInfo("Asia/Seoul")
_REGULAR_SESSION_OPEN = time(9, 30)
_REGULAR_SESSION_CLOSE = time(16, 0)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "continuation_contract_invalid",
        "minute_page_limit_exceeded",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "observation cannot end before it starts",
        "observation call counts are incomplete",
        "observation call counts are invalid",
        "observation call counts are not bounded",
        "observation continuation facts are inconsistent",
        "observation continuation page is not bounded",
        "observation continuation was not available",
        "observation continuation fields are incomplete",
        "observation first page fields are incomplete",
        "observation first page is not bounded",
        "observation is outside the declared session",
        "observation scope must be QQQ NAS",
        "observation session date is invalid",
        "observation timestamp bounds are incomplete",
        "observation timestamp bounds are invalid",
        "observation_window_closed",
        "paper_host_required",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
    }
)


class KisPaperRawMinuteObservationError(RuntimeError):
    """Safe, metadata-only observation failure."""


@dataclass(frozen=True)
class KisPaperRawMinuteObservation:
    """Sanitizable facts from one token and no more than two raw-minute pages."""

    observed_at_start: datetime
    observed_at_end: datetime
    session_date: date
    call_counts: KisPaperMinuteCallCounts
    first_page_row_count: int
    continuation_page_row_count: int | None
    continuation_available: bool
    continuation_requested: bool
    first_page_required_ohlcv_fields_present: bool
    continuation_page_required_ohlcv_fields_present: bool | None
    first_exchange_newest: datetime
    first_exchange_oldest: datetime
    first_korea_newest: datetime
    first_korea_oldest: datetime
    continuation_exchange_newest: datetime | None
    continuation_exchange_oldest: datetime | None
    continuation_korea_newest: datetime | None
    continuation_korea_oldest: datetime | None
    exchange: str = KIS_PAPER_RAW_MINUTE_OBSERVATION_EXCHANGE
    symbol: str = KIS_PAPER_RAW_MINUTE_OBSERVATION_SYMBOL
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "observed_at_start",
            "observed_at_end",
            "first_exchange_newest",
            "first_exchange_oldest",
            "first_korea_newest",
            "first_korea_oldest",
        ):
            object.__setattr__(self, field_name, require_utc(getattr(self, field_name), field_name))
        for field_name in (
            "continuation_exchange_newest",
            "continuation_exchange_oldest",
            "continuation_korea_newest",
            "continuation_korea_oldest",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_utc(value, field_name))
        if self.observed_at_end < self.observed_at_start:
            raise ValueError("observation cannot end before it starts")
        if not isinstance(self.session_date, date) or isinstance(self.session_date, datetime):
            raise ValueError("observation session date is invalid")
        if not (
            is_kis_paper_raw_minute_observation_window(
                self.observed_at_start,
                session_date=self.session_date,
            )
            and is_kis_paper_raw_minute_observation_window(
                self.observed_at_end,
                session_date=self.session_date,
            )
        ):
            raise ValueError("observation is outside the declared session")
        if (
            self.exchange != KIS_PAPER_RAW_MINUTE_OBSERVATION_EXCHANGE
            or self.symbol != KIS_PAPER_RAW_MINUTE_OBSERVATION_SYMBOL
        ):
            raise ValueError("observation scope must be QQQ NAS")
        _require_observation_call_counts(self.call_counts, observed=True)
        if not (0 < self.first_page_row_count <= 120):
            raise ValueError("observation first page is not bounded")
        if not self.first_page_required_ohlcv_fields_present:
            raise ValueError("observation first page fields are incomplete")
        if self.continuation_requested != (self.continuation_page_row_count is not None):
            raise ValueError("observation continuation facts are inconsistent")
        if self.continuation_requested and not self.continuation_available:
            raise ValueError("observation continuation was not available")
        if self.continuation_page_row_count is not None and not (
            0 < self.continuation_page_row_count <= 120
        ):
            raise ValueError("observation continuation page is not bounded")
        if (
            self.continuation_page_row_count is not None
            and self.continuation_page_required_ohlcv_fields_present is not True
        ):
            raise ValueError("observation continuation fields are incomplete")
        if self.continuation_page_row_count is None and (
            self.continuation_page_required_ohlcv_fields_present is not None
        ):
            raise ValueError("observation continuation fields are inconsistent")
        _require_timestamp_bounds(self.first_exchange_newest, self.first_exchange_oldest)
        _require_timestamp_bounds(self.first_korea_newest, self.first_korea_oldest)
        _require_optional_timestamp_bounds(
            self.continuation_exchange_newest,
            self.continuation_exchange_oldest,
        )
        _require_optional_timestamp_bounds(
            self.continuation_korea_newest,
            self.continuation_korea_oldest,
        )


@dataclass(frozen=True)
class KisPaperRawMinuteObservationFailure:
    """Typed failure facts safe to write after a bounded observation attempt."""

    observed_at: datetime
    call_counts: KisPaperMinuteCallCounts
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        _require_observation_call_counts(self.call_counts, observed=False)
        object.__setattr__(
            self,
            "reason",
            sanitize_kis_paper_raw_minute_failure_reason(self.reason),
        )


def is_kis_paper_raw_minute_observation_window(
    value: datetime,
    *,
    session_date: date,
) -> bool:
    """Check only current weekday/hours; a caller confirms the exchange calendar."""

    if not isinstance(session_date, date) or isinstance(session_date, datetime):
        return False
    observed_at = require_utc(value, "value").astimezone(_NEW_YORK)
    local_time = observed_at.timetz().replace(tzinfo=None)
    return (
        observed_at.date() == session_date
        and observed_at.weekday() < 5
        and _REGULAR_SESSION_OPEN <= local_time < _REGULAR_SESSION_CLOSE
    )


def run_bounded_kis_paper_raw_minute_observation(
    client: KisPaperMinuteClient,
    *,
    session_date: date,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    observed_at_start: datetime | None = None,
) -> KisPaperRawMinuteObservation:
    """Read a literal QQQ/NAS first page and one optional continuation only."""

    start = require_utc(
        observed_at_start if observed_at_start is not None else clock(),
        "observed_at_start",
    )
    _require_observation_window(start, session_date=session_date)
    _require_observation_window(require_utc(clock(), "before_token"), session_date=session_date)
    client.ensure_authenticated()

    def require_page_window() -> None:
        _require_observation_window(
            require_utc(clock(), "before_minute_page"),
            session_date=session_date,
        )

    first_page = client.fetch_page(
        KisPaperMinuteQuery(
            exchange=KIS_PAPER_RAW_MINUTE_OBSERVATION_EXCHANGE,
            symbol=KIS_PAPER_RAW_MINUTE_OBSERVATION_SYMBOL,
        ),
        before_request=require_page_window,
    )
    _require_page_scope(first_page)
    continuation_page: KisPaperMinutePage | None = None
    if first_page.next_cursor is not None:
        if not isinstance(first_page.next_cursor, str) or not first_page.next_cursor:
            raise KisPaperRawMinuteObservationError("continuation_contract_invalid")
        continuation_query = KisPaperMinuteQuery(
            exchange=KIS_PAPER_RAW_MINUTE_OBSERVATION_EXCHANGE,
            symbol=KIS_PAPER_RAW_MINUTE_OBSERVATION_SYMBOL,
            continuation_next=first_page.next_cursor,
            continuation_key=_continuation_key_before(first_page.bars[-1]),
        )
        continuation_page = client.fetch_page(
            continuation_query,
            before_request=require_page_window,
        )
        _require_page_scope(continuation_page)
        if (
            continuation_page.query.continuation_next != first_page.next_cursor
            or continuation_page.query.continuation_key != continuation_query.continuation_key
        ):
            raise KisPaperRawMinuteObservationError("continuation_contract_invalid")

    end = require_utc(clock(), "observed_at_end")
    _require_observation_window(end, session_date=session_date)
    call_counts = client.call_counts
    _require_observation_call_counts(call_counts, observed=True)
    first_exchange = _exchange_timestamps(first_page.bars)
    first_korea = _korea_timestamps(first_page.bars)
    continuation_exchange = (
        _exchange_timestamps(continuation_page.bars) if continuation_page is not None else ()
    )
    continuation_korea = (
        _korea_timestamps(continuation_page.bars) if continuation_page is not None else ()
    )
    return KisPaperRawMinuteObservation(
        observed_at_start=start,
        observed_at_end=end,
        session_date=session_date,
        call_counts=call_counts,
        first_page_row_count=len(first_page.bars),
        continuation_page_row_count=(
            len(continuation_page.bars) if continuation_page is not None else None
        ),
        continuation_available=first_page.next_cursor is not None,
        continuation_requested=continuation_page is not None,
        first_page_required_ohlcv_fields_present=_typed_bars_present(first_page.bars),
        continuation_page_required_ohlcv_fields_present=(
            _typed_bars_present(continuation_page.bars) if continuation_page is not None else None
        ),
        first_exchange_newest=max(first_exchange),
        first_exchange_oldest=min(first_exchange),
        first_korea_newest=max(first_korea),
        first_korea_oldest=min(first_korea),
        continuation_exchange_newest=(
            max(continuation_exchange) if continuation_exchange else None
        ),
        continuation_exchange_oldest=(
            min(continuation_exchange) if continuation_exchange else None
        ),
        continuation_korea_newest=(max(continuation_korea) if continuation_korea else None),
        continuation_korea_oldest=(min(continuation_korea) if continuation_korea else None),
    )


def sanitized_kis_paper_raw_minute_observation_summary(
    evidence: KisPaperRawMinuteObservation,
) -> dict[str, object]:
    """Render facts that are safe outside the process holding raw minute bars."""

    if not isinstance(evidence, KisPaperRawMinuteObservation):
        raise TypeError("observation summary requires typed evidence")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_raw_minute_observation",
        "observation_version": KIS_PAPER_RAW_MINUTE_OBSERVATION_VERSION,
        "status": "observed",
        "promotion": "not_available_from_one_shot_observation",
        "scope": {
            "exchange": evidence.exchange,
            "symbol": evidence.symbol,
            "timeframe": "1m",
            "network_scope": "paper token plus one first page and at most one continuation",
            "order_or_account_endpoint_called": False,
        },
        "session_gate": {
            "exchange": "NASDAQ",
            "declared_and_observed_local_date": evidence.session_date.isoformat(),
            "mode": "caller_confirmed_current_regular_hours",
        },
        "observation": {
            "started_at_utc": _format_utc(evidence.observed_at_start),
            "ended_at_utc": _format_utc(evidence.observed_at_end),
            "first_page_row_count": evidence.first_page_row_count,
            "continuation_page_row_count": evidence.continuation_page_row_count,
            "continuation_available": evidence.continuation_available,
            "continuation_requested": evidence.continuation_requested,
            "call_counts": {
                "token_attempts": evidence.call_counts.token_attempts,
                "minute_page_attempts": evidence.call_counts.minute_page_attempts,
            },
            "first_page_required_ohlcv_fields_present": (
                evidence.first_page_required_ohlcv_fields_present
            ),
            "continuation_page_required_ohlcv_fields_present": (
                evidence.continuation_page_required_ohlcv_fields_present
            ),
            "first_exchange_timestamp_bounds_utc": _timestamp_bounds(
                evidence.first_exchange_newest,
                evidence.first_exchange_oldest,
            ),
            "first_korea_timestamp_bounds_utc": _timestamp_bounds(
                evidence.first_korea_newest,
                evidence.first_korea_oldest,
            ),
            "continuation_exchange_timestamp_bounds_utc": _optional_timestamp_bounds(
                evidence.continuation_exchange_newest,
                evidence.continuation_exchange_oldest,
            ),
            "continuation_korea_timestamp_bounds_utc": _optional_timestamp_bounds(
                evidence.continuation_korea_newest,
                evidence.continuation_korea_oldest,
            ),
        },
        "storage": {
            "raw_market_data_retained": False,
            "in_memory_only": True,
            "persistent_cache_allowed": False,
        },
        "limitations": [
            "No raw prices, volume, rows, cursor, token, account identifier, or response body "
            "is retained.",
            "This one-shot observation cannot qualify timestamps, retention, completed bars, "
            "storage rights, or model eligibility.",
        ],
    }


def sanitized_kis_paper_raw_minute_observation_failure_summary(
    *,
    observed_at: datetime,
    call_counts: KisPaperMinuteCallCounts,
    reason: str,
) -> dict[str, object]:
    """Render a bounded failure without persisting transport or response detail."""

    failure = KisPaperRawMinuteObservationFailure(
        observed_at=observed_at,
        call_counts=call_counts,
        reason=reason,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_raw_minute_observation",
        "observation_version": KIS_PAPER_RAW_MINUTE_OBSERVATION_VERSION,
        "status": "rejected",
        "reason": failure.reason,
        "observed_at_utc": _format_utc(failure.observed_at),
        "call_counts": {
            "token_attempts": failure.call_counts.token_attempts,
            "minute_page_attempts": failure.call_counts.minute_page_attempts,
        },
        "scope": {"order_or_account_endpoint_called": False},
        "storage": {"raw_market_data_retained": False, "in_memory_only": True},
    }


def sanitize_kis_paper_raw_minute_failure_reason(value: BaseException | str) -> str:
    """Avoid recording arbitrary endpoint, response, token, or parser text."""

    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_observation_error"


def write_kis_paper_raw_minute_observation_summary(
    *,
    result: KisPaperRawMinuteObservation | KisPaperRawMinuteObservationFailure,
    artifact_root: Path,
    run_id: str,
    repo_root: Path,
) -> tuple[Path, str]:
    """Atomically persist an internally sanitized result outside the repository."""

    if not run_id or any(character not in "0123456789TZ-" for character in run_id):
        raise ValueError("observation run_id is invalid")
    if isinstance(result, KisPaperRawMinuteObservation):
        document = sanitized_kis_paper_raw_minute_observation_summary(result)
    elif isinstance(result, KisPaperRawMinuteObservationFailure):
        document = sanitized_kis_paper_raw_minute_observation_failure_summary(
            observed_at=result.observed_at,
            call_counts=result.call_counts,
            reason=result.reason,
        )
    else:
        raise TypeError("observation summary requires typed evidence or failure")
    return write_external_one_shot_summary(
        document=document,
        artifact_root=artifact_root,
        run_id=run_id,
        repo_root=repo_root,
    )


def _require_observation_window(value: datetime, *, session_date: date) -> None:
    if not is_kis_paper_raw_minute_observation_window(value, session_date=session_date):
        raise KisPaperRawMinuteObservationError("observation_window_closed")


def _require_page_scope(page: KisPaperMinutePage) -> None:
    if (
        page.query.exchange != KIS_PAPER_RAW_MINUTE_OBSERVATION_EXCHANGE
        or page.query.symbol != KIS_PAPER_RAW_MINUTE_OBSERVATION_SYMBOL
        or not _typed_bars_present(page.bars)
    ):
        raise KisPaperRawMinuteObservationError("minute_response_invalid")


def _typed_bars_present(rows: tuple[KisPaperMinuteRawBar, ...]) -> bool:
    return bool(rows) and all(isinstance(row, KisPaperMinuteRawBar) for row in rows)


def _exchange_timestamps(rows: tuple[KisPaperMinuteRawBar, ...]) -> tuple[datetime, ...]:
    return tuple(_local_timestamp(row.exchange_date, row.exchange_time, _NEW_YORK) for row in rows)


def _korea_timestamps(rows: tuple[KisPaperMinuteRawBar, ...]) -> tuple[datetime, ...]:
    return tuple(_local_timestamp(row.korea_date, row.korea_time, _SEOUL) for row in rows)


def _local_timestamp(date_text: str, time_text: str, zone: ZoneInfo) -> datetime:
    try:
        return datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M%S").replace(
            tzinfo=zone
        ).astimezone(UTC)
    except ValueError as error:
        raise KisPaperRawMinuteObservationError("minute_response_invalid") from error


def _continuation_key_before(row: KisPaperMinuteRawBar) -> str:
    try:
        exchange_local = datetime.strptime(
            f"{row.exchange_date}{row.exchange_time}", "%Y%m%d%H%M%S"
        ).replace(tzinfo=_NEW_YORK)
    except ValueError as error:
        raise KisPaperRawMinuteObservationError("continuation_contract_invalid") from error
    return (exchange_local - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")


def _require_observation_call_counts(
    call_counts: KisPaperMinuteCallCounts,
    *,
    observed: bool,
) -> None:
    if not isinstance(call_counts, KisPaperMinuteCallCounts):
        raise ValueError("observation call counts are invalid")
    if not (0 <= call_counts.token_attempts <= 1 and 0 <= call_counts.minute_page_attempts <= 2):
        raise ValueError("observation call counts are not bounded")
    if observed and (
        call_counts.token_attempts != 1 or call_counts.minute_page_attempts not in {1, 2}
    ):
        raise ValueError("observation call counts are incomplete")


def _require_timestamp_bounds(newest: datetime, oldest: datetime) -> None:
    if newest < oldest:
        raise ValueError("observation timestamp bounds are invalid")


def _require_optional_timestamp_bounds(newest: datetime | None, oldest: datetime | None) -> None:
    if (newest is None) != (oldest is None):
        raise ValueError("observation timestamp bounds are incomplete")
    if newest is not None and oldest is not None:
        _require_timestamp_bounds(newest, oldest)


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")


def _timestamp_bounds(newest: datetime, oldest: datetime) -> dict[str, str]:
    _require_timestamp_bounds(newest, oldest)
    return {"newest": _format_utc(newest), "oldest": _format_utc(oldest)}


def _optional_timestamp_bounds(
    newest: datetime | None,
    oldest: datetime | None,
) -> dict[str, str] | None:
    _require_optional_timestamp_bounds(newest, oldest)
    if newest is None or oldest is None:
        return None
    return _timestamp_bounds(newest, oldest)
