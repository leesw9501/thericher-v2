from __future__ import annotations

import csv
import gzip
import importlib.util
import io
import json
import shutil
import socket
import sys
import urllib.request
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_daily_price_endpoints as endpoints
from thericher_v2.execution.kis_market_data import KisMarketDataResponse, KisPaperMarketDataConfig

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    SPEC = importlib.util.spec_from_file_location(
        "oc_cohort_tests", ROOT / "scripts/freeze_kis_cross_asset_oc_cohort.py"
    )
    script = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = script
    SPEC.loader.exec_module(script)
    old_freezer = importlib.import_module("freeze_kis_cross_asset_d1_input")
finally:
    sys.path.pop(0)

SECRET = "fake-secret-never-public"


def dates(a, b, count):
    start, end = date.fromisoformat(a), date.fromisoformat(b)
    all_days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    weekdays = [d.isoformat() for d in all_days if d.weekday() < 5]
    return tuple([*weekdays[: count - 1], weekdays[-1]])


def store(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = script._json(document)
    path.write_bytes(raw)
    return script._sha(raw)


def body(ds):
    return dict(
        rt_cd="0",
        output1={},
        output2=[
            dict(xymd=d.replace("-", ""), open="13.125", clos="10", high="20", low="1", tvol="9")
            for d in ds
        ],
    )


def history_pages(ds):
    position = len(ds) - 1
    while position > 0:
        first = max(0, position - 99)
        yield ds[first : position + 1]
        position = first


@pytest.fixture(scope="module")
def no_external_io():
    def forbidden(*args, **kwargs):
        raise AssertionError("external call forbidden in synthetic tests")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(urllib.request, "urlopen", forbidden)
        patch.setattr(script.strict_history, "load_kis_paper_market_data_config", forbidden)
        patch.setattr(
            script.strict_history,
            "private_daily_cache_would_cross_free_space_floor",
            lambda **kwargs: False,
        )
        patch.setattr(
            old_freezer.history,
            "private_daily_cache_would_cross_free_space_floor",
            lambda **kwargs: False,
        )
        yield


@pytest.fixture(scope="module")
def template(tmp_path_factory, no_external_io):
    base = tmp_path_factory.getbasetemp() / "z"
    market, artifacts = base / "m", base / "a"
    parts = {
        "pre": dates("2007-08-21", "2016-02-01", 2127),
        "older": dates("2016-02-02", "2020-12-31", 1239),
        "bridge": dates("2021-01-04", "2021-08-19", 159),
        "strict": dates("2021-08-20", "2026-10-07", 1288),
    }
    full = tuple(d for ds in parts.values() for d in ds)
    calendar = artifacts / "calendar.json"
    store(
        calendar,
        dict(
            kind="caller_nyse_session_dates_v1",
            calendar_attestation="caller_predeclared_full_scope_nyse_sessions",
            start="2007-08-21",
            end=script.END,
            session_dates=full,
        ),
    )
    counter = [0]

    def archive(names, label):
        root = artifacts / "archives" / label
        pins = {}
        for n in names:
            raw = (ROOT / n).read_bytes()
            p = root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            pins[n] = script._sha(raw)
        return root, pins

    def page(name, pins, symbol, venue, anchor, ds, stage="history", ordinal=None):
        counter[0] += 1
        rid = f"{counter[0]:032x}"
        prefix = f"us_equities/kis_paper_private/cross-asset-oc/{script.KINDS[name]}/attempts/{rid}"
        continuation = "F" if name == "oc" and stage == "probe" and ordinal == 1 else None
        q = dict(symbol=symbol, exchange=venue, BYMD=anchor, MODP="0", continuation=continuation)
        query = script.KisPaperDailyQuery(symbol, anchor, continuation, venue, endpoints.SCOPE)
        payload = body(ds)
        if symbol == "GLD" and "2016-02-02" in ds:
            r = next(r for r in payload["output2"] if r["xymd"] == "20160202")
            r["low"] = "12"
        typed = endpoints.parse_kis_daily_price_endpoints(
            KisMarketDataResponse.from_payload(payload), query=query
        )
        intent = dict(
            kind=script.KINDS[name],
            source_pins=pins,
            query=q,
            stage=stage,
            question_ordinal=ordinal,
            request_id=rid,
        )
        if name == "oc":
            intent.pop("stage")
        ib = dict(
            market_relative_path=prefix + "-intent.json",
            sha256=store(market / (prefix + "-intent.json"), intent),
        )
        rb = dict(
            market_relative_path=prefix + "-rows.json",
            sha256=store(market / (prefix + "-rows.json"), [r.as_document() for r in typed.rows]),
        )
        m = dict(
            kind=script.KINDS[name],
            source_pins=pins,
            query=q,
            intent=ib,
            rows=rb,
            facts=typed.safe_facts(),
            source_row_fingerprints=typed.source_row_fingerprints,
            dated_unused_ohlcv_faults={
                r.session_date: list(r.unused_ohlcv_faults)
                for r in typed.rows
                if r.unused_ohlcv_faults
            },
            observed_at_utc=(datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=counter[0]))
            .isoformat()
            .replace("+00:00", "Z"),
        )
        if name == "oc":
            m["question_ordinal"] = ordinal
        return dict(
            market_relative_path=prefix + "-manifest.json",
            sha256=store(market / (prefix + "-manifest.json"), m),
        )

    refs, receipts = {}, {}
    for name in ("oc", "older", "bridge"):
        extra = (
            ()
            if name == "oc"
            else (
                "scripts/acquire_kis_tlt_"
                + ("oc_history_recovery" if name == "older" else "venue_bridge")
                + ".py",
            )
        )
        arc, pins = archive((*script.OC_SOURCES, *extra), name)
        output = artifacts / name
        target = {}
        probes = []
        index = dict(kind=script.KINDS[name], source_pins=pins, pending=None, targets=target)
        coverage = {}
        if name == "oc":
            seeds = []
            questions = (
                ("GLD", "AMS", "20210820"),
                ("TLT", "NAS", "20151231"),
                ("TLT", "AMS", "20151231"),
                ("TLT", "AMS", "20071231"),
                ("GLD", "AMS", "20071231"),
                ("SPY", "AMS", "20071231"),
            )
            for ordinal, (s, v, a) in enumerate(questions, 1):
                ds = tuple(d for d in full if d.replace("-", "") <= a)[-100:] if s != "TLT" else ()
                seeds.append(page(name, pins, s, v, a, ds, "probe", ordinal))
            seed_path = artifacts / "oc-seed" / "receipt.json"
            seed_contract = store(
                seed_path.parent / "contract.json",
                dict(
                    source_pins=pins,
                    mode="probe6",
                    queries=[
                        dict(symbol=s, exchange=v, BYMD=a, MODP="0", continuation=c)
                        for s, v, a, c in script.QUESTIONS["oc"]
                    ],
                    maximum_GETs=6,
                    maximum_token_POSTs=1,
                ),
            )
            seed_pin = store(
                seed_path,
                dict(
                    kind=script.KINDS[name],
                    source_pins=pins,
                    mode="probe6",
                    source_reattestation="matched",
                    contract_sha256=seed_contract,
                    pages=seeds,
                    accepted_page_count=6,
                ),
            )
            index["seed_binding"] = dict(
                artifact_relative_path=seed_path.relative_to(artifacts).as_posix(), sha256=seed_pin
            )
            for s in ("SPY", "GLD"):
                chunks = []
                for b in seeds:
                    m = json.loads((market / b["market_relative_path"]).read_bytes())
                    if m["query"]["symbol"] == s:
                        chunks.append({**b, "seed": True})
                cursor = "20261007"
                for ds in history_pages(full):
                    b = page(name, pins, s, "AMS", cursor, ds)
                    chunks.append({**b, "seed": False})
                    cursor = ds[0].replace("-", "")
                target[s + "/AMS"] = dict(
                    cursor=cursor, continuation=None, state="floor", chunks=chunks
                )
                coverage[s + "/AMS"] = dict(unique_date_count=4813, cursor=cursor, state="floor")
        else:
            questions = (
                (
                    ("NAS", "20201231"),
                    ("AMS", "20201231"),
                    ("NAS", "20151231"),
                    ("AMS", "20151231"),
                    ("NAS", "20101231"),
                    ("AMS", "20101231"),
                )
                if name == "older"
                else (
                    ("NYS", "20160201"),
                    ("NYS", "20101231"),
                    ("NYS", "20071231"),
                    ("NAS", "20210819"),
                )
            )
            seed_ordinal = 1 if name == "older" else 4
            seed_ds = parts[name][-100:]
            for ordinal, (v, a) in enumerate(questions, 1):
                b = page(
                    name,
                    pins,
                    "TLT",
                    v,
                    a,
                    seed_ds if ordinal == seed_ordinal else (),
                    "probe",
                    ordinal,
                )
                probes.append(dict(ordinal=ordinal, status="accepted", binding=b))
            index["probes"] = probes
            cursor = seed_ds[0].replace("-", "")
            chunks = []
            all_pages = (
                list(history_pages(parts[name]))[1:]
                if name == "older"
                else ((*parts["older"][-40:], *parts["bridge"][:60]),)
            )
            for ds in all_pages:
                chunks.append(page(name, pins, "TLT", "NAS", cursor, ds))
                cursor = ds[0].replace("-", "")
            failure = None
            if name == "older":
                rid = uuid.uuid4().hex
                prefix = (
                    f"us_equities/kis_paper_private/cross-asset-oc/{script.KINDS[name]}"
                    f"/attempts/{rid}"
                )
                intent = dict(
                    source_pins=pins,
                    query=dict(
                        symbol="TLT", exchange="NAS", BYMD=cursor, continuation=None, MODP="0"
                    ),
                )
                ib = dict(
                    market_relative_path=prefix + "-intent.json",
                    sha256=store(market / (prefix + "-intent.json"), intent),
                )
                failure = dict(
                    market_relative_path=prefix + "-failure.json",
                    sha256=store(
                        market / (prefix + "-failure.json"),
                        dict(status="rejected", reason="nonadvancing_cursor", intent=ib),
                    ),
                )
            state = "stopped" if name == "older" else "floor"
            target["TLT/NAS"] = dict(
                seed_ordinal=seed_ordinal,
                cursor=cursor,
                continuation=None,
                state=state,
                chunks=chunks,
                failure=failure,
            )
            coverage["TLT/NAS"] = dict(
                unique_date_count=script.COUNTS[name], cursor=cursor, state=state
            )
        index_pin = store(output / "index.json", index)
        contract_pin = store(
            output / "contract.json", dict(kind=script.KINDS[name], source_pins=pins)
        )
        receipts[name] = dict(
            kind=script.KINDS[name],
            source_pins=pins,
            source_reattestation="matched",
            pending_projection="verified",
            source_bodies_retained=False,
            strict_ohlcv_grade=False,
            qualification="not_claimed",
            status="partial" if name != "bridge" else "scope_terminal",
            pending=None,
            contract_sha256=contract_pin,
            coverage=coverage,
            catalog=dict(
                status="matched", immutable_artifact_snapshot="index.json", sha256=index_pin
            ),
        )
        store(output / "receipt.json", receipts[name])
        refs[name] = script.Source(output / "receipt.json", arc)

    # Exercise the real canonical writer/readback using an entirely mocked transport.
    seconds = [0.0]

    def clock():
        return datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=seconds[0])

    class Transport:
        def request(self, request):
            seconds[0] += 1
            if request.method == "POST":
                return KisMarketDataResponse.from_payload(dict(access_token="fake-token"))
            ds = tuple(d for d in parts["strict"] if d.replace("-", "") <= request.query["BYMD"])[
                -100:
            ]
            return KisMarketDataResponse.from_payload(body(ds))

    outcome = script.strict_history.run_history(
        market_root=market,
        artifact_root=artifacts,
        repository_root=ROOT,
        run_label="strict-fixture",
        dotenv_path=base / "never-read.env",
        maximum_get_pages=64,
        transport_factory=lambda **kw: Transport(),
        config_loader=lambda _: KisPaperMarketDataConfig("fake-key", "fake-secret"),
        space_check=lambda _: False,
        clock=clock,
        monotonic=lambda: seconds[0],
    )
    strict_input = old_freezer.freeze_input(
        history_receipt=Path(outcome["receipt_path"]),
        history_sha256=outcome["receipt_sha256"],
        calendar_path=calendar,
        calendar_sha256=script._sha(calendar.read_bytes()),
        market_root=market,
        artifact_root=artifacts,
        repository_root=ROOT,
        run_label="strict-input",
    )
    assert strict_input["status"] == "available"
    arc, _ = archive(script.STRICT_SOURCES, "strict")
    refs["strict"] = script.Source(Path(strict_input["commitment_path"]), arc)
    return SimpleNamespace(
        base=base,
        market=market,
        artifacts=artifacts,
        calendar=calendar,
        refs=refs,
        parts=parts,
        serial=[0],
    )


@pytest.fixture
def f(template, tmp_path_factory, monkeypatch):
    template.serial[0] += 1
    base = tmp_path_factory.getbasetemp() / f"{template.serial[0]:02d}"
    shutil.copytree(template.base, base)
    m, a = base / "m", base / "a"
    refs = {
        n: script.Source(
            a / r.path.relative_to(template.artifacts),
            a / r.source_root.relative_to(template.artifacts),
        )
        for n, r in template.refs.items()
    }
    calendar = a / template.calendar.relative_to(template.artifacts)
    monkeypatch.setattr(
        script, "INPUT_PINS", {n: script._sha(r.path.read_bytes()) for n, r in refs.items()}
    )
    monkeypatch.setattr(script, "CALENDAR_PIN", script._sha(calendar.read_bytes()))
    return SimpleNamespace(
        market=m,
        artifacts=a,
        refs=refs,
        calendar=calendar,
        kwargs=dict(
            market_root=m, artifact_root=a, calendar_path=calendar, **refs, run_label="new"
        ),
    )


def repin(f, name, doc):
    store(f.refs[name].path, doc)
    script.INPUT_PINS[name] = script._sha(f.refs[name].path.read_bytes())


def test_default_read_only_exact_geometry_no_snapshot_writes(f):
    before = {p: p.read_bytes() for p in f.market.rglob("*") if p.is_file()}
    result = script.freeze_cohort(**f.kwargs)
    assert result["status"] == "prepared" and result["date_count"] == 2686
    assert result["read_only"] and result["commitment_path"] is None
    assert not (
        f.market / f"us_equities/kis_paper_private/cross-asset-oc/research-input/{script.VERSION}"
    ).exists()
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_new_identity_price_only_all_dates_partial_vintages_and_overhang(f):
    old_bytes = f.refs["strict"].path.read_bytes()
    result = script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    c = json.loads(Path(result["commitment_path"]).read_bytes())
    assert (
        result["status"] == "published"
        and c["commitment_id"] != json.loads(old_bytes)["commitment_id"]
    )
    assert f.refs["strict"].path.read_bytes() == old_bytes
    assert c["source_facts"]["older"]["status"] == "partial"
    assert c["source_facts"]["older"]["retained_failure_reason"] == "nonadvancing_cursor"
    assert c["source_facts"]["strict"]["status"] == "partial"
    assert c["source_facts"]["bridge"]["coverage"]["TLT/NAS"]["excluded_overhang_date_count"] == 40
    assert c["dated_unused_ohlcv_faults"]["GLD/2016-02-02"] == ["low_above_open_close"]
    assert len({x["observed_at_utc"] for x in c["chunks"]}) > 1
    assert c["adjustment_mode"] == "MODP0_opaque" and c["qualification"] == "not_claimed"
    assert "13.125" not in json.dumps(c) and "13.125" not in json.dumps(result)
    for symbol in ("SPY", "TLT", "GLD"):
        info = c["price_only_files"][symbol]
        raw = (f.market / info["market_relative_path"]).read_bytes()
        assert script._sha(raw) == info["sha256"]
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode())))
        assert len(rows) == 2686 and tuple(rows[0]) == script.COLUMNS
        assert rows[0]["session_date"] == script.START and rows[-1]["session_date"] == script.END
        if symbol == "TLT":
            assert sum(r["source_chunk_id"].startswith("bridge-") for r in rows) == 159
            assert sum(r["source_chunk_id"].startswith("older-") for r in rows) == 1239
            assert sum(r["source_chunk_id"].startswith("strict-") for r in rows) == 1288


@pytest.mark.parametrize("name", ("oc", "older", "bridge", "strict"))
def test_exact_receipt_byte_mutation_rejected(f, name):
    f.refs[name].path.write_bytes(f.refs[name].path.read_bytes() + b" ")
    with pytest.raises(script.CohortError, match="source_hash_mismatch"):
        script.freeze_cohort(**f.kwargs)


def test_archive_pin_distinct_from_import_and_mutation_rejected(f):
    path = f.refs["oc"].source_root / "src/thericher_v2/data/kis_daily_price_endpoints.py"
    path.write_bytes(path.read_bytes() + b"# changed")
    with pytest.raises(script.CohortError, match="source_hash_mismatch"):
        script.freeze_cohort(**f.kwargs)


def test_mutated_calendar_is_not_repaired(f):
    doc = json.loads(f.calendar.read_bytes())
    doc["session_dates"].remove("2021-01-04")
    store(f.calendar, doc)
    script.CALENDAR_PIN = script._sha(f.calendar.read_bytes())
    with pytest.raises(script.CohortError, match="calendar_invalid"):
        script.freeze_cohort(**f.kwargs)


def test_mutable_live_catalog_is_not_an_input_selector(f):
    for name in ("oc", "older", "bridge"):
        root = f.market / f"us_equities/kis_paper_private/cross-asset-oc/{script.KINDS[name]}"
        (root / "index.json").write_bytes(b"unrelated-new-frontier")
    assert script.freeze_cohort(**f.kwargs)["status"] == "prepared"


def test_storage_floor_before_new_output_and_originals_unchanged(f):
    with pytest.raises(script.CohortError, match="storage_floor"):
        script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: True)
    assert not (f.artifacts / f"research/{script.VERSION}").exists()


def test_repeat_publication_identical_bytes_no_overwrite(f):
    first = script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    path = Path(first["commitment_path"])
    before = path.read_bytes()
    second = script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    assert second == first and path.read_bytes() == before


def test_final_reattestation_blocks_publication(f, monkeypatch):
    pins = script._pins()
    calls = [0]

    def changed():
        calls[0] += 1
        return pins if calls[0] == 1 else {**pins, "changed": "sha256:" + "0" * 64}

    monkeypatch.setattr(script, "_pins", changed)
    with pytest.raises(script.CohortError, match="reader_source_changed"):
        script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    assert not (f.artifacts / f"research/{script.VERSION}").exists()


def test_cli_no_secret_exception_and_check_only_default(monkeypatch, capsys):
    observed = []

    def fail(**kwargs):
        observed.append(kwargs["publish"])
        raise OSError(SECRET)

    monkeypatch.setattr(script, "freeze_cohort", fail)
    args = ["--calendar", "calendar", "--run-label", "x"]
    for name in script.INPUT_PINS:
        args += [f"--{name}", name, f"--{name}-source-root", name + "-archive"]
    assert script.main(args) == 20
    assert observed == [False] and SECRET not in capsys.readouterr().out


def change_page(f, name, key, position, edit):
    receipt = json.loads(f.refs[name].path.read_bytes())
    index_path = f.refs[name].path.parent / "index.json"
    index = json.loads(index_path.read_bytes())
    binding = index["targets"][key]["chunks"][position]
    manifest_path = f.market / binding["market_relative_path"]
    manifest = json.loads(manifest_path.read_bytes())
    row_path = f.market / manifest["rows"]["market_relative_path"]
    records = json.loads(row_path.read_bytes())
    edit(records)
    q = manifest["query"]
    query = script.KisPaperDailyQuery(
        q["symbol"], q["BYMD"], q["continuation"], q["exchange"], endpoints.SCOPE
    )
    payload = body([r["session_date"] for r in records])
    for raw, record in zip(payload["output2"], records, strict=True):
        raw["open"], raw["clos"] = record["open"], record["close"]
    page = endpoints.parse_kis_daily_price_endpoints(
        KisMarketDataResponse.from_payload(payload), query=query
    )
    manifest["rows"]["sha256"] = store(row_path, [r.as_document() for r in page.rows])
    manifest.update(
        facts=page.safe_facts(),
        source_row_fingerprints=page.source_row_fingerprints,
        dated_unused_ohlcv_faults={
            r.session_date: list(r.unused_ohlcv_faults) for r in page.rows if r.unused_ohlcv_faults
        },
    )
    binding["sha256"] = store(manifest_path, manifest)
    receipt["catalog"]["sha256"] = store(index_path, index)
    repin(f, name, receipt)


@pytest.mark.parametrize(
    "name,key,position,row", (("oc", "SPY/AMS", 1, 50), ("bridge", "TLT/NAS", 0, 51))
)
def test_hash_consistent_required_gap_rejects_no_imputation(f, name, key, position, row):
    change_page(f, name, key, position, lambda rows: rows.pop(row))
    with pytest.raises(script.CohortError, match="required_date_missing"):
        script.freeze_cohort(**f.kwargs)


def test_real_producer_ordinal_locations(f):
    for name in ("oc", "older", "bridge"):
        index = json.loads((f.refs[name].path.parent / "index.json").read_bytes())
        if name == "oc":
            binding = index["targets"]["SPY/AMS"]["chunks"][0]
        else:
            binding = index["probes"][0]["binding"]
        manifest = json.loads((f.market / binding["market_relative_path"]).read_bytes())
        intent = json.loads((f.market / manifest["intent"]["market_relative_path"]).read_bytes())
        assert "question_ordinal" in intent
        assert ("question_ordinal" in manifest) == (name == "oc")
    assert script.freeze_cohort(**f.kwargs)["status"] == "prepared"


@pytest.mark.parametrize("name,key,position", (("oc", "SPY/AMS", -1), ("bridge", "TLT/NAS", 0)))
def test_precalendar_unselected_overhang_excluded_with_bound_witness(f, name, key, position):
    def outside(rows):
        rows[0]["session_date"] = "2007-08-20"

    change_page(f, name, key, position, outside)
    receipt = json.loads(f.refs[name].path.read_bytes())
    index_path = f.refs[name].path.parent / "index.json"
    index = json.loads(index_path.read_bytes())
    index["targets"][key]["cursor"] = "20070820"
    receipt["coverage"][key]["cursor"] = "20070820"
    receipt["catalog"]["sha256"] = store(index_path, index)
    repin(f, name, receipt)
    result = script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    commitment = json.loads(Path(result["commitment_path"]).read_bytes())
    witness = commitment["source_facts"][name]["coverage"][key]["excluded_selector_dates"]
    assert witness["oldest_date"] == "2007-08-20" and witness["not_in_calendar_count"] == 1
    assert witness["unique_date_count"] == (2128 if name == "oc" else 40)
    assert result["date_count"] == 2686 and result["missing_count"] == 0
    symbol = key.split("/")[0]
    price_path = f.market / commitment["price_only_files"][symbol]["market_relative_path"]
    assert "2007-08-20" not in gzip.decompress(price_path.read_bytes()).decode()


def test_hash_consistent_overlap_conflict_rejects_not_latest_wins(f):
    def conflict(rows):
        rows[-1]["close"] = "12"

    change_page(f, "oc", "SPY/AMS", 2, conflict)
    with pytest.raises(RuntimeError, match="oc_overlap_conflict"):
        script.freeze_cohort(**f.kwargs)


@pytest.mark.parametrize("name", ("oc", "strict"))
def test_bound_row_bytes_mutation_rejects(f, name):
    source = json.loads(f.refs[name].path.read_bytes())
    if name == "oc":
        index = json.loads((f.refs[name].path.parent / "index.json").read_bytes())
        binding = index["targets"]["SPY/AMS"]["chunks"][1]
        manifest = json.loads((f.market / binding["market_relative_path"]).read_bytes())
        path = f.market / manifest["rows"]["market_relative_path"]
    else:
        path = f.market / source["price_only_files"]["TLT"]["market_relative_path"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(script.CohortError, match="source_hash_mismatch"):
        script.freeze_cohort(**f.kwargs)


def test_partial_publication_exact_orphan_reattach_without_rewrite(f, monkeypatch):
    original = script._write
    first = []

    def fail_second(path, raw):
        if first:
            raise OSError(SECRET)
        original(path, raw)
        first.append((path, raw, path.stat().st_mtime_ns))

    monkeypatch.setattr(script, "_write", fail_second)
    with pytest.raises(OSError):
        script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    assert not (f.artifacts / f"research/{script.VERSION}").exists()
    monkeypatch.setattr(script, "_write", original)
    assert (
        script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)["status"]
        == "published"
    )
    path, raw, mtime = first[0]
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == mtime


def test_arbitrary_receipt_metadata_not_copied_to_output(f):
    receipt = json.loads(f.refs["oc"].path.read_bytes())
    receipt["coverage"]["SPY/AMS"]["ignored"] = SECRET
    repin(f, "oc", receipt)
    result = script.freeze_cohort(**f.kwargs, publish=True, space_check=lambda _: False)
    assert SECRET not in Path(result["commitment_path"]).read_text()


@pytest.mark.parametrize("raw", (b'{"x":1,"x":2}', b'{"x":NaN}'))
def test_duplicate_json_and_nonfinite_marker_reject(raw):
    with pytest.raises(script.CohortError):
        script._decode(raw)
