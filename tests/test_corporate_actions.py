from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import socket
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from thericher_v2.data import CatalogedCorporateActions, load_cataloged_corporate_actions
from thericher_v2.data.corporate_actions import (
    CAMPAIGN_COVERAGE_END,
    CAMPAIGN_COVERAGE_START,
    CORPORATE_ACTION_COLUMNS,
    CORPORATE_ACTION_EVENT_TYPES,
    CORPORATE_ACTION_SYMBOLS,
)

R2_ID = "us_equities.fixed_etf_daily.1d.snapshot=2026-07-18-r2"
R2_HASH = "sha256:" + "a" * 64
R2_MANIFEST_HASH = "sha256:" + "b" * 64


@dataclass
class _Fixture:
    snapshot: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    sessions: dict[str, frozenset[date]]


def test_loader_attests_replay_snapshot_offline_and_preserves_duplicate_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_snapshot(tmp_path / "external")
    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: pytest.fail("network"))

    catalog = _load(fixture, require_replay_eligible=True)

    assert catalog.dataset_id == fixture.dataset_id
    assert catalog.dataset_hash == fixture.dataset_hash
    assert catalog.manifest_hash == fixture.manifest_hash
    assert catalog.r2_dataset_hash == R2_HASH
    assert catalog.r2_manifest_hash == R2_MANIFEST_HASH
    assert catalog.retrieved_at_utc == datetime(2026, 7, 18, 1, 2, 3, tzinfo=UTC)
    assert catalog.source_as_of == CAMPAIGN_COVERAGE_END
    assert catalog.revision == "fixture-r1"
    assert len(catalog.for_symbol("spy")) == 2
    assert catalog.for_symbol("SPY")[0].cash_amount == Decimal("1.23")
    assert catalog.affected_session_dates("SPY") == frozenset({date(2024, 3, 15)})
    assert len(catalog.events) == 6
    catalog.assert_replay_eligible()
    with pytest.raises(TypeError, match="use load_cataloged_corporate_actions"):
        CatalogedCorporateActions()


def test_replay_assertion_rejects_object_new_identity_bypass(tmp_path: Path) -> None:
    catalog = _load(_write_snapshot(tmp_path / "attestation"))
    forged = object.__new__(CatalogedCorporateActions)
    for field in (
        "dataset_id",
        "dataset_hash",
        "manifest_path",
        "manifest_hash",
        "r2_dataset_id",
        "r2_dataset_hash",
        "r2_manifest_hash",
        "retrieved_at_utc",
        "source_as_of",
        "revision",
        "events",
    ):
        object.__setattr__(forged, field, getattr(catalog, field))
    object.__setattr__(forged, "_replay_ineligibility_reasons", ())

    with pytest.raises(ValueError, match="not loader-attested"):
        forged.assert_replay_eligible()
    object.__setattr__(forged, "_identity_attestation", object())
    with pytest.raises(ValueError, match="not loader-attested"):
        forged.assert_replay_eligible()
    catalog.assert_replay_eligible()


def test_loader_rejects_manifest_dataset_raw_and_lineage_tamper(tmp_path: Path) -> None:
    fixture = _write_snapshot(tmp_path / "hashes")
    with pytest.raises(ValueError, match="manifest content hash mismatch"):
        _load(fixture, manifest_hash="sha256:" + "c" * 64)
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        _load(fixture, dataset_hash="sha256:" + "d" * 64)
    with pytest.raises(ValueError, match="r2 lineage mismatch"):
        _load(fixture, r2_manifest_hash="sha256:" + "e" * 64)

    raw_path = fixture.snapshot / "raw" / "issuer-a.json"
    raw_path.write_bytes(raw_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="raw source size mismatch"):
        _load(fixture)

    missing = _write_snapshot(tmp_path / "missing")
    (missing.snapshot / "manifest.json").unlink()
    with pytest.raises(ValueError, match="manifest is missing"):
        _load(missing)


def test_loader_is_mount_portable_and_rejects_git_workspace_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_snapshot(tmp_path / "original")
    relocated = tmp_path / "mounted" / fixture.snapshot.name
    shutil.copytree(fixture.snapshot, relocated)
    relocated_fixture = _Fixture(
        relocated,
        fixture.dataset_id,
        fixture.dataset_hash,
        fixture.manifest_hash,
        fixture.sessions,
    )
    assert _load(relocated_fixture).manifest_path == relocated / "manifest.json"

    renamed = tmp_path / "mounted" / "snapshot=wrong"
    shutil.copytree(fixture.snapshot, renamed)
    with pytest.raises(ValueError, match="dataset_id is inconsistent"):
        _load(
            _Fixture(
                renamed,
                fixture.dataset_id,
                fixture.dataset_hash,
                fixture.manifest_hash,
                fixture.sessions,
            )
        )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    inside = repo / fixture.snapshot.name
    shutil.copytree(fixture.snapshot, inside)
    with pytest.raises(ValueError, match="outside Git"):
        _load(
            _Fixture(
                inside,
                fixture.dataset_id,
                fixture.dataset_hash,
                fixture.manifest_hash,
                fixture.sessions,
            )
        )

    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == fixture.snapshot or real_is_symlink(path),
    )
    with pytest.raises(ValueError, match="snapshot cannot be a symlink"):
        _load(fixture)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ((1, "event_id", "spy-cash-a"), "duplicate corporate-action event_id"),
        ((1, "cash_amount", "9.99"), "conflicting normalized"),
        ((2, "event_type", "dividend"), "unsupported corporate-action event_type"),
        ((0, "source_date_kind", "effective_date"), "requires ex_date"),
        ((2, "source_date_kind", "ex_date"), "requires split_trading_date"),
        ((0, "mapping_status", "unmapped"), "mapped observed-session rule"),
        ((0, "affected_session_date", "2024-03-18"), "cannot be rolled"),
        ((0, "source_event_date", "2024-03-16"), "cannot be rolled"),
        ((1, "source_id", "issuer-a"), "source record"),
    ],
)
def test_loader_rejects_invalid_or_conflicting_events(
    tmp_path: Path, change: tuple[int, str, str], match: str
) -> None:
    rows = _event_rows()
    row_index, field, value = change
    rows[row_index][field] = value
    if field == "source_id":
        rows[row_index]["source_record_id"] = rows[0]["source_record_id"]
    fixture = _write_snapshot(tmp_path / field, rows=rows)

    with pytest.raises(ValueError, match=match):
        _load(fixture)


def test_loader_rejects_non_session_and_inexact_session_universe(tmp_path: Path) -> None:
    rows = _event_rows()
    rows[0]["source_event_date"] = "2024-03-16"
    rows[0]["affected_session_date"] = "2024-03-16"
    rows[1]["source_event_date"] = "2024-03-16"
    rows[1]["affected_session_date"] = "2024-03-16"
    fixture = _write_snapshot(tmp_path / "weekend", rows=rows)
    with pytest.raises(ValueError, match="non-session"):
        _load(fixture)

    fixture = _write_snapshot(tmp_path / "symbols")
    fixture.sessions.pop("IWM")
    with pytest.raises(ValueError, match="exact fixed symbols"):
        _load(fixture)


def test_replay_eligibility_fails_closed_on_coverage_and_source_as_of(
    tmp_path: Path,
) -> None:
    incomplete = _write_snapshot(tmp_path / "incomplete")
    manifest = _read_manifest(incomplete)
    manifest["coverage"][0]["status"] = "unknown"
    _rewrite_manifest(incomplete, manifest)
    catalog = _load(incomplete)
    with pytest.raises(ValueError, match="SPY/cash_distribution coverage is unknown"):
        catalog.assert_replay_eligible()
    with pytest.raises(ValueError, match="not replay eligible"):
        _load(incomplete, require_replay_eligible=True)

    stale = _write_snapshot(tmp_path / "stale", source_as_of=date(2026, 6, 21))
    with pytest.raises(ValueError, match="source_as_of predates campaign end"):
        _load(stale, require_replay_eligible=True)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("missing_rights", "rights_status must be confirmed"),
        ("unconfirmed_rights", "rights_status must be confirmed"),
        ("http_url", "must be an HTTPS URL"),
        ("wrong_scope", "use_scope must be private_internal_use"),
        ("source_time_order", "source_as_of cannot follow retrieval UTC date"),
        ("snapshot_time_order", "snapshot source_as_of cannot follow retrieval UTC date"),
        ("undeclared_symbol", "does not declare its symbol and event_type"),
        ("unsorted_symbols", "must be exact, unique, and sorted"),
    ],
)
def test_loader_rejects_opaque_or_unqualified_raw_source_contracts(
    tmp_path: Path, mutation: str, match: str
) -> None:
    fixture = _write_snapshot(tmp_path / mutation)
    manifest = _read_manifest(fixture)
    source = manifest["raw_sources"][1]
    if mutation == "missing_rights":
        source.pop("rights_status")
    elif mutation == "unconfirmed_rights":
        source["rights_status"] = "unknown"
    elif mutation == "http_url":
        source["source_url"] = "http://issuer-b.example/actions"
    elif mutation == "wrong_scope":
        source["use_scope"] = "research_only"
    elif mutation == "source_time_order":
        source["source_as_of"] = "2026-07-19"
    elif mutation == "snapshot_time_order":
        manifest["snapshot_metadata"]["source_as_of"] = "2026-07-19"
    elif mutation == "undeclared_symbol":
        source["symbols"] = ["QQQ"]
    else:
        source["symbols"] = ["SPY", "QQQ"]
    _rewrite_manifest(fixture, manifest)

    with pytest.raises(ValueError, match=match):
        _load(fixture)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("missing_coverage", "coverage is incomplete"),
        ("wrong_count", "event_count disagrees"),
        ("wrong_symbols", "exact fixed symbols"),
        ("naive_retrieval", "explicit UTC timestamp"),
        ("blank_revision", "revision is required"),
        ("wrong_event_path", "normalized event path is inconsistent"),
        ("wrong_r2_path", "r2 manifest path is inconsistent"),
        ("wrong_duplicate_policy", "duplicate/conflict policy"),
    ],
)
def test_loader_rejects_incomplete_or_ambiguous_manifest_contract(
    tmp_path: Path, mutation: str, match: str
) -> None:
    fixture = _write_snapshot(tmp_path / mutation)
    manifest = _read_manifest(fixture)
    if mutation == "missing_coverage":
        manifest["coverage"].pop()
    elif mutation == "wrong_count":
        manifest["coverage"][0]["event_count"] += 1
    elif mutation == "wrong_symbols":
        manifest["symbols"] = ["SPY", "QQQ"]
    elif mutation == "naive_retrieval":
        manifest["snapshot_metadata"]["retrieved_at_utc"] = "2026-07-18T01:02:03"
    elif mutation == "blank_revision":
        manifest["snapshot_metadata"]["revision"] = ""
    elif mutation == "wrong_event_path":
        manifest["normalized_events"]["path"] = r"D:\market_data\wrong\events.csv"
    elif mutation == "wrong_r2_path":
        manifest["r2_lineage"]["manifest_path"] = r"D:\market_data\wrong\manifest.json"
    else:
        manifest["duplicate_policy"]["conflict"] = "last_write_wins"
    _rewrite_manifest(fixture, manifest)

    with pytest.raises(ValueError, match=match):
        _load(fixture)


def _load(
    fixture: _Fixture,
    *,
    dataset_hash: str | None = None,
    manifest_hash: str | None = None,
    r2_manifest_hash: str = R2_MANIFEST_HASH,
    require_replay_eligible: bool = False,
) -> CatalogedCorporateActions:
    return load_cataloged_corporate_actions(
        fixture.snapshot,
        dataset_id=fixture.dataset_id,
        expected_dataset_hash=dataset_hash or fixture.dataset_hash,
        expected_manifest_hash=manifest_hash or fixture.manifest_hash,
        expected_r2_dataset_id=R2_ID,
        expected_r2_dataset_hash=R2_HASH,
        expected_r2_manifest_hash=r2_manifest_hash,
        observed_session_dates=fixture.sessions,
        require_replay_eligible=require_replay_eligible,
    )


def _write_snapshot(
    root: Path,
    *,
    rows: list[dict[str, str]] | None = None,
    source_as_of: date = CAMPAIGN_COVERAGE_END,
) -> _Fixture:
    snapshot = root / "snapshot=2026-07-18-events-r1"
    raw_dir = snapshot / "raw"
    raw_dir.mkdir(parents=True)
    raw_files = {
        "issuer-a": ("issuer-a.json", b'{"issuer":"a"}\n'),
        "issuer-b": ("issuer-b.json", b'{"issuer":"b"}\n'),
    }
    for filename, content in raw_files.values():
        (raw_dir / filename).write_bytes(content)

    selected_rows = rows if rows is not None else _event_rows()
    event_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        event_buffer, fieldnames=CORPORATE_ACTION_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(selected_rows)
    event_bytes = event_buffer.getvalue().encode("utf-8")
    event_path = snapshot / "corporate_actions.csv"
    event_path.write_bytes(event_bytes)
    event_hash = _sha256(event_bytes)
    dataset_id = f"us_equities.fixed_etf_corporate_actions.{snapshot.name}"
    retrieval = "2026-07-18T01:02:03Z"
    coverage = []
    for symbol in CORPORATE_ACTION_SYMBOLS:
        for event_type in CORPORATE_ACTION_EVENT_TYPES:
            matching = [
                row
                for row in selected_rows
                if row["symbol"] == symbol and row["event_type"] == event_type
            ]
            source_ids = sorted({row["source_id"] for row in matching} or {"issuer-a"})
            coverage.append(
                {
                    "symbol": symbol,
                    "event_type": event_type,
                    "start": CAMPAIGN_COVERAGE_START.isoformat(),
                    "end": CAMPAIGN_COVERAGE_END.isoformat(),
                    "status": "complete",
                    "event_count": len(matching),
                    "source_ids": source_ids,
                }
            )
    raw_sources = []
    for source_id, (filename, content) in raw_files.items():
        if source_id == "issuer-b":
            source_symbols = ["SPY"]
            source_event_types = ["cash_distribution"]
        else:
            source_symbols = sorted(CORPORATE_ACTION_SYMBOLS)
            source_event_types = sorted(CORPORATE_ACTION_EVENT_TYPES)
        raw_sources.append(
            {
                "source_id": source_id,
                "provider": f"Fixture {source_id}",
                "source_url": f"https://{source_id}.example/corporate-actions",
                "source_kind": "issuer_download",
                "acquisition_mode": "manual_operator",
                "use_scope": "private_internal_use",
                "rights_status": "confirmed",
                "symbols": source_symbols,
                "event_types": source_event_types,
                "coverage_start": CAMPAIGN_COVERAGE_START.isoformat(),
                "coverage_end": CAMPAIGN_COVERAGE_END.isoformat(),
                "filename": filename,
                "path": rf"D:\market_data\events\{snapshot.name}\raw\{filename}",
                "sha256": _sha256(content),
                "size_bytes": len(content),
                "retrieved_at_utc": retrieval,
                "source_as_of": source_as_of.isoformat(),
                "revision": "source-r1",
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "fixed_etf_corporate_actions",
        "dataset_id": dataset_id,
        "dataset_hash": event_hash,
        "immutable_snapshot": True,
        "symbols": list(CORPORATE_ACTION_SYMBOLS),
        "event_types": list(CORPORATE_ACTION_EVENT_TYPES),
        "date_kinds": ["ex_date", "split_trading_date"],
        "normalized_events": {
            "path": rf"D:\market_data\events\{snapshot.name}\{event_path.name}",
            "sha256": event_hash,
            "size_bytes": len(event_bytes),
            "schema": list(CORPORATE_ACTION_COLUMNS),
        },
        "raw_sources": raw_sources,
        "snapshot_metadata": {
            "retrieved_at_utc": retrieval,
            "source_as_of": source_as_of.isoformat(),
            "revision": "fixture-r1",
        },
        "campaign_coverage": {
            "start": CAMPAIGN_COVERAGE_START.isoformat(),
            "end": CAMPAIGN_COVERAGE_END.isoformat(),
        },
        "coverage": coverage,
        "date_semantics": {
            "exchange_timezone": "America/New_York",
            "session_date_semantics": "date_only_no_utc_conversion",
            "non_session_policy": "reject",
            "ambiguous_effective_date_policy": "reject",
        },
        "mapping_policy": {
            "id": "identity_observed_session_v1",
            "status": "mapped_only",
            "calendar_lineage": "verified_r2_observed_sessions",
        },
        "duplicate_policy": {
            "event_id": "reject",
            "source_record": "reject",
            "identical_normalized_action": "preserve_records_collapse_mask_date",
            "conflict": "reject",
        },
        "scope": {
            "retrospective_development_replay_only": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "r2_lineage": {
            "dataset_id": R2_ID,
            "dataset_hash": R2_HASH,
            "manifest_sha256": R2_MANIFEST_HASH,
            "snapshot_name": "snapshot=2026-07-18-r2",
            "subset_path": (
                r"D:\market_data\us_equities\fixed_etf_daily\canonical\ohlcv_1d"
                r"\snapshot=2026-07-18-r2\ohlcv_1d.csv.gz"
            ),
            "manifest_path": (
                r"D:\market_data\us_equities\fixed_etf_daily\canonical\ohlcv_1d"
                r"\snapshot=2026-07-18-r2\manifest.json"
            ),
        },
    }
    manifest_path = snapshot / "manifest.json"
    manifest_bytes = _json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    sessions = {
        symbol: frozenset(
            {
                CAMPAIGN_COVERAGE_START,
                CAMPAIGN_COVERAGE_END,
                *(date.fromisoformat(row["affected_session_date"]) for row in _event_rows()),
            }
        )
        for symbol in CORPORATE_ACTION_SYMBOLS
    }
    return _Fixture(snapshot, dataset_id, event_hash, _sha256(manifest_bytes), sessions)


def _event_rows() -> list[dict[str, str]]:
    return [
        _distribution_row(
            "spy-cash-a", "SPY", "cash_distribution", date(2024, 3, 15), "1.23", "issuer-a"
        ),
        _distribution_row(
            "spy-cash-b", "SPY", "cash_distribution", date(2024, 3, 15), "1.23", "issuer-b"
        ),
        _split_row("qqq-split", "QQQ", date(2023, 1, 10)),
        _distribution_row(
            "qqq-cash-20231218",
            "QQQ",
            "cash_distribution",
            date(2023, 12, 18),
            "0.57",
            "issuer-a",
        ),
        _distribution_row(
            "iwm-cash-20240112",
            "IWM",
            "cash_distribution",
            date(2024, 1, 12),
            "0.11",
            "issuer-a",
        ),
        _distribution_row(
            "iwm-cash-20240321",
            "IWM",
            "cash_distribution",
            date(2024, 3, 21),
            "0.52",
            "issuer-a",
        ),
    ]


def _distribution_row(
    event_id: str,
    symbol: str,
    event_type: str,
    session: date,
    amount: str,
    source_id: str,
) -> dict[str, str]:
    return {
        "event_id": event_id,
        "symbol": symbol,
        "event_type": event_type,
        "source_date_kind": "ex_date",
        "source_event_date": session.isoformat(),
        "affected_session_date": session.isoformat(),
        "cash_amount": amount,
        "currency": "USD",
        "split_numerator": "",
        "split_denominator": "",
        "source_id": source_id,
        "source_record_id": f"record-{event_id.rsplit('-', 1)[-1]}",
        "mapping_rule_id": "identity_observed_session_v1",
        "mapping_status": "mapped",
    }


def _split_row(event_id: str, symbol: str, session: date) -> dict[str, str]:
    return {
        "event_id": event_id,
        "symbol": symbol,
        "event_type": "split",
        "source_date_kind": "split_trading_date",
        "source_event_date": session.isoformat(),
        "affected_session_date": session.isoformat(),
        "cash_amount": "",
        "currency": "",
        "split_numerator": "2",
        "split_denominator": "1",
        "source_id": "issuer-a",
        "source_record_id": "record-qqq-split",
        "mapping_rule_id": "identity_observed_session_v1",
        "mapping_status": "mapped",
    }


def _read_manifest(fixture: _Fixture) -> dict[str, Any]:
    return json.loads((fixture.snapshot / "manifest.json").read_text(encoding="utf-8"))


def _rewrite_manifest(fixture: _Fixture, manifest: dict[str, Any]) -> None:
    data = _json_bytes(manifest)
    (fixture.snapshot / "manifest.json").write_bytes(data)
    fixture.manifest_hash = _sha256(data)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
