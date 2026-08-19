from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.data.kis_paper_iwm_temporal_reach_probe import (
    KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_ARTIFACT_DIRECTORY,
    run_kis_paper_iwm_temporal_reach_probe,
    write_kis_paper_iwm_temporal_reach_probe_evidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)


class _ProbeClient:
    def __init__(self, outcomes: list[KisPaperMinutePage | KisPaperMarketDataError]) -> None:
        self._outcomes = list(outcomes)
        self.queries: list[KisPaperMinuteQuery] = []

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        request_count = len(self.queries)
        return KisPaperMarketDataCallCounts(
            token_attempts=1 if request_count else 0,
            minute_page_attempts=request_count,
            daily_page_attempts=0,
        )

    def fetch_minute_page(self, query: KisPaperMinuteQuery) -> KisPaperMinutePage:
        self.queries.append(query)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, KisPaperMarketDataError):
            raise outcome
        return outcome


def test_probe_reaches_only_a_strictly_older_nonconflicting_second_page_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_network_and_environment(monkeypatch)
    client = _ProbeClient(
        [
            _page(("20260818100000", "20260818095900"), continuation="M"),
            _page(("20260818095800", "20260818095700"), continuation=""),
        ]
    )

    outcome = run_kis_paper_iwm_temporal_reach_probe(client=client, monotonic_clock=lambda: 0.0)

    assert outcome.status == "reachable"
    assert outcome.accepted_page_count == 2
    assert outcome.continuation_disposition == "accepted_older_nonconflicting"
    assert outcome.overlap_direction == "strictly_older_nonconflicting"
    assert outcome.safe_payload()["model_input_eligibility"] is False
    assert [query.request_intent for query in client.queries] == [
        "iwm_temporal_reach_probe_head",
        "iwm_temporal_reach_probe_continuation",
    ]
    assert client.queries[1].include_previous_day is True
    assert client.queries[1].continuation_next == "1"


@pytest.mark.parametrize("continuation", ["", "X"])
def test_probe_does_not_request_a_second_page_without_a_recognized_header(
    continuation: str,
) -> None:
    client = _ProbeClient(
        [_page(("20260818100000", "20260818095900"), continuation=continuation)]
    )

    outcome = run_kis_paper_iwm_temporal_reach_probe(client=client, monotonic_clock=lambda: 0.0)

    assert outcome.status == "continuation_not_observed"
    assert outcome.accepted_page_count == 1
    assert outcome.continuation_disposition == "header_not_recognized"
    assert len(client.queries) == 1


def test_probe_never_calls_an_overlapping_second_page_reachable() -> None:
    client = _ProbeClient(
        [
            _page(("20260818100000", "20260818095900"), continuation="F"),
            _page(("20260818095900", "20260818095800"), continuation=""),
        ]
    )

    outcome = run_kis_paper_iwm_temporal_reach_probe(client=client, monotonic_clock=lambda: 0.0)

    assert outcome.status == "non_older_or_conflicting"
    assert outcome.continuation_disposition == "accepted_non_older_or_conflicting"
    assert outcome.overlap_direction == "overlap_or_not_older"


def test_probe_records_a_continuation_failure_without_retry() -> None:
    client = _ProbeClient(
        [
            _page(("20260818100000", "20260818095900"), continuation="M"),
            KisPaperMarketDataError("rate_limited"),
        ]
    )

    outcome = run_kis_paper_iwm_temporal_reach_probe(client=client, monotonic_clock=lambda: 0.0)

    assert outcome.status == "input_unavailable"
    assert outcome.accepted_page_count == 1
    assert outcome.continuation_disposition == "continuation_unavailable"
    assert outcome.minute_page_request_count == 2
    assert len(client.queries) == 2


def test_probe_receipt_is_external_and_excludes_raw_values_and_timestamps(tmp_path: Path) -> None:
    client = _ProbeClient(
        [
            _page(("20260818100000", "20260818095900"), continuation="M"),
            _page(("20260818095800", "20260818095700"), continuation=""),
        ]
    )
    outcome = run_kis_paper_iwm_temporal_reach_probe(client=client, monotonic_clock=lambda: 0.0)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    receipt = write_kis_paper_iwm_temporal_reach_probe_evidence(
        outcome=outcome,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    assert receipt.evidence_path.parent == (
        artifact_root / KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_ARTIFACT_DIRECTORY
    )
    assert receipt.evidence_path.is_relative_to(artifact_root)
    payload = receipt.outcome.safe_payload()
    assert json.loads(receipt.evidence_path.read_text(encoding="utf-8")) == payload
    assert receipt.evidence_sha256 == "sha256:" + hashlib.sha256(
        receipt.evidence_path.read_bytes()
    ).hexdigest()
    assert payload["model_input_eligibility"] is False
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in ("20260818", "100", "0959", "Decimal", str(receipt.evidence_path)):
        assert forbidden not in serialized


def test_probe_rejects_an_artifact_intermediate_symlink(tmp_path: Path) -> None:
    client = _ProbeClient([_page(("20260818100000", "20260818095900"), continuation="")])
    outcome = run_kis_paper_iwm_temporal_reach_probe(client=client, monotonic_clock=lambda: 0.0)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    try:
        (artifact_root / "data").symlink_to(outside_root, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable on this host")

    with pytest.raises(ValueError, match="artifact destination is invalid"):
        write_kis_paper_iwm_temporal_reach_probe_evidence(
            outcome=outcome,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )


def _page(
    timestamps: tuple[str, ...],
    *,
    continuation: str,
) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="AMS", symbol="IWM"),
        bars=tuple(_bar(value) for value in timestamps),
        next_cursor="1" if continuation in {"M", "F"} else None,
        more="",
        continuation_signal=(
            "recognized_continuation"
            if continuation in {"M", "F"}
            else "blank_or_absent"
            if continuation == ""
            else "unrecognized_nonblank"
        ),
    )


def _bar(value: str) -> KisPaperMinuteRawBar:
    timestamp = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return KisPaperMinuteRawBar(
        exchange_date=timestamp.strftime("%Y%m%d"),
        exchange_time=timestamp.strftime("%H%M%S"),
        korea_date=timestamp.strftime("%Y%m%d"),
        korea_time=timestamp.strftime("%H%M%S"),
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        last=Decimal("101"),
        volume=Decimal("1000"),
    )


def _forbid_network_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        os,
        "getenv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("environment read")),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )
