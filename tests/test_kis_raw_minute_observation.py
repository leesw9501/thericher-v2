from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMinuteCallCounts,
    KisPaperMinuteClient,
)
from thericher_v2.execution.kis_raw_minute_observation import (
    KisPaperRawMinuteObservation,
    KisPaperRawMinuteObservationError,
    is_kis_paper_raw_minute_observation_window,
    run_bounded_kis_paper_raw_minute_observation,
    sanitized_kis_paper_raw_minute_observation_failure_summary,
    sanitized_kis_paper_raw_minute_observation_summary,
    write_kis_paper_raw_minute_observation_summary,
)

_NEW_YORK = ZoneInfo("America/New_York")
_SEOUL = ZoneInfo("Asia/Seoul")
_SESSION_DATE = date(2026, 7, 21)
_START = datetime(2026, 7, 21, 17, 30, 20, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def test_bounded_observation_uses_fake_transport_and_retains_metadata_only() -> None:
    first_rows = _rows(_START.replace(second=0), 120)
    second_rows = _rows(_START.replace(second=0) - timedelta(minutes=120), 120)
    transport = _RecordingTransport(
        [
            KisMarketDataResponse.from_payload({"access_token": "token-sentinel-must-not-persist"}),
            KisMarketDataResponse.from_payload(
                _page_payload(
                    first_rows,
                    next_cursor="cursor-sentinel-must-not-persist",
                    account_identifier="account-sentinel-must-not-persist",
                )
            ),
            KisMarketDataResponse.from_payload(
                _page_payload(second_rows, next_cursor="third-cursor-must-not-be-requested")
            ),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    evidence = run_bounded_kis_paper_raw_minute_observation(
        client,
        session_date=_SESSION_DATE,
        observed_at_start=_START,
        clock=_clock(
            _START + timedelta(seconds=1),
            _START + timedelta(seconds=2),
            _START + timedelta(seconds=3),
            _START + timedelta(minutes=3),
        ),
    )

    assert evidence.call_counts == KisPaperMinuteCallCounts(1, 2)
    assert evidence.first_page_row_count == 120
    assert evidence.continuation_page_row_count == 120
    assert evidence.continuation_available is True
    assert evidence.continuation_requested is True
    assert evidence.first_page_required_ohlcv_fields_present is True
    assert evidence.continuation_page_required_ohlcv_fields_present is True
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ] == [KIS_PAPER_TOKEN_PATH, KIS_PAPER_MINUTE_PATH, KIS_PAPER_MINUTE_PATH]
    assert transport.requests[1].query["PINC"] == "0"
    assert transport.requests[2].query["PINC"] == "1"

    summary = sanitized_kis_paper_raw_minute_observation_summary(evidence)
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["promotion"] == "not_available_from_one_shot_observation"
    assert summary["scope"]["order_or_account_endpoint_called"] is False
    assert summary["storage"]["raw_market_data_retained"] is False
    assert summary["observation"]["first_exchange_timestamp_bounds_utc"] == {
        "newest": "2026-07-21T17:30:00Z",
        "oldest": "2026-07-21T15:31:00Z",
    }
    assert "123.45" not in rendered
    assert "987654321.987" not in rendered
    assert "cursor-sentinel-must-not-persist" not in rendered
    assert "account-sentinel-must-not-persist" not in rendered
    assert "token-sentinel-must-not-persist" not in rendered
    assert "paper-key" not in rendered
    assert '"open":' not in rendered
    assert '"output2":' not in rendered


def test_closed_second_page_gate_stops_before_a_second_get() -> None:
    transport = _RecordingTransport(
        [
            KisMarketDataResponse.from_payload({"access_token": "fake-token"}),
            KisMarketDataResponse.from_payload(_page_payload(_rows(_START, 2), next_cursor="1")),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(KisPaperRawMinuteObservationError, match="observation_window_closed"):
        run_bounded_kis_paper_raw_minute_observation(
            client,
            session_date=_SESSION_DATE,
            observed_at_start=_START,
            clock=_clock(
                _START + timedelta(seconds=1),
                _START + timedelta(seconds=2),
                datetime(2026, 7, 21, 20, 0, tzinfo=UTC),
            ),
        )

    assert [request.method for request in transport.requests] == ["POST", "GET"]
    assert client.call_counts == KisPaperMinuteCallCounts(1, 1)


def test_window_requires_the_declared_current_weekday_regular_session() -> None:
    assert is_kis_paper_raw_minute_observation_window(_START, session_date=_SESSION_DATE) is True
    assert (
        is_kis_paper_raw_minute_observation_window(
            _START - timedelta(hours=5), session_date=_SESSION_DATE
        )
        is False
    )
    assert (
        is_kis_paper_raw_minute_observation_window(
            _START, session_date=_SESSION_DATE + timedelta(days=1)
        )
        is False
    )


def test_writer_stays_outside_git_and_failure_summary_redacts_untrusted_text(
    tmp_path: Path,
) -> None:
    evidence = _evidence()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_raw_minute_observation_summary(
            result=evidence,
            artifact_root=repo_root / "artifacts",
            run_id="20260721T173020Z",
            repo_root=repo_root,
        )

    path, digest = write_kis_paper_raw_minute_observation_summary(
        result=evidence,
        artifact_root=tmp_path / "external",
        run_id="20260721T173020Z",
        repo_root=repo_root,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    assert path.is_relative_to(tmp_path / "external")
    assert digest.startswith("sha256:")
    assert document["storage"]["raw_market_data_retained"] is False

    failure = sanitized_kis_paper_raw_minute_observation_failure_summary(
        observed_at=_START,
        call_counts=KisPaperMinuteCallCounts(1, 1),
        reason="token-sentinel-must-not-persist",
    )
    assert failure["reason"] == "unexpected_observation_error"
    assert "token-sentinel-must-not-persist" not in json.dumps(failure, sort_keys=True)

    structural_failure = sanitized_kis_paper_raw_minute_observation_failure_summary(
        observed_at=_START,
        call_counts=KisPaperMinuteCallCounts(1, 1),
        reason="observation scope must be QQQ NAS",
    )
    assert structural_failure["reason"] == "observation scope must be QQQ NAS"


def _evidence() -> KisPaperRawMinuteObservation:
    return KisPaperRawMinuteObservation(
        observed_at_start=_START,
        observed_at_end=_START + timedelta(seconds=4),
        session_date=_SESSION_DATE,
        call_counts=KisPaperMinuteCallCounts(1, 2),
        first_page_row_count=120,
        continuation_page_row_count=120,
        continuation_available=True,
        continuation_requested=True,
        first_page_required_ohlcv_fields_present=True,
        continuation_page_required_ohlcv_fields_present=True,
        first_exchange_newest=_START.replace(second=0),
        first_exchange_oldest=_START.replace(second=0) - timedelta(minutes=119),
        first_korea_newest=_START.replace(second=0),
        first_korea_oldest=_START.replace(second=0) - timedelta(minutes=119),
        continuation_exchange_newest=_START.replace(second=0) - timedelta(minutes=120),
        continuation_exchange_oldest=_START.replace(second=0) - timedelta(minutes=239),
        continuation_korea_newest=_START.replace(second=0) - timedelta(minutes=120),
        continuation_korea_oldest=_START.replace(second=0) - timedelta(minutes=239),
    )


def _page_payload(
    rows: list[dict[str, str]],
    *,
    next_cursor: str | None = None,
    account_identifier: str | None = None,
) -> dict[str, object]:
    output1: dict[str, object] = {"next": next_cursor or "", "more": ""}
    if account_identifier is not None:
        output1["account_identifier"] = account_identifier
    return {"rt_cd": "0", "output1": output1, "output2": rows}


def _rows(start: datetime, count: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for offset in range(count):
        exchange = (start - timedelta(minutes=offset)).astimezone(_NEW_YORK)
        korea = exchange.astimezone(_SEOUL)
        rows.append(
            {
                "xymd": exchange.strftime("%Y%m%d"),
                "xhms": exchange.strftime("%H%M%S"),
                "kymd": korea.strftime("%Y%m%d"),
                "khms": korea.strftime("%H%M%S"),
                "open": "123.45",
                "high": "124.00",
                "low": "123.00",
                "last": "123.50",
                "evol": "987654321.987",
            }
        )
    return rows


def _clock(*values: datetime):
    iterator: Iterator[datetime] = iter(values)
    return lambda: next(iterator)
