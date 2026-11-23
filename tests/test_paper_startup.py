import hashlib
import json
from pathlib import Path

import pytest

from thericher_v2.ops.paper_startup import STAGES, run_startup


def invoke(path, checks, prepare):
    return run_startup(
        path,
        opportunity="a" * 32,
        source="b" * 64,
        phase="entry",
        checks=checks,
        prepare=prepare,
    )


@pytest.mark.parametrize("failed", (*STAGES, "prepare"))
def test_preflight_failure_has_bound_safe_stage(tmp_path, failed):
    entered = []

    def step(name):
        entered.append(name)
        if name == failed:
            raise ValueError("not-for-receipt")

    checks = {name: lambda name=name: step(name) for name in STAGES}
    with pytest.raises(ValueError, match="not-for-receipt"):
        invoke(tmp_path, checks, lambda: step("prepare"))
    directory = tmp_path / ("a" * 32 + "-entry")
    raw = (directory / "ATTEMPT.json").read_bytes()
    outcome = (directory / "STARTUP.json").read_bytes()
    decoded = json.loads(outcome)
    assert decoded["status"] == "failed"
    assert decoded["stage"] == failed
    assert decoded["category"] == "ValueError"
    assert decoded["attempt_sha256"] == hashlib.sha256(raw).hexdigest()
    assert b"not-for-receipt" not in raw + outcome
    assert entered[-1] == failed
    with pytest.raises(FileExistsError):
        invoke(tmp_path, checks, pytest.fail)
    assert (directory / "STARTUP.json").read_bytes() == outcome


def test_ready_is_only_preflight_result(tmp_path):
    checks = dict.fromkeys(STAGES, lambda: None)
    assert invoke(tmp_path, checks, lambda: 42) == 42
    outcome = json.loads((tmp_path / ("a" * 32 + "-entry") / "STARTUP.json").read_bytes())
    assert set(outcome) == {"attempt_sha256", "status", "stage", "category", "finished_at"}
    assert outcome["status"] == "ready"


def test_relative_evidence_root_rejected_before_callbacks():
    with pytest.raises(ValueError, match="startup binding"):
        invoke(Path("relative"), dict.fromkeys(STAGES, pytest.fail), pytest.fail)
