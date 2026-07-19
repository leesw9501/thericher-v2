from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.execution.kis_historical_probe import (
    KisPaperHistoricalDailyObservation,
    KisPaperHistoricalMinuteObservation,
    KisPaperHistoricalProbeEvidence,
    KisPaperHistoricalProbeFailure,
    run_bounded_kis_paper_historical_probe,
    sanitized_kis_paper_historical_probe_failure_summary,
    sanitized_kis_paper_historical_probe_summary,
    write_kis_paper_historical_probe_summary,
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

_OBSERVED_AT = datetime(2026, 7, 19, 9, 30, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def test_bounded_probe_uses_one_token_and_only_approved_metadata_requests() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page("20260717", "20260716", continuation="F"),
            _daily_page("20260715", "20260714", continuation=""),
            _daily_page("20260717", "20260716", continuation=""),
            _minute_page("195900", "195800", next_value="1"),
            _minute_page("195700", "195600", next_value=""),
            _minute_page("195900", "195800", next_value=""),
        ]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    evidence = run_bounded_kis_paper_historical_probe(
        client,
        observed_at=_OBSERVED_AT,
    )
    document = sanitized_kis_paper_historical_probe_summary(evidence)
    serialized = json.dumps(document, sort_keys=True)

    assert evidence.call_counts == KisPaperMarketDataCallCounts(
        token_attempts=1,
        minute_page_attempts=3,
        daily_page_attempts=3,
    )
    assert [item.symbol for item in evidence.daily] == ["QQQ", "SPY"]
    assert [item.symbol for item in evidence.minute] == ["QQQ", "SPY"]
    assert evidence.daily[0].continuation_requested is True
    assert evidence.daily[0].continuation_has_older_date is True
    assert evidence.minute[0].continuation_requested is True
    assert evidence.minute[0].continuation_boundary_contiguous is True
    assert evidence.minute[0].exact_overlap_count == 0

    paths = [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ]
    assert paths == [
        KIS_PAPER_TOKEN_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_MINUTE_PATH,
        KIS_PAPER_MINUTE_PATH,
        KIS_PAPER_MINUTE_PATH,
    ]
    assert [request.query.get("SYMB") for request in transport.requests[1:]] == [
        "QQQ",
        "QQQ",
        "SPY",
        "QQQ",
        "QQQ",
        "SPY",
    ]
    assert transport.requests[2].headers["tr_cont"] == "F"
    assert transport.requests[5].query["PINC"] == "1"
    assert transport.requests[5].query["KEYB"] == "20260717195700"
    assert all("trading" not in request.url for request in transport.requests)
    assert all("account" not in request.url for request in transport.requests)
    assert "paper-key" not in serialized
    assert "paper-secret" not in serialized
    assert "issued-token" not in serialized
    assert "777.777" not in serialized
    assert "999999" not in serialized
    assert document["storage"] == {
        "raw_market_data_retained": False,
        "in_memory_only": True,
        "persistent_cache_allowed": False,
    }


def test_summary_writer_revalidates_metadata_and_stays_outside_git(tmp_path: Path) -> None:
    evidence = _evidence()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    object.__setattr__(evidence.daily[0], "symbol", "paper-secret")
    with pytest.raises(ValueError, match="symbol"):
        write_kis_paper_historical_probe_summary(
            result=evidence,
            artifact_root=tmp_path / "outside",
            run_id="20260719T093000Z",
            repo_root=repo_root,
        )
    assert not (tmp_path / "outside").exists()

    evidence = _evidence()
    summary_path, _summary_hash = write_kis_paper_historical_probe_summary(
        result=evidence,
        artifact_root=tmp_path / "outside",
        run_id="20260719T093001Z",
        repo_root=repo_root,
    )
    serialized = summary_path.read_text(encoding="utf-8")
    assert summary_path.is_relative_to(tmp_path / "outside")
    assert "777.777" not in serialized
    assert "issued-token" not in serialized

    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_historical_probe_summary(
            result=_evidence(),
            artifact_root=repo_root / "artifacts",
            run_id="20260719T093002Z",
            repo_root=repo_root,
        )


def test_failure_summary_keeps_only_fixed_scope_and_sanitized_reason() -> None:
    failure = KisPaperHistoricalProbeFailure(
        observed_at=_OBSERVED_AT,
        call_counts=KisPaperMarketDataCallCounts(
            token_attempts=1,
            minute_page_attempts=1,
            daily_page_attempts=2,
        ),
        reason="http 500 included a secret response body",
    )

    document = sanitized_kis_paper_historical_probe_failure_summary(failure)

    assert document["reason"] == "unexpected_probe_error"
    assert document["scope"] == {
        "symbols": ["QQQ", "SPY"],
        "exchange": "NAS",
        "endpoints": ["overseas_daily", "overseas_raw_1m"],
        "account_or_order_endpoint_called": False,
        "live_endpoint_called": False,
    }
    assert "secret" not in json.dumps(document, sort_keys=True)


def _evidence() -> KisPaperHistoricalProbeEvidence:
    first_newest = _OBSERVED_AT
    first_oldest = first_newest - timedelta(minutes=1)
    continuation_newest = first_oldest - timedelta(minutes=1)
    continuation_oldest = continuation_newest - timedelta(minutes=1)
    return KisPaperHistoricalProbeEvidence(
        observed_at=_OBSERVED_AT,
        requested_by_date="20260719",
        call_counts=KisPaperMarketDataCallCounts(
            token_attempts=1,
            minute_page_attempts=3,
            daily_page_attempts=3,
        ),
        daily=(
            KisPaperHistoricalDailyObservation(
                symbol="QQQ",
                first_row_count=2,
                first_newest_date="20260717",
                first_oldest_date="20260716",
                required_ohlcv_fields_present=True,
                continuation_available=True,
                continuation_requested=True,
                continuation_row_count=2,
                continuation_newest_date="20260715",
                continuation_oldest_date="20260714",
                continuation_has_older_date=True,
            ),
            KisPaperHistoricalDailyObservation(
                symbol="SPY",
                first_row_count=2,
                first_newest_date="20260717",
                first_oldest_date="20260716",
                required_ohlcv_fields_present=True,
                continuation_available=False,
                continuation_requested=False,
                continuation_row_count=None,
                continuation_newest_date=None,
                continuation_oldest_date=None,
                continuation_has_older_date=False,
            ),
        ),
        minute=(
            KisPaperHistoricalMinuteObservation(
                symbol="QQQ",
                first_row_count=2,
                first_newest_utc=first_newest,
                first_oldest_utc=first_oldest,
                continuation_available=True,
                continuation_requested=True,
                continuation_row_count=2,
                continuation_newest_utc=continuation_newest,
                continuation_oldest_utc=continuation_oldest,
                exact_overlap_count=0,
                continuation_boundary_contiguous=True,
            ),
            KisPaperHistoricalMinuteObservation(
                symbol="SPY",
                first_row_count=2,
                first_newest_utc=first_newest,
                first_oldest_utc=first_oldest,
                continuation_available=False,
                continuation_requested=False,
                continuation_row_count=None,
                continuation_newest_utc=None,
                continuation_oldest_utc=None,
                exact_overlap_count=0,
                continuation_boundary_contiguous=False,
            ),
        ),
    )


def _token() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "issued-token"})


def _daily_page(first_date: str, second_date: str, *, continuation: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"nrec": "100"},
            "output2": [
                {
                    "xymd": first_date,
                    "open": "777.777",
                    "high": "778.777",
                    "low": "776.777",
                    "clos": "777.777",
                    "tvol": "999999",
                },
                {
                    "xymd": second_date,
                    "open": "777.777",
                    "high": "778.777",
                    "low": "776.777",
                    "clos": "777.777",
                    "tvol": "999999",
                },
            ],
        },
        headers={"tr_cont": continuation},
    )


def _minute_page(first_time: str, second_time: str, *, next_value: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"next": next_value, "more": "0"},
            "output2": [_minute_row(first_time), _minute_row(second_time)],
        }
    )


def _minute_row(exchange_time: str) -> dict[str, str]:
    return {
        "xymd": "20260717",
        "xhms": exchange_time,
        "kymd": "20260718",
        "khms": "085900",
        "open": "777.777",
        "high": "778.777",
        "low": "776.777",
        "last": "777.777",
        "evol": "999999",
    }
