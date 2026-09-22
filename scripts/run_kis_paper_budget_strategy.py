"""Launch bounded budget visits through the existing daily-SPY Paper service."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from thericher_v2.execution.kis_paper_session import _write_session_json
from thericher_v2.execution.kis_readonly import load_kis_paper_config

ROOT = Path(__file__).resolve().parents[1]
CONTAINER_NAME = "thericher-spy-budget-strategy"


def run(*, project_root: Path, execute: bool, visits: int) -> dict[str, object]:
    if type(visits) is not int or not 1 <= visits <= 24:
        raise ValueError("invalid bounded budget visits")
    if os.environ.get("THERICHER_MODE", "off").strip().lower() == "kis_live":
        raise ValueError("live_mode_unavailable")
    root = project_root.resolve()
    result = {"kind": "kis_paper_spy_budget_dispatch", "paper_only": True}
    # Filter names before reading values; Compose must not inherit any KIS route.
    environment = {
        key: os.environ[key] for key in os.environ if not key.upper().startswith("KIS_")
    }
    environment["THERICHER_HOST_MODEL_ARTIFACT_ROOT"] = _artifact_root(root).as_posix()
    common = dict(env=environment, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    existing = subprocess.run(
        ["docker", "container", "inspect", CONTAINER_NAME], timeout=30, **common
    )
    if existing.returncode == 0:
        return {**result, "status": "owned_container_present"}
    if execute:
        config = load_kis_paper_config(root / ".env")
        environment.update(
            KIS_PAPER_APP_KEY=config.app_key,
            KIS_PAPER_APP_SECRET=config.app_secret,
            KIS_PAPER_ACCOUNT_NO=config.account_number,
            KIS_PAPER_ACCOUNT_PRODUCT_CODE=config.account_product_code,
        )
    command = [
        "docker", "compose", "--project-directory", str(root),
        "--env-file", str(root / ".env.example"), "--profile", "kis-paper-daily-spy-session",
        "run", "--rm", "--no-deps", "--pull", "never", "-T", "--name", CONTAINER_NAME,
        "kis-paper-daily-spy-session", "timeout", "--signal=TERM", "--kill-after=30s", "1260s",
        "python", "-m", "thericher_v2.execution.kis_paper_daily_spy_session",
        "--budget-trial", "--budget-visits", str(visits),
        "--repository-root", "/app",
        "--cache-root", "/app/market_data/us_equities/kis_paper_private/daily",
        "--head-cache-root", "/app/market_data/us_equities/kis_paper_private/daily-head/v1",
        "--availability-root",
        "/app/model_artifacts/_control/kis-paper-daily-spy-input-availability-v1",
        "--state-root", "/app/private/canary",
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
        # Stop only the fixed budget worker; its durable intents remain recoverable.
        try:
            stopped = subprocess.run(
                ["docker", "stop", "--time", "30", CONTAINER_NAME], timeout=45, **common
            )
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
    root = Path(
        os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT") or "D:/thericher-v2/model-artifacts"
    ).resolve()
    if root.is_relative_to(project_root.resolve()):
        raise ValueError("artifact root must be outside the repository")
    return root


def write_dispatch_result(result: dict[str, object], project_root: Path) -> None:
    destination = (
        _artifact_root(project_root) / "execution" / "kis-paper-spy-budget" / "dispatch.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_session_json(destination, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--visits", type=int, choices=range(1, 25), default=24)
    args = parser.parse_args(argv)
    try:
        result = run(project_root=args.project_root, execute=args.execute, visits=args.visits)
    except Exception:
        result = {
            "kind": "kis_paper_spy_budget_dispatch",
            "status": "dispatch_unavailable",
            "paper_only": True,
        }
    try:
        write_dispatch_result(result, args.project_root)
    except Exception:
        result["dispatch_record_written"] = False
    print(json.dumps(result, sort_keys=True))
    success = result["status"] == "worker_exited" and "dispatch_record_written" not in result
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
