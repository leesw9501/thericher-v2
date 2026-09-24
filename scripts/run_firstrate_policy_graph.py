"""Run the fixed combined-policy study through the existing CPU supervisor."""

from __future__ import annotations

import os
import runpy

from thericher_v2.research import firstrate_policy_graph as study


def main(argv=None):
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        os.environ[name] = "1"
    runner = runpy.run_path(str(study.REPO / "scripts/run_tiingo_month_start_development.py"))
    namespace = runner["main"].__globals__
    namespace["study"] = study
    namespace["worker"] = study.worker_entry
    return runner["main"](argv)


if __name__ == "__main__":
    raise SystemExit(main())
