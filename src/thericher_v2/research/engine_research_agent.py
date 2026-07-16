"""Single-shot Engine Research Agent queue runner.

The runner is intentionally thin: it claims one external queue item, runs the
existing Docker research job command once, and records compact state outside
the Git workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .validation import (
    DEFAULT_MARKET_DATA_ROOT,
    _reject_repo_artifact_path,
    resolve_model_artifact_root,
)

AGENT_NAME = "engine_research_agent"
AGENT_ROOT_NAME = "engine-research-agent"
DEFAULT_GPU_SMOKE_JOB_ID = "engine-research-agent-gpu-training-smoke"
DOCKER_MODEL_ARTIFACT_ROOT = "/app/model_artifacts"
RESEARCH_JOB_COMMAND = "thericher-v2-research-job"
SUPPORTED_ENQUEUED_RESEARCH_JOB_KINDS = (
    "gpu_training_smoke",
    "candidate_breadth_holdout",
    "candidate_breadth_queue",
    "candidate_depth_comparison",
    "candidate_depth_target",
    "candidate_training",
    "candidate_evaluation",
    "candidate_feature_branch",
    "candidate_feature_branch_replay",
    "candidate_feature_input_ablation",
    "candidate_replay",
    "candidate_replay_comparison",
    "candidate_threshold_sweep",
    "candidate_threshold_robustness",
    "candidate_threshold_calibration",
    "candidate_threshold_holdout",
    "candidate_threshold_attribution",
    "candidate_threshold_band_rerun",
    "candidate_threshold_rerun",
)

RUNNER_COMPLETED = 0
RUNNER_EMPTY_QUEUE = 20
RUNNER_GPU_LOCKED = 21
RUNNER_FAILED = 1

AgentJobKind = Literal["docker_research_job"]
AgentRunStatus = Literal[
    "completed",
    "failed",
    "gpu_locked",
    "queue_empty",
]
SubprocessExecutor = Callable[
    [list[str], Path, dict[str, str]],
    subprocess.CompletedProcess[str],
]

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SECRET_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "CREDENTIAL",
    "API_KEY",
    "ACCESS_KEY",
    "PRIVATE_KEY",
)
_DISALLOWED_RESEARCH_ARG_VALUES = (
    ".env",
    "kis",
    "broker",
    "credential",
    "secret",
    "password",
    "api-key",
    "api_key",
    "token",
)
_DISALLOWED_RESEARCH_ARG_FLAGS = (
    "--artifact-root",
    "--env",
    "-e",
    "--env-file",
    "--env-from-file",
    "--network",
)


@dataclass(frozen=True)
class AgentJobSpec:
    job_id: str
    kind: AgentJobKind
    research_job_args: tuple[str, ...]
    queued_at: datetime
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _JOB_ID_PATTERN.match(self.job_id):
            raise ValueError("job_id must be path-safe and non-empty")
        if self.kind != "docker_research_job":
            raise ValueError(f"unsupported engine research agent job kind: {self.kind}")
        if not self.research_job_args:
            raise ValueError("research_job_args are required")
        if any(not item for item in self.research_job_args):
            raise ValueError("research_job_args must not contain empty values")
        _validate_research_job_args(self.research_job_args)
        object.__setattr__(self, "queued_at", self.queued_at.astimezone(UTC))


@dataclass(frozen=True)
class AgentClaim:
    spec: AgentJobSpec
    run_dir: Path
    claimed_job_path: Path


@dataclass(frozen=True)
class AgentRunResult:
    status: AgentRunStatus
    checked_at: datetime
    reason: str
    agent_root: Path
    job_id: str | None = None
    run_dir: Path | None = None
    claimed_job_path: Path | None = None
    status_artifact: Path | None = None
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


class GpuLockHeldError(RuntimeError):
    """Raised when another Engine Research Agent invocation holds the GPU lock."""


class GpuFileLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._fd: int | None = None

    def __enter__(self) -> GpuFileLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            self._fd = os.open(str(self.lock_path), flags)
        except FileExistsError as exc:
            raise GpuLockHeldError(f"GPU lock already exists: {self.lock_path}") from exc
        payload = {
            "schema_version": SCHEMA_VERSION,
            "agent": AGENT_NAME,
            "pid": os.getpid(),
            "created_at": datetime.now(UTC).isoformat(),
            "manual_recovery": "remove this file only after verifying no research job is running",
        }
        os.write(self._fd, json.dumps(payload, sort_keys=True).encode("utf-8"))
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


def resolve_agent_root(artifact_root: Path | None = None) -> Path:
    root = artifact_root or resolve_model_artifact_root()
    return root / AGENT_ROOT_NAME


def seed_gpu_training_smoke_job(
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    job_id: str = DEFAULT_GPU_SMOKE_JOB_ID,
    queued_at: datetime | None = None,
) -> Path:
    return enqueue_research_job(
        artifact_root=artifact_root,
        repo_root=repo_root,
        job_id=job_id,
        queued_at=queued_at or datetime.now(UTC),
        research_kind="gpu_training_smoke",
        reason="bounded PyTorch CUDA smoke through Docker research",
    )


def enqueue_research_job(
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    job_id: str,
    research_kind: str,
    research_args: tuple[str, ...] = (),
    queued_at: datetime | None = None,
    reason: str = "bounded Docker research job",
) -> Path:
    root = artifact_root or resolve_model_artifact_root()
    _reject_repo_artifact_path(root, repo_root)
    if research_kind not in SUPPORTED_ENQUEUED_RESEARCH_JOB_KINDS:
        raise ValueError(f"unsupported research job kind: {research_kind}")
    _reject_repo_path_args(research_args, repo_root)
    spec = AgentJobSpec(
        job_id=job_id,
        kind="docker_research_job",
        research_job_args=(
            "--job-id",
            job_id,
            "--kind",
            research_kind,
            *research_args,
        ),
        queued_at=queued_at or datetime.now(UTC),
        reason=reason,
    )
    return _write_queue_spec(spec, root)


def claim_next_job(agent_root: Path) -> AgentClaim | None:
    queue_dir = agent_root / "queue"
    if not queue_dir.exists():
        return None
    for queue_path in sorted(queue_dir.glob("*.json"), key=lambda path: path.name):
        spec = _read_agent_job_spec(queue_path)
        run_dir = agent_root / "runs" / spec.job_id
        run_dir.mkdir(parents=True, exist_ok=False)
        claimed_path = run_dir / "job.json"
        queue_path.replace(claimed_path)
        return AgentClaim(spec=spec, run_dir=run_dir, claimed_job_path=claimed_path)
    return None


def run_once(
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    executor: SubprocessExecutor | None = None,
    now: datetime | None = None,
) -> AgentRunResult:
    checked_at = now or datetime.now(UTC)
    root = artifact_root or resolve_model_artifact_root()
    _reject_repo_artifact_path(root, repo_root)
    agent_root = resolve_agent_root(root)
    lock_path = agent_root / "locks" / "gpu.lock"
    try:
        with GpuFileLock(lock_path):
            claim = claim_next_job(agent_root)
            if claim is None:
                return AgentRunResult(
                    status="queue_empty",
                    checked_at=checked_at,
                    reason="no queued Engine Research Agent jobs",
                    agent_root=agent_root,
                )
            return _run_claim(
                claim,
                artifact_root=root,
                repo_root=repo_root or Path.cwd(),
                executor=executor or _run_subprocess,
                checked_at=checked_at,
            )
    except GpuLockHeldError as exc:
        return AgentRunResult(
            status="gpu_locked",
            checked_at=checked_at,
            reason=str(exc),
            agent_root=agent_root,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed-gpu-training-smoke")
    seed.add_argument("--job-id", default=DEFAULT_GPU_SMOKE_JOB_ID)

    enqueue = subparsers.add_parser("enqueue-research-job")
    enqueue.add_argument("--job-id", required=True)
    enqueue.add_argument("--kind", required=True, choices=SUPPORTED_ENQUEUED_RESEARCH_JOB_KINDS)
    enqueue.add_argument("--reason", default="bounded Docker research job")
    enqueue.add_argument("research_args", nargs=argparse.REMAINDER)

    subparsers.add_parser("run-once")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    if args.command == "seed-gpu-training-smoke":
        queue_path = seed_gpu_training_smoke_job(
            artifact_root=artifact_root,
            repo_root=args.repo_root,
            job_id=args.job_id,
        )
        print(
            json.dumps(
                {
                    "status": "queued",
                    "agent": AGENT_NAME,
                    "queue_path": str(queue_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(RUNNER_COMPLETED)
    if args.command == "enqueue-research-job":
        queue_path = enqueue_research_job(
            artifact_root=artifact_root,
            repo_root=args.repo_root,
            job_id=args.job_id,
            research_kind=args.kind,
            research_args=_clean_research_args(args.research_args),
            reason=args.reason,
        )
        print(
            json.dumps(
                {
                    "status": "queued",
                    "agent": AGENT_NAME,
                    "queue_path": str(queue_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(RUNNER_COMPLETED)

    result = run_once(artifact_root=artifact_root, repo_root=args.repo_root)
    print(json.dumps(_agent_run_payload(result, artifact_root), indent=2, sort_keys=True))
    raise SystemExit(_exit_code_for(result.status))


def _run_claim(
    claim: AgentClaim,
    *,
    artifact_root: Path,
    repo_root: Path,
    executor: SubprocessExecutor,
    checked_at: datetime,
) -> AgentRunResult:
    started_at = datetime.now(UTC)
    command = _docker_research_command(claim.spec, repo_root=repo_root)
    env = _docker_research_env(artifact_root)
    try:
        completed = executor(command, repo_root, env)
        status: AgentRunStatus = "completed" if completed.returncode == 0 else "failed"
        reason = (
            "Docker research job completed"
            if completed.returncode == 0
            else "Docker research job failed"
        )
        result = AgentRunResult(
            status=status,
            checked_at=checked_at,
            reason=reason,
            agent_root=claim.run_dir.parent.parent,
            job_id=claim.spec.job_id,
            run_dir=claim.run_dir,
            claimed_job_path=claim.claimed_job_path,
            command=tuple(command),
            returncode=completed.returncode,
            stdout_tail=_tail_text(completed.stdout),
            stderr_tail=_tail_text(completed.stderr),
        )
    except Exception as exc:  # noqa: BLE001 - the runner records non-fatal launch failures.
        result = AgentRunResult(
            status="failed",
            checked_at=checked_at,
            reason=f"Docker research job launch failed: {exc}",
            agent_root=claim.run_dir.parent.parent,
            job_id=claim.spec.job_id,
            run_dir=claim.run_dir,
            claimed_job_path=claim.claimed_job_path,
            command=tuple(command),
        )
    status_artifact = _write_run_status(
        result,
        artifact_root=artifact_root,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    return AgentRunResult(
        status=result.status,
        checked_at=result.checked_at,
        reason=result.reason,
        agent_root=result.agent_root,
        job_id=result.job_id,
        run_dir=result.run_dir,
        claimed_job_path=result.claimed_job_path,
        status_artifact=status_artifact,
        command=result.command,
        returncode=result.returncode,
        stdout_tail=result.stdout_tail,
        stderr_tail=result.stderr_tail,
    )


def _run_subprocess(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _docker_research_command(spec: AgentJobSpec, *, repo_root: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--profile",
        "research",
        "run",
        "--rm",
        "--no-deps",
        "--volume",
        f"{_compose_host_path(repo_root / 'src')}:/app/src:ro",
        "research",
        RESEARCH_JOB_COMMAND,
        *spec.research_job_args,
        "--artifact-root",
        DOCKER_MODEL_ARTIFACT_ROOT,
    ]


def _docker_research_env(artifact_root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
    ):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env.update(
        {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "THERICHER_MODE": "off",
            "THERICHER_HOST_MODEL_ARTIFACT_ROOT": _compose_host_path(artifact_root),
            "THERICHER_HOST_MARKET_DATA_ROOT": _compose_host_path(DEFAULT_MARKET_DATA_ROOT),
            "THERICHER_MODEL_ARTIFACT_ROOT": DOCKER_MODEL_ARTIFACT_ROOT,
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return {
        key: value
        for key, value in env.items()
        if not any(marker in key.upper() for marker in _SECRET_MARKERS)
    }


def _compose_host_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _write_queue_spec(spec: AgentJobSpec, artifact_root: Path) -> Path:
    queue_dir = resolve_agent_root(artifact_root) / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queue_path = queue_dir / f"{spec.job_id}.json"
    if queue_path.exists():
        return queue_path
    temp_path = queue_path.with_name(f".{queue_path.name}.tmp")
    temp_path.write_text(
        json.dumps(_agent_job_payload(spec, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(queue_path)
    return queue_path


def _clean_research_args(args: list[str]) -> tuple[str, ...]:
    cleaned = tuple(str(item) for item in args)
    if cleaned and cleaned[0] == "--":
        cleaned = cleaned[1:]
    return cleaned


def _validate_research_job_args(args: tuple[str, ...]) -> None:
    if "--kind" not in args:
        raise ValueError("research_job_args must include --kind")
    kind_index = args.index("--kind")
    if kind_index == len(args) - 1:
        raise ValueError("research_job_args must include a kind value")
    research_kind = args[kind_index + 1]
    if research_kind not in SUPPORTED_ENQUEUED_RESEARCH_JOB_KINDS:
        raise ValueError(f"unsupported research job kind: {research_kind}")
    for flag in _DISALLOWED_RESEARCH_ARG_FLAGS:
        if flag in args:
            raise ValueError(f"queued research args cannot include {flag}")
    for item in args:
        lowered = item.lower()
        if any(marker in lowered for marker in _DISALLOWED_RESEARCH_ARG_VALUES):
            raise ValueError("queued research args cannot include credential, KIS, or broker terms")
        if item in {"docker", RESEARCH_JOB_COMMAND}:
            raise ValueError("queued research args must not include executable names")
        if any(separator in item for separator in (";", "&&", "|", "\n", "\r")):
            raise ValueError("queued research args must be plain argv tokens")


def _reject_repo_path_args(args: tuple[str, ...], repo_root: Path | None) -> None:
    if repo_root is None:
        return
    repo_text = str(repo_root.resolve()).lower()
    for item in args:
        normalized = item.replace("/", "\\").lower()
        if repo_text in normalized:
            raise ValueError("queued research args must not point inside the Git workspace")


def _read_agent_job_spec(path: Path) -> AgentJobSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    research_job_args = payload.get("research_job_args")
    if research_job_args is None:
        research_job_args = payload.get("execution", {}).get("research_job_args", ())
    return AgentJobSpec(
        job_id=str(payload["job_id"]),
        kind=payload["kind"],
        research_job_args=tuple(str(item) for item in research_job_args),
        queued_at=datetime.fromisoformat(str(payload["queued_at"])),
        reason=str(payload.get("reason", "")),
        schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
    )


def _agent_job_payload(spec: AgentJobSpec, artifact_root: Path) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": spec.schema_version,
            "agent": AGENT_NAME,
            "status": "queued",
            "job_id": spec.job_id,
            "kind": spec.kind,
            "queued_at": spec.queued_at,
            "reason": spec.reason,
            "research_job_args": spec.research_job_args,
            "execution": {
                "mode": "single_docker_research_job",
                "docker_service": "research",
                "command": RESEARCH_JOB_COMMAND,
                "research_job_args": spec.research_job_args,
                "artifact_root": DOCKER_MODEL_ARTIFACT_ROOT,
            },
            "artifact_policy": {
                "host_model_artifact_root": str(artifact_root),
                "agent_root": str(resolve_agent_root(artifact_root)),
                "repo_storage_allowed": False,
            },
            "boundaries": {
                "kis_api": False,
                "broker_submit": False,
                "credential_read": False,
                "env_file_read": False,
                "public_dashboard": False,
                "local_torch_dependency": False,
            },
        }
    )


def _write_run_status(
    result: AgentRunResult,
    *,
    artifact_root: Path,
    started_at: datetime,
    completed_at: datetime,
) -> Path:
    if result.run_dir is None:
        raise ValueError("run_dir is required to write run status")
    path = result.run_dir / "status.json"
    result_with_path = AgentRunResult(
        status=result.status,
        checked_at=result.checked_at,
        reason=result.reason,
        agent_root=result.agent_root,
        job_id=result.job_id,
        run_dir=result.run_dir,
        claimed_job_path=result.claimed_job_path,
        status_artifact=path,
        command=result.command,
        returncode=result.returncode,
        stdout_tail=result.stdout_tail,
        stderr_tail=result.stderr_tail,
    )
    payload = _agent_run_payload(
        result_with_path,
        artifact_root,
        started_at=started_at,
        completed_at=completed_at,
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    last_run = result.agent_root / "last-run.json"
    last_run.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _agent_run_payload(
    result: AgentRunResult,
    artifact_root: Path,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "agent": AGENT_NAME,
            "status": result.status,
            "checked_at": result.checked_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "reason": result.reason,
            "job_id": result.job_id,
            "agent_root": str(result.agent_root),
            "run_dir": None if result.run_dir is None else str(result.run_dir),
            "claimed_job_path": (
                None if result.claimed_job_path is None else str(result.claimed_job_path)
            ),
            "status_artifact": (
                None if result.status_artifact is None else str(result.status_artifact)
            ),
            "command": result.command,
            "returncode": result.returncode,
            "stdout_tail": result.stdout_tail,
            "stderr_tail": result.stderr_tail,
            "artifact_policy": {
                "host_model_artifact_root": str(artifact_root),
                "docker_model_artifact_root": DOCKER_MODEL_ARTIFACT_ROOT,
                "repo_storage_allowed": False,
            },
            "execution": {
                "one_job_per_invocation": True,
                "docker_research_only": True,
                "gpu_lock": str(result.agent_root / "locks" / "gpu.lock"),
            },
            "boundaries": {
                "kis_api": False,
                "broker_submit": False,
                "credential_read": False,
                "env_file_read": False,
                "public_dashboard": False,
            },
        }
    )


def _tail_text(value: str | None, *, limit: int = 4000) -> str:
    if not value:
        return ""
    return value[-limit:]


def _exit_code_for(status: AgentRunStatus) -> int:
    if status == "completed":
        return RUNNER_COMPLETED
    if status == "queue_empty":
        return RUNNER_EMPTY_QUEUE
    if status == "gpu_locked":
        return RUNNER_GPU_LOCKED
    return RUNNER_FAILED


if __name__ == "__main__":
    main()
