"""Persist one minimal, sanitized local-paper observation from a verified input."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, EmergencyState
from thericher_v2.data.kis_intraday_prospective_observation import (
    KisIntradayProspectiveObservationInput,
)
from thericher_v2.data.resample import SessionWindow
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.state import Event, EventStore

from .kis_intraday_prospective_observation_consumer import (
    KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES,
    KisIntradayProspectiveCandidateReplayPlan,
    KisIntradayProspectiveObservationConsumer,
    build_kis_intraday_prospective_observation_consumer,
)
from .validation import (
    VALIDATION_SOURCE,
    InMemoryCampaignEventStore,
    ValidationConfig,
    run_local_paper_validation,
)

_RUN_DIRECTORY_NAME = "kis-intraday-prospective-observation"
_EVENTS_DIRECTORY_NAME = "events"
_FROZEN_MODEL_RECEIPT_NAME = "frozen-model-receipt.json"
_SUMMARY_NAME = "summary.json"


@dataclass(frozen=True)
class KisIntradayProspectiveObservationRun:
    """A minimal handle to one immutable model receipt and aggregate observation."""

    consumer: KisIntradayProspectiveObservationConsumer
    frozen_model_receipt_path: Path
    summary_path: Path
    reused: bool
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class _ClearEmergencyStore:
    """The bounded replay has no broker route and starts locally clear."""

    updated_at: datetime

    def read(self) -> EmergencyState:
        return EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason="kis_intraday_prospective_observation_local_paper_only",
            updated_at=self.updated_at,
        )


def run_kis_intraday_prospective_observation(
    observation_input: KisIntradayProspectiveObservationInput,
    *,
    artifact_root: Path,
    repo_root: Path | None = None,
) -> KisIntradayProspectiveObservationRun:
    """Run fixed local-paper candidates and retain only sanitized evidence.

    Raw validation events exist only in ``InMemoryCampaignEventStore``. Each
    candidate writes one replayable JSONL stream containing only the local-paper
    action or fill shape; the aggregate summary binds those streams to the
    verified input and frozen model.
    """

    if not isinstance(observation_input, KisIntradayProspectiveObservationInput):
        raise TypeError("prospective observation requires a verified Data input")
    repository = (repo_root or Path.cwd()).resolve()
    root = Path(artifact_root).resolve()
    _reject_repo_artifact_root(root, repo_root=repository)
    consumer = build_kis_intraday_prospective_observation_consumer(
        observation_input=observation_input,
    )
    frozen_payload = _frozen_model_receipt_payload(consumer)
    run_directory = _run_directory(root, consumer.frozen_model_receipt.receipt_hash)
    if run_directory.exists() or run_directory.is_symlink():
        return _resume_run(
            consumer=consumer,
            observation_input=observation_input,
            run_directory=run_directory,
            frozen_payload=frozen_payload,
        )

    run_directory.mkdir(parents=True, exist_ok=False)
    frozen_path = run_directory / _FROZEN_MODEL_RECEIPT_NAME
    _write_json_new(frozen_path, frozen_payload)
    return _materialize_summary(
        consumer=consumer,
        observation_input=observation_input,
        run_directory=run_directory,
        frozen_path=frozen_path,
        summary_exists=False,
    )


def _resume_run(
    *,
    consumer: KisIntradayProspectiveObservationConsumer,
    observation_input: KisIntradayProspectiveObservationInput,
    run_directory: Path,
    frozen_payload: Mapping[str, object],
) -> KisIntradayProspectiveObservationRun:
    if run_directory.is_symlink() or not run_directory.is_dir():
        raise ValueError("prospective observation artifact directory is invalid")
    _require_run_directory_shape(run_directory)
    frozen_path = run_directory / _FROZEN_MODEL_RECEIPT_NAME
    if _read_json(frozen_path) != frozen_payload:
        raise ValueError("prospective observation frozen-model receipt does not match")
    summary_path = run_directory / _SUMMARY_NAME
    return _materialize_summary(
        consumer=consumer,
        observation_input=observation_input,
        run_directory=run_directory,
        frozen_path=frozen_path,
        summary_exists=summary_path.exists() or summary_path.is_symlink(),
    )


def _materialize_summary(
    *,
    consumer: KisIntradayProspectiveObservationConsumer,
    observation_input: KisIntradayProspectiveObservationInput,
    run_directory: Path,
    frozen_path: Path,
    summary_exists: bool,
) -> KisIntradayProspectiveObservationRun:
    candidate_payloads, any_replayed = _candidate_payloads(
        consumer=consumer,
        run_directory=run_directory,
    )
    summary_payload = _summary_payload(
        observation_input=observation_input,
        consumer=consumer,
        run_directory=run_directory,
        candidate_payloads=candidate_payloads,
    )
    summary_path = run_directory / _SUMMARY_NAME
    if summary_exists:
        if summary_path.is_symlink() or not summary_path.is_file():
            raise ValueError("prospective observation summary is invalid")
        existing = _read_json(summary_path)
        if not any_replayed:
            if existing != summary_payload:
                raise ValueError("prospective observation summary does not match")
            return KisIntradayProspectiveObservationRun(
                consumer=consumer,
                frozen_model_receipt_path=frozen_path,
                summary_path=summary_path,
                reused=True,
            )
        _write_json_replace(summary_path, summary_payload)
    else:
        _write_json_new(summary_path, summary_payload)
    return KisIntradayProspectiveObservationRun(
        consumer=consumer,
        frozen_model_receipt_path=frozen_path,
        summary_path=summary_path,
        reused=False,
    )


def _candidate_payloads(
    *,
    consumer: KisIntradayProspectiveObservationConsumer,
    run_directory: Path,
) -> tuple[tuple[dict[str, object], ...], bool]:
    events_directory = _events_directory(run_directory)
    _prepare_events_directory(events_directory)
    payloads: list[dict[str, object]] = []
    any_replayed = False
    for plan in consumer.candidate_replay_plans:
        event_path = events_directory / f"{plan.candidate_id}.jsonl"
        if event_path.exists() or event_path.is_symlink():
            events = _read_sanitized_events(event_path, plan=plan)
        else:
            events = _run_ephemeral_candidate_replay(consumer=consumer, plan=plan)
            _write_events_new(event_path, events)
            any_replayed = True
        payloads.append(_candidate_payload(plan=plan, events=events, event_path=event_path))
    return tuple(payloads), any_replayed


def _run_ephemeral_candidate_replay(
    *,
    consumer: KisIntradayProspectiveObservationConsumer,
    plan: KisIntradayProspectiveCandidateReplayPlan,
) -> tuple[Event, ...]:
    store = InMemoryCampaignEventStore()
    run_local_paper_validation(
        consumer.prospective_cataloged_bars,
        event_store=store,
        emergency_store=_ClearEmergencyStore(updated_at=plan.allowed_session_windows[0].open_ts),
        model=plan.model,
        config=ValidationConfig(
            run_id=plan.replay_id,
            fee_bps=consumer.campaign.costs.fee_bps,
            slippage_bps=consumer.campaign.costs.slippage_bps,
        ),
        campaign=consumer.campaign,
        phase=plan.campaign_phase,
        fold_id="prospective-observation",
        eligible_signal_starts=plan.eligible_signal_starts,
        allowed_session_windows=plan.allowed_session_windows,
    )
    return _sanitize_events(store.iter_events(), plan=plan)


def _sanitize_events(
    events: tuple[Event, ...],
    *,
    plan: KisIntradayProspectiveCandidateReplayPlan,
) -> tuple[Event, ...]:
    expected_times = frozenset(plan.model.samples_by_decision_end)
    decision_times: list[datetime] = []
    sanitized: list[Event] = []
    for event in events:
        if event.event_type == "ensemble_decision":
            action = event.payload.get("action")
            if (
                event.payload.get("source") != VALIDATION_SOURCE
                or event.payload.get("run_id") != plan.replay_id
                or action not in {"buy", "hold", "sell"}
                or event.created_at not in expected_times
            ):
                raise RuntimeError("prospective observation decision evidence is invalid")
            decision_times.append(event.created_at)
            sanitized.append(
                Event(
                    event_type="ensemble_decision",
                    created_at=event.created_at,
                    payload={
                        "source": LOCAL_PAPER_SOURCE,
                        "candidate_id": plan.candidate_id,
                        "action": action,
                    },
                )
            )
        elif event.event_type == "fill":
            payload = event.payload
            if (
                payload.get("source") != LOCAL_PAPER_SOURCE
                or payload.get("side") not in {"buy", "sell"}
                or not isinstance(payload.get("market"), str)
                or not isinstance(payload.get("symbol"), str)
                or not isinstance(payload.get("quantity"), str)
            ):
                raise RuntimeError("prospective observation fill evidence is invalid")
            sanitized.append(
                Event(
                    event_type="fill",
                    created_at=event.created_at,
                    payload={
                        "source": LOCAL_PAPER_SOURCE,
                        "candidate_id": plan.candidate_id,
                        "market": payload["market"],
                        "symbol": payload["symbol"],
                        "side": payload["side"],
                        "quantity": payload["quantity"],
                    },
                )
            )
    if frozenset(decision_times) != expected_times or len(decision_times) != len(expected_times):
        raise RuntimeError("prospective observation decisions do not match the frozen plan")
    return tuple(sanitized)


def _candidate_payload(
    *,
    plan: KisIntradayProspectiveCandidateReplayPlan,
    events: tuple[Event, ...],
    event_path: Path,
) -> dict[str, object]:
    decision_count = sum(event.event_type == "ensemble_decision" for event in events)
    fill_count = sum(event.event_type == "fill" for event in events)
    return {
        "candidate_id": plan.candidate_id,
        "replay_id": plan.replay_id,
        "fill_source": LOCAL_PAPER_SOURCE,
        "plan_sha256": _sha256_payload(plan.to_payload()),
        "event_jsonl_sha256": _sha256_file(event_path),
        "event_count": len(events),
        "decision_count": decision_count,
        "fill_count": fill_count,
    }


def _summary_payload(
    *,
    observation_input: KisIntradayProspectiveObservationInput,
    consumer: KisIntradayProspectiveObservationConsumer,
    run_directory: Path,
    candidate_payloads: tuple[dict[str, object], ...],
) -> dict[str, object]:
    if [item["candidate_id"] for item in candidate_payloads] != list(
        KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES
    ):
        raise ValueError("prospective observation candidates are invalid")
    sessions = _session_payloads(
        consumer=consumer,
        run_directory=run_directory,
        candidate_payloads=candidate_payloads,
    )
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_intraday_prospective_observation_summary",
        "status": "complete",
        "mode": "offline_local_paper",
        "observation_input": observation_input.safe_payload(),
        "frozen_model_receipt_hash": consumer.frozen_model_receipt.receipt_hash,
        "candidate_replays": list(candidate_payloads),
        "session_observations": sessions,
        "selection_allowed": False,
        "profitability_conclusion": False,
        "broker_order_submitted": False,
    }
    return {**base, "receipt_sha256": _sha256_payload(base)}


def _session_payloads(
    *,
    consumer: KisIntradayProspectiveObservationConsumer,
    run_directory: Path,
    candidate_payloads: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    events_directory = _events_directory(run_directory)
    payload_by_id = {str(item["candidate_id"]): item for item in candidate_payloads}
    plans = {plan.candidate_id: plan for plan in consumer.candidate_replay_plans}
    sessions: list[dict[str, object]] = []
    for session_date, window in zip(
        consumer.summary.prospective_session_dates,
        _session_windows(consumer),
        strict=True,
    ):
        candidate_sessions: list[dict[str, object]] = []
        for candidate_id in KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES:
            plan = plans[candidate_id]
            events = _read_sanitized_events(
                events_directory / f"{candidate_id}.jsonl",
                plan=plan,
            )
            session_events = tuple(
                event
                for event in events
                if window.open_ts <= event.created_at < window.close_ts
            )
            if not session_events:
                raise ValueError("prospective observation session replay is incomplete")
            sequences = tuple(event.seq for event in session_events)
            if sequences != tuple(range(sequences[0], sequences[-1] + 1)):
                raise ValueError("prospective observation session replay is not contiguous")
            candidate = payload_by_id[candidate_id]
            candidate_sessions.append(
                {
                    "candidate_id": candidate_id,
                    "replay_id": plan.replay_id,
                    "fill_source": LOCAL_PAPER_SOURCE,
                    "event_jsonl_sha256": candidate["event_jsonl_sha256"],
                    "session_event_sha256": _sha256_payload(
                        {"events": [event.to_record() for event in session_events]}
                    ),
                    "first_event_seq": sequences[0],
                    "last_event_seq": sequences[-1],
                    "event_count": len(session_events),
                    "decision_count": sum(
                        event.event_type == "ensemble_decision" for event in session_events
                    ),
                    "fill_count": sum(event.event_type == "fill" for event in session_events),
                }
            )
        sessions.append(
            {
                "session_date": session_date.isoformat(),
                "fill_source": LOCAL_PAPER_SOURCE,
                "candidate_replays": candidate_sessions,
            }
        )
    return sessions


def _read_sanitized_events(
    event_path: Path,
    *,
    plan: KisIntradayProspectiveCandidateReplayPlan,
) -> tuple[Event, ...]:
    if event_path.is_symlink() or not event_path.is_file():
        raise ValueError("prospective observation event evidence is invalid")
    try:
        events = tuple(EventStore(event_path.with_suffix(".sqlite"), event_path).iter_events())
    except (OSError, ValueError) as error:
        raise ValueError("prospective observation event evidence is invalid") from error
    expected_times = frozenset(plan.model.samples_by_decision_end)
    decision_times: list[datetime] = []
    for expected_sequence, event in enumerate(events, start=1):
        if event.seq != expected_sequence:
            raise ValueError("prospective observation event evidence is invalid")
        if event.event_type == "ensemble_decision":
            if (
                event.created_at not in expected_times
                or set(event.payload) != {"source", "candidate_id", "action"}
                or event.payload.get("source") != LOCAL_PAPER_SOURCE
                or event.payload.get("candidate_id") != plan.candidate_id
                or event.payload.get("action") not in {"buy", "hold", "sell"}
            ):
                raise ValueError("prospective observation event evidence is invalid")
            decision_times.append(event.created_at)
        elif event.event_type == "fill":
            if (
                set(event.payload)
                != {"source", "candidate_id", "market", "symbol", "side", "quantity"}
                or event.payload.get("source") != LOCAL_PAPER_SOURCE
                or event.payload.get("candidate_id") != plan.candidate_id
                or event.payload.get("side") not in {"buy", "sell"}
                or not isinstance(event.payload.get("market"), str)
                or not isinstance(event.payload.get("symbol"), str)
                or not isinstance(event.payload.get("quantity"), str)
            ):
                raise ValueError("prospective observation event evidence is invalid")
        else:
            raise ValueError("prospective observation event evidence is invalid")
    if not events or frozenset(decision_times) != expected_times:
        raise ValueError("prospective observation event evidence is invalid")
    return events


def _prepare_events_directory(events_directory: Path) -> None:
    if events_directory.exists() or events_directory.is_symlink():
        if events_directory.is_symlink() or not events_directory.is_dir():
            raise ValueError("prospective observation event directory is invalid")
        allowed = {
            f"{candidate_id}.jsonl"
            for candidate_id in KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES
        }
        entries = tuple(events_directory.iterdir())
        if any(
            entry.is_symlink()
            or not entry.is_file()
            or (
                entry.name not in allowed
                and not (entry.name.startswith(".") and entry.name.endswith(".tmp"))
            )
            for entry in entries
        ):
            raise ValueError("prospective observation event directory requires reconciliation")
        for entry in entries:
            if entry.name.startswith("."):
                entry.unlink()
        return
    events_directory.mkdir(parents=True)


def _write_events_new(path: Path, events: tuple[Event, ...]) -> None:
    temporary = path.parent / f".{path.stem}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            for sequence, event in enumerate(events, start=1):
                handle.write(
                    json.dumps(
                        event.with_seq(sequence).to_record(),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _session_windows(
    consumer: KisIntradayProspectiveObservationConsumer,
) -> tuple[SessionWindow, ...]:
    plans = consumer.candidate_replay_plans
    windows = plans[0].allowed_session_windows
    if any(plan.allowed_session_windows != windows for plan in plans[1:]):
        raise ValueError("prospective observation session windows are invalid")
    return windows


def _frozen_model_receipt_payload(
    consumer: KisIntradayProspectiveObservationConsumer,
) -> dict[str, object]:
    model_payload = consumer.frozen_linear_model.to_payload()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_intraday_prospective_observation_frozen_model_receipt",
        "status": "frozen",
        "frozen_model_receipt": consumer.frozen_model_receipt.to_payload(),
        "frozen_model_receipt_hash": consumer.frozen_model_receipt.receipt_hash,
        "regularized_linear": model_payload,
        "regularized_linear_sha256": _sha256_payload(model_payload),
        "artifact_policy": {
            "raw_market_data_written": False,
            "model_checkpoint_written": False,
            "repository_storage_allowed": False,
            "prices_or_order_identifiers_written": False,
        },
    }


def _run_directory(artifact_root: Path, frozen_model_receipt_hash: str) -> Path:
    _require_sha256(frozen_model_receipt_hash, "frozen_model_receipt_hash")
    slot = uuid.uuid5(uuid.NAMESPACE_URL, frozen_model_receipt_hash).hex
    return artifact_root / _RUN_DIRECTORY_NAME / slot


def _events_directory(run_directory: Path) -> Path:
    return run_directory / _EVENTS_DIRECTORY_NAME


def _require_run_directory_shape(run_directory: Path) -> None:
    allowed = {_FROZEN_MODEL_RECEIPT_NAME, _SUMMARY_NAME, _EVENTS_DIRECTORY_NAME}
    entries = tuple(run_directory.iterdir())
    if any(entry.is_symlink() or entry.name not in allowed for entry in entries):
        raise ValueError("prospective observation artifact directory is invalid")


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("prospective observation artifact already exists")
    _write_json(path, payload, replace=False)


def _write_json_replace(path: Path, payload: Mapping[str, object]) -> None:
    _write_json(path, payload, replace=True)


def _write_json(path: Path, payload: Mapping[str, object], *, replace: bool) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.parent / f".{uuid.uuid4().hex[:8]}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and (path.exists() or path.is_symlink()):
            raise ValueError("prospective observation artifact already exists")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> Mapping[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("prospective observation artifact is invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prospective observation artifact is invalid") from error
    if not isinstance(value, Mapping):
        raise ValueError("prospective observation artifact is invalid")
    return value


def _sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("prospective observation event evidence is invalid")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError("prospective observation event evidence is invalid") from error
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _reject_repo_artifact_root(artifact_root: Path, *, repo_root: Path) -> None:
    docker_repo_root = Path("/app").resolve()
    docker_artifact_root = docker_repo_root / "model_artifacts"
    if os.name != "nt" and repo_root == docker_repo_root and (
        artifact_root == docker_artifact_root or docker_artifact_root in artifact_root.parents
    ):
        return
    if artifact_root == repo_root or artifact_root.is_relative_to(repo_root):
        raise ValueError("prospective observation artifacts must stay outside the Git workspace")
