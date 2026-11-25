import os
import subprocess
import sys
from pathlib import Path

import pytest

from thericher_v2.ops import h3_dec4_root_watchdog as watchdog

_ROOT = Path(watchdog.__file__).parents[2]
_PROBE = """
import os
import sys
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from thericher_v2.execution.paper_peer_visit import process_start
from thericher_v2.ops.h3_dec4_root_watchdog import arm_root_watchdog

pid = os.getpid()
ticks = process_start(pid).removeprefix('win-filetime:')
mode = sys.argv[2]
try:
    watcher = arm_root_watchdog(
        executable=Path(sys.executable).resolve(strict=True),
        pid=pid,
        start_ticks=str(int(ticks) + 1) if mode == 'wrong' else ticks,
        hard_cutoff=datetime.now(UTC) + timedelta(seconds=3),
    )
except ValueError:
    sys.exit(42 if mode == 'wrong' else 99)
if mode == 'wrong':
    sys.exit(90)
if mode == 'normal':
    assert watcher.check() is True
    actor = watcher.actor
    assert actor.pid == watcher.process.pid and actor.pid != pid
    assert process_start(actor.pid) == 'win-filetime:' + actor.start_ticks
    assert re.fullmatch(r'[0-9a-f]{64}', actor.argv_sha256)
    sys.exit(17)
if mode == 'dead_watchdog':
    watcher.process.terminate()
    watcher.process.wait(timeout=2)
    try:
        watcher.check()
    except ValueError:
        sys.exit(19)
    sys.exit(91)
watcher.process.wait(timeout=8)
sys.exit(92)
"""


@pytest.mark.skipif(os.name != "nt", reason="native Windows handle list required")
@pytest.mark.parametrize(
    "mode,code", [("normal", 17), ("cutoff", 20), ("wrong", 42), ("dead_watchdog", 19)]
)
def test_native_watchdog_only_targets_its_invented_root(mode, code):
    executable = Path(sys._base_executable).resolve(strict=True).with_name("pythonw.exe")
    assert executable.is_file()
    result = subprocess.run(
        [str(executable), "-I", "-S", "-B", "-c", _PROBE, str(_ROOT), mode],
        env={k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=15,
        check=False,
    )
    assert result.returncode == code
