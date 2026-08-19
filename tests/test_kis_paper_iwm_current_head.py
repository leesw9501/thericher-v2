from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data.kis_paper_iwm_current_head import (
    KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_ARTIFACT_DIRECTORY,
    build_kis_paper_iwm_current_head_ingestion_outcome,
    write_kis_paper_iwm_current_head_ingestion_evidence,
)
from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    KisPaperIwmM1CurrentHeadOutcome,
    write_kis_paper_iwm_m1_current_head_evidence,
)
from thericher_v2.data.kis_paper_iwm_m1_current_head_replay import (
    list_verified_kis_paper_iwm_m1_current_head_observations,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataCallCounts
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_IWM_CURRENT_HEAD_TARGET,
    KisPaperPrivateIntradayBackfillRun,
    validate_kis_paper_iwm_current_head_request,
)


def test_recovered_identical_page_records_no_new_raw_retention() -> None:
    outcome = build_kis_paper_iwm_current_head_ingestion_outcome(
        run=KisPaperPrivateIntradayBackfillRun(
            status="recovered",
            target_key="IWM/AMS/1m",
            row_count=1,
            exact_overlap_rows=1,
            reason="already_cached",
        ),
        call_counts=KisPaperMarketDataCallCounts(
            token_attempts=1,
            minute_page_attempts=1,
            daily_page_attempts=0,
        ),
        request_start_count=2,
        observed_at=_observed_at(),
    )

    assert outcome.status == "recovered"
    assert outcome.accepted_page_count == 1
    assert outcome.raw_market_data_retained is False
    assert outcome.safe_payload()["raw_market_data_retained"] is False
    with pytest.raises(ValueError, match="ingestion outcome is invalid"):
        replace(outcome, raw_market_data_retained=True)


def test_ingestion_receipt_isolated_from_existing_iwm_replay_receipt_root(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    existing_replay_root = artifact_root / "data" / "kis-paper-iwm-m1-current-head"
    existing_replay_root.mkdir(parents=True)
    outcome = build_kis_paper_iwm_current_head_ingestion_outcome(
        run=KisPaperPrivateIntradayBackfillRun(
            status="recovered",
            target_key="IWM/AMS/1m",
            row_count=1,
            exact_overlap_rows=1,
            reason="already_cached",
        ),
        call_counts=KisPaperMarketDataCallCounts(1, 1, 0),
        request_start_count=2,
        observed_at=_observed_at(),
    )

    evidence_path = write_kis_paper_iwm_current_head_ingestion_evidence(
        outcome,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert evidence_path.parent == (
        artifact_root / KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_ARTIFACT_DIRECTORY
    )
    assert evidence_path.parent != existing_replay_root
    write_kis_paper_iwm_m1_current_head_evidence(
        outcome=KisPaperIwmM1CurrentHeadOutcome(
            status="collected",
            observed_at=_observed_at(),
            row_count=1,
            exact_duplicate_rows=0,
            continuation_category="not_observed",
            cache_disposition="retained",
            response_class="accepted",
            raw_market_data_retained=True,
            snapshot_content_sha256="a" * 64,
        ),
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    observations = list_verified_kis_paper_iwm_m1_current_head_observations(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert len(observations) == 1
    assert observations[0].snapshot_content_sha256 == "a" * 64


def test_iwm_current_head_cache_stays_under_market_data_and_away_from_existing_roots(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    market_data_root = tmp_path / "market-data"
    active_private_root = market_data_root / "us_equities" / "kis_paper_private" / "intraday"
    existing_replay_root = (
        market_data_root / "us_equities" / "kis_paper_private" / "iwm_m1_current_head"
    )
    current_head_root = market_data_root / "us_equities" / "kis_paper_private" / "iwm_current_head"
    kwargs = {
        "target": KIS_PAPER_IWM_CURRENT_HEAD_TARGET,
        "repo_root": repository_root,
        "market_data_root": market_data_root,
        "protected_cache_roots": (active_private_root, existing_replay_root),
    }

    assert validate_kis_paper_iwm_current_head_request(
        cache_root=current_head_root,
        **kwargs,
    ) == current_head_root.resolve(strict=False)
    assert not current_head_root.exists()
    for invalid_root in (
        tmp_path / "outside-market-data",
        market_data_root,
        active_private_root,
        active_private_root / "child",
        existing_replay_root,
        existing_replay_root / "child",
    ):
        with pytest.raises(ValueError, match="cache root is invalid"):
            validate_kis_paper_iwm_current_head_request(
                cache_root=invalid_root,
                **kwargs,
            )


def _observed_at() -> datetime:
    return datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
