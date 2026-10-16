import importlib.util
import io
import itertools
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution import kis_market_data as m
from thericher_v2.execution.kis_stock_intraday_foundation import (
    COHORT,
    FoundationLedger,
    FoundationOwner,
    file_ref,
    observed_coverage,
    prior_regular_key,
    run_foundation,
)

SESSIONS = [
    dict(open_utc=f"2026-10-{day}T13:30:00+00:00", close_utc=f"2026-10-{day}T20:00:00+00:00")
    for day in (15, 16)
]
TARGETS = [(s, "NAS") for s in COHORT]


@pytest.fixture
def held_owner(tmp_path):
    with FoundationOwner(tmp_path / "m") as owner:
        yield owner


def ledger(tmp_path, owner, normal=40, retry=2):
    return FoundationLedger(
        artifact_root=tmp_path / "a",
        market_root=tmp_path / "m",
        targets=TARGETS,
        sessions=SESSIONS,
        owner=owner,
        normal_cap=normal,
        retry_cap=retry,
    )


def page(query, empty=False):
    start = datetime.strptime(query.continuation_key or "20261016155900", "%Y%m%d%H%M%S")
    rows = []
    for i in range(0 if empty else 120):
        x = start - timedelta(minutes=i)
        k = x.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("Asia/Seoul"))
        rows.append(
            m._parse_minute_bar(
                dict(
                    xymd=x.strftime("%Y%m%d"),
                    xhms=x.strftime("%H%M%S"),
                    kymd=k.strftime("%Y%m%d"),
                    khms=k.strftime("%H%M%S"),
                    open="10",
                    high="12",
                    low="9",
                    last="11",
                    evol="100",
                )
            )
        )
    return m.KisPaperMinutePage(
        query=query,
        bars=tuple(rows),
        next_cursor=None,
        more="",
        continuation_signal="blank_or_absent",
    )


def test_native_ledger_rounds_heads_before_backfill_and_no_repeat(tmp_path, held_owner):
    job = ledger(tmp_path, held_owner)
    called = []

    def fetch(q, retry):
        called.append((q.symbol, q.continuation_key))
        job.begin_wire("GET", query=q, retry=retry)
        body = json.dumps({"output2": [b.as_document() for b in page(q).bars]}).encode()
        ref = job.retain_raw(body)
        return page(q), ref, datetime.now(UTC).isoformat()

    run_foundation(job, fetch, lambda: None, lambda: None, prior_close_key="20261015155900")
    assert called[0] == ("AAPL", "20261015155900")
    assert called[1:21] == [(s, None) for s in COHORT]
    assert len(called) == len(set(called)) == job.state["GET"] == 40
    assert job.state["retry"] == 0
    coverage = observed_coverage(job)
    assert coverage["AAPL"]["regular_labels"] >= 120
    assert not any(v["transfer_ready"] for v in coverage.values())


def test_rth_calendar_jump_and_scope_bound():
    assert prior_regular_key("20261016092900", SESSIONS) == "20261015155900"
    assert prior_regular_key("20261016190000", SESSIONS) == "20261016155900"
    with pytest.raises(ValueError, match="calendar_bound"):
        prior_regular_key("20261015092900", SESSIONS)


def test_caps_pending_resume_and_new_scope_fail_closed(tmp_path, held_owner):
    job = ledger(tmp_path, held_owner, normal=1, retry=1)
    q = job.query("AAPL")
    job.begin_wire("GET", query=q)
    with pytest.raises(ValueError, match="pending"):
        ledger(tmp_path, held_owner, normal=1, retry=1)
    with pytest.raises(ValueError, match="pending"):
        job.begin_wire("POST", query=None)
    job.reject(q, "transport_failure", None, retryable=True)
    job.begin_wire("GET", query=q, retry=True)
    job.reject(q, "transport_failure", None)
    with pytest.raises(ValueError, match="cap"):
        job.begin_wire("GET", query=q, retry=True)
    job.begin_wire("POST", query=None)
    job.authentication_completed()
    with pytest.raises(ValueError, match="auth_cap"):
        job.begin_wire("POST", query=None)
    with pytest.raises(ValueError, match="cohort"):
        FoundationLedger(
            artifact_root=tmp_path / "a",
            market_root=tmp_path / "m",
            targets=list(reversed(TARGETS)),
            sessions=SESSIONS,
            owner=held_owner,
        )


def test_empty_is_scoped_and_whole_pages_are_immutable(tmp_path, held_owner):
    job = ledger(tmp_path, held_owner)
    q = job.query("AAPL", "20261015155900")
    job.begin_wire("GET", query=q)
    raw = job.retain_raw(b'{"output2":[]}')
    with pytest.raises(FileExistsError):
        job.retain_raw(b"replacement")
    job.accept(q, page(q, empty=True), raw, datetime.now(UTC).isoformat())
    assert job.state["cursors"]["AAPL"]["status"] == "exact_cursor_empty"
    assert job.state["cursors"]["MSFT"]["status"] == "pending_head"
    assert file_ref(__import__("pathlib").Path(raw["path"])) == raw


def test_observed_300_label_coverage_requires_real_contiguous_rows(tmp_path, held_owner):
    job = ledger(tmp_path, held_owner)
    q = job.query("AAPL")
    for _ in range(3):
        job.begin_wire("GET", query=q)
        raw = job.retain_raw(b"synthetic-raw")
        job.accept(q, page(q), raw, datetime.now(UTC).isoformat())
        q = job.query("AAPL", job.state["cursors"]["AAPL"]["key"])
    v = observed_coverage(job)["AAPL"]
    assert v["regular_labels"] == v["longest_contiguous_regular_labels"] == 360
    assert v["label_context300"] and not v["transfer_ready"]


def test_retry_requires_exact_durable_failed_attempt(tmp_path, held_owner, monkeypatch):
    job = ledger(tmp_path, held_owner)
    q = job.query("AAPL")
    job.begin_wire("GET", query=q)
    save = job.save
    monkeypatch.setattr(job, "save", lambda: (_ for _ in ()).throw(OSError("SYN disk failure")))
    with pytest.raises(OSError):
        job.reject(q, "transport_failure", None, retryable=True)
    monkeypatch.setattr(job, "save", save)
    with pytest.raises(ValueError, match="pending_unknown"):
        job.begin_wire("GET", query=q, retry=True)
    assert json.loads((tmp_path / "a/cursor.json").read_bytes())["pending"]["method"] == "GET"


def test_retry_different_query_refused_without_debit(tmp_path, held_owner):
    job = ledger(tmp_path, held_owner)
    q = job.query("AAPL")
    job.begin_wire("GET", query=q)
    job.reject(q, "transport_failure", None, retryable=True)
    before = (tmp_path / "a/cursor.json").read_bytes()
    with pytest.raises(ValueError, match="exact_failed_attempt"):
        job.begin_wire("GET", query=job.query("MSFT"), retry=True)
    assert (tmp_path / "a/cursor.json").read_bytes() == before


@pytest.fixture
def cli_sandbox(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "foundation_cli_synthetic",
        Path(__file__).resolve().parents[1] / "scripts/collect_kis_stock_intraday_foundation.py",
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    artifact = tmp_path / "artifact"
    market = tmp_path / "market/capture"
    artifact.mkdir()
    cli.atomic_json(
        artifact / "assignment.json",
        dict(
            appointment_utc=datetime.now(UTC).isoformat(),
            active_cap_seconds=900,
            end_cap_seconds=2400,
            capture_root=str(market),
            consumer="native SYN only",
        ),
    )
    cli.atomic_json(
        artifact / "patch-ready.json", dict(source_pins={}, owner_probe="SYNowners.ps1")
    )
    cli.atomic_json(artifact / "source-routes.json", dict(ordered_targets=TARGETS))
    cli.atomic_json(artifact / "calendar.json", SESSIONS)

    def path(value):
        text = str(value).replace("\\", "/")
        if text == "D:/market_data" or text.startswith("D:/market_data/"):
            return tmp_path / "market" / text.removeprefix("D:/market_data").lstrip("/")
        return Path(value)

    facts = []

    def scheduler_mock(args, **kwargs):
        assert "-File" in args and "SYNowners.ps1" in args
        assert kwargs["creationflags"] == cli.subprocess.CREATE_NO_WINDOW
        assert (market / "owner.lock.d/owner.json").is_file()
        facts.append(True)
        value = dict(
            observed_utc=datetime.now(UTC).isoformat(),
            model_task_found=1,
            observer_task_found=1,
            nearest_future_due_seconds=1000,
            running_relevant_tasks=0,
            named_market_account_actors=0,
            paper_account_data_containers=0,
        )
        return SimpleNamespace(returncode=0, stdout=json.dumps(value).encode())

    token_type = cli.gates.KisPaperMarketDataTokenStartGate
    rate_type = cli.gates.KisPaperMarketDataRateGate
    floor = []

    class Token(token_type):
        def __init__(self, **kwargs):
            floor.append(kwargs["minimum_request_interval_seconds"])
            super().__init__(**kwargs)

    class Rate(rate_type):
        def __init__(self, **kwargs):
            kwargs["minimum_request_interval_seconds"] = 0.000001
            super().__init__(**kwargs)

    reads, requests, closeout = [], [], []
    mode = dict(GET_failure=None, POST_failure=None, POST_invalid=False)
    atomic = cli.atomic_json

    def monitored_atomic(target, value):
        if target.name in {"manifest.json", "completion.json"}:
            assert (market / "owner.lock.d/owner.json").exists()
            closeout.append(target.name)
        return atomic(target, value)

    class Response(io.BytesIO):
        status = 200
        headers = {"tr_cont": "N"}

        def __init__(self, method):
            self.method = method
            payload = (
                {"access_token": "SYN-native-token"}
                if method == "POST"
                else {"rt_cd": "0", "output1": {}, "output2": []}
            )
            if method == "POST" and mode["POST_invalid"]:
                payload = {}
            super().__init__(json.dumps(payload).encode())

        def read(self, *_args):
            state = json.loads((artifact / "cursor.json").read_bytes())
            assert state["pending"]["method"] == self.method
            reads.append(self.method)
            key = self.method + "_failure"
            if mode[key] is not None:
                error, mode[key] = mode[key], None
                raise error
            return super().read()

    class Opener:
        def open(self, request, timeout):
            assert timeout <= 5
            method = request.get_method()
            state = json.loads((artifact / "cursor.json").read_bytes())
            assert state["pending"]["method"] == method
            if method == "GET" and state["retry"]:
                assert state["failed_attempts"][0]["reason"] == "transport_failure"
                assert state["failed_attempts"][0]["GET"] == 1
                assert state["failed_attempts"][0]["retry_started"] == 2
            requests.append((method, request.full_url))
            return Response(method)

    config_calls = []

    def configuration(*_args, **_kwargs):
        config_calls.append(True)
        return m.KisPaperMarketDataConfig(app_key="SYN-app-key", app_secret="SYN-app-secret")

    monkeypatch.setattr(cli, "Path", path)
    monkeypatch.setattr(cli.sys, "_base_executable", cli.sys.executable)
    monkeypatch.setattr(
        cli.sys, "argv", ["collect", "--contract", str(artifact / "assignment.json")]
    )
    monkeypatch.setattr(cli.subprocess, "run", scheduler_mock)
    monkeypatch.setattr(
        cli.shutil, "disk_usage", lambda _path: SimpleNamespace(free=10**12, total=2 * 10**12)
    )
    counter = itertools.count(0, 3)
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(counter))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(cli.gates, "KisPaperMarketDataTokenStartGate", Token)
    monkeypatch.setattr(cli.gates, "KisPaperMarketDataRateGate", Rate)
    monkeypatch.setattr(cli.m, "load_kis_paper_market_data_config", configuration)
    monkeypatch.setattr(cli.m.urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(cli, "atomic_json", monitored_atomic)
    return SimpleNamespace(
        cli=cli,
        artifact=artifact,
        market=market,
        facts=facts,
        mode=mode,
        reads=reads,
        requests=requests,
        closeout=closeout,
        floor=floor,
        config_calls=config_calls,
    )


def test_native_CLI_pending_spans_open_body_and_closeout_precedes_release(cli_sandbox):
    case = cli_sandbox
    case.cli.main()
    state = json.loads((case.artifact / "cursor.json").read_bytes())
    assert state["POST"] == state["authenticated_POST"] == 1
    assert state["GET"] == len(case.reads) - 1 and state["pending"] is None
    assert case.floor == [300]
    assert case.closeout == ["manifest.json", "completion.json"]
    assert not (case.market / "owner.lock.d").exists()


def test_native_CLI_losing_invocation_does_not_touch_any_owner_bytes(cli_sandbox):
    case = cli_sandbox
    with FoundationOwner(case.market) as owner:
        for name in ("cursor.json", "manifest.json", "completion.json"):
            (case.artifact / name).write_bytes(b"SYN original other-owner evidence")
        paths = [
            case.artifact / name for name in ("cursor.json", "manifest.json", "completion.json")
        ]
        paths.append(owner.path / "owner.json")
        before = {path: path.read_bytes() for path in paths}
        with pytest.raises(FileExistsError):
            case.cli.main()
        assert all(path.read_bytes() == data for path, data in before.items())
        assert not case.facts and not case.config_calls
        owner.require_held()


def test_native_CLI_body_timeout_closes_failure_before_same_query_retry(cli_sandbox):
    case = cli_sandbox
    case.mode["GET_failure"] = TimeoutError("SYN body timeout")
    case.cli.main()
    state = json.loads((case.artifact / "cursor.json").read_bytes())
    assert state["retry"] == 1 and state["pending"] is None
    assert state["GET"] == state["normal_GET"] + 1
    gets = [url for method, url in case.requests if method == "GET"]
    assert gets[0] == gets[1]
    assert len(state["failed_attempts"]) == 1
    assert state["failed_attempts"][0]["GET"] == 1
    assert state["failed_attempts"][0]["retry_started"] == 2


def test_native_CLI_interruption_keeps_durable_pending_and_debit(cli_sandbox):
    case = cli_sandbox
    case.mode["GET_failure"] = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        case.cli.main()
    state = json.loads((case.artifact / "cursor.json").read_bytes())
    assert state["GET"] == 1 and state["retry"] == 0
    assert state["pending"]["method"] == "GET"
    assert not state["pages"]
    assert not (case.market / "owner.lock.d").exists()


def test_native_CLI_initialization_failure_releases_only_acquired_lease(cli_sandbox, monkeypatch):
    case = cli_sandbox

    def fail(**_kwargs):
        assert (case.market / "owner.lock.d/owner.json").exists()
        raise ValueError("SYN initialization failure")

    monkeypatch.setattr(case.cli, "FoundationLedger", fail)
    with pytest.raises(ValueError, match="initialization failure"):
        case.cli.main()
    assert not (case.market / "owner.lock.d").exists()
    assert not (case.artifact / "cursor.json").exists()
    assert not case.facts and not case.config_calls


@pytest.mark.parametrize("failure", ["timeout", "invalid_token"])
def test_native_CLI_POST_pending_only_clears_after_authenticated_completion(cli_sandbox, failure):
    case = cli_sandbox
    if failure == "timeout":
        case.mode["POST_failure"] = TimeoutError("SYN token body timeout")
    else:
        case.mode["POST_invalid"] = True
    case.cli.main()
    state = json.loads((case.artifact / "cursor.json").read_bytes())
    assert state["POST"] == 1 and state["GET"] == 0 and state["retry"] == 0
    assert state["pending"]["method"] == "POST"
    assert "authenticated_POST" not in state
    assert not (case.market / "owner.lock.d").exists()
    before = (case.artifact / "cursor.json").read_bytes()
    with pytest.raises(ValueError, match="pending request mismatch"):
        case.cli.main()
    assert (case.artifact / "cursor.json").read_bytes() == before


def test_native_CLI_prior_auth_debit_rejects_without_rewriting_closed_evidence(cli_sandbox):
    case = cli_sandbox
    case.cli.main()
    paths = [case.artifact / name for name in ("cursor.json", "manifest.json", "completion.json")]
    before = {path: path.read_bytes() for path in paths}
    requests = len(case.requests)
    with pytest.raises(ValueError, match="prior_auth_debit"):
        case.cli.main()
    assert len(case.requests) == requests
    assert all(path.read_bytes() == body for path, body in before.items())
    assert not (case.market / "owner.lock.d").exists()


def test_owner_marker_initialization_failure_cleans_own_directory(tmp_path, monkeypatch):
    from thericher_v2.execution import kis_stock_intraday_foundation as f

    def fail(path, _document):
        path.with_suffix(".json.pending").write_bytes(b"SYN incomplete owner marker")
        raise OSError("SYN owner marker failure")

    monkeypatch.setattr(f, "atomic_json", fail)
    with pytest.raises(OSError, match="owner marker failure"):
        with FoundationOwner(tmp_path / "owner-init-failure"):
            pytest.fail("initialization should fail")
    assert not (tmp_path / "owner-init-failure/owner.lock.d").exists()


def test_owner_finalizer_refuses_changed_identity(tmp_path):
    owner = FoundationOwner(tmp_path / "identity")
    owner.__enter__()
    identity = owner.identity
    before = (owner.path / "owner.json").read_bytes()
    owner.identity = (-1, -1)
    with pytest.raises(ValueError, match="lease_identity_changed"):
        owner.__exit__(None, None, None)
    assert (owner.path / "owner.json").read_bytes() == before
    owner.identity = identity
    owner.__exit__(None, None, None)
