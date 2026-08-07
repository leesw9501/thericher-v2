from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY,
    collect_and_write_kis_paper_iwm_m1_current_head,
    collect_kis_paper_iwm_m1_current_head,
    validate_kis_paper_iwm_m1_current_head_cache_root,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)


class _MinuteClient:
    def __init__(self, responses: list[KisPaperMinutePage | BaseException]) -> None:
        self._responses = iter(responses)
        self.queries: list[KisPaperMinuteQuery] = []

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: object = None,
    ) -> KisPaperMinutePage:
        self.queries.append(query)
        response = next(self._responses)
        if isinstance(response, BaseException):
            raise response
        return response


def test_collects_one_iwm_current_page_in_an_isolated_immutable_snapshot(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    primary_cache = tmp_path / "primary" / "index.json"
    primary_cache.parent.mkdir()
    primary_cache.write_text('{"qqq_spy":"unchanged"}\n', encoding="utf-8")
    cache_root = tmp_path / "market-data" / "iwm-current-head"
    client = _MinuteClient([_page(_bar_count=2, next_cursor="1")])

    result = collect_kis_paper_iwm_m1_current_head(
        client=client,
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=cache_root.parent,
        observed_at=_observed_at(),
    )

    assert result.outcome.status == "collected"
    assert result.outcome.continuation_category == "observed_not_followed"
    assert result.outcome.cache_disposition == "retained"
    assert result.snapshot_path is not None
    assert result.snapshot_path.is_relative_to(cache_root)
    assert primary_cache.read_text(encoding="utf-8") == '{"qqq_spy":"unchanged"}\n'
    assert len(client.queries) == 1
    assert client.queries == [KisPaperMinuteQuery(exchange="AMS", symbol="IWM")]
    serialized = json.dumps(result.outcome.safe_payload(), sort_keys=True)
    assert KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY in serialized
    assert "12345.67" not in serialized
    assert "20260724" not in serialized
    assert "access_token" not in serialized
    assert (result.snapshot_path / "rows.csv.gz").is_file()
    assert (result.snapshot_path / "manifest.json").is_file()


def test_reuses_identical_page_but_preserves_a_changed_head_as_another_snapshot(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "iwm-current-head"
    first_page = _page(_bar_count=2, next_cursor=None)

    first = collect_kis_paper_iwm_m1_current_head(
        client=_MinuteClient([first_page]),
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=cache_root.parent,
        observed_at=_observed_at(),
    )
    repeated = collect_kis_paper_iwm_m1_current_head(
        client=_MinuteClient([first_page]),
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=cache_root.parent,
        observed_at=_observed_at() + timedelta(minutes=1),
    )
    changed = collect_kis_paper_iwm_m1_current_head(
        client=_MinuteClient([_page(_bar_count=2, next_cursor=None, last="12345.68")]),
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=cache_root.parent,
        observed_at=_observed_at() + timedelta(minutes=2),
    )

    assert first.outcome.cache_disposition == "retained"
    assert repeated.outcome.cache_disposition == "already_retained"
    assert changed.outcome.cache_disposition == "retained"
    snapshot_root = cache_root / "v1" / "snapshots"
    assert len([path for path in snapshot_root.iterdir() if path.is_dir()]) == 2


@pytest.mark.parametrize(
    ("conflict", "expected_status", "expected_reason"),
    [
        (False, "unavailable", "transport_failure"),
        (True, "rejected", "minute_duplicate_conflict"),
    ],
)
def test_failures_leave_no_partial_iwm_cache(
    tmp_path: Path,
    conflict: bool,
    expected_status: str,
    expected_reason: str,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "iwm-current-head"
    response: KisPaperMinutePage | BaseException = (
        _conflicting_page() if conflict else KisPaperMarketDataError("transport_failure")
    )

    result = collect_kis_paper_iwm_m1_current_head(
        client=_MinuteClient([response]),
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=cache_root.parent,
        observed_at=_observed_at(),
    )

    assert result.outcome.status == expected_status
    assert result.outcome.response_class == expected_reason
    assert result.outcome.raw_market_data_retained is False
    assert result.snapshot_path is None
    assert not cache_root.exists()


def test_rejects_in_repository_cache_before_calling_the_provider(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    client = _MinuteClient([_page(_bar_count=1, next_cursor=None)])

    with pytest.raises(ValueError, match="must stay outside Git"):
        collect_kis_paper_iwm_m1_current_head(
            client=client,
            cache_root=repository_root / "raw-cache",
            repository_root=repository_root,
            market_data_root=tmp_path / "market-data",
            observed_at=_observed_at(),
        )

    assert client.queries == []


def test_rejects_a_cross_target_response_before_writing_iwm_cache(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "iwm-current-head"
    timestamp = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    cross_target_page = KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"),
        bars=(_bar(timestamp, last="12345.67"),),
        next_cursor=None,
        more="",
    )
    client = _MinuteClient([cross_target_page])

    result = collect_kis_paper_iwm_m1_current_head(
        client=client,
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=cache_root.parent,
        observed_at=_observed_at(),
    )

    assert result.outcome.status == "unavailable"
    assert result.outcome.response_class == "minute_response_invalid"
    assert result.snapshot_path is None
    assert client.queries == [KisPaperMinuteQuery(exchange="AMS", symbol="IWM")]
    assert not cache_root.exists()


def test_writes_a_source_safe_receipt_only_outside_the_repository(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    receipt = collect_and_write_kis_paper_iwm_m1_current_head(
        client=_MinuteClient([_page(_bar_count=1, next_cursor=None)]),
        cache_root=tmp_path / "market-data" / "iwm-current-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        market_data_root=tmp_path / "market-data",
        observed_at=_observed_at(),
    )

    assert receipt.evidence_path.is_relative_to(artifact_root)
    payload = receipt.evidence_path.read_text(encoding="utf-8")
    assert json.loads(payload) == receipt.result.outcome.safe_payload()
    assert "12345.67" not in payload
    assert "20260724" not in payload
    assert "access_token" not in payload
    with pytest.raises(ValueError, match="must stay outside Git"):
        validate_kis_paper_iwm_m1_current_head_cache_root(
            cache_root=repository_root / "raw-cache",
            repository_root=repository_root,
            market_data_root=tmp_path / "market-data",
        )


def test_rejects_non_market_data_or_active_private_cache_before_fetch(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    market_data_root = tmp_path / "market-data"
    active_private_cache = market_data_root / "us_equities" / "intraday"
    client = _MinuteClient([_page(_bar_count=1, next_cursor=None)])

    for cache_root in (tmp_path / "outside", active_private_cache):
        with pytest.raises(ValueError):
            collect_kis_paper_iwm_m1_current_head(
                client=client,
                cache_root=cache_root,
                repository_root=repository_root,
                market_data_root=market_data_root,
                protected_cache_roots=(active_private_cache,),
                observed_at=_observed_at(),
            )

    assert client.queries == []


def _page(
    *,
    _bar_count: int,
    next_cursor: str | None,
    last: str = "12345.67",
) -> KisPaperMinutePage:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="AMS", symbol="IWM"),
        bars=tuple(
            _bar(start + timedelta(minutes=index), last=last)
            for index in range(_bar_count)
        ),
        next_cursor=next_cursor,
        more="",
    )


def _conflicting_page() -> KisPaperMinutePage:
    stamp = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="AMS", symbol="IWM"),
        bars=(_bar(stamp, last="12345.67"), _bar(stamp, last="12345.68")),
        next_cursor=None,
        more="",
    )


def _bar(timestamp: datetime, *, last: str) -> KisPaperMinuteRawBar:
    last_value = Decimal(last)
    return KisPaperMinuteRawBar(
        exchange_date=timestamp.strftime("%Y%m%d"),
        exchange_time=timestamp.strftime("%H%M%S"),
        korea_date=timestamp.strftime("%Y%m%d"),
        korea_time=timestamp.strftime("%H%M%S"),
        open=Decimal("12345.67"),
        high=max(Decimal("12345.68"), last_value),
        low=Decimal("12345.66"),
        last=last_value,
        volume=Decimal("123"),
    )


def _observed_at() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
