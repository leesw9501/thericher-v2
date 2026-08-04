from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import thericher_v2.data.kis_spy_paginated_prefix_capability as capability
from thericher_v2.execution.kis_market_data import (
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMinuteQuery,
)

_EASTERN = ZoneInfo("America/New_York")
_SESSION_DATE = date(2026, 8, 3)
_OBSERVER_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "observe_kis_paper_spy_paginated_prefix_capability.py"
)
_COLLECTOR_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "collect_kis_paper_spy_paginated_prefix_capability.py"
)


@dataclass(frozen=True)
class _Row:
    timestamp: datetime

    def as_document(self) -> dict[str, str]:
        eastern = self.timestamp.astimezone(_EASTERN)
        return {
            "xymd": eastern.strftime("%Y%m%d"),
            "xhms": eastern.strftime("%H%M%S"),
            "kymd": "20260804",
            "khms": "000000",
            "open": "913.111",
            "high": "914.111",
            "low": "912.111",
            "last": "913.611",
            "evol": "7777",
        }


@dataclass(frozen=True)
class _Page:
    bars: tuple[_Row, ...]
    next_cursor: str | None
    continuation_signal: str | None = None


class _ResponseTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def test_paginated_full_prefix_is_exactly_bound_to_one_clean_fresh_run(tmp_path: Path) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    control = capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    calls: list[tuple[str | None, str | None]] = []
    pages = _prefix_pages(_SESSION_DATE)

    def fetch_page(next_value: str | None, keyb: str | None) -> _Page:
        calls.append((next_value, keyb))
        return pages.pop(0)

    collection = capability.collect_spy_paginated_prefix_pages(fetch_page=fetch_page)
    run = capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=3,
    )
    preflight = capability.preflight_spy_paginated_prefix_positive(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff + timedelta(seconds=2),
    )
    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )

    assert control.status == "negative_control_clean"
    assert preflight.status == "ready"
    assert collection.status == "collected"
    assert run.manifest_path.is_file()
    assert calls == [
        (None, None),
        ("1", "20260803132900"),
        ("1", "20260803112900"),
    ]
    assert observation.status == "availability_within_validity_after_collection"
    assert observation.complete_minute_count == 360
    assert observation.missing_minute_count == 0
    assert observation.page_seam_status == "continuous"
    assert observation.terminal_continuation_signal == "blank_or_absent"
    manifest = json.loads(run.manifest_path.read_text(encoding="ascii"))
    assert manifest["collection"]["terminal_continuation_signal"] == "blank_or_absent"
    payload = json.loads(observation.artifact_path.read_text(encoding="ascii"))
    assert payload["collection"]["terminal_continuation_signal"] == "blank_or_absent"
    assert payload["timing"]["collection_started_at"] == {
        "eastern": "2026-08-03T15:30:01-04:00",
        "eastern_dst": True,
        "eastern_utc_offset": "-0400",
        "utc": "2026-08-03T19:30:01Z",
    }
    assert "913.111" not in json.dumps(payload, sort_keys=True)
    assert "7777" not in json.dumps(payload, sort_keys=True)
    assert str(cache_root) not in json.dumps(payload, sort_keys=True)


def test_raw_continuation_header_is_never_persisted_or_projected(tmp_path: Path) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    raw_header_marker = "unrecognized-header-value-for-test"
    page_rows = [row.as_document() for row in _prefix_pages(_SESSION_DATE)[0].bars]
    transport = _ResponseTransport(
        [
            KisMarketDataResponse.from_payload({"access_token": "test-token"}),
            KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"next": "0", "more": "0"},
                    "output2": page_rows,
                },
                headers={"tr_cont": raw_header_marker},
            ),
        ]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda next_value, keyb: client.fetch_minute_page(
            KisPaperMinuteQuery(
                exchange="AMS",
                symbol="SPY",
                continuation_next=next_value,
                continuation_key=keyb,
            )
        )
    )
    run = capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=1,
    )
    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )
    fact = capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
    )

    assert collection.pages[-1].continuation_signal == "unrecognized_nonblank"
    assert observation.terminal_continuation_signal == "unrecognized_nonblank"
    assert fact.terminal_continuation_signal == "unrecognized_nonblank"
    persisted_payloads = [
        run.manifest_path.read_text(encoding="ascii"),
        (run.manifest_path.parent / "raw-pages.json").read_text(encoding="ascii"),
        observation.artifact_path.read_text(encoding="ascii"),
        json.dumps(fact.safe_payload(), sort_keys=True),
    ]
    assert all(raw_header_marker not in payload for payload in persisted_payloads)


def test_legacy_zero_page_receipt_has_no_terminal_continuation_signal(tmp_path: Path) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: _Page(bars=(), next_cursor=None)
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=1,
    )
    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )
    legacy_payload = json.loads(observation.artifact_path.read_text(encoding="ascii"))
    legacy_payload["collection"].pop("terminal_continuation_signal")
    observation.artifact_path.write_bytes(_canonical_bytes(legacy_payload))
    fact = capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
    )

    assert collection.pages == ()
    assert observation.terminal_continuation_signal is None
    assert fact.terminal_continuation_signal is None


def test_unrecognized_terminal_continuation_is_retained_only_as_a_safe_category(
    tmp_path: Path,
) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    first_page = _prefix_pages(_SESSION_DATE)[0]
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: _Page(
            bars=first_page.bars,
            next_cursor=None,
            continuation_signal="unrecognized_nonblank",
        )
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=1,
    )
    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )
    fact = capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
    )

    assert collection.status == "collected"
    assert collection.pages[-1].continuation_signal == "unrecognized_nonblank"
    assert observation.status == "incomplete_prefix"
    assert observation.terminal_continuation_signal == "unrecognized_nonblank"
    assert fact.result_class == "measurement_incomplete_or_invalid"
    assert fact.terminal_continuation_signal == "unrecognized_nonblank"
    payload = json.loads(observation.artifact_path.read_text(encoding="ascii"))
    assert payload["collection"]["terminal_continuation_signal"] == "unrecognized_nonblank"
    assert "tr_cont" not in json.dumps(payload, sort_keys=True)


def test_negative_control_detects_preexisting_planned_run_and_blocks_collection(
    tmp_path: Path,
) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    planned_run = cache_root / "runs" / run_id
    planned_run.mkdir(parents=True)

    control = capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    preflight = capability.preflight_spy_paginated_prefix_positive(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff,
    )

    assert control.status == "negative_control_violation"
    assert control.valid_for_collection is False
    assert preflight.status == "control_not_clean"


def test_observer_uses_its_own_clock_and_rejects_a_delayed_negative_control(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    observer = _load_observer_script()
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    args = [
        "--phase",
        "negative-control",
        "--run-id",
        run_id,
        "--session-date",
        _SESSION_DATE.isoformat(),
        "--cache-root",
        str(cache_root),
        "--artifact-root",
        str(artifact_root),
        "--repository-root",
        str(repository),
    ]

    assert observer.main(args, now_utc=lambda: cutoff - timedelta(seconds=1)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["timing"]["observed_at"]["utc"] == "2026-08-03T19:29:59Z"

    with pytest.raises(ValueError, match="negative control"):
        observer.main(args, now_utc=lambda: cutoff)
    with pytest.raises(SystemExit):
        observer.main(args + ["--observed-at", (cutoff - timedelta(seconds=1)).isoformat()])


def test_collector_uses_its_own_clock_and_stops_before_credentials_outside_the_window(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    collector = _load_script("spy_prefix_collector", _COLLECTOR_SCRIPT)
    repository, cache_root, _artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)

    def unexpected_config_loader(_path: Path) -> object:
        raise AssertionError("collector must not load credentials outside the positive window")

    exit_code = collector.main(
        [
            "--execute",
            "--run-id",
            run_id,
            "--session-date",
            _SESSION_DATE.isoformat(),
            "--cache-root",
            str(cache_root),
            "--repository-root",
            str(repository),
        ],
        config_loader=unexpected_config_loader,
        now_utc=lambda: cutoff + timedelta(minutes=1),
    )

    assert exit_code == 20
    assert json.loads(capsys.readouterr().out) == {
        "collection_started_at": "2026-08-03T19:31:00Z",
        "kind": capability.KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
        "reason": "outside_stage_window",
        "run_id": run_id,
        "status": "collection_unavailable",
    }


def test_missing_page_seam_cannot_be_reclassified_as_complete_prefix(tmp_path: Path) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    pages = _prefix_pages(_SESSION_DATE)
    first = pages[0]
    pages[0] = _Page(bars=first.bars[1:], next_cursor=first.next_cursor)
    iterator = iter(pages)
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: next(iterator)
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=3,
    )

    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )

    assert observation.status == "page_seam_invalid"
    assert observation.complete_minute_count == 359
    assert observation.missing_minute_count == 1


def test_a_noncompleted_1530_bar_cannot_be_accepted_as_a_clean_prefix(tmp_path: Path) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    prefix_pages = _prefix_pages(_SESSION_DATE)
    pages = iter(
        [
            _Page((_Row(cutoff),), "1"),
            *prefix_pages,
        ]
    )
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: next(pages)
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=4,
    )

    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )

    assert observation.status == "page_seam_invalid"
    assert observation.complete_minute_count == 360
    assert observation.missing_minute_count == 0


def test_collection_never_requests_a_fifth_page() -> None:
    cutoff = _cutoff(_SESSION_DATE)
    pages = [_Page((_Row(cutoff - timedelta(minutes=index + 1)),), "1") for index in range(5)]
    calls: list[tuple[str | None, str | None]] = []

    def fetch_page(next_value: str | None, keyb: str | None) -> _Page:
        calls.append((next_value, keyb))
        return pages[len(calls) - 1]

    collection = capability.collect_spy_paginated_prefix_pages(fetch_page=fetch_page)

    assert collection.status == "collected"
    assert collection.reason == "page_limit_reached"
    assert len(collection.pages) == 4
    assert len(calls) == capability.KIS_SPY_PAGINATED_PREFIX_MAX_PAGES


def test_observer_rejects_a_tampered_page_larger_than_the_provider_page_bound(
    tmp_path: Path,
) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    iterator = iter(_prefix_pages(_SESSION_DATE))
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: next(iterator)
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=3,
    )
    run_root = cache_root / "runs" / run_id
    raw_path = run_root / "raw-pages.json"
    manifest_path = run_root / "manifest.json"
    raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_payload["pages"] = [
        {
            "index": 1,
            "continuation_advertised": False,
            "rows": [
                row.as_document()
                for page in _prefix_pages(_SESSION_DATE)
                for row in page.bars
            ],
        }
    ]
    raw_bytes = _canonical_bytes(raw_payload)
    raw_path.write_bytes(raw_bytes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["collection"]["page_count"] = 1
    manifest["collection"]["continuation_advertised_on_final_page"] = False
    manifest["raw_content_sha256"] = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    manifest_path.write_bytes(_canonical_bytes(manifest))

    observation = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )

    assert observation.status == "fresh_run_invalid"


def test_collection_must_be_new_and_all_capture_timestamps_must_finish_before_1531(
    tmp_path: Path,
) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    cutoff = _cutoff(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    iterator = iter(_prefix_pages(_SESSION_DATE))
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: next(iterator)
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        run_id=run_id,
        session_date=_SESSION_DATE,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=3,
    )

    expired = capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(minutes=1),
    )

    assert expired.status == "capture_expired"
    with pytest.raises(ValueError, match="fresh run already exists"):
        capability.write_spy_paginated_prefix_collection_run(
            collection=collection,
            cache_root=cache_root,
            repository_root=repository,
            run_id=run_id,
            session_date=_SESSION_DATE,
            collection_started_at=cutoff + timedelta(seconds=2),
            token_attempts=1,
            minute_page_attempts=3,
        )


@pytest.mark.parametrize(
    ("session_date", "cutoff_utc", "offset"),
    [
        (date(2026, 3, 9), datetime(2026, 3, 9, 19, 30, tzinfo=UTC), "-0400"),
        (date(2026, 11, 2), datetime(2026, 11, 2, 20, 30, tzinfo=UTC), "-0500"),
    ],
    ids=["daylight-saving", "standard-time"],
)
def test_control_and_preflight_use_serialized_eastern_dst_geometry(
    tmp_path: Path,
    session_date: date,
    cutoff_utc: datetime,
    offset: str,
) -> None:
    repository, cache_root, artifact_root = _roots(tmp_path)
    run_id = capability.run_id_for_session(session_date)
    control = capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=session_date,
        run_id=run_id,
        observed_at=cutoff_utc - timedelta(seconds=30),
    )
    preflight = capability.preflight_spy_paginated_prefix_positive(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=session_date,
        run_id=run_id,
        observed_at=cutoff_utc,
    )

    payload = json.loads(control.artifact_path.read_text(encoding="ascii"))
    assert payload["timing"]["observed_at"]["eastern_utc_offset"] == offset
    assert preflight.status == "ready"


def test_observer_has_no_network_credential_or_execution_surface(tmp_path: Path) -> None:
    module_source = Path(capability.__file__).read_text(encoding="ascii")
    observer_source = _OBSERVER_SCRIPT.read_text(encoding="ascii")

    assert "thericher_v2.execution" not in module_source
    assert "os.environ" not in module_source
    assert "KIS_PAPER_APP_KEY" not in module_source
    assert "KIS_LIVE" not in module_source
    assert "thericher_v2.execution" not in observer_source
    assert "os.environ" not in observer_source
    assert "KIS_PAPER_APP_KEY" not in observer_source
    assert "KIS_LIVE" not in observer_source
    assert "--observed-at" not in observer_source
    collector_source = _COLLECTOR_SCRIPT.read_text(encoding="ascii")
    assert "--collection-started-at" not in collector_source

    completed = subprocess.run(
        [sys.executable, "-c", _OBSERVER_ISOLATION_SCRIPT, str(tmp_path / "isolated")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == {"status": "negative_control_clean"}


def test_external_cache_and_artifact_roots_cannot_escape_into_git(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    cutoff = _cutoff(_SESSION_DATE)
    with pytest.raises(ValueError, match="outside Git"):
        capability.record_spy_paginated_prefix_negative_control(
            cache_root=repository / "market-data",
            artifact_root=tmp_path / "artifacts",
            repository_root=repository,
            session_date=_SESSION_DATE,
            run_id=capability.run_id_for_session(_SESSION_DATE),
            observed_at=cutoff - timedelta(seconds=30),
        )
    with pytest.raises(ValueError, match="outside Git"):
        capability.record_spy_paginated_prefix_negative_control(
            cache_root=tmp_path / "market-data",
            artifact_root=repository / "artifacts",
            repository_root=repository,
            session_date=_SESSION_DATE,
            run_id=capability.run_id_for_session(_SESSION_DATE),
            observed_at=cutoff - timedelta(seconds=30),
        )


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repo"
    cache_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    repository.mkdir()
    return repository, cache_root, artifact_root


def _load_observer_script() -> object:
    return _load_script("spy_prefix_observer", _OBSERVER_SCRIPT)


def _load_script(name: str, path: Path) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError("observer script is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cutoff(session_date: date) -> datetime:
    return (
        datetime.combine(session_date, datetime.min.time(), _EASTERN)
        .replace(
            hour=15,
            minute=30,
        )
        .astimezone(UTC)
    )


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )


def _prefix_pages(session_date: date) -> list[_Page]:
    cutoff = _cutoff(session_date)
    starts = [
        cutoff - timedelta(minutes=capability.KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES - index)
        for index in range(capability.KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES)
    ]
    return [
        _Page(tuple(_Row(timestamp) for timestamp in starts[240:]), "1"),
        _Page(tuple(_Row(timestamp) for timestamp in starts[120:240]), "1"),
        _Page(tuple(_Row(timestamp) for timestamp in starts[:120]), None),
    ]


_OBSERVER_ISOLATION_SCRIPT = r"""
import json
import os
import socket
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path


def deny(*_args, **_kwargs):
    raise AssertionError("observer must not access a network or environment")


class DeniedEnvironment:
    def __getitem__(self, _key):
        deny()

    def get(self, _key, _default=None):
        deny()

    def __contains__(self, _key):
        deny()


import thericher_v2.data.kis_spy_paginated_prefix_capability as capability

socket.socket = deny
socket.create_connection = deny
os.environ = DeniedEnvironment()

root = Path(sys.argv[1])
repository = root / "repo"
cache = root / "market"
artifact = root / "artifact"
repository.mkdir(parents=True)
cutoff = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
result = capability.record_spy_paginated_prefix_negative_control(
    cache_root=cache,
    artifact_root=artifact,
    repository_root=repository,
    session_date=date(2026, 8, 3),
    run_id=capability.run_id_for_session(date(2026, 8, 3)),
    observed_at=cutoff - timedelta(seconds=30),
)
print(json.dumps({"status": result.status}, sort_keys=True))
"""
