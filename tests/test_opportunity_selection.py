from __future__ import annotations

import ast
import inspect
import os
import socket
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.models import opportunity_selection as selection_module
from thericher_v2.models.current_source_opportunity_eligibility import (
    CurrentSourceContract,
    CurrentSourceMetadata,
    adapt_current_source_opportunity_eligibility,
)
from thericher_v2.models.opportunity_selection import (
    OpportunitySelectionConfig,
    OpportunitySelectionContext,
    OpportunitySelectionEntry,
    OpportunitySelectionInputError,
    select_source_attested_opportunities,
)
from thericher_v2.models.target_position_policy import OpportunityEligibility

_NOW = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)


def test_selection_is_top_k_stable_across_caller_order_and_retains_all_outcomes() -> None:
    entries = (
        _entry("SPY", "0.90"),
        _entry("QQQ", "0.90"),
        _entry("IWM", "0.80"),
        _entry("DIA", "0.40"),
        _entry("XLK", "0.99", upstream_eligible=False),
    )

    first = select_source_attested_opportunities(
        entries,
        config=_config(maximum_selected=2),
        context=_context(),
    )
    second = select_source_attested_opportunities(
        tuple(reversed(entries)),
        config=_config(maximum_selected=2),
        context=_context(),
    )

    expected = (
        ("DIA", False, None, "score_below_threshold"),
        ("IWM", False, None, "selection_capacity_exhausted"),
        ("QQQ", True, 1, "selected"),
        ("SPY", True, 2, "selected"),
        ("XLK", False, None, "source_upstream_ineligible"),
    )
    assert _summary(first) == expected
    assert _summary(second) == expected


@pytest.mark.parametrize(
    ("entries_factory", "reason"),
    (
        (
            lambda: (_entry("QQQ", "0.90", score_valid_until=_NOW - timedelta(seconds=1)),),
            "score_stale",
        ),
        (lambda: (_entry("QQQ", "0.90", source_status="unqualified"),), "source_unqualified"),
        (
            lambda: (_entry("QQQ", "0.90", source_semantics_id="other-semantics-v1"),),
            "context_misaligned",
        ),
        (
            lambda: (_entry("QQQ", "0.90", snapshot_id="other-snapshot-v1"),),
            "context_misaligned",
        ),
        (
            lambda: (_entry("QQQ", "0.90", availability_grade="other-grade-v1"),),
            "context_misaligned",
        ),
        (
            lambda: (_entry("QQQ", "0.90", score_schema_id="other-score-v1"),),
            "score_schema_misaligned",
        ),
        (lambda: (_entry("QQQ", "0.90"), _entry("QQQ", "0.80")), "duplicate_identity"),
    ),
)
def test_stale_unqualified_mixed_or_duplicate_input_rejects_the_whole_cycle(
    entries_factory: Callable[[], tuple[OpportunitySelectionEntry, ...]],
    reason: str,
) -> None:
    with pytest.raises(OpportunitySelectionInputError, match=reason):
        select_source_attested_opportunities(
            entries_factory(),
            config=_config(maximum_selected=2),
            context=_context(),
        )


def test_selection_rejects_scores_that_are_not_observable_at_the_shared_snapshot() -> None:
    with pytest.raises(OpportunitySelectionInputError, match="score_future"):
        select_source_attested_opportunities(
            (_entry("QQQ", "0.90", score_observed_at=_NOW + timedelta(seconds=1)),),
            config=_config(maximum_selected=1),
            context=_context(),
        )


def test_selection_is_pure_without_data_network_broker_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("opportunity selection must not access external state")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    outcomes = select_source_attested_opportunities(
        (_entry("QQQ", "0.90"),),
        config=_config(maximum_selected=1),
        context=_context(),
    )

    assert _summary(outcomes) == (("QQQ", True, 1, "selected"),)
    tree = ast.parse(inspect.getsource(selection_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        module.startswith(("thericher_v2.data", "thericher_v2.execution"))
        for module in imported
    )


def _summary(
    outcomes: tuple[object, ...],
) -> tuple[tuple[str, bool, int | None, str], ...]:
    return tuple(
        (
            outcome.entry.source_eligibility.eligibility.symbol,
            outcome.selected,
            outcome.selection_rank,
            outcome.reason,
        )
        for outcome in outcomes
        if hasattr(outcome, "entry")
    )


def _config(*, maximum_selected: int) -> OpportunitySelectionConfig:
    return OpportunitySelectionConfig(
        selector_id="cross-sectional-selection-test-v1",
        score_schema_id="cross-sectional-score-v1",
        maximum_selected=maximum_selected,
        minimum_score=Decimal("0.50"),
    )


def _context() -> OpportunitySelectionContext:
    return OpportunitySelectionContext(
        snapshot_id="selection-snapshot-test-v1",
        as_of=_NOW,
        source_semantics_id="completed-bar-source-v1",
        availability_grade="causal-current-v1",
    )


def _entry(
    symbol: str,
    score: str,
    *,
    upstream_eligible: bool = True,
    source_status: str = "ready",
    score_schema_id: str = "cross-sectional-score-v1",
    snapshot_id: str = "selection-snapshot-test-v1",
    source_semantics_id: str = "completed-bar-source-v1",
    availability_grade: str = "causal-current-v1",
    score_observed_at: datetime = _NOW - timedelta(seconds=1),
    score_valid_until: datetime = _NOW + timedelta(minutes=1),
) -> OpportunitySelectionEntry:
    contract = CurrentSourceContract(
        contract_id=f"source-{symbol.lower()}-v1",
        contract_hash="sha256:" + symbol.lower().encode().hex().ljust(64, "0"),
    )
    candidate = OpportunityEligibility(
        opportunity_ref="ref:" + symbol.lower().encode().hex().ljust(64, "0"),
        symbol=symbol,
        market="US",
        eligible=upstream_eligible,
        input_status="ready",
        observed_at=_NOW - timedelta(minutes=1),
        valid_until=_NOW + timedelta(minutes=2),
    )
    source = CurrentSourceMetadata(
        contract=contract,
        symbol=symbol,
        market="US",
        input_status=source_status,
        complete=True,
        observed_at=_NOW - timedelta(seconds=30),
        valid_until=_NOW + timedelta(minutes=1),
    )
    return OpportunitySelectionEntry(
        source_eligibility=adapt_current_source_opportunity_eligibility(
            candidate,
            source,
            expected_contract=contract,
            as_of=_NOW,
        ),
        selection_ref="ref:" + (symbol.lower().encode().hex() + "f" * 64)[:64],
        selection_score=Decimal(score),
        score_schema_id=score_schema_id,
        snapshot_id=snapshot_id,
        source_semantics_id=source_semantics_id,
        availability_grade=availability_grade,
        score_observed_at=score_observed_at,
        score_valid_until=score_valid_until,
    )
