"""Exact offline shadow input for fresh Paper preparation, not retained recovery.

Controls and their hashes are frozen by the caller, never selected from a result.
The reader touches only the original R2 claim's linked JSON metadata. It neither
loads numerical/model bytes nor proves provider finality or installed-job origin.
"""

from __future__ import annotations

import json
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Context, localcontext
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from thericher_v2.data.prospective_five_session_shadow_link import (
        ShadowControls,
        VerifiedShadowLink,
    )
    from thericher_v2.execution.kis_paper_five_session import KisPaperFiveSessionCohort

    from .five_session_paper_decision import FiveSessionPaperDecision

_GOAL = "kis-stock-five-session-prospective512-shadow-delivery-v1"
_ARTIFACTS = "D:/thericher-v2/model-artifacts"
_DELIVERY = f"{_ARTIFACTS}/research/{_GOAL}"
_RUNTIME = str(PureWindowsPath(_DELIVERY, "delivery-r2", "runtime"))
_R3_ROOT = str(PureWindowsPath(_DELIVERY, "delivery-r3"))
_CLAIM = str(PureWindowsPath(_RUNTIME, "opportunity.claim.json"))
_DATA = str(PureWindowsPath(_ARTIFACTS, "data", _GOAL))
_CACHE = (
    "D:/market_data/us_equities/kis_paper_private/stock-five-session-shadow512/v1/shadow-20261019"
)
_WORKER_R3 = "sha256:9846b862c878fbe68f5c5a38205db2aef0a774bec50b2b69680d6a9706c6bd97"
_GRADE = "hash_linked_metadata_availability_assumed_not_observed"


class ShadowInputError(ValueError):
    """Static local reader category, without paths or callback exception bodies."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ShadowInputError(reason)


def _metadata_path(value: str) -> PureWindowsPath:
    _require(type(value) is str, "metadata_path")
    path = PureWindowsPath(value)
    _require(
        path.is_absolute()
        and path.drive.casefold() == "d:"
        and ".." not in path.parts
        and not any(":" in part for part in path.parts[1:]),
        "metadata_path",
    )
    for root, pattern in (
        (
            _RUNTIME,
            r"(?:opportunity\.claim\.json|[0-9a-f]{32}/(?:receipt\.json|engine-plan\.json|"
            r"engine-attempt\.claim\.json|engine-output/result\.json|data-process/handoff\.json))",
        ),
        (
            _DATA,
            r"(?:runtime-contract\.json|attempt-[0-9a-f]{32}/(?:"
            r"receipt\.json|worker-receipt\.json|started\.json))",
        ),
        (
            _CACHE,
            r"(?:view/manifest\.json|snapshot=[A-Za-z0-9_.=-]{1,230}/(?:"
            r"manifest\.json|physical-capture\.json))",
        ),
    ):
        try:
            relative = path.relative_to(PureWindowsPath(root)).as_posix()
        except ValueError:
            continue
        if re.fullmatch(pattern, relative, re.ASCII):
            return path
    raise ShadowInputError("metadata_path")


def read_shadow_metadata(path: str, cap: int) -> bytes:
    """Bounded native filesystem reader; no directory search or non-JSON input."""
    target = Path(str(_metadata_path(path)))
    _require(target.is_absolute(), "native_windows_reader_required")
    _require(type(cap) is int and 0 < cap <= 4 * 1024**2, "metadata_cap")
    for component in (*reversed(target.parents), target):
        facts = component.lstat()
        _require(
            not stat.S_ISLNK(facts.st_mode)
            and not getattr(facts, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "metadata_link",
        )
    _require(stat.S_ISREG(facts.st_mode) and 0 < facts.st_size <= cap, "metadata_size")
    with target.open("rb") as stream:
        raw = stream.read(cap + 1)
    _require(0 < len(raw) <= cap, "metadata_size")
    return raw


@dataclass(frozen=True, slots=True, repr=False)
class ProspectiveShadowInput:
    """Finite fresh-input result; no account basis, inference or order authority."""

    status: str
    reason: str
    source_grade: str
    decision: FiveSessionPaperDecision | None = None
    cohort: KisPaperFiveSessionCohort | None = None
    link: VerifiedShadowLink | None = None


def load_prospective_shadow_input(
    *,
    controls: ShadowControls,
    as_of: datetime,
    read_metadata: Callable[[str, int], bytes] = read_shadow_metadata,
) -> ProspectiveShadowInput:
    """R3 controls -> original R2 claim -> Data 15 links -> schema1 DTO -> cohort.

    ``ShadowControls`` must include explicit caller-frozen R3 job/template hashes
    and delivery root, not the Data type's R2 defaults. Friday inference retains
    its actual timestamp when consumed Monday before the original entry expiry.
    Missing/faulted fresh input is local no-intent, never a retained-exit hold.
    The injected reader has the same exact JSON scope and per-read byte ceiling.
    """
    from thericher_v2.data.prospective_five_session_shadow_link import (
        ShadowControls,
        validate_shadow_controls,
        verify_shadow_link,
    )
    from thericher_v2.execution.kis_paper_five_session import cohort_from_paper_decision

    from .prospective_five_session_shadow_decision import restore_prospective_shadow_decision

    phase = "controls_invalid"
    link = None
    try:
        _require(type(as_of) is datetime and as_of.utcoffset() == timedelta(0), "input_clock")
        _require(
            type(controls) is ShadowControls
            and PureWindowsPath(controls.expected_delivery_root) == PureWindowsPath(_R3_ROOT),
            "input_controls",
        )
        validate_shadow_controls(controls)
        template = json.loads(controls.engine_template_bytes)
        _require(template["pins"]["/worker/shadow_worker.py"] == _WORKER_R3, "input_worker")
        data = json.loads(controls.data_plan_bytes)["metadata"]
        prior = datetime.fromisoformat(data["prior_clocks"][-1]["close_ts"])
        future = data["future_clocks"]
        opens = tuple(datetime.fromisoformat(row["open_ts"]) for row in future)
        closes = tuple(datetime.fromisoformat(row["close_ts"]) for row in future)
        nominal = datetime.fromisoformat(future[0]["decision_ts"])
        expiry = datetime.fromisoformat(template["entry_valid_until"])

        calls = total = 0

        def read(path: str, cap: int) -> bytes:
            nonlocal calls, total
            _metadata_path(path)
            _require(type(cap) is int and 0 < cap <= 4 * 1024**2, "metadata_cap")
            calls += 1
            _require(calls <= 2100, "metadata_read_budget")
            raw = read_metadata(path, cap)
            _require(type(raw) is bytes and 0 < len(raw) <= cap, "metadata_size")
            total += len(raw)
            _require(total <= 128 * 1024**2, "metadata_read_budget")
            return raw

        phase = "missing_shadow_claim"
        claim = read(_CLAIM, 65536)
        phase = "shadow_chain_invalid"
        link = verify_shadow_link(claim, controls=controls, read_metadata=read, observed_at=as_of)
        phase = "shadow_result_invalid"
        result_path = str(
            PureWindowsPath(_RUNTIME, link.invocation_id, "engine-output", "result.json")
        )
        raw = read(result_path, 1024**2)
        with localcontext(Context(prec=64, rounding=ROUND_DOWN)):
            bound = restore_prospective_shadow_decision(
                raw,
                expected_links=link.expected_engine_links(),
                identities=tuple(data["keys"]),
                prior_close_at=prior,
                nominal_decision_at=nominal,
                session_opens=opens,
                session_closes=closes,
                entry_valid_until=expiry,
                as_of=as_of,
                expected_worker_sha256=_WORKER_R3,
            )
            if bound.status != "bound_shadow_metadata":
                return ProspectiveShadowInput(
                    "no_intent", bound.reason, _GRADE, bound.decision, link=link
                )
            phase = "native_cohort_invalid"
            cohort = cohort_from_paper_decision(bound.decision, calendar_ref=bound.calendar_ref)
        return ProspectiveShadowInput("ready", bound.reason, _GRADE, bound.decision, cohort, link)
    except Exception:
        # Reader/constructor bodies may contain private values; publish only phase.
        return ProspectiveShadowInput("no_intent", phase, "unavailable", link=link)
