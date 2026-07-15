from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.gpu_runtime import (
    run_gpu_runtime_smoke,
    write_gpu_runtime_smoke_artifact,
)
from thericher_v2.research.validation import GpuReadiness


def test_gpu_runtime_smoke_writes_artifact_outside_repo(tmp_path) -> None:
    candidate_artifact = _candidate_artifact(tmp_path)
    result = run_gpu_runtime_smoke(
        run_id="unit-gpu-runtime",
        candidate_artifact=candidate_artifact,
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    artifact = write_gpu_runtime_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_ready_only"
    assert payload["candidate_experiment_id"] == "unit_candidate"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_gpu_runtime_smoke_artifact(
            result,
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
        )


def test_gpu_runtime_missing_gpu_records_nonfatal_prepared_state(tmp_path) -> None:
    result = run_gpu_runtime_smoke(
        run_id="missing-gpu-runtime",
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    artifact = write_gpu_runtime_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "prepared_not_trained"
    assert "unavailable" in payload["reason"]


def test_gpu_runtime_smoke_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GPU runtime smoke must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("GPU runtime smoke must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_gpu_runtime_smoke(
        run_id="offline-gpu-runtime",
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )
    artifact = write_gpu_runtime_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    assert artifact.exists()


def test_base_engine_does_not_require_gpu_packages_for_runtime_smoke() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()

    assert "torch" not in pyproject
    assert "tensorflow" not in pyproject
    assert "cupy" not in pyproject


def _candidate_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
            }
        ),
        encoding="utf-8",
    )
    return path
