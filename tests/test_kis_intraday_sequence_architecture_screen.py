from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.kis_intraday_cuda_sequence_smoke import (
    build_kis_intraday_cuda_sequence_input,
)
from thericher_v2.research.kis_intraday_sequence_architecture_screen import (
    KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS,
    KIS_INTRADAY_SEQUENCE_ARCHITECTURES,
    KisIntradaySequenceArchitectureSpec,
    KisIntradayTrainedSequenceArchitecture,
    run_kis_intraday_sequence_architecture_screen,
)


def test_sequence_screen_precommits_before_comparison_and_uses_only_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    run_label = "unit-r1"
    precommit_path = (
        artifact_root
        / "kis-intraday-sequence-architecture-screen"
        / run_label
        / "precommit.json"
    )
    trained_inputs: list[tuple[str, str, int]] = []
    comparison_seen: dict[str, object] = {}

    def trainer(
        development_input,
        spec: KisIntradaySequenceArchitectureSpec,
    ) -> KisIntradayTrainedSequenceArchitecture:
        assert precommit_path.exists()
        trained_inputs.append(
            (
                spec.architecture_id,
                development_input.development_input_hash,
                len(development_input.sequences),
            )
        )
        return _trained_architecture(development_input, spec)

    def comparison_builder(contract):
        payload = json.loads(precommit_path.read_text(encoding="utf-8"))
        assert payload["comparison_materialized"] is False
        assert payload["reporting"] == {
            "all_architectures_reported_jointly": True,
            "ensemble_allowed": False,
            "selection_allowed": False,
            "winner": None,
        }
        comparison_seen["precommit_hash"] = payload["precommit_hash"]
        from thericher_v2.research.kis_intraday_feature_breadth import (
            build_kis_intraday_feature_candidate_comparison_samples,
        )

        return build_kis_intraday_feature_candidate_comparison_samples(contract)

    run = run_kis_intraday_sequence_architecture_screen(
        _catalog(),
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        work_root=tmp_path / "work",
        run_label=run_label,
        repo_root=Path.cwd(),
        trainer=trainer,
        comparison_samples_builder=comparison_builder,
    )

    assert [item[0] for item in trained_inputs] == list(KIS_INTRADAY_SEQUENCE_ARCHITECTURES)
    assert {item[1] for item in trained_inputs} == {run.development_input.development_input_hash}
    assert {item[2] for item in trained_inputs} == {10 * 299}
    assert comparison_seen["precommit_hash"] == run.precommit_hash
    assert tuple(item.architecture_id for item in run.architecture_runs) == (
        KIS_INTRADAY_SEQUENCE_ARCHITECTURES
    )
    assert all(item.replay.fill_source == LOCAL_PAPER_SOURCE for item in run.architecture_runs)
    assert all(
        item.replay.replay_evidence.fill_source == LOCAL_PAPER_SOURCE
        for item in run.architecture_runs
    )
    assert all(item.replay.result.trades for item in run.architecture_runs)
    assert run.precommit_path.is_relative_to(artifact_root)
    assert run.summary_path.is_relative_to(artifact_root)

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["development_input_hash"] == run.development_input.development_input_hash
    assert [item["architecture_id"] for item in precommit["architectures"]] == list(
        KIS_INTRADAY_SEQUENCE_ARCHITECTURES
    )
    assert summary["precommit"]["written_before_comparison_materialized"] is True
    assert summary["candidate_comparison"]["winner"] is None
    assert summary["candidate_comparison"]["selection_allowed"] is False
    assert summary["sealed_confirmation"]["materialized"] is False
    assert all(item["fill_source"] == LOCAL_PAPER_SOURCE for item in summary["architectures"])
    assert "KIS_PAPER_" not in run.summary_path.read_text(encoding="utf-8")


def test_sequence_precommit_inputs_stay_development_only_when_later_data_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    baseline = build_kis_intraday_cuda_sequence_input(_catalog(), session_dates=_SESSION_DATES)
    changed_later_source = build_kis_intraday_cuda_sequence_input(
        _catalog(later_confirmation_price_shift=Decimal("30")),
        session_dates=_SESSION_DATES,
    )

    assert baseline.contract.contract_hash != changed_later_source.contract.contract_hash
    assert baseline.development_input_hash == changed_later_source.development_input_hash
    assert tuple(item.architecture_id for item in KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS) == (
        KIS_INTRADAY_SEQUENCE_ARCHITECTURES
    )


def test_sequence_screen_rejects_a_repo_artifact_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_kis_intraday_sequence_architecture_screen(
            _catalog(),
            session_dates=_SESSION_DATES,
            artifact_root=repo_root / "model-artifacts",
            work_root=tmp_path / "work",
            run_label="invalid-root",
            repo_root=repo_root,
            trainer=_trained_architecture,
        )


def _trained_architecture(
    development_input,
    spec: KisIntradaySequenceArchitectureSpec,
) -> KisIntradayTrainedSequenceArchitecture:
    return KisIntradayTrainedSequenceArchitecture(
        spec=spec,
        training={
            "backend": "unit_cuda",
            "architecture": spec.architecture_id,
            "sample_count": len(development_input.sequences),
            "sequence_length": 90,
            "feature_count": 3,
            "epochs": spec.epochs,
            "learning_rate": spec.learning_rate,
            "initial_loss": "0.70000000",
            "final_loss": "0.60000000",
        },
        predict_probabilities=lambda batch: tuple(0.75 for _ in batch),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS intraday sequence screen must not open the network")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS intraday sequence screen must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _catalog(*, later_confirmation_price_shift: Decimal = Decimal("0")) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        shift = later_confirmation_price_shift if session_index >= 16 else Decimal("0")
        for minute in range(390):
            opened = (
                Decimal("100")
                + Decimal(session_index)
                + Decimal(minute) / Decimal("100")
                + shift
            )
            closed = opened + Decimal("0.02")
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=closed + Decimal("0.01"),
                    low=opened - Decimal("0.01"),
                    close=closed,
                    volume=Decimal("1000") + Decimal(minute),
                    complete=True,
                )
            )
    hash_character = "b" if later_confirmation_price_shift else "a"
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.sequence-unit-v1",
        dataset_hash="sha256:" + hash_character * 64,
        source_path=Path(f"D:/market_data/unit-kis-sequence-index-{hash_character}.json"),
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
