"""Run the bounded profiled-MTF target-free runtime smoke in the research image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from thericher_v2.research import profiled_mtf_flat_mlp_runtime_smoke as runtime_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path("/app/market_data/us_equities/kis_paper_private/intraday"),
    )
    parser.add_argument("--artifact-root", type=Path, default=Path("/app/model_artifacts"))
    parser.add_argument("--repo-root", type=Path, default=Path("/app"))
    parser.add_argument("--attempt-id", default="local-cache-r1")
    parser.add_argument("--phase", choices=("cpu", "cuda", "both"), default="both")
    parser.add_argument("--code-revision-sha256")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    code_revision_sha256 = args.code_revision_sha256 or _module_sha256()
    inventory = runtime_smoke.inspect_profiled_mtf_flat_mlp_runtime_inventory(
        cache_root=args.cache_root,
        repo_root=args.repo_root,
        code_revision_sha256=code_revision_sha256,
    )
    inventory_path = runtime_smoke.write_profiled_mtf_flat_mlp_runtime_inventory(
        inventory,
        artifact_root=args.artifact_root,
        repo_root=args.repo_root,
        attempt_id=args.attempt_id,
    )
    payload: dict[str, object] = {
        "inventory": inventory.safe_payload(),
        "inventory_path": str(inventory_path),
    }
    if inventory.status != "runtime_input_ready":
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return

    contract = runtime_smoke.freeze_profiled_mtf_flat_mlp_runtime_smoke(
        inventory,
        artifact_root=args.artifact_root,
        repo_root=args.repo_root,
        code_revision_sha256=code_revision_sha256,
        attempt_id=args.attempt_id,
    )
    payload["campaign_contract_sha256"] = contract.contract_sha256
    if args.phase in {"cpu", "both"}:
        payload["cpu"] = runtime_smoke.run_profiled_mtf_flat_mlp_runtime_cpu(
            contract
        ).safe_payload()
    if args.phase in {"cuda", "both"}:
        payload["cuda"] = runtime_smoke.run_profiled_mtf_flat_mlp_runtime_cuda(
            contract
        ).safe_payload()
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _module_sha256() -> str:
    source = Path(runtime_smoke.__file__).read_bytes()
    return "sha256:" + hashlib.sha256(source).hexdigest()


if __name__ == "__main__":
    main()
