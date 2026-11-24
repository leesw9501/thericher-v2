"""Source-bound startup evidence for a scheduled Paper worker, before broker effects."""

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar
from uuid import uuid4

T = TypeVar("T")
Phase = Literal["entry", "exit"]
STAGES = ("source", "release", "window", "owner")
ERROR_CATEGORIES = (ValueError, TypeError, KeyError, OSError, RuntimeError, TimeoutError)


def _write(path: Path, value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def run_startup(
    root: Path,
    *,
    opportunity: str,
    source: str,
    phase: Phase,
    checks: Mapping[str, Callable[[], object]],
    prepare: Callable[[], T],
    claim_after_checks: bool = False,
) -> T:
    """Run preflight only, using a caller-owned evidence root, not financial state.

    Callbacks must not submit orders or reconcile custody. When claiming after
    checks, each diagnostic is independent; only the fixed claim directory
    consumes the slot. An interrupted claim must not be removed or retried.
    """
    if (
        not root.is_absolute()
        or re.fullmatch(r"[a-f0-9]{32}", opportunity) is None
        or re.fullmatch(r"[a-f0-9]{64}", source) is None
        or phase not in ("entry", "exit")
        or tuple(checks) != STAGES
    ):
        raise ValueError("Invalid Paper startup binding")
    attempt = dict(
        schema="paper_startup_v1",
        opportunity=opportunity,
        source=source,
        phase=phase,
        started_at=datetime.now(UTC).isoformat(),
    )
    slot = root / f"{opportunity}-{phase}"
    if claim_after_checks and slot.exists():
        raise FileExistsError(slot)
    directory = (
        root / f"diagnostic-{opportunity}-{phase}-{uuid4().hex}" if claim_after_checks else slot
    )
    directory.mkdir(exist_ok=False)
    digest = _write(directory / "ATTEMPT.json", attempt)

    def terminal(status: str, stage: str, category: str | None) -> None:
        _write(
            directory / "STARTUP.json",
            dict(
                attempt_sha256=digest,
                status=status,
                stage=stage,
                category=category,
                finished_at=datetime.now(UTC).isoformat(),
            ),
        )

    stage = "source"
    try:
        for stage in STAGES:
            checks[stage]()
        stage = "prepare"
        result = prepare()
        if claim_after_checks:
            stage = "claim"
            slot.mkdir(exist_ok=False)
            _write(slot / "CLAIM.json", dict(diagnostic=directory.name, attempt_sha256=digest))
            stage = "prepare"
    except Exception as error:
        kind = type(error)
        terminal("failed", stage, kind.__name__ if kind in ERROR_CATEGORIES else "Other")
        raise
    terminal("ready", stage, None)
    return result
