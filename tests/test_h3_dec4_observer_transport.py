import hashlib
import json
import os
import subprocess
from dataclasses import asdict

import pytest

from test_h3_dec4_observer_lease import _OFF, _ORIGINAL
from thericher_v2.ops import h3_dec4_observer_transport as native
from thericher_v2.ops.h3_dec4_observer_plan import Dec4ObserverPlan


@pytest.fixture
def backend(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows absolute source binder")
    root = tmp_path.resolve(strict=True)
    base = root / "observer-entry"
    base.mkdir()
    pwsh = root / "pwsh.exe"
    bridge = base / "observer_bridge.ps1"
    core = base / "paper_h3_observer_native.psm1"
    for path in (pwsh, bridge, core):
        path.write_bytes(path.name.encode("ascii"))

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    plan = Dec4ObserverPlan("entry", str(root), sha(bridge), sha(core))
    manifest = base / "OBSERVER-PLAN.json"
    manifest.write_bytes(plan.manifest_bytes)
    monkeypatch.setattr(native, "_windows_root", lambda: root)
    return native.Dec4NativeObserverTransport(plan, pwsh, sha(pwsh)), manifest


def test_exact_read_returns_typed_sample_with_no_write_argument(backend, monkeypatch):
    observer, _ = backend

    def call(argv, **kwargs):
        assert argv[-4:] == ["-Mode", "SampleEnabled", "-PlanSha256", observer.plan.sha256]
        assert kwargs["timeout"] == 5 and kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(asdict(_ORIGINAL)).encode())

    monkeypatch.setattr(native.subprocess, "run", call)
    assert observer.sample(enabled=True) == _ORIGINAL


def test_switch_routes_only_exact_attempt_and_native_failure_is_categorical(backend, monkeypatch):
    observer, _ = backend

    def call(argv, **kwargs):
        del kwargs
        assert argv[-6:] == [
            "-Mode",
            "Disable",
            "-PlanSha256",
            observer.plan.sha256,
            "-AttemptSha256",
            "e" * 64,
        ]
        return subprocess.CompletedProcess(argv, 1, stdout=b"invented private fault")

    monkeypatch.setattr(native.subprocess, "run", call)
    expected = observer.pwsh.parent / "observer-entry" / "owned-output" / "STARTED.json"
    with pytest.raises(ValueError, match="^h3_observer_transport_scope$"):
        observer.switch(
            _ORIGINAL,
            enabled=False,
            attempt=expected.parent / "OTHER.json",
            attempt_sha256="e" * 64,
        )
    with pytest.raises(ValueError, match="^h3_observer_lease_transport_unavailable$"):
        observer.switch(_ORIGINAL, enabled=False, attempt=expected, attempt_sha256="e" * 64)


def test_source_drift_refuses_before_starting_native_child(backend, monkeypatch):
    observer, manifest = backend
    manifest.write_bytes(b"changed")
    monkeypatch.setattr(native.subprocess, "run", lambda *a, **k: pytest.fail("unverified launch"))
    with pytest.raises(ValueError, match="^h3_observer_lease_transport_unavailable$"):
        observer.sample(enabled=False)


def test_duplicate_native_json_field_is_refused(backend, monkeypatch):
    observer, _ = backend
    sample = json.dumps(asdict(_OFF)).removesuffix("}") + ',"enabled":false}'
    monkeypatch.setattr(
        native.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=sample.encode()),
    )
    with pytest.raises(ValueError, match="^h3_observer_lease_transport_unavailable$"):
        observer.sample(enabled=False)
