from __future__ import annotations

import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
)
from thericher_v2.models.target_exposure_cycle_allocator import (
    TargetExposureAllocationCycleEntry,
    allocate_target_exposure_cycle,
)

_NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_cycle_preserves_caller_order_and_consumes_shared_capacity_serially() -> None:
    result = allocate_target_exposure_cycle(
        (
            _entry("QQQ", target_exposure="0.50"),
            _entry("SPY", target_exposure="0.50"),
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert [(item.symbol, item.action, item.target_exposure) for item in result] == [
        ("QQQ", "enter", Decimal("0.30")),
        ("SPY", "hold", Decimal("0")),
    ]
    assert result[1].reason == "allocation_capacity_exhausted"


def test_cycle_does_not_release_capacity_for_an_unexecuted_exit() -> None:
    result = allocate_target_exposure_cycle(
        (
            _entry(
                "QQQ",
                action="exit",
                target_exposure="0",
                current_symbol_exposure="0.30",
                current_portfolio_exposure="0.80",
                available_portfolio_capacity="0",
                portfolio_exposure_cap="0.80",
            ),
            _entry(
                "SPY",
                target_exposure="0.20",
                current_portfolio_exposure="0.80",
                available_portfolio_capacity="0",
                portfolio_exposure_cap="0.80",
            ),
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert [(item.symbol, item.action, item.target_exposure) for item in result] == [
        ("QQQ", "exit", Decimal("0")),
        ("SPY", "hold", Decimal("0")),
    ]
    assert result[1].reason == "allocation_capacity_exhausted"


def test_cycle_does_not_consume_capacity_for_a_caller_hold_proposal() -> None:
    result = allocate_target_exposure_cycle(
        (
            _entry("QQQ", action="hold", target_exposure="0.50"),
            _entry("SPY", target_exposure="0.50"),
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert [(item.symbol, item.action, item.target_exposure) for item in result] == [
        ("QQQ", "hold", Decimal("0.50")),
        ("SPY", "enter", Decimal("0.30")),
    ]


def test_cycle_rejects_duplicate_symbol_or_inconsistent_portfolio_snapshot() -> None:
    with pytest.raises(ValueError, match="unique market/symbol"):
        allocate_target_exposure_cycle(
            (_entry("QQQ"), _entry("QQQ", proposal_id="second-qqq")),
            config=_config(),
            as_of=_NOW,
        )

    with pytest.raises(ValueError, match="share one portfolio snapshot"):
        allocate_target_exposure_cycle(
            (
                _entry("QQQ"),
                _entry("SPY", current_portfolio_exposure="0.41"),
            ),
            config=_config(),
            as_of=_NOW,
        )


def test_stale_or_unqualified_entries_abstain_without_consuming_shared_capacity() -> None:
    stale = _entry(
        "QQQ",
        decided_at=_NOW - timedelta(minutes=2),
        valid_until=_NOW - timedelta(seconds=1),
    )
    ready = _entry("SPY", target_exposure="0.50")
    stale_then_ready = allocate_target_exposure_cycle(
        (stale, ready),
        config=_config(),
        as_of=_NOW,
    )
    unqualified = allocate_target_exposure_cycle(
        (_entry("IWM", input_status="unqualified"),),
        config=_config(),
        as_of=_NOW,
    )

    assert (stale_then_ready[0].action, stale_then_ready[0].reason) == (
        "abstain",
        "proposal_stale",
    )
    assert (stale_then_ready[1].action, stale_then_ready[1].target_exposure) == (
        "enter",
        Decimal("0.30"),
    )
    assert (unqualified[0].action, unqualified[0].reason) == (
        "abstain",
        "allocation_unqualified",
    )


def test_cycle_allocator_is_pure_and_needs_no_external_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)

    result = allocate_target_exposure_cycle(
        (_entry("QQQ"), _entry("SPY")),
        config=_config(),
        as_of=_NOW,
    )

    assert len(result) == 2


def _entry(
    symbol: str,
    *,
    proposal_id: str | None = None,
    action: str = "enter",
    target_exposure: str = "0.50",
    current_symbol_exposure: str = "0",
    current_portfolio_exposure: str = "0.40",
    available_portfolio_capacity: str = "0.30",
    portfolio_exposure_cap: str = "0.70",
    input_status: str = "ready",
    decided_at: datetime = _NOW,
    valid_until: datetime | None = None,
) -> TargetExposureAllocationCycleEntry:
    proposal = TargetExposureProposal(
        proposal_id=proposal_id or f"source-{symbol.lower()}-proposal-v1",
        symbol=symbol,
        market="US",
        action=action,
        target_exposure=Decimal(target_exposure),
        confidence=Decimal("0.80"),
        feature_schema_id="target-policy-features-v1",
        input_status="ready",
        decided_at=decided_at,
        valid_until=valid_until or decided_at + timedelta(minutes=2),
        feature_window_end=decided_at - timedelta(minutes=1),
        reason="source_target",
    )
    allocation = TargetExposureAllocationInput(
        current_symbol_exposure=Decimal(current_symbol_exposure),
        current_portfolio_exposure=Decimal(current_portfolio_exposure),
        available_portfolio_capacity=Decimal(available_portfolio_capacity),
        portfolio_exposure_cap=Decimal(portfolio_exposure_cap),
        per_symbol_exposure_cap=Decimal("0.50"),
        confidence_multiplier=Decimal("1"),
        risk_multiplier=Decimal("1"),
        input_status=input_status,
        observed_at=_NOW - timedelta(seconds=1),
        valid_until=_NOW + timedelta(minutes=1),
    )
    return TargetExposureAllocationCycleEntry(proposal=proposal, allocation=allocation)


def _config() -> TargetExposureAllocationConfig:
    return TargetExposureAllocationConfig(allocator_id="target-exposure-allocation-v1")


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("same-cycle target allocation must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
