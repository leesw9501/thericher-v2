from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from thericher_v2.data import norgate_trial_host_readiness_reconciliation as reconciliation
from thericher_v2.data.norgate_host_readiness_bridge import (
    NorgateHostReadiness,
    build_norgate_host_readiness_receipt,
)


class _NotReadyClient:
    def __init__(self) -> None:
        self.status_calls = 0
        self.catalog_calls = 0
        self.metadata_calls = 0
        self.raw_accessed = False

    def status(self) -> bool:
        self.status_calls += 1
        return False

    def databases(self) -> list[str]:
        self.catalog_calls += 1
        raise AssertionError("not-ready reconciliation must not inspect a catalog")

    def last_database_update_time(self, _database: str) -> datetime:
        self.metadata_calls += 1
        raise AssertionError("not-ready reconciliation must not inspect metadata")

    @property
    def price_timeseries(self) -> Any:
        self.raw_accessed = True
        raise AssertionError("reconciliation must not access raw prices")


class _ReadyClient:
    def __init__(self, update_at: datetime) -> None:
        self._update_at = update_at
        self.status_calls = 0
        self.catalog_calls = 0
        self.metadata_calls = 0
        self.raw_accessed = False

    def status(self) -> bool:
        self.status_calls += 1
        return True

    def databases(self) -> list[str]:
        self.catalog_calls += 1
        return ["US Equities"]

    def last_database_update_time(self, _database: str) -> datetime:
        self.metadata_calls += 1
        return self._update_at

    @property
    def price_timeseries(self) -> Any:
        self.raw_accessed = True
        raise AssertionError("reconciliation must not access raw prices")


def test_not_ready_diagnosis_binds_prior_before_safe_updater_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior_root, prior_source, repo_root = _prior_receipt(tmp_path)
    client = _NotReadyClient()
    events: list[str] = []
    original_reader = reconciliation.read_norgate_host_readiness_receipt

    def ordered_reader(**kwargs: object) -> object:
        events.append("reader")
        return original_reader(**kwargs)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("reconciliation must not create a network connection")

    monkeypatch.setattr(
        reconciliation, "read_norgate_host_readiness_receipt", ordered_reader
    )
    monkeypatch.setattr(socket, "create_connection", fail_network)

    diagnosis = reconciliation.diagnose_norgate_trial_host_readiness(
        prior_receipt_source=prior_source,
        prior_receipt_root=prior_root,
        client_loader=lambda: _event_client(events, client),
        updater_installation_marker_probe=lambda: _event_marker(
            events, "installation", "not_observed"
        ),
        updater_process_probe=lambda: _event_marker(
            events, "process", "not_observed"
        ),
        repo_root=repo_root,
    )

    assert events == ["reader", "loader", "installation", "process"]
    assert diagnosis.reason == "local_api_not_ready_updater_not_observed"
    assert diagnosis.recovery == "ensure_norgate_data_updater_is_installed_and_running"
    assert diagnosis.local_api_status == "not_ready"
    assert diagnosis.updater_installation_marker_status == "not_observed"
    assert diagnosis.updater_process_status == "not_observed"
    assert client.status_calls == 1
    assert client.catalog_calls == 0
    assert client.metadata_calls == 0
    assert not client.raw_accessed
    serialized = json.dumps(diagnosis.safe_payload(), sort_keys=True)
    assert "private" not in serialized
    assert "price_timeseries" not in serialized


def test_import_failure_does_not_inspect_updater_markers(tmp_path: Path) -> None:
    prior_root, prior_source, repo_root = _prior_receipt(tmp_path)

    def unavailable_client() -> object:
        raise RuntimeError("private import detail")

    diagnosis = reconciliation.diagnose_norgate_trial_host_readiness(
        prior_receipt_source=prior_source,
        prior_receipt_root=prior_root,
        client_loader=unavailable_client,
        updater_installation_marker_probe=lambda: pytest.fail(
            "runtime import failure must stop before installation probing"
        ),
        updater_process_probe=lambda: pytest.fail(
            "runtime import failure must stop before process probing"
        ),
        repo_root=repo_root,
    )

    assert diagnosis.reason == "runtime_import_unavailable"
    assert diagnosis.module_import_status == "unavailable"
    assert diagnosis.local_api_status == "unavailable"


def test_ready_diagnosis_uses_only_catalog_metadata_and_root_presence(tmp_path: Path) -> None:
    prior_root, prior_source, repo_root = _prior_receipt(tmp_path)
    update_at = datetime(2026, 8, 20, 12, tzinfo=UTC)
    candidate = _metadata_root(tmp_path / "private-source-root", update_at)
    client = _ReadyClient(update_at)

    diagnosis = reconciliation.diagnose_norgate_trial_host_readiness(
        prior_receipt_source=prior_source,
        prior_receipt_root=prior_root,
        client_loader=lambda: client,
        updater_installation_marker_probe=lambda: pytest.fail(
            "ready reconciliation must not inspect an updater marker"
        ),
        updater_process_probe=lambda: pytest.fail(
            "ready reconciliation must not inspect an updater process"
        ),
        candidate_roots=(candidate,),
        repo_root=repo_root,
    )

    assert diagnosis.reason == "ready_for_date_indexed_probe"
    assert diagnosis.status == "ready"
    assert client.status_calls == 1
    assert client.catalog_calls == 1
    assert client.metadata_calls == 1
    assert not client.raw_accessed
    assert "private-source-root" not in json.dumps(diagnosis.safe_payload())


def test_receipt_is_external_idempotent_and_validation_is_offline(tmp_path: Path) -> None:
    prior_root, prior_source, repo_root = _prior_receipt(tmp_path)
    artifact_root = tmp_path / "external-artifacts"
    retrieved_at = datetime(2026, 8, 20, tzinfo=UTC)

    first = reconciliation.run_norgate_trial_host_readiness_reconciliation(
        run_label="unit-r1",
        retrieved_at_utc=retrieved_at,
        prior_receipt_source=prior_source,
        prior_receipt_root=prior_root,
        artifact_root=artifact_root,
        client_loader=_NotReadyClient,
        updater_installation_marker_probe=lambda: "not_observed",
        updater_process_probe=lambda: "not_observed",
        repo_root=repo_root,
    )
    second = reconciliation.run_norgate_trial_host_readiness_reconciliation(
        run_label="unit-r1",
        retrieved_at_utc=retrieved_at,
        prior_receipt_source=prior_source,
        prior_receipt_root=prior_root,
        artifact_root=artifact_root,
        client_loader=_NotReadyClient,
        updater_installation_marker_probe=lambda: "not_observed",
        updater_process_probe=lambda: "not_observed",
        repo_root=repo_root,
    )
    validation = reconciliation.validate_norgate_trial_host_readiness_reconciliation(
        run_label="unit-r1",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    document = first.summary_path.read_text(encoding="ascii")
    assert first.summary_path == artifact_root / "diagnosis-unit-r1.json"
    assert first.summary_sha256 == second.summary_sha256 == validation.summary_sha256
    assert validation.prior_receipt_sha256 == first.diagnosis.prior_receipt_sha256
    assert "external-artifacts" not in document
    assert "credentials_read\": false" in document
    assert "raw_market_data_read\": false" in document
    assert "paths_or_configuration_values_retained\": false" in document


def test_reconciliation_rejects_git_artifacts_and_tampered_summary(tmp_path: Path) -> None:
    prior_root, prior_source, repo_root = _prior_receipt(tmp_path)

    with pytest.raises(ValueError, match="outside Git"):
        reconciliation.run_norgate_trial_host_readiness_reconciliation(
            run_label="unit-r1",
            retrieved_at_utc=datetime(2026, 8, 20, tzinfo=UTC),
            prior_receipt_source=prior_source,
            prior_receipt_root=prior_root,
            artifact_root=repo_root / "artifacts",
            client_loader=_NotReadyClient,
            updater_installation_marker_probe=lambda: "not_observed",
            updater_process_probe=lambda: "not_observed",
            repo_root=repo_root,
        )

    artifact_root = tmp_path / "external-artifacts"
    receipt = reconciliation.run_norgate_trial_host_readiness_reconciliation(
        run_label="unit-r1",
        retrieved_at_utc=datetime(2026, 8, 20, tzinfo=UTC),
        prior_receipt_source=prior_source,
        prior_receipt_root=prior_root,
        artifact_root=artifact_root,
        client_loader=_NotReadyClient,
        updater_installation_marker_probe=lambda: "not_observed",
        updater_process_probe=lambda: "not_observed",
        repo_root=repo_root,
    )
    receipt.summary_path.write_text("{}", encoding="ascii")

    with pytest.raises(ValueError, match="schema"):
        reconciliation.validate_norgate_trial_host_readiness_reconciliation(
            run_label="unit-r1",
            artifact_root=artifact_root,
            repo_root=repo_root,
        )


def test_module_has_no_direct_network_credential_or_execution_import() -> None:
    source = Path(reconciliation.__file__).read_text(encoding="utf-8")

    for prohibited in (
        "import socket",
        "import requests",
        "thericher_v2.execution",
        ".env",
    ):
        assert prohibited not in source


def _prior_receipt(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    prior_root = tmp_path / "prior-receipts"
    readiness = NorgateHostReadiness(
        status="input_unavailable",
        reason="local_api_not_ready",
        host_runtime_status="available",
        local_api_status="not_ready",
        us_equities_catalog_status="not_checked",
        source_update_metadata_status="not_checked",
        active_root_resolution="not_checked",
    )
    receipt = build_norgate_host_readiness_receipt(
        destination="bridge-prior.json",
        readiness=readiness,
        retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
        artifact_root=prior_root,
        repo_root=repo_root,
    )
    return prior_root, receipt.receipt_path, repo_root


def _event_client(events: list[str], client: _NotReadyClient) -> _NotReadyClient:
    events.append("loader")
    return client


def _event_marker(events: list[str], name: str, result: str) -> str:
    events.append(name)
    return result


def _metadata_root(root: Path, timestamp: datetime) -> Path:
    root.mkdir()
    marker = root / "core_us.ngdb"
    marker.write_bytes(b"metadata-only")
    os.utime(marker, (timestamp.timestamp(), timestamp.timestamp()))
    return root
