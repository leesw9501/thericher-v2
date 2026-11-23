import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from thericher_v2.ops.paper_scheduled_preflight import (
    ScheduledPaperPlan,
    ScheduledPaperPreflight,
    run_scheduled_preflight,
)


@pytest.fixture
def plan():
    start = datetime(2030, 1, 2, 14, 31, tzinfo=UTC)
    return ScheduledPaperPlan(
        slot="invented-h3-slot",
        phase="entry",
        task_name="invented-h3-entry",
        action_sha256="a" * 64,
        source_sha256="b" * 64,
        release_sha256="c" * 64,
        starts_at=start,
        ends_at=start + timedelta(minutes=4),
        hard_stop=start + timedelta(minutes=6),
    )


def attempt_dir(root, plan):
    return root / f"{plan.opportunity}-{plan.phase}"


def invoke(root, plan, **overrides):
    kwargs = dict(
        plan=plan,
        source_sha256=plan.source_sha256,
        release_sha256=plan.release_sha256,
        phase=plan.phase,
        clock=lambda: plan.starts_at,
        check_source=lambda p: None,
        check_release=lambda p, source: None,
        check_window=lambda p, at: None,
        check_owner=lambda p, source: None,
    )
    return run_scheduled_preflight(root, **(kwargs | overrides))


def test_returns_checked_objects_without_calling_financial_path(tmp_path, plan):
    order = []
    source, release, owner = object(), object(), object()
    directory = attempt_dir(tmp_path, plan)

    def check_source(p):
        assert p is plan
        assert (directory / "ATTEMPT.json").is_file()
        order.append("source")
        return source

    def check_release(p, value):
        assert p is plan and value is source
        order.append("release")
        return release

    def check_window(p, at):
        assert p is plan and at == plan.starts_at
        order.append("window")

    def check_owner(p, value):
        assert p is plan and value is source
        order.append("owner")
        return owner

    result = invoke(
        tmp_path,
        plan,
        check_source=check_source,
        check_release=check_release,
        check_window=check_window,
        check_owner=check_owner,
    )

    assert isinstance(result, ScheduledPaperPreflight)
    assert (result.plan, result.source, result.release, result.owner, result.checked_at) == (
        plan,
        source,
        release,
        owner,
        plan.starts_at,
    )
    assert order == ["source", "release", "window", "owner"]
    assert set(tmp_path.iterdir()) == {directory}
    assert {p.name for p in directory.iterdir()} == {"ATTEMPT.json", "STARTUP.json"}
    attempt = (directory / "ATTEMPT.json").read_bytes()
    assert json.loads(attempt)["source"] == plan.source_sha256
    terminal = json.loads((directory / "STARTUP.json").read_bytes())
    assert terminal["status"] == "ready"
    assert terminal["attempt_sha256"] == hashlib.sha256(attempt).hexdigest()
    with pytest.raises(FileExistsError):
        invoke(tmp_path, plan, check_source=lambda _: pytest.fail("duplicate ran"))


@pytest.mark.parametrize("failed", ["source", "release", "window", "owner"])
def test_failure_short_circuits_and_retains_only_category(tmp_path, plan, failed):
    order = []
    stages = ["source", "release", "window", "owner"]

    def check(stage):
        order.append(stage)
        if stage == failed:
            raise RuntimeError("do not retain me")

    checks = {f"check_{s}": lambda *_, s=s: check(s) for s in stages}
    with pytest.raises(RuntimeError, match="do not retain me"):
        invoke(tmp_path, plan, **checks)
    assert order == stages[: stages.index(failed) + 1]
    raw = (attempt_dir(tmp_path, plan) / "STARTUP.json").read_bytes()
    assert b"do not retain me" not in raw
    terminal = json.loads(raw)
    assert (terminal["status"], terminal["stage"], terminal["category"]) == (
        "failed",
        failed,
        "RuntimeError",
    )


def test_false_owner_proof_cannot_admit(tmp_path, plan):
    with pytest.raises(ValueError, match="denied"):
        invoke(tmp_path, plan, check_owner=lambda *_: False)
    assert (
        json.loads((attempt_dir(tmp_path, plan) / "STARTUP.json").read_bytes())["stage"] == "owner"
    )


def test_interrupted_attempt_stays_consumed_even_if_source_changes(tmp_path, plan):
    def interrupt(*_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        invoke(tmp_path, plan, check_owner=interrupt)
    directory = attempt_dir(tmp_path, plan)
    assert {p.name for p in directory.iterdir()} == {"ATTEMPT.json"}
    replacement = replace(plan, source_sha256="d" * 64, task_name="invented-renamed-entry")
    with pytest.raises(FileExistsError):
        invoke(tmp_path, replacement, check_source=lambda _: pytest.fail("duplicate ran"))
    assert {p.name for p in directory.iterdir()} == {"ATTEMPT.json"}


@pytest.mark.parametrize("offset", [timedelta(microseconds=-1), timedelta(minutes=4)])
def test_window_denies_early_or_expired_without_owner_proof(tmp_path, plan, offset):
    with pytest.raises(ValueError, match="Outside scheduled"):
        invoke(
            tmp_path,
            plan,
            clock=lambda: plan.starts_at + offset,
            check_window=lambda *_: pytest.fail("window callback ran"),
            check_owner=lambda *_: pytest.fail("owner callback ran"),
        )
    assert (
        json.loads((attempt_dir(tmp_path, plan) / "STARTUP.json").read_bytes())["stage"] == "window"
    )


def test_expiry_during_owner_proof_withholds_ready_result(tmp_path, plan):
    moments = iter([plan.starts_at, plan.ends_at])
    with pytest.raises(ValueError, match="Outside scheduled"):
        invoke(tmp_path, plan, clock=lambda: next(moments))
    terminal = json.loads((attempt_dir(tmp_path, plan) / "STARTUP.json").read_bytes())
    assert (terminal["stage"], terminal["status"]) == ("prepare", "failed")


@pytest.mark.parametrize(
    "overrides", [{"phase": "exit"}, {"source_sha256": "d" * 64}, {"release_sha256": "d" * 64}]
)
def test_launch_mismatch_cannot_consume_real_opportunity(tmp_path, plan, overrides):
    with pytest.raises(ValueError, match="plan binding"):
        invoke(
            tmp_path, plan, **overrides, check_source=lambda _: pytest.fail("source callback ran")
        )
    assert not list(tmp_path.iterdir())


def test_exit_has_its_own_attempt(tmp_path, plan):
    exit_plan = replace(plan, phase="exit", task_name="invented-h3-exit")
    invoke(tmp_path, plan)
    assert invoke(tmp_path, exit_plan).plan == exit_plan
    assert set(tmp_path.iterdir()) == {
        attempt_dir(tmp_path, plan),
        attempt_dir(tmp_path, exit_plan),
    }


@pytest.mark.parametrize("field", ["action_sha256", "hard_stop", "starts_at"])
def test_rejects_invalid_frozen_plan(tmp_path, plan, field):
    invalid = {
        "action_sha256": "invalid",
        "hard_stop": plan.starts_at,
        "starts_at": plan.starts_at.astimezone(timezone(timedelta(hours=9))),
    }
    with pytest.raises(ValueError, match="plan binding"):
        invoke(tmp_path, replace(plan, **{field: invalid[field]}))
    assert not list(tmp_path.iterdir())
