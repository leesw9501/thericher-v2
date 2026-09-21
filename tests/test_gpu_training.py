from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.gpu_training import (
    run_gpu_training_smoke,
    write_gpu_training_smoke_artifact,
)
from thericher_v2.research.validation import GpuReadiness


def test_gpu_training_smoke_records_injected_success_outside_repo(tmp_path) -> None:
    result = run_gpu_training_smoke(
        run_id="unit-gpu-training",
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=lambda candidate: {
            "backend": "unit",
            "operation": "tiny_training_step",
            "initial_loss": "2.000000",
            "final_loss": "1.000000",
            "candidate_experiment_id": candidate["candidate_experiment_id"],
        },
    )

    artifact = write_gpu_training_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "training_ran_only"
    assert payload["training_result"]["final_loss"] == "1.000000"
    assert payload["training_result"]["candidate_experiment_id"] == "unit_candidate"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_gpu_training_smoke_artifact(
            result,
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
        )


def test_gpu_training_smoke_missing_backend_is_nonfatal(tmp_path) -> None:
    result = run_gpu_training_smoke(
        run_id="missing-training-backend",
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    artifact = write_gpu_training_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] in {"training_ran_only", "prepared_not_trained"}
    if payload["status"] == "prepared_not_trained":
        assert "backend" in payload["reason"] or "training smoke unavailable" in payload["reason"]


def test_gpu_training_smoke_missing_gpu_is_nonfatal(tmp_path) -> None:
    result = run_gpu_training_smoke(
        run_id="missing-gpu-training",
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    artifact = write_gpu_training_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "prepared_not_trained"
    assert "GPU readiness unavailable" in payload["reason"]


def test_gpu_training_smoke_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GPU training smoke must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("GPU training smoke must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_gpu_training_smoke(
        run_id="offline-gpu-training",
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=lambda candidate: {
            "backend": "unit",
            "result": "trained",
            "candidate_experiment_id": candidate["candidate_experiment_id"],
        },
    )
    artifact = write_gpu_training_smoke_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    assert artifact.exists()


def test_base_engine_does_not_require_gpu_packages_for_training_smoke() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    dependencies = pyproject.split("[project.optional-dependencies]", maxsplit=1)[0]

    assert "torch" not in dependencies
    assert "tensorflow" not in dependencies
    assert "cupy" not in dependencies


def test_torch_cuda_backend_is_research_stage_only() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    stages = _dockerfile_stages(dockerfile)

    assert "base" in stages
    assert "research" in stages
    assert "runtime" in stages
    assert "torch==" not in stages["base"].lower()
    assert "torch==" in stages["research"].lower()
    assert "download.pytorch.org/whl/cu128" in stages["research"]
    assert "torch==" not in stages["runtime"].lower()


def test_research_installs_pinned_torch_before_resolving_extras() -> None:
    research = _dockerfile_stages(Path("Dockerfile").read_text(encoding="utf-8"))["research"]

    assert "ARG PYTORCH_VERSION=2.7.0+cu128" in research
    assert "ARG PYTORCH_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu128" in research
    assert research.count('"torch==${PYTORCH_VERSION}"') == 1
    assert research.index('"torch==${PYTORCH_VERSION}"') < research.index(
        'python -m pip install -e ".[research]"'
    )


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


def _dockerfile_stages(dockerfile: str) -> dict[str, str]:
    stages: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    for line in dockerfile.splitlines():
        lower = line.lower()
        if lower.startswith("from "):
            if current_name is not None:
                stages[current_name] = "\n".join(current_lines)
            current_lines = [line]
            current_name = lower.rsplit(" as ", maxsplit=1)[-1].strip()
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        stages[current_name] = "\n".join(current_lines)
    return stages
