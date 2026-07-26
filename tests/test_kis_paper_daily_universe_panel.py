from __future__ import annotations

import csv
import gzip
import hashlib
import inspect
import io
import json
import os
import socket
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from thericher_v2.data import kis_paper_daily_universe_panel as panel_module
from thericher_v2.data.kis_paper_daily_universe_panel import (
    KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
    KisPaperDailyUniversePanel,
    _FrozenPanelIdentity,
    _load_panel,
    _materialize_panel,
    load_frozen_kis_paper_daily_universe_panel,
    materialize_frozen_kis_paper_daily_universe_panel,
    prepare_kis_paper_daily_universe_completed_bar_input,
)
from thericher_v2.data.official_symbol_directory_nas_probe import NAS_COMMON_STOCK_PROBE_SYMBOLS
from thericher_v2.execution import EmergencyStore
from thericher_v2.research.validation import ValidationConfig, run_local_paper_validation
from thericher_v2.state import EventStore


@dataclass(frozen=True)
class _Fixture:
    cache_root: Path
    evidence_root: Path
    repository_root: Path
    manifest_path: Path
    evidence_path: Path
    identity: _FrozenPanelIdentity


def test_loader_reconstructs_a_hash_bound_common_session_panel(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    panel = _load(fixture)

    assert isinstance(panel, KisPaperDailyUniversePanel)
    assert panel.dataset_id == KIS_PAPER_DAILY_UNIVERSE_PANEL_ID
    assert tuple(panel.bars_by_symbol) == NAS_COMMON_STOCK_PROBE_SYMBOLS
    assert len(panel.common_sessions) == 11
    assert panel.alignment_excluded_rows == {
        "AAPL": 1,
        "AMZN": 1,
        "GOOGL": 1,
        "META": 1,
        "MSFT": 1,
        "NVDA": 0,
    }
    for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS:
        stream = panel.validation_series(symbol)
        assert stream.dataset_id == panel.dataset_id
        assert stream.dataset_hash == panel.dataset_hash
        assert tuple(bar.start_ts.date() for bar in stream.bars) == panel.common_sessions
        assert all(bar.complete for bar in stream.bars)


def test_loader_rejects_corrupted_raw_file(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    raw_path = fixture.manifest_path.parent / "raw" / "aapl-nas-ohlcv-daily.csv.gz"
    raw_path.write_bytes(raw_path.read_bytes() + b"corrupt")

    with pytest.raises(ValueError, match="raw file hash mismatch"):
        _load(fixture)


def test_loader_rejects_noncanonical_registry_scope(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    manifest = _read_mapping(fixture.manifest_path)
    manifest["registry"]["target_keys"] = list(reversed(manifest["registry"]["target_keys"]))
    fixture = _rewrite_manifest_and_evidence(fixture, manifest)

    with pytest.raises(ValueError, match="manifest is incompatible"):
        _load(fixture)


def test_loader_rejects_evidence_with_a_broken_cache_link(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    evidence = _read_mapping(fixture.evidence_path)
    evidence["cache_manifest"]["path"] = "not-the-verified-manifest"
    fixture = _rewrite_evidence(fixture, evidence)

    with pytest.raises(ValueError, match="evidence is incompatible"):
        _load(fixture)


def test_loader_is_offline_and_keeps_fixture_roots_outside_git(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("panel loader must not use this capability")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    panel = _load(fixture)

    assert panel.common_sessions
    source = inspect.getsource(panel_module).lower()
    for forbidden_name in ("urllib", "requests", "socket", "getenv", ".env", "orderintent"):
        assert forbidden_name not in source
    with pytest.raises(ValueError, match="outside Git"):
        _load_panel(
            cache_root=fixture.cache_root,
            evidence_root=fixture.evidence_root,
            identity=fixture.identity,
            repository_root=fixture.cache_root.parent,
        )
    assert (
        "repository_root"
        not in inspect.signature(load_frozen_kis_paper_daily_universe_panel).parameters
    )
    assert (
        "repository_root"
        not in inspect.signature(materialize_frozen_kis_paper_daily_universe_panel).parameters
    )


def test_materialization_is_raw_row_free_and_reusable(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    panel = _load(fixture)
    panel_root = fixture.cache_root.parent / "panel"
    artifact_root = fixture.cache_root.parent / "panel-artifacts"

    first = _materialize_panel(
        panel=panel,
        panel_root=panel_root,
        artifact_root=artifact_root,
        identity=fixture.identity,
        repository_root=fixture.repository_root,
    )
    second = _materialize_panel(
        panel=panel,
        panel_root=panel_root,
        artifact_root=artifact_root,
        identity=fixture.identity,
        repository_root=fixture.repository_root,
    )

    assert first.manifest_path == second.manifest_path
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.evidence_path == second.evidence_path
    assert first.evidence_sha256 == second.evidence_sha256
    assert "100.123" not in first.manifest_path.read_text(encoding="utf-8")
    assert "100.123" not in first.evidence_path.read_text(encoding="utf-8")
    assert {path.name for path in artifact_root.rglob("*") if path.is_file()} == {"evidence.json"}
    with pytest.raises(ValueError, match="outside Git"):
        _materialize_panel(
            panel=panel,
            panel_root=fixture.repository_root / "forbidden-panel",
            artifact_root=artifact_root,
            identity=fixture.identity,
            repository_root=fixture.repository_root,
        )
    assert not (fixture.repository_root / "forbidden-panel").exists()
    with pytest.raises(ValueError, match="must not overlap its source"):
        _materialize_panel(
            panel=panel,
            panel_root=panel.cache_manifest_path.parent,
            artifact_root=artifact_root,
            identity=fixture.identity,
            repository_root=fixture.repository_root,
        )
    rejected_panel_root = panel.cache_manifest_path.parent / "rejected-panel-output"
    with pytest.raises(ValueError, match="must not overlap its source"):
        _materialize_panel(
            panel=panel,
            panel_root=rejected_panel_root,
            artifact_root=artifact_root,
            identity=fixture.identity,
            repository_root=fixture.repository_root,
        )
    assert not rejected_panel_root.exists()
    with pytest.raises(ValueError, match="must not overlap its source"):
        _materialize_panel(
            panel=panel,
            panel_root=panel_root,
            artifact_root=panel.evidence_path.parent,
            identity=fixture.identity,
            repository_root=fixture.repository_root,
        )
    rejected_evidence_root = panel.evidence_path.parent / "rejected-evidence-output"
    with pytest.raises(ValueError, match="must not overlap its source"):
        _materialize_panel(
            panel=panel,
            panel_root=panel_root,
            artifact_root=rejected_evidence_root,
            identity=fixture.identity,
            repository_root=fixture.repository_root,
        )
    assert not rejected_evidence_root.exists()


def test_completed_bar_adapter_exposes_only_a_cataloged_local_paper_input(
    tmp_path: Path,
) -> None:
    panel = _load(_fixture(tmp_path))
    input = prepare_kis_paper_daily_universe_completed_bar_input(panel, symbol="aapl")

    assert input.symbol == "AAPL"
    assert input.cataloged_bars is panel.validation_series("AAPL")
    assert input.local_paper_only is True
    assert input.paper_trading_eligible is False
    assert "100.123" not in json.dumps(input.safe_payload(), sort_keys=True)
    with pytest.raises(ValueError, match="unsupported"):
        prepare_kis_paper_daily_universe_completed_bar_input(panel, symbol="SPY")
    forged = object.__new__(KisPaperDailyUniversePanel)
    with pytest.raises(ValueError, match="loader attestation"):
        prepare_kis_paper_daily_universe_completed_bar_input(forged, symbol="AAPL")

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    result = run_local_paper_validation(
        input.cataloged_bars,
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        config=ValidationConfig(run_id="daily-universe-local-paper"),
        data_source="six-symbol-panel-fixture",
    )
    fill_events = [event for event in store.iter_events() if event.event_type == "fill"]

    assert result.trades
    assert fill_events
    assert {event.payload["source"] for event in fill_events} == {"local_paper"}


def _load(fixture: _Fixture) -> KisPaperDailyUniversePanel:
    return _load_panel(
        cache_root=fixture.cache_root,
        evidence_root=fixture.evidence_root,
        identity=fixture.identity,
        repository_root=fixture.repository_root,
    )


def _fixture(root: Path) -> _Fixture:
    repository_root = root / "repo"
    repository_root.mkdir(parents=True, exist_ok=True)
    cache_root = root / "cache"
    evidence_root = root / "evidence"
    snapshot_name = "snapshot=fixture-daily-universe-probe-v1"
    evidence_run_name = "run=fixture"
    snapshot = cache_root / snapshot_name
    raw_root = snapshot / "raw"
    raw_root.mkdir(parents=True)
    target_keys = tuple(f"{symbol}/NAS" for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS)
    raw_documents: dict[str, dict[str, object]] = {}
    start = date(2026, 1, 1)
    for symbol_index, symbol in enumerate(NAS_COMMON_STOCK_PROBE_SYMBOLS):
        sessions = tuple(start + timedelta(days=index) for index in range(12))
        if symbol == "NVDA":
            sessions = tuple(
                session for session in sessions if session != start + timedelta(days=4)
            )
        payload = _gzip_rows(symbol=symbol, sessions=sessions, offset=symbol_index)
        file_name = f"{symbol.lower()}-nas-ohlcv-daily.csv.gz"
        (raw_root / file_name).write_bytes(payload)
        raw_documents[f"{symbol}/NAS"] = {
            "path": f"raw/{file_name}",
            "sha256": _sha256(payload),
            "size_bytes": len(payload),
            "format": "csv.gz",
            "ordering": "session_date_ascending",
            "columns": [
                "symbol",
                "exchange",
                "session_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        }
    manifest = {
        "schema_version": 1,
        "kind": "kis_paper_daily_universe_capability_probe",
        "immutable_snapshot": True,
        "dataset_id": f"kis.paper.private.daily.universe.{snapshot_name}",
        "registry": {
            "registry_sha256": "sha256:" + "a" * 64,
            "source_manifest_sha256": "sha256:" + "b" * 64,
            "source_file_sha256": "sha256:" + "c" * 64,
            "target_keys": list(target_keys),
            "prospective_only": True,
            "historical_point_in_time_eligible": False,
        },
        "source": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "adjustment_mode": KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
            "account_or_order_endpoints_used": False,
        },
        "targets": [
            {"target_key": target_key, "classification": "accepted"} for target_key in target_keys
        ],
        "files": {"raw_daily_rows": raw_documents},
    }
    manifest_path = snapshot / "manifest.json"
    _write_json(manifest_path, manifest)
    manifest_sha256 = _sha256(manifest_path.read_bytes())
    evidence_path = evidence_root / evidence_run_name / "evidence.json"
    evidence = _evidence_document(
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        target_keys=target_keys,
        registry=manifest["registry"],
    )
    _write_json(evidence_path, evidence)
    return _Fixture(
        cache_root=cache_root,
        evidence_root=evidence_root,
        repository_root=repository_root,
        manifest_path=manifest_path,
        evidence_path=evidence_path,
        identity=_identity(
            snapshot_name=snapshot_name,
            evidence_run_name=evidence_run_name,
            manifest_sha256=manifest_sha256,
            evidence_sha256=_sha256(evidence_path.read_bytes()),
            registry=manifest["registry"],
            target_keys=target_keys,
        ),
    )


def _gzip_rows(*, symbol: str, sessions: tuple[date, ...], offset: int) -> bytes:
    contents = io.StringIO(newline="")
    writer = csv.DictWriter(
        contents,
        fieldnames=(
            "symbol",
            "exchange",
            "session_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for index, session in enumerate(sessions):
        open_value = 100 + offset + index
        writer.writerow(
            {
                "symbol": symbol,
                "exchange": "NAS",
                "session_date": session.isoformat(),
                "open": str(open_value),
                "high": str(open_value + 2),
                "low": str(open_value - 1),
                "close": f"{open_value + 0.123:.3f}",
                "volume": str(1000 + index),
            }
        )
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as handle:
        handle.write(contents.getvalue().encode("utf-8"))
    return compressed.getvalue()


def _rewrite_manifest_and_evidence(
    fixture: _Fixture,
    manifest: dict[str, object],
) -> _Fixture:
    _write_json(fixture.manifest_path, manifest)
    manifest_sha256 = _sha256(fixture.manifest_path.read_bytes())
    evidence = _read_mapping(fixture.evidence_path)
    evidence["cache_manifest"]["sha256"] = manifest_sha256
    _write_json(fixture.evidence_path, evidence)
    return replace(
        fixture,
        identity=replace(
            fixture.identity,
            cache_manifest_sha256=manifest_sha256,
            evidence_sha256=_sha256(fixture.evidence_path.read_bytes()),
        ),
    )


def _rewrite_evidence(fixture: _Fixture, evidence: dict[str, object]) -> _Fixture:
    _write_json(fixture.evidence_path, evidence)
    return replace(
        fixture,
        identity=replace(
            fixture.identity,
            evidence_sha256=_sha256(fixture.evidence_path.read_bytes()),
        ),
    )


def _evidence_document(
    *,
    manifest_path: Path,
    manifest_sha256: str,
    target_keys: tuple[str, ...],
    registry: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_paper_daily_universe_capability_probe_evidence",
        "cache_manifest": {"path": str(manifest_path), "sha256": manifest_sha256},
        "registry": {
            "registry_sha256": registry["registry_sha256"],
            "source_manifest_sha256": registry["source_manifest_sha256"],
            "source_file_sha256": registry["source_file_sha256"],
            "target_keys": list(target_keys),
        },
        "targets": [
            {"target_key": target_key, "classification": "accepted"} for target_key in target_keys
        ],
        "redaction": {
            "raw_rows_persisted": False,
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "order_facts_persisted": False,
        },
    }


def _identity(
    *,
    snapshot_name: str,
    evidence_run_name: str,
    manifest_sha256: str,
    evidence_sha256: str,
    registry: dict[str, object],
    target_keys: tuple[str, ...],
) -> _FrozenPanelIdentity:
    return _FrozenPanelIdentity(
        snapshot_name=snapshot_name,
        evidence_run_name=evidence_run_name,
        panel_snapshot_name="panel=fixture",
        cache_manifest_sha256=manifest_sha256,
        evidence_sha256=evidence_sha256,
        registry_sha256=str(registry["registry_sha256"]),
        source_manifest_sha256=str(registry["source_manifest_sha256"]),
        source_file_sha256=str(registry["source_file_sha256"]),
        target_keys=target_keys,
    )


def _read_mapping(path: Path) -> dict[str, object]:
    result = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(result, dict)
    return result


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
