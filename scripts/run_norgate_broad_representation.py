"""Run a bounded target-free Norgate D1 sequence-representation study."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT
from thericher_v2.research.norgate_broad_representation import (
    NORGATE_BROAD_REPRESENTATION_ID,
    freeze_representation_campaign,
    load_frozen_observed_return_dataset,
    run_representation_cpu_smoke,
    run_representation_cuda_batch,
)
from thericher_v2.research.validation import resolve_model_artifact_root


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("freeze", "cpu-smoke", "cuda-batch"), required=True)
    parser.add_argument("--artifact-root", type=Path, default=resolve_model_artifact_root())
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default=NORGATE_BROAD_REPRESENTATION_ID)
    parser.add_argument("--code-revision", default="unrecorded")
    args = parser.parse_args(argv)

    dataset = load_frozen_observed_return_dataset(
        market_data_root=args.market_data_root,
        repo_root=args.repo_root,
    )
    contract = freeze_representation_campaign(
        dataset,
        artifact_root=args.artifact_root,
        repo_root=args.repo_root,
        run_id=args.run_id,
        code_revision=args.code_revision,
    )
    payload: dict[str, object] = {
        "mode": args.mode,
        "campaign_contract_sha256": contract.contract_sha256,
        "contract_path": str(contract.contract_path),
        "registry_record_sha256": contract.registry_entry.record_sha256,
        "development_window_count": int(contract.dataset.development_windows.shape[0]),
        "diagnostic_window_count": int(contract.dataset.diagnostic_windows.shape[0]),
    }
    if args.mode == "freeze":
        print(json.dumps(payload, sort_keys=True))
        return
    if args.mode == "cpu-smoke":
        result = run_representation_cpu_smoke(contract)
        payload["cpu_smoke"] = _run_payload(result)
        print(json.dumps(payload, sort_keys=True))
        return

    result = run_representation_cuda_batch(contract)
    payload["cuda_batch"] = {
        "batch_summary_path": str(result.batch_summary_path),
        "batch_summary_sha256": result.batch_summary_sha256,
        "registry_outcome_sha256": result.registry_outcome.record_sha256,
        "architectures": [_run_payload(item) for item in result.results],
        "selection": "disabled",
    }
    print(json.dumps(payload, sort_keys=True))


def _run_payload(result: object) -> dict[str, object]:
    return {
        "architecture_id": result.architecture_id,
        "summary_path": str(result.summary_path),
        "summary_sha256": result.summary_sha256,
        "weights_path": str(result.weights_path),
        "weights_sha256": result.weights_sha256,
        "device": result.device,
    }


if __name__ == "__main__":
    main()
