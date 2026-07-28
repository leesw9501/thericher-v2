from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import socket
import urllib.request
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from thericher_v2.data import kis_paper_daily_history_panel as panel


def test_materializes_reusable_source_local_panel_without_external_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root = _write_history_cache(tmp_path / "cache")
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    panel_root = tmp_path / "panel"
    artifact_root = tmp_path / "artifacts"
    _deny_external_access(monkeypatch)

    result = panel.materialize_kis_paper_daily_history_panel(
        cache_root=cache_root,
        panel_root=panel_root,
        artifact_root=artifact_root,
        repo_root=repository_root,
    )
    rebuilt = panel.load_materialized_kis_paper_daily_history_panel(
        result.manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repository_root,
    )
    repeated = panel.materialize_kis_paper_daily_history_panel(
        cache_root=cache_root,
        panel_root=panel_root,
        artifact_root=artifact_root,
        repo_root=repository_root,
    )

    assert result.panel.dataset_id == panel.KIS_PAPER_DAILY_HISTORY_PANEL_ID
    assert result.panel.common_intersection_available is True
    assert len(result.panel.common_sessions) == 3
    assert tuple(result.panel.bars_by_symbol) == panel.KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    assert result.panel.targets_by_key["META/NAS"].state == "source_limited"
    assert result.panel.targets_by_key["META/NAS"].last_reason == "no_cursor_progress"
    assert rebuilt.dataset_hash == result.panel.dataset_hash
    assert repeated.manifest_path == result.manifest_path
    assert repeated.receipt_hash == result.receipt_hash
    assert result.manifest_path.is_relative_to(panel_root)
    assert result.receipt_path.is_relative_to(artifact_root)
    assert not result.manifest_path.is_relative_to(repository_root)
    assert not result.receipt_path.is_relative_to(repository_root)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert manifest["common_intersection"]["exact_session_alignment_verified"] is True
    assert manifest["eligibility"]["ranking"] is False
    assert receipt["artifact_policy"]["network_accessed"] is False
    assert receipt["artifact_policy"]["kis_accessed"] is False
    for document in (manifest, receipt):
        _assert_no_raw_fields(document)
    assert not list(panel_root.rglob("*.csv"))
    assert not list(panel_root.rglob("*.csv.gz"))
    assert not list(artifact_root.rglob("*.csv"))
    assert not list(artifact_root.rglob("*.csv.gz"))
    assert not list(artifact_root.rglob("*.jsonl"))
    assert not list(artifact_root.rglob("*.sqlite"))
    assert not list(artifact_root.rglob("*.pt"))


def test_fails_closed_on_lineage_drift_and_does_not_fake_cross_symbol_alignment(
    tmp_path: Path,
) -> None:
    cache_root = _write_history_cache(tmp_path / "drift-cache")
    index = _read_json(cache_root / "index.json")
    raw_path = cache_root / str(index["targets"][0]["chunks"][0]["manifest_path"]).replace(
        "manifest.json", "rows.csv.gz"
    )
    raw_path.write_bytes(raw_path.read_bytes() + b"drift")

    with pytest.raises(ValueError, match="raw hash"):
        panel.build_kis_paper_daily_history_panel(cache_root=cache_root)

    misaligned_cache = _write_history_cache(
        tmp_path / "misaligned-cache",
        session_overrides={"MSFT": (date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 6))},
    )
    result = panel.build_kis_paper_daily_history_panel(cache_root=misaligned_cache)

    assert result.common_intersection_available is False
    assert result.common_sessions == ()
    assert all(stream.bars for stream in result.bars_by_symbol.values())


def test_rejects_mutable_outputs_and_paths_inside_git(tmp_path: Path) -> None:
    cache_root = _write_history_cache(tmp_path / "cache")
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    panel_root = tmp_path / "panel"
    artifact_root = tmp_path / "artifacts"
    result = panel.materialize_kis_paper_daily_history_panel(
        cache_root=cache_root,
        panel_root=panel_root,
        artifact_root=artifact_root,
        repo_root=repository_root,
    )
    result.manifest_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable"):
        panel.materialize_kis_paper_daily_history_panel(
            cache_root=cache_root,
            panel_root=panel_root,
            artifact_root=artifact_root,
            repo_root=repository_root,
        )
    with pytest.raises(ValueError, match="outside Git"):
        panel.materialize_kis_paper_daily_history_panel(
            cache_root=cache_root,
            panel_root=repository_root / "panel",
            artifact_root=artifact_root,
            repo_root=repository_root,
        )


def test_allows_only_a_mounted_repo_nested_market_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    mount_root = repository_root / "market_data"
    cache_root = mount_root / "daily-history"
    panel_root = mount_root / "daily-history-panel"
    cache_root.mkdir(parents=True)
    panel_root.mkdir()
    original_is_mount = Path.is_mount

    def is_mount(path: Path) -> bool:
        return path.resolve() == mount_root.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_mount)

    assert (
        panel._external_existing_root(  # noqa: SLF001
            cache_root,
            repository_root,
            "history cache",
        )
        == cache_root.resolve()
    )
    assert (
        panel._external_existing_root(  # noqa: SLF001
            panel_root,
            repository_root,
            "panel root",
        )
        == panel_root.resolve()
    )


def test_rejects_a_non_mount_repo_nested_market_data_root(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    cache_root = repository_root / "market_data" / "daily-history"
    repository_root.mkdir()
    cache_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="outside Git"):
        panel._external_existing_root(  # noqa: SLF001
            cache_root,
            repository_root,
            "history cache",
        )


def _write_history_cache(
    root: Path,
    *,
    session_overrides: Mapping[str, tuple[date, ...]] | None = None,
) -> Path:
    session_overrides = session_overrides or {}
    default_sessions = (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6))
    targets: list[dict[str, object]] = []
    for offset, symbol in enumerate(panel.KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        sessions = session_overrides.get(symbol, default_sessions)
        records = tuple(
            (
                symbol,
                "NAS",
                session.isoformat(),
                str(100 + offset + index),
                str(102 + offset + index),
                str(99 + offset + index),
                str(101 + offset + index),
                str(1000 + offset + index),
            )
            for index, session in enumerate(sessions)
        )
        snapshot = root / f"snapshot={symbol.lower()}"
        snapshot.mkdir(parents=True)
        raw_path = snapshot / "rows.csv.gz"
        raw_bytes = _gzip_rows(records)
        raw_path.write_bytes(raw_bytes)
        raw_hash = _sha256(raw_bytes)
        output_cursor = min(record[2] for record in records).replace("-", "")
        state = "source_limited" if symbol == "META" else "complete"
        reason = "no_cursor_progress" if state == "source_limited" else None
        manifest = {
            "kind": "kis_paper_private_daily_cache",
            "collector_objective_id": panel.KIS_PAPER_DAILY_HISTORY_CACHE_VERSION,
            "collector_version": panel.KIS_PAPER_DAILY_HISTORY_CACHE_VERSION,
            "source": {
                "symbol": symbol,
                "exchange": "NAS",
                "endpoint": "dailyprice",
                "adjustment_mode": "MODP=0_unadjusted",
            },
            "backfill": {
                "contract_version": panel.KIS_PAPER_DAILY_HISTORY_CACHE_VERSION,
                "cursor_strategy": "oldest_session_date_with_exact_overlap",
                "input_cursor_date": "20260724",
                "logical_cursor_persisted": True,
                "output_cursor_date": output_cursor,
                "target_key": f"{symbol}/NAS/MODP=0",
            },
            "files": {
                "raw_daily_rows": {
                    "path": "rows.csv.gz",
                    "format": "csv.gz",
                    "ordering": "session_date_ascending",
                    "columns": list(_raw_columns()),
                    "size_bytes": len(raw_bytes),
                    "sha256": raw_hash,
                }
            },
            "requests": {"accepted_pages": 1},
        }
        manifest_bytes = _json_bytes(manifest)
        manifest_path = snapshot / "manifest.json"
        manifest_path.write_bytes(manifest_bytes)
        targets.append(
            {
                "target_key": f"{symbol}/NAS",
                "symbol": symbol,
                "exchange": "NAS",
                "next_anchor_date": output_cursor,
                "state": state,
                "accepted_page_count": 1,
                "categorical_failure_count": int(state == "source_limited"),
                "last_reason": reason,
                "chunks": [
                    {
                        "outcome": "source_limited" if state == "source_limited" else "complete",
                        "input_cursor_date": "20260724",
                        "output_cursor_date": output_cursor,
                        "manifest_path": str(manifest_path.relative_to(root)),
                        "manifest_sha256": _sha256(manifest_bytes),
                        "raw_sha256": raw_hash,
                        "row_count": len(records),
                        "accepted_page_count": 1,
                        "exact_overlap_row_count": 0,
                        "row_fingerprints": {
                            record[2]: _sha256("\x1f".join(record)) for record in records
                        },
                        "stop_outcome": "source_exhausted",
                    }
                ],
            }
        )
    _write_json(
        root / "index.json",
        {
            "schema_version": 1,
            "kind": "kis_paper_daily_nas_history_index",
            "version": panel.KIS_PAPER_DAILY_HISTORY_CACHE_VERSION,
            "initial_anchor_date": "20260724",
            "terminal_date": "19900101",
            "generation": 1,
            "registry": panel._SOURCE_REGISTRY,  # noqa: SLF001
            "targets": targets,
            "storage": panel._INDEX_STORAGE,  # noqa: SLF001
            "redaction": panel._INDEX_REDACTION,  # noqa: SLF001
        },
    )
    return root


def _gzip_rows(records: tuple[tuple[str, ...], ...]) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(_raw_columns())
    writer.writerows(records)
    result = io.BytesIO()
    with gzip.GzipFile(fileobj=result, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(text.getvalue().encode("utf-8"))
    return result.getvalue()


def _raw_columns() -> tuple[str, ...]:
    return (
        "symbol",
        "exchange",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("history panel materialization must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_raw_fields(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_fields(nested)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(payload))


def _read_json(path: Path) -> dict[str, object]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise AssertionError("fixture JSON is invalid")
    return result


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")


def _sha256(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(payload).hexdigest()
