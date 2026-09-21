"""Run the fixed, hash-reviewed TRAIN-only H30 appendix, never a training job."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import tempfile
from pathlib import Path

from thericher_v2.research import firstrate_h30_train_diagnostic as diagnostic


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--diagnostic-contract-sha256")
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    if args.describe == bool(args.diagnostic_contract_sha256):
        parser.error("use --describe OR a reviewed --diagnostic-contract-sha256")
    h30 = diagnostic.h30
    scope = diagnostic.contract()
    scope_hash = h30.digest(h30.encode(scope))
    if args.describe:
        print(json.dumps({"contract": scope, "sha256": scope_hash}, sort_keys=True))
        return 0
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    try:
        diagnostic.require(scope_hash == args.diagnostic_contract_sha256, "contract_changed")
        output, *_ = diagnostic.bindings(args.artifact_root)
        appendix = output / diagnostic.NAME
        appendix.mkdir(exist_ok=False)
        supervise = runpy.run_path(
            str(h30.REPO / "scripts" / "run_firstrate_m5_h30_lstm_dev_20260921.py")
        )["supervise"]
        with tempfile.TemporaryDirectory(prefix="job-", dir=appendix) as temporary:
            path = Path(temporary) / "result.json"
            job = supervise(
                diagnostic.worker,
                (args.artifact_root, args.market_data_root, scope_hash, path),
                seconds=diagnostic.SECONDS,
                name=f"h30-{diagnostic.NAME}",
            )
            result = diagnostic.failure(scope_hash, "worker_failed_or_timed_out")
            if not job["timed_out"] and job["exit_code"] == 0 and path.is_file():
                candidate = json.loads(path.read_bytes())
                keys = [tuple(f[k] for k in diagnostic.IDENTITY) for f in candidate.get("fits", [])]
                valid = (
                    candidate.get("status") == "complete" and keys == diagnostic.fit_keys()
                ) or (candidate.get("status") == "failed_all16" and not keys)
                if candidate.get("diagnostic_contract_sha256") == scope_hash and valid:
                    result = candidate
            result["job"] = job
            with (appendix / "summary.json").open("xb") as handle:
                handle.write(h30.encode(result))
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "fit_count": len(result["fits"]),
                    "diagnostic_contract_sha256": scope_hash,
                },
                sort_keys=True,
            )
        )
        return 0 if result["status"] == "complete" else 1
    except Exception:
        print(json.dumps({"status": "dispatch_unavailable", "raw_error_suppressed": True}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
