"""Freeze or supervise the single CPU-only opening-range DEVELOPMENT contract.

Reuse the existing position-study supervisor/CLI protocol without changing its
source, timeout handling, immutable receipts, or external campaign registry.
"""

from __future__ import annotations

import runpy

from thericher_v2.research import firstrate_opening_range as study


def main(argv=None):
    runner = runpy.run_path(str(study.REPO / "scripts/run_firstrate_position_policy.py"))
    runner["main"].__globals__["study"] = study
    return runner["main"](argv)


if __name__ == "__main__":
    raise SystemExit(main())
