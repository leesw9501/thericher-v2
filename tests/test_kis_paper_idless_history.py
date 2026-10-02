from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from test_kis_paper_canary import (
    FakeKisPaperCanaryTransport,
    _config,
    _decision,
    _matching_open_order_payload,
    _paths,
)
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
    UrllibKisPaperCanaryTransport,
    reconcile_kis_paper_canary_unknown_run,
    recover_kis_paper_canary_pending_run,
    run_kis_paper_canary,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BASE_URL,
    KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    UrllibKisHttpTransport,
)
from thericher_v2.execution.paper_account_snapshot import read_paper_account_snapshot

ORDER_AT = datetime(2026, 7, 23, 1, tzinfo=UTC)
RECOVERY_AT = ORDER_AT + timedelta(days=3)
HISTORICAL_ID = "SYNTHETIC-HISTORICAL-123"
RAW_STATUS = "synthetic-raw-status-must-not-escape"


@pytest.fixture(autouse=True)
def prohibit_real_transports(monkeypatch):
    def reject(*_args, **_kwargs):
        pytest.fail("synthetic history tests must never invoke a real transport")

    monkeypatch.setattr(UrllibKisHttpTransport, "request", reject)
    monkeypatch.setattr(UrllibKisPaperCanaryTransport, "request", reject)


@dataclass
class HistoryTransport(FakeKisPaperCanaryTransport):
    history_pages: list[KisHttpResponse | KisPaperReadOnlyError] = field(default_factory=list)

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        assert request.url.startswith(KIS_PAPER_BASE_URL + "/")
        assert request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        if request.headers.get("tr_id") != KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
            return super().request(request)
        self.requests.append(request)
        assert self.history_pages, "unexpected additional history request"
        response = self.history_pages.pop(0)
        if isinstance(response, KisPaperReadOnlyError):
            raise response
        return response

    @property
    def history_requests(self) -> list[KisHttpRequest]:
        return [
            request
            for request in self.requests
            if request.headers.get("tr_id") == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id
        ]


def _row(**updates):
    return {
        "odno": HISTORICAL_ID,
        "orgn_odno": "",
        "ord_dt": "20260722",
        "pdno": "QQQ",
        "ovrs_excg_cd": "NASD",
        "sll_buy_dvsn_cd": "02",
        "tr_crcy_cd": "USD",
        "ft_ord_qty": "1",
        "ft_ord_unpr3": "500.25",
        "rvse_cncl_dvsn": "00",
        "ft_ccld_qty": "1",
        "ft_ccld_unpr3": "500.25",
        "ft_ccld_amt3": "500.25",
        "nccs_qty": "0",
        "prcs_stat_name": RAW_STATUS,
        "ord_tmd": "210000",
        **updates,
    }


def _page(rows, *, continuation="", **updates):
    payload = {"rt_cd": "0", "output": rows, **updates}
    if continuation in {"M", "F"}:
        payload.setdefault("ctx_area_fk200", "synthetic-next-fk")
        payload.setdefault("ctx_area_nk200", "synthetic-next-nk")
    return KisHttpResponse.from_payload(payload, headers={"tr_cont": continuation})


def _inspect(pages, *, side="buy", order_at=ORDER_AT):
    transport = HistoryTransport(history_pages=list(pages))
    client = KisPaperReadOnlyClient(
        config=_config(), transport=transport, access_token="synthetic-token"
    )
    observation = client.inspect_idless_order_history(
        order_at=order_at,
        symbol="QQQ",
        exchange="NASD",
        side=side,
        quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
    )
    return observation, transport


def _state(*, order_at=ORDER_AT, known_id=None, legacy=False):
    intent = KisPaperCanaryIntent.from_decision(
        _decision(decision_as_of=order_at - timedelta(minutes=2)), run_id="idless-history"
    )
    return KisPaperCanaryState(
        intent=intent,
        phase="outcome_unknown",
        updated_at=order_at + timedelta(hours=1),
        reason_code="reconciliation_unresolved",
        broker_order_id=known_id,
        submission_started_at=None if legacy else order_at,
        submitted_at=order_at if known_id and not legacy else None,
        cancel_after_submit=True,
        submit_response_category="success_order_reference_missing" if known_id is None else None,
    )


def _persist(tmp_path, state, *, legacy=False):
    path = tmp_path / "synthetic-state" / "idless-history.json"
    path.parent.mkdir(parents=True)
    payload = state.to_dict()
    if legacy:
        payload.pop("submission_started_at")
        payload.pop("submitted_at")
    path.write_text(json.dumps(payload), encoding="utf-8")
    restored = KisPaperCanaryStateStore(path).read()
    assert restored == state
    return path, restored


def _recover(tmp_path, state_path, transport, *, entrypoint="read_only", now=RECOVERY_AT):
    state = KisPaperCanaryStateStore(state_path).read()
    assert state is not None
    config = _config()
    arguments = {
        "run_id": state.intent.run_id,
        "environment": {
            "KIS_PAPER_APP_KEY": config.app_key,
            "KIS_PAPER_APP_SECRET": config.app_secret,
            "KIS_PAPER_ACCOUNT_NO": config.account_number,
            "KIS_PAPER_ACCOUNT_PRODUCT_CODE": config.account_product_code,
        },
        "state_path": state_path,
        "transport": transport,
        "now": now,
        "execution_control_path": tmp_path / "synthetic-control.json",
        **_paths(tmp_path),
    }
    if entrypoint == "read_only":
        return reconcile_kis_paper_canary_unknown_run(**arguments)
    if entrypoint == "pending":
        return recover_kis_paper_canary_pending_run(**arguments)
    assert entrypoint == "execute"
    return run_kis_paper_canary(
        decision=_decision(decision_as_of=state.intent.created_at),
        execute=True,
        cancel_after_submit=True,
        **arguments,
    )


def _assert_diagnostic_only(reconciliation, *, status, rows, candidates):
    assert reconciliation.account_status == "available"
    assert reconciliation.snapshot is not None
    assert reconciliation.snapshot.open_orders.complete
    assert reconciliation.snapshot.cash.available_cash == Decimal("1200.50")
    assert reconciliation.status == "unresolved"
    assert reconciliation.matching_open_order is False
    assert reconciliation.matching_ccnl is False
    assert reconciliation.recovered_broker_order_id is None
    assert reconciliation.execution is None
    assert reconciliation.ccnl_row_count == 0
    assert reconciliation.idless_history is not None
    assert reconciliation.idless_history.safe_payload() == {
        "status": status, "row_count": rows, "candidate_count": candidates
    }


@pytest.mark.parametrize("rows,status,candidates", [
    ([], "absent", 0),
    ([_row()], "unique", 1),
    ([_row(), _row(odno="SECOND-HISTORICAL")], "ambiguous", 2),
    ([_row(), _row()], "ambiguous", 2),
])
def test_complete_history_reports_only_candidate_counts(rows, status, candidates):
    before = [dict(row) for row in rows]
    observation, transport = _inspect([_page(rows)])
    assert observation.safe_payload() == {
        "status": status, "row_count": len(rows), "candidate_count": candidates
    }
    assert rows == before
    assert len(transport.history_requests) == 1
    assert not transport.history_pages
    assert set(vars(observation)) == {"status", "row_count", "candidate_count"}
    assert HISTORICAL_ID not in repr(observation)
    assert RAW_STATUS not in repr(observation)


@pytest.mark.parametrize("continuation", ["M", "F"])
@pytest.mark.parametrize("first,second,status,candidates", [
    ([], [], "absent", 0),
    ([], [_row()], "unique", 1),
    ([_row()], [], "unique", 1),
    ([_row()], [_row(odno="SECOND-HISTORICAL")], "ambiguous", 2),
    ([_row()], [_row()], "ambiguous", 2),
])
def test_history_finishes_all_pages_before_uniqueness(
    continuation, first, second, status, candidates,
):
    observation, transport = _inspect([
        _page(first, continuation=continuation), _page(second),
    ])
    assert observation.safe_payload() == {
        "status": status, "row_count": len(first) + len(second), "candidate_count": candidates
    }
    requests = transport.history_requests
    assert len(requests) == 2
    assert not transport.history_pages
    assert [request.headers["tr_cont"] for request in requests] == ["", "N"]
    assert requests[0].query["CTX_AREA_FK200"] == requests[0].query["CTX_AREA_NK200"] == ""
    assert requests[1].query["CTX_AREA_FK200"] == "synthetic-next-fk"
    assert requests[1].query["CTX_AREA_NK200"] == "synthetic-next-nk"
    for request in requests:
        assert request.query["ORD_STRT_DT"] == request.query["ORD_END_DT"] == "20260722"
        assert all(request.query[key] == "" for key in ("PDNO", "OVRS_EXCG_CD", "ODNO", "ORD_DT"))
        assert request.query["SLL_BUY_DVSN"] == request.query["CCLD_NCCS_DVSN"] == "00"


@pytest.mark.parametrize("field,value", [
    ("ft_ord_qty", "0.5"), ("ft_ord_qty", "2"),
    ("ft_ord_unpr3", "500.24"), ("ft_ord_unpr3", "500.26"),
    ("ord_dt", "20260723"), ("pdno", "SPY"), ("ovrs_excg_cd", "AMEX"),
    ("sll_buy_dvsn_cd", "01"), ("tr_crcy_cd", "KRW"), ("tr_crcy_cd", "EUR"),
])
def test_history_requires_exact_order_identity_quantity_and_limit(field, value):
    observation, _ = _inspect([_page([_row(**{field: value})])])
    assert observation.safe_payload() == {
        "status": "absent", "row_count": 1, "candidate_count": 0
    }


@pytest.mark.parametrize("side,code", [("buy", "02"), ("sell", "01")])
def test_side_and_numeric_equivalence_are_checked_without_inferring_fill(side, code):
    observation, _ = _inspect([_page([_row(
        sll_buy_dvsn_cd=code, ft_ord_qty="1.000", ft_ord_unpr3="500.2500",
        ft_ccld_qty="0", ft_ccld_amt3="0", nccs_qty="0",
    )])], side=side)
    assert observation.status == "unique"
    assert observation.candidate_count == 1
    assert set(observation.safe_payload()) == {"status", "row_count", "candidate_count"}


@pytest.mark.parametrize("kind,original", [
    ("01", ""), ("02", ""), ("01", HISTORICAL_ID), ("02", HISTORICAL_ID),
    ("00", HISTORICAL_ID), ("00", "000123"),
])
def test_cancel_amend_and_original_order_lineage_are_not_candidates(kind, original):
    child = _row(odno="LINEAGE-CHILD", rvse_cncl_dvsn=kind, orgn_odno=original)
    excluded, _ = _inspect([_page([child])])
    assert excluded.status == "absent"
    assert excluded.candidate_count == 0
    with_original, _ = _inspect([_page([_row()], continuation="M"), _page([child])])
    assert with_original.safe_payload() == {
        "status": "unique", "row_count": 2, "candidate_count": 1
    }


@pytest.mark.parametrize("original", ["", "0", "0000000000"])
def test_empty_or_zero_original_lineage_keeps_the_original_candidate(original):
    observation, _ = _inspect([_page([_row(orgn_odno=original)])])
    assert observation.status == "unique"
    assert observation.candidate_count == 1


@pytest.mark.parametrize("field", [
    "odno", "ord_dt", "pdno", "ovrs_excg_cd", "sll_buy_dvsn_cd", "tr_crcy_cd",
    "rvse_cncl_dvsn", "orgn_odno", "ft_ord_qty", "ft_ord_unpr3",
])
@pytest.mark.parametrize("missing", [False, True])
def test_missing_or_nonstring_identity_and_missing_numeric_fields_are_incomplete(field, missing):
    row = _row()
    if missing:
        row.pop(field)
    else:
        row[field] = None
    observation, _ = _inspect([_page([_row(), row])])
    assert observation.safe_payload() == {
        "status": "incomplete", "row_count": 0, "candidate_count": 0
    }


@pytest.mark.parametrize("field", ["rvse_cncl_dvsn", "orgn_odno"])
@pytest.mark.parametrize("value", [[], {}, True, 0], ids=["list", "dict", "bool", "int"])
def test_nonstring_revision_or_original_lineage_is_incomplete_and_keeps_account(
    tmp_path, field, value,
):
    malformed = _row(**{field: value})
    observation, _ = _inspect([_page([_row(), malformed])])
    expected = {"status": "incomplete", "row_count": 0, "candidate_count": 0}
    assert observation.safe_payload() == expected

    state_path, original = _persist(tmp_path, _state())
    transport = HistoryTransport(history_pages=[
        _page([_row()], continuation="M"), _page([malformed]),
    ])
    outcome = _recover(tmp_path, state_path, transport)
    _assert_diagnostic_only(outcome.reconciliation, status="incomplete", rows=0, candidates=0)
    assert outcome.phase == "outcome_unknown"
    assert outcome.safe_payload()["idless_history"] == expected
    assert len(transport.history_requests) == 2
    assert not transport.cancellation_seen

    restored = KisPaperCanaryStateStore(state_path).read()
    assert restored is not None
    assert restored.intent == original.intent
    assert restored.submission_started_at == original.submission_started_at
    assert restored.broker_order_id is restored.submitted_at is restored.cumulative_fill is None
    assert restored.fill_observation_status == "not_observed"
    snapshot = read_paper_account_snapshot(outcome.paper_account_snapshot_path, now=RECOVERY_AT)
    assert snapshot.status == "available"
    assert snapshot.snapshot is not None
    assert snapshot.snapshot.orderable_foreign_funds.amount == Decimal("1200.50")


@pytest.mark.parametrize("field", ["ft_ord_qty", "ft_ord_unpr3"])
@pytest.mark.parametrize("value", ["", "invalid", "NaN", "Infinity", "-1", True])
def test_invalid_candidate_numbers_do_not_allow_a_unique_partial_result(field, value):
    observation, _ = _inspect([_page([_row(), _row(**{field: value})])])
    assert observation.status == "incomplete"
    assert observation.candidate_count == 0


@pytest.mark.parametrize("field", [
    "odno", "ord_dt", "pdno", "ovrs_excg_cd", "sll_buy_dvsn_cd", "tr_crcy_cd",
    "rvse_cncl_dvsn",
])
def test_blank_required_identity_fields_do_not_allow_a_unique_partial_result(field):
    observation, _ = _inspect([_page([_row(), _row(**{field: ""})])])
    assert observation.status == "incomplete"
    assert observation.candidate_count == 0


def _broken_pages(case):
    good = _page([_row()], continuation="M")
    failures = {
        "http": KisHttpResponse.from_payload({"rt_cd": "1", "msg1": RAW_STATUS}, status_code=500),
        "rejected": KisHttpResponse.from_payload({"rt_cd": "1", "msg1": RAW_STATUS}),
        "transport": KisPaperReadOnlyError("transport_failure"),
        "json": KisHttpResponse(status_code=200, headers={}, body=b"{bad-json"),
        "missing_output": KisHttpResponse.from_payload({"rt_cd": "0"}),
        "object_output": _page(_row()),
        "string_output": _page("not-a-list"),
        "nonmapping_row": _page([None]),
        "invalid_id": _page([_row(odno="not a valid order id")]),
        "more_after_bound": _page([], continuation="M"),
        "malformed_continuation": _page([], continuation="BROKEN"),
    }
    if case in failures:
        return [good, failures[case]]
    field, form = case.split(":")
    value = {"blank": "", "nonstring": None}.get(form)
    payload = {"rt_cd": "0", "output": [_row()],
               "ctx_area_fk200": "f", "ctx_area_nk200": "n"}
    if form == "missing":
        payload.pop(field)
    else:
        payload[field] = value
    return [KisHttpResponse.from_payload(payload, headers={"tr_cont": "M"})]


BROKEN_PAGE_CASES = [
    "http", "rejected", "transport", "json", "missing_output", "object_output",
    "string_output", "nonmapping_row", "invalid_id", "more_after_bound",
    "malformed_continuation",
] + [f"{field}:{form}" for field in ("ctx_area_fk200", "ctx_area_nk200")
     for form in ("missing", "blank", "nonstring")]


@pytest.mark.parametrize("case", BROKEN_PAGE_CASES)
def test_malformed_or_partial_pagination_is_incomplete_even_after_a_matching_row(case):
    observation, transport = _inspect(_broken_pages(case))
    assert observation.safe_payload() == {
        "status": "incomplete", "row_count": 0, "candidate_count": 0
    }
    assert 1 <= len(transport.history_requests) <= 2


@pytest.mark.parametrize("order_at,expected_date", [
    (ORDER_AT, "20260722"),
    (datetime(2026, 1, 23, 1, tzinfo=UTC), "20260122"),
    (datetime(2026, 7, 23, 4, 1, tzinfo=UTC), "20260723"),
])
@pytest.mark.parametrize("entrypoint", ["read_only", "pending", "execute"])
def test_unique_historical_candidate_survives_restart_as_diagnostic_only(
    tmp_path, monkeypatch, order_at, expected_date, entrypoint,
):
    original = _state(order_at=order_at)
    state_path, _ = _persist(tmp_path, original)
    transitions = []
    transition = KisPaperCanaryStateStore.transition

    def record_transition(store, *args, **kwargs):
        transitions.append(kwargs)
        return transition(store, *args, **kwargs)

    monkeypatch.setattr(KisPaperCanaryStateStore, "transition", record_transition)
    for offset in (3, 4):
        transport = HistoryTransport(history_pages=[_page([_row(ord_dt=expected_date)])])
        outcome = _recover(
            tmp_path, state_path, transport, entrypoint=entrypoint,
            now=order_at + timedelta(days=offset),
        )
        _assert_diagnostic_only(outcome.reconciliation, status="unique", rows=1, candidates=1)
        assert outcome.phase == "outcome_unknown"
        restored = KisPaperCanaryStateStore(state_path).read()
        assert restored is not None
        assert restored.intent == original.intent
        assert restored.phase == "outcome_unknown"
        assert restored.submission_started_at == order_at
        assert restored.broker_order_id is restored.submitted_at is restored.cumulative_fill is None
        assert restored.fill_observation_status == "not_observed"
        assert restored.fill_observed_at is None
        assert len(transport.history_requests) == 1
        request = transport.history_requests[0]
        assert request.query["ORD_STRT_DT"] == request.query["ORD_END_DT"] == expected_date
        token_count = sum(
            request.url.endswith(KIS_PAPER_TOKEN_PATH) for request in transport.requests
        )
        assert token_count == 1
        assert not transport.cancellation_seen
        safe = outcome.safe_payload()
        assert safe["idless_history"] == {
            "status": "unique", "row_count": 1, "candidate_count": 1
        }
        evidence = json.loads(outcome.evidence_path.read_text(encoding="utf-8"))
        assert evidence["reconciliation"]["idless_history"] == safe["idless_history"]
        assert evidence["order_reference"] is None
        assert evidence["reconciliation"]["matching_ccnl"] is False
        snapshot = read_paper_account_snapshot(
            outcome.paper_account_snapshot_path, now=order_at + timedelta(days=offset)
        )
        assert snapshot.status == "available"
        assert snapshot.snapshot is not None
        exposed = " ".join([
            repr(outcome), json.dumps(safe), json.dumps(evidence),
            outcome.runtime_path.read_text(encoding="utf-8"),
            outcome.paper_account_snapshot_path.read_text(encoding="utf-8"),
            state_path.read_text(encoding="utf-8"),
        ])
        for forbidden in (HISTORICAL_ID, RAW_STATUS, "paper-app-key", "paper-app-secret",
                          "test-access-token", "12345678", "210000"):
            assert forbidden not in exposed
    assert transitions
    assert all(item["phase"] == "outcome_unknown" for item in transitions)
    assert all(item.get("broker_order_id") is None for item in transitions)


@pytest.mark.parametrize("case", BROKEN_PAGE_CASES)
def test_history_failure_keeps_valid_account_snapshot_and_unknown_intent(tmp_path, case):
    state_path, original = _persist(tmp_path, _state())
    transport = HistoryTransport(history_pages=_broken_pages(case))
    outcome = _recover(tmp_path, state_path, transport)
    _assert_diagnostic_only(outcome.reconciliation, status="incomplete", rows=0, candidates=0)
    assert outcome.phase == "outcome_unknown"
    restored = KisPaperCanaryStateStore(state_path).read()
    assert restored.intent == original.intent
    assert restored.broker_order_id is restored.cumulative_fill is None
    assert restored.submission_started_at == ORDER_AT
    snapshot = read_paper_account_snapshot(outcome.paper_account_snapshot_path, now=RECOVERY_AT)
    assert snapshot.status == "available"
    assert snapshot.snapshot.orderable_foreign_funds.amount == Decimal("1200.50")
    assert outcome.safe_payload()["idless_history"]["status"] == "incomplete"
    assert RAW_STATUS not in outcome.evidence_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("known_id", [None, HISTORICAL_ID])
def test_legacy_state_without_submission_timestamp_skips_history(tmp_path, known_id):
    state_path, _ = _persist(tmp_path, _state(known_id=known_id, legacy=True), legacy=True)
    transport = HistoryTransport()
    outcome = _recover(tmp_path, state_path, transport)
    reconciliation = outcome.reconciliation
    assert reconciliation.account_status == "available"
    assert reconciliation.snapshot is not None
    assert reconciliation.idless_history is None
    assert reconciliation.execution is None
    assert reconciliation.recovered_broker_order_id is None
    assert reconciliation.matching_ccnl is False
    assert transport.history_requests == []
    assert outcome.phase == "outcome_unknown"
    restored = KisPaperCanaryStateStore(state_path).read()
    assert restored.broker_order_id == known_id
    assert restored.submission_started_at is restored.submitted_at is None
    assert outcome.safe_payload()["idless_history"] is None


@pytest.mark.parametrize("raw_id,row_id", [
    (HISTORICAL_ID, HISTORICAL_ID), ("000123", "123"), ("123", "000123"),
])
def test_known_id_reconciliation_still_observes_exact_fill_without_idless_lookup(
    monkeypatch, raw_id, row_id,
):
    def reject_idless(*_args, **_kwargs):
        pytest.fail("known-ID reconciliation must not invoke ID-less history")

    monkeypatch.setattr(KisPaperReadOnlyClient, "inspect_idless_order_history", reject_idless)
    transport = HistoryTransport(history_pages=[_page([_row(odno=row_id)])])
    state = _state(known_id=raw_id)
    reconciliation = KisPaperCanaryClient(config=_config(), transport=transport).reconcile(
        state, now=RECOVERY_AT,
    )
    assert reconciliation.account_status == "available"
    assert reconciliation.status == "clean"
    assert reconciliation.matching_ccnl is True
    assert reconciliation.ccnl_row_count == 1
    assert reconciliation.idless_history is None
    assert reconciliation.recovered_broker_order_id is None
    assert reconciliation.execution.status == "available"
    assert reconciliation.execution.fill.quantity == Decimal("1")
    assert reconciliation.execution.fill.gross_amount == Decimal("500.25")
    assert reconciliation.execution.fill.status == "filled"
    assert len(transport.history_requests) == 1
    assert transport.history_requests[0].query["ORD_STRT_DT"] == "20260722"


def test_known_id_direct_and_original_lineage_remain_separate_across_pages():
    transport = HistoryTransport(history_pages=[
        _page([_row()], continuation="M"),
        _page([_row(odno="CANCEL-CHILD", orgn_odno=HISTORICAL_ID, rvse_cncl_dvsn="02",
                    ft_ccld_qty="0", ft_ccld_amt3="0", ft_ccld_unpr3="0")]),
    ])
    reconciliation = KisPaperCanaryClient(config=_config(), transport=transport).reconcile(
        _state(known_id=HISTORICAL_ID), now=RECOVERY_AT,
    )
    assert reconciliation.status == "clean"
    assert reconciliation.matching_ccnl is True
    assert reconciliation.ccnl_row_count == 2
    assert reconciliation.execution.status == "available"
    assert reconciliation.execution.fill.quantity == Decimal("1")
    assert reconciliation.execution.fill.gross_amount == Decimal("500.25")
    assert reconciliation.execution.cancellation_confirmed is False
    assert reconciliation.idless_history is None
    assert len(transport.history_requests) == 2


@pytest.mark.parametrize("entrypoint", ["direct", "read_only"])
def test_exact_open_recovery_does_not_make_an_extra_history_get(tmp_path, monkeypatch, entrypoint):
    def reject_idless(*_args, **_kwargs):
        pytest.fail("unique exact-open recovery already has an ID and must skip history")

    monkeypatch.setattr(KisPaperReadOnlyClient, "inspect_idless_order_history", reject_idless)
    state_path, state = _persist(tmp_path, _state())
    transport = HistoryTransport(order_open=True)
    if entrypoint == "direct":
        reconciliation = KisPaperCanaryClient(config=_config(), transport=transport).reconcile(
            state, now=RECOVERY_AT,
        )
    else:
        outcome = _recover(tmp_path, state_path, transport)
        reconciliation = outcome.reconciliation
        assert outcome.phase == "outcome_unknown"
        assert KisPaperCanaryStateStore(state_path).read().broker_order_id is None
    assert reconciliation.account_status == "available"
    assert reconciliation.open_order_count == 1
    assert reconciliation.recovered_broker_order_id == "ORD-123456789"
    assert reconciliation.idless_history is None
    assert reconciliation.execution is None
    assert reconciliation.matching_ccnl is False
    assert reconciliation.ccnl_row_count == 0
    assert transport.history_requests == []
    assert not transport.cancellation_seen


@pytest.mark.parametrize("open_case", ["absent", "ambiguous", "nonmatching"])
@pytest.mark.parametrize("history_case", ["absent", "unique", "ambiguous"])
def test_nonrecoverable_open_evidence_does_not_turn_history_candidates_into_recovered_ids(
    open_case, history_case,
):
    open_row = _matching_open_order_payload()
    open_rows = {
        "absent": [],
        "ambiguous": [open_row, {**open_row, "odno": "SECOND-OPEN"}],
        "nonmatching": [{**open_row, "ft_ord_unpr3": "500.26"}],
    }[open_case]
    rows = {
        "absent": [], "unique": [_row()],
        "ambiguous": [_row(), _row(odno="SECOND-HISTORICAL")],
    }[history_case]
    transport = HistoryTransport(open_order_rows=open_rows, history_pages=[_page(rows)])
    reconciliation = KisPaperCanaryClient(config=_config(), transport=transport).reconcile(
        _state(), now=RECOVERY_AT,
    )
    _assert_diagnostic_only(
        reconciliation, status=history_case, rows=len(rows), candidates=len(rows)
    )
    assert len(transport.history_requests) == 1
