from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE
from thericher_v2.research import kis_nas_d1_volatility_trend_sealed_evaluation as sealed


def test_local_paper_evaluation_is_offline_replayable_and_marks_intratrade_drawdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    slot = _unit_slot()
    campaign_input = SimpleNamespace(
        contract=SimpleNamespace(
            costs=SimpleNamespace(fee_bps=Decimal("1"), slippage_bps=Decimal("0"))
        )
    )

    result = sealed._evaluate_actions(  # noqa: SLF001
        result_id="unit-candidate:AAPL",
        result_kind="candidate",
        model_family="unit",
        symbol="AAPL",
        lineage_hash="sha256:" + "1" * 64,
        actions=(True,),
        slots=(slot,),
        campaign_input=campaign_input,
    )

    assert result.fill_source == LOCAL_PAPER_SOURCE
    assert result.all_fills_local_paper is True
    assert result.replay_reconstructed is True
    assert result.terminal_position_zero is True
    assert result.fill_count == 2
    assert result.maximum_drawdown == Decimal("50.01")
    payload = result.safe_payload()
    assert payload["fill_source"] == LOCAL_PAPER_SOURCE
    assert payload["event_rows_retained"] is False
    sealed._assert_source_safe(payload)  # noqa: SLF001


def test_cpu_prediction_batches_require_frozen_receipt_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature_sequence = tuple((0.0,) * 5 for _ in range(20))
    samples_by_symbol = {
        symbol: (
            SimpleNamespace(symbol=symbol, feature_sequence=feature_sequence),
            SimpleNamespace(symbol=symbol, feature_sequence=feature_sequence),
        )
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    standardizers = {
        symbol: SimpleNamespace(
            standardizer_hash=f"sha256:{index + 1:064x}",
            transform=lambda values, *, sequence_length: values,
        )
        for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    }
    models = {
        symbol: SimpleNamespace(
            parameter_hash=f"sha256:{index + 11:064x}",
            weights=(0.0,) * 100,
            intercept=0.0,
        )
        for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    }
    campaign_input = SimpleNamespace(
        contract=SimpleNamespace(features=SimpleNamespace(sequence_length=20)),
        validation_samples=lambda symbol: samples_by_symbol[symbol],
        development_samples=lambda symbol: samples_by_symbol[symbol],
    )
    breadth_input = SimpleNamespace(
        campaign_input=campaign_input,
        standardizer=lambda symbol: standardizers[symbol],
    )
    evaluation_input = SimpleNamespace(breadth_input=breadth_input)
    summary = {
        "candidates": [
            {
                "symbol": spec.symbol,
                "model_id": "l2_logistic",
                "model_parameter_hash": models[spec.symbol].parameter_hash,
                "standardizer_hash": standardizers[spec.symbol].standardizer_hash,
                "development_sample_count": len(samples_by_symbol[spec.symbol]),
                "steps": spec.steps,
                "seed": spec.seed,
            }
            for spec in sealed.KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
        ]
    }
    monkeypatch.setattr(
        sealed,
        "fit_kis_nas_d1_volatility_trend_l2_logistic_smoke",
        lambda _breadth_input, spec: models[spec.symbol],
    )

    batches = sealed._cpu_prediction_batches(  # noqa: SLF001
        evaluation_input,
        cpu_summary=summary,
    )

    assert len(batches) == len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    assert {len(batch.probabilities) for batch in batches} == {2}

    summary["candidates"][0]["model_parameter_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="CPU model lineage drifted"):
        sealed._cpu_prediction_batches(  # noqa: SLF001
            evaluation_input,
            cpu_summary=summary,
        )


def test_candidate_evidence_failure_writes_external_source_safe_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "external-model-artifacts"
    evaluation_input = _preflight_input()
    slots_opened = False

    monkeypatch.setattr(
        sealed,
        "require_attested_kis_nas_d1_volatility_trend_sealed_evaluation_input",
        lambda _value: None,
    )

    def fail_candidate_evidence(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("candidate evidence drift")

    def slots_must_not_open(*_args: object, **_kwargs: object) -> object:
        nonlocal slots_opened
        slots_opened = True
        raise AssertionError("validation slots must remain sealed")

    monkeypatch.setattr(sealed, "_validate_external_candidate_evidence", fail_candidate_evidence)
    monkeypatch.setattr(sealed, "_validation_slots", slots_must_not_open)

    with pytest.raises(RuntimeError, match="candidate evidence drift"):
        sealed.run_kis_nas_d1_volatility_trend_sealed_evaluation(
            evaluation_input,
            artifact_root=artifact_root,
            run_label="candidate-evidence-failure",
            review_status="review_unavailable",
            repo_root=repository,
        )

    output_dir = (
        artifact_root
        / sealed.KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ID
        / "candidate-evidence-failure"
    )
    failure = json.loads((output_dir / "failure.json").read_text(encoding="utf-8"))
    assert slots_opened is False
    assert failure["stage"] == "candidate_evidence"
    assert failure["precommit_hash"] is None
    assert not (output_dir / "precommit.json").exists()
    assert (output_dir / "failure.json").is_relative_to(artifact_root)
    sealed._assert_source_safe(failure)  # noqa: SLF001


def test_output_root_cannot_be_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        sealed._prepare_output_dir(  # noqa: SLF001
            artifact_root=repository / "model-artifacts",
            repository=repository,
            run_label="repository-root",
        )


def test_runner_has_no_environment_or_broker_access_surface() -> None:
    source = Path("scripts/run_kis_nas_d1_volatility_trend_sealed_evaluation.py").read_text(
        encoding="utf-8"
    )

    assert "load_dotenv" not in source
    assert "os.environ" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert "requests" not in source
    assert "http" not in source


def _unit_slot() -> sealed.KisNasD1VolatilityTrendEvaluationSlot:
    start = datetime(2024, 1, 2, tzinfo=UTC)
    signal_bar = _bar(start, open_value=Decimal("99"), low_value=Decimal("98"))
    entry_bar = _bar(start + timedelta(days=1), open_value=Decimal("100"), low_value=Decimal("50"))
    exit_bar = _bar(start + timedelta(days=2), open_value=Decimal("100"), low_value=Decimal("99"))
    sample = SimpleNamespace(
        symbol="AAPL",
        decision_start=signal_bar.start_ts,
        decision_end=signal_bar.end_ts,
    )
    return sealed.KisNasD1VolatilityTrendEvaluationSlot(
        sample=sample,
        signal_bar=signal_bar,
        entry_bar=entry_bar,
        exit_bar=exit_bar,
    )


def _bar(start: datetime, *, open_value: Decimal, low_value: Decimal) -> Bar:
    return Bar(
        symbol="AAPL",
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start,
        open=open_value,
        high=max(open_value, low_value) + Decimal("1"),
        low=low_value,
        close=open_value,
        volume=Decimal("1"),
        complete=True,
    )


def _preflight_input() -> SimpleNamespace:
    phase = SimpleNamespace(common_sessions=(date(2024, 1, 2),))
    return SimpleNamespace(
        source_input=SimpleNamespace(
            panel_dataset_hash="sha256:" + "1" * 64,
            development=phase,
            purge=phase,
            validation=phase,
        ),
        campaign_input=SimpleNamespace(
            contract=SimpleNamespace(contract_hash="sha256:" + "2" * 64),
            development_input_hash="sha256:" + "3" * 64,
            validation_input_hash="sha256:" + "4" * 64,
            source_limitations=(),
        ),
        breadth_input=SimpleNamespace(campaign_precommit_hash="sha256:" + "5" * 64),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(os, "getenv", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
