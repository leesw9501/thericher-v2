"""Freeze the offline NAS D1 sequence campaign contract without training."""

from __future__ import annotations

import json
from pathlib import Path

from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH,
    load_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.kis_nas_d1_sequence_campaign import (
    KIS_NAS_D1_SEQUENCE_PRECOMMIT_ROOT,
    build_kis_nas_d1_sequence_campaign,
    write_kis_nas_d1_sequence_campaign_precommit,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source_input = load_kis_paper_daily_history_sequence_input(
        KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH,
        repo_root=_REPOSITORY_ROOT,
    )
    campaign_input = build_kis_nas_d1_sequence_campaign(source_input)
    precommit = write_kis_nas_d1_sequence_campaign_precommit(
        campaign_input,
        artifact_root=KIS_NAS_D1_SEQUENCE_PRECOMMIT_ROOT,
        repo_root=_REPOSITORY_ROOT,
    )
    print(
        json.dumps(
            {
                "status": "precommitted",
                "campaign_id": campaign_input.contract.campaign_id,
                "campaign_contract_hash": campaign_input.contract.contract_hash,
                "precommit_hash": precommit.precommit_hash,
                "development_sample_counts": {
                    symbol: len(samples)
                    for symbol, samples in campaign_input.development_samples_by_symbol.items()
                },
                "validation_sample_counts": {
                    symbol: len(samples)
                    for symbol, samples in campaign_input.validation_samples_by_symbol.items()
                },
                "model_fitting_materialized": False,
                "prediction_materialized": False,
                "replay_materialized": False,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
