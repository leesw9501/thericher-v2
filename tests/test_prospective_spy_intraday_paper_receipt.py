from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.prospective_spy_intraday_observation import (
    observe_prospective_spy_intraday_baseline,
)
from thericher_v2.models.prospective_spy_intraday_session import (
    build_prospective_spy_intraday_session_record,
)
from thericher_v2.research.prospective_spy_intraday_paper_receipt import (
    prospective_spy_intraday_input_manifest_ref,
    research_receipt_from_prospective_spy_intraday_observation,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CUTOFF = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_SOURCE_CONTRACT_HASH = "sha256:" + "a" * 64


def test_enter_observation_becomes_a_current_paper_research_receipt() -> None:
    observation = observe_prospective_spy_intraday_baseline(_record())

    receipt = research_receipt_from_prospective_spy_intraday_observation(observation.receipt)

    assert receipt.decision_class == "enter"
    assert receipt.reason_class == "eligible_enter"
    assert receipt.input_status == "ready"
    assert receipt.decided_at == observation.receipt.decided_at
    assert receipt.valid_until == observation.receipt.valid_until
    assert receipt.input_manifest_ref == prospective_spy_intraday_input_manifest_ref(
        observation.receipt
    )


def test_changed_observation_content_cannot_reuse_a_paper_decision_identity() -> None:
    first = observe_prospective_spy_intraday_baseline(_record()).receipt
    bars = list(_source_bars())
    bars[-1] = replace(
        bars[-1],
        open=bars[-1].open + Decimal("0.001"),
        high=bars[-1].high + Decimal("0.001"),
        low=bars[-1].low + Decimal("0.001"),
        close=bars[-1].close + Decimal("0.001"),
    )
    changed = observe_prospective_spy_intraday_baseline(_record(tuple(bars))).receipt

    first_paper = research_receipt_from_prospective_spy_intraday_observation(first)
    changed_paper = research_receipt_from_prospective_spy_intraday_observation(changed)

    assert first.decision_class == changed.decision_class == "enter"
    assert first_paper.input_manifest_ref != changed_paper.input_manifest_ref
    assert first_paper.proposal_ref != changed_paper.proposal_ref
    assert first_paper.decision_id != changed_paper.decision_id


def test_abstaining_observation_remains_an_abstaining_paper_receipt() -> None:
    observation = observe_prospective_spy_intraday_baseline(_record(upward=False))

    receipt = research_receipt_from_prospective_spy_intraday_observation(observation.receipt)

    assert observation.receipt.decision_class == "abstain"
    assert receipt.decision_class == "abstain"
    assert receipt.reason_class == "model_abstain"


def _record(
    bars: tuple[Bar, ...] | None = None,
    *,
    upward: bool = True,
):
    return build_prospective_spy_intraday_session_record(
        _source_bars(upward=upward) if bars is None else bars,
        session=_SESSION,
        cutoff=_CUTOFF,
        source_contract_hash=_SOURCE_CONTRACT_HASH,
    )


def _source_bars(*, upward: bool = True) -> tuple[Bar, ...]:
    count = (_CUTOFF - _SESSION.open_ts) // Timeframe.M1.duration
    return tuple(_bar_at(index, upward=upward) for index in range(count))


def _bar_at(index: int, *, upward: bool) -> Bar:
    movement = Decimal(index) / Decimal("1000")
    open_value = Decimal("111.111") + movement if upward else Decimal("222.222") - movement
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + Timeframe.M1.duration * index,
        open=open_value,
        high=open_value + Decimal("1"),
        low=open_value - Decimal("0.5"),
        close=open_value + Decimal("0.2"),
        volume=Decimal("7777"),
        complete=True,
    )
