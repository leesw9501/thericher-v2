from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.dashboard import operations as ops
from thericher_v2.dashboard.view import build_snapshot, render_dashboard
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.state.event_log import EventStore

NOW = datetime(2026, 11, 2, 21, 6, tzinfo=UTC)


def write(path: Path, value: object) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def unit_outcome() -> dict:
    return {
        "schema": "US19_UNIT_OFFLINE_OUTCOME_V1",
        "reason": "OK",
        "no_intent": "NO",
        "attempt": "RECORDED",
        "acceptance": "ACKNOWLEDGED",
        "exact_fill": "FULL",
        "current_local_owned": "POSITIVE",
        "terminal": "YES",
        "pending": "NO",
        "intent_count": 1,
        "exact_fill_count": 1,
        "current_local_owned_count": 1,
        "host_runtime_chain": "UNKNOWN",
        "broker_holdings": "NOT_READ",
        "fees": "UNKNOWN",
        "settlement": "UNKNOWN",
        "net_PnL": "UNKNOWN",
        "reservation_released": False,
        "broker_calls": 0,
        "private_writes": 0,
    }


def h20_outcome() -> dict:
    return {
        "schema": "H20_EXACT_OFFLINE_OUTCOME_V1",
        "attempt": "RECORDED",
        "acceptance": "ACKNOWLEDGED",
        "fill": "FULL",
        "current_owned_inventory": "POSITIVE",
        "terminal": "YES",
        "reservation_released": False,
        "broker_holdings": "NOT_READ",
        "net_PnL": "UNKNOWN",
        "raw_exception_retained": False,
    }


@pytest.fixture(params=["h20", "googl"])
def graph(tmp_path, monkeypatch, request):
    """Invented public producer envelope through real isolated parse-and-return."""
    run = next(run for run in ops._RUNS if run.key == request.param)
    root = tmp_path / "artifacts"
    producer = root / "execution" / run.producer
    reader_root = root / "execution" / run.reader_root
    reader_root.mkdir(parents=True, exist_ok=True)
    producer.mkdir(parents=True, exist_ok=True)
    reader = reader_root / "read_outcome.py"
    # No mocked intake: the host executes this bounded source-format consumer.
    reader.write_text(
        "import hashlib,json,sys\nfrom pathlib import Path\n"
        f"root=Path({str(producer)!r})\n"
        f"h20={run.key == 'h20'!r}\n"
        "p=root/'actual-once/RESULT.json'\n"
        "if not p.exists():\n"
        " out={'status':'UNKNOWN_NO_COMPLETE_OUTCOME','financial_result':'UNKNOWN'} if h20 else "
        "json.loads((root/'unknown.json').read_bytes())\n"
        "else:\n"
        " raw=p.read_bytes(); e=json.loads(raw); v=e['result']\n"
        " out=dict(status='VALIDATED_CURRENT_RETAINED_STATE',evidence="
        "dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest()),"
        "observed_utc=e.get('observed_utc'),**{k:v[k] for k in "
        "('attempt','acceptance','fill','current_owned_inventory','terminal')}) if h20 else v\n"
        "print(json.dumps(out))\n",
        encoding="ascii",
    )
    native = write(producer / "NATIVE.json", {"status": "PASS"})
    binding = {}
    for name in ("installed_host", "release", "plan", "contract", "reader_source"):
        binding[name] = write(producer / f"{name}.json", {"invented_public_source": name})
    binding.update(input_ref="sha256:" + "a" * 64, policy_ref="sha256:" + "b" * 64)
    binding_ref = write(producer / "BINDING.json", binding)
    reader_ref = {"path": str(reader), "sha256": hashlib.sha256(reader.read_bytes()).hexdigest()}
    source = write(producer / "SOURCE.json", {"pins": [binding_ref, native, reader_ref]})
    if run.key == "h20":
        manifest = write(reader_root / "READER-SOURCE.json", {"pins": [reader_ref]})
        monkeypatch.setattr(ops, "_H20_READER_MANIFEST", manifest["sha256"])
    run = replace(
        run, source=source["sha256"], native=native["sha256"], reader=reader_ref["sha256"]
    )
    monkeypatch.setattr(ops, "HOST_ARTIFACT_ROOT", root)
    monkeypatch.setattr(ops, "_RUNS", (run,))
    unknown = unit_outcome()
    unknown.update(
        reason="MISSING_OR_UNBOUND", no_intent="UNKNOWN", terminal="UNKNOWN", pending="UNKNOWN"
    )
    for key in ("attempt", "acceptance", "exact_fill", "current_local_owned"):
        unknown[key] = "UNKNOWN"
    for key in ("intent_count", "exact_fill_count", "current_local_owned_count"):
        unknown[key] = None
    write(producer / "unknown.json", unknown)
    admissions = []
    for phase in ops._PHASES:
        verdict = write(
            producer / f"actual-once/CAPABILITY-{phase}.json",
            {
                "status": "NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED",
            },
        )
        admissions.append({"phase": phase, "verdict": verdict, "actual_caller": {"invented": True}})
    closed = write(
        producer / "actual-once/CLOSED.json",
        {
            "status": "PASS",
            "CID_absent": True,
            "admissions": admissions,
            "Jobs": [{"exit": 0, "active": 0, "closed": True}],
        },
    )
    evidence_at = NOW if run.key == "googl" else NOW.replace(hour=15, minute=36)
    value = {
        "source_sha256": run.source,
        "native_proof_sha256": run.native,
        "schema": "US19_UNIT_OUTCOME_RECEIPT_V1",
        "historical_scheduler_origin": "UNKNOWN",
        "broker_calls": 0,
        "private_writes": 0,
        "reservation_released": False,
        "current_read_not_historical_OS_origin": True,
        "fees_settlement_netPnL": "NOT_OBSERVED",
        "input_ref": binding["input_ref"],
        "policy_ref": binding["policy_ref"],
        "observed_at": ops._iso(evidence_at),
        "observed_utc": ops._iso(evidence_at),
        "admissions": admissions,
        "closure": closed,
        "result": h20_outcome() if run.key == "h20" else unit_outcome(),
    }
    value.update(binding)
    value["H20_source"] = binding["installed_host"]
    result = producer / "actual-once/RESULT.json"
    write(result, value)
    return run, producer, result, value, evidence_at


def test_no_configuration_does_no_io_or_inference(monkeypatch):
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("unexpected I/O"))
    snapshot = ops.build_operations_snapshot(None, now=NOW)
    assert snapshot["observed_at"] == "2026-11-02T21:06:00Z"
    assert [row["key"] for row in snapshot["runs"]] == ["h20", "googl", "h3"]
    for row in snapshot["runs"]:
        assert row["status"] == "unknown"
        assert all(row[key] == "unknown" for key in ops._FINANCIAL)
        assert row["evidence_at"] is row["evidence_pointer"] is None


def test_exact_schedule_exposes_native_times_not_early_task_triggers():
    h20, googl, h3 = ops.build_operations_snapshot(None, now=NOW)["runs"]
    assert (h20["entry_due_at"], h20["read_due_at"], h20["exit_due_at"]) == (
        "2026-11-02T15:15:00Z",
        "2026-11-02T15:35:00Z",
        "2026-12-01T14:30:00Z",
    )
    assert (googl["entry_due_at"], googl["read_due_at"], googl["exit_due_at"]) == (
        "2026-11-02T20:55:00Z",
        "2026-11-02T21:05:00Z",
        "2026-11-09T20:55:00Z",
    )
    assert (h3["entry_due_at"], h3["read_due_at"], h3["exit_due_at"]) == (
        "2026-11-03T20:55:00Z",
        None,
        "2026-11-06T20:45:00Z",
    )


def test_missing_does_not_scan_latest_or_read_host_files(tmp_path, monkeypatch):
    write(tmp_path / "latest.json", {"fill": "FULL", "account": "private-marker"})
    monkeypatch.setattr(ops, "_invoke_public_reader", lambda *a: pytest.fail("web execution"))
    rows = ops.build_operations_snapshot(tmp_path, now=NOW)["runs"]
    assert all(row["reason_code"] == "projection_missing" for row in rows)
    assert all(row["inventory"] == "unknown" for row in rows)


def test_real_public_format_parse_return_then_projection(graph, tmp_path):
    run, _, _, _, when = graph
    projection = ops._collect_public_projection(run, when)
    assert projection["status"] == "validated"
    assert projection["submit"] == "accepted" and projection["fill"] == "confirmed"
    assert (
        projection["inventory"] == "owned"
        and projection["evidence_pointer"] == run.evidence_pointer
    )
    assert projection["trust"] == "host_published_public_outcome_not_authenticated"
    path = tmp_path / "public" / f"{run.key}.json"
    write(path, projection)
    row = ops.build_operations_snapshot(path.parent, now=when)["runs"][0]
    assert row["reason_code"] == "host_published_public_outcome"
    assert row["status"] == "validated" and row["fill"] == "confirmed"
    assert set(row) == {
        "key",
        "label",
        "symbol",
        "entry_due_at",
        "read_due_at",
        "exit_due_at",
        "status",
        "submit",
        "fill",
        "inventory",
        "reason_code",
        "evidence_at",
        "evidence_pointer",
    }


def test_missing_result_is_unknown_without_private_read(graph):
    run, _, path, _, when = graph
    path.unlink()
    projection = ops._collect_public_projection(run, when)
    assert projection["status"] == "unknown"
    assert projection["reason_code"] == "public_evidence_missing"
    assert projection["evidence_at"] is None
    assert all(projection[key] == "unknown" for key in ops._FINANCIAL)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_source",
        "wrong_native",
        "wrong_cohort",
        "unbound_fill",
        "missing_binding",
        "tampered_link",
        "missing_admission",
        "writer_present",
        "open_container",
        "failed_job",
        "empty_jobs",
        "private_effect",
        "partial_envelope",
        "wrong_category",
        "invalid_timestamp",
    ],
)
def test_forged_partial_or_unbound_evidence_never_claims_financials(graph, fault):
    run, producer, path, value, when = graph
    if fault == "wrong_source":
        value["source_sha256"] = "0" * 64
    elif fault == "wrong_native":
        if run.key == "h20":
            (producer / "NATIVE.json").write_bytes(b"tampered")
        else:
            value["native_proof_sha256"] = "0" * 64
    elif fault == "wrong_cohort":
        value["H20_source" if run.key == "h20" else "installed_host"] = value["release"]
    elif fault == "unbound_fill":
        value["result"]["attempt"] = "UNKNOWN"
    elif fault == "missing_binding":
        del value["contract"]
    elif fault == "tampered_link":
        value["closure"]["sha256"] = "0" * 64
    elif fault in {
        "missing_admission",
        "writer_present",
        "open_container",
        "failed_job",
        "empty_jobs",
    }:
        closure_path = producer / "actual-once/CLOSED.json"
        closed = json.loads(closure_path.read_bytes())
        if fault == "missing_admission":
            closed["admissions"].pop()
        elif fault == "writer_present":
            verdict = closed["admissions"][0]["verdict"]
            closed["admissions"][0]["verdict"] = write(
                Path(verdict["path"]), {"status": "WITHHELD"}
            )
        elif fault == "open_container":
            closed["CID_absent"] = False
        elif fault == "failed_job":
            closed["Jobs"][0]["exit"] = 20
        else:
            closed["Jobs"] = []
        value["closure"] = write(closure_path, closed)
        value["admissions"] = closed["admissions"]
    elif fault == "private_effect":
        value["broker_calls"] = 1
    elif fault == "partial_envelope":
        del value["result"][
            "current_owned_inventory" if run.key == "h20" else "current_local_owned"
        ]
    elif fault == "wrong_category":
        value["result"]["fill" if run.key == "h20" else "exact_fill"] = "private-marker"
    else:
        value["observed_utc" if run.key == "h20" else "observed_at"] = "2026-11-02T00:00:00"
    write(path, value)
    projection = ops._collect_public_projection(run, when)
    assert projection["status"] == "invalid"
    assert all(projection[key] == "unknown" for key in ops._FINANCIAL)
    assert "private-marker" not in json.dumps(projection)


def test_source_tamper_denies_before_external_execution(graph, monkeypatch):
    run, producer, _, _, when = graph
    (producer / "BINDING.json").write_bytes(b"{}")
    monkeypatch.setattr(
        ops, "_invoke_public_reader", lambda *a: pytest.fail("tampered source executed")
    )
    assert ops._collect_public_projection(run, when)["status"] == "invalid"


def test_result_changed_during_consumer_is_withheld(graph, monkeypatch):
    run, _, path, value, when = graph
    invoke = ops._invoke_public_reader

    def mutate(*args):
        raw = invoke(*args)
        value["extra"] = "not-public"
        write(path, value)
        return raw

    monkeypatch.setattr(ops, "_invoke_public_reader", mutate)
    projection = ops._collect_public_projection(run, when)
    assert projection["status"] == "invalid" and projection["fill"] == "unknown"


def test_no_durable_duty_is_not_no_intent_or_flat(graph):
    run, _, path, value, when = graph
    if run.key == "h20":
        for key in ("attempt", "acceptance", "fill", "current_owned_inventory", "terminal"):
            value["result"][key] = "UNKNOWN"
    else:
        result = value["result"]
        result.update(
            reason="NO_ENTRY_PLAN",
            no_intent="UNKNOWN",
            intent_count=0,
            exact_fill_count=None,
            current_local_owned_count=None,
        )
        for key in (
            "attempt",
            "acceptance",
            "exact_fill",
            "current_local_owned",
            "terminal",
            "pending",
        ):
            result[key] = "UNKNOWN"
    write(path, value)
    projection = ops._collect_public_projection(run, when)
    assert all(projection[key] == "unknown" for key in ops._FINANCIAL)
    assert projection["status"] == ("validated" if run.key == "h20" else "unknown")


@pytest.mark.parametrize(
    "fault",
    [
        "extra_price",
        "extra_identifier",
        "wrong_key",
        "wrong_reader",
        "wrong_source",
        "wrong_native",
        "wrong_pointer",
        "not_authenticated_qualifier",
        "missing_result_hash",
        "future_evidence",
        "naive_evidence",
        "pre_read_evidence",
        "unknown_success",
        "owned_without_fill",
    ],
)
def test_projection_requires_exact_bounded_qualified_source(graph, tmp_path, fault):
    run, _, _, _, when = graph
    projection = ops._collect_public_projection(run, when)
    if fault.startswith("extra_"):
        projection[fault] = "private-marker"
    elif fault == "wrong_key":
        projection["key"] = "foreign"
    elif fault in {"wrong_reader", "wrong_source", "wrong_native"}:
        projection[fault.removeprefix("wrong_") + "_sha256"] = "0" * 64
    elif fault == "wrong_pointer":
        projection["evidence_pointer"] = "file:///private/canary.json"
    elif fault == "not_authenticated_qualifier":
        projection["trust"] = "cryptographically_proven"
    elif fault == "missing_result_hash":
        projection["result_sha256"] = None
    elif fault == "future_evidence":
        projection["evidence_at"] = ops._iso(when + timedelta(seconds=1))
    elif fault == "naive_evidence":
        projection["evidence_at"] = "2026-11-02T21:05:00"
    elif fault == "pre_read_evidence":
        projection["evidence_at"] = "2026-11-01T00:00:00Z"
    elif fault == "unknown_success":
        projection["status"] = "unknown"
    else:
        projection["fill"] = "unknown"
    write(tmp_path / f"{run.key}.json", projection)
    row = ops.build_operations_snapshot(tmp_path, now=when)["runs"][0]
    assert row["status"] == "invalid" and row["fill"] == row["inventory"] == "unknown"
    assert "private-marker" not in json.dumps(row)


def test_retained_history_survives_but_inventory_cannot_be_refreshed_by_checked_at(graph, tmp_path):
    run, _, _, _, when = graph
    projection = ops._collect_public_projection(run, when)
    later = when + ops.PROJECTION_TTL + timedelta(seconds=1)
    for checked in (when, later):
        projection["checked_at"] = ops._iso(checked)
        write(tmp_path / f"{run.key}.json", projection)
        row = ops.build_operations_snapshot(tmp_path, now=later)["runs"][0]
        assert row["status"] == "validated" and row["reason_code"] == "historical_public_outcome"
        assert row["evidence_at"] == ops._iso(when)
        assert row["evidence_pointer"] == run.evidence_pointer
        assert row["submit"] == "accepted" and row["fill"] == "confirmed"
        assert row["inventory"] == "unknown"


def test_old_validated_receipt_remains_historical_without_polling(graph, tmp_path):
    run, _, _, _, when = graph
    later = when + timedelta(days=365)
    projection = ops._collect_public_projection(run, later)
    assert projection["status"] == "validated"
    assert projection["reason_code"] == "historical_public_outcome"
    assert projection["inventory"] == "unknown"
    write(tmp_path / f"{run.key}.json", projection)
    row = ops.build_operations_snapshot(tmp_path, now=later)["runs"][0]
    assert row["submit"] == "accepted" and row["fill"] == "confirmed"
    assert row["evidence_at"] == ops._iso(when)
    assert row["inventory"] == "unknown"


def test_old_missing_projection_is_stale_unknown_not_historical_success(graph, tmp_path):
    run, _, path, _, when = graph
    path.unlink()
    projection = ops._collect_public_projection(run, when)
    write(tmp_path / f"{run.key}.json", projection)
    row = ops.build_operations_snapshot(
        tmp_path,
        now=when + ops.PROJECTION_TTL + timedelta(seconds=1),
    )["runs"][0]
    assert row["status"] == "unknown" and row["reason_code"] == "projection_stale"
    assert row["evidence_at"] is row["evidence_pointer"] is None
    assert all(row[key] == "unknown" for key in ops._FINANCIAL)


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"[]",
        b"not-json",
        b"\xff",
        b" " * 4097,
        b"[" * 2000 + b"]" * 2000,
        b'{"schema":1,"schema":2}',
    ],
)
def test_malformed_projection_is_local_failure_only(tmp_path, raw):
    (tmp_path / "h20.json").write_bytes(raw)
    h20, googl, h3 = ops.build_operations_snapshot(tmp_path, now=NOW)["runs"]
    assert h20["status"] == "invalid" and h20["inventory"] == "unknown"
    assert googl["reason_code"] == "projection_missing"


def test_hardlink_projection_is_rejected_without_reading(tmp_path, monkeypatch):
    source = tmp_path / "other.json"
    source.write_bytes(b"private-marker")
    alias = tmp_path / "h20.json"
    os.link(source, alias)
    try:
        monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("aliased input read"))
        assert ops.build_operations_snapshot(tmp_path, now=NOW)["runs"][0]["status"] == "invalid"
    finally:
        alias.unlink()


def _v2(projection, run):
    result = dict(projection)
    result.pop("source_sha256")
    result.update(
        schema=ops._SCHEMA_V2,
        display_contract_sha256=ops.display_contract_sha256(run.key),
        operational_source_sha256="c" * 64,
        native_sha256="d" * 64,
        reader_sha256="e" * 64,
    )
    return result


def test_v2_separates_fixed_display_contract_from_host_validated_runtime(graph, tmp_path):
    run, _, _, _, when = graph
    projection = _v2(ops._collect_public_projection(run, when), run)
    contract = projection["display_contract_sha256"]
    for operational in ("c" * 64, "f" * 64):
        projection["operational_source_sha256"] = operational
        write(tmp_path / f"{run.key}.json", projection)
        row = ops.build_operations_snapshot(tmp_path, now=when)["runs"][0]
        assert row["submit"] == "accepted" and row["fill"] == "confirmed"
        assert ops.display_contract_sha256(run.key) == contract
        assert operational not in json.dumps(row)


@pytest.mark.parametrize(
    "fault",
    ["contract", "source", "native", "reader", "pointer", "extra", "legacy_source", "trust"],
)
def test_v2_rejects_malformed_or_foreign_display_contract(graph, tmp_path, fault):
    run, _, _, _, when = graph
    projection = _v2(ops._collect_public_projection(run, when), run)
    if fault == "contract":
        projection["display_contract_sha256"] = "0" * 64
    elif fault in {"source", "native", "reader"}:
        field = "operational_source_sha256" if fault == "source" else fault + "_sha256"
        projection[field] = "0" * 64
    elif fault == "pointer":
        projection["evidence_pointer"] = "artifact:foreign/actual-once/RESULT.json"
    elif fault == "extra":
        projection["order_identifier"] = "private-marker"
    elif fault == "legacy_source":
        projection["source_sha256"] = run.source
    else:
        projection["trust"] = "cryptographically_authenticated"
    write(tmp_path / f"{run.key}.json", projection)
    row = ops.build_operations_snapshot(tmp_path, now=when)["runs"][0]
    assert row["status"] == "invalid"
    assert all(row[field] == "unknown" for field in ops._FINANCIAL)
    assert "private-marker" not in json.dumps(row)


def test_v2_preserves_only_historical_outcome_when_inventory_expires(graph, tmp_path):
    run, _, _, _, when = graph
    projection = _v2(ops._collect_public_projection(run, when), run)
    write(tmp_path / f"{run.key}.json", projection)
    row = ops.build_operations_snapshot(
        tmp_path, now=when + ops.PROJECTION_TTL + timedelta(seconds=1)
    )["runs"][0]
    assert row["submit"] == "accepted" and row["fill"] == "confirmed"
    assert row["inventory"] == "unknown" and row["reason_code"] == "historical_public_outcome"


def test_v2_native_file_to_snapshot_to_korean_html_handoff(graph, tmp_path):
    run, _, _, _, when = graph
    projection = _v2(ops._collect_public_projection(run, when), run)
    public = tmp_path / "public-operations"
    write(public / f"{run.key}.json", projection)
    events = EventStore(tmp_path / "view.sqlite", tmp_path / "view-events.jsonl")
    events.bootstrap()
    snapshot = build_snapshot(
        events,
        EmergencyStore(tmp_path / "view-emergency.json"),
        now=when,
        operations_snapshot=ops.build_operations_snapshot(public, now=when),
    )
    row = next(
        item
        for item in snapshot.to_dict()["operations_snapshot"]["runs"]
        if item["key"] == run.key
    )
    assert row["submit"] == "accepted" and row["fill"] == "confirmed"
    html = render_dashboard(snapshot)
    assert '<html lang="ko">' in html and run.symbol in html
    assert "operational_source_sha256" not in html
    assert projection["operational_source_sha256"] not in html


def test_stability_check_catches_replacement(graph, monkeypatch):
    run, _, _, _, when = graph
    unchanged = ops._PublicFiles.unchanged

    def changed(files):
        path = next(iter(files.seen))
        raw = path.read_bytes()
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(raw)
        os.replace(replacement, path)
        unchanged(files)

    monkeypatch.setattr(ops._PublicFiles, "unchanged", changed)
    assert ops._collect_public_projection(run, when)["status"] == "invalid"


def test_atomic_publisher_has_only_two_owned_targets_and_no_get_side_effect(
    graph, tmp_path, monkeypatch
):
    run, _, _, _, when = graph
    destination = tmp_path / "public"
    monkeypatch.setattr(ops, "PUBLIC_PROJECTION_ROOT", destination)
    monkeypatch.setattr(ops.sys, "platform", "win32")
    assert ops.publish_operations_projections(now=when) == {run.key: "validated"}
    assert {path.name for path in destination.iterdir()} == {f"{run.key}.json"}
    before = {path: path.read_bytes() for path in destination.iterdir()}
    monkeypatch.setattr(ops, "_invoke_public_reader", lambda *a: pytest.fail("GET executed reader"))
    snapshot = ops.build_operations_snapshot(destination, now=when)
    assert snapshot["runs"][0]["status"] == "validated"
    assert {path: path.read_bytes() for path in destination.iterdir()} == before


def test_non_windows_publication_is_unsupported(monkeypatch):
    monkeypatch.setattr(ops.sys, "platform", "linux")
    with pytest.raises(ValueError, match="invalid_public_evidence"):
        ops.publish_operations_projections(now=NOW)
