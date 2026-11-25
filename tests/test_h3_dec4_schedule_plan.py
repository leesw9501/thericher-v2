import hashlib
import json
from datetime import UTC, datetime
from subprocess import list2cmdline
from xml.etree import ElementTree as ET

import pytest

from thericher_v2.ops.h3_dec4_bank_visit import ROUND, TASKS
from thericher_v2.ops.h3_dec4_schedule_plan import NATIVE_MODULES, build_dec4_schedule_plan

LAUNCHER = b"def main():\n    raise SystemExit(1)\n"
SID = "S-1-5-21-111-222-333-1001"
ARGS = dict(
    source_sha256="a" * 64,
    release_sha256="b" * 64,
    dispatcher_root=r"D:\invented & owned\dispatcher",
    launcher_path=r"C:\invented host\launch.pyw",
    launcher_source=LAUNCHER,
    launcher_sha256=hashlib.sha256(LAUNCHER).hexdigest(),
    pythonw_path=r"C:\invented Python\pythonw.exe",
    pythonw_sha256="c" * 64,
    native_module_sha256=dict.fromkeys(NATIVE_MODULES, "d" * 64),
    sid=SID,
    now_utc=datetime(2026, 11, 26, tzinfo=UTC),
    install_deadline_utc=datetime(2026, 12, 3, tzinfo=UTC),
)
NS = {"": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def test_protected_future_pair_definition_and_runtime_expectations_agree():
    plan = build_dec4_schedule_plan(**ARGS)
    assert plan["round_id"] == ROUND
    assert plan["manifest"] == dict(
        schema="PAPER_TASK_REGISTRATION_V1",
        runtime_source_sha256=ARGS["source_sha256"],
        runtime_release_sha256=ARGS["release_sha256"],
        entry_name=TASKS["entry"],
        exit_name=TASKS["exit"],
    )
    assert tuple(plan["phases"]) == ("exit", "entry")
    assert plan["registration_sddl"] == f"O:{SID}G:{SID}D:P(A;;FA;;;{SID})(A;;FA;;;SY)(A;;FA;;;BA)"
    for phase, day, minute, role in (
        ("entry", "04", "31", "ENTRY"),
        ("exit", "09", "30", "ORIGINAL_EXIT"),
    ):
        leg = plan["phases"][phase]
        slot, item = leg["slot"], leg["item"]
        assert slot == dict(
            name=TASKS[phase],
            start_UTC=f"2026-12-{day}T14:{minute}:00+00:00",
            end_UTC=f"2026-12-{day}T14:35:00+00:00",
            hard_UTC=f"2026-12-{day}T14:37:00+00:00",
        )
        assert item["role"] == role and item["name"] == TASKS[phase]
        assert item["execution_time_limit"] == "PT2M"
        assert item["start_UTC"] == slot["start_UTC"]
        assert item["last_start_exclusive_UTC"] == slot["end_UTC"]
        argv = leg["expected_argv"]
        assert argv == [
            ARGS["pythonw_path"],
            "-I",
            "-S",
            "-B",
            ARGS["launcher_path"],
            "--phase",
            phase,
            "--source-sha256",
            ARGS["source_sha256"],
            "--release-sha256",
            ARGS["release_sha256"],
        ]
        assert item["arguments"] == list2cmdline(argv[1:])
        assert (
            leg["expected_argv_sha256"]
            == hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()
        )
        fields = {k: item[k] for k in ("executable", "arguments", "working_directory")}
        assert json.loads(leg["action"]) == fields
        assert leg["owner_expected"] == dict(
            dispatcher_source=ARGS["source_sha256"],
            dispatcher_release=ARGS["release_sha256"],
            dispatcher_root=ARGS["dispatcher_root"],
            task_name=TASKS[phase],
            round_id=ROUND,
            task_action_sha256=hashlib.sha256(leg["action"].encode()).hexdigest(),
        )

        xml = ET.fromstring(leg["disabled_xml"])
        assert xml.attrib == {"version": "1.4"}
        assert (
            xml.findtext("RegistrationInfo/SecurityDescriptor", namespaces=NS)
            == plan["registration_sddl"]
        )
        assert xml.find("RegistrationInfo/URI", NS) is None  # Protected profile adds URI.
        assert xml.findtext("Principals/Principal/UserId", namespaces=NS) == SID
        assert xml.findtext("Principals/Principal/LogonType", namespaces=NS) == "InteractiveToken"
        assert xml.findtext("Principals/Principal/RunLevel", namespaces=NS) == "LeastPrivilege"
        assert len(xml.find("Triggers", NS)) == len(xml.find("Actions", NS)) == 1
        assert xml.find("Triggers/TimeTrigger/Repetition", NS) is None
        assert (
            xml.findtext("Triggers/TimeTrigger/StartBoundary", namespaces=NS) == slot["start_UTC"]
        )
        assert xml.findtext("Triggers/TimeTrigger/EndBoundary", namespaces=NS) == slot["end_UTC"]
        for name in ("Enabled", "AllowStartOnDemand", "StartWhenAvailable", "WakeToRun"):
            assert xml.findtext(f"Settings/{name}", namespaces=NS) == "false"
        assert xml.findtext("Settings/Hidden", namespaces=NS) == "true"
        assert xml.findtext("Settings/UseUnifiedSchedulingEngine", namespaces=NS) == "true"
        assert xml.findtext("Settings/MultipleInstancesPolicy", namespaces=NS) == "IgnoreNew"
        assert (
            xml.findtext("Settings/ExecutionTimeLimit", namespaces=NS)
            == item["execution_time_limit"]
        )
        for field, tag in zip(fields, ("Command", "Arguments", "WorkingDirectory"), strict=True):
            assert xml.findtext(f"Actions/Exec/{tag}", namespaces=NS) == fields[field]

    assert plan["environment_expected"]["absent_prefixes"] == ("KIS_LIVE_",)
    assert set(plan["environment_expected"]["mode_allowed_if_present"]) == {
        "off",
        "paper",
        "kis_paper",
    }
    assert plan["native_module_sha256"] == ARGS["native_module_sha256"]


def test_rebinding_does_not_reopen_one_attempt():
    first = build_dec4_schedule_plan(**ARGS)
    second = build_dec4_schedule_plan(**(ARGS | {"release_sha256": "e" * 64}))
    assert first["install_attempt_id"] == second["install_attempt_id"]
    for phase in TASKS:
        left, right = first["phases"][phase], second["phases"][phase]
        assert left["opportunity"] == right["opportunity"]
        assert left["action"] != right["action"]
        assert left["expected_argv_sha256"] != right["expected_argv_sha256"]


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"launcher_source": None}, "loaded_launcher_pin"),
        ({"launcher_source": b""}, "loaded_launcher_pin"),
        ({"launcher_source": b"different"}, "loaded_launcher_pin"),
        ({"pythonw_path": r"C:\Python\python.exe"}, "quiet_launcher"),
        ({"launcher_path": r"C:\%TEMP%\host.py"}, "local_path"),
        ({"launcher_path": r"C:\$(Arg0)\host.py"}, "local_path"),
        ({"dispatcher_root": r"C:\parent\..\folder"}, "local_path"),
        ({"launcher_path": r"C:\NUL\host.py"}, "local_path"),
        ({"native_module_sha256": {}}, "native_modules"),
        ({"source_sha256": "A" * 64}, "pin"),
        ({"sid": "S-1-5-18"}, "sid"),
        ({"install_deadline_utc": ARGS["now_utc"]}, "future_deadline"),
        ({"install_deadline_utc": datetime(2026, 12, 4, 14, 31, tzinfo=UTC)}, "future_deadline"),
        ({"now_utc": datetime(2026, 11, 26)}, "future_deadline"),
    ],
)
def test_refuses_unbound_or_nonfuture_inputs(updates, reason):
    with pytest.raises(ValueError, match=f"^dec4_schedule_{reason}$"):
        build_dec4_schedule_plan(**(ARGS | updates))
