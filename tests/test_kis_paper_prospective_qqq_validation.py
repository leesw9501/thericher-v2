from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    select_kis_paper_intraday_runtime_window,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_paper_prospective_qqq_session import (
    KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY,
    KIS_PAPER_PROSPECTIVE_QQQ_SESSION_KIND,
)
from thericher_v2.ops.kis_paper_prospective_qqq_validation import (
    KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_ARTIFACT_DIRECTORY,
    KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID,
    validate_kis_paper_prospective_qqq_session,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.kis_paper_prospective_loop import run_kis_paper_prospective_loop

_SESSION_DATE = date(2026, 7, 20)
_CATALOG_ID = "kis.paper.private.intraday.qqq.nas.m1.validation-v1"
_COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_recomputes_ready_window_and_local_paper_replay_without_external_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    session_id = "prospective-qqq-validation-ready"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="account_unavailable",
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.validation_scope == "runtime_recomputed"
    assert result.session_status == "no_intent"
    assert result.runtime_window is not None
    assert result.runtime_window["status"] == "ready"
    assert result.local_paper_replay == {
        "status": "filled",
        "fill_source": "local_paper",
        "event_log_sha256": loop.local_paper_replay.event_log_sha256,
    }
    rendered = result.evidence_path.read_text(encoding="ascii")
    assert result.evidence_path.is_relative_to(
        artifact_root / KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_ARTIFACT_DIRECTORY
    )
    assert result.evidence_path.parent.name == KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID
    assert result.safe_payload()["validation_contract"] == (
        KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID
    )
    assert "100.000" not in rendered
    assert '"price"' not in rendered
    assert "credential" not in rendered


def test_accepts_reduce_baseline_narrowed_to_abstain_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    payload = loop.safe_payload()
    _replace_loop_receipt_action(payload, action="reduce")

    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-reduce",
        observed_at=catalog.bars[-1].end_ts,
        loop=payload,
        status="no_intent",
        reason_code="receipt_not_eligible",
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id="prospective-qqq-validation-reduce",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.session_status == "no_intent"
    assert result.runtime_window is not None


def test_rejects_reduce_baseline_with_enter_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    payload = loop.safe_payload()
    baseline = payload["baseline"]
    assert isinstance(baseline, dict)
    baseline["action"] = "reduce"

    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-reduce-mismatch",
        observed_at=catalog.bars[-1].end_ts,
        loop=payload,
        status="no_intent",
        reason_code="receipt_not_eligible",
    )

    with pytest.raises(ValueError, match="baseline and receipt lineage"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-reduce-mismatch",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_reduce_baseline_with_model_abstain_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    payload = loop.safe_payload()
    _replace_loop_receipt_action(payload, action="abstain")
    baseline = payload["baseline"]
    assert isinstance(baseline, dict)
    baseline["action"] = "reduce"

    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-reduce-reason-mismatch",
        observed_at=catalog.bars[-1].end_ts,
        loop=payload,
        status="no_intent",
        reason_code="receipt_not_eligible",
    )

    with pytest.raises(ValueError, match="baseline and receipt lineage"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-reduce-reason-mismatch",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_unknown_persisted_baseline_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    payload = loop.safe_payload()
    baseline = payload["baseline"]
    assert isinstance(baseline, dict)
    baseline["action"] = "future_action"

    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-unknown-action",
        observed_at=catalog.bars[-1].end_ts,
        loop=payload,
        status="no_intent",
        reason_code="receipt_not_eligible",
    )

    with pytest.raises(ValueError, match="baseline and receipt lineage"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-unknown-action",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_tampered_immutable_receipt_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    payload = loop.safe_payload()
    receipt = payload["receipt"]
    assert isinstance(receipt, dict)
    receipt["decision_id"] = "decision:sha256:" + "0" * 64

    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-tampered-receipt",
        observed_at=catalog.bars[-1].end_ts,
        loop=payload,
        status="no_intent",
        reason_code="receipt_not_eligible",
    )

    with pytest.raises(ValueError, match="decision receipt is invalid"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-tampered-receipt",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_accepts_a_current_canary_lifecycle_only_with_matching_ready_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    session_id = "prospective-qqq-validation-canary"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="canary_completed",
        reason_code="cancelled",
        position_resolution={
            "paper_only": True,
            "action": "buy",
            "reason_code": "flat_qqq_position",
        },
        prepared={"route": "kis_paper", "status": "ready"},
        canary={
            "paper_only": True,
            "phase": "cancelled",
            "reconciliation_status": "clean",
        },
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.session_status == "canary_completed"
    assert result.canary_present is True
    assert result.runtime_window is not None
    assert result.runtime_window["input_manifest_ref"] == loop.window.input_manifest_ref


@pytest.mark.parametrize(
    ("phase", "reconciliation_status"),
    [
        ("outcome_unknown", "unresolved"),
        ("submitted", "clean"),
        ("cancelled", "unresolved"),
    ],
)
def test_rejects_completed_canary_without_terminal_clean_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    phase: str,
    reconciliation_status: str,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id=f"prospective-qqq-validation-incomplete-{phase}-{reconciliation_status}",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="canary_completed",
        reason_code="reconciliation_unresolved",
        position_resolution={"paper_only": True, "action": "buy"},
        prepared={"route": "kis_paper", "status": "ready"},
        canary={
            "paper_only": True,
            "phase": phase,
            "reconciliation_status": reconciliation_status,
        },
    )

    with pytest.raises(ValueError, match="canary (lifecycle|reconciliation) is incomplete"):
        validate_kis_paper_prospective_qqq_session(
            session_id=f"prospective-qqq-validation-incomplete-{phase}-{reconciliation_status}",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_stale_window_is_a_valid_target_local_no_intent_fact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(90)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    observed_at = catalog.bars[-1].end_ts + timedelta(minutes=3)
    window = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=observed_at,
        max_age=timedelta(minutes=2),
    )
    loop = run_kis_paper_prospective_loop(
        window,
        local_paper_state_root=tmp_path / "local-paper",
        repo_root=repository_root,
    )
    session_id = "prospective-qqq-validation-stale"
    _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=observed_at,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="runtime_window_stale",
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.validation_scope == "runtime_recomputed"
    assert result.runtime_window is not None
    assert result.runtime_window["status"] == "stale"
    assert result.local_paper_replay is None
    assert result.canary_present is False


def test_accepts_legacy_runtime_window_payload_without_freshness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    legacy_loop = loop.safe_payload()
    legacy_window = legacy_loop["window"]
    assert isinstance(legacy_window, dict)
    legacy_window.pop("freshness")
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-legacy-freshness",
        observed_at=catalog.bars[-1].end_ts,
        loop=legacy_loop,
        status="no_intent",
        reason_code="account_unavailable",
        include_freshness_fields=False,
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id="prospective-qqq-validation-legacy-freshness",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.runtime_window is not None
    assert result.runtime_window["freshness"]["lag_category"] == "within_budget"


def test_validates_pre_account_expiry_against_the_recomputed_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    pre_account_freshness = loop.window.freshness_at(
        as_of=catalog.bars[-1].end_ts + timedelta(minutes=2, microseconds=1)
    ).safe_payload()
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-pre-account-freshness",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="runtime_window_expired_before_account",
        pre_account_freshness=pre_account_freshness,
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id="prospective-qqq-validation-pre-account-freshness",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.session_status == "no_intent"
    assert result.canary_present is False


def test_revalidation_keeps_legacy_validation_evidence_immutable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    session_id = "prospective-qqq-validation-contract-revision"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="account_unavailable",
    )
    legacy_path = (
        artifact_root
        / KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_ARTIFACT_DIRECTORY
        / f"{session_id}.json"
    )
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_rendered = '{"legacy_validation_contract":true}\n'
    legacy_path.write_text(legacy_rendered, encoding="ascii")

    result = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    repeated = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert legacy_path.read_text(encoding="ascii") == legacy_rendered
    assert result.evidence_path != legacy_path
    assert result.evidence_path.parent.name == KIS_PAPER_PROSPECTIVE_QQQ_VALIDATION_CONTRACT_ID
    assert repeated.evidence_path == result.evidence_path
    assert repeated.validation_identity == result.validation_identity


def test_validates_pre_submit_freshness_against_the_recomputed_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    pre_submit_freshness = loop.window.freshness_at(
        as_of=catalog.bars[-1].end_ts + timedelta(minutes=2, microseconds=1)
    ).safe_payload()
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-pre-submit-freshness",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="runtime_window_expired_during_preparation",
        position_resolution={"paper_only": True},
        prepared={"route": "kis_paper", "status": "ready"},
        pre_submit_freshness=pre_submit_freshness,
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id="prospective-qqq-validation-pre-submit-freshness",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.session_status == "no_intent"
    assert result.canary_present is False


def test_rejects_no_intent_with_a_non_paper_prepared_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-no-intent-non-paper",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="receipt_preparation_unavailable",
        prepared={"route": "live", "status": "no_intent"},
    )

    with pytest.raises(ValueError, match="prepared route is invalid"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-no-intent-non-paper",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_no_intent_with_a_non_paper_position_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-no-intent-non-paper-position",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="target_bridge_mismatch",
        position_resolution={"paper_only": False},
        prepared={"route": "kis_paper", "status": "ready"},
    )

    with pytest.raises(ValueError, match="position route is invalid"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-no-intent-non-paper-position",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_expiry_reason_with_current_pre_submit_freshness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    pre_submit_freshness = loop.window.freshness_at(
        as_of=catalog.bars[-1].end_ts
    ).safe_payload()
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-current-expiry",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="runtime_window_expired_during_preparation",
        position_resolution={"paper_only": True},
        prepared={"route": "kis_paper", "status": "ready"},
        pre_submit_freshness=pre_submit_freshness,
    )

    with pytest.raises(ValueError, match="pre-submit expiry freshness is inconsistent"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-current-expiry",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_pre_submit_freshness_before_the_session_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    pre_submit_freshness = loop.window.freshness_at(
        as_of=catalog.bars[-1].end_ts - timedelta(microseconds=1)
    ).safe_payload()
    _write_session(
        artifact_root,
        session_id="prospective-qqq-validation-pre-submit-before-observation",
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="runtime_window_expired_during_preparation",
        position_resolution={"paper_only": True},
        prepared={"route": "kis_paper", "status": "ready"},
        pre_submit_freshness=pre_submit_freshness,
    )

    with pytest.raises(ValueError, match="pre-submit freshness precedes"):
        validate_kis_paper_prospective_qqq_session(
            session_id="prospective-qqq-validation-pre-submit-before-observation",
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_a_completed_canary_with_a_non_paper_prepared_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    session_id = "prospective-qqq-validation-wrong-route"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="canary_completed",
        reason_code="cancelled",
        position_resolution={"paper_only": True},
        prepared={"route": "local_paper"},
        canary={"paper_only": True},
    )

    with pytest.raises(ValueError, match="prepared route is invalid"):
        validate_kis_paper_prospective_qqq_session(
            session_id=session_id,
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_rejects_session_evidence_that_does_not_match_the_verified_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_validator_catalog(monkeypatch, catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    session_id = "prospective-qqq-validation-corrupt"
    loop = _ready_loop(catalog, tmp_path=tmp_path, repository_root=repository_root)
    evidence_path = _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=catalog.bars[-1].end_ts,
        loop=loop.safe_payload(),
        status="no_intent",
        reason_code="account_unavailable",
    )
    payload = json.loads(evidence_path.read_text(encoding="ascii"))
    payload["loop"]["window"]["input_manifest_ref"] = "sha256:" + "0" * 64
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True),
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="does not match verified cache"):
        validate_kis_paper_prospective_qqq_session(
            session_id=session_id,
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def test_catalog_unavailable_recovery_never_attempts_a_cache_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = __import__(
        "thericher_v2.ops.kis_paper_prospective_qqq_validation",
        fromlist=["placeholder"],
    )

    def fail_catalog(**_kwargs: object) -> CatalogedBars:
        raise AssertionError("catalog-recovery validation must not load a cache")

    monkeypatch.setattr(module, "load_verified_kis_paper_private_intraday_catalog", fail_catalog)
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    session_id = "prospective-qqq-validation-recovery"
    observed_at = us_equity_2026_session(_SESSION_DATE).window.open_ts
    _write_session(
        artifact_root,
        session_id=session_id,
        observed_at=observed_at,
        loop=None,
        status="no_intent",
        reason_code="verified_catalog_unavailable",
    )

    result = validate_kis_paper_prospective_qqq_session(
        session_id=session_id,
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.validation_scope == "target_local_recovery"
    assert result.runtime_window is None
    assert result.local_paper_replay is None


def test_compose_validation_service_is_offline_and_has_no_kis_credential_surface() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split(
        "\n  kis-paper-prospective-qqq-validation:\n", maxsplit=1
    )[1].split("\n  kis-paper-intraday-head-receipt:\n", maxsplit=1)[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "network_mode: none" in section
    assert "read_only: true" in section
    assert "thericher_v2.ops.kis_paper_prospective_qqq_validation" in section
    assert "KIS_PAPER_" not in section
    assert "kis_live" not in lowered
    assert "/app/market_data:ro" in section
    assert "/app/model_artifacts" in section


def _ready_loop(catalog: CatalogedBars, *, tmp_path: Path, repository_root: Path):
    window = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=catalog.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )
    result = run_kis_paper_prospective_loop(
        window,
        local_paper_state_root=tmp_path / "local-paper",
        repo_root=repository_root,
    )
    assert result.local_paper_replay is not None
    return result


def _replace_loop_receipt_action(payload: dict[str, object], *, action: str) -> None:
    baseline = payload["baseline"]
    receipt = payload["receipt"]
    assert isinstance(baseline, dict)
    assert isinstance(receipt, dict)
    decided_at = _parse_marker(baseline["decided_at"])
    valid_until = _parse_marker(baseline["valid_until"])
    proposal = TargetExposureProposal(
        proposal_id="prospective-qqq-validation-proposal",
        symbol="QQQ",
        market="US",
        action=action,  # type: ignore[arg-type]
        target_exposure=Decimal("0.5") if action not in {"abstain", "exit"} else Decimal("0"),
        confidence=Decimal("0.5"),
        feature_schema_id="prospective-qqq-validation",
        input_status=baseline["input_status"],  # type: ignore[arg-type]
        decided_at=decided_at,
        valid_until=valid_until,
        feature_window_end=decided_at,
        reason="test-only receipt projection",
    )
    projected = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=receipt["campaign_ref"],  # type: ignore[arg-type]
            model_ref=receipt["model_ref"],  # type: ignore[arg-type]
            input_manifest_ref=receipt["input_manifest_ref"],  # type: ignore[arg-type]
            proposal_ref=receipt["proposal_ref"],  # type: ignore[arg-type]
        ),
    )
    baseline["action"] = action
    payload["receipt"] = projected.to_payload()


def _parse_marker(value: object) -> datetime:
    assert isinstance(value, str)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_session(
    artifact_root: Path,
    *,
    session_id: str,
    observed_at,
    loop: dict[str, object] | None,
    status: str,
    reason_code: str,
    position_resolution: dict[str, object] | None = None,
    prepared: dict[str, object] | None = None,
    pre_account_freshness: dict[str, object] | None = None,
    pre_submit_freshness: dict[str, object] | None = None,
    canary: dict[str, object] | None = None,
    include_freshness_fields: bool = True,
) -> Path:
    payload = {
        "schema_version": 1,
        "kind": KIS_PAPER_PROSPECTIVE_QQQ_SESSION_KIND,
        "session_id": session_id,
        "status": status,
        "reason_code": reason_code,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "paper_only": True,
        "loop": loop,
        "position_resolution": position_resolution,
        "prepared": prepared,
        "canary": canary,
    }
    if include_freshness_fields:
        payload["pre_account_freshness"] = pre_account_freshness
        payload["pre_submit_freshness"] = pre_submit_freshness
    path = (
        artifact_root
        / KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY
        / f"{session_id}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    return path


def _install_validator_catalog(monkeypatch: pytest.MonkeyPatch, catalog: CatalogedBars) -> None:
    module = __import__(
        "thericher_v2.ops.kis_paper_prospective_qqq_validation",
        fromlist=["placeholder"],
    )
    monkeypatch.setattr(
        module,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_kwargs: catalog,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective validation must stay offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)


def _catalog(count: int) -> CatalogedBars:
    session = us_equity_2026_session(_SESSION_DATE)
    assert session is not None
    bars = tuple(
        _bar(index=index, start_ts=session.window.open_ts + timedelta(minutes=index))
        for index in range(count)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id=_CATALOG_ID,
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("unit-index.json"),
        bars=bars,
    )


def _bar(*, index: int, start_ts) -> Bar:
    opened = Decimal("100") + Decimal(index) / Decimal("100")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("0.02"),
        low=opened - Decimal("0.01"),
        close=opened + Decimal("0.005"),
        volume=Decimal("1000"),
        complete=True,
    )
