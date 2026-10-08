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
    KIS_PAPER_BASE_URL,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_READ_ONLY_ENDPOINTS,
    KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
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
    load_kis_paper_config_from_environment,
    reconcile_kis_paper_readonly,
    run_kis_paper_readonly_discovery,
    write_kis_paper_readonly_evidence,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@dataclass
class FakeKisTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    reject_balance: bool = False
    balance_failure_code: object | None = None
    balance_failure_message: str = "must-not-persist-free-text"
    paginated_balance: bool = False
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
                payload: dict[str, object] = {
                    "rt_cd": "1",
                    "msg1": self.balance_failure_message,
                }
                if self.balance_failure_code is not None:
                    payload["msg_cd"] = self.balance_failure_code
                return KisHttpResponse.from_payload(payload, status_code=500)
            exchange = request.query["OVRS_EXCG_CD"]
            if self.paginated_balance and exchange == "NASD":
                if request.headers["tr_cont"] == "":
                    return KisHttpResponse.from_payload(
                        {
                            "rt_cd": "0",
                            "output1": [_position_payload()],
                            "ctx_area_fk200": "balance-next-fk",
                            "ctx_area_nk200": "balance-next-nk",
                        },
                        headers={"tr_cont": "M"},
                    )
                return KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
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


@dataclass
class ScriptedBalanceTransport(FakeKisTransport):
    balance_pages: dict[str, list[KisHttpResponse | KisPaperReadOnlyError]] = field(
        default_factory=dict
    )

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        if request.headers.get("tr_id") != KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return super().request(request)
        self.requests.append(request)
        pages = self.balance_pages.get(request.query["OVRS_EXCG_CD"])
        if pages is None:
            return _balance_page([])
        assert pages, "unexpected additional balance page"
        response = pages.pop(0)
        if isinstance(response, KisPaperReadOnlyError):
            raise response
        return response


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
    sleep_calls: list[float] = []
    transport = UrllibKisHttpTransport(sleeper=sleep_calls.append)
    open_calls: list[object] = []

    class FailingOpener:
        def open(self, request: object, *, timeout: float) -> None:
            open_calls.append(request)
            raise AssertionError(f"non-allowlisted request reached opener with timeout {timeout}")

    monkeypatch.setattr(transport, "_opener", FailingOpener())
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
    assert sleep_calls == []
    assert open_calls == []


def test_real_transport_paces_only_valid_external_requests(monkeypatch) -> None:
    current_time = [100.0]
    sleep_calls: list[float] = []
    dispatch_times: list[float] = []

    def monotonic_clock() -> float:
        return current_time[0]

    def sleeper(delay: float) -> None:
        sleep_calls.append(delay)
        current_time[0] += delay

    class Response:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"test-token"}'

    class RecordingOpener:
        def open(self, _request: object, *, timeout: float) -> Response:
            assert timeout == 15.0
            dispatch_times.append(monotonic_clock())
            return Response()

    transport = UrllibKisHttpTransport(
        monotonic_clock=monotonic_clock,
        sleeper=sleeper,
    )
    monkeypatch.setattr(transport, "_opener", RecordingOpener())
    request = KisHttpRequest(
        method="POST",
        url=f"{KIS_PAPER_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
        headers={"content-type": "application/json", "accept": "application/json"},
        json_body={
            "grant_type": "client_credentials",
            "appkey": "test-app-key",
            "appsecret": "test-app-secret",
        },
    )

    transport.request(request)
    transport.request(request)
    transport.request(request)

    assert dispatch_times == [100.0, 101.0, 102.0]
    assert sleep_calls == [1.0, 1.0]


def test_real_transport_paces_after_a_failed_external_attempt(monkeypatch) -> None:
    current_time = [50.0]
    sleep_calls: list[float] = []
    dispatch_times: list[float] = []

    def monotonic_clock() -> float:
        return current_time[0]

    def sleeper(delay: float) -> None:
        sleep_calls.append(delay)
        current_time[0] += delay

    class Response:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"test-token"}'

    class FirstAttemptFails:
        attempts = 0

        def open(self, _request: object, *, timeout: float) -> Response:
            assert timeout == 15.0
            self.attempts += 1
            dispatch_times.append(monotonic_clock())
            if self.attempts == 1:
                raise urllib.error.URLError("temporary-test-failure")
            return Response()

    transport = UrllibKisHttpTransport(
        monotonic_clock=monotonic_clock,
        sleeper=sleeper,
    )
    monkeypatch.setattr(transport, "_opener", FirstAttemptFails())
    request = KisHttpRequest(
        method="POST",
        url=f"{KIS_PAPER_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
        headers={"content-type": "application/json", "accept": "application/json"},
        json_body={
            "grant_type": "client_credentials",
            "appkey": "test-app-key",
            "appsecret": "test-app-secret",
        },
    )

    with pytest.raises(KisPaperReadOnlyError, match="transport_failure"):
        transport.request(request)
    transport.request(request)

    assert dispatch_times == [50.0, 51.0]
    assert sleep_calls == [1.0]


@pytest.fixture
def guarded_paper_config_reader(tmp_path, monkeypatch):
    def install(payload):
        path = tmp_path / "paper.env"
        path.write_bytes(payload)
        keys, values, offset = set(), set(), 0
        for line in payload.splitlines(keepends=True):
            body = line.rstrip(b"\r\n")
            separator = body.find(b"=")
            keys.add((offset, offset + (separator if separator >= 0 else len(body))))
            if separator >= 0:
                try:
                    key = body[:separator].decode("utf-8").strip()
                except UnicodeDecodeError:
                    key = ""
                if key.startswith("export "):
                    key = key[len("export ") :].lstrip()
                if key in kis_readonly.KIS_PAPER_ENV_KEYS:
                    values.add((offset + separator + 1, offset + len(body)))
            offset += len(line)
        slices, value_decodes, closed = [], [], []
        original_open = Path.open

        class KeyOnlyFile:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.handle.close()

            def fileno(self):
                return self.handle.fileno()

            def __iter__(self):
                raise AssertionError("whole-line iteration is forbidden")

            def read(self, *_args):
                raise AssertionError("whole-file reads are forbidden")

            def readline(self, *_args):
                raise AssertionError("whole-line reads are forbidden")

        def guarded_open(actual_path, *args, **kwargs):
            assert actual_path == path and args == ("rb",) and kwargs == {"buffering": 0}
            return KeyOnlyFile(original_open(actual_path, *args, **kwargs))

        class FakeMMap:
            def __init__(self, _fileno, length, *, access):
                assert length == 0 and access == kis_readonly.mmap.ACCESS_READ

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                closed.append(True)

            def __len__(self):
                return len(payload)

            def find(self, needle, start=0, end=None):
                assert needle in {b"\r", b"\n", b"="}
                return payload.find(needle, start, len(payload) if end is None else end)

            def __getitem__(self, span):
                assert isinstance(span, slice) and span.step is None
                bounds = span.start, span.stop
                assert bounds in keys | values, "slice touched an unapproved value"
                slices.append(bounds)

                class CheckedBytes(bytes):
                    def decode(self, encoding="utf-8", errors="strict"):
                        assert encoding == "utf-8" and errors == "strict"
                        if bounds in values:
                            value_decodes.append(bounds)
                        return super().decode(encoding, errors)

                return CheckedBytes(payload[span])

        monkeypatch.setattr(Path, "open", guarded_open)
        monkeypatch.setattr(kis_readonly.mmap, "mmap", FakeMMap)
        return path, values, slices, value_decodes, closed

    return install


@pytest.mark.parametrize("newline", (b"\n", b"\r\n", b"\r"))
@pytest.mark.parametrize("final_newline", (False, True))
def test_file_config_materializes_only_the_four_paper_values(
    guarded_paper_config_reader, monkeypatch, newline, final_newline
):
    payload = newline.join(
        (
            b"KIS_LIVE_APP_KEY=forbidden-live-before\xff",
            b"KIS_PAPER_APP_KE=forbidden-short-prefix\xfe",
            b"KIS_PAPER_APP_KEY_EXTRA=forbidden-long-prefix\xff",
            b"OTHER=KIS_PAPER_APP_KEY=forbidden-decoy\xfe",
            b"# KIS_PAPER_APP_KEY=forbidden-comment\xff",
            b"export\tKIS_PAPER_APP_KEY=forbidden-export-grammar\xfe",
            b"\xff=forbidden-invalid-key-value\xff",
            b" \texport  KIS_PAPER_APP_KEY \t= 'test-app-key' ",
            b'KIS_PAPER_APP_SECRET="test-app-secret"',
            b"KIS_PAPER_ACCOUNT_NO=12345678",
            b"KIS_PAPER_ACCOUNT_PRODUCT_CODE=01",
            b"KIS_LIVE_APP_SECRET=forbidden-live-after\xff",
            b"KIS_PAPER_UNAPPROVED=forbidden-paper-after\xfe",
            b"TIINGO_API_TOKEN=forbidden-token\xff",
        )
    ) + (newline if final_newline else b"")
    path, values, slices, decodes, closed = guarded_paper_config_reader(payload)
    monkeypatch.setattr(kis_readonly.os, "environ", {})

    config = load_kis_paper_config(path)

    assert config.app_key == "test-app-key" and config.app_secret == "test-app-secret"
    assert config.masked_account_identity == "****5678-**"
    assert len(decodes) == 4 and set(decodes) == values
    assert all(span in slices for span in decodes) and closed == [True]


@pytest.mark.parametrize(
    ("assignment", "expected"),
    (
        (b"KIS_PAPER_APP_KEY=x=y==z", "x=y==z"),
        (b"KIS_PAPER_APP_KEY=literal#not-comment", "literal#not-comment"),
        (b"KIS_PAPER_APP_KEY=\t' spaced '\t", "spaced"),
        (b'KIS_PAPER_APP_KEY="unmatched', '"unmatched'),
        (b"KIS_PAPER_APP_KEY=\xce\xb1", "\u03b1"),
        (b"\xc2\xa0export \tKIS_PAPER_APP_KEY\xc2\xa0=key\xc2\xa0", "key"),
    ),
)
def test_file_config_preserves_value_export_and_whitespace_grammar(
    guarded_paper_config_reader, assignment, expected
):
    payload = assignment + (
        b"\r\nKIS_PAPER_APP_SECRET=secret\rKIS_PAPER_ACCOUNT_NO=12345678\n"
        b"KIS_PAPER_ACCOUNT_PRODUCT_CODE=01"
    )
    path, values, _, decodes, closed = guarded_paper_config_reader(payload)
    assert load_kis_paper_config(path).app_key == expected
    assert set(decodes) == values and closed == [True]


@pytest.mark.parametrize(
    ("payload", "reason", "decoded_count"),
    (
        (b"", "config_missing", 0),
        (b"KIS_LIVE_APP_KEY=\xff\rOTHER=\xfe", "config_missing", 0),
        (b"KIS_PAPER_APP_KEY", "config_missing", 0),
        (b"KIS_PAPER_APP_KEY= \t", "config_missing", 1),
        (b"KIS_PAPER_APP_KEY=' '", "config_missing", 1),
        (b"KIS_PAPER_APP_KEY=\xff", "config_missing", 1),
        (
            b"KIS_PAPER_APP_KEY\rKIS_LIVE_APP_KEY=\xff\nKIS_PAPER_APP_KEY=\xfe",
            "config_duplicate",
            0,
        ),
    ),
)
def test_file_config_missing_empty_invalid_and_no_equals_duplicate_are_categorical(
    guarded_paper_config_reader, payload, reason, decoded_count
):
    path, _, _, decodes, closed = guarded_paper_config_reader(payload)
    with pytest.raises(KisPaperReadOnlyError, match=f"^{reason}$") as error:
        load_kis_paper_config(path)
    assert len(decodes) == decoded_count
    assert closed == ([True] if payload else [])
    if error.value.__context__ is not None:
        assert error.value.__suppress_context__


@pytest.mark.parametrize("key", kis_readonly.KIS_PAPER_ENV_KEYS)
def test_file_config_rejects_each_duplicate_before_copying_its_second_value(
    guarded_paper_config_reader, key
):
    payload = f"{key}=first\r\n export {key} =".encode("ascii") + b"\xff"
    path, _, _, decodes, closed = guarded_paper_config_reader(payload)
    with pytest.raises(KisPaperReadOnlyError, match="^config_duplicate$"):
        load_kis_paper_config(path)
    assert len(decodes) == 1 and closed == [True]


@pytest.mark.parametrize("empty_file", (False, True))
def test_file_config_does_not_fall_back_to_environment(tmp_path, monkeypatch, empty_file):
    path = tmp_path / "paper.env"
    if empty_file:
        path.write_bytes(b"")
    monkeypatch.setattr(
        kis_readonly.os, "environ", dict.fromkeys(kis_readonly.KIS_PAPER_ENV_KEYS, "present")
    )
    with pytest.raises(KisPaperReadOnlyError, match="^config_missing$"):
        load_kis_paper_config(path)


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


def test_environment_config_reads_only_the_four_paper_values() -> None:
    class PaperOnlyEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            assert key.startswith("KIS_PAPER_")
            return super().get(key, default)

    config = load_kis_paper_config_from_environment(
        PaperOnlyEnvironment(
            {
                "KIS_PAPER_APP_KEY": "test-app-key",
                "KIS_PAPER_APP_SECRET": "test-app-secret",
                "KIS_PAPER_ACCOUNT_NO": "12345678",
                "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
                "KIS_LIVE_APP_KEY": "must-not-be-read",
            }
        )
    )

    assert config.masked_account_identity == "****5678-**"


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
        "https://openapivts.koreainvestment.com:29443/uapi/overseas-stock/v1/trading/inquire-nccs",
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


def test_virtual_balance_request_contract_covers_initial_and_continuation_pages(
    monkeypatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("injected transport must make this test network-free")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    transport = FakeKisTransport(paginated_balance=True)

    KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    balance_url = (
        "https://openapivts.koreainvestment.com:29443"
        "/uapi/overseas-stock/v1/trading/inquire-balance"
    )
    balance_requests = [request for request in transport.requests if request.url == balance_url]

    assert [request.method for request in balance_requests] == ["GET"] * 4
    assert [request.headers["tr_id"] for request in balance_requests] == ["VTTS3012R"] * 4
    assert [request.headers["custtype"] for request in balance_requests] == ["P"] * 4
    assert [request.query["OVRS_EXCG_CD"] for request in balance_requests] == [
        "NASD",
        "NASD",
        "NYSE",
        "AMEX",
    ]
    assert [request.headers["tr_cont"] for request in balance_requests] == [
        "",
        "N",
        "",
        "",
    ]
    assert balance_requests[0].query == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }
    assert balance_requests[1].query == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "balance-next-fk",
        "CTX_AREA_NK200": "balance-next-nk",
    }
    for request, exchange in zip(balance_requests[2:], ("NYSE", "AMEX"), strict=True):
        assert request.query == {
            "CANO": "12345678",
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": exchange,
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }


def test_balance_cross_scope_rows_keep_reported_venues_and_all_query_routes() -> None:
    nasdaq = _position_payload() | {"ovrs_pdno": "QQQ"}
    amex = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    transport = ScriptedBalanceTransport(balance_pages={"NASD": [_balance_page([nasdaq, amex])]})

    snapshot = KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert [(p.exchange, p.symbol) for p in snapshot.positions] == [
        ("AMEX", "SPY"), ("NASD", "QQQ"),
    ]
    assert all(p.quantity == 2 and p.currency == "USD" for p in snapshot.positions)
    assert [
        request.query["OVRS_EXCG_CD"] for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_BALANCE_ENDPOINT.tr_id
    ] == ["NASD", "NYSE", "AMEX"]
    assert transport.requests[-1].headers["tr_id"] == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id


@pytest.mark.parametrize("continued", [False, True])
def test_identical_typed_positions_coalesce_only_across_completed_queries(continued) -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    equivalent = row | {"ovrs_cblc_qty": "2.0", "pchs_avg_pric": "500.00"}
    nasdaq_pages = (
        [_balance_page([], continued=True), _balance_page([row])]
        if continued else [_balance_page([row])]
    )
    transport = ScriptedBalanceTransport(balance_pages={
        "NASD": nasdaq_pages,
        "NYSE": [_balance_page([equivalent])],
        "AMEX": [_balance_page([row])],
    })

    snapshot = KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert len(snapshot.positions) == 1
    position = snapshot.positions[0]
    assert (position.exchange, position.symbol, position.quantity) == ("AMEX", "SPY", 2)
    assert (position.average_price, position.market_price) == (500, 510)
    assert all(not pages for pages in transport.balance_pages.values())
    requests = [
        request for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_BALANCE_ENDPOINT.tr_id
    ]
    assert [request.query["OVRS_EXCG_CD"] for request in requests] == (
        ["NASD", "NASD", "NYSE", "AMEX"] if continued else ["NASD", "NYSE", "AMEX"]
    )
    if continued:
        assert requests[1].headers["tr_cont"] == "N"
        assert requests[1].query["CTX_AREA_FK200"] == "synthetic-fk"
        assert requests[1].query["CTX_AREA_NK200"] == "synthetic-nk"


def test_position_coalescing_key_includes_both_reported_venue_and_symbol() -> None:
    row = _position_payload()
    transport = ScriptedBalanceTransport(balance_pages={"NASD": [_balance_page([
        row,
        row | {"ovrs_excg_cd": "AMEX"},
        row | {"ovrs_pdno": "QQQ"},
    ])]})

    snapshot = KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert [(p.exchange, p.symbol) for p in snapshot.positions] == [
        ("AMEX", "SPY"), ("NASD", "QQQ"), ("NASD", "SPY"),
    ]


@pytest.mark.parametrize("query", ["NYSE", "AMEX"])
@pytest.mark.parametrize("change", [
    {"pchs_avg_pric": "501"},
    {"ovrs_cblc_qty": "3"},
    {"tr_crcy_cd": "KRW"},
])
def test_cross_query_position_conflicts_never_overwrite_or_sum(query, change) -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    transport = ScriptedBalanceTransport(balance_pages={
        "NASD": [_balance_page([row])],
        query: [_balance_page([row | change])],
    })

    with pytest.raises(KisPaperReadOnlyError, match="^balance_response_duplicate$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert transport.requests[-1].headers["tr_id"] == KIS_PAPER_BALANCE_ENDPOINT.tr_id


def test_cross_query_mark_changes_preserve_first_indicative_price() -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    transport = ScriptedBalanceTransport(balance_pages={
        "NASD": [_balance_page([row])],
        "NYSE": [_balance_page([row | {"now_pric2": "511"}])],
        "AMEX": [_balance_page([row | {"now_pric2": "509"}])],
    })

    snapshot = KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert len(snapshot.positions) == 1
    position = snapshot.positions[0]
    assert (position.exchange, position.symbol, position.quantity) == ("AMEX", "SPY", 2)
    assert position.average_price == 500
    assert position.market_price == 510
    assert all(not pages for pages in transport.balance_pages.values())


@pytest.mark.parametrize("query", ["NASD", "NYSE", "AMEX"])
@pytest.mark.parametrize("across_pages", [False, True])
@pytest.mark.parametrize("change", [{}, {"ovrs_cblc_qty": "3"}, {"now_pric2": "511"}])
def test_duplicate_positions_inside_one_query_are_never_coalesced(
    query, across_pages, change,
) -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    duplicate = row | change
    pages = (
        [_balance_page([row], continued=True), _balance_page([duplicate])]
        if across_pages else [_balance_page([row, duplicate])]
    )
    transport = ScriptedBalanceTransport(balance_pages={query: pages})

    with pytest.raises(KisPaperReadOnlyError, match="^balance_response_duplicate$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()


@pytest.mark.parametrize("query", ["NYSE", "AMEX"])
@pytest.mark.parametrize("failure", ["transport", "provider", "continuation"])
def test_successful_cross_scope_rows_do_not_hide_later_query_failure(query, failure) -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    if failure == "transport":
        response = KisPaperReadOnlyError("transport_failure")
        expected = "transport_failure"
    elif failure == "provider":
        response = KisHttpResponse.from_payload({"rt_cd": "1"}, status_code=500)
        expected = "balance_rejected"
    else:
        response = KisHttpResponse.from_payload(
            {"rt_cd": "0", "output1": [row]}, headers={"tr_cont": "M"},
        )
        expected = "balance_response_incomplete"
    transport = ScriptedBalanceTransport(balance_pages={
        "NASD": [_balance_page([row])],
        query: [response],
    })

    with pytest.raises(KisPaperReadOnlyError, match=f"^{expected}$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert transport.requests[-1].query["OVRS_EXCG_CD"] == query
    assert not any(
        request.headers.get("tr_id") == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id
        for request in transport.requests
    )


def test_cross_query_merge_waits_for_remaining_pages_before_accepting_a_group() -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"}
    transport = ScriptedBalanceTransport(balance_pages={
        "NASD": [_balance_page([row])],
        "NYSE": [
            _balance_page([row], continued=True),
            KisPaperReadOnlyError("transport_failure"),
        ],
    })

    with pytest.raises(KisPaperReadOnlyError, match="^transport_failure$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()

    assert transport.requests[-1].headers["tr_cont"] == "N"


@pytest.mark.parametrize("venue", ["HKEX", "NAS", "AMEX.extra", "", None])
def test_cross_scope_balance_still_rejects_foreign_or_invalid_venues(venue) -> None:
    transport = ScriptedBalanceTransport(balance_pages={"NASD": [_balance_page([
        _position_payload() | {"ovrs_excg_cd": venue},
    ])]})

    with pytest.raises(KisPaperReadOnlyError, match="^balance_response_incomplete$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()


@pytest.mark.parametrize("field_name", ["pchs_avg_pric", "now_pric2"])
@pytest.mark.parametrize("value", [None, "", "0", "-1", "NaN", "Infinity", "invalid"])
def test_cross_scope_balance_does_not_relax_positive_price_fields(field_name, value) -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX", field_name: value}
    transport = ScriptedBalanceTransport(balance_pages={"NASD": [_balance_page([row])]})

    with pytest.raises(KisPaperReadOnlyError, match="^balance_response_incomplete$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()


@pytest.mark.parametrize("change", [
    {"ovrs_cblc_qty": None},
    {"ovrs_cblc_qty": "-1"},
    {"ovrs_cblc_qty": "NaN"},
    {"ovrs_pdno": ""},
    {"tr_crcy_cd": ""},
])
def test_cross_scope_balance_still_requires_valid_inventory_fields(change) -> None:
    row = _position_payload() | {"ovrs_excg_cd": "AMEX"} | change
    transport = ScriptedBalanceTransport(balance_pages={"NASD": [_balance_page([row])]})

    with pytest.raises(KisPaperReadOnlyError, match="^balance_response_incomplete$"):
        KisPaperReadOnlyClient(config=_config(), transport=transport).snapshot()


def test_no_order_tr_ids_or_actions_are_reachable() -> None:
    public_actions = {"submit_order", "cancel_order", "modify_order", "order_status"}
    source = Path(kis_readonly.__file__).read_text(encoding="utf-8")

    assert not public_actions & set(vars(KisPaperReadOnlyClient))
    assert {endpoint.tr_id for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS} == {
        "VTTS3012R",
        "VTTS3007R",
        "VTTS3018R",
        "VTTS3035R",
    }
    assert all(
        endpoint.path.startswith("/uapi/overseas-stock/v1/trading/inquire-")
        for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS
    )
    assert "VTTT" not in source
    assert "order-rvsecncl" not in source
    assert '"/uapi/overseas-stock/v1/trading/order"' not in source


def test_same_day_order_id_observation_is_read_only_and_never_retains_the_raw_id() -> None:
    @dataclass
    class SameDayTransport:
        requests: list[KisHttpRequest] = field(default_factory=list)

        def request(self, request: KisHttpRequest) -> KisHttpResponse:
            self.requests.append(request)
            if request.method == "POST":
                return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
            if request.headers["tr_id"] == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
                return KisHttpResponse.from_payload(
                    {"rt_cd": "0", "output": [{"odno": "ORD-123456789"}]}
                )
            raise AssertionError(f"unexpected read-only request: {request!r}")

    transport = SameDayTransport()
    observation = KisPaperReadOnlyClient(
        config=_config(),
        transport=transport,
    ).observe_same_day_order_id("ORD-123456789", as_of=NOW)

    assert observation.same_day_order_id_seen is True
    assert observation.row_count == 1
    assert "ORD-123456789" not in repr(observation)
    assert [request.headers.get("tr_id") for request in transport.requests] == [
        None,
        KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id,
    ]
    assert all(
        request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        for request in transport.requests
    )


@pytest.mark.parametrize(
    "order_at,expected_day",
    [
        (datetime(2026, 7, 23, 1, 0, tzinfo=UTC), "20260722"),
        (datetime(2026, 1, 23, 4, 0, tzinfo=UTC), "20260122"),
    ],
)
def test_history_observation_separates_order_day_from_recovery_clock(
    order_at: datetime,
    expected_day: str,
) -> None:
    class HistoryTransport:
        requests: list[KisHttpRequest]

        def __init__(self) -> None:
            self.requests = []

        def request(self, request: KisHttpRequest) -> KisHttpResponse:
            self.requests.append(request)
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})

    transport = HistoryTransport()
    recovered_at = datetime(2026, 7, 25, 15, 0, tzinfo=UTC)
    observation = KisPaperReadOnlyClient(
        config=_config(),
        transport=transport,
        access_token="synthetic-token",
    ).observe_same_day_order_id("ORD-123456789", as_of=recovered_at, order_at=order_at)
    assert observation.observed_at == recovered_at
    assert len(transport.requests) == 1
    assert transport.requests[0].query["ORD_STRT_DT"] == expected_day
    assert transport.requests[0].query["ORD_END_DT"] == expected_day


def test_terminal_field_probe_uses_persisted_order_day_and_redacts_raw_fields() -> None:
    @dataclass
    class TerminalFieldTransport:
        requests: list[KisHttpRequest] = field(default_factory=list)

        def request(self, request: KisHttpRequest) -> KisHttpResponse:
            self.requests.append(request)
            if request.method == "POST":
                return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
            if request.headers["tr_id"] == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
                return KisHttpResponse.from_payload(
                    {
                        "rt_cd": "0",
                        "output": [
                            {
                                "odno": "ORD-123456789",
                                "orgn_odno": "",
                                "ft_ord_qty": "1",
                                "ft_ccld_qty": "0",
                                "nccs_qty": "1",
                                "ft_ccld_unpr3": "0",
                                "ft_ccld_amt3": "0",
                                "prcs_stat_name": "private-status-text",
                                "rvse_cncl_dvsn": "00",
                                "ord_tmd": "101010",
                            }
                        ],
                    }
                )
            raise AssertionError(f"unexpected read-only request: {request!r}")

    transport = TerminalFieldTransport()
    observation = KisPaperReadOnlyClient(
        config=_config(),
        transport=transport,
    ).inspect_order_history_terminal_fields(
        "ORD-123456789",
        order_at=datetime(2026, 7, 22, 1, 0, tzinfo=UTC),
    )

    assert observation.identity_match == "exact_order"
    assert set(observation.field_states.values()) == {"present"}
    assert observation.pagination_status == "complete"
    assert observation.terminal_state_support == "unqualified"
    assert observation.pnl_status == "not_observed"
    safe_payload = observation.safe_payload()
    assert "ORD-123456789" not in repr(observation)
    assert "ORD-123456789" not in str(safe_payload)
    assert "private-status-text" not in str(safe_payload)
    history_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id
    )
    assert history_request.query["ORD_STRT_DT"] == "20260721"
    assert history_request.query["ORD_END_DT"] == "20260721"
    assert all(
        request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        for request in transport.requests
    )
    assert all(
        not request.headers.get("tr_id", "").startswith("VTTT") for request in transport.requests
    )


def test_terminal_field_probe_requires_completed_pagination_before_field_support() -> None:
    @dataclass
    class PaginatedTerminalFieldTransport:
        requests: list[KisHttpRequest] = field(default_factory=list)

        def request(self, request: KisHttpRequest) -> KisHttpResponse:
            self.requests.append(request)
            if request.method == "POST":
                return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
            if request.headers["tr_id"] != KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
                raise AssertionError(f"unexpected read-only request: {request!r}")
            if request.headers["tr_cont"] == "":
                return KisHttpResponse.from_payload(
                    {
                        "rt_cd": "0",
                        "output": [],
                        "ctx_area_fk200": "next-fk",
                        "ctx_area_nk200": "next-nk",
                    },
                    headers={"tr_cont": "M"},
                )
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": [
                        {
                            "odno": "ORD-123456789",
                            "orgn_odno": "",
                            "ft_ord_qty": "1",
                            "ft_ccld_qty": "0",
                            "nccs_qty": "1",
                            "ft_ccld_unpr3": "0",
                            "ft_ccld_amt3": "0",
                            "prcs_stat_name": "private-status-text",
                            "rvse_cncl_dvsn": "00",
                            "ord_tmd": "101010",
                        }
                    ],
                }
            )

    transport = PaginatedTerminalFieldTransport()
    observation = KisPaperReadOnlyClient(
        config=_config(),
        transport=transport,
    ).inspect_order_history_terminal_fields("ORD-123456789", order_at=NOW)

    assert observation.identity_match == "exact_order"
    history_requests = [
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id
    ]
    assert [request.headers["tr_cont"] for request in history_requests] == ["", "N"]
    assert history_requests[1].query["CTX_AREA_FK200"] == "next-fk"
    assert history_requests[1].query["CTX_AREA_NK200"] == "next-nk"


def _history_client_with_rows(rows):
    class HistoryTransport:
        def request(self, request):
            assert request.method == "GET"
            assert request.headers["tr_id"] == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id
            assert request.query["ODNO"] == ""
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": rows})

    return KisPaperReadOnlyClient(
        config=_config(), transport=HistoryTransport(), access_token="synthetic-token"
    )


@pytest.mark.parametrize(
    "raw_id,candidate,matched",
    [
        ("000123", "123", True),
        ("123", "000123", True),
        ("1", "0" * 63 + "1", True),
        ("AB-001_X", "AB-001_X", True),
        ("AB001", "AB1", False),
        ("001AB", "1AB", False),
        ("ab1", "AB1", False),
        ("-001", "-1", False),
        ("001_", "1_", False),
        ("0", "000", False),
        ("000", "0", False),
        ("0", "0", True),
        ("123", "124", False),
    ],
)
def test_history_only_padding_comparison_applies_to_direct_and_lineage(raw_id, candidate, matched):
    rows = [{"odno": candidate, "orgn_odno": candidate}]
    history = _history_client_with_rows(rows)._read_same_day_order_history(raw_id, order_at=NOW)
    assert history.row_count == 1
    assert bool(history.direct_matches) is matched
    assert bool(history.lineage_matches) is matched
    assert rows == [{"odno": candidate, "orgn_odno": candidate}]


@pytest.mark.parametrize("field", ["odno", "orgn_odno"])
@pytest.mark.parametrize(
    "candidate",
    [
        None, 123, "", "+123", "123.0", " 123", "123 ",
        "\uff11\uff12\uff13", "\u0661\u0662\u0663", "0" * 64 + "123",
    ],
)
def test_invalid_history_alias_is_never_equivalent(field, candidate):
    row = {"odno": "OTHER-123", "orgn_odno": ""}
    row[field] = candidate
    client = _history_client_with_rows([row])
    if field == "odno":
        with pytest.raises(KisPaperReadOnlyError, match="ccnl_response_incomplete"):
            client._read_same_day_order_history("123", order_at=NOW)
    else:
        history = client._read_same_day_order_history("123", order_at=NOW)
        assert not history.direct_matches and not history.lineage_matches


@pytest.mark.parametrize("raw_id", [None, 123, "", " 123", "\uff11\uff12\uff13", "0" * 64 + "123"])
def test_invalid_requested_history_id_still_rejected(raw_id):
    with pytest.raises(KisPaperReadOnlyError, match="order_id_invalid"):
        _history_client_with_rows([])._read_same_day_order_history(raw_id, order_at=NOW)


@pytest.mark.parametrize("raw_id,alias", [("000123", "123"), ("123", "000123")])
def test_numeric_lineage_padding_retains_structural_only_observation(raw_id, alias):
    row = {"odno": "OTHER-123", "orgn_odno": alias}
    observation = _history_client_with_rows([row]).inspect_order_history_terminal_fields(
        raw_id, order_at=NOW
    )
    assert observation.identity_match == "original_order_lineage"
    assert observation.terminal_state_support == "unqualified"
    assert observation.pnl_status == "not_observed"
    ambiguous = _history_client_with_rows([
        row, {"odno": "OTHER-456", "orgn_odno": raw_id}
    ]).inspect_order_history_terminal_fields(raw_id, order_at=NOW)
    assert ambiguous.identity_match == "ambiguous"


def test_terminal_field_probe_rejects_ambiguous_order_lineage_without_terminal_inference() -> None:
    @dataclass
    class AmbiguousTerminalFieldTransport:
        def request(self, request: KisHttpRequest) -> KisHttpResponse:
            if request.method == "POST":
                return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
            if request.headers["tr_id"] == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
                return KisHttpResponse.from_payload(
                    {
                        "rt_cd": "0",
                        "output": [
                            {"odno": "ORD-123456789"},
                            {"odno": "ORD-987654321", "orgn_odno": "ORD-123456789"},
                        ],
                    }
                )
            raise AssertionError(f"unexpected read-only request: {request!r}")

    observation = KisPaperReadOnlyClient(
        config=_config(),
        transport=AmbiguousTerminalFieldTransport(),
    ).inspect_order_history_terminal_fields("ORD-123456789", order_at=NOW)

    assert observation.identity_match == "ambiguous"
    assert set(observation.field_states.values()) == {"not_observed"}
    assert observation.terminal_state_support == "unqualified"
    assert observation.pnl_status == "not_observed"


def test_evidence_excludes_credentials_raw_account_and_prices_and_stays_external(tmp_path) -> None:
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
    assert outcome.reconciliation.account_snapshot_complete is True
    assert outcome.reconciliation.scope == "read_only"
    assert outcome.reconciliation.reasons == ()
    assert evidence_path.is_file()
    assert evidence_path.is_relative_to(tmp_path / "artifacts")
    assert not evidence_path.is_relative_to(repo_root)
    evidence = evidence_path.read_text(encoding="utf-8")
    assert "app-key-value" not in evidence
    assert "super-secret-value" not in evidence
    assert "12345678" not in evidence
    assert "ORD-123456789" not in evidence
    payload = json.loads(evidence)
    assert set(payload) == {
        "schema_version",
        "kind",
        "status",
        "reason_code",
        "captured_at",
        "paper_only",
        "submit_capability",
        "facts",
        "reconciliation",
    }
    assert payload["submit_capability"] is False
    assert isinstance(payload["captured_at"], str)
    assert payload["facts"] == {
        "cash_currency": "USD",
        "orderable_funds_currency": "USD",
        "position_count": 1,
        "open_order_count": 1,
    }
    assert payload["reconciliation"] == {
        "account_snapshot_complete": True,
        "scope": "read_only",
        "reasons": [],
        "reconciled_at": payload["reconciliation"]["reconciled_at"],
    }
    assert isinstance(payload["reconciliation"]["reconciled_at"], str)
    assert "snapshot" not in payload


def test_reconciliation_records_account_facts_on_currency_mismatch() -> None:
    snapshot = _snapshot(cash_currency="USD", orderable_currency="KRW")

    reconciliation = reconcile_kis_paper_readonly(snapshot, reconciled_at=NOW)

    assert reconciliation.account_snapshot_complete is True
    assert reconciliation.scope == "read_only"
    assert reconciliation.reasons == ("cash_orderable_currency_mismatch",)


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


def test_safe_kis_message_code_is_projected_without_response_text(tmp_path) -> None:
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
        transport=FakeKisTransport(
            reject_balance=True,
            balance_failure_code="EGW00201",
            balance_failure_message="raw-message-12345678-ORD-123456789-must-not-persist",
        ),
    )

    expected_diagnostic = {
        "endpoint": "balance",
        "tr_id": KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        "http_status": "500",
        "upstream_code": "EGW00201",
    }
    assert outcome.diagnostic == expected_diagnostic
    evidence = evidence_path.read_text(encoding="utf-8")
    assert json.loads(evidence)["diagnostic"] == expected_diagnostic
    assert "raw-message-12345678-ORD-123456789-must-not-persist" not in evidence
    assert "super-secret-value" not in evidence
    assert "12345678" not in evidence


@pytest.mark.parametrize(
    "value",
    ("", "egw00201", "EGW-00201", " EGW00201", "A" * 17, 123, None, "12345678"),
)
def test_untrusted_kis_message_code_is_omitted_from_runtime_diagnostic(value: object) -> None:
    response = KisHttpResponse.from_payload(
        {
            "rt_cd": "1",
            "msg_cd": value,
            "msg1": "must-not-persist-free-text",
        },
        status_code=403,
    )

    with pytest.raises(KisPaperReadOnlyError) as raised:
        kis_readonly._successful_payload(
            response,
            "balance_rejected",
            endpoint=KIS_PAPER_BALANCE_ENDPOINT,
        )

    expected = {
        "endpoint": "balance",
        "tr_id": KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        "http_status": "403",
    }
    if value == "12345678":
        expected["upstream_code"] = "paper_numeric_unclassified"
    assert raised.value.diagnostic == expected


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


def _balance_page(rows: list[object], *, continued: bool = False) -> KisHttpResponse:
    payload = {"rt_cd": "0", "output1": rows}
    if continued:
        payload |= {"ctx_area_fk200": "synthetic-fk", "ctx_area_nk200": "synthetic-nk"}
    return KisHttpResponse.from_payload(payload, headers={"tr_cont": "M" if continued else ""})


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
