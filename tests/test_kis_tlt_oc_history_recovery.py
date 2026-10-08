from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from thericher_v2.execution.kis_market_data import (
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    SPEC = importlib.util.spec_from_file_location(
        "tlt_oc_recovery_test", ROOT / "scripts/acquire_kis_tlt_oc_history_recovery.py"
    )
    script = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(script)
finally:
    sys.path.pop(0)

SECRET = "fake-secret-not-for-retention"


def payload(anchor, *, count=2, empty=False, **changes):
    day = datetime.strptime(anchor, "%Y%m%d")
    rows = (
        []
        if empty
        else [
            dict(
                xymd=(day - timedelta(days=n)).strftime("%Y%m%d"),
                open="10.125",
                clos="12.50",
                high="20",
                low="1",
                tvol="9",
                **changes,
            )
            for n in range(count)
        ]
    )
    return dict(rt_cd="0", output1={}, output2=rows)


@pytest.fixture(autouse=True)
def block_real_calls(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("unmocked credential/network access")

    monkeypatch.setattr(script, "load_kis_paper_market_data_config", blocked)
    monkeypatch.setattr(script, "KisPaperDailyEndpointTransport", blocked)


@pytest.fixture
def f(tmp_path):
    state = SimpleNamespace(
        market=tmp_path / "m",
        artifacts=tmp_path / "a",
        seconds=0.0,
        requests=[],
        rule=None,
        transports=[],
        loader_calls=[],
    )

    def clock():
        return datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=state.seconds)

    def sleeper(delay):
        state.seconds += delay

    class Transport:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            state.transports.append(self)

        def request(self, request):
            url = urlsplit(request.url)
            assert url.scheme == "https" and url.netloc == "openapivts.koreainvestment.com:29443"
            if request.method == "POST":
                assert url.path == "/oauth2/tokenP"
                if not self.kwargs["token_start_gate"].claim_token_request_start():
                    raise KisPaperMarketDataError("token_request_not_due")
            else:
                assert request.method == "GET" and request.query["SYMB"] == "TLT"
                assert request.query["EXCD"] in {"NAS", "AMS"} and request.query["MODP"] == "0"
                assert url.path == "/uapi/overseas-price/v1/quotations/dailyprice"
            self.kwargs["request_gate"].wait_for_request_slot()
            state.requests.append(request)
            if state.rule is not None:
                result = state.rule(request)
                if result is not None:
                    return result
            body = (
                dict(access_token="bearer-unit")
                if request.method == "POST"
                else payload(request.query["BYMD"])
            )
            return KisMarketDataResponse.from_payload(body, headers={"tr_cont": "F"})

    def loader(path):
        state.loader_calls.append(path)
        return KisPaperMarketDataConfig("key-unit", SECRET)

    def run(mode="probe6", label="one", **kwargs):
        return script.run_recovery(
            mode=mode,
            market_root=state.market,
            artifact_root=state.artifacts,
            run_label=label,
            dotenv_path=tmp_path / "not-read.env",
            config_loader=loader,
            transport_factory=Transport,
            clock=clock,
            monotonic=lambda: state.seconds,
            sleeper=sleeper,
            space_check=kwargs.pop("space_check", lambda count: False),
            **kwargs,
        )

    state.run = run
    state.root = state.market / script.CACHE
    return state


def receipt(result):
    return json.loads(Path(result["receipt_path"]).read_bytes())


def index(f):
    return json.loads((f.root / "index.json").read_bytes())


def gets(f):
    return [r for r in f.requests if r.method == "GET"]


def test_exact_six_queries_and_single_cached_token(f):
    result = f.run()
    r = receipt(result)
    assert result["status"] == "observed" and result["accepted_page_count"] == 6
    assert result["daily_GET_attempts"] == 6 and result["token_POST_attempts"] == 1
    assert len(f.transports) == len(f.loader_calls) == 1
    assert [(q.query["EXCD"], q.query["BYMD"]) for q in gets(f)] == [
        (venue, anchor) for anchor in script.ANCHORS for venue in ("NAS", "AMS")
    ]
    assert (
        r["count_semantics"]
        == "inherited dispatch attempts; not independently measured wire starts"
    )
    assert r["source_bodies_retained"] is False and len(r["probe_outcomes"]) == 6
    assert r["source_reattestation"] == "matched" and r["catalog"]["status"] == "matched"
    assert script._verified_index(f.root, f.market, r["source_pins"])[0] == index(f)


def test_recover_shares_probe_and_history_token_budget_and_cursor(f):
    result = f.run("recover", maximum_pages=8)
    assert result["reason"] == "page_budget" and result["accepted_page_count"] == 8
    assert result["daily_GET_attempts"] == 8 and result["token_POST_attempts"] == 1
    assert len(f.transports) == 1
    assert [r.query["BYMD"] for r in gets(f)[6:]] == ["20201230", "20201229"]
    assert result["coverage"]["TLT/NAS"]["cursor"] == "20201228"
    assert result["coverage"]["TLT/AMS"]["cursor"] == "20201230"
    assert result["coverage"]["TLT/NAS"]["unique_date_count"] == 4


def test_empty_deep_anchor_is_only_its_scope_and_latest_useful_seed_retained(f):
    def rule(request):
        if request.method == "GET" and request.query["BYMD"] in {"20151231", "20101231"}:
            return KisMarketDataResponse.from_payload(payload(request.query["BYMD"], empty=True))

    f.rule = rule
    result = f.run("recover", maximum_pages=7)
    assert len(gets(f)) == 7 and result["coverage"]["TLT/NAS"]["seed_ordinal"] == 1
    assert result["coverage"]["TLT/AMS"]["seed_ordinal"] == 2
    assert receipt(result)["probe_outcomes"][2]["facts"]["source_row_count"] == 0


def test_fallback_seed_is_latest_nonempty_per_venue_without_other_anchor_graft(f):
    def rule(request):
        if request.method == "GET" and request.query["BYMD"] == "20201231":
            return KisMarketDataResponse.from_payload(payload("20201231", empty=True))

    f.rule = rule
    result = f.run()
    assert result["coverage"]["TLT/NAS"]["seed_ordinal"] == 3
    assert result["coverage"]["TLT/AMS"]["seed_ordinal"] == 4
    assert all(c["unique_date_count"] == 2 for c in result["coverage"].values())


def test_all_empty_is_unestablished_not_provider_exhaustion(f):
    f.rule = lambda q: (
        KisMarketDataResponse.from_payload(payload(q.query["BYMD"], empty=True))
        if q.method == "GET"
        else None
    )
    result = f.run("recover")
    assert result["status"] == "scope_terminal" and len(gets(f)) == 6
    assert all(c["state"] == "unestablished" for c in result["coverage"].values())


@pytest.mark.parametrize("where", ("probe", "history"))
def test_true_empty_accepted_only_and_history_source_limit_is_exact_scope(f, where):
    def rule(request):
        if request.method == "GET" and (
            where == "probe" or request.query["BYMD"] not in script.ANCHORS
        ):
            return KisMarketDataResponse.from_payload(payload(request.query["BYMD"], empty=True))

    f.rule = rule
    result = f.run("recover")
    assert result["status"] == "scope_terminal"
    assert len(gets(f)) == (6 if where == "probe" else 8)
    assert all(
        c["state"] == ("unestablished" if where == "probe" else "source_limited")
        for c in result["coverage"].values()
    )


def test_nonadvancing_cursor_stops_one_venue_companion_continues(f):
    def rule(request):
        if request.method == "GET" and request.query["BYMD"] not in script.ANCHORS:
            if request.query["EXCD"] == "NAS":
                return KisMarketDataResponse.from_payload(payload(request.query["BYMD"], count=1))
            return KisMarketDataResponse.from_payload(payload(request.query["BYMD"], empty=True))

    f.rule = rule
    result = f.run("recover")
    assert result["failure_page_count"] == 1 and len(gets(f)) == 8
    assert result["coverage"]["TLT/NAS"]["state"] == "stopped"
    assert result["coverage"]["TLT/NAS"]["cursor"] == "20201230"
    assert result["coverage"]["TLT/AMS"]["state"] == "source_limited"


@pytest.mark.parametrize("body_kind", ("http_error", "success_echo", "escaped_echo"))
def test_secret_echo_never_retained_in_success_or_error(f, body_kind):
    def rule(request):
        if request.method != "GET":
            return None
        body = payload(request.query["BYMD"])
        body["extra"] = SECRET
        raw = json.dumps(body).encode()
        if body_kind == "escaped_echo":
            raw = raw.replace(
                SECRET.encode(), b"".join(f"\\u{ord(c):04x}".encode() for c in SECRET)
            )
        return KisMarketDataResponse(
            status_code=401 if body_kind == "http_error" else 200, headers={}, body=raw
        )

    f.rule = rule
    result = f.run()
    assert result["accepted_page_count"] == 0 and result["failure_page_count"] >= 1
    for p in f.market.rglob("*.json"):
        assert SECRET.encode() not in p.read_bytes() and b"access_token" not in p.read_bytes()
    for p in f.artifacts.rglob("*.json"):
        assert SECRET.encode() not in p.read_bytes() and b'"open"' not in p.read_bytes()
    assert SECRET not in json.dumps(result)


def test_token_failure_no_get_or_retry(f):
    f.rule = lambda q: (
        KisMarketDataResponse.from_payload(dict(rt_cd="1", msg1=SECRET), status_code=401)
        if q.method == "POST"
        else None
    )
    result = f.run()
    assert result["reason"] == "auth_rejected" and result["token_POST_attempts"] == 1
    assert result["daily_GET_attempts"] == 0 and not gets(f)


def test_fresh_process_local_token_guard_yields_due_without_sleep(f):
    f.run()
    seconds = f.seconds
    result = f.run("recover", "two", maximum_pages=7)
    assert result["reason"] == "token_request_not_due" and result["owned_next_due"]
    assert result["daily_GET_attempts"] == 0 and f.seconds == seconds


def test_unknown_get_retained_and_new_identity_retry_allowed_on_resume(f):
    f.rule = lambda q: (
        (_ for _ in ()).throw(KisPaperMarketDataError("transport_failure", SECRET))
        if q.method == "GET"
        else None
    )
    first = f.run()
    assert first["reason"] == "transport_failure" and len(gets(f)) == 1
    before = {p: p.read_bytes() for p in (f.root / "attempts").glob("*")}
    f.seconds += 301
    f.rule = None
    second = f.run(label="two")
    assert second["accepted_page_count"] == 6 and len(gets(f)) == 7
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert gets(f)[0].query == gets(f)[1].query


@pytest.mark.parametrize("ordinal", (1, 3))
@pytest.mark.parametrize("error", ("transport_failure", "endpoint_numeric_invalid"))
def test_fetch_failure_uses_current_attempt_not_previous_manifest(f, ordinal, error):
    def rule(request):
        if request.method == "GET" and len(gets(f)) == ordinal:
            raise KisPaperMarketDataError(error, SECRET)

    f.rule = rule
    result = f.run()
    r = receipt(result)
    assert result["failure_page_count"] == 1 and r["catalog"]["status"] == "matched"
    assert index(f)["pending"] is None and r["pending_projection"] == "verified"
    if error == "transport_failure":
        assert result["reason"] == error and result["accepted_page_count"] == ordinal - 1
        assert len(gets(f)) == ordinal and len(index(f)["probes"]) == ordinal - 1
    else:
        assert result["accepted_page_count"] == 5 and len(gets(f)) == 6
        assert index(f)["probes"][ordinal - 1]["status"] == "rejected"
    failure_paths = list((f.root / "attempts").glob("*-failure.json"))
    assert len(failure_paths) == 1
    failure = json.loads(failure_paths[0].read_bytes())
    intent = json.loads((f.market / failure["intent"]["market_relative_path"]).read_bytes())
    assert intent["question_ordinal"] == ordinal
    assert (
        not failure_paths[0]
        .with_name(failure_paths[0].name.replace("-failure", "-manifest"))
        .exists()
    )


@pytest.mark.parametrize("stage", ("probe", "history"))
def test_crash_after_manifest_recovers_without_get_preserving_original_bytes(f, monkeypatch, stage):
    save = script._save
    fault = [True]

    def crash(root, value):
        if (
            fault[0]
            and value["pending"] is None
            and (
                (stage == "probe" and len(value["probes"]) == 1)
                or (stage == "history" and value["targets"]["TLT/NAS"]["chunks"])
            )
        ):
            fault[0] = False
            raise OSError(SECRET)
        return save(root, value)

    monkeypatch.setattr(script, "_save", crash)
    first = f.run("recover", maximum_pages=7)
    assert first["reason"] == "local_io_unavailable"
    assert receipt(first)["pending_projection"] == "verified" and index(f)["pending"]
    original = {p: p.read_bytes() for p in (f.root / "attempts").glob("*")}
    calls = len(f.requests)
    second = f.run("recover", "two", maximum_pages=7)
    assert second["recovered_page_count"] == 1 and second["daily_GET_attempts"] == 0
    assert len(f.requests) == calls and index(f)["pending"] is None
    assert all(p.read_bytes() == raw for p, raw in original.items())


def test_catalog_snapshot_fault_preserves_counts_and_terminal(f, monkeypatch):
    write = script._write

    def fail(path, raw):
        if path == f.artifacts / f"data/{script.VERSION}/one/index.json":
            raise OSError(SECRET)
        return write(path, raw)

    monkeypatch.setattr(script, "_write", fail)
    result = f.run()
    assert result["accepted_page_count"] == 6 and result["reason"] == "local_io_unavailable"
    assert receipt(result)["catalog"] is None and result["coverage"] == {}


def test_busy_never_reads_foreign_index_or_claims_coverage(f, monkeypatch):
    f.root.mkdir(parents=True)
    (f.root / "index.json").write_bytes(b"foreign-private-catalog")
    monkeypatch.setattr(script, "_acquire_worker_lock", lambda **kw: None)
    monkeypatch.setattr(script, "_verified_index", lambda *a: pytest.fail("foreign read"))
    result = f.run()
    assert result["reason"] == "worker_busy" and result["coverage"] == {}
    assert not f.requests and receipt(result)["catalog"] is None


@pytest.mark.parametrize("moment", ("initial", "end"))
def test_source_pin_io_failure_still_categorical_terminal(f, monkeypatch, moment):
    pins = script._pins

    def fail():
        if moment == "initial" or len(gets(f)) == 6:
            raise OSError(SECRET)
        return pins()

    monkeypatch.setattr(script, "_pins", fail)
    result = f.run()
    assert result["reason"] == "source_hash_unavailable"
    assert receipt(result)["source_reattestation"] == "unavailable"
    assert result["accepted_page_count"] == (0 if moment == "initial" else 5)
    assert SECRET not in json.dumps(receipt(result))


def test_storage_floor_before_token(f):
    result = f.run(space_check=lambda count: True)
    assert result["reason"] == "storage_floor" and not f.requests


def test_runtime_budget_bounds_actual_pacing_no_second_request(f):
    def rule(request):
        if request.method == "POST":
            f.seconds += 20

    f.rule = rule
    result = f.run(runtime_seconds=30)
    assert result["reason"] == "runtime_budget" and result["daily_GET_attempts"] == 0


def test_full_fingerprint_sets_and_unused_warnings_survive_readback(f):
    def rule(request):
        if request.method == "GET":
            body = payload(request.query["BYMD"])
            body["output2"].append({**body["output2"][0], "low": "11", "high": "11"})
            return KisMarketDataResponse.from_payload(body)

    f.rule = rule
    r = receipt(f.run())
    manifest, _, page = script._load_page(f.market, f.root, r["pages"][0], r["source_pins"])
    assert len(page.source_row_fingerprints) == 3 and page.duplicate_row_count == 1
    assert len(manifest["dated_unused_ohlcv_faults"]) == 1


def test_tampered_seed_ordinal_rejected_without_new_calls(f):
    f.run()
    data = index(f)
    data["targets"]["TLT/NAS"]["seed_ordinal"] = 5
    script._save(f.root, data)
    calls = len(f.requests)
    result = f.run("recover", "two")
    assert result["reason"] == "catalog_invalid" and len(f.requests) == calls


def test_duplicate_private_json_key_rejected_without_calls(f):
    f.run()
    raw = (f.root / "index.json").read_bytes()
    (f.root / "index.json").write_bytes(raw.replace(b'"kind":', b'"kind":"bad","kind":', 1))
    calls = len(f.requests)
    result = f.run("recover", "two")
    assert result["reason"] == "catalog_invalid" and len(f.requests) == calls


def test_original_output_not_overwritten(f):
    first = f.run()
    before = Path(first["receipt_path"]).read_bytes()
    with pytest.raises(script.Stop):
        f.run()
    assert Path(first["receipt_path"]).read_bytes() == before


@pytest.mark.parametrize(
    "override",
    (
        {"maximum_pages": 65},
        {"runtime_seconds": 361},
        {"maximum_pages": True},
        {"runtime_seconds": float("nan")},
    ),
)
def test_invalid_budget_before_any_io_or_calls(f, override):
    with pytest.raises(script.Stop):
        f.run(**override)
    assert not f.requests and not f.artifacts.exists()


def test_main_stdout_only_safe_projection(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "run_recovery",
        lambda **kw: dict(status="partial", reason="page_budget", accepted_page_count=6),
    )
    assert script.main(["--recover", "--run-label", "synthetic"]) == 20
    assert json.loads(capsys.readouterr().out) == dict(
        status="partial", reason="page_budget", accepted_page_count=6
    )
