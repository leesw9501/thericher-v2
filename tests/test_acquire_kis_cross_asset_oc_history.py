from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_market_data import (
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_history_test", ROOT / "scripts/acquire_kis_cross_asset_oc_history.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)
SECRET = "fake-secret-not-for-artifacts"


def payload(anchor, **changes):
    day = datetime.strptime(anchor, "%Y%m%d")
    rows = [
        dict(xymd=d.strftime("%Y%m%d"), open="10.125", clos="12.50", high="20", low="1", tvol="9")
        for d in (day, day - timedelta(days=1))
    ]
    for row in rows:
        row.update(changes)
    return {"rt_cd": "0", "output1": {}, "output2": rows}


@pytest.fixture
def f(tmp_path):
    state = SimpleNamespace(
        market=tmp_path / "m",
        artifacts=tmp_path / "a",
        seconds=0.0,
        requests=[],
        rule=None,
        transports=[],
        seed_result=None,
    )

    def clock():
        return datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=state.seconds)

    def sleep(delay):
        state.seconds += delay

    class Transport:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            state.transports.append(self)

        def request(self, request):
            if request.method == "POST":
                if not self.kwargs["token_start_gate"].token_request_is_due():
                    raise KisPaperMarketDataError("token_request_not_due")
                assert self.kwargs["token_start_gate"].claim_token_request_start()
            self.kwargs["request_gate"].wait_for_request_slot()
            state.requests.append(request)
            if state.rule:
                result = state.rule(request)
                if result is not None:
                    return result
            body = (
                {"access_token": "bearer-unit"}
                if request.method == "POST"
                else payload(request.query["BYMD"])
            )
            return KisMarketDataResponse.from_payload(body, headers={"tr_cont": "F"})

    def run(mode, label="one", **kwargs):
        return script.run_collection(
            mode=mode,
            market_root=state.market,
            artifact_root=state.artifacts,
            run_label=label,
            dotenv_path=tmp_path / "never-read.env",
            config_loader=lambda path: KisPaperMarketDataConfig("key-unit", SECRET),
            transport_factory=Transport,
            clock=clock,
            monotonic=lambda: state.seconds,
            sleeper=sleep,
            space_check=lambda count: False,
            **kwargs,
        )

    def seed():
        if state.seed_result is None:
            state.seed_result = run("probe6", "probe")
            assert state.seed_result["accepted_page_count"] == 6
        state.seconds += 301
        return dict(
            seed_receipt=Path(state.seed_result["receipt_path"]),
            seed_sha256=state.seed_result["receipt_sha256"],
        )

    def history(label="history", **kwargs):
        return run("history", label, **seed(), **kwargs)

    state.run, state.seed, state.history = run, seed, history
    return state


def receipt(result):
    return json.loads(Path(result["receipt_path"]).read_bytes())


def index(f):
    root = (
        f.market
        / f"us_equities/kis_paper_private/cross-asset-oc/{script.VERSION}/history/oc-venues-v1"
    )
    return root, json.loads((root / "index.json").read_bytes())


def test_six_exact_queries_one_client_token_and_no_body_retention(f):
    result = f.run("probe6")
    r = receipt(result)
    assert result["status"] == "observed"
    assert result["daily_GET_attempts"] == 6 and result["token_POST_attempts"] == 1
    assert len(f.transports) == 1 and r["source_bodies_retained"] is False
    assert (
        r["count_semantics"]
        == "inherited dispatch attempts; not independently measured wire starts"
    )
    actual = [
        (q.query["SYMB"], q.query["EXCD"], q.query["BYMD"], q.headers["tr_cont"])
        for q in f.requests
        if q.method == "GET"
    ]
    assert actual == [
        ("GLD", "AMS", "20210820", "F"),
        ("TLT", "NAS", "20151231", ""),
        ("TLT", "AMS", "20151231", ""),
        ("TLT", "AMS", "20071231", ""),
        ("GLD", "AMS", "20071231", ""),
        ("SPY", "AMS", "20071231", ""),
    ]
    for binding in r["pages"]:
        manifest, page = script._load(f.market, binding)
        assert manifest["facts"] == page.safe_facts()
        assert len(manifest["source_row_fingerprints"]) == page.source_row_count
        assert manifest["query"]["MODP"] == "0"
    assert all(
        SECRET.encode() not in p.read_bytes() and b"access_token" not in p.read_bytes()
        for p in f.market.rglob("*.json")
    )


def test_duplicate_unused_variants_retain_every_fingerprint_and_warning(f):
    def rule(request):
        if request.method == "GET":
            body = payload(request.query["BYMD"])
            body["output2"].append({**body["output2"][0], "low": "11", "high": "11"})
            body["msg1"] = "unneeded-provider-text-never-retained"
            return KisMarketDataResponse.from_payload(body)

    f.rule = rule
    r = receipt(f.run("probe6"))
    manifest, page = script._load(f.market, r["pages"][0])
    assert page.source_row_count == 3 and page.duplicate_row_count == 1 and len(page.rows) == 2
    assert len(manifest["source_row_fingerprints"]) == 3
    assert manifest["dated_unused_ohlcv_faults"][page.rows[-1].session_date] == [
        "high_below_open_close",
        "low_above_open_close",
    ]
    assert all(b"unneeded-provider-text" not in p.read_bytes() for p in f.market.rglob("*.json"))


def test_complete_overlap_fingerprint_sets_track_duplicate_variant_and_replay(f):
    from thericher_v2.data.kis_daily_price_endpoints import parse_kis_daily_price_endpoints

    f.seed()
    _, previous = script._load(f.market, receipt(f.seed_result)["pages"][-1])
    body = payload("20071231")
    body["output2"].append({**body["output2"][0], "high": "19"})
    page = parse_kis_daily_price_endpoints(
        KisMarketDataResponse.from_payload(body), query=previous.query
    )
    values = {}
    assert script._merge(values, previous) == 0
    assert script._merge(values, page) == 1
    assert len(values[page.rows[-1].session_date][2]) == 2
    assert script._merge(values, previous) == script._merge(values, page) == 0

    def rule(q):
        if q.method == "GET" and q.query["SYMB"] == "SPY":
            return KisMarketDataResponse.from_payload(body)

    f.rule = rule
    result = f.history(maximum_get_pages=1)
    manifest, _ = script._load(f.market, receipt(result)["pages"][0])
    assert manifest["overlap_unused_variant_date_count"] == 1
    root, i = index(f)
    _, reconstructed = script._verified_index(
        root, f.market, script._pins(), i["seed_binding"], f.artifacts
    )
    assert script._merge(reconstructed["SPY/AMS"], page) == 0


@pytest.mark.parametrize("success", [True, False])
def test_secret_echo_valid_or_error_body_never_retained(f, capsys, success):
    def rule(request):
        if request.method == "GET":
            body = payload(request.query["BYMD"]) if success else {"rt_cd": "1"}
            body["msg1"] = SECRET
            return KisMarketDataResponse.from_payload(body, status_code=200 if success else 403)

    f.rule = rule
    result = f.run("probe6")
    assert result["accepted_page_count"] == 0
    assert SECRET not in capsys.readouterr().out
    assert not list(f.market.rglob("*-rows.json"))
    assert all(SECRET.encode() not in p.read_bytes() for p in f.artifacts.rglob("*.json"))


def test_invalid_required_oc_query_does_not_stop_other_probe_questions(f):
    f.rule = lambda q: (
        KisMarketDataResponse.from_payload(payload(q.query["BYMD"], open="0"))
        if q.method == "GET" and q.query["SYMB"] == "GLD" and q.query["BYMD"] == "20210820"
        else None
    )
    result = f.run("probe6")
    assert result["accepted_page_count"] == 5 and result["failure_page_count"] == 1
    assert result["daily_GET_attempts"] == 6


def test_token_failure_has_no_get_and_no_token_retry(f):
    f.rule = lambda q: KisMarketDataResponse.from_payload({"message": SECRET}, status_code=403)
    result = f.run("probe6")
    assert result["reason"] == "auth_rejected"
    assert result["token_POST_attempts"] == 1 and result["daily_GET_attempts"] == 0
    assert len(f.requests) == 1


def test_local_token_guard_yields_without_sleep_or_http(f):
    f.run("probe6", "prior")
    f.requests.clear()
    before = f.seconds
    result = f.run("probe6", "blocked")
    assert result["reason"] == "token_request_not_due" and result["owned_next_due"]
    assert result["token_POST_attempts"] == 0 and not f.requests and before == f.seconds


def test_history_keeps_venues_separate_seed_vintages_and_source_cursor(f):
    result = f.history(maximum_get_pages=2)
    r = receipt(result)
    root, i = index(f)
    assert result["accepted_page_count"] == 2 and result["reason"] == "page_budget"
    assert result["token_POST_attempts"] == 1 and result["daily_GET_attempts"] == 2
    assert i["targets"]["SPY/AMS"]["cursor"] == "20261005"
    assert i["targets"]["SPY/AMS"]["continuation"] == "F"
    assert len(i["targets"]["TLT/AMS"]["chunks"]) == 2
    assert len(i["targets"]["TLT/NAS"]["chunks"]) == 1
    assert r["catalog"]["sha256"] == script._sha((root / "index.json").read_bytes())
    assert (Path(result["receipt_path"]).parent / "index.json").read_bytes() == (
        root / "index.json"
    ).read_bytes()
    seed_binding = i["targets"]["SPY/AMS"]["chunks"][0]
    assert seed_binding["market_relative_path"] in [
        x["market_relative_path"] for x in receipt(f.seed_result)["pages"]
    ]


def test_required_history_failure_stops_only_target_companion_continues(f):
    f.seed()
    f.rule = lambda q: (
        KisMarketDataResponse.from_payload(payload(q.query["BYMD"], clos="bad"))
        if q.method == "GET" and q.query["SYMB"] == "SPY"
        else None
    )
    result = f.history(maximum_get_pages=2)
    _, i = index(f)
    assert result["accepted_page_count"] == 1 and result["failure_page_count"] == 1
    assert i["targets"]["SPY/AMS"]["state"] == "stopped"
    assert i["targets"]["SPY/AMS"]["cursor"] == script.END
    assert i["targets"]["GLD/AMS"]["cursor"] == "20261006"


@pytest.mark.parametrize("variant", ["unused", "required_string"])
def test_overlap_compares_only_exact_required_strings_preserving_unused_variants(f, variant):
    f.seed()

    def rule(q):
        if q.method == "GET" and q.query["SYMB"] == "SPY":
            return KisMarketDataResponse.from_payload(
                payload("20071231", **({"high": "15"} if variant == "unused" else {"clos": "12.5"}))
            )

    f.rule = rule
    result = f.history(maximum_get_pages=1)
    if variant == "unused":
        assert result["accepted_page_count"] == 1
        manifest, _ = script._load(f.market, receipt(result)["pages"][0])
        assert manifest["overlap_unused_variant_date_count"] == 2
    else:
        assert result["accepted_page_count"] == 0
        assert receipt(result)["target_failures"][0]["reason"] == "oc_overlap_conflict"


def test_true_empty_history_scope_does_not_stop_companion(f):
    f.seed()
    f.rule = lambda q: (
        KisMarketDataResponse.from_payload({"rt_cd": "0", "output1": {}, "output2": []})
        if q.method == "GET" and q.query["SYMB"] == "SPY"
        else None
    )
    result = f.history(maximum_get_pages=2)
    assert result["coverage"]["SPY/AMS"]["state"] == "empty"
    assert result["coverage"]["GLD/AMS"]["cursor"] == "20261006"


def test_unknown_readonly_get_preserved_then_fresh_bounded_request_allowed(f):
    f.seed()
    failed = False

    def rule(q):
        nonlocal failed
        if q.method == "GET" and not failed:
            failed = True
            raise KisPaperMarketDataError("transport_failure", SECRET)

    f.rule = rule
    first = f.history("unknown", maximum_get_pages=1)
    old_bytes = Path(first["receipt_path"]).read_bytes()
    assert receipt(first)["target_failures"][0]["status"] == "unknown"
    second = f.history("fresh", maximum_get_pages=1)
    assert second["accepted_page_count"] == 1
    assert (
        receipt(second)["pages"][0]["market_relative_path"]
        != receipt(first)["target_failures"][0]["intent"]["market_relative_path"]
    )
    assert Path(first["receipt_path"]).read_bytes() == old_bytes


def test_snapshot_before_index_crash_restart_reattaches_exact_orphan_without_get(f, monkeypatch):
    f.seed()
    save = script._save

    def crash(root, i):
        if i["pending"] is None and any(
            not c["seed"] for t in i["targets"].values() for c in t["chunks"]
        ):
            raise OSError(SECRET)
        save(root, i)

    monkeypatch.setattr(script, "_save", crash)
    first = f.history("crash", maximum_get_pages=1)
    assert first["accepted_page_count"] == 1 and first["reason"] == "local_io_unavailable"
    assert first["coverage"]["SPY/AMS"]["cursor"] == script.END
    assert receipt(first)["pending"] is not None
    retained = {p: p.read_bytes() for p in f.market.rglob("*-manifest.json")}
    monkeypatch.setattr(script, "_save", save)
    f.requests.clear()
    recovered = f.history("recover", maximum_get_pages=1)
    assert recovered["status"] == "recovered" and recovered["recovered_page_count"] == 1
    assert (
        recovered["daily_GET_attempts"] == recovered["token_POST_attempts"] == 0 and not f.requests
    )
    assert recovered["coverage"]["SPY/AMS"]["cursor"] == "20261006"
    assert all(p.read_bytes() == data for p, data in retained.items())
    _, i = index(f)
    assert sum(not c["seed"] for c in i["targets"]["SPY/AMS"]["chunks"]) == 1


@pytest.mark.parametrize("which", ["rows", "manifest", "intent"])
def test_mutated_seed_bytes_reject_before_config_or_provider(f, which):
    seed = f.seed()
    binding = receipt(f.seed_result)["pages"][0]
    manifest_path = f.market / binding["market_relative_path"]
    manifest = json.loads(manifest_path.read_bytes())
    path = (
        manifest_path if which == "manifest" else f.market / manifest[which]["market_relative_path"]
    )
    path.write_bytes(path.read_bytes() + b" ")
    f.requests.clear()
    result = f.run("history", **seed, maximum_get_pages=1)
    assert result["reason"] == "catalog_invalid" and not f.requests


def test_seed_wrong_receipt_hash_rejected_before_request(f):
    seed = f.seed()
    seed["seed_sha256"] = "sha256:" + "0" * 64
    f.requests.clear()
    assert f.run("history", **seed)["reason"] == "catalog_invalid" and not f.requests


def test_resume_revalidates_exact_seed_receipt_no_latest_replacement(f):
    first = f.history(maximum_get_pages=1)
    root, _ = index(f)
    before = (root / "index.json").read_bytes()
    seed_path = Path(f.seed_result["receipt_path"])
    seed_path.write_bytes(seed_path.read_bytes() + b" ")
    f.requests.clear()
    second = f.history("bad-seed", maximum_get_pages=1)
    assert second["reason"] == "catalog_invalid" and not f.requests
    assert (root / "index.json").read_bytes() == before
    assert Path(first["receipt_path"]).exists()


@pytest.mark.parametrize("which", ["read", "copy"])
def test_final_catalog_io_failure_preserves_terminal_counts_not_advanced_projection(
    f, monkeypatch, which
):
    f.seed()
    if which == "copy":
        original = script._write

        def write(path, data):
            if path.name == "index.json" and path.is_relative_to(f.artifacts):
                raise OSError(SECRET)
            return original(path, data)

        monkeypatch.setattr(script, "_write", write)
    else:
        original = Path.read_bytes

        def read(path):
            if path.name == "index.json" and any(
                q.method == "GET" and q.query["BYMD"] == script.END for q in f.requests
            ):
                raise OSError(SECRET)
            return original(path)

        monkeypatch.setattr(Path, "read_bytes", read)
    result = f.history(maximum_get_pages=1)
    r = receipt(result)
    assert result["accepted_page_count"] == 1 and result["daily_GET_attempts"] == 1
    assert r["catalog"] == {"status": "unavailable", "sha256": None}
    assert result["coverage"] == {} and r["pending_projection"] == "unavailable"
    assert SECRET not in json.dumps(r)


def test_final_pin_read_error_preserves_terminal_observed_pages(f, monkeypatch):
    pins, load = script._pins, script._load
    done = False

    def read_pins():
        if done:
            raise OSError(SECRET)
        return pins()

    def read_page(*args):
        nonlocal done
        result = load(*args)
        done = result[0]["question_ordinal"] == 6
        return result

    monkeypatch.setattr(script, "_pins", read_pins)
    monkeypatch.setattr(script, "_load", read_page)
    result = f.run("probe6")
    r = receipt(result)
    assert result["accepted_page_count"] == 6 and result["reason"] == "source_hash_unavailable"
    assert r["source_reattestation"] == "unavailable" and r["source_pins"]


def test_storage_floor_no_config_or_provider(f):
    result = script.run_probe6(
        market_root=f.market,
        artifact_root=f.artifacts,
        run_label="floor",
        dotenv_path=Path("never-read"),
        config_loader=lambda path: pytest.fail("config read"),
        space_check=lambda count: True,
    )
    assert result["reason"] == "storage_floor" and result["daily_GET_attempts"] == 0


def test_worker_busy_no_provider(f, monkeypatch):
    f.history("initial", maximum_get_pages=1)
    root, _ = index(f)
    live = root / "index.json"
    read = Path.read_bytes

    def reject_foreign_catalog(path):
        assert path != live, "unowned catalog read"
        return read(path)

    f.requests.clear()
    monkeypatch.setattr(script, "_acquire_worker_lock", lambda **kwargs: None)
    monkeypatch.setattr(Path, "read_bytes", reject_foreign_catalog)
    assert f.run("probe6", "busy-probe")["reason"] == "worker_busy" and not f.requests
    result = f.history("busy-history", maximum_get_pages=1)
    r = receipt(result)
    assert result["reason"] == "worker_busy" and not f.requests
    assert r["catalog"] == {"status": "unavailable", "sha256": None}
    assert result["coverage"] == {} and r["pending_projection"] == "unavailable"
    assert not (Path(result["receipt_path"]).parent / "index.json").exists()


def test_runtime_budget_stops_before_another_get(f):
    f.seed()
    result = f.history(maximum_get_pages=180, runtime_seconds=15)
    assert result["reason"] == "runtime_budget" and result["daily_GET_attempts"] == 0


def test_path_escape_and_existing_receipt_never_overwrite(f):
    with pytest.raises(script.Stop):
        script._path(f.market, "../outside")
    first = f.run("probe6")
    data = Path(first["receipt_path"]).read_bytes()
    with pytest.raises(script.Stop):
        f.run("probe6")
    assert Path(first["receipt_path"]).read_bytes() == data


def test_cli_redacts_dynamic_failure_and_has_exact_probe_mode(monkeypatch, capsys):
    def fail(**kwargs):
        assert kwargs["mode"] == "probe6"
        raise OSError(SECRET)

    monkeypatch.setattr(script, "run_collection", fail)
    assert script.main(["--probe6", "--run-label", "synthetic"]) == 20
    assert json.loads(capsys.readouterr().out) == {
        "status": "unavailable",
        "reason": "local_io_unavailable",
    }


@pytest.mark.parametrize("mutation", ["integer", "string", "relabeled", "reordered"])
def test_seed_flags_and_exact_pinned_probe_membership_order_reject(f, mutation):
    f.history("initial", maximum_get_pages=1)
    root, i = index(f)
    if mutation in {"integer", "string"}:
        i["targets"]["SPY/AMS"]["chunks"][0]["seed"] = 1 if mutation == "integer" else "True"
    elif mutation == "relabeled":
        i["targets"]["SPY/AMS"]["chunks"][-1]["seed"] = True
        i["targets"]["SPY/AMS"].update(cursor=script.END, continuation=None)
    else:
        i["targets"]["TLT/AMS"]["chunks"].reverse()
    script._save(root, i)
    before = (root / "index.json").read_bytes()
    f.requests.clear()
    result = f.history("reject", maximum_get_pages=1)
    assert result["reason"] == "catalog_invalid" and not f.requests
    assert result["coverage"] == {} and result["recovered_page_count"] == 0
    assert (root / "index.json").read_bytes() == before


def test_nonadvancing_orphan_and_nonseed_replay_reject_before_cursor_or_get(f, monkeypatch):
    f.seed()
    save = script._save

    def crash(root, i):
        if i["pending"] is None and any(
            not c["seed"] for t in i["targets"].values() for c in t["chunks"]
        ):
            raise OSError(SECRET)
        save(root, i)

    monkeypatch.setattr(script, "_save", crash)
    first = f.history("crash", maximum_get_pages=1)
    root, i = index(f)
    binding = receipt(first)["pages"][0]
    path = f.market / binding["market_relative_path"]
    manifest, page = script._load(f.market, binding)
    latest = page.rows[-1]
    single = script.KisDailyEndpointPage(
        page.query,
        (latest,),
        1,
        0,
        page.source_body_sha256,
        page.continuation,
        ((latest.session_date, latest.provider_row_sha256),),
    )
    rows = script._json([latest.as_document()])
    (f.market / manifest["rows"]["market_relative_path"]).write_bytes(rows)
    manifest["rows"]["sha256"] = script._sha(rows)
    manifest["facts"] = single.safe_facts()
    manifest["source_row_fingerprints"] = list(single.source_row_fingerprints)
    path.write_bytes(script._json(manifest))
    monkeypatch.setattr(script, "_save", save)
    before = (root / "index.json").read_bytes()
    f.requests.clear()
    rejected = f.history("orphan-reject", maximum_get_pages=1)
    assert rejected["reason"] == "nonadvancing_cursor" and not f.requests
    assert rejected["recovered_page_count"] == 0
    assert rejected["coverage"]["SPY/AMS"]["cursor"] == script.END
    assert (root / "index.json").read_bytes() == before
    i["pending"] = None
    i["targets"]["SPY/AMS"]["chunks"].append(
        {**binding, "sha256": script._sha(path.read_bytes()), "seed": False}
    )
    i["targets"]["SPY/AMS"]["continuation"] = page.continuation
    save(root, i)
    with pytest.raises(script.Stop, match="nonadvancing_cursor"):
        script._verified_index(root, f.market, script._pins(), i["seed_binding"], f.artifacts)


def test_worker_lock_excludes_competing_writer_through_snapshot_and_terminal(f, monkeypatch):
    f.seed()
    root = (
        f.market
        / f"us_equities/kis_paper_private/cross-asset-oc/{script.VERSION}/history/oc-venues-v1"
    )
    write = script._write
    boundaries = []

    def guarded(path, data):
        if path.parent.name == "boundary" and path.name in {"index.json", "receipt.json"}:
            competing = script._acquire_worker_lock(root=root, observed_at=datetime.now(UTC))
            if competing is not None:
                script._release_worker_lock(competing)
            assert competing is None
            boundaries.append(path.name)
        return write(path, data)

    monkeypatch.setattr(script, "_write", guarded)
    result = f.history("boundary", maximum_get_pages=1)
    assert boundaries == ["index.json", "receipt.json"]
    assert receipt(result)["catalog"]["sha256"] == script._sha((root / "index.json").read_bytes())
    available = script._acquire_worker_lock(root=root, observed_at=datetime.now(UTC))
    assert available is not None
    script._release_worker_lock(available)


def test_release_failure_cannot_erase_already_writable_terminal(f, monkeypatch):
    f.seed()
    release = script._release_worker_lock

    def fail_after_release(lock):
        release(lock)
        if lock is not None:
            raise RuntimeError(SECRET)

    monkeypatch.setattr(script, "_release_worker_lock", fail_after_release)
    result = f.history("release-failure", maximum_get_pages=1)
    r = receipt(result)
    assert result["accepted_page_count"] == 1
    assert result["receipt_sha256"] == script._sha(Path(result["receipt_path"]).read_bytes())
    assert r["catalog"]["status"] == "matched" and SECRET not in json.dumps(r)
