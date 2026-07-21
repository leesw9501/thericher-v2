"""Run the bounded offline L2 trade-quality gate on the private KIS daily panel."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KisPaperPrivateDailyCatalog,
    load_kis_paper_private_daily_catalog,
)
from thericher_v2.research.daily_trade_quality_gate import (
    DEFAULT_DAILY_TRADE_QUALITY_GATE_ARTIFACT_ROOT,
    DailyTradeQualityGateConfig,
    run_daily_trade_quality_gate,
)
from thericher_v2.research.kis_daily_comparative_validation import (
    DailySessionSegment,
    KisDailyComparativeContract,
    PrecontractExposure,
)

_PRECONTRACT_EXPOSURE = PrecontractExposure(
    source_id="daily-three-etf-relative-strength-v0-smoke-20260722T0221",
    first_observed_session=date(2024, 4, 3),
    last_observed_session=date(2026, 7, 17),
    evidence_sha256="sha256:f848f4efa1e86df4e4b0d29fa864188476af9a99b45ce972a85e3f6d33abe7c1",
    evidence_reference=(
        "D:/thericher-v2/model-artifacts/daily-three-etf-relative-strength-v0/"
        "daily-three-etf-relative-strength-v0-smoke-20260722T0221/run.json"
    ),
)
_FROZEN_DATASET_ID = "kis.paper.private.daily.backfill-v1.common-panel"
_FROZEN_DATASET_HASH = "sha256:4495dea26c5a27e6949b2b0dad05d82f4c555748191ed45cb880d7a242ced9b7"
_FROZEN_INDEX_HASH = "sha256:343691f6ff814b0d1d0c046782fd5af26d9225f4bada021e2a7820c205ed5408"
_FROZEN_COMMON_SESSION_COUNT = 694
_FROZEN_DEVELOPMENT_RANGE = (0, 414)
_FROZEN_PURGE_RANGE = (414, 416)
_FROZEN_VALIDATION_RANGE = (416, 554)
_FROZEN_EMBARGO_RANGE = (554, 556)
_FROZEN_HOLDOUT_RANGE = (556, 694)
_FROZEN_PREFIX_SESSION_COUNT = 556
_FROZEN_PREFIX_FIRST_SESSION = date(2023, 10, 10)
_FROZEN_PREFIX_LAST_SESSION = date(2025, 12, 26)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_DAILY_TRADE_QUALITY_GATE_ARTIFACT_ROOT,
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    run_id = arguments.run_id or f"kis-daily-trade-quality-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    catalog = load_kis_paper_private_daily_catalog(
        arguments.cache_root,
        expected_index_hash=_FROZEN_INDEX_HASH,
        end_session=_FROZEN_PREFIX_LAST_SESSION,
        repo_root=arguments.repo_root,
    )
    _assert_frozen_prefix_catalog(catalog)
    contract = _frozen_contract()
    _assert_frozen_contract(contract)
    result = run_daily_trade_quality_gate(
        catalog,
        contract=contract,
        config=DailyTradeQualityGateConfig(run_id=run_id),
        artifact_root=arguments.artifact_root,
        repo_root=arguments.repo_root,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "status": result.status,
                "stop_reasons": list(result.stop_reasons),
                "development_entry_count": result.development_entry_count,
                "all_fills_local_paper": result.all_fills_local_paper,
                "summary_path": str(result.summary_path),
            },
            sort_keys=True,
        )
    )
    return 0


def _assert_frozen_prefix_catalog(catalog: KisPaperPrivateDailyCatalog) -> None:
    if (
        catalog.dataset_id != _FROZEN_DATASET_ID
        or catalog.index_hash != _FROZEN_INDEX_HASH
        or len(catalog.common_sessions) != _FROZEN_PREFIX_SESSION_COUNT
        or catalog.common_sessions[0] != _FROZEN_PREFIX_FIRST_SESSION
        or catalog.common_sessions[-1] != _FROZEN_PREFIX_LAST_SESSION
    ):
        raise ValueError("L2 trade-quality gate input no longer matches its frozen KIS prefix")


def _frozen_contract() -> KisDailyComparativeContract:
    return KisDailyComparativeContract(
        contract_id="kis-daily-trade-quality-gate-v1",
        dataset_id=_FROZEN_DATASET_ID,
        dataset_hash=_FROZEN_DATASET_HASH,
        index_hash=_FROZEN_INDEX_HASH,
        common_session_count=_FROZEN_COMMON_SESSION_COUNT,
        development=DailySessionSegment(
            label="development",
            start_index=0,
            stop_index=414,
            first_session=date(2023, 10, 10),
            last_session=date(2025, 6, 4),
            session_hash="sha256:97a5ecfdd1d10669ccd6e8d13e04439eed3e03abeac4ea4ac88ca1916983a40e",
        ),
        purge=DailySessionSegment(
            label="purge_after_development",
            start_index=414,
            stop_index=416,
            first_session=date(2025, 6, 5),
            last_session=date(2025, 6, 6),
            session_hash="sha256:090338f1e38263f583583eaa0df5379a874ce4efd0695683d2c9b145b265fba5",
        ),
        validation=DailySessionSegment(
            label="validation",
            start_index=416,
            stop_index=554,
            first_session=date(2025, 6, 9),
            last_session=date(2025, 12, 23),
            session_hash="sha256:e61fe440543a6f850db934a0cdba79080d2d2f455fef64700cdf4d0bd4587b39",
        ),
        embargo=DailySessionSegment(
            label="embargo_after_validation",
            start_index=554,
            stop_index=556,
            first_session=date(2025, 12, 24),
            last_session=date(2025, 12, 26),
            session_hash="sha256:837413000c60234c2c8e0d3faf9bc0e7ededda306c67ffbb668156002fd01f1e",
        ),
        sealed_holdout=DailySessionSegment(
            label="sealed_holdout",
            start_index=556,
            stop_index=694,
            first_session=date(2025, 12, 29),
            last_session=date(2026, 7, 17),
            session_hash="sha256:64d47fbb63acb35a6480e4433afa017682e3298f66a3d8f2db23648a0f70c8a9",
            state="burned_precontract",
        ),
        precontract_exposure=_PRECONTRACT_EXPOSURE,
    )


def _assert_frozen_contract(contract: KisDailyComparativeContract) -> None:
    segments = (
        (getattr(contract, "development", None), _FROZEN_DEVELOPMENT_RANGE, None),
        (getattr(contract, "purge", None), _FROZEN_PURGE_RANGE, None),
        (getattr(contract, "validation", None), _FROZEN_VALIDATION_RANGE, None),
        (getattr(contract, "embargo", None), _FROZEN_EMBARGO_RANGE, None),
        (getattr(contract, "sealed_holdout", None), _FROZEN_HOLDOUT_RANGE, "burned_precontract"),
    )
    for segment, (start, stop), expected_state in segments:
        if (
            segment is None
            or getattr(segment, "start_index", None) != start
            or getattr(segment, "stop_index", None) != stop
            or (expected_state is not None and getattr(segment, "state", None) != expected_state)
        ):
            raise ValueError("L2 trade-quality gate split no longer matches its frozen geometry")


if __name__ == "__main__":
    raise SystemExit(main())
