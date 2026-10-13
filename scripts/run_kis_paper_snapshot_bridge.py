"""Paper snapshot freshness consumer: selective credentials and sanitized Docker launch."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from thericher_v2.execution import kis_readonly as ro
from thericher_v2.execution.kis_paper_console_bridge import (
    KisPaperConsoleBridgeOutcome,
    kis_paper_bridge_source_digest,
)

OS_DOCKER_KEYS = (
    "PATH",
    "SystemRoot",
    "SYSTEMROOT",
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
FIELDS = frozenset(
    {
        "status",
        "reason_code",
        "observed_at",
        "evidence_path",
        "observer_evidence_path",
        "observer_invocation_id",
        "scope",
        "account_snapshot_complete",
    }
)
SAFE_REASONS = frozenset(
    {
        "unexpected_failure",
        "refresh_in_progress",
        "refresh_busy",
        "config_missing",
        "config_duplicate",
        "config_account_invalid",
        "config_product_invalid",
        "access_token_invalid",
        "auth_response_invalid",
        "auth_rejected",
        "token_request_not_due",
        "token_request_busy",
        "balance_rejected",
        "open_orders_rejected",
        "orderable_funds_rejected",
        "ccnl_rejected",
        "ccnl_pagination_incomplete",
        "ccnl_response_incomplete",
        "preview_quote_rejected",
        "preview_quote_incomplete",
        "transport_failure",
        "response_invalid",
        "paper_host_required",
        "redirect_rejected",
        "request_not_allowlisted",
        "query_not_allowlisted",
        "balance_pagination_incomplete",
        "balance_response_duplicate",
        "balance_response_incomplete",
        "open_orders_pagination_incomplete",
        "open_orders_response_duplicate",
        "open_orders_response_incomplete",
        "orderable_funds_pagination_incomplete",
        "orderable_funds_response_duplicate",
        "orderable_funds_response_incomplete",
    }
)
# Leave 45 seconds of the existing PT4M limit for host checks and outcome handling.
BRIDGE_TIMEOUT_SECONDS = 180
CLEANUP_TIMEOUT_SECONDS = 5
INVOCATION_LABEL = "thericher.snapshot-observer.invocation"
OWNERSHIP_FORMAT = (
    '{"id":{{json .Id}},"name":{{json .Name}},'
    f'"invocation":{{{{json (index .Config.Labels "{INVOCATION_LABEL}")}}}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"read_only":{{json .HostConfig.ReadonlyRootfs}}}'
)


def failure(category: str) -> dict[str, object]:
    return {
        "kind": "kis_paper_snapshot_bridge_launcher",
        "status": "unavailable",
        "failure_category": category,
        "submit_capability": False,
    }


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def sanitize(stdout: bytes | str, invocation_id: str) -> dict[str, object]:
    if len(stdout) > 65536:
        raise ValueError("oversized output")
    value = json.loads(stdout, object_pairs_hook=unique_object)
    source_fields = FIELDS | {"runtime_source_sha256"}
    if not isinstance(value, dict) or set(value) not in (
        source_fields,
        source_fields | {"diagnostic"},
    ):
        raise ValueError("output schema")
    if value["runtime_source_sha256"] != kis_paper_bridge_source_digest():
        raise ValueError("runtime source mismatch")
    if value["scope"] != "read_only" or type(value["account_snapshot_complete"]) is not bool:
        raise ValueError("scope")
    observed = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
    if observed.tzinfo is not UTC:
        raise ValueError("clock")
    status, reason = value["status"], value["reason_code"]
    if status not in {"complete", "unavailable", "busy"}:
        raise ValueError("status")
    if reason is not None and reason not in SAFE_REASONS:
        raise ValueError("reason")
    if value["account_snapshot_complete"] is not (status == "complete"):
        raise ValueError("completeness")
    diagnostic = value.get("diagnostic", {})
    if not isinstance(diagnostic, dict):
        raise ValueError("diagnostic")
    if diagnostic:
        ro.validate_kis_paper_readonly_diagnostic(diagnostic)
    if status == "busy":
        if any(
            value[key] is not None
            for key in (
                "evidence_path",
                "observer_evidence_path",
                "observer_invocation_id",
            )
        ):
            raise ValueError("busy identity")
    else:
        stamp = observed.strftime("%Y%m%dT%H%M%S%fZ")
        if value["observer_invocation_id"] != invocation_id:
            raise ValueError("invocation")
        if value["evidence_path"] != (
            f"/app/model_artifacts/execution/kis-paper-console-bridge/{stamp}-{status}.json"
        ) or value["observer_evidence_path"] != (
            f"/app/model_artifacts/execution/kis-paper-snapshot-observer/"
            f"{stamp}-{invocation_id}-{status}.json"
        ):
            raise ValueError("evidence path")
    KisPaperConsoleBridgeOutcome(
        status=status,
        reason_code=reason,
        observed_at=observed,
        snapshot_path=Path("runtime/state/paper_account_snapshot.json"),
        evidence_path=Path(value["evidence_path"]) if value["evidence_path"] else None,
        observer_evidence_path=(
            Path(value["observer_evidence_path"]) if value["observer_evidence_path"] else None
        ),
        diagnostic=diagnostic,
    )
    return {key: value[key] for key in sorted(FIELDS)}


def cleanup_owned_container(
    name: str, invocation_id: str, project_root: Path, docker_env: dict[str, str]
) -> bool:
    try:
        inspected = subprocess.run(
            ["docker.exe", "container", "inspect", "--format", OWNERSHIP_FORMAT, name],
            cwd=project_root,
            env=docker_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=CLEANUP_TIMEOUT_SECONDS,
        )
        if inspected.returncode or len(inspected.stdout) > 4096:
            return False
        owner = json.loads(inspected.stdout, object_pairs_hook=unique_object)
        if (
            not isinstance(owner, dict)
            or set(owner) != {"id", "name", "invocation", "service", "read_only"}
            or not isinstance(owner["id"], str)
            or re.fullmatch(r"[a-f0-9]{64}", owner["id"]) is None
            or owner["name"] != f"/{name}"
            or owner["invocation"] != invocation_id
            or owner["service"] != "kis-readonly"
            or owner["read_only"] is not True
        ):
            return False
        # Use the verified immutable ID, not a name that could be reassigned.
        removed = subprocess.run(
            ["docker.exe", "container", "rm", "--force", owner["id"]],
            cwd=project_root,
            env=docker_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=CLEANUP_TIMEOUT_SECONDS,
        )
        if removed.returncode:
            return False
        remaining = subprocess.run(
            [
                "docker.exe",
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"id={owner['id']}",
            ],
            cwd=project_root,
            env=docker_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=CLEANUP_TIMEOUT_SECONDS,
        )
        return remaining.returncode == 0 and not remaining.stdout.strip()
    except Exception:
        return False


def launch(
    project_root: Path,
    credential_path: Path,
    invocation_id: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], int]:
    try:
        invocation = UUID(invocation_id)
        if invocation.version != 4 or str(invocation) != invocation_id:
            raise ValueError("invocation")
    except (ValueError, TypeError, AttributeError):
        return failure("invocation_invalid"), 3
    try:
        config = ro.load_kis_paper_config(credential_path)
    except Exception:
        return failure("paper_config_unavailable"), 3
    source = os.environ if environment is None else environment
    docker_env = {key: source[key] for key in OS_DOCKER_KEYS if key in source}
    child_env = dict(docker_env)
    child_env.update(
        {
            "KIS_PAPER_APP_KEY": config.app_key,
            "KIS_PAPER_APP_SECRET": config.app_secret,
            "KIS_PAPER_ACCOUNT_NO": config.account_number,
            "KIS_PAPER_ACCOUNT_PRODUCT_CODE": config.account_product_code,
            "COMPOSE_DISABLE_ENV_FILE": "1",
        }
    )
    container_name = f"thericher-snapshot-bridge-{invocation.hex}"
    command = [
        "docker.exe",
        "compose",
        "--env-file",
        str(project_root / ".env.example"),
        "--project-directory",
        str(project_root),
        "--profile",
        "kis-readonly",
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
        "--name",
        container_name,
        "--label",
        f"{INVOCATION_LABEL}={invocation_id}",
        "-e",
        f"THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID={invocation_id}",
        "kis-readonly",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=BRIDGE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        cleaned = cleanup_owned_container(container_name, invocation_id, project_root, docker_env)
        return failure("docker_timeout" if cleaned else "docker_timeout_cleanup_unknown"), 3
    except Exception:
        return failure("docker_launch_failed"), 3
    try:
        payload = sanitize(completed.stdout, invocation_id)
    except Exception:
        return failure("bridge_output_invalid"), completed.returncode or 3
    if completed.returncode and payload["status"] != "unavailable":
        return failure("docker_nonzero_exit"), completed.returncode
    return payload, completed.returncode


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid arguments")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = SafeParser()
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--project-root", type=Path)
        parser.add_argument("--paper-credential-path", type=Path)
        parser.add_argument("--observer-invocation-id")
        args = parser.parse_args(argv)
        if not args.execute:
            payload, code = {"status": "inert", "submit_capability": False}, 0
        elif None in (args.project_root, args.paper_credential_path, args.observer_invocation_id):
            payload, code = failure("arguments_missing"), 3
        else:
            payload, code = launch(
                args.project_root,
                args.paper_credential_path,
                args.observer_invocation_id,
            )
    except Exception:
        payload, code = failure("launcher_failed"), 3
    print(json.dumps(payload, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
