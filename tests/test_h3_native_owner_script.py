"""The standalone Windows reader must reject bad pins before connecting."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parents[1] / "scripts" / "read_h3_native_owner.ps1"
TASK = r"\fixture-owner"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _ps(value):
    return "'" + str(value).replace("'", "''") + "'"


@pytest.mark.parametrize("fault", ["digest", "task", "shape", "module"])
def test_bad_pin_cannot_touch_scheduler(tmp_path, fault):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required for the native reader")
    profile = {
        "schema": "PAPER_NATIVE_OWNER_PROFILE_V1",
        "task_path": TASK,
        "action_sha256": "a" * 64,
        "export_xml": "<invented />",
        "definition_xml": "<invented />",
        "acl7": "invented",
        "readback_module_sha256": "b" * 64,
        "registration_module_sha256": "c" * 64,
    }
    if fault == "task":
        profile["task_path"] = r"\other-task"
    if fault == "shape":
        profile["foreign"] = "must_not_be_parsed_as_authority"
    raw = json.dumps(profile).encode()
    pin = "0" * 64 if fault == "digest" else _sha(raw)
    file = tmp_path / "profile.json"
    file.write_bytes(raw)
    wrapper = tmp_path / "probe-fixture.ps1"
    wrapper.write_text(
        "$PSModuleAutoLoadingPreference = 'None'\n"
        "function New-Object { param($ComObject)\n"
        "    Write-Output 'UNEXPECTED_SCHEDULER'; throw 'mock' }\n"
        f"& {_ps(PROBE)} -TaskPath {_ps(TASK)} -ExpectedEnginePid 17 "
        f"-ExpectedProfileSha256 {pin} -ProfilePath {_ps(file)}\n"
        "exit $LASTEXITCODE\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(wrapper)],
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert out.returncode == 20
    assert out.stdout == out.stderr == b""
