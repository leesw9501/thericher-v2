from __future__ import annotations

import importlib.util
import json
import math
import os
import socket
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, ModuleType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KisPaperPrivateDailyCatalog,
    slice_kis_paper_private_daily_catalog,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.daily_trade_quality_gate import (
    DailyTradeQualityGateConfig,
    run_daily_trade_quality_gate,
)
from thericher_v2.research.kis_daily_comparative_validation import (
    KisDailyComparativeContract,
    PrecontractExposure,
    freeze_kis_daily_comparative_contract,
)

_SYMBOLS = ("QQQ", "SPY", "IWM")


def test_runs_frozen_l2_gate_offline_with_local_paper_only(tmp_path: Path, monkeypatch) -> None:
    full_catalog = _catalog(tmp_path, session_count=374)
    contract = _contract(full_catalog)
    catalog = _prefix(full_catalog, contract)

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("trade-quality gate must not open a network connection")

    def no_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("trade-quality gate must not read credentials")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(os, "getenv", no_environment)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result = run_daily_trade_quality_gate(
        catalog,
        contract=contract,
        config=DailyTradeQualityGateConfig(
            run_id="unit-l2-gate",
            bootstrap_samples=64,
        ),
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
    )

    assert result.status in {"retired", "retrospective_pass"}
    assert result.development_entry_count >= 100
    assert result.development_positive_count >= 25
    assert result.development_negative_count >= 25
    assert result.model_path is not None
    assert result.model_path.is_relative_to(tmp_path / "artifacts")
    assert result.summary_path.is_relative_to(tmp_path / "artifacts")
    assert result.validation_selector is not None
    assert result.validation_candidate is not None
    assert result.validation_selector.scheduled_decision_count == 26
    assert result.validation_candidate.accepted_trade_count <= (
        result.validation_selector.accepted_trade_count
    )
    assert result.validation_cash_mean_return == 0.0
    assert result.all_fills_local_paper is True

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["execution"]["broker"] == "local_paper"
    assert summary["execution"]["all_fills_local_paper"] is True
    assert summary["historical_interpretation"] == (
        "historical_comparison_only_prospective_holdout_required"
    )
    assert summary["validation"]["stress_slippage_bps_per_side"] == "2"
    assert summary["config_sha256"].startswith("sha256:")
    contract_path = result.summary_path.parent / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["config_sha256"] == summary["config_sha256"]
    assert contract["config"]["bootstrap_block_size"] == 5
    assert contract["target"]["entry"] == "t_plus_1_open"
    assert contract["target"]["exit"] == "t_plus_2_open"
    assert contract["compute"] == {"runtime": "cpu_only", "gpu_used": False}

    assert result.model_path is not None
    model = json.loads(result.model_path.read_text(encoding="utf-8"))
    assert model["config_sha256"] == summary["config_sha256"]
    events_path = result.summary_path.parent / "replays" / "development_selector" / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
    ]
    fills = [event for event in events if event["event_type"] == "fill"]
    assert fills
    assert all(event["payload"]["source"] == "local_paper" for event in fills)
    entry_fill, exit_fill = fills[:2]
    assert entry_fill["payload"]["side"] == "buy"
    assert exit_fill["payload"]["side"] == "sell"
    assert entry_fill["payload"]["client_order_id"].removesuffix("-entry") == exit_fill[
        "payload"
    ]["client_order_id"].removesuffix("-exit")
    assert datetime.fromisoformat(exit_fill["created_at"]) - datetime.fromisoformat(
        entry_fill["created_at"]
    ) == timedelta(days=1)
    assert not list(repo_root.iterdir())


def test_core_rejects_full_catalog_before_burned_holdout_materialization(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, session_count=374)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="catalog prefix"):
        run_daily_trade_quality_gate(
            catalog,
            contract=_contract(catalog),
            config=DailyTradeQualityGateConfig(
                run_id="full-catalog-rejected",
                bootstrap_samples=32,
            ),
            artifact_root=tmp_path / "artifacts",
            repo_root=repo_root,
        )


def test_validation_values_do_not_change_development_model(tmp_path: Path) -> None:
    first_full = _catalog(tmp_path / "first", session_count=374)
    second_full = _catalog(
        tmp_path / "second",
        session_count=374,
        validation_offset=Decimal("1000"),
    )
    first_contract = _contract(first_full)
    second_contract = _contract(second_full)
    first = _prefix(first_full, first_contract)
    second = _prefix(second_full, second_contract)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    first_result = run_daily_trade_quality_gate(
        first,
        contract=first_contract,
        config=DailyTradeQualityGateConfig(
            run_id="first-validation-isolation",
            bootstrap_samples=32,
        ),
        artifact_root=tmp_path / "first-artifacts",
        repo_root=repo_root,
    )
    second_result = run_daily_trade_quality_gate(
        second,
        contract=second_contract,
        config=DailyTradeQualityGateConfig(
            run_id="second-validation-isolation",
            bootstrap_samples=32,
        ),
        artifact_root=tmp_path / "second-artifacts",
        repo_root=repo_root,
    )

    assert first_result.model_path is not None
    assert second_result.model_path is not None
    assert first_result.model_path.read_bytes() == second_result.model_path.read_bytes()


def test_gate_accepts_only_the_prefix_through_its_embargo(tmp_path: Path) -> None:
    full_catalog = _catalog(tmp_path / "full", session_count=374)
    contract = _contract(full_catalog)
    prefix = _prefix(full_catalog, contract)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = run_daily_trade_quality_gate(
        prefix,
        contract=contract,
        config=DailyTradeQualityGateConfig(run_id="prefix-l2-gate", bootstrap_samples=32),
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
    )

    assert result.status in {"retired", "retrospective_pass"}
    assert result.model_path is not None
    assert len(prefix.common_sessions) == contract.embargo.stop_index


def test_retired_development_gate_does_not_create_a_candidate_model(tmp_path: Path) -> None:
    full_catalog = _catalog(tmp_path, session_count=154)
    contract = _contract(full_catalog)
    catalog = _prefix(full_catalog, contract)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result = run_daily_trade_quality_gate(
        catalog,
        contract=contract,
        config=DailyTradeQualityGateConfig(run_id="short-l2-gate", bootstrap_samples=16),
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
    )

    assert result.status == "retired"
    assert "development_eligible_entries_below_100" in result.stop_reasons
    assert result.model_path is None
    assert result.validation_candidate is None
    assert result.all_fills_local_paper is True


def test_cli_uses_frozen_prefix_contract_and_loader_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner_module()
    observed: dict[str, object] = {}
    catalog = SimpleNamespace(
        dataset_id=runner._FROZEN_DATASET_ID,
        index_hash=runner._FROZEN_INDEX_HASH,
        common_sessions=(runner._FROZEN_PREFIX_FIRST_SESSION,)
        + (runner._FROZEN_PREFIX_FIRST_SESSION,) * (runner._FROZEN_PREFIX_SESSION_COUNT - 2)
        + (runner._FROZEN_PREFIX_LAST_SESSION,),
    )

    def load_catalog(*args: object, **kwargs: object) -> SimpleNamespace:
        observed["loader_args"] = args
        observed["loader_kwargs"] = kwargs
        return catalog

    def run_gate(*args: object, **kwargs: object) -> SimpleNamespace:
        observed["gate_args"] = args
        observed["gate_kwargs"] = kwargs
        return SimpleNamespace(
            run_id="frozen-cli",
            status="retired",
            stop_reasons=("expected",),
            development_entry_count=155,
            all_fills_local_paper=True,
            summary_path=tmp_path / "artifacts" / "summary.json",
        )

    monkeypatch.setattr(runner, "load_kis_paper_private_daily_catalog", load_catalog)
    monkeypatch.setattr(runner, "run_daily_trade_quality_gate", run_gate)

    assert runner.main(
        [
            "--run-id",
            "frozen-cli",
            "--cache-root",
            str(tmp_path / "cache"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--repo-root",
            str(tmp_path / "repo"),
        ]
    ) == 0

    assert observed["loader_args"] == (tmp_path / "cache",)
    assert observed["loader_kwargs"] == {
        "expected_index_hash": runner._FROZEN_INDEX_HASH,
        "end_session": runner._FROZEN_PREFIX_LAST_SESSION,
        "repo_root": tmp_path / "repo",
    }
    gate_kwargs = observed["gate_kwargs"]
    assert isinstance(gate_kwargs, dict)
    contract = gate_kwargs["contract"]
    assert contract.dataset_id == runner._FROZEN_DATASET_ID
    assert contract.dataset_hash == runner._FROZEN_DATASET_HASH
    assert contract.index_hash == runner._FROZEN_INDEX_HASH
    assert contract.common_session_count == runner._FROZEN_COMMON_SESSION_COUNT
    assert contract.embargo.stop_index == runner._FROZEN_PREFIX_SESSION_COUNT
    assert contract.sealed_holdout.stop_index == runner._FROZEN_COMMON_SESSION_COUNT


def _load_runner_module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_daily_three_etf_l2_trade_quality_gate.py"
    spec = importlib.util.spec_from_file_location("daily_trade_quality_gate_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prefix(
    catalog: KisPaperPrivateDailyCatalog,
    contract: KisDailyComparativeContract,
) -> KisPaperPrivateDailyCatalog:
    prefix = slice_kis_paper_private_daily_catalog(
        catalog,
        start_index=0,
        stop_index=contract.embargo.stop_index,
    )
    return replace(prefix, dataset_id=catalog.dataset_id)


def _contract(catalog: KisPaperPrivateDailyCatalog):
    holdout_start = catalog.common_sessions[
        (len(catalog.common_sessions) - 4) * 4 // 5 + 4
    ]
    return freeze_kis_daily_comparative_contract(
        catalog,
        contract_id=f"contract-{len(catalog.common_sessions)}",
        precontract_exposure=PrecontractExposure(
            source_id="historical-smoke",
            first_observed_session=holdout_start,
            last_observed_session=catalog.common_sessions[-1],
            evidence_sha256="sha256:" + "a" * 64,
            evidence_reference="D:/artifacts/historical-smoke/run.json",
        ),
    )


def _catalog(
    tmp_path: Path,
    *,
    session_count: int,
    holdout_offset: Decimal = Decimal("0"),
    validation_offset: Decimal = Decimal("0"),
) -> KisPaperPrivateDailyCatalog:
    sessions = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(session_count))
    usable_sessions = session_count - 4
    development_stop = usable_sessions * 3 // 5
    validation_start = development_stop + 2
    validation_stop = validation_start + usable_sessions // 5
    holdout_start = session_count - ((session_count - 4) // 5)
    streams = {}
    for symbol in _SYMBOLS:
        bars = tuple(
            _bar(
                symbol=symbol,
                session=session,
                index=index,
                holdout_start=holdout_start,
                holdout_offset=holdout_offset,
                validation_start=validation_start,
                validation_stop=validation_stop,
                validation_offset=validation_offset,
            )
            for index, session in enumerate(sessions)
        )
        streams[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
            dataset_hash="sha256:" + "b" * 64,
            source_path=tmp_path / "index.json",
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        dataset_hash="sha256:" + "b" * 64,
        index_hash="sha256:" + "c" * 64,
        index_path=tmp_path / "index.json",
        source_root=tmp_path,
        adjustment_mode="MODP=0_unadjusted",
        bars_by_symbol=MappingProxyType(streams),
        common_sessions=sessions,
        raw_price_limitations=("MODP=0_unadjusted", "corporate_action_semantics_not_qualified"),
    )


def _bar(
    *,
    symbol: str,
    session: date,
    index: int,
    holdout_start: int,
    holdout_offset: Decimal,
    validation_start: int,
    validation_stop: int,
    validation_offset: Decimal,
) -> Bar:
    if symbol == "QQQ":
        close = (
            Decimal("200")
            + Decimal("0.3") * index
            + Decimal("1.5") * Decimal(str(math.sin(index * math.pi / 2)))
        )
    elif symbol == "SPY":
        close = Decimal("200") + Decimal("0.08") * index
    else:
        close = Decimal("200") + Decimal("0.04") * index
    if symbol == "QQQ" and index >= holdout_start:
        close += holdout_offset
    if symbol == "QQQ" and validation_start <= index < validation_stop:
        close += validation_offset
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
