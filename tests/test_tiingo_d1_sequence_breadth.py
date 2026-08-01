from __future__ import annotations

import json
import socket
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.research.tiingo_d1_sequence_breadth as sequence_breadth
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
    TiingoEtfDailySnapshot,
)
from thericher_v2.research.tiingo_d1_sequence_breadth import (
    TIINGO_D1_SEQUENCE_GPU_ARCHITECTURES,
    build_tiingo_d1_sequence_input,
    run_tiingo_d1_sequence_cpu,
    run_tiingo_d1_sequence_cuda,
)


def test_sequence_input_has_purged_non_overlapping_dependencies() -> None:
    sequence_input = build_tiingo_d1_sequence_input(_snapshot())

    assert sequence_input.gpu_eligible is True
    assert sequence_input.config.safe_payload()["purge_sessions"] == 22
    assert (
        sequence_input.config.safe_payload()["target"]
        == "next_session_open_to_close_direction_non_up_is_zero"
    )
    assert (
        sequence_input.config.safe_payload()["feature_discontinuity_window"]
        == "t-L+1_through_t_only"
    )
    for key, development in sequence_input.development_samples.items():
        validation = sequence_input.validation_samples[key]
        assert min(sample.dependency_start_index for sample in validation) > max(
            sample.dependency_end_index for sample in development
        )

    safe_payload = json.dumps(sequence_input.safe_payload(), sort_keys=True)
    assert "123.456789" not in safe_payload
    assert "raw_market_data" not in safe_payload


def test_input_identity_excludes_runtime_normalizer_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    initial = build_tiingo_d1_sequence_input(snapshot)
    original_fit = sequence_breadth._fit_normalizer

    def perturbed_fit(samples: object) -> tuple[tuple[float, ...], tuple[float, ...]]:
        means, scales = original_fit(samples)
        return (means[0] + 0.000001, *means[1:]), scales

    monkeypatch.setattr(sequence_breadth, "_fit_normalizer", perturbed_fit)
    perturbed = build_tiingo_d1_sequence_input(snapshot)

    assert perturbed.input_hash == initial.input_hash
    assert perturbed.normalizer_hashes != initial.normalizer_hashes


def test_target_day_jump_is_not_a_feature_filter_but_event_and_feature_jumps_are() -> None:
    rows = list(_rows("SPY", count=1_000, start_price=Decimal("100")))
    decision_index = 300
    rows[decision_index + 1] = replace(
        rows[decision_index + 1],
        close=rows[decision_index + 1].close * Decimal("1.50"),
    )

    assert (
        sequence_breadth._sample_exclusion(
            tuple(rows),
            decision_index=decision_index,
            length=5,
            discontinuity_limit=Decimal("0.20"),
        )
        is None
    )
    rows[decision_index] = replace(
        rows[decision_index],
        close=rows[decision_index].close * Decimal("1.50"),
    )
    assert (
        sequence_breadth._sample_exclusion(
            tuple(rows),
            decision_index=decision_index,
            length=5,
            discontinuity_limit=Decimal("0.20"),
        )
        == "feature_discontinuity"
    )
    rows[decision_index] = replace(
        rows[decision_index],
        close=rows[decision_index - 1].close * Decimal("1.01"),
    )
    rows[decision_index + 1] = replace(
        rows[decision_index + 1],
        div_cash=Decimal("0.01"),
    )
    assert (
        sequence_breadth._sample_exclusion(
            tuple(rows),
            decision_index=decision_index,
            length=5,
            discontinuity_limit=Decimal("0.20"),
        )
        == "event"
    )


def test_cpu_and_mocked_cuda_write_external_source_safe_artifacts_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot(start_price=Decimal("123.456789"))

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("sequence campaign must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    cpu_run = run_tiingo_d1_sequence_cpu(
        snapshot,
        artifact_root=artifact_root,
        run_label="cpu-unit-run",
        repo_root=repo_root,
    )
    cpu_summary = json.loads(cpu_run.summary_path.read_text(encoding="utf-8"))

    assert cpu_run.precommit_path.is_relative_to(artifact_root)
    assert cpu_run.summary_path.is_relative_to(artifact_root)
    assert cpu_summary["input_hash"] == cpu_run.input.input_hash
    assert cpu_summary["gpu_eligibility"]["eligible"] is True
    assert cpu_summary["promotion_allowed"] is False
    assert "123.456789" not in cpu_run.summary_path.read_text(encoding="utf-8")
    assert "KIS_" not in cpu_run.summary_path.read_text(encoding="utf-8")

    cuda_run = run_tiingo_d1_sequence_cuda(
        snapshot,
        cpu_summary_path=cpu_run.summary_path,
        artifact_root=artifact_root,
        run_label="cuda-unit-run",
        repo_root=repo_root,
        trainer=_fake_cuda_breadth,
    )
    cuda_summary = json.loads(cuda_run.summary_path.read_text(encoding="utf-8"))
    assert cuda_summary["gpu_appointment_created"] is True
    assert cuda_summary["checkpoint_written"] is False
    assert cuda_summary["input_hash"] == cpu_run.input.input_hash
    assert cuda_summary["promotion_allowed"] is False

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_tiingo_d1_sequence_cpu(
            snapshot,
            artifact_root=repo_root / "artifacts",
            run_label="repo-unit-run",
            repo_root=repo_root,
        )


def test_cuda_requires_matching_eligible_cpu_evidence(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot()
    cpu_run = run_tiingo_d1_sequence_cpu(
        snapshot,
        artifact_root=artifact_root,
        run_label="cpu-match-run",
        repo_root=repo_root,
    )
    summary = json.loads(cpu_run.summary_path.read_text(encoding="utf-8"))
    summary["input_hash"] = "sha256:" + "f" * 64
    mismatched_summary_path = tmp_path / "mismatched-cpu-summary.json"
    mismatched_summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="input identity does not match"):
        run_tiingo_d1_sequence_cuda(
            snapshot,
            cpu_summary_path=mismatched_summary_path,
            artifact_root=artifact_root,
            run_label="cuda-mismatch-run",
            repo_root=repo_root,
            trainer=_fake_cuda_breadth,
        )


def test_docker_model_artifact_mount_is_external_but_other_app_paths_are_not() -> None:
    container_repo = Path("/app").resolve()

    assert sequence_breadth._is_container_external_artifact_root(
        (container_repo / "model_artifacts").resolve(),
        container_repo,
    )
    assert not sequence_breadth._is_container_external_artifact_root(
        (container_repo / "market_data").resolve(),
        container_repo,
    )


def _fake_cuda_breadth(_sequence_input: object) -> dict[str, object]:
    return {
        "backend": "torch_cuda",
        "device_count": 1,
        "cuda_version": "fixture",
        "models": [
            {
                "architecture_id": architecture_id,
                "sequence_length": length,
                "checkpoint_written": False,
                "validation_cells": [
                    {"symbol": symbol}
                    for symbol in TIINGO_ETF_D1_SYMBOLS
                ],
            }
            for length in (5, 20)
            for architecture_id in TIINGO_D1_SEQUENCE_GPU_ARCHITECTURES
        ],
        "candidate_selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
    }


def _snapshot(
    *,
    count: int = 1_000,
    start_price: Decimal = Decimal("100"),
) -> LoadedTiingoEtfDailySnapshot:
    rows_by_symbol = {
        symbol: _rows(
            symbol,
            count=count,
            start_price=start_price + Decimal(index * 10),
        )
        for index, symbol in enumerate(TIINGO_ETF_D1_SYMBOLS)
    }
    snapshot = TiingoEtfDailySnapshot(
        snapshot_dir=Path(
            "D:/market_data/us_equities/tiingo_etf_daily/canonical/"
            "snapshot=fixture-tiingo-etf-d1-r1"
        ),
        dataset_id="us_equities.tiingo_etf_daily.snapshot=fixture-tiingo-etf-d1-r1",
        dataset_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        raw_hashes={
            symbol: "sha256:" + character * 64
            for symbol, character in zip(TIINGO_ETF_D1_SYMBOLS, "cde", strict=True)
        },
        session_counts={symbol: count for symbol in TIINGO_ETF_D1_SYMBOLS},
        date_ranges={
            symbol: (rows[0].session_date, rows[-1].session_date)
            for symbol, rows in rows_by_symbol.items()
        },
        event_session_counts={symbol: 0 for symbol in TIINGO_ETF_D1_SYMBOLS},
        row_count=count * len(TIINGO_ETF_D1_SYMBOLS),
        free_percent=40.0,
    )
    return LoadedTiingoEtfDailySnapshot(snapshot=snapshot, rows_by_symbol=rows_by_symbol)


def _rows(
    symbol: str,
    *,
    count: int,
    start_price: Decimal,
) -> tuple[TiingoEtfDailyRow, ...]:
    rows: list[TiingoEtfDailyRow] = []
    for index in range(count):
        trend = Decimal(index) / Decimal("100")
        wiggle = Decimal("0.08") if index % 2 else Decimal("-0.06")
        close = start_price + trend + wiggle
        open_price = close - Decimal("0.03")
        rows.append(
            TiingoEtfDailyRow(
                symbol=symbol,
                session_date=date(2020, 1, 1) + timedelta(days=index),
                open=open_price,
                high=close + Decimal("0.02"),
                low=open_price - Decimal("0.02"),
                close=close,
                volume=Decimal("1000") + Decimal(index % 7),
                div_cash=Decimal("0"),
                split_factor=Decimal("1"),
            )
        )
    return tuple(rows)
