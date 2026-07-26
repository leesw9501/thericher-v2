from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research import kis_daily_sequence_architecture_screen as screen


def test_daily_sequence_input_is_qqq_spy_only_and_keeps_windows_phase_local() -> None:
    source = _catalog(count=180)

    prepared = screen.build_kis_daily_sequence_screen_input(source)

    assert tuple(prepared.catalog.bars_by_symbol) == ("QQQ", "SPY")
    assert prepared.split.purge_session_count == screen.KIS_DAILY_SEQUENCE_PURGE_SESSIONS
    assert prepared.campaign.target.entry_bar_offset == 1
    assert prepared.campaign.target.exit_bar_offset == 2
    assert prepared.campaign.costs.fee_bps == Decimal("1")
    assert prepared.campaign.costs.slippage_bps == Decimal("2")
    assert all(sample.label in {0, 1} for sample in prepared.development_samples)
    assert all(
        sample.label is None
        and _within_catalog(
            sample,
            prepared.validation_catalog.bars_by_symbol[symbol].bars,
        )
        for symbol, samples in prepared.validation_samples_by_symbol.items()
        for sample in samples
    )
    assert all(
        _within_catalog(
            sample,
            prepared.development_catalog.bars_by_symbol[sample.symbol].bars,
        )
        for sample in prepared.development_samples
    )


def test_daily_features_are_causal_while_label_uses_next_two_observed_opens() -> None:
    baseline = _catalog(count=80)
    shifted_exit = _catalog(count=80, qqq_open_boosts={22: Decimal("40")})
    costs = screen.CampaignCosts(
        fee_bps=Decimal("1"),
        slippage_bps=Decimal("2"),
        slippage_source_id="unit-local-paper-cost",
    )
    baseline_samples = screen._build_phase_samples(  # noqa: SLF001
        baseline,
        include_labels=True,
        decision_stride=1,
        costs=costs,
    )
    shifted_samples = screen._build_phase_samples(  # noqa: SLF001
        shifted_exit,
        include_labels=True,
        decision_stride=1,
        costs=costs,
    )
    baseline_sample = _sample_for_decision(baseline_samples, symbol="QQQ", index=20)
    shifted_sample = _sample_for_decision(shifted_samples, symbol="QQQ", index=20)

    assert baseline_sample.features == shifted_sample.features
    assert baseline_sample.label == 0
    assert shifted_sample.label == 1
    assert baseline_sample.entry_start.date() > baseline_sample.decision_start.date()
    assert baseline_sample.exit_start.date() > baseline_sample.entry_start.date()


def test_validation_suffix_cannot_change_development_standardizer_or_input_hash() -> None:
    baseline = screen.build_kis_daily_sequence_screen_input(_catalog(count=180))
    shifted = screen.build_kis_daily_sequence_screen_input(
        _catalog(count=180, qqq_price_shift_start=120, qqq_price_shift=Decimal("50"))
    )

    assert baseline.development_input_hash == shifted.development_input_hash
    assert baseline.standardizer.standardizer_hash == shifted.standardizer.standardizer_hash
    assert baseline.validation_input_hash != shifted.validation_input_hash


def test_daily_sequence_rejects_iwm_or_an_incompatible_adjustment_mode() -> None:
    source = _catalog(count=180)
    with_iwm = replace(
        source,
        bars_by_symbol=MappingProxyType(
            {
                **source.bars_by_symbol,
                "IWM": source.bars_by_symbol["SPY"],
            }
        ),
    )

    with pytest.raises(ValueError, match="source contract"):
        screen.build_kis_daily_sequence_screen_input(with_iwm)
    with pytest.raises(ValueError, match="source contract"):
        screen.build_kis_daily_sequence_screen_input(
            replace(source, adjustment_mode="MODP=1_adjusted")
        )


def test_cpu_smoke_is_deterministic_offline_local_paper_and_never_selects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"

    first = screen.run_kis_daily_sequence_architecture_screen(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cpu-a",
        mode="cpu-smoke",
        repo_root=Path.cwd(),
        trainer=_fake_trainer,
    )
    second = screen.run_kis_daily_sequence_architecture_screen(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cpu-b",
        mode="cpu-smoke",
        repo_root=Path.cwd(),
        trainer=_fake_trainer,
    )

    first_summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert first.precommit_hash == second.precommit_hash
    assert first.screen_input.development_input_hash == second.screen_input.development_input_hash
    assert [cell.prediction_hash for cell in first.replay_cells] == [
        cell.prediction_hash for cell in second.replay_cells
    ]
    assert len(first.replay_cells) == 6
    assert all(cell.replay.fill_source == LOCAL_PAPER_SOURCE for cell in first.replay_cells)
    assert all(
        cell.replay.replay_evidence.fill_source == LOCAL_PAPER_SOURCE
        for cell in first.replay_cells
    )
    assert all(cell.replay.result.trades for cell in first.replay_cells)
    assert first_summary["reporting"] == {
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "sealed_holdout_materialized": False,
        "selection_allowed": False,
        "winner": None,
    }
    assert first_summary["source"]["symbols"] == ["QQQ", "SPY"]
    assert first_summary["artifact_policy"]["repo_storage_allowed"] is False
    assert first.summary_path.is_relative_to(artifact_root)
    assert all(
        item.checkpoint_path.is_relative_to(artifact_root) for item in first.trained_architectures
    )


def test_cuda_mode_accepts_mocked_external_checkpoints_without_a_gpu(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    seen_modes: list[str] = []

    def cuda_trainer(
        prepared: screen.KisDailySequenceScreenInput,
        spec: screen.KisDailySequenceArchitectureSpec,
        mode: screen.DailySequenceMode,
        checkpoint_dir: Path,
    ) -> screen.KisDailyTrainedSequenceArchitecture:
        seen_modes.append(mode)
        return _fake_trainer(prepared, spec, mode, checkpoint_dir)

    run = screen.run_kis_daily_sequence_architecture_screen(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cuda-mock",
        mode="cuda-screen",
        repo_root=Path.cwd(),
        trainer=cuda_trainer,
    )

    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert seen_modes == ["cuda-screen"] * 3
    assert summary["mode"] == "offline_cuda_local_paper"
    assert all(
        item.checkpoint_path.is_relative_to(artifact_root)
        for item in run.trained_architectures
    )


def test_daily_sequence_rejects_repository_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        screen.run_kis_daily_sequence_architecture_screen(
            _catalog(count=180),
            artifact_root=repo_root / "model-artifacts",
            run_label="bad-root",
            mode="cpu-smoke",
            repo_root=repo_root,
            trainer=_fake_trainer,
        )


def _fake_trainer(
    prepared: screen.KisDailySequenceScreenInput,
    spec: screen.KisDailySequenceArchitectureSpec,
    mode: screen.DailySequenceMode,
    checkpoint_dir: Path,
) -> screen.KisDailyTrainedSequenceArchitecture:
    checkpoint_path = checkpoint_dir / f"{spec.architecture_id}.pt"
    checkpoint_path.write_bytes(f"{mode}:{spec.architecture_id}".encode("ascii"))
    epochs = (
        screen.KIS_DAILY_SEQUENCE_CPU_EPOCHS
        if mode == "cpu-smoke"
        else screen.KIS_DAILY_SEQUENCE_CUDA_EPOCHS
    )
    probabilities = {
        symbol: tuple(0.75 for _ in samples)
        for symbol, samples in prepared.validation_samples_by_symbol.items()
    }
    return screen.KisDailyTrainedSequenceArchitecture(
        spec=spec,
        training={
            "backend": "unit",
            "mode": mode,
            "architecture": spec.architecture_id,
            "sample_count": len(prepared.development_samples),
            "sequence_length": screen.KIS_DAILY_SEQUENCE_LENGTH,
            "feature_count": len(screen.KIS_DAILY_SEQUENCE_FEATURE_NAMES),
            "epochs": epochs,
        },
        probabilities_by_symbol=probabilities,
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=screen._sha256_file(checkpoint_path),  # noqa: SLF001
    )


def _catalog(
    *,
    count: int,
    qqq_open_boosts: dict[int, Decimal] | None = None,
    qqq_price_shift_start: int | None = None,
    qqq_price_shift: Decimal = Decimal("0"),
) -> KisPaperPrivateDailyCatalog:
    qqq_open_boosts = qqq_open_boosts or {}
    start = datetime(2020, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(count))
    qqq_bars: list[Bar] = []
    spy_bars: list[Bar] = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        later_shift = (
            qqq_price_shift
            if qqq_price_shift_start is not None and index >= qqq_price_shift_start
            else Decimal("0")
        )
        qqq_open = Decimal("100") + Decimal(index) / Decimal("1000") + later_shift
        qqq_open += qqq_open_boosts.get(index, Decimal("0"))
        spy_open = Decimal("200") + Decimal(index) / Decimal("2000")
        qqq_bars.append(_bar(symbol="QQQ", start_ts=timestamp, opened=qqq_open))
        spy_bars.append(_bar(symbol="SPY", start_ts=timestamp, opened=spy_open))
    source_hash = "b" if qqq_price_shift_start is None and not qqq_open_boosts else "c"
    dataset_hash = "sha256:" + source_hash * 64
    source_path = Path(f"D:/market_data/unit-kis-daily-sequence-index-{source_hash}.json")
    return KisPaperPrivateDailyCatalog(
        dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "d" * 64,
        index_path=source_path,
        source_root=source_path.parent,
        adjustment_mode=KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(
            {
                "QQQ": _cataloged_bars_from_verified_loader(
                    dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
                    dataset_hash=dataset_hash,
                    source_path=source_path,
                    bars=tuple(qqq_bars),
                ),
                "SPY": _cataloged_bars_from_verified_loader(
                    dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
                    dataset_hash=dataset_hash,
                    source_path=source_path,
                    bars=tuple(spy_bars),
                ),
            }
        ),
        common_sessions=sessions,
        raw_price_limitations=(
            "MODP=0_unadjusted",
            "corporate_action_semantics_not_qualified",
        ),
    )


def _bar(*, symbol: str, start_ts: datetime, opened: Decimal) -> Bar:
    closed = opened
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("1"),
        low=opened - Decimal("1"),
        close=closed,
        volume=Decimal("1000"),
        complete=True,
    )


def _sample_for_decision(
    samples: tuple[screen.KisDailySequenceSample, ...],
    *,
    symbol: str,
    index: int,
) -> screen.KisDailySequenceSample:
    target = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index + 1)
    return next(
        sample for sample in samples if sample.symbol == symbol and sample.decision_end == target
    )


def _within_catalog(
    sample: screen.KisDailySequenceSample,
    bars: tuple[Bar, ...],
) -> bool:
    return sample.history_start >= bars[0].start_ts and sample.exit_start <= bars[-1].start_ts


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS daily sequence screen must remain offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)
