"""Quiet, source-pinned Docker Paper worker; no credentials in argv or Docker env."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from thericher_v2.execution.kis_readonly import load_kis_paper_config

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = Path("D:/thericher-v2/model-artifacts")
MARKET = Path("D:/market_data")
VOLUMES = (
    "thericher-v2-paper-canary-private-acct-20261007-v1",
    "thericher-v2_thericher-v2-runtime",
    "thericher-v2_thericher-v2-web-emergency",
)
LABEL = "thericher.execution.daily-portfolio.uuid"
SAFE_KEYS = frozenset(
    {
        "kind",
        "status",
        "reason",
        "limitation",
        "paper_only",
        "visits",
        "calls",
        "market_daily_gets",
        "collection_reason",
        "next_due_utc",
        "observed_at_utc",
        "fees",
        "settled_cash",
        "net_pnl",
        "unknown_effects_not_assumed_zero",
    }
)
SAFE_REASONS = frozenset(
    {
        "execution_not_requested",
        "exact_cycle_advanced",
        "exact_cycle_complete",
        "already_completed",
        "current_input_unavailable",
        "native_recovery_required",
        "retained_context_recovery_required",
        "session_configuration_invalid",
        "worker_recovery_required",
    }
)


def os_environment():
    helper = Path(__file__).with_name("run_kis_paper_etf_daily_context.py")
    spec = importlib.util.spec_from_file_location("daily_paper_docker_environment", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.os_environment()


def source_map():
    files = list((ROOT / "src").rglob("*.py")) + [
        ROOT / "scripts/run_kis_paper_current_daily_session_worker.py"
    ]
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }


def validate_result(value):
    if (
        type(value) is not dict
        or not set(value) <= SAFE_KEYS
        or value.get("paper_only") is not True
        or value.get("status") not in {"complete", "pending", "no_intent", "unavailable"}
        or value.get("reason") not in SAFE_REASONS
    ):
        raise ValueError("daily_worker_output_invalid")
    if (
        "kind" in value
        and value["kind"] != "kis_paper_current_daily_session_v1"
        or "limitation" in value
        and value["limitation"] != "cycle_status_not_current_inventory_or_net_pnl"
    ):
        raise ValueError("daily_worker_output_invalid")
    for key in ("fees", "settled_cash", "net_pnl"):
        if key in value and value[key] != "not_observed":
            raise ValueError("daily_worker_output_invalid")
    if (
        "unknown_effects_not_assumed_zero" in value
        and value["unknown_effects_not_assumed_zero"] is not True
    ):
        raise ValueError("daily_worker_output_invalid")
    if "visits" in value:
        if type(value["visits"]) is not list or len(value["visits"]) > 4:
            raise ValueError("daily_worker_output_invalid")
        for row in value["visits"]:
            if (
                type(row) is not dict
                or set(row) != {"kind", "status", "reason", "limitation"}
                or row["kind"] != "kis_paper_current_daily_session_v1"
                or row["status"] not in {"complete", "pending", "no_intent", "unavailable"}
                or row["reason"] not in SAFE_REASONS
                or row["limitation"] != "cycle_status_not_current_inventory_or_net_pnl"
            ):
                raise ValueError("daily_worker_output_invalid")
    if "calls" in value:
        calls = value["calls"]
        if (
            type(calls) is not dict
            or set(calls)
            != {"token_posts", "get_requests", "buy_posts", "sell_posts", "cancel_posts"}
            or any(type(n) is not int or not 0 <= n <= 128 for n in calls.values())
            or calls["token_posts"] > 1
            or calls["buy_posts"] + calls["sell_posts"] > 3
            or calls["cancel_posts"] > 3
            or sum(calls.values()) > 128
        ):
            raise ValueError("daily_worker_output_invalid")
    if "market_daily_gets" in value and not (
        type(value["market_daily_gets"]) is int and 0 <= value["market_daily_gets"] <= 16
    ):
        raise ValueError("daily_worker_output_invalid")
    from thericher_v2.data.kis_paper_etf_daily_context import _FAILURES

    if value.get("collection_reason") not in _FAILURES | {None}:
        raise ValueError("daily_worker_output_invalid")
    for key in ("observed_at_utc", "next_due_utc"):
        if value.get(key) is not None:
            at = datetime.fromisoformat(value[key])
            if at.utcoffset() is None or at.utcoffset().total_seconds() != 0:
                raise ValueError("daily_worker_output_invalid")
    return value


def command(image, identity):
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise ValueError("exact_local_image_required")
    args = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--name",
        "thericher-daily-portfolio-" + identity,
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
    ]
    for volume, target in zip(VOLUMES, ("private", "runtime", "emergency"), strict=True):
        args += ["--mount", f"type=volume,source={volume},target=/app/{target},volume-nocopy"]
    return args + [
        "--mount",
        "type=bind,source=" + str(MARKET) + ",target=/app/market_data",
        "--mount",
        "type=bind,source=" + str(ARTIFACT) + ",target=/app/model_artifacts",
        "--entrypoint",
        "timeout",
        image,
        "300",
        "python",
        "-B",
        "/app/scripts/run_kis_paper_current_daily_session_worker.py",
        "--execute",
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


def run(*, image, execute=False):
    if not execute:
        return dict(status="inert", credential_reads=0, broker_calls=0)
    identity = uuid4().hex
    args = command(image, identity)
    environment = os_environment()
    before = source_map()
    code = (
        "import json,hashlib;from pathlib import Path;files=" + repr(tuple(before)) + ";"
        "print(json.dumps({n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest() "
        "for n in files}))"
    )
    probe_name = "thericher-daily-source-" + identity
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
                code,
            ],
            env=environment,
            capture_output=True,
            timeout=15,
            check=False,
        )
    finally:
        if not cleanup(probe_name, identity, environment):
            raise ValueError("source_probe_not_reaped")
    if probe.returncode or json.loads(probe.stdout) != before:
        raise ValueError("worker_image_source_mismatch")
    for volume in VOLUMES:
        subprocess.run(
            ["docker", "volume", "inspect", volume],
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    config = load_kis_paper_config(ROOT / ".env")
    packet = json.dumps(
        dict(
            KIS_PAPER_APP_KEY=config.app_key,
            KIS_PAPER_APP_SECRET=config.app_secret,
            KIS_PAPER_ACCOUNT_NO=config.account_number,
            KIS_PAPER_ACCOUNT_PRODUCT_CODE=config.account_product_code,
            THERICHER_MODE="kis_paper",
        )
    ).encode()
    result = dict(
        status="unavailable",
        reason="worker_recovery_required",
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
    )
    absent = False
    worker_report = None
    try:
        finished = subprocess.run(
            args,
            input=packet,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=320,
            check=False,
        )
        if len(finished.stdout) > 16384:
            raise ValueError("daily_worker_output_invalid")
        worker_report = validate_result(json.loads(finished.stdout))
        expected_exit = 20 if worker_report["status"] == "unavailable" else 0
        if finished.returncode != expected_exit:
            raise ValueError("worker_exit_mismatch")
        result = worker_report
        if source_map() != before:
            raise ValueError("host_source_changed")
    except Exception:
        result = dict(
            status="unavailable",
            reason="worker_recovery_required",
            paper_only=True,
            unknown_effects_not_assumed_zero=True,
        )
        if worker_report is not None:
            result["worker_report"] = worker_report
    finally:
        del packet
        absent = cleanup("thericher-daily-portfolio-" + identity, identity, environment)
    if not absent:
        result = dict(
            status="unavailable",
            reason="worker_cleanup_unresolved",
            paper_only=True,
            unknown_effects_not_assumed_zero=True,
            worker_report=result,
        )
    result.update(
        exact_container_absent=absent,
        image=image,
        source_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        completed_at_utc=datetime.now(UTC).isoformat(),
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--image", default="")
    args = parser.parse_args()
    try:
        result = run(image=args.image, execute=args.execute)
    except Exception:
        result = dict(status="unavailable", reason="launcher_preflight_failed")
    if args.execute:
        root = ARTIFACT / "execution/current-daily-portfolio-dispatch-v1"
        root.mkdir(parents=True, exist_ok=True)
        path = root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        with path.open("x", encoding="utf-8") as file:
            json.dump(result, file, sort_keys=True, indent=2)
        result["evidence_path"] = str(path)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"inert", "complete", "no_intent", "pending"} else 20


if __name__ == "__main__":
    raise SystemExit(main())
