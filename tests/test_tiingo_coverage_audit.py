from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.data.tiingo_daily_pilot as tiingo_daily_pilot
from thericher_v2.data.tiingo_coverage_audit import (
    TiingoDailyCoverageAuditInputs,
    default_tiingo_daily_coverage_audit_dir,
    run_tiingo_daily_coverage_audit,
)
from thericher_v2.data.tiingo_daily_pilot import (
    acquire_tiingo_daily_pilot,
    acquire_tiingo_daily_shard,
)

_START = date(2024, 7, 18)
_END = date(2026, 7, 17)


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_offline_audit_is_aggregate_only_and_does_not_need_secrets_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, artifact_root, repo = _snapshots(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline audit must not cross this boundary")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(tiingo_daily_pilot, "read_tiingo_api_token", fail)
    result = _audit(inputs=inputs, artifact_root=artifact_root, repo=repo)

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    rendered = result.summary_path.read_text(encoding="utf-8")
    assert result.summary_path.is_relative_to(artifact_root)
    assert not result.summary_path.is_relative_to(repo)
    assert result.r1_common_session_count == 1
    assert result.r2_common_session_count == 2
    assert result.combined_common_session_count == 1
    assert result.existing_reference_window_candidate_count == 59
    assert summary["snapshots"]["r2"]["common_session_count"] == 2
    assert summary["combined"]["common_session_count"] == 1
    assert summary["combined"]["r1_is_binding_common_window"] is True
    assert summary["existing_window_filter"]["candidate_identifiers_persisted"] is False
    assert summary["recommendation"]["decision"] == (
        "defer_third_shard_for_existing_window_filter_analysis"
    )
    scope = summary["scope"]
    assert all(value is False for key, value in scope.items() if key.endswith("eligible"))
    assert "SYMBOL0001" not in rendered
    assert "raw-value-external-only" not in rendered
    assert "test-tiingo-token" not in rendered
    assert "must-not-be-used" not in rendered


def test_offline_audit_rejects_attested_hash_tampering(tmp_path: Path) -> None:
    inputs, artifact_root, repo = _snapshots(tmp_path)
    manifest = inputs.r1_snapshot_dir / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        _audit(inputs=inputs, artifact_root=artifact_root, repo=repo)
    assert not list(artifact_root.rglob("summary.json"))


def test_offline_audit_rejects_retention_marker_tampering(tmp_path: Path) -> None:
    inputs, artifact_root, repo = _snapshots(tmp_path)
    (inputs.r1_snapshot_dir / "TIINGO_PRIVATE_INTERNAL_DATA_MARKER.txt").write_text(
        "tampered\n", encoding="ascii"
    )

    with pytest.raises(ValueError, match="retention marker"):
        _audit(inputs=inputs, artifact_root=artifact_root, repo=repo)
    assert not list(artifact_root.rglob("summary.json"))


def test_offline_audit_rejects_git_artifact_root(tmp_path: Path) -> None:
    inputs, _artifact_root, repo = _snapshots(tmp_path)

    with pytest.raises(ValueError, match="artifact root must stay outside Git"):
        run_tiingo_daily_coverage_audit(
            inputs=inputs,
            destination=repo / "snapshot=2026-07-19-tiingo-daily-coverage-audit-r1",
            audited_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
            artifact_root=repo,
            market_data_root=inputs.r1_snapshot_dir.parents[1],
            repo_root=repo,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
        )


def test_default_audit_destination_uses_external_artifact_root() -> None:
    assert default_tiingo_daily_coverage_audit_dir(date(2026, 7, 19)) == Path(
        "D:/thericher-v2/model-artifacts/data-agent/tiingo-daily-coverage-audit/"
        "snapshot=2026-07-19-tiingo-daily-coverage-audit-r1"
    )


def _audit(
    *,
    inputs: TiingoDailyCoverageAuditInputs,
    artifact_root: Path,
    repo: Path,
):
    return run_tiingo_daily_coverage_audit(
        inputs=inputs,
        destination=artifact_root
        / "data-agent"
        / "snapshot=2026-07-19-tiingo-daily-coverage-audit-r1",
        audited_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        artifact_root=artifact_root,
        market_data_root=inputs.r1_snapshot_dir.parents[1],
        repo_root=repo,
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )


def _snapshots(tmp_path: Path) -> tuple[TiingoDailyCoverageAuditInputs, Path, Path]:
    market_data_root, candidate_path, manifest_path, candidate_hash, repo = _candidate_union(
        tmp_path
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "KIS_PAPER_APP_SECRET=must-not-be-used\nTIINGO_API_TOKEN=test-tiingo-token\n",
        encoding="utf-8",
    )
    r1_calls = 0

    def r1_opener(_request: object, *, timeout: float) -> _Response:
        nonlocal r1_calls
        assert timeout > 0
        r1_calls += 1
        return _Response(_payload(short=r1_calls == 1))

    r1 = acquire_tiingo_daily_pilot(
        candidate_union_path=candidate_path,
        candidate_union_manifest_path=manifest_path,
        expected_candidate_union_hash=candidate_hash,
        env_path=env_path,
        destination=market_data_root
        / "pilot"
        / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r1",
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        sample_size=30,
        market_data_root=market_data_root,
        repo_root=repo,
        opener=r1_opener,
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    r2 = acquire_tiingo_daily_shard(
        candidate_union_path=candidate_path,
        candidate_union_manifest_path=manifest_path,
        expected_candidate_union_hash=candidate_hash,
        predecessor_snapshot_dir=r1.snapshot_dir,
        expected_predecessor_dataset_hash=r1.dataset_hash,
        expected_predecessor_manifest_hash=r1.manifest_hash,
        env_path=env_path,
        destination=market_data_root
        / "pilot"
        / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r2",
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, 1, tzinfo=UTC),
        market_data_root=market_data_root,
        repo_root=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    return (
        TiingoDailyCoverageAuditInputs(
            r1_snapshot_dir=r1.snapshot_dir,
            r1_dataset_hash=r1.dataset_hash,
            r1_manifest_hash=r1.manifest_hash,
            r2_snapshot_dir=r2.snapshot_dir,
            r2_dataset_hash=r2.dataset_hash,
            r2_manifest_hash=r2.manifest_hash,
            candidate_union_hash=candidate_hash,
        ),
        artifact_root,
        repo,
    )


def _candidate_union(tmp_path: Path) -> tuple[Path, Path, Path, str, Path]:
    market_data_root = tmp_path / "market_data"
    snapshot = market_data_root / "norgate" / "snapshot=fixture"
    snapshot.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate_path = snapshot / "candidate_union.csv"
    candidate_rows = "".join(f"{rank},SYMBOL{rank:04d}\n" for rank in range(1, 61))
    candidate_bytes = ("candidate_rank,symbol\n" + candidate_rows).encode("utf-8")
    candidate_path.write_bytes(candidate_bytes)
    candidate_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
    manifest_path = snapshot / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "norgate_sp500_current_past_membership_matrix",
                "candidate_count": 60,
                "scope": {
                    "direct_historical_universe_list": False,
                    "publication_time_proven": False,
                    "pit_eligible": False,
                    "campaign_eligible": False,
                    "model_eligible": False,
                },
                "files": {
                    "candidate_union": {
                        "path": candidate_path.name,
                        "sha256": candidate_hash,
                        "size_bytes": len(candidate_bytes),
                        "columns": ["candidate_rank", "symbol"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return market_data_root, candidate_path, manifest_path, candidate_hash, repo


def _payload(*, short: bool = False) -> bytes:
    rows = [
        {
            "date": "2024-07-18T00:00:00.000Z",
            "open": "99",
            "high": "102",
            "low": "98",
            "close": "100",
            "volume": "1000",
            "divCash": "0",
            "splitFactor": "1",
            "ignored_raw_value": "raw-value-external-only",
        }
    ]
    if not short:
        rows.append(
            {
                "date": "2024-07-19T00:00:00.000Z",
                "open": "100",
                "high": "103",
                "low": "99",
                "close": "101",
                "volume": "1001",
                "divCash": "0",
                "splitFactor": "1",
                "ignored_raw_value": "raw-value-external-only",
            }
        )
    return json.dumps(rows).encode("utf-8")
