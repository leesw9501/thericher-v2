from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_host_runner_is_a_closed_market_noop_without_cache_or_credential_access() -> None:
    script = Path("scripts/run_kis_mtf_profiled_forward_outcome_witness.py")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--observed-at",
            "2026-08-01T16:00:00Z",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "kind": "kis-mtf-profiled-forward-outcome-witness-v1",
        "status": "outside_outcome_window",
        "target_ready_pair_count": 0,
    }
    source = script.read_text(encoding="utf-8").lower()
    for forbidden in ("os.environ", "kis_live", "requests", "socket", ".env"):
        assert forbidden not in source
