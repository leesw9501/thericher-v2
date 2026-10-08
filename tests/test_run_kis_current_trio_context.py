from __future__ import annotations

import importlib.util
import json
import urllib.parse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_market_data import (
    KisMarketDataRequest,
    KisPaperMarketDataConfig,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "current_trio_script", ROOT / "scripts/run_kis_current_trio_context.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)
KEY, SECRET, TOKEN = "fake_secret_key", "fake_secret_appsecret", "fake_secret_token"
INVOCATION = "a" * 32


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 8, 15, tzinfo=UTC)
        self.elapsed = 0.0
        self.sleeps = []

    def utc(self):
        return self.now

    def monotonic(self):
        return self.elapsed

    def advance(self, seconds):
        self.elapsed += seconds
        self.now += timedelta(seconds=seconds)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.advance(seconds)


def synthetic_rows(anchor, count=100):
    rows = []
    day = datetime.strptime(anchor, "%Y%m%d").date()
    while len(rows) < count:
        if script.calendar.us_equity_2026_session(day) is not None:
            rows.append(
                dict(
                    xymd=day.strftime("%Y%m%d"),
                    open="10000.125",
                    clos="20000.375",
                    high="30000",
                    low="1",
                    tvol="10",
                )
            )
        day -= timedelta(days=1)
    return rows


class WireResponse:
    def __init__(self, status, payload):
        self.status, self.headers = status, {"tr_cont": "F"}
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.body


class FakeWire:
    def __init__(self, clock):
        self.clock, self.calls, self.gets = clock, [], 0
        self.token_failure = self.get_failure = self.echo = self.row_fault = None
        self.after_get = None

    def open(self, request, timeout):
        assert timeout == 15
        assert request.full_url.startswith(script.market.KIS_PAPER_MARKET_DATA_BASE_URL)
        method = request.get_method()
        self.calls.append((method, request.full_url))
        self.clock.advance(0.2)
        if method == "POST":
            assert request.full_url.endswith(script.market.KIS_PAPER_TOKEN_PATH)
            assert json.loads(request.data) == dict(
                grant_type="client_credentials", appkey=KEY, appsecret=SECRET
            )
            if self.token_failure:
                return WireResponse(401, dict(error_description=SECRET))
            return WireResponse(200, dict(access_token=TOKEN))
        assert method == "GET" and request.full_url.split("?")[0].endswith(
            script.market.KIS_PAPER_DAILY_PATH
        )
        params = {
            k: v[0]
            for k, v in urllib.parse.parse_qs(
                urllib.parse.urlsplit(request.full_url).query, keep_blank_values=True
            ).items()
        }
        symbol, venue = script.TARGETS[self.gets]
        self.gets += 1
        assert params == dict(AUTH="", SYMB=symbol, EXCD=venue, BYMD="20261007", GUBN="0", MODP="0")
        if self.get_failure == self.gets:
            return WireResponse(200, dict(rt_cd="1", msg1=SECRET, output1={}, output2=[]))
        rows = synthetic_rows(params["BYMD"])
        if self.row_fault == "gap":
            rows.pop(1)
        if self.row_fault == "future":
            rows[0]["xymd"] = "20261008"
        if self.row_fault == "unused":
            rows[0]["low"] = "30000"
        if self.after_get:
            self.after_get(self.gets)
        return WireResponse(
            200,
            dict(rt_cd="0", output1={}, output2=rows, msg1=self.echo or "market-only synthetic"),
        )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    market, artifacts = tmp_path / "market", tmp_path / "artifacts"
    market.mkdir()
    artifacts.mkdir()
    clock = Clock()
    wire = FakeWire(clock)
    state = SimpleNamespace(
        clock=clock,
        wire=wire,
        market=market,
        artifacts=artifacts,
        loader_calls=[],
        gates=[],
        token_due=True,
        delay=1.0,
        locks=[],
        releases=[],
        busy=False,
        floor=False,
    )
    monkeypatch.setattr(script, "MARKET_ROOT", market)
    monkeypatch.setattr(script, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(script, "_source_pins", lambda root: {"pure": script.CONTEXT_PIN})

    def load(path):
        state.loader_calls.append(path)
        return KisPaperMarketDataConfig(KEY, SECRET)

    class RequestGate:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            state.gates.append(kwargs)

        def wait_for_request_slot(self):
            self.kwargs["sleeper"](state.delay)
            self.kwargs["on_request_started"](clock.utc())

        def record_rate_limit(self):
            pass

        def snapshot(self):
            return SimpleNamespace(retry_not_before_utc=clock.utc() + timedelta(seconds=60))

    class TokenGate:
        def __init__(self, **kwargs):
            state.gates.append(kwargs)

        def token_request_is_due(self):
            return state.token_due

        def claim_token_request_start(self):
            return state.token_due

        def snapshot(self):
            return SimpleNamespace(
                next_token_request_not_before_utc=clock.utc() + timedelta(seconds=300)
            )

    native_class = script.endpoint.KisPaperDailyEndpointTransport

    def native(**kwargs):
        transport = native_class(**kwargs)
        transport._opener = wire
        return transport

    def acquire(**kwargs):
        state.locks.append(kwargs)
        return None if state.busy else object()

    monkeypatch.setattr(script.market, "load_kis_paper_market_data_config", load)
    monkeypatch.setattr(script.pace, "KisPaperMarketDataRateGate", RequestGate)
    monkeypatch.setattr(script.pace, "KisPaperMarketDataTokenStartGate", TokenGate)
    monkeypatch.setattr(script.endpoint, "KisPaperDailyEndpointTransport", native)
    monkeypatch.setattr(script.backfill, "_acquire_worker_lock", acquire)
    monkeypatch.setattr(
        script.backfill, "_release_worker_lock", lambda lock: state.releases.append(lock)
    )
    monkeypatch.setattr(
        script.storage,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **kwargs: state.floor,
    )

    runner = script.run_current_trio_context

    def run(**kwargs):
        return runner(
            invocation_id=INVOCATION,
            dotenv_path=tmp_path / "not-read.env",
            market_root=market,
            artifact_root=artifacts,
            clock=clock.utc,
            monotonic=clock.monotonic,
            sleeper=clock.sleep,
            **kwargs,
        )

    state.run = run
    return state


def receipt(state):
    return json.loads(
        (state.artifacts / script.ARTIFACT_SCOPE / INVOCATION / "receipt.json").read_bytes()
    )


def assert_redacted(state, result):
    rendered = json.dumps(result)
    for value in (KEY, SECRET, TOKEN, "20000.375", "10000.125"):
        assert value not in rendered
    for path in state.artifacts.rglob("*"):
        if path.is_file():
            assert all(
                v.encode() not in path.read_bytes() for v in (KEY, SECRET, TOKEN, "20000.375")
            )
    for path in state.market.rglob("*"):
        if path.is_file():
            assert all(v.encode() not in path.read_bytes() for v in (KEY, SECRET, TOKEN))


def test_three_native_gated_gets_one_cached_token_and_64_exact_private_closes(harness):
    state = harness
    result = state.run()
    assert result["status"] == "ready" and result["reason"] is None
    assert result["accepted_pages"] == result["daily_GET_attempts"] == 3
    assert result["token_POST_attempts"] == 1
    assert [method for method, _ in state.wire.calls] == ["POST", "GET", "GET", "GET"]
    assert [p["symbol"] for p in result["pages"]] == ["SPY", "TLT", "GLD"]
    assert [p["unique_date_count"] for p in result["pages"]] == [100] * 3
    assert len(state.loader_calls) == 1 and len(state.locks) == len(state.releases) == 1
    assert all(g["control_root"] == state.market / script.CONTROL_SCOPE for g in state.gates)
    assert state.clock.sleeps == [1.0] * 4
    private = json.loads((state.market / result["input_binding"]["context"]["path"]).read_bytes())
    assert tuple(map(len, private["closes"])) == (64, 64, 64)
    assert private["feature_cutoff"] == "2026-10-07T20:00:00Z"
    assert datetime.fromisoformat(private["decision_at"]) >= datetime.fromisoformat(
        result["started_at"]
    )
    assert all(
        datetime.fromisoformat(t) > datetime.fromisoformat(private["feature_cutoff"])
        for t in private["observed_at_by_symbol"]
    )
    assert private["facts"]["provider_publication_at"] == "not_observed"
    assert receipt(state)["status"] == "ready"
    assert_redacted(state, result)


def test_raw_and_typed_bytes_binding_readback_and_original_source_grade(harness):
    result = harness.run()
    for relative, digest in result["retained_files"].items():
        assert script._sha((harness.market / relative).read_bytes()) == digest
    for facts in result["pages"]:
        raw = harness.market / script.MARKET_SCOPE / INVOCATION / f"{facts['symbol']}.raw.json"
        assert script._sha(raw.read_bytes()) == facts["source_body_sha256"]
    assert result["PIT"] == "not_claimed" and result["MODP"] == "0_opaque"
    assert result["source_reattestation"] == "matched"


@pytest.mark.parametrize(
    "fault", ["auth", "token_not_due", "cooldown", "provider_first", "provider_second"]
)
def test_first_fault_stops_all_further_calls_without_token_renewal_or_secret_retention(
    harness, fault
):
    state = harness
    if fault == "auth":
        state.wire.token_failure = True
    elif fault == "token_not_due":
        state.token_due = False
    elif fault == "cooldown":
        state.delay = 60
    else:
        state.wire.get_failure = 1 if fault == "provider_first" else 2
    result = state.run()
    expected = {
        "auth": ("auth_rejected", 1, 0),
        "token_not_due": ("token_request_not_due", 0, 0),
        "cooldown": ("cooldown_not_due", 0, 0),
        "provider_first": ("daily_response_rejected", 2, 0),
        "provider_second": ("daily_response_rejected", 3, 1),
    }
    reason, calls, accepted = expected[fault]
    assert result["status"] == "input_unavailable" and result["reason"] == reason
    assert len(state.wire.calls) == calls and result["accepted_pages"] == accepted
    assert sum(m == "POST" for m, _ in state.wire.calls) <= 1
    assert result["input_binding"] is None
    if fault in {"token_not_due", "cooldown"}:
        assert result["next_due"] is not None and state.clock.sleeps == []
    assert receipt(state)["reason"] == reason
    assert_redacted(state, result)


@pytest.mark.parametrize("echo", [KEY, SECRET, TOKEN])
def test_successful_typed_market_body_with_credential_echo_is_never_retained(harness, echo):
    harness.wire.echo = echo
    result = harness.run()
    assert result["reason"] == "credential_echo_rejected" and result["accepted_pages"] == 0
    assert len(harness.wire.calls) == 2
    assert result["retained_files"] == {}
    assert_redacted(harness, result)


@pytest.mark.parametrize(
    "fault,reason", [("gap", "required_session_missing"), ("future", "endpoint_date_after_anchor")]
)
def test_current_date_or_required_gap_cannot_enter_context_or_trigger_more_gets(
    harness, fault, reason
):
    harness.wire.row_fault = fault
    result = harness.run()
    assert result["reason"] == reason and result["input_binding"] is None
    assert len(harness.wire.calls) == 2
    assert not any(p.name == "context.json" for p in harness.market.rglob("*"))


def test_unused_ohlcv_fault_not_promoted_or_silently_repaired(harness):
    harness.wire.row_fault = "unused"
    result = harness.run()
    assert result["status"] == "ready"
    assert all(
        p["unused_ohlcv_fault_counts"] == {"low_above_open_close": 1} for p in result["pages"]
    )
    assert all(p["strict_ohlcv_grade"] is False for p in result["pages"])


def test_capture_hash_mismatch_refuses_market_bytes_before_write(harness, monkeypatch):
    original = script.endpoint.KisPaperDailyEndpointClient.fetch_daily_endpoint_page

    def changed(client, query):
        return replace(original(client, query), source_body_sha256="sha256:" + "b" * 64)

    monkeypatch.setattr(
        script.endpoint.KisPaperDailyEndpointClient, "fetch_daily_endpoint_page", changed
    )
    result = harness.run()
    assert result["reason"] == "page_hash_mismatch" and result["retained_files"] == {}
    assert len(harness.wire.calls) == 2


@pytest.mark.parametrize("fault", ["busy", "floor", "offhours"])
def test_pre_dispatch_faults_have_zero_provider_and_credential_calls(harness, fault):
    if fault == "busy":
        harness.busy = True
    elif fault == "floor":
        harness.floor = True
    else:
        harness.clock.now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    result = harness.run()
    assert result["status"] == "input_unavailable"
    assert harness.wire.calls == harness.loader_calls == []
    assert result["accepted_pages"] == 0 and result["input_binding"] is None


def test_existing_invocation_is_not_overwritten_or_reissued(harness):
    harness.run()
    before = (harness.artifacts / script.ARTIFACT_SCOPE / INVOCATION / "receipt.json").read_bytes()
    calls = len(harness.wire.calls)
    with pytest.raises(script.Stop, match="invocation_exists"):
        harness.run()
    assert len(harness.wire.calls) == calls
    assert (
        harness.artifacts / script.ARTIFACT_SCOPE / INVOCATION / "receipt.json"
    ).read_bytes() == before


def test_runtime_deadline_never_foreground_sleeps_or_issues_another_request(harness):
    harness.wire.after_get = lambda n: harness.clock.advance(120)
    result = harness.run()
    assert result["reason"] == "runtime_budget" and len(harness.wire.calls) == 2
    assert result["daily_GET_attempts"] == 1  # Late first response stops before a second dispatch.
    assert "not independently measured wire starts" in result["count_semantics"]


def test_late_final_get_at_124_8_seconds_cannot_publish_ready_or_retain_late_body(harness):
    harness.wire.after_get = lambda n: harness.clock.advance(120) if n == 3 else None
    result = harness.run()
    stored = receipt(harness)
    assert result["elapsed_seconds"] == pytest.approx(124.8)
    assert result["status"] == stored["status"] == "input_unavailable"
    assert result["reason"] == stored["reason"] == "runtime_budget"
    assert result["input_binding"] is stored["input_binding"] is None
    assert result["daily_GET_attempts"] == 3 and result["token_POST_attempts"] == 1
    assert result["accepted_pages"] == 2 and len(result["retained_files"]) == 4
    assert len(harness.wire.calls) == 4
    assert not (harness.market / script.MARKET_SCOPE / INVOCATION / "GLD.raw.json").exists()
    assert_redacted(harness, result)


def test_context_write_overrun_keeps_all_evidence_but_not_a_usable_binding(harness, monkeypatch):
    original = script.storage._write_bytes_and_sync

    def write(path, data):
        original(path, data)
        if path.name == "context.json":
            harness.clock.advance(121)

    monkeypatch.setattr(script.storage, "_write_bytes_and_sync", write)
    result = harness.run()
    assert result["reason"] == receipt(harness)["reason"] == "runtime_budget"
    assert result["input_binding"] is None
    assert result["accepted_pages"] == result["daily_GET_attempts"] == 3
    assert len(result["retained_files"]) == 8
    for relative, digest in result["retained_files"].items():
        assert script._sha((harness.market / relative).read_bytes()) == digest
    private = json.loads(
        (harness.market / script.MARKET_SCOPE / INVOCATION / "context.json").read_bytes()
    )
    assert tuple(map(len, private["closes"])) == (64, 64, 64)


@pytest.mark.parametrize("phase", ["staged_write", "rename", "receipt_read"])
def test_late_terminal_publication_never_leaves_ready_receipt_or_stdout(
    harness, monkeypatch, phase
):
    original_write = script.storage._write_bytes_and_sync
    original_rename = Path.rename
    original_read = Path.read_bytes
    triggered = False

    def delay_once():
        nonlocal triggered
        if not triggered:
            triggered = True
            harness.clock.advance(121)

    def write(path, data):
        original_write(path, data)
        if phase == "staged_write" and path.name == "receipt.pending.json":
            delay_once()

    def rename(path, target):
        renamed = original_rename(path, target)
        if phase == "rename" and path.name == "receipt.pending.json":
            delay_once()
        return renamed

    def read(path):
        data = original_read(path)
        if phase == "receipt_read" and path.name == "receipt.json":
            delay_once()
        return data

    monkeypatch.setattr(script.storage, "_write_bytes_and_sync", write)
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(Path, "read_bytes", read)
    result = harness.run()
    stored = receipt(harness)
    assert triggered and result["elapsed_seconds"] > 120
    assert result["status"] == stored["status"] == "input_unavailable"
    assert result["reason"] == stored["reason"] == "runtime_budget"
    assert result["input_binding"] is stored["input_binding"] is None
    assert result["daily_GET_attempts"] == stored["accepted_pages"] == 3
    assert result["token_POST_attempts"] == 1 and len(result["retained_files"]) == 8
    actual_path = harness.artifacts / script.ARTIFACT_SCOPE / INVOCATION / "receipt.json"
    assert result["receipt_sha256"] == script._sha(actual_path.read_bytes())
    evidence = actual_path.with_name(
        "receipt.pending.json" if phase == "staged_write" else "receipt.overdeadline.json"
    )
    assert json.loads(evidence.read_bytes())["status"] == "ready"
    assert_redacted(harness, result)


def test_final_source_reattestation_overrun_downgrades_already_prepared_context(
    harness, monkeypatch
):
    def pins(root):
        if (harness.market / script.MARKET_SCOPE / INVOCATION / "context.json").exists():
            harness.clock.advance(121)
        return {"pure": script.CONTEXT_PIN}

    monkeypatch.setattr(script, "_source_pins", pins)
    result = harness.run()
    assert result["source_reattestation"] == "matched"
    assert result["reason"] == receipt(harness)["reason"] == "runtime_budget"
    assert result["input_binding"] is None and result["accepted_pages"] == 3
    assert len(harness.wire.calls) == 4


def test_post_dispatch_source_read_failure_preserves_terminal_and_known_counts(
    harness, monkeypatch
):
    def pins(root):
        if harness.wire.gets == 3:
            raise OSError(SECRET)
        return {"pure": script.CONTEXT_PIN}

    monkeypatch.setattr(script, "_source_pins", pins)
    result = harness.run()
    assert result["reason"] == "source_hash_unavailable" and result["input_binding"] is None
    assert result["accepted_pages"] == 3 and result["daily_GET_attempts"] == 3
    assert result["source_pins"] == {"pure": script.CONTEXT_PIN}
    assert result["source_reattestation"] == "unavailable"
    assert receipt(harness)["reason"] == "source_hash_unavailable"
    assert_redacted(harness, result)


def test_source_changed_blocks_ready_claim_without_losing_accepted_pages(harness, monkeypatch):
    monkeypatch.setattr(
        script,
        "_source_pins",
        lambda root: {
            "pure": script.CONTEXT_PIN if harness.wire.gets < 3 else "sha256:" + "b" * 64
        },
    )
    result = harness.run()
    assert result["reason"] == "source_hash_changed" and result["accepted_pages"] == 3
    assert result["source_reattestation"] == "changed" and result["input_binding"] is None


def test_retention_write_fault_preserves_nonzero_attempts_and_no_ready_claim(harness, monkeypatch):
    original = script.storage._write_bytes_and_sync

    def write(path, data):
        if path.name == "SPY.raw.json":
            raise OSError(SECRET)
        return original(path, data)

    monkeypatch.setattr(script.storage, "_write_bytes_and_sync", write)
    result = harness.run()
    assert result["reason"] == "local_io_unavailable" and result["daily_GET_attempts"] == 1
    assert result["accepted_pages"] == 1 and receipt(harness)["status"] == "input_unavailable"
    assert_redacted(harness, result)


def test_inert_cli_does_not_read_clock_config_files_or_source(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("inert mode accessed runtime")

    monkeypatch.setattr(script, "run_current_trio_context", forbidden)
    monkeypatch.setattr(script.market, "load_kis_paper_market_data_config", forbidden)
    monkeypatch.setattr(script, "_source_pins", forbidden)
    assert script.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "not_executed"


def test_execute_cli_outputs_only_safe_projection_with_success_exit(harness, monkeypatch, capsys):
    monkeypatch.setattr(script, "run_current_trio_context", lambda **kwargs: harness.run())
    assert script.main(["--execute", "--invocation-id", INVOCATION]) == 0
    output = capsys.readouterr().out
    assert (
        KEY not in output
        and SECRET not in output
        and TOKEN not in output
        and "20000.375" not in output
    )
    assert json.loads(output)["status"] == "ready"


def test_existing_selective_loader_reads_only_named_paper_keys_without_live_values(
    harness, monkeypatch
):
    class NamedEnvironment(dict):
        def get(self, name, default=None):
            assert name in {"THERICHER_MODE", "KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET"}
            return super().get(name, default)

        def items(self):
            pytest.fail("excluded environment values materialized")

    # The runner calls this existing loader once; exercise its source-owned selective helper.
    env = NamedEnvironment(
        KIS_PAPER_APP_KEY=KEY, KIS_PAPER_APP_SECRET=SECRET, KIS_LIVE_APP_KEY="never-read"
    )
    config = script.market._load_kis_paper_market_data_environment_config(env)
    assert config.app_key == KEY and config.app_secret == SECRET


def test_original_research_cohort_is_not_read_or_rewritten(harness):
    sentinel = harness.market / "frozen-4a.json"
    sentinel.write_bytes(b"synthetic-frozen-cohort-not-input")
    before = sentinel.read_bytes()
    assert harness.run()["status"] == "ready"
    assert sentinel.read_bytes() == before
    assert all("frozen-4a" not in n for n in receipt(harness)["retained_files"])


@pytest.mark.parametrize("change", ["live_host", "order_post", "unknown_symbol", "wrong_anchor"])
def test_capture_fixed_allowlist_refuses_wrong_host_route_symbol_or_anchor_before_delegate(change):
    delegate = SimpleNamespace(
        request=lambda request: pytest.fail("invalid request reached delegate")
    )
    capture = script._CaptureTransport(
        delegate,
        check=lambda: None,
        check_deadline=lambda: None,
        clock=lambda: datetime.now(UTC),
        anchor="20261007",
    )
    request = KisMarketDataRequest(
        "GET",
        script.market.KIS_PAPER_MARKET_DATA_BASE_URL + script.market.KIS_PAPER_DAILY_PATH,
        dict(tr_id=script.market.KIS_PAPER_DAILY_TR_ID, tr_cont=""),
        query=dict(AUTH="", EXCD="AMS", SYMB="SPY", GUBN="0", BYMD="20261007", MODP="0"),
    )
    if change == "live_host":
        request = replace(
            request, url="https://example.invalid" + script.market.KIS_PAPER_DAILY_PATH
        )
    elif change == "order_post":
        request = replace(
            request, method="POST", url=script.market.KIS_PAPER_MARKET_DATA_BASE_URL + "/order"
        )
    else:
        query = dict(request.query)
        query["SYMB" if change == "unknown_symbol" else "BYMD"] = (
            "QQQ" if change == "unknown_symbol" else "20261008"
        )
        request = replace(request, query=query)
    with pytest.raises(script.Stop, match="request_not_allowlisted"):
        capture.request(request)


def test_source_pins_bind_actual_import_origins_and_exact_pure_module(tmp_path, monkeypatch):
    source = tmp_path / "synthetic-source"
    path = source / "src/thericher_v2/data/kis_current_trio_context.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic public module")
    name = path.relative_to(source).as_posix()
    monkeypatch.setattr(script, "SOURCE_ORIGINS", {name: path})
    monkeypatch.setattr(script, "CONTEXT_PIN", script._sha(path.read_bytes()))
    assert script._source_pins(source) == {name: script.CONTEXT_PIN}
    path.write_bytes(b"changed source")
    with pytest.raises(script.Stop, match="source_hash_changed"):
        script._source_pins(source)


def test_wrong_root_rejects_before_any_runtime_or_file_creation(harness):
    with pytest.raises(script.Stop, match="local_contract_invalid"):
        script._root(ROOT / "market-data", harness.market, ROOT)
    assert harness.wire.calls == harness.loader_calls == []


def test_linked_scope_directory_rejects_before_credentials_or_provider(harness, monkeypatch):
    linked = harness.market / script.MARKET_SCOPE
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == linked or original(p))
    linked.mkdir(parents=True)
    with pytest.raises(script.Stop, match="local_contract_invalid"):
        harness.run()
    assert harness.wire.calls == harness.loader_calls == []


def test_unexpected_transport_exception_is_categorical_and_keeps_attempt_counts(
    harness, monkeypatch
):
    def fail(request, timeout):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(harness.wire, "open", fail)
    result = harness.run()
    assert result["reason"] == "local_unexpected_failure"
    assert result["token_POST_attempts"] == 1
    assert receipt(harness)["reason"] == "local_unexpected_failure"
    assert_redacted(harness, result)


def test_release_failure_cannot_leave_ready_terminal_behind_unavailable_stdout(
    harness, monkeypatch
):
    def fail(lock):
        raise OSError(SECRET)

    monkeypatch.setattr(script.backfill, "_release_worker_lock", fail)
    result = harness.run()
    stored = receipt(harness)
    assert result["status"] == stored["status"] == "input_unavailable"
    assert result["reason"] == stored["reason"] == "local_io_unavailable"
    assert stored["accepted_pages"] == stored["daily_GET_attempts"] == 3
    assert result["input_binding"] is stored["input_binding"] is None
    assert_redacted(harness, result)


def test_initial_source_read_failure_has_terminal_with_zero_attempts(harness, monkeypatch):
    def fail(root):
        raise OSError(SECRET)

    monkeypatch.setattr(script, "_source_pins", fail)
    result = harness.run()
    assert result["reason"] == "source_hash_unavailable"
    assert result["token_POST_attempts"] == result["daily_GET_attempts"] == 0
    assert receipt(harness)["source_reattestation"] == "unavailable"
    assert harness.wire.calls == harness.loader_calls == []
    assert_redacted(harness, result)


def test_source_import_origin_mismatch_rejects_same_bytes_from_wrong_tree(tmp_path, monkeypatch):
    path = tmp_path / "actual-source.py"
    path.write_bytes(b"synthetic public module")
    root = tmp_path / "claimed-source"
    other = root / "source.py"
    other.parent.mkdir()
    other.write_bytes(path.read_bytes())
    monkeypatch.setattr(script, "SOURCE_ORIGINS", {"source.py": path})
    with pytest.raises(script.Stop, match="source_import_origin_mismatch"):
        script._source_pins(root)


def test_runner_source_has_no_account_loader_or_order_routes():
    source = Path(SPEC.origin).read_text()
    assert "load_kis_paper_config(" not in source
    assert "KIS_LIVE_" not in source
    assert "authenticate_token_only(" not in source
    assert "preview_orderable" not in source
