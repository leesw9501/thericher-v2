from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_broad512_later_refresh as r
from thericher_v2.execution.kis_market_data import (
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionTarget,
    run_bounded_kis_paper_private_daily_collection,
    write_kis_paper_private_daily_cache,
)


def plan_fixture():
    keys = [f"S{i:04}/NAS/MODP=0" for i in range(512)]
    days = [(datetime(2026, 6, 26) + timedelta(days=i)).date().isoformat() for i in range(71)]
    return {
        "metadata": {
            "keys": keys,
            "scheduled_dates": days,
            "original_target_keys": keys[:128],
            "permutation": list(range(512)),
            "scope_pins": {"synthetic": True},
            "clocks": [],
            "calendar71_sha256": "synthetic",
            "reference_manifest_sha256": "synthetic",
        },
        "source_pins": {},
    }


class Transport:
    def __init__(self, pages):
        self.pages, self.requests = list(pages), []

    def request(self, request):
        self.requests.append(request)
        if request.method == "POST":
            return KisMarketDataResponse.from_payload({"access_token": "synthetic-token"})
        value = self.pages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def page(dates, continuation=""):
    rows = [
        {
            "xymd": d.replace("-", ""),
            "open": "100.001",
            "high": "102.002",
            "low": "99.003",
            "clos": "101.004",
            "tvol": "777.005",
        }
        for d in sorted(dates, reverse=True)
    ]
    return KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {"nrec": str(len(rows))}, "output2": rows},
        headers={"tr_cont": continuation},
    )


def client(transport):
    return KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret"),
        transport=transport,
        max_daily_page_attempts=1024,
    )


def make_snapshot(root, key, dates, run_id="20261011T010101Z"):
    symbol, exchange, _ = key.split("/")
    result = run_bounded_kis_paper_private_daily_collection(
        client(Transport([page(dates)])),
        code_revision="synthetic",
        target=KisPaperPrivateDailyCollectionTarget(
            symbol=symbol,
            exchange=exchange,
            anchor_date=r.ANCHOR,
            approved_symbol_exchanges={symbol: frozenset({exchange})},
        ),
    )
    path, _ = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=root,
        repo_root=root.parent / "repo",
        run_id=run_id,
        collector_objective_id=r.VERSION,
        collector_version=r.VERSION,
        backfill_context={
            "contract_version": r.KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
            "cursor_strategy": "oldest_session_date_with_exact_overlap",
            "input_cursor_date": r.ANCHOR,
            "logical_cursor_persisted": True,
            "output_cursor_date": result.rows[0].xymd if result.rows else None,
            "target_key": key,
        },
    )
    return path


def test_mock_metadata_512_original_order_and_71_clock_before_credentials(monkeypatch):
    monkeypatch.setattr(
        r, "load_kis_paper_market_data_config", lambda *a, **k: pytest.fail("credentials accessed")
    )
    keys = tuple(plan_fixture()["metadata"]["keys"])
    day = date(2026, 6, 26)
    calendar = {}
    while day <= date(2026, 10, 7):
        if day.weekday() < 5 and day not in {date(2026, 7, 3), date(2026, 9, 7)}:
            calendar[day] = tuple(
                datetime(day.year, day.month, day.day, hour, tzinfo=UTC) for hour in (12, 13, 20)
            )
        day += timedelta(days=1)
    fake = SimpleNamespace(
        Budget=lambda deadline: None,
        SOURCE_PINS={},
        DATA=Path("synthetic-reference"),
        CALENDAR=Path("synthetic-calendar"),
        CALENDAR_PIN="synthetic-calendar-pin",
        MANIFEST_PIN="synthetic-reference-pin",
        document=r.document,
        canonical_metadata_parsers=lambda budget: (lambda raw: calendar, lambda key: True),
        pinned_bytes=lambda *args: b"{}",
        metadata_binding=lambda *args: SimpleNamespace(keys=keys, permutation=tuple(range(512))),
        SCOPE_PINS={"original128_order_sha256": r.digest(r.encode(keys[:128]))},
    )
    monkeypatch.setattr(r, "load_pinned_module", lambda *args: fake)
    monkeypatch.setattr(
        r, "read", lambda *args: r.encode({"selected_target_keys": list(keys[:128])})
    )
    monkeypatch.setattr(r, "attest", lambda path, pin=None: pin)
    scope = r.metadata_scope()
    assert len(scope["keys"]) == 512 and len(set(scope["keys"])) == 512
    assert scope["keys"][:128] == scope["original_target_keys"]
    assert scope["scheduled_dates"][0] == "2026-06-26"
    assert scope["scheduled_dates"][21] == "2026-07-28"
    assert scope["scheduled_dates"][-1] == "2026-10-06"
    assert len(scope["clocks"]) == 71 and scope["score_cohorts"] == 10
    assert sorted(scope["permutation"]) == list(range(512))


def test_two_real_parser_pages_keep_continuation_and_measure_incremental_yield():
    plan = plan_fixture()
    days = plan["metadata"]["scheduled_dates"]
    state = r.new_cursor(plan, "synthetic", time.time())
    state["pending"] = {"target_key": plan["metadata"]["keys"][0]}
    transport = Transport([page(days, "F"), page([days[0]], "F")])
    debits = []
    owned = r.OwnedClient(
        client(transport), state, lambda: debits.append(state["daily_attempts"]), time.time(), days
    )
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    result = run_bounded_kis_paper_private_daily_collection(
        owned,
        code_revision="synthetic",
        target=KisPaperPrivateDailyCollectionTarget(
            symbol="S0000",
            exchange="NAS",
            anchor_date=r.ANCHOR,
            approved_symbol_exchanges={"S0000": frozenset({"NAS"})},
        ),
        sleeper=sleep,
        monotonic_clock=lambda: clock[0],
    )
    assert result.status == "observed" and result.stop_outcome == "two_pages_completed"
    assert debits == [1, 2] and owned.call_counts.token_attempts == 1
    first, second = owned.page_observations
    assert len(first["needed"]) == 71 and first["floor_reached"]
    assert first["provider_continuation"] and not second["needed"] - first["needed"]
    assert transport.requests[-1].query["BYMD"] == days[0].replace("-", "")
    assert transport.requests[-1].headers["tr_cont"] == "F"


def test_failed_attempt_debit_is_durable_and_cap_cannot_refund():
    plan = plan_fixture()
    state = r.new_cursor(plan, "synthetic", time.time())
    state["daily_attempts"] = 1023
    state["pending"] = {"target_key": plan["metadata"]["keys"][0]}
    persisted = []
    transport = Transport([KisPaperMarketDataError("transport_failure")])
    owned = r.OwnedClient(
        client(transport), state, lambda: persisted.append(copy.deepcopy(state)), time.time(), []
    )
    query = KisPaperDailyQuery(
        symbol="S0000",
        exchange="NAS",
        by_date=r.ANCHOR,
        approved_symbol_exchanges={"S0000": frozenset({"NAS"})},
    )
    with pytest.raises(KisPaperMarketDataError):
        owned.fetch_daily_raw_page(query)
    assert persisted[-1]["daily_attempts"] == 1024
    with pytest.raises(r.Stop, match="attempt_budget"):
        owned.fetch_daily_raw_page(query)
    assert len(transport.requests) == 2  # One token and one failed daily call.


def test_shared_token_due_yields_without_credentials_or_sleep(monkeypatch, tmp_path):
    token = r.KisPaperMarketDataTokenStartGate(control_root=tmp_path)
    rate = r.KisPaperMarketDataRateGate(control_root=tmp_path)
    assert token.claim_token_request_start()
    monkeypatch.setattr(r, "make_client", lambda *a: pytest.fail("client accessed"))
    monkeypatch.setattr(r.time, "sleep", lambda s: pytest.fail("sleep accessed"))
    with pytest.raises(r.Stop, match="fresh_token_yield") as caught:
        r.due_check(rate, token)
    assert caught.value.due is not None
    with pytest.raises(r.Stop, match="shared_rate_yield"):
        r.controlled_sleep(60, time.time())


def test_orphan_commit_exact_identity_nooverwrite_and_empty(tmp_path):
    plan = plan_fixture()
    root = tmp_path / "cache"
    key = plan["metadata"]["keys"][0]
    pending = {"target_key": key, "run_id": "20261011T010101Z", "attempt_base": 0}
    path = make_snapshot(root, key, [])
    assert r.snapshot_path(root, pending) == path
    state = r.new_cursor(plan, "synthetic", time.time())
    r.commit_chunk(state, pending, path, root, plan["metadata"]["scheduled_dates"])
    assert state["position"] == 1 and state["targets"][0]["state"] == "empty"
    assert len(state["targets"]) == 512
    assert state["targets"][0]["page_yield"]["status"] == "orphan_page_yield_unavailable"
    with pytest.raises(FileExistsError):
        make_snapshot(root, key, [])
    with pytest.raises(r.Stop, match="orphan_identity"):
        r.commit_chunk(
            state,
            {**pending, "target_key": plan["metadata"]["keys"][1]},
            path,
            root,
            plan["metadata"]["scheduled_dates"],
        )


def numeric_fixture(monkeypatch, tmp_path):
    plan = plan_fixture()
    epoch = time.time()
    cursor = r.new_cursor(plan, "synthetic", epoch)
    root = tmp_path / "cache"
    root.mkdir()
    for i, dates in enumerate(
        [plan["metadata"]["scheduled_dates"], plan["metadata"]["scheduled_dates"][:2], []]
    ):
        key = plan["metadata"]["keys"][i]
        path = make_snapshot(root, key, dates)
        r.commit_chunk(cursor, {"target_key": key}, path, root, plan["metadata"]["scheduled_dates"])
    for target in cursor["targets"][3:]:
        target["state"] = "empty"
    cursor["position"] = 512
    monkeypatch.setattr(r, "audit", lambda *a, **k: None)
    return plan, cursor, root, epoch


def test_fresh_numeric_decimal_sparse_empty_512_and_71_no_old_payload(monkeypatch, tmp_path):
    plan, cursor, root, epoch = numeric_fixture(monkeypatch, tmp_path)
    result = r.materialize(plan, "synthetic", cursor, root, epoch)
    assert (
        result["record_count"],
        result["full_targets"],
        result["sparse_targets"],
        result["empty_targets"],
    ) == (73, 1, 1, 510)
    final = r.document(r.read(root / "view/manifest.json"))
    assert final["selected_target_keys"] == plan["metadata"]["keys"]
    assert final["grid_count"] == 36352 and len(final["row_counts"]) == 512
    assert (
        r.numeric_readback(
            root / "view/bars.csv.gz",
            plan["metadata"]["keys"],
            plan["metadata"]["scheduled_dates"],
            epoch,
        )[0]
        == final["row_counts"]
    )
    with pytest.raises(FileExistsError):
        r.materialize(plan, "synthetic", cursor, root, epoch)


def test_source_drift_and_publication_failure_retain_candidate_not_success(monkeypatch, tmp_path):
    plan, cursor, root, epoch = numeric_fixture(monkeypatch, tmp_path)

    def fail(*a, **k):
        raise r.Stop("source_or_input_changed")

    monkeypatch.setattr(r, "audit", fail)
    with pytest.raises(r.Stop, match="source_or_input_changed"):
        r.materialize(plan, "synthetic", cursor, root, epoch)
    assert (root / "view/manifest.candidate.json").exists()
    assert (root / "view/bars.csv.gz").exists()
    assert not (root / "view/manifest.json").exists()
    source = tmp_path / "source.py"
    source.write_bytes(b"original")
    pin = r.attest(source)
    source.write_bytes(b"changed")
    with pytest.raises(r.Stop, match="source_or_input_changed"):
        r.attest(source, pin)


def test_exclusive_final_link_failure_has_no_success_manifest(monkeypatch, tmp_path):
    plan, cursor, root, epoch = numeric_fixture(monkeypatch, tmp_path)
    link = r.os.link

    def fail_final(source, dest):
        if Path(dest).name == "manifest.json":
            raise OSError("synthetic publication failure")
        return link(source, dest)

    monkeypatch.setattr(r.os, "link", fail_final)
    with pytest.raises(OSError):
        r.materialize(plan, "synthetic", cursor, root, epoch)
    assert not (root / "view/manifest.json").exists()
    assert (root / "view/manifest.candidate.json").exists()


def test_deadline_reset_nonfinite_foreign_plan_and_root_escape(monkeypatch, tmp_path):
    plan = plan_fixture()
    cursor = r.new_cursor(plan, "synthetic", time.time())
    with pytest.raises(r.Stop, match="cursor_scope"):
        r.validate_cursor(cursor, plan, "different")
    with pytest.raises(r.Stop, match="path_escape"):
        r.plain(tmp_path / "outside", tmp_path / "inside")
    now = time.time()
    monkeypatch.setattr(r.time, "time", lambda: now)
    for epoch in [float("nan"), float("inf"), now + 1, now - 1680]:
        with pytest.raises(r.Stop, match="deadline"):
            r.check_deadline(epoch)
    r.check_deadline(now - 1680, "publication")
    with pytest.raises(r.Stop, match="deadline"):
        r.check_deadline(now - 1800, "publication")


def test_cli_inert_no_cache_or_credential_operations():
    script = Path(__file__).parents[1] / "scripts/collect_kis_broad512_later_daily.py"
    completed = subprocess.run(
        [sys.executable, "-I", "-B", str(script)], capture_output=True, timeout=10, check=True
    )
    assert r.document(completed.stdout) == {"status": "inert", "actual_acquisition": False}
    assert not completed.stderr


def test_selective_config_and_transport_use_only_named_mocked_helper(monkeypatch):
    config_calls = []
    monkeypatch.setattr(
        r,
        "load_kis_paper_market_data_config",
        lambda path, **kwargs: (
            config_calls.append((path, kwargs))
            or KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret")
        ),
    )
    real = r.make_client(None, None, time.time(), lambda now: None)
    assert real.call_counts.daily_page_attempts == 0
    assert config_calls == [(r.REPO / ".env", {"environment": {"THERICHER_MODE": "off"}})]
    with pytest.raises(r.Stop, match="market_only_route"):
        from urllib.request import Request

        real._transport._opener.open(Request("https://example.invalid"), timeout=1)


def test_outer_job_mock_exact_pin_reap_and_stdout_discard(monkeypatch, tmp_path):
    plan = plan_fixture()
    monkeypatch.setattr(r, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(r, "PREPARATION", tmp_path / "preparation")
    monkeypatch.setattr(r, "audit", lambda *a, **k: None)
    calls = []

    def run_tree(argv, budget):
        calls.append((argv, budget))
        receipt = Path(argv[argv.index("--receipt") + 1])
        r.save(
            receipt,
            {
                "plan_sha256": "synthetic",
                "status": "retained_failure",
                "category": "synthetic_child_failure",
            },
        )
        return {
            "tree_reaped": True,
            "root_reaped": True,
            "timed_out": False,
            "root_exit_code": 1,
        }, b"synthetic_untrusted_stdout_not_retained"

    def load(path, pin, name):
        assert path == r.WATCHDOG and pin == r.WATCHDOG_PIN
        return SimpleNamespace(run_tree=run_tree)

    monkeypatch.setattr(r, "load_pinned_module", load)
    result = r.execute(plan, "synthetic")
    assert result["category"] == "synthetic_child_failure"
    assert result["owned_tree"]["tree_reaped"] and not result["raw_stdout_retained"]
    assert calls[0][0][1:3] == ["-I", "-B"] and 0 < calls[0][1] <= 1680
    receipt = next(r.PREPARATION.glob("attempt-*/receipt.json"))
    assert b"synthetic_untrusted_stdout" not in receipt.read_bytes()


def test_entrypoint_worker_does_not_print_provider_output(monkeypatch):
    script = Path(__file__).parents[1] / "scripts/collect_kis_broad512_later_daily.py"
    spec = importlib.util.spec_from_file_location("later_command_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(script), "--execute"])
    assert module.main() == 1  # Missing exact plan pin never enters execution.


def test_full_cursor_512_one_real_client_empty_keys_no_token_wait(monkeypatch, tmp_path):
    plan = plan_fixture()
    root = tmp_path / "cache"
    root.mkdir()
    monkeypatch.setattr(r, "CONTROL", tmp_path / "control")
    monkeypatch.setattr(r, "audit", lambda *a, **k: None)
    # Cardinality/client test; the focused snapshot/publication tests retain real fsync.
    monkeypatch.setattr(r.os, "fsync", lambda fd: None)
    monkeypatch.setattr(r.time, "sleep", lambda seconds: pytest.fail("extra target sleep"))
    transport = Transport([page([]) for _ in range(512)])
    factories = []

    def factory(*args):
        factories.append(args)
        return client(transport)

    epoch = time.time()
    cursor = r.collect(plan, "synthetic", epoch, root, client_factory=factory)
    assert len(factories) == 1 and len(transport.requests) == 513
    assert sum(request.method == "POST" for request in transport.requests) == 1
    assert cursor["position"] == 512 and cursor["daily_attempts"] == 512
    assert all(t["state"] == "empty" and t["chunk"] for t in cursor["targets"])
    assert cursor["categories"] == {"chunk_completed": 512}
    assert r.document(r.read(root / "cursor.json"))["family_epoch"] == epoch
    r.validate_cursor(cursor, plan, "synthetic")
    cursor["targets"][0]["chunk"] = None
    with pytest.raises(r.Stop, match="cursor_terminal_state"):
        r.validate_cursor(cursor, plan, "synthetic")


def test_collect_recovers_committed_pending_without_client_and_preserves_debit(
    monkeypatch, tmp_path
):
    plan = plan_fixture()
    root = tmp_path / "cache"
    root.mkdir()
    epoch = time.time()
    cursor = r.new_cursor(plan, "synthetic", epoch)
    cursor["daily_attempts"] = 2
    cursor["pending"] = {
        "target_key": plan["metadata"]["keys"][0],
        "run_id": "20261011T010101Z",
        "attempt_base": 0,
    }
    make_snapshot(root, cursor["pending"]["target_key"], [])
    r.save(root / "cursor.json", cursor)
    monkeypatch.setattr(r, "CONTROL", tmp_path / "control")
    monkeypatch.setattr(r, "audit", lambda *a, **k: None)
    token = r.KisPaperMarketDataTokenStartGate(control_root=tmp_path / "control")
    token.claim_token_request_start()
    with pytest.raises(r.Stop, match="fresh_token_yield"):
        r.collect(
            plan,
            "synthetic",
            epoch,
            root,
            client_factory=lambda *a: pytest.fail("orphan refetched"),
        )
    recovered = r.document(r.read(root / "cursor.json"))
    assert recovered["position"] == 1 and recovered["orphan_recoveries"] == 1
    assert recovered["daily_attempts"] == 2 and recovered["pending"] is None
    assert recovered["next_due"] is not None and recovered["family_epoch"] == epoch


def test_worker_source_drift_kills_before_client_or_cache(monkeypatch, tmp_path):
    def fail(*a, **k):
        raise r.Stop("source_or_input_changed")

    monkeypatch.setattr(r, "audit", fail)
    monkeypatch.setattr(r, "CACHE", tmp_path / "never-created")
    monkeypatch.setattr(
        r, "load_kis_paper_market_data_config", lambda *a, **k: pytest.fail("credentials accessed")
    )
    receipt = tmp_path / "worker-receipt.json"
    assert r.worker(plan_fixture(), "synthetic", time.time(), receipt) == 1
    assert not r.CACHE.exists()
    assert r.document(r.read(receipt))["category"] == "source_or_input_changed"
