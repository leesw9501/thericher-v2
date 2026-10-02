from __future__ import annotations

import json
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.execution import kis_readonly as readonly
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    KisPaperSubmitRejected,
)
from thericher_v2.execution.paper_canary_runtime import PaperCanaryRuntimeSnapshot

NOW = datetime(2026, 10, 3, tzinfo=UTC)
_CASES = [
    ("90070000", "paper_account_user_mismatch"),
    ("40910000", "paper_account_expired"),
    ("12345678", "paper_numeric_unclassified"),
    ("00000000", "paper_numeric_unclassified"),
    ("99999999", "paper_numeric_unclassified"),
]


@pytest.fixture(autouse=True)
def deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network and credential access forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(readonly.UrllibKisHttpTransport, "request", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config_from_environment", deny)


@pytest.mark.parametrize(("code", "category"), _CASES)
def test_numeric_codes_become_only_closed_idempotent_categories(code: str, category: str) -> None:
    assert readonly.safe_kis_paper_upstream_code(code) == category
    assert readonly.safe_kis_paper_upstream_code(category) == category
    assert code not in category


@pytest.mark.parametrize(("code", "category"), _CASES)
def test_readonly_failure_roundtrip_never_emits_numeric_code_or_message(
    code: str, category: str, capsys: pytest.CaptureFixture[str]
) -> None:
    response = readonly.KisHttpResponse.from_payload(
        {
            "rt_cd": "1",
            "msg_cd": code,
            "msg1": "raw-secret-message",
        }
    )
    with pytest.raises(readonly.KisPaperReadOnlyError) as raised:
        readonly._successful_payload(
            response,
            "orderable_funds_rejected",
            endpoint=readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
        )
    diagnostic = raised.value.diagnostic
    assert diagnostic == {
        "endpoint": "orderable_funds",
        "tr_id": "VTTS3007R",
        "http_status": "200",
        "upstream_code": category,
    }
    readonly.validate_kis_paper_readonly_diagnostic(json.loads(json.dumps(diagnostic)))
    assert code not in json.dumps(diagnostic)
    assert "raw-secret-message" not in str(raised.value) + json.dumps(diagnostic)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(("code", "category"), _CASES)
def test_actual_private_state_and_runtime_validators_accept_category_roundtrip(
    code: str, category: str
) -> None:
    state = KisPaperCanaryState(
        intent=KisPaperCanaryIntent(
            run_id="numeric-category-test",
            client_order_id="numeric-category-order",
            decision_id="numeric-category-decision",
            symbol="QQQ",
            exchange="NASD",
            quantity=Decimal("1"),
            limit_price=Decimal("500"),
            created_at=NOW,
            valid_until=NOW + timedelta(minutes=5),
        ),
        phase="outcome_unknown",
        updated_at=NOW,
        reason_code="submit_rejected",
        submission_started_at=NOW,
        submit_response_category="provider_rejected",
        submit_upstream_code=readonly.safe_kis_paper_upstream_code(code),
    )
    restored = KisPaperCanaryState.from_dict(json.loads(json.dumps(state.to_dict())))
    assert restored.submit_upstream_code == category
    assert restored.phase == "outcome_unknown"
    assert restored.broker_order_id is None and restored.cumulative_fill is None
    assert restored.intent.fingerprint == state.intent.fingerprint

    runtime = PaperCanaryRuntimeSnapshot(
        run_id=state.intent.run_id,
        status="outcome_unknown",
        reconciliation_status="unresolved",
        account_status="unknown",
        position_count=0,
        open_order_count=0,
        stop_new_orders=False,
        cancel_open_orders_requested=False,
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        submit_upstream_code=category,
    )
    runtime_payload = runtime.to_dict()
    restored_runtime = PaperCanaryRuntimeSnapshot.from_dict(json.loads(json.dumps(runtime_payload)))
    assert restored_runtime.submit_upstream_code == category
    assert restored_runtime.account_status == "unknown"
    assert restored_runtime.status == "outcome_unknown"
    assert code not in json.dumps(state.to_dict()) + json.dumps(runtime_payload)
    assert KisPaperSubmitRejected(upstream_code=category).upstream_code == category


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        90070000,
        40910000.0,
        {},
        [],
        "",
        "9007000",
        "900700000",
        " 90070000",
        "90070000 ",
        "90070000\n",
        "+90070000",
        "-90070000",
        "9.007e7",
        "９００７００００",
        "٩٠٠٧٠٠٠٠",
        "90070000 raw message",
        "paper_account_expired ",
        "paper_account_expired1",
        "paper_other_error",
        "paper_numeric_unclassified\n",
    ],
)
def test_absent_or_invalid_numeric_and_category_inputs_are_not_normalized(value: object) -> None:
    assert readonly.safe_kis_paper_upstream_code(value) is None


@pytest.mark.parametrize("code", ["EGW00201", "KIS1001", "A1", "X123456789012345"])
def test_existing_alphanumeric_codes_are_unchanged(code: str) -> None:
    assert readonly.safe_kis_paper_upstream_code(code) == code


@pytest.mark.parametrize("code", ["egw00201", "EGW-00201", " EGW00201", "A" * 17, "ONLYLETTERS"])
def test_existing_alphanumeric_filter_is_not_widened(code: str) -> None:
    assert readonly.safe_kis_paper_upstream_code(code) is None


@pytest.mark.parametrize("code", ["90070000", "40910000", "12345678", "paper_other_error"])
def test_private_diagnostic_validator_rejects_raw_or_unapproved_category(code: str) -> None:
    with pytest.raises(ValueError, match="upstream code is not allowlisted"):
        readonly.validate_kis_paper_readonly_diagnostic(
            {
                "endpoint": "orderable_funds",
                "tr_id": "VTTS3007R",
                "http_status": "200",
                "upstream_code": code,
            }
        )
