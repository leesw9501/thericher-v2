"""Bounded native subprocess backend for the protected observer lease."""

import hashlib
import json
import os
import subprocess
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _hash
from thericher_v2.ops.h3_dec4_observer_lease import ObserverSnapshot
from thericher_v2.ops.h3_dec4_observer_plan import Dec4ObserverPlan
from thericher_v2.ops.h3_dec4_scheduler_provider import (
    _file_stamp,
    _open_locked,
    _path_stamp,
    _unique_object,
    _windows_root,
)


@dataclass(frozen=True, slots=True)
class Dec4NativeObserverTransport:
    plan: Dec4ObserverPlan
    pwsh: Path
    pwsh_sha256: str

    def sample(self, *, enabled: bool):
        if type(enabled) is not bool:
            raise ValueError("h3_observer_transport_scope")
        return self._call("SampleEnabled" if enabled else "SampleDisabled")

    def switch(self, before, *, enabled, attempt, attempt_sha256):
        if (
            type(enabled) is not bool
            or type(before) is not ObserverSnapshot
            or before.enabled is enabled
        ):
            raise ValueError("h3_observer_transport_scope")
        name = "RESTORE_STARTED.json" if enabled else "STARTED.json"
        if attempt != Path(self.plan.output_root) / name or not _hash(attempt_sha256):
            raise ValueError("h3_observer_transport_scope")
        return self._call("Restore" if enabled else "Disable", attempt_sha256)

    def _call(self, mode, attempt=None):
        try:
            return self._read(mode, attempt)
        except Exception:
            # Never include child stderr, full task XML or native exceptions.
            raise ValueError("h3_observer_lease_transport_unavailable") from None

    def _read(self, mode, attempt):
        if type(self.plan) is not Dec4ObserverPlan or self.pwsh.name.lower() != "pwsh.exe":
            raise ValueError
        root = _windows_root()
        base = Path(self.plan.helper_root)
        bridge = base / "observer_bridge.ps1"
        manifest = base / "OBSERVER-PLAN.json"
        core = base / "paper_h3_observer_native.psm1"
        protected = {
            self.pwsh: self.pwsh_sha256,
            bridge: self.plan.bridge_sha256,
            core: self.plan.core_sha256,
            manifest: self.plan.sha256,
        }
        argv = [
            str(self.pwsh),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(bridge),
            "-Mode",
            mode,
            "-PlanSha256",
            self.plan.sha256,
        ]
        if attempt is not None:
            argv += ["-AttemptSha256", attempt]
        with ExitStack() as stack:
            stamps = {}
            for path, pin in protected.items():
                stamp = _path_stamp(path)
                source = stack.enter_context(_open_locked(path))
                if (
                    not _hash(pin)
                    or _file_stamp(os.fstat(source.fileno())) != stamp
                    or hashlib.file_digest(source, "sha256").hexdigest() != pin
                    or _path_stamp(path) != stamp
                ):
                    raise ValueError
                stamps[path] = stamp
            completed = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=root / "System32",
                env={
                    "SystemRoot": str(root),
                    "TEMP": str(root / "Temp"),
                    "TMP": str(root / "Temp"),
                },
                timeout=5,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if (
                completed.returncode != 0
                or not 0 < len(completed.stdout) <= 1024
                or any(_path_stamp(path) != stamp for path, stamp in stamps.items())
            ):
                raise ValueError
            return ObserverSnapshot(
                **json.loads(completed.stdout, object_pairs_hook=_unique_object)
            )
