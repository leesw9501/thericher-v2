from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from thericher_v2.data.norgate_host_readiness_bridge import (
    NorgateHostReadiness,
    assess_norgate_host_readiness,
    build_norgate_host_readiness_receipt,
    read_norgate_host_readiness_receipt,
)


class _SafeClient:
    def __init__(
        self,
        *,
        status_ready: bool = True,
        databases: tuple[str, ...] = ("US Equities",),
        update_at: datetime | Exception = datetime(2026, 8, 18, 12, tzinfo=UTC),
    ) -> None:
        self._status_ready = status_ready
        self._databases = databases
        self._update_at = update_at
        self.catalog_calls = 0
        self.metadata_calls = 0
        self.raw_accessed = False

    def status(self) -> bool:
        return self._status_ready

    def databases(self) -> list[str]:
        self.catalog_calls += 1
        return list(self._databases)

    def last_database_update_time(self, _database: str) -> datetime:
        self.metadata_calls += 1
        if isinstance(self._update_at, Exception):
            raise self._update_at
        return self._update_at

    @property
    def price_timeseries(self) -> Any:
        self.raw_accessed = True
        raise AssertionError("bridge must not access price data")

    @property
    def watchlist_symbols(self) -> Any:
        self.raw_accessed = True
        raise AssertionError("bridge must not access membership data")

    @property
    def capital_event_timeseries(self) -> Any:
        self.raw_accessed = True
        raise AssertionError("bridge must not access corporate actions")


def test_ready_bridge_is_source_safe_and_resolves_one_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_at = datetime(2026, 8, 18, 12, tzinfo=UTC)
    active = _database_root(tmp_path / "private-active-root", update_at)
    stale = _database_root(tmp_path / "stale-root", update_at - timedelta(hours=1))
    client = _SafeClient(update_at=update_at)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Norgate bridge must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    readiness = assess_norgate_host_readiness(
        client_loader=lambda: client,
        candidate_roots=(stale, active),
    )

    assert readiness.safe_payload() == {
        "status": "ready",
        "reason": "ready",
        "host_runtime_status": "available",
        "local_api_status": "ready",
        "us_equities_catalog_status": "configured",
        "source_update_metadata_status": "available",
        "active_root_resolution": "one",
    }
    assert client.catalog_calls == 1
    assert client.metadata_calls == 1
    assert not client.raw_accessed


@pytest.mark.parametrize(
    ("host_runtime_available", "status_ready", "reason", "catalog_calls", "metadata_calls"),
    [
        (False, True, "host_runtime_unavailable", 0, 0),
        (True, False, "local_api_not_ready", 0, 0),
    ],
)
def test_unavailable_runtime_or_api_stops_before_catalog_or_raw_access(
    host_runtime_available: bool,
    status_ready: bool,
    reason: str,
    catalog_calls: int,
    metadata_calls: int,
) -> None:
    client = _SafeClient(status_ready=status_ready)

    readiness = assess_norgate_host_readiness(
        client_loader=lambda: client,
        host_runtime_available=host_runtime_available,
    )

    assert readiness.status == "input_unavailable"
    assert readiness.reason == reason
    assert client.catalog_calls == catalog_calls
    assert client.metadata_calls == metadata_calls
    assert not client.raw_accessed


@pytest.mark.parametrize(
    ("databases", "update_at", "expected_reason", "expected_root"),
    [
        ((), datetime(2026, 8, 18, 12, tzinfo=UTC), "us_equities_not_configured", "not_checked"),
        (
            ("US Equities",),
            RuntimeError("private client failure"),
            "source_update_metadata_unavailable",
            "not_checked",
        ),
    ],
)
def test_catalog_and_update_failures_are_categorical_only(
    databases: tuple[str, ...],
    update_at: datetime | Exception,
    expected_reason: str,
    expected_root: str,
) -> None:
    client = _SafeClient(databases=databases, update_at=update_at)

    readiness = assess_norgate_host_readiness(client_loader=lambda: client)

    assert readiness.status == "input_unavailable"
    assert readiness.reason == expected_reason
    assert readiness.active_root_resolution == expected_root
    assert not client.raw_accessed


def test_root_resolution_reports_multiple_without_retaining_candidate_paths(tmp_path: Path) -> None:
    update_at = datetime(2026, 8, 18, 12, tzinfo=UTC)
    first = _database_root(tmp_path / "confidential-first", update_at)
    second = _database_root(tmp_path / "confidential-second", update_at)
    readiness = assess_norgate_host_readiness(
        client_loader=lambda: _SafeClient(update_at=update_at),
        candidate_roots=(first, second),
    )

    assert readiness.status == "input_unavailable"
    assert readiness.reason == "active_root_ambiguous"
    assert readiness.active_root_resolution == "multiple"
    serialized = json.dumps(readiness.safe_payload(), sort_keys=True)
    assert "confidential" not in serialized


def test_receipt_is_external_idempotent_and_excludes_private_root(tmp_path: Path) -> None:
    update_at = datetime(2026, 8, 18, 12, tzinfo=UTC)
    candidate = _database_root(tmp_path / "private-norgate-root", update_at)
    readiness = assess_norgate_host_readiness(
        client_loader=lambda: _SafeClient(update_at=update_at),
        candidate_roots=(candidate,),
    )
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    retrieved_at = datetime(2026, 8, 19, tzinfo=UTC)

    first = build_norgate_host_readiness_receipt(
        destination="bridge-fixture.json",
        readiness=readiness,
        retrieved_at_utc=retrieved_at,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    second = build_norgate_host_readiness_receipt(
        destination="bridge-fixture.json",
        readiness=readiness,
        retrieved_at_utc=retrieved_at,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    document = first.receipt_path.read_text(encoding="utf-8")
    assert first.receipt_path == artifact_root / "bridge-fixture.json"
    assert first.receipt_sha256 == second.receipt_sha256
    assert first.safe_payload()["receipt_sha256"] == first.receipt_sha256
    assert (
        read_norgate_host_readiness_receipt(
            source=first.receipt_path,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
        == first
    )
    assert "private-norgate-root" not in document
    assert "price_timeseries" not in document
    assert "network_access\": false" in document
    assert "raw_market_data_read\": false" in document


def test_receipt_rejects_repository_artifact_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    readiness = NorgateHostReadiness(
        status="input_unavailable",
        reason="host_runtime_unavailable",
        host_runtime_status="unavailable",
        local_api_status="unavailable",
        us_equities_catalog_status="not_checked",
        source_update_metadata_status="not_checked",
        active_root_resolution="not_checked",
    )

    with pytest.raises(ValueError, match="outside Git"):
        build_norgate_host_readiness_receipt(
            destination="bridge-repo.json",
            readiness=readiness,
            retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
        )


def test_reader_rejects_tampered_receipt(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    receipt = artifact_root / "bridge-tampered.json"
    artifact_root.mkdir()
    receipt.write_text("{}", encoding="ascii")

    with pytest.raises(ValueError, match="schema"):
        read_norgate_host_readiness_receipt(source=receipt, artifact_root=artifact_root)


def _database_root(root: Path, timestamp: datetime) -> Path:
    root.mkdir()
    core = root / "core_us.ngdb"
    core.write_bytes(b"metadata-only")
    os.utime(core, (timestamp.timestamp(), timestamp.timestamp()))
    return root
