"""Inert-by-default host for one separately owned current20 native Paper wake.

Offline preparation alone may decode the frozen allocation archive. Scheduled
execution receives only pinned native JSON and an exact Parent release binding.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import math
import queue
import re
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = Path("D:/thericher-v2/model-artifacts")
RUNTIME_RELATIVE = "execution/current20-ensemble-paper-runtime-20261018-v1"
TASK = "thericher-kis-paper-current20-equalrank4-20261018"
LABEL = "thericher.execution.current20-ensemble.uuid"
PREFIX = "thericher-current20-ensemble-"
HOST = "scripts/run_current20_paper_candidate.py"
WORKER = "scripts/run_current20_paper_candidate_worker.py"
HELPERS = (
    "scripts/run_kis_paper_current_stock_cycle.py",
    "scripts/run_kis_paper_current_stock_cycle_worker.py",
    "scripts/run_kis_paper_current_daily_session.py",
    "scripts/run_kis_paper_etf_daily_context.py",
)
DATA_BINDING_SHA256 = "2290e74be071e6644664f1c106728382fc0d5d389b42d4a59257058f99bafd0f"
PYTHONW = Path(
    "C:/Users/User/AppData/Roaming/uv/python/cpython-3.14.3-windows-x86_64-none/pythonw.exe"
)
PS = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
KIND = "current20-paper-worker-v1"
TRUSTED_SITE = Path("C:/Users/Public/Documents/thericher-v2/.venv/Lib/site-packages")
TZDATA_PINS = {
    "tzdata/__init__.py": ("e2bfe056345bcf835f032f930539fb7f113b4d6e94c16e596ed30f09ee48e09a"),
    "tzdata/zoneinfo/__init__.py": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "tzdata/zoneinfo/America/__init__.py": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "tzdata/zoneinfo/America/New_York": (
        "d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9"
    ),
    "tzdata-2026.3.dist-info/METADATA": (
        "511c019df477939fe7f4c38e32ad74a570c4ebb05b13fd2fffd0f0f2dbe6f7b1"
    ),
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _legacy():
    module = _load("current20_native_host_helpers", ROOT / HELPERS[0])
    module.LABEL = LABEL
    module._docker = _docker
    return module


def bootstrap():
    """No site/.pth execution: append only the byte-pinned Windows dependency."""
    sys.path.insert(0, str(ROOT / "src"))
    if sys.platform == "win32":
        for name, pin in TZDATA_PINS.items():
            _read(TRUSTED_SITE / name, "sha256:" + pin)
        if str(TRUSTED_SITE) not in sys.path:
            sys.path.append(str(TRUSTED_SITE))
        import tzdata

        if (
            tzdata.__version__ != "2026.3"
            or tzdata.IANA_VERSION != "2026c"
            or _plain(tzdata.__file__) != _plain(TRUSTED_SITE / "tzdata/__init__.py")
        ):
            raise ValueError("trusted_timezone_dependency_required")


def _native():
    bootstrap()
    from thericher_v2.research import current20_paper_candidate

    return current20_paper_candidate


def _sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate_json_field")
        result[key] = value
    return result


def _json(raw):
    return json.loads(
        raw,
        object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_number")),
    )


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _plain(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() and (
            part.is_symlink() or getattr(part.lstat(), "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("input_reparse_path_refused")
    return path.resolve()


def _read(path, pin, limit=65536):
    if type(pin) is not str or PIN.fullmatch(pin) is None:
        raise ValueError("exact_input_pin_required")
    with _plain(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or _sha(raw) != pin:
        raise ValueError("input_pin_mismatch")
    return raw


def _artifact_relative(path):
    relative = _plain(path).relative_to(_plain(ARTIFACT)).as_posix()
    if ".." in Path(relative).parts:
        raise ValueError("artifact_scope_invalid")
    return relative


def _new(path, raw):
    path = _plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        import os

        os.fsync(stream.fileno())


def source_map():
    files = list((ROOT / "src").rglob("*.py")) + [ROOT / name for name in (HOST, WORKER, *HELPERS)]
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
    }


def read_source_manifest(path, pin):
    value = _json(_read(path, pin, 1024 * 1024))
    if type(value) is not dict or set(value) != {"files"} or value["files"] != source_map():
        raise ValueError("host_source_manifest_mismatch")
    return value["files"]


def prepare_input(
    *,
    parent_contract,
    parent_contract_ref,
    data_binding,
    data_binding_ref,
    bundle,
    weights,
    clock=lambda: datetime.now(UTC),
):
    """Create exactly one new native JSON input; never credentials or inference."""
    if data_binding_ref != "sha256:" + DATA_BINDING_SHA256:
        raise ValueError("exact_Data_binding_required")
    api = _native()
    contract = _read(parent_contract, parent_contract_ref)
    data = _read(data_binding, data_binding_ref, 131072)
    bundle_raw = _read(bundle, "sha256:" + api.BUNDLE_SHA256)
    weights_raw = _read(weights, "sha256:" + api.WEIGHTS_SHA256, 16384)
    now = clock()
    if type(now) is not datetime or now.utcoffset() is None or now.utcoffset().total_seconds():
        raise ValueError("actual_UTC_decision_clock_required")
    value = api.prepare_current20_paper_candidate(
        contract_bytes=contract,
        expected_contract_sha256=parent_contract_ref[7:],
        bundle_bytes=bundle_raw,
        weights_bytes=weights_raw,
        calendar=api.current20_paper_calendar_from_binding(
            data, expected_sha256=data_binding_ref[7:]
        ),
        decided_at=now,
    )
    payload = api.serialize_current20_paper_input(value)
    loaded = api.load_current20_paper_input(payload, expected_sha256=_sha(payload)[7:])
    if (loaded.input_ref, loaded.policy_ref) != (value.input_ref, parent_contract_ref):
        raise ValueError("native_semantic_reference_mismatch")
    if any(t.proposal.valid_until != value.entry_session.close_ts for t in value.targets):
        raise ValueError("original_Oct19_close_expiry_required")
    folder = _plain(ARTIFACT / RUNTIME_RELATIVE / "prepared-input")
    folder.mkdir(parents=True, exist_ok=False)
    _new(folder / "proposal.json", payload)
    manifest = dict(
        kind="current20-paper-native-input-v1",
        candidate_id=api.CANDIDATE_ID,
        profile=value.profile.value,
        payload_name="proposal.json",
        payload_ref=_sha(payload),
        input_ref=value.input_ref,
        policy_ref=value.policy_ref,
        contract=dict(path=_artifact_relative(parent_contract), ref=parent_contract_ref),
        data_binding=dict(path=_artifact_relative(data_binding), ref=data_binding_ref),
        bundle_ref="sha256:" + api.BUNDLE_SHA256,
        weights_ref="sha256:" + api.WEIGHTS_SHA256,
        decided_at=now.isoformat(),
        signal_valid_until=value.entry_session.close_ts.isoformat(),
        target_count=5,
        model_calls=0,
    )
    encoded = _encode(manifest)
    _new(folder / "manifest.json", encoded)
    return dict(
        status="input_prepared",
        input_manifest=str(folder / "manifest.json"),
        input_manifest_ref=_sha(encoded),
        input_ref=value.input_ref,
        policy_ref=value.policy_ref,
        payload_ref=_sha(payload),
        target_count=5,
        credential_reads=0,
        broker_calls=0,
        model_calls=0,
    )


def read_input_manifest(path, pin):
    path = _plain(path)
    if not path.is_relative_to(_plain(ARTIFACT / RUNTIME_RELATIVE)):
        raise ValueError("new_candidate_input_namespace_required")
    doc = _json(_read(path, pin))
    expected = {
        "kind",
        "candidate_id",
        "profile",
        "payload_name",
        "payload_ref",
        "input_ref",
        "policy_ref",
        "contract",
        "data_binding",
        "bundle_ref",
        "weights_ref",
        "decided_at",
        "signal_valid_until",
        "target_count",
        "model_calls",
    }
    if (
        type(doc) is not dict
        or set(doc) != expected
        or doc["kind"] != "current20-paper-native-input-v1"
        or doc["payload_name"] != "proposal.json"
        or doc["target_count"] != 5
        or doc["model_calls"] != 0
    ):
        raise ValueError("native_input_manifest_invalid")
    payload = _read(path.parent / "proposal.json", doc["payload_ref"])
    for name in ("contract", "data_binding"):
        item = doc[name]
        if (
            type(item) is not dict
            or set(item) != {"path", "ref"}
            or Path(item["path"]).is_absolute()
            or ".." in Path(item["path"]).parts
            or "\\" in item["path"]
            or ":" in item["path"]
        ):
            raise ValueError("native_input_artifact_scope_invalid")
        _read(ARTIFACT / item["path"], item["ref"], 131072)
    if doc["data_binding"]["ref"] != "sha256:" + DATA_BINDING_SHA256:
        raise ValueError("exact_Data_binding_required")
    api = _native()
    value = api.load_current20_paper_input(payload, expected_sha256=doc["payload_ref"][7:])
    if (
        value.input_ref != doc["input_ref"]
        or value.policy_ref != doc["policy_ref"]
        or value.policy_ref != doc["contract"]["ref"]
        or value.profile.value != doc["profile"]
        or api.CANDIDATE_ID != doc["candidate_id"]
        or "sha256:" + api.BUNDLE_SHA256 != doc["bundle_ref"]
        or "sha256:" + api.WEIGHTS_SHA256 != doc["weights_ref"]
        or value.targets[0].metadata.decided_at.isoformat() != doc["decided_at"]
        or any(
            t.proposal.valid_until.isoformat() != doc["signal_valid_until"] for t in value.targets
        )
    ):
        raise ValueError("native_semantic_reference_mismatch")
    return doc, value


def _docker(args, **kwargs):
    return subprocess.run(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)


def command(
    image,
    identity,
    *,
    execute=False,
    input_manifest=None,
    input_manifest_ref="",
    source_manifest=None,
    source_manifest_ref="",
):
    base = _legacy().command(image, identity, execute=execute)
    changes = {
        "thericher-current-stock-" + identity: PREFIX + identity,
        "/app/scripts/run_kis_paper_current_stock_cycle_worker.py": "/app/" + WORKER,
        "300": "150",
    }
    args = [changes.get(v, v) for v in base]
    if not execute:
        # Public inert image proof must not mount private/shared state at all.
        for index in reversed([i for i, item in enumerate(args) if item == "--mount"]):
            del args[index : index + 2]
        return args
    for flag, path, pin in (
        ("input-manifest", input_manifest, input_manifest_ref),
        ("source-manifest", source_manifest, source_manifest_ref),
    ):
        if PIN.fullmatch(pin) is None:
            raise ValueError("explicit_release_pins_required")
        args += [
            "--" + flag,
            "/app/model_artifacts/" + _artifact_relative(path),
            "--" + flag + "-ref",
            pin,
        ]
    return args + ["--owner-admission-stdio"]


def _identity():
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.GetCurrentProcess.restype = wintypes.HANDLE
    dll.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.c_void_p] * 4
    values = [ctypes.c_ulonglong() for _ in range(4)]
    if not dll.GetProcessTimes(dll.GetCurrentProcess(), *(ctypes.byref(v) for v in values)):
        raise ValueError("owner_creation_unavailable")
    dll.GetCommandLineW.restype = wintypes.LPWSTR
    dll.GetConsoleWindow.restype = wintypes.HWND
    image = ctypes.create_unicode_buffer(32768)
    if not dll.GetModuleFileNameW(None, image, len(image)):
        raise ValueError("owner_image_unavailable")
    return dict(
        pid=__import__("os").getpid(),
        creation_microseconds=values[0].value // 10,
        command_line_sha256=hashlib.sha256(dll.GetCommandLineW().encode()).hexdigest(),
        entry=str(ROOT / HOST),
        source_sha256=hashlib.sha256((ROOT / HOST).read_bytes()).hexdigest(),
        executable=str(Path(image.value).resolve()),
        console_window=int(dll.GetConsoleWindow() or 0),
    )


def owner_admission(
    *, probe, probe_ref, context, folder, environment, clock=lambda: datetime.now(UTC)
):
    _read(probe, probe_ref, 131072)
    raw = _encode(context)
    path = folder / ("owner-" + str(context["sequence"]) + ".json")
    _new(path, raw)
    result = _docker(
        [
            PS,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
            "-ContextPath",
            str(path),
            "-ContextRef",
            _sha(raw),
        ],
        stdin=subprocess.DEVNULL,
        env=environment,
        capture_output=True,
        timeout=12,
    )
    if result.returncode or len(result.stdout) > 4096:
        raise ValueError("owner_admission_unknown")
    fact = _json(result.stdout.decode("utf-8-sig"))
    keys = {"kind", "context_ref", "ready", "observed_at_utc", "snapshot_span_seconds"}
    if (
        type(fact) is not dict
        or set(fact) != keys
        or fact["kind"] != "current20-paper-owner-fact-v1"
        or fact["context_ref"] != _sha(raw)
        or type(fact["ready"]) is not bool
        or type(fact["snapshot_span_seconds"]) not in (int, float)
        or not math.isfinite(fact["snapshot_span_seconds"])
        or not 0 <= fact["snapshot_span_seconds"] <= 10
    ):
        raise ValueError("owner_admission_invalid")
    at = datetime.fromisoformat(fact["observed_at_utc"].replace("Z", "+00:00"))
    if (
        at.utcoffset() is None
        or at.utcoffset().total_seconds()
        or not 0 <= (clock() - at).total_seconds() <= 5
    ):
        raise ValueError("owner_admission_stale")
    return fact["ready"]


def validate_result(value):
    bootstrap()
    from thericher_v2.execution import kis_paper_current_stock_cycle as cycle

    if value == dict(
        kind=KIND,
        status="unavailable",
        reason="native_recovery_required",
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        request_counts="unknown",
    ):
        return value

    keys = {
        "kind",
        "status",
        "reason",
        "leg_count",
        "outcomes",
        "calls",
        "paper_only",
        "unknown_effects_not_assumed_zero",
        "http_start_gaps_seconds",
        "pacing_basis",
        "observed_at_utc",
        "fees",
        "settled_cash",
        "net_pnl",
    }
    if type(value) is not dict or set(value) != keys or value["kind"] != KIND:
        raise ValueError("worker_output_invalid")
    outcomes = value["outcomes"]
    if type(outcomes) is not list or not 1 <= len(outcomes) <= 6:
        raise ValueError("worker_output_invalid")
    for item in outcomes:
        if (
            type(item) is not dict
            or set(item) != {"status", "reason", "leg_count"}
            or item["status"] not in cycle._STATUSES
            or item["reason"] not in cycle._REASONS
            or type(item["leg_count"]) is not int
            or item["leg_count"] not in (0, 1)
        ):
            raise ValueError("worker_output_invalid")
    if (value["status"], value["reason"], value["leg_count"]) != (
        outcomes[-1]["status"],
        outcomes[-1]["reason"],
        sum(v["leg_count"] for v in outcomes),
    ):
        raise ValueError("worker_output_invalid")
    calls = value["calls"]
    if (
        type(calls) is not dict
        or set(calls) != {"token_posts", "get_requests", "buy_posts", "sell_posts", "cancel_posts"}
        or any(type(n) is not int or not 0 <= n <= 128 for n in calls.values())
        or sum(calls.values()) > 128
        or calls["token_posts"] > 1
        or calls["buy_posts"] + calls["sell_posts"] > 5
        or calls["cancel_posts"] > 5
    ):
        raise ValueError("worker_output_invalid")
    gaps = value["http_start_gaps_seconds"]
    if (
        type(gaps) is not list
        or len(gaps) != max(0, sum(calls.values()) - 1)
        or any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in gaps)
        or value["paper_only"] is not True
        or value["unknown_effects_not_assumed_zero"] is not True
        or any(value[k] != "not_observed" for k in ("fees", "settled_cash", "net_pnl"))
        or value["pacing_basis"] != "final_opener_delegate_boundary_not_socket_wire_measurement"
    ):
        raise ValueError("worker_output_invalid")
    at = datetime.fromisoformat(value["observed_at_utc"])
    if at.utcoffset() is None or at.utcoffset().total_seconds():
        raise ValueError("worker_output_invalid")
    return value


def _failure(reason="worker_recovery_required"):
    return dict(
        status="unavailable", reason=reason, paper_only=True, unknown_effects_not_assumed_zero=True
    )


def _exchange(args, packet, admission, *, environment, monotonic=time.monotonic, deadline=None):
    """One outstanding, bounded metadata request on existing process stdio."""
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines = queue.Queue(maxsize=2)
    stopped = threading.Event()

    def reader():
        while not stopped.is_set():
            line = process.stdout.readline(32769)
            while not stopped.is_set():
                try:
                    lines.put(line, timeout=0.1)
                    break
                except queue.Full:
                    continue
            if not line or len(line) > 32768:
                return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline, sequence = monotonic() + 145 if deadline is None else deadline, 0
    try:
        process.stdin.write(packet + b"\n")
        process.stdin.flush()
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ValueError("worker_wall_exhausted")
            try:
                line = lines.get(timeout=min(15, remaining))
            except queue.Empty:
                if process.poll() is not None and not thread.is_alive():
                    raise ValueError("worker_closed_without_result") from None
                continue
            if not line or len(line) > 32768 or not line.endswith(b"\n"):
                raise ValueError("worker_frame_invalid")
            value = _json(line)
            if value.get("kind") == "current20-owner-request-v1":
                if set(value) != {"kind", "sequence"} or type(value["sequence"]) is not int:
                    raise ValueError("worker_frame_invalid")
                sequence += 1
                if value["sequence"] != sequence or sequence > 128:
                    raise ValueError("worker_frame_invalid")
                ready = admission(sequence)
                response = dict(kind="current20-owner-answer-v1", sequence=sequence, ready=ready)
                process.stdin.write(_encode(response) + b"\n")
                process.stdin.flush()
                continue
            result = validate_result(value)
            process.stdin.close()
            code = process.wait(timeout=max(0.1, deadline - monotonic()))
            if code != (20 if result["status"] == "unavailable" else 0):
                raise ValueError("worker_exit_mismatch")
            return result
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()
        thread.join(timeout=1)


def execution_window(now):
    bootstrap()
    from thericher_v2.data.us_equity_session import us_equity_2026_session

    if (
        type(now) is not datetime
        or now.utcoffset() is None
        or now.utcoffset().total_seconds()
        or not datetime(2026, 10, 19, 15, 10, tzinfo=UTC)
        <= now
        < datetime(2026, 11, 20, 22, tzinfo=UTC)
    ):
        return False
    session = us_equity_2026_session(now.date())
    return session is not None and session.window.open_ts <= now < session.window.close_ts


def _container_identity(name, identity, image, environment):
    result = _docker(
        [
            "docker",
            "inspect",
            "--format",
            '{{.Id}}|{{.Image}}|{{index .Config.Labels "'
            + LABEL
            + '"}}|{{.Name}}|{{.State.Running}}',
            name,
        ],
        env=environment,
        capture_output=True,
        timeout=5,
    )
    if result.returncode or len(result.stdout) > 512:
        raise ValueError("exact_worker_identity_unavailable")
    pieces = result.stdout.decode("ascii").strip().split("|")
    if (
        len(pieces) != 5
        or re.fullmatch(r"[0-9a-f]{64}", pieces[0]) is None
        or pieces[1:] != [image, identity, "/" + name, "true"]
    ):
        raise ValueError("exact_worker_identity_unavailable")
    return pieces[0]


def run(
    *,
    execute=False,
    image="",
    source_manifest=None,
    source_manifest_ref="",
    input_manifest=None,
    input_manifest_ref="",
    owner_probe=None,
    owner_probe_ref="",
    clock=lambda: datetime.now(UTC),
    monotonic=time.monotonic,
):
    if not execute:
        return dict(status="inert", credential_reads=0, broker_calls=0)
    deadline = monotonic() + 145
    before = read_source_manifest(source_manifest, source_manifest_ref)
    read_input_manifest(input_manifest, input_manifest_ref)
    _read(owner_probe, owner_probe_ref, 131072)
    if not execution_window(clock()):
        return dict(
            status="hold", reason="outside_owned_regular_window", credential_reads=0, broker_calls=0
        )
    own = _identity()
    if Path(own["executable"]).resolve() != PYTHONW or own["console_window"] != 0:
        raise ValueError("physical_quiet_pythonw_required")
    identity = uuid4().hex
    native = _legacy()
    environment = native.os_environment()
    args = command(
        image,
        identity,
        execute=True,
        input_manifest=input_manifest,
        input_manifest_ref=input_manifest_ref,
        source_manifest=source_manifest,
        source_manifest_ref=source_manifest_ref,
    )
    folder = ARTIFACT / RUNTIME_RELATIVE / "runs" / identity
    folder.mkdir(parents=True, exist_ok=False)
    result, cleanup_failed, packet = _failure(), False, None
    try:
        context = dict(
            kind="current20-paper-owner-context-v1",
            task_name=TASK,
            identity=identity,
            host=own,
            image=image,
            label=LABEL,
            container_name=PREFIX + identity,
            source_manifest_ref=source_manifest_ref,
            input_manifest_ref=input_manifest_ref,
            arguments=subprocess.list2cmdline(
                launch_argv(
                    image=image,
                    source_manifest=source_manifest,
                    source_manifest_ref=source_manifest_ref,
                    input_manifest=input_manifest,
                    input_manifest_ref=input_manifest_ref,
                    owner_probe=owner_probe,
                    owner_probe_ref=owner_probe_ref,
                )[1:]
            ),
            working_directory=str(ROOT),
        )

        container_id = None

        def admission(sequence):
            nonlocal container_id
            if monotonic() + 12 >= deadline:
                return False
            if sequence and container_id is None:
                container_id = _container_identity(PREFIX + identity, identity, image, environment)
            return owner_admission(
                probe=owner_probe,
                probe_ref=owner_probe_ref,
                context=dict(context, sequence=sequence, container_id=container_id),
                folder=folder,
                environment=environment,
                clock=clock,
            )

        # Public source probe is network-none and has no private/data mounts.
        probe_name = PREFIX + "source-" + identity
        code = (
            "import json,hashlib;from pathlib import Path;files=" + repr(tuple(before)) + ";"
            "paths={p.relative_to('/app').as_posix() for p in Path('/app/src').rglob('*.py')};"
            "paths.update(n for n in files if not n.startswith('src/'));"
            "print(json.dumps({n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest()"
            " for n in paths}))"
        )
        try:
            probe = _docker(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    probe_name,
                    "--label",
                    LABEL + "=" + identity,
                    "--pull",
                    "never",
                    "--network",
                    "none",
                    "--read-only",
                    "--log-driver",
                    "none",
                    "--entrypoint",
                    "python",
                    image,
                    "-B",
                    "-c",
                    code,
                ],
                env=environment,
                capture_output=True,
                timeout=15,
            )
        finally:
            cleanup_failed = True
            cleanup_failed = not native.cleanup(probe_name, identity, environment)
        if cleanup_failed:
            raise ValueError("source_probe_cleanup_unresolved")
        if probe.returncode or len(probe.stdout) > 1024 * 1024 or _json(probe.stdout) != before:
            raise ValueError("worker_image_source_mismatch")
        if not admission(0):
            result = _failure("owner_admission_unavailable")
            return result
        for volume in native.VOLUMES:
            _docker(
                ["docker", "volume", "inspect", volume],
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        # Every source/input/probe/image/owner check above precedes this scoped loader.
        config = native.load_paper_config()
        packet = _encode(
            dict(
                KIS_PAPER_APP_KEY=config.app_key,
                KIS_PAPER_APP_SECRET=config.app_secret,
                KIS_PAPER_ACCOUNT_NO=config.account_number,
                KIS_PAPER_ACCOUNT_PRODUCT_CODE=config.account_product_code,
                THERICHER_MODE="kis_paper",
            )
        )
        try:
            result = _exchange(
                args, packet, admission, environment=environment,
                monotonic=monotonic, deadline=deadline,
            )
            if source_map() != before:
                raise ValueError("host_source_changed")
        finally:
            packet = None
            cleanup_failed = True
            cleanup_failed = not native.cleanup(PREFIX + identity, identity, environment)
    except Exception:
        result = _failure()
    except BaseException:
        result = _failure()
        raise
    finally:
        packet = None
        if cleanup_failed:
            result = _failure("worker_cleanup_unresolved")
        _new(folder / "result.json", _encode(result))
    return result


def launch_argv(
    *,
    image,
    source_manifest,
    source_manifest_ref,
    input_manifest,
    input_manifest_ref,
    owner_probe,
    owner_probe_ref,
):
    return [
        str(PYTHONW),
        "-I",
        "-B",
        str(ROOT / HOST),
        "--execute",
        "--image",
        image,
        "--source-manifest",
        str(source_manifest),
        "--source-manifest-ref",
        source_manifest_ref,
        "--input-manifest",
        str(input_manifest),
        "--input-manifest-ref",
        input_manifest_ref,
        "--owner-probe",
        str(owner_probe),
        "--owner-probe-ref",
        owner_probe_ref,
    ]


def validate_input(
    *, source_manifest, source_manifest_ref, input_manifest, input_manifest_ref, proof_path
):
    """Quiet physical-runtime proof only; never config, Docker, network or prepare."""
    read_source_manifest(source_manifest, source_manifest_ref)
    document, value = read_input_manifest(input_manifest, input_manifest_ref)
    own = _identity()
    if Path(own["executable"]).resolve() != PYTHONW or own["console_window"] != 0:
        raise ValueError("physical_quiet_pythonw_required")
    if not _plain(proof_path).is_relative_to(_plain(ARTIFACT / RUNTIME_RELATIVE)):
        raise ValueError("owned_proof_scope_required")
    result = dict(
        status="offline_input_validated_not_executed",
        input_ref=value.input_ref,
        payload_ref=document["payload_ref"],
        policy_ref=value.policy_ref,
        executable=own["executable"],
        executable_ref=_sha(PYTHONW.read_bytes()),
        console_window=0,
        timezone="America/New_York",
        tzdata_version="2026.3",
        source_manifest_ref=source_manifest_ref,
        input_manifest_ref=input_manifest_ref,
        entry_open=value.entry_session.open_ts.isoformat(),
        entry_close=value.entry_session.close_ts.isoformat(),
        exit_open=value.exit_session.open_ts.isoformat(),
        exit_close=value.exit_session.close_ts.isoformat(),
        credential_reads=0,
        broker_calls=0,
        Docker_calls=0,
        model_calls=0,
    )
    _new(proof_path, _encode(result))
    return result


def planned_slots():
    day, slots = date(2026, 10, 19), []
    while day <= date(2026, 11, 20):
        if day.weekday() < 5:
            slots.append(day.isoformat() + "T15:10:00Z")
        day += timedelta(days=1)
    for day in ("2026-10-19", "2026-11-17"):
        slots.extend(day + "T15:" + minute + ":00Z" for minute in ("14", "18", "22"))
    return sorted(slots)


def write_launch_binding(
    *,
    image,
    source_manifest,
    source_manifest_ref,
    input_manifest,
    input_manifest_ref,
    owner_probe,
    owner_probe_ref,
):
    """Parent calls only after source QA/frozen release/image/input pins exist."""
    if PIN.fullmatch(image) is None:
        raise ValueError("exact_local_image_required")
    read_source_manifest(source_manifest, source_manifest_ref)
    read_input_manifest(input_manifest, input_manifest_ref)
    _read(owner_probe, owner_probe_ref, 131072)
    argv = launch_argv(
        image=image,
        source_manifest=source_manifest,
        source_manifest_ref=source_manifest_ref,
        input_manifest=input_manifest,
        input_manifest_ref=input_manifest_ref,
        owner_probe=owner_probe,
        owner_probe_ref=owner_probe_ref,
    )
    value = dict(
        kind="current20-paper-public-launch-binding-v1",
        task_name=TASK,
        executable=str(PYTHONW),
        argv=argv,
        arguments=subprocess.list2cmdline(argv[1:]),
        working_directory=str(ROOT),
        source_manifest_ref=source_manifest_ref,
        input_manifest_ref=input_manifest_ref,
        owner_probe_ref=owner_probe_ref,
        image=image,
        host_ref=_sha((ROOT / HOST).read_bytes()),
        worker_ref=_sha((ROOT / WORKER).read_bytes()),
        executable_ref=_sha(PYTHONW.read_bytes()),
        timezone_dependency=dict(
            site=str(TRUSTED_SITE), version="2026.3", IANA="2026c", files=TZDATA_PINS
        ),
        source_manifest=str(source_manifest),
        input_manifest=str(input_manifest),
        owner_probe=str(owner_probe),
        explicit_utc_slots=planned_slots(),
        multiple_instances="IgnoreNew",
        execution_time_limit="PT5M",
        status="SOURCE_PINNED_LAUNCH_CONFIGURATION_NOT_INVOCATION",
    )
    path = ARTIFACT / RUNTIME_RELATIVE / (
        "PUBLIC-LAUNCH-BINDING-" + source_manifest_ref[7:] + ".json"
    )
    _new(path, _encode(value))
    return dict(
        status="launch_binding_written", binding_path=str(path), binding_ref=_sha(_encode(value))
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--prepare-input", action="store_true")
    modes.add_argument("--write-launch-binding", action="store_true")
    modes.add_argument("--validate-input", action="store_true")
    parser.add_argument("--proof-path", type=Path)
    for name in (
        "parent-contract",
        "data-binding",
        "bundle",
        "weights",
        "source-manifest",
        "input-manifest",
        "owner-probe",
    ):
        parser.add_argument("--" + name, type=Path)
    for name in (
        "parent-contract-ref",
        "data-binding-ref",
        "source-manifest-ref",
        "input-manifest-ref",
        "owner-probe-ref",
        "image",
    ):
        parser.add_argument("--" + name, default="")
    args = parser.parse_args(argv)
    try:
        if args.prepare_input:
            result = prepare_input(
                parent_contract=args.parent_contract,
                parent_contract_ref=args.parent_contract_ref,
                data_binding=args.data_binding,
                data_binding_ref=args.data_binding_ref,
                bundle=args.bundle,
                weights=args.weights,
            )
        elif args.validate_input:
            result = validate_input(
                source_manifest=args.source_manifest,
                source_manifest_ref=args.source_manifest_ref,
                input_manifest=args.input_manifest,
                input_manifest_ref=args.input_manifest_ref,
                proof_path=args.proof_path,
            )
        else:
            options = dict(
                image=args.image,
                source_manifest=args.source_manifest,
                source_manifest_ref=args.source_manifest_ref,
                input_manifest=args.input_manifest,
                input_manifest_ref=args.input_manifest_ref,
                owner_probe=args.owner_probe,
                owner_probe_ref=args.owner_probe_ref,
            )
            result = (
                write_launch_binding(**options)
                if args.write_launch_binding
                else run(execute=args.execute, **options)
            )
    except Exception:
        result = _failure("host_preflight_unavailable")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 20 if result["status"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
