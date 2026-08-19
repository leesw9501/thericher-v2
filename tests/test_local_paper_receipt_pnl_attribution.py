from __future__ import annotations

import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.execution import (
    EmergencyStore,
    LocalPaperBroker,
    LocalPaperDecisionPnl,
    replay_local_paper_decision_pnl,
)
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    prepare_local_paper_intent,
    receipt_attribution_ref,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.local_paper_receipt_pnl_attribution import (
    attribute_local_paper_decision_pnl_to_receipts,
)
from thericher_v2.state import EventStore

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_local_paper_pnl_segments_retain_exact_receipt_lineage(tmp_path: Path) -> None:
    entry, exit, accounting = _closed_pair_accounting(tmp_path)

    attribution = attribute_local_paper_decision_pnl_to_receipts(
        accounting,
        (entry, exit),
    )

    assert attribution.accounting is accounting
    assert len(attribution.closed_segments) == 1
    segment = attribution.closed_segments[0]
    assert segment.accounting == accounting.closed_segments[0]
    assert segment.entry_receipt.decision_id == entry.decision_id
    assert segment.exit_receipt.decision_id == exit.decision_id
    assert segment.entry_receipt.receipt_ref == receipt_attribution_ref(entry)
    assert segment.exit_receipt.receipt_ref == receipt_attribution_ref(exit)
    assert segment.entry_receipt.campaign_ref == entry.campaign_ref
    assert segment.exit_receipt.model_ref == exit.model_ref
    assert segment.entry_receipt.input_manifest_ref == entry.input_manifest_ref
    assert segment.exit_receipt.proposal_ref == exit.proposal_ref
    assert segment.accounting.realized_after_cost_pnl == (
        accounting.aggregate.realized_after_cost_pnl
    )


def test_one_exit_receipt_retains_every_fifo_entry_lineage(tmp_path: Path) -> None:
    entry_a = _distinct_receipt(
        action="enter",
        target_exposure=Decimal("0.25"),
        decided_at=NOW,
        marker="1",
    )
    entry_b = _distinct_receipt(
        action="enter",
        target_exposure=Decimal("0.50"),
        decided_at=NOW + timedelta(minutes=1),
        marker="2",
    )
    exit_receipt = _distinct_receipt(
        action="exit",
        target_exposure=Decimal("0"),
        decided_at=NOW + timedelta(minutes=2),
        marker="3",
    )
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    prepared_entry_a = prepare_local_paper_intent(
        entry_a,
        binding=_binding(
            entry_a,
            target_exposure=Decimal("0.25"),
            current_quantity=Decimal("0"),
        ),
        as_of=NOW,
    )
    prepared_entry_b = prepare_local_paper_intent(
        entry_b,
        binding=_binding(
            entry_b,
            target_exposure=Decimal("0.50"),
            current_quantity=Decimal("2"),
        ),
        as_of=NOW + timedelta(minutes=1),
    )
    prepared_exit = prepare_local_paper_intent(
        exit_receipt,
        binding=_binding(
            exit_receipt,
            target_exposure=Decimal("0"),
            current_quantity=Decimal("4"),
        ),
        as_of=NOW + timedelta(minutes=2),
    )
    assert prepared_entry_a.local_paper_intent is not None
    assert prepared_entry_b.local_paper_intent is not None
    assert prepared_exit.local_paper_intent is not None
    broker.submit_and_fill_next_bar(
        prepared_entry_a.local_paper_intent,
        signal_bar=_bar(NOW - timedelta(minutes=1)),
        execution_bar=_bar(NOW),
    )
    broker.submit_and_fill_next_bar(
        prepared_entry_b.local_paper_intent,
        signal_bar=_bar(NOW),
        execution_bar=_bar(NOW + timedelta(minutes=1)),
    )
    broker.submit_and_fill_next_bar(
        prepared_exit.local_paper_intent,
        signal_bar=_bar(NOW + timedelta(minutes=1)),
        execution_bar=_bar(NOW + timedelta(minutes=2)),
    )

    accounting = replay_local_paper_decision_pnl(tuple(store.iter_events()))
    attribution = attribute_local_paper_decision_pnl_to_receipts(
        accounting,
        (exit_receipt, entry_b, entry_a),
    )

    assert [
        (
            segment.entry_receipt.decision_id,
            segment.exit_receipt.decision_id,
            segment.accounting.quantity,
        )
        for segment in attribution.closed_segments
    ] == [
        (entry_a.decision_id, exit_receipt.decision_id, Decimal("2")),
        (entry_b.decision_id, exit_receipt.decision_id, Decimal("2")),
    ]
    assert {
        segment.exit_receipt.receipt_ref for segment in attribution.closed_segments
    } == {receipt_attribution_ref(exit_receipt)}
    assert sum(
        (segment.accounting.realized_after_cost_pnl for segment in attribution.closed_segments),
        Decimal("0"),
    ) == accounting.aggregate.realized_after_cost_pnl


def test_missing_or_duplicate_receipts_fail_closed(tmp_path: Path) -> None:
    entry, exit, accounting = _closed_pair_accounting(tmp_path)

    with pytest.raises(ValueError, match="exit decision receipt is missing"):
        attribute_local_paper_decision_pnl_to_receipts(accounting, (entry,))
    with pytest.raises(ValueError, match="duplicate decision receipt identity"):
        attribute_local_paper_decision_pnl_to_receipts(accounting, (entry, entry, exit))


def test_role_inverted_accounting_segment_fails_closed(tmp_path: Path) -> None:
    entry, exit, accounting = _closed_pair_accounting(tmp_path)
    segment = accounting.closed_segments[0]
    inverted = replace(
        segment,
        entry_decision_id=exit.decision_id,
        exit_decision_id=entry.decision_id,
    )
    malformed = replace(
        accounting,
        closed_segments=(inverted,),
        entry_decision_totals=(
            replace(accounting.entry_decision_totals[0], decision_id=exit.decision_id),
        ),
        exit_decision_totals=(
            replace(accounting.exit_decision_totals[0], decision_id=entry.decision_id),
        ),
        decision_pair_totals=(
            replace(
                accounting.decision_pair_totals[0],
                entry_decision_id=exit.decision_id,
                exit_decision_id=entry.decision_id,
            ),
        ),
    )

    with pytest.raises(ValueError, match="entry decision receipt is not execution-eligible"):
        attribute_local_paper_decision_pnl_to_receipts(malformed, (entry, exit))


def test_receipt_for_another_instrument_cannot_claim_local_paper_pnl(tmp_path: Path) -> None:
    _, exit_receipt, accounting = _closed_pair_accounting(tmp_path)
    foreign_entry = _distinct_receipt(
        action="enter",
        target_exposure=Decimal("0.5"),
        decided_at=NOW,
        marker="4",
        symbol="SPY",
    )
    segment = accounting.closed_segments[0]
    malformed = replace(
        accounting,
        closed_segments=(replace(segment, entry_decision_id=foreign_entry.decision_id),),
        entry_decision_totals=(
            replace(accounting.entry_decision_totals[0], decision_id=foreign_entry.decision_id),
        ),
        decision_pair_totals=(
            replace(
                accounting.decision_pair_totals[0],
                entry_decision_id=foreign_entry.decision_id,
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="entry decision receipt does not match local-paper instrument",
    ):
        attribute_local_paper_decision_pnl_to_receipts(
            malformed,
            (foreign_entry, exit_receipt),
        )


def test_internally_inconsistent_pnl_projection_fails_closed(tmp_path: Path) -> None:
    _, _, accounting = _closed_pair_accounting(tmp_path)

    with pytest.raises(
        ValueError,
        match="local-paper decision PnL does not reconcile closed segments",
    ):
        replace(
            accounting,
            aggregate=replace(
                accounting.aggregate,
                realized_after_cost_pnl=accounting.aggregate.realized_after_cost_pnl
                + Decimal("1"),
            ),
        )


def test_impossible_local_fill_count_fails_closed(tmp_path: Path) -> None:
    _, _, accounting = _closed_pair_accounting(tmp_path)

    with pytest.raises(ValueError, match="local-paper decision PnL fill count cannot close"):
        replace(
            accounting,
            aggregate=replace(accounting.aggregate, local_paper_fill_count=1),
        )


def test_receipt_pnl_attribution_is_offline_and_does_not_read_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry, exit, accounting = _closed_pair_accounting(tmp_path)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("receipt PnL attribution must not access external state")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("receipt PnL attribution must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    attribution = attribute_local_paper_decision_pnl_to_receipts(accounting, (entry, exit))

    assert attribution.closed_segments[0].entry_receipt.receipt_ref.startswith("sha256:")


def _closed_pair_accounting(
    tmp_path: Path,
) -> tuple[ResearchDecisionReceipt, ResearchDecisionReceipt, LocalPaperDecisionPnl]:
    entry = _receipt(action="enter")
    exit = _receipt(action="exit")
    entry_prepared = prepare_local_paper_intent(
        entry,
        binding=_binding(
            entry,
            target_exposure=Decimal("0.5"),
            current_quantity=Decimal("0"),
        ),
        as_of=NOW,
    )
    exit_prepared = prepare_local_paper_intent(
        exit,
        binding=_binding(
            exit,
            target_exposure=Decimal("0"),
            current_quantity=Decimal("4"),
        ),
        as_of=NOW + timedelta(minutes=1),
    )
    assert entry_prepared.local_paper_intent is not None
    assert exit_prepared.local_paper_intent is not None

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    broker.submit_and_fill_next_bar(
        entry_prepared.local_paper_intent,
        signal_bar=_bar(NOW - timedelta(minutes=1)),
        execution_bar=_bar(NOW),
    )
    broker.submit_and_fill_next_bar(
        exit_prepared.local_paper_intent,
        signal_bar=_bar(NOW),
        execution_bar=_bar(NOW + timedelta(minutes=1)),
    )
    return entry, exit, replay_local_paper_decision_pnl(tuple(store.iter_events()))


def _receipt(*, action: Literal["enter", "exit"]) -> ResearchDecisionReceipt:
    target_exposure = Decimal("0.5") if action == "enter" else Decimal("0")
    proposal = TargetExposureProposal(
        proposal_id="source-proposal-not-exported",
        symbol="QQQ",
        market="US",
        action=action,
        target_exposure=target_exposure,
        confidence=Decimal("0.55"),
        feature_schema_id="receipt-pnl-attribution-test-v1",
        input_status="ready",
        decided_at=NOW if action == "enter" else NOW + timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=2),
        feature_window_end=NOW,
        reason="not-exported-to-receipt",
    )
    return receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_ref("a" if action == "enter" else "e"),
            model_ref=_ref("b" if action == "enter" else "f"),
            input_manifest_ref=f"sha256:{('c' if action == 'enter' else 'a') * 64}",
            proposal_ref=_ref("d" if action == "enter" else "b"),
        ),
    )


def _distinct_receipt(
    *,
    action: Literal["enter", "exit"],
    target_exposure: Decimal,
    decided_at: datetime,
    marker: str,
    symbol: str = "QQQ",
) -> ResearchDecisionReceipt:
    proposal = TargetExposureProposal(
        proposal_id=f"source-proposal-{marker}-not-exported",
        symbol=symbol,
        market="US",
        action=action,
        target_exposure=target_exposure,
        confidence=Decimal("0.55"),
        feature_schema_id="receipt-pnl-attribution-test-v1",
        input_status="ready",
        decided_at=decided_at,
        valid_until=decided_at + timedelta(minutes=2),
        feature_window_end=decided_at,
        reason="not-exported-to-receipt",
    )
    return receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_ref(marker),
            model_ref=_ref("a" if marker != "a" else "b"),
            input_manifest_ref=f"sha256:{marker * 64}",
            proposal_ref=_ref("b" if marker != "b" else "c"),
        ),
    )


def _binding(
    receipt: ResearchDecisionReceipt,
    *,
    target_exposure: Decimal,
    current_quantity: Decimal,
) -> LocalPaperTargetBinding:
    return LocalPaperTargetBinding(
        proposal_ref=receipt.proposal_ref,
        symbol="QQQ",
        target_exposure=target_exposure,
        current_quantity=current_quantity,
        maximum_quantity=Decimal("8"),
    )


def _bar(start: datetime) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start,
        open=Decimal("101"),
        high=Decimal("102"),
        low=Decimal("100"),
        close=Decimal("101.50"),
        volume=Decimal("1000"),
        complete=True,
    )


def _ref(value: str) -> str:
    return f"ref:{value * 32}"
