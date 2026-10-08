from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, create_autospec

import pytest

from thericher_v2.execution import kis_paper_owned_portfolio_session as module
from thericher_v2.execution.kis_paper_portfolio_control_input import (
    KisPaperPortfolioControlInputBinding,
    KisPaperPortfolioControlInputError,
)
from thericher_v2.execution.kis_paper_portfolio_session_input import (
    KisPaperPortfolioSessionInput,
    KisPaperPortfolioSessionInputError,
)
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

SHA = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
OLD_CALENDAR = "sha256:" + "c" * 64
NOW = datetime(2026, 1, 5, 16, tzinfo=UTC)


def input_binding(label, pin):
    return KisPaperPortfolioControlInputBinding(
        f"data/synthetic-{label}/control.json",
        pin,
        f"data/synthetic-{label}/receipt.json",
        pin,
        f"data/synthetic-parent-{label}.json",
        pin,
    )


def loaded(label, target_at):
    symbols = ("SPY", "TLT", "GLD")
    return SimpleNamespace(
        input_ref=SHA if label == "A" else OTHER,
        control_ref=OLD_CALENDAR if label == "A" else OTHER,
        target_as_of=target_at,
        weights_by_symbol={s: Decimal(".1") for s in symbols},
        covariance_by_symbol={
            s: {t: Decimal(".01") if s == t else Decimal(0) for t in symbols} for s in symbols
        },
        reattest=Mock(return_value=True),
        safe_payload=Mock(return_value=dict(status="bound", synthetic_input=label)),
    )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    # An invented ordered schedule, not an assertion about an exchange calendar.
    start = date(2025, 4, 26)
    past = tuple(
        CrossAssetSession(
            start + timedelta(days=i),
            datetime(2025, 4, 26, 14, 30, tzinfo=UTC) + timedelta(days=i),
            datetime(2025, 4, 26, 21, tzinfo=UTC) + timedelta(days=i),
        )
        for i in range(254)
    )
    session = CrossAssetSession(
        date(2026, 1, 5),
        datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 5, 21, tzinfo=UTC),
    )
    future = CrossAssetSession(
        date(2026, 1, 6),
        datetime(2026, 1, 6, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 6, 21, tzinfo=UTC),
    )
    events = []
    config = SimpleNamespace(
        base_url="https://paper.invalid",
        account_number="synthetic",
        account_product_code="test-only",
    )

    class Client:
        config_reads = 0

        @property
        def _config(self):
            self.config_reads += 1
            return config

        def __getattr__(self, name):
            pytest.fail("No client operation is allowed in this synthetic test")

    client = Client()
    account = module.budget._digest(
        [config.base_url, config.account_number, config.account_product_code]
    )
    binding = dict(version=3, legacy_spy=None, basis_ref=SHA, synthetic_version="current")
    owners = [(SimpleNamespace(owner_ref="current-owner"), OTHER)]
    current_refs = {owner.owner_ref: ref for owner, ref in owners}
    a, b = input_binding("A", SHA), input_binding("B", OTHER)
    saved = KisPaperPortfolioSessionInput(
        binding=a,
        sessions=past[:253],
        helper_sha256=SHA,
        expected_calendar_sha256=OLD_CALENDAR,
        frozen_at=NOW - timedelta(minutes=1),
        session_id="synthetic-session",
        account_ref=account,
        basis_ref=SHA,
        owner_refs={"retained-owner": OLD_CALENDAR},
        binding_ref=SHA,
        checkpoint_ref=OLD_CALENDAR,
        resumed=True,
    )
    inputs = {a: loaded("A", past[252].close_at), b: loaded("B", past[-1].close_at)}
    preview_result = SimpleNamespace(
        safe_payload=Mock(return_value=dict(status="preview_ready", new_submits=0))
    )
    cycle_result = SimpleNamespace(
        safe_payload=Mock(return_value=dict(status="cycle_ready", new_submits=0))
    )
    reads, states = Mock(return_value=object()), Mock(return_value=object())
    clock = Mock(return_value=NOW)

    def choose(**kwargs):
        if kwargs["input_binding"] is None:
            events.append("lookup")
            raise KisPaperPortfolioSessionInputError("session_input_missing")
        events.append("freeze_B")
        return KisPaperPortfolioSessionInput(
            binding=kwargs["input_binding"],
            sessions=kwargs["expected_sessions"],
            helper_sha256=kwargs["engineering_helper_sha256"],
            expected_calendar_sha256=kwargs.get("expected_calendar_sha256", OTHER),
            frozen_at=kwargs["frozen_at"],
            session_id=kwargs["session_id"],
            account_ref=kwargs["expected_account_ref"],
            basis_ref=kwargs["expected_basis_ref"],
            owner_refs=dict(kwargs["expected_owner_refs"]),
            binding_ref=kwargs["expected_binding_ref"],
            checkpoint_ref=OTHER,
            resumed=False,
        )

    def load(**kwargs):
        selected = kwargs["binding"]
        events.append("load_A" if selected == a else "load_B")
        return inputs[selected]

    def advance(**kwargs):
        events.append("advance")
        kwargs["reads_factory"]()
        return cycle_result

    choice = create_autospec(
        module.freeze_or_load_kis_paper_portfolio_session_input, side_effect=choose
    )
    loader = create_autospec(module.load_kis_paper_portfolio_control_input, side_effect=load)
    binding_reader, owner_reader = Mock(return_value=binding), Mock(return_value=owners)
    advance_mock = Mock(side_effect=advance)
    preview = Mock(return_value=preview_result)
    monkeypatch.setattr(module.budget, "_load_binding", binding_reader)
    monkeypatch.setattr(module.budget, "_owners", owner_reader)
    monkeypatch.setattr(module, "freeze_or_load_kis_paper_portfolio_session_input", choice)
    monkeypatch.setattr(module, "load_kis_paper_portfolio_control_input", loader)
    monkeypatch.setattr(module, "advance_kis_paper_portfolio_cycle", advance_mock)
    monkeypatch.setattr(module, "project_kis_paper_portfolio_preview", preview)
    kwargs = dict(
        state_root=tmp_path / "never-created-state",
        repository_root=tmp_path / "synthetic-repo",
        artifact_root=tmp_path / "synthetic-A",
        market_root=tmp_path / "synthetic-M",
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "snapshot.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "off",
        client=client,
        proposed_input=b,
        calendar_sessions=past + (session, future),
        expected_calendar_sha256=OTHER,
        session=session,
        session_id="synthetic-session",
        engineering_control=Mock(name="synthetic_helper"),
        engineering_helper_sha256=OTHER,
        reads_factory=reads,
        states_factory=states,
        clock=clock,
    )
    return SimpleNamespace(
        kwargs=kwargs,
        past=past,
        session=session,
        client=client,
        account=account,
        binding=binding,
        current_refs=current_refs,
        a=a,
        b=b,
        saved=saved,
        inputs=inputs,
        choice=choice,
        loader=loader,
        reads=reads,
        states=states,
        clock=clock,
        binding_reader=binding_reader,
        owner_reader=owner_reader,
        advance=advance_mock,
        preview=preview,
        events=events,
    )


def visit(harness, **overrides):
    return module.visit_kis_paper_owned_portfolio_session(**(harness.kwargs | overrides))


def assert_no_input_or_cycle(h):
    h.loader.assert_not_called()
    h.choice.assert_not_called()
    h.reads.assert_not_called()
    h.states.assert_not_called()
    h.advance.assert_not_called()
    h.preview.assert_not_called()


@pytest.mark.parametrize("boundary", ["before_open", "exact_close"])
def test_closed_execute_stops_before_custody_input_or_any_read(harness, boundary):
    h = harness
    h.clock.return_value = (
        h.session.open_at - timedelta(microseconds=1)
        if boundary == "before_open"
        else h.session.close_at
    )
    assert visit(h, execute=True) == dict(
        status="not_due", reason="outside_owned_regular_session", new_submits=0
    )
    assert h.client.config_reads == 0
    h.binding_reader.assert_not_called()
    h.owner_reader.assert_not_called()
    assert_no_input_or_cycle(h)


def test_default_preview_is_read_only_and_never_chooses_or_advances(harness):
    h = harness
    result = visit(h)
    assert result["status"] == "preview_ready" and result["read_only"] is True
    assert result["input"]["synthetic_input"] == "B"
    h.choice.assert_not_called()
    h.advance.assert_not_called()
    h.reads.assert_called_once_with()
    h.states.assert_called_once_with(h.binding)
    h.preview.assert_called_once()
    assert h.loader.call_args.kwargs["expected_sessions"] == h.past[-253:]
    assert h.loader.call_args.kwargs["expected_calendar_sha256"] == OTHER
    assert h.inputs[h.b].reattest.call_count == 2
    assert not h.kwargs["state_root"].exists()


def test_resume_a_ignores_b_preserves_old_custody_and_no_replacement(harness):
    h = harness
    h.choice.side_effect = None
    h.choice.return_value = h.saved
    result = visit(h, execute=True)
    assert result["input"]["synthetic_input"] == "A" and result["read_only"] is False
    h.choice.assert_called_once()
    assert h.choice.call_args.kwargs["input_binding"] is None
    h.loader.assert_called_once()
    request = h.advance.call_args.kwargs
    assert request["expected_account_ref"] == h.saved.account_ref
    assert request["expected_basis_ref"] == h.saved.basis_ref
    assert request["expected_owner_refs"] == h.saved.owner_refs != h.current_refs
    assert request["expected_binding_ref"] == h.saved.binding_ref
    assert request["input_ref"] == h.inputs[h.a].input_ref
    assert request["control_ref"] == h.inputs[h.a].control_ref
    assert request["target_as_of"] == h.inputs[h.a].target_as_of
    h.inputs[h.b].reattest.assert_not_called()
    h.states.assert_not_called()


def test_resume_uses_saved_window_helper_fullcalendar_not_latest_head(harness):
    h = harness
    h.choice.side_effect = None
    h.choice.return_value = h.saved
    visit(h, execute=True)
    args = h.loader.call_args.kwargs
    assert args["binding"] is h.a
    assert args["expected_sessions"] == h.saved.sessions != h.past[-253:]
    assert args["engineering_helper_sha256"] == SHA
    assert args["expected_calendar_sha256"] == OLD_CALENDAR != OTHER
    assert args["decision_at"] == NOW
    assert args["engineering_control"] is h.kwargs["engineering_control"]


def test_valid_first_input_loaded_before_freeze_then_reloaded_before_cycle(harness):
    h = harness
    result = visit(h, execute=True)
    assert h.events == ["lookup", "load_B", "freeze_B", "load_B", "advance"]
    assert result["checkpoint"]["resumed"] is False
    freeze_args = h.choice.call_args_list[1].kwargs
    assert freeze_args["input_binding"] is h.b
    assert freeze_args["expected_sessions"] == h.past[-253:]
    assert freeze_args["expected_calendar_sha256"] == OTHER
    assert freeze_args["expected_owner_refs"] == h.current_refs
    assert h.loader.call_count == 2 and h.reads.call_count == 1
    assert not h.kwargs["state_root"].exists()


@pytest.mark.parametrize("reason", ["bytes_changed", "helper_changed"])
def test_first_invalid_proposed_input_cannot_freeze_or_advance(harness, reason):
    h = harness
    h.loader.side_effect = KisPaperPortfolioControlInputError(reason)
    with pytest.raises(KisPaperPortfolioControlInputError, match=reason):
        visit(h, execute=True)
    h.choice.assert_called_once()
    assert h.choice.call_args.kwargs["input_binding"] is None
    h.advance.assert_not_called()
    h.reads.assert_not_called()


def test_race_writer_a_wins_and_must_reload_a_not_proposed_b(harness):
    h = harness
    h.choice.side_effect = [KisPaperPortfolioSessionInputError("session_input_missing"), h.saved]
    result = visit(h, execute=True)
    assert [c.kwargs["binding"] for c in h.loader.call_args_list] == [h.b, h.a]
    assert result["input"]["synthetic_input"] == "A"
    assert h.advance.call_args.kwargs["expected_owner_refs"] == h.saved.owner_refs
    assert h.advance.call_args.kwargs["expected_binding_ref"] == h.saved.binding_ref
    assert h.advance.call_args.kwargs["input_ref"] == h.inputs[h.a].input_ref
    h.inputs[h.b].reattest.assert_called_once_with()


def test_existing_checkpoint_loader_failure_never_chooses_replacement(harness):
    h = harness
    h.choice.side_effect = None
    h.choice.return_value = h.saved
    h.loader.side_effect = KisPaperPortfolioControlInputError("helper_changed")
    with pytest.raises(KisPaperPortfolioControlInputError, match="helper_changed"):
        visit(h, execute=True)
    h.choice.assert_called_once()
    h.advance.assert_not_called()
    h.reads.assert_not_called()


def test_checkpoint_integrity_error_is_not_missing_or_fresh_choice(harness):
    h = harness
    h.choice.side_effect = KisPaperPortfolioSessionInputError("session_input_digest_invalid")
    with pytest.raises(KisPaperPortfolioSessionInputError, match="session_input_digest_invalid"):
        visit(h, execute=True)
    h.choice.assert_called_once()
    h.loader.assert_not_called()
    h.advance.assert_not_called()
    h.reads.assert_not_called()


def test_existing_input_hash_change_before_cycle_no_advance_or_reads(harness):
    h = harness
    h.choice.side_effect = None
    h.choice.return_value = h.saved
    h.inputs[h.a].reattest.return_value = False
    with pytest.raises(ValueError, match="^session_input_changed$"):
        visit(h, execute=True)
    h.advance.assert_not_called()
    h.reads.assert_not_called()


def test_hash_change_at_cycle_read_callback_stops_actual_reads(harness):
    h = harness
    h.choice.side_effect = None
    h.choice.return_value = h.saved
    h.inputs[h.a].reattest.side_effect = [True, False]
    with pytest.raises(ValueError, match="^session_input_changed$"):
        visit(h, execute=True)
    h.advance.assert_called_once()
    h.reads.assert_not_called()


def test_preview_detects_post_read_hash_change_without_choice_or_advance(harness):
    h = harness
    h.inputs[h.b].reattest.side_effect = [True, False]
    with pytest.raises(ValueError, match="^session_input_changed$"):
        visit(h)
    h.reads.assert_called_once()
    h.choice.assert_not_called()
    h.advance.assert_not_called()


def test_invalid_custody_stops_input_and_cycle(harness):
    h = harness
    h.binding_reader.return_value = dict(version=2, legacy_spy=None, basis_ref=SHA)
    with pytest.raises(ValueError, match="^session_custody_unavailable$"):
        visit(h, execute=True)
    assert_no_input_or_cycle(h)


def test_non_boolean_execute_stops_before_clock_or_any_read(harness):
    h = harness
    with pytest.raises(ValueError, match="^session_execute_invalid$"):
        visit(h, execute=1)
    h.clock.assert_not_called()
    assert_no_input_or_cycle(h)


def test_closed_default_preview_allows_read_only_reads_without_freeze_or_advance(harness):
    h = harness
    h.clock.return_value = h.session.close_at
    result = visit(h)
    assert result["status"] == "preview_ready" and result["read_only"] is True
    assert result["new_submits"] == 0
    assert result["input"]["synthetic_input"] == "B"
    h.reads.assert_called_once_with()
    assert h.client.config_reads == 1
    h.binding_reader.assert_called_once()
    h.loader.assert_called_once()
    h.states.assert_called_once_with(h.binding)
    h.preview.assert_called_once()
    h.choice.assert_not_called()
    h.advance.assert_not_called()
    assert not h.kwargs["state_root"].exists()


def test_first_input_changed_after_load_must_not_publish_checkpoint(harness):
    h = harness
    h.inputs[h.b].reattest.return_value = False
    with pytest.raises(ValueError, match="^session_input_changed$"):
        visit(h, execute=True)
    # The only allowed choice call is the read-only lookup. No first-choice freeze.
    assert h.choice.call_count == 1
    assert h.choice.call_args.kwargs["input_binding"] is None
    h.advance.assert_not_called()
    h.reads.assert_not_called()
