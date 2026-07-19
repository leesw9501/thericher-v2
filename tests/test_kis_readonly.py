from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_READ_ONLY_ENDPOINTS,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperDiscoveryOutcome,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    UrllibKisHttpTransport,
    load_kis_paper_config,
    reconcile_kis_paper_readonly,
    run_kis_paper_readonly_discovery,
    write_kis_paper_readonly_evidence,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@dataclass
class FakeKisTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    reject_balance: bool = False
    reject_open_orders: bool = False
    partial_open_orders: bool = False
    open_order_exchange: str = "NASD"
    paginated_open_orders: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        if request.method == "POST":
            return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
        tr_id = request.headers["tr_id"]
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            if self.reject_open_orders:
                return KisHttpResponse.from_payload(
                    {
                        "rt_cd": "1",
                        "msg_cd": "mock-server-code-should-not-persist",
                        "msg1": "must-not-persist-free-text",
                    },
                    status_code=403,
                )
            if self.partial_open_orders:
                return KisHttpResponse.from_payload(
                    {"rt_cd": "0", "output": []},
                    headers={"tr_cont": "M"},
                )
            if self.paginated_open_orders:
                if request.headers["tr_cont"] == "":
                    return KisHttpResponse.from_payload(
                        {
                            "rt_cd": "0",
                            "output": [_open_order_payload(exchange="NASD")],
                            "ctx_area_fk200": "next-fk",
                            "ctx_area_nk200": "next-nk",
                        },
                        headers={"tr_cont": "M"},
                    )
                return KisHttpResponse.from_payload(
                    {
                        "rt_cd": "0",
                        "output": [
                            _open_order_payload(
                                exchange="NYSE",
                                order_number="ORD-123456790",
                            )
                        ],
                    }
                )
            exchange = request.query["OVRS_EXCG_CD"]
            rows = (
                [_open_order_payload(exchange=self.open_order_exchange)]
                if exchange == "NASD"
                else []
            )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": rows})
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            if self.reject_balance:
                return KisHttpResponse.from_payload({"rt_cd": "1"})
            exchange = request.query["OVRS_EXCG_CD"]
            rows = [_position_payload()] if exchange == "NASD" else []
            return KisHttpResponse.from_payload({"rt_cd": "0", "output1": rows})
        if tr_id == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1200.50",
                        "ovrs_ord_psbl_amt": "1199.75",
                    },
                }
            )
        raise AssertionError("unexpected KIS request")


def test_requires_the_exact_virtual_paper_host_before_any_network(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("rejected host must not reach the network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    invalid_request = KisHttpRequest(
        method="GET",
        url="https://openapi.koreainvestment.com:9443/uapi/overseas-stock/v1/trading/inquire-balance",
        headers={"tr_id": KIS_PAPER_BALANCE_ENDPOINT.tr_id, "authorization": "Bearer test"},
        query={key: "test" for key in KIS_PAPER_BALANCE_ENDPOINT.query_keys},
    )

    with pytest.raises(KisPaperReadOnlyError, match="paper_host_required"):
        UrllibKisHttpTransport().request(invalid_request)
    with pytest.raises(KisPaperReadOnlyError, match="paper_host_required"):
        KisPaperConfig(
            "test-app-key",
            "test-app-secret",
            "12345678",
            "01",
            base_url="https://openapi.koreainvestment.com:9443",
        )


def test_transport_rejects_non_allowlisted_requests_before_network(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("non-allowlisted requests must not reach the network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    transport = UrllibKisHttpTransport()
    requests = (
        KisHttpRequest(
            method="GET",
            url=(
                "https://openapivts.koreainvestment.com:29443"
                "/uapi/overseas-stock/v1/trading/not-allowlisted"
            ),
            headers={"tr_id": "VTTS3012R", "authorization": "Bearer test"},
        ),
        KisHttpRequest(
            method="POST",
            url="https://openapivts.koreainvestment.com:29443/oauth2/tokenP",
            headers={"content-type": "application/json", "accept": "application/json"},
            json_body={
                "grant_type": "client_credentials",
                "appkey": "test",
                "appsecret": "test",
                "unexpected": "value",
            },
        ),
    )

    for request in requests:
        with pytest.raises(KisPaperReadOnlyError, match="request_not_allowlisted"):
            transport.request(request)


def test_config_reads_only_authorized_values_and_blank_config_fails_closed(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dotenv_path = repo_root / ".env"
    dotenv_path.write_text(
        "TIINGO_API_TOKEN=must-not-be-used\n"
        "KIS_LIVE_APP_KEY=must-not-be-used\n"
        "KIS_PAPER_APP_KEY=\n"
        "KIS_PAPER_APP_SECRET=test-app-secret\n"
        "KIS_PAPER_ACCOUNT_NO=12345678\n"
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE=01\n",
        encoding="utf-8",
    )
    transport = FakeKisTransport()

    with pytest.raises(KisPaperReadOnlyError, match="config_missing"):
        load_kis_paper_config(dotenv_path)
    outcome, evidence_path = run_kis_paper_readonly_discovery(
        dotenv_path=dotenv_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=repo_root,
        transport=transport,
    )

    assert outcome.status == "failed_closed"
    assert outcome.reason_code == "config_missing"
    assert transport.requests == []
    assert evidence_path.is_file()
    evidence = evidence_path.read_text(encoding="utf-8")
    assert "must-not-be-used" not in evidence
    assert "12345678" not in evidence


def test_read_only_snapshot_uses_fixed_allowlisted_requests_with_injected_transport(
    monkeypatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("injected transport must make this test network-free")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    transport = FakeKisTransport()
    client = KisPaperReadOnlyClient(config=_config(), transport=transport)

    snapshot = client.snapshot()

    assert len(transport.requests) == 6
    assert transport.requests[0].method == "POST"
    assert transport.requests[0].headers == {
        "content-type": "application/json",
        "accept": "application/json",
    }
    assert all(request.method == "GET" for request in transport.requests[1:])
    assert [request.headers["tr_id"] for request in transport.requests[1:]] == [
        KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id,
    ]
    assert {request.url for request in transport.requests[1:]} == {
        "https://openapivts.koreainvestment.com:29443"
        "/uapi/overseas-stock/v1/trading/inquire-balance",
        "https://openapivts.koreainvestment.com:29443"
        "/uapi/overseas-stock/v1/trading/inquire-psamount",
        "https://openapivts.koreainvestment.com:29443"
        "/uapi/overseas-stock/v1/trading/inquire-nccs",
    }
    assert transport.requests[1].query["OVRS_EXCG_CD"] == "NASD"
    assert transport.requests[1].headers["tr_cont"] == ""
    assert all(request.headers["tr_cont"] == "" for request in transport.requests[2:])
    assert snapshot.identity.masked_account == "****5678-**"
    assert snapshot.cash.available_cash == Decimal("1200.50")
    assert snapshot.orderable_funds.orderable_funds == Decimal("1199.75")
    assert snapshot.positions == (
        KisPaperPosition(
            symbol="SPY",
            exchange="NASD",
            currency="USD",
            quantity=Decimal("2"),
            average_price=Decimal("500"),
            market_price=Decimal("510"),
            captured_at=snapshot.captured_at,
        ),
    )
    assert snapshot.open_orders.complete is True
    assert snapshot.open_orders.orders == (
        KisPaperOpenOrder(
            order_reference=snapshot.open_orders.orders[0].order_reference,
            symbol="SPY",
            exchange="NASD",
            currency="USD",
            side="buy",
            requested_quantity=Decimal("5"),
            filled_quantity=Decimal("2"),
            remaining_quantity=Decimal("3"),
            limit_price=Decimal("510"),
            captured_at=snapshot.captured_at,
        ),
    )
    assert snapshot.open_orders.orders[0].order_reference.startswith("open-")


def test_no_order_tr_ids_or_actions_are_reachable() -> None:
    public_actions = {"submit_order", "cancel_order", "modify_order", "order_status"}
    source = Path(kis_readonly.__file__).read_text(encoding="utf-8")

    assert not public_actions & set(vars(KisPaperReadOnlyClient))
    assert {endpoint.tr_id for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS} == {
        "VTTS3012R",
        "VTTS3007R",
        "VTTS3018R",
    }
    assert all(
        endpoint.path.startswith("/uapi/overseas-stock/v1/trading/inquire-")
        for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS
    )
    assert "VTTT" not in source
    assert "order-rvsecncl" not in source
    assert '"/uapi/overseas-stock/v1/trading/order"' not in source


def test_masked_evidence_excludes_credentials_and_raw_account_and_stays_external(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dotenv_path = repo_root / ".env"
    dotenv_path.write_text(
        "KIS_PAPER_APP_KEY=app-key-value\n"
        "KIS_PAPER_APP_SECRET=super-secret-value\n"
        "KIS_PAPER_ACCOUNT_NO=12345678\n"
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE=01\n",
        encoding="utf-8",
    )

    outcome, evidence_path = run_kis_paper_readonly_discovery(
        dotenv_path=dotenv_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=repo_root,
        transport=FakeKisTransport(),
    )

    assert outcome.status == "collected"
    assert outcome.reconciliation is not None
    assert outcome.reconciliation.safe_to_submit is False
    assert outcome.reconciliation.reasons == ("read_only_boundary",)
    assert evidence_path.is_file()
    assert evidence_path.is_relative_to(tmp_path / "artifacts")
    assert not evidence_path.is_relative_to(repo_root)
    evidence = evidence_path.read_text(encoding="utf-8")
    assert "app-key-value" not in evidence
    assert "super-secret-value" not in evidence
    assert "12345678" not in evidence
    assert "ORD-123456789" not in evidence
    assert "****5678-**" in evidence
    assert json.loads(evidence)["submit_capability"] is False


def test_reconciliation_remains_typed_and_fail_closed_on_currency_mismatch() -> None:
    snapshot = _snapshot(cash_currency="USD", orderable_currency="KRW")

    reconciliation = reconcile_kis_paper_readonly(snapshot, reconciled_at=NOW)

    assert reconciliation.safe_to_submit is False
    assert set(reconciliation.reasons) == {
        "read_only_boundary",
        "cash_orderable_currency_mismatch",
    }


def test_rejected_response_writes_only_a_non_secret_fail_closed_outcome(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dotenv_path = repo_root / ".env"
    dotenv_path.write_text(
        "KIS_PAPER_APP_KEY=app-key-value\n"
        "KIS_PAPER_APP_SECRET=super-secret-value\n"
        "KIS_PAPER_ACCOUNT_NO=12345678\n"
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE=01\n",
        encoding="utf-8",
    )

    outcome, evidence_path = run_kis_paper_readonly_discovery(
        dotenv_path=dotenv_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=repo_root,
        transport=FakeKisTransport(reject_balance=True),
    )

    assert outcome.status == "failed_closed"
    assert outcome.reason_code == "balance_rejected"
    assert outcome.snapshot is None
    assert outcome.reconciliation is None
    evidence = evidence_path.read_text(encoding="utf-8")
    assert "super-secret-value" not in evidence
    assert "12345678" not in evidence
    assert "snapshot" not in evidence


@pytest.mark.parametrize(
    ("transport", "reason_code"),
    (
        (FakeKisTransport(reject_open_orders=True), "open_orders_rejected"),
        (FakeKisTransport(partial_open_orders=True), "open_orders_response_incomplete"),
    ),
    ids=("rejected", "partial"),
)
def test_open_order_evidence_rejection_or_partial_response_fails_closed(
    tmp_path,
    transport: FakeKisTransport,
    reason_code: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dotenv_path = repo_root / ".env"
    dotenv_path.write_text(
        "KIS_PAPER_APP_KEY=app-key-value\n"
        "KIS_PAPER_APP_SECRET=super-secret-value\n"
        "KIS_PAPER_ACCOUNT_NO=12345678\n"
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE=01\n",
        encoding="utf-8",
    )

    outcome, evidence_path = run_kis_paper_readonly_discovery(
        dotenv_path=dotenv_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=repo_root,
        transport=transport,
    )

    assert outcome.status == "failed_closed"
    assert outcome.reason_code == reason_code
    assert outcome.snapshot is None
    assert outcome.reconciliation is None
    assert [request.headers.get("tr_id") for request in transport.requests[1:]] == [
        KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id
    ]
    evidence = evidence_path.read_text(encoding="utf-8")
    assert "super-secret-value" not in evidence
    assert "12345678" not in evidence
    assert "snapshot" not in evidence
    if reason_code == "open_orders_rejected":
        assert json.loads(evidence)["diagnostic"] == {
            "endpoint": "open_orders",
            "tr_id": KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
            "http_status": "403",
        }
        assert "must-not-persist-free-text" not in evidence
        assert "mock-server-code-should-not-persist" not in evidence


@pytest.mark.parametrize("exchange", ("NASD", "NYSE", "AMEX"))
def test_nasd_open_order_query_accepts_documented_us_wide_rows(exchange: str) -> None:
    transport = FakeKisTransport(open_order_exchange=exchange)

    snapshot = KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert snapshot.open_orders.orders[0].exchange == exchange
    open_order_requests = [
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id
    ]
    assert len(open_order_requests) == 1
    assert open_order_requests[0].query["OVRS_EXCG_CD"] == "NASD"
    assert open_order_requests[0].headers["tr_cont"] == ""


def test_nasd_open_order_query_preserves_mixed_rows_and_continuation() -> None:
    transport = FakeKisTransport(paginated_open_orders=True)

    snapshot = KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert {order.exchange for order in snapshot.open_orders.orders} == {"NASD", "NYSE"}
    open_order_requests = [
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id
    ]
    assert len(open_order_requests) == 2
    assert open_order_requests[0].headers["tr_cont"] == ""
    assert open_order_requests[0].query["CTX_AREA_FK200"] == ""
    assert open_order_requests[0].query["CTX_AREA_NK200"] == ""
    assert open_order_requests[1].headers["tr_cont"] == "N"
    assert open_order_requests[1].query["CTX_AREA_FK200"] == "next-fk"
    assert open_order_requests[1].query["CTX_AREA_NK200"] == "next-nk"


def test_evidence_root_inside_repository_is_rejected() -> None:
    outcome = KisPaperDiscoveryOutcome(
        status="failed_closed",
        reason_code="config_missing",
        captured_at=NOW,
    )
    repository_root = Path.cwd()

    with pytest.raises(KisPaperReadOnlyError, match="artifact_root_inside_repository"):
        write_kis_paper_readonly_evidence(
            outcome,
            artifact_root=repository_root / "model-artifacts",
            repository_root=repository_root,
        )


def test_failure_diagnostics_reject_unallowlisted_fields_or_mismatched_request_identity() -> None:
    with pytest.raises(ValueError, match="allowlisted string mapping"):
        KisPaperDiscoveryOutcome(
            status="failed_closed",
            reason_code="open_orders_rejected",
            captured_at=NOW,
            diagnostic={
                "endpoint": "open_orders",
                "tr_id": KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
                "http_status": "403",
                "opaque_server_value": "tokenlike-response-value",
            },
        )
    with pytest.raises(ValueError, match="allowlisted endpoint"):
        KisPaperDiscoveryOutcome(
            status="failed_closed",
            reason_code="open_orders_rejected",
            captured_at=NOW,
            diagnostic={
                "endpoint": "open_orders",
                "tr_id": KIS_PAPER_BALANCE_ENDPOINT.tr_id,
                "http_status": "403",
            },
        )


def _config() -> KisPaperConfig:
    return KisPaperConfig(
        app_key="test-app-key",
        app_secret="test-app-secret",
        account_number="12345678",
        account_product_code="01",
    )


def _position_payload() -> dict[str, str]:
    return {
        "ovrs_pdno": "SPY",
        "ovrs_excg_cd": "NASD",
        "tr_crcy_cd": "USD",
        "ovrs_cblc_qty": "2",
        "pchs_avg_pric": "500",
        "now_pric2": "510",
    }


def _open_order_payload(
    *,
    exchange: str = "NASD",
    order_number: str = "ORD-123456789",
) -> dict[str, str]:
    return {
        "odno": order_number,
        "pdno": "SPY",
        "ovrs_excg_cd": exchange,
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "5",
        "ft_ccld_qty": "2",
        "nccs_qty": "3",
        "ft_ord_unpr3": "510",
    }


def _snapshot(*, cash_currency: str, orderable_currency: str) -> KisPaperReadOnlySnapshot:
    return KisPaperReadOnlySnapshot(
        identity=KisPaperAccountIdentity("****5678-**", NOW),
        cash=KisPaperCashSnapshot(cash_currency, Decimal("1000"), NOW),
        orderable_funds=KisPaperOrderableFundsSnapshot(
            currency=orderable_currency,
            orderable_funds=Decimal("900"),
            reference_exchange="NASD",
            reference_symbol="SPY",
            reference_price=Decimal("1"),
            captured_at=NOW,
        ),
        positions=(),
        open_orders=KisPaperOpenOrdersSnapshot((), NOW),
        captured_at=NOW,
    )
