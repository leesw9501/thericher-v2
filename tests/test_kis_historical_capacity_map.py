from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution.kis_historical_capacity_map import (
    KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    KisPaperDailyCapacityMapResult,
    run_bounded_kis_paper_daily_capacity_map,
    run_bounded_kis_paper_minute_capacity_map,
    sanitized_kis_paper_daily_capacity_map_summary,
    sanitized_kis_paper_minute_capacity_map_summary,
    write_kis_paper_daily_capacity_map_summary,
)
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
)

_NEW_YORK = ZoneInfo("America/New_York")
_OBSERVED_AT = datetime(2026, 7, 21, 17, 30, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def test_daily_capacity_map_measures_two_anchors_and_redacts_rows() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page("20260717", "20260716", continuation="F"),
            _daily_page("20260715", "20260714", continuation=""),
            _daily_page("20250717", "20250716", continuation="F"),
            _daily_page("20250715", "20250714", continuation=""),
        ]
    )
    client = _client(
        transport,
        max_daily_page_attempts=KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    )

    result = run_bounded_kis_paper_daily_capacity_map(client, observed_at=_OBSERVED_AT)
    document = sanitized_kis_paper_daily_capacity_map_summary(result)
    rendered = json.dumps(document, sort_keys=True)

    assert result.status == "observed"
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 0, 4)
    assert [(page.anchor_date, page.page_number) for page in result.pages] == [
        ("20260717", 1),
        ("20260717", 2),
        ("20250717", 1),
        ("20250717", 2),
    ]
    assert result.pages[1].progressed_older_than_previous is True
    assert result.pages[3].progressed_older_than_previous is True
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ] == [
        KIS_PAPER_TOKEN_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_DAILY_PATH,
    ]
    assert transport.requests[2].query["BYMD"] == "20260716"
    assert transport.requests[2].headers["tr_cont"] == "F"
    assert "777.777" not in rendered
    assert "capacity-token" not in rendered
    assert "paper-key" not in rendered
    assert document["storage"] == {"raw_market_data_retained": False, "in_memory_only": True}


def test_daily_capacity_map_stops_on_first_rejection() -> None:
    transport = _RecordingTransport([_token(), _rejected()])
    client = _client(
        transport,
        max_daily_page_attempts=KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    )

    result = run_bounded_kis_paper_daily_capacity_map(client, observed_at=_OBSERVED_AT)

    assert result.status == "rejected"
    assert result.reason == "daily_response_rejected"
    assert result.pages == ()
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 0, 1)
    assert len(transport.requests) == 2


def test_minute_capacity_map_uses_eight_pages_and_the_true_oldest_boundary() -> None:
    first_start = _OBSERVED_AT.replace(second=0)
    responses = [_token()]
    responses.append(
        _minute_page_from_timestamps(
            (first_start, first_start - timedelta(minutes=2), first_start - timedelta(minutes=1)),
            next_value="cursor-sentinel-must-not-persist",
        )
    )
    for page_number in range(2, KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS + 1):
        start = first_start - timedelta(minutes=page_number + 1)
        responses.append(
            _minute_page_from_timestamps(
                (start, start - timedelta(minutes=1)),
                next_value=(
                    "1" if page_number < KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS else ""
                ),
            )
        )
    transport = _RecordingTransport(responses)
    client = _client(
        transport,
        max_minute_page_attempts=KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    )

    result = run_bounded_kis_paper_minute_capacity_map(client, observed_at=_OBSERVED_AT)
    document = sanitized_kis_paper_minute_capacity_map_summary(result)
    rendered = json.dumps(document, sort_keys=True)

    assert result.status == "observed"
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 8, 0)
    assert len(result.pages) == 8
    assert result.pages[0].timestamps_strictly_descending is False
    assert result.pages[0].timestamps_one_minute_contiguous is False
    assert result.pages[1].boundary_contiguous_to_previous is True
    assert result.pages[1].overlap_with_previous_count == 0
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ] == [KIS_PAPER_TOKEN_PATH] + [KIS_PAPER_MINUTE_PATH] * 8
    assert transport.requests[2].query["KEYB"] == "20260721132700"
    assert transport.requests[2].query["PINC"] == "1"
    assert "777.777" not in rendered
    assert "cursor-sentinel-must-not-persist" not in rendered
    assert "capacity-token" not in rendered


def test_minute_capacity_map_stops_after_the_first_rejected_page() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _minute_page_from_timestamps(
                (
                    _OBSERVED_AT.replace(second=0),
                    _OBSERVED_AT.replace(second=0) - timedelta(minutes=1),
                ),
                next_value="1",
            ),
            _rejected(),
        ]
    )
    client = _client(
        transport,
        max_minute_page_attempts=KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    )

    result = run_bounded_kis_paper_minute_capacity_map(client, observed_at=_OBSERVED_AT)

    assert result.status == "rejected"
    assert result.reason == "minute_response_rejected"
    assert len(result.pages) == 1
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 2, 0)
    assert len(transport.requests) == 3


def test_daily_summary_writer_revalidates_and_stays_outside_git(tmp_path: Path) -> None:
    result = KisPaperDailyCapacityMapResult(
        observed_at=_OBSERVED_AT,
        call_counts=KisPaperMarketDataCallCounts(1, 0, 0),
        pages=(),
        status="rejected",
        reason="daily_response_rejected",
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    summary_path, _digest = write_kis_paper_daily_capacity_map_summary(
        result=result,
        artifact_root=tmp_path / "external",
        run_id="20260721T173000Z",
        repo_root=repo_root,
    )

    assert summary_path.is_relative_to(tmp_path / "external")
    assert json.loads(summary_path.read_text(encoding="utf-8"))["status"] == "rejected"

    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_daily_capacity_map_summary(
            result=result,
            artifact_root=repo_root / "artifacts",
            run_id="20260721T173001Z",
            repo_root=repo_root,
        )


def _client(
    transport: _RecordingTransport,
    *,
    max_daily_page_attempts: int = 3,
    max_minute_page_attempts: int = 3,
) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
        max_daily_page_attempts=max_daily_page_attempts,
        max_minute_page_attempts=max_minute_page_attempts,
    )


def _token() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "capacity-token"})


def _rejected() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"rt_cd": "1", "msg1": "secret server text"})


def _daily_page(first_date: str, second_date: str, *, continuation: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"nrec": "100"},
            "output2": [
                {
                    "xymd": first_date,
                    "open": "100",
                    "high": "102",
                    "low": "99",
                    "clos": "101",
                    "tvol": "777.777",
                },
                {
                    "xymd": second_date,
                    "open": "98",
                    "high": "101",
                    "low": "97",
                    "clos": "100",
                    "tvol": "776.776",
                },
            ],
        },
        headers={"tr_cont": continuation},
    )


def _minute_page_from_timestamps(
    timestamps: tuple[datetime, ...],
    *,
    next_value: str,
) -> KisMarketDataResponse:
    rows = []
    for timestamp in timestamps:
        exchange = timestamp.astimezone(_NEW_YORK)
        korea = exchange.astimezone(ZoneInfo("Asia/Seoul"))
        rows.append(
            {
                "xymd": exchange.strftime("%Y%m%d"),
                "xhms": exchange.strftime("%H%M%S"),
                "kymd": korea.strftime("%Y%m%d"),
                "khms": korea.strftime("%H%M%S"),
                "open": "100",
                "high": "102",
                "low": "99",
                "last": "101",
                "evol": "777.777",
            }
        )
    return KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {"next": next_value, "more": ""}, "output2": rows}
    )
