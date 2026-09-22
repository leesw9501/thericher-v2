from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryReconciliation,
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
    recover_kis_paper_canary_pending_run,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BASE_URL,
    KisHttpResponse,
    KisPaperConfig,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
)

NOW = datetime(2026, 9, 21, 19, tzinfo=UTC)
ORDER = "SYNTHETIC-123"


def _fill(quantity="1", amount="500", *, observed_at=NOW, order=ORDER):
    return KisPaperCumulativeFill(
        identity_ref=fill_identity_ref(
            raw_order_id=order,
            order_at=NOW,
            symbol="SPY",
            exchange="AMEX",
            side="buy",
            quantity=Decimal("2"),
        ),
        requested_quantity=Decimal("2"),
        quantity=Decimal(quantity),
        gross_amount=Decimal(amount),
        observed_at=observed_at,
    )


def _row(**updates):
    return {
        "odno": ORDER,
        "orgn_odno": "",
        "ord_dt": "20260921",
        "pdno": "SPY",
        "ovrs_excg_cd": "AMEX",
        "sll_buy_dvsn_cd": "02",
        "tr_crcy_cd": "USD",
        "ft_ord_qty": "2",
        "ft_ccld_qty": "1",
        "ft_ccld_amt3": "500",
        "ft_ccld_unpr3": "500",
        "nccs_qty": "1",
        **updates,
    }


def _observe(rows, *, pages=None):
    requests = []

    class Transport:
        def request(self, request):
            requests.append(request)
            assert request.method == "GET"
            assert request.url.startswith(KIS_PAPER_BASE_URL + "/")
            assert request.query["ORD_STRT_DT"] == request.query["ORD_END_DT"] == "20260921"
            if pages is not None:
                return pages.pop(0)
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": rows})

    client = KisPaperReadOnlyClient(
        config=KisPaperConfig("fake-key", "fake-secret", "12345678", "01"),
        access_token="fake-token",
        transport=Transport(),
    )
    result = client.observe_order_execution(
        ORDER,
        order_at=NOW,
        observed_at=NOW + timedelta(days=1),
        symbol="SPY",
        exchange="AMEX",
        side="buy",
        quantity=Decimal("2"),
    )
    assert len(requests) >= 1
    return result


def _store(tmp_path):
    intent = KisPaperCanaryIntent(
        run_id="synthetic-fill",
        client_order_id="canary-synthetic-fill",
        decision_id="synthetic-fill",
        symbol="SPY",
        exchange="AMEX",
        side="buy",
        quantity=Decimal("2"),
        limit_price=Decimal("501"),
        created_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
    )
    store = KisPaperCanaryStateStore(tmp_path / "private" / "fill.json")
    store.record_intent(intent, cancel_after_submit=False, now=NOW)
    store.transition(
        intent,
        expected=frozenset({"intent_recorded"}),
        phase="submission_started",
        reason_code="reconciliation_unresolved",
        now=NOW,
        submission_started_at=NOW,
    )
    store.transition(
        intent,
        expected=frozenset({"submission_started"}),
        phase="submitted",
        reason_code="reconciliation_unresolved",
        now=NOW,
        submitted_at=NOW,
        broker_order_id=ORDER,
    )
    return store, intent


def _record(store, intent, fill):
    return store.record_fill_observation(
        intent,
        KisPaperExecutionObservation(1, True, "available", fill),
        now=fill.observed_at,
    )


def test_exact_history_bound_to_original_date_and_amount():
    observation = _observe([_row()])
    assert observation.status == "available"
    assert observation.fill.quantity == 1
    assert observation.fill.gross_amount == 500
    assert observation.fill.status == "partial"
    assert "500" not in repr(observation)
    assert ORDER not in repr(observation)


@pytest.mark.parametrize(
    "updates",
    [
        {"ord_dt": "20260922"},
        {"pdno": "QQQ"},
        {"ovrs_excg_cd": "NASD"},
        {"sll_buy_dvsn_cd": "01"},
        {"tr_crcy_cd": "KRW"},
    ],
)
def test_identity_conflicts_are_not_fills(updates):
    result = _observe([_row(**updates)])
    assert result.status == "identity_mismatch"
    assert result.same_day_order_id_seen and result.fill is None


@pytest.mark.parametrize(
    "updates",
    [
        {"ft_ord_qty": "3"},
        {"ft_ccld_qty": "-1"},
        {"ft_ccld_amt3": "NaN"},
        {"ft_ccld_qty": "0"},
        {"nccs_qty": "2"},
        {"ft_ccld_unpr3": "0"},
        {"ft_ccld_amt3": "50000"},
        {"ft_ccld_qty": "0.5"},
        {"ft_ccld_amt3": ""},
    ],
)
def test_invalid_or_wrong_unit_amount_is_not_accounted(updates):
    result = _observe([_row(**updates)])
    assert result.status == "fields_invalid"
    assert result.fill is None


def test_zero_remaining_does_not_imply_a_fill():
    result = _observe([_row(ft_ccld_qty="0", ft_ccld_amt3="0", nccs_qty="0")])
    assert result.fill.status == "unfilled"


def test_duplicate_rows_and_lineage_never_get_summed():
    assert _observe([_row(), _row()]).status == "ambiguous"
    lineage = _row(odno="SYNTHETIC-456", orgn_odno=ORDER)
    assert _observe([lineage]).status == "absent"
    assert _observe([_row(), lineage]).fill.quantity == 1


def test_all_pages_are_completed_before_accepting_exact_row():
    first = KisHttpResponse.from_payload(
        {"rt_cd": "0", "output": [_row()], "ctx_area_fk200": "f", "ctx_area_nk200": "n"},
        headers={"tr_cont": "M"},
    )
    duplicate = KisHttpResponse.from_payload({"rt_cd": "0", "output": [_row()]})
    assert _observe([], pages=[first, duplicate]).status == "ambiguous"
    failed = KisHttpResponse.from_payload({"rt_cd": "1"}, status_code=500)
    with pytest.raises(KisPaperReadOnlyError):
        _observe([], pages=[first, failed])


def test_restart_duplicate_partial_full_and_transition_preserve_totals(tmp_path):
    store, intent = _store(tmp_path)
    first = _record(store, intent, _fill())
    assert first.position_contribution == 1
    assert first.gross_cashflow_contribution == -500
    store = KisPaperCanaryStateStore(store.path)
    duplicate = _record(store, intent, _fill(observed_at=NOW + timedelta(seconds=1)))
    assert duplicate.position_contribution == 1
    assert duplicate.gross_cashflow_contribution == -500
    full = _record(store, intent, _fill("2", "1001", observed_at=NOW + timedelta(seconds=2)))
    assert full.current_fill.status == "filled"
    assert full.position_contribution == 2 and full.gross_cashflow_contribution == -1001
    later = store.transition(
        intent,
        expected=frozenset({"submitted"}),
        phase="cancelled",
        reason_code="reconciliation_clean",
        now=NOW + timedelta(seconds=3),
    )
    assert later.cumulative_fill == full.cumulative_fill
    assert KisPaperCanaryState.from_dict(later.to_dict()) == later


@pytest.mark.parametrize(
    "fill",
    [
        _fill("0", "0"),
        _fill("1", "501"),
        _fill("2", "499"),
        _fill(observed_at=NOW - timedelta(seconds=1)),
        _fill(order="OTHER-123"),
    ],
)
def test_conflict_preserves_prior_but_cannot_look_current(tmp_path, fill):
    store, intent = _store(tmp_path)
    original = _record(store, intent, _fill())
    result = _record(store, intent, fill)
    assert result.fill_observation_status == "conflict"
    assert result.cumulative_fill == original.cumulative_fill
    assert result.current_fill is result.position_contribution is None
    assert result.gross_cashflow_contribution is None


def test_absent_row_preserves_historical_totals_without_current_claim(tmp_path):
    store, intent = _store(tmp_path)
    original = _record(store, intent, _fill())
    absent = store.record_fill_observation(
        intent,
        KisPaperExecutionObservation(0, False, "absent"),
        now=NOW + timedelta(days=1),
    )
    assert absent.cumulative_fill == original.cumulative_fill
    assert absent.current_fill is None


def test_new_order_cannot_reuse_other_intent_or_fill(tmp_path):
    store, intent = _store(tmp_path)
    other = replace(intent, run_id="other-intent", client_order_id="canary-other-intent")
    with pytest.raises(KisPaperCanaryError, match="state_intent_mismatch"):
        _record(store, other, _fill())
    assert _record(store, intent, _fill(order="OTHER-123")).fill_observation_status == "conflict"


def test_legacy_state_without_fill_fields_still_loads(tmp_path):
    store, _ = _store(tmp_path)
    payload = store.read().to_dict()
    for key in ("cumulative_fill", "fill_observation_status", "fill_observed_at"):
        payload.pop(key)
    legacy = KisPaperCanaryState.from_dict(payload)
    assert legacy.current_fill is None and legacy.fill_observation_status == "not_observed"


def test_local_paper_and_tampered_fill_payloads_rejected():
    payload = _fill().to_dict()
    payload["source"] = "local_paper"
    with pytest.raises(ValueError):
        KisPaperCumulativeFill.from_dict(payload)


def test_sell_contributions_are_signed_without_inventing_fees(tmp_path):
    store, _ = _store(tmp_path)
    buy = _record(store, store.read().intent, _fill())
    sell_intent = replace(buy.intent, side="sell")
    sell_fill = replace(
        buy.current_fill,
        identity_ref=fill_identity_ref(
            raw_order_id=ORDER,
            order_at=NOW,
            symbol="SPY",
            exchange="AMEX",
            side="sell",
            quantity=Decimal("2"),
        ),
    )
    sell = replace(buy, intent=sell_intent, cumulative_fill=sell_fill)
    assert sell.position_contribution == -1
    assert sell.gross_cashflow_contribution == 500
    assert "fee" not in sell_fill.to_dict() and "net_pnl" not in sell_fill.to_dict()


def test_recovery_preserves_first_fill_before_requery_regresses(tmp_path):
    store, intent = _store(tmp_path)
    # Resume an exact order after a lost cancellation response.
    state = replace(store.read(), phase="outcome_unknown", cancel_after_submit=True)
    store.path.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    class Client:
        calls = 0

        def reconcile(self, state, *, now):
            self.calls += 1
            fill = _fill() if self.calls == 1 else _fill("0", "0")
            return KisPaperCanaryReconciliation(
                snapshot=None,
                account_status="available",
                ccnl_row_count=1,
                matching_open_order=self.calls == 1,
                matching_ccnl=True,
                status="clean",
                execution=KisPaperExecutionObservation(1, True, "available", fill),
            )

    client = Client()
    recover_kis_paper_canary_pending_run(
        run_id=intent.run_id,
        environment={"THERICHER_MODE": "off"},
        state_path=store.path,
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        client=client,
        now=NOW,
        execution_control_path=tmp_path / "control.json",
    )
    assert client.calls == 2
    recovered = store.read()
    assert recovered.cumulative_fill.quantity == 1
    assert recovered.cumulative_fill.gross_amount == 500
    assert recovered.fill_observation_status == "conflict"
    assert recovered.current_fill is None
