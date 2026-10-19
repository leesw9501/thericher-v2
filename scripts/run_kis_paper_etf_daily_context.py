"""Source-pinned Docker intake; default is inert and Paper credentials use stdin."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from thericher_v2.execution.kis_market_data import load_kis_paper_market_data_config

REPO = Path(__file__).resolve().parents[1]
MARKET = Path("D:/market_data")
ARTIFACT = Path("D:/thericher-v2/model-artifacts")
LABEL = "thericher.data.etf-context.uuid"
SOURCE_FILES = (
    "scripts/collect_kis_paper_etf_daily_context.py",
    "src/thericher_v2/data/kis_paper_etf_daily_context.py",
    "src/thericher_v2/execution/kis_market_data.py",
    "src/thericher_v2/execution/kis_market_data_rate_gate.py",
    "src/thericher_v2/execution/kis_private_daily_collector.py",
    "src/thericher_v2/contracts.py",
)
OS_KEYS = frozenset(
    key.upper()
    for key in (
        "PATH",
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "DOCKER_API_VERSION",
    )
)


def os_environment() -> dict[str, str]:
    environment = {key: os.environ[key] for key in os.environ if key.upper() in OS_KEYS}
    pathext = next((key for key in environment if key.upper() == "PATHEXT"), "PATHEXT")
    # Whitespace-only is empty; preserve every other inherited value unchanged.
    if not environment.get(pathext, "").strip():
        environment[pathext] = ".COM;.EXE;.BAT;.CMD"
    return environment


def source_map() -> dict[str, str]:
    return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def validate_result(value: object) -> dict[str, object]:
    from thericher_v2.data.kis_paper_etf_daily_context import _FAILURES

    if isinstance(value, dict) and set(value) == {"status", "reason"}:
        if value["status"] == "unavailable" and value["reason"] in _FAILURES | {
            "input_unavailable"
        }:
            # Missing counters stay unknown; a CLI failure is not zero attempted reads.
            return value
        raise ValueError("invalid_intake_output")
    if not isinstance(value, dict) or set(value) != {
        "status",
        "reason",
        "token_posts",
        "daily_gets",
        "next_due_utc",
        "receipts",
        "http_start_gaps_seconds",
        "pacing_basis",
    }:
        raise ValueError("invalid_intake_output")
    if value["status"] not in {"complete", "incomplete"} or value["reason"] not in _FAILURES | {
        None
    }:
        raise ValueError("invalid_intake_output")
    if not (
        type(value["token_posts"]) is int
        and 0 <= value["token_posts"] <= 1
        and type(value["daily_gets"]) is int
        and 0 <= value["daily_gets"] <= 16
    ):
        raise ValueError("invalid_intake_output")
    if value["next_due_utc"] is not None:
        due = datetime.fromisoformat(value["next_due_utc"])
        if due.utcoffset() is None or due.utcoffset().total_seconds() != 0:
            raise ValueError("invalid_intake_output")
    if (
        value["pacing_basis"] != "final_opener_delegate_boundary_not_socket_wire_measurement"
        or type(value["http_start_gaps_seconds"]) is not list
        or any(
            type(gap) not in {int, float} or not math.isfinite(gap) or gap < 0
            for gap in value["http_start_gaps_seconds"]
        )
        or type(value["receipts"]) is not list
        or len(value["receipts"]) > 5
    ):
        raise ValueError("invalid_intake_output")
    mapped = []
    prefix = "/app/model_artifacts/data/etf-daily-context-v1/"
    for row in value["receipts"]:
        if (
            type(row) is not dict
            or set(row) != {"path", "sha256"}
            or type(row["path"]) is not str
            or not row["path"].startswith(prefix)
            or type(row["sha256"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", row["sha256"]) is None
        ):
            raise ValueError("invalid_intake_output")
        relative = row["path"][len(prefix) :]
        if (
            re.fullmatch(r"[0-9a-f]{32}/(?:SPY-baseline2|SPY|QQQ|TLT|GLD)/receipt.json", relative)
            is None
        ):
            raise ValueError("invalid_intake_output")
        mapped.append(
            dict(path=str(ARTIFACT / "data/etf-daily-context-v1" / relative), sha256=row["sha256"])
        )
    return {**value, "receipts": mapped}


def docker_command(image: str, identity: str) -> list[str]:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise ValueError("exact_local_image_required")
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--name",
        "thericher-etf-context-" + identity,
        "--label",
        LABEL + "=" + identity,
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--log-driver",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--cpus",
        "2",
        "--memory",
        "1g",
        "--pids-limit",
        "128",
        "--mount",
        "type=bind,source=" + str(MARKET) + ",target=/app/market_data",
        "--mount",
        "type=bind,source=" + str(ARTIFACT) + ",target=/app/model_artifacts",
        "--entrypoint",
        "timeout",
        image,
        "150",
        "python",
        "-B",
        "/app/scripts/collect_kis_paper_etf_daily_context.py",
        "--execute",
        "--paper-config-stdin",
        "--token-interval-seconds",
        "60",
        "--cache-root",
        "/app/market_data/us_equities/kis_paper_private/etf-daily-context-v1",
        "--artifact-root",
        "/app/model_artifacts/data/etf-daily-context-v1",
        "--control-root",
        "/app/market_data/us_equities/kis_paper_private/collection-control-v1",
    ]


def cleanup(name, identity, environment):
    def listed():
        return subprocess.run(
            [
                "docker",
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                "name=^/" + name + "$",
            ],
            env=environment,
            capture_output=True,
            timeout=5,
        )

    try:
        remaining = listed()
        if remaining.returncode == 0 and remaining.stdout.strip():
            container_id = remaining.stdout.decode("ascii").strip()
            if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
                return False
            label = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "' + LABEL + '"}}',
                    container_id,
                ],
                env=environment,
                capture_output=True,
                timeout=5,
            )
            if label.returncode != 0 or label.stdout.decode().strip() != identity:
                return False
            removed = subprocess.run(
                ["docker", "rm", "--force", container_id],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
            if removed.returncode:
                return False
            remaining = listed()
        return remaining.returncode == 0 and not remaining.stdout.strip()
    except Exception:
        return False


def run(*, image: str, execute: bool = False) -> dict[str, object]:
    if not execute:
        return dict(status="inert", credential_reads=0, broker_calls=0)
    identity = uuid4().hex
    command = docker_command(image, identity)
    before = source_map()
    environment = os_environment()
    probe_code = (
        "import json,hashlib;from pathlib import Path;"
        "files=" + repr(SOURCE_FILES) + ";"
        "print(json.dumps({n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest() "
        "for n in files}))"
    )
    probe_name = "thericher-etf-source-" + identity
    try:
        probe = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                probe_name,
                "--label",
                LABEL + "=" + identity,
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--log-driver",
                "none",
                "--entrypoint",
                "python",
                image,
                "-B",
                "-c",
                probe_code,
            ],
            env=environment,
            capture_output=True,
            timeout=10,
            check=False,
        )
    finally:
        if not cleanup(probe_name, identity, environment):
            raise ValueError("source_probe_not_reaped")
    if probe.returncode != 0 or json.loads(probe.stdout) != before:
        raise ValueError("image_source_mismatch")
    config = load_kis_paper_market_data_config(REPO / ".env", environment={"THERICHER_MODE": "off"})
    packet = json.dumps(
        dict(KIS_PAPER_APP_KEY=config.app_key, KIS_PAPER_APP_SECRET=config.app_secret)
    ).encode()
    result = dict(status="unknown", reason="intake_result_unavailable")
    absent = False
    worker_report = None
    try:
        completed = subprocess.run(
            command,
            input=packet,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=165,
            check=False,
        )
        if len(completed.stdout) > 16384:
            raise ValueError("invalid_intake_output")
        worker_report = validate_result(json.loads(completed.stdout))
        expected_exit = 0 if worker_report["status"] == "complete" else 20
        if completed.returncode != expected_exit:
            raise ValueError("intake_process_failed")
        result = worker_report
        if source_map() != before:
            raise ValueError("source_changed")
    except Exception:
        result = dict(status="unknown", reason="intake_or_source_unavailable")
        if worker_report is not None:
            result["worker_report"] = worker_report
    finally:
        del packet
        absent = cleanup("thericher-etf-context-" + identity, identity, environment)
    if not absent:
        result = dict(status="unknown", reason="intake_cleanup_unresolved", worker_report=result)
    return dict(
        result,
        image=image,
        exact_container_absent=absent,
        observed_at_utc=datetime.now(UTC).isoformat(),
        paper_only=True,
        scope="market_data_only",
        submit_capability=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--image", default="")
    args = parser.parse_args()
    try:
        value = run(image=args.image, execute=args.execute)
    except Exception:
        value = dict(status="unavailable", reason="launcher_preflight_failed")
    print(json.dumps(value, sort_keys=True))
    return 0 if value["status"] in {"inert", "complete"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
