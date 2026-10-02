"""Bounded QQQ/NASD unit connectivity cycle through the existing Paper service.

Receipts are canned execution checks, not model or market-data evidence. The
budget core owns submission, private reservations, recovery and both locks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# A direct default preview must not create Python import caches either.
sys.dont_write_bytecode = True

from thericher_v2.contracts import TargetExposureProposal, require_utc  # noqa: E402
from thericher_v2.execution import kis_paper_budget_strategy as budget  # noqa: E402
from thericher_v2.execution.kis_paper_canary import (  # noqa: E402
    KisPaperCanaryClient,
    UrllibKisPaperCanaryTransport,
)
from thericher_v2.execution.kis_readonly import (  # noqa: E402
    load_kis_paper_config,
    load_kis_paper_config_from_environment,
)
from thericher_v2.research.decision_receipt import (  # noqa: E402
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "kis-paper-daily-spy-session"
INVOCATION_LABEL = "thericher.qqq-unit-invocation"
POLL_SECONDS = 15
WORKER_SECONDS = 1200
_WORKER_STATUSES = frozenset(
    {
        "unit_cycle_complete",
        "pending",
        "visit_budget_exhausted",
        "worker_time_budget_exhausted",
        "recovery_required",
        "not_due",
        "no_intent",
        "unit_cycle_not_completed",
    }
)
_REPLAY_STATUSES = frozenset(
    {
        "not_observed",
        "entry_ready",
        "exit_ready",
        "pending",
        "complete",
        "entry_finalized",
    }
)


def _validate_visits(visits: int) -> None:
    if type(visits) is not int or not 1 <= visits <= 24:
        raise ValueError("invalid_visit_bound")


def _canonical_cycle_id(cycle_id: str) -> str:
    if (
        not isinstance(cycle_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", cycle_id) is None
    ):
        raise ValueError("invalid_cycle_identity")
    return "qqq-unit-" + hashlib.sha256(cycle_id.encode("utf-8")).hexdigest()


def _cycle_ref(cycle_id: str) -> str:
    return "sha256:" + budget._digest(cycle_id)


def _summary(cycle_id, status, visits=0, view=None) -> dict[str, object]:
    return {
        "kind": "kis_paper_qqq_unit_cycle",
        "paper_only": True,
        "instrument": "QQQ",
        "exchange": "NASD",
        "decision_use": "execution_connectivity_only",
        "result_basis": "owned_unit_replay",
        "owned_cycle_ref": _cycle_ref(cycle_id),
        "status": status,
        "replay_status": "not_observed" if view is None else view.status,
        "visits_completed": visits,
        "closed_buy_fill_count": 0 if view is None else view.buy_fills,
        "closed_sell_fill_count": 0 if view is None else view.sell_fills,
    }


@dataclass(frozen=True)
class _CycleView:
    status: str
    buy_fills: int
    sell_fills: int
    input_ref: str


def _filled_unit(state) -> bool:
    # _state validates the fill's exact broker/date/instrument/side identity.
    fill = state.cumulative_fill
    return (
        state.broker_order_id is not None
        and (state.submission_started_at or state.submitted_at) is not None
        and fill is not None
        and fill.requested_quantity == 1
        and fill.quantity == 1
    )


def _inspect_cycle(state_root: Path, cycle_id: str, at: datetime) -> _CycleView:
    binding = budget._load_binding(state_root)
    reference = {"use": "execution_connectivity_only", "cycle_ref": _cycle_ref(cycle_id)}
    if binding is None or binding["version"] == 1:
        if binding is not None:
            budget.project_budget(state_root, binding)
            reference["legacy_binding_ref"] = "sha256:" + budget._digest(binding)
        return _CycleView("entry_ready", 0, 0, "sha256:" + budget._digest(reference))
    records = budget._orders(binding, cycle_id)
    projection = budget.project_budget(state_root, binding, qqq_cycle_id=cycle_id, as_of=at)
    states = [budget._state(state_root, row, symbol="QQQ", exchange="NASD") for row in records]
    if any(state.intent.quantity != 1 for state in states) or (
        states
        and (
            states[0].intent.side != "buy"
            or any(state.intent.side != "sell" for state in states[1:])
        )
    ):
        raise ValueError("unit_cycle_state_conflict")
    reference.update(
        basis_ref=binding["basis_ref"],
        owner_ref=binding["qqq"]["owner_ref"],
        orders=[
            {
                "intent_ref": row["intent_ref"],
                "closed": row["closed"],
                "fill_ref": (
                    None if state.cumulative_fill is None else state.cumulative_fill.identity_ref
                ),
            }
            for row, state in zip(records, states, strict=True)
        ],
        selected_quantity=str(projection.quantity),
    )
    input_ref = "sha256:" + budget._digest(reference)
    buy_fills = int(bool(states and records[0]["closed"] and _filled_unit(states[0])))
    sell_fills = sum(
        int(row["closed"] and _filled_unit(state))
        for row, state in zip(records[1:], states[1:], strict=True)
    )
    if sell_fills > 1 or (sell_fills and not buy_fills):
        raise ValueError("unit_cycle_fill_conflict")
    if records and not records[-1]["closed"]:
        status = "pending"
    elif not records and projection.quantity == 0:
        status = "entry_ready"
    elif (
        buy_fills == sell_fills == 1
        and projection.quantity == 0
        and states[-1].intent.side == "sell"
        and _filled_unit(states[-1])
    ):
        status = "complete"
    elif buy_fills == 1 and sell_fills == 0 and projection.quantity == 1:
        status = "exit_ready"
    elif states and not buy_fills and not sell_fills and projection.quantity == 0:
        status = "entry_finalized"
    else:
        raise ValueError("unit_cycle_projection_conflict")
    return _CycleView(status, buy_fills, sell_fills, input_ref)


def _receipt(state_root: Path, cycle_id: str, at: datetime) -> ResearchDecisionReceipt:
    view = _inspect_cycle(state_root, cycle_id, at)
    if view.status == "pending":
        raise ValueError("pending_recovery_must_precede_receipt")
    action = {"entry_ready": "enter", "exit_ready": "exit"}.get(view.status, "abstain")
    proposal_ref = "ref:" + budget._digest([_cycle_ref(cycle_id), view.input_ref, action])
    proposal = TargetExposureProposal(
        proposal_id=proposal_ref,
        symbol="QQQ",
        market="US",
        action=action,
        # This marker does not size an order; the core shares the existing tenth.
        target_exposure=Decimal("0.10") if action == "enter" else Decimal(0),
        confidence=Decimal(0),
        feature_schema_id="qqq-unit-execution-connectivity-v1",
        input_status="ready" if action != "abstain" else "unqualified",
        decided_at=at,
        valid_until=at + timedelta(seconds=60),
        feature_window_end=None,
        reason="execution_connectivity_only_no_dataset_or_trained_model",
    )
    return receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref="ref:" + budget._digest(["qqq-unit-connectivity-v1", cycle_id]),
            model_ref="ref:" + budget._digest("canned_execution_receipt_no_trained_model_v1"),
            input_manifest_ref=view.input_ref,
            proposal_ref=proposal_ref,
        ),
    )


def run_worker(
    *,
    cycle_id: str,
    execute: bool,
    visits: int = 24,
    environment: Mapping[str, str] | None = None,
    state_root: Path = Path("/app/private/canary"),
    runtime_projection_path: Path = Path("/app/runtime/state/kis_paper_canary.json"),
    paper_account_snapshot_path: Path = Path("/app/runtime/state/paper_account_snapshot.json"),
    emergency_state_path: Path = Path("/app/emergency/emergency_state.json"),
    execution_control_path: Path = Path("/app/emergency/paper_execution_control.json"),
    artifact_root: Path = Path("/app/model_artifacts"),
    repository_root: Path = Path("/app"),
    clock=None,
) -> dict[str, object]:
    _validate_visits(visits)
    if not isinstance(cycle_id, str) or re.fullmatch(r"qqq-unit-[0-9a-f]{64}", cycle_id) is None:
        raise ValueError("invalid_worker_cycle_identity")
    if not execute:
        return _summary(cycle_id, "preview")
    completed_visits, view = 0, None
    deadline = time.monotonic() + WORKER_SECONDS
    try:
        source = os.environ if environment is None else environment
        if source.get("THERICHER_MODE", "off").strip().lower() == "kis_live":
            return _summary(cycle_id, "recovery_required")
        config = load_kis_paper_config_from_environment(source)
        client = KisPaperCanaryClient(config=config, transport=UrllibKisPaperCanaryTransport())
        for _ in range(visits):
            if time.monotonic() >= deadline:
                return _summary(cycle_id, "worker_time_budget_exhausted", completed_visits, view)
            outcome = budget.run_kis_paper_budget_strategy(
                receipt_loader=lambda at: _receipt(state_root, cycle_id, at),
                environment=source,
                state_root=state_root,
                runtime_projection_path=runtime_projection_path,
                paper_account_snapshot_path=paper_account_snapshot_path,
                emergency_state_path=emergency_state_path,
                execution_control_path=execution_control_path,
                artifact_root=artifact_root,
                repository_root=repository_root,
                execute=True,
                client=client,
                clock=clock,
                qqq_cycle_id=cycle_id,
            )
            completed_visits += 1
            payload = outcome.safe_payload()
            if (
                payload.get("instrument") != "QQQ"
                or payload.get("exchange") != "NASD"
                or payload.get("owned_cycle_ref") != _cycle_ref(cycle_id)
                or payload.get("status") != outcome.status
                or outcome.status not in {"pending", "order_complete", "no_intent", "not_due"}
            ):
                return _summary(cycle_id, "recovery_required", completed_visits, view)
            if time.monotonic() >= deadline:
                return _summary(cycle_id, "worker_time_budget_exhausted", completed_visits, view)
            inspection_root = state_root.resolve()
            with budget.exclusive_kis_paper_canary_state_lock(
                inspection_root / ".session_execution"
            ):
                with budget.exclusive_kis_paper_canary_state_lock(
                    inspection_root / ".canary_execution"
                ):
                    view = _inspect_cycle(
                        inspection_root,
                        cycle_id,
                        require_utc(clock() if clock else datetime.now(UTC)),
                    )
            if view.status == "complete":
                return _summary(cycle_id, "unit_cycle_complete", completed_visits, view)
            if view.status == "entry_finalized":
                return _summary(cycle_id, "unit_cycle_not_completed", completed_visits, view)
            if outcome.status in {"not_due", "no_intent"}:
                return _summary(cycle_id, outcome.status, completed_visits, view)
            if view.status not in {"pending", "exit_ready"}:
                return _summary(cycle_id, "recovery_required", completed_visits, view)
            if completed_visits == visits:
                return _summary(cycle_id, "visit_budget_exhausted", completed_visits, view)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _summary(cycle_id, "worker_time_budget_exhausted", completed_visits, view)
            time.sleep(min(POLL_SECONDS, remaining))
    except Exception:
        return _summary(cycle_id, "recovery_required", completed_visits, view)
    return _summary(cycle_id, "visit_budget_exhausted", completed_visits, view)


def _exit_code(result) -> int:
    if result["status"] in {"unit_cycle_complete", "preview"}:
        return 0
    if result["status"] in {"pending", "visit_budget_exhausted", "worker_time_budget_exhausted"}:
        return 21
    if result["status"] == "not_due":
        return 22
    if result["status"] in {"no_intent", "unit_cycle_not_completed"}:
        return 23
    return 20


def _worker_result(output, cycle_id, visits):
    if not isinstance(output, str) or len(output) > 4096:
        raise ValueError("worker_output_invalid")
    result = json.loads(output)
    expected = _summary(cycle_id, "preview")
    variable = {
        "status",
        "replay_status",
        "visits_completed",
        "closed_buy_fill_count",
        "closed_sell_fill_count",
    }
    if (
        not isinstance(result, dict)
        or set(result) != set(expected)
        or any(
            type(result[key]) is not type(value) or (key not in variable and result[key] != value)
            for key, value in expected.items()
        )
    ):
        raise ValueError("worker_output_invalid")
    if (
        result["status"] not in _WORKER_STATUSES
        or result["replay_status"] not in _REPLAY_STATUSES
        or not 0 <= result["visits_completed"] <= visits
        or result["closed_buy_fill_count"] not in {0, 1}
        or result["closed_sell_fill_count"] not in {0, 1}
        or (
            result["status"] == "unit_cycle_complete"
            and (
                result["replay_status"] != "complete"
                or result["visits_completed"] == 0
                or result["closed_buy_fill_count"] != 1
                or result["closed_sell_fill_count"] != 1
            )
        )
    ):
        raise ValueError("worker_output_invalid")
    return result


def _stop_owned_container(name, invocation, common) -> str:
    try:
        inspected = subprocess.run(
            [
                "docker",
                "container",
                "inspect",
                "--format",
                '{"id":{{json .Id}},"invocation":{{json (index .Config.Labels '
                '"' + INVOCATION_LABEL + '")}}}',
                name,
            ],
            timeout=30,
            stdout=subprocess.PIPE,
            text=True,
            **common,
        )
        identity = json.loads(inspected.stdout)
        if (
            inspected.returncode != 0
            or not isinstance(identity, dict)
            or set(identity) != {"id", "invocation"}
            or identity["invocation"] != invocation
            or not isinstance(identity["id"], str)
            or re.fullmatch(r"[0-9a-f]{64}", identity["id"]) is None
        ):
            return "ownership_unconfirmed"
        stopped = subprocess.run(
            ["docker", "stop", "--time", "30", identity["id"]],
            timeout=45,
            stdout=subprocess.DEVNULL,
            **common,
        )
        return "confirmed" if stopped.returncode == 0 else "unconfirmed"
    except Exception:
        return "ownership_unconfirmed"


def run(*, project_root: Path, execute: bool, cycle_id: str, visits: int = 24):
    _validate_visits(visits)
    cycle_id = _canonical_cycle_id(cycle_id)
    if not execute:
        return _summary(cycle_id, "preview")
    try:
        if os.environ.get("THERICHER_MODE", "off").strip().lower() == "kis_live":
            return _summary(cycle_id, "dispatch_unavailable")
        # Reject inherited route names before accessing any of their values.
        environment = {
            key: os.environ[key] for key in os.environ if not key.upper().startswith("KIS_")
        }
        root = project_root.resolve()
        artifact_root = Path(
            environment.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT")
            or "D:/thericher-v2/model-artifacts"
        ).resolve()
        if artifact_root.is_relative_to(root):
            return _summary(cycle_id, "dispatch_unavailable")
        environment["THERICHER_HOST_MODEL_ARTIFACT_ROOT"] = artifact_root.as_posix()
        common = dict(env=environment, cwd=root, stderr=subprocess.DEVNULL)
        name = "thericher-qqq-unit-" + _cycle_ref(cycle_id).removeprefix("sha256:")
        present = subprocess.run(
            ["docker", "container", "inspect", name],
            timeout=30,
            stdout=subprocess.DEVNULL,
            **common,
        )
        if present.returncode == 0:
            return _summary(cycle_id, "owned_container_present")
        config = load_kis_paper_config(root / ".env")
        environment.update(
            KIS_PAPER_APP_KEY=config.app_key,
            KIS_PAPER_APP_SECRET=config.app_secret,
            KIS_PAPER_ACCOUNT_NO=config.account_number,
            KIS_PAPER_ACCOUNT_PRODUCT_CODE=config.account_product_code,
        )
        invocation = uuid.uuid4().hex
        command = [
            "docker",
            "compose",
            "--project-directory",
            str(root),
            "--env-file",
            str(root / ".env.example"),
            "--profile",
            PROFILE,
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "-T",
            "--name",
            name,
            "--label",
            INVOCATION_LABEL + "=" + invocation,
            PROFILE,
            "timeout",
            "--signal=TERM",
            "--kill-after=30s",
            "1260s",
            "python",
            "-B",
            "scripts/run_kis_paper_qqq_unit_cycle.py",
            "--worker",
            "--execute",
            "--cycle-id",
            cycle_id,
            "--visits",
            str(visits),
        ]
        try:
            completed = subprocess.run(
                command,
                timeout=1350,
                stdout=subprocess.PIPE,
                text=True,
                **common,
            )
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            result = _summary(
                cycle_id,
                "worker_timeout"
                if isinstance(error, subprocess.TimeoutExpired)
                else "worker_interrupted",
            )
            result["container_stop_status"] = _stop_owned_container(name, invocation, common)
            return result
        try:
            result = _worker_result(completed.stdout, cycle_id, visits)
            if completed.returncode == _exit_code(result):
                return result
        except (ValueError, TypeError):
            pass
        return _summary(cycle_id, "worker_failed")
    except Exception:
        return _summary(cycle_id, "dispatch_unavailable")


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_arguments")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _SafeArgumentParser(description=__doc__)
        parser.add_argument("--project-root", type=Path, default=ROOT)
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--worker", action="store_true")
        parser.add_argument("--cycle-id", required=True)
        parser.add_argument("--visits", type=int, default=24)
        args = parser.parse_args(argv)
        result = (
            run_worker(cycle_id=args.cycle_id, execute=args.execute, visits=args.visits)
            if args.worker
            else run(
                project_root=args.project_root,
                cycle_id=args.cycle_id,
                execute=args.execute,
                visits=args.visits,
            )
        )
    except Exception:
        result = {
            "kind": "kis_paper_qqq_unit_cycle",
            "instrument": "QQQ",
            "exchange": "NASD",
            "paper_only": True,
            "status": "arguments_unavailable",
        }
    print(json.dumps(result, sort_keys=True), flush=True)
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
