from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta

import pytest

from thericher_v2.execution import kis_paper_portfolio_session_input as module
from thericher_v2.execution.kis_paper_portfolio_control_input import (
    KisPaperPortfolioControlInputBinding,
)
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

SHA = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


@pytest.fixture
def terms(tmp_path):
    start = date(2025, 1, 1)
    sessions = tuple(
        CrossAssetSession(
            start + timedelta(days=i),
            datetime(2025, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=i),
            datetime(2025, 1, 1, 21, tzinfo=UTC) + timedelta(days=i),
        )
        for i in range(253)
    )
    return dict(
        state_root=tmp_path / "synthetic-private",
        session_id="goal25-2025-09-11",
        expected_account_ref="c" * 64,
        expected_basis_ref=SHA,
        expected_owner_refs={"baseline-spy": SHA, "portfolio-tlt": OTHER},
        expected_binding_ref=SHA,
        input_binding=KisPaperPortfolioControlInputBinding(
            "data/choice-a/control.json",
            SHA,
            "data/choice-a/receipt.json",
            SHA,
            "data/parent-a.json",
            SHA,
        ),
        expected_sessions=sessions,
        engineering_helper_sha256=SHA,
        frozen_at=sessions[-1].close_at + timedelta(minutes=1),
        expected_calendar_sha256=SHA,
    )


def freeze(terms):
    return module.freeze_or_load_kis_paper_portfolio_session_input(**terms)


def checkpoint(terms):
    return next((terms["state_root"] / ".portfolio_session_inputs").glob("*.json"))


def test_a_to_b_resumes_original_custody_calendar_and_terms(terms, monkeypatch):
    original = freeze(terms)
    raw = checkpoint(terms).read_bytes()
    proposed = dict(
        terms,
        expected_owner_refs={"new-owner": OTHER},
        expected_binding_ref=OTHER,
        input_binding=replace(
            terms["input_binding"], control_relative_path="data/choice-b/control.json"
        ),
        expected_sessions=tuple(
            replace(s, open_at=s.open_at + timedelta(minutes=1)) for s in terms["expected_sessions"]
        ),
        engineering_helper_sha256=OTHER,
        expected_calendar_sha256=OTHER,
        frozen_at=terms["frozen_at"] + timedelta(days=1),
    )
    monkeypatch.setattr(
        module.budget, "_atomic_json", lambda *args: pytest.fail("no replacement write")
    )
    resumed = freeze(proposed)
    assert resumed.resumed and not original.resumed
    assert replace(resumed, resumed=False) == original
    assert checkpoint(terms).read_bytes() == raw
    assert resumed.owner_refs == terms["expected_owner_refs"]
    assert "choice-a" not in repr(resumed) and "baseline-spy" not in repr(resumed)
    safe = resumed.safe_payload()
    assert safe["session_count"] == 253 and safe["owner_count"] == 2 and safe["new_submits"] == 0
    assert SHA not in json.dumps(safe) and terms["session_id"] not in json.dumps(safe)
    with pytest.raises(TypeError):
        resumed.owner_refs["new"] = SHA
    with pytest.raises(FrozenInstanceError):
        resumed.resumed = False


def test_crash_after_checkpoint_resumes_a_without_proposal_or_extra_write(terms, monkeypatch):
    original_write = module.budget._atomic_json

    def write_then_crash(path, value):
        original_write(path, value)
        raise OSError("private path must not leak")

    monkeypatch.setattr(module.budget, "_atomic_json", write_then_crash)
    with pytest.raises(module.KisPaperPortfolioSessionInputError, match="^session_input_invalid$"):
        freeze(terms)
    raw = checkpoint(terms).read_bytes()
    monkeypatch.setattr(module.budget, "_atomic_json", lambda *args: pytest.fail("no retry write"))
    result = freeze(
        dict(
            terms,
            input_binding=None,
            expected_sessions=None,
            engineering_helper_sha256=None,
            expected_owner_refs=None,
            expected_binding_ref=None,
            frozen_at=None,
        )
    )
    assert result.resumed and result.binding == terms["input_binding"]
    assert result.sessions == terms["expected_sessions"]
    assert checkpoint(terms).read_bytes() == raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_binding", None),
        ("expected_sessions", None),
        ("engineering_helper_sha256", None),
        ("expected_owner_refs", {}),
        ("expected_binding_ref", "private-value"),
        ("expected_calendar_sha256", "invalid"),
        ("frozen_at", datetime(2025, 1, 1)),
    ],
)
def test_new_choice_missing_or_invalid_never_publishes(terms, field, value):
    with pytest.raises(module.KisPaperPortfolioSessionInputError):
        freeze(dict(terms, **{field: value}))
    assert not list((terms["state_root"] / ".portfolio_session_inputs").glob("*.json"))


@pytest.mark.parametrize(
    "field,value",
    [("session_id", "../outside"), ("expected_account_ref", SHA), ("expected_basis_ref", "a" * 64)],
)
def test_identity_format_rejected_before_any_state_write(terms, field, value):
    with pytest.raises(
        module.KisPaperPortfolioSessionInputError, match="session_input_identity_invalid"
    ):
        freeze(dict(terms, **{field: value}))
    assert not terms["state_root"].exists()


@pytest.mark.parametrize("fault", ["digest", "malformed", "duplicate", "identity", "extra"])
def test_saved_mutation_duplicate_or_spliced_identity_is_not_repaired(terms, fault):
    freeze(terms)
    path = checkpoint(terms)
    value = json.loads(path.read_bytes())
    if fault == "digest":
        value["binding_ref"] = OTHER
    elif fault == "identity":
        value["account_ref"] = "d" * 64
        value["digest"] = "sha256:" + module.budget._digest(
            {k: v for k, v in value.items() if k != "digest"}
        )
    elif fault == "extra":
        value["approval"] = True
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if fault == "malformed":
        raw = b"{"
    elif fault == "duplicate":
        raw = raw[:-1] + b',"version":1}'
    path.write_bytes(raw)
    with pytest.raises(module.KisPaperPortfolioSessionInputError):
        freeze(terms)
    assert path.read_bytes() == raw


def test_different_account_basis_session_scopes_do_not_adopt_another_checkpoint(terms):
    first = freeze(terms)
    for changes in (
        {"expected_account_ref": "d" * 64},
        {"expected_basis_ref": OTHER},
        {"session_id": "goal25-other-session"},
    ):
        other = freeze(dict(terms, **changes))
        assert not other.resumed and other.checkpoint_ref != first.checkpoint_ref
    assert len(list((terms["state_root"] / ".portfolio_session_inputs").glob("*.json"))) == 4


@pytest.mark.parametrize("slot", ["root", "checkpoint", "lock"])
def test_link_rejection_before_read_or_write(terms, monkeypatch, slot):
    if slot != "root":
        freeze(terms)
        target = checkpoint(terms)
        if slot == "lock":
            target = target.with_name("." + target.name + ".lock")
    else:
        target = terms["state_root"].absolute()
    from pathlib import Path

    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == target or original(p))
    monkeypatch.setattr(module.budget, "_read_json", lambda *args: pytest.fail("no linked read"))
    monkeypatch.setattr(module.budget, "_atomic_json", lambda *args: pytest.fail("no linked write"))
    with pytest.raises(module.KisPaperPortfolioSessionInputError, match="^session_input_invalid$"):
        freeze(terms)


def test_native_lock_is_held_for_read_publication_and_readback(terms, monkeypatch):
    from contextlib import contextmanager

    held, writes = [], []
    real_read, real_write = module.budget._read_json, module.budget._atomic_json

    @contextmanager
    def lock(path):
        held.append(path)
        try:
            yield
        finally:
            held.pop()

    def read(path):
        assert held == [path]
        return real_read(path)

    def write(path, value):
        assert held == [path]
        writes.append(path)
        real_write(path, value)

    monkeypatch.setattr(module, "exclusive_kis_paper_canary_state_lock", lock)
    monkeypatch.setattr(module.budget, "_read_json", read)
    monkeypatch.setattr(module.budget, "_atomic_json", write)
    freeze(terms)
    assert freeze(terms).resumed
    assert len(writes) == 1 and not held


def test_none_calendar_pin_uses_native_selected253_geometry(terms):
    result = freeze(dict(terms, expected_calendar_sha256=None))
    expected = module.control._sha(
        module.control._encode(
            [
                dict(
                    date=s.session_date.isoformat(),
                    open_at=s.open_at.isoformat().replace("+00:00", "Z"),
                    close_at=s.close_at.isoformat().replace("+00:00", "Z"),
                )
                for s in terms["expected_sessions"]
            ]
        )
    )
    assert result.expected_calendar_sha256 == expected and expected != SHA
    assert freeze(dict(terms, expected_calendar_sha256=OTHER)).expected_calendar_sha256 == expected
