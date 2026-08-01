from __future__ import annotations

import ast
import inspect
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.models import current_source_opportunity_eligibility as eligibility_module
from thericher_v2.models.current_source_opportunity_eligibility import (
    CurrentSourceContract,
    CurrentSourceMetadata,
    CurrentSourceOpportunityEligibility,
    adapt_current_source_opportunity_eligibility,
    build_causal_bar_source_contract,
)
from thericher_v2.models.target_position_policy import OpportunityEligibility

_NOW = datetime(2026, 8, 2, 15, 0, tzinfo=UTC)
_CONTRACT = CurrentSourceContract(
    contract_id="current-source-qqq-us-v1",
    contract_hash="sha256:" + "a" * 64,
)


def test_compatible_current_source_preserves_an_upstream_eligible_candidate() -> None:
    result = adapt_current_source_opportunity_eligibility(
        _candidate(),
        _source(),
        expected_contract=_CONTRACT,
        as_of=_NOW,
    )

    assert result.eligible is True
    assert result.input_status == "ready"
    assert result.reason == "source_compatible"
    assert result.eligibility.opportunity_ref == _candidate().opportunity_ref
    assert result.eligibility.symbol == "QQQ"
    assert result.eligibility.market == "US"
    assert result.eligibility.observed_at == _NOW - timedelta(minutes=1)
    assert result.eligibility.valid_until == _NOW + timedelta(minutes=1)


@pytest.mark.parametrize(
    ("source_factory", "status", "reason"),
    (
        (
            lambda: _source(valid_until=_NOW - timedelta(seconds=1)),
            "stale",
            "source_stale",
        ),
        (
            lambda: _source(symbol="SPY"),
            "misaligned",
            "source_symbol_market_mismatch",
        ),
        (
            lambda: _source(complete=False),
            "incomplete",
            "source_incomplete",
        ),
        (
            lambda: _source(
                contract=CurrentSourceContract(
                    "current-source-qqq-us-v1",
                    "sha256:" + "b" * 64,
                )
            ),
            "misaligned",
            "source_contract_mismatch",
        ),
    ),
)
def test_stale_mismatched_or_incomplete_source_metadata_downgrades_candidate(
    source_factory: object,
    status: str,
    reason: str,
) -> None:
    assert callable(source_factory)
    source = source_factory()
    assert isinstance(source, CurrentSourceMetadata)
    result = adapt_current_source_opportunity_eligibility(
        _candidate(),
        source,
        expected_contract=_CONTRACT,
        as_of=_NOW,
    )

    assert (result.eligible, result.input_status, result.reason) == (False, status, reason)
    assert result.eligibility.observed_at == _NOW
    assert result.eligibility.valid_until == _NOW


def test_adapter_cannot_mint_true_eligibility_and_rejects_a_forged_projection() -> None:
    upstream = _candidate(eligible=False)
    result = adapt_current_source_opportunity_eligibility(
        upstream,
        _source(),
        expected_contract=_CONTRACT,
        as_of=_NOW,
    )
    forged_true = replace(result.eligibility, eligible=True)

    assert (result.eligible, result.input_status, result.reason) == (
        False,
        "ready",
        "upstream_ineligible",
    )
    with pytest.raises(ValueError, match="deterministic monotone projection"):
        CurrentSourceOpportunityEligibility(
            upstream_candidate=upstream,
            source=_source(),
            expected_contract=_CONTRACT,
            as_of=_NOW,
            eligibility=forged_true,
            reason="source_compatible",
        )


def test_adapter_output_is_deterministic_for_identical_facts() -> None:
    first = adapt_current_source_opportunity_eligibility(
        _candidate(),
        _source(),
        expected_contract=_CONTRACT,
        as_of=_NOW,
    )
    second = adapt_current_source_opportunity_eligibility(
        _candidate(),
        _source(),
        expected_contract=_CONTRACT,
        as_of=_NOW,
    )

    assert first == second
    assert first.eligibility == second.eligibility


def test_causal_bar_contract_ignores_future_bars_but_not_observed_prefix() -> None:
    as_of = _NOW
    observed = _bar(start_ts=_NOW - timedelta(minutes=2), close=Decimal("101"))
    future = _bar(start_ts=_NOW, close=Decimal("102"))

    baseline = build_causal_bar_source_contract(
        (observed, future),
        contract_id="causal-qqq-us-v1",
        as_of=as_of,
    )
    future_changed = build_causal_bar_source_contract(
        (observed, _bar(start_ts=future.start_ts, close=Decimal("202"))),
        contract_id="causal-qqq-us-v1",
        as_of=as_of,
    )
    observed_changed = build_causal_bar_source_contract(
        (_bar(start_ts=observed.start_ts, close=Decimal("201")), future),
        contract_id="causal-qqq-us-v1",
        as_of=as_of,
    )

    assert future_changed == baseline
    assert observed_changed != baseline


def test_contract_is_pure_without_data_universe_network_broker_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("current-source eligibility must not access external state")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    result = adapt_current_source_opportunity_eligibility(
        _candidate(),
        _source(),
        expected_contract=_CONTRACT,
        as_of=_NOW,
    )

    assert result.eligible is True
    tree = ast.parse(inspect.getsource(eligibility_module))
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
    source = inspect.getsource(eligibility_module).lower()
    for forbidden_name in (
        "source_scoped_liquid_universe",
        "norgate",
        "tiingo",
        "orderintent",
        "requests",
        "urllib",
        "socket",
        "getenv",
        ".env",
    ):
        assert forbidden_name not in source


def _candidate(*, eligible: bool = True) -> OpportunityEligibility:
    return OpportunityEligibility(
        opportunity_ref="ref:" + "1" * 64,
        symbol="QQQ",
        market="US",
        eligible=eligible,
        input_status="ready",
        observed_at=_NOW - timedelta(minutes=2),
        valid_until=_NOW + timedelta(minutes=2),
    )


def _source(
    *,
    contract: CurrentSourceContract = _CONTRACT,
    symbol: str = "QQQ",
    market: str = "US",
    complete: bool = True,
    valid_until: datetime = _NOW + timedelta(minutes=1),
) -> CurrentSourceMetadata:
    return CurrentSourceMetadata(
        contract=contract,
        symbol=symbol,
        market=market,
        input_status="ready",
        complete=complete,
        observed_at=_NOW - timedelta(minutes=1),
        valid_until=valid_until,
    )


def _bar(*, start_ts: datetime, close: Decimal) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=Decimal("100"),
        high=max(Decimal("100"), close),
        low=min(Decimal("100"), close),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )
