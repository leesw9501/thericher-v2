from __future__ import annotations

import inspect
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_capability import (
    KisCapabilityQualification,
    KisCapabilityState,
    KisMarketDataCapability,
    KisStorageRightsStatus,
    observed_kis_paper_capabilities,
)
from thericher_v2.execution import (
    EmergencyStore,
    LocalPaperBroker,
    collect_fill_source_evidence,
    replay_local_paper_account,
    target_proposal_to_order_intent,
)
from thericher_v2.execution.fill_source import FillEventArtifact
from thericher_v2.research import kis_paper_baseline
from thericher_v2.research.kis_paper_baseline import (
    KIS_PAPER_BASELINE_SCHEMA_ID,
    KisPaperBaselineAuthorization,
    KisPaperBaselineInput,
    evaluate_kis_paper_baseline,
)
from thericher_v2.state import EventStore


def test_fixed_baseline_builds_exact_90_1m_input_and_local_resamples(monkeypatch) -> None:
    bars = _bars(92)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)

    result = evaluate_kis_paper_baseline(
        bars[:90],
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[89].end_ts,
    )

    assert result.baseline_input is not None
    assert len(result.baseline_input.m1_bars) == 90
    assert len(result.baseline_input.m5_bars) == 18
    assert len(result.baseline_input.m10_bars) == 9
    assert result.proposal.action == "enter"
    assert result.proposal.target_exposure == Decimal("0.05")
    assert result.proposal.feature_schema_id == KIS_PAPER_BASELINE_SCHEMA_ID
    assert result.proposal.input_status == "ready"
    assert result.proposal.valid_until == bars[89].end_ts + timedelta(minutes=10)
    assert result.capability_authorization == "qualified"

    source = inspect.getsource(kis_paper_baseline)
    assert "orderintent" not in source.lower()


def test_baseline_records_immutable_as_of_separately_from_feature_window(monkeypatch) -> None:
    bars = _bars(92)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    feature_window_end = bars[89].end_ts
    as_of = feature_window_end + timedelta(minutes=1)

    result = evaluate_kis_paper_baseline(
        bars[:90],
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=as_of,
    )

    assert result.baseline_input is not None
    assert result.proposal.input_status == "ready"
    assert result.proposal.decided_at == as_of
    assert result.proposal.feature_window_end == feature_window_end
    assert result.proposal.valid_until == feature_window_end + timedelta(minutes=10)
    assert feature_window_end.strftime("%Y%m%dT%H%M%SZ") in result.proposal.proposal_id
    assert ":ready:" in result.proposal.proposal_id

    retry = evaluate_kis_paper_baseline(
        bars[:90],
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=as_of + timedelta(microseconds=1),
    )
    revised_bars = [*bars[:90]]
    revised_bars[-1] = replace(
        revised_bars[-1],
        close=revised_bars[-1].close + Decimal("0.001"),
        high=revised_bars[-1].high + Decimal("0.001"),
    )
    revised = evaluate_kis_paper_baseline(
        revised_bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=as_of,
    )

    assert retry.proposal.decided_at == as_of + timedelta(microseconds=1)
    assert retry.proposal.proposal_id == result.proposal.proposal_id
    assert revised.proposal.proposal_id != result.proposal.proposal_id


def test_baseline_expires_at_the_next_ten_minute_boundary_even_with_relaxed_age(
    monkeypatch,
) -> None:
    bars = _bars(92)
    capability = replace(
        _qualified_capability(),
        freshness_budget=timedelta(minutes=20),
    )
    _trust_for_test(monkeypatch, capability)
    as_of = bars[89].end_ts + timedelta(minutes=10)

    result = evaluate_kis_paper_baseline(
        bars[:90],
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=as_of,
        max_age=timedelta(minutes=20),
    )

    assert result.baseline_input is None
    assert result.proposal.action == "abstain"
    assert result.proposal.input_status == "stale"
    assert result.proposal.reason == "baseline_input_expired"
    assert result.proposal.decided_at == as_of
    assert result.proposal.feature_window_end == bars[89].end_ts


def test_bar_window_fingerprint_is_decimal_context_independent() -> None:
    bar = _bars(1)[0]
    first = replace(bar, volume=Decimal("1.00000000000000000000000000001"))
    second = replace(bar, volume=Decimal("1.00000000000000000000000000002"))
    signed_zero = replace(bar, volume=Decimal("-0"))
    unsigned_zero = replace(bar, volume=Decimal("0.00"))

    with localcontext() as context:
        context.prec = 6
        low_precision_first = kis_paper_baseline._bar_window_fingerprint((first,))
        low_precision_second = kis_paper_baseline._bar_window_fingerprint((second,))
        low_precision_zero = kis_paper_baseline._bar_window_fingerprint((signed_zero,))

    with localcontext() as context:
        context.prec = 80
        high_precision_first = kis_paper_baseline._bar_window_fingerprint((first,))
        high_precision_second = kis_paper_baseline._bar_window_fingerprint((second,))
        high_precision_zero = kis_paper_baseline._bar_window_fingerprint((unsigned_zero,))

    assert low_precision_first == high_precision_first
    assert low_precision_second == high_precision_second
    assert low_precision_first != low_precision_second
    assert low_precision_zero == high_precision_zero


def test_baseline_abstains_for_unusable_input(monkeypatch) -> None:
    complete = _bars(90)
    gapped = _bars(91)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    cases = (
        (_bars(89), _bars(89)[-1].end_ts, "missing"),
        (complete, complete[-1].end_ts + timedelta(minutes=3), "stale"),
        (gapped[:40] + gapped[41:], gapped[-1].end_ts, "non_contiguous"),
        (
            [*complete[:15], replace(complete[15], complete=False), *complete[16:]],
            complete[-1].end_ts,
            "incomplete",
        ),
        ([*complete, complete[12]], complete[-1].end_ts, "duplicate"),
    )

    for bars, as_of, expected_status in cases:
        result = evaluate_kis_paper_baseline(
            bars,
            capability=capability,
            symbol="QQQ",
            market="US",
            as_of=as_of,
        )

        assert result.baseline_input is None
        assert result.proposal.action == "abstain"
        assert result.proposal.target_exposure == 0
        assert result.proposal.input_status == expected_status


def test_baseline_abstains_until_a_matching_capability_has_a_trusted_binding() -> None:
    bars = _bars(90)
    observed_raw_minute = next(
        capability
        for capability in observed_kis_paper_capabilities()
        if capability.capability_id == "kis.paper.us.raw-1m.2026-07-19"
    )
    direct_qualified = _qualified_capability()

    observed_result = evaluate_kis_paper_baseline(
        bars,
        capability=observed_raw_minute,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )
    mismatched_result = evaluate_kis_paper_baseline(
        bars,
        capability=_qualified_capability(symbol_scope=("IWM",)),
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )
    direct_result = evaluate_kis_paper_baseline(
        bars,
        capability=direct_qualified,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )

    for result in (observed_result, mismatched_result, direct_result):
        assert result.baseline_input is None
        assert result.proposal.action == "abstain"
        assert result.proposal.input_status == "unqualified"
        assert result.proposal.reason == "baseline_input_capability_unqualified"

    assert (
        target_proposal_to_order_intent(
            direct_result.proposal,
            client_order_id="untrusted-qualified-capability",
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("20"),
        )
        is None
    )


def test_provisional_observed_capability_requires_an_explicit_hash_bound_authorization() -> None:
    bars = _bars(90)
    capability = _observed_provisional_capability()

    without_authorization = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )
    result = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
        provisional_authorization=_provisional_authorization(capability),
    )

    assert capability.state == KisCapabilityState.OBSERVED
    assert without_authorization.baseline_input is None
    assert without_authorization.proposal.action == "abstain"
    assert without_authorization.capability_authorization == "unqualified"
    assert result.baseline_input is not None
    assert result.proposal.action == "enter"
    assert result.capability_authorization == "provisional"


def test_provisional_authorization_fails_closed_for_invalid_or_mismatched_capabilities() -> None:
    bars = _bars(90)
    capability = _observed_provisional_capability()
    missing_freshness = replace(capability, freshness_budget=None)
    changed_capability = replace(capability, paging_facts="unit changed continuation")
    invalid_evidence_capability = replace(capability, evidence_reference="unit-evidence")

    cases = (
        (missing_freshness, _provisional_authorization(missing_freshness)),
        (changed_capability, _provisional_authorization(capability)),
        (invalid_evidence_capability, _provisional_authorization(capability)),
    )
    for candidate, authorization in cases:
        result = evaluate_kis_paper_baseline(
            bars,
            capability=candidate,
            symbol="QQQ",
            market="US",
            as_of=bars[-1].end_ts,
            provisional_authorization=authorization,
        )

        assert result.baseline_input is None
        assert result.proposal.action == "abstain"
        assert result.proposal.input_status == "unqualified"
        assert result.capability_authorization == "unqualified"

    with pytest.raises(ValueError, match="evidence_reference"):
        KisPaperBaselineAuthorization(
            capability_id=capability.capability_id,
            capability_contract_sha256=capability.contract_sha256,
            evidence_reference="not-a-sha256-reference",
        )
    with pytest.raises(ValueError, match="scope"):
        KisPaperBaselineAuthorization(
            capability_id=capability.capability_id,
            capability_contract_sha256=capability.contract_sha256,
            evidence_reference=capability.evidence_reference,
            scope_id="another-paper-experiment",
        )


def test_static_observed_capability_cannot_bypass_its_missing_freshness_budget() -> None:
    bars = _bars(90)
    static_observed = next(
        capability
        for capability in observed_kis_paper_capabilities()
        if capability.capability_id == "kis.paper.us.raw-1m.2026-07-19"
    )
    hash_attested_without_freshness = replace(
        static_observed,
        evidence_reference="sha256:" + "d" * 64,
    )

    result = evaluate_kis_paper_baseline(
        bars,
        capability=hash_attested_without_freshness,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
        provisional_authorization=_provisional_authorization(hash_attested_without_freshness),
    )

    assert result.baseline_input is None
    assert result.proposal.action == "abstain"
    assert result.capability_authorization == "unqualified"


@pytest.mark.parametrize(
    ("trend_sign", "momentum_sign", "expected_action", "expected_exposure"),
    (
        (1, 1, "enter", Decimal("0.05")),
        (1, 0, "hold", Decimal("0.05")),
        (1, -1, "reduce", Decimal("0.025")),
        (0, 1, "hold", Decimal("0.05")),
        (0, 0, "abstain", Decimal("0")),
        (0, -1, "reduce", Decimal("0.025")),
        (-1, 1, "reduce", Decimal("0.025")),
        (-1, 0, "exit", Decimal("0")),
        (-1, -1, "exit", Decimal("0")),
    ),
)
def test_fixed_trend_and_momentum_table_emits_all_target_actions(
    monkeypatch: pytest.MonkeyPatch,
    trend_sign: int,
    momentum_sign: int,
    expected_action: str,
    expected_exposure: Decimal,
) -> None:
    bars = _bars_with_trend_and_momentum_signs(trend_sign, momentum_sign)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)

    result = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )

    assert result.baseline_input is not None
    assert result.capability_authorization == "qualified"
    assert result.proposal.input_status == "ready"
    assert result.proposal.action == expected_action
    assert result.proposal.target_exposure == expected_exposure


def test_nasdaq_baseline_abstains_for_a_non_us_market_stream(monkeypatch) -> None:
    bars = [replace(bar, market="KR") for bar in _bars(90)]
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)

    result = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="KR",
        as_of=bars[-1].end_ts,
    )

    assert result.baseline_input is None
    assert result.proposal.action == "abstain"
    assert result.proposal.input_status == "unqualified"
    assert result.proposal.market == "KR"


def test_baseline_stays_pinned_to_qqq_even_when_a_capability_scope_is_broader(monkeypatch) -> None:
    bars = [replace(bar, symbol="SPY") for bar in _bars(90)]
    capability = _qualified_capability(symbol_scope=("QQQ", "SPY"))
    _trust_for_test(monkeypatch, capability)

    result = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="SPY",
        market="US",
        as_of=bars[-1].end_ts,
    )

    assert result.baseline_input is None
    assert result.proposal.action == "abstain"
    assert result.proposal.input_status == "unqualified"


def test_baseline_rejects_a_qualified_capability_from_another_endpoint_category(
    monkeypatch,
) -> None:
    bars = _bars(90)
    capability = _qualified_capability(endpoint_category="overseas_stock_daily")
    _trust_for_test(monkeypatch, capability)

    result = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )

    assert result.baseline_input is None
    assert result.proposal.action == "abstain"
    assert result.proposal.input_status == "unqualified"


def test_baseline_input_rejects_incomplete_direct_construction(monkeypatch) -> None:
    bars = _bars(90)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    baseline_input = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    ).baseline_input
    assert baseline_input is not None

    with pytest.raises(ValueError, match="complete"):
        KisPaperBaselineInput(
            m1_bars=(
                replace(baseline_input.m1_bars[0], complete=False),
                *baseline_input.m1_bars[1:],
            ),
            m5_bars=baseline_input.m5_bars,
            m10_bars=baseline_input.m10_bars,
            feature_window_end=baseline_input.feature_window_end,
        )

    with pytest.raises(ValueError, match="match local raw resampling"):
        KisPaperBaselineInput(
            m1_bars=baseline_input.m1_bars,
            m5_bars=(
                replace(baseline_input.m5_bars[0], volume=Decimal("999999")),
                *baseline_input.m5_bars[1:],
            ),
            m10_bars=baseline_input.m10_bars,
            feature_window_end=baseline_input.feature_window_end,
        )


def test_execution_maps_ready_target_to_replayable_local_paper_fill(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bars = _bars(92)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    proposal = evaluate_kis_paper_baseline(
        bars[:90],
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[89].end_ts,
    ).proposal
    order = target_proposal_to_order_intent(
        proposal,
        client_order_id="kis-paper-baseline-local-1",
        current_quantity=Decimal("0"),
        maximum_quantity=Decimal("20"),
    )

    assert order is not None
    assert order.side == "buy"
    assert order.quantity == Decimal("1.00")
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    execution = broker.submit_and_fill_next_bar(
        order,
        signal_bar=bars[89],
        execution_bar=bars[90],
    )

    assert execution.fill is not None
    evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=tmp_path / "events.jsonl",
                expected_fill_count=1,
                label="baseline",
            ),
        )
    )
    assert evidence.all_fills_local_paper
    assert replay_local_paper_account(store).quantity(market="US", symbol="QQQ") == Decimal("1.00")


def test_baseline_and_local_replay_are_network_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bars = _bars(92)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("baseline and local paper must stay offline")

    original_open = Path.open

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.lower().startswith(".env"):
            raise AssertionError("baseline and local paper must not read credentials")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "open", guard_open)

    proposal = evaluate_kis_paper_baseline(
        bars[:90],
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[89].end_ts,
    ).proposal
    order = target_proposal_to_order_intent(
        proposal,
        client_order_id="offline-local-paper",
        current_quantity=0,
        maximum_quantity=20,
    )
    assert order is not None
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    assert broker.submit_and_fill_next_bar(order, signal_bar=bars[89], execution_bar=bars[90]).fill


def test_baseline_abstains_for_a_binding_of_a_changed_capability(monkeypatch) -> None:
    bars = _bars(90)
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    changed_capability = replace(capability, paging_facts="unit changed continuation")

    result = evaluate_kis_paper_baseline(
        bars,
        capability=changed_capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )

    assert result.baseline_input is None
    assert result.proposal.action == "abstain"
    assert result.proposal.input_status == "unqualified"
    assert result.proposal.reason == "baseline_input_capability_unqualified"


def _bars(count: int) -> list[Bar]:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result: list[Bar] = []
    for index in range(count):
        open_price = Decimal("100") + Decimal(index) / Decimal("100")
        close = open_price + Decimal("0.01")
        result.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start + timedelta(minutes=index),
                open=open_price,
                high=close + Decimal("0.01"),
                low=open_price - Decimal("0.01"),
                close=close,
                volume=Decimal("1000") + Decimal(index),
                complete=True,
            )
        )
    return result


def _bars_with_trend_and_momentum_signs(
    trend_sign: int,
    momentum_sign: int,
) -> list[Bar]:
    bars = _bars(90)
    latest_close = Decimal("100")
    reference_close = {
        1: Decimal("99"),
        0: latest_close,
        -1: Decimal("101"),
    }
    if trend_sign not in reference_close or momentum_sign not in reference_close:
        raise ValueError("trend and momentum signs must be -1, 0, or 1")
    bars[9] = _with_close(bars[9], reference_close[trend_sign])
    bars[84] = _with_close(bars[84], reference_close[momentum_sign])
    bars[89] = _with_close(bars[89], latest_close)
    return bars


def _with_close(bar: Bar, close: Decimal) -> Bar:
    return replace(
        bar,
        open=close,
        high=close + Decimal("0.01"),
        low=close - Decimal("0.01"),
        close=close,
    )


def _observed_provisional_capability() -> KisMarketDataCapability:
    return KisMarketDataCapability(
        capability_id="unit.kis.paper.observed-raw-1m",
        state=KisCapabilityState.OBSERVED,
        endpoint_category="overseas_stock_intraday",
        exchange_scope=("NAS",),
        symbol_scope=("QQQ",),
        raw_fields=("open", "high", "low", "last", "evol"),
        timeframe=Timeframe.M1,
        time_semantics="unit observed bar-open timestamp evidence",
        completed_bar_rule="unit observed current-minute exclusion",
        freshness_budget=timedelta(minutes=2),
        paging_facts="unit observed contiguous continuation",
        storage_rights=KisStorageRightsStatus.UNVERIFIED,
        evidence_reference="sha256:" + "c" * 64,
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _provisional_authorization(
    capability: KisMarketDataCapability,
) -> KisPaperBaselineAuthorization:
    return KisPaperBaselineAuthorization(
        capability_id=capability.capability_id,
        capability_contract_sha256=capability.contract_sha256,
        evidence_reference=capability.evidence_reference,
    )


def _qualified_capability(
    *,
    symbol_scope: tuple[str, ...] = ("QQQ",),
    endpoint_category: str = "overseas_stock_intraday",
) -> KisMarketDataCapability:
    return KisMarketDataCapability(
        capability_id="unit.kis.paper.raw-1m",
        state=KisCapabilityState.QUALIFIED,
        endpoint_category=endpoint_category,
        exchange_scope=("NAS",),
        symbol_scope=symbol_scope,
        raw_fields=("open", "high", "low", "last", "evol"),
        timeframe=Timeframe.M1,
        time_semantics="unit bar-open timestamp evidence",
        completed_bar_rule="unit current-minute exclusion",
        freshness_budget=timedelta(minutes=2),
        paging_facts="unit contiguous continuation",
        storage_rights=KisStorageRightsStatus.UNVERIFIED,
        evidence_reference="unit-capability-evidence",
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _trust_for_test(monkeypatch: pytest.MonkeyPatch, capability: KisMarketDataCapability) -> None:
    monkeypatch.setattr(
        kis_paper_baseline,
        "trusted_kis_paper_baseline_qualifications",
        lambda: (
            KisCapabilityQualification(
                qualification_id=f"unit.qualification.{capability.capability_id}",
                capability_id=capability.capability_id,
                capability_contract_sha256=capability.contract_sha256,
                evidence_reference="unit-qualification-evidence",
                reviewed_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        ),
    )
