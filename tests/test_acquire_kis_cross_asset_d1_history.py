from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataTokenStartGate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cross_asset_history_test", ROOT / "scripts/acquire_kis_cross_asset_d1_history.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)
SECRET = "fake_secret_never_retained"


def row(date, price="10"):
    return {"xymd": date, "open": price, "high": "20", "low": "1", "clos": "10", "tvol": "100"}


class Clock:
    seconds = 0.0

    def now(self):
        return datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=self.seconds)

    def monotonic(self):
        return self.seconds

    def sleep(self, delay):
        assert 0 <= delay <= 1.000001
        self.seconds += delay


@pytest.fixture
def h(tmp_path):
    temporary = tmp_path.parent / uuid.uuid4().hex[:8]
    clock = Clock()
    calls = []
    loads = []
    transports = []

    def factory(**kwargs):
        class Transport:
            def request(self, request):
                if request.url.endswith(KIS_PAPER_TOKEN_PATH):
                    if not kwargs["token_start_gate"].claim_token_request_start():
                        raise KisPaperMarketDataError("token_request_not_due")
                kwargs["request_gate"].wait_for_request_slot()
                calls.append(request)
                clock.seconds += 0.01
                if request.method == "POST":
                    return KisMarketDataResponse.from_payload({"access_token": "synthetic-token"})
                return response(request)

        t = Transport()
        transports.append(t)
        return t

    def response(request):
        return KisMarketDataResponse.from_payload(
            {
                "rt_cd": "0",
                "output1": {},
                "output2": [row(request.query["BYMD"]), row(script.START)],
            }
        )

    def loader(path):
        loads.append(path)
        return KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret")

    fixture = SimpleNamespace(
        clock=clock, calls=calls, loads=loads, transports=transports, response=response
    )

    def dynamic_factory(**kwargs):
        nonlocal response
        response = fixture.response
        fixture.gate = kwargs["request_gate"]
        return factory(**kwargs)

    fixture.kwargs = dict(
        market_root=temporary / "m",
        artifact_root=temporary / "a",
        repository_root=ROOT,
        run_label="history-1",
        dotenv_path=tmp_path / "never-read.env",
        clock=clock.now,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
        config_loader=loader,
        transport_factory=dynamic_factory,
        space_check=lambda count: False,
    )
    return fixture


def receipt(result):
    return json.loads(Path(result["receipt_path"]).read_bytes())


def root(h):
    return (
        h.kwargs["market_root"]
        / f"us_equities/kis_paper_private/cross-asset-d1/{script.GOAL}/canonical-trio-v1"
    )


def index(h):
    return json.loads((root(h) / "index.json").read_bytes())


def next_run(h):
    h.kwargs["run_label"] += "-next"
    h.clock.seconds += 301
    h.calls.clear()
    h.loads.clear()


def seed(h):
    def response(request):
        anchor = request.query["BYMD"]
        rows = [] if anchor == "20071231" else [row(anchor), row("20261006")]
        return KisMarketDataResponse.from_payload({"rt_cd": "0", "output1": {}, "output2": rows})

    h.response = response
    kwargs = {
        k: v for k, v in h.kwargs.items() if k not in {"maximum_get_pages", "runtime_seconds"}
    }
    result = script.probe.run_probe(**{**kwargs, "run_label": "seed-probe"})
    assert result["status"] == "partial" and result["accepted_page_count"] == 6
    assert result["reason"] == "empty_response"
    h.kwargs.update(seed_receipt=Path(result["receipt_path"]), seed_sha256=result["receipt_sha256"])
    h.clock.seconds += 301
    h.calls.clear()
    h.loads.clear()
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {}, "output2": [row(request.query["BYMD"]), row(script.START)]}
    )
    return result


def test_three_fixed_assets_one_client_token_and_typed_private_writer(h):
    result = script.run_history(**h.kwargs)
    assert result["status"] == "complete"
    assert result["accepted_page_count"] == 3
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 3}
    assert len(h.transports) == len(h.loads) == 1
    assert {(r.query["SYMB"], r.query["EXCD"], r.query["MODP"]) for r in h.calls[1:]} == {
        ("SPY", "AMS", "0"),
        ("TLT", "NAS", "0"),
        ("GLD", "AMS", "0"),
    }
    assert all(r.daily_adjustment_modes is None for r in h.calls)
    assert all(
        t["state"] == "window_covered" and t["unique_date_count"] == 2
        for t in result["targets"].values()
    )
    for target in index(h)["targets"].values():
        c = target["chunks"][0]
        assert (
            script._snapshot(root(h), c["manifest_path"], ROOT)["manifest_hash"]
            == c["manifest_hash"]
        )
    r = receipt(result)
    assert (
        script.probe._sha((Path(result["receipt_path"]).parent / "index.json").read_bytes())
        == r["catalog"]["sha256"]
    )


def test_partial_probe_seeds_current_trio_not_deep_pages_or_vintage_relabel(h):
    original = seed(h)
    result = script.run_history(**h.kwargs)
    assert result["seed_page_count"] == 3 and result["accepted_page_count"] == 3
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 3}
    assert all(r.query["BYMD"] == "20261006" for r in h.calls[1:])
    for target in index(h)["targets"].values():
        first = target["chunks"][0]
        assert first["seed"]["receipt_sha256"] == original["receipt_sha256"]
        assert first["collected_at_utc"] == receipt(original)["completed_at_utc"]
        assert first["seed"]["original_source_pins"]
        assert first["row_count"] == 2


def test_seed_raw_mutation_stops_before_config_no_fallback_requests(h):
    original = seed(h)
    r = receipt(original)
    raw = h.kwargs["market_root"] / r["private_daily_responses"][0]["market_relative_path"]
    raw.write_bytes(raw.read_bytes() + b" ")
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "seed_binding_invalid"
    assert h.loads == h.calls == []
    assert all(t["cursor"] == script.END for t in index(h)["targets"].values())


def test_old_probe_source_archive_is_exactly_hash_bound(h):
    original = seed(h)
    path = Path(original["receipt_path"])
    r = receipt(original)
    archive = path.parent / "source-before-terminal-pin-repair"
    for name in script.probe.SOURCE_FILES:
        destination = archive / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            b"retained original probe"
            if name.startswith("scripts/")
            else (ROOT / name).read_bytes()
        )
    r["source_pins"] = {
        name: script.probe._sha((archive / name).read_bytes()) for name in script.probe.SOURCE_FILES
    }
    contract_path = path.parent / "contract.json"
    contract = json.loads(contract_path.read_bytes())
    contract["source_pins"] = r["source_pins"]
    contract_path.write_text(json.dumps(contract))
    r["contract_sha256"] = script.probe._sha(contract_path.read_bytes())
    path.write_text(json.dumps(r))
    h.kwargs.update(seed_sha256=script.probe._sha(path.read_bytes()), seed_source_root=archive)
    assert script.run_history(**h.kwargs)["seed_page_count"] == 3


def test_page_budget_is_180_attempts_not_per_asset_and_exact_restart_cursor(h):
    def response(request):
        anchor = datetime.strptime(request.query["BYMD"], "%Y%m%d")
        return KisMarketDataResponse.from_payload(
            {
                "rt_cd": "0",
                "output1": {},
                "output2": [
                    row(anchor.strftime("%Y%m%d")),
                    row((anchor - timedelta(days=1)).strftime("%Y%m%d")),
                ],
            }
        )

    h.response = response
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "page_budget" and result["accepted_page_count"] == 180
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 180}
    assert all(
        t["snapshot_count"] == 60 and t["unique_date_count"] == 61
        for t in result["targets"].values()
    )
    cursors = {s: t["cursor"] for s, t in result["targets"].items()}
    next_run(h)
    h.kwargs["maximum_get_pages"] = 1
    again = script.run_history(**h.kwargs)
    assert again["accepted_page_count"] == 1
    request = h.calls[1]
    assert request.query["BYMD"] == cursors[request.query["SYMB"]]


@pytest.mark.parametrize("status,rt_cd", [(403, "1"), (200, "1"), (500, "1")])
def test_error_body_never_reaches_storage_or_output(h, capsys, status, rt_cd):
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {"rt_cd": rt_cd, "msg1": SECRET, "error_description": SECRET}, status_code=status
    )
    result = script.run_history(**h.kwargs)
    print(json.dumps(result))
    assert SECRET not in capsys.readouterr().out
    assert len(h.calls) == 2 and result["accepted_page_count"] == 0
    assert not list(root(h).glob("snapshot=*"))
    assert index(h)["pending"] is None
    assert all(t["cursor"] == script.END for t in index(h)["targets"].values())
    for path in h.kwargs["market_root"].parent.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()


def test_success_body_extras_and_token_body_never_retained(h):
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {},
            "output2": [row(request.query["BYMD"]), row(script.START)],
            "extra": SECRET,
        }
    )
    assert script.run_history(**h.kwargs)["status"] == "complete"
    for path in h.kwargs["market_root"].parent.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()
            assert b"synthetic-token" not in path.read_bytes()


def test_local_token_guard_no_post_no_get_and_seeds_still_retained(h):
    seed(h)
    control = h.kwargs["market_root"] / "us_equities/kis_paper_private/collection-control-v1"
    gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=h.clock.now)
    assert gate.claim_token_request_start()
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "token_request_not_due"
    assert result["call_counts"] == {"token_attempts": 0, "daily_page_attempts": 0}
    assert result["seed_page_count"] == 3 and result["owned_next_due_utc"]
    assert h.calls == []


def test_floor_before_credential_loader(h):
    h.kwargs["space_check"] = lambda count: True
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "storage_floor" and h.loads == h.calls == []


def test_empty_ends_only_one_asset_scope(h):
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {},
            "output2": []
            if request.query["SYMB"] == "TLT"
            else [row(request.query["BYMD"]), row(script.START)],
        }
    )
    result = script.run_history(**h.kwargs)
    assert result["targets"]["TLT"]["state"] == "source_limited"
    assert result["targets"]["TLT"]["unique_date_count"] == 0
    assert (
        result["targets"]["SPY"]["state"] == result["targets"]["GLD"]["state"] == "window_covered"
    )


@pytest.mark.parametrize("failure", ["conflict", "future", "nonadvancing"])
def test_bad_page_never_advances_cursor_or_writes_snapshot(h, failure):
    rows = {
        "conflict": [row(script.END), row(script.END, "11")],
        "future": [row("20261008")],
        "nonadvancing": [row(script.END)],
    }
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {}, "output2": rows[failure]}
    )
    result = script.run_history(**h.kwargs)
    assert result["accepted_page_count"] == 0
    assert not list(root(h).glob("snapshot=*"))
    assert all(t["cursor"] == script.END for t in index(h)["targets"].values())
    assert sum(t["state"] == "blocked" for t in result["targets"].values()) == 1


@pytest.mark.parametrize("crash_point", ["after_writer", "before_index"])
def test_exact_crash_snapshot_recovery_without_new_request(h, monkeypatch, crash_point):
    if crash_point == "after_writer":
        original = script.write_kis_paper_private_daily_cache

        def fail(**kwargs):
            original(**kwargs)
            raise OSError(SECRET)

        monkeypatch.setattr(script, "write_kis_paper_private_daily_cache", fail)
    else:
        original = script._apply_snapshot
        monkeypatch.setattr(
            script, "_apply_snapshot", lambda *args: (_ for _ in ()).throw(OSError(SECRET))
        )
    first = script.run_history(**h.kwargs)
    assert first["reason"] == "local_io_or_contract_invalid" and index(h)["pending"]
    original_bytes = {p: p.read_bytes() for p in root(h).glob("snapshot=*/manifest.json")}
    if crash_point == "after_writer":
        monkeypatch.setattr(script, "write_kis_paper_private_daily_cache", original)
    else:
        monkeypatch.setattr(script, "_apply_snapshot", original)
    next_run(h)
    recovered = script.run_history(**h.kwargs)
    assert recovered["status"] == "recovered" and h.calls == h.loads == []
    assert index(h)["pending"] is None
    assert sum(len(t["chunks"]) for t in index(h)["targets"].values()) == 1
    assert all(p.read_bytes() == b for p, b in original_bytes.items())


def test_unknown_readonly_get_preserved_and_fresh_bounded_same_query_allowed(h):
    h.response = lambda request: (_ for _ in ()).throw(RuntimeError(SECRET))
    first = script.run_history(**h.kwargs)
    assert first["reason"] == "local_io_or_contract_invalid" and index(h)["pending"]
    before = (root(h) / "intents/000001.json").read_bytes()
    old_receipt = Path(first["receipt_path"]).read_bytes()
    old_query = dict(h.calls[1].query)
    next_run(h)
    h.kwargs["maximum_get_pages"] = 1
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {}, "output2": [row(request.query["BYMD"]), row(script.START)]}
    )
    second = script.run_history(**h.kwargs)
    assert second["accepted_page_count"] == 1
    assert dict(h.calls[1].query) == old_query
    assert index(h)["sequence"] == 2
    assert (root(h) / "intents/000001.json").read_bytes() == before
    assert Path(first["receipt_path"]).read_bytes() == old_receipt
    assert (
        json.loads((root(h) / "intents/000001-unknown.json").read_bytes())["category"]
        == "read_only_GET_outcome_unknown"
    )


def test_mutated_catalog_cursor_rejects_without_loading_credentials(h):
    script.run_history(**h.kwargs)
    state = index(h)
    state["targets"]["SPY"]["cursor"] = script.END
    (root(h) / "index.json").write_text(json.dumps(state))
    before = (root(h) / "index.json").read_bytes()
    next_run(h)
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "local_io_or_contract_invalid"
    assert h.loads == h.calls == []
    assert (root(h) / "index.json").read_bytes() == before


def test_deadline_stops_before_another_http_start(h):
    h.response = lambda request: (
        setattr(h.clock, "seconds", 890)
        or KisMarketDataResponse.from_payload(
            {
                "rt_cd": "0",
                "output1": {},
                "output2": [row(request.query["BYMD"]), row(script.START)],
            }
        )
    )
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "runtime_budget" and len(h.calls) == 2


def test_no_execute_no_reads_or_writes(h, monkeypatch, capsys):
    monkeypatch.setattr(script, "run_history", lambda **kwargs: pytest.fail("executed"))
    assert script.main(["--run-label", "preview"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "not_executed"
    assert h.calls == h.loads == []


@pytest.mark.parametrize("failure", ["read", "copy"])
def test_terminal_catalog_io_failure_preserves_counts_receipt_and_known_cursors(
    h, monkeypatch, failure
):
    if failure == "read":
        original = Path.read_bytes

        def read(path):
            if path == root(h) / "index.json" and len(h.calls) == 4:
                raise OSError(SECRET)
            return original(path)

        monkeypatch.setattr(Path, "read_bytes", read)
    else:
        original = script.probe._write_new

        def write(path, data):
            if path.name == "index.json" and path.is_relative_to(h.kwargs["artifact_root"]):
                raise OSError(SECRET)
            return original(path, data)

        monkeypatch.setattr(script.probe, "_write_new", write)
    result = script.run_history(**h.kwargs)
    assert result["status"] == "partial" and result["reason"] == "catalog_projection_unavailable"
    assert result["accepted_page_count"] == 3
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 3}
    if failure == "copy":
        assert all(t["cursor"] == script.START for t in result["targets"].values())
    else:
        assert result["targets"] == {}
    r = receipt(result)
    assert r["catalog"]["status"] == "unavailable" and r["catalog"]["sha256"] is None
    assert SECRET not in json.dumps(r)


def test_terminal_source_pin_failure_never_claims_complete(h, monkeypatch):
    initial = script._pins(ROOT)

    def pins(repository):
        if len(h.calls) == 4 and all(len(t["chunks"]) for t in index(h)["targets"].values()):
            raise OSError(SECRET)
        return initial

    monkeypatch.setattr(script, "_pins", pins)
    result = script.run_history(**h.kwargs)
    assert result["status"] == "partial" and result["reason"] == "source_hash_unavailable"
    assert result["accepted_page_count"] == 3
    assert receipt(result)["source_reattestation"] == "unavailable"


def test_source_hash_drift_after_get_preserves_exact_unknown_intent(h, monkeypatch):
    initial = script._pins(ROOT)
    monkeypatch.setattr(
        script,
        "_pins",
        lambda repository: (
            initial
            if len(h.calls) < 2
            else {**initial, "scripts/acquire_kis_cross_asset_d1_history.py": "sha256:" + "0" * 64}
        ),
    )
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "source_hash_changed"
    assert result["accepted_page_count"] == 0 and index(h)["pending"]
    assert receipt(result)["pending"] == index(h)["pending"]
    assert not list(root(h).glob("snapshot=*"))


def test_identical_page_duplicates_dedupe_with_manifest_input_counts(h):
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {},
            "output2": [row(request.query["BYMD"])] * 2 + [row(script.START)],
        }
    )
    result = script.run_history(**h.kwargs)
    assert result["status"] == "complete"
    for target in index(h)["targets"].values():
        path = root(h) / target["chunks"][0]["manifest_path"]
        dedupe = json.loads(path.read_bytes())["deduplication"]
        assert dedupe["input_row_count"] == 3 and dedupe["unique_row_count"] == 2
        assert dedupe["exact_duplicate_rows_removed"] == 1


def test_seed_overlap_conflict_blocks_only_affected_asset_preserves_sources(h):
    seed(h)
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {},
            "output2": [row(request.query["BYMD"], "11"), row(script.START)],
        }
    )
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "daily_duplicate_conflict"
    assert result["seed_page_count"] == 3 and result["accepted_page_count"] == 0
    affected = h.calls[1].query["SYMB"]
    assert result["targets"][affected]["state"] == "blocked"
    before = {p: p.read_bytes() for p in root(h).glob("snapshot=*/manifest.json")}
    next_run(h)
    h.response = lambda request: KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {}, "output2": [row(request.query["BYMD"]), row(script.START)]}
    )
    resumed = script.run_history(**h.kwargs)
    assert resumed["accepted_page_count"] == 2
    assert all(r.query["SYMB"] != affected for r in h.calls[1:])
    assert all(p.read_bytes() == data for p, data in before.items())


def test_rate_limit_stops_without_retry_and_projects_existing_fresh_token_due(h):
    def response(request):
        h.gate.record_rate_limit()
        return KisMarketDataResponse.from_payload({"msg1": SECRET}, status_code=429)

    h.response = response
    result = script.run_history(**h.kwargs)
    assert result["reason"] == "rate_limited" and len(h.calls) == 2
    assert result["call_counts"] == {"token_attempts": 1, "daily_page_attempts": 1}
    assert result["owned_next_due_utc"] == "2026-10-08T00:05:00Z"
    assert not list(root(h).glob("snapshot=*"))


@pytest.mark.parametrize("phase", ["intent_pointer", "completion_pointer", "cursor_publication"])
def test_repeat_index_write_crash_reattaches_exact_orphans_never_projects_ahead(
    h, monkeypatch, phase
):
    original = script._save_index

    def fail(cache_root, state):
        pending = state["pending"]
        has_chunks = any(t["chunks"] for t in state["targets"].values())
        hit = (
            phase == "intent_pointer"
            and pending is not None
            and pending["intent_path"].endswith("000001.json")
            or phase == "completion_pointer"
            and pending is not None
            and pending["intent_path"].endswith("-accepted.json")
            or phase == "cursor_publication"
            and pending is None
            and has_chunks
        )
        if hit:
            raise OSError(SECRET)
        return original(cache_root, state)

    monkeypatch.setattr(script, "_save_index", fail)
    first = script.run_history(**h.kwargs)
    assert first["reason"] == "local_io_or_contract_invalid"
    assert all(
        t["cursor"] == script.END and t["snapshot_count"] == 0 for t in first["targets"].values()
    )
    preserved = {p: p.read_bytes() for p in (root(h) / "intents").iterdir()}
    next_run(h)
    second = script.run_history(**h.kwargs)
    assert second["reason"] == "local_io_or_contract_invalid"
    assert h.calls == []
    assert all(p.read_bytes() == data for p, data in preserved.items())
    assert all(
        t["cursor"] == script.END and t["snapshot_count"] == 0 for t in second["targets"].values()
    )
    monkeypatch.setattr(script, "_save_index", original)
    next_run(h)
    h.kwargs["maximum_get_pages"] = 1
    third = script.run_history(**h.kwargs)
    if phase == "intent_pointer":
        assert third["accepted_page_count"] == 1
        assert h.calls[1].query["BYMD"] == script.END
    else:
        assert third["status"] == "recovered" and h.calls == []
    assert all(p.read_bytes() == data for p, data in preserved.items())
    assert sum(len(t["chunks"]) for t in index(h)["targets"].values()) == 1
