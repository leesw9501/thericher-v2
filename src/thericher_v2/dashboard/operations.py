"""Display-only Paper outcomes from exact, host-published public files.

``artifact_root`` is the dedicated projection directory, NOT model-artifacts.
Docker needs only that directory mounted read-only. It never executes readers
or resolves their Windows links. Publication is an explicit host-only command:
``python -m thericher_v2.dashboard.operations --publish-public-projections``.

The trusted boundary is the authorized host publisher and its protected mount,
not cryptographic host authentication. A validated category describes a retained
public-reader result at evidence_at, not fresh broker holdings or net PnL.
Submit/fill receipts remain historical facts; only inventory expires after 300s.
Publication is finite/manual; no background refresh or Scheduler is installed.
V2 separates the stable display/cohort contract from operational source pins.
Only the trusted host publisher validates those dynamic runtime pins; the web
does not execute artifacts or claim to authenticate a host publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

HOST_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
PUBLIC_PROJECTION_ROOT = HOST_ARTIFACT_ROOT / "monitor/paper-operations"
PROJECTION_TTL = timedelta(seconds=300)
_SCHEMA = "PAPER_OPERATIONS_PUBLIC_PROJECTION_V1"
_SCHEMA_V2 = "PAPER_OPERATIONS_PUBLIC_PROJECTION_V2"
_TRUST = "host_published_public_outcome_not_authenticated"
_PHASES = ("before_create", "before_start", "before_read", "after_read", "after_remove")
_FINANCIAL = ("submit", "fill", "inventory")
_REASONS = {
    "public_reader_unavailable",
    "public_evidence_missing",
    "public_evidence_invalid",
    "public_evidence_withheld",
    "host_published_public_outcome",
    "historical_public_outcome",
}


@dataclass(frozen=True)
class _Run:
    key: str
    label: str
    symbol: str
    entry: str
    read: str | None
    exit: str
    producer: str
    reader_root: str
    source: str
    native: str
    reader: str

    @property
    def evidence_pointer(self) -> str | None:
        if self.key == "h3":
            return None
        return f"artifact:execution/{self.producer}/actual-once/RESULT.json"


_RUNS = (
    _Run(
        "h20",
        "H20",
        "SPY",
        "2026-11-02T15:15:00Z",
        "2026-11-02T15:35:00Z",
        "2026-12-01T14:30:00Z",
        "current-h20-reader-parent-completion-20261101-v1",
        "current-h20-reader-parent-activation-20261101-v1",
        "b2e0ec7324844d604bdc572873990f77121b0334c84078537b29c1234503418a",
        "4a891fdac118e7ce7b5a6b345d8f0a3ef212d052497031fda0ddbcabdff6e5db",
        "e4e4c96af7a4d013054a23e5063189c79a070f1abf8dca8b5f5d13ee1f51fa83",
    ),
    _Run(
        "googl",
        "GOOGL",
        "GOOGL",
        "2026-11-02T20:55:00Z",
        "2026-11-02T21:05:00Z",
        "2026-11-09T20:55:00Z",
        "current-us19-unit-reader-binding-repair-20261101-v1",
        "current-us19-unit-reader-binding-repair-20261101-v1",
        "12e4d0087f0eb6e7cf720980096c105debd454a339b80b7f97b3ec9d2386235b",
        "96ab848b4c370ac9e96b6968c7038872f4247ebffb6388bb347af5ae8d74b369",
        "cdc7bd3328d80f94944496c45e4ce6c003bf6d0faa26fa65e4d0a7b8becd7580",
    ),
)
_H20_READER_MANIFEST = "3402c3378e69ebe8fe9fa2ba15872ede0a25e02894886df7e0479e2b43475bfd"
# Display-only H3 is deliberately absent from the legacy host publisher's _RUNS.
_H3_RUN = _Run(
    "h3",
    "H3",
    "AMD",
    "2026-11-03T20:55:00Z",
    None,
    "2026-11-06T20:45:00Z",
    "current-h3-runtime-result-reader-preparation-20261103-v1",
    "current-h3-runtime-result-reader-preparation-20261103-v1",
    "03ecf2ae05f78bca3ff676ad618c26beb85d934bb18ee5c2695b4aa225d757ad",
    "c045d21e66fb7263739995cbab02e5b0ee9f6a6490479ca30b4fa015d0edfb3f",
    "4990c3dfd5b3c93a53e3e808648cdf30d045987d3b72fa50f356a704ca3fe85f",
)
_H3_POINT = "ad3b0bcf7cda223e2897c04dc744097f2444ba4916ac3820962731d63c46375c"
_H3_SEAL = "f8fe560355d979839b1da8a482b735c46e5c085cfc60749f43ed90f0f9b9563d"
_H3_INSTALLATION = "31e83c91325d95ab9bf507e781afb10c38db4df1f351935e1002e9d12627f6ef"
_H3_FINANCIAL_SOURCE = "6ae5408804b8dea0dc47552f071cd44b6401a3497dd1d2524ac16eccf88ab9af"
_H3_RELEASE = "32f5a92eb9c5d3ac51eb028bba5f70f6462c20e18a43d731d2553366ed50de3a"
_H3_POLICY = "sha256:3ff30cdebd1941efb8979a2a4e6f3e73f1829cf8f15873f45a95211dc7e500ad"
_H3_REASONS = {
    "h3_installation_retained",
    "h3_future_outcome_unknown",
    "h3_host_diagnostic_unknown_finance",
    "h3_technical_fault_unknown_finance",
    "public_evidence_invalid",
    "public_evidence_withheld",
}
_PROJECTION_KEYS = {
    "schema",
    "trust",
    "key",
    "checked_at",
    "source_sha256",
    "native_sha256",
    "reader_sha256",
    "result_sha256",
    "status",
    "submit",
    "fill",
    "inventory",
    "reason_code",
    "evidence_at",
    "evidence_pointer",
}
_PROJECTION_V2_KEYS = (_PROJECTION_KEYS - {"source_sha256"}) | {
    "display_contract_sha256",
    "operational_source_sha256",
}


def display_contract_sha256(key: str) -> str:
    """Stable cohort/display routing, NOT attestation of currently executed code.

    Runtime source/native/reader pins belong to the separately qualified host
    publisher. Keeping them out of this digest prevents a web-image/source cycle.
    """
    run = _H3_RUN if key == "h3" else next(run for run in _RUNS if run.key == key)
    contract = {
        "schema": "PAPER_OPERATIONS_DISPLAY_CONTRACT_V1",
        "key": run.key,
        "symbol": run.symbol,
        "entry_due_at": run.entry,
        "read_due_at": run.read,
        "exit_due_at": run.exit,
        "original_reader_source": run.source,
        "original_native": run.native,
        "original_reader": run.reader,
        "evidence_pointer": run.evidence_pointer,
    }
    if key == "h3":
        contract.update(
            point_sha256=_H3_POINT,
            seal_sha256=_H3_SEAL,
            installation_readback_sha256=_H3_INSTALLATION,
            financial_projection="UNKNOWN_ONLY_NO_QUALIFIED_READ_CLOCK",
        )
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _need(condition: object) -> None:
    if not condition:
        raise ValueError("invalid_public_evidence")


def _timestamp(value: object) -> datetime:
    _need(isinstance(value, str) and len(value) <= 40)
    parsed = datetime.fromisoformat(value)
    _need(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0))
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    _need(value.tzinfo is not None and value.utcoffset() is not None)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json(raw: bytes) -> dict:
    def unique(pairs: list) -> dict:
        result = {}
        for key, value in pairs:
            _need(key not in result)
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    _need(type(value) is dict)
    return value


def _identity(value: os.stat_result) -> tuple:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_nlink,
    )


def _no_alias(path: Path) -> None:
    _need(path.is_absolute())
    for item in (path, *path.parents):
        info = item.lstat()
        _need(not stat.S_ISLNK(info.st_mode))
        _need(not getattr(info, "st_file_attributes", 0) & 0x400)


def _read_stable(path: Path, limit: int = 65536) -> bytes:
    _no_alias(path)
    first = path.stat()
    _need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= limit)
    with path.open("rb") as stream:
        _need(_identity(os.fstat(stream.fileno())) == _identity(first))
        raw = stream.read(limit + 1)
        _need(_identity(os.fstat(stream.fileno())) == _identity(first))
    _no_alias(path)
    _need(_identity(path.stat()) == _identity(first) and len(raw) == first.st_size)
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _row(run: _Run, reason: str = "not_configured", status: str = "unknown") -> dict:
    return {
        "key": run.key,
        "label": run.label,
        "symbol": run.symbol,
        "entry_due_at": run.entry,
        "read_due_at": run.read,
        "exit_due_at": run.exit,
        "status": status,
        "submit": "unknown",
        "fill": "unknown",
        "inventory": "unknown",
        "reason_code": reason,
        "evidence_at": None,
        "evidence_pointer": None,
    }


def _projection(run: _Run, checked: datetime) -> dict:
    row = _row(run, "public_evidence_missing")
    return {
        "schema": _SCHEMA,
        "trust": _TRUST,
        "key": run.key,
        "checked_at": _iso(checked),
        "source_sha256": run.source,
        "native_sha256": run.native,
        "reader_sha256": run.reader,
        "result_sha256": None,
        **{
            key: row[key]
            for key in (*_FINANCIAL, "status", "reason_code", "evidence_at", "evidence_pointer")
        },
    }


def _decode_projection(raw: bytes, run: _Run, now: datetime) -> dict:
    value = _json(raw)
    _need(value["trust"] == _TRUST and value["key"] == run.key)
    if value["schema"] == _SCHEMA:
        _need(set(value) == _PROJECTION_KEYS)
        _need(
            value["source_sha256"] == run.source
            and value["native_sha256"] == run.native
            and value["reader_sha256"] == run.reader
        )
    else:
        _need(value["schema"] == _SCHEMA_V2 and set(value) == _PROJECTION_V2_KEYS)
        _need(value["display_contract_sha256"] == display_contract_sha256(run.key))
        for name in ("operational_source_sha256", "native_sha256", "reader_sha256"):
            _need(_digest(value[name]) and value[name] != "0" * 64)
    _need(value["reason_code"] in (_H3_REASONS if run.key == "h3" else _REASONS))
    if run.key == "h3":
        _need(value["schema"] == _SCHEMA_V2 and value["status"] == "unknown")
        _need(all(value[name] == "unknown" for name in _FINANCIAL))
        _need(
            all(
                value[name] is None for name in ("evidence_at", "evidence_pointer", "result_sha256")
            )
        )
        _need(value["operational_source_sha256"] == _H3_FINANCIAL_SOURCE)
        _need(value["native_sha256"] == run.native and value["reader_sha256"] == run.reader)
    checked = _timestamp(value["checked_at"])
    _need(checked <= now + timedelta(seconds=30))
    evidence = value["evidence_at"]
    if evidence is not None:
        evidence = _timestamp(evidence)
        _need(_timestamp(run.read) <= evidence <= checked and evidence <= now)
        _need(value["evidence_pointer"] == run.evidence_pointer and _digest(value["result_sha256"]))
    else:
        _need(value["evidence_pointer"] is None and value["result_sha256"] is None)
    if value["status"] == "validated":
        _need(
            evidence is not None
            and value["reason_code"]
            in {
                "host_published_public_outcome",
                "historical_public_outcome",
            }
        )
        _need(value["submit"] in {"unknown", "not_observed", "attempted", "accepted"})
        _need(value["fill"] in {"unknown", "not_observed", "confirmed"})
        _need(value["inventory"] in {"unknown", "owned", "flat"})
        _need(value["fill"] != "confirmed" or value["submit"] in {"attempted", "accepted"})
        _need(value["inventory"] != "owned" or value["fill"] == "confirmed")
        _need(value["inventory"] != "flat" or value["fill"] in {"confirmed", "not_observed"})
    else:
        _need(value["status"] in {"unknown", "invalid", "unavailable"})
        _need(
            value["reason_code"]
            not in {
                "host_published_public_outcome",
                "historical_public_outcome",
            }
        )
        _need(all(value[key] == "unknown" for key in _FINANCIAL))
    row = _row(run)
    row.update(
        {
            key: value[key]
            for key in (*_FINANCIAL, "status", "reason_code", "evidence_at", "evidence_pointer")
        }
    )
    if now - checked > PROJECTION_TTL or evidence is not None and now - evidence > PROJECTION_TTL:
        if row["status"] == "validated":
            row.update(inventory="unknown", reason_code="historical_public_outcome")
        else:
            row.update(reason_code="projection_stale")
    if row["reason_code"] == "historical_public_outcome":
        row["inventory"] = "unknown"
    return row


def build_operations_snapshot(
    artifact_root: Path | None,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Read only h20.json, googl.json and h3.json; no discovery or effects."""
    current = now if now is not None else datetime.now(UTC)
    observed = _iso(current)
    runs = []
    for run in (*_RUNS, _H3_RUN):
        row = _row(run)
        if artifact_root is not None:
            try:
                row = _decode_projection(
                    _read_stable(Path(artifact_root).absolute() / f"{run.key}.json", 4096),
                    run,
                    current,
                )
            except FileNotFoundError:
                row = _row(run, "projection_missing")
            except OSError:
                row = _row(run, "projection_unavailable", "unavailable")
            except (ValueError, KeyError, TypeError, RecursionError, OverflowError):
                row = _row(run, "projection_invalid", "invalid")
        runs.append(row)
    return {"observed_at": observed, "runs": runs}


def build_h3_public_projection(
    *,
    now: datetime,
    diagnostic: dict | None = None,
    installation_only: bool = False,
) -> dict:
    """Pure HOST-side display adapter, never a GET-time parser or publisher.

    Caller separately qualifies the pinned public parser and exact input path/hash.
    The diagnostic DTO is NOT financial evidence. No financial categories/times,
    counters, raw errors or evidence paths are promoted into the V2 envelope.
    This function performs no I/O and cannot publish, schedule or query anything.
    """
    _need(type(installation_only) is bool)
    value = _projection(_H3_RUN, now)
    value.pop("source_sha256")
    value.update(
        schema=_SCHEMA_V2,
        display_contract_sha256=display_contract_sha256("h3"),
        operational_source_sha256=_H3_FINANCIAL_SOURCE,
        reason_code="h3_installation_retained"
        if installation_only
        else "h3_future_outcome_unknown",
    )
    if diagnostic is not None:
        _need(type(diagnostic) is dict and not installation_only)
        _need(diagnostic["schema"] == "H3_FUTURE_RUNTIME_DIAGNOSTIC_PROJECTION_V1")
        _need(diagnostic["trust"] == "host_diagnostic_not_authenticated_not_financial_evidence")
        _need(diagnostic["key"] == "h3" and diagnostic["deployable_monitor_v2"] is False)
        _need(diagnostic["source_sha256"] == _H3_FINANCIAL_SOURCE)
        _need(diagnostic["release_sha256"] == _H3_RELEASE)
        _need(diagnostic["input_ref"] == "sha256:" + _H3_POINT)
        _need(diagnostic["policy_ref"] == _H3_POLICY)
        _need(diagnostic["round_id"] == "h3-rank-preferred-finite-20261103-v1")
        _need(diagnostic["phase"] in {"entry", "exit"})
        _need(_timestamp(diagnostic["checked_at"]) <= now)
        financial = diagnostic["financial"]
        _need(
            type(financial) is dict
            and set(financial)
            == {
                "signal",
                "no_intent",
                "attempt",
                "acceptance",
                "exact_linked_fill",
                "current_owned_inventory",
                "terminal_reconciliation",
                "fees",
                "settlement",
                "net_PnL",
            }
        )
        _need(all(item == "UNKNOWN" for item in financial.values()))
        _need(diagnostic["status"] in {"diagnostic_only", "technical_failure"})
        value["reason_code"] = (
            "h3_technical_fault_unknown_finance"
            if diagnostic["status"] == "technical_failure"
            else "h3_host_diagnostic_unknown_finance"
        )
    _decode_projection(json.dumps(value).encode("ascii"), _H3_RUN, now)
    return value


class _PublicFiles:
    """Finite exact public links, re-read after the isolated outcome consumer."""

    def __init__(self) -> None:
        self.seen: dict[Path, tuple] = {}

    def read(self, path: Path, digest: str | None = None) -> bytes:
        raw = _read_stable(path, 4194304)
        fingerprint = (_identity(path.stat()), _sha(raw))
        _need(path not in self.seen or self.seen[path] == fingerprint)
        self.seen[path] = fingerprint
        _need(digest is None or fingerprint[1] == digest)
        return raw

    def ref(self, value: dict, expected: Path | None = None) -> bytes:
        _need(set(value) in ({"path", "sha256"}, {"path", "sha256", "bytes"}))
        _need(_digest(value["sha256"]) and isinstance(value["path"], str))
        path = Path(value["path"])
        _need(expected is None or path == expected)
        raw = self.read(path, value["sha256"])
        _need("bytes" not in value or type(value["bytes"]) is int and value["bytes"] == len(raw))
        return raw

    def unchanged(self) -> None:
        for path, before in self.seen.items():
            raw = _read_stable(path, 4194304)
            _need((_identity(path.stat()), _sha(raw)) == before)


def _audit_source(run: _Run, files: _PublicFiles) -> tuple[Path, Path, dict]:
    producer = HOST_ARTIFACT_ROOT / "execution" / run.producer
    reader = HOST_ARTIFACT_ROOT / "execution" / run.reader_root / "read_outcome.py"
    manifests = [(producer / "SOURCE.json", run.source)]
    if run.key == "h20":
        manifests.append((reader.parent / "READER-SOURCE.json", _H20_READER_MANIFEST))
    for path, digest in manifests:
        source = _json(files.read(path, digest))
        _need(type(source["pins"]) is list and 0 < len(source["pins"]) <= 128)
        for pin in source["pins"]:
            files.ref(pin)
    files.read(reader, run.reader)
    native = _json(files.read(producer / "NATIVE.json", run.native))
    _need(native["status"] == "PASS")
    return producer, reader, _json(files.read(producer / "BINDING.json"))


def _envelope(run: _Run, producer: Path, binding: dict, files: _PublicFiles) -> tuple[dict, str]:
    path = producer / "actual-once/RESULT.json"
    raw = files.read(path)
    value = _json(raw)
    _need(value["source_sha256"] == run.source)
    _need(
        type(value["broker_calls"]) is int
        and value["broker_calls"] == 0
        and type(value["private_writes"]) is int
        and value["private_writes"] == 0
    )
    names = (
        ("reader_source", "H20_source", "release", "plan", "contract")
        if run.key == "h20"
        else (
            "installed_host",
            "release",
            "contract",
            "reader_source",
        )
    )
    for name in names:
        expected = binding["installed_host" if name == "H20_source" else name]
        _need(value[name] == expected)
        files.ref(expected)
    if run.key == "h20":
        _need(
            value["input_ref"] == binding["input_ref"]
            and value["policy_ref"] == binding["policy_ref"]
        )
        _need(
            value["reservation_released"] is False
            and value["current_read_not_historical_OS_origin"] is True
            and value["fees_settlement_netPnL"] == "NOT_OBSERVED"
        )
    else:
        _need(
            type(value["broker_calls"]) is int
            and value["broker_calls"] == 0
            and type(value["private_writes"]) is int
            and value["private_writes"] == 0
        )
        _need(
            value["schema"] == "US19_UNIT_OUTCOME_RECEIPT_V1"
            and value["native_proof_sha256"] == run.native
            and value["historical_scheduler_origin"] == "UNKNOWN"
        )
    closed = _json(files.ref(value["closure"], producer / "actual-once/CLOSED.json"))
    _need(
        closed["CID_absent"] is True
        and type(closed["Jobs"]) is list
        and 0 < len(closed["Jobs"]) <= 128
    )
    for job in closed["Jobs"]:
        _need(
            type(job["exit"]) is int
            and job["exit"] == 0
            and type(job["active"]) is int
            and job["active"] == 0
            and job["closed"] is True
        )
    admissions = closed["admissions"]
    _need([a["phase"] for a in admissions] == list(_PHASES))
    if run.key == "h20":
        _need(closed["status"] == "PASS" and value["admissions"] == admissions)
    for admission in admissions:
        verdict = _json(
            files.ref(
                admission["verdict"],
                producer / "actual-once" / f"CAPABILITY-{admission['phase']}.json",
            )
        )
        _need(verdict["status"] == "NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED")
        _need(type(admission["actual_caller"]) is dict and admission["actual_caller"])
    return value, _sha(raw)


def _categories(run: _Run, value: dict) -> dict:
    """Only the native, source-bound parser's explicit categories carry forward."""
    h20 = run.key == "h20"
    _need(
        value["schema"]
        == ("H20_EXACT_OFFLINE_OUTCOME_V1" if h20 else "US19_UNIT_OFFLINE_OUTCOME_V1")
    )
    attempt, acceptance = value["attempt"], value["acceptance"]
    fill = value["fill" if h20 else "exact_fill"]
    inventory = value["current_owned_inventory" if h20 else "current_local_owned"]
    _need(attempt in {"UNKNOWN", "RECORDED", "NOT_RECORDED"})
    _need(acceptance in {"UNKNOWN", "ACKNOWLEDGED"})
    _need(fill in {"UNKNOWN", "NOT_RECORDED", "ZERO", "PARTIAL", "FULL"})
    _need(inventory in {"UNKNOWN", "POSITIVE", "FLAT"} and value["terminal"] in {"UNKNOWN", "YES"})
    _need(
        value["reservation_released"] is False
        and value["broker_holdings"] == "NOT_READ"
        and value["net_PnL"] == "UNKNOWN"
    )
    _need(acceptance != "ACKNOWLEDGED" or attempt == "RECORDED")
    _need(fill not in {"ZERO", "PARTIAL", "FULL"} or attempt == "RECORDED")
    _need(inventory == "UNKNOWN" or fill in {"ZERO", "PARTIAL", "FULL"})
    _need(inventory != "POSITIVE" or fill in {"PARTIAL", "FULL"})
    if h20:
        _need(value["raw_exception_retained"] is False)
    else:
        _need(
            value["host_runtime_chain"] == "UNKNOWN"
            and value["fees"] == value["settlement"] == "UNKNOWN"
        )
        _need(
            value["pending"] in {"UNKNOWN", "YES", "NO"} and value["no_intent"] in {"UNKNOWN", "NO"}
        )
        for key in ("intent_count", "exact_fill_count", "current_local_owned_count"):
            _need(value[key] is None or type(value[key]) is int and value[key] in {0, 1})
        if value["reason"] != "OK":
            _need(all(item == "UNKNOWN" for item in (attempt, acceptance, fill, inventory)))
            return dict.fromkeys(_FINANCIAL, "unknown")
        _need(value["no_intent"] == "NO" and value["intent_count"] == 1)
        _need((fill == "FULL") == (value["exact_fill_count"] == 1))
        _need((inventory == "POSITIVE") == (value["current_local_owned_count"] == 1))
    return {
        "submit": "accepted"
        if acceptance == "ACKNOWLEDGED"
        else {
            "UNKNOWN": "unknown",
            "RECORDED": "attempted",
            "NOT_RECORDED": "not_observed",
        }[attempt],
        "fill": "confirmed"
        if fill in {"PARTIAL", "FULL"}
        else ("unknown" if fill == "UNKNOWN" else "not_observed"),
        "inventory": {"UNKNOWN": "unknown", "POSITIVE": "owned", "FLAT": "flat"}[inventory],
    }


def _invoke_public_reader(run: _Run, reader: Path) -> bytes:
    # This function is called only by explicit host publication, never a GET.
    argv = [sys.executable, "-I", "-B", str(reader)]
    if run.key == "googl":
        argv += [run.source, run.native]
    environment = {
        name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ
    }
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(
            argv,
            cwd=reader.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _need(result.returncode == 0 and output.tell() <= 32768)
        output.seek(0)
        return output.read(32769)


def _collect_public_projection(run: _Run, now: datetime) -> dict:
    projection = _projection(run, now)
    files = _PublicFiles()
    try:
        producer, reader, binding = _audit_source(run, files)
        result_path = producer / "actual-once/RESULT.json"
        try:
            envelope, digest = _envelope(run, producer, binding, files)
        except FileNotFoundError:
            _need(not result_path.exists())
            envelope, digest = None, None
        raw = _invoke_public_reader(run, reader)
        output = _json(raw)
        if envelope is None:
            _need(not result_path.exists())
            if run.key == "h20":
                _need(
                    output
                    == {"status": "UNKNOWN_NO_COMPLETE_OUTCOME", "financial_result": "UNKNOWN"}
                )
            else:
                _categories(run, output)
                _need(output["reason"] == "MISSING_OR_UNBOUND")
        else:
            categories = _categories(run, envelope["result"])
            if run.key == "h20":
                _need(output["status"] == "VALIDATED_CURRENT_RETAINED_STATE")
                files.ref(output["evidence"], result_path)
                for name in (
                    "attempt",
                    "acceptance",
                    "fill",
                    "current_owned_inventory",
                    "terminal",
                ):
                    _need(output[name] == envelope["result"][name])
                _need(output["observed_utc"] == envelope["observed_utc"])
                evidence_at = envelope["observed_utc"]
            else:
                _need(output == envelope["result"])
                evidence_at = envelope["observed_at"]
            withheld = run.key == "googl" and output["reason"] != "OK"
            projection.update(
                status="unknown" if withheld else "validated",
                **categories,
                reason_code="public_evidence_withheld"
                if withheld
                else "host_published_public_outcome",
                evidence_at=_iso(_timestamp(evidence_at)),
                evidence_pointer=run.evidence_pointer,
                result_sha256=digest,
            )
        files.unchanged()
        row = _decode_projection(json.dumps(projection).encode(), run, now)
        if row["reason_code"] == "historical_public_outcome":
            projection.update(inventory="unknown", reason_code="historical_public_outcome")
    except (OSError, subprocess.SubprocessError):
        projection = _projection(run, now)
        projection.update(status="unavailable", reason_code="public_reader_unavailable")
    except (ValueError, KeyError, TypeError, RecursionError, OverflowError):
        projection = _projection(run, now)
        projection.update(status="invalid", reason_code="public_evidence_invalid")
    return projection


def publish_operations_projections(*, now: datetime | None = None) -> dict[str, str]:
    """Explicit Windows-host action; replace only the two owned public files.

    No financial reader/Task/daemon is started. Only RUNBOOK read_outcome.py
    consumers run, after exact source/member checks. A malicious host can forge
    this unsigned publication; Docker must not treat it as authenticated proof.
    """
    _need(sys.platform == "win32")
    current = now if now is not None else datetime.now(UTC)
    _iso(current)
    PUBLIC_PROJECTION_ROOT.mkdir(parents=True, exist_ok=True)
    _no_alias(PUBLIC_PROJECTION_ROOT)
    statuses = {}
    for run in _RUNS:
        value = _collect_public_projection(run, current)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "ascii"
        )
        _need(len(raw) <= 4096)
        target = PUBLIC_PROJECTION_ROOT / f"{run.key}.json"
        if target.exists() or target.is_symlink():
            _no_alias(target)
            _need(target.stat().st_nlink == 1)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=PUBLIC_PROJECTION_ROOT, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        statuses[run.key] = value["status"]
    return statuses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-public-projections", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(publish_operations_projections(), sort_keys=True))


if __name__ == "__main__":
    main()
