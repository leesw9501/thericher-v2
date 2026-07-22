"""Run the exact Paper-host-pinned AMS/SPY best-price shape probe."""

from __future__ import annotations

import json
import os

from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    UrllibKisPaperCanaryTransport,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)


def main() -> int:
    try:
        config = load_kis_paper_config_from_environment(os.environ)
        probe = KisPaperCanaryClient(
            config=config,
            transport=UrllibKisPaperCanaryTransport(),
        ).probe_spy_asking_price()
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError):
        print(json.dumps({"status": "unavailable", "paper_only": True}, sort_keys=True))
        return 2
    print(json.dumps({"status": "complete", **probe.safe_payload()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
