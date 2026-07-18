from __future__ import annotations

import builtins
import csv
import gzip
import hashlib
import io
import json
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import (
    CatalogedCorporateActions,
    build_fixed_etf_daily_raw_subset,
    build_fixed_etf_daily_subset,
    load_cataloged_corporate_actions,
    load_cataloged_yahoo_daily_1d_bars,
)
from thericher_v2.data.corporate_actions import (
    CAMPAIGN_COVERAGE_END,
    CAMPAIGN_COVERAGE_START,
    CORPORATE_ACTION_COLUMNS,
    CORPORATE_ACTION_EVENT_TYPES,
)
from thericher_v2.execution import EmergencyStore
from thericher_v2.research.daily_campaign import (
    DAILY_CANDIDATES,
    DAILY_COMMON_SESSIONS,
    DAILY_EMBARGO_SESSIONS,
    DAILY_EPOCHS,
    DAILY_FEE_BPS,
    DAILY_HIDDEN_UNITS,
    DAILY_LEARNING_RATE,
    DAILY_MAX_TRAINING_RUNS,
    DAILY_PURGE_SESSIONS,
    DAILY_SEED,
    DAILY_SIGNAL_CADENCE,
    DAILY_SLIPPAGE_BPS,
    DAILY_SYMBOLS,
    DAILY_THRESHOLD,
    DAILY_WEIGHT_DECAY,
    DailyCatalogFacts,
    DailyReplayCell,
    build_daily_campaign_plan,
    build_daily_training_batch,
    check_daily_sensitivity,
    eligible_daily_signal_starts_for_dates,
    executable_open_to_open_pnl,
    prepare_daily_explicit_event_replay,
    run_daily_cpu_baselines,
    run_daily_cuda_breadth,
    run_daily_explicit_event_replay,
    write_daily_campaign_summary,
)
from thericher_v2.research.validation import run_local_paper_validation
from thericher_v2.state import EventStore

SOURCE_FIELDS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    "asset_type",
    "yahoo_symbol",
    "source",
)


@pytest.fixture(scope="module")
def daily_plan(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("daily-campaign-data")
    source = root / "source.csv.gz"
    _write_source_snapshot(source)
    r1_root = root / "r1"
    build_fixed_etf_daily_subset(source, r1_root)
    r2_root = root / "r2"
    manifest_path = build_fixed_etf_daily_raw_subset(r1_root, r2_root)
    manifest = json.loads(manifest_path.read_text())
    snapshot = r2_root / "ohlcv_1d.csv.gz"
    cataloged = tuple(
        load_cataloged_yahoo_daily_1d_bars(
            snapshot,
            dataset_id=manifest["dataset_id"],
            expected_dataset_hash=manifest["dataset_hash"],
            symbol=symbol,
        )
        for symbol in DAILY_SYMBOLS
    )
    return build_daily_campaign_plan(
        cataloged,
        catalog_facts=DailyCatalogFacts(
            catalog_id="unit-fixed-etf-catalog",
            constructed_as_of_utc=datetime(2026, 7, 18, tzinfo=UTC),
            development_training_eligible=True,
        ),
        campaign_id="unit-raw-d1-development",
    )


def test_daily_plan_freezes_exact_forward_two_session_boundaries(daily_plan) -> None:
    plan = daily_plan
    fold1, fold2 = plan.folds

    assert len(plan.common_sessions) == DAILY_COMMON_SESSIONS == 896
    assert (
        len(fold1.development),
        len(fold1.purge),
        len(fold1.validation),
        len(plan.embargo_sessions),
        len(fold2.development),
        len(fold2.purge),
        len(fold2.validation),
    ) == (252, 2, 63, 2, 512, 2, 63)
    flattened = (
        *fold1.development,
        *fold1.purge,
        *fold1.validation,
        *plan.embargo_sessions,
        *fold2.development,
        *fold2.purge,
        *fold2.validation,
    )
    assert flattened == plan.common_sessions
    assert len(set(flattened)) == len(flattened)
    assert fold1.validation[-1] < plan.embargo_sessions[0]
    assert plan.embargo_sessions[-1] < fold2.development[0]

    contract = plan.contract
    assert contract.evidence_use == "development"
    assert contract.sealed_holdout is None
    assert contract.catalog.ranking_eligible is False
    assert contract.catalog.sealed_holdout_eligible is False
    assert contract.purge == timedelta(days=DAILY_PURGE_SESSIONS)
    assert contract.embargo == timedelta(days=DAILY_EMBARGO_SESSIONS)
    assert contract.costs.fee_bps == DAILY_FEE_BPS
    assert contract.costs.slippage_bps == DAILY_SLIPPAGE_BPS
    assert contract.deterministic_seed == DAILY_SEED
    assert tuple(item.bars[0].symbol for item in plan.cataloged_bars) == DAILY_SYMBOLS
    assert all(item.bars[0].timeframe == Timeframe.D1 for item in plan.cataloged_bars)
    assert all(item.bars[0].open < Decimal("1000") for item in plan.cataloged_bars)

    assert len(plan.boundary_proofs) == 2
    for proof in plan.boundary_proofs:
        assert len(proof.purge_sessions) == 2
        assert proof.last_development_label_exit < proof.first_validation_entry

    timing = tuple(
        proof
        for fold in plan.folds
        for symbol in DAILY_SYMBOLS
        for proof in plan.execution_timing_proofs(
            symbol,
            fold.fold_id,
            "validation",
            scenario="primary",
        )
    )
    assert timing
    assert all(proof.entry_common_index == proof.signal_common_index + 1 for proof in timing)
    assert all(proof.exit_common_index == proof.signal_common_index + 2 for proof in timing)
    assert any(proof.entry_start - proof.signal_start > timedelta(days=1) for proof in timing)

    with pytest.raises(ValueError, match="input order"):
        build_daily_campaign_plan(
            (plan.cataloged_bars[1], plan.cataloged_bars[0], plan.cataloged_bars[2]),
            catalog_facts=DailyCatalogFacts(
                catalog_id="unit",
                constructed_as_of_utc=datetime(2026, 7, 18, tzinfo=UTC),
                development_training_eligible=True,
            ),
        )

    for unsafe_campaign_id in ("../escape", r"C:\escape", "/tmp/escape", ".", ".."):
        with pytest.raises(ValueError, match="safe path component"):
            build_daily_campaign_plan(
                plan.cataloged_bars,
                catalog_facts=DailyCatalogFacts(
                    catalog_id="unit",
                    constructed_as_of_utc=datetime(2026, 7, 18, tzinfo=UTC),
                    development_training_eligible=True,
                ),
                campaign_id=unsafe_campaign_id,
            )


def test_sensitivity_rejects_all_item_relative_order_reversal() -> None:
    cells = (
        _sensitivity_cell("candidate", "d1-core-lb5", "primary", "6"),
        _sensitivity_cell("candidate", "d1-core-lb5", "factor_sensitivity", "6"),
        _sensitivity_cell("baseline", "always_long", "primary", "5"),
        _sensitivity_cell("baseline", "always_long", "factor_sensitivity", "7"),
    )

    check = check_daily_sensitivity(cells)

    assert check.sign_changes == ()
    assert check.candidate_order_changed is False
    assert check.primary_candidate_order == ("d1-core-lb5",)
    assert check.sensitivity_candidate_order == ("d1-core-lb5",)
    assert check.all_item_primary_order == (
        "candidate:d1-core-lb5",
        "baseline:always_long",
    )
    assert check.all_item_sensitivity_order == (
        "baseline:always_long",
        "candidate:d1-core-lb5",
    )
    assert check.relative_order_changed is True
    assert check.verdict == "unsupported"


def test_explicit_date_mask_uses_inclusive_i_minus_20_through_i_plus_2(
    daily_plan,
) -> None:
    bars = daily_plan.phase_bars("SPY", "fold-1", "validation")
    event_index = 22
    event_dates = frozenset({bars[event_index].start_ts.date()})
    primary = eligible_daily_signal_starts_for_dates(
        daily_plan,
        "SPY",
        "fold-1",
        "validation",
        affected_session_dates=frozenset(),
    )
    explicit = eligible_daily_signal_starts_for_dates(
        daily_plan,
        "SPY",
        "fold-1",
        "validation",
        affected_session_dates=event_dates,
    )
    by_start = {bar.start_ts: index for index, bar in enumerate(bars)}
    excluded_indices = {by_start[start] for start in primary - explicit}
    expected = {
        index
        for index in range(20, len(bars) - 2, DAILY_SIGNAL_CADENCE)
        if index - 20 <= event_index <= index + 2
    }

    assert excluded_indices == expected
    assert min(excluded_indices) + 2 == event_index
    assert max(excluded_indices) - 20 == event_index
    assert daily_plan.eligible_signal_starts(
        "SPY",
        "fold-1",
        "validation",
        scenario="factor_sensitivity",
    ) == eligible_daily_signal_starts_for_dates(
        daily_plan,
        "SPY",
        "fold-1",
        "validation",
        affected_session_dates=frozenset(daily_plan.factor_dates_for("SPY")),
    )
    with pytest.raises(TypeError, match="frozenset of dates"):
        eligible_daily_signal_starts_for_dates(
            daily_plan,
            "SPY",
            "fold-1",
            "validation",
            affected_session_dates=frozenset(
                {datetime(2024, 1, 2, tzinfo=UTC)}
            ),
        )


def test_prepare_explicit_event_replay_is_no_training_and_fixed_36_cells(
    daily_plan,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    actions = _corporate_actions_fixture(daily_plan, tmp_path / "events-success")
    artifact_root, summary_path, summary_hash = _write_source_cuda_summary(
        daily_plan, tmp_path
    )

    def fail_training(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("explicit-event preparation must not train or build batches")

    monkeypatch.setattr(
        "thericher_v2.research.daily_campaign.build_daily_training_batch",
        fail_training,
    )
    monkeypatch.setattr(
        "thericher_v2.research.daily_campaign.train_daily_candidate_torch_cuda",
        fail_training,
    )
    monkeypatch.setattr(
        "thericher_v2.research.daily_campaign.run_daily_cuda_breadth",
        fail_training,
    )
    import torch

    load_calls: list[Path] = []
    original_load = torch.load

    def tracked_cpu_load(path: Path, **kwargs: object):
        assert kwargs == {"map_location": "cpu", "weights_only": True}
        load_calls.append(Path(path))
        return original_load(path, **kwargs)

    def fail_cuda_probe() -> bool:
        raise AssertionError("explicit-event preparation must not inspect or use CUDA")

    monkeypatch.setattr(torch, "load", tracked_cpu_load)
    monkeypatch.setattr(torch.cuda, "is_available", fail_cuda_probe)

    prepared = prepare_daily_explicit_event_replay(
        daily_plan,
        corporate_actions=actions,
        source_summary_path=summary_path,
        expected_source_summary_sha256=summary_hash,
        replay_id="unit-explicit-events-r1",
        artifact_root=artifact_root,
    )

    assert isinstance(actions, CatalogedCorporateActions)
    assert prepared.training_runs == 0
    assert prepared.parent_sensitivity_verdict == "unsupported"
    assert prepared.artifact_root == artifact_root.resolve()
    assert len(prepared.cells) == 36
    assert len(load_calls) == 6
    assert len(set(load_calls)) == 6
    assert sum(cell.kind == "baseline" for cell in prepared.cells) == 18
    assert sum(cell.kind == "candidate" for cell in prepared.cells) == 18
    assert all(
        cell.checkpoint_path is None and cell.checkpoint_sha256 is None
        for cell in prepared.cells
        if cell.kind == "baseline"
    )
    assert all(
        cell.checkpoint_path is not None
        and cell.checkpoint_sha256 == _file_sha256(cell.checkpoint_path)
        for cell in prepared.cells
        if cell.kind == "candidate"
    )
    assert prepared.development_only is True
    assert prepared.retrospective_only is True
    assert prepared.ranking is prepared.promotion is prepared.candidate_selection is False
    assert prepared.sealed_holdout is prepared.profitability_claim is False


def test_run_explicit_event_replay_reuses_cpu_checkpoints_and_local_paper_only(
    daily_plan,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    actions = _corporate_actions_fixture(daily_plan, tmp_path / "events-execute")
    artifact_root, summary_path, summary_hash = _write_source_cuda_summary(
        daily_plan, tmp_path
    )
    torch = pytest.importorskip("torch", reason="requires the research runtime")

    def fail_training(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("explicit-event replay must not train or build batches")

    def fail_cuda_probe() -> bool:
        raise AssertionError("explicit-event replay must not inspect or use CUDA")

    monkeypatch.setattr(
        "thericher_v2.research.daily_campaign.build_daily_training_batch",
        fail_training,
    )
    monkeypatch.setattr(
        "thericher_v2.research.daily_campaign.train_daily_candidate_torch_cuda",
        fail_training,
    )
    monkeypatch.setattr(torch.cuda, "is_available", fail_cuda_probe)

    prepared = prepare_daily_explicit_event_replay(
        daily_plan,
        corporate_actions=actions,
        source_summary_path=summary_path,
        expected_source_summary_sha256=summary_hash,
        replay_id="unit-explicit-events-execute-r1",
        artifact_root=artifact_root,
    )
    result = run_daily_explicit_event_replay(
        daily_plan,
        replay_plan=prepared,
        artifact_root=artifact_root,
        work_root=artifact_root / "daily-campaign" / prepared.replay_id,
    )

    assert len(result.cells) == 36
    assert sum(cell.cell.kind == "baseline" for cell in result.cells) == 18
    assert sum(cell.cell.kind == "candidate" for cell in result.cells) == 18
    assert result.execution_backend == "torch_cpu"
    assert all(cell.replay.fill_source == "local_paper" for cell in result.cells)
    assert all(cell.replay.replay_evidence.fill_source == "local_paper" for cell in result.cells)
    assert all(cell.replay.result.final_position == 0 for cell in result.cells)
    assert all(cell.replay.artifact_path.is_file() for cell in result.cells)
    assert result.summary_sha256 == _file_sha256(result.summary_path)

    payload = json.loads(result.summary_path.read_text())
    assert payload["parent_sensitivity_verdict"] == "unsupported"
    assert payload["execution"] == {
        "backend": "torch_cpu",
        "training_runs": 0,
        "frozen_cells": 36,
        "baseline_cells": 18,
        "candidate_cells": 18,
        "fill_source": "local_paper",
        "all_final_positions_flat": True,
    }
    assert payload["labels"] == {
        "development_only": True,
        "retrospective_only": True,
        "ranking": False,
        "promotion": False,
        "candidate_selection": False,
        "sealed_holdout": False,
        "profitability_claim": False,
    }


def test_prepare_explicit_event_replay_rejects_ineligible_or_tampered_inputs(
    daily_plan,
    tmp_path: Path,
) -> None:
    artifact_root, summary_path, summary_hash = _write_source_cuda_summary(
        daily_plan, tmp_path
    )
    ineligible = _corporate_actions_fixture(
        daily_plan,
        tmp_path / "events-ineligible",
        coverage_status="incomplete",
    )
    with pytest.raises(ValueError, match="not replay eligible"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=ineligible,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-ineligible",
            artifact_root=artifact_root,
        )

    actions = _corporate_actions_fixture(daily_plan, tmp_path / "events-valid")
    with pytest.raises(ValueError, match="summary SHA-256 mismatch"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256="sha256:" + "0" * 64,
            replay_id="unit-explicit-summary-tamper",
            artifact_root=artifact_root,
        )

    valid_r2_manifest_hash = actions.r2_manifest_hash
    object.__setattr__(actions, "r2_manifest_hash", "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="r2 manifest"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-lineage-tamper",
            artifact_root=artifact_root,
        )
    object.__setattr__(actions, "r2_manifest_hash", valid_r2_manifest_hash)

    summary = json.loads(summary_path.read_text())
    summary["sensitivity"]["verdict"] = "supported-with-limits"
    verdict_hash = _rewrite_json(summary_path, summary)
    with pytest.raises(ValueError, match="verdict must be unsupported"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=verdict_hash,
            replay_id="unit-explicit-parent-verdict",
            artifact_root=artifact_root,
        )
    summary["sensitivity"]["verdict"] = "unsupported"
    summary["checkpoints"][0]["standardization"]["scales"][0] = 0
    malformed_standardization_hash = _rewrite_json(summary_path, summary)
    with pytest.raises(ValueError, match="standardization is malformed"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=malformed_standardization_hash,
            replay_id="unit-explicit-malformed-standardization",
            artifact_root=artifact_root,
        )
    summary["checkpoints"][0]["standardization"]["scales"][0] = 1.0
    summary_hash = _rewrite_json(summary_path, summary)
    checkpoint = (
        artifact_root
        / "daily-campaign"
        / daily_plan.contract.campaign_id
        / summary["checkpoints"][0]["fold_id"]
        / f"{summary['checkpoints'][0]['candidate_id']}.pt"
    )
    import torch

    checkpoint_bytes = checkpoint.read_bytes()
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    payload["state_dict"].pop(next(iter(payload["state_dict"])))
    torch.save(payload, checkpoint)
    summary["checkpoints"][0]["sha256"] = _file_sha256(checkpoint)
    incompatible_hash = _rewrite_json(summary_path, summary)
    with pytest.raises(ValueError, match="model state is incompatible"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=incompatible_hash,
            replay_id="unit-explicit-checkpoint-structure",
            artifact_root=artifact_root,
        )

    checkpoint.write_bytes(checkpoint_bytes)
    summary["checkpoints"][0]["sha256"] = _file_sha256(checkpoint)
    summary_hash = _rewrite_json(summary_path, summary)
    checkpoint.write_bytes(checkpoint.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checkpoint SHA-256 mismatch"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-checkpoint-tamper",
            artifact_root=artifact_root,
        )


def test_prepare_explicit_event_replay_rejects_fake_repo_and_outside_paths(
    daily_plan,
    tmp_path: Path,
) -> None:
    artifact_root, summary_path, summary_hash = _write_source_cuda_summary(
        daily_plan, tmp_path
    )
    actions = _corporate_actions_fixture(daily_plan, tmp_path / "events-paths")
    outside_dates = {
        symbol: date(2025, 1, 2 + index)
        for index, symbol in enumerate(DAILY_SYMBOLS)
    }
    outside_events = _corporate_actions_fixture(
        daily_plan,
        tmp_path / "events-outside-plan",
        event_dates=outside_dates,
    )
    with pytest.raises(ValueError, match="outside plan.common_sessions"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=outside_events,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-event-outside-plan",
            artifact_root=artifact_root,
        )
    fake = SimpleNamespace(
        assert_replay_eligible=lambda: (_ for _ in ()).throw(
            AssertionError("fake method must not be called")
        )
    )
    with pytest.raises(TypeError, match="must be CatalogedCorporateActions"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=fake,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-fake",
            artifact_root=artifact_root,
        )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-repo-root",
            artifact_root=Path.cwd(),
            repo_root=Path.cwd(),
        )

    outside_summary = tmp_path / "outside-summary.json"
    outside_summary.write_bytes(summary_path.read_bytes())
    with pytest.raises(ValueError, match="exact non-symlink campaign summary"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=outside_summary,
            expected_source_summary_sha256=_file_sha256(outside_summary),
            replay_id="unit-explicit-outside-summary",
            artifact_root=artifact_root,
        )

    summary = json.loads(summary_path.read_text())
    outside_checkpoint = tmp_path / "outside.pt"
    outside_checkpoint.write_bytes(b"outside")
    summary["checkpoints"][0]["path"] = str(outside_checkpoint)
    summary["checkpoints"][0]["sha256"] = _file_sha256(outside_checkpoint)
    outside_checkpoint_hash = _rewrite_json(summary_path, summary)
    with pytest.raises(ValueError, match="expected artifact-relative tail"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=outside_checkpoint_hash,
            replay_id="unit-explicit-outside-checkpoint",
            artifact_root=artifact_root,
        )


def test_prepare_explicit_event_replay_rejects_symlinked_evidence_component(
    daily_plan,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root, summary_path, summary_hash = _write_source_cuda_summary(
        daily_plan, tmp_path
    )
    actions = _corporate_actions_fixture(daily_plan, tmp_path / "events-symlink")
    summary = json.loads(summary_path.read_text())
    checkpoint = (
        artifact_root
        / "daily-campaign"
        / daily_plan.contract.campaign_id
        / summary["checkpoints"][0]["fold_id"]
        / f"{summary['checkpoints'][0]['candidate_id']}.pt"
    )
    path_type = type(checkpoint)
    original_is_symlink = path_type.is_symlink

    def injected_is_symlink(path: Path) -> bool:
        return path == checkpoint or original_is_symlink(path)

    monkeypatch.setattr(path_type, "is_symlink", injected_is_symlink)
    with pytest.raises(ValueError, match="cannot contain symlinks"):
        prepare_daily_explicit_event_replay(
            daily_plan,
            corporate_actions=actions,
            source_summary_path=summary_path,
            expected_source_summary_sha256=summary_hash,
            replay_id="unit-explicit-symlink",
            artifact_root=artifact_root,
        )


def test_daily_targets_use_raw_next_opens_and_fold_local_development_stats(
    daily_plan,
) -> None:
    plan = daily_plan
    candidate = DAILY_CANDIDATES[0]
    first = build_daily_training_batch(plan, fold_id="fold-1", candidate=candidate)
    second = build_daily_training_batch(plan, fold_id="fold-2", candidate=candidate)
    sample = first.samples[0]
    bars = plan.phase_bars(sample.symbol, "fold-1", "development")
    signal_index = next(
        index for index, bar in enumerate(bars) if bar.start_ts == sample.signal_start
    )

    assert sample.entry_start == bars[signal_index + 1].start_ts
    assert sample.exit_start == bars[signal_index + 2].start_ts
    assert sample.after_cost_pnl == executable_open_to_open_pnl(
        bars[signal_index + 1].open,
        bars[signal_index + 2].open,
    )
    assert sample.label == (1 if sample.after_cost_pnl > 0 else 0)
    assert max(abs(value) for value in sample.features) < 10

    for item in first.samples:
        symbol_bars = plan.phase_bars(item.symbol, "fold-1", "development")
        index = next(
            offset
            for offset, bar in enumerate(symbol_bars)
            if bar.start_ts == item.signal_start
        )
        touched = {
            bar.start_ts.date() for bar in symbol_bars[index - 20 : index + 3]
        }
        assert not touched.intersection(plan.factor_dates_for(item.symbol))

    for batch, fold_id in ((first, "fold-1"), (second, "fold-2")):
        fold = plan.fold_for(fold_id)
        standardization = batch.standardization
        assert standardization.fold_id == fold_id
        assert standardization.development_start == fold.development[0]
        assert standardization.development_end == fold.development[-1] + timedelta(days=1)
        assert all(sample.exit_start < fold.validation[0] for sample in batch.samples)
        assert all(math_value == math_value for math_value in standardization.means)
    assert first.standardization.means != second.standardization.means


def test_daily_replays_are_offline_durable_temporal_and_mock_cuda_bounded(
    daily_plan,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("daily campaign must remain offline")

    original_import = builtins.__import__

    def guard_import(name: str, *args: object, **kwargs: object):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("injected host tests must not import torch")
        if "kis" in name.lower():
            raise AssertionError("daily campaign must not import KIS")
        return original_import(name, *args, **kwargs)

    original_read_text = Path.read_text

    def guard_credentials(path: Path, *args: object, **kwargs: object) -> str:
        lowered = path.name.lower()
        if lowered.startswith(".env") or any(
            marker in lowered for marker in ("credential", "secret", "token")
        ):
            raise AssertionError("daily campaign must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(builtins, "__import__", guard_import)
    monkeypatch.setattr(Path, "read_text", guard_credentials)

    for fold in daily_plan.folds:
        for symbol in DAILY_SYMBOLS:
            phase_bars = daily_plan.phase_bars(symbol, fold.fold_id, "validation")
            by_start = {bar.start_ts: index for index, bar in enumerate(phase_bars)}
            for scenario in ("primary", "factor_sensitivity"):
                indices = tuple(
                    sorted(
                        by_start[start]
                        for start in daily_plan.eligible_signal_starts(
                            symbol,
                            fold.fold_id,
                            "validation",
                            scenario=scenario,
                        )
                    )
                )
                assert all(
                    (current - prior) % DAILY_SIGNAL_CADENCE == 0
                    for prior, current in zip(indices, indices[1:], strict=False)
                )

    artifacts = tmp_path / "artifacts"
    baselines = run_daily_cpu_baselines(
        daily_plan,
        artifact_root=artifacts,
        work_root=tmp_path / "baseline-work",
        repo_root=Path.cwd(),
    )
    assert len(baselines.cells) == 36
    assert baselines.sensitivity.verdict == "supported-with-limits"
    assert baselines.sensitivity.relative_order_changed is False
    assert {
        (cell.item_id, cell.symbol, cell.fold_id, cell.scenario)
        for cell in baselines.cells
    } == {
        (baseline, symbol, fold, scenario)
        for baseline in ("always_long", "previous_bar_direction", "flat")
        for symbol in DAILY_SYMBOLS
        for fold in ("fold-1", "fold-2")
        for scenario in ("primary", "factor_sensitivity")
    }
    _assert_replay_evidence(baselines.cells)
    baseline_decisions = _decision_counts(baselines.cells)

    repo_artifacts = Path.cwd() / f".daily-campaign-no-write-{tmp_path.name}"
    assert not repo_artifacts.exists()
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_daily_campaign_summary(
            daily_plan,
            baselines,
            artifact_root=repo_artifacts,
            repo_root=Path.cwd(),
        )
    assert not repo_artifacts.exists()

    batches: list[object] = []

    def mock_trainer(candidate, batch, checkpoint_path: Path) -> dict[str, object]:
        batches.append(batch)
        with checkpoint_path.open("xb") as handle:
            handle.write(
                f"{batch.fold_id}:{candidate.candidate_id}:{batch.standardization.means}".encode()
            )
        return {"backend": "injected_cpu_mock", "examples": len(batch.samples)}

    probabilities = {
        "d1-core-lb5": 0.75,
        "d1-core-lb20": 0.25,
        "d1-pressure-lb20": 0.55,
    }

    def mock_inference_factory(candidate, _path, standardization):
        assert standardization.fold_id in {"fold-1", "fold-2"}
        return lambda _features: probabilities[candidate.candidate_id]

    candidates = run_daily_cuda_breadth(
        daily_plan,
        baselines=baselines,
        artifact_root=artifacts,
        work_root=tmp_path / "candidate-work",
        repo_root=Path.cwd(),
        trainer=mock_trainer,
        inference_factory=mock_inference_factory,
    )
    assert len(candidates.training) == DAILY_MAX_TRAINING_RUNS == 6
    assert len(candidates.cells) == 36
    assert len(batches) == 6
    assert all(item.checkpoint_path.is_file() for item in candidates.training)
    assert all(item.checkpoint_sha256.startswith("sha256:") for item in candidates.training)
    assert all(
        item.trainer_metrics["backend"] == "injected_cpu_mock"
        for item in candidates.training
    )
    assert all(
        item.development_sample_policy == "factor_safe_for_both_validation_scenarios"
        for item in candidates.training
    )
    assert {
        (
            item.candidate.hidden_units,
            item.candidate.activation,
            item.candidate.learning_rate,
            item.candidate.weight_decay,
            item.candidate.threshold,
            item.candidate.epochs,
            item.candidate.seed,
        )
        for item in candidates.training
    } == {
        (
            DAILY_HIDDEN_UNITS,
            "relu",
            DAILY_LEARNING_RATE,
            DAILY_WEIGHT_DECAY,
            DAILY_THRESHOLD,
            DAILY_EPOCHS,
            DAILY_SEED,
        )
    }
    _assert_replay_evidence(candidates.cells)

    for cell in candidates.cells:
        key = (cell.symbol, cell.fold_id, cell.scenario)
        assert cell.replay.result.decisions_seen == baseline_decisions[key]
    unstable = bool(candidates.sensitivity.sign_changes) or (
        candidates.sensitivity.relative_order_changed
    )
    assert candidates.sensitivity.verdict == (
        "unsupported" if unstable else "supported-with-limits"
    )
    assert candidates.development_only is True
    assert candidates.summary_path.is_file()
    assert candidates.summary_sha256 == _file_sha256(candidates.summary_path)
    summary = json.loads(candidates.summary_path.read_text())
    assert datetime.fromisoformat(summary["created_at_utc"]).utcoffset() == timedelta(0)
    assert summary["campaign_contract_hash"] == daily_plan.contract.contract_hash
    assert summary["dataset"]["dataset_hash"] == daily_plan.contract.catalog.dataset_hash
    assert summary["split"]["purge_observed_sessions"] == 2
    assert summary["split"]["embargo_observed_sessions"] == 2
    assert summary["training_policy"]["runs"] == 6
    assert summary["training_policy"]["development_samples"] == "factor_safe"
    assert summary["training_policy"]["retraining_by_validation_scenario"] is False
    assert summary["execution_timing"]["entry_observed_session_offset"] == 1
    assert summary["execution_timing"]["exit_observed_session_offset"] == 2
    assert summary["execution_timing"]["common_session_adjacency_proven"] is True
    assert summary["sensitivity"]["relative_order_changed"] is unstable
    assert summary["sensitivity"]["all_item_primary_order"]
    assert summary["sensitivity"]["all_item_sensitivity_order"]
    assert summary["cuda"]["used"] is False
    assert summary["labels"] == {
        "candidate_selection": False,
        "development_only": True,
        "profitability_claim": False,
        "promotion": False,
        "ranking": False,
        "sealed_holdout": False,
    }
    assert len(summary["checkpoints"]) == 6
    assert len(summary["replays"]) == 72
    assert "winner" not in candidates.summary_path.read_text().lower()

    with pytest.raises(FileExistsError, match="summary already exists"):
        run_daily_cuda_breadth(
            daily_plan,
            baselines=baselines,
            artifact_root=artifacts,
            work_root=tmp_path / "duplicate-candidate-work",
            repo_root=Path.cwd(),
            trainer=mock_trainer,
            inference_factory=mock_inference_factory,
        )


def test_intraday_validation_continuity_remains_strict(tmp_path: Path) -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    bars = [_m1_bar(start + timedelta(minutes=index)) for index in range(9)]
    bars.pop(4)
    with pytest.raises(ValueError, match="must be contiguous"):
        run_local_paper_validation(
            bars,
            event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
            emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        )


def _assert_replay_evidence(cells) -> None:
    for cell in cells:
        replay = cell.replay
        result = replay.result
        assert replay.fill_source == "local_paper"
        assert replay.replay_evidence.fill_source == "local_paper"
        assert result.final_position == 0
        assert result.total_fees >= 0
        assert result.total_slippage >= 0
        assert result.after_cost_pnl == result.gross_pnl - result.total_fees - result.total_slippage
        assert replay.artifact_path.is_file()
        payload = json.loads(replay.artifact_path.read_text())
        assert payload["replay_evidence"]["fill_source"] == "local_paper"
        evidence = replay.replay_evidence
        assert evidence.event_jsonl_sha256 == _file_sha256(evidence.event_jsonl_path)
        assert evidence.state_sqlite_sha256 == _file_sha256(evidence.state_sqlite_path)
        assert evidence.emergency_sha256 == _file_sha256(evidence.emergency_path)
        events = list(
            EventStore(
                evidence.state_sqlite_path,
                evidence.event_jsonl_path,
            ).iter_events()
        )
        assert [event.created_at for event in events] == sorted(
            event.created_at for event in events
        )
        fills = [event for event in events if event.event_type == "fill"]
        assert all(event.payload["source"] == "local_paper" for event in fills)
        for entry, exit_fill in zip(result.trades[::2], result.trades[1::2], strict=True):
            assert entry.side == "buy"
            assert exit_fill.side == "sell"
            assert entry.filled_at < exit_fill.filled_at


def _sensitivity_cell(
    kind: str,
    item_id: str,
    scenario: str,
    pnl: str,
) -> DailyReplayCell:
    replay = SimpleNamespace(result=SimpleNamespace(after_cost_pnl=Decimal(pnl)))
    return DailyReplayCell(
        kind=kind,
        item_id=item_id,
        symbol="SPY",
        fold_id="fold-1",
        scenario=scenario,
        replay=replay,
    )


def _decision_counts(cells) -> dict[tuple[str, str, str], int]:
    grouped: dict[tuple[str, str, str], set[int]] = {}
    for cell in cells:
        key = (cell.symbol, cell.fold_id, cell.scenario)
        grouped.setdefault(key, set()).add(cell.replay.result.decisions_seen)
    assert all(len(counts) == 1 for counts in grouped.values())
    return {key: next(iter(counts)) for key, counts in grouped.items()}


def _corporate_actions_fixture(
    daily_plan,
    root: Path,
    *,
    coverage_status: str = "complete",
    event_dates: dict[str, date] | None = None,
) -> CatalogedCorporateActions:
    dates = event_dates or {
        symbol: daily_plan.phase_bars(symbol, "fold-2", "validation")[
            10 + index * 10
        ].start_ts.date()
        for index, symbol in enumerate(DAILY_SYMBOLS)
    }
    snapshot, dataset_id, dataset_hash, manifest_hash = (
        _write_corporate_action_snapshot(
            daily_plan,
            root,
            dates,
            coverage_status=coverage_status,
        )
    )
    observed_campaign_dates = {
        session.date() for session in daily_plan.common_sessions
    } | set(dates.values()) | {CAMPAIGN_COVERAGE_START, CAMPAIGN_COVERAGE_END}
    observed_dates = {
        symbol: frozenset(observed_campaign_dates) for symbol in DAILY_SYMBOLS
    }
    return load_cataloged_corporate_actions(
        snapshot,
        dataset_id=dataset_id,
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=manifest_hash,
        expected_r2_dataset_id=daily_plan.contract.catalog.dataset_id,
        expected_r2_dataset_hash=daily_plan.contract.catalog.dataset_hash,
        expected_r2_manifest_hash=_file_sha256(
            daily_plan.cataloged_bars[0].source_path.parent / "manifest.json"
        ),
        observed_session_dates=observed_dates,
        require_replay_eligible=coverage_status == "complete",
        repo_root=Path.cwd(),
    )


def _write_corporate_action_snapshot(
    daily_plan,
    root: Path,
    dates: dict[str, date],
    *,
    coverage_status: str,
) -> tuple[Path, str, str, str]:
    snapshot = root / "snapshot=unit-events-r1"
    raw_root = snapshot / "raw"
    raw_root.mkdir(parents=True)
    raw_bytes = b'{"source":"unit"}\n'
    raw_path = raw_root / "unit-source.json"
    raw_path.write_bytes(raw_bytes)
    rows = [
        {
            "event_id": f"{symbol.lower()}-cash",
            "symbol": symbol,
            "event_type": "cash_distribution",
            "source_date_kind": "ex_date",
            "source_event_date": dates[symbol].isoformat(),
            "affected_session_date": dates[symbol].isoformat(),
            "cash_amount": "1.0",
            "currency": "USD",
            "split_numerator": "",
            "split_denominator": "",
            "source_id": "unit-source",
            "source_record_id": f"{symbol.lower()}-record",
            "mapping_rule_id": "identity_observed_session_v1",
            "mapping_status": "mapped",
        }
        for symbol in DAILY_SYMBOLS
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CORPORATE_ACTION_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    event_bytes = buffer.getvalue().encode()
    event_path = snapshot / "corporate_actions.csv"
    event_path.write_bytes(event_bytes)
    dataset_hash = _bytes_sha256(event_bytes)
    dataset_id = f"us_equities.fixed_etf_corporate_actions.{snapshot.name}"
    retrieval = "2026-07-18T01:02:03Z"
    coverage = []
    for symbol in DAILY_SYMBOLS:
        for event_type in CORPORATE_ACTION_EVENT_TYPES:
            count = int(event_type == "cash_distribution")
            coverage.append(
                {
                    "symbol": symbol,
                    "event_type": event_type,
                    "start": CAMPAIGN_COVERAGE_START.isoformat(),
                    "end": CAMPAIGN_COVERAGE_END.isoformat(),
                    "status": coverage_status,
                    "event_count": count,
                    "source_ids": ["unit-source"],
                }
            )
    r2_snapshot = daily_plan.contract.catalog.dataset_id.rsplit(".", 1)[-1]
    r2_manifest_hash = _file_sha256(
        daily_plan.cataloged_bars[0].source_path.parent / "manifest.json"
    )
    manifest = {
        "schema_version": 1,
        "kind": "fixed_etf_corporate_actions",
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "symbols": list(DAILY_SYMBOLS),
        "event_types": list(CORPORATE_ACTION_EVENT_TYPES),
        "date_kinds": ["ex_date", "split_trading_date"],
        "normalized_events": {
            "path": f"/market_data/{snapshot.name}/corporate_actions.csv",
            "sha256": dataset_hash,
            "size_bytes": len(event_bytes),
            "schema": list(CORPORATE_ACTION_COLUMNS),
        },
        "raw_sources": [
            {
                "source_id": "unit-source",
                "provider": "Unit Fixture",
                "source_url": "https://unit.example/corporate-actions",
                "source_kind": "issuer_download",
                "acquisition_mode": "manual_operator",
                "use_scope": "private_internal_use",
                "rights_status": "confirmed",
                "symbols": sorted(DAILY_SYMBOLS),
                "event_types": sorted(CORPORATE_ACTION_EVENT_TYPES),
                "coverage_start": CAMPAIGN_COVERAGE_START.isoformat(),
                "coverage_end": CAMPAIGN_COVERAGE_END.isoformat(),
                "filename": raw_path.name,
                "path": f"/market_data/{snapshot.name}/raw/{raw_path.name}",
                "sha256": _bytes_sha256(raw_bytes),
                "size_bytes": len(raw_bytes),
                "retrieved_at_utc": retrieval,
                "source_as_of": CAMPAIGN_COVERAGE_END.isoformat(),
                "revision": "unit-r1",
            }
        ],
        "snapshot_metadata": {
            "retrieved_at_utc": retrieval,
            "source_as_of": CAMPAIGN_COVERAGE_END.isoformat(),
            "revision": "unit-r1",
        },
        "campaign_coverage": {
            "start": CAMPAIGN_COVERAGE_START.isoformat(),
            "end": CAMPAIGN_COVERAGE_END.isoformat(),
        },
        "coverage": coverage,
        "date_semantics": {
            "exchange_timezone": "America/New_York",
            "session_date_semantics": "date_only_no_utc_conversion",
            "non_session_policy": "reject",
            "ambiguous_effective_date_policy": "reject",
        },
        "mapping_policy": {
            "id": "identity_observed_session_v1",
            "status": "mapped_only",
            "calendar_lineage": "verified_r2_observed_sessions",
        },
        "duplicate_policy": {
            "event_id": "reject",
            "source_record": "reject",
            "identical_normalized_action": "preserve_records_collapse_mask_date",
            "conflict": "reject",
        },
        "scope": {
            "retrospective_development_replay_only": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "r2_lineage": {
            "dataset_id": daily_plan.contract.catalog.dataset_id,
            "dataset_hash": daily_plan.contract.catalog.dataset_hash,
            "manifest_sha256": r2_manifest_hash,
            "snapshot_name": r2_snapshot,
            "subset_path": f"/market_data/{r2_snapshot}/ohlcv_1d.csv.gz",
            "manifest_path": f"/market_data/{r2_snapshot}/manifest.json",
        },
    }
    manifest_path = snapshot / "manifest.json"
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode()
    manifest_path.write_bytes(manifest_bytes)
    return snapshot, dataset_id, dataset_hash, _bytes_sha256(manifest_bytes)


def _write_source_cuda_summary(
    daily_plan,
    root: Path,
) -> tuple[Path, Path, str]:
    torch = pytest.importorskip("torch", reason="requires the research runtime")

    artifact_root = root / "artifacts"
    campaign_root = artifact_root / "daily-campaign" / daily_plan.contract.campaign_id
    campaign_root.mkdir(parents=True)
    checkpoints = []
    for fold in daily_plan.folds:
        for candidate in DAILY_CANDIDATES:
            fold_root = campaign_root / fold.fold_id
            fold_root.mkdir(exist_ok=True)
            path = fold_root / f"{candidate.candidate_id}.pt"
            standardization = _standardization_fixture(
                daily_plan,
                fold.fold_id,
                candidate.feature_set,
            )
            model = torch.nn.Sequential(
                torch.nn.Linear(len(standardization["feature_names"]), candidate.hidden_units),
                torch.nn.ReLU(),
                torch.nn.Linear(candidate.hidden_units, 1),
            )
            checkpoint_standardization = {
                **standardization,
                "feature_names": tuple(standardization["feature_names"]),
                "means": tuple(standardization["means"]),
                "scales": tuple(standardization["scales"]),
            }
            with path.open("xb") as handle:
                torch.save(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "model_kind": "daily_tiny_mlp_v1",
                        "candidate": {
                            "candidate_id": candidate.candidate_id,
                            "feature_set": candidate.feature_set,
                            "lookback": candidate.lookback,
                            "hidden_units": candidate.hidden_units,
                            "activation": candidate.activation,
                            "learning_rate": candidate.learning_rate,
                            "weight_decay": candidate.weight_decay,
                            "threshold": candidate.threshold,
                            "epochs": candidate.epochs,
                            "seed": candidate.seed,
                        },
                        "standardization": checkpoint_standardization,
                        "state_dict": model.state_dict(),
                    },
                    handle,
                )
            checkpoints.append(
                {
                    "fold_id": fold.fold_id,
                    "candidate_id": candidate.candidate_id,
                    "path": _declared_artifact_path(
                        "daily-campaign",
                        daily_plan.contract.campaign_id,
                        fold.fold_id,
                        f"{candidate.candidate_id}.pt",
                    ),
                    "sha256": _file_sha256(path),
                    "standardization": standardization,
                }
            )
    payload = {
        "campaign_id": daily_plan.contract.campaign_id,
        "campaign_contract_hash": daily_plan.contract.contract_hash,
        "labels": {
            "candidate_selection": False,
            "development_only": True,
            "profitability_claim": False,
            "promotion": False,
            "ranking": False,
            "sealed_holdout": False,
        },
        "dataset": {
            "catalog_id": daily_plan.contract.catalog.catalog_id,
            "dataset_id": daily_plan.contract.catalog.dataset_id,
            "dataset_hash": daily_plan.contract.catalog.dataset_hash,
            "price_basis": "raw_ohlcv_only",
            "symbols": list(DAILY_SYMBOLS),
        },
        "cuda": {"used": True, "training_runs": 6},
        "training_policy": {
            "runs": 6,
            "maximum_runs": 6,
            "retraining_by_validation_scenario": False,
        },
        "sensitivity": {"verdict": "unsupported"},
        "checkpoints": checkpoints,
    }
    path = campaign_root / "summary.json"
    summary_hash = _rewrite_json(path, payload)
    return artifact_root, path, summary_hash


def _rewrite_json(path: Path, payload: object) -> str:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return _file_sha256(path)


def _standardization_fixture(daily_plan, fold_id: str, feature_set: str) -> dict:
    fold = daily_plan.fold_for(fold_id)
    feature_names = (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
    )
    if feature_set == "pressure":
        feature_names = (
            *feature_names,
            "close_position",
            "range_expansion",
            "bar_body_return",
        )
    return {
        "fit_phase": "development",
        "fit_fold_id": fold_id,
        "development_start": fold.development[0].isoformat(),
        "development_end": (fold.development[-1] + Timeframe.D1.duration).isoformat(),
        "feature_names": list(feature_names),
        "means": [0.0] * len(feature_names),
        "scales": [1.0] * len(feature_names),
    }


def _declared_artifact_path(*parts: str) -> str:
    return str(PurePosixPath("/app/model_artifacts", *parts))


def _write_source_snapshot(path: Path) -> None:
    sessions = _business_sessions(date(2021, 1, 4), DAILY_COMMON_SESSIONS)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_FIELDS)
        writer.writeheader()
        for symbol_index, symbol in enumerate(DAILY_SYMBOLS):
            base = Decimal("100") + Decimal(symbol_index * 25)
            for index, session in enumerate(sessions):
                regime = Decimal(index) / (Decimal("200") if index < 319 else Decimal("80"))
                opened = base + regime
                body = Decimal((index % 7) - 3) / Decimal("20")
                closed = opened + body
                if symbol == "SPY":
                    factor = Decimal("0.5") if index >= 274 else Decimal("1")
                elif symbol == "QQQ":
                    factor = Decimal("0.8") if index >= 350 else Decimal("1")
                else:
                    factor = Decimal("1.2") if index >= 855 else Decimal("1")
                writer.writerow(
                    {
                        "symbol": symbol,
                        "date": session.isoformat(),
                        "open": opened,
                        "high": max(opened, closed) + Decimal("1"),
                        "low": min(opened, closed) - Decimal("1"),
                        "close": closed,
                        "volume": 100000 + index * (symbol_index + 1),
                        "adj_close": closed * factor,
                        "asset_type": "stock",
                        "yahoo_symbol": symbol,
                        "source": "research_unit_fixture",
                    }
                )


def _business_sessions(start: date, count: int) -> tuple[date, ...]:
    sessions: list[date] = []
    current = start
    while len(sessions) < count:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return tuple(sessions)


def _m1_bar(start: datetime) -> Bar:
    return Bar(
        symbol="AAPL",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1000"),
    )


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
