from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution import kis_paper_receipt_observer
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
)
from thericher_v2.execution.kis_paper_receipt_observer import (
    KisPaperReceiptObservationError,
    observe_kis_paper_receipt,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlyClient,
    KisPaperReadOnlySnapshot,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)
READ_ONLY_NOW = datetime.now(UTC) + timedelta(hours=1)
RUN_ID = "receipt-" + "a" * 64
RAW_ORDER_ID = "ORD-123456789"


@dataclass
class FakeObserverTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    exact_open_order: bool = False
    same_day_id_seen: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        tr_id = request.headers.get("tr_id")
        if request.method == "POST" and request.url.endswith(KIS_PAPER_TOKEN_PATH):
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            rows = [_open_order_payload()] if self.exact_open_order else []
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": rows})
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1200.50",
                        "ovrs_ord_psbl_amt": "1199.75",
                    },
                }
            )
        if tr_id == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
            rows = [{"odno": RAW_ORDER_ID}] if self.same_day_id_seen else []
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": rows})
        raise AssertionError(f"unexpected observer request: {request!r}")


class NoCredentialEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"unexpected credential access: {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def test_open_receipt_observation_uses_only_read_only_kis_requests_and_redacts_raw_facts(
    tmp_path: Path,
) -> None:
    _write_state(tmp_path, phase="submitted", broker_order_id=RAW_ORDER_ID)
    transport = FakeObserverTransport(exact_open_order=True)

    outcome = _observe(tmp_path, transport=transport)

    observation = outcome.observation
    assert observation.lifecycle_state == "open"
    assert observation.open_order_observation == "exact_match"
    assert observation.same_day_order_id_observation == "same_day_id_absent"
    assert observation.position_state == "flat"
    assert observation.pnl_status == "not_observed"
    assert outcome.evidence_path.is_relative_to(tmp_path / "artifacts")
    assert not outcome.evidence_path.is_relative_to(tmp_path / "repo")
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("paper-app-secret", "12345678", RAW_ORDER_ID, "1200.50", "500.25"):
        assert forbidden not in evidence
    assert RAW_ORDER_ID not in repr(observation)
    assert all(
        request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        for request in transport.requests
    )
    assert all(
        not request.headers.get("tr_id", "").startswith("VTTT")
        for request in transport.requests
    )


def test_same_day_order_id_sighting_never_becomes_a_fill_or_realized_pnl(tmp_path: Path) -> None:
    _write_state(tmp_path, phase="submitted", broker_order_id=RAW_ORDER_ID)
    transport = FakeObserverTransport(same_day_id_seen=True)

    outcome = _observe(tmp_path, transport=transport)

    observation = outcome.observation
    assert observation.lifecycle_state == "outcome_unknown"
    assert observation.open_order_observation == "exact_absent"
    assert observation.same_day_order_id_observation == "same_day_id_seen"
    assert observation.reconciliation_status == "ambiguous"
    assert observation.reason_code == "same_day_order_id_not_terminal"
    assert observation.pnl_status == "not_observed"
    safe_payload = observation.safe_payload()
    assert safe_payload["lifecycle_state"] not in {"filled", "cancelled"}
    assert "realized" not in str(safe_payload)


def test_exact_absence_without_terminal_evidence_remains_scoped_and_ambiguous(
    tmp_path: Path,
) -> None:
    state_path = _write_state(tmp_path, phase="submitted", broker_order_id=RAW_ORDER_ID)
    before = state_path.read_bytes()
    transport = FakeObserverTransport()

    outcome = _observe(tmp_path, transport=transport)
    replay = _observe(tmp_path, transport=transport)

    observation = outcome.observation
    assert observation.lifecycle_state == "outcome_unknown"
    assert observation.account_fact_status == "current"
    assert observation.open_order_observation == "exact_absent"
    assert observation.same_day_order_id_observation == "same_day_id_absent"
    assert observation.reconciliation_status == "ambiguous"
    assert observation.reason_code == "terminal_state_not_supported"
    assert observation.pnl_status == "not_observed"
    assert replay.observation.safe_payload() == observation.safe_payload()
    assert state_path.read_bytes() == before
    assert all(
        request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        for request in transport.requests
    )
    assert all(
        not request.headers.get("tr_id", "").startswith("VTTT")
        for request in transport.requests
    )


def test_intent_only_and_missing_state_need_no_credentials_network_or_order_request(
    tmp_path: Path,
) -> None:
    _write_state(tmp_path, phase="intent_recorded", broker_order_id=None)
    intent_only = observe_kis_paper_receipt(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )
    missing = observe_kis_paper_receipt(
        run_id="receipt-" + "b" * 64,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )

    assert intent_only.observation.lifecycle_state == "not_submitted"
    assert intent_only.observation.reason_code == "intent_not_submitted"
    assert missing.observation.lifecycle_state == "not_submitted"
    assert missing.observation.reason_code == "state_missing"
    assert intent_only.observation.pnl_status == missing.observation.pnl_status == "not_observed"


def test_stale_account_fact_is_unavailable_and_does_not_query_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, phase="submitted", broker_order_id=RAW_ORDER_ID)

    def stale_snapshot(_client: KisPaperReadOnlyClient) -> KisPaperReadOnlySnapshot:
        return _snapshot(captured_at=NOW - timedelta(seconds=121))

    def fail_history(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("stale snapshot must not be followed by history lookup")

    monkeypatch.setattr(KisPaperReadOnlyClient, "snapshot", stale_snapshot)
    monkeypatch.setattr(KisPaperReadOnlyClient, "observe_same_day_order_id", fail_history)

    outcome = observe_kis_paper_receipt(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        client=KisPaperReadOnlyClient(config=_config(), transport=FakeObserverTransport()),
        now=NOW,
    )

    observation = outcome.observation
    assert observation.lifecycle_state == "unavailable"
    assert observation.reason_code == "account_snapshot_stale"
    assert observation.pnl_status == "not_observed"


def test_future_account_fact_is_unavailable_and_does_not_query_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, phase="submitted", broker_order_id=RAW_ORDER_ID)

    def future_snapshot(_client: KisPaperReadOnlyClient) -> KisPaperReadOnlySnapshot:
        return _snapshot(captured_at=NOW + timedelta(seconds=1))

    def fail_history(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("future snapshot must not be followed by history lookup")

    monkeypatch.setattr(KisPaperReadOnlyClient, "snapshot", future_snapshot)
    monkeypatch.setattr(KisPaperReadOnlyClient, "observe_same_day_order_id", fail_history)

    outcome = observe_kis_paper_receipt(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        client=KisPaperReadOnlyClient(config=_config(), transport=FakeObserverTransport()),
        now=NOW,
    )

    assert outcome.observation.lifecycle_state == "unavailable"
    assert outcome.observation.reason_code == "account_snapshot_stale"
    assert outcome.observation.pnl_status == "not_observed"


def test_observer_rejects_an_injected_non_readonly_client_before_any_state_or_network(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="exact read-only client"):
        observe_kis_paper_receipt(
            run_id=RUN_ID,
            environment=NoCredentialEnvironment(),
            state_root=tmp_path / "private",
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
            execute=True,
            client=object(),  # type: ignore[arg-type]
            now=NOW,
        )


def test_artifact_root_inside_the_actual_checkout_is_rejected_despite_caller_root(
    tmp_path: Path,
) -> None:
    _write_state(tmp_path, phase="intent_recorded", broker_order_id=None)
    actual_repository = Path(kis_paper_receipt_observer.__file__).resolve().parents[3]

    with pytest.raises(
        KisPaperReceiptObservationError,
        match="artifact root must stay outside Git",
    ):
        observe_kis_paper_receipt(
            run_id=RUN_ID,
            environment=NoCredentialEnvironment(),
            state_root=tmp_path / "private",
            artifact_root=actual_repository / "tests",
            repository_root=tmp_path / "pretend-repository",
            execute=True,
            now=NOW,
        )


def test_artifact_junction_back_to_checkout_is_rejected_before_any_write(tmp_path: Path) -> None:
    _write_state(tmp_path, phase="intent_recorded", broker_order_id=None)
    actual_repository = Path(kis_paper_receipt_observer.__file__).resolve().parents[3]
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    try:
        os.symlink(actual_repository, artifact_root / "execution", target_is_directory=True)
    except OSError:
        pytest.skip("this Windows test host does not permit directory symlinks")

    with pytest.raises(
        KisPaperReceiptObservationError,
        match="observation destination must stay outside Git",
    ):
        observe_kis_paper_receipt(
            run_id=RUN_ID,
            environment=NoCredentialEnvironment(),
            state_root=tmp_path / "private",
            artifact_root=artifact_root,
            repository_root=tmp_path / "pretend-repository",
            execute=True,
            now=NOW,
        )


def test_replay_is_idempotent_for_artifact_and_never_changes_the_private_intent(
    tmp_path: Path,
) -> None:
    state_path = _write_state(tmp_path, phase="submitted", broker_order_id=RAW_ORDER_ID)
    before = state_path.read_bytes()
    transport = FakeObserverTransport(exact_open_order=True)

    first = _observe(tmp_path, transport=transport)
    second = _observe(tmp_path, transport=transport)

    assert first.evidence_path == second.evidence_path
    assert first.evidence_path.read_bytes() == second.evidence_path.read_bytes()
    assert state_path.read_bytes() == before
    assert all(
        not request.headers.get("tr_id", "").startswith("VTTT")
        for request in transport.requests
    )


def test_invalid_private_state_fails_closed_without_credential_or_network_access(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "private" / f"{RUN_ID}.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not-json", encoding="utf-8")

    outcome = observe_kis_paper_receipt(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        now=NOW,
    )

    assert outcome.observation.lifecycle_state == "unavailable"
    assert outcome.observation.reason_code == "state_invalid"
    assert outcome.observation.pnl_status == "not_observed"


def _observe(
    tmp_path: Path,
    *,
    transport: FakeObserverTransport,
):
    return observe_kis_paper_receipt(
        run_id=RUN_ID,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        client=KisPaperReadOnlyClient(config=_config(), transport=transport),
        now=READ_ONLY_NOW,
        max_account_fact_age=timedelta(days=1),
    )


def _write_state(
    tmp_path: Path,
    *,
    phase: str,
    broker_order_id: str | None,
) -> Path:
    intent = KisPaperCanaryIntent(
        run_id=RUN_ID,
        client_order_id=f"canary-{RUN_ID}",
        decision_id=RUN_ID,
        symbol="SPY",
        exchange="AMEX",
        quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
        created_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=5),
    )
    reason_by_phase = {
        "intent_recorded": "preview",
        "submitted": "reconciliation_clean",
    }
    state = KisPaperCanaryState(
        intent=intent,
        phase=phase,
        updated_at=NOW,
        reason_code=reason_by_phase[phase],
        broker_order_id=broker_order_id,
    )
    path = tmp_path / "private" / f"{RUN_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), sort_keys=True), encoding="utf-8")
    return path


def _snapshot(*, captured_at: datetime) -> KisPaperReadOnlySnapshot:
    return KisPaperReadOnlySnapshot(
        identity=KisPaperAccountIdentity(masked_account="****5678-**", captured_at=captured_at),
        cash=KisPaperCashSnapshot(
            currency="USD",
            available_cash=Decimal("1"),
            captured_at=captured_at,
        ),
        orderable_funds=KisPaperOrderableFundsSnapshot(
            currency="USD",
            orderable_funds=Decimal("1"),
            reference_exchange="NASD",
            reference_symbol="SPY",
            reference_price=Decimal("1"),
            captured_at=captured_at,
        ),
        positions=(),
        open_orders=KisPaperOpenOrdersSnapshot(orders=(), captured_at=captured_at),
        captured_at=captured_at,
    )


def _config() -> KisPaperConfig:
    return KisPaperConfig(
        app_key="paper-app-key",
        app_secret="paper-app-secret",
        account_number="12345678",
        account_product_code="01",
    )


def _open_order_payload() -> dict[str, str]:
    return {
        "odno": RAW_ORDER_ID,
        "pdno": "SPY",
        "ovrs_excg_cd": "AMEX",
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "1",
        "ft_ccld_qty": "0",
        "nccs_qty": "1",
        "ft_ord_unpr3": "500.00",
    }
