from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import socket
import subprocess
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.data.tiingo_norgate_cross_source_cohort as cohort
from thericher_v2.data.tiingo_norgate_cross_source_cohort import (
    CrossSourceCohortExpectation,
    build_tiingo_norgate_cross_source_cohort,
    load_verified_tiingo_norgate_cross_source_cohort,
    verify_tiingo_norgate_cross_source_cohort,
)

_START = date(2024, 1, 2)
_SYMBOLS = ("ALFA", "BRAVO", "CHARLIE")
_NORGATE_SESSIONS = 50
_FORWARD_SESSIONS = 4


def test_builds_compact_external_metadata_without_forbidden_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("cohort crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("cohort must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = build_tiingo_norgate_cross_source_cohort(
        tiingo_snapshot=fixture.tiingo_snapshot,
        norgate_snapshot=fixture.norgate_snapshot,
        artifact_root=fixture.artifact_root,
        market_data_root=fixture.market_data_root,
        repo_root=fixture.repo_root,
        expectation=fixture.expectation,
    )

    assert result.artifact_dir.is_relative_to(fixture.artifact_root)
    assert not result.artifact_dir.is_relative_to(fixture.repo_root)
    assert sorted(path.name for path in result.artifact_dir.iterdir()) == ["manifest.json"]
    assert (result.artifact_dir / "manifest.json").stat().st_size < 1_000_000
    assert result.rank_count == len(_SYMBOLS)
    assert result.overlap_session_count == _NORGATE_SESSIONS
    assert result.forward_only_session_count == _FORWARD_SESSIONS
    assert result.marker_count == 3
    assert result.excluded_decision_count == 26
    assert not hasattr(result, "bars")
    assert not hasattr(result, "features")
    assert not hasattr(result, "labels")
    assert not hasattr(result, "__iter__")

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert all(
        value is False
        for key, value in manifest["scope"].items()
        if key != "cross_source_engineering_evidence_only"
    )
    assert manifest["scope"]["cross_source_engineering_evidence_only"] is True
    assert all(value is False for value in manifest["access_boundary"].values())
    assert manifest["parents"]["tiingo"]["snapshot_relative_to_market_data_root"] == "tiingo"
    assert manifest["parents"]["norgate"]["snapshot_relative_to_market_data_root"] == "norgate"
    assert manifest["session_contract"]["forward_only_session_count"] == _FORWARD_SESSIONS
    assert manifest["session_contract"]["norgate_fields_in_forward_only_slice"] is False
    assert manifest["conservative_marker_mask"]["edge_censored_decision_indices"] == [
        *range(20),
        48,
        49,
    ]
    per_rank = manifest["conservative_marker_mask"]["per_rank"]
    assert per_rank[0]["excluded_decision_indices"] == list(range(23, 46))
    assert per_rank[1]["excluded_decision_indices"] == [45, 46, 47]
    assert per_rank[2]["forward_only_marker_session_indices"] == [50]
    assert "10.00" not in json.dumps(manifest)

    loaded = load_verified_tiingo_norgate_cross_source_cohort(
        result.artifact_dir,
        artifact_root=fixture.artifact_root,
        market_data_root=fixture.market_data_root,
        repo_root=fixture.repo_root,
        expectation=fixture.expectation,
    )
    assert loaded.manifest_hash == result.manifest_hash


def test_default_artifact_root_selects_docker_mount_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cohort, "_is_docker_runtime", lambda: True)

    assert cohort.default_tiingo_norgate_cross_source_cohort_dir() == Path(
        "/app/model_artifacts/tiingo-norgate-cross-source-cohort/"
        "tiingo-norgate-cross-source-cohort-r1"
    )
    assert cohort._market_data_root_or_default(None) == Path("/app/market_data")


def test_rejects_tampering_rank_mismatch_and_invalid_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = build_tiingo_norgate_cross_source_cohort(
        tiingo_snapshot=fixture.tiingo_snapshot,
        norgate_snapshot=fixture.norgate_snapshot,
        artifact_root=fixture.artifact_root,
        market_data_root=fixture.market_data_root,
        repo_root=fixture.repo_root,
        expectation=fixture.expectation,
    )

    manifest_path = result.artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scope"]["model_eligible"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="manifest is inconsistent"):
        verify_tiingo_norgate_cross_source_cohort(
            result.artifact_dir,
            artifact_root=fixture.artifact_root,
            market_data_root=fixture.market_data_root,
            repo_root=fixture.repo_root,
            expectation=fixture.expectation,
        )

    second = _fixture(tmp_path / "rank-mismatch", monkeypatch, tiingo_symbol_override="WRONG")
    with pytest.raises(ValueError, match="linkage"):
        build_tiingo_norgate_cross_source_cohort(
            tiingo_snapshot=second.tiingo_snapshot,
            norgate_snapshot=second.norgate_snapshot,
            artifact_root=second.artifact_root,
            market_data_root=second.market_data_root,
            repo_root=second.repo_root,
            expectation=second.expectation,
        )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        build_tiingo_norgate_cross_source_cohort(
            tiingo_snapshot=fixture.tiingo_snapshot,
            norgate_snapshot=fixture.norgate_snapshot,
            artifact_root=fixture.repo_root,
            market_data_root=fixture.market_data_root,
            repo_root=fixture.repo_root,
            expectation=fixture.expectation,
        )

    storage = _fixture(tmp_path / "storage", monkeypatch)
    with pytest.raises(ValueError, match="hard free-space floor"):
        build_tiingo_norgate_cross_source_cohort(
            tiingo_snapshot=storage.tiingo_snapshot,
            norgate_snapshot=storage.norgate_snapshot,
            artifact_root=storage.artifact_root,
            market_data_root=storage.market_data_root,
            repo_root=storage.repo_root,
            expectation=storage.expectation,
            disk_usage=lambda _path: SimpleNamespace(total=1_000_000, free=150_000),
        )


def test_rejects_unexpected_artifact_file_and_parent_hash_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = build_tiingo_norgate_cross_source_cohort(
        tiingo_snapshot=fixture.tiingo_snapshot,
        norgate_snapshot=fixture.norgate_snapshot,
        artifact_root=fixture.artifact_root,
        market_data_root=fixture.market_data_root,
        repo_root=fixture.repo_root,
        expectation=fixture.expectation,
    )
    (result.artifact_dir / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact files are invalid"):
        verify_tiingo_norgate_cross_source_cohort(
            result.artifact_dir,
            artifact_root=fixture.artifact_root,
            market_data_root=fixture.market_data_root,
            repo_root=fixture.repo_root,
            expectation=fixture.expectation,
        )

    (result.artifact_dir / "unexpected.txt").unlink()
    panel_path = fixture.norgate_snapshot / "panel_ohlcv_1d.csv.gz"
    panel_path.write_bytes(panel_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="Norgate cohort parent panel hash mismatch"):
        verify_tiingo_norgate_cross_source_cohort(
            result.artifact_dir,
            artifact_root=fixture.artifact_root,
            market_data_root=fixture.market_data_root,
            repo_root=fixture.repo_root,
            expectation=fixture.expectation,
        )


class _Fixture:
    def __init__(
        self,
        *,
        market_data_root: Path,
        repo_root: Path,
        artifact_root: Path,
        tiingo_snapshot: Path,
        norgate_snapshot: Path,
        expectation: CrossSourceCohortExpectation,
    ) -> None:
        self.market_data_root = market_data_root
        self.repo_root = repo_root
        self.artifact_root = artifact_root
        self.tiingo_snapshot = tiingo_snapshot
        self.norgate_snapshot = norgate_snapshot
        self.expectation = expectation


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tiingo_symbol_override: str | None = None,
) -> _Fixture:
    market_data_root = tmp_path / "market-data"
    market_data_root.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    tiingo_snapshot = market_data_root / "tiingo"
    norgate_snapshot = market_data_root / "norgate"
    tiingo_snapshot.mkdir()
    norgate_snapshot.mkdir()

    tiingo_data = _tiingo_csv(tiingo_symbol_override=tiingo_symbol_override)
    tiingo_hash = _sha256(tiingo_data)
    (tiingo_snapshot / "ohlcv_1d.csv.gz").write_bytes(tiingo_data)
    predecessor = market_data_root / "predecessor"
    predecessor.mkdir()
    tiingo_manifest = _tiingo_manifest(tiingo_hash, len(tiingo_data))
    tiingo_manifest_path = tiingo_snapshot / "manifest.json"
    _write_json(tiingo_manifest_path, tiingo_manifest)
    tiingo_manifest_hash = _sha256(tiingo_manifest_path.read_bytes())

    norgate_data = _norgate_csv()
    norgate_hash = _sha256(norgate_data)
    (norgate_snapshot / "panel_ohlcv_1d.csv.gz").write_bytes(norgate_data)
    availability = _availability_csv()
    availability_hash = _sha256(availability)
    (norgate_snapshot / "candidate_availability.csv").write_bytes(availability)
    norgate_manifest = _norgate_manifest(
        norgate_hash,
        len(norgate_data),
        availability_hash,
        len(availability),
    )
    norgate_manifest_path = norgate_snapshot / "manifest.json"
    _write_json(norgate_manifest_path, norgate_manifest)
    norgate_manifest_hash = _sha256(norgate_manifest_path.read_bytes())
    expectation = CrossSourceCohortExpectation(
        tiingo_dataset_hash=tiingo_hash,
        tiingo_manifest_hash=tiingo_manifest_hash,
        norgate_dataset_hash=norgate_hash,
        norgate_manifest_hash=norgate_manifest_hash,
        tiingo_available_rank_count=len(_SYMBOLS),
        tiingo_session_count=_NORGATE_SESSIONS + _FORWARD_SESSIONS,
        norgate_selected_rank_count=len(_SYMBOLS),
        norgate_session_count=_NORGATE_SESSIONS,
        forward_only_session_count=_FORWARD_SESSIONS,
    )

    monkeypatch.setattr(
        cohort,
        "verify_tiingo_daily_shard_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        cohort,
        "verify_norgate_trial_development_panel_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            dataset_hash=norgate_hash,
            manifest_hash=norgate_manifest_hash,
            selected_symbol_count=len(_SYMBOLS),
            common_session_count=_NORGATE_SESSIONS,
            development_training_eligible=True,
        ),
    )
    return _Fixture(
        market_data_root=market_data_root,
        repo_root=repo_root,
        artifact_root=artifact_root,
        tiingo_snapshot=tiingo_snapshot,
        norgate_snapshot=norgate_snapshot,
        expectation=expectation,
    )


def _tiingo_csv(*, tiingo_symbol_override: str | None) -> bytes:
    rows: list[dict[str, str]] = []
    for rank, original_symbol in enumerate(_SYMBOLS, start=1):
        symbol = tiingo_symbol_override if rank == 1 and tiingo_symbol_override else original_symbol
        for index in range(_NORGATE_SESSIONS + _FORWARD_SESSIONS):
            session = _START + timedelta(days=index)
            dividend = "1.00" if (rank, index) == (1, 25) else "0"
            split = "2" if (rank, index) == (2, 47) else "1"
            if (rank, index) == (3, 50):
                dividend = "1.00"
            rows.append(
                {
                    "candidate_rank": str(rank),
                    "candidate_symbol": symbol,
                    "request_identifier": symbol,
                    "date": session.isoformat(),
                    "open": "10.00",
                    "high": "11.00",
                    "low": "9.00",
                    "close": "10.00",
                    "volume": "100",
                    "div_cash": dividend,
                    "split_factor": split,
                }
            )
    return _gzip_csv(rows, list(cohort._TIINGO_COLUMNS))


def _norgate_csv() -> bytes:
    rows: list[dict[str, str]] = []
    for rank, symbol in enumerate(_SYMBOLS, start=1):
        for index in range(_NORGATE_SESSIONS):
            rows.append(
                {
                    "candidate_rank": str(rank),
                    "symbol": symbol,
                    "date": (_START + timedelta(days=index)).isoformat(),
                    "open": "10.00",
                    "high": "11.00",
                    "low": "9.00",
                    "close": "10.00",
                    "volume": "100",
                }
            )
    return _gzip_csv(rows, list(cohort._NORGATE_PANEL_COLUMNS))


def _availability_csv() -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(cohort._NORGATE_AVAILABILITY_COLUMNS))
    writer.writeheader()
    for rank, symbol in enumerate(_SYMBOLS, start=1):
        writer.writerow(
            {
                "candidate_rank": rank,
                "symbol": symbol,
                "status": "selected",
                "returned_row_count": _NORGATE_SESSIONS,
            }
        )
    return stream.getvalue().encode("utf-8")


def _gzip_csv(rows: list[dict[str, str]], fieldnames: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(stream.getvalue().encode("utf-8"), mtime=0)


def _tiingo_manifest(dataset_hash: str, size: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "tiingo_standard_eod_daily_pilot",
        "pilot_version": "tiingo-standard-eod-pilot-r2",
        "immutable_snapshot": True,
        "dataset_id": "test.tiingo.r2",
        "dataset_hash": dataset_hash,
        "scope": {
            "campaign_eligible": False,
            "gpu_eligible": False,
            "model_eligible": False,
            "paper_trading_eligible": False,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "files": {
            "canonical_raw_fields": {
                "path": "ohlcv_1d.csv.gz",
                "format": "csv.gz",
                "columns": list(cohort._TIINGO_COLUMNS),
                "ordering": "candidate_rank_then_date_ascending",
                "sha256": dataset_hash,
                "size_bytes": size,
            }
        },
        "aggregate": {"available": len(_SYMBOLS)},
        "predecessor": {
            "snapshot_dir": "D:\\market-data\\predecessor",
            "dataset_hash": "sha256:" + "a" * 64,
            "manifest_hash": "sha256:" + "b" * 64,
            "candidate_union_hash": "sha256:" + "c" * 64,
        },
        "raw_sources": [
            {
                "candidate_rank": rank,
                "candidate_symbol": symbol,
                "request_identifier": symbol,
                "classification": "available",
                "row_count": _NORGATE_SESSIONS + _FORWARD_SESSIONS,
            }
            for rank, symbol in enumerate(_SYMBOLS, start=1)
        ],
    }


def _norgate_manifest(
    dataset_hash: str, dataset_size: int, availability_hash: str, availability_size: int
) -> dict[str, object]:
    return {
        "dataset_id": "test.norgate.panel",
        "files": {
            "panel_ohlcv": {
                "path": "panel_ohlcv_1d.csv.gz",
                "format": "csv.gz",
                "columns": list(cohort._NORGATE_PANEL_COLUMNS),
                "sha256": dataset_hash,
                "size_bytes": dataset_size,
            },
            "candidate_availability": {
                "path": "candidate_availability.csv",
                "format": "csv",
                "columns": list(cohort._NORGATE_AVAILABILITY_COLUMNS),
                "sha256": availability_hash,
                "size_bytes": availability_size,
            },
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
