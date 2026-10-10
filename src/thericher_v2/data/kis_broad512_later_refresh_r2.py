"""Goal79 fixed-identity later Paper daily collection and fresh 71-session view."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_daily_broad_panel import _is_target_key, _parse_raw_records
from thericher_v2.data.local import CSV_FIELDS, bar_from_record, bar_to_record
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisPaperMarketDataClient,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
    _acquire_worker_lock,
    _release_worker_lock,
    inspect_kis_paper_private_daily_backfill_snapshot,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionTarget,
    private_daily_cache_would_cross_free_space_floor,
    run_bounded_kis_paper_private_daily_collection,
    write_kis_paper_private_daily_cache,
)

REPO = Path("C:/Users/Public/Documents/thericher-v2")
ARTIFACT = Path("D:/thericher-v2/model-artifacts/data")
PREPARATION = ARTIFACT / "kis-stock-five-session-later-refresh-preparation-r2-v1"
CACHE = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-broad512-later/v1/"
    "fixed512-20260728-50sessions-r2"
)
CONTROL = Path("D:/market_data/us_equities/kis_paper_private/collection-control-v1")
BINDING = ARTIFACT / "kis-stock-broad512-five-session-input-binding-v1/binding.py"
BINDING_PIN = "sha256:25934743e94a7f835dc7ce51d15f85ee002750f8496eadb103a5c74378ee3086"
WATCHDOG = ARTIFACT / "kis-stock-broad512-numeric-execution-v1/watchdog.py"
WATCHDOG_PIN = "sha256:e561b89e917811d7aa11defe723e4e940385c36db8d0795cbe191783e9c7b7df"
ORIGINAL = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-broad-compact/v1/"
    "goal31-original-6ee8fa56-r2/manifest.json"
)
ORIGINAL_PIN = "sha256:1a0b9fa5d3d8b602f6a54433fe6b2d7c4c64b6889fb9cdc71fb22afbf600d0f7"
FAMILY_EPOCH = 1791651521.3678787
PRIOR_COMMAND_DEBIT = 0.685537
R1_PREPARATION = ARTIFACT / "kis-stock-five-session-later-refresh-preparation-v1"
R1_ATTEMPT = R1_PREPARATION / "attempt-36d8243e078f40cc9e43fc7c906ce01b"
R1_CURSOR = Path(str(CACHE).removesuffix("-r2")) / "cursor.json"
R1_PINS = {
    R1_PREPARATION
    / "plan.json": "sha256:178a8773c85c1f087863a9c8f203e3d6556d0068323e5a75bc8a257e902986e5",
    R1_ATTEMPT
    / "receipt.json": "sha256:fe854f4b5062a0528c1330c7e793064ee0bd52cb2250532b044395190583b09c",
    R1_ATTEMPT
    / "worker-receipt.json": (
        "sha256:c94820901736c7bf943261f31581e1ac9fcd9d2a385dfff69a6530fec857a7f0"
    ),
    R1_CURSOR: "sha256:196a190e85c1574444e9fd9a595ccbfb36536ff02c76b34721e93e2e22b51834",
    REPO
    / "src/thericher_v2/data/kis_broad512_later_refresh.py": (
        "sha256:fea632ee44e258f37a7a5eebc5dbb1d19a8d5ac6098419b773cb8a4e7942e63c"
    ),
    REPO
    / "scripts/collect_kis_broad512_later_daily.py": (
        "sha256:e260b9e10216f81f5cf8c703a1a4d96eb648c956479dc791c806daddbec2b3fb"
    ),
}
VERSION = "kis-fixed512-later-refresh-r2"
ANCHOR = "20261006"
BUDGET = {
    "whole_seconds": 1800,
    "worker_seconds": 1680,
    "publication_seconds": 120,
    "daily_attempts": 1024,
    "pages_per_chunk": 2,
    "free_space_floor": 0.15,
}
LIMITATIONS = [
    "current_listing_frozen512",
    "MODP0_source_values_not_PIT",
    "corporate_actions_unverified",
    "not_total_return_qualified",
    "later_development_only_not_Paper_adoption",
]


class Stop(RuntimeError):
    def __init__(self, category, due=None):
        super().__init__(category)
        self.category, self.due = category, due


def require(ok, category):
    if not ok:
        raise Stop(category)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def plain(path, root=None):
    path = Path(path).absolute()
    require(
        not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)), "linked_path"
    )
    if root is not None:
        require(path.is_relative_to(Path(root).absolute()), "path_escape")
    return path


def read(path, cap=8 * 1024**2):
    path = plain(path)
    require(path.stat().st_size <= cap, "size_cap")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    require(len(raw) <= cap, "size_cap")
    return raw


def document(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    encode(value)
    require(type(value) is dict, "nonobject_json")
    return value


def attest(path, pin=None):
    actual = digest(read(path))
    require(pin is None or pin == actual, "source_or_input_changed")
    return actual


def save(path, value, *, replace=False):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_name(path.name + ".candidate-" + uuid.uuid4().hex)
    with candidate.open("xb") as stream:
        stream.write(encode(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(candidate, path)
    else:
        os.link(candidate, path)
        candidate.unlink()


def load_pinned_module(path, pin, name):
    attest(path, pin)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    attest(path, pin)
    return module


def metadata_scope():
    b = load_pinned_module(BINDING, BINDING_PIN, "goal79_pinned_metadata")
    budget = b.Budget(time.monotonic() + 30)
    for path, pin in b.SOURCE_PINS.items():
        b.attest(path, pin, budget)
    parser, key_parser = b.canonical_metadata_parsers(budget)
    calendar = parser(b.pinned_bytes(b.CALENDAR, b.CALENDAR_PIN, budget, 2 * 1024**2))
    old = b.document(b.pinned_bytes(b.DATA / "manifest.json", b.MANIFEST_PIN, budget, 8 * 1024**2))
    binding = b.metadata_binding(old, calendar, key_parser)
    original = document(read(ORIGINAL))
    attest(ORIGINAL, ORIGINAL_PIN)
    require(list(binding.keys[:128]) == original["selected_target_keys"], "original128_order")
    days = tuple(d for d in calendar if date(2026, 6, 26) <= d <= date(2026, 10, 6))
    require(
        len(days) == 71
        and days[20] == date(2026, 7, 27)
        and days[21] == date(2026, 7, 28)
        and days[-1] == date(2026, 10, 6),
        "later_calendar_geometry",
    )
    clocks = [
        {
            "session_date": d.isoformat(),
            "decision_ts": calendar[d][0].isoformat(),
            "open_ts": calendar[d][1].isoformat(),
            "close_ts": calendar[d][2].isoformat(),
        }
        for d in days
    ]
    for previous, clock in zip(clocks, clocks[1:], strict=False):
        require(
            previous["close_ts"] < clock["decision_ts"] < clock["open_ts"] < clock["close_ts"],
            "later_calendar_clock",
        )
    return {
        "keys": list(binding.keys),
        "original_target_keys": list(binding.keys[:128]),
        "permutation": list(binding.permutation),
        "scope_pins": dict(b.SCOPE_PINS),
        "scheduled_dates": [d.isoformat() for d in days],
        "clocks": clocks,
        "calendar71_sha256": digest(encode(clocks)),
        "reference_manifest_sha256": b.MANIFEST_PIN,
        "calendar_source_sha256": b.CALENDAR_PIN,
        "context_sessions": 21,
        "score_sessions": 50,
        "score_cohorts": 10,
        "calendar_tail_unused": "2026-10-07",
    }


def source_paths():
    relative = [
        "contracts.py",
        "data/local.py",
        "data/provider.py",
        "data/resample.py",
        "data/synthetic.py",
        "data/kis_paper_daily_broad_panel.py",
        "data/kis_paper_daily_broad_registry.py",
        "data/kis_broad_d1_compact.py",
        "data/kis_broad_d1_explicit_keys.py",
        "data/kis_broad512_later_refresh_r2.py",
        "execution/kis_market_data.py",
        "execution/kis_market_data_rate_gate.py",
        "execution/kis_private_daily_collector.py",
        "execution/kis_private_daily_backfill.py",
    ]
    return [REPO / "src/thericher_v2" / p for p in relative] + [
        REPO / "scripts/collect_kis_broad512_later_daily_r2.py",
        BINDING,
        WATCHDOG,
        ARTIFACT.parent / "research/kis-stock-broad-ranking-driver-preparation-v1/driver.py",
    ]


def recovery_lineage():
    for path, pin in R1_PINS.items():
        attest(path, pin)
    cursor = document(read(R1_CURSOR))
    result = document(read(R1_ATTEMPT / "receipt.json"))
    require(
        cursor["family_epoch"] == FAMILY_EPOCH
        and cursor["daily_attempts"] == 0
        and cursor["position"] == 0
        and cursor["pending"] is None
        and result["family_elapsed_seconds"] == PRIOR_COMMAND_DEBIT
        and result["owned_tree"]["tree_reaped"],
        "original_failure_lineage",
    )
    return {
        "family_epoch": FAMILY_EPOCH,
        "deadline_epoch": FAMILY_EPOCH + 1800,
        "worker_deadline_epoch": FAMILY_EPOCH + 1680,
        "prior_command_debit_seconds": PRIOR_COMMAND_DEBIT,
        "command_budget_after_prior_debit_seconds": 1799.314463,
        "scope": "same_original_wall_clock_no_reset_or_extension",
        "pins": {str(path): pin for path, pin in R1_PINS.items()},
    }


def identity_parts(key):
    require(_is_target_key(key), "view_identity_schema")
    return key.split("/", maxsplit=1)


def prepare_plan():
    return {
        "kind": VERSION,
        "cache_root": str(CACHE),
        "control_root": str(CONTROL),
        "anchor": ANCHOR,
        "budget": BUDGET,
        "recovery": recovery_lineage(),
        "metadata": metadata_scope(),
        "source_pins": {str(p): attest(p) for p in source_paths()},
        "reference_inputs": {
            str(ORIGINAL): ORIGINAL_PIN,
            "D:/market_data/us_equities/kis_paper_private/daily-nas-broad512/v1/"
            "goal77-numeric-recovery-r2/manifest.json": (
                "sha256:fd559b22a38bf6bb188d0c9b4d299f8fc31091a2fcc9b1d6b784ac894133f0af"
            ),
            "D:/thericher-v2/model-artifacts/data/kis-cross-asset-d1-input-foundation-v1/"
            "calendar-nyse-20070821-20261007-v1.json": (
                "sha256:d2dab6f2ab27a7439ed4be91bacefc68b04908d0b3b7d509e4a2b19925a42721"
            ),
        },
        "pacing": {
            "shared_market_start_seconds": 1,
            "fresh_token_start_seconds": 300,
            "extra_target_sleep": 0,
            "core_inter_page_seconds": 1,
            "core_delay_reason": "unchanged_collector_also_supports_ungated_clients",
        },
        "limitations": LIMITATIONS,
        "actual_acquisition": False,
    }


def audit(plan, *, metadata=False):
    require(
        plan["kind"] == VERSION
        and plan["budget"] == BUDGET
        and plan["cache_root"] == str(CACHE)
        and plan["control_root"] == str(CONTROL)
        and plan["anchor"] == ANCHOR,
        "plan_scope",
    )
    require(plan["recovery"] == recovery_lineage(), "recovery_binding")
    require(set(plan["source_pins"]) == {str(p) for p in source_paths()}, "source_pin_set")
    for path, pin in {**plan["source_pins"], **plan["reference_inputs"]}.items():
        attest(path, pin)
    require(
        plan["source_pins"][str(BINDING)] == BINDING_PIN
        and plan["source_pins"][str(WATCHDOG)] == WATCHDOG_PIN,
        "released_source_pin",
    )
    if metadata:
        require(plan["metadata"] == metadata_scope(), "metadata_binding_changed")


def check_deadline(epoch, phase="worker"):
    limit = BUDGET["worker_seconds" if phase == "worker" else "whole_seconds"]
    require(
        type(epoch) in (int, float) and math.isfinite(epoch) and 0 <= time.time() - epoch < limit,
        "deadline",
    )


def floor(root, projected=1024**2):
    plain(root)
    require(
        not private_daily_cache_would_cross_free_space_floor(
            cache_root=root, repo_root=REPO, projected_bytes=projected
        ),
        "storage_floor",
    )


def new_cursor(plan, pin, epoch):
    check_deadline(epoch)
    return {
        "kind": VERSION,
        "plan_sha256": pin,
        "family_epoch": epoch,
        "deadline_epoch": epoch + 1800,
        "worker_deadline_epoch": epoch + 1680,
        "daily_attempts": 0,
        "position": 0,
        "pending": None,
        "next_due": None,
        "categories": {},
        "accepted_pages": 0,
        "orphan_recoveries": 0,
        "lost_pending_attempts": 0,
        "market_start_count": 0,
        "minimum_market_start_gap_seconds": None,
        "first_page_needed_rows": 0,
        "first_page_floor_reached_targets": 0,
        "second_page_incremental_needed_rows": 0,
        "targets": [
            {"target_key": k, "state": "ready", "chunk": None, "needed_rows": 0}
            for k in plan["metadata"]["keys"]
        ],
    }


def validate_cursor(cursor, plan, pin):
    require(
        cursor["kind"] == VERSION
        and cursor["plan_sha256"] == pin
        and [t["target_key"] for t in cursor["targets"]] == plan["metadata"]["keys"]
        and type(cursor["daily_attempts"]) is int
        and 0 <= cursor["daily_attempts"] <= 1024
        and type(cursor["position"]) is int
        and 0 <= cursor["position"] <= 512
        and cursor["deadline_epoch"] == cursor["family_epoch"] + 1800
        and cursor["worker_deadline_epoch"] == cursor["family_epoch"] + 1680,
        "cursor_scope",
    )
    for i, target in enumerate(cursor["targets"]):
        if i < cursor["position"]:
            require(
                target["state"] in {"full", "sparse", "empty"}
                and type(target["needed_rows"]) is int
                and 0 <= target["needed_rows"] <= 71
                and type(target["chunk"]) is dict,
                "cursor_terminal_state",
            )
        else:
            require(
                target["state"] == "ready"
                and target["chunk"] is None
                and target["needed_rows"] == 0,
                "cursor_unfinished_state",
            )


def due_check(rate, token):
    now = datetime.now(UTC)
    due = rate.snapshot().retry_not_before_utc
    if due and now < due:
        raise Stop("shared_rate_yield", due.isoformat())
    if not token.token_request_is_due():
        due = token.snapshot().next_token_request_not_before_utc
        raise Stop("fresh_token_yield", due.isoformat() if due else None)


class OwnedClient:
    """Debit before side effects; keep one real client and observe both page yields."""

    def __init__(self, client, cursor, persist, epoch, days):
        self.client, self.cursor, self.persist, self.epoch = client, cursor, persist, epoch
        self.days = {d.replace("-", "") for d in days}
        self.page_observations = []

    @property
    def call_counts(self):
        return self.client.call_counts

    def ensure_authenticated(self):
        check_deadline(self.epoch)
        self.client.ensure_authenticated()

    def fetch_daily_raw_page(self, query):
        check_deadline(self.epoch)
        require(self.cursor["daily_attempts"] < 1024, "attempt_budget")
        pending = self.cursor["pending"]
        require(f"{query.symbol}/{query.exchange}" == pending["target_key"], "query_identity")
        self.cursor["daily_attempts"] += 1
        self.persist()
        page = self.client.fetch_daily_raw_page(query)
        self.page_observations.append(
            {
                "needed": {r.xymd for r in page.rows if r.xymd in self.days},
                "row_count": len(page.rows),
                "floor_reached": bool(page.rows)
                and min(r.xymd for r in page.rows) <= min(self.days),
                "provider_continuation": page.page.continuation_available,
            }
        )
        return page


def controlled_sleep(seconds, epoch):
    check_deadline(epoch)
    if seconds > 2:
        raise Stop(
            "shared_rate_yield", (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
        )
    require(0 <= seconds and time.time() + seconds < epoch + 1680, "deadline")
    time.sleep(seconds)


def make_client(rate, token, epoch, market_started):
    # The only credential entry point, after metadata/source/lock/storage/due checks.
    config = load_kis_paper_market_data_config(REPO / ".env", environment={"THERICHER_MODE": "off"})
    transport = UrllibKisPaperMarketDataTransport(request_gate=rate, token_start_gate=token)
    opener = transport._opener

    class DeadlineOpener:
        def open(self, request, timeout):
            check_deadline(epoch)
            url = request.full_url.split("?", 1)[0]
            require(
                (request.get_method(), url)
                in {
                    ("POST", KIS_PAPER_MARKET_DATA_BASE_URL + KIS_PAPER_TOKEN_PATH),
                    ("GET", KIS_PAPER_MARKET_DATA_BASE_URL + KIS_PAPER_DAILY_PATH),
                },
                "market_only_route",
            )
            if request.get_method() == "GET":
                market_started(datetime.now(UTC))
            return opener.open(request, timeout=min(timeout, max(0.01, epoch + 1680 - time.time())))

    transport._opener = DeadlineOpener()
    return KisPaperMarketDataClient(
        config=config, transport=transport, max_daily_page_attempts=1024
    )


def snapshot_path(root, pending):
    symbol, exchange = identity_parts(pending["target_key"])
    return plain(
        root
        / f"snapshot={pending['run_id']}-{symbol.lower()}-{exchange.lower()}-modp0-v1"
        / "manifest.json",
        root,
    )


def inspect_chunk(path, root):
    path = plain(path, root)
    manifest = document(read(path, 1024**2))
    require(
        manifest["collector_objective_id"] == VERSION and manifest["collector_version"] == VERSION,
        "foreign_snapshot",
    )
    raw = manifest["files"]["raw_daily_rows"]
    if raw:
        payload = read(plain(path.parent / raw["path"], path.parent), 1024**2)
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
            require(len(compressed.read(512 * 1024 + 1)) <= 512 * 1024, "raw_expansion_cap")
    verified = inspect_kis_paper_private_daily_backfill_snapshot(
        manifest_path=path, cache_root=root, repo_root=REPO
    )
    return verified, manifest


def commit_chunk(cursor, pending, path, root, days, observations=()):
    verified, manifest = inspect_chunk(path, root)
    require(
        verified["target_key"] == pending["target_key"] + "/MODP=0"
        and verified["input_cursor_date"] == ANCHOR,
        "orphan_identity",
    )
    target = cursor["targets"][cursor["position"]]
    require(
        target["target_key"] == pending["target_key"] and target["chunk"] is None, "cursor_conflict"
    )
    usable = (
        verified["status"] in {"completed", "partial"}
        and manifest["deduplication"]["conflicting_duplicate_rows"] == 0
    )
    n = len(set(verified["row_fingerprints"]) & set(days)) if usable else 0
    target.update(
        state="full" if n == len(days) else "sparse" if n else "empty",
        needed_rows=n,
        chunk={
            "manifest_path": path.relative_to(root).as_posix(),
            "manifest_sha256": verified["manifest_hash"],
            "raw_sha256": verified["raw_sha256"],
            "usable": usable,
            "provider_stop_outcome": verified["stop_outcome"],
        },
    )
    category = "chunk_" + verified["status"]
    cursor["categories"][category] = cursor["categories"].get(category, 0) + 1
    cursor["accepted_pages"] += manifest["requests"]["accepted_pages"]
    if observations:
        first = observations[0]
        cursor["first_page_needed_rows"] += len(first["needed"])
        cursor["first_page_floor_reached_targets"] += int(first["floor_reached"])
        cursor["second_page_incremental_needed_rows"] += (
            len(observations[1]["needed"] - first["needed"]) if len(observations) == 2 else 0
        )
        target["page_yield"] = {
            "first_page_row_count": first["row_count"],
            "first_page_needed_rows": len(first["needed"]),
            "first_page_floor_reached": first["floor_reached"],
            "first_page_provider_continuation": first["provider_continuation"],
            "second_incremental_needed_rows": len(observations[1]["needed"] - first["needed"])
            if len(observations) == 2
            else 0,
        }
    else:
        target["page_yield"] = {"status": "orphan_page_yield_unavailable"}
    cursor["position"] += 1
    cursor["pending"] = None


def collect(plan, pin, epoch, root, *, client_factory=make_client):
    root = plain(root)
    cursor_path = plain(root / "cursor.json", root)
    cursor = document(read(cursor_path)) if cursor_path.exists() else new_cursor(plan, pin, epoch)
    validate_cursor(cursor, plan, pin)
    require(epoch == cursor["family_epoch"], "family_clock_reset")
    check_deadline(epoch)

    def persist():
        save(cursor_path, cursor, replace=True)

    persist()
    days = plan["metadata"]["scheduled_dates"]
    pending = cursor["pending"]
    if pending:
        path = snapshot_path(root, pending)
        if path.exists():
            commit_chunk(cursor, pending, path, root, days)
            cursor["orphan_recoveries"] += 1
        else:
            cursor["lost_pending_attempts"] += cursor["daily_attempts"] - pending["attempt_base"]
            cursor["pending"] = None
        persist()
    client = None
    last_start = None

    def started(now):
        nonlocal last_start
        cursor["market_start_count"] += 1
        if last_start is not None:
            gap = (now - last_start).total_seconds()
            previous = cursor["minimum_market_start_gap_seconds"]
            cursor["minimum_market_start_gap_seconds"] = (
                gap if previous is None else min(previous, gap)
            )
        last_start = now
        persist()

    plain(CONTROL)
    rate = KisPaperMarketDataRateGate(
        control_root=CONTROL, sleeper=lambda s: controlled_sleep(s, epoch)
    )
    token = KisPaperMarketDataTokenStartGate(control_root=CONTROL)
    approved = {}
    for key in plan["metadata"]["keys"]:
        symbol, exchange = identity_parts(key)
        approved[symbol] = approved.get(symbol, frozenset()) | frozenset({exchange})
    try:
        while cursor["position"] < len(cursor["targets"]):
            check_deadline(epoch)
            require(cursor["daily_attempts"] <= 1022, "attempt_budget")
            floor(root)
            audit(plan)
            if client is None:
                due_check(rate, token)
                client = OwnedClient(
                    client_factory(rate, token, epoch, started), cursor, persist, epoch, days
                )
            target = cursor["targets"][cursor["position"]]
            key = target["target_key"]
            run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + f"-{cursor['daily_attempts']}"
            pending = {
                "target_key": key,
                "run_id": run_id,
                "attempt_base": cursor["daily_attempts"],
            }
            cursor["pending"] = pending
            persist()
            symbol, exchange = identity_parts(key)
            client.page_observations = []
            result = run_bounded_kis_paper_private_daily_collection(
                client,
                code_revision=pin,
                target=KisPaperPrivateDailyCollectionTarget(
                    symbol=symbol,
                    exchange=exchange,
                    anchor_date=ANCHOR,
                    approved_symbol_exchanges=approved,
                ),
                sleeper=lambda s: controlled_sleep(s, epoch),
            )
            check_deadline(epoch)
            # Retain rejected evidence, but its rows never enter the numeric view.
            path, _ = write_kis_paper_private_daily_cache(
                result=result,
                cache_root=root,
                run_id=run_id,
                repo_root=REPO,
                collector_objective_id=VERSION,
                collector_version=VERSION,
                backfill_context={
                    "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
                    "cursor_strategy": "oldest_session_date_with_exact_overlap",
                    "input_cursor_date": ANCHOR,
                    "logical_cursor_persisted": True,
                    "output_cursor_date": result.rows[0].xymd
                    if result.rows and result.status in {"observed", "partial"}
                    else None,
                    "target_key": key + "/MODP=0",
                },
            )
            commit_chunk(cursor, pending, path, root, days, client.page_observations)
            persist()
            if result.reason in {
                "rate_limited",
                "token_request_not_due",
                "auth_rejected",
                "auth_response_invalid",
                "transport_failure",
            }:
                if result.reason == "rate_limited":
                    rate.record_rate_limit()
                due = (
                    rate.snapshot().retry_not_before_utc
                    if result.reason == "rate_limited"
                    else (token.snapshot().next_token_request_not_before_utc)
                )
                raise Stop("provider_yield", due.isoformat() if due else None)
        audit(plan)
        validate_cursor(cursor, plan, pin)
        return cursor
    except Stop as error:
        cursor["next_due"] = error.due
        cursor["categories"][error.category] = cursor["categories"].get(error.category, 0) + 1
        persist()
        raise


def target_bars(target, root, days):
    chunk = target["chunk"]
    if not chunk:
        return {}
    path = plain(root / chunk["manifest_path"], root)
    verified, manifest = inspect_chunk(path, root)
    require(
        verified["manifest_hash"] == chunk["manifest_sha256"]
        and verified["raw_sha256"] == chunk["raw_sha256"]
        and verified["target_key"] == target["target_key"] + "/MODP=0",
        "chunk_changed",
    )
    if not chunk["usable"]:
        return {}
    raw = manifest["files"]["raw_daily_rows"]
    if raw is None:
        return {}
    symbol, exchange = identity_parts(target["target_key"])
    payload = read(plain(path.parent / raw["path"], path.parent), 1024**2)
    require(digest(payload) == raw["sha256"], "raw_changed")
    bars, _ = _parse_raw_records(payload, symbol=symbol, exchange=exchange)
    return {day: bars[date.fromisoformat(day)] for day in days if date.fromisoformat(day) in bars}


def numeric_readback(path, keys, days, epoch, phase="worker"):
    counts = dict.fromkeys(keys, 0)
    hashes = {k: hashlib.sha256() for k in keys}
    order = {k: i for i, k in enumerate(keys)}
    prior = (-1, "")
    with gzip.open(plain(path), "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == (*CSV_FIELDS, "target_key"), "packed_header")
        for record in reader:
            check_deadline(epoch, phase)
            require(set(record) == set((*CSV_FIELDS, "target_key")), "packed_row_schema")
            key = record.pop("target_key")
            require(key in counts, "packed_identity")
            bar = bar_from_record(record)
            day = bar.start_ts.date().isoformat()
            require(
                bar.symbol == key.split("/")[0]
                and bar.market == "US"
                and bar.timeframe.value == "1d"
                and bar.complete
                and bar.start_ts == datetime.combine(bar.start_ts.date(), datetime.min.time(), UTC)
                and day in days,
                "packed_clock",
            )
            current = (order[key], day)
            require(current > prior, "packed_order_or_duplicate")
            prior = current
            counts[key] += 1
            hashes[key].update(encode(bar_to_record(bar)) + b"\n")
            require(counts[key] <= len(days), "packed_count")
    return counts, {k: "sha256:" + h.hexdigest() for k, h in hashes.items()}


def materialize(plan, pin, cursor, root, epoch):
    check_deadline(epoch)
    require(cursor["position"] == len(cursor["targets"]) == 512, "unfinished_cursor")
    view = plain(root / "view", root)
    view.mkdir()  # Retained failures and prior successes are never reused.
    floor(root, 16 * 1024**2)
    keys, days = plan["metadata"]["keys"], plan["metadata"]["scheduled_dates"]
    counts, hashes = {}, {}
    packed = view / "bars.csv.gz"
    with packed.open("xb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", mtime=0, filename="") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(
                    text, fieldnames=(*CSV_FIELDS, "target_key"), lineterminator="\n"
                )
                writer.writeheader()
                for target in cursor["targets"]:
                    check_deadline(epoch)
                    key = target["target_key"]
                    bars = target_bars(target, root, days)
                    counts[key] = len(bars)
                    require(counts[key] == target["needed_rows"], "support_count_changed")
                    h = hashlib.sha256()
                    for day in days:
                        if day in bars:
                            record = bar_to_record(bars[day])
                            h.update(encode(record) + b"\n")
                            writer.writerow({**record, "target_key": key})
                    hashes[key] = "sha256:" + h.hexdigest()
        binary.flush()
        os.fsync(binary.fileno())
    require(numeric_readback(packed, keys, days, epoch) == (counts, hashes), "numeric_readback")
    packed_pin = attest(packed)
    manifest = {
        "kind": "kis_broad512_later_numeric_view_v1",
        "plan_sha256": pin,
        "selected_target_keys": keys,
        "original_target_keys": plan["metadata"]["original_target_keys"],
        "permutation": plan["metadata"]["permutation"],
        "data_ordinal_target_keys": sorted(keys),
        "permutation_semantics": "original128_first_to_frozen_reference_data_ordinal",
        "packed_order": "selected_target_keys_then_session_date",
        "scope_pins": plan["metadata"]["scope_pins"],
        "reference_manifest_sha256": plan["metadata"]["reference_manifest_sha256"],
        "scheduled_dates": days,
        "calendar_clocks": plan["metadata"]["clocks"],
        "calendar71_sha256": plan["metadata"]["calendar71_sha256"],
        "context_sessions": 21,
        "score_sessions": 50,
        "score_cohorts": 10,
        "row_counts": counts,
        "logical_record_sha256": hashes,
        "record_count": sum(counts.values()),
        "grid_count": 512 * 71,
        "no_key_filter_or_replacement": True,
        "fresh_cache_only": True,
        "source_pins": plan["source_pins"],
        "source_chunks": cursor["targets"],
        "limitations": LIMITATIONS,
        "packed": {
            "path": "bars.csv.gz",
            "sha256": packed_pin,
            "size_bytes": packed.stat().st_size,
            "columns": [*CSV_FIELDS, "target_key"],
        },
    }
    candidate = view / "manifest.candidate.json"
    save(candidate, manifest)
    # Candidate is durable before the final source/input/chunk audit and success publication.
    for target in cursor["targets"]:
        check_deadline(epoch)
        target_bars(target, root, days)
    attest(packed, packed_pin)
    require(document(read(candidate)) == manifest, "manifest_candidate_readback")
    manifest_pin = attest(candidate)
    audit(plan, metadata=True)
    check_deadline(epoch)
    final = view / "manifest.json"
    os.link(candidate, final)
    return {
        "status": "fresh_later_numeric_view_serialized",
        "manifest_sha256": manifest_pin,
        "packed_sha256": packed_pin,
        "target_count": 512,
        "calendar_count": 71,
        "grid_count": 36352,
        "record_count": sum(counts.values()),
        "full_targets": sum(n == 71 for n in counts.values()),
        "sparse_targets": sum(0 < n < 71 for n in counts.values()),
        "empty_targets": sum(n == 0 for n in counts.values()),
        "qualification": "not_claimed",
    }


def worker(plan, pin, epoch, receipt_path):
    start = time.monotonic()
    lock = None
    receipt = {"status": "retained_failure", "plan_sha256": pin, "raw_stdout_retained": False}
    stage = "family_clock"
    try:
        require(epoch == FAMILY_EPOCH, "family_clock_reset")
        check_deadline(epoch)
        stage = "source_and_metadata_audit"
        audit(plan, metadata=True)
        stage = "cache_and_storage_floor"
        root = plain(CACHE)
        floor(root, 512 * 1024**2)
        root.mkdir(parents=True, exist_ok=True)
        stage = "cache_lock_and_nonreuse"
        lock = _acquire_worker_lock(root=root, observed_at=datetime.now(UTC))
        require(lock is not None, "cache_owned")
        if not (root / "cursor.json").exists():
            require(
                all(p.name == "worker.lock" for p in root.iterdir()),
                "foreign_or_used_cache",
            )
        stage = "collect"
        cursor = collect(plan, pin, epoch, root)
        stage = "fresh_numeric_view"
        receipt.update(materialize(plan, pin, cursor, root, epoch))
        receipt.update(
            {
                k: cursor[k]
                for k in (
                    "daily_attempts",
                    "accepted_pages",
                    "categories",
                    "orphan_recoveries",
                    "lost_pending_attempts",
                    "market_start_count",
                    "minimum_market_start_gap_seconds",
                    "first_page_needed_rows",
                    "first_page_floor_reached_targets",
                    "second_page_incremental_needed_rows",
                )
            }
        )
    except Stop as error:
        receipt.update(category=error.category, next_due=error.due)
    except Exception as error:
        receipt.update(
            category="unexpected_worker_failure",
            failure_stage=stage,
            exception_type=type(error).__name__
            if type(error).__name__
            in {
                "ValueError",
                "TypeError",
                "KeyError",
                "OSError",
                "FileNotFoundError",
                "PermissionError",
                "RuntimeError",
                "TimeoutError",
            }
            else "other_exception",
        )
    finally:
        if lock is not None and (CACHE / "cursor.json").exists():
            try:
                current = document(read(CACHE / "cursor.json"))
                validate_cursor(current, plan, pin)
                receipt.update(
                    {
                        k: current[k]
                        for k in (
                            "daily_attempts",
                            "accepted_pages",
                            "categories",
                            "orphan_recoveries",
                            "lost_pending_attempts",
                            "position",
                            "next_due",
                            "market_start_count",
                            "minimum_market_start_gap_seconds",
                            "first_page_needed_rows",
                            "first_page_floor_reached_targets",
                            "second_page_incremental_needed_rows",
                        )
                    }
                )
                receipt["cursor_sha256"] = attest(CACHE / "cursor.json")
            except Exception:
                receipt["cursor_projection"] = "unavailable"
        _release_worker_lock(lock)
    receipt["elapsed_seconds"] = round(time.monotonic() - start, 6)
    save(receipt_path, receipt)
    return 0 if receipt["status"] == "fresh_later_numeric_view_serialized" else 1


def execute(plan, pin):
    audit(plan, metadata=True)
    root = plain(CACHE)
    cursor_path = root / "cursor.json"
    epoch = FAMILY_EPOCH
    if cursor_path.exists():
        cursor = document(read(cursor_path))
        validate_cursor(cursor, plan, pin)
        require(cursor["family_epoch"] == FAMILY_EPOCH, "family_clock_reset")
    check_deadline(epoch)
    attempt = plain(PREPARATION / ("attempt-" + uuid.uuid4().hex), PREPARATION)
    attempt.mkdir(parents=True)
    receipt_path = attempt / "worker-receipt.json"
    watchdog = load_pinned_module(WATCHDOG, WATCHDOG_PIN, "goal79_owned_windows_job")
    watchdog.ROOT = attempt
    facts = {"status": "retained_failure", "plan_sha256": pin, "raw_stdout_retained": False}
    try:
        argv = [
            str(REPO / ".venv/Scripts/python.exe"),
            "-I",
            "-B",
            str(REPO / "scripts/collect_kis_broad512_later_daily_r2.py"),
            "--_worker",
            "--plan",
            str(PREPARATION / "plan.json"),
            "--pin",
            pin,
            "--epoch",
            str(epoch),
            "--receipt",
            str(receipt_path),
        ]
        tree, discarded_stdout = watchdog.run_tree(argv, max(0, epoch + 1680 - time.time()))
        del discarded_stdout
        facts["owned_tree"] = tree
        require(
            tree["tree_reaped"] and tree["root_reaped"] and not tree["timed_out"], "tree_deadline"
        )
        check_deadline(epoch, "publication")
        result = document(read(receipt_path, 64 * 1024))
        require(result["plan_sha256"] == pin, "worker_receipt_binding")
        facts["worker_receipt_sha256"] = attest(receipt_path)
        if (
            tree["root_exit_code"] == 0
            and result["status"] == "fresh_later_numeric_view_serialized"
        ):
            final = root / "view/manifest.json"
            attest(final, result["manifest_sha256"])
            manifest = document(read(final))
            require(
                manifest["plan_sha256"] == pin
                and manifest["selected_target_keys"] == plan["metadata"]["keys"]
                and manifest["scheduled_dates"] == plan["metadata"]["scheduled_dates"],
                "final_manifest_scope",
            )
            packed = plain(final.parent / manifest["packed"]["path"], final.parent)
            attest(packed, result["packed_sha256"])
            counts, hashes = numeric_readback(
                packed,
                plan["metadata"]["keys"],
                plan["metadata"]["scheduled_dates"],
                epoch,
                phase="publication",
            )
            require(
                counts == manifest["row_counts"]
                and hashes == manifest["logical_record_sha256"]
                and sum(counts.values()) == result["record_count"],
                "final_count_readback",
            )
            audit(plan, metadata=True)
            check_deadline(epoch, "publication")
            facts.update(result)
        else:
            facts["category"] = result.get("category", "child_failed")
            facts["next_due"] = result.get("next_due")
    except Stop as error:
        facts.update(status="retained_failure", category=error.category)
    except Exception:
        facts.update(status="retained_failure", category="unexpected_parent_failure")
    facts["family_elapsed_seconds"] = round(time.time() - epoch, 6)
    if facts["family_elapsed_seconds"] >= 1800:
        facts.update(status="retained_failure", category="whole_deadline")
    save(attempt / "receipt.json", facts)
    return facts
