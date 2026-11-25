"""Fixed-path Linux entry point for the owner-bound Dec4 NET25 capsule."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, "/app/src")

from thericher_v2.ops.h3_dec4_capsule import (  # noqa: E402
    inspect_dec4_capsule,
    run_dec4_account_capsule,
)

BINDING = Path("/admission/CAPSULE-BINDING.json")
FRAME = Path("/admission/NET25.frame")
WORKER = Path("/app/scripts/run_kis_paper_current_stock_cycle_worker.py")
OUTCOME = Path("/out/RAW-PRODUCER.json")


class _Args(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid capsule arguments\n")


def _read(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise ValueError("capsule_member_length")
    return raw


def _worker_bytes(expected):
    raw = _read(WORKER, 2 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("capsule_worker_digest")
    return raw


def _load_worker(expected):
    raw = _worker_bytes(expected)
    worker = ModuleType("_dec4_owned_worker")
    worker.__file__ = str(WORKER)
    sys.modules[worker.__name__] = worker
    exec(compile(raw, str(WORKER), "exec"), worker.__dict__)
    return vars(worker)


def _emit(result, *, retain):
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if retain:
        with OUTCOME.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def main():
    parser = _Args()
    parser.add_argument("--binding-sha256", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--verify-frame", action="store_true")
    modes.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    stage = "input"
    try:
        binding, guest = inspect_dec4_capsule(
            _read(BINDING, 16_384),
            _read(FRAME, 2 * 1024 * 1024),
            binding_sha256=args.binding_sha256,
        )
        stage = "worker"
        _worker_bytes(binding["worker_sha256"])
        if args.verify_frame:
            _emit(
                dict(
                    status="frame_verified",
                    phase=guest.cohort.slot.phase,
                    financial_claim="UNKNOWN",
                ),
                retain=False,
            )
            return 0
        stage = "session"
        result = run_dec4_account_capsule(
            binding,
            guest,
            stream=sys.stdin.buffer,
            sink=sys.stdout.buffer,
            load_worker=_load_worker,
        )
    except Exception:
        # A fault after admission may have effects. Never project it as no intent.
        result = dict(
            schema="dec4-net25-capsule-fault-v1",
            status="unavailable",
            stage=stage,
            financial_claim="UNKNOWN",
            reservation_release=False,
        )
    _emit(result, retain=args.execute)
    return 20 if result["status"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
