import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
_PARENT = """
import hashlib, os, sys, time
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[4]]
from thericher_v2.ops.h3_dec4_restore_process import Dec4RestoreProcess, _birth, _kernel
exe, script = Path(sys.executable).resolve(), Path(sys.argv[2])
pin = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
scope = Dec4RestoreProcess(exe, pin(exe), script, pin(script))
k = _kernel()
lease = scope.arm(
    pid=os.getpid(), start_ticks=_birth(k,k.GetCurrentProcess()), cutoff=time.time()+8,
    phase="entry", source="1"*64, release="2"*64, handoff="3"*64,
)
assert lease.check() and len(lease.actor.argv_sha256)==64
sys.exit(int(sys.argv[3]))
"""
_CHILD = """
import sys
from pathlib import Path
sys.path.insert(0, SOURCE_PATH)
from thericher_v2.ops.h3_dec4_restore_process import wait_for_dec4_normal_root
phase, source, release, handoff, root, arm, pid, ticks, utc, mono = sys.argv[1:]
assert (phase,source,release,handoff)==("entry","1"*64,"2"*64,"3"*64)
try:
    wait_for_dec4_normal_root(
        root=int(root),arm=int(arm),pid=int(pid),birth=ticks,
        cutoff=float(utc),monotonic_cutoff=float(mono),
    )
except ValueError:
    result="refused"
else:
    result="normal"
pending=Path("result.pending")
pending.write_text(result,encoding="ascii")
pending.rename("result")
"""


@pytest.mark.skipif(os.name != "nt", reason="requires the Windows inherited handle ABI")
@pytest.mark.parametrize("exit_code, result", [(0, "normal"), (20, "refused")])
def test_restricted_child_arms_then_distinguishes_exact_root_exit(tmp_path, exit_code, result):
    script = tmp_path / "inert.py"
    script.write_text(_CHILD.replace("SOURCE_PATH", repr(str(_SRC))), encoding="ascii")
    exe = str(Path(sys._base_executable).resolve())
    proc = subprocess.run(
        [
            exe,
            "-I",
            "-S",
            "-B",
            "-c",
            _PARENT,
            str(_SRC),
            str(script),
            str(exit_code),
            str(Path(sys.prefix) / "Lib" / "site-packages"),
        ],
        cwd=tmp_path,
        timeout=12,
        check=False,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert proc.returncode == exit_code, proc.stderr.decode(errors="replace")
    receipt = tmp_path / "result"
    end = time.monotonic() + 9
    while not receipt.is_file() and time.monotonic() < end:
        time.sleep(0.02)
    assert receipt.read_text(encoding="ascii") == result
