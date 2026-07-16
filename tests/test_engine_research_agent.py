from __future__ import annotations

import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.engine_research_agent import (
    DOCKER_MODEL_ARTIFACT_ROOT,
    RUNNER_EMPTY_QUEUE,
    RUNNER_GPU_LOCKED,
    _exit_code_for,
    claim_next_job,
    run_once,
    seed_gpu_training_smoke_job,
)


def test_seed_gpu_training_smoke_job_writes_external_queue_item(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    queue_path = seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="unit-gpu-smoke",
        queued_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue_path == artifact_root / "engine-research-agent" / "queue" / "unit-gpu-smoke.json"
    assert payload["agent"] == "engine_research_agent"
    assert payload["status"] == "queued"
    assert payload["kind"] == "docker_research_job"
    assert payload["execution"]["docker_service"] == "research"
    assert payload["execution"]["artifact_root"] == DOCKER_MODEL_ARTIFACT_ROOT
    assert payload["execution"]["research_job_args"] == [
        "--job-id",
        "unit-gpu-smoke",
        "--kind",
        "gpu_training_smoke",
    ]
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["boundaries"]["credential_read"] is False
    assert payload["boundaries"]["broker_submit"] is False

    with pytest.raises(ValueError, match="outside the Git workspace"):
        seed_gpu_training_smoke_job(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            job_id="bad-repo-queue",
        )


def test_claim_next_job_is_deterministic_by_queue_filename(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="b-job",
    )
    seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="a-job",
    )

    claim = claim_next_job(artifact_root / "engine-research-agent")

    assert claim is not None
    assert claim.spec.job_id == "a-job"
    assert claim.claimed_job_path.exists()
    assert not (artifact_root / "engine-research-agent" / "queue" / "a-job.json").exists()
    assert (artifact_root / "engine-research-agent" / "queue" / "b-job.json").exists()


def test_run_once_claims_one_job_and_does_not_double_claim(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="one-shot-gpu-smoke",
    )
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def executor(
        command: list[str],
        cwd: Path,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, env))
        return subprocess.CompletedProcess(command, 0, stdout="research ok", stderr="")

    first = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        executor=executor,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    second = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        executor=executor,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert first.status == "completed"
    assert first.returncode == 0
    assert first.status_artifact is not None
    assert first.status_artifact.exists()
    assert second.status == "queue_empty"
    assert _exit_code_for(second.status) == RUNNER_EMPTY_QUEUE
    assert len(calls) == 1
    command, cwd, env = calls[0]
    assert cwd == Path.cwd()
    assert command[:7] == [
        "docker",
        "compose",
        "--profile",
        "research",
        "run",
        "--rm",
        "--no-deps",
    ]
    assert "research" in command
    assert "thericher-v2-research-job" in command
    assert "--artifact-root" in command
    assert DOCKER_MODEL_ARTIFACT_ROOT in command
    assert env["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert env["THERICHER_MODEL_ARTIFACT_ROOT"] == DOCKER_MODEL_ARTIFACT_ROOT
    assert not any("SECRET" in key or "TOKEN" in key for key in env)


def test_run_once_preexisting_lock_does_not_claim_queue(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    queue_path = seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="locked-gpu-smoke",
    )
    lock_path = artifact_root / "engine-research-agent" / "locks" / "gpu.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("held", encoding="utf-8")

    result = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        executor=lambda _command, _cwd, _env: pytest.fail("executor must not run"),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert result.status == "gpu_locked"
    assert _exit_code_for(result.status) == RUNNER_GPU_LOCKED
    assert queue_path.exists()
    assert not (artifact_root / "engine-research-agent" / "runs" / "locked-gpu-smoke").exists()


def test_run_once_failure_after_claim_keeps_claimed_job_and_releases_lock(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="failing-gpu-smoke",
    )

    def failing_executor(
        _command: list[str],
        _cwd: Path,
        _env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("unit docker launch failure")

    result = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        executor=failing_executor,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    run_dir = artifact_root / "engine-research-agent" / "runs" / "failing-gpu-smoke"
    assert result.status == "failed"
    assert result.status_artifact == run_dir / "status.json"
    assert result.status_artifact.exists()
    assert (run_dir / "job.json").exists()
    assert not (
        artifact_root / "engine-research-agent" / "queue" / "failing-gpu-smoke.json"
    ).exists()
    assert not (artifact_root / "engine-research-agent" / "locks" / "gpu.lock").exists()
    payload = json.loads(result.status_artifact.read_text(encoding="utf-8"))
    assert "unit docker launch failure" in payload["reason"]
    assert payload["artifact_policy"]["repo_storage_allowed"] is False


def test_run_once_is_offline_and_does_not_read_credentials(monkeypatch, tmp_path) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Engine Research Agent runner must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        lower_name = path.name.lower()
        if lower_name.startswith(".env") or "secret" in lower_name:
            raise AssertionError("Engine Research Agent runner must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root = tmp_path / "model-artifacts"
    seed_gpu_training_smoke_job(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        job_id="offline-gpu-smoke",
    )
    result = run_once(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        executor=lambda command, _cwd, _env: subprocess.CompletedProcess(
            command,
            0,
            stdout="offline ok",
            stderr="",
        ),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert result.status == "completed"


def test_engine_research_agent_keeps_torch_out_of_local_dependencies() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    dependencies = pyproject.split("[project.optional-dependencies]", maxsplit=1)[0]
    stages = _dockerfile_stages(dockerfile)

    assert "torch" not in dependencies
    assert "torch==" not in stages["base"].lower()
    assert "torch==" in stages["research"].lower()
    assert "torch==" not in stages["runtime"].lower()


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
