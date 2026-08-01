from __future__ import annotations

import json
import os
import socket
import urllib.request
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import kis_intraday_window_matrix as window_matrix
from thericher_v2.research.kis_intraday_campaign import build_kis_intraday_cpu_campaign_plan


def test_window_matrix_preflight_is_offline_aggregate_only_and_external(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    _shorten_preflight(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"

    run = window_matrix.run_kis_intraday_window_matrix_preflight(
        _catalog(),
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=Path.cwd(),
    )

    assert run.status == "complete"
    assert run.precommit_path.is_relative_to(artifact_root)
    assert run.summary_path.is_relative_to(artifact_root)
    assert len(run.cell_results) == len(window_matrix.KIS_INTRADAY_WINDOW_MATRIX_WINDOWS)
    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert payload["precommit"]["written_before_real_matrix"] is True
    assert payload["matrix"]["per_cell_metrics_materialized"] is False
    assert payload["matrix"]["ranked_cell"] is None
    assert payload["gate"]["selection_allowed"] is False
    assert payload["gate"]["ensemble_allowed"] is False
    assert payload["gate"]["paper_input_allowed"] is False
    assert payload["cost_sensitivity"]["materialized"] is False
    assert payload["artifact_policy"] == {
        "checkpoint_written": False,
        "raw_market_data_written": False,
        "repo_storage_allowed": False,
        "root": str(artifact_root.resolve()),
    }
    text = run.summary_path.read_text(encoding="utf-8")
    assert "KIS_PAPER_" not in text
    assert "cell_results" not in text


def test_window_matrix_fits_only_development_features(monkeypatch: pytest.MonkeyPatch) -> None:
    _deny_external_access(monkeypatch)
    baseline_plan = build_kis_intraday_cpu_campaign_plan(
        _catalog(),
        session_dates=_SESSION_DATES,
        campaign_id="window-matrix-unit",
    )
    changed_plan = build_kis_intraday_cpu_campaign_plan(
        _catalog(later_validation_shift=Decimal("30")),
        session_dates=_SESSION_DATES,
        campaign_id="window-matrix-unit",
    )

    _, baseline_development, _ = window_matrix._build_matrix_inputs(baseline_plan)[0]
    _, changed_development, _ = window_matrix._build_matrix_inputs(changed_plan)[0]
    baseline_model = window_matrix._fit_logistic(
        baseline_development,
        tuple(sample.target_label for sample in baseline_development),
    )
    changed_model = window_matrix._fit_logistic(
        changed_development,
        tuple(sample.target_label for sample in changed_development),
    )

    assert baseline_development == changed_development
    assert baseline_model == changed_model


def test_window_matrix_block_permutation_preserves_whole_session_label_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    plan = build_kis_intraday_cpu_campaign_plan(
        _catalog(),
        session_dates=_SESSION_DATES,
        campaign_id="window-matrix-unit",
    )
    _, development, _ = window_matrix._build_matrix_inputs(plan)[0]
    permuted = window_matrix._permuted_block_labels(development, 1, phase="development")
    original_blocks = _label_blocks(development, tuple(item.target_label for item in development))
    permuted_blocks = _label_blocks(development, permuted)

    assert sorted(permuted) == sorted(sample.target_label for sample in development)
    assert set(permuted_blocks.values()).issubset(set(original_blocks.values()))


def test_window_matrix_records_input_unavailable_after_precommit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        window_matrix,
        "_build_matrix_inputs",
        lambda _plan: (_ for _ in ()).throw(window_matrix._InputUnavailable("unit")),
    )
    artifact_root = tmp_path / "model-artifacts"

    run = window_matrix.run_kis_intraday_window_matrix_preflight(
        _catalog(),
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        run_label="unavailable-r1",
        repo_root=Path.cwd(),
    )

    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert run.status == "input_unavailable"
    assert run.structure_gate == "input_unavailable"
    assert run.cell_results == ()
    assert run.precommit_path.exists()
    assert payload["matrix"]["comparison_materialized"] is False
    assert payload["gate"]["cuda_eligible"] is False


def test_window_matrix_rejects_a_repo_artifact_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        window_matrix.run_kis_intraday_window_matrix_preflight(
            _catalog(),
            session_dates=_SESSION_DATES,
            artifact_root=repo_root / "model-artifacts",
            run_label="invalid-root",
            repo_root=repo_root,
        )


def _shorten_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_matrix, "KIS_INTRADAY_WINDOW_MATRIX_NULL_REPLICATES", 3)
    monkeypatch.setattr(window_matrix, "KIS_INTRADAY_WINDOW_MATRIX_OPTIMIZER_STEPS", 3)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("window matrix preflight must not open the network")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("window matrix preflight must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _label_blocks(
    samples: tuple[window_matrix._WindowSample, ...],
    labels: tuple[int, ...],
) -> dict[date, tuple[int, ...]]:
    blocks: dict[date, list[int]] = defaultdict(list)
    for sample, label in zip(samples, labels, strict=True):
        blocks[sample.session_date].append(label)
    return {session_date: tuple(values) for session_date, values in blocks.items()}


def _catalog(*, later_validation_shift: Decimal = Decimal("0")) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        direction = Decimal("1") if session_index % 2 == 0 else Decimal("-1")
        shift = later_validation_shift if session_index >= 11 else Decimal("0")
        for minute in range(390):
            opened = (
                Decimal("100")
                + Decimal(session_index)
                + direction * Decimal(minute) / 100
                + shift
            )
            closed = opened + direction * Decimal("0.02")
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
                    volume=Decimal("1000") + Decimal(minute) + Decimal(session_index),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.window-matrix-unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("D:/market_data/unit-kis-window-matrix-index.json"),
        bars=tuple(bars),
    )


_SESSION_DATES = (
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
)
