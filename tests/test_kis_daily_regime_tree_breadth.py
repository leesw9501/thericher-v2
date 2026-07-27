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
from thericher_v2.research import kis_daily_regime_tree_breadth as breadth


def test_tree_breadth_reuses_the_frozen_qqq_spy_completed_bar_contract() -> None:
    prepared = breadth.build_kis_daily_regime_tree_breadth_input(_catalog(count=180))

    assert prepared.campaign.campaign_id == breadth.KIS_DAILY_REGIME_TREE_BREADTH_ID
    assert tuple(prepared.sequence_input.catalog.bars_by_symbol) == ("QQQ", "SPY")
    assert prepared.sequence_input.split.purge_session_count == 22
    assert all(sample.label in {0, 1} for sample in prepared.sequence_input.development_samples)
    assert all(
        sample.label is None
        for samples in prepared.sequence_input.validation_samples_by_symbol.values()
        for sample in samples
    )
    with pytest.raises(ValueError, match="hyperparameters are frozen"):
        breadth.KisDailyRegimeTreeBreadthSpec(max_leaf_nodes=8)


def test_validation_suffix_cannot_change_the_tree_development_fit() -> None:
    baseline = breadth.build_kis_daily_regime_tree_breadth_input(_catalog(count=180))
    shifted = breadth.build_kis_daily_regime_tree_breadth_input(
        _catalog(count=180, qqq_price_shift_start=145, qqq_price_shift=Decimal("20"))
    )

    baseline_model = breadth.fit_kis_daily_regime_tree_breadth(baseline)
    shifted_model = breadth.fit_kis_daily_regime_tree_breadth(shifted)

    assert (
        baseline.sequence_input.development_input_hash
        == shifted.sequence_input.development_input_hash
    )
    assert (
        baseline.sequence_input.validation_input_hash
        != shifted.sequence_input.validation_input_hash
    )
    assert baseline_model.model_identity_hash == shifted_model.model_identity_hash
    assert baseline_model.fit_backend == "hist_gradient_tree"


def test_tree_breadth_is_deterministic_offline_local_paper_and_never_serializes_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    first = breadth.run_kis_daily_regime_tree_breadth(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cpu-a",
        repo_root=repo_root,
    )
    second = breadth.run_kis_daily_regime_tree_breadth(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cpu-b",
        repo_root=repo_root,
    )

    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert first.precommit_hash == second.precommit_hash
    assert first.model.model_identity_hash == second.model.model_identity_hash
    assert [cell.prediction_hash for cell in first.replay_cells] == [
        cell.prediction_hash for cell in second.replay_cells
    ]
    assert [cell.symbol for cell in first.replay_cells] == ["QQQ", "SPY"]
    assert len(first.baseline_cells) == 6
    assert all(cell.replay.fill_source == LOCAL_PAPER_SOURCE for cell in first.replay_cells)
    assert all(
        cell.replay.replay_evidence.fill_source == LOCAL_PAPER_SOURCE
        for cell in first.replay_cells
    )
    assert all(cell.replay.fill_source == LOCAL_PAPER_SOURCE for cell in first.baseline_cells)
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    assert not first.summary_path.is_relative_to(repo_root)
    assert summary["mode"] == "offline_cpu_local_paper"
    assert summary["validation"]["labels_materialized_for_fit"] is False
    assert summary["model"]["serialized_model_written"] is False
    assert summary["artifact_policy"] == {
        "raw_market_data_written": False,
        "repo_storage_allowed": False,
        "serialized_model_written": False,
    }
    assert not list(artifact_root.rglob("*.pkl"))
    assert not list(artifact_root.rglob("*.joblib"))


def test_tree_breadth_rejects_repository_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        breadth.run_kis_daily_regime_tree_breadth(
            _catalog(count=180),
            artifact_root=repo_root / "model-artifacts",
            run_label="bad-root",
            repo_root=repo_root,
        )


def test_tree_decision_rejects_non_validation_or_incomplete_windows() -> None:
    prepared = breadth.build_kis_daily_regime_tree_breadth_input(_catalog(count=180))
    model = breadth.fit_kis_daily_regime_tree_breadth(prepared)
    symbol = "QQQ"
    sample = prepared.sequence_input.validation_samples_by_symbol[symbol][0]
    probability = model.probabilities((sample,))[0]
    decision_model = breadth._KisDailyRegimeTreeDecisionModel(  # noqa: SLF001
        symbol=symbol,
        samples_by_decision_end={sample.decision_end: sample},
        probabilities_by_decision_end={sample.decision_end: probability},
        precommit_hash="sha256:" + "e" * 64,
        model_identity_hash=model.model_identity_hash,
    )
    bars = prepared.sequence_input.catalog.bars_by_symbol[symbol].bars
    validation_window = [
        bar for bar in bars if sample.history_start <= bar.start_ts <= sample.decision_start
    ]

    with pytest.raises(ValueError, match="future or cross-phase data"):
        decision_model.predict(
            [*validation_window[:-1], replace(validation_window[-1], complete=False)]
        )
    with pytest.raises(ValueError, match="non-validation decision"):
        decision_model.predict(list(bars[: breadth.KIS_DAILY_SEQUENCE_LENGTH]))


def _catalog(
    *,
    count: int,
    qqq_price_shift_start: int | None = None,
    qqq_price_shift: Decimal = Decimal("0"),
) -> KisPaperPrivateDailyCatalog:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(count))
    qqq_bars: list[Bar] = []
    spy_bars: list[Bar] = []
    qqq_cycle = (Decimal("100"), Decimal("102"), Decimal("99"), Decimal("103"))
    spy_cycle = (Decimal("200"), Decimal("203"), Decimal("198"), Decimal("204"))
    for index in range(count):
        timestamp = start + timedelta(days=index)
        qqq_open = qqq_cycle[index % len(qqq_cycle)]
        if qqq_price_shift_start is not None and index >= qqq_price_shift_start:
            qqq_open += qqq_price_shift
        spy_open = spy_cycle[index % len(spy_cycle)]
        qqq_bars.append(_bar(symbol="QQQ", start_ts=timestamp, opened=qqq_open))
        spy_bars.append(_bar(symbol="SPY", start_ts=timestamp, opened=spy_open))
    source_hash = "b" if qqq_price_shift_start is None else "c"
    dataset_hash = "sha256:" + source_hash * 64
    source_path = Path(f"C:/unit-market-data/kis-daily-tree-{source_hash}-index.json")
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
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("1"),
        low=opened - Decimal("1"),
        close=opened,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "KIS daily regime tree breadth must remain offline and credential-free"
        )

    original_getenv = os.getenv

    def deny_secret_environment(name: str, default: str | None = None) -> str | None:
        if name.startswith(("KIS_", "TIINGO_", "THERICHER_DASHBOARD_")):
            raise AssertionError(
                "KIS daily regime tree breadth must not read a credential environment value"
            )
        return original_getenv(name, default)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", deny_secret_environment)
