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
from thericher_v2.research.kis_intraday_cuda_sequence_smoke import (
    KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES,
    KisIntradayCudaSequenceInput,
    build_kis_intraday_cuda_sequence_input,
    run_kis_intraday_cuda_sequence_smoke,
)


def test_cuda_sequence_input_uses_development_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    baseline = build_kis_intraday_cuda_sequence_input(
        _catalog(),
        session_dates=_SESSION_DATES,
    )
    changed_later_source = build_kis_intraday_cuda_sequence_input(
        _catalog(later_session_price_shift=Decimal("30")),
        session_dates=_SESSION_DATES,
    )

    assert baseline.contract.contract_hash != changed_later_source.contract.contract_hash
    assert baseline.development_input_hash == changed_later_source.development_input_hash
    assert baseline.sequences == changed_later_source.sequences
    assert baseline.labels == changed_later_source.labels
    assert len(baseline.sequences) == 10 * 299
    assert all(len(sequence) == 90 for sequence in baseline.sequences)
    assert all(
        len(row) == len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES)
        for sequence in baseline.sequences
        for row in sequence
    )


def test_cuda_sequence_smoke_is_offline_and_writes_only_external_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    seen: dict[str, object] = {}

    def trainer(sequence_input: KisIntradayCudaSequenceInput) -> dict[str, object]:
        sequences = sequence_input.sequences
        seen["sample_count"] = len(sequences)
        return {
            "backend": "unit_cuda",
            "architecture": "gru_fixed_smoke",
            "sample_count": len(sequences),
            "sequence_length": 90,
            "feature_count": 3,
            "epochs": 8,
            "initial_loss": "0.70000000",
            "final_loss": "0.60000000",
        }

    run = run_kis_intraday_cuda_sequence_smoke(
        _catalog(),
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=Path.cwd(),
        trainer=trainer,
    )

    assert seen["sample_count"] == 10 * 299
    assert run.summary_path.is_relative_to(artifact_root)
    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "offline_cuda_research"
    assert payload["candidate_comparison_materialized"] is False
    assert payload["sealed_confirmation_materialized"] is False
    assert payload["artifact_policy"] == {
        "root": str(artifact_root.resolve()),
        "repo_storage_allowed": False,
        "checkpoint_written": False,
    }
    assert payload["training"]["backend"] == "unit_cuda"
    assert "KIS_PAPER_" not in run.summary_path.read_text(encoding="utf-8")


def test_cuda_sequence_smoke_rejects_a_repo_artifact_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_kis_intraday_cuda_sequence_smoke(
            _catalog(),
            session_dates=_SESSION_DATES,
            artifact_root=repo_root / "model-artifacts",
            run_label="invalid-root",
            repo_root=repo_root,
            trainer=lambda _input: {},
        )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS CUDA sequence smoke must not open the network")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS CUDA sequence smoke must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _catalog(*, later_session_price_shift: Decimal = Decimal("0")) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        shift = later_session_price_shift if session_index >= 11 else Decimal("0")
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
    hash_character = "b" if later_session_price_shift else "a"
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.cuda-unit-v1",
        dataset_hash="sha256:" + hash_character * 64,
        source_path=Path(f"D:/market_data/unit-kis-cuda-index-{hash_character}.json"),
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
