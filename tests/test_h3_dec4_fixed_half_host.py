import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.ops import h3_dec4_fixed_half_host as host


@pytest.mark.skipif(os.name != "nt", reason="native Windows Job")
@pytest.mark.parametrize("fault", ["none", "exit", "birth", "command"])
def test_native_job_digest_join(tmp_path, monkeypatch, fault):
    control = tmp_path.resolve()
    start = datetime.now(UTC) - timedelta(seconds=2)
    monkeypatch.setattr(host, "OPENS", start)
    monkeypatch.setattr(host, "LAST_START", start + timedelta(seconds=15))
    monkeypatch.setattr(host, "HARD_STOP", start + timedelta(seconds=20))
    monkeypatch.setattr(host, "WATCHDOG", Path(host.__file__).with_name("h3_dec4_watchdog.py"))
    seal = "a" * 64
    child = control / "child.py"
    child.write_text(
        f"""
import runpy
import sys
from datetime import datetime
from pathlib import Path

module = runpy.run_path({host.__file__!r})
child = module['run_fixed_half_job_child']
child.__globals__.update(
    OPENS=datetime.fromisoformat({start.isoformat()!r}),
    LAST_START=datetime.fromisoformat({host.LAST_START.isoformat()!r}),
    HARD_STOP=datetime.fromisoformat({host.HARD_STOP.isoformat()!r}),
    _released_owner=lambda: lambda *args, **kwargs: {seal!r},
)
control = Path({str(control)!r})
fault = {fault!r}
if fault == 'command':
    sys.orig_argv[0] += '-changed'
child(control=control, launch_sha256=sys.argv[-1], host_ready=lambda: True)
if fault == 'birth':
    path = control / module['RETURN']
    returned = module['json'].loads(path.read_bytes())
    returned['native_start'] = 'win-filetime:1'
    path.write_bytes(module['_json'](returned))
sys.exit(2 if fault == 'exit' else 0)
""",
        encoding="ascii",
    )
    argv = (str(Path(sys._base_executable)), "-I", "-S", "-B", str(child))

    def run():
        return host.supervise_fixed_half_job(
            argv=argv, cwd=control, control=control, host_ready=lambda: True
        )

    receipt = control / host.COMPLETE
    if fault == "none":
        assert run() == host._sha(receipt.read_bytes())
        doc = json.loads(receipt.read_bytes())
        assert doc["seal_sha256"] == seal
        assert doc["source_sha256"] == host.SOURCE_PIN
        assert doc["disposition"] == "EXITED" and doc["exit_code"] == 0
        assert doc["child_return_sha256"] == host._sha((control / host.RETURN).read_bytes())
    else:
        with pytest.raises(ValueError, match="dec4_fixed_half_host_binding"):
            run()
        assert not receipt.exists()
    with pytest.raises(FileExistsError):
        run()
