"""Replay one retained IWM current-head snapshot without provider access."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT,
    KIS_PAPER_MARKET_DATA_ROOT,
)
from thericher_v2.data.kis_paper_iwm_m1_current_head_replay import (
    list_verified_kis_paper_iwm_m1_current_head_observations,
    load_selected_verified_kis_paper_iwm_m1_current_head_replay,
    resample_verified_kis_paper_iwm_m1_current_head_replay,
    write_kis_paper_iwm_m1_current_head_replay_evidence,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=KIS_PAPER_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--observation-id")
    parser.add_argument("--list-observations", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        if arguments.list_observations:
            if arguments.observation_id is not None:
                raise ValueError("observation selection is invalid")
            observations = list_verified_kis_paper_iwm_m1_current_head_observations(
                artifact_root=arguments.artifact_root,
                repository_root=_REPOSITORY_ROOT,
            )
            print(
                json.dumps(
                    {
                        "broker_or_network_used": False,
                        "observations": [
                            observation.safe_payload() for observation in observations
                        ],
                        "paper_only": True,
                        "route_class": "offline_local_cache",
                        "status": "observations_listed",
                    },
                    sort_keys=True,
                )
            )
            return 0
        if arguments.observation_id is None:
            raise ValueError("observation selection is required")
        replay = load_selected_verified_kis_paper_iwm_m1_current_head_replay(
            observation_id=arguments.observation_id,
            cache_root=arguments.cache_root,
            artifact_root=arguments.artifact_root,
            repository_root=_REPOSITORY_ROOT,
            market_data_root=arguments.market_data_root,
        )
        resampled = resample_verified_kis_paper_iwm_m1_current_head_replay(replay)
        write_kis_paper_iwm_m1_current_head_replay_evidence(
            replay=replay,
            resampled=resampled,
            artifact_root=arguments.artifact_root,
            repository_root=_REPOSITORY_ROOT,
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "broker_or_network_used": False,
                    "paper_only": True,
                    "route_class": "offline_local_cache",
                    "status": "unavailable",
                },
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(replay.safe_payload(resampled=resampled), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
