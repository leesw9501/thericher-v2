"""Pure Dec4/9 observer pins for the Paper BankLeg's suspend/check/restore bridge.

The protected launcher freezes this plan before either leg. The bridge, not
this module, attests native facts, takes the disable receipt, and restores
only after positive closure of the exact owner. No Scheduler or filesystem I/O.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import PureWindowsPath
from re import fullmatch

from thericher_v2.execution.paper_peer_visit import encode
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_schedule_plan import _path, _pin
from thericher_v2.ops.paper_startup import Phase

OBSERVER_NAME = "thericher-kis-paper-snapshot-observer"
OBSERVER_TASK_PATH = "\\" + OBSERVER_NAME
# Local registered-task XML and API7 SDDL, hashed as exact UTF-8 text.
OBSERVER_XML_SHA256 = "e2cbf12f821dd447ecf4a1f3f65498795363a52ecb7a9654e45360498d94d827"
OBSERVER_API7_SHA256 = "fab150776db7652ebf7fe24828069e0637db567357437cf6f93bbb1141f28a04"
_REFERENCE_SOURCES = {
    "2b0ce611d33c4c29d712ad994cbee8dcca220d567a370abf0192d67e6dcaf7a8",
    "3291ca1e75a9f8dd49525c293799d30e6b0e5a3733e813e311e017896233c0be",
}
READINESS_SCHEMA = "DEC4_H3_OBSERVER_READINESS_V1"


@dataclass(frozen=True, slots=True)
class Dec4ObserverPlan:
    phase: Phase
    package_root: str
    bridge_sha256: str
    core_sha256: str

    def __post_init__(self) -> None:
        if type(self.phase) is not str or self.phase not in ("entry", "exit"):
            raise ValueError("dec4_observer_phase")
        root = _path(self.package_root)
        if len(root.parts) < 2 or ".." in root.parts:
            raise ValueError("dec4_observer_package_root")
        pins = (_pin(self.bridge_sha256), _pin(self.core_sha256))
        if pins[0] == pins[1] or any(pin in _REFERENCE_SOURCES for pin in pins):
            raise ValueError("dec4_observer_bridge_source")

    @property
    def helper_root(self) -> PureWindowsPath:
        return PureWindowsPath(self.package_root) / f"observer-{self.phase}"

    @property
    def work_root(self) -> PureWindowsPath:
        return self.helper_root / "work"

    @property
    def output_root(self) -> PureWindowsPath:
        return self.helper_root / "owned-output"

    @property
    def policy_path(self) -> PureWindowsPath:
        return self.helper_root / "POLICY.json"

    @property
    def policy_bytes(self) -> bytes:
        """Exact yield-core ABI; restore has a lower bound, not an expiry.

        An overrun never grants admission, but must not strand a known disable
        obligation once the independent exact-owner closure is available.
        """
        opens, closes, _ = _TIMES[self.phase]
        return encode(
            dict(
                name=OBSERVER_NAME,
                original_enabled=True,
                xml_sha256=OBSERVER_XML_SHA256,
                api7_sha256=OBSERVER_API7_SHA256,
                suspend_not_before=opens.isoformat(),
                suspend_not_after=closes.isoformat(),
                restore_not_before=opens.isoformat(),
            )
        )

    @property
    def policy_sha256(self) -> str:
        return sha256(self.policy_bytes).hexdigest()

    @property
    def manifest_bytes(self) -> bytes:
        """Pin the policy, exact helper source/paths and the bank leg together."""
        opens, closes, hard = _TIMES[self.phase]
        return encode(
            dict(
                schema="DEC4_H3_OBSERVER_PLAN_V1",
                round=ROUND,
                phase=self.phase,
                bank_task_path="\\" + TASKS[self.phase],
                observer_task_path=OBSERVER_TASK_PATH,
                opens_utc=opens.isoformat(),
                closes_utc=closes.isoformat(),
                hard_utc=hard.isoformat(),
                helper_root=str(self.helper_root),
                work_root=str(self.work_root),
                output_root=str(self.output_root),
                policy_path=str(self.policy_path),
                policy_sha256=self.policy_sha256,
                bridge_path=str(self.helper_root / "observer_bridge.ps1"),
                bridge_sha256=self.bridge_sha256,
                core_path=str(self.helper_root / "yield_observer.ps1"),
                core_sha256=self.core_sha256,
            )
        )

    @property
    def sha256(self) -> str:
        return sha256(self.manifest_bytes).hexdigest()


def require_dec4_observer_readiness(
    plan: Dec4ObserverPlan,
    reply: dict,
    *,
    expected_plan_sha256: str,
    request_id: str,
    now_utc: datetime,
) -> None:
    """Validate one fresh authenticated transport reply, not a saved receipt.

    The caller independently pins the plan and supplies a never-reused request
    ID for its synchronous, read-only probe. A match is pre-suspend only:
    Suspend and Check must repeat exact native readback, not reuse this reply.
    """
    opens, closes, _ = _TIMES[plan.phase]
    if _pin(expected_plan_sha256) != plan.sha256:
        raise ValueError("dec4_observer_plan_pin")
    if (
        type(now_utc) is not datetime
        or now_utc.utcoffset() != timedelta(0)
        or not opens <= now_utc < closes
    ):
        raise ValueError("dec4_observer_readiness_window")
    if type(request_id) is not str or fullmatch(r"[0-9a-f]{32}", request_id) is None:
        raise ValueError("dec4_observer_readiness_request")
    expected = dict(
        schema=READINESS_SCHEMA,
        status="EXACT_ORIGINAL_OBSERVER_READINESS",
        plan_sha256=expected_plan_sha256,
        request_id=request_id,
        task_path=OBSERVER_TASK_PATH,
        xml_sha256=OBSERVER_XML_SHA256,
        api7_sha256=OBSERVER_API7_SHA256,
        enabled=True,
        hidden_inclusive=True,
        instances=0,
        Task_writes=0,
    )
    if (
        type(reply) is not dict
        or reply.keys() != expected.keys()
        or any(
            type(reply[key]) is not type(value) or reply[key] != value
            for key, value in expected.items()
        )
    ):
        raise ValueError("dec4_observer_readiness_unknown")
