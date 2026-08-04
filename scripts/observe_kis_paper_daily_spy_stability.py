"""Execute one separately timed KIS Paper SPY D1 stability measurement."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_daily_spy_stability_observer import (
    KisPaperDailySpyStabilityObserverError,
    observe_kis_paper_daily_spy_stability,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

_CANONICAL_REPOSITORY_ROOT = Path("/app")
_CANONICAL_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/daily-head/v1")
_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    environment: Mapping[str, str] | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=_CANONICAL_CACHE_ROOT)
    parser.add_argument("--control-root", type=Path, default=_CANONICAL_CONTROL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_CANONICAL_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_CANONICAL_REPOSITORY_ROOT)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "unavailable", "reason": "execute_flag_required"}))
        return
    if not _canonical_container_roots(
        cache_root=Path(args.cache_root),
        control_root=Path(args.control_root),
        artifact_root=Path(args.artifact_root),
        repository_root=Path(args.repository_root),
    ):
        print(json.dumps({"status": "unavailable", "reason": "canonical_container_roots_required"}))
        return

    request_gate = KisPaperMarketDataRateGate(control_root=Path(args.control_root))
    token_start_gate = KisPaperMarketDataTokenStartGate(control_root=Path(args.control_root))

    def client_factory() -> KisPaperMarketDataClient:
        return KisPaperMarketDataClient(
            config=load_kis_paper_market_data_environment_config(environment=environment),
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=request_gate,
                token_start_gate=token_start_gate,
            ),
            max_minute_page_attempts=1,
            max_daily_page_attempts=1,
        )

    try:
        observation = observe_kis_paper_daily_spy_stability(
            cache_root=Path(args.cache_root),
            artifact_root=Path(args.artifact_root),
            repository_root=Path(args.repository_root),
            observed_at=clock(),
            client_factory=client_factory,
        )
    except (KisPaperDailySpyStabilityObserverError, KisPaperMarketDataError, OSError, ValueError):
        print(
            json.dumps(
                {"status": "unavailable", "reason": "observer_unavailable"},
                sort_keys=True,
            )
        )
        return
    print(json.dumps(observation.safe_payload(), sort_keys=True))


def _canonical_container_roots(
    *,
    cache_root: Path,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    return (
        cache_root == _CANONICAL_CACHE_ROOT
        and control_root == _CANONICAL_CONTROL_ROOT
        and artifact_root == _CANONICAL_ARTIFACT_ROOT
        and repository_root == _CANONICAL_REPOSITORY_ROOT
    )


if __name__ == "__main__":
    main()
