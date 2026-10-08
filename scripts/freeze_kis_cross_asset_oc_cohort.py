"""Offline fixed 2016+ OC cohort; default check-only, never acquire or revise inputs."""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import acquire_kis_cross_asset_d1_history as strict_history
from acquire_kis_cross_asset_oc_history import _json, _merge, _sha, _write

from thericher_v2.data.kis_daily_price_endpoints import (
    SCOPE,
    KisDailyEndpointPage,
    KisDailyEndpointRow,
)
from thericher_v2.execution.kis_market_data import KisPaperDailyQuery
from thericher_v2.execution.kis_private_daily_collector import (
    private_daily_cache_would_cross_free_space_floor,
)

ROOT = Path(__file__).resolve().parents[1]
VERSION = "kis-cross-asset-oc-cohort-v1"
START, END = "2016-02-02", "2026-10-07"
CALENDAR_PIN = "sha256:d2dab6f2ab27a7439ed4be91bacefc68b04908d0b3b7d509e4a2b19925a42721"
INPUT_PINS = {
    "oc": "sha256:562aa2e0c490a6a486b12e4a55140246b6c65b2945df9b279c3ca27daeae5bab",
    "older": "sha256:3ba295136735419f71a71a6b3e69e205b5dc4c31865d4690a0eb74853834b61e",
    "bridge": "sha256:714950bc5a088f57889c3e4471b40b5124eaedc5f6272d49d4e8269b96ca67bc",
    "strict": "sha256:02dcc0007a5aa2804c4b0ce497dfb51e21387122869f1ef90f539d597158e516",
}
BASE_SOURCES = (
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/execution/kis_market_data.py",
    "src/thericher_v2/execution/kis_market_data_rate_gate.py",
    "src/thericher_v2/execution/kis_private_daily_backfill.py",
    "src/thericher_v2/execution/kis_private_daily_collector.py",
)
OC_SOURCES = (
    *BASE_SOURCES,
    "scripts/acquire_kis_cross_asset_oc_history.py",
    "src/thericher_v2/data/kis_daily_price_endpoints.py",
)
STRICT_SOURCES = (
    *BASE_SOURCES,
    "scripts/acquire_kis_cross_asset_d1.py",
    "scripts/acquire_kis_cross_asset_d1_history.py",
    "scripts/freeze_kis_cross_asset_d1_input.py",
)
SOURCES = (
    *OC_SOURCES,
    "scripts/acquire_kis_cross_asset_d1.py",
    "scripts/acquire_kis_cross_asset_d1_history.py",
    "scripts/freeze_kis_cross_asset_oc_cohort.py",
)
KINDS = {
    "oc": "kis-cross-asset-oc-history-v1",
    "older": "kis-tlt-oc-history-recovery-v1",
    "bridge": "kis-tlt-venue-bridge-v1",
}
WINDOWS = {
    "oc": (START, END),
    "older": (START, "2020-12-31"),
    "bridge": ("2021-01-04", "2021-08-19"),
    "strict": ("2021-08-20", END),
}
COUNTS = {"oc": 2686, "older": 1239, "bridge": 159, "strict": 1288}
COLUMNS = ("symbol", "exchange", "session_date", "open", "close", "source_chunk_id")
QUESTIONS = {
    "oc": (
        ("GLD", "AMS", "20210820", "F"),
        ("TLT", "NAS", "20151231", None),
        ("TLT", "AMS", "20151231", None),
        ("TLT", "AMS", "20071231", None),
        ("GLD", "AMS", "20071231", None),
        ("SPY", "AMS", "20071231", None),
    ),
    "older": tuple(
        ("TLT", v, a, None) for a in ("20201231", "20151231", "20101231") for v in ("NAS", "AMS")
    ),
    "bridge": (
        ("TLT", "NYS", "20160201", None),
        ("TLT", "NYS", "20101231", None),
        ("TLT", "NYS", "20071231", None),
        ("TLT", "NAS", "20210819", None),
    ),
}


class CohortError(RuntimeError):
    """Closed category only; never propagate input values or exception text."""


@dataclass(frozen=True, slots=True)
class Source:
    path: Path
    source_root: Path


def _require(condition, code="input_chain_invalid"):
    if not condition:
        raise CohortError(code)


def _decode(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            _require(k not in result)
            result[k] = v
        return result

    def nonfinite(_):
        raise CohortError("input_chain_invalid")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def _path(root, relative=""):
    root = Path(root).absolute()
    relative = Path(relative)
    _require(not relative.is_absolute() and ".." not in relative.parts, "source_path_invalid")
    path = root / relative
    _require(path.is_relative_to(root) and path == path.resolve(), "source_path_invalid")
    _require(
        not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
        "source_path_invalid",
    )
    return path


def _pins():
    return {name: _sha((ROOT / name).read_bytes()) for name in SOURCES}


def _utc(text):
    _require(type(text) is str)
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    _require(value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value))
    return value.isoformat().replace("+00:00", "Z")


def _page_stage(name, intent):
    # The original OC producer encoded probe/history only in its ordinal.
    return (
        ("history" if intent["question_ordinal"] is None else "probe")
        if name == "oc"
        else intent["stage"]
    )


def freeze_cohort(
    *,
    market_root,
    artifact_root,
    calendar_path,
    oc,
    older,
    bridge,
    strict,
    run_label,
    publish=False,
    space_check=None,
):
    """One fixed selector, archived producer pins and separately pinned current reader."""
    _require(
        type(publish) is bool and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_label),
        "argument_invalid",
    )
    market, artifacts = _path(market_root), _path(artifact_root)
    _require(
        not market.is_relative_to(artifacts)
        and not artifacts.is_relative_to(market)
        and not market.is_relative_to(ROOT)
        and not artifacts.is_relative_to(ROOT),
        "source_path_invalid",
    )
    code_pins, tracked, bindings, chunks = _pins(), {}, {}, []
    references = {"oc": oc, "older": older, "bridge": bridge, "strict": strict}
    values = {s: {} for s in ("SPY", "TLT", "GLD")}
    witnesses, faults = {}, {}

    def read(path, pin, label):
        base = market if label == "MARKET" else artifacts
        path = _path(base, Path(path).absolute().relative_to(base))
        raw = path.read_bytes()
        _require(_sha(raw) == pin, "source_hash_mismatch")
        _require(path not in tracked or tracked[path] == pin, "source_hash_mismatch")
        tracked[path] = pin
        key = (label, path.relative_to(base).as_posix())
        bindings[key] = dict(root=label, path=key[1], sha256=pin)
        return raw

    def document(path, pin, label="ARTIFACT"):
        return _decode(read(path, pin, label))

    def archive(pins, source_root, expected):
        _require(set(pins) == set(expected))
        for name, pin in pins.items():
            read(_path(source_root, name), pin, "ARTIFACT")

    def market_document(binding, prefix):
        path = _path(market, binding["market_relative_path"])
        _require(path.is_relative_to(_path(market, prefix)))
        return document(path, binding["sha256"], "MARKET")

    def load_page(binding, name, pins):
        prefix = f"us_equities/kis_paper_private/cross-asset-oc/{KINDS[name]}"
        manifest = market_document(binding, prefix)
        intent = market_document(manifest["intent"], prefix)
        _require(
            manifest["kind"] == intent["kind"] == KINDS[name]
            and manifest["source_pins"] == intent["source_pins"] == pins
            and manifest["query"] == intent["query"]
        )
        q = intent["query"]
        query = KisPaperDailyQuery(q["symbol"], q["BYMD"], q["continuation"], q["exchange"], SCOPE)
        _require(
            q
            == dict(
                symbol=query.symbol,
                exchange=query.exchange,
                BYMD=query.by_date,
                continuation=query.continuation,
                MODP="0",
            )
        )
        rid = intent["request_id"]
        _require(type(rid) is str and re.fullmatch(r"[0-9a-f]{32}", rid))
        stem = Path(manifest["intent"]["market_relative_path"])
        _require(
            stem.name == rid + "-intent.json"
            and Path(binding["market_relative_path"]) == stem.with_name(rid + "-manifest.json")
            and Path(manifest["rows"]["market_relative_path"]) == stem.with_name(rid + "-rows.json")
        )
        ordinal = intent["question_ordinal"]
        stage = _page_stage(name, intent)
        _require(stage in {"probe", "history"})
        if name == "oc":
            _require(ordinal == manifest["question_ordinal"])
        if stage == "probe":
            _require(
                type(ordinal) is int
                and 1 <= ordinal <= len(QUESTIONS[name])
                and (query.symbol, query.exchange, query.by_date, query.continuation)
                == QUESTIONS[name][ordinal - 1]
            )
        else:
            _require(ordinal is None)
        records = market_document(manifest["rows"], prefix)
        rows = tuple(
            KisDailyEndpointRow(
                r["session_date"],
                r["open"],
                r["close"],
                r["provider_row_sha256"],
                tuple(r["unused_ohlcv_faults"]),
            )
            for r in records
        )
        _require([r.as_document() for r in rows] == records)
        facts = manifest["facts"]
        page = KisDailyEndpointPage(
            query,
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

    calendar = document(calendar_path, CALENDAR_PIN)
    full_dates = tuple(calendar["session_dates"])
    _require(
        calendar["kind"] == "caller_nyse_session_dates_v1"
        and calendar["calendar_attestation"] == "caller_predeclared_full_scope_nyse_sessions"
        and calendar["start"] == "2007-08-21"
        and calendar["end"] == END
        and len(full_dates) == 4813
        and full_dates == tuple(sorted(set(full_dates)))
        and full_dates[0] == "2007-08-21"
        and full_dates[-1] == END
        and all(date.fromisoformat(d).isoformat() == d for d in full_dates),
        "calendar_invalid",
    )
    expected = {n: tuple(d for d in full_dates if a <= d <= b) for n, (a, b) in WINDOWS.items()}
    _require(all(len(expected[n]) == COUNTS[n] for n in expected), "calendar_invalid")
    full_set, source_facts = set(full_dates), {}

    def accept(symbol, venue, day, opening, close, chunk_id, warning=()):
        old = values[symbol].get(day)
        _require(old is None or old[:2] == (opening, close), "oc_overlap_conflict")
        values[symbol].setdefault(day, (opening, close, venue, chunk_id))
        witnesses.setdefault(f"{symbol}/{day}", []).append(chunk_id)
        if warning:
            faults[f"{symbol}/{day}"] = sorted(
                set(faults.get(f"{symbol}/{day}", ())) | set(warning)
            )

    for name in ("oc", "older", "bridge"):
        ref = references[name]
        receipt = document(ref.path, INPUT_PINS[name])
        pins = receipt["source_pins"]
        extra = (
            ()
            if name == "oc"
            else (
                "scripts/acquire_kis_tlt_"
                + ("oc_history_recovery" if name == "older" else "venue_bridge")
                + ".py",
            )
        )
        archive(pins, ref.source_root, (*OC_SOURCES, *extra))
        contract = document(Path(ref.path).parent / "contract.json", receipt["contract_sha256"])
        _require(
            receipt["kind"] == contract["kind"] == KINDS[name]
            and receipt["source_reattestation"] == "matched"
            and contract["source_pins"] == pins
            and receipt["pending_projection"] == "verified"
            and receipt["source_bodies_retained"] is False
            and receipt["strict_ohlcv_grade"] is False
            and receipt["qualification"] == "not_claimed"
            and receipt["status"] in {"partial", "scope_terminal", "recovered"}
        )
        catalog = receipt["catalog"]
        _require(
            catalog["status"] == "matched"
            and catalog["immutable_artifact_snapshot"] == "index.json"
        )
        index = document(Path(ref.path).parent / "index.json", catalog["sha256"])
        _require(
            index["kind"] == KINDS[name]
            and index["source_pins"] == pins
            and index["pending"] == receipt["pending"]
        )
        source_facts[name] = dict(
            receipt_sha256=INPUT_PINS[name],
            status=receipt["status"],
            coverage={},
            catalog_sha256=catalog["sha256"],
            producer_source_pins=pins,
        )
        if name == "oc":
            seed = index["seed_binding"]
            seed_path = _path(artifacts, seed["artifact_relative_path"])
            sr = document(seed_path, seed["sha256"])
            sc = document(seed_path.parent / "contract.json", sr["contract_sha256"])
            questions = [
                dict(symbol=s, exchange=v, BYMD=a, MODP="0", continuation=c)
                for s, v, a, c in QUESTIONS[name]
            ]
            _require(
                sr["source_pins"] == sc["source_pins"] == pins
                and sr["kind"] == KINDS[name]
                and sr["mode"] == sc["mode"] == "probe6"
                and sc["queries"] == questions
                and sc["maximum_GETs"] == 6
                and sc["maximum_token_POSTs"] == 1
                and sr["source_reattestation"] == "matched"
                and sr["accepted_page_count"] == len(sr["pages"]) == 6
            )
            for ordinal, b in enumerate(sr["pages"], 1):
                m, i, _ = load_page(b, name, pins)
                _require(m["question_ordinal"] == ordinal and _page_stage(name, i) == "probe")
            for symbol in ("SPY", "GLD"):
                target = index["targets"][f"{symbol}/AMS"]
                selected_seeds = []
                for b in sr["pages"]:
                    _, _, p = load_page(b, name, pins)
                    if p.query.symbol == symbol:
                        selected_seeds.append({**b, "seed": True})
                _require([b for b in target["chunks"] if b["seed"] is True] == selected_seeds)
        targets = ("SPY/AMS", "GLD/AMS") if name == "oc" else ("TLT/NAS",)
        for key in targets:
            symbol, venue = key.split("/")
            target = index["targets"][key]
            if name == "oc":
                selected, cursor, continuation = target["chunks"], "20261007", None
            else:
                ordinal = 1 if name == "older" else 4
                _require(
                    target["seed_ordinal"] == ordinal
                    and len(index["probes"]) == len(QUESTIONS[name])
                )
                for number, p in enumerate(index["probes"], 1):
                    _require(p["status"] == "accepted" and p["ordinal"] == number)
                    _, pi, _ = load_page(p["binding"], name, pins)
                    _require(pi["question_ordinal"] == number and _page_stage(name, pi) == "probe")
                probe = index["probes"][ordinal - 1]
                _require(probe["status"] == "accepted" and probe["ordinal"] == ordinal)
                selected, cursor, continuation = [probe["binding"], *target["chunks"]], None, None
            all_values, source_dates, history_seen = {}, set(), False
            for ordinal, binding in enumerate(selected):
                manifest, intent, page = load_page(binding, name, pins)
                _require((page.query.symbol, page.query.exchange) == (symbol, venue))
                if name == "oc":
                    _require(type(binding["seed"]) is bool)
                    is_seed = binding["seed"]
                    _require(not (is_seed and history_seen))
                else:
                    is_seed = ordinal == 0
                _require(_page_stage(name, intent) == ("probe" if is_seed else "history"))
                if not is_seed:
                    history_seen = True
                    _require(
                        page.query.by_date == cursor
                        and page.query.continuation == continuation
                        and (not page.rows or page.rows[0].session_date.replace("-", "") < cursor)
                    )
                if name != "oc" or not is_seed:
                    cursor = page.rows[0].session_date.replace("-", "") if page.rows else cursor
                    continuation = page.continuation
                _merge(all_values, page)
                chunk_id = f"{name}-{symbol.lower()}-{ordinal + 1:03d}"
                chunks.append(
                    dict(
                        chunk_id=chunk_id,
                        source=name,
                        symbol=symbol,
                        exchange=venue,
                        manifest=dict(
                            market_relative_path=binding["market_relative_path"],
                            sha256=binding["sha256"],
                        ),
                        observed_at_utc=_utc(manifest["observed_at_utc"]),
                        facts=page.safe_facts(),
                        provenance_kind="typed_OC_provider_row_fingerprints",
                    )
                )
                for row in page.rows:
                    source_dates.add(row.session_date)
                    if WINDOWS[name][0] <= row.session_date <= WINDOWS[name][1]:
                        _require(row.session_date in full_set, "off_calendar_source_date")
                        accept(
                            symbol,
                            venue,
                            row.session_date,
                            row.open,
                            row.close,
                            chunk_id,
                            row.unused_ohlcv_faults,
                        )
            _require(target["cursor"] == cursor and target["continuation"] == continuation)
            scoped = source_dates.intersection(expected[name])
            _require(scoped == set(expected[name]), "required_date_missing")
            declared = receipt["coverage"][key]
            declared_dates = {
                d for d in source_dates if d >= ("2007-08-21" if name != "bridge" else "2021-01-01")
            }
            _require(
                declared["unique_date_count"] == len(declared_dates)
                and declared["cursor"] == cursor
                and declared["state"] == target["state"]
            )
            _require(target["state"] in {"ready", "floor", "stopped", "empty", "unestablished"})
            excluded = {d for d in source_dates if not WINDOWS[name][0] <= d <= WINDOWS[name][1]}
            source_facts[name]["coverage"][key] = dict(
                unique_date_count=len(declared_dates),
                oldest_date=min(declared_dates),
                newest_date=max(declared_dates),
                selected_date_count=len(scoped),
                cursor=cursor,
                state=target["state"],
                excluded_overhang_date_count=len(source_dates - declared_dates),
                excluded_selector_dates=dict(
                    unique_date_count=len(excluded),
                    oldest_date=min(excluded) if excluded else None,
                    newest_date=max(excluded) if excluded else None,
                    not_in_calendar_count=len(excluded - full_set),
                ),
            )
            if target.get("failure") is not None:
                prefix = f"us_equities/kis_paper_private/cross-asset-oc/{KINDS[name]}"
                failure = market_document(target["failure"], prefix)
                fi = market_document(failure["intent"], prefix)
                _require(
                    target["state"] == "stopped"
                    and failure["status"] == "rejected"
                    and failure["reason"] == "nonadvancing_cursor"
                    and fi["query"]
                    == dict(
                        symbol=symbol,
                        exchange=venue,
                        BYMD=cursor,
                        continuation=continuation,
                        MODP="0",
                    )
                    and fi["source_pins"] == pins
                )
                source_facts[name]["retained_failure_reason"] = "nonadvancing_cursor"

    ref = strict
    original = document(ref.path, INPUT_PINS["strict"])
    archive(original["source_pins"], ref.source_root, STRICT_SOURCES)
    _require(
        original["kind"] == "kis-cross-asset-d1-price-only-input-v1"
        and original["calendar_sha256"] == CALENDAR_PIN
        and original["no_date_fill"] is True
        and original["adjustment_mode"] == "MODP0_opaque"
    )
    _require(
        all(
            code_pins[n] == original["source_pins"][n]
            for n in (
                *BASE_SOURCES,
                "scripts/acquire_kis_cross_asset_d1.py",
                "scripts/acquire_kis_cross_asset_d1_history.py",
            )
        ),
        "strict_reader_source_mismatch",
    )
    strict_status = None
    for b in original["source_bindings"]:
        _require(b["root"] in {"MARKET", "ARTIFACT"})
        base = market if b["root"] == "MARKET" else artifacts
        prefix = (
            "us_equities/kis_paper_private/cross-asset-d1/kis-cross-asset-d1-input-foundation-v1"
            if b["root"] == "MARKET"
            else ""
        )
        path = _path(base, b["path"])
        _require(
            path.is_relative_to(_path(base, prefix)) and path.name.endswith((".json", ".gz", ".py"))
        )
        if b["root"] == "ARTIFACT":
            _require(
                path == Path(calendar_path).absolute()
                or any(
                    path.is_relative_to(_path(artifacts, f"{p}/{strict_history.GOAL}"))
                    for p in ("data", "research")
                )
            )
        raw = read(path, b["sha256"], b["root"])
        if b["root"] == "ARTIFACT" and path.name == "receipt.json":
            d = _decode(raw)
            if (
                d.get("kind") == strict_history.VERSION
                and b["sha256"] == original["history_receipt_sha256"]
            ):
                _require(d["status"] in {"partial", "complete", "recovered", "unavailable"})
                strict_status = d["status"]
    _require(strict_status is not None)
    source_facts["strict"] = dict(
        input_commitment_sha256=INPUT_PINS["strict"],
        status=strict_status,
        producer_source_pins=original["source_pins"],
    )
    strict_rows = {}
    for chunk in original["chunks"]:
        if chunk["symbol"] != "TLT":
            continue
        path = _path(market, chunk["manifest_market_relative_path"])
        manifest = document(path, chunk["manifest_sha256"], "MARKET")
        raw_info = manifest["files"]["raw_daily_rows"]
        read(_path(path.parent, raw_info["path"]), chunk["raw_sha256"], "MARKET")
        snapshot = strict_history._snapshot(
            path.parent.parent, path.parent.name + "/manifest.json", ROOT
        )
        _require(
            snapshot["manifest_hash"] == chunk["manifest_sha256"]
            and snapshot["raw_sha256"] == chunk["raw_sha256"]
            and snapshot["collected_at_utc"] == chunk["observed_at_utc"]
            and chunk["exchange"] == "NAS"
            and chunk["producer_source_pins"]
            == {n: original["source_pins"][n] for n in strict_history._pins(ROOT)}
        )
        rows = csv.DictReader(
            io.StringIO(
                gzip.decompress(
                    read(_path(path.parent, raw_info["path"]), chunk["raw_sha256"], "MARKET")
                ).decode()
            )
        )
        chunk_id = "strict-" + chunk["chunk_id"]
        chunks.append(
            dict(
                chunk_id=chunk_id,
                source="strict",
                symbol="TLT",
                exchange="NAS",
                manifest=dict(
                    market_relative_path=chunk["manifest_market_relative_path"],
                    sha256=chunk["manifest_sha256"],
                ),
                observed_at_utc=_utc(chunk["observed_at_utc"]),
                provenance_kind="strict_canonical_rows_not_original_HTTP_fingerprints",
            )
        )
        for row in rows:
            d = row["session_date"]
            _require(d in expected["strict"], "off_calendar_source_date")
            old = strict_rows.get(d)
            _require(old is None or old[:2] == (row["open"], row["close"]), "oc_overlap_conflict")
            strict_rows.setdefault(d, (row["open"], row["close"], chunk_id))
    pf = original["price_only_files"]["TLT"]
    private = read(_path(market, pf["market_relative_path"]), pf["sha256"], "MARKET")
    projected = list(csv.DictReader(io.StringIO(gzip.decompress(private).decode())))
    _require(len(projected) == pf["row_count"] == 1288 and tuple(projected[0]) == COLUMNS)
    for row in projected:
        d = row["session_date"]
        _require(
            row["symbol"] == "TLT"
            and row["exchange"] == "NAS"
            and d in strict_rows
            and (row["open"], row["close"], "strict-" + row["source_chunk_id"]) == strict_rows[d]
        )
        accept("TLT", "NAS", d, row["open"], row["close"], strict_rows[d][2])
    _require(
        {r["session_date"] for r in projected} == set(expected["strict"]), "required_date_missing"
    )
    _require(all(set(v) == set(expected["oc"]) for v in values.values()), "required_date_missing")

    def reattest():
        _require(_pins() == code_pins, "reader_source_changed")
        _require(
            all(_sha(path.read_bytes()) == pin for path, pin in tracked.items()),
            "source_hash_mismatch",
        )

    output = _path(
        market, f"us_equities/kis_paper_private/cross-asset-oc/research-input/{VERSION}/{run_label}"
    )
    destination = _path(artifacts, f"research/{VERSION}/input/{run_label}/input-commitment.json")
    files, payloads = {}, {}
    for symbol, rows in values.items():
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(
            (symbol, venue, d, opening, close, cid)
            for d, (opening, close, venue, cid) in sorted(rows.items())
        )
        payload = gzip.compress(buffer.getvalue().encode(), mtime=0)
        path = output / f"{symbol.lower()}-price-only.csv.gz"
        payloads[path] = payload
        files[symbol] = dict(
            market_relative_path=path.relative_to(market).as_posix(),
            row_count=len(rows),
            sha256=_sha(payload),
            size_bytes=len(payload),
        )
    commitment = dict(
        kind=VERSION,
        run_label=run_label,
        window=dict(start=START, end=END),
        source_pins=code_pins,
        calendar_sha256=CALENDAR_PIN,
        calendar_attestation_owned_by="caller",
        selectors={
            n: dict(start=a, end=b, source_sha256=INPUT_PINS[n]) for n, (a, b) in WINDOWS.items()
        },
        expected_session_count=2686,
        price_only_files=files,
        source_facts=source_facts,
        chunks=chunks,
        source_bindings=list(bindings.values()),
        no_date_fill=True,
        adjustment_mode="MODP0_opaque",
        strict_ohlcv_grade=False,
        qualification="not_claimed",
        dated_unused_ohlcv_faults=faults,
        overlap_date_sources={d: c for d, c in witnesses.items() if len(c) > 1},
        vintage_contract="New commitment identity, distinct retained per-chunk observation times.",
        limitations=[
            "No adjusted/TR/PIT/finality/source-accuracy or historical-availability claim.",
            "NYS empty anchors do not establish provider exhaustion.",
            "Archived producer/current loader pins are distinct; no runtime-equivalence claim.",
        ],
    )
    commitment["commitment_id"] = _sha(_json(commitment))
    data = _json(commitment)
    reattest()
    if publish:
        space = space_check or (
            lambda n: private_daily_cache_would_cross_free_space_floor(
                cache_root=output, repo_root=ROOT, projected_bytes=n
            )
        )
        _require(not space(sum(len(p) for p in payloads.values()) + len(data)), "storage_floor")
        for path, payload in payloads.items():
            _write(path, payload)
        reattest()
        _write(destination, data)
        _require(all(path.read_bytes() == payload for path, payload in payloads.items()))
        _require(destination.read_bytes() == data)
    reattest()
    return dict(
        status="published" if publish else "prepared",
        read_only=not publish,
        commitment_id=commitment["commitment_id"],
        commitment_path=str(destination) if publish else None,
        commitment_sha256=_sha(data) if publish else None,
        date_count=2686,
        first_date=START,
        last_date=END,
        missing_count=0,
        qualification="not_claimed",
        source_binding_count=len(bindings),
        source_hashes_unchanged=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--market-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--calendar", dest="calendar_path", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    for name in INPUT_PINS:
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--{name}-source-root", type=Path, required=True)
    args = vars(parser.parse_args(argv))
    publish = args.pop("freeze")
    check_only = args.pop("check_only")
    try:
        _require(not (publish and check_only), "argument_invalid")
        for name in INPUT_PINS:
            args[name] = Source(args[name], args.pop(name + "_source_root"))
        result = freeze_cohort(**args, publish=publish)
    except Exception:
        result = dict(
            status="input_unavailable", reason="cohort_binding_invalid", read_only=not publish
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"prepared", "published"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
