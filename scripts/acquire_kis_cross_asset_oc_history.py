"""Finite, separate MODP0 OPEN/CLOSE collection; never a strict Bar cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

from thericher_v2.data.kis_daily_price_endpoints import (
    SCOPE,
    KisDailyEndpointPage,
    KisDailyEndpointRow,
    KisPaperDailyEndpointClient,
    KisPaperDailyEndpointTransport,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyQuery,
    KisPaperMarketDataError,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    _acquire_worker_lock,
    _release_worker_lock,
)
from thericher_v2.execution.kis_private_daily_collector import (
    private_daily_cache_would_cross_free_space_floor,
)

ROOT = Path(__file__).resolve().parents[1]
GOAL = "kis-cross-asset-monthly-momentum-development-v1"
VERSION = "kis-cross-asset-oc-history-v1"
START, END = "20070821", "20261007"
TARGETS = ("SPY/AMS", "GLD/AMS", "TLT/NAS", "TLT/AMS")
SOURCE_FILES = (
    "scripts/acquire_kis_cross_asset_oc_history.py",
    "src/thericher_v2/data/kis_daily_price_endpoints.py",
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/execution/kis_market_data.py",
    "src/thericher_v2/execution/kis_market_data_rate_gate.py",
    "src/thericher_v2/execution/kis_private_daily_backfill.py",
    "src/thericher_v2/execution/kis_private_daily_collector.py",
)
# fmt: off
SAFE_CODES = frozenset({
    "endpoint_date_invalid", "endpoint_numeric_invalid", "endpoint_query_invalid",
    "endpoint_schema_invalid", "endpoint_date_after_anchor", "endpoint_duplicate_conflict",
    "credential_echo_rejected", "daily_response_rejected", "daily_response_invalid",
    "response_invalid", "transport_failure", "rate_limited", "auth_rejected",
    "auth_response_invalid", "token_request_not_due", "cooldown_not_due", "runtime_budget",
    "page_budget", "storage_floor", "worker_busy", "source_hash_changed",
    "source_hash_unavailable", "catalog_invalid", "nonadvancing_cursor", "oc_overlap_conflict",
    "invalid_pacing_delay", "local_io_unavailable", "provider_failure_unclassified",
})
WORKER_ERRORS = frozenset({"rate_limited", "auth_rejected", "auth_response_invalid",
    "token_request_not_due", "cooldown_not_due", "runtime_budget", "source_hash_changed",
    "storage_floor", "invalid_pacing_delay"})
# fmt: on


class Stop(RuntimeError):
    """Closed categorical failure, never provider text."""


def _require(condition, code="catalog_invalid"):
    if not condition:
        raise Stop(code)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json(document) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _pins() -> dict:
    return {name: _sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def _path(root: Path, relative="") -> Path:
    path = (root / relative).absolute()
    _require(
        not any(p.exists() and (p.is_symlink() or p.is_junction()) for p in (path, *path.parents))
    )
    _require(
        path == path.resolve()
        and not path.is_relative_to(ROOT)
        and path.is_relative_to(root.absolute())
    )
    return path


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _require(path.read_bytes() == data)
    else:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    return _sha(data)


def _save(root: Path, index: dict):
    temporary = root / f"index-{uuid.uuid4().hex}.tmp"
    _write(temporary, _json(index))
    os.replace(temporary, root / "index.json")


def _utc(value: datetime) -> str:
    _require(value.tzinfo == UTC)
    return value.isoformat().replace("+00:00", "Z")


def _query(key: str, anchor: str, continuation=None):
    symbol, exchange = key.split("/")
    return KisPaperDailyQuery(symbol, anchor, continuation, exchange, SCOPE)


def _question(query) -> dict:
    return dict(
        symbol=query.symbol,
        exchange=query.exchange,
        BYMD=query.by_date,
        MODP="0",
        continuation=query.continuation,
    )


def probe_queries() -> tuple:
    return tuple(
        _query(key, anchor, continuation)
        for key, anchor, continuation in (
            ("GLD/AMS", "20210820", "F"),
            ("TLT/NAS", "20151231", None),
            ("TLT/AMS", "20151231", None),
            ("TLT/AMS", "20071231", None),
            ("GLD/AMS", "20071231", None),
            ("SPY/AMS", "20071231", None),
        )
    )


def _load(market: Path, binding: dict) -> tuple[dict, KisDailyEndpointPage]:
    path = _path(market, binding["market_relative_path"])
    data = path.read_bytes()
    _require(_sha(data) == binding["sha256"])
    manifest = json.loads(data)
    intent_path = _path(market, manifest["intent"]["market_relative_path"])
    intent_data = intent_path.read_bytes()
    _require(_sha(intent_data) == manifest["intent"]["sha256"])
    intent = json.loads(intent_data)
    q = manifest["query"]
    _require(
        manifest["kind"] == VERSION
        and intent["kind"] == VERSION
        and manifest["query"] == intent["query"]
        and manifest["source_pins"] == intent["source_pins"]
        and manifest["source_pins"] == _pins()
        and q["MODP"] == "0"
    )
    query = _query(f"{q['symbol']}/{q['exchange']}", q["BYMD"], q["continuation"])
    row_path = _path(market, manifest["rows"]["market_relative_path"])
    raw = row_path.read_bytes()
    _require(_sha(raw) == manifest["rows"]["sha256"])
    rows = tuple(
        KisDailyEndpointRow(
            row["session_date"],
            row["open"],
            row["close"],
            row["provider_row_sha256"],
            tuple(row["unused_ohlcv_faults"]),
        )
        for row in json.loads(raw)
    )
    pairs = tuple(tuple(pair) for pair in manifest["source_row_fingerprints"])
    facts = manifest["facts"]
    page = KisDailyEndpointPage(
        query,
        rows,
        facts["source_row_count"],
        facts["duplicate_row_count"],
        facts["source_body_sha256"],
        facts["continuation"],
        pairs,
    )
    _require(page.safe_facts() == facts)
    _require(
        manifest["dated_unused_ohlcv_faults"]
        == {r.session_date: list(r.unused_ohlcv_faults) for r in rows if r.unused_ohlcv_faults}
    )
    return manifest, page


def _merge(prior: dict, page: KisDailyEndpointPage) -> int:
    variants = 0
    current = {r.session_date: set() for r in page.rows}
    for day, digest in page.source_row_fingerprints:
        current[day].add(digest)
    for row in page.rows:
        old = prior.get(row.session_date)
        _require(old is None or old[:2] == (row.open, row.close), "oc_overlap_conflict")
        variants += int(old is not None and bool(current[row.session_date] - old[2]))
        prior[row.session_date] = (
            row.open,
            row.close,
            frozenset(current[row.session_date] | (old[2] if old is not None else set())),
        )
    return variants


def _advances(page: KisDailyEndpointPage, cursor: str):
    _require(
        not page.rows or page.rows[0].session_date.replace("-", "") < cursor, "nonadvancing_cursor"
    )


def _verified_index(
    root: Path, market: Path, pins: dict, seed, artifacts: Path
) -> tuple[dict, dict]:
    index = json.loads((root / "index.json").read_bytes())
    _require(
        index["kind"] == VERSION
        and index["source_pins"] == pins
        and index["seed_binding"] == seed
        and tuple(index["targets"]) == tuple(sorted(TARGETS))
    )
    seed_pages = _seeds(
        _path(artifacts, seed["artifact_relative_path"]), seed["sha256"], artifacts, market, pins
    )
    expected_seeds = {key: [] for key in TARGETS}
    for binding in seed_pages:
        _, page = _load(market, binding)
        expected_seeds[f"{page.query.symbol}/{page.query.exchange}"].append(
            {**binding, "seed": True}
        )
    values = {key: {} for key in TARGETS}
    for key, target in index["targets"].items():
        cursor, continuation = END, None
        observed_seeds, nonseed_seen = [], False
        for binding in target["chunks"]:
            _require(type(binding["seed"]) is bool)
            manifest, page = _load(market, binding)
            _require(f"{page.query.symbol}/{page.query.exchange}" == key)
            if binding["seed"]:
                _require(not nonseed_seen)
                observed_seeds.append(binding)
            else:
                nonseed_seen = True
                _require(page.query.by_date == cursor and page.query.continuation == continuation)
                _require(manifest["question_ordinal"] is None)
                _advances(page, cursor)
                cursor = page.rows[0].session_date.replace("-", "") if page.rows else cursor
                continuation = page.continuation
            _merge(values[key], page)
        _require(
            observed_seeds == expected_seeds[key]
            and target["cursor"] == cursor
            and target["continuation"] == continuation
            and target["state"] in {"ready", "unestablished", "stopped", "empty", "floor"}
        )
    return index, values


def _seeds(path: Path, digest: str, artifacts: Path, market: Path, pins: dict) -> list:
    data = _path(artifacts, path.absolute().relative_to(artifacts)).read_bytes()
    _require(_sha(data) == digest)
    receipt = json.loads(data)
    contract_data = (path.parent / "contract.json").read_bytes()
    contract = json.loads(contract_data)
    _require(
        receipt["kind"] == VERSION
        and receipt["mode"] == "probe6"
        and receipt["source_pins"] == pins
        and receipt["source_reattestation"] == "matched"
        and receipt["contract_sha256"] == _sha(contract_data)
        and contract["source_pins"] == pins
        and contract["mode"] == "probe6"
        and contract["queries"] == [_question(q) for q in probe_queries()]
        and contract["maximum_GETs"] == 6
        and contract["maximum_token_POSTs"] == 1
        and receipt["accepted_page_count"] == len(receipt["pages"])
    )
    pages = receipt["pages"]
    ordinals = []
    for binding in pages:
        manifest, page = _load(market, binding)
        ordinal = manifest["question_ordinal"]
        _require(
            type(ordinal) is int
            and 1 <= ordinal <= 6
            and _question(page.query) == _question(probe_queries()[ordinal - 1])
        )
        ordinals.append(ordinal)
    _require(ordinals == sorted(set(ordinals)))
    return pages


def run_collection(
    *,
    mode: str,
    market_root: Path,
    artifact_root: Path,
    run_label: str,
    dotenv_path: Path,
    scope: str = "oc-venues-v1",
    seed_receipt: Path | None = None,
    seed_sha256: str | None = None,
    maximum_get_pages: int = 180,
    runtime_seconds: float = 900,
    clock: Callable | None = None,
    monotonic: Callable = time.monotonic,
    sleeper: Callable = time.sleep,
    transport_factory: Callable | None = None,
    config_loader: Callable | None = None,
    space_check: Callable | None = None,
) -> dict:
    _require(
        mode in {"probe6", "history"}
        and type(maximum_get_pages) is int
        and 1 <= maximum_get_pages <= 180
        and math.isfinite(runtime_seconds)
        and 15 <= runtime_seconds <= 900
        and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", v) for v in (run_label, scope))
        and (seed_receipt is None) == (seed_sha256 is None)
        and (seed_sha256 is None or re.fullmatch(r"sha256:[0-9a-f]{64}", seed_sha256))
    )
    if mode == "probe6":
        maximum_get_pages, runtime_seconds = 6, 60
    market, artifacts = _path(market_root), _path(artifact_root)
    _require(not market.is_relative_to(artifacts) and not artifacts.is_relative_to(market))
    root = _path(
        market,
        f"us_equities/kis_paper_private/cross-asset-oc/{VERSION}/"
        + (f"probe/{run_label}" if mode == "probe6" else f"history/{scope}"),
    )
    run_root = _path(artifacts, f"data/{GOAL}/oc-only/{mode}/{run_label}")
    _require(not run_root.exists())
    run_root.mkdir(parents=True)
    clock = clock or (lambda: datetime.now(UTC))
    started, deadline, pins = clock(), monotonic() + runtime_seconds, _pins()
    seed = (
        None
        if seed_receipt is None
        else {
            "artifact_relative_path": seed_receipt.absolute().relative_to(artifacts).as_posix(),
            "sha256": seed_sha256,
        }
    )
    contract_hash = _write(
        run_root / "contract.json",
        _json(
            dict(
                kind=VERSION,
                mode=mode,
                source_pins=pins,
                started_at_utc=_utc(started),
                scope=scope,
                maximum_GETs=maximum_get_pages,
                maximum_token_POSTs=1,
                runtime_seconds=runtime_seconds,
                timeout_seconds=15,
                start=START,
                end=END,
                seed_binding=seed,
                queries=[_question(q) for q in probe_queries()] if mode == "probe6" else None,
                input_contract="MODP0 opaque OC; no Bar/adjustment/TR/PIT/qualification claim",
            )
        ),
    )
    check_space = space_check or (
        lambda count: private_daily_cache_would_cross_free_space_floor(
            cache_root=root, repo_root=ROOT, projected_bytes=count
        )
    )
    index = client = lock = token_gate = request_gate = None
    values = {key: {} for key in TARGETS}
    accepted = failures = recovered = 0
    pages, outcomes, reason, next_due = [], [], None, None

    def check_source():
        _require(_pins() == pins, "source_hash_changed")

    def pace(delay):
        nonlocal next_due
        _require(math.isfinite(delay) and delay >= 0, "invalid_pacing_delay")
        if delay > 1 + 1e-6:
            next_due = _utc(clock() + timedelta(seconds=delay))
            raise Stop("cooldown_not_due")
        _require(monotonic() + delay + 15 < deadline, "runtime_budget")
        sleeper(delay)

    def accept(intent_binding, intent, page):
        nonlocal accepted
        key = f"{page.query.symbol}/{page.query.exchange}"
        variants = _merge(dict(values[key]), page) if mode == "history" else 0
        if mode == "history":
            _advances(page, page.query.by_date)
        check_source()
        private = _json([r.as_document() for r in page.rows])
        _require(not check_space(len(private) + 100_000), "storage_floor")
        rows_path = root / "attempts" / f"{intent['request_id']}-rows.json"
        row_hash = _write(rows_path, private)
        manifest = dict(
            kind=VERSION,
            query=intent["query"],
            source_pins=pins,
            observed_at_utc=_utc(clock()),
            intent=intent_binding,
            facts=page.safe_facts(),
            question_ordinal=intent["question_ordinal"],
            source_row_fingerprints=list(page.source_row_fingerprints),
            dated_unused_ohlcv_faults={
                r.session_date: list(r.unused_ohlcv_faults)
                for r in page.rows
                if r.unused_ohlcv_faults
            },
            overlap_unused_variant_date_count=variants,
            overlap_unused_variant_count_definition="Overlap dates with new row fingerprints",
            rows=dict(
                market_relative_path=rows_path.relative_to(market).as_posix(), sha256=row_hash
            ),
        )
        path = root / "attempts" / f"{intent['request_id']}-manifest.json"
        digest = _write(path, _json(manifest))
        binding = dict(market_relative_path=path.relative_to(market).as_posix(), sha256=digest)
        _load(market, binding)
        pages.append(binding)
        accepted += 1
        if mode == "history":
            apply(binding, page)
            _save(root, index)

    def apply(binding, page):
        key = f"{page.query.symbol}/{page.query.exchange}"
        target = index["targets"][key]
        _require(
            page.query.by_date == target["cursor"]
            and page.query.continuation == target["continuation"]
        )
        _advances(page, target["cursor"])
        _merge(values[key], page)
        target["chunks"].append({**binding, "seed": False})
        if page.rows:
            target["cursor"] = page.rows[0].session_date.replace("-", "")
            target["state"] = "floor" if target["cursor"] <= START else "ready"
        else:
            target["state"] = "empty"
        target["continuation"] = page.continuation
        index["pending"] = None

    def failure(error):
        if isinstance(error, (Stop, KisPaperMarketDataError)) and str(error) in SAFE_CODES:
            return str(error)
        return (
            "local_io_unavailable"
            if isinstance(error, OSError)
            else "provider_failure_unclassified"
        )

    def collect():
        nonlocal lock, index, values, client, token_gate, request_gate, recovered, failures
        _require(not check_space(1_048_576), "storage_floor")
        root.mkdir(parents=True, exist_ok=True)
        lock = _acquire_worker_lock(root=root, observed_at=started)
        _require(lock is not None, "worker_busy")
        values = {key: {} for key in TARGETS}
        if mode == "history":
            _require(seed_receipt is not None)
            seed_pages = _seeds(seed_receipt, seed_sha256, artifacts, market, pins)
            if (root / "index.json").exists():
                index, values = _verified_index(root, market, pins, seed, artifacts)
            else:
                index = dict(
                    kind=VERSION,
                    source_pins=pins,
                    seed_binding=seed,
                    pending=None,
                    targets={
                        key: dict(cursor=END, continuation=None, state="unestablished", chunks=[])
                        for key in sorted(TARGETS)
                    },
                )
                for binding in seed_pages:
                    _, page = _load(market, binding)
                    key = f"{page.query.symbol}/{page.query.exchange}"
                    _merge(values[key], page)
                    index["targets"][key]["chunks"].append({**binding, "seed": True})
                    if page.rows:
                        index["targets"][key]["state"] = "ready"
                _save(root, index)
            if index["pending"] is not None:
                pending = index["pending"]
                intent_data = _path(market, pending["market_relative_path"]).read_bytes()
                _require(_sha(intent_data) == pending["sha256"])
                intent = json.loads(intent_data)
                path = root / "attempts" / f"{intent['request_id']}-manifest.json"
                if path.exists():
                    binding = dict(
                        market_relative_path=path.relative_to(market).as_posix(),
                        sha256=_sha(path.read_bytes()),
                    )
                    manifest, page = _load(market, binding)
                    _require(manifest["intent"] == pending)
                    apply(binding, page)
                    _save(root, index)
                    recovered = 1
                else:
                    _write(
                        root / "attempts" / f"{intent['request_id']}-unknown.json",
                        _json(dict(status="unknown", intent=pending)),
                    )
                    index["pending"] = None
                    _save(root, index)
        if not recovered and (
            mode == "probe6"
            or any(target["state"] == "ready" for target in index["targets"].values())
        ):
            control = _path(market, "us_equities/kis_paper_private/collection-control-v1")
            request_gate = KisPaperMarketDataRateGate(
                control_root=control, clock=clock, sleeper=pace
            )
            token_gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=clock)
            check_source()
            client = KisPaperDailyEndpointClient(
                config=(config_loader or load_kis_paper_market_data_config)(dotenv_path),
                transport=(transport_factory or KisPaperDailyEndpointTransport)(
                    timeout_seconds=15, request_gate=request_gate, token_start_gate=token_gate
                ),
                max_daily_page_attempts=maximum_get_pages,
            )
            _require(monotonic() + 15 < deadline, "runtime_budget")
            client.ensure_authenticated()
            keys = TARGETS if mode == "history" else range(6)
            for item in keys:
                while mode == "probe6" or index["targets"][item]["state"] == "ready":
                    _require(
                        client.call_counts.daily_page_attempts < maximum_get_pages, "page_budget"
                    )
                    _require(monotonic() + 15 < deadline, "runtime_budget")
                    check_source()
                    query = (
                        probe_queries()[item]
                        if mode == "probe6"
                        else _query(
                            item,
                            index["targets"][item]["cursor"],
                            index["targets"][item]["continuation"],
                        )
                    )
                    intent = dict(
                        kind=VERSION,
                        request_id=uuid.uuid4().hex,
                        query=_question(query),
                        source_pins=pins,
                        started_at_utc=_utc(clock()),
                        question_ordinal=item + 1 if mode == "probe6" else None,
                    )
                    path = root / "attempts" / f"{intent['request_id']}-intent.json"
                    binding = dict(
                        market_relative_path=path.relative_to(market).as_posix(),
                        sha256=_write(path, _json(intent)),
                    )
                    if mode == "history":
                        index["pending"] = binding
                        _save(root, index)
                    try:
                        page = client.fetch_daily_endpoint_page(query)
                        accept(binding, intent, page)
                    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                        code = failure(error)
                        failures += 1
                        outcome = dict(
                            intent=binding,
                            query=_question(query),
                            reason=code,
                            status="unknown" if code == "transport_failure" else "rejected",
                        )
                        _write(run_root / f"failure-{intent['request_id']}.json", _json(outcome))
                        outcomes.append(outcome)
                        if code in WORKER_ERRORS or code in {
                            "local_io_unavailable",
                            "catalog_invalid",
                        }:
                            raise Stop(code) from None
                        if mode == "history":
                            index["pending"] = None
                            if code != "transport_failure":
                                index["targets"][item].update(state="stopped", reason=code)
                            _save(root, index)
                        break
                    if mode == "probe6":
                        break

    def publish():
        nonlocal reason, next_due, index, values
        reattestation, catalog, coverage = "unavailable", None, {}
        if mode == "history":
            catalog = dict(status="unavailable", sha256=None)
        try:
            reattestation = "matched" if _pins() == pins else "mismatched"
            if reattestation == "mismatched":
                reason = reason or "source_hash_changed"
        except OSError:
            reason = reason or "source_hash_unavailable"
        try:
            if mode == "history" and lock is not None and (root / "index.json").exists():
                index, values = _verified_index(root, market, pins, seed, artifacts)
                data = (root / "index.json").read_bytes()
                _require(data == _json(index))
                digest = _write(run_root / "index.json", data)
                catalog = dict(
                    status="matched",
                    sha256=digest,
                    market_relative_path=(root / "index.json").relative_to(market).as_posix(),
                    immutable_artifact_snapshot="index.json",
                )
                for key, rows in values.items():
                    dates = sorted(d for d in rows if START <= d.replace("-", "") <= END)
                    target = index["targets"][key]
                    coverage[key] = dict(
                        unique_date_count=len(dates),
                        oldest_date=dates[0] if dates else None,
                        newest_date=dates[-1] if dates else None,
                        accepted_chunk_count=len(target["chunks"]),
                        cursor=target["cursor"],
                        continuation=target["continuation"],
                        state=target["state"],
                    )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            catalog = dict(status="unavailable", sha256=None)
            coverage = {}
            reason = reason or "local_io_unavailable"
        try:
            if reason == "token_request_not_due" and token_gate is not None:
                due = token_gate.snapshot().next_token_request_not_before_utc
                next_due = _utc(due) if due is not None else None
            elif reason == "rate_limited" and request_gate is not None:
                due = request_gate.snapshot().retry_not_before_utc
                next_due = _utc(due) if due is not None else None
        except (OSError, ValueError):
            next_due = None
        counts = client.call_counts if client is not None else None
        receipt = dict(
            kind=VERSION,
            mode=mode,
            source_pins=pins,
            source_reattestation=reattestation,
            contract_sha256=contract_hash,
            started_at_utc=_utc(started),
            completed_at_utc=_utc(clock()),
            status="observed"
            if mode == "probe6" and not reason and not failures
            else "recovered"
            if recovered and not reason
            else "partial",
            reason=reason,
            accepted_page_count=accepted,
            failure_page_count=failures,
            recovered_page_count=recovered,
            daily_GET_attempts=counts.daily_page_attempts if counts else 0,
            token_POST_attempts=counts.token_attempts if counts else 0,
            count_semantics="inherited dispatch attempts; not independently measured wire starts",
            pages=pages,
            target_failures=outcomes,
            catalog=catalog,
            pending=index["pending"] if catalog and catalog["status"] == "matched" else None,
            pending_projection="verified"
            if catalog and catalog["status"] == "matched"
            else "unavailable",
            coverage=coverage,
            owned_next_due=next_due,
            remaining_pages="unknown",
            eta="unknown",
            recovery_class="resume",
            strict_ohlcv_grade=False,
            qualification="not_claimed",
            source_bodies_retained=False,
        )
        digest = _write(run_root / "receipt.json", _json(receipt))
        return dict(
            status=receipt["status"],
            reason=reason,
            receipt_path=str(run_root / "receipt.json"),
            receipt_sha256=digest,
            accepted_page_count=accepted,
            failure_page_count=failures,
            recovered_page_count=recovered,
            daily_GET_attempts=receipt["daily_GET_attempts"],
            token_POST_attempts=receipt["token_POST_attempts"],
            owned_next_due=next_due,
            coverage=coverage,
        )

    try:
        try:
            collect()
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
            reason = failure(error)
        return publish()
    finally:
        try:
            _release_worker_lock(lock)
        except Exception:
            pass


run_probe6 = partial(run_collection, mode="probe6")
run_history = partial(run_collection, mode="history")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe6", action="store_true")
    mode.add_argument("--history", action="store_true")
    parser.add_argument("--market-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env.example")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--scope", default="oc-venues-v1")
    parser.add_argument("--seed-receipt", type=Path)
    parser.add_argument("--seed-sha256")
    parser.add_argument("--maximum-get-pages", type=int, default=180)
    parser.add_argument("--runtime-seconds", type=float, default=900)
    args = parser.parse_args(argv)
    kwargs = vars(args)
    selected = "probe6" if kwargs.pop("probe6") else "history"
    kwargs.pop("history")
    kwargs["dotenv_path"] = kwargs.pop("dotenv")
    try:
        result = run_collection(mode=selected, **kwargs)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        result = dict(status="unavailable", reason="local_io_unavailable")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"observed", "recovered"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
