from dataclasses import replace
from datetime import timedelta

import pytest

from test_kis_paper_fill_accounting import NOW, ORDER, _fill, _observe, _record, _row, _store
from test_kis_paper_spy_position import _open_order, _position, _snapshot
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryReconciliation,
    KisPaperCanaryStateStore,
    recover_kis_paper_canary_pending_run,
)
from thericher_v2.execution.kis_paper_fill_accounting import KisPaperExecutionObservation
from thericher_v2.execution.kis_readonly import KisHttpResponse, KisPaperReadOnlyError


def _rows(original=ORDER, link=ORDER, cancel="SYNTHETIC-CANCEL"):
    original_row = _row(
        odno=original, rvse_cncl_dvsn="00", ft_ccld_qty="0", ft_ccld_amt3="0",
        ft_ccld_unpr3="0", nccs_qty="0", rjct_rson="", rjct_rson_name="",
    )
    return [original_row, {**original_row, "odno": cancel, "orgn_odno": link,
                           "rvse_cncl_dvsn": "02"}]


def _pages(rows):
    return [
        KisHttpResponse.from_payload(
            {"rt_cd": "0", "output": rows[:1], "ctx_area_fk200": "f", "ctx_area_nk200": "n"},
            headers={"tr_cont": "M"},
        ),
        KisHttpResponse.from_payload({"rt_cd": "0", "output": rows[1:]}),
    ]


@pytest.mark.parametrize("raw,original,link,cancel", [
    (ORDER, ORDER, ORDER, "SYNTHETIC-CANCEL"),
    ("000123", "123", "00123", "000456"),
    ("123", "000123", "123", "456"),
])
@pytest.mark.parametrize("layout", ["same_page", "reversed", "paginated"])
@pytest.mark.parametrize("rejection_code", ["", "0", "000"])
def test_exact_full_cancel_lineage_keeps_unfilled_status(
    raw, original, link, cancel, layout, rejection_code,
):
    rows = _rows(original, link, cancel)
    for row in rows:
        row["rjct_rson"] = rejection_code
    if layout == "reversed":
        rows.reverse()
    before = [dict(row) for row in rows]
    result = _observe(rows, order_id=raw, pages=_pages(rows) if layout == "paginated" else None)
    assert result.cancellation_confirmed is True
    assert result.status == "available" and result.same_day_order_id_seen
    assert result.fill.identity_ref == _fill(order=raw).identity_ref
    assert result.fill.status == "unfilled"
    assert result.fill.quantity == result.fill.gross_amount == result.fill.remaining_quantity == 0
    assert rows == before


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("field,value", [
    ("ord_dt", "20260922"), ("pdno", "QQQ"), ("ovrs_excg_cd", "NASD"),
    ("sll_buy_dvsn_cd", "01"), ("tr_crcy_cd", "KRW"), ("rvse_cncl_dvsn", "01"),
    ("ft_ord_qty", "1"), ("ft_ord_qty", "3"), ("ft_ccld_qty", "1"),
    ("ft_ccld_amt3", "500"), ("nccs_qty", "1"), ("nccs_qty", "NaN"),
    ("rjct_rson", "REJECTED"), ("rjct_rson_name", "synthetic rejection"),
])
def test_foreign_modified_partial_or_rejected_rows_never_prove_cancel(index, field, value):
    rows = _rows()
    rows[index][field] = value
    assert _observe(rows).cancellation_confirmed is False


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("field", [
    "odno", "ord_dt", "pdno", "ovrs_excg_cd", "sll_buy_dvsn_cd", "tr_crcy_cd",
    "rvse_cncl_dvsn", "ft_ord_qty", "ft_ccld_qty", "ft_ccld_amt3", "nccs_qty",
    "rjct_rson", "rjct_rson_name",
])
@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_nonstring_required_fields_never_prove_cancel(index, field, missing):
    rows = _rows()
    if missing:
        rows[index].pop(field)
    else:
        rows[index][field] = None
    if field == "odno":
        with pytest.raises(KisPaperReadOnlyError, match="ccnl_response_incomplete"):
            _observe(rows)
    else:
        assert _observe(rows).cancellation_confirmed is False


@pytest.mark.parametrize("shape", ["original_only", "cancel_only", "duplicate_original",
                                  "duplicate_cancel", "two_cancels", "same_id", "modify"])
@pytest.mark.parametrize("paginated", [False, True])
def test_nonunique_or_missing_lineage_is_not_confirmation(shape, paginated):
    original, cancel = _rows()
    rows = {
        "original_only": [original], "cancel_only": [cancel],
        "duplicate_original": [original, original, cancel],
        "duplicate_cancel": [original, cancel, cancel],
        "two_cancels": [original, cancel, {**cancel, "odno": "SECOND-CANCEL"}],
        "same_id": [original, {**cancel, "odno": ORDER}],
        "modify": [original, cancel, {**cancel, "odno": "MODIFY", "rvse_cncl_dvsn": "01"}],
    }[shape]
    assert _observe(rows, pages=_pages(rows) if paginated else None).cancellation_confirmed is False


@pytest.mark.parametrize("link,cancel", [
    ("", "456"), ("124", "456"), (" 123", "456"), ("+123", "456"),
    ("123.0", "456"), ("0", "456"), ("00123", "000123"),
    ("00123", "0"), ("00123", "000"),
])
def test_numeric_matching_does_not_broaden_lineage_or_distinct_identity(link, cancel):
    assert _observe(_rows("123", link, cancel), order_id="000123").cancellation_confirmed is False


@pytest.mark.parametrize("failure", ["http", "missing_cursor"])
def test_complete_proof_on_first_page_cannot_bypass_incomplete_pagination(failure):
    payload = {"rt_cd": "0", "output": _rows()}
    if failure == "http":
        payload.update(ctx_area_fk200="f", ctx_area_nk200="n")
    pages = [KisHttpResponse.from_payload(payload, headers={"tr_cont": "M"}),
             KisHttpResponse.from_payload({"rt_cd": "1"}, status_code=500)]
    with pytest.raises(KisPaperReadOnlyError):
        _observe([], pages=pages)


def test_legacy_observations_and_ordinary_fills_default_to_no_confirmation():
    assert KisPaperExecutionObservation(0, False, "absent").cancellation_confirmed is False
    for row, status in [(_row(), "partial"), (_row(ft_ccld_qty="2", ft_ccld_amt3="1000",
                                                nccs_qty="0"), "filled")]:
        rows = _rows()
        rows[0].update(row)
        observation = _observe(rows)
        assert observation.cancellation_confirmed is False
        assert observation.fill.status == status


@pytest.mark.parametrize("phase", ["submitted", "cancel_started", "outcome_unknown"])
@pytest.mark.parametrize("case", ["proof", "no_proof", "open", "prior_fill", "stale",
    "foreign_fill", "absent", "same_instrument_open", "identity", "no_snapshot", "network_delay",
] + [f"{part}:{age}" for part in ("snapshot", "identity", "cash", "orderable_funds",
                                "open_orders", "position", "execution")
     for age in (-6, -5, 120, 121)])
def test_recovery_requires_fresh_exact_proof_and_current_zero_fill(tmp_path, phase, case):
    store, intent = _store(tmp_path)
    previous = _fill() if case == "prior_fill" else _fill("0", "0", remaining="0")
    _record(store, intent, previous)
    store.transition(intent, expected=frozenset({"submitted"}), phase=phase,
                     reason_code="reconciliation_unresolved", now=NOW)
    observed_at = NOW + timedelta(days=1)
    observation = _observe(_rows())
    snapshot = _snapshot(captured_at=observed_at)
    successful = case == "proof"
    if case == "no_proof":
        observation = replace(observation, cancellation_confirmed=False)
    elif case == "absent":
        observation = KisPaperExecutionObservation(0, False, "absent", observed_at=observed_at)
    elif case in {"stale", "foreign_fill"}:
        stamp = NOW - timedelta(seconds=1) if case == "stale" else observed_at
        fill = _fill("0", "0", remaining="0", observed_at=stamp,
                     order="FOREIGN-ORDER" if case == "foreign_fill" else ORDER)
        observation = replace(observation, fill=fill, observed_at=stamp)
    if case == "same_instrument_open":
        snapshot = _snapshot(captured_at=observed_at, open_orders=(
            replace(_open_order(), captured_at=observed_at, side="sell"),))
    elif case == "identity":
        identity = replace(snapshot.identity, masked_account="****9999-**")
        snapshot = replace(snapshot, identity=identity)
    elif case == "no_snapshot":
        snapshot = None
    elif ":" in case:
        part, age = case.split(":")
        stamp = observed_at - timedelta(seconds=int(age))
        successful = (0 if part == "execution" else -5) <= int(age) <= 120
        if part == "execution":
            observation = replace(observation, observed_at=stamp,
                                  fill=replace(observation.fill, observed_at=stamp))
        elif part == "position":
            snapshot = replace(snapshot, positions=(replace(_position(), captured_at=stamp),))
        elif part == "snapshot":
            snapshot = replace(snapshot, captured_at=stamp)
        else:
            component = replace(getattr(snapshot, part), captured_at=stamp)
            snapshot = replace(snapshot, **{part: component})
    calls = []
    clock = [observed_at]

    class Client:
        def reconcile(self, state, *, now):
            calls.append(state.intent)
            assert state.intent == intent and state.broker_order_id == ORDER
            if case == "network_delay":
                clock[0] = now + timedelta(seconds=121)
            return KisPaperCanaryReconciliation(
                snapshot=snapshot, account_status="available", ccnl_row_count=observation.row_count,
                matching_open_order=case == "open", matching_ccnl=True, status="clean",
                execution=observation,
            )

        def __getattr__(self, name):
            pytest.fail(f"recovery attempted a client side effect: {name}")

    outcome = recover_kis_paper_canary_pending_run(
        run_id=intent.run_id, state_path=store.path, environment={"THERICHER_MODE": "off",
            "KIS_PAPER_APP_KEY": "fake-key", "KIS_PAPER_APP_SECRET": "fake-secret",
            "KIS_PAPER_ACCOUNT_NO": "12345678", "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01"},
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json", artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo", execution_control_path=tmp_path / "control.json",
        client=Client(), clock=lambda: clock[0],
    )
    recovered = KisPaperCanaryStateStore(store.path).read()
    assert calls and recovered.intent == intent and recovered.broker_order_id == ORDER
    assert (outcome.phase == "cancelled") is successful
    assert recovered.phase == outcome.phase
    if successful:
        assert recovered.current_fill.status == "unfilled"
        assert recovered.position_contribution == recovered.gross_cashflow_contribution == 0
        assert "cancellation_confirmed" not in recovered.to_dict()
    elif case == "prior_fill":
        assert recovered.cumulative_fill == previous and recovered.current_fill is None
