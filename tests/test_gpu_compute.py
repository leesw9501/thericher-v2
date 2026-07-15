from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.gpu_compute import (
    run_gpu_compute_smoke,
    write_gpu_compute_smoke_artifact,
)
from thericher_v2.research.validation import GpuReadiness


def test_gpu_compute_smoke_records_injected_success_outside_repo(tmp_path) -> None:
    result = run_gpu_compute_smoke(
        run_id="unit-gpu-compute",
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        tensor_runner=lambda: {
            "backend": "unit",
            "operation": "sum_of_squares",
            "result": "14.0000",
        },
    )

    artifact = write_gpu_compute_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "compute_ran_only"
    assert payload["compute_result"]["result"] == "14.0000"
    assert payload["candidate_experiment_id"] == "unit_candidate"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_gpu_compute_smoke_artifact(
            result,
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
        )


def test_gpu_compute_smoke_missing_backend_is_nonfatal(tmp_path) -> None:
    result = run_gpu_compute_smoke(
        run_id="missing-compute-backend",
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    artifact = write_gpu_compute_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] in {"compute_ran_only", "prepared_not_trained"}
    if payload["status"] == "prepared_not_trained":
        assert "backend" in payload["reason"]


def test_gpu_compute_smoke_missing_gpu_is_nonfatal(tmp_path) -> None:
    result = run_gpu_compute_smoke(
        run_id="missing-gpu-compute",
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    artifact = write_gpu_compute_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "prepared_not_trained"
    assert "GPU readiness unavailable" in payload["reason"]


def test_gpu_compute_smoke_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GPU compute smoke must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("GPU compute smoke must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_gpu_compute_smoke(
        run_id="offline-gpu-compute",
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        tensor_runner=lambda: {"backend": "unit", "result": "14.0000"},
    )
    artifact = write_gpu_compute_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    assert artifact.exists()


def test_base_engine_does_not_require_gpu_packages_for_compute_smoke() -> None:
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
