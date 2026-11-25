import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import PureWindowsPath

import pytest

from thericher_v2.ops.h3_dec4_observer_plan import (
    OBSERVER_API7_SHA256,
    OBSERVER_TASK_PATH,
    OBSERVER_XML_SHA256,
    READINESS_SCHEMA,
    Dec4ObserverPlan,
    require_dec4_observer_readiness,
)

ROOT = r"D:\test-release\dec4-r1"
REQUEST = "c" * 32


def _plan(phase="entry"):
    return Dec4ObserverPlan(phase, ROOT, "a" * 64, "b" * 64)


def _reply(plan):
    return {
        "schema": READINESS_SCHEMA,
        "status": "EXACT_ORIGINAL_OBSERVER_READINESS",
        "plan_sha256": plan.sha256,
        "request_id": REQUEST,
        "task_path": OBSERVER_TASK_PATH,
        "xml_sha256": OBSERVER_XML_SHA256,
        "api7_sha256": OBSERVER_API7_SHA256,
        "enabled": True,
        "hidden_inclusive": True,
        "instances": 0,
        "Task_writes": 0,
    }


def _check(plan, reply, **kwargs):
    return require_dec4_observer_readiness(
        plan,
        reply,
        **(
            dict(
                expected_plan_sha256=plan.sha256,
                request_id=REQUEST,
                now_utc=datetime(2026, 12, 4, 14, 31, tzinfo=UTC),
            )
            | kwargs
        ),
    )


@pytest.mark.parametrize(
    ("phase", "date", "minute", "bank_task"),
    [
        ("entry", "04", "31", r"\thericher-kis-paper-dec4-h3-entry-20261204-v1"),
        ("exit", "09", "30", r"\thericher-kis-paper-dec9-h3-owned-exit-20261209-v1"),
    ],
)
def test_exact_phase_policy_and_bridge_locations(phase, date, minute, bank_task):
    plan = _plan(phase)
    opens = f"2026-12-{date}T14:{minute}:00+00:00"
    closes = f"2026-12-{date}T14:35:00+00:00"
    hard = f"2026-12-{date}T14:37:00+00:00"
    root = PureWindowsPath(ROOT) / f"observer-{phase}"
    assert json.loads(plan.policy_bytes) == {
        "name": r"\thericher-kis-paper-snapshot-observer"[1:],
        "original_enabled": True,
        "xml_sha256": "e2cbf12f821dd447ecf4a1f3f65498795363a52ecb7a9654e45360498d94d827",
        "api7_sha256": "fab150776db7652ebf7fe24828069e0637db567357437cf6f93bbb1141f28a04",
        "suspend_not_before": opens,
        "suspend_not_after": closes,
        "restore_not_before": opens,
    }
    manifest = json.loads(plan.manifest_bytes)
    assert manifest["bank_task_path"] == bank_task
    assert manifest["observer_task_path"] == r"\thericher-kis-paper-snapshot-observer"
    assert (manifest["opens_utc"], manifest["closes_utc"], manifest["hard_utc"]) == (
        opens,
        closes,
        hard,
    )
    for key, path in {
        "helper_root": root,
        "work_root": root / "work",
        "output_root": root / "owned-output",
        "policy_path": root / "POLICY.json",
        "bridge_path": root / "observer_bridge.ps1",
        "core_path": root / "yield_observer.ps1",
    }.items():
        assert manifest[key] == str(path)
    assert (manifest["bridge_sha256"], manifest["core_sha256"]) == ("a" * 64, "b" * 64)
    assert manifest["policy_sha256"] == hashlib.sha256(plan.policy_bytes).hexdigest()
    assert _check(plan, _reply(plan), now_utc=datetime.fromisoformat(opens)) is None


def test_entry_and_exit_cannot_replay_policy_or_readiness():
    entry, exit_ = _plan(), _plan("exit")
    assert not set((entry.helper_root, entry.work_root, entry.output_root)) & set(
        (exit_.helper_root, exit_.work_root, exit_.output_root)
    )
    assert entry.policy_sha256 != exit_.policy_sha256
    assert entry.sha256 != exit_.sha256
    policy = json.loads(entry.policy_bytes)
    old = {
        key: value.replace("2026-12-04", "2026-11-09") if type(value) is str else value
        for key, value in policy.items()
    }
    old_bytes = json.dumps(old, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(old_bytes).hexdigest() != entry.policy_sha256
    with pytest.raises(ValueError, match="readiness_unknown"):
        _check(exit_, _reply(entry), now_utc=datetime(2026, 12, 9, 14, 30, tzinfo=UTC))


@pytest.mark.parametrize(
    "changes",
    [
        {"task_path": r"\other\thericher-kis-paper-snapshot-observer"},
        {"xml_sha256": "f" * 64},
        {"api7_sha256": "f" * 64},
        {"enabled": 1},
        {"hidden_inclusive": False},
        {"instances": 1},
        {"instances": False},
        {"Task_writes": False},
        {"Task_writes": 1},
        {"request_id": "f" * 32},
        {"restore_obligation": False},
    ],
)
def test_readiness_rejects_drift_unknown_and_wrong_request(changes):
    plan = _plan()
    with pytest.raises(ValueError, match="readiness_unknown"):
        _check(plan, _reply(plan) | changes)


def test_reference_bridge_reply_is_not_current_hidden_inclusive_proof():
    with pytest.raises(ValueError, match="readiness_unknown"):
        _check(
            _plan(),
            {"status": "EXACT_ORIGINAL_OBSERVER_READINESS", "instances": 0, "Task_writes": 0},
        )


def test_readiness_requires_independent_manifest_pin():
    plan = _plan()
    drift = replace(plan, bridge_sha256="d" * 64)
    with pytest.raises(ValueError, match="plan_pin"):
        _check(drift, _reply(drift), expected_plan_sha256=plan.sha256)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 11, 9, 14, 31, tzinfo=UTC),
        datetime(2026, 12, 4, 14, 31, tzinfo=UTC) - timedelta(microseconds=1),
        datetime(2026, 12, 4, 14, 31),
        datetime(2026, 12, 4, 14, 35, tzinfo=UTC),
        datetime(2026, 12, 4, 14, 37, tzinfo=UTC),
    ],
)
def test_readiness_is_within_the_exact_open_closed_window(now):
    plan = _plan()
    with pytest.raises(ValueError, match="readiness_window"):
        _check(plan, _reply(plan), now_utc=now)


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "nov9"},
        {"package_root": "relative"},
        {"package_root": "D:\\"},
        {"package_root": r"\\server\share\release"},
        {"package_root": r"D:\release\..\reference"},
        {"bridge_sha256": "b" * 64},
        {"bridge_sha256": "2b0ce611d33c4c29d712ad994cbee8dcca220d567a370abf0192d67e6dcaf7a8"},
        {"core_sha256": "3291ca1e75a9f8dd49525c293799d30e6b0e5a3733e813e311e017896233c0be"},
    ],
)
def test_rejects_nonowned_path_shape_and_reference_sources(changes):
    with pytest.raises(ValueError):
        replace(_plan(), **changes)
