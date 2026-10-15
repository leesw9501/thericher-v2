"""Quiet immutable-source host for one bounded native owned stock Paper visit.

Run this script from the parent-owned frozen repository. An exact external
source manifest is required for explicit execution; credentials are selected
only from the original project's private file, never copied to the snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL_PATH = Path("C:/Users/Public/Documents/thericher-v2/.env")
ARTIFACT = Path("D:/thericher-v2/model-artifacts")
LABEL = "thericher.execution.current-stock.uuid"
WORKER = "scripts/run_kis_paper_current_stock_cycle_worker.py"
HOST = "scripts/run_kis_paper_current_stock_cycle.py"
HELPERS = (
    "scripts/run_kis_paper_current_daily_session.py",
    "scripts/run_kis_paper_etf_daily_context.py",
)
VOLUMES = (
    "thericher-v2-paper-canary-private-acct-20261007-v1",
    "thericher-v2_thericher-v2-runtime",
    "thericher-v2_thericher-v2-web-emergency",
)
SAFE_REASONS = frozenset(
    {
        "already_completed",
        "native_recovery_required",
        "worker_recovery_required",
        "native_leg_closed",
        "exact_request_retained",
        "await_declared_exit",
        "outside_declared_session",
        "policy_owned_flat",
        "native_risk_no_intent",
        "cycle_reference_invalid",
        "cycle_value_invalid",
        "cycle_checkpoint_invalid",
        "cycle_existing_basis_required",
        "cycle_basis_changed",
        "cycle_client_unavailable",
        "cycle_client_invalid",
        "cycle_account_changed",
        "cycle_owner_missing",
        "cycle_foreign_stock_registration",
        "cycle_input_invalid",
        "cycle_session_invalid",
        "cycle_ten_targets_required",
        "cycle_target_invalid",
        "cycle_target_duplicate",
        "cycle_target_clock_invalid",
        "cycle_input_binding_mismatch",
        "cycle_receipt_invalid",
        "cycle_reservation_missing",
        "cycle_request_changed",
        "cycle_reservation_changed",
        "cycle_retained_quote_stale",
        "cycle_configuration_invalid",
        "cycle_target_unavailable",
        "cycle_target_quote_unavailable",
        "cycle_quote_timestamp_unavailable",
        "cycle_quote_timestamp_invalid",
        "cycle_quote_timestamp_stale",
        "cycle_quote_tick_invalid",
        "cycle_quote_bid_ask_invalid",
        "cycle_readonly_snapshot_unavailable",
        "cycle_policy_changed",
        "cycle_never_reserved_retired",
        "cycle_retirement_unproven",
        "cycle_retired_request_restored",
        "cycle_owned_not_flat",
    }
)
STATUS_REASONS = {
    "advanced": {"native_leg_closed"},
    "pending": {"exact_request_retained"},
    "hold": {"await_declared_exit", "outside_declared_session"},
    "complete": {"already_completed", "policy_owned_flat"},
    "no_intent": {
        "native_risk_no_intent",
        "cycle_never_reserved_retired",
        "cycle_target_quote_unavailable",
    },
    "unavailable": {
        value
        for value in SAFE_REASONS
        if (
            value.startswith("cycle_")
            and value not in {"cycle_never_reserved_retired", "cycle_target_quote_unavailable"}
        )
        or value in {"native_recovery_required", "worker_recovery_required"}
    },
}
BASE_KEYS = frozenset({"kind", "status", "reason", "limitation", "leg_count"})
EXTRA_KEYS = frozenset(
    {
        "paper_only",
        "unknown_effects_not_assumed_zero",
        "calls",
        "visits",
        "http_start_gaps_seconds",
        "pacing_basis",
        "observed_at_utc",
        "fees",
        "settled_cash",
        "net_pnl",
    }
)


def _docker(args, **kwargs):
    return subprocess.run(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)


def _daily():
    sys.path.insert(0, str(ROOT / "src"))
    path = ROOT / HELPERS[0]
    spec = importlib.util.spec_from_file_location("current_stock_daily_host_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.LABEL = LABEL
    # Do not mutate the shared subprocess module used by the original host.
    module.subprocess = SimpleNamespace(run=_docker, DEVNULL=subprocess.DEVNULL)
    return module


def os_environment():
    return _daily().os_environment()


def load_paper_config():
    # Lazy import after immutable source verification; no implicit dotenv load.
    sys.path.insert(0, str(ROOT / "src"))
    from thericher_v2.execution.kis_readonly import load_kis_paper_config

    return load_kis_paper_config(CREDENTIAL_PATH)


def source_map():
    paths = list((ROOT / "src").rglob("*.py")) + [ROOT / name for name in (HOST, WORKER, *HELPERS)]
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_field")
        result[key] = value
    return result


def _json(raw):
    return json.loads(
        raw,
        object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_number")),
    )


def read_manifest(path, pin):
    if type(pin) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", pin) is None:
        raise ValueError("exact_source_manifest_required")
    with Path(path).open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != pin[7:]:
        raise ValueError("source_manifest_mismatch")
    value = _json(raw)
    if type(value) is not dict or set(value) != {"files"} or type(value["files"]) is not dict:
        raise ValueError("source_manifest_invalid")
    expected = value["files"]
    if expected != source_map():
        raise ValueError("host_source_manifest_mismatch")
    return expected


def command(image, identity, *, execute=False):
    if type(identity) is not str or re.fullmatch(r"[0-9a-f]{32}", identity) is None:
        raise ValueError("actor_identity_invalid")
    args = _daily().command(image, identity)
    substitutions = {
        "thericher-daily-portfolio-" + identity: "thericher-current-stock-" + identity,
        "/app/scripts/run_kis_paper_current_daily_session_worker.py": "/app/" + WORKER,
    }
    args = [substitutions.get(value, value) for value in args]
    if not execute:
        args.remove("--execute")
        args[2:2] = ["--network", "none"]
    return args


def cleanup(name, identity, environment):
    if not _daily().cleanup(name, identity, environment):
        return False
    try:
        remaining = _docker(
            [
                "docker",
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                "label=" + LABEL + "=" + identity,
            ],
            env=environment,
            capture_output=True,
            timeout=5,
        )
        return remaining.returncode == 0 and not remaining.stdout.strip()
    except Exception:
        return False


def validate_result(value):
    def invalid():
        raise ValueError("stock_worker_output_invalid")

    if (
        type(value) is not dict
        or not set(value) <= BASE_KEYS | EXTRA_KEYS
        or value.get("paper_only") is not True
        or type(value.get("status")) is not str
        or value["status"] not in STATUS_REASONS
        or type(value.get("reason")) is not str
        or value["reason"] not in STATUS_REASONS[value["status"]]
    ):
        invalid()
    if value["status"] != "unavailable" and set(value) != BASE_KEYS | EXTRA_KEYS:
        invalid()
    if "kind" in value and value["kind"] != "kis_paper_current_stock_cycle_v1":
        invalid()
    if (
        "limitation" in value
        and value["limitation"] != "cycle_status_not_current_inventory_or_net_pnl"
    ):
        invalid()
    for key in ("fees", "settled_cash", "net_pnl"):
        if key in value and value[key] != "not_observed":
            invalid()
    if (
        "unknown_effects_not_assumed_zero" in value
        and value["unknown_effects_not_assumed_zero"] is not True
    ):
        invalid()
    if "visits" in value and (type(value["visits"]) is not int or value["visits"] != 1):
        invalid()
    if "leg_count" in value and (
        type(value["leg_count"]) is not int or value["leg_count"] not in {0, 1}
    ):
        invalid()
    if "calls" in value:
        calls = value["calls"]
        if (
            type(calls) is not dict
            or set(calls)
            != {"token_posts", "get_requests", "buy_posts", "sell_posts", "cancel_posts"}
            or any(type(n) is not int or not 0 <= n <= 128 for n in calls.values())
            or calls["token_posts"] > 1
            or calls["cancel_posts"] > 1
            or calls["buy_posts"] + calls["sell_posts"] > 1
            or sum(calls.values()) > 128
        ):
            invalid()
    if "http_start_gaps_seconds" in value:
        gaps = value["http_start_gaps_seconds"]
        if (
            type(gaps) is not list
            or len(gaps) > 127
            or any(type(n) not in {int, float} or not math.isfinite(n) or n < 0 for n in gaps)
            or "calls" not in value
            or len(gaps) != max(0, sum(value["calls"].values()) - 1)
        ):
            invalid()
    if (
        "pacing_basis" in value
        and value["pacing_basis"] != "final_opener_delegate_boundary_not_socket_wire_measurement"
    ):
        invalid()
    if "observed_at_utc" in value:
        try:
            at = datetime.fromisoformat(value["observed_at_utc"])
            if at.utcoffset() is None or at.utcoffset().total_seconds() != 0:
                invalid()
        except (ValueError, TypeError):
            invalid()
    return value


def _failure(reason="worker_recovery_required", worker_report=None):
    value = dict(
        status="unavailable", reason=reason, paper_only=True, unknown_effects_not_assumed_zero=True
    )
    if worker_report is not None:
        value["worker_report"] = worker_report
    return value


def run(*, image="", execute=False, source_manifest=None, source_manifest_ref=""):
    if not execute:
        return dict(status="inert", credential_reads=0, broker_calls=0)
    before = read_manifest(source_manifest, source_manifest_ref)
    identity = uuid4().hex
    args = command(image, identity, execute=True)
    environment = os_environment()
    probe_name = "thericher-current-stock-source-" + identity
    code = (
        "import json,hashlib;from pathlib import Path;files=" + repr(tuple(before)) + ";"
        "paths={p.relative_to('/app').as_posix() for p in Path('/app/src').rglob('*.py')};"
        "paths.update(n for n in files if not n.startswith('src/'));"
        "print(json.dumps({n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest() "
        "for n in paths}))"
    )
    try:
        probe = _docker(
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
    if probe.returncode or len(probe.stdout) > 1024 * 1024 or _json(probe.stdout) != before:
        raise ValueError("worker_image_source_mismatch")
    for volume in VOLUMES:
        _docker(
            ["docker", "volume", "inspect", volume],
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    config = load_paper_config()
    packet = json.dumps(
        dict(
            KIS_PAPER_APP_KEY=config.app_key,
            KIS_PAPER_APP_SECRET=config.app_secret,
            KIS_PAPER_ACCOUNT_NO=config.account_number,
            KIS_PAPER_ACCOUNT_PRODUCT_CODE=config.account_product_code,
            THERICHER_MODE="kis_paper",
        )
    ).encode("ascii")
    report = None
    try:
        finished = _docker(
            args,
            input=packet,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=320,
            check=False,
        )
        if len(finished.stdout) > 16384:
            raise ValueError("stock_worker_output_invalid")
        report = validate_result(_json(finished.stdout))
        if finished.returncode != (20 if report["status"] == "unavailable" else 0):
            raise ValueError("worker_exit_mismatch")
        if source_map() != before:
            raise ValueError("host_source_changed")
        result = report
    except Exception:
        result = _failure(worker_report=report)
    finally:
        del packet
        absent = cleanup("thericher-current-stock-" + identity, identity, environment)
    if not absent:
        result = _failure("worker_cleanup_unresolved", result)
    result.update(
        exact_container_absent=absent,
        image=image,
        source_manifest_ref=source_manifest_ref,
        completed_at_utc=datetime.now(UTC).isoformat(),
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--image", default="")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--source-manifest-ref", default="")
    args = parser.parse_args(argv)
    try:
        result = run(
            image=args.image,
            execute=args.execute,
            source_manifest=args.source_manifest,
            source_manifest_ref=args.source_manifest_ref,
        )
    except Exception:
        result = _failure("launcher_preflight_failed")
    if args.execute:
        root = ARTIFACT / "execution/current-nas-owned-model-paper-runtime-20261015-v1"
        root.mkdir(parents=True, exist_ok=True)
        path = root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        with path.open("x", encoding="ascii") as stream:
            json.dump(result, stream, sort_keys=True)
        result["evidence_path"] = str(path)
    print(json.dumps(result, sort_keys=True))
    return (
        0
        if result["status"] in {"inert", "complete", "no_intent", "pending", "advanced", "hold"}
        else 20
    )


if __name__ == "__main__":
    raise SystemExit(main())
