"""Project the Dec4/9 BankLeg schedule into protected native installer inputs."""

import hashlib
import ntpath
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from subprocess import list2cmdline
from xml.etree.ElementTree import Element, SubElement, tostring

from thericher_v2.execution.paper_peer_visit import digest, encode
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.paper_scheduled_preflight import ScheduledPaperPlan

NATIVE_MODULES = (
    "scripts/paper_task_registration.psm1",
    "scripts/paper_native_task_definition.psm1",
    "scripts/paper_native_pair_readback.psm1",
    "scripts/paper_native_future_pair.psm1",
)


def _pin(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("dec4_schedule_pin")
    return value


def _path(value: str) -> PureWindowsPath:
    path = PureWindowsPath(value)
    isreserved = getattr(ntpath, "isreserved", None)
    if (
        re.fullmatch(r"[A-Za-z]:", path.drive) is None
        or not path.is_absolute()
        or str(path) != value
        or re.search(r'[<>"|?*%\x00-\x1f]', value)
        or "$(" in value
        or any(p.endswith((" ", ".")) or ":" in p for p in path.parts[1:])
        or any(
            isreserved(p) if isreserved is not None else PureWindowsPath(p).is_reserved()
            for p in path.parts[1:]
        )
    ):
        raise ValueError("dec4_schedule_local_path")
    return path


def _xml_fields(parent: Element, fields: Mapping[str, str]) -> None:
    for name, value in fields.items():
        SubElement(parent, name).text = value


def _disabled_xml(item: dict, sid: str, sddl: str) -> str:
    task = Element(
        "Task", version="1.4", xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"
    )
    _xml_fields(SubElement(task, "RegistrationInfo"), {"Author": sid, "SecurityDescriptor": sddl})
    trigger = SubElement(SubElement(task, "Triggers"), "TimeTrigger")
    _xml_fields(
        trigger,
        {
            "StartBoundary": item["start_UTC"],
            "EndBoundary": item["last_start_exclusive_UTC"],
            "Enabled": "true",
        },
    )
    principal = SubElement(SubElement(task, "Principals"), "Principal", id="Owner")
    _xml_fields(
        principal, {"UserId": sid, "LogonType": "InteractiveToken", "RunLevel": "LeastPrivilege"}
    )
    settings = SubElement(task, "Settings")
    _xml_fields(
        settings,
        {
            "MultipleInstancesPolicy": "IgnoreNew",
            "DisallowStartIfOnBatteries": "true",
            "StopIfGoingOnBatteries": "true",
            "AllowHardTerminate": "true",
            "StartWhenAvailable": "false",
            "RunOnlyIfNetworkAvailable": "false",
        },
    )
    SubElement(settings, "IdleSettings")
    _xml_fields(
        settings,
        {
            "AllowStartOnDemand": "false",
            "Enabled": "false",
            "Hidden": "true",
            "RunOnlyIfIdle": "false",
            "DisallowStartOnRemoteAppSession": "false",
            "UseUnifiedSchedulingEngine": "true",
            "WakeToRun": "false",
            "ExecutionTimeLimit": item["execution_time_limit"],
            "Priority": "7",
        },
    )
    action = SubElement(SubElement(task, "Actions", Context="Owner"), "Exec")
    _xml_fields(
        action,
        {
            "Command": item["executable"],
            "Arguments": item["arguments"],
            "WorkingDirectory": item["working_directory"],
        },
    )
    return tostring(task, encoding="unicode")


def build_dec4_schedule_plan(
    *,
    source_sha256: str,
    release_sha256: str,
    dispatcher_root: str,
    launcher_path: str,
    launcher_source: bytes,
    launcher_sha256: str,
    pythonw_path: str,
    pythonw_sha256: str,
    native_module_sha256: Mapping[str, str],
    sid: str,
    now_utc: datetime,
    install_deadline_utc: datetime,
) -> dict:
    """Return plan data only; never read files, inspect ambient env, or claim an attempt.

    The authenticated host source must bind the caller-pinned launcher path/bytes,
    interpreter and installer modules. The launcher must implement this exact
    argv ABI and use each phase's ``action`` and ``slot`` for native preflight.
    The installer still authenticates the plan, proves local SID and absence,
    derives its protected readback from stamped COM drafts, and claims once.
    Runtime must prove actual XML/API/ACL, instance, PID/birth, argv and environment.
    """
    source_sha256, release_sha256 = _pin(source_sha256), _pin(release_sha256)
    launcher_sha256, pythonw_sha256 = _pin(launcher_sha256), _pin(pythonw_sha256)
    root, launcher, pythonw = map(_path, (dispatcher_root, launcher_path, pythonw_path))
    if launcher.suffix.lower() not in {".py", ".pyw"} or pythonw.name.lower() != "pythonw.exe":
        raise ValueError("dec4_schedule_quiet_launcher")
    if (
        type(launcher_source) is not bytes
        or not launcher_source.strip()
        or hashlib.sha256(launcher_source).hexdigest() != launcher_sha256
    ):
        raise ValueError("dec4_schedule_loaded_launcher_pin")
    if set(native_module_sha256) != set(NATIVE_MODULES):
        raise ValueError("dec4_schedule_native_modules")
    native_pins = {name: _pin(native_module_sha256[name]) for name in NATIVE_MODULES}
    if type(sid) is not str or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", sid) is None:
        raise ValueError("dec4_schedule_sid")
    if (
        any(
            type(t) is not datetime or t.utcoffset() != timedelta(0)
            for t in (now_utc, install_deadline_utc)
        )
        or not now_utc < install_deadline_utc < _TIMES["entry"][0]
    ):
        raise ValueError("dec4_schedule_future_deadline")

    manifest = dict(
        schema="PAPER_TASK_REGISTRATION_V1",
        runtime_source_sha256=source_sha256,
        runtime_release_sha256=release_sha256,
        entry_name=TASKS["entry"],
        exit_name=TASKS["exit"],
    )
    sddl = f"O:{sid}G:{sid}D:P(A;;FA;;;{sid})(A;;FA;;;SY)(A;;FA;;;BA)"
    phases = {}
    for phase, role in (("exit", "ORIGINAL_EXIT"), ("entry", "ENTRY")):
        start, end, hard = _TIMES[phase]
        argv = [
            str(pythonw),
            "-I",
            "-S",
            "-B",
            str(launcher),
            "--phase",
            phase,
            "--source-sha256",
            source_sha256,
            "--release-sha256",
            release_sha256,
        ]
        action_fields = dict(
            executable=argv[0], arguments=list2cmdline(argv[1:]), working_directory=str(root)
        )
        action = encode(action_fields).decode("ascii")
        slot = dict(
            name=TASKS[phase],
            start_UTC=start.isoformat(),
            end_UTC=end.isoformat(),
            hard_UTC=hard.isoformat(),
        )
        item = dict(
            name=slot["name"],
            role=role,
            **action_fields,
            start_UTC=slot["start_UTC"],
            last_start_exclusive_UTC=slot["end_UTC"],
            # The Scheduler limit is relative to launch, not an absolute hard stop.
            execution_time_limit=f"PT{(hard - end) // timedelta(minutes=1)}M",
        )
        action_pin = hashlib.sha256(action.encode("ascii")).hexdigest()
        phases[phase] = dict(
            slot=slot,
            item=item,
            disabled_xml=_disabled_xml(item, sid, sddl),
            action=action,
            opportunity=ScheduledPaperPlan(
                ROUND,
                phase,
                slot["name"],
                action_pin,
                source_sha256,
                release_sha256,
                start,
                end,
                hard,
            ).opportunity,
            expected_argv=argv,
            expected_argv_sha256=digest(argv),
            owner_expected=dict(
                dispatcher_source=source_sha256,
                dispatcher_release=release_sha256,
                dispatcher_root=str(root),
                task_name=slot["name"],
                task_action_sha256=action_pin,
                round_id=ROUND,
            ),
        )
    return dict(
        round_id=ROUND,
        manifest=manifest,
        phases=phases,
        sid=sid,
        install_deadline_utc=install_deadline_utc.isoformat(),
        install_attempt_id=digest(["paper-native-future-install-v1", ROUND]),
        registration_sddl=sddl,
        native_module_sha256=native_pins,
        launcher_sha256=launcher_sha256,
        pythonw_sha256=pythonw_sha256,
        environment_expected=dict(
            # Exec does not set environment variables. Verify inherited names
            # case-insensitively without reading or recording live values.
            mode_key="THERICHER_MODE",
            mode_allowed_if_present=("off", "paper", "kis_paper"),
            absent_prefixes=("KIS_LIVE_",),
        ),
    )
