from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.ops.kis_paper_prospective_spy_cycle as cycle
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryOutcome,
    KisPaperCanaryReconciliation,
)
from thericher_v2.execution.kis_paper_prospective_spy_session import (
    KisPaperProspectiveSpySessionOutcome,
)
from thericher_v2.execution.kis_paper_receipt_canary import receipt_canary_run_id
from thericher_v2.execution.paper_decision_bridge import PaperDecisionBridgeResult
from thericher_v2.research.kis_paper_canary_intent import KisPaperCanaryBuyDecision

_OBSERVED_AT = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_CANONICAL_RECEIPT = '{"kind":"prospective-spy-observation-receipt-v1","receipt_id":"unit"}'
_DECISION_RECEIPT_REF = "sha256:" + "d" * 64
_PRICE_CONTRACT_REF = "sha256:" + "e" * 64


def test_not_ready_capture_never_touches_execution_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[object] = []

    def capture(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            status="not_yet_observed",
            reason="before_decision_cutoff",
            receipt=None,
        )

    def fail_execution(**_kwargs: object) -> None:
        raise AssertionError("not-ready capture must not touch the execution surface")

    monkeypatch.setattr(cycle, "capture_kis_paper_prospective_spy_observation", capture)
    monkeypatch.setattr(cycle, "run_kis_paper_prospective_spy_session", fail_execution)
    artifact_root, repository_root = _roots(tmp_path)

    outcome = cycle.run_kis_paper_prospective_spy_cycle(
        environment=_NoCredentialEnvironment(),
        observed_at=_OBSERVED_AT,
        cache_root=tmp_path / "intraday-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "before_decision_cutoff"
    assert outcome.execution_status is None
    assert len(calls) == 1
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["capture"] == {
        "reason_code": "before_decision_cutoff",
        "status": "not_yet_observed",
    }
    assert payload["execution"]["attempted"] is False
    _assert_safe(payload, artifact_root)


def test_captured_receipt_records_the_returned_durable_canary_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = SimpleNamespace(canonical_json=lambda: _CANONICAL_RECEIPT)
    captured_calls: list[dict[str, object]] = []
    execution_calls: list[dict[str, object]] = []

    def capture(**kwargs: object) -> SimpleNamespace:
        captured_calls.append(kwargs)
        return SimpleNamespace(status="captured", reason=None, receipt=receipt)

    def execute(**kwargs: object) -> KisPaperProspectiveSpySessionOutcome:
        execution_calls.append(kwargs)
        return _completed_session(
            session_id=kwargs["session_id"],
            artifact_root=artifact_root,
            decision_receipt_ref=_DECISION_RECEIPT_REF,
        )

    monkeypatch.setattr(cycle, "capture_kis_paper_prospective_spy_observation", capture)
    monkeypatch.setattr(cycle, "run_kis_paper_prospective_spy_session", execute)
    artifact_root, repository_root = _roots(tmp_path)

    outcome = cycle.run_kis_paper_prospective_spy_cycle(
        environment={"not": "read"},
        observed_at=_OBSERVED_AT,
        cache_root=tmp_path / "intraday-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    expected_observation_ref = cycle._observation_receipt_ref(_CANONICAL_RECEIPT)
    expected_canary_run_id = receipt_canary_run_id(_DECISION_RECEIPT_REF)
    assert outcome.status == "canary_completed"
    assert outcome.observation_receipt_ref == expected_observation_ref
    assert outcome.prepared_decision_receipt_ref == _DECISION_RECEIPT_REF
    assert outcome.canary_run_id == expected_canary_run_id
    assert outcome.canary_run_id != receipt_canary_run_id(expected_observation_ref)
    assert captured_calls[0]["cache_root"] == tmp_path / "intraday-head"
    assert execution_calls == [
        {
            "environment": {"not": "read"},
            "artifact_root": artifact_root.resolve(),
            "repository_root": repository_root,
            "state_root": tmp_path / "private",
            "runtime_projection_path": tmp_path / "runtime" / "projection.json",
            "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
            "emergency_state_path": tmp_path / "emergency" / "state.json",
            "execution_control_path": tmp_path / "emergency" / "control.json",
            "execute": True,
            "cancel_after_submit": True,
            "now": _OBSERVED_AT,
            "session_id": f"{outcome.cycle_id}-execution",
        }
    ]
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["execution"]["observation_receipt_ref"] == expected_observation_ref
    assert payload["execution"]["prepared_decision_receipt_ref"] == _DECISION_RECEIPT_REF
    assert payload["execution"]["canary_attempted"] is True
    assert payload["execution"]["canary_run_id"] == outcome.canary_run_id
    assert payload["execution"]["single_flight"] == "receipt_canary_state_lock"
    _assert_safe(payload, artifact_root)


def test_repeated_cycle_attempts_share_one_receipt_canary_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = SimpleNamespace(canonical_json=lambda: _CANONICAL_RECEIPT)
    canary_ids: list[str] = []

    monkeypatch.setattr(
        cycle,
        "capture_kis_paper_prospective_spy_observation",
        lambda **_kwargs: SimpleNamespace(status="captured", reason=None, receipt=receipt),
    )

    def execute(**kwargs: object) -> KisPaperProspectiveSpySessionOutcome:
        session = _completed_session(
            session_id=kwargs["session_id"],
            artifact_root=artifact_root,
            decision_receipt_ref=_DECISION_RECEIPT_REF,
        )
        assert session.canary is not None
        canary_ids.append(session.canary.run_id)
        return session

    monkeypatch.setattr(cycle, "run_kis_paper_prospective_spy_session", execute)
    artifact_root, repository_root = _roots(tmp_path)
    common = {
        "environment": {"not": "read"},
        "cache_root": tmp_path / "intraday-head",
        "artifact_root": artifact_root,
        "repository_root": repository_root,
        "execute": True,
        "cancel_after_submit": True,
        **_paths(tmp_path),
    }

    first = cycle.run_kis_paper_prospective_spy_cycle(observed_at=_OBSERVED_AT, **common)
    second = cycle.run_kis_paper_prospective_spy_cycle(
        observed_at=_OBSERVED_AT.replace(microsecond=1), **common
    )

    assert first.cycle_id != second.cycle_id
    assert first.observation_receipt_ref == second.observation_receipt_ref
    assert first.prepared_decision_receipt_ref == second.prepared_decision_receipt_ref
    assert first.canary_run_id == second.canary_run_id
    assert canary_ids == [first.canary_run_id, second.canary_run_id]


def test_captured_no_intent_never_falls_back_to_an_observation_derived_canary_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = SimpleNamespace(canonical_json=lambda: _CANONICAL_RECEIPT)
    monkeypatch.setattr(
        cycle,
        "capture_kis_paper_prospective_spy_observation",
        lambda **_kwargs: SimpleNamespace(status="captured", reason=None, receipt=receipt),
    )
    artifact_root, repository_root = _roots(tmp_path)

    def execute(**kwargs: object) -> KisPaperProspectiveSpySessionOutcome:
        return KisPaperProspectiveSpySessionOutcome(
            session_id=kwargs["session_id"],
            status="no_intent",
            reason_code="receipt_abstain",
            observed_at=_OBSERVED_AT,
            evidence_path=artifact_root / "session" / "evidence.json",
        )

    monkeypatch.setattr(cycle, "run_kis_paper_prospective_spy_session", execute)
    outcome = cycle.run_kis_paper_prospective_spy_cycle(
        environment={"not": "read"},
        observed_at=_OBSERVED_AT,
        cache_root=tmp_path / "intraday-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.observation_receipt_ref == cycle._observation_receipt_ref(_CANONICAL_RECEIPT)
    assert outcome.prepared_decision_receipt_ref is None
    assert outcome.canary_run_id is None
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["execution"]["canary_attempted"] is False
    assert payload["execution"]["canary_run_id"] is None


def test_same_cycle_replay_writes_identical_external_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        cycle,
        "capture_kis_paper_prospective_spy_observation",
        lambda **_kwargs: SimpleNamespace(
            status="not_yet_observed",
            reason="before_decision_cutoff",
            receipt=None,
        ),
    )
    artifact_root, repository_root = _roots(tmp_path)
    kwargs = {
        "environment": _NoCredentialEnvironment(),
        "observed_at": _OBSERVED_AT,
        "cache_root": tmp_path / "intraday-head",
        "artifact_root": artifact_root,
        "repository_root": repository_root,
        "execute": True,
        "cancel_after_submit": True,
        "cycle_id": "same-cycle",
        **_paths(tmp_path),
    }

    first = cycle.run_kis_paper_prospective_spy_cycle(**kwargs)
    second = cycle.run_kis_paper_prospective_spy_cycle(**kwargs)

    assert second.evidence_path == first.evidence_path
    assert second.evidence_path.read_bytes() == first.evidence_path.read_bytes()


def test_cycle_rejects_artifacts_inside_the_repository(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        cycle.run_kis_paper_prospective_spy_cycle(
            environment=_NoCredentialEnvironment(),
            observed_at=_OBSERVED_AT,
            cache_root=tmp_path / "intraday-head",
            artifact_root=repository_root / "artifacts",
            repository_root=repository_root,
            execute=False,
            cancel_after_submit=True,
            **_paths(tmp_path),
        )


class _NoCredentialEnvironment(dict[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"not-ready capture must not read {key}")

    def get(self, key: str, default=None):
        raise AssertionError(f"not-ready capture must not read {key}")


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    artifact_root.mkdir()
    repository_root.mkdir()
    return artifact_root, repository_root


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "state_root": tmp_path / "private",
        "runtime_projection_path": tmp_path / "runtime" / "projection.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency" / "state.json",
        "execution_control_path": tmp_path / "emergency" / "control.json",
    }


def _completed_session(
    *,
    session_id: str,
    artifact_root: Path,
    decision_receipt_ref: str,
) -> KisPaperProspectiveSpySessionOutcome:
    prepared = PaperDecisionBridgeResult(
        route="kis_paper",
        receipt_ref=decision_receipt_ref,
        status="ready",
        reason="eligible",
        kis_paper_decision=KisPaperCanaryBuyDecision(
            decision_id="unit-decision",
            symbol="SPY",
            exchange="AMEX",
            quantity=Decimal("1"),
            limit_price=Decimal("100"),
            decision_as_of=_OBSERVED_AT,
            valid_until=_OBSERVED_AT + timedelta(minutes=1),
        ),
        price_contract_ref=_PRICE_CONTRACT_REF,
    )
    canary = KisPaperCanaryOutcome(
        run_id=receipt_canary_run_id(decision_receipt_ref),
        phase="cancelled",
        reason_code="cancelled",
        evidence_path=artifact_root / "canary" / "evidence.json",
        runtime_path=artifact_root / "runtime" / "state.json",
        paper_account_snapshot_path=artifact_root / "runtime" / "account.json",
        reconciliation=KisPaperCanaryReconciliation(
            snapshot=None,
            account_status="available",
            ccnl_row_count=0,
            matching_open_order=False,
            matching_ccnl=False,
            status="clean",
        ),
    )
    return KisPaperProspectiveSpySessionOutcome(
        session_id=session_id,
        status="canary_completed",
        reason_code="cancelled",
        observed_at=_OBSERVED_AT,
        evidence_path=artifact_root / "session" / "evidence.json",
        prepared=prepared,
        canary=canary,
    )


def _assert_safe(payload: dict[str, object], artifact_root: Path) -> None:
    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    for forbidden in (str(artifact_root), "KIS_PAPER_APP_SECRET", "token", "12345678", "500.25"):
        assert forbidden not in rendered
