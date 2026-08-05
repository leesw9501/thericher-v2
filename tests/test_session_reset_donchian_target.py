from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import thericher_v2.models.session_reset_donchian_target as target_adapter
from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.session_reset_donchian import SessionResetDonchianRule
from thericher_v2.models.session_reset_donchian_target import (
    SessionResetDonchianTargetConfig,
    propose_session_reset_donchian_target,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CONFIG = SessionResetDonchianTargetConfig(
    symbol="QQQ",
    market="US",
    timeframe=Timeframe.M1,
    target_exposure=Decimal("0.20"),
    confidence=Decimal("0.60"),
    decision_ttl=timedelta(minutes=2),
)


def test_entry_maps_to_the_configured_long_target() -> None:
    bars = _baseline_bars(20)
    bars.append(_bar(20, close=Decimal("102"), high=Decimal("102")))

    proposal = _propose(bars, model_position="flat")

    assert isinstance(proposal, TargetExposureProposal)
    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "enter",
        "ready",
        "donchian_entry_breakout",
    )
    assert proposal.target_exposure == _CONFIG.target_exposure
    assert proposal.confidence == _CONFIG.confidence
    assert proposal.valid_until - proposal.decided_at == _CONFIG.decision_ttl
    assert proposal.feature_window_end == bars[-1].end_ts


def test_exit_maps_to_zero_target() -> None:
    bars = _baseline_bars(10)
    bars.append(_bar(10, close=Decimal("98"), low=Decimal("98")))

    proposal = _propose(bars, model_position="long")

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "exit",
        "ready",
        "donchian_exit_breakdown",
    )
    assert proposal.target_exposure == Decimal("0")
    assert proposal.confidence == _CONFIG.confidence
    assert proposal.valid_until - proposal.decided_at == _CONFIG.decision_ttl


@pytest.mark.parametrize(
    ("model_position", "expected_target", "reason"),
    [
        ("flat", Decimal("0"), "donchian_inside_entry_channel"),
        ("long", _CONFIG.target_exposure, "donchian_inside_exit_channel"),
    ],
)
def test_valid_hold_preserves_the_caller_declared_model_position(
    model_position: str,
    expected_target: Decimal,
    reason: str,
) -> None:
    bars = _baseline_bars(21 if model_position == "flat" else 11)

    proposal = _propose(bars, model_position=model_position)

    assert (proposal.action, proposal.input_status, proposal.reason) == ("hold", "ready", reason)
    assert proposal.target_exposure == expected_target
    assert proposal.confidence == _CONFIG.confidence
    assert proposal.valid_until - proposal.decided_at == _CONFIG.decision_ttl


def test_insufficient_valid_history_is_missing_input_abstain() -> None:
    bars = _baseline_bars(20)

    proposal = _propose(bars, model_position="flat")

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "missing",
        "donchian_insufficient_entry_history",
    )
    assert proposal.target_exposure == Decimal("0")
    assert proposal.confidence == Decimal("0")
    assert proposal.valid_until == proposal.decided_at
    assert proposal.feature_window_end == bars[-1].end_ts


def test_empty_history_is_a_scoped_missing_input_abstain() -> None:
    proposal = _propose([], model_position="flat", as_of=_SESSION.open_ts)

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "missing",
        "donchian_insufficient_history",
    )
    assert proposal.feature_window_end is None


def test_future_bars_do_not_change_an_earlier_target_proposal() -> None:
    bars = _baseline_bars(20)
    bars.append(_bar(20, close=Decimal("102"), high=Decimal("102")))
    as_of = bars[-1].end_ts
    future = _bar(21, close=Decimal("250"), high=Decimal("250"))

    original = _propose(bars, model_position="flat", as_of=as_of)
    with_future = _propose([*bars, future], model_position="flat", as_of=as_of)

    assert with_future == original


def test_proposal_identity_is_deterministic_and_price_free() -> None:
    bars = _baseline_bars(20)
    bars.append(_bar(20, close=Decimal("102"), high=Decimal("102")))
    shifted = [_offset_prices(bar, Decimal("1000")) for bar in bars]

    first = _propose(bars, model_position="flat")
    second = _propose(bars, model_position="flat")
    changed_prices = _propose(shifted, model_position="flat")

    assert first.proposal_id == second.proposal_id == changed_prices.proposal_id
    assert first.proposal_id.startswith("session-reset-donchian-target-v1:sha256:")
    assert len(first.proposal_id.rsplit(":", maxsplit=1)[-1]) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("symbol", "", "symbol"),
        ("market", " US", "market"),
        ("timeframe", "not-a-timeframe", "timeframe"),
        ("target_exposure", Decimal("0"), "target_exposure"),
        ("target_exposure", Decimal("1.01"), "target_exposure"),
        ("confidence", Decimal("0"), "confidence"),
        ("confidence", Decimal("-0.01"), "confidence"),
        ("confidence", Decimal("1.01"), "confidence"),
        ("decision_ttl", timedelta(0), "decision_ttl"),
    ],
)
def test_config_rejects_invalid_explicit_target_state_geometry(
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs: dict[str, object] = {
        "symbol": "QQQ",
        "market": "US",
        "timeframe": Timeframe.M1,
        "target_exposure": Decimal("0.20"),
        "confidence": Decimal("0.60"),
        "decision_ttl": timedelta(minutes=2),
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        SessionResetDonchianTargetConfig(**kwargs)  # type: ignore[arg-type]


def test_config_requires_an_explicit_caller_declared_confidence() -> None:
    with pytest.raises(TypeError, match="confidence"):
        SessionResetDonchianTargetConfig(
            symbol="QQQ",
            market="US",
            timeframe=Timeframe.M1,
            target_exposure=Decimal("0.20"),
            decision_ttl=timedelta(minutes=2),
        )  # type: ignore[call-arg]


def test_adapter_rejects_invalid_position_rule_identity_and_time_inputs() -> None:
    bars = _baseline_bars(21)

    with pytest.raises(ValueError, match="model_position"):
        _propose(bars, model_position="short")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="rule"):
        propose_session_reset_donchian_target(
            bars,
            session=_SESSION,
            as_of=bars[-1].end_ts,
            model_position="flat",
            rule=object(),  # type: ignore[arg-type]
            config=_CONFIG,
        )
    with pytest.raises(ValueError, match="as_of"):
        _propose(bars, model_position="flat", as_of=bars[-1].end_ts.replace(tzinfo=None))
    with pytest.raises(ValueError, match="identity"):
        _propose([replace(bar, symbol="SPY") for bar in bars], model_position="flat")
    with pytest.raises(ValueError, match="complete"):
        _propose([replace(bars[0], complete=False), *bars[1:]], model_position="flat")


def test_module_has_no_kis_broker_network_or_credential_route() -> None:
    source = inspect.getsource(target_adapter)
    imports = _imported_modules(source)

    blocked_prefixes = (
        "dotenv",
        "http",
        "os",
        "pathlib",
        "requests",
        "socket",
        "subprocess",
        "thericher_v2.data.kis",
        "thericher_v2.execution",
        "thericher_v2.providers",
        "urllib",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imports
        for prefix in blocked_prefixes
    )
    assert "OrderIntent" not in source
    assert "KIS" not in source
    assert "credential" not in source.lower()


def _propose(
    bars: list[Bar],
    *,
    model_position: str,
    as_of: datetime | None = None,
) -> TargetExposureProposal:
    cutoff = as_of if as_of is not None else (bars[-1].end_ts if bars else _SESSION.open_ts)
    return propose_session_reset_donchian_target(
        bars,
        session=_SESSION,
        as_of=cutoff,
        model_position=model_position,  # type: ignore[arg-type]
        rule=SessionResetDonchianRule(),
        config=_CONFIG,
    )


def _baseline_bars(count: int) -> list[Bar]:
    return [_bar(index) for index in range(count)]


def _bar(
    minute_offset: int,
    *,
    close: Decimal = Decimal("100"),
    high: Decimal = Decimal("101"),
    low: Decimal = Decimal("99"),
) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + timedelta(minutes=minute_offset),
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
    )


def _offset_prices(bar: Bar, offset: Decimal) -> Bar:
    return replace(
        bar,
        open=bar.open + offset,
        high=bar.high + offset,
        low=bar.low + offset,
        close=bar.close + offset,
    )


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports
