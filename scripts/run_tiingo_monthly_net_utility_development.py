"""One bounded GPU campaign; main owns offline2CPU/6GiB confinement and image."""

import os
import runpy

from thericher_v2.research import tiingo_monthly_net_utility_development as study
from thericher_v2.research.engine_research_agent import GpuFileLock, resolve_agent_root


def main(argv=None):
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "2"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    runner = runpy.run_path(str(study.REPO / "scripts/run_tiingo_month_start_development.py"))
    namespace = runner["main"].__globals__
    namespace["study"], namespace["worker"] = study, study.worker_entry
    dispatch = namespace["dispatch"]

    def locked_dispatch(artifact_root, market_data_root, pin):
        with GpuFileLock(resolve_agent_root(artifact_root) / "locks/gpu.lock"):
            return dispatch(artifact_root, market_data_root, pin)

    namespace["dispatch"] = locked_dispatch
    return runner["main"](argv)


if __name__ == "__main__":
    raise SystemExit(main())
