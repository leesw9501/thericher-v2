"""Source-bound startup evidence for a scheduled Paper worker, before broker effects."""

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar

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
) -> T:
    """Run preflight only, using a caller-owned evidence root, not financial state.

    Callbacks must not submit orders or reconcile custody. An existing attempt
    or an interrupted write never grants another preflight for that opportunity.
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
    directory = root / f"{opportunity}-{phase}"
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
    except Exception as error:
        kind = type(error)
        terminal("failed", stage, kind.__name__ if kind in ERROR_CATEGORIES else "Other")
        raise
    terminal("ready", stage, None)
    return result
