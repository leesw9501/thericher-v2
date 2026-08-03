from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_host_runner_is_outside_slot_noop_without_cache_or_credential_access() -> None:
    script = Path("scripts/run_profiled_mtf_forward_capture_cycle.py")

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
        "action": "outside_cycle_slot",
        "kind": "profiled-mtf-forward-capture-cycle-v1",
        "status": "outside_cycle_slot",
    }
    source = script.read_text(encoding="utf-8").lower()
    for forbidden in ("os.environ", "kis_live", "requests", "socket", ".env", "torch"):
        assert forbidden not in source
