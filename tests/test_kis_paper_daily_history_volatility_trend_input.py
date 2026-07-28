from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_history_sequence_input as sequence_input
from thericher_v2.data import kis_paper_daily_history_volatility_trend_input as volatility_input
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_nas_d1_volatility_trend_breadth as breadth
from thericher_v2.research import kis_nas_d1_volatility_trend_campaign as campaign
from thericher_v2.research.causal_bar_features import (
    KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES,
    KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS,
    KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH,
    build_kis_nas_d1_volatility_trend_feature_sequence,
)


def test_completed_features_ignore_the_next_two_bars_and_have_frozen_shape(
    tmp_path: Path,
) -> None:
    baseline = volatility_input.build_kis_paper_daily_history_volatility_trend_input(
        _source(tmp_path / "baseline")
    )
    future_changed = volatility_input.build_kis_paper_daily_history_volatility_trend_input(
        _source(
            tmp_path / "future-changed",
            altered_symbol="AAPL",
            altered_from_index=30,
            alteration=Decimal("7"),
        )
    )

    baseline_sample = baseline.development_samples("AAPL")[0]
    changed_sample = future_changed.development_samples("AAPL")[0]

    assert baseline_sample == changed_sample
    assert len(baseline_sample.feature_sequence) == KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH
    assert all(
        len(row) == len(KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES)
        for row in baseline_sample.feature_sequence
    )
    assert baseline_sample.lookback_anchor_start < baseline_sample.feature_start
    assert baseline_sample.feature_start <= baseline_sample.decision_start
    assert baseline_sample.decision_start < baseline_sample.decision_end


def test_validation_samples_are_target_free_and_safe_payload_hides_values(tmp_path: Path) -> None:
    prepared = volatility_input.build_kis_paper_daily_history_volatility_trend_input(
        _source(tmp_path / "source")
    )
    sample = prepared.validation_samples("AAPL")[0]
    payload = prepared.safe_payload()

    assert len(prepared.development_samples("AAPL")) == 1481
    assert len(prepared.validation_samples("AAPL")) == 618
    assert not hasattr(sample, "label")
    assert not hasattr(sample, "entry_start")
    assert not hasattr(sample, "exit_start")
    assert payload["features"]["future_bars_read"] is False
    _assert_no_value_fields(payload)


def test_symbol_changes_are_isolated_but_own_symbol_changes_are_detected(tmp_path: Path) -> None:
    baseline = volatility_input.build_kis_paper_daily_history_volatility_trend_input(
        _source(tmp_path / "baseline")
    )
    other_symbol_changed = volatility_input.build_kis_paper_daily_history_volatility_trend_input(
        _source(
            tmp_path / "other-symbol",
            altered_symbol="AMZN",
            altered_from_index=300,
            alteration=Decimal("5"),
        )
    )
    own_symbol_changed = volatility_input.build_kis_paper_daily_history_volatility_trend_input(
        _source(
            tmp_path / "own-symbol",
            altered_symbol="AAPL",
            altered_from_index=300,
            alteration=Decimal("5"),
        )
    )

    assert baseline.development_samples("AAPL") == other_symbol_changed.development_samples("AAPL")
    assert baseline.validation_samples("AAPL") == other_symbol_changed.validation_samples("AAPL")
    assert baseline.development_samples("AAPL") != own_symbol_changed.development_samples("AAPL")
    assert baseline.validation_samples("AAPL") != own_symbol_changed.validation_samples("AAPL")


def test_incomplete_non_d1_short_misaligned_and_invalid_ohlc_inputs_reject(tmp_path: Path) -> None:
    incomplete = _source(tmp_path / "incomplete")
    incomplete_stream = incomplete.development.bars_by_symbol["AAPL"]
    object.__setattr__(
        incomplete_stream,
        "bars",
        (replace(incomplete_stream.bars[0], complete=False), *incomplete_stream.bars[1:]),
    )
    with pytest.raises(ValueError):
        volatility_input.build_kis_paper_daily_history_volatility_trend_input(incomplete)

    non_d1 = _source(tmp_path / "non-d1")
    non_d1_stream = non_d1.development.bars_by_symbol["AAPL"]
    object.__setattr__(
        non_d1_stream,
        "bars",
        (replace(non_d1_stream.bars[0], timeframe=Timeframe.M1), *non_d1_stream.bars[1:]),
    )
    with pytest.raises(ValueError):
        volatility_input.build_kis_paper_daily_history_volatility_trend_input(non_d1)

    misaligned = _source(tmp_path / "misaligned")
    misaligned_stream = misaligned.development.bars_by_symbol["AAPL"]
    object.__setattr__(
        misaligned_stream,
        "bars",
        (
            replace(
                misaligned_stream.bars[0],
                start_ts=misaligned_stream.bars[0].start_ts + timedelta(days=1),
            ),
            *misaligned_stream.bars[1:],
        ),
    )
    with pytest.raises(ValueError):
        volatility_input.build_kis_paper_daily_history_volatility_trend_input(misaligned)

    invalid_ohlc = _source(tmp_path / "invalid-ohlc")
    invalid_ohlc_bar = invalid_ohlc.development.bars_by_symbol["AAPL"].bars[0]
    object.__setattr__(invalid_ohlc_bar, "high", invalid_ohlc_bar.low)
    with pytest.raises(ValueError, match="OHLC"):
        volatility_input.build_kis_paper_daily_history_volatility_trend_input(invalid_ohlc)

    short_bars = _source(tmp_path / "short").development.stream("AAPL").bars[
        : KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1
    ]
    with pytest.raises(ValueError, match="decision index"):
        build_kis_nas_d1_volatility_trend_feature_sequence(
            short_bars,
            symbol="AAPL",
            decision_index=len(short_bars) - 1,
        )


def test_builder_stays_offline_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source(tmp_path / "source")
    _deny_external_access(monkeypatch)

    prepared = volatility_input.build_kis_paper_daily_history_volatility_trend_input(source)

    assert prepared.development.feature_input_hash.startswith("sha256:")
    assert prepared.validation.feature_input_hash.startswith("sha256:")


def test_campaign_filters_phase_ends_and_keeps_validation_target_free(tmp_path: Path) -> None:
    campaign_input = campaign.build_kis_nas_d1_volatility_trend_campaign(
        _source(tmp_path / "source")
    )

    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        development = campaign_input.development_samples(symbol)
        validation = campaign_input.validation_samples(symbol)
        assert len(development) == 1479
        assert len(validation) == 308
        assert all(sample.label in {0, 1} for sample in development)
        assert not hasattr(validation[0], "label")
        assert development[-1].decision_start.date() < campaign_input.development_sessions[-1]
        assert validation[-1].decision_start.date() < campaign_input.validation_sessions[-1]
        assert campaign.is_kis_nas_d1_volatility_trend_reference_long(
            campaign_input,
            validation[0],
            comparator_id="volatility_gated_5d_trend",
        ) in {True, False}


def test_development_fit_stays_isolated_from_validation_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    baseline = _breadth_input(tmp_path / "baseline")
    changed = _breadth_input(
        tmp_path / "validation-changed",
        altered_symbol="AAPL",
        altered_from_index=1600,
        alteration=Decimal("9"),
    )
    spec = breadth.KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS[0]

    baseline_model = breadth.fit_kis_nas_d1_volatility_trend_l2_logistic_smoke(baseline, spec)
    changed_model = breadth.fit_kis_nas_d1_volatility_trend_l2_logistic_smoke(changed, spec)

    assert baseline.standardizer("AAPL").standardizer_hash == changed.standardizer(
        "AAPL"
    ).standardizer_hash
    assert baseline_model.parameter_hash == changed_model.parameter_hash
    assert (
        baseline.campaign_input.validation_input_hash
        != changed.campaign_input.validation_input_hash
    )


def test_cpu_and_fake_cuda_breadth_are_offline_source_safe_and_external(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    _deny_external_access(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    artifact_root = tmp_path / "external-model-artifacts"
    cpu = breadth.run_kis_nas_d1_volatility_trend_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu",
        repo_root=tmp_path / "repo",
    )
    cpu_payload = json.loads(cpu.summary_path.read_text(encoding="utf-8"))

    assert len(cpu.candidates) == len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    assert all(
        candidate.validation_forward.output_shape == (308, 1)
        for candidate in cpu.candidates
    )
    assert cpu_payload["validation"] == {
        "forward_only": True,
        "labels_materialized": False,
    }
    assert cpu.summary_path.is_relative_to(artifact_root)
    _assert_no_value_fields(cpu_payload)

    monkeypatch.setattr(
        breadth,
        "_torch_or_none",
        lambda: SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
    )
    cuda = breadth.run_kis_nas_d1_volatility_trend_cuda_breadth(
        prepared,
        cpu_smoke_summary_path=cpu.summary_path,
        artifact_root=artifact_root,
        run_label="cuda",
        repo_root=tmp_path / "repo",
        trainer=_fake_cuda_trainer,
    )
    cuda_payload = json.loads(cuda.summary_path.read_text(encoding="utf-8"))

    assert cuda.status == "completed"
    assert len(cuda.candidates) == 18
    assert all(candidate.safe_weights_only_reload for candidate in cuda.candidates)
    assert all(
        candidate.checkpoint_path.is_relative_to(artifact_root)
        for candidate in cuda.candidates
    )
    assert cuda_payload["reporting"]["selection_allowed"] is False
    _assert_no_value_fields(cuda_payload)


def test_breadth_rejects_git_and_linked_artifact_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(ValueError, match="outside the Git workspace"):
        breadth.run_kis_nas_d1_volatility_trend_l2_logistic_smoke(
            prepared,
            artifact_root=repository / "artifacts",
            run_label="inside-repo",
            repo_root=repository,
        )

    external_root = tmp_path / "external-model-artifacts"
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda value: value == external_root or original_is_symlink(value),
    )
    with pytest.raises(ValueError, match="link"):
        breadth.run_kis_nas_d1_volatility_trend_l2_logistic_smoke(
            prepared,
            artifact_root=external_root,
            run_label="linked-root",
            repo_root=repository,
        )


def test_cuda_rejects_a_cpu_summary_with_the_wrong_sibling_precommit_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fast_cpu(monkeypatch)
    prepared = _breadth_input(tmp_path / "source")
    artifact_root = tmp_path / "external-model-artifacts"
    cpu = breadth.run_kis_nas_d1_volatility_trend_l2_logistic_smoke(
        prepared,
        artifact_root=artifact_root,
        run_label="cpu",
        repo_root=tmp_path / "repo",
    )
    payload = json.loads(cpu.summary_path.read_text(encoding="utf-8"))
    payload["precommit_hash"] = "sha256:" + "0" * 64
    cpu.summary_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="CPU smoke summary"):
        breadth.run_kis_nas_d1_volatility_trend_cuda_breadth(
            prepared,
            cpu_smoke_summary_path=cpu.summary_path,
            artifact_root=artifact_root,
            run_label="cuda",
            repo_root=tmp_path / "repo",
            trainer=_fake_cuda_trainer,
        )


def _breadth_input(
    root: Path,
    *,
    altered_symbol: str | None = None,
    altered_from_index: int = 0,
    alteration: Decimal = Decimal("0"),
) -> breadth.KisNasD1VolatilityTrendBreadthInput:
    campaign_input = campaign.build_kis_nas_d1_volatility_trend_campaign(
        _source(
            root,
            altered_symbol=altered_symbol,
            altered_from_index=altered_from_index,
            alteration=alteration,
        )
    )
    return breadth.build_kis_nas_d1_volatility_trend_breadth_input(
        campaign_input,
        campaign_precommit_hash=(
            campaign.calculate_kis_nas_d1_volatility_trend_campaign_precommit_hash(
                campaign_input,
                review_status="review_unavailable",
            )
        ),
        review_status="review_unavailable",
    )


def _fast_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(breadth, "KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_STEPS", 2)
    monkeypatch.setattr(
        breadth,
        "KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS",
        tuple(
            breadth.KisNasD1VolatilityTrendL2LogisticSpec(
                symbol=symbol,
                seed=2026072815 + index,
                steps=2,
            )
            for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
        ),
    )


def _fake_cuda_trainer(
    prepared: breadth.KisNasD1VolatilityTrendBreadthInput,
    spec: breadth.KisNasD1VolatilityTrendArchitectureSpec,
    checkpoint_dir: Path,
) -> breadth.KisNasD1VolatilityTrendGpuCandidateReceipt:
    checkpoint_path = checkpoint_dir / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
    checkpoint_path.write_bytes(b"unit-checkpoint")
    return breadth.KisNasD1VolatilityTrendGpuCandidateReceipt(
        spec=spec,
        development_sample_count=len(prepared.campaign_input.development_samples(spec.symbol)),
        validation_forward=breadth.KisNasD1VolatilityTrendTargetFreeForward(
            symbol=spec.symbol,
            sample_count=len(prepared.campaign_input.validation_samples(spec.symbol)),
            output_shape=(len(prepared.campaign_input.validation_samples(spec.symbol)), 1),
            all_finite=True,
            output_bounds_valid=True,
        ),
        checkpoint_path=checkpoint_path,
        checkpoint_sha256="sha256:" + hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        backend="unit",
        device="unit",
        torch_version="unit",
        cuda_version=None,
        initial_loss=0.5,
        final_loss=0.4,
        cuda_peak_memory_bytes=0,
        safe_weights_only_reload=True,
    )


def _source(
    root: Path,
    *,
    altered_symbol: str | None = None,
    altered_from_index: int = 0,
    alteration: Decimal = Decimal("0"),
) -> sequence_input.KisPaperDailyHistorySequenceInput:
    return sequence_input._prepare_kis_paper_daily_history_sequence_input(  # noqa: SLF001
        _panel(
            root,
            altered_symbol=altered_symbol,
            altered_from_index=altered_from_index,
            alteration=alteration,
        )
    )


def _panel(
    root: Path,
    *,
    altered_symbol: str | None,
    altered_from_index: int,
    alteration: Decimal,
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    start = datetime(2018, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(2179))
    dataset_hash = sequence_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for symbol_offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        bars = tuple(
            _bar(
                symbol=symbol,
                start_ts=start + timedelta(days=index),
                value=(
                    Decimal("100")
                    + Decimal(symbol_offset)
                    + Decimal(index) / Decimal("100")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
            )
            for index in range(2179)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state="complete",
            last_reason=None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket=_quarter(sessions[0]),
            coverage_end_bucket=_quarter(sessions[-1]),
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "a" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(*, symbol: str, start_ts: datetime, value: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("1000"),
        complete=True,
    )


def _quarter(value: date) -> str:
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("volatility trend adapter must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(os, "getenv", denied)


def _assert_no_value_fields(value: object) -> None:
    forbidden = {
        "bars",
        "close",
        "entry",
        "exit",
        "feature_sequence",
        "high",
        "label",
        "low",
        "open",
        "prices",
        "volume",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden)
        for nested in value.values():
            _assert_no_value_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_value_fields(nested)
