from __future__ import annotations

import ast
import inspect
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import thericher_v2.models.session_reset_ema_state_target as target_adapter
from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.session_reset_donchian import SessionResetDonchianRule
from thericher_v2.models.session_reset_donchian_target import (
    SessionResetDonchianTargetConfig,
    propose_session_reset_donchian_target,
)
from thericher_v2.models.session_reset_ema_state import (
    SessionResetEmaStateDecision,
    SessionResetEmaStateRule,
)
from thericher_v2.models.session_reset_ema_state_target import (
    SessionResetEmaStateTargetConfig,
    propose_session_reset_ema_state_target,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CONFIG = SessionResetEmaStateTargetConfig(
    symbol="QQQ",
    market="US",
    timeframe=Timeframe.M1,
    target_exposure=Decimal("0.20"),
    confidence=Decimal("0.60"),
    decision_ttl=timedelta(minutes=2),
)


def test_warmup_is_a_structural_missing_input_abstain() -> None:
    bars = _bars([Decimal("100")] * 2)

    proposal = _propose_bars(bars, model_position="flat")

    assert isinstance(proposal, TargetExposureProposal)
    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "missing",
        "ema_ema_warmup",
    )
    assert proposal.target_exposure == Decimal("0")
    assert proposal.confidence == Decimal("0")
    assert proposal.valid_until == proposal.decided_at


def test_missing_status_does_not_depend_on_a_reason_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = _bars([Decimal("100")] * 3)

    def missing_decision(
        _self: SessionResetEmaStateRule,
        _bars: tuple[Bar, ...],
        *,
        position: str,
        session: SessionWindow,
        as_of: datetime,
    ) -> SessionResetEmaStateDecision:
        assert session is _SESSION
        assert as_of == bars[-1].end_ts
        return SessionResetEmaStateDecision(
            action="hold",
            position_after=position,  # type: ignore[arg-type]
            input_status="missing",
            reason="unexpected_missing_shape",
            feature_window_end=bars[-1].end_ts,
        )

    monkeypatch.setattr(SessionResetEmaStateRule, "decide", missing_decision)

    proposal = _propose_bars(bars, model_position="flat")

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "missing",
        "ema_unexpected_missing_shape",
    )


def test_ready_status_does_not_depend_on_a_warmup_looking_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = _bars([Decimal("100")] * 3)

    def ready_decision(
        _self: SessionResetEmaStateRule,
        _bars: tuple[Bar, ...],
        *,
        position: str,
        session: SessionWindow,
        as_of: datetime,
    ) -> SessionResetEmaStateDecision:
        assert session is _SESSION
        assert as_of == bars[-1].end_ts
        return SessionResetEmaStateDecision(
            action="hold",
            position_after=position,  # type: ignore[arg-type]
            input_status="ready",
            reason="ema_warmup",
            feature_window_end=bars[-1].end_ts,
            fast_ema=Decimal("100"),
            slow_ema=Decimal("100"),
        )

    monkeypatch.setattr(SessionResetEmaStateRule, "decide", ready_decision)

    proposal = _propose_bars(bars, model_position="flat")

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "hold",
        "ready",
        "ema_ema_warmup",
    )
    assert proposal.target_exposure == Decimal("0")
    assert proposal.confidence == _CONFIG.confidence


def test_entry_exit_and_hold_preserve_explicit_target_geometry() -> None:
    entry = _propose([Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")], "flat")
    exit_proposal = _propose(
        [Decimal("100"), Decimal("100"), Decimal("100"), Decimal("70")],
        "long",
    )
    hold = _propose([Decimal("100")] * 4, "long")

    assert (entry.action, entry.target_exposure, entry.confidence) == (
        "enter",
        _CONFIG.target_exposure,
        _CONFIG.confidence,
    )
    assert (exit_proposal.action, exit_proposal.target_exposure) == ("exit", Decimal("0"))
    assert (hold.action, hold.target_exposure) == ("hold", _CONFIG.target_exposure)
    assert all(item.input_status == "ready" for item in (entry, exit_proposal, hold))


def test_ready_target_ttl_never_extends_past_session_close() -> None:
    bars = [_bar(index, close=Decimal("100")) for index in range(386, 389)]
    bars.append(_bar(389, close=Decimal("100")))

    proposal = _propose_bars(bars, model_position="long")

    assert proposal.valid_until == _SESSION.close_ts


def test_proposal_identity_is_price_free_and_contains_rule_seed_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")]
    original = _propose(bars, "flat")
    shifted = _propose([value + Decimal("1000") for value in bars], "flat")
    changed_period = _propose(
        bars,
        "flat",
        rule=SessionResetEmaStateRule(fast_period=2, slow_period=4, tolerance=Decimal("0")),
    )
    changed_tolerance = _propose(
        bars,
        "flat",
        rule=SessionResetEmaStateRule(fast_period=2, slow_period=3, tolerance=Decimal("0.01")),
    )
    monkeypatch.setattr(
        target_adapter,
        "SESSION_RESET_EMA_STATE_SEED_POLICY",
        "alternative_seed_policy_for_test",
    )
    changed_seed_policy = _propose(bars, "flat")

    assert original.proposal_id == shifted.proposal_id
    assert original.proposal_id != changed_period.proposal_id
    assert original.proposal_id != changed_tolerance.proposal_id
    assert original.proposal_id != changed_seed_policy.proposal_id
    assert original.proposal_id.startswith("session-reset-ema-state-target-v1:sha256:")


def test_ema_target_identity_cannot_collide_with_donchian_target_identity() -> None:
    bars = _bars([Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")])
    ema = _propose_bars(bars, model_position="flat")
    donchian = propose_session_reset_donchian_target(
        bars,
        session=_SESSION,
        as_of=bars[-1].end_ts,
        model_position="flat",
        rule=SessionResetDonchianRule(entry_lookback=2, exit_lookback=3),
        config=SessionResetDonchianTargetConfig(
            symbol="QQQ",
            market="US",
            timeframe=Timeframe.M1,
            target_exposure=Decimal("0.20"),
            confidence=Decimal("0.60"),
            decision_ttl=timedelta(minutes=2),
        ),
    )

    assert ema.feature_schema_id != donchian.feature_schema_id
    assert ema.proposal_id != donchian.proposal_id


def test_target_output_exposes_no_ema_price_or_order_fields() -> None:
    proposal = _propose([Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")], "flat")
    field_names = {field.name for field in fields(proposal)}

    assert not {"fast_ema", "slow_ema", "price", "open", "high", "low", "order"} & field_names


def test_adapter_rejects_invalid_identity_position_and_time_inputs() -> None:
    bars = _bars([Decimal("100")] * 4)

    with pytest.raises(ValueError, match="model_position"):
        _propose_bars(bars, model_position="short")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="rule"):
        propose_session_reset_ema_state_target(
            bars,
            session=_SESSION,
            as_of=bars[-1].end_ts,
            model_position="flat",
            rule=object(),  # type: ignore[arg-type]
            config=_CONFIG,
        )
    with pytest.raises(ValueError, match="as_of"):
        _propose_bars(bars, model_position="flat", as_of=bars[-1].end_ts.replace(tzinfo=None))
    with pytest.raises(ValueError, match="identity"):
        _propose_bars([replace(bar, symbol="SPY") for bar in bars], model_position="flat")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("symbol", "", "symbol"),
        ("market", " US", "market"),
        ("timeframe", "not-a-timeframe", "timeframe"),
        ("target_exposure", Decimal("0"), "target_exposure"),
        ("confidence", Decimal("0"), "confidence"),
        ("decision_ttl", timedelta(0), "decision_ttl"),
    ],
)
def test_config_rejects_invalid_explicit_target_geometry(
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
        SessionResetEmaStateTargetConfig(**kwargs)  # type: ignore[arg-type]


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
    closes: list[Decimal],
    model_position: str,
    *,
    rule: SessionResetEmaStateRule | None = None,
) -> TargetExposureProposal:
    return _propose_bars(
        _bars(closes),
        model_position=model_position,
        rule=rule or SessionResetEmaStateRule(fast_period=2, slow_period=3, tolerance=Decimal("0")),
    )


def _propose_bars(
    bars: list[Bar],
    *,
    model_position: str,
    rule: SessionResetEmaStateRule | None = None,
    as_of: datetime | None = None,
) -> TargetExposureProposal:
    cutoff = as_of if as_of is not None else (bars[-1].end_ts if bars else _SESSION.open_ts)
    return propose_session_reset_ema_state_target(
        bars,
        session=_SESSION,
        as_of=cutoff,
        model_position=model_position,  # type: ignore[arg-type]
        rule=rule or SessionResetEmaStateRule(fast_period=2, slow_period=3, tolerance=Decimal("0")),
        config=_CONFIG,
    )


def _bars(closes: list[Decimal]) -> list[Bar]:
    return [_bar(index, close=close) for index, close in enumerate(closes)]


def _bar(minute_offset: int, *, close: Decimal) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + timedelta(minutes=minute_offset),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=Decimal("1"),
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
