from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily_spy_input import KisPaperDailySpyInput
from thericher_v2.execution import kis_paper_daily_spy_session as session_module
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_daily_spy_session import KisPaperDailySpySessionOutcome
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_receipt_observer import KisPaperReceiptObservation
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
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


class NoCredentialEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"unexpected environment access: {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


@dataclass
class FakePaperClient:
    limit_input: KisPaperSpyLimitInput
    observed_at: datetime | None = None
    account_snapshot: KisPaperReadOnlySnapshot | None = None

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        return self.account_snapshot or _account_snapshot()

    def fetch_spy_limit_input(
        self, *, observed_at: datetime | None = None
    ) -> KisPaperSpyLimitInput:
        self.observed_at = observed_at
        return self.limit_input


@dataclass
class FakeObserverTransport:
    raw_order_id: str
    requests: list[KisHttpRequest] = field(default_factory=list)

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        tr_id = request.headers.get("tr_id")
        if request.method == "POST" and request.url.endswith(KIS_PAPER_TOKEN_PATH):
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
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
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {"rt_cd": "0", "output": [_open_order_payload(self.raw_order_id)]}
            )
        if tr_id == KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {"rt_cd": "0", "output": [{"odno": self.raw_order_id}]}
            )
        raise AssertionError(f"unexpected observer request: {request!r}")


@dataclass(frozen=True)
class FakeCanaryOutcome:
    run_id: str = "receipt-" + "a" * 64
    phase: str = "submitted"
    reason_code: str = "reconciliation_unresolved"

    def safe_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "reason_code": self.reason_code,
            "paper_only": True,
        }


def _fake_canary_outcome(prepared) -> FakeCanaryOutcome:
    return FakeCanaryOutcome(
        run_id="receipt-" + prepared.receipt_ref.removeprefix("sha256:"),
    )


def test_stale_daily_input_records_no_intent_without_credentials_or_transport(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 17)),
    )
    monkeypatch.setattr(
        session_module,
        "observe_kis_paper_receipt",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("no-intent session observed a receipt")
        ),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        now=NOW,
        session_id="stale-daily-input",
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "daily_receipt_not_current"
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"paper_only": true' in evidence
    assert "KIS_LIVE" not in evidence


def test_eligible_daily_receipt_reaches_only_the_receipt_canary_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    daily_input = _input(last_session=date(2026, 7, 21))
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: daily_input,
    )

    def run_canary(prepared, **kwargs):
        captured["prepared"] = prepared
        captured["kwargs"] = kwargs
        return _fake_canary_outcome(prepared)

    monkeypatch.setattr(session_module, "run_kis_paper_receipt_canary", run_canary)
    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="eligible-daily-input",
        **_paths(tmp_path),
    )

    prepared = captured["prepared"]
    assert outcome.status == "canary_completed"
    assert client.observed_at == NOW
    assert prepared.status == "ready"
    assert prepared.route == "kis_paper"
    assert captured["kwargs"]["environment"].__class__ is NoCredentialEnvironment
    assert outcome.observer_status == "completed"
    assert outcome.observation is not None
    assert outcome.observation.run_id == outcome.run_id
    assert outcome.observation.receipt_ref == outcome.receipt_ref
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("500.25", "D:/external/input.json", "KIS_LIVE"):
        assert forbidden not in evidence


def test_exit_receipt_with_one_current_spy_share_reaches_only_the_sell_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    daily_input = _input(
        last_session=date(2026, 7, 21),
        closes=(Decimal("101"), Decimal("100")),
    )
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        ),
        account_snapshot=_account_snapshot(positions=(_spy_position(),)),
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: daily_input,
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **kwargs: captured.update(prepared=prepared, kwargs=kwargs)
        or _fake_canary_outcome(prepared),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="eligible-daily-exit",
        **_paths(tmp_path),
    )

    prepared = captured["prepared"]
    assert outcome.status == "canary_completed"
    assert prepared.kis_paper_decision is not None
    assert prepared.kis_paper_decision.side == "sell"
    assert outcome.observer_status == "completed"
    assert outcome.observation is not None
    assert outcome.observation.run_id == outcome.run_id
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"action": "sell"' in evidence
    assert '"pnl_status": "not_observed"' in evidence
    for forbidden in ("500.25", "D:/external/input.json", "KIS_LIVE", "****5678-**"):
        assert forbidden not in evidence


def test_stale_account_snapshot_does_not_fetch_a_quote_or_submit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        ),
        account_snapshot=_account_snapshot(
            positions=(_spy_position(),),
            captured_at=NOW.replace(minute=27),
        ),
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="stale-account-fact",
        **_paths(tmp_path),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "account_snapshot_not_current"
    assert client.observed_at is None


def test_daily_session_observer_receives_only_the_completed_canary_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    captured: dict[str, object] = {}
    actual_observer = session_module.observe_kis_paper_receipt

    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **_kwargs: _fake_canary_outcome(prepared),
    )

    def observe(**kwargs):
        captured.update(kwargs)
        return actual_observer(**kwargs)

    monkeypatch.setattr(session_module, "observe_kis_paper_receipt", observe)
    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="same-run-observation",
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.observer_status == "completed"
    assert outcome.observation is not None
    assert captured["run_id"] == outcome.run_id
    assert outcome.observation.run_id == outcome.run_id
    assert outcome.observation.receipt_ref == outcome.receipt_ref
    assert outcome.observation.lifecycle_state == "not_submitted"
    assert outcome.observation.reason_code == "state_missing"
    assert captured["execute"] is True


def test_observer_error_never_changes_the_completed_canary_outcome(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **_kwargs: _fake_canary_outcome(prepared),
    )
    monkeypatch.setattr(
        session_module,
        "observe_kis_paper_receipt",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("observer transport failed")
        ),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="observer-failure-isolated",
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "reconciliation_unresolved"
    assert outcome.observer_status == "unavailable"
    assert outcome.observer_reason_code == "observer_unavailable"
    assert outcome.observation is None
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"observer_status": "unavailable"' in evidence
    assert '"observer_reason_code": "observer_unavailable"' in evidence


def test_unavailable_receipt_observation_remains_completed_session_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **_kwargs: _fake_canary_outcome(prepared),
    )

    def observe(**kwargs):
        run_id = kwargs["run_id"]
        return type(
            "ObservationOutcome",
            (),
            {
                "observation": KisPaperReceiptObservation(
                    run_id=run_id,
                    receipt_ref="sha256:" + run_id.removeprefix("receipt-"),
                    intent_ref=None,
                    decision_ref=None,
                    order_side=None,
                    state_phase=None,
                    observed_at=NOW,
                    lifecycle_state="unavailable",
                    account_fact_status="unavailable",
                    open_order_observation="unavailable",
                    same_day_order_id_observation="unavailable",
                    position_state="not_observed",
                    reconciliation_status="unavailable",
                    reason_code="read_only_unavailable",
                )
            },
        )()

    monkeypatch.setattr(session_module, "observe_kis_paper_receipt", observe)
    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        now=NOW,
        session_id="unavailable-observation-is-evidence",
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.observer_status == "completed"
    assert outcome.observer_reason_code is None
    assert outcome.observation is not None
    assert outcome.observation.lifecycle_state == "unavailable"
    assert outcome.observation.pnl_status == "not_observed"


def test_daily_session_linked_observer_uses_only_read_only_routes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_order_id = "ORD-123456789"
    transport = FakeObserverTransport(raw_order_id=raw_order_id)
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    actual_observer = session_module.observe_kis_paper_receipt
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **kwargs: _write_submitted_state_for_canary(
            kwargs["state_root"],
            _fake_canary_outcome(prepared),
            raw_order_id=raw_order_id,
        ),
    )

    def observe(**kwargs):
        captured.update(kwargs)
        return actual_observer(
            **{
                **kwargs,
                "now": None,
                "clock": lambda: datetime.now(UTC),
            }
        )

    monkeypatch.setattr(session_module, "observe_kis_paper_receipt", observe)
    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=_paper_environment(),
        execute=True,
        cancel_after_submit=False,
        client=client,  # type: ignore[arg-type]
        transport=transport,
        now=NOW,
        session_id="linked-readonly-observation",
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.observer_status == "completed"
    assert outcome.observation is not None
    assert outcome.observation.lifecycle_state == "open"
    assert outcome.observation.pnl_status == "not_observed"
    assert captured["run_id"] == outcome.run_id
    assert all(
        request.method == "GET" or request.url.endswith(KIS_PAPER_TOKEN_PATH)
        for request in transport.requests
    )
    assert {
        KIS_PAPER_BALANCE_ENDPOINT.tr_id,
        KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id,
        KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
        KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id,
    } <= {request.headers.get("tr_id") for request in transport.requests}
    assert all(
        not request.headers.get("tr_id", "").startswith("VTTT")
        for request in transport.requests
    )
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in (raw_order_id, "1200.50", "500.25", "12345678", "paper-app-secret"):
        assert forbidden not in evidence


def test_mismatched_canary_run_is_rejected_before_observer_invocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    observer_called = False
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda _prepared, **_kwargs: FakeCanaryOutcome(run_id="receipt-" + "b" * 64),
    )

    def observe(**_kwargs):
        nonlocal observer_called
        observer_called = True
        raise AssertionError("mismatched canary result reached observer")

    monkeypatch.setattr(session_module, "observe_kis_paper_receipt", observe)
    with pytest.raises(ValueError, match="canary run identity"):
        session_module.run_kis_paper_daily_spy_session(
            environment=NoCredentialEnvironment(),
            execute=True,
            cancel_after_submit=False,
            client=client,  # type: ignore[arg-type]
            now=NOW,
            session_id="mismatched-run-before-observer",
            **_paths(tmp_path),
        )

    assert observer_called is False


def test_completed_session_replay_reuses_only_its_same_safe_observation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = FakePaperClient(
        limit_input=KisPaperSpyLimitInput(
            last=Decimal("500.25"),
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=NOW,
        )
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )
    monkeypatch.setattr(
        session_module,
        "run_kis_paper_receipt_canary",
        lambda prepared, **_kwargs: _fake_canary_outcome(prepared),
    )

    kwargs = {
        "environment": NoCredentialEnvironment(),
        "execute": True,
        "cancel_after_submit": False,
        "client": client,
        "now": NOW,
        "session_id": "same-run-replay",
        **_paths(tmp_path),
    }
    first = session_module.run_kis_paper_daily_spy_session(**kwargs)  # type: ignore[arg-type]
    second = session_module.run_kis_paper_daily_spy_session(**kwargs)  # type: ignore[arg-type]

    assert first.evidence_path == second.evidence_path
    assert first.evidence_path.read_bytes() == second.evidence_path.read_bytes()
    assert first.run_id == second.run_id
    assert first.observation is not None
    assert second.observation is not None
    assert first.observation.safe_payload() == second.observation.safe_payload()


def test_daily_session_rejects_a_mismatched_receipt_run_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="receipt and run identity"):
        KisPaperDailySpySessionOutcome(
            session_id="mismatched-receipt-run",
            status="canary_completed",
            reason_code="reconciliation_unresolved",
            observed_at=NOW,
            evidence_path=tmp_path / "evidence.json",
            receipt_ref="sha256:" + "a" * 64,
            run_id="receipt-" + "b" * 64,
        )


def test_preview_is_offline_even_for_an_eligible_daily_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: _input(last_session=date(2026, 7, 21)),
    )

    outcome = session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=False,
        cancel_after_submit=False,
        now=NOW,
        session_id="preview-daily-input",
        **_paths(tmp_path),
    )

    assert outcome.status == "preview"
    assert outcome.reason_code == "preview"


def test_preferred_input_chooses_one_newer_head_source_without_row_mixing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    head_input = _input(last_session=date(2026, 7, 21))
    history_input = _input(last_session=date(2026, 7, 17))
    head = type(
        "Head",
        (),
        {
            "bars": head_input.bars,
            "dataset_id": head_input.catalog_dataset_id,
            "dataset_hash": head_input.catalog_dataset_hash,
        },
    )()
    monkeypatch.setattr(
        session_module,
        "load_verified_kis_paper_daily_spy_head",
        lambda **_kwargs: head,
    )
    monkeypatch.setattr(
        session_module,
        "attest_kis_paper_daily_spy_bars",
        lambda **_kwargs: head_input,
    )
    monkeypatch.setattr(
        session_module,
        "load_kis_paper_daily_spy_input",
        lambda **_kwargs: history_input,
    )

    selected = session_module._load_preferred_daily_spy_input(
        cache_root=tmp_path / "history",
        head_cache_root=tmp_path / "head",
        availability_root=tmp_path / "availability",
        repository_root=tmp_path / "repo",
        attested_at=NOW,
    )

    assert selected is head_input
    assert selected.bars == head_input.bars
    assert selected.last_consumed_session != history_input.last_consumed_session


def _input(
    *,
    last_session: date,
    closes: tuple[Decimal, Decimal] = (Decimal("100"), Decimal("101")),
) -> KisPaperDailySpyInput:
    previous_session = date(2026, 7, 20) if last_session == date(2026, 7, 21) else date(2026, 7, 16)
    return KisPaperDailySpyInput(
        bars=(
            _bar(previous_session, closes[0]),
            _bar(last_session, closes[1]),
        ),
        catalog_dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        catalog_dataset_hash="sha256:" + "a" * 64,
        last_consumed_session=last_session,
        first_available_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        input_manifest_ref="sha256:" + "b" * 64,
        availability_record_path=Path("D:/external/input.json"),
    )


def _bar(session: date, close: Decimal) -> Bar:
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _account_snapshot(
    *,
    positions: tuple[KisPaperPosition, ...] = (),
    captured_at: datetime = NOW,
) -> KisPaperReadOnlySnapshot:
    return KisPaperReadOnlySnapshot(
        identity=KisPaperAccountIdentity("****5678-**", captured_at),
        cash=KisPaperCashSnapshot("USD", Decimal("1000"), captured_at),
        orderable_funds=KisPaperOrderableFundsSnapshot(
            "USD",
            Decimal("1000"),
            "NASD",
            "SPY",
            Decimal("1"),
            captured_at,
        ),
        positions=positions,
        open_orders=KisPaperOpenOrdersSnapshot((), captured_at),
        captured_at=captured_at,
    )


def _spy_position() -> KisPaperPosition:
    return KisPaperPosition(
        symbol="SPY",
        exchange="AMEX",
        currency="USD",
        quantity=Decimal("1"),
        average_price=Decimal("500.25"),
        market_price=Decimal("500.50"),
        captured_at=NOW,
    )


def _write_submitted_state_for_canary(
    state_root: Path,
    outcome: FakeCanaryOutcome,
    *,
    raw_order_id: str,
) -> FakeCanaryOutcome:
    intent = KisPaperCanaryIntent(
        run_id=outcome.run_id,
        client_order_id=f"canary-{outcome.run_id}",
        decision_id=outcome.run_id,
        symbol="SPY",
        exchange="AMEX",
        quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
        created_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=5),
    )
    state = KisPaperCanaryState(
        intent=intent,
        phase="submitted",
        updated_at=NOW,
        reason_code="reconciliation_clean",
        broker_order_id=raw_order_id,
    )
    path = state_root / f"{outcome.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), sort_keys=True), encoding="utf-8")
    return outcome


def _open_order_payload(raw_order_id: str) -> dict[str, str]:
    return {
        "odno": raw_order_id,
        "pdno": "SPY",
        "ovrs_excg_cd": "AMEX",
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "1",
        "ft_ccld_qty": "0",
        "nccs_qty": "1",
        "ft_ord_unpr3": "500.00",
    }


def _paper_environment() -> dict[str, str]:
    return {
        "KIS_PAPER_APP_KEY": "paper-app-key",
        "KIS_PAPER_APP_SECRET": "paper-app-secret",
        "KIS_PAPER_ACCOUNT_NO": "12345678",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    return {
        "cache_root": tmp_path / "cache",
        "head_cache_root": tmp_path / "daily-head",
        "availability_root": tmp_path / "availability",
        "state_root": tmp_path / "private",
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency" / "state.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": repository_root,
        "execution_control_path": tmp_path / "emergency" / "control.json",
    }
