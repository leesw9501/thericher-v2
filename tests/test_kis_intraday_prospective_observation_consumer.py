from __future__ import annotations

import os
import socket
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_intraday_prospective_observation as prospective_input
import thericher_v2.research.kis_intraday_prospective_observation_consumer as consumer
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import prepare_kis_paper_intraday_feature_input
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.kis_intraday_feature_breadth import (
    KIS_INTRADAY_FEATURE_M1_BARS,
    KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION,
)
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
)

_HISTORICAL_DATES = KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
_PROSPECTIVE_DATES = (
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
)


def test_history_only_fit_never_receives_prospective_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_input = _observation_input()
    seen_training_dates: list[tuple[date, ...]] = []
    original_fit = consumer.fit_kis_intraday_regularized_linear_samples

    def observe_fit(samples, *, development_session_dates):
        seen_training_dates.append(tuple(sample.session_date for sample in samples))
        return original_fit(samples, development_session_dates=development_session_dates)

    monkeypatch.setattr(
        consumer,
        "fit_kis_intraday_regularized_linear_samples",
        observe_fit,
    )

    result = consumer.build_kis_intraday_prospective_observation_consumer(
        observation_input=observation_input
    )

    assert len(seen_training_dates) == 1
    assert set(seen_training_dates[0]) == set(_HISTORICAL_DATES)
    assert set(seen_training_dates[0]).isdisjoint(_PROSPECTIVE_DATES)
    assert result.historical_input.session_dates == _HISTORICAL_DATES
    assert result.prospective_input.session_dates == _PROSPECTIVE_DATES


def test_prospective_values_cannot_change_the_frozen_history_model() -> None:
    baseline = consumer.build_kis_intraday_prospective_observation_consumer(
        observation_input=_observation_input()
    )
    changed = consumer.build_kis_intraday_prospective_observation_consumer(
        observation_input=_observation_input(
            prospective_value_shift=Decimal("9"),
            prospective_hash_marker="c",
        )
    )

    assert baseline.frozen_linear_model.to_payload() == changed.frozen_linear_model.to_payload()
    assert (
        baseline.frozen_model_receipt.model_parameters_hash
        == changed.frozen_model_receipt.model_parameters_hash
    )
    assert baseline.frozen_model_receipt.historical_sample_hash == (
        changed.frozen_model_receipt.historical_sample_hash
    )
    assert baseline.prospective_input.dataset_hash != changed.prospective_input.dataset_hash


def test_consumer_requires_verified_input_and_prepares_fixed_local_paper_plans() -> None:
    with pytest.raises(TypeError, match="verified Data input"):
        consumer.build_kis_intraday_prospective_observation_consumer(observation_input=object())

    result = consumer.build_kis_intraday_prospective_observation_consumer(
        observation_input=_observation_input()
    )

    assert tuple(plan.candidate_id for plan in result.candidate_replay_plans) == (
        "flat",
        "always_long",
        "previous_bar_direction",
        "regularized_linear",
    )
    assert all(plan.fill_source == LOCAL_PAPER_SOURCE for plan in result.candidate_replay_plans)
    assert all(plan.campaign_phase == "validation" for plan in result.candidate_replay_plans)
    assert all(
        len(plan.eligible_signal_starts)
        == len(_PROSPECTIVE_DATES) * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
        for plan in result.candidate_replay_plans
    )
    assert result.summary.to_payload()["selection_allowed"] is False
    assert result.summary.to_payload()["profitability_conclusion"] is False
    assert (
        result.frozen_model_receipt.to_payload()["prospective_evaluation"][
            "preparation_identity"
        ]["head_index_metadata_sha256"]
        == "sha256:" + "9" * 64
    )

    sample = result.prospective_samples[0]
    history = [
        bar
        for bar in result.prospective_cataloged_bars.bars
        if sample.history_start <= bar.start_ts < sample.decision_end
    ][-KIS_INTRADAY_FEATURE_M1_BARS:]
    predictions = {
        plan.candidate_id: plan.model.predict(history) for plan in result.candidate_replay_plans
    }
    assert predictions["flat"].signal.action == "hold"
    assert predictions["always_long"].signal.action == "buy"


def test_consumer_is_offline_and_credential_free(monkeypatch: pytest.MonkeyPatch) -> None:
    observation_input = _observation_input()

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective observation consumer must remain offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(Path, "read_bytes", fail_external)
    monkeypatch.setattr(Path, "write_text", fail_external)

    result = consumer.build_kis_intraday_prospective_observation_consumer(
        observation_input=observation_input
    )

    assert result.summary.fill_source == LOCAL_PAPER_SOURCE


def _observation_input(
    *,
    prospective_value_shift: Decimal = Decimal("0"),
    prospective_hash_marker: str = "b",
) -> prospective_input.KisIntradayProspectiveObservationInput:
    historical = prepare_kis_paper_intraday_feature_input(
        _catalog(_HISTORICAL_DATES, dataset_marker="historical", hash_marker="a"),
        session_dates=_HISTORICAL_DATES,
    )
    prospective = prepare_kis_paper_intraday_feature_input(
        _catalog(
            _PROSPECTIVE_DATES,
            dataset_marker="prospective",
            hash_marker=prospective_hash_marker,
            value_shift=prospective_value_shift,
        ),
        session_dates=_PROSPECTIVE_DATES,
    )
    contract_hash = "sha256:" + "c" * 64
    precommit_hash = "sha256:" + "d" * 64
    artifact_slot_id = prospective_input._artifact_slot_id(
        contract_hash=contract_hash,
        selected_session_dates=_PROSPECTIVE_DATES,
    )
    selected_rows_fingerprint_sha256 = "sha256:" + "f" * 64
    head_index_metadata_sha256 = "sha256:" + "9" * 64
    input_hash = prospective_input._input_hash(
        historical_input_hash=historical.input_hash,
        prospective_input_hash=prospective.input_hash,
        contract_hash=contract_hash,
        precommit_hash=precommit_hash,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=head_index_metadata_sha256,
        historical_session_dates=historical.session_dates,
        prospective_session_dates=prospective.session_dates,
    )
    return prospective_input._verified_observation_input(
        historical_catalog=historical.catalog,
        prospective_catalog=prospective.catalog,
        historical_session_dates=historical.session_dates,
        prospective_session_dates=prospective.session_dates,
        historical_input_hash=historical.input_hash,
        prospective_input_hash=prospective.input_hash,
        contract_hash=contract_hash,
        precommit_hash=precommit_hash,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=head_index_metadata_sha256,
        input_hash=input_hash,
    )


def _catalog(
    session_dates: tuple[date, ...],
    *,
    dataset_marker: str,
    hash_marker: str,
    value_shift: Decimal = Decimal("0"),
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(session_dates):
        session = us_equity_2026_session(session_date)
        assert session is not None
        for minute in range(390):
            perturbation = value_shift * Decimal((minute % 7) - 3) / Decimal("100")
            opened = (
                Decimal("100")
                + Decimal(session_index)
                + Decimal(minute) / Decimal("100")
                + perturbation
            )
            closed = opened + (Decimal("0.02") if minute % 3 else Decimal("-0.01"))
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=max(opened, closed) + Decimal("0.01"),
                    low=min(opened, closed) - Decimal("0.01"),
                    close=closed,
                    volume=Decimal("1000") + Decimal(minute),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id=f"kis.paper.private.intraday.qqq.nas.m1.{dataset_marker}-synthetic-v1",
        dataset_hash="sha256:" + hash_marker * 64,
        source_path=Path(f"D:/market_data/{dataset_marker}-synthetic.json"),
        bars=tuple(bars),
    )
