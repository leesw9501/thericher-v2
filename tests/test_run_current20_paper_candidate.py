"""Invented allocation fixtures and native boundaries; no broker, Docker or Task."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import socket
import subprocess
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.execution import kis_readonly as readonly
from thericher_v2.research import current20_paper_candidate as candidate

REPO = Path(__file__).resolve().parents[1]
IMAGE = "sha256:" + "a" * 64
IDENTITY = "b" * 32
NOW = datetime(2026, 10, 19, 15, 10, tzinfo=UTC)
DECISION = datetime(2026, 10, 18, 1, tzinfo=UTC)


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


host = load("current20_test_host", "scripts/run_current20_paper_candidate.py")
worker = load("current20_test_worker", "scripts/run_current20_paper_candidate_worker.py")


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    def deny(*_args, **_kwargs):
        pytest.fail("actual_network_credentials_Docker_Task_forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(host, "_docker", deny)
    monkeypatch.setattr(host.subprocess, "Popen", deny)


def put(path, value):
    raw = value if isinstance(value, bytes) else host._encode(value)
    host._new(path, raw)
    return host._sha(raw)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    # SYN bytes only, never read or materialize the actual f9 bundle/allocation.
    import numpy as np

    monkeypatch.setattr(host, "ARTIFACT", tmp_path)
    monkeypatch.setattr(worker, "ARTIFACT", tmp_path)
    monkeypatch.setattr(worker, "CONTROL", tmp_path / "control")
    monkeypatch.setattr(worker, "_host", lambda: host)
    stream = io.BytesIO()
    matrix = np.zeros((2, 17))
    matrix[0, :5] = 0.2
    np.savez(stream, weights=matrix, source_slots=np.arange(3, 20), entry_ordinal=np.array(5230))
    weights = stream.getvalue()
    wp = put(tmp_path / "synthetic/weights.npz", weights)
    bundle = dict(
        tradable_order=candidate.STOCK_KEYS,
        policies=[candidate.POLICY, "synthetic_cash"],
        binding_sha256=candidate.SOURCE_BINDING_SHA256,
        weights_sha256=wp[7:],
        immutable_seal_utc=candidate.PUBLICATION.isoformat(),
        logical_previous_close_utc=candidate.FEATURE_CLOSE.isoformat(),
        actual_source_observed_utc=candidate.SOURCE_OBSERVED.isoformat(),
        model_output_written_by_utc=candidate.INFERENCE_COMPLETED.isoformat(),
    )
    bp = put(tmp_path / "synthetic/bundle.json", bundle)
    monkeypatch.setattr(candidate, "BUNDLE_SHA256", bp[7:])
    monkeypatch.setattr(candidate, "WEIGHTS_SHA256", wp[7:])
    defaults = candidate.Current20PaperMetadata.__init__.__defaults__
    monkeypatch.setattr(
        candidate.Current20PaperMetadata.__init__, "__defaults__", (bp, wp, *defaults[2:])
    )
    day, dates = date(2026, 10, 19), []
    while day <= date(2026, 11, 16):
        if us_equity_2026_session(day) is not None:
            dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    data = dict(
        clocks=dict(
            candidate_available_utc=candidate.PUBLICATION.isoformat(),
            source_available_utc=candidate.SOURCE_OBSERVED.isoformat(),
            output_written_by_utc=candidate.INFERENCE_COMPLETED.isoformat(),
            context_close_utc=candidate.FEATURE_CLOSE.isoformat(),
        ),
        frozen_output=dict(bundle_ref=dict(sha256=bp[7:])),
        calendar=dict(
            expected_session_dates=dates,
            entry=dict(open_utc="2026-10-19T13:30:00Z", close_utc="2026-10-19T20:00:00Z"),
            exit=dict(
                session_date="2026-11-17",
                open_utc="2026-11-17T14:30:00Z",
                close_utc="2026-11-17T21:00:00Z",
            ),
        ),
    )
    dp = put(tmp_path / "synthetic/data.json", data)
    monkeypatch.setattr(host, "DATA_BINDING_SHA256", dp[7:])
    contract = dict(
        schema="current20_equalrank4_provisional_paper_contract_v1",
        candidate_id=candidate.CANDIDATE_ID,
        policy=candidate.POLICY,
        signal_bundle_sha256=bp[7:],
        prediction_sha256=candidate.PREDICTIONS_SHA256,
        weights_sha256=wp[7:],
        independent_shadow_readback_sha256=candidate.SHADOW_REVIEW_SHA256,
        entry_us_session="2026-10-19",
        latest_completed_feature_session="2026-10-16",
        earliest_owned_exit_us_session="2026-11-17",
        desired_targets=5,
        original_basis_fraction_per_target="0.005",
        maximum_original_basis_fraction_for_new_candidate="0.025",
    )
    cp = put(tmp_path / "synthetic/contract.json", contract)
    options = dict(
        parent_contract=tmp_path / "synthetic/contract.json",
        parent_contract_ref=cp,
        data_binding=tmp_path / "synthetic/data.json",
        data_binding_ref=dp,
        bundle=tmp_path / "synthetic/bundle.json",
        weights=tmp_path / "synthetic/weights.npz",
        clock=lambda: DECISION,
    )
    result = host.prepare_input(**options)
    source = tmp_path / "synthetic/source.json"
    sp = put(source, dict(files=host.source_map()))
    options = dict(
        input_manifest=Path(result["input_manifest"]),
        input_manifest_ref=result["input_manifest_ref"],
        source_manifest=source,
        source_manifest_ref=sp,
    )
    return SimpleNamespace(options=options, result=result, prepare=options, cp=cp, root=tmp_path)


def test_default_and_help_are_inert_before_all_reads(monkeypatch, capsys):
    monkeypatch.setattr(host, "read_source_manifest", lambda *a: pytest.fail("inert read"))
    monkeypatch.setattr(worker, "_helpers", lambda: pytest.fail("inert helper"))
    stdin = io.BytesIO(b"not-consumed")
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=stdin))
    assert host.run()["status"] == worker.run()["status"] == "inert"
    assert host.main([]) == worker.main([]) == 0
    for entry in (host.main, worker.main):
        with pytest.raises(SystemExit) as exc:
            entry(["--help"])
        assert exc.value.code == 0
    assert stdin.tell() == 0
    assert "synthetic-secret" not in capsys.readouterr().out


def test_real_prepare_serialize_load_to_native_profile_reference_pair(prepared, monkeypatch):
    document, value = worker.load_input(
        **dict(
            path=prepared.options["input_manifest"],
            pin=prepared.options["input_manifest_ref"],
            source_manifest=prepared.options["source_manifest"],
            source_manifest_ref=prepared.options["source_manifest_ref"],
        )
    )
    assert document["payload_ref"] != value.input_ref == document["input_ref"]
    assert value.policy_ref == prepared.cp
    assert value.profile is cycle.StockCycleProfile.CURRENT20_EQUALRANK4
    assert all(
        t.proposal.valid_until == datetime(2026, 10, 19, 20, tzinfo=UTC) for t in value.targets
    )
    assert value.targets[0].proposal.decided_at == DECISION
    seen = []

    def native_visit(**arguments):
        seen.append(arguments)
        assert arguments["profile"] is cycle.StockCycleProfile.CURRENT20_EQUALRANK4
        assert arguments["expected_input_ref"] == value.input_ref
        assert arguments["expected_policy_ref"] == value.policy_ref
        assert (
            cycle._validate_input(arguments["target_loader"](), NOW, arguments["profile"]) == value
        )
        return cycle.CurrentStockCycleOutcome("hold", "await_declared_exit", 0)

    monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", native_visit)
    native = worker._helpers()
    expected_paths = native.native_paths()
    config = readonly.KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01")
    result = worker.run(
        config, execute=True, **prepared.options, owner_ready=lambda: None, clock=lambda: NOW
    )
    assert result["status"] == "hold" and len(seen) == 1
    assert all(seen[0][key] == path for key, path in expected_paths.items())
    assert host.validate_result(result) == result
    assert not (prepared.root / host.RUNTIME_RELATIVE / "private").exists()


@pytest.mark.parametrize(
    "field", ["input_ref", "policy_ref", "payload_ref", "data_binding", "decided_at"]
)
def test_semantic_or_byte_or_clock_alias_rejected_before_native(prepared, field):
    path = prepared.options["input_manifest"]
    doc = json.loads(path.read_bytes())
    doc[field] = (
        "sha256:" + "f" * 64 if field != "data_binding" else dict(path="../foreign", ref=IMAGE)
    )
    raw = host._encode(doc)
    path.write_bytes(raw)
    with pytest.raises((ValueError, TypeError)):
        host.read_input_manifest(path, host._sha(raw))


def test_source_pin_precedes_host_credentials_and_namespace_is_create_once(prepared):
    opts = dict(prepared.options, source_manifest_ref=IMAGE)
    with pytest.raises(ValueError, match="pin_mismatch"):
        host.run(execute=True, image=IMAGE, **opts)
    with pytest.raises(FileExistsError):
        host._new(prepared.options["input_manifest"], b"not-overwritten")
    assert (
        host._json(prepared.options["input_manifest"].read_bytes())["kind"]
        == "current20-paper-native-input-v1"
    )


def request(native, key):
    return readonly.KisHttpRequest(
        method="GET" if key == "get_requests" else "POST",
        url="https://openapivts.koreainvestment.com:29443"
        + (
            readonly.KIS_PAPER_TOKEN_PATH
            if key == "token_posts"
            else native.canary.KIS_PAPER_US_CANCEL_PATH
            if key == "cancel_posts"
            else "/synthetic"
        ),
        headers={
            "tr_id": native.canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
            if key == "buy_posts"
            else "synthetic"
        },
        query={},
        json_body=None,
    )


def test_scoped_budget_get_local_binding_post_fresh_owner_after_pacing(tmp_path, monkeypatch):
    events = []
    native = worker._helpers()
    limits = worker.request_budget(
        control_root=tmp_path,
        owner_ready=lambda: events.append("owner"),
        bindings_ready=lambda: events.append("pins"),
        monotonic=lambda: 0,
        clock=lambda: NOW,
    )
    limits.rate = SimpleNamespace(wait_for_request_slot=lambda: events.append("pace"))
    limits.token = SimpleNamespace(claim_token_request_start=lambda: True)
    limits.pacer = SimpleNamespace(record_request_start=lambda: events.append("record"))
    limits.start(request(native, "get_requests"), lambda: events.append("native"))
    assert events == ["pace", "pins", "native", "record"]
    events.clear()
    limits.start(request(native, "token_posts"), lambda: events.append("native"))
    assert events == ["pace", "pins", "owner", "native", "record"]
    assert limits.calls["token_posts"] == 1
    with pytest.raises(native.canary.KisPaperCanaryError):
        limits.start(request(native, "token_posts"), None)


def test_owner_denial_prevents_post_delegate_or_debit(tmp_path):
    native = worker._helpers()
    events = []

    def deny():
        events.append("deny")
        raise ValueError("owner_busy")

    limits = worker.request_budget(control_root=tmp_path, owner_ready=deny, clock=lambda: NOW)
    limits.rate = SimpleNamespace(wait_for_request_slot=lambda: events.append("pace"))
    with pytest.raises(ValueError, match="owner_busy"):
        limits.start(request(native, "buy_posts"), lambda: events.append("POST_delegate"))
    assert events == ["pace", "deny"] and sum(limits.calls.values()) == 0


@pytest.mark.parametrize("cap", ["orders", "cancels", "total", "wall"])
def test_new_caps_and_legacy_defaults_unchanged(tmp_path, cap):
    native = worker._helpers()
    limits = worker.request_budget(
        control_root=tmp_path / "new",
        owner_ready=lambda: None,
        monotonic=lambda: 0,
        clock=lambda: NOW,
    )
    old = native.RequestBudget(
        control_root=tmp_path / "old", monotonic=lambda: 0, clock=lambda: NOW
    )
    assert old.deadline == 280 and limits.deadline == 150
    if cap == "orders":
        old.calls["buy_posts"] = 1
        with pytest.raises(native.canary.KisPaperCanaryError):
            old._check("sell_posts")
        limits.calls.update(buy_posts=3, sell_posts=1)
        limits._check("sell_posts")
        limits.calls["sell_posts"] = 2
        key = "buy_posts"
    elif cap == "cancels":
        limits.calls["cancel_posts"] = 5
        key = "cancel_posts"
    elif cap == "total":
        limits.calls["get_requests"] = 128
        key = "get_requests"
    else:
        limits.monotonic = lambda: 142
        key = "get_requests"
    with pytest.raises(native.canary.KisPaperCanaryError):
        limits._check(key)


def test_one_native_factory_token_shared_without_order_or_network(tmp_path, monkeypatch):
    native = worker._helpers()
    requests = []

    class FakeTransport:
        def __init__(self, **_):
            pass

        def request(self, req):
            requests.append(req)
            assert req.url.endswith(readonly.KIS_PAPER_TOKEN_PATH)
            return readonly.KisHttpResponse.from_payload(dict(access_token="synthetic-token"))

    monkeypatch.setattr(native, "OwnedTransport", FakeTransport)
    factory = native.client_factory(
        readonly.KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01"), None
    )
    for symbol in ("AAPL", "MSFT", "AMZN", "GOOG", "NVDA"):
        item = native.KisPaperStockInstrument(symbol, "ref:" + "f" * 64)
        assert factory(item) is factory(item)
        assert factory(item)._access_token == "synthetic-token"
    assert len(requests) == 1


def test_public_inert_command_has_no_mount_execute_uses_same_bank(prepared):
    inert = host.command(IMAGE, IDENTITY)
    assert inert[inert.index("--network") + 1] == "none"
    assert "--mount" not in inert and "--execute" not in inert
    active = host.command(IMAGE, IDENTITY, execute=True, **prepared.options)
    assert host.LABEL + "=" + IDENTITY in active
    assert host.PREFIX + IDENTITY in active and "150" in active
    assert "/app/" + host.WORKER in active and "--owner-admission-stdio" in active
    for volume in host._legacy().VOLUMES:
        assert any("source=" + volume + "," in item for item in active)
    assert not any("KIS_" in item or ".env" in item for item in active)


@pytest.mark.parametrize("fault", ["sequence", "false", "extra", "oversize", "stale"])
def test_worker_owner_frames_fail_closed(fault, monkeypatch):
    frame = dict(kind="current20-owner-answer-v1", sequence=1, ready=True)
    if fault == "sequence":
        frame["sequence"] = 2
    elif fault == "false":
        frame["ready"] = False
    elif fault == "extra":
        frame["private"] = "never-forward"
    raw = host._encode(frame) + b"\n"
    if fault == "oversize":
        raw = b"x" * 4097
    times = iter([0, 14 if fault == "stale" else 0])
    monkeypatch.setattr(worker, "_host", lambda: host)
    with pytest.raises(ValueError):
        worker.OwnerAdmission(io.BytesIO(raw), io.StringIO(), monotonic=lambda: next(times))()


def test_owner_frame_roundtrip_and_maximum(monkeypatch):
    monkeypatch.setattr(worker, "_host", lambda: host)
    sink = io.StringIO()
    admission = worker.OwnerAdmission(
        io.BytesIO(
            host._encode(dict(kind="current20-owner-answer-v1", sequence=1, ready=True)) + b"\n"
        ),
        sink,
    )
    admission()
    assert json.loads(sink.getvalue()) == dict(kind="current20-owner-request-v1", sequence=1)
    admission.sequence = 128
    with pytest.raises(ValueError, match="count_exhausted"):
        admission()


def test_outer_unobserved_failure_never_fabricates_zero_calls(prepared, monkeypatch, capsys):
    monkeypatch.setattr(worker, "_no_model_runtime", lambda: None)
    packet = dict(
        KIS_PAPER_APP_KEY="synthetic-key",
        KIS_PAPER_APP_SECRET="synthetic-secret",
        KIS_PAPER_ACCOUNT_NO="12345678",
        KIS_PAPER_ACCOUNT_PRODUCT_CODE="01",
        THERICHER_MODE="kis_paper",
    )
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(host._encode(packet) + b"\n"))
    )
    monkeypatch.setattr(
        worker, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("after_unknown"))
    )
    argv = ["--execute", "--owner-admission-stdio"]
    for key, value in prepared.options.items():
        argv += ["--" + key.replace("_", "-"), str(value)]
    assert worker.main(argv) == 20
    result = json.loads(capsys.readouterr().out)
    assert result["request_counts"] == "unknown" and "calls" not in result
    assert host.validate_result(result) == result


def test_actual_calendar_window_and_exact31_slot_launch_binding(prepared):
    assert len(host.planned_slots()) == 31 and len(set(host.planned_slots())) == 31
    assert host.planned_slots()[0] == "2026-10-19T15:10:00Z"
    assert host.planned_slots()[-1] == "2026-11-20T15:10:00Z"
    assert host.execution_window(NOW)
    assert host.execution_window(datetime(2026, 11, 20, 15, 10, tzinfo=UTC))
    assert not host.execution_window(datetime(2026, 10, 18, 15, 10, tzinfo=UTC))
    assert not host.execution_window(datetime(2026, 10, 19, 20, tzinfo=UTC))
    probe = prepared.root / "synthetic/probe.ps1"
    pp = put(probe, b"# synthetic only\n")
    result = host.write_launch_binding(
        image=IMAGE, **prepared.options, owner_probe=probe, owner_probe_ref=pp
    )
    binding = json.loads(Path(result["binding_path"]).read_bytes())
    assert binding["task_name"] == "thericher-kis-paper-current20-equalrank4-20261018"
    assert binding["argv"][1:3] == ["-I", "-B"]
    assert binding["executable"] == str(host.PYTHONW)
    assert binding["arguments"] == subprocess.list2cmdline(binding["argv"][1:])
    assert (
        binding["multiple_instances"] == "IgnoreNew" and binding["execution_time_limit"] == "PT5M"
    )
    assert binding["input_manifest_ref"] == prepared.options["input_manifest_ref"]
    assert binding["status"].endswith("NOT_INVOCATION")


@pytest.mark.parametrize("fault", ["private", "nan", "count", "reason"])
def test_projection_rejects_private_or_unbounded_native_output(prepared, monkeypatch, fault):
    monkeypatch.setattr(
        worker, "load_input", lambda *a: (_ for _ in ()).throw(ValueError("synthetic"))
    )
    result = worker.run(None, execute=True, owner_ready=lambda: None)
    result = copy.deepcopy(result)
    if fault == "private":
        result["secret"] = "never-forward"
    elif fault == "nan":
        result["http_start_gaps_seconds"] = [float("nan")]
    elif fault == "count":
        result["calls"]["buy_posts"] = 6
    else:
        result["outcomes"][0]["reason"] = "private-body"
    with pytest.raises(ValueError):
        host.validate_result(result)


@pytest.mark.parametrize("fault", [None, "duplicate_sequence", "private_frame", "exit_mismatch"])
def test_duplex_host_worker_exchange_is_finite_and_exact(monkeypatch, fault):
    result = dict(
        kind=host.KIND,
        status="unavailable",
        reason="native_recovery_required",
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        request_counts="unknown",
    )
    frames = [dict(kind="current20-owner-request-v1", sequence=1), result]
    if fault == "duplicate_sequence":
        frames.insert(1, frames[0])
    elif fault == "private_frame":
        frames[0]["raw"] = "never-forward"

    class Sink(io.BytesIO):
        def close(self):
            self.saved = self.getvalue()
            super().close()

    class Process:
        def __init__(self):
            self.stdin = Sink()
            self.stdout = io.BytesIO(b"".join(host._encode(v) + b"\n" for v in frames))
            self.code = None

        def wait(self, **_):
            self.code = 0 if fault == "exit_mismatch" else 20
            return self.code

        def poll(self):
            return self.code

        def kill(self):
            self.code = -1

    process = Process()
    monkeypatch.setattr(host.subprocess, "Popen", lambda *a, **k: process)
    admissions = []

    def call():
        return host._exchange(
            ["synthetic-not-Docker"],
            b"synthetic-packet",
            lambda n: admissions.append(n) or True,
            environment={},
        )

    if fault:
        with pytest.raises(ValueError):
            call()
    else:
        assert call() == result
        assert admissions == [1]
        lines = process.stdin.saved.splitlines()
        assert lines[0] == b"synthetic-packet"
        assert host._json(lines[1]) == dict(
            kind="current20-owner-answer-v1", sequence=1, ready=True
        )
    assert process.poll() is not None


@pytest.mark.parametrize("terminal_frame", [True, False])
def test_silent_get_work_uses_absolute_deadline_not_queue_poll_timeout(monkeypatch, terminal_frame):
    ticks = [0.0]
    result = dict(
        kind=host.KIND,
        status="unavailable",
        reason="native_recovery_required",
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        request_counts="unknown",
    )

    class Process:
        stdin = io.BytesIO()
        stdout = io.BytesIO()
        code = None
        killed = False

        def poll(self):
            return self.code

        def wait(self, **_):
            if self.code is None:
                self.code = 20
            return self.code

        def kill(self):
            self.killed, self.code = True, -1

    class VirtualQueue:
        def __init__(self, **_):
            pass

        def get(self, *, timeout):
            if terminal_frame and ticks[0] + timeout >= 16:
                ticks[0] = 16
                return host._encode(result) + b"\n"
            ticks[0] += timeout
            raise host.queue.Empty

    class QuietReader:
        def __init__(self, **_):
            pass

        def start(self):
            pass

        def is_alive(self):
            return True

        def join(self, **_):
            pass

    process = Process()
    monkeypatch.setattr(host.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(host.queue, "Queue", VirtualQueue)
    monkeypatch.setattr(host.threading, "Thread", QuietReader)

    def exchange():
        return host._exchange(
            ["synthetic-not-Docker"],
            b"synthetic-packet",
            lambda _: pytest.fail("GET_work_does_not_request_POST_admission"),
            environment={},
            monotonic=lambda: ticks[0],
            deadline=31,
        )

    if terminal_frame:
        assert exchange() == result
        assert ticks[0] == 16 and not process.killed
    else:
        with pytest.raises(ValueError, match="worker_wall_exhausted"):
            exchange()
        assert ticks[0] == 31 and process.killed
