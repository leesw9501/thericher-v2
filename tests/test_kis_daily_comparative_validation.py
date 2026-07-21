from __future__ import annotations

import json
import os
import socket
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KisPaperPrivateDailyCatalog,
    slice_kis_paper_private_daily_catalog,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.kis_daily_comparative_validation import (
    KisDailyComparativeBaselineConfig,
    PrecontractExposure,
    freeze_kis_daily_comparative_contract,
    run_kis_daily_comparative_cpu_baselines,
)

_SYMBOLS = ("QQQ", "SPY", "IWM")
_DATASET_HASH = "sha256:" + "a" * 64


def test_freezes_burned_holdout_and_runs_isolated_local_paper_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _catalog(tmp_path, session_count=154)
    exposure = PrecontractExposure(
        source_id="prior-relative-strength-smoke",
        first_observed_session=catalog.common_sessions[120],
        last_observed_session=catalog.common_sessions[-1],
        evidence_sha256="sha256:" + "b" * 64,
        evidence_reference="D:/artifacts/prior-relative-strength-smoke/run.json",
    )
    contract = freeze_kis_daily_comparative_contract(
        catalog,
        contract_id="unit-comparative-contract",
        precontract_exposure=exposure,
    )

    assert contract.development.session_count == 90
    assert contract.purge.session_count == 2
    assert contract.validation.session_count == 30
    assert contract.embargo.session_count == 2
    assert contract.sealed_holdout.session_count == 30
    assert contract.sealed_holdout.state == "burned_precontract"
    assert contract.sealed_holdout.first_session == catalog.common_sessions[124]
    assert contract.sealed_holdout.last_session == catalog.common_sessions[-1]
    assert (
        contract.historical_interpretation
        == "historical_comparison_only_prospective_holdout_required"
    )

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("comparative baseline must not open a network connection")

    def no_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("comparative baseline must not read credentials")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(os, "getenv", no_environment)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result = run_kis_daily_comparative_cpu_baselines(
        catalog,
        contract=contract,
        config=KisDailyComparativeBaselineConfig(run_id="unit-comparative-run"),
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
    )

    assert result.contract_path.is_relative_to(tmp_path / "artifacts")
    assert not result.contract_path.is_relative_to(repo_root)
    assert len(result.relative_strength_runs) == 2
    assert [run.comparative_phase for run in result.relative_strength_runs] == [
        "development",
        "validation",
    ]
    assert [run.common_session_count for run in result.relative_strength_runs] == [90, 30]
    assert all(run.all_fills_local_paper for run in result.relative_strength_runs)
    assert len(result.comparator_runs) == 8
    assert {run.phase for run in result.comparator_runs} == {"development", "validation"}
    development_counts = {
        run.common_session_count
        for run in result.comparator_runs
        if run.phase == "development"
    }
    validation_counts = {
        run.common_session_count
        for run in result.comparator_runs
        if run.phase == "validation"
    }
    assert development_counts == {90}
    assert validation_counts == {30}
    assert all(run.all_fills_local_paper for run in result.comparator_runs)
    assert all(
        run.event_jsonl_path.is_relative_to(tmp_path / "artifacts")
        for run in result.comparator_runs
    )
    cash_runs = [run for run in result.comparator_runs if run.comparator == "cash"]
    invested_runs = [run for run in result.comparator_runs if run.comparator == "always_invested"]
    assert len(cash_runs) == 2
    assert len(invested_runs) == 6
    assert all(run.local_paper_fill_count == 0 for run in cash_runs)
    assert all(run.local_paper_fill_count == 2 for run in invested_runs)

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["contract_hash"] == contract.contract_hash
    assert summary["historical_interpretation"] == contract.historical_interpretation
    assert {entry["common_session_count"] for entry in summary["relative_strength_runs"]} == {
        90,
        30,
    }
    first_manifest = json.loads(invested_runs[0].run_manifest_path.read_text(encoding="utf-8"))
    assert first_manifest["execution"]["broker"] == "local_paper"
    assert first_manifest["contract_hash"] == contract.contract_hash
    assert first_manifest["evidence"]["expected_local_paper_fill_count"] == 2
    relative_manifests = [
        json.loads(run.run_manifest_path.read_text(encoding="utf-8"))
        for run in result.relative_strength_runs
    ]
    assert {
        (
            manifest["comparative_contract"]["contract_hash"],
            manifest["comparative_contract"]["phase"],
        )
        for manifest in relative_manifests
    } == {
        (contract.contract_hash, "development"),
        (contract.contract_hash, "validation"),
    }
    contract_payload = json.loads(result.contract_path.read_text(encoding="utf-8"))
    holdout = contract_payload["geometry"]["sealed_holdout"]
    exposure_payload = contract_payload["precontract_exposure"]
    assert holdout["first_session"] <= exposure_payload["last_observed_session"]
    assert exposure_payload["evidence_reference"].endswith("run.json")


def test_data_owned_slice_has_new_hash_and_rejects_invalid_ranges(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, session_count=30)
    sliced = slice_kis_paper_private_daily_catalog(catalog, start_index=3, stop_index=27)

    assert sliced.dataset_id.endswith(":slice-3-27")
    assert sliced.dataset_hash != catalog.dataset_hash
    assert sliced.common_sessions == catalog.common_sessions[3:27]
    assert all(len(stream.bars) == 24 for stream in sliced.bars_by_symbol.values())
    assert all(
        stream.dataset_hash == sliced.dataset_hash for stream in sliced.bars_by_symbol.values()
    )
    with pytest.raises(ValueError, match="slice range"):
        slice_kis_paper_private_daily_catalog(catalog, start_index=10, stop_index=10)


def _catalog(tmp_path: Path, *, session_count: int) -> KisPaperPrivateDailyCatalog:
    sessions = tuple(date(2025, 1, 2) + timedelta(days=index) for index in range(session_count))
    steps = {"QQQ": Decimal("2"), "SPY": Decimal("1"), "IWM": Decimal("-0.5")}
    starts = {"QQQ": Decimal("100"), "SPY": Decimal("200"), "IWM": Decimal("300")}
    streams = {}
    for symbol in _SYMBOLS:
        bars = tuple(
            _bar(
                symbol=symbol,
                session=session,
                close=starts[symbol] + steps[symbol] * index,
            )
            for index, session in enumerate(sessions)
        )
        streams[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
            dataset_hash=_DATASET_HASH,
            source_path=tmp_path / "index.json",
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        dataset_hash=_DATASET_HASH,
        index_hash="sha256:" + "c" * 64,
        index_path=tmp_path / "index.json",
        source_root=tmp_path,
        adjustment_mode="MODP=0_unadjusted",
        bars_by_symbol=MappingProxyType(streams),
        common_sessions=sessions,
        raw_price_limitations=("MODP=0_unadjusted",),
    )


def _bar(*, symbol: str, session: date, close: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )
