"""Launch the explicit bounded cycle through the existing Paper Docker service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from thericher_v2.execution.kis_paper_session import _is_safe_session_id, _write_session_json
from thericher_v2.execution.kis_readonly import load_kis_paper_config

ROOT = Path(__file__).resolve().parents[1]


def run(*, project_root: Path, cycle_id: str, execute: bool, visits: int) -> dict[str, object]:
    if not _is_safe_session_id(cycle_id) or not 1 <= visits <= 20:
        raise ValueError("invalid bounded cycle arguments")
    root = project_root.resolve()
    cycle_ref = hashlib.sha256(json.dumps(cycle_id).encode("utf-8")).hexdigest()
    name = "thericher-spy-fill-" + cycle_ref[:20]
    result = {"kind": "kis_paper_spy_fill_dispatch", "cycle_ref": cycle_ref, "paper_only": True}
    # Compose must not parse the real .env or inherit another KIS route.
    environment = {key: os.environ[key] for key in os.environ if not key.startswith("KIS_")}
    artifact_root = _artifact_root(root)
    environment["THERICHER_HOST_MODEL_ARTIFACT_ROOT"] = artifact_root.as_posix()
    if execute:
        config = load_kis_paper_config(root / ".env")
        environment.update(
            KIS_PAPER_APP_KEY=config.app_key,
            KIS_PAPER_APP_SECRET=config.app_secret,
            KIS_PAPER_ACCOUNT_NO=config.account_number,
            KIS_PAPER_ACCOUNT_PRODUCT_CODE=config.account_product_code,
        )
    common = dict(env=environment, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    existing = subprocess.run(["docker", "container", "inspect", name], timeout=30, **common)
    if existing.returncode == 0:
        return {**result, "status": "owned_container_present"}
    command = [
        "docker", "compose", "--project-directory", str(root),
        "--env-file", str(root / ".env.example"), "--profile", "kis-paper-session",
        "run", "--rm", "--no-deps", "--pull", "never", "-T", "--name", name,
        "kis-paper-session", "timeout", "--signal=TERM", "--kill-after=30s", "1260s",
        "python", "-m", "thericher_v2.execution.kis_paper_session",
        "--fill-cycle-id", cycle_id, "--fill-cycle-visits", str(visits),
        "--repository-root", "/app", "--state-root", "/app/private/canary",
        "--runtime-projection", "/app/runtime/state/kis_paper_canary.json",
        "--paper-account-snapshot", "/app/runtime/state/paper_account_snapshot.json",
        "--emergency-state", "/app/emergency/emergency_state.json",
        "--execution-control", "/app/emergency/paper_execution_control.json",
        "--artifact-root", "/app/model_artifacts",
    ]
    if execute:
        command.append("--execute")
    try:
        completed = subprocess.run(command, timeout=1350, **common)
    except subprocess.TimeoutExpired:
        # Stop only this launched identity. Durable intents survive interruption.
        try:
            stopped = subprocess.run(["docker", "stop", "--time", "30", name], timeout=45, **common)
            contained = stopped.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            contained = False
        return {**result, "status": "worker_timeout", "container_stop_confirmed": contained}
    return {
        **result,
        "status": "worker_exited" if completed.returncode == 0 else "worker_failed",
        "worker_exit_code": completed.returncode,
    }


def _artifact_root(project_root: Path) -> Path:
    root = Path(os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT")
                or "D:/thericher-v2/model-artifacts").resolve()
    if root.is_relative_to(project_root.resolve()):
        raise ValueError("artifact root must be outside the repository")
    return root


def write_dispatch_result(result: dict[str, object], project_root: Path) -> None:
    destination = (_artifact_root(project_root) / "execution" / "kis-paper-spy-fill-cycle"
                   / str(result["cycle_ref"]) / "dispatch.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_session_json(destination, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--visits", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        result = run(project_root=args.project_root, cycle_id=args.cycle_id,
                     execute=args.execute, visits=args.visits)
    except Exception:
        result = {"kind": "kis_paper_spy_fill_dispatch", "status": "dispatch_unavailable",
                  "paper_only": True,
                  "cycle_ref": hashlib.sha256(json.dumps(args.cycle_id).encode()).hexdigest()}
    try:
        write_dispatch_result(result, args.project_root)
    except Exception:
        result["dispatch_record_written"] = False
    print(json.dumps(result, sort_keys=True))
    success = result["status"] == "worker_exited" and "dispatch_record_written" not in result
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
