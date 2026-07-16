from __future__ import annotations

import csv
import gzip
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data.agent import (
    RUNNER_EMPTY_QUEUE,
    SUPPORTED_DATA_JOB_KINDS,
    _exit_code_for,
    claim_next_job,
    enqueue_data_job,
    resolve_data_agent_root,
    run_once,
)
from thericher_v2.research.engine_research_agent import (
    resolve_agent_root as resolve_engine_agent_root,
)


def test_enqueue_data_job_writes_external_queue_item(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market-data"

    queue_path = enqueue_data_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="unit-inventory",
        market_data_root=market_data_root,
        queued_at=datetime(2026, 1, 2, tzinfo=UTC),
        reason="unit bounded inventory",
    )

    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue_path == artifact_root / "data-agent" / "queue" / "unit-inventory.json"
    assert payload["agent"] == "data_agent"
    assert payload["status"] == "queued"
    assert payload["kind"] == "market_data_inventory"
    assert payload["market_data_root"] == str(market_data_root)
    assert payload["execution"]["one_job_per_invocation"] is True
    assert payload["execution"]["docker_required"] is False
    assert payload["execution"]["gpu_required"] is False
    assert payload["artifact_policy"]["artifact_owner"] == "data_agent"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["boundaries"]["credential_read"] is False
    assert payload["boundaries"]["broker_submit"] is False
    assert payload["boundaries"]["writes_market_data"] is False

    with pytest.raises(ValueError, match="outside the Git workspace"):
        enqueue_data_job(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            job_id="bad-repo-artifact",
            market_data_root=market_data_root,
        )


def test_claim_next_data_job_is_deterministic_by_queue_filename(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market-data"
    enqueue_data_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="b-job",
        market_data_root=market_data_root,
    )
    enqueue_data_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="a-job",
        market_data_root=market_data_root,
    )

    claim = claim_next_job(artifact_root / "data-agent")

    assert claim is not None
    assert claim.spec.job_id == "a-job"
    assert claim.claimed_job_path.exists()
    assert not (artifact_root / "data-agent" / "queue" / "a-job.json").exists()
    assert (artifact_root / "data-agent" / "queue" / "b-job.json").exists()


def test_data_agent_run_once_records_bounded_inventory_and_is_single_shot(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market-data"
    snapshot = _write_yahoo_intraday_snapshot(market_data_root, symbols=("AAA", "BBB"))
    enqueue_data_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="unit-inventory-run",
        market_data_root=market_data_root,
    )

    first = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    second = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert first.status == "completed"
    assert first.status_artifact is not None
    assert first.status_artifact.exists()
    assert first.inventory_artifact is not None
    assert first.inventory_artifact.exists()
    assert second.status == "queue_empty"
    assert _exit_code_for(second.status) == RUNNER_EMPTY_QUEUE
    assert not (artifact_root / "data-agent" / "queue" / "unit-inventory-run.json").exists()

    inventory_payload = json.loads(first.inventory_artifact.read_text(encoding="utf-8"))
    useful_file = inventory_payload["inventory"]["useful_files"][0]
    assert inventory_payload["status"] == "market_data_inventory_recorded"
    assert inventory_payload["artifact_policy"]["repo_storage_allowed"] is False
    assert inventory_payload["boundaries"]["network"] is False
    assert inventory_payload["boundaries"]["writes_market_data"] is False
    assert inventory_payload["result_scope"]["mode"] == "data_collection_inventory_only"
    assert inventory_payload["result_scope"]["blocks_research"] is False
    assert inventory_payload["inventory"]["root_exists"] is True
    assert inventory_payload["inventory"]["snapshot_count"] == 1
    assert inventory_payload["inventory"]["useful_file_count"] == 1
    assert useful_file["path"] == str(snapshot)
    assert useful_file["sampled_symbol_count"] == 2
    assert useful_file["sampled_symbols"] == ["AAA", "BBB"]
    assert useful_file["sample_scope"]["mode"] == "bounded_head_sample"

    status_payload = json.loads(first.status_artifact.read_text(encoding="utf-8"))
    assert status_payload["inventory_artifact"] == str(first.inventory_artifact)
    assert status_payload["execution"]["docker_required"] is False
    assert status_payload["execution"]["gpu_required"] is False


def test_data_agent_roots_are_disjoint_from_engine_research_agent(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"

    assert resolve_data_agent_root(artifact_root) == artifact_root / "data-agent"
    assert resolve_engine_agent_root(artifact_root) == artifact_root / "engine-research-agent"
    assert resolve_data_agent_root(artifact_root) != resolve_engine_agent_root(artifact_root)


def test_data_agent_rejects_unsafe_roots_and_unknown_kind(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market-data"

    with pytest.raises(ValueError, match="unsupported Data Agent job kind"):
        enqueue_data_job(
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
            job_id="bad-kind",
            kind="deep_generic_agent_magic",
            market_data_root=market_data_root,
        )
    with pytest.raises(ValueError, match="market_data_root must be outside"):
        enqueue_data_job(
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
            job_id="repo-market-data",
            market_data_root=Path.cwd() / "market-data",
        )
    with pytest.raises(ValueError, match="artifact_root must not be inside"):
        enqueue_data_job(
            artifact_root=market_data_root / "artifacts",
            repo_root=Path.cwd(),
            job_id="artifact-in-market-data",
            market_data_root=market_data_root,
        )
    with pytest.raises(ValueError, match="credential, KIS, or broker"):
        enqueue_data_job(
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
            job_id="bad-secret-root",
            market_data_root=tmp_path / "kis-secret-token-data",
        )

    assert SUPPORTED_DATA_JOB_KINDS == ("market_data_inventory",)
    assert not (artifact_root / "data-agent" / "queue").exists()


def test_data_agent_run_once_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Data Agent must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        lower_name = path.name.lower()
        if lower_name.startswith(".env") or "secret" in lower_name:
            raise AssertionError("Data Agent must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market-data"
    _write_yahoo_intraday_snapshot(market_data_root, symbols=("AAA",))
    enqueue_data_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="offline-inventory",
        market_data_root=market_data_root,
    )

    result = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert result.status == "completed"


def test_data_agent_does_not_write_under_market_data_root(monkeypatch, tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market-data"
    _write_yahoo_intraday_snapshot(market_data_root, symbols=("AAA",))
    enqueue_data_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="read-only-market-data",
        market_data_root=market_data_root,
    )
    original_write_text = Path.write_text

    def guard_write_text(path: Path, *args: object, **kwargs: object) -> int:
        resolved_path = path.resolve()
        resolved_market = market_data_root.resolve()
        if resolved_path == resolved_market or resolved_market in resolved_path.parents:
            raise AssertionError("Data Agent must not write under market_data_root")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guard_write_text)

    result = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert result.status == "completed"


def test_data_agent_module_imports_no_execution_or_dashboard_boundaries() -> None:
    source = Path("src/thericher_v2/data/agent.py").read_text(encoding="utf-8")

    assert "thericher_v2.execution" not in source
    assert "thericher_v2.dashboard" not in source
    assert "subprocess" not in source


def _write_yahoo_intraday_snapshot(
    market_data_root: Path,
    *,
    symbols: tuple[str, ...],
) -> Path:
    snapshot_dir = (
        market_data_root
        / "us_equities"
        / "yahoo_intraday_starter"
        / "canonical"
        / "ohlcv_1m"
        / "snapshot=2026-01-02"
    )
    snapshot_dir.mkdir(parents=True)
    path = snapshot_dir / "ohlcv_1m.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "timestamp_utc",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ),
        )
        writer.writeheader()
        for index, symbol in enumerate(symbols):
            writer.writerow(
                {
                    "timestamp_utc": f"2026-01-02T09:3{index}:00+00:00",
                    "symbol": symbol,
                    "open": "100",
                    "high": "101",
                    "low": "99",
                    "close": "100.5",
                    "volume": "1000",
                }
            )
    return path
