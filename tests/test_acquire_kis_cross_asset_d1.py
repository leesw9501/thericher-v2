from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisPaperDailyQuery,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataTokenStartGate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cross_asset_d1_script", ROOT / "scripts" / "acquire_kis_cross_asset_d1.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)
CANARY = "synthetic-private-body-or-secret-canary"
KEY = "synthetic-appkey-fake_secret"
SECRET = "synthetic-appsecret-fake_secret"
TOKEN = "synthetic-token-fake_secret"


class FakeClock:
    def __init__(self):
        self.seconds = 0.0
        self.sleeps = []

    def now(self):
        return datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=self.seconds)

    def monotonic(self):
        return self.seconds

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.seconds += delay


def row(session_date, *, price="10"):
    return {
        "xymd": session_date,
        "open": price,
        "high": "20",
        "low": "1",
        "clos": "10",
        "tvol": "100",
    }


class FakeOpener:
    def __init__(self, clock, payload=None, on_request=None):
        self.clock = clock
        self.payload = payload
        self.on_request = on_request
        self.requests = []

    def open(self, request, timeout):
        parsed = urllib.parse.urlsplit(request.full_url)
        query = {
            k: v[0] for k, v in urllib.parse.parse_qs(parsed.query, keep_blank_values=True).items()
        }
        fact = {
            "method": request.method,
            "path": parsed.path,
            "query": query,
            "timeout": timeout,
            "url": request.full_url,
        }
        self.requests.append(fact)
        self.clock.seconds += 0.02
        if self.on_request:
            self.on_request(fact)
        if parsed.path == KIS_PAPER_TOKEN_PATH:
            payload, status = {"access_token": TOKEN}, 200
        else:
            payload, status = (
                {
                    "rt_cd": "0",
                    "output1": {},
                    "output2": [row(query["BYMD"])],
                    "private_body": CANARY,
                },
                200,
            )
        if self.payload:
            payload, status = self.payload(fact, payload, status)
        body = json.dumps(payload).encode()

        class Response:
            headers = {"tr_cont": "F"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return body

        response = Response()
        response.status = status
        return response


@pytest.fixture
def harness(tmp_path):
    clock = FakeClock()
    opener = FakeOpener(clock)
    transports = []
    config_calls = []

    def factory(**kwargs):
        transport = script.CrossAssetDailyTransport(**kwargs)
        transport._opener = opener
        transports.append(transport)
        return transport

    def loader(path):
        config_calls.append(path)
        return KisPaperMarketDataConfig(app_key=KEY, app_secret=SECRET)

    kwargs = dict(
        market_root=tmp_path / "market",
        artifact_root=tmp_path / "artifacts",
        repository_root=ROOT,
        run_label="synthetic",
        dotenv_path=tmp_path / "unread.env",
        clock=clock.now,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
        transport_factory=factory,
        config_loader=loader,
        space_check=lambda count: False,
    )
    return SimpleNamespace(
        kwargs=kwargs, clock=clock, opener=opener, transports=transports, config_calls=config_calls
    )


def receipt(result):
    return json.loads(Path(result["receipt_path"]).read_bytes())


def assert_redacted(harness, result):
    for path in harness.kwargs["artifact_root"].rglob("*.json"):
        assert all(value not in path.read_text() for value in (CANARY, KEY, SECRET, TOKEN))
    assert all(value not in json.dumps(result) for value in (CANARY, KEY, SECRET, TOKEN))


def test_exact_eight_get_scope_one_token_and_private_only_retention(harness):
    result = script.run_probe(**harness.kwargs)
    r = receipt(result)
    assert result["status"] == "observed"
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 8}
    assert len(harness.transports) == 1 and len(harness.config_calls) == 1
    assert len(harness.opener.requests) == 9
    assert [x["path"] for x in harness.opener.requests] == [KIS_PAPER_TOKEN_PATH] + [
        KIS_PAPER_DAILY_PATH
    ] * 8
    actual = [
        (x["query"]["SYMB"], x["query"]["EXCD"], x["query"]["BYMD"], x["query"]["MODP"])
        for x in harness.opener.requests[1:]
    ]
    assert actual == [
        (q.symbol, q.exchange, q.by_date, q.adjustment_mode) for q in script.probe_queries()
    ]
    assert all(x["timeout"] == 15 for x in harness.opener.requests)
    assert all(0 <= delay <= 1.000001 for delay in harness.clock.sleeps)
    assert r["accepted_page_count"] == 8 and r["queries_not_attempted"] == []
    assert r["token_body_retained"] is False
    assert len(r["private_daily_responses"]) == 8
    for binding in r["private_daily_responses"]:
        path = harness.kwargs["market_root"] / binding["market_relative_path"]
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
        assert CANARY in path.read_text()
    assert_redacted(harness, result)


def test_contract_is_frozen_before_config_or_transport(harness):
    loader = harness.kwargs["config_loader"]

    def checked_loader(path):
        contract = (
            harness.kwargs["artifact_root"]
            / "data"
            / script.GOAL
            / "capability"
            / ("synthetic/contract.json")
        )
        assert contract.is_file()
        d = json.loads(contract.read_bytes())
        assert d["maximum_daily_GETs"] == 8 and d["maximum_token_POSTs"] == 1
        assert len(d["queries"]) == 8 and d["source_pins"]
        return loader(path)

    harness.kwargs["config_loader"] = checked_loader
    assert script.run_probe(**harness.kwargs)["status"] == "observed"


def test_same_client_ordinary_query_after_eight_probes_retains_token(harness):
    t = harness.kwargs["transport_factory"](timeout_seconds=15)
    c = KisPaperMarketDataClient(
        config=harness.kwargs["config_loader"](Path("not-read")),
        transport=t,
        max_daily_page_attempts=9,
    )
    c.ensure_authenticated()
    for q in script.probe_queries():
        c.fetch_daily_raw_page(q)
    c.fetch_daily_raw_page(
        KisPaperDailyQuery(
            symbol="TLT", exchange="NAS", by_date="20071231", approved_symbol_exchanges=script.SCOPE
        )
    )
    assert c.call_counts.token_attempts == 1 and c.call_counts.daily_page_attempts == 9
    assert sum(x["path"] == KIS_PAPER_TOKEN_PATH for x in harness.opener.requests) == 1


@pytest.mark.parametrize(
    "path,method",
    [
        ("/uapi/overseas-stock/v1/trading/order", "POST"),
        ("/uapi/overseas-stock/v1/trading/inquire-balance", "GET"),
        ("/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice", "GET"),
    ],
)
def test_transport_rejects_every_non_daily_non_token_route(harness, path, method):
    transport = harness.kwargs["transport_factory"](timeout_seconds=15)
    with pytest.raises(KisPaperMarketDataError):
        transport.request(
            KisMarketDataRequest(
                method=method, url=KIS_PAPER_MARKET_DATA_BASE_URL + path, headers={}
            )
        )
    assert harness.opener.requests == []


@pytest.mark.parametrize("symbol,exchange", [("QQQ", "NAS"), ("TLT", "AMS"), ("GLD", "NYS")])
def test_transport_fixed_scope_cannot_be_widened_by_query(harness, symbol, exchange):
    transport = harness.kwargs["transport_factory"](timeout_seconds=15)
    c = KisPaperMarketDataClient(
        config=harness.kwargs["config_loader"](Path("not-read")), transport=transport
    )
    query = KisPaperDailyQuery(
        symbol=symbol,
        exchange=exchange,
        by_date="20261007",
        approved_symbol_exchanges={symbol: frozenset({exchange})},
    )
    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        c.fetch_daily_raw_page(query)
    assert len(harness.opener.requests) == 1


@pytest.mark.parametrize("marker,mode", [(None, "1"), (frozenset({"1"}), "1")])
def test_transport_rejects_mode_one_without_exact_probe_marker(harness, marker, mode):
    t = harness.kwargs["transport_factory"](timeout_seconds=15)
    with pytest.raises(KisPaperMarketDataError):
        t.request(
            KisMarketDataRequest(
                method="GET",
                url=KIS_PAPER_MARKET_DATA_BASE_URL + KIS_PAPER_DAILY_PATH,
                headers={"tr_id": "HHDFS76240000", "tr_cont": ""},
                query={
                    "AUTH": "",
                    "EXCD": "NAS",
                    "SYMB": "TLT",
                    "BYMD": "20261007",
                    "GUBN": "0",
                    "MODP": mode,
                },
                daily_adjustment_modes=marker,
            )
        )
    assert harness.opener.requests == []


@pytest.mark.parametrize("code", ["auth_rejected", "rate_limited", "transport_failure"])
def test_first_token_failure_does_not_retry_or_get(harness, code):
    def failed(_request):
        raise KisPaperMarketDataError(code, CANARY)

    harness.opener.on_request = failed
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == code
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 0}
    assert len(harness.opener.requests) == 1
    assert len(receipt(result)["queries_not_attempted"]) == 8
    assert_redacted(harness, result)


def test_local_token_guard_has_zero_token_and_get_attempts(harness):
    control = harness.kwargs["market_root"] / "us_equities/kis_paper_private/collection-control-v1"
    gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=harness.clock.now)
    assert gate.claim_token_request_start()
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "token_request_not_due"
    assert result["call_counts"] == {"token_attempts": 0, "daily_page_attempts": 0}
    assert result["owned_next_due_utc"] == "2026-10-08T00:05:00Z"
    assert harness.opener.requests == [] and harness.clock.sleeps == []


def test_unknown_provider_exception_text_stays_redacted(harness):
    harness.opener.on_request = lambda request: (_ for _ in ()).throw(
        KisPaperMarketDataError(CANARY)
    )
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "provider_failure_unclassified"
    assert_redacted(harness, result)


@pytest.mark.parametrize("failure", ["rejected", "malformed", "future", "conflict", "empty"])
def test_first_daily_failure_retains_no_body_and_stops(harness, failure):
    def payload(fact, p, status):
        if fact["path"] == KIS_PAPER_TOKEN_PATH:
            return p, status
        if failure == "rejected":
            p["rt_cd"] = "1"
        elif failure == "malformed":
            p["output2"] = [{"xymd": "20261007"}]
        elif failure == "future":
            p["output2"] = [row("20261008")]
        elif failure == "conflict":
            p["output2"] = [row("20261007"), row("20261007", price="11")]
        else:
            p["output2"] = []
        return p, status

    harness.opener.payload = payload
    result = script.run_probe(**harness.kwargs)
    assert result["status"] == "unavailable"
    assert result["accepted_page_count"] == 0
    assert result["call_counts"]["daily_page_attempts"] == 1
    assert len(harness.opener.requests) == 2
    assert receipt(result)["private_daily_responses"] == []
    assert not list(harness.kwargs["market_root"].rglob("daily-*.json"))
    assert_redacted(harness, result)


@pytest.mark.parametrize("status", [200, 403, 500])
def test_get_error_secret_echo_is_never_retained_or_printed(harness, monkeypatch, capsys, status):
    fake_secret = "fake_secret_from_failed_GET_body"

    def payload(fact, p, code):
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            return {"rt_cd": "1", "msg1": fake_secret, "error_description": fake_secret}, status
        return p, code

    harness.opener.payload = payload
    run_probe = script.run_probe
    monkeypatch.setattr(script, "run_probe", lambda **kwargs: run_probe(**harness.kwargs))
    assert script.main(["--execute", "--run-label", "synthetic"]) == 20
    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert result["accepted_page_count"] == 0
    assert receipt(result)["private_daily_responses"] == []
    assert len(harness.opener.requests) == 2
    assert fake_secret not in stdout
    for path in harness.kwargs["market_root"].parent.rglob("*"):
        if path.is_file():
            assert fake_secret.encode() not in path.read_bytes()


@pytest.mark.parametrize("private_value", [KEY, SECRET, TOKEN])
def test_successful_typed_get_with_request_secret_echo_is_not_retained(
    harness, monkeypatch, capsys, private_value
):
    def payload(fact, p, status):
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            p["extra"] = {"nested": ["echo:" + private_value]}
        return p, status

    harness.opener.payload = payload
    run_probe = script.run_probe
    monkeypatch.setattr(script, "run_probe", lambda **kwargs: run_probe(**harness.kwargs))
    assert script.main(["--execute", "--run-label", "synthetic"]) == 20
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["reason"] == "credential_echo_rejected"
    assert result["accepted_page_count"] == 0
    assert receipt(result)["private_daily_responses"] == []
    assert private_value not in output
    for path in harness.kwargs["market_root"].parent.rglob("*"):
        if path.is_file():
            assert private_value.encode() not in path.read_bytes()


def test_terminal_pin_read_failure_preserves_receipt_initial_pins_and_facts(harness, monkeypatch):
    initial = script._source_pins(ROOT)
    calls = 0

    def pins(root):
        nonlocal calls
        calls += 1
        if calls >= 30:
            raise OSError(CANARY)
        return initial

    monkeypatch.setattr(script, "_source_pins", pins)
    result = script.run_probe(**harness.kwargs)
    r = receipt(result)
    assert result["reason"] == "source_hash_unavailable"
    assert result["status"] == "partial"
    assert result["accepted_page_count"] == 8
    assert r["source_reattestation"] == "unavailable"
    assert r["source_pins"] == initial
    assert r["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 8}
    assert len(r["pages"]) == len(r["private_daily_responses"]) == 8
    assert_redacted(harness, result)


def test_successful_typed_get_with_numeric_request_key_echo_is_not_retained(harness):
    harness.kwargs["config_loader"] = lambda path: KisPaperMarketDataConfig(
        app_key="735198602471", app_secret=SECRET)
    def payload(fact, p, status):
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            p["extra"] = 735198602471
        return p, status
    harness.opener.payload = payload
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "credential_echo_rejected"
    assert receipt(result)["private_daily_responses"] == []
    for path in harness.kwargs["market_root"].parent.rglob("*"):
        if path.is_file():
            assert b"735198602471" not in path.read_bytes()


def test_identical_duplicate_dates_are_counted_without_source_values(harness):
    def payload(fact, p, status):
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            p["output2"] = [row(fact["query"]["BYMD"])] * 2
        return p, status

    harness.opener.payload = payload
    result = script.run_probe(**harness.kwargs)
    assert result["status"] == "observed"
    assert all(
        p["exact_duplicate_date_count"] == 1 and p["unique_date_count"] == 1
        for p in receipt(result)["pages"]
    )


def test_nonadvancing_deep_anchor_stops_without_inventing_cursor(harness):
    def payload(fact, p, status):
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            p["output2"] = [row("20070101")]
        return p, status

    harness.opener.payload = payload
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "nonadvancing_cursor"
    assert result["accepted_page_count"] == 6
    assert result["call_counts"]["daily_page_attempts"] == 7


def test_source_hash_change_after_get_retains_no_body_and_rejects_attestation(harness, monkeypatch):
    original = script._source_pins(ROOT)
    changed = False

    def on_request(fact):
        nonlocal changed
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            changed = True

    monkeypatch.setattr(
        script,
        "_source_pins",
        lambda root: original if not changed else {**original, "changed": "sha256:" + "0" * 64},
    )
    harness.opener.on_request = on_request
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "source_hash_changed"
    assert len(harness.opener.requests) == 2
    assert receipt(result)["private_daily_responses"] == []


def test_storage_floor_yields_before_credentials(harness):
    harness.kwargs["space_check"] = lambda count: True
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "storage_floor"
    assert harness.config_calls == [] and harness.opener.requests == []


def test_long_cooldown_yields_without_sleeping_or_extra_post(harness):
    def on_request(fact):
        if fact["path"] == KIS_PAPER_DAILY_PATH:
            harness.transports[0]._request_gate.record_rate_limit()

    harness.opener.on_request = on_request
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "cooldown_not_due"
    assert result["owned_next_due_utc"] is not None
    assert result["accepted_page_count"] == 1
    assert len(harness.opener.requests) == 2
    assert all(delay <= 1.000001 for delay in harness.clock.sleeps)


def test_runtime_expiry_after_token_has_no_get(harness):
    def on_request(fact):
        if fact["path"] == KIS_PAPER_TOKEN_PATH:
            harness.clock.seconds = 61

    harness.opener.on_request = on_request
    result = script.run_probe(**harness.kwargs)
    assert result["reason"] == "runtime_budget"
    assert len(harness.opener.requests) == 1


def test_completed_appointment_cannot_be_reexecuted(harness):
    script.run_probe(**harness.kwargs)
    with pytest.raises(FileExistsError):
        script.run_probe(**harness.kwargs)
    assert len(harness.opener.requests) == 9


@pytest.mark.parametrize("label", ["../escape", "a/b", "a\\b", "", "x" * 81])
def test_invalid_run_labels_never_load_credentials(harness, label):
    harness.kwargs["run_label"] = label
    with pytest.raises(ValueError):
        script.run_probe(**harness.kwargs)
    assert harness.config_calls == []


def test_repository_root_or_shared_roots_are_rejected(harness):
    harness.kwargs["market_root"] = ROOT
    with pytest.raises(ValueError):
        script.run_probe(**harness.kwargs)
    harness.kwargs["market_root"] = harness.kwargs["artifact_root"]
    with pytest.raises(ValueError):
        script.run_probe(**harness.kwargs)


def test_no_execute_never_loads_environment_or_writes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "run_probe", lambda **kwargs: pytest.fail("probe executed"))
    assert (
        script.main(
            [
                "--run-label",
                "preview",
                "--market-root",
                str(tmp_path / "market"),
                "--artifact-root",
                str(tmp_path / "artifacts"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "not_executed"
    assert not list(tmp_path.iterdir())


def test_main_failure_never_prints_dynamic_exception(monkeypatch, capsys):
    def fail(**kwargs):
        raise ValueError(CANARY)

    monkeypatch.setattr(script, "run_probe", fail)
    assert script.main(["--execute", "--run-label", "synthetic"]) == 20
    text = capsys.readouterr().out
    assert CANARY not in text and json.loads(text)["status"] == "unavailable"
