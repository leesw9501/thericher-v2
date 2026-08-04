from __future__ import annotations

import inspect
import socket
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_spy_input
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.kis_paper_daily_spy_input import attest_kis_paper_daily_spy_input
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution import EmergencyStore, LocalPaperBroker
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    prepare_local_paper_intent,
)
from thericher_v2.research.kis_paper_daily_spy_baseline import (
    evaluate_kis_paper_daily_spy_baseline,
)
from thericher_v2.state import EventStore

_FIRST_AVAILABLE_AT = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)


def test_same_session_close_stays_unavailable_until_after_local_availability(
    tmp_path: Path,
) -> None:
    input = _input(tmp_path)

    before = evaluate_kis_paper_daily_spy_baseline(
        input,
        as_of=_FIRST_AVAILABLE_AT - timedelta(microseconds=1),
    )
    exact = evaluate_kis_paper_daily_spy_baseline(input, as_of=_FIRST_AVAILABLE_AT)
    eligible = evaluate_kis_paper_daily_spy_baseline(
        input,
        as_of=_FIRST_AVAILABLE_AT + timedelta(microseconds=1),
    )

    assert before.receipt.decision_class == "abstain"
    assert exact.receipt.decision_class == "abstain"
    assert before.receipt.input_status == "future"
    assert exact.receipt.input_status == "future"
    assert eligible.receipt.decision_class == "enter"
    assert eligible.receipt.input_status == "ready"
    assert eligible.proposal.decided_at == _FIRST_AVAILABLE_AT
    assert eligible.receipt.input_manifest_ref == input.input_manifest_ref


def test_daily_input_availability_is_stable_and_safe_after_first_attestation(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)
    first = attest_kis_paper_daily_spy_input(
        catalog,
        availability_root=tmp_path / "availability",
        repository_root=tmp_path / "repo",
        attested_at=_FIRST_AVAILABLE_AT,
    )
    second = attest_kis_paper_daily_spy_input(
        catalog,
        availability_root=tmp_path / "availability",
        repository_root=tmp_path / "repo",
        attested_at=_FIRST_AVAILABLE_AT + timedelta(hours=1),
    )

    assert first.first_available_at == second.first_available_at == _FIRST_AVAILABLE_AT
    assert first.input_manifest_ref == second.input_manifest_ref
    assert first.availability_record_path == second.availability_record_path
    payload = first.safe_payload()
    assert payload["source_timestamp_semantics"] == "session_label_only"
    assert payload["completed_bar_rule"] == "decision_at_strictly_after_first_available_at"
    serialized = str(payload)
    for forbidden in ("100", "101", str(first.availability_record_path)):
        assert forbidden not in serialized


def test_concurrent_first_attestation_reuses_one_availability_instant(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    barrier = threading.Barrier(2)

    def attest(attested_at: datetime):
        barrier.wait(timeout=5)
        return attest_kis_paper_daily_spy_input(
            catalog,
            availability_root=tmp_path / "availability",
            repository_root=repo_root,
            attested_at=attested_at,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = tuple(
            executor.map(
                attest,
                (_FIRST_AVAILABLE_AT, _FIRST_AVAILABLE_AT + timedelta(hours=1)),
            )
        )

    assert first.first_available_at == second.first_available_at
    assert first.first_available_at in {
        _FIRST_AVAILABLE_AT,
        _FIRST_AVAILABLE_AT + timedelta(hours=1),
    }
    assert first.availability_record_path == second.availability_record_path


def test_ready_daily_receipt_replays_through_local_paper_with_exact_identity(
    tmp_path: Path,
) -> None:
    input = _input(tmp_path)
    evaluation = evaluate_kis_paper_daily_spy_baseline(
        input,
        as_of=_FIRST_AVAILABLE_AT + timedelta(microseconds=1),
    )
    prepared = prepare_local_paper_intent(
        evaluation.receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=evaluation.receipt.proposal_ref,
            symbol="SPY",
            target_exposure=evaluation.proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("20"),
        ),
        as_of=_FIRST_AVAILABLE_AT + timedelta(minutes=1),
    )
    assert prepared.status == "ready"
    assert prepared.local_paper_intent is not None

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    fill = broker.submit_and_fill_next_bar(
        prepared.local_paper_intent,
        signal_bar=input.bars[-1],
        execution_bar=_bar(date(2026, 7, 22), Decimal("102")),
    ).fill

    assert fill is not None
    assert fill.source == "local_paper"
    accepted = next(
        event for event in store.iter_events() if event.event_type == "local_paper_order_accepted"
    )
    assert accepted.payload["decision_id"] == evaluation.receipt.decision_id


def test_expired_daily_execution_window_is_a_scoped_abstain(tmp_path: Path) -> None:
    input = _input(tmp_path)
    result = evaluate_kis_paper_daily_spy_baseline(
        input,
        as_of=datetime(2026, 7, 22, 20, 1, tzinfo=UTC),
    )

    assert result.receipt.decision_class == "abstain"
    assert result.receipt.input_status == "stale"
    assert result.receipt.reason_class == "input_unavailable"


def test_downward_two_close_baseline_emits_an_explicit_exit_receipt(tmp_path: Path) -> None:
    input = _input(
        tmp_path,
        closes=(Decimal("101"), Decimal("100")),
    )

    result = evaluate_kis_paper_daily_spy_baseline(
        input,
        as_of=_FIRST_AVAILABLE_AT + timedelta(minutes=1),
    )

    assert result.proposal.action == "exit"
    assert result.receipt.decision_class == "exit"
    assert result.receipt.reason_class == "eligible_exit"


def test_attestation_is_offline_and_rejects_a_git_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("daily input attestation must remain offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    catalog = _catalog(tmp_path)
    with pytest.raises(ValueError, match="outside Git"):
        attest_kis_paper_daily_spy_input(
            catalog,
            availability_root=repo_root / "artifacts",
            repository_root=repo_root,
            attested_at=_FIRST_AVAILABLE_AT,
        )
    source = inspect.getsource(kis_paper_daily_spy_input).lower()
    for forbidden in ("urllib", "socket", "getenv", "kis_live", ".env"):
        assert forbidden not in source


def _input(
    tmp_path: Path,
    *,
    closes: tuple[Decimal, Decimal] = (Decimal("100"), Decimal("101")),
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(exist_ok=True)
    return attest_kis_paper_daily_spy_input(
        _catalog(tmp_path, closes=closes),
        availability_root=tmp_path / "availability",
        repository_root=repo_root,
        attested_at=_FIRST_AVAILABLE_AT,
    )


def _catalog(
    tmp_path: Path,
    *,
    closes: tuple[Decimal, Decimal] = (Decimal("100"), Decimal("101")),
) -> KisPaperPrivateDailyCatalog:
    sessions = (date(2026, 7, 20), date(2026, 7, 21))
    bars = (_bar(sessions[0], closes[0]), _bar(sessions[1], closes[1]))
    dataset_hash = "sha256:" + "a" * 64
    stream = _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        dataset_hash=dataset_hash,
        source_path=tmp_path / "index.json",
        bars=bars,
    )
    return KisPaperPrivateDailyCatalog(
        dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "b" * 64,
        index_path=tmp_path / "index.json",
        source_root=tmp_path,
        adjustment_mode="MODP=0_unadjusted",
        bars_by_symbol=MappingProxyType({"SPY": stream}),
        common_sessions=sessions,
        raw_price_limitations=("MODP=0_unadjusted",),
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
