"""Finite TLT MODP0 OC recovery in a separate cache; no provider-wide reach claim."""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from acquire_kis_cross_asset_oc_history import (
    SAFE_CODES,
    Stop,
    _advances,
    _json,
    _merge,
    _path,
    _question,
    _require,
    _save,
    _sha,
    _utc,
    _write,
)

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
VERSION = "kis-tlt-oc-history-recovery-v1"
CACHE = f"us_equities/kis_paper_private/cross-asset-oc/{VERSION}"
TARGETS = ("TLT/NAS", "TLT/AMS")
ANCHORS = ("20201231", "20151231", "20101231")
FLOOR = "20070821"
SOURCE_FILES = (
    "scripts/acquire_kis_tlt_oc_history_recovery.py",
    "scripts/acquire_kis_cross_asset_oc_history.py",
    "src/thericher_v2/data/kis_daily_price_endpoints.py",
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/execution/kis_market_data.py",
    "src/thericher_v2/execution/kis_market_data_rate_gate.py",
    "src/thericher_v2/execution/kis_private_daily_backfill.py",
    "src/thericher_v2/execution/kis_private_daily_collector.py",
)
CODES = SAFE_CODES | {"endpoint_page_invalid", "endpoint_hash_invalid", "endpoint_fault_invalid"}
YIELD_CODES = {
    "auth_rejected",
    "auth_response_invalid",
    "rate_limited",
    "token_request_not_due",
    "cooldown_not_due",
    "transport_failure",
    "runtime_budget",
    "page_budget",
    "source_hash_changed",
    "source_hash_unavailable",
    "storage_floor",
    "local_io_unavailable",
    "catalog_invalid",
    "invalid_pacing_delay",
    "provider_failure_unclassified",
}


def _pins():
    return {name: _sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result)
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    _require(raw == _json(value))
    return value


def _query(key, anchor, continuation=None):
    _require(key in TARGETS)
    return KisPaperDailyQuery("TLT", anchor, continuation, key.split("/")[1], SCOPE)


def probe_queries():
    return tuple(_query(key, anchor) for anchor in ANCHORS for key in TARGETS)


def configuration():
    return dict(
        kind=VERSION,
        queries=[_question(q) for q in probe_queries()],
        maximum_GET_attempts=64,
        maximum_accepted_pages=64,
        maximum_token_POST_attempts=1,
        runtime_seconds=360,
        timeout_seconds=15,
        requested_floor=FLOOR,
        cache_market_relative_path=CACHE,
        seed_rule="latest nonempty fixed anchor per venue; other probes remain separate witnesses",
        budget_scope="one invocation; probe and serial history share all budgets",
        input_contract="MODP0 opaque OPEN/CLOSE only; no Bar/adjusted/TR/PIT/finality claim",
    )


def _binding(path, market, raw):
    return dict(market_relative_path=path.relative_to(market).as_posix(), sha256=_sha(raw))


def _read_bound(market, root, binding):
    path = _path(market, binding["market_relative_path"])
    _require(path.is_relative_to(root / "attempts"))
    raw = path.read_bytes()
    _require(_sha(raw) == binding["sha256"])
    return _decode(raw)


def _intent(market, root, binding, pins):
    value = _read_bound(market, root, binding)
    _require(value["kind"] == VERSION and value["source_pins"] == pins)
    request_id = value["request_id"]
    _require(
        type(request_id) is str
        and len(request_id) == 32
        and all(c in "0123456789abcdef" for c in request_id)
    )
    _require(
        binding["market_relative_path"]
        == (root / "attempts" / f"{request_id}-intent.json").relative_to(market).as_posix()
    )
    q = value["query"]
    query = _query(f"{q['symbol']}/{q['exchange']}", q["BYMD"], q["continuation"])
    _require(_question(query) == q)
    ordinal = value["question_ordinal"]
    _require(value["stage"] in {"probe", "history"})
    if value["stage"] == "probe":
        _require(
            type(ordinal) is int
            and 1 <= ordinal <= 6
            and q == _question(probe_queries()[ordinal - 1])
        )
    else:
        _require(ordinal is None)
    return value


def _load_page(market, root, binding, pins):
    manifest = _read_bound(market, root, binding)
    intent = _intent(market, root, manifest["intent"], pins)
    _require(
        manifest["kind"] == VERSION
        and manifest["source_pins"] == pins
        and manifest["query"] == intent["query"]
    )
    base = root / "attempts" / intent["request_id"]
    _require(
        binding["market_relative_path"]
        == Path(str(base) + "-manifest.json").relative_to(market).as_posix()
        and manifest["rows"]["market_relative_path"]
        == Path(str(base) + "-rows.json").relative_to(market).as_posix()
    )
    q = intent["query"]
    raw = _read_bound(market, root, manifest["rows"])
    rows = tuple(
        KisDailyEndpointRow(
            r["session_date"],
            r["open"],
            r["close"],
            r["provider_row_sha256"],
            tuple(r["unused_ohlcv_faults"]),
        )
        for r in raw
    )
    facts = manifest["facts"]
    page = KisDailyEndpointPage(
        _query(f"{q['symbol']}/{q['exchange']}", q["BYMD"], q["continuation"]),
        rows,
        facts["source_row_count"],
        facts["duplicate_row_count"],
        facts["source_body_sha256"],
        facts["continuation"],
        tuple(tuple(p) for p in manifest["source_row_fingerprints"]),
    )
    _require(
        page.safe_facts() == facts
        and manifest["dated_unused_ohlcv_faults"]
        == {r.session_date: list(r.unused_ohlcv_faults) for r in rows if r.unused_ohlcv_faults}
    )
    return manifest, intent, page


def _empty_target():
    return dict(
        seed_ordinal=None,
        cursor=None,
        continuation=None,
        state="unestablished",
        chunks=[],
        failure=None,
    )


def _seed_targets(index, market, root, pins):
    values = {key: {} for key in TARGETS}
    targets = {key: _empty_target() for key in TARGETS}
    if len(index["probes"]) == 6:
        for outcome in index["probes"]:
            if outcome["status"] != "accepted":
                continue
            _, intent, page = _load_page(market, root, outcome["binding"], pins)
            key = f"TLT/{page.query.exchange}"
            if page.rows and targets[key]["seed_ordinal"] is None:
                _merge(values[key], page)
                targets[key].update(
                    seed_ordinal=intent["question_ordinal"],
                    cursor=page.rows[0].session_date.replace("-", ""),
                    continuation=page.continuation,
                    state="floor"
                    if page.rows[0].session_date.replace("-", "") <= FLOOR
                    else "ready",
                )
    return targets, values


def _apply_history(target, prior, page, binding):
    _require(
        target["state"] == "ready"
        and page.query.by_date == target["cursor"]
        and page.query.continuation == target["continuation"]
    )
    _advances(page, target["cursor"])
    _merge(prior, page)
    target["chunks"].append(binding)
    if page.rows:
        target["cursor"] = page.rows[0].session_date.replace("-", "")
        target["state"] = "floor" if target["cursor"] <= FLOOR else "ready"
    else:
        target["state"] = "source_limited"
    target["continuation"] = page.continuation


def _verified_index(root, market, pins):
    index = _decode((root / "index.json").read_bytes())
    _require(
        index["kind"] == VERSION
        and index["source_pins"] == pins
        and set(index["targets"]) == set(TARGETS)
        and len(index["probes"]) <= 6
    )
    for ordinal, outcome in enumerate(index["probes"], 1):
        _require(outcome["ordinal"] == ordinal and type(outcome["ordinal"]) is int)
        if outcome["status"] == "accepted":
            _, intent, _ = _load_page(market, root, outcome["binding"], pins)
        else:
            failure = _read_bound(market, root, outcome["binding"])
            _require(
                outcome["status"] == failure["status"] == "rejected"
                and failure["reason"] in CODES - YIELD_CODES
            )
            intent = _intent(market, root, failure["intent"], pins)
        _require(intent["stage"] == "probe" and intent["question_ordinal"] == ordinal)
    targets, values = _seed_targets(index, market, root, pins)
    for key in TARGETS:
        actual, expected = index["targets"][key], targets[key]
        for binding in actual["chunks"]:
            _, intent, page = _load_page(market, root, binding, pins)
            _require(intent["stage"] == "history" and f"TLT/{page.query.exchange}" == key)
            _apply_history(expected, values[key], page, binding)
        if actual["failure"] is not None:
            failure = _read_bound(market, root, actual["failure"])
            intent = _intent(market, root, failure["intent"], pins)
            _require(
                expected["state"] == "ready"
                and failure["status"] == "rejected"
                and failure["reason"] in CODES - YIELD_CODES
                and intent["stage"] == "history"
                and intent["query"]
                == _question(_query(key, expected["cursor"], expected["continuation"]))
            )
            expected.update(state="stopped", failure=actual["failure"])
        _require(actual == expected)
    if index["pending"] is not None:
        intent = _intent(market, root, index["pending"], pins)
        if intent["stage"] == "probe":
            _require(intent["question_ordinal"] == len(index["probes"]) + 1)
        else:
            key = f"TLT/{intent['query']['exchange']}"
            t = targets[key]
            _require(
                t["state"] == "ready"
                and intent["query"] == _question(_query(key, t["cursor"], t["continuation"]))
            )
    return index, values


def _failure(error):
    if isinstance(error, (Stop, KisPaperMarketDataError)) and str(error) in CODES:
        return str(error)
    return "local_io_unavailable" if isinstance(error, OSError) else "provider_failure_unclassified"


def run_recovery(
    *,
    mode,
    market_root,
    artifact_root,
    run_label,
    dotenv_path,
    maximum_pages=64,
    runtime_seconds=360,
    clock=None,
    monotonic=time.monotonic,
    sleeper=time.sleep,
    transport_factory=None,
    config_loader=None,
    space_check=None,
):
    _require(
        mode in {"probe6", "recover"}
        and type(maximum_pages) is int
        and 6 <= maximum_pages <= 64
        and type(runtime_seconds) in (int, float)
        and math.isfinite(runtime_seconds)
        and 15 <= runtime_seconds <= 360
    )
    _require(
        type(run_label) is str
        and 1 <= len(run_label) <= 80
        and run_label[0].isalnum()
        and run_label.isascii()
        and all(c.isalnum() or c in "_-" for c in run_label)
    )
    market, artifacts = _path(Path(market_root)), _path(Path(artifact_root))
    _require(not market.is_relative_to(artifacts) and not artifacts.is_relative_to(market))
    root, output = _path(market, CACHE), _path(artifacts, f"data/{VERSION}/{run_label}")
    _require(not output.exists())
    output.mkdir(parents=True)
    clock = clock or (lambda: datetime.now(UTC))
    started, tick = clock(), monotonic()
    deadline = tick + runtime_seconds
    limit = 6 if mode == "probe6" else maximum_pages
    pins, lock, index, client, request_gate, token_gate = {}, None, None, None, None, None
    accepted = failures = recovered = 0
    pages, reason, next_due = [], None, None
    contract_pin = None
    space = space_check or (
        lambda count: private_daily_cache_would_cross_free_space_floor(
            cache_root=root, repo_root=ROOT, projected_bytes=count
        )
    )

    def check_source():
        try:
            _require(_pins() == pins, "source_hash_changed")
        except OSError:
            raise Stop("source_hash_unavailable") from None

    def pace(delay):
        nonlocal next_due
        _require(math.isfinite(delay) and delay >= 0, "invalid_pacing_delay")
        if delay > 1 + 1e-6:
            next_due = _utc(clock() + timedelta(seconds=delay))
            raise Stop("cooldown_not_due")
        _require(monotonic() + delay + 15 < deadline, "runtime_budget")
        sleeper(delay)

    def apply(binding, intent, page):
        nonlocal index
        if intent["stage"] == "probe":
            _require(intent["question_ordinal"] == len(index["probes"]) + 1)
            index["probes"].append(
                dict(ordinal=intent["question_ordinal"], status="accepted", binding=binding)
            )
            index["targets"], _ = _seed_targets(index, market, root, pins)
        else:
            key = f"TLT/{page.query.exchange}"
            _apply_history(index["targets"][key], values[key], page, binding)
        index["pending"] = None
        _save(root, index)

    def collect():
        nonlocal pins, contract_pin, lock, index, client, request_gate, token_gate
        nonlocal accepted, failures, recovered, values
        try:
            pins = _pins()
        except OSError:
            raise Stop("source_hash_unavailable") from None
        contract_pin = _write(
            output / "contract.json",
            _json(
                dict(
                    configuration(),
                    mode=mode,
                    source_pins=pins,
                    maximum_GET_attempts=limit,
                    maximum_accepted_pages=limit,
                    runtime_seconds=runtime_seconds,
                    started_at_utc=_utc(started),
                )
            ),
        )
        _require(not space(1_048_576), "storage_floor")
        root.mkdir(parents=True, exist_ok=True)
        lock = _acquire_worker_lock(root=root, observed_at=started)
        _require(lock is not None, "worker_busy")
        if (root / "index.json").exists():
            index, values = _verified_index(root, market, pins)
        else:
            index = dict(
                kind=VERSION,
                source_pins=pins,
                probes=[],
                pending=None,
                targets={key: _empty_target() for key in TARGETS},
            )
            _save(root, index)
            values = {key: {} for key in TARGETS}
        if index["pending"] is not None:
            pending = index["pending"]
            intent = _intent(market, root, pending, pins)
            manifest_path = root / "attempts" / f"{intent['request_id']}-manifest.json"
            if manifest_path.exists():
                binding = _binding(manifest_path, market, manifest_path.read_bytes())
                manifest, original, page = _load_page(market, root, binding, pins)
                _require(manifest["intent"] == pending and original == intent)
                apply(binding, intent, page)
                recovered = 1
                return
            _write(
                root / "attempts" / f"{intent['request_id']}-unknown.json",
                _json(dict(status="unknown", intent=pending)),
            )
            index["pending"] = None
            _save(root, index)
        while True:
            ordinal = len(index["probes"]) + 1
            if ordinal <= 6:
                query, stage = probe_queries()[ordinal - 1], "probe"
            else:
                if mode == "probe6":
                    return
                key = next((k for k in TARGETS if index["targets"][k]["state"] == "ready"), None)
                if key is None:
                    return
                target = index["targets"][key]
                query, stage, ordinal = (
                    _query(key, target["cursor"], target["continuation"]),
                    "history",
                    None,
                )
            _require(
                accepted < limit
                and (client is None or client.call_counts.daily_page_attempts < limit),
                "page_budget",
            )
            _require(monotonic() + 15 < deadline, "runtime_budget")
            check_source()
            if client is None:
                control = _path(market, "us_equities/kis_paper_private/collection-control-v1")
                request_gate = KisPaperMarketDataRateGate(
                    control_root=control, clock=clock, sleeper=pace
                )
                token_gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=clock)
                client = KisPaperDailyEndpointClient(
                    config=(config_loader or load_kis_paper_market_data_config)(dotenv_path),
                    transport=(transport_factory or KisPaperDailyEndpointTransport)(
                        timeout_seconds=15, request_gate=request_gate, token_start_gate=token_gate
                    ),
                    max_daily_page_attempts=limit,
                )
                client.ensure_authenticated()
                _require(monotonic() + 15 < deadline, "runtime_budget")
            intent = dict(
                kind=VERSION,
                request_id=uuid.uuid4().hex,
                stage=stage,
                question_ordinal=ordinal,
                query=_question(query),
                source_pins=pins,
                started_at_utc=_utc(clock()),
            )
            base = root / "attempts" / intent["request_id"]
            raw_intent = _json(intent)
            intent_path = Path(str(base) + "-intent.json")
            _write(intent_path, raw_intent)
            pending = _binding(intent_path, market, raw_intent)
            index["pending"] = pending
            _save(root, index)
            manifest_path = Path(str(base) + "-manifest.json")
            try:
                page = client.fetch_daily_endpoint_page(query)
                _require(page.query == query)
                if stage == "history":
                    _advances(page, query.by_date)
                    _merge(dict(values[f"TLT/{query.exchange}"]), page)
                check_source()
                rows = _json([r.as_document() for r in page.rows])
                _require(not space(len(rows) + 100_000), "storage_floor")
                row_path = Path(str(base) + "-rows.json")
                _write(row_path, rows)
                manifest = dict(
                    kind=VERSION,
                    source_pins=pins,
                    intent=pending,
                    query=_question(query),
                    observed_at_utc=_utc(clock()),
                    facts=page.safe_facts(),
                    source_row_fingerprints=list(page.source_row_fingerprints),
                    dated_unused_ohlcv_faults={
                        r.session_date: list(r.unused_ohlcv_faults)
                        for r in page.rows
                        if r.unused_ohlcv_faults
                    },
                    rows=_binding(row_path, market, rows),
                )
                raw_manifest = _json(manifest)
                _write(manifest_path, raw_manifest)
                binding = _binding(manifest_path, market, raw_manifest)
                _load_page(market, root, binding, pins)
                pages.append(binding)
                accepted += 1
                apply(binding, intent, page)
                if stage == "probe" and len(index["probes"]) == 6:
                    _, values = _seed_targets(index, market, root, pins)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                code = _failure(error)
                failures += 1
                # Preserve pending intent when a committed page still needs index reattachment.
                if manifest_path.exists():
                    raise Stop(code) from None
                outcome = dict(
                    status="unknown" if code == "transport_failure" else "rejected",
                    reason=code,
                    intent=pending,
                )
                failure_path = Path(str(base) + "-failure.json")
                raw = _json(outcome)
                _write(failure_path, raw)
                failure_binding = _binding(failure_path, market, raw)
                index["pending"] = None
                if code not in YIELD_CODES:
                    if stage == "probe":
                        index["probes"].append(
                            dict(ordinal=ordinal, status="rejected", binding=failure_binding)
                        )
                        index["targets"], values = _seed_targets(index, market, root, pins)
                    else:
                        index["targets"][f"TLT/{query.exchange}"].update(
                            state="stopped", failure=failure_binding
                        )
                _save(root, index)
                if code in YIELD_CODES:
                    raise Stop(code) from None

    values = {key: {} for key in TARGETS}
    try:
        try:
            collect()
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
            reason = _failure(error)
        reattestation, catalog, coverage, pending, probe_facts = "unavailable", None, {}, None, []
        try:
            if pins:
                reattestation = "matched" if _pins() == pins else "mismatched"
            if reattestation == "mismatched":
                reason = reason or "source_hash_changed"
        except OSError:
            reason = reason or "source_hash_unavailable"
        try:
            if lock is not None and (root / "index.json").exists():
                durable, durable_values = _verified_index(root, market, pins)
                data = (root / "index.json").read_bytes()
                _require(data == _json(durable))
                catalog = dict(
                    status="matched",
                    sha256=_write(output / "index.json", data),
                    market_relative_path=(root / "index.json").relative_to(market).as_posix(),
                    immutable_artifact_snapshot="index.json",
                )
                pending = durable["pending"]
                for outcome in durable["probes"]:
                    fact = dict(
                        ordinal=outcome["ordinal"],
                        status=outcome["status"],
                        query=_question(probe_queries()[outcome["ordinal"] - 1]),
                        binding=outcome["binding"],
                    )
                    if outcome["status"] == "accepted":
                        _, _, page = _load_page(market, root, outcome["binding"], pins)
                        fact["facts"] = page.safe_facts()
                    else:
                        fact["reason"] = _read_bound(market, root, outcome["binding"])["reason"]
                    probe_facts.append(fact)
                for key, rows in durable_values.items():
                    dates = sorted(d for d in rows if d.replace("-", "") >= FLOOR)
                    target = durable["targets"][key]
                    coverage[key] = dict(
                        unique_date_count=len(dates),
                        oldest_date=dates[0] if dates else None,
                        newest_date=dates[-1] if dates else None,
                        cursor=target["cursor"],
                        continuation=target["continuation"],
                        state=target["state"],
                        seed_ordinal=target["seed_ordinal"],
                        accepted_history_pages=len(target["chunks"]),
                    )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            catalog, coverage, pending, probe_facts = None, {}, None, []
            reason = reason or "local_io_unavailable"
        try:
            if reason == "token_request_not_due" and token_gate is not None:
                due = token_gate.snapshot().next_token_request_not_before_utc
                next_due = _utc(due) if due else None
            elif reason == "rate_limited" and request_gate is not None:
                due = request_gate.snapshot().retry_not_before_utc
                next_due = _utc(due) if due else None
        except (OSError, ValueError):
            next_due = None
        counts = client.call_counts if client else None
        status = "partial"
        if not reason and not failures and reattestation == "matched" and catalog is not None:
            status = (
                "recovered" if recovered else "observed" if mode == "probe6" else "scope_terminal"
            )
            if mode == "recover" and any(
                c["state"] in {"ready", "stopped"} for c in coverage.values()
            ):
                status = "partial"
        receipt = dict(
            kind=VERSION,
            mode=mode,
            source_pins=pins,
            source_reattestation=reattestation,
            contract_sha256=contract_pin,
            status=status,
            reason=reason,
            started_at_utc=_utc(started),
            completed_at_utc=_utc(clock()),
            elapsed_seconds=round(monotonic() - tick, 3),
            accepted_page_count=accepted,
            failure_page_count=failures,
            recovered_page_count=recovered,
            pages=pages,
            daily_GET_attempts=counts.daily_page_attempts if counts else 0,
            token_POST_attempts=counts.token_attempts if counts else 0,
            count_semantics="inherited dispatch attempts; not independently measured wire starts",
            measured_shared_interval_seconds=1.0,
            catalog=catalog,
            coverage=coverage,
            pending=pending,
            probe_outcomes=probe_facts,
            pending_projection="verified" if catalog else "unavailable",
            owned_next_due=next_due,
            remaining_pages="unknown",
            eta="unknown",
            recovery_class="reattach_or_resume",
            source_bodies_retained=False,
            strict_ohlcv_grade=False,
            qualification="not_claimed",
        )
        digest = _write(output / "receipt.json", _json(receipt))
        return {
            key: receipt[key]
            for key in (
                "status",
                "reason",
                "accepted_page_count",
                "failure_page_count",
                "recovered_page_count",
                "daily_GET_attempts",
                "token_POST_attempts",
                "owned_next_due",
                "elapsed_seconds",
                "coverage",
            )
        } | dict(receipt_path=str(output / "receipt.json"), receipt_sha256=digest)
    finally:
        try:
            _release_worker_lock(lock)
        except Exception:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--probe6", action="store_true")
    modes.add_argument("--recover", action="store_true")
    parser.add_argument("--market-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env.example")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--maximum-pages", type=int, default=64)
    parser.add_argument("--runtime-seconds", type=float, default=360)
    args = vars(parser.parse_args(argv))
    mode = "probe6" if args.pop("probe6") else "recover"
    args.pop("recover")
    args["dotenv_path"] = args.pop("dotenv")
    try:
        result = run_recovery(mode=mode, **args)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        result = dict(status="unavailable", reason="local_io_unavailable")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"observed", "recovered", "scope_terminal"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
