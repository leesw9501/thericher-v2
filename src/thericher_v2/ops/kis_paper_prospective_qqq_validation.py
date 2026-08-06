"""Offline reattachment for one persisted prospective QQQ Paper session."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE,
    KisPaperIntradayRuntimeWindow,
    KisPaperIntradayRuntimeWindowLocalAvailability,
    attest_kis_paper_intraday_runtime_window_local_availability,
    select_kis_paper_intraday_runtime_window,
)
from thericher_v2.execution.kis_paper_prospective_qqq_session import (
    KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY,
    KIS_PAPER_PROSPECTIVE_QQQ_SESSION_KIND,
)
from thericher_v2.research.decision_receipt import (
    ResearchDecisionReceipt,
    receipt_projection_for_target_action,
)

KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_KIND = "kis_paper_prospective_qqq_validation"
KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_ARTIFACT_DIRECTORY = (
    "validation/kis-paper-prospective-qqq-cycle"
)
KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID = "runtime-freshness-v4"
KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_STATUS = "validated"
KIS_PAPER_PROSPECTIVE_QQQ_HEAD_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday-head"
)
DEFAULT_KIS_PAPER_PROSPECTIVE_QQQ_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)
_DEFAULT_REPOSITORY_ROOT = Path.cwd()
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SHA256_REF = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_TERMINAL_CANARY_PHASES = frozenset({"cancelled"})


@dataclass(frozen=True)
class KisPaperProspectiveQqqValidation:
    """One source-safe, offline validation result."""

    session_id: str
    session_evidence_sha256: str
    session_status: str
    validation_scope: str
    runtime_window: dict[str, object] | None
    local_paper_replay: dict[str, object] | None
    local_input_availability: dict[str, object] | None
    canary_present: bool
    evidence_path: Path
    validation_contract: str
    validation_identity: str

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_KIND,
            "status": KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_STATUS,
            "session_id": self.session_id,
            "session_evidence_sha256": self.session_evidence_sha256,
            "session_status": self.session_status,
            "validation_scope": self.validation_scope,
            "runtime_window": self.runtime_window,
            "local_paper_replay": self.local_paper_replay,
            "local_input_availability": self.local_input_availability,
            "canary_present": self.canary_present,
            "validation_contract": self.validation_contract,
            "validation_identity": self.validation_identity,
            "claim": (
                "offline cache-and-evidence validation; not a model promotion, "
                "profitability claim, or new broker action"
            ),
        }


def validate_kis_paper_prospective_qqq_session(
    *,
    session_id: str,
    cache_root: Path = KIS_PAPER_PROSPECTIVE_QQQ_HEAD_CACHE_ROOT,
    artifact_root: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_QQQ_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
) -> KisPaperProspectiveQqqValidation:
    """Recompute the exact cached input for one already-recorded Paper session.

    This function deliberately has no credential, network, broker, or
    local-paper mutation path. It verifies only the durable source-safe record
    and cache lineage that the scheduler already produced.
    """

    _require_session_id(session_id)
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    session_path = root / KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY / (
        f"{session_id}.json"
    )
    session_bytes = session_path.read_bytes()
    _reject_unsafe_surface(session_bytes)
    payload = _json_object(session_bytes, "prospective QQQ session evidence")
    (
        observed_at,
        status,
        reason_code,
        loop,
        local_input_availability,
        pre_account_freshness,
        pre_submit_freshness,
    ) = _validate_session_envelope(
        payload,
        session_id=session_id,
    )

    runtime_window: dict[str, object] | None = None
    replay: dict[str, object] | None = None
    validated_local_input_availability: dict[str, object] | None = None
    scope = "target_local_recovery"
    if loop is not None:
        runtime_window, replay, validated_local_input_availability = _recompute_loop(
            loop,
            observed_at=observed_at,
            cache_root=cache_root,
            repository_root=repository_root,
            status=status,
            reason_code=reason_code,
            local_input_availability=local_input_availability,
            pre_account_freshness=pre_account_freshness,
            pre_submit_freshness=pre_submit_freshness,
        )
        scope = "runtime_recomputed"

    identity_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_KIND,
        "status": KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_STATUS,
        "validation_contract": KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID,
        "session_id": session_id,
        "session_evidence_sha256": _sha256_bytes(session_bytes),
        "session_status": status,
        "validation_scope": scope,
        "runtime_window": runtime_window,
        "local_paper_replay": replay,
        "local_input_availability": validated_local_input_availability,
        "canary_present": payload["canary"] is not None,
    }
    result = KisPaperProspectiveQqqValidation(
        session_id=session_id,
        session_evidence_sha256=identity_payload["session_evidence_sha256"],
        session_status=status,
        validation_scope=scope,
        runtime_window=runtime_window,
        local_paper_replay=replay,
        local_input_availability=validated_local_input_availability,
        canary_present=payload["canary"] is not None,
        evidence_path=_validation_evidence_path(root=root, session_id=session_id),
        validation_contract=KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID,
        validation_identity=_sha256_json(identity_payload),
    )
    _write_json_atomically(result.evidence_path, result.safe_payload())
    return result


def latest_kis_paper_prospective_qqq_session_id(*, artifact_root: Path) -> str:
    """Find the latest source-safe execution-session record by timestamp only."""

    directory = Path(artifact_root).resolve() / KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY
    candidates = [
        path
        for path in directory.glob("*.json")
        if path.is_file() and _SAFE_SESSION_ID.fullmatch(path.stem) is not None
    ]
    if not candidates:
        raise ValueError("no prospective QQQ session evidence is available")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name)).stem


def _validate_session_envelope(
    payload: Mapping[str, object], *, session_id: str
) -> tuple[
    datetime,
    str,
    str,
    Mapping[str, object] | None,
    Mapping[str, object] | None,
    Mapping[str, object] | None,
    Mapping[str, object] | None,
]:
    if (
        payload.get("kind") != KIS_PAPER_PROSPECTIVE_QQQ_SESSION_KIND
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("session_id") != session_id
        or payload.get("paper_only") is not True
    ):
        raise ValueError("prospective QQQ session envelope is invalid")
    status = payload.get("status")
    if status not in {"no_intent", "canary_completed"}:
        raise ValueError("prospective validator requires an execution-session outcome")
    reason_code = payload.get("reason_code")
    if not isinstance(reason_code, str):
        raise ValueError("prospective QQQ session reason is invalid")
    observed_at = _parse_utc(payload.get("observed_at"), "prospective QQQ observed_at")
    loop = _object_or_none(payload.get("loop"), "prospective QQQ loop")
    canary = _object_or_none(payload.get("canary"), "prospective QQQ canary")
    prepared = _object_or_none(payload.get("prepared"), "prospective QQQ prepared decision")
    position = _object_or_none(payload.get("position_resolution"), "prospective QQQ position")
    pre_account_freshness = _object_or_none(
        payload.get("pre_account_freshness"),
        "prospective QQQ pre-account freshness",
    )
    pre_submit_freshness = _object_or_none(
        payload.get("pre_submit_freshness"),
        "prospective QQQ pre-submit freshness",
    )
    local_input_availability = _object_or_none(
        payload.get("local_input_availability"),
        "prospective QQQ local input availability",
    )
    if (pre_account_freshness is not None or pre_submit_freshness is not None) and loop is None:
        raise ValueError("execution freshness requires a prospective QQQ loop")
    if local_input_availability is not None and loop is None:
        raise ValueError("local input availability requires a prospective QQQ loop")
    if prepared is not None and prepared.get("route") != "kis_paper":
        raise ValueError("prospective QQQ prepared route is invalid")
    if position is not None and position.get("paper_only") is not True:
        raise ValueError("prospective QQQ position route is invalid")
    if status == "no_intent":
        if canary is not None:
            raise ValueError("no-intent prospective QQQ session cannot carry a canary")
        if loop is None and (prepared is not None or position is not None):
            raise ValueError("catalog-recovery session evidence is inconsistent")
        if reason_code == "runtime_window_expired_before_account" and (
            pre_account_freshness is None or prepared is not None or position is not None
        ):
            raise ValueError("pre-account expiry session evidence is inconsistent")
        if reason_code == "runtime_window_expired_during_preparation" and (
            pre_submit_freshness is None or prepared is None or position is None
        ):
            raise ValueError("pre-submit expiry session evidence is inconsistent")
        if reason_code == "runtime_window_local_availability_unavailable" and (
            loop is None
            or local_input_availability is not None
            or prepared is not None
            or position is not None
        ):
            raise ValueError("local input availability recovery session evidence is inconsistent")
        if reason_code == "runtime_window_not_locally_available" and (
            loop is None
            or local_input_availability is None
            or prepared is not None
            or position is not None
        ):
            raise ValueError("local input availability no-intent session evidence is inconsistent")
    else:
        if loop is None or canary is None or prepared is None or position is None:
            raise ValueError("completed prospective QQQ canary evidence is incomplete")
        if canary.get("paper_only") is not True:
            raise ValueError("prospective QQQ prepared route is invalid")
        if canary.get("phase") not in _TERMINAL_CANARY_PHASES:
            raise ValueError("prospective QQQ canary lifecycle is incomplete")
        if canary.get("reconciliation_status") != "clean":
            raise ValueError("prospective QQQ canary reconciliation is incomplete")
        baseline = _object(loop.get("baseline"), "prospective QQQ baseline")
        if baseline.get("action") not in {"enter", "exit"}:
            raise ValueError("prospective QQQ canary has no eligible baseline action")
    return (
        observed_at,
        status,
        reason_code,
        loop,
        local_input_availability,
        pre_account_freshness,
        pre_submit_freshness,
    )


def _recompute_loop(
    loop: Mapping[str, object],
    *,
    observed_at: datetime,
    cache_root: Path,
    repository_root: Path,
    status: str,
    reason_code: str,
    local_input_availability: Mapping[str, object] | None,
    pre_account_freshness: Mapping[str, object] | None,
    pre_submit_freshness: Mapping[str, object] | None,
) -> tuple[dict[str, object], dict[str, object] | None, dict[str, object] | None]:
    if (
        loop.get("kind") != "kis_paper_prospective_loop"
        or loop.get("mode") != "offline_local_paper"
    ):
        raise ValueError("prospective QQQ loop route is invalid")
    baseline = _object(loop.get("baseline"), "prospective QQQ baseline")
    receipt = _validated_decision_receipt(
        _object(loop.get("receipt"), "prospective QQQ receipt")
    )
    stored_window = _object(loop.get("window"), "prospective QQQ runtime window")
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repository_root,
        symbol="QQQ",
        exchange="NAS",
    )
    recomputed = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=observed_at,
        max_age=KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE,
    )
    expected_window = recomputed.safe_payload()
    legacy_expected_window = dict(expected_window)
    legacy_expected_window.pop("freshness")
    if (
        dict(stored_window) != expected_window
        and dict(stored_window) != legacy_expected_window
    ):
        raise ValueError("stored prospective QQQ runtime window does not match verified cache")
    pre_account_current = _validate_recorded_freshness(
        pre_account_freshness,
        field_name="pre-account",
        recomputed=recomputed,
        session_observed_at=observed_at,
    )
    pre_submit_current = _validate_recorded_freshness(
        pre_submit_freshness,
        field_name="pre-submit",
        recomputed=recomputed,
        session_observed_at=observed_at,
    )
    if reason_code == "runtime_window_expired_before_account":
        if pre_account_current is not False or pre_submit_current is not None:
            raise ValueError("pre-account expiry freshness is inconsistent")
    elif pre_account_current is not None:
        raise ValueError("pre-account freshness has an inconsistent session reason")
    if reason_code == "runtime_window_expired_during_preparation":
        if pre_submit_current is not False:
            raise ValueError("pre-submit expiry freshness is inconsistent")
    elif pre_submit_current is not None and not pre_submit_current:
        raise ValueError("pre-submit freshness is stale for this session outcome")
    if status == "canary_completed" and pre_submit_current is False:
        raise ValueError("completed canary cannot retain stale pre-submit freshness")
    observed_marker = observed_at.isoformat().replace("+00:00", "Z")
    baseline_action = baseline.get("action")
    if not isinstance(baseline_action, str):
        raise ValueError("prospective QQQ baseline and receipt lineage is inconsistent")
    try:
        expected_decision_class, expected_reason_class = receipt_projection_for_target_action(
            baseline_action,
            input_status=recomputed.status,
        )
    except ValueError as error:
        raise ValueError("prospective QQQ baseline and receipt lineage is inconsistent") from error
    if (
        baseline.get("input_status") != recomputed.status
        or receipt.input_status != recomputed.status
        or receipt.input_manifest_ref != recomputed.input_manifest_ref
        or receipt.decision_class != expected_decision_class
        or receipt.reason_class != expected_reason_class
        or baseline.get("decided_at") != observed_marker
        or receipt.decided_at.isoformat().replace("+00:00", "Z") != observed_marker
    ):
        raise ValueError("prospective QQQ baseline and receipt lineage is inconsistent")
    validated_local_input_availability = _validate_recorded_local_input_availability(
        local_input_availability,
        catalog=catalog,
        cache_root=cache_root,
        repository_root=repository_root,
        recomputed=recomputed,
        receipt=receipt,
    )
    if reason_code == "runtime_window_not_locally_available":
        if (
            validated_local_input_availability is None
            or validated_local_input_availability.get("local_input_available_by_decision")
            is not False
        ):
            raise ValueError("local input availability no-intent evidence is inconsistent")
    elif reason_code == "runtime_window_local_availability_unavailable":
        if validated_local_input_availability is not None:
            raise ValueError("local input availability recovery evidence is inconsistent")
    elif (
        validated_local_input_availability is not None
        and validated_local_input_availability.get("local_input_available_by_decision") is not True
    ):
        raise ValueError("unavailable local input requires its exact no-intent reason")
    if status == "canary_completed" and (
        validated_local_input_availability is not None
        and validated_local_input_availability.get("local_input_available_by_decision") is not True
    ):
        raise ValueError("completed prospective QQQ canary lacks local input availability")
    replay = _object_or_none(loop.get("local_paper_replay"), "prospective QQQ local-paper replay")
    if recomputed.status != "ready":
        if replay is not None or baseline.get("action") != "abstain":
            raise ValueError("unready prospective QQQ input is not an abstaining no-intent fact")
        return expected_window, None, validated_local_input_availability
    if replay is None:
        raise ValueError("ready prospective QQQ runtime window lacks local-paper replay evidence")
    if replay.get("status") == "filled":
        if replay.get("fill_source") != "local_paper":
            raise ValueError("prospective QQQ replay fill source is not local_paper")
        _require_sha256(replay.get("event_log_sha256"), "prospective QQQ replay event log")
    elif replay.get("status") not in {"no_intent", "awaiting_replay_bar"}:
        raise ValueError("prospective QQQ local-paper replay status is invalid")
    return expected_window, {
        "status": replay.get("status"),
        "fill_source": replay.get("fill_source"),
        "event_log_sha256": replay.get("event_log_sha256"),
    }, validated_local_input_availability


def _validate_recorded_local_input_availability(
    recorded: Mapping[str, object] | None,
    *,
    catalog,
    cache_root: Path,
    repository_root: Path,
    recomputed: KisPaperIntradayRuntimeWindow,
    receipt: ResearchDecisionReceipt,
) -> dict[str, object] | None:
    if recorded is None:
        return None
    attestation: KisPaperIntradayRuntimeWindowLocalAvailability = (
        attest_kis_paper_intraday_runtime_window_local_availability(
            catalog,
            runtime_window=recomputed,
            cache_root=cache_root,
            repo_root=repository_root,
            decided_at=receipt.decided_at,
        )
    )
    expected = attestation.safe_payload()
    if dict(recorded) != expected:
        raise ValueError("local input availability does not match verified cache")
    return expected


def _validate_recorded_freshness(
    recorded: Mapping[str, object] | None,
    *,
    field_name: str,
    recomputed: KisPaperIntradayRuntimeWindow,
    session_observed_at: datetime,
) -> bool | None:
    if recorded is None:
        return None
    checked_at = _parse_utc(
        recorded.get("route_observed_at"),
        f"prospective QQQ {field_name} freshness observed_at",
    )
    if checked_at < session_observed_at:
        raise ValueError(f"{field_name} freshness precedes the session observation")
    expected = recomputed.freshness_at(as_of=checked_at)
    if dict(recorded) != expected.safe_payload():
        raise ValueError(f"{field_name} freshness does not match verified cache")
    return expected.current


def _reject_unsafe_surface(payload: bytes) -> None:
    lowered = payload.lower()
    if b"kis_live" in lowered or any(
        key in lowered
        for key in (b'"app_key"', b'"app_secret"', b'"account_no"', b'"authorization"')
    ):
        raise ValueError("prospective QQQ evidence has an unsafe route or credential surface")


def _json_object(value: bytes, name: str) -> Mapping[str, object]:
    try:
        parsed = json.loads(value.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not valid ASCII JSON") from error
    return _object(parsed, name)


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _object_or_none(value: object, name: str) -> Mapping[str, object] | None:
    return None if value is None else _object(value, name)


def _validated_decision_receipt(payload: Mapping[str, object]) -> ResearchDecisionReceipt:
    try:
        schema_version = payload.get("schema_version")
        if not isinstance(schema_version, int):
            raise ValueError("receipt schema_version is invalid")
        return ResearchDecisionReceipt(
            campaign_ref=_required_string(payload.get("campaign_ref"), "receipt campaign_ref"),
            model_ref=_required_string(payload.get("model_ref"), "receipt model_ref"),
            input_manifest_ref=_required_string(
                payload.get("input_manifest_ref"),
                "receipt input_manifest_ref",
            ),
            proposal_ref=_required_string(payload.get("proposal_ref"), "receipt proposal_ref"),
            instrument_binding_ref=_optional_string(
                payload.get("instrument_binding_ref"),
                "receipt instrument_binding_ref",
            ),
            target_binding_ref=_optional_string(
                payload.get("target_binding_ref"),
                "receipt target_binding_ref",
            ),
            decision_id=_required_string(payload.get("decision_id"), "receipt decision_id"),
            decision_class=_required_string(
                payload.get("decision_class"),
                "receipt decision_class",
            ),
            input_status=_required_string(payload.get("input_status"), "receipt input_status"),
            decided_at=_parse_utc(payload.get("decided_at"), "receipt decided_at"),
            valid_until=_parse_utc(payload.get("valid_until"), "receipt valid_until"),
            reason_class=_required_string(payload.get("reason_class"), "receipt reason_class"),
            schema_version=schema_version,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("prospective QQQ decision receipt is invalid") from error


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _optional_string(value: object, name: str) -> str | None:
    return None if value is None else _required_string(value, name)


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be a UTC timestamp") from error
    if parsed.tzinfo is not UTC:
        raise ValueError(f"{name} must be a UTC timestamp")
    return require_utc(parsed, name)


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise ValueError("prospective QQQ validation root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validation_evidence_path(*, root: Path, session_id: str) -> Path:
    """Namespace immutable validation outputs by their checked contract."""

    return (
        root
        / KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_ARTIFACT_DIRECTORY
        / KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID
        / f"{session_id}.json"
    )


def _write_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != rendered:
            raise ValueError("prospective QQQ validation evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _require_session_id(value: str) -> None:
    if _SAFE_SESSION_ID.fullmatch(value) is None:
        raise ValueError("prospective validation session id is invalid")


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256_REF.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact sha256 reference")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_json(value: Mapping[str, object]) -> str:
    return _sha256_bytes(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently reattach one prospective QQQ Paper session"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--session-id")
    source.add_argument("--latest", action="store_true")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=KIS_PAPER_PROSPECTIVE_QQQ_HEAD_CACHE_ROOT,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_PROSPECTIVE_QQQ_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    session_id = (
        latest_kis_paper_prospective_qqq_session_id(artifact_root=args.artifact_root)
        if args.latest
        else args.session_id
    )
    assert isinstance(session_id, str)
    result = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=args.cache_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()
