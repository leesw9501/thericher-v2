"""Explicit metadata retirement never releases a native intent or reservation."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta

import pytest

from test_kis_paper_current_daily_preintent_refresh import (
    add_stock_owner,
    book,
    book_bytes,
    directory,
    native_plan,
    pointer_path,
)
from test_kis_paper_current_daily_preintent_refresh import preintent as preintent
from test_kis_paper_portfolio_execute import harness as harness
from test_kis_paper_portfolio_execute import (
    no_actual_provider_or_credentials as no_actual_provider_or_credentials,
)
from thericher_v2.execution import kis_paper_current_daily_session as daily


def options(args, old):
    return dict(
        paths=old["context"]["paths"],
        expected_account_ref=old["context"]["expected_account_ref"],
        expected_basis_ref=old["context"]["expected_basis_ref"],
        expected_binding_ref="sha256:" + daily.budget._digest(book(args)),
        expected_record_ref=old["ref"],
        expected_pointer_sha256=hashlib.sha256(pointer_path(args).read_bytes()).hexdigest(),
        clock=args["clock"], execute=True,
    )


def expire(args, old):
    args["client"].now = (
        datetime.fromisoformat(old["context"]["valid_until"]) + timedelta(seconds=1)
    )


def archive_path(args, old):
    return args["state_root"] / ".daily_unstarted_archive" / (old["ref"][7:] + ".json")


def forbid(*args, **kwargs):
    pytest.fail("maintenance_must_not_call_a_client_or_environment")


def test_default_false_has_no_path_clock_credentials_or_lock_io(monkeypatch):
    monkeypatch.setattr(daily.Path, "resolve", forbid)
    monkeypatch.setattr(daily.budget, "_read_json", forbid)
    monkeypatch.setattr(daily.canary, "exclusive_kis_paper_canary_state_lock", forbid)
    assert daily.retire_expired_unstarted_daily_context(
        paths=None, expected_account_ref=None, expected_basis_ref=None,
        expected_binding_ref=None, expected_record_ref=None, expected_pointer_sha256=None,
        clock=forbid,
    ) is False


def test_native_retirement_is_byte_exact_idempotent_and_book_unchanged(preintent, monkeypatch):
    args, old, loads = preintent
    original, before = pointer_path(args).read_bytes(), book_bytes(args)
    expire(args, old)
    kwargs = options(args, old)
    monkeypatch.setattr(args["client"], "snapshot", forbid)
    monkeypatch.setattr(args["client"], "submit_limit", forbid)
    monkeypatch.setattr(daily, "_account", forbid)
    assert daily.retire_expired_unstarted_daily_context(**kwargs) is True
    assert not pointer_path(args).exists() and archive_path(args, old).read_bytes() == original
    assert book_bytes(args) == before and loads == [True]
    assert daily.retire_expired_unstarted_daily_context(**kwargs) is True
    assert archive_path(args, old).read_bytes() == original and book_bytes(args) == before


@pytest.mark.parametrize("phase", ["reserved", "unknown", "terminal"])
def test_unrelated_stock_reservation_and_journal_are_not_released(preintent, phase):
    args, old, _ = preintent
    _, state = add_stock_owner(args, phase=phase)
    before = book_bytes(args)
    path = args["state_root"] / (state.intent.run_id + ".json")
    state_before = path.read_bytes() if path.exists() else None
    expire(args, old)
    reserved = daily.cycle._project(
        args["state_root"], book(args), args["clock"]()
    )[3].reserved_buys
    assert daily.retire_expired_unstarted_daily_context(**options(args, old)) is True
    after = daily.cycle._project(args["state_root"], book(args), args["clock"]())[3].reserved_buys
    assert after == reserved and book_bytes(args) == before
    assert (path.read_bytes() if path.exists() else None) == state_before
    if phase in {"reserved", "unknown"}:
        assert after > 0


@pytest.mark.parametrize("side", ["sell", "buy"])
def test_registered_original_seed_without_file_blocks_retirement(preintent, side):
    args, old, _ = preintent
    plan = native_plan(args, old["context"], side)
    daily.budget._atomic_json(args["state_root"] / daily.budget.BUDGET_FILE, plan.binding)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    expire(args, old)
    with pytest.raises((ValueError, daily.cycle._RecoveryRequired)):
        daily.retire_expired_unstarted_daily_context(**options(args, old))
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before
    assert not archive_path(args, old).exists()


@pytest.mark.parametrize("name", ["cycle.json", "buy.json", "sell.json", ".binding-crash.tmp"])
def test_any_native_or_unknown_cycle_entry_blocks_retirement(preintent, name):
    args, old, _ = preintent
    parent = directory(args, old)
    parent.mkdir(parents=True, exist_ok=True)
    marker = parent / name
    marker.write_text("{}", encoding="ascii")
    expire(args, old)
    before = pointer_path(args).read_bytes(), book_bytes(args), marker.read_bytes()
    with pytest.raises((ValueError, daily.cycle._RecoveryRequired)):
        daily.retire_expired_unstarted_daily_context(**options(args, old))
    assert (pointer_path(args).read_bytes(), book_bytes(args), marker.read_bytes()) == before


@pytest.mark.parametrize("kind", ["journal", "journal_lock"])
def test_exact_canonical_path_or_lock_presence_blocks_retirement(preintent, kind):
    args, old, _ = preintent
    run = sorted(daily._preintent_request_runs(old["context"])[1])[0]
    target = args["state_root"] / (run + ".json")
    if kind == "journal_lock":
        target = target.with_name("." + target.name + ".lock")
    target.write_text("{}", encoding="ascii")
    expire(args, old)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    # Freeze the expected binding before the intentionally unbound path is loaded.
    kwargs = dict(paths=old["context"]["paths"],
                  expected_account_ref=old["context"]["expected_account_ref"],
                  expected_basis_ref=old["context"]["expected_basis_ref"],
                  expected_binding_ref="sha256:" + daily.budget._digest(
                      daily.budget._read_json(args["state_root"] / daily.budget.BUDGET_FILE)),
                  expected_record_ref=old["ref"],
                  expected_pointer_sha256=hashlib.sha256(pointer_path(args).read_bytes()).hexdigest(),
                  clock=args["clock"], execute=True)
    with pytest.raises((ValueError, daily.cycle._RecoveryRequired)):
        daily.retire_expired_unstarted_daily_context(**kwargs)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before
    assert target.read_text(encoding="ascii") == "{}"


@pytest.mark.parametrize("field", ["expected_record_ref", "expected_binding_ref",
                                  "expected_basis_ref", "expected_account_ref",
                                  "expected_pointer_sha256"])
def test_stale_or_foreign_expected_identity_never_archives(preintent, field):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    kwargs[field] = "sha256:" + "0" * 64
    before = pointer_path(args).read_bytes(), book_bytes(args)
    with pytest.raises((ValueError, daily.cycle._RecoveryRequired)):
        daily.retire_expired_unstarted_daily_context(**kwargs)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


def test_active_context_is_untouched(preintent):
    args, old, _ = preintent
    before = pointer_path(args).read_bytes(), book_bytes(args)
    assert daily.retire_expired_unstarted_daily_context(**options(args, old)) is False
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


def test_tampered_existing_archive_is_not_overwritten(preintent):
    args, old, _ = preintent
    target = archive_path(args, old)
    target.parent.mkdir(parents=True)
    target.write_text("tampered", encoding="ascii")
    before = pointer_path(args).read_bytes(), book_bytes(args)
    expire(args, old)
    with pytest.raises(ValueError):
        daily.retire_expired_unstarted_daily_context(**options(args, old))
    assert target.read_text(encoding="ascii") == "tampered"
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


def test_failed_atomic_rename_keeps_original_and_book(preintent, monkeypatch):
    args, old, _ = preintent
    before = pointer_path(args).read_bytes(), book_bytes(args)
    expire(args, old)

    def unavailable(self, target):
        raise OSError("SYN_rename_failure")

    monkeypatch.setattr(daily.Path, "rename", unavailable)
    with pytest.raises(OSError):
        daily.retire_expired_unstarted_daily_context(**options(args, old))
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before
    assert not archive_path(args, old).exists()


def test_crash_after_rename_can_be_acknowledged_without_another_mutation(preintent, monkeypatch):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    original, before = pointer_path(args).read_bytes(), book_bytes(args)
    rename = daily.Path.rename

    def interrupted(path, target):
        rename(path, target)
        raise OSError("SYN_after_rename")

    with monkeypatch.context() as patch:
        patch.setattr(daily.Path, "rename", interrupted)
        with pytest.raises(OSError):
            daily.retire_expired_unstarted_daily_context(**kwargs)
    assert not pointer_path(args).exists() and archive_path(args, old).read_bytes() == original
    assert daily.retire_expired_unstarted_daily_context(**kwargs) is True
    assert book_bytes(args) == before


@pytest.mark.parametrize("field", ["binding", "pointer"])
def test_concurrent_change_before_archive_never_overwrites_other_work(
    preintent, monkeypatch, field,
):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    original = pointer_path(args).read_bytes()
    project = daily.cycle._project
    changed = []

    def mutate(root, binding, at):
        result = project(root, binding, at)
        if field == "binding":
            payload, target = copy.deepcopy(binding), root / daily.budget.BUDGET_FILE
            payload["basis_ref"] = "sha256:" + "0" * 64
        else:
            payload, target = copy.deepcopy(old), pointer_path(args)
            payload["context"]["native"]["input_ref"] = "sha256:" + "0" * 64
            payload["ref"] = "sha256:" + daily.budget._digest(
                {k: v for k, v in payload.items() if k != "ref"})
        daily.budget._atomic_json(target, payload)
        changed.append((target, target.read_bytes()))
        return result

    monkeypatch.setattr(daily.cycle, "_project", mutate)
    with pytest.raises((ValueError, daily.cycle._RecoveryRequired)):
        daily.retire_expired_unstarted_daily_context(**kwargs)
    assert changed and all(path.read_bytes() == raw for path, raw in changed)
    assert not archive_path(args, old).exists()
    if field == "binding":
        assert pointer_path(args).read_bytes() == original


def test_semantically_equal_but_byte_different_archive_is_preserved(preintent):
    args, old, _ = preintent
    target = archive_path(args, old)
    target.parent.mkdir(parents=True)
    raw = json.dumps(old, indent=2).encode("utf-8")
    target.write_bytes(raw)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    expire(args, old)
    with pytest.raises(ValueError):
        daily.retire_expired_unstarted_daily_context(**options(args, old))
    assert target.read_bytes() == raw
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


@pytest.mark.parametrize("completed", [False, True])
def test_known_cycle_pointer_is_never_retired(preintent, completed):
    args, old, _ = preintent
    retained = copy.deepcopy(old)
    retained.update(cycle_ref="sha256:" + "f" * 64, completed=completed,
                    terminal_state="complete" if completed else "active")
    retained["ref"] = "sha256:" + daily.budget._digest(
        {k: v for k, v in retained.items() if k != "ref"})
    daily.budget._atomic_json(pointer_path(args), retained)
    expire(args, old)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    assert daily.retire_expired_unstarted_daily_context(**options(args, retained)) is False
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


def test_clock_reversal_before_archive_keeps_expired_context(preintent):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    until = datetime.fromisoformat(old["context"]["valid_until"])
    times = iter([until + timedelta(seconds=1), until + timedelta(seconds=1),
                  until - timedelta(seconds=1)])
    kwargs["clock"] = lambda: next(times)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    with pytest.raises(ValueError):
        daily.retire_expired_unstarted_daily_context(**kwargs)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before
    assert not archive_path(args, old).exists()


def test_existing_identical_archive_acknowledges_duplicate_pointer(preintent):
    args, old, _ = preintent
    expire(args, old)
    raw, before = pointer_path(args).read_bytes(), book_bytes(args)
    target = archive_path(args, old)
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    assert daily.retire_expired_unstarted_daily_context(**options(args, old)) is True
    assert not pointer_path(args).exists() and target.read_bytes() == raw
    assert book_bytes(args) == before


def test_archive_only_retry_requires_original_byte_hash(preintent):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    assert daily.retire_expired_unstarted_daily_context(**kwargs) is True
    target = archive_path(args, old)
    tampered = json.dumps(old, indent=2).encode("utf-8")
    target.write_bytes(tampered)
    with pytest.raises(ValueError):
        daily.retire_expired_unstarted_daily_context(**kwargs)
    assert target.read_bytes() == tampered and not pointer_path(args).exists()


def test_redirected_public_path_rejects_original_context(preintent):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    kwargs["paths"] = dict(kwargs["paths"], emergency_state_path=str(
        args["emergency_state_path"].with_name("other-emergency.json")))
    before = pointer_path(args).read_bytes(), book_bytes(args)
    with pytest.raises(ValueError):
        daily.retire_expired_unstarted_daily_context(**kwargs)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


def test_linked_pointer_is_rejected_without_reading_target(preintent):
    args, old, _ = preintent
    expire(args, old)
    kwargs = options(args, old)
    pointer = pointer_path(args)
    original = pointer.read_bytes()
    backup = pointer.with_name("SYN_original_pointer.backup")
    backup.write_bytes(original)
    pointer.unlink()
    try:
        pointer.symlink_to(backup)
    except OSError:
        pointer.write_bytes(original)
        pytest.skip("Windows symlink privilege unavailable")
    try:
        with pytest.raises((ValueError, daily.cycle._RecoveryRequired)):
            daily.retire_expired_unstarted_daily_context(**kwargs)
        assert backup.read_bytes() == original and not archive_path(args, old).exists()
    finally:
        pointer.unlink()
        pointer.write_bytes(original)
