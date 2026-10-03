"""Reuse the existing single-attempt CPU position-study supervisor protocol."""

from __future__ import annotations

import runpy

from thericher_v2.research import firstrate_time_of_day_band as study


def main(argv=None):
    runner = runpy.run_path(str(study.REPO / "scripts/run_firstrate_position_policy.py"))
    runner["main"].__globals__["study"] = study
    return runner["main"](argv)


if __name__ == "__main__":
    raise SystemExit(main())
