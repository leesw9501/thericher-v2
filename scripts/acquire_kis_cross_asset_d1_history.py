"""Finite MODP0 trio history collection with exact seed and restart bindings."""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import io
import json
import math
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataResponse,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    _parse_daily_raw_row,
    _successful_payload,
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
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectorPage,
    private_daily_cache_would_cross_free_space_floor,
    write_kis_paper_private_daily_cache,
)

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "cross_asset_d1_frozen_probe", ROOT / "scripts/acquire_kis_cross_asset_d1.py"
)
assert _SPEC is not None and _SPEC.loader is not None
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)
GOAL = probe.GOAL
VERSION = "kis-cross-asset-d1-history-v1"
START = "20070821"
END = "20261007"
STOP_CODES = frozenset(
    {
        "storage_floor",
        "worker_busy",
        "page_budget",
        "runtime_budget",
        "cooldown_not_due",
        "source_hash_changed",
        "seed_binding_invalid",
        "catalog_binding_invalid",
        "pending_outcome_unknown",
        "date_after_anchor",
        "daily_duplicate_conflict",
        "nonadvancing_cursor",
        "invalid_pacing_delay",
        "local_io_or_contract_invalid",
        "provider_failure_unclassified",
    }
)


class HistoryStop(RuntimeError):
    """Only closed categorical codes are projected outside this process."""


def _pins(repository: Path) -> dict[str, str]:
    return {
        **probe._source_pins(repository),
        "scripts/acquire_kis_cross_asset_d1_history.py": probe._sha(Path(__file__).read_bytes()),
    }


def _date(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d")


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo != UTC:
        raise ValueError("UTC required")
    return parsed


def _child(root: Path, relative: str, repository: Path) -> Path:
    path = probe._external(root / relative, repository)
    if not path.is_relative_to(root):
        raise ValueError("scope path invalid")
    return path


def _save_index(root: Path, index: dict) -> None:
    data = (json.dumps(index, sort_keys=True, indent=2) + "\n").encode()
    temporary = root / f"index-{uuid.uuid4().hex}.tmp"
    probe._write_new(temporary, data)
    os.replace(temporary, root / "index.json")


def _write_exact_json(path: Path, document: dict) -> str:
    data = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
    if path.exists():
        if path.read_bytes() != data:
            raise HistoryStop("catalog_binding_invalid")
        return probe._sha(data)
    return probe._write_new(path, data)


def _verify_intent(intent: dict, index: dict) -> None:
    target = index["targets"][intent["symbol"]]
    if (
        intent["exchange"] != target["exchange"]
        or intent["input_cursor"] != target["cursor"]
        or intent["continuation_before"] != target["continuation"]
        or target["state"] != "ready"
    ):
        raise HistoryStop("catalog_binding_invalid")


def _validated_rows(page: KisPaperDailyRawPage, anchor: str) -> tuple:
    unique = {}
    for row in page.rows:
        _date(row.xymd)
        if row.xymd > anchor:
            raise HistoryStop("date_after_anchor")
        if row.xymd in unique and unique[row.xymd] != row:
            raise HistoryStop("daily_duplicate_conflict")
        unique[row.xymd] = row
    return tuple(unique[key] for key in sorted(unique))


def _seed_pages(
    *,
    path: Path,
    digest: str,
    market: Path,
    artifacts: Path,
    repository: Path,
    source_root: Path | None = None,
):
    """Reparse the exact accepted prefix; deep anchors never become history seeds."""
    try:
        path = probe._external(path, repository)
        if not path.is_relative_to(artifacts) or probe._sha(path.read_bytes()) != digest:
            raise ValueError("seed receipt hash invalid")
        receipt = json.loads(path.read_bytes())
        expected_pins = probe._source_pins(repository)
        if receipt["source_pins"] != expected_pins:
            if source_root is None:
                raise ValueError("original seed source pins required")
            source_root = probe._external(source_root, repository)
            if not source_root.is_relative_to(artifacts):
                raise ValueError("seed source root invalid")
            expected_pins = {
                name: probe._sha(_child(source_root, name, repository).read_bytes())
                for name in probe.SOURCE_FILES
            }
            # The repair changes only the probe envelope, not shared typed parsing/storage.
            if any(
                expected_pins[name] != probe._source_pins(repository)[name]
                for name in probe.SOURCE_FILES
                if name != "scripts/acquire_kis_cross_asset_d1.py"
            ):
                raise ValueError("seed parser source changed")
        contract_bytes = (path.parent / "contract.json").read_bytes()
        contract = json.loads(contract_bytes)
        queries = probe.probe_queries()
        if (
            receipt["kind"] != "kis_cross_asset_d1_capability_receipt"
            or receipt["goal"] != GOAL
            or receipt["status"] not in {"observed", "partial"}
            or receipt["source_pins"] != expected_pins
            or receipt["contract_sha256"] != probe._sha(contract_bytes)
            or contract["source_pins"] != receipt["source_pins"]
            or contract["goal"] != GOAL
            or contract["queries"] != [probe._query_fact(q) for q in queries]
            or contract["maximum_daily_GETs"] != 8
            or contract["maximum_token_POSTs"] != 1
            or not 5 <= receipt["accepted_page_count"] <= 8
            or len(receipt["pages"]) != receipt["accepted_page_count"]
            or len(receipt["private_daily_responses"]) != receipt["accepted_page_count"]
        ):
            raise ValueError("seed contract invalid")
        observed = _time(receipt["completed_at_utc"])
        if observed < _time(receipt["started_at_utc"]):
            raise ValueError("seed times invalid")
        pages = {}
        ordinary = {}
        for ordinal, (fact, binding) in enumerate(
            zip(receipt["pages"], receipt["private_daily_responses"], strict=True), 1
        ):
            query = queries[ordinal - 1]
            expected = {
                "SYMB": query.symbol,
                "EXCD": query.exchange,
                "BYMD": query.by_date,
                "MODP": query.adjustment_mode,
            }
            if (
                binding["ordinal"] != ordinal
                or binding["query"] != expected
                or binding["http_status_class"] != "2xx"
            ):
                raise ValueError("seed query invalid")
            raw = _child(market, binding["market_relative_path"], repository).read_bytes()
            if probe._sha(raw) != binding["sha256"]:
                raise ValueError("seed raw hash invalid")
            payload = _successful_payload(
                KisMarketDataResponse(200, {}, raw), "daily_response_rejected"
            )
            if not isinstance(payload.get("output1"), Mapping):
                raise ValueError("seed schema invalid")
            rows = tuple(_parse_daily_raw_row(r) for r in payload["output2"])
            dates = [r.xymd for r in rows]
            continuation = "F" if fact["continuation_category"] == "F" else None
            page = KisPaperDailyRawPage(
                KisPaperDailyPage(
                    query,
                    len(rows),
                    max(dates) if dates else None,
                    min(dates) if dates else None,
                    bool(rows),
                    continuation is not None,
                    continuation,
                ),
                rows,
            )
            if probe._page_fact(page, query, ordinary) != fact:
                raise ValueError("seed facts invalid")
            if query.by_date == END and query.adjustment_mode == "0":
                pages[query.symbol] = (
                    page,
                    observed,
                    {
                        "receipt_artifact_relative_path": path.relative_to(artifacts).as_posix(),
                        "receipt_sha256": digest,
                        "contract_sha256": receipt["contract_sha256"],
                        "raw_market_relative_path": binding["market_relative_path"],
                        "raw_sha256": binding["sha256"],
                        "ordinal": ordinal,
                        "original_started_at_utc": receipt["started_at_utc"],
                        "original_completed_at_utc": receipt["completed_at_utc"],
                        "original_source_pins": receipt["source_pins"],
                    },
                )
        if set(pages) != set(probe.SCOPE):
            raise ValueError("seed trio missing")
        return pages
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
        raise HistoryStop("seed_binding_invalid") from error


def _snapshot(root: Path, relative: str, repository: Path) -> dict:
    path = _child(root, relative, repository)
    snapshot = inspect_kis_paper_private_daily_backfill_snapshot(
        manifest_path=path, cache_root=root, repo_root=repository
    )
    manifest = json.loads(path.read_bytes())
    if (
        manifest["collector_objective_id"] != GOAL
        or manifest["collector_version"] != VERSION
        or manifest["status"] != "completed"
        or manifest["completed"] is not True
        or manifest["source"]["adjustment_mode"] != "MODP=0_unadjusted"
    ):
        raise ValueError("snapshot contract invalid")
    raw = manifest["files"]["raw_daily_rows"]
    rows = []
    if raw is not None:
        payload = _child(path.parent, raw["path"], repository).read_bytes()
        reader = csv.DictReader(io.StringIO(gzip.decompress(payload).decode(), newline=""))
        for record in reader:
            rows.append(
                _parse_daily_raw_row(
                    {
                        "xymd": record["session_date"].replace("-", ""),
                        "open": record["open"],
                        "high": record["high"],
                        "low": record["low"],
                        "clos": record["close"],
                        "tvol": record["volume"],
                    }
                )
            )
    dates = [row.xymd for row in rows]
    if (
        any(not START <= _date(d) <= END for d in dates)
        or dates != sorted(set(dates))
        or snapshot["output_cursor_date"] != (min(dates) if dates else None)
    ):
        raise ValueError("snapshot bounds invalid")
    snapshot["manifest_path"] = relative
    page = manifest["pages"][0]
    snapshot["page_facts"] = {
        "row_count": page["row_count"],
        "unique_date_count": manifest["deduplication"]["input_row_count"]
        - manifest["deduplication"]["exact_duplicate_rows_removed"],
        "oldest_date": page["oldest_session_date"].replace("-", "")
        if page["oldest_session_date"]
        else None,
        "newest_date": page["newest_session_date"].replace("-", "")
        if page["newest_session_date"]
        else None,
    }
    snapshot["continuation_after"] = "F" if page["continuation_advertised"] else None
    snapshot["code_revision"] = manifest["code_revision"]
    return snapshot


def _initial_index(seed_binding: dict | None) -> dict:
    return {
        "kind": VERSION,
        "goal": GOAL,
        "start": START,
        "end": END,
        "seed_binding": seed_binding,
        "sequence": 0,
        "pending": None,
        "targets": {
            s: {
                "exchange": next(iter(ex)),
                "cursor": END,
                "continuation": None,
                "state": "ready",
                "reason": None,
                "chunks": [],
            }
            for s, ex in probe.SCOPE.items()
        },
    }


def _apply_snapshot(index: dict, snapshot: dict, intent: dict) -> dict:
    symbol = intent["symbol"]
    target = index["targets"][symbol]
    if (
        snapshot["target_key"] != f"{symbol}/{target['exchange']}/MODP=0"
        or snapshot["input_cursor_date"] != target["cursor"]
        or intent["input_cursor"] != target["cursor"]
        or intent["manifest_path"] != snapshot["manifest_path"]
        or snapshot["code_revision"]
        != intent["source_pins"]["scripts/acquire_kis_cross_asset_d1_history.py"]
        or snapshot["page_facts"] != intent["page_facts"]
        or snapshot["continuation_after"] != intent["continuation_after"]
        or ("manifest_hash" in intent and intent["manifest_hash"] != snapshot["manifest_hash"])
        or ("raw_sha256" in intent and intent["raw_sha256"] != snapshot["raw_sha256"])
    ):
        raise ValueError("snapshot cursor invalid")
    prior = {d: h for chunk in target["chunks"] for d, h in chunk["row_fingerprints"].items()}
    current = snapshot["row_fingerprints"]
    if any(d in prior and prior[d] != h for d, h in current.items()):
        raise HistoryStop("daily_duplicate_conflict")
    if current and snapshot["output_cursor_date"] >= target["cursor"]:
        raise HistoryStop("nonadvancing_cursor")
    output = snapshot["output_cursor_date"]
    pages = intent["page_facts"]
    oldest = pages["oldest_date"]
    state = (
        "source_limited" if oldest is None else ("window_covered" if oldest <= START else "ready")
    )
    chunk = {
        key: snapshot[key]
        for key in (
            "manifest_path",
            "manifest_hash",
            "raw_sha256",
            "row_count",
            "row_fingerprints",
            "input_cursor_date",
            "output_cursor_date",
            "collected_at_utc",
        )
    }
    chunk.update(
        {
            "intent_path": intent["intent_path"],
            "intent_sha256": intent["intent_sha256"],
            "seed": intent["seed"],
            "page_facts": pages,
            "state_after": state,
            "exact_overlap_count": sum(d in prior for d in current),
        }
    )
    target["chunks"].append(chunk)
    target.update(
        cursor=output or target["cursor"],
        continuation=intent["continuation_after"],
        state=state,
        reason="empty_response" if state == "source_limited" else None,
    )
    index["pending"] = None
    return chunk


def _verify_index(index: dict, root: Path, repository: Path, seed_binding: dict | None) -> None:
    expected = _initial_index(seed_binding)
    if any(index[key] != expected[key] for key in ("kind", "goal", "start", "end", "seed_binding")):
        raise ValueError("catalog identity invalid")
    if set(index["targets"]) != set(probe.SCOPE):
        raise ValueError("catalog targets invalid")
    for symbol, target in index["targets"].items():
        if target["exchange"] != expected["targets"][symbol]["exchange"]:
            raise ValueError("catalog venue invalid")
        for chunk in target["chunks"]:
            intent_bytes = _child(root, chunk["intent_path"], repository).read_bytes()
            if probe._sha(intent_bytes) != chunk["intent_sha256"]:
                raise ValueError("intent hash invalid")
            intent = json.loads(intent_bytes)
            intent.update(intent_path=chunk["intent_path"], intent_sha256=chunk["intent_sha256"])
            snapshot = _snapshot(root, chunk["manifest_path"], repository)
            replayed = _apply_snapshot(expected, snapshot, intent)
            if replayed != chunk:
                raise ValueError("catalog source drift")
        if any(
            target[key] != expected["targets"][symbol][key] for key in ("cursor", "continuation")
        ):
            raise ValueError("catalog cursor drift")
        replayed_target = expected["targets"][symbol]
        blocked = (
            target["state"] == "blocked"
            and replayed_target["state"] == "ready"
            and target["reason"]
            in {"daily_duplicate_conflict", "nonadvancing_cursor", "date_after_anchor"}
        )
        if not blocked and any(target[key] != replayed_target[key] for key in ("state", "reason")):
            raise ValueError("catalog terminal drift")


class _FiniteTransport:
    def __init__(self, delegate, *, deadline, monotonic, check_source, maximum_get_pages):
        self.delegate = delegate
        self.deadline = deadline
        self.monotonic = monotonic
        self.check_source = check_source
        self.maximum_get_pages = maximum_get_pages
        self.posts = self.gets = 0

    def request(self, request):
        self.check_source()
        if self.monotonic() + 15 > self.deadline:
            raise HistoryStop("runtime_budget")
        if request.method == "POST" and request.url.endswith(KIS_PAPER_TOKEN_PATH):
            if self.posts >= 1:
                raise HistoryStop("page_budget")
            self.posts += 1
        elif (
            request.method == "GET"
            and request.url.endswith(KIS_PAPER_DAILY_PATH)
            and request.daily_adjustment_modes is None
            and request.query.get("MODP") == "0"
        ):
            if self.gets >= self.maximum_get_pages:
                raise HistoryStop("page_budget")
            self.gets += 1
        else:
            raise KisPaperMarketDataError("request_not_allowlisted")
        response = self.delegate.request(request)
        self.check_source()
        return response


def run_history(
    *,
    market_root: Path,
    artifact_root: Path,
    repository_root: Path,
    run_label: str,
    dotenv_path: Path,
    seed_receipt: Path | None = None,
    seed_sha256: str | None = None,
    seed_source_root: Path | None = None,
    maximum_get_pages: int = 180,
    runtime_seconds: float = 900,
    clock: Callable | None = None,
    monotonic: Callable = time.monotonic,
    sleeper: Callable = time.sleep,
    transport_factory: Callable | None = None,
    config_loader: Callable | None = None,
    space_check: Callable | None = None,
) -> dict:
    if (
        not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", run_label)
        or type(maximum_get_pages) is not int
        or not 1 <= maximum_get_pages <= 180
        or not math.isfinite(runtime_seconds)
        or not 15 <= runtime_seconds <= 900
        or (seed_receipt is None) != (seed_sha256 is None)
        or (seed_sha256 is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", seed_sha256))
        or repository_root.resolve() != ROOT
    ):
        raise ValueError("appointment contract invalid")
    clock = clock or (lambda: datetime.now(UTC))
    started = clock()
    deadline = monotonic() + runtime_seconds
    pins = _pins(repository_root)
    market = probe._external(market_root, repository_root)
    artifacts = probe._external(artifact_root, repository_root)
    if market == artifacts or market.is_relative_to(artifacts) or artifacts.is_relative_to(market):
        raise ValueError("disjoint roots required")
    root = _child(
        market,
        f"us_equities/kis_paper_private/cross-asset-d1/{GOAL}/canonical-trio-v1",
        repository_root,
    )
    run_root = _child(artifacts, f"data/{GOAL}/history/{run_label}", repository_root)
    run_root.mkdir(parents=True)
    seed_binding = (
        None
        if seed_receipt is None
        else {
            "artifact_relative_path": probe._external(seed_receipt, repository_root)
            .relative_to(artifacts)
            .as_posix(),
            "sha256": seed_sha256,
        }
    )
    contract_sha = probe._write_json(
        run_root / "contract.json",
        {
            "kind": VERSION,
            "goal": GOAL,
            "run_label": run_label,
            "started_at_utc": probe._utc(started),
            "source_pins": pins,
            "maximum_GETs": maximum_get_pages,
            "maximum_token_POSTs": 1,
            "runtime_seconds": runtime_seconds,
            "timeout_seconds": 15,
            "start": START,
            "end": END,
            "seed_binding": seed_binding,
            "modes": "MODP0 opaque; no dividend/TR/PIT/finality claim",
        },
    )
    check_space = space_check or (
        lambda count: private_daily_cache_would_cross_free_space_floor(
            cache_root=root, repo_root=repository_root, projected_bytes=count
        )
    )
    index = None
    lock = None
    client = None
    token_gate = request_gate = None
    reason = next_due = None
    accepted = seeds = failures = 0
    recovered = False

    def check_source():
        if _pins(repository_root) != pins:
            raise HistoryStop("source_hash_changed")

    def paced_sleep(delay):
        nonlocal next_due
        if not math.isfinite(delay) or delay < 0:
            raise HistoryStop("invalid_pacing_delay")
        if delay > 1.0 + 1e-6:
            next_due = probe._utc(clock() + timedelta(seconds=delay))
            raise HistoryStop("cooldown_not_due")
        if monotonic() + delay + 15 > deadline:
            raise HistoryStop("runtime_budget")
        sleeper(delay)

    def begin(symbol, seed):
        target = index["targets"][symbol]
        index["sequence"] += 1
        sequence = index["sequence"]
        run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + f"-{sequence:06d}"
        snapshot_name = f"snapshot={run_id}-{symbol.lower()}-{target['exchange'].lower()}-modp0-v1"
        relative = f"{snapshot_name}/manifest.json"
        intent = {
            "symbol": symbol,
            "exchange": target["exchange"],
            "input_cursor": target["cursor"],
            "continuation_before": target["continuation"],
            "manifest_path": relative,
            "run_id": run_id,
            "source_pins": pins,
            "observed_at_utc": probe._utc(clock()),
            "seed": seed,
        }
        path = root / "intents" / f"{sequence:06d}.json"
        digest = _write_exact_json(path, intent)
        index["pending"] = {
            "intent_path": path.relative_to(root).as_posix(),
            "intent_sha256": digest,
        }
        _save_index(root, index)
        return intent

    def finish(page, observed, intent):
        nonlocal accepted, seeds
        rows = _validated_rows(page, intent["input_cursor"])
        target = index["targets"][intent["symbol"]]
        prior = {
            d.replace("-", ""): h
            for c in target["chunks"]
            for d, h in c["row_fingerprints"].items()
        }
        # Compare the same CSV fingerprint contract as the existing offline reader.
        for row in rows:
            csv_values = (
                intent["symbol"],
                intent["exchange"],
                datetime.strptime(row.xymd, "%Y%m%d").date().isoformat(),
                row.open,
                row.high,
                row.low,
                row.clos,
                row.tvol,
            )
            if row.xymd in prior and prior[row.xymd] != probe._sha(
                "\x1f".join(csv_values).encode()
            ):
                raise HistoryStop("daily_duplicate_conflict")
        if rows and rows[0].xymd >= intent["input_cursor"]:
            raise HistoryStop("nonadvancing_cursor")
        if check_space(1_048_576):
            raise HistoryStop("storage_floor")
        check_source()
        selected = tuple(r for r in rows if START <= r.xymd <= END)
        result = KisPaperPrivateDailyCollectionResult(
            observed_at=observed,
            requested_anchor_date=intent["input_cursor"],
            code_revision=intent["source_pins"]["scripts/acquire_kis_cross_asset_d1_history.py"],
            call_counts=KisPaperMarketDataCallCounts(0, 0, 1),
            pages=(
                KisPaperPrivateDailyCollectorPage(
                    1,
                    len(page.rows),
                    max((r.xymd for r in page.rows), default=None),
                    min((r.xymd for r in page.rows), default=None),
                    page.page.continuation_available,
                ),
            ),
            rows=selected,
            dedupe_count=len(page.rows) - len(rows),
            conflicting_duplicate_rows=0,
            inter_page_delay_seconds=(),
            status="observed",
            symbol=intent["symbol"],
            exchange=intent["exchange"],
            approved_symbol_exchanges=probe.SCOPE,
        )
        write_kis_paper_private_daily_cache(
            result=result,
            cache_root=root,
            run_id=intent["run_id"],
            repo_root=repository_root,
            collector_objective_id=GOAL,
            collector_version=VERSION,
            backfill_context={
                "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
                "cursor_strategy": "oldest_session_date_with_exact_overlap",
                "input_cursor_date": intent["input_cursor"],
                "logical_cursor_persisted": True,
                "output_cursor_date": selected[0].xymd if selected else None,
                "target_key": f"{intent['symbol']}/{intent['exchange']}/MODP=0",
            },
        )
        intent["page_facts"] = {
            "row_count": len(page.rows),
            "unique_date_count": len(rows),
            "oldest_date": rows[0].xymd if rows else None,
            "newest_date": rows[-1].xymd if rows else None,
        }
        intent["continuation_after"] = "F" if page.page.continuation_available else None
        snapshot = _snapshot(root, intent["manifest_path"], repository_root)
        intent["manifest_hash"] = snapshot["manifest_hash"]
        intent["raw_sha256"] = snapshot["raw_sha256"]
        # This immutable completion binds the accepted raw manifest before index publication.
        pending = index["pending"]
        complete_path = root / "intents" / f"{index['sequence']:06d}-accepted.json"
        complete_hash = _write_exact_json(complete_path, intent)
        pending.update(
            intent_path=complete_path.relative_to(root).as_posix(), intent_sha256=complete_hash
        )
        _save_index(root, index)
        intent.update(pending)
        chunk = _apply_snapshot(index, snapshot, intent)
        _save_index(root, index)
        if chunk["seed"] is None:
            accepted += 1
        else:
            seeds += 1

    try:
        if check_space(1_048_576):
            raise HistoryStop("storage_floor")
        root.mkdir(parents=True, exist_ok=True)
        (root / "intents").mkdir(exist_ok=True)
        lock = _acquire_worker_lock(root=root, observed_at=started)
        if lock is None:
            raise HistoryStop("worker_busy")
        index_path = root / "index.json"
        candidate = (
            json.loads(index_path.read_bytes())
            if index_path.exists()
            else _initial_index(seed_binding)
        )
        _verify_index(candidate, root, repository_root, seed_binding)
        index = candidate
        if not index_path.exists():
            _save_index(root, index)
        if index["pending"] is None:
            orphan_path = root / "intents" / f"{index['sequence'] + 1:06d}.json"
            if orphan_path.exists():
                orphan_bytes = orphan_path.read_bytes()
                _verify_intent(json.loads(orphan_bytes), index)
                index["sequence"] += 1
                index["pending"] = {
                    "intent_path": orphan_path.relative_to(root).as_posix(),
                    "intent_sha256": probe._sha(orphan_bytes),
                }
                _save_index(root, index)
        seed_pages = (
            {}
            if seed_receipt is None
            else _seed_pages(
                path=seed_receipt,
                digest=seed_sha256,
                market=market,
                artifacts=artifacts,
                repository=repository_root,
                source_root=seed_source_root,
            )
        )
        if index["pending"] is not None:
            pending = index["pending"]
            data = _child(root, pending["intent_path"], repository_root).read_bytes()
            if probe._sha(data) != pending["intent_sha256"]:
                raise HistoryStop("catalog_binding_invalid")
            intent = json.loads(data)
            _verify_intent(intent, index)
            if "page_facts" not in intent:
                manifest_path = _child(root, intent["manifest_path"], repository_root)
                if not manifest_path.exists():
                    unknown_path = root / "intents" / f"{index['sequence']:06d}-unknown.json"
                    _write_exact_json(
                        unknown_path,
                        {
                            **pending,
                            "category": "read_only_GET_outcome_unknown",
                            "accepted_snapshot_observed": False,
                        },
                    )
                    index["pending"] = None
                    _save_index(root, index)
                else:
                    snapshot = _snapshot(root, intent["manifest_path"], repository_root)
                    intent["page_facts"] = snapshot["page_facts"]
                    intent["continuation_after"] = snapshot["continuation_after"]
                    intent["manifest_hash"] = snapshot["manifest_hash"]
                    intent["raw_sha256"] = snapshot["raw_sha256"]
                    complete_path = root / "intents" / f"{index['sequence']:06d}-accepted.json"
                    digest = _write_exact_json(complete_path, intent)
                    pending.update(
                        intent_path=complete_path.relative_to(root).as_posix(), intent_sha256=digest
                    )
                    _save_index(root, index)
            if index["pending"] is not None:
                intent.update(pending)
                _apply_snapshot(
                    index, _snapshot(root, intent["manifest_path"], repository_root), intent
                )
                _save_index(root, index)
                recovered = True
        if not recovered:
            for symbol, (page, observed, binding) in seed_pages.items():
                if not index["targets"][symbol]["chunks"]:
                    finish(page, observed, begin(symbol, binding))
            _save_index(root, index)
            control = _child(
                market, "us_equities/kis_paper_private/collection-control-v1", repository_root
            )
            request_gate = KisPaperMarketDataRateGate(
                control_root=control, clock=clock, sleeper=paced_sleep
            )
            token_gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=clock)
            if any(t["state"] == "ready" for t in index["targets"].values()):
                check_source()
                config = (config_loader or load_kis_paper_market_data_config)(dotenv_path)
                transport = (transport_factory or probe.CrossAssetDailyTransport)(
                    timeout_seconds=15, request_gate=request_gate, token_start_gate=token_gate
                )
                client = KisPaperMarketDataClient(
                    config=config,
                    transport=_FiniteTransport(
                        transport,
                        deadline=deadline,
                        monotonic=monotonic,
                        check_source=check_source,
                        maximum_get_pages=maximum_get_pages,
                    ),
                    max_daily_page_attempts=maximum_get_pages,
                    max_minute_page_attempts=1,
                )
                client.ensure_authenticated()
                while True:
                    ready = [(s, t) for s, t in index["targets"].items() if t["state"] == "ready"]
                    if not ready:
                        break
                    if client.call_counts.daily_page_attempts >= maximum_get_pages:
                        raise HistoryStop("page_budget")
                    if monotonic() + 15 > deadline:
                        raise HistoryStop("runtime_budget")
                    symbol, target = min(ready, key=lambda item: (len(item[1]["chunks"]), item[0]))
                    if check_space(1_048_576):
                        raise HistoryStop("storage_floor")
                    intent = begin(symbol, None)
                    page = client.fetch_daily_raw_page(
                        KisPaperDailyQuery(
                            symbol=symbol,
                            exchange=target["exchange"],
                            by_date=target["cursor"],
                            continuation=target["continuation"],
                            approved_symbol_exchanges=probe.SCOPE,
                        )
                    )
                    finish(page, clock(), intent)
    except HistoryStop as error:
        reason = str(error) if str(error) in STOP_CODES else "local_io_or_contract_invalid"
    except KisPaperMarketDataError as error:
        reason = str(error) if str(error) in probe.SAFE_REASONS else "provider_failure_unclassified"
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        reason = "local_io_or_contract_invalid"
    finally:
        if reason is not None:
            failures = int(
                reason
                not in {
                    "page_budget",
                    "runtime_budget",
                    "worker_busy",
                    "storage_floor",
                    "cooldown_not_due",
                    "token_request_not_due",
                }
            )
        try:
            if reason == "token_request_not_due" and token_gate is not None:
                due = token_gate.snapshot().next_token_request_not_before_utc
                next_due = probe._utc(due) if due else None
            if reason == "rate_limited" and request_gate is not None:
                due = request_gate.snapshot().retry_not_before_utc
                next_due = probe._utc(due) if due else None
            if (
                index is not None
                and token_gate is not None
                and any(target["state"] == "ready" for target in index["targets"].values())
            ):
                due = token_gate.snapshot().next_token_request_not_before_utc
                if due is not None and due > clock():
                    next_due = probe._utc(max(due, _time(next_due) if next_due else due))
            # Known failures do not reset or advance a cursor. Unknown results stay exact.
            if (
                lock is not None
                and index is not None
                and index["pending"] is not None
                and reason
                in (
                    probe.SAFE_REASONS
                    | {
                        "daily_duplicate_conflict",
                        "nonadvancing_cursor",
                        "date_after_anchor",
                        "cooldown_not_due",
                        "runtime_budget",
                        "storage_floor",
                    }
                )
            ):
                pending_data = _child(
                    root, index["pending"]["intent_path"], repository_root
                ).read_bytes()
                pending_intent = json.loads(pending_data)
                if "page_facts" not in pending_intent:
                    symbol = pending_intent["symbol"]
                    if reason in {
                        "daily_duplicate_conflict",
                        "nonadvancing_cursor",
                        "date_after_anchor",
                    }:
                        index["targets"][symbol].update(state="blocked", reason=reason)
                    index["pending"] = None
                    _save_index(root, index)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            reason = "catalog_projection_unavailable"
        finally:
            _release_worker_lock(lock)
    try:
        source_reattestation = "matched" if _pins(repository_root) == pins else "mismatch"
        if source_reattestation == "mismatch":
            reason = "source_hash_changed"
    except OSError:
        source_reattestation = "unavailable"
        reason = "source_hash_unavailable"
    counts = client.call_counts if client else KisPaperMarketDataCallCounts(0, 0, 0)
    catalog = None
    targets = {}
    durable_index = None
    if index is not None:
        catalog = {
            "market_relative_path": (root / "index.json").relative_to(market).as_posix(),
            "status": "unavailable",
            "sha256": None,
            "immutable_artifact_snapshot": None,
        }
        try:
            data = (root / "index.json").read_bytes()
            disk = json.loads(data)
            _verify_index(disk, root, repository_root, seed_binding)
            durable_index = disk
            for symbol, target in disk["targets"].items():
                keys = {d for c in target["chunks"] for d in c["row_fingerprints"]}
                targets[symbol] = {
                    "exchange": target["exchange"],
                    "state": target["state"],
                    "cursor": target["cursor"],
                    "reason": target["reason"],
                    "unique_date_count": len(keys),
                    "oldest_date": min(keys) if keys else None,
                    "newest_date": max(keys) if keys else None,
                    "snapshot_count": len(target["chunks"]),
                }
            probe._write_new(run_root / "index.json", data)
            catalog.update(
                status="matched", sha256=probe._sha(data), immutable_artifact_snapshot="index.json"
            )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            reason = "catalog_projection_unavailable"
    index = durable_index
    if reason is not None:
        status = "partial" if accepted or seeds or recovered else "unavailable"
    elif recovered:
        status = "recovered"
    elif index is not None and all(
        t["state"] in {"source_limited", "window_covered"} for t in index["targets"].values()
    ):
        status = "complete"
    else:
        status = "partial" if accepted or seeds else "unavailable"
    if reason in {
        "source_hash_unavailable",
        "catalog_projection_unavailable",
        "source_hash_changed",
    }:
        failures = 1
    receipt_path = run_root / "receipt.json"
    receipt_hash = probe._write_json(
        receipt_path,
        {
            "kind": VERSION,
            "goal": GOAL,
            "run_label": run_label,
            "started_at_utc": probe._utc(started),
            "completed_at_utc": probe._utc(clock()),
            "source_pins": pins,
            "source_reattestation": source_reattestation,
            "contract_sha256": contract_sha,
            "status": status,
            "reason": reason,
            "accepted_page_count": accepted,
            "seed_page_count": seeds,
            "categorical_failure_count": failures,
            "call_counts": {
                "token_attempts": counts.token_attempts,
                "daily_page_attempts": counts.daily_page_attempts,
            },
            "dispatch_attempts_are_not_proof_of_HTTP_start": True,
            "catalog": catalog,
            "pending": index["pending"] if index else None,
            "pending_projection": "verified" if index is not None else "unavailable",
            "targets": targets,
            "owned_next_due_utc": next_due,
            "remaining_page_estimate": "unknown",
            "eta": "unknown",
            "recovery_class": "exact_pending_reconcile"
            if index and index["pending"]
            else "resume_exact_cursor",
            "token_body_retained": False,
            "error_body_retained": False,
            "limitations": [
                "MODP0 opaque; no dividend/TR/PIT/finality claim.",
                "Only fixed scope endpoints observed; gaps/calendar completeness not attested.",
                "Deep probe pages never grafted into history.",
            ],
        },
    )
    return {
        "status": status,
        "reason": reason,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_hash,
        "accepted_page_count": accepted,
        "seed_page_count": seeds,
        "categorical_failure_count": failures,
        "call_counts": {
            "token_attempts": counts.token_attempts,
            "daily_page_attempts": counts.daily_page_attempts,
        },
        "targets": targets,
        "owned_next_due_utc": next_due,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--dotenv-path", type=Path, default=ROOT / ".env")
    parser.add_argument("--seed-receipt", type=Path)
    parser.add_argument("--seed-sha256")
    parser.add_argument("--seed-source-root", type=Path)
    parser.add_argument("--maximum-get-pages", type=int, default=180)
    args = parser.parse_args(argv)
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "maximum_GETs": 180,
                    "runtime_seconds": 900,
                    "start": START,
                    "end": END,
                }
            )
        )
        return 0
    try:
        result = run_history(
            market_root=args.market_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            run_label=args.run_label,
            dotenv_path=args.dotenv_path,
            seed_receipt=args.seed_receipt,
            seed_sha256=args.seed_sha256,
            seed_source_root=args.seed_source_root,
            maximum_get_pages=args.maximum_get_pages,
        )
    except (OSError, ValueError, RuntimeError):
        result = {"status": "unavailable", "reason": "local_io_or_contract_invalid"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"complete", "partial", "recovered"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
