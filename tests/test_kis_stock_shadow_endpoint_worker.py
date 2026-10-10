"""Price-only worker integration with synthetic pages and isolated local storage."""

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_stock_shadow_endpoint as endpoint
from thericher_v2.data import kis_stock_shadow_endpoint_storage as storage
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_market_data as market
from thericher_v2.execution import kis_private_daily_backfill as locks
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

SOURCE = Path(__file__).resolve().parents[1] / "scripts/collect_kis_stock_shadow_endpoints.py"
spec = importlib.util.spec_from_file_location("shadow_endpoint_runner_test", SOURCE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
PIN = "sha256:" + "a" * 64


@pytest.fixture
def case(tmp_path, monkeypatch):
    for name, suffix in (("ROOT", "artifacts"), ("MARKET", "market"), ("CONTROL", "control")):
        monkeypatch.setattr(worker, name, tmp_path / suffix)
    monkeypatch.setattr(worker, "REPO", tmp_path / "repo")
    peers = tuple(endpoint.EndpointPeer(f"key-{i}", f"S{i}", "NAS") for i in range(42))
    session = us_equity_2026_session(date(2026, 10, 12))
    scope = endpoint.EndpointScope(
        peers,
        endpoint.peer_sha256(peers),
        worker.CLOSURE,
        CrossAssetSession(session.session_date, session.window.open_ts, session.window.close_ts),
        datetime(2026, 10, 9, 23, tzinfo=UTC),
    )
    binding = storage.StorageBinding(
        scope,
        "entry",
        PIN,
        (
            ("endpoint_worker.py", storage.ENDPOINT_WORKER_SHA256),
            ("runner.py", PIN),
        ),
    )
    binding.record()
    monkeypatch.setattr(worker, "runtime", lambda *a: (endpoint, storage, binding))
    monkeypatch.setattr(worker, "load_job", lambda *a: ({}, {}))
    calls = SimpleNamespace(config=0, fetch=0, token=0, daily=0, locks=0, releases=0)
    state = SimpleNamespace(
        now=worker.moment(worker.DUE["entry"]) + timedelta(minutes=5),
        failure=None,
        missing=False,
        future=False,
        secret=False,
        busy=False,
    )

    def load_config(*args, **kwargs):
        assert kwargs == {"environment": {"THERICHER_MODE": "off"}}
        calls.config += 1
        return SimpleNamespace(
            app_key="7.001" if state.secret else "MOCK_APP", app_secret="MOCK_SECRET"
        )

    monkeypatch.setattr(market, "load_kis_paper_market_data_config", load_config)

    def acquire(**kwargs):
        assert kwargs["root"] == worker.MARKET
        calls.locks += 1
        return None if state.busy else object()

    monkeypatch.setattr(locks, "_acquire_worker_lock", acquire)
    monkeypatch.setattr(
        locks, "_release_worker_lock", lambda lock: setattr(calls, "releases", calls.releases + 1)
    )

    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 0.01
            field = "token" if request.get_method() == "POST" else "daily"
            setattr(calls, field, getattr(calls, field) + 1)
            return None

    class Transport:
        def __init__(self, **kwargs):
            assert set(kwargs) == {"request_gate", "token_start_gate"}
            self._opener = Opener()

    class Client:
        def __init__(self, *, config, transport, max_daily_page_attempts):
            assert max_daily_page_attempts == 42
            self.transport = transport
            self._access_token = None

        def fetch_daily_raw_page(self, query):
            calls.fetch += 1
            if state.failure:
                reason, state.failure = state.failure, None
                raise market.KisPaperMarketDataError(reason)
            if self._access_token is None:
                self.transport._opener.open(
                    SimpleNamespace(get_method=lambda: "POST"), timeout=0.01
                )
                self._access_token = "MOCK_TOKEN"
            self.transport._opener.open(SimpleNamespace(get_method=lambda: "GET"), timeout=0.01)
            day = "20261013" if state.future else "20261009" if state.missing else query.by_date
            rows = (market.KisPaperDailyRawRow(day, "7.0010", "8.0", "6.0", "7.2", "100"),)
            return market.KisPaperDailyRawPage(
                market.KisPaperDailyPage(query, 1, day, day, True, False, None),
                rows,
            )

    monkeypatch.setattr(market, "UrllibKisPaperMarketDataTransport", Transport)
    monkeypatch.setattr(market, "KisPaperMarketDataClient", Client)

    def run():
        result = worker.run({}, {}, PIN, "entry", clock=lambda: state.now)
        if "terminal_path" in result:
            # Mocked parent custody, not an actual process/runtime attestation.
            worker.attest_child(result, PIN, "entry", result["observed_elapsed_seconds"] + 0.1, 0)
        return result

    return SimpleNamespace(
        state=state,
        calls=calls,
        binding=binding,
        run=run,
    )


def test_full_scope_one_token_and_current_readback(case):
    result = case.run()
    assert result["status"] == "scope_complete"
    assert result["available_count"] == result["next_index"] == result["wire_daily_starts"] == 42
    assert result["wire_token_starts"] == case.calls.token == 1
    assert case.calls.config == case.calls.releases == 1
    assert result["account_calls"] == result["order_calls"] == result["live_calls"] == 0
    assert result["publication_observed"] and not result["own_return_publication_observed"]
    observed = worker.read_current({}, {}, PIN, "entry")
    assert observed["status"] == "scope_complete" and observed["endpoint_complete"]
    assert observed["provider_finality"] == "not_observed"
    assert "7.001" not in str(observed) and "MOCK_TOKEN" not in str(observed)
    recovered = case.run()
    assert recovered["status"] == "scope_complete"
    assert worker.read_current({}, {}, PIN, "entry")["endpoint_complete"]
    assert case.calls.fetch == 42 and case.calls.config == 1


@pytest.mark.parametrize("when,status", [(-1, "not_due"), (60, "expired")])
def test_outside_owned_opportunity_no_credentials_or_writes(case, when, status):
    case.state.now = worker.moment(worker.DUE["entry"]) + timedelta(minutes=when)
    assert case.run()["status"] == status
    assert case.calls.config == case.calls.fetch == case.calls.locks == 0
    assert not worker.MARKET.exists() and not worker.ROOT.exists()


def test_busy_owner_no_credentials(case):
    case.state.busy = True
    assert case.run()["status"] == "worker_busy"
    assert case.calls.config == case.calls.fetch == 0


@pytest.mark.parametrize("reason", ["rate_limited", "token_request_not_due", "auth_rejected"])
def test_retry_same_cursor_with_retained_failure(case, reason):
    case.state.failure = reason
    first = case.run()
    assert first["status"] == "yielded" and first["next_index"] == 0
    assert first["attempt_receipt_count"] == 1
    case.state.now += timedelta(minutes=6)
    second = case.run()
    assert second["status"] == "scope_complete" and second["attempt_receipt_count"] == 43
    assert second["available_count"] == 42 and case.calls.fetch == 43


@pytest.mark.parametrize("flag", ["missing", "future"])
def test_unavailable_peers_not_silently_filtered(case, flag):
    setattr(case.state, flag, True)
    result = case.run()
    assert result["status"] == "scope_complete" and result["next_index"] == 42
    assert result["missing_or_rejected_count"] == 42 and result["available_count"] == 0
    assert not result["endpoint_complete"]


def test_secret_echo_is_never_persisted(case):
    case.state.secret = True
    result = case.run()
    assert result["status"] == "yielded" and result["available_count"] == 0
    assert not (worker.MARKET / "pages").exists()


def test_exact_orphan_checkpoint_recovers_without_refetch(case, monkeypatch):
    original = worker.publish
    state = {"failed": False}

    def fail_after_checkpoint(path, raw, **kwargs):
        result = original(path, raw, **kwargs)
        if "checkpoints" in Path(path).parts and not state["failed"]:
            state["failed"] = True
            raise worker.Stop("immutable_conflict")
        return result

    monkeypatch.setattr(worker, "publish", fail_after_checkpoint)
    assert case.run()["status"] == "input_unavailable"
    current = worker.decode(worker.read(worker.cursor_path("entry")))
    assert current["pending"] is not None and not current["checkpoints"]
    case.state.now += timedelta(minutes=6)
    recovered_result = case.run()
    assert recovered_result["status"] == "scope_complete", recovered_result
    assert case.calls.fetch == 42


def test_missing_outcome_not_success(case):
    assert worker.read_current({}, {}, PIN, "entry")["status"] == "not_observed"


def test_changed_terminal_rejected(case):
    result = case.run()
    path = Path(result["terminal_path"])
    path.write_bytes(b"{}")
    with pytest.raises(worker.Stop, match="evidence_changed"):
        worker.read_current({}, {}, PIN, "entry")


@pytest.mark.parametrize("pin", ["sha256:../../.env", "sha256:" + "G" * 64, "", None])
def test_malformed_pin_rejected_before_file_read(case, monkeypatch, pin):
    monkeypatch.setattr(worker, "read", lambda *a: pytest.fail("file must not be read"))
    with pytest.raises(worker.Stop, match="binding_invalid"):
        worker.pinned(Path(".env"), pin)


@pytest.mark.parametrize("value", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_strict_json(value):
    with pytest.raises(worker.Stop):
        worker.decode(value)


@pytest.mark.parametrize("relative", ["../.env", "C:/private", "/private", "a\\b", ""])
def test_child_path_escape_rejected(case, relative):
    with pytest.raises(worker.Stop):
        worker.child(worker.ROOT, relative)


def test_immutable_publication_conflict_and_atomic_replace(case):
    path = worker.ROOT / "metadata.json"
    worker.publish(path, b"old")
    with pytest.raises(worker.Stop, match="immutable_conflict"):
        worker.publish(path, b"new")
    assert path.read_bytes() == b"old"
    worker.publish(path, b"new", replace=True)
    assert path.read_bytes() == b"new"


def test_pending_wrong_cursor_rejected(case):
    current = worker.initial(PIN, "entry")
    current["pending"] = {"id": "a" * 32, "start": 1}
    with pytest.raises(worker.Stop, match="cursor_invalid"):
        worker.accept_pending(storage, case.binding, current, PIN, "entry")


def test_foreign_worker_lock_not_released(case):
    case.state.busy = True
    case.run()
    assert case.calls.releases == 0


@pytest.fixture
def job_files(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(worker, "MARKET", tmp_path / "market")
    monkeypatch.setattr(worker, "CONTROL", tmp_path / "control")
    root = worker.ROOT
    package = root / "source/thericher_v2/__init__.py"
    worker.publish(package, b"# synthetic package\n")
    helper_pins = {}
    for name in ("endpoint_worker.py", "endpoint_storage.py"):
        helper_pins[name] = worker.publish(root / name, b"# synthetic helper\n")
    peers = dict(
        forecast_closure_sha256=worker.CLOSURE,
        peers=[{} for _ in range(42)],
        entry_session=worker.DATES["entry"],
        exit_session=worker.DATES["exit"],
        entry_due=worker.DUE["entry"],
        exit_due=worker.DUE["exit"],
        provider_calls=0,
        fits=0,
        raw_target_reads=0,
    )
    peer_pin = worker.publish(root / "peer-source.json", worker.encode(peers))
    freeze = dict(
        status="peers_frozen",
        peer_source_sha256=peer_pin,
        peer_count=42,
        peer_publication_observed=True,
        completed_at="2026-10-09T23:00:00+00:00",
        observed_elapsed_seconds=1.0,
    )
    freeze_pin = worker.publish(root / "peer-freeze-return.json", worker.encode(freeze))
    job = dict(
        kind=worker.KINDS,
        forecast_closure_sha256=worker.CLOSURE,
        market_root=str(worker.MARKET),
        control_root=str(worker.CONTROL),
        package_root=str(root / "source"),
        dates=worker.DATES,
        due=worker.DUE,
        work_seconds=230,
        total_seconds=270,
        peer_count=42,
        paper_only=True,
        account_calls=0,
        order_calls=0,
        live_calls=0,
        runner_sha256=worker.sha(worker.read(SOURCE)),
        python_path=sys.executable,
        python_sha256=worker.sha(worker.read(Path(sys.executable))),
        peer_source_sha256=peer_pin,
        peer_freeze_return_sha256=freeze_pin,
        helper_pins=helper_pins,
        package_pins={"thericher_v2/__init__.py": worker.sha(worker.read(package))},
    )

    def save():
        return worker.publish(root / "job.json", worker.encode(job), replace=True)

    return SimpleNamespace(job=job, root=root, save=save)


def test_exact_job_metadata_readback(job_files):
    pin = job_files.save()
    job, peers = worker.load_job(job_files.root / "job.json", pin)
    assert job == job_files.job and len(peers["peers"]) == 42


@pytest.mark.parametrize(
    "field,value",
    [
        ("forecast_closure_sha256", PIN),
        ("peer_count", 7),
        ("paper_only", False),
        ("order_calls", 1),
        ("live_calls", 1),
        ("account_calls", 1),
        ("work_seconds", 300),
        ("total_seconds", 600),
        ("runner_sha256", PIN),
        ("python_sha256", PIN),
        ("python_path", "C:/foreign/python.exe"),
        ("package_pins", {}),
        ("helper_pins", {}),
        ("market_root", "C:/private"),
    ],
)
def test_changed_job_scope_rejected(job_files, field, value):
    job_files.job[field] = value
    pin = job_files.save()
    with pytest.raises(worker.Stop):
        worker.load_job(job_files.root / "job.json", pin)


def test_unlisted_package_source_rejected(job_files):
    pin = job_files.save()
    worker.publish(job_files.root / "source/extra.py", b"# unexpected\n")
    with pytest.raises(worker.Stop, match="package_source_set_changed"):
        worker.load_job(job_files.root / "job.json", pin)


def test_inner_completion_without_parent_is_not_qualified(case):
    result = worker.run({}, {}, PIN, "entry", clock=lambda: case.state.now)
    assert result["status"] == "scope_complete"
    observed = worker.read_current({}, {}, PIN, "entry")
    assert observed["status"] == "not_observed" and observed["next_index"] == 42


@pytest.mark.parametrize("elapsed", [0.0, -1.0, 280.0, float("nan"), float("inf")])
def test_parent_cannot_attest_impossible_child_elapsed(case, elapsed):
    result = worker.run({}, {}, PIN, "entry", clock=lambda: case.state.now)
    result["observed_elapsed_seconds"] = 269.0
    with pytest.raises(worker.Stop):
        worker.attest_child(result, PIN, "entry", elapsed, 0)


def test_parent_rejects_child_debit_greater_than_observed(case):
    result = worker.run({}, {}, PIN, "entry", clock=lambda: case.state.now)
    result["observed_elapsed_seconds"] = 269.0
    with pytest.raises(worker.Stop, match="child_result_invalid"):
        worker.attest_child(result, PIN, "entry", 6.0, 0)


def test_child_dispatch_sanitizes_environment_and_arguments(case, monkeypatch):
    seen = {}

    def run(args, **kwargs):
        seen.update(args=args, **kwargs)
        return SimpleNamespace(returncode=0, stdout=b'{"status":"not_due"}')

    monkeypatch.setattr(worker.subprocess, "run", run)
    monkeypatch.setattr(worker.os, "environ", {"PATH": "mock_path", "PRIVATE_TEST_KEY": "fake"})
    result = worker.dispatch({}, {}, PIN, "entry")
    assert result["status"] == "not_due"
    assert seen["env"] == {"PATH": "mock_path"}
    assert seen["args"][-1] == "--child" and seen["timeout"] == 280
    assert seen["shell"] is False and "--job-sha256" in seen["args"]
