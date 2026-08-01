from __future__ import annotations

import ast
import inspect
import os
import socket
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models import prospective_spy_intraday_baseline as baseline
from thericher_v2.models.prospective_spy_intraday_session import (
    ProspectiveSpyIntradaySessionInputError,
    ProspectiveSpyIntradaySessionRecord,
    build_prospective_spy_intraday_session_record,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CUTOFF = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_SOURCE_CONTRACT_HASH = "sha256:" + "1" * 64


def test_all_positive_timeframes_enter_with_the_fixed_research_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    record = _record()

    assert {
        timeframe: len(window.bars)
        for timeframe, window in record.sequence_window.windows.items()
    } == {
        Timeframe.M1: 30,
        Timeframe.M5: 6,
        Timeframe.M10: 3,
        Timeframe.H1: 2,
        Timeframe.H3: 2,
    }
    assert all(
        window.bars[-1].close > window.bars[0].close
        for window in record.sequence_window.windows.values()
    )

    evaluation = baseline.evaluate_prospective_spy_intraday_baseline(record)

    assert isinstance(evaluation.proposal, TargetExposureProposal)
    assert (evaluation.proposal.action, evaluation.proposal.input_status) == ("enter", "ready")
    assert evaluation.proposal.target_exposure == Decimal("0.02")
    assert evaluation.proposal.reason == "unanimous_trailing_return_enter"
    assert (
        evaluation.proposal.valid_until - evaluation.proposal.decided_at
        == baseline.PROSPECTIVE_SPY_INTRADAY_BASELINE_DECISION_TTL
    )
    assert evaluation.safe_metadata["round_trip_cost_bps"] == "10"
    assert evaluation.safe_metadata["naive_comparator"] == "always_flat"
    assert evaluation.safe_metadata["decision"] == "enter_long"
    _assert_no_ohlcv_keys(evaluation.safe_metadata)


def test_one_nonpositive_timeframe_abstains_without_a_trade_semantic() -> None:
    record = _record(m10_nonpositive=True)
    m10 = record.sequence_window.windows[Timeframe.M10]

    assert m10.bars[-1].close < m10.bars[0].close

    evaluation = baseline.evaluate_prospective_spy_intraday_baseline(record)

    assert (evaluation.proposal.action, evaluation.proposal.target_exposure) == (
        "abstain",
        Decimal("0"),
    )
    assert evaluation.proposal.reason == "trailing_return_not_unanimous_abstain"
    assert evaluation.safe_metadata["decision"] == "abstain_no_trade"


def test_proposal_identity_is_price_free_but_distinguishes_categorical_action() -> None:
    record = _record()
    changed_prices = _record(price_offset=Decimal("100"))
    first = baseline.evaluate_prospective_spy_intraday_baseline(record)
    second = baseline.evaluate_prospective_spy_intraday_baseline(changed_prices)
    validated = baseline._validate_record(record)

    assert record.contract_hash == changed_prices.contract_hash
    assert first.proposal.proposal_id == second.proposal.proposal_id
    assert baseline._proposal_id(validated, enters_long=False) != baseline._proposal_id(
        validated,
        enters_long=True,
    )


def test_data_builder_prevents_future_bars_from_reaching_the_baseline() -> None:
    future_bar = _bar(start=_CUTOFF, close=Decimal("200"))

    with pytest.raises(ProspectiveSpyIntradaySessionInputError, match="future"):
        build_prospective_spy_intraday_session_record(
            (*_source_bars(), future_bar),
            session=_SESSION,
            cutoff=_CUTOFF,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )


def test_data_builder_enforces_spy_identity_and_frozen_sequence_shape() -> None:
    with pytest.raises(ProspectiveSpyIntradaySessionInputError, match="SPY"):
        build_prospective_spy_intraday_session_record(
            _source_bars(symbol="QQQ"),
            session=_SESSION,
            cutoff=_CUTOFF,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )
    with pytest.raises(ProspectiveSpyIntradaySessionInputError, match="missing"):
        build_prospective_spy_intraday_session_record(
            _source_bars()[:-1],
            session=_SESSION,
            cutoff=_CUTOFF,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        )


def test_baseline_requires_the_actual_data_record_type() -> None:
    with pytest.raises(TypeError, match="ProspectiveSpyIntradaySessionRecord"):
        baseline.evaluate_prospective_spy_intraday_baseline(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="SPY/US"):
        baseline.evaluate_prospective_spy_intraday_baseline(_record(market="NYSE_ARCA"))


def test_baseline_rejects_a_safe_payload_that_names_ohlcv_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    original_safe_payload = ProspectiveSpyIntradaySessionRecord.safe_payload

    def unsafe_payload(self: ProspectiveSpyIntradaySessionRecord) -> dict[str, object]:
        payload = original_safe_payload(self)
        payload["close"] = "not_allowed"
        return payload

    monkeypatch.setattr(ProspectiveSpyIntradaySessionRecord, "safe_payload", unsafe_payload)

    with pytest.raises(ValueError, match="OHLCV"):
        baseline.evaluate_prospective_spy_intraday_baseline(record)


def test_module_has_no_io_or_execution_dependencies() -> None:
    tree = ast.parse(inspect.getsource(baseline))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0
    )

    assert not any(
        module == blocked or module.startswith(f"{blocked}.")
        for module in imported_modules
        for blocked in (
            "os",
            "pathlib",
            "socket",
            "subprocess",
            "urllib",
            "requests",
            "http",
            "thericher_v2.execution",
            "thericher_v2.providers",
        )
    )


def test_module_has_no_historical_source_reference_or_claim() -> None:
    assert "mim" not in inspect.getsource(baseline).lower()


def _record(
    *,
    market: str = "US",
    m10_nonpositive: bool = False,
    price_offset: Decimal = Decimal("0"),
) -> ProspectiveSpyIntradaySessionRecord:
    return build_prospective_spy_intraday_session_record(
        _source_bars(
            market=market,
            m10_nonpositive=m10_nonpositive,
            price_offset=price_offset,
        ),
        session=_SESSION,
        cutoff=_CUTOFF,
        source_contract_hash=_SOURCE_CONTRACT_HASH,
    )


def _source_bars(
    *,
    symbol: str = "SPY",
    market: str = "US",
    m10_nonpositive: bool = False,
    price_offset: Decimal = Decimal("0"),
) -> tuple[Bar, ...]:
    bars: list[Bar] = []
    for index in range(360):
        close = Decimal("100") + price_offset + Decimal(index) / Decimal("100")
        if m10_nonpositive and index >= 350:
            close = Decimal("90") + price_offset + Decimal(index - 350) / Decimal("100")
        bars.append(
            _bar(
                symbol=symbol,
                market=market,
                start=_SESSION.open_ts + Timeframe.M1.duration * index,
                close=close,
            )
        )
    return tuple(bars)


def _bar(
    *,
    start: datetime,
    close: Decimal,
    symbol: str = "SPY",
    market: str = "US",
) -> Bar:
    return Bar(
        symbol=symbol,
        market=market,
        timeframe=Timeframe.M1,
        start_ts=start,
        open=close - Decimal("0.01"),
        high=close + Decimal("0.01"),
        low=close - Decimal("0.02"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _assert_no_ohlcv_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            assert key.lower() not in {"open", "high", "low", "close", "volume", "ohlcv", "price"}
            _assert_no_ohlcv_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_no_ohlcv_keys(nested)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective baseline must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
