from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
)
from thericher_v2.execution.kis_paper_terminal_field_probe import (
    probe_kis_paper_terminal_fields,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)
INTENT_CREATED_AT = datetime(2026, 7, 22, 3, 59, tzinfo=UTC)
SUBMITTED_AT = datetime(2026, 7, 22, 4, 1, tzinfo=UTC)
RUN_ID = "canary-terminal-field-probe-001"
RAW_ORDER_ID = "ORD-123456789"


@dataclass
class ProbeTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        if request.method == "POST" and request.url.endswith(KIS_PAPER_TOKEN_PATH):
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
        if request.headers.get("tr_id") == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": [
                        {
                            "odno": RAW_ORDER_ID,
                            "orgn_odno": "",
                            "ft_ord_qty": "1",
                            "ft_ccld_qty": "0",
                            "nccs_qty": "1",
                            "ft_ccld_unpr3": "0",
                            "ft_ccld_amt3": "0",
                            "prcs_stat_name": "private-status-text",
                            "rvse_cncl_dvsn": "00",
                            "ord_tmd": "101010",
                        }
                    ],
                }
            )
        raise AssertionError(f"unexpected terminal field request: {request!r}")


class NoCredentialEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"unexpected credential access: {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def test_terminal_field_probe_uses_private_state_only_in_memory_and_writes_redacted_evidence(
    tmp_path: Path,
) -> None:
    state_path = _write_state(tmp_path)
    before = state_path.read_bytes()
    transport = ProbeTransport()

    result = probe_kis_paper_terminal_fields(
        run_id=RUN_ID,
        environment=_environment(),
        state_root=tmp_path / "private" / "canary",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        transport=transport,
        now=NOW,
    )

    outcome = result.outcome
    assert outcome.status == "observed"
    assert outcome.reason_code == "history_observed"
    assert outcome.field_observation is not None
    assert outcome.field_observation.identity_match == "exact_order"
    assert outcome.field_observation.terminal_state_support == "unqualified"
    assert outcome.field_observation.pnl_status == "not_observed"
    assert outcome.safe_payload()["order_date_scope"] == "acknowledged_submission_et_day"
    assert result.evidence_path.is_relative_to(tmp_path / "artifacts")
    assert not result.evidence_path.is_relative_to(tmp_path / "repo")
    evidence = result.evidence_path.read_text(encoding="utf-8")
    for forbidden in (RAW_ORDER_ID, "500.25", "private-status-text", "paper-secret", "12345678"):
        assert forbidden not in evidence
    assert "run_id" not in evidence
    history_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id
    )
    assert history_request.query["ORD_STRT_DT"] == "20260722"
    assert history_request.query["ORD_END_DT"] == "20260722"
    assert all(
        request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        for request in transport.requests
    )
    assert all(
        not request.headers.get("tr_id", "").startswith("VTTT")
        for request in transport.requests
    )
    assert state_path.read_bytes() == before
    assert not state_path.with_name(f".{state_path.name}.lock").exists()


def test_missing_state_needs_no_credential_or_network_access(tmp_path: Path) -> None:
    result = probe_kis_paper_terminal_fields(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private" / "canary",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )

    assert result.outcome.status == "not_observed"
    assert result.outcome.reason_code == "state_missing"
    assert result.outcome.field_observation is None
    assert result.outcome.safe_payload()["pnl_status"] == "not_observed"


def test_preview_keeps_broker_order_id_private_and_makes_no_network_call(tmp_path: Path) -> None:
    _write_state(tmp_path)

    result = probe_kis_paper_terminal_fields(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private" / "canary",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=False,
        now=NOW,
    )

    assert result.outcome.status == "not_observed"
    assert result.outcome.reason_code == "preview"
    assert RAW_ORDER_ID not in result.evidence_path.read_text(encoding="utf-8")


def test_legacy_state_without_submission_time_needs_no_credential_or_network_access(
    tmp_path: Path,
) -> None:
    _write_state(tmp_path, submitted_at=None)

    result = probe_kis_paper_terminal_fields(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private" / "canary",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )

    assert result.outcome.status == "not_observed"
    assert result.outcome.reason_code == "submission_time_missing"
    assert result.outcome.field_observation is None
    assert result.outcome.safe_payload()["order_date_scope"] == "not_observed"


def test_state_run_mismatch_needs_no_credential_or_network_access(tmp_path: Path) -> None:
    _write_state(tmp_path, state_run_id="other-canary-run-001")

    result = probe_kis_paper_terminal_fields(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private" / "canary",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )

    assert result.outcome.status == "unavailable"
    assert result.outcome.reason_code == "state_run_mismatch"
    assert result.outcome.field_observation is None


@pytest.mark.parametrize(
    ("client_order_id", "decision_id"),
    [
        ("canary-other-run", RUN_ID),
        (f"canary-{RUN_ID}", "other-decision"),
    ],
)
def test_state_receipt_identity_mismatch_needs_no_credential_or_network_access(
    tmp_path: Path,
    client_order_id: str,
    decision_id: str,
) -> None:
    _write_state(
        tmp_path,
        client_order_id=client_order_id,
        decision_id=decision_id,
    )

    result = probe_kis_paper_terminal_fields(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private" / "canary",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )

    assert result.outcome.status == "unavailable"
    assert result.outcome.reason_code == "state_receipt_identity_mismatch"
    assert result.outcome.field_observation is None


def _write_state(
    tmp_path: Path,
    *,
    state_run_id: str = RUN_ID,
    submitted_at: datetime | None = SUBMITTED_AT,
    client_order_id: str | None = None,
    decision_id: str | None = None,
) -> Path:
    state_path = tmp_path / "private" / "canary" / f"{RUN_ID}.json"
    state_path.parent.mkdir(parents=True)
    intent = KisPaperCanaryIntent(
        run_id=state_run_id,
        client_order_id=client_order_id or f"canary-{state_run_id}",
        decision_id=decision_id or state_run_id,
        symbol="SPY",
        exchange="AMEX",
        quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
        created_at=INTENT_CREATED_AT,
        valid_until=INTENT_CREATED_AT + timedelta(minutes=5),
    )
    state = KisPaperCanaryState(
        intent=intent,
        phase="cancelled",
        updated_at=NOW,
        reason_code="reconciliation_clean",
        broker_order_id=RAW_ORDER_ID,
        submitted_at=submitted_at,
        cancel_after_submit=True,
    )
    state_path.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    return state_path


def _environment() -> Mapping[str, str]:
    return {
        "KIS_PAPER_APP_KEY": "paper-key",
        "KIS_PAPER_APP_SECRET": "paper-secret",
        "KIS_PAPER_ACCOUNT_NO": "12345678",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
    }
