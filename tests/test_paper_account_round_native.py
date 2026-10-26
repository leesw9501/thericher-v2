"""Real native journal -> progress handoff, with invented custody and no wire."""

from datetime import timedelta

import pytest

import test_kis_paper_current_stock_cycle as native
from test_kis_paper_current_stock_cycle import (
    NativeSyntheticStockClient,
    budget,
    kis_readonly,
    record,
    run,
)
from thericher_v2.execution.paper_account_round import (
    PaperCohortProgress,
    PaperRoundSlot,
    run_cohort_progress,
)

ADAPTER = "sha256:" + "a" * 64


@pytest.fixture
def h(tmp_path):
    return native.h.__wrapped__(tmp_path)


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    native.no_actual_calls.__wrapped__(monkeypatch)


def native_progress(h, *, completed=0, max_visits=2):
    data = h["data"]
    frozen = tuple(t.proposal.symbol for t in data.targets)
    item = PaperRoundSlot(
        "invented-native-cohort", "entry", data.entry_session.open_ts,
        data.entry_session.close_ts, data.input_ref, data.policy_ref,
    )

    def invoke(original, cursor, deadline):
        assert original == item and h["now"] < deadline <= item.ends_at
        before = record(h)
        if before is not None:
            assert before["active"]["entries_done"] == list(frozen[:cursor])
        outcome = run(h, expected_input_ref=item.input_ref, expected_policy_ref=item.policy_ref)
        after = record(h)
        assert after["policy_ref"] == item.policy_ref
        assert after["active"]["input_ref"] == item.input_ref
        done = after["active"]["entries_done"]
        assert done == list(frozen[:len(done)])
        pending = after["pending"] is not None
        return PaperCohortProgress(
            item, ADAPTER, cursor, len(done), outcome.status,
            outcome.status in {"advanced", "no_intent"} and not pending, pending,
        )

    return run_cohort_progress(
        item, adapter_ref=ADAPTER, work_units=len(frozen), completed=completed,
        clock=lambda: h["now"], monotonic=lambda: 0.0, invoke_original_target=invoke,
        max_visits=max_visits, wall_seconds=300,
    )


def test_actual_native_quote_skip_advances_to_original_second_target(h, monkeypatch):
    first, second = h["data"].targets[:2]
    original = NativeSyntheticStockClient.stock_preview_snapshot

    def preview(client, **arguments):
        if client.instrument.symbol == first.proposal.symbol:
            raise kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")
        return original(client, **arguments)

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", preview)
    result = native_progress(h)
    assert result["completed_after"] == 2 and result["invocations"] == 2
    assert result["status"] == "cohort_visit_limit"
    assert len(h["submits"]) == 1 and h["submits"][0].symbol == second.proposal.symbol
    assert not result["broker_acceptance_fill_inventory_PnL_proved"]


def test_actual_native_unknown_submit_stops_with_exact_pending_reservation(h):
    h["unknown"] = True
    result = native_progress(h)
    assert result["status"] == "stopped_for_exact_reconciliation"
    assert result["invocations"] == 1 and result["completed_after"] == 0
    assert len(h["submits"]) == 1 and record(h)["pending"] is not None
    assert result["outer_debits"] == 0


def test_actual_native_all_quote_skips_traverse_without_new_debit_or_orders(h, monkeypatch):
    def missing(*_args, **_kwargs):
        raise kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", missing)
    before = (h["root"] / budget.BUDGET_FILE).read_bytes()
    result = native_progress(h, max_visits=10)
    assert result["status"] == "traversal_complete_not_fill_evidence"
    assert result["invocations"] == result["completed_after"] == 10
    assert not h["submits"] and not h["cancels"]
    assert (h["root"] / budget.BUDGET_FILE).read_bytes() == before
    assert record(h)["pending"] is None


def test_actual_native_restart_uses_persisted_prefix_not_loader_or_target_zero(h, monkeypatch):
    def missing(*_args, **_kwargs):
        raise kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(NativeSyntheticStockClient, "stock_preview_snapshot", missing)
    first = native_progress(h, max_visits=1)
    assert first["completed_after"] == 1
    h["call"]["target_loader"] = lambda: pytest.fail("must_use_original_persisted_basket")
    h["now"] += timedelta(seconds=1)
    second = native_progress(h, completed=1, max_visits=1)
    assert second["completed_before"] == 1 and second["completed_after"] == 2
    assert h["loads"] == 1 and not h["submits"]
