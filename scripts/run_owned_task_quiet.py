"""Launch a pinned existing Data/Paper task action without a Windows console.

This changes process presentation only; the original worker owns its effects,
timeouts, locks, recovery and private outcome evidence.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def read_config(path, expected_sha):
    raw = Path(path).read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("config_binding")
    value = json.loads(raw)
    if set(value) != {"task", "execute", "arguments", "working_directory", "receipt_root"}:
        raise ValueError("config_schema")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value["task"]):
        raise ValueError("task_name")
    for key in ("execute", "arguments", "receipt_root"):
        if not isinstance(value[key], str) or "\x00" in value[key]:
            raise ValueError("config_value")
    if not Path(value["execute"]).is_absolute() or not Path(value["receipt_root"]).is_absolute():
        raise ValueError("absolute_path_required")
    directory = value["working_directory"]
    if directory is not None and (
        not isinstance(directory, str) or not Path(directory).is_absolute()
    ):
        raise ValueError("working_directory")
    return value


def launch(value, expected_sha):
    if os.name != "nt":
        raise ValueError("windows_required")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    # Keep Scheduler's existing argument string, including its quoting, intact.
    command = subprocess.list2cmdline([value["execute"]])
    if value["arguments"]:
        command += " " + value["arguments"]
    started = datetime.now(UTC).isoformat()
    code = 3
    status = "launch_failed"
    try:
        child = subprocess.Popen(
            command,
            executable=value["execute"],
            cwd=value["working_directory"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startup,
        )
        status = "worker_started_outcome_unknown"
        code = child.wait()
        status = "worker_returned"
    finally:
        root = Path(value["receipt_root"])
        root.mkdir(parents=True, exist_ok=True)
        receipt = {
            "task": value["task"],
            "action_config_sha256": expected_sha,
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
            "status": status,
            "exit_code": code,
            "create_no_window": True,
            "limitation": "process_launch_only_not_broker_or_scheduler_origin_proof",
        }
        with (root / (uuid4().hex + ".json")).open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    if not args.execute:
        return 0
    try:
        if args.config is None or re.fullmatch(r"[0-9a-f]{64}", args.sha256 or "") is None:
            return 3
        return launch(read_config(args.config, args.sha256), args.sha256)
    except Exception:
        # Never copy an original worker's command or private output to a log.
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
