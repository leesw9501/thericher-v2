"""Execute one scheduled QQQ/SPY D1 revision-leakage measurement."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_d1_prospective_observation_pairing import (
    KisPaperD1ProspectiveObservationPairingError,
    run_kis_paper_d1_prospective_observation_pairing,
)
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_pair_forward import (
    UrllibKisPaperDailyPairForwardTransport,
)

_CANONICAL_REPOSITORY_ROOT = Path("/app")
_CANONICAL_CACHE_ROOT = Path("/app/market_data")
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
        _emit({"status": "unavailable", "reason": "execute_flag_required"})
        return
    if not _canonical_container_roots(
        cache_root=Path(args.cache_root),
        control_root=Path(args.control_root),
        artifact_root=Path(args.artifact_root),
        repository_root=Path(args.repository_root),
    ):
        _emit({"status": "unavailable", "reason": "canonical_container_roots_required"})
        return
    request_gate = KisPaperMarketDataRateGate(control_root=Path(args.control_root))
    token_start_gate = KisPaperMarketDataTokenStartGate(control_root=Path(args.control_root))

    def client_factory() -> KisPaperMarketDataClient:
        return KisPaperMarketDataClient(
            config=load_kis_paper_market_data_environment_config(environment=environment),
            transport=UrllibKisPaperDailyPairForwardTransport(
                request_gate=request_gate,
                token_start_gate=token_start_gate,
            ),
            # One page per target shares the same client-wide attempt budget.
            max_daily_page_attempts=len(KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS),
        )

    try:
        result = run_kis_paper_d1_prospective_observation_pairing(
            cache_root=Path(args.cache_root),
            artifact_root=Path(args.artifact_root),
            repository_root=Path(args.repository_root),
            observed_at=clock(),
            client_factory=client_factory,
        )
    except (
        KisPaperD1ProspectiveObservationPairingError,
        KisPaperMarketDataError,
        OSError,
        ValueError,
    ):
        _emit({"status": "unavailable", "reason": "observer_unavailable"})
        return
    _emit(result.safe_payload())


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


def _emit(payload: Mapping[str, object]) -> None:
    print(json.dumps(dict(payload), sort_keys=True))


if __name__ == "__main__":
    main()
