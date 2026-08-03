from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_mtf_profiled_prospective_observer as observer
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import (
    profiled_mtf_forward_campaign_readiness as readiness,
)
from thericher_v2.research import (
    profiled_mtf_forward_ragged_sequence_cpu_campaign as campaign,
)
from thericher_v2.research import (
    profiled_mtf_forward_supervised_dataset as dataset,
)


def test_runs_fixed_native_ragged_families_without_value_or_weight_artifacts(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    repository = tmp_path / "repo"
    repository.mkdir()
    receipt, materialization = _materialization(
        _catalog(),
        root=tmp_path / "fixture",
        repository=repository,
    )
    policy = campaign.freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
        receipt,
        code_revision_sha256=_sha256("ragged-campaign-code-r1"),
    )

    batch = campaign.build_profiled_mtf_forward_ragged_sequence_input_batch(materialization)
    result = campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
        policy,
        dataset_receipt=receipt,
        materialization=materialization,
    )
    artifact_root = tmp_path / "model-artifacts"
    written = campaign.write_profiled_mtf_forward_ragged_sequence_cpu_campaign_receipt(
        result,
        policy=policy,
        artifact_root=artifact_root,
        repo_root=repository,
        attempt_id="fixture-r1",
    )

    assert tuple(frame.sequence_length for frame in batch.frames) == (15, 3, 3, 2, 2)
    assert batch.token_count == 25
    assert batch.safe_payload()["mask_policy"]["cross_timeframe_row_alignment"] == "none"
    assert all(all(all(mask) for mask in control) for control in batch.validity_masks)
    assert result.status == "cpu_evaluated_not_promoting"
    assert (result.train_row_count, result.purge_row_count, result.validation_row_count) == (
        40,
        4,
        16,
    )
    assert tuple(metric.candidate_id for metric in result.candidate_metrics) == (
        "no_trade_zero",
        "per_timeframe_recurrent",
        "causal_tcn",
        "masked_cross_timeframe_attention",
    )
    assert result == campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
        policy,
        dataset_receipt=receipt,
        materialization=materialization,
    )
    rendered = written.receipt_path.read_text(encoding="utf-8")
    assert "target_log_return" not in rendered
    assert str(materialization.rows[0].target_log_return) not in rendered
    assert "state_dict" not in rendered
    assert not list(artifact_root.rglob("*.pt"))
    assert not list(artifact_root.rglob("*.pth"))


def test_ragged_inputs_ignore_outcomes_and_pair_purge_targets(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    repository = tmp_path / "repo"
    repository.mkdir()
    first_receipt, first = _materialization(
        _catalog(),
        root=tmp_path / "first",
        repository=repository,
    )
    changed_receipt, changed = _materialization(
        _catalog(pair_outcome_multipliers={20: Decimal("2"), 21: Decimal("3")} ),
        root=tmp_path / "changed",
        repository=repository,
    )
    first_policy = campaign.freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
        first_receipt,
        code_revision_sha256=_sha256("ragged-campaign-code-r1"),
    )
    changed_policy = campaign.freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
        changed_receipt,
        code_revision_sha256=_sha256("ragged-campaign-code-r1"),
    )

    first_batch = campaign.build_profiled_mtf_forward_ragged_sequence_input_batch(first)
    changed_batch = campaign.build_profiled_mtf_forward_ragged_sequence_input_batch(changed)
    first_result = campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
        first_policy,
        dataset_receipt=first_receipt,
        materialization=first,
    )
    changed_result = campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
        changed_policy,
        dataset_receipt=changed_receipt,
        materialization=changed,
    )

    assert first.rows[40].target_log_return != changed.rows[40].target_log_return
    assert first_batch.sequences == changed_batch.sequences
    assert first_batch.projection_sha256s == changed_batch.projection_sha256s
    assert first_result.candidate_metrics == changed_result.candidate_metrics


def test_bridge_rejects_mask_geometry_and_source_receipt_drift(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    first_receipt, materialization = _materialization(
        _catalog(),
        root=tmp_path / "first",
        repository=repository,
    )
    batch = campaign.build_profiled_mtf_forward_ragged_sequence_input_batch(materialization)
    invalid_masks = tuple(
        tuple(
            tuple(
                False if (control_index, frame_index, row_index) == (0, 0, 0) else value
                for row_index, value in enumerate(frame)
            )
            for frame_index, frame in enumerate(control)
        )
        for control_index, control in enumerate(batch.validity_masks)
    )
    with pytest.raises(ValueError, match="values or mask"):
        replace(batch, validity_masks=invalid_masks)
    with pytest.raises(ValueError, match="identity"):
        replace(batch, frames=tuple(reversed(batch.frames)))

    changed_receipt, changed_materialization = _materialization(
        _catalog(pair_outcome_multipliers={0: Decimal("2")} ),
        root=tmp_path / "changed",
        repository=repository,
    )
    policy = campaign.freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
        first_receipt,
        code_revision_sha256=_sha256("ragged-campaign-code-r1"),
    )
    with pytest.raises(ValueError, match="stale or mismatched"):
        campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
            policy,
            dataset_receipt=changed_receipt,
            materialization=changed_materialization,
        )


def test_zero_dataset_is_scoped_unavailable_and_pair_kill_is_block_preserving(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    receipt = _dataset_receipt_without_materialization(
        _catalog(pair_count=0),
        root=tmp_path / "zero",
        repository=repository,
    )
    policy = campaign.freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
        receipt,
        code_revision_sha256=_sha256("ragged-campaign-code-r1"),
    )

    result = campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
        policy,
        dataset_receipt=receipt,
        materialization=None,
    )

    assert result.status == "input_unavailable"
    assert result.candidate_metrics == ()
    assert result.input_batch_sha256 is None
    assert result.safe_payload()["scope"]["model_trained_cpu_only_in_memory"] is False
    assert campaign._pair_block_reversal_indices(20) == tuple(
        index for pair in reversed(range(20)) for index in (pair * 2, pair * 2 + 1)
    )


def test_core_and_runner_have_no_credentials_network_execution_or_gpu_route() -> None:
    source = Path(campaign.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "kis_paper_",
        "kis_live_",
        "os.environ",
        "requests",
        "urllib",
        "socket",
        "orderintent",
        "cuda",
    ):
        assert forbidden not in source
    script = """
import sys
import thericher_v2.research.profiled_mtf_forward_ragged_sequence_cpu_campaign
for name in sys.modules:
    if name == 'torch' or name.startswith('torch.') or name.startswith('thericher_v2.execution'):
        raise SystemExit(name)
"""
    imported = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stderr or imported.stdout

    runner_path = Path("scripts/run_profiled_mtf_forward_ragged_sequence_cpu_campaign.py")
    runner_source = runner_path.read_text(encoding="utf-8").lower()
    assert 'path("/app/model_artifacts")' in runner_source
    assert 'path("/app/market_data/' in runner_source
    for forbidden in (
        "os.environ",
        ".env",
        "requests",
        "urllib",
        "socket",
        "thericher_v2.execution",
        "local_paper",
        "kis_live",
        "cuda",
    ):
        assert forbidden not in runner_source


def _materialization(
    catalog: observer.KisMtfProfiledForwardOutcomeSnapshotCatalog,
    *,
    root: Path,
    repository: Path,
) -> tuple[
    dataset.ProfiledMtfForwardSupervisedDatasetReceipt,
    dataset.ProfiledMtfForwardSupervisedDatasetMaterialization,
]:
    readiness_receipt = _readiness_receipt(
        catalog,
        artifact_root=root / "readiness-artifacts",
        repository=repository,
    )
    policy = dataset.freeze_profiled_mtf_forward_supervised_dataset_policy(
        readiness_receipt,
        code_revision_sha256=_sha256("dataset-code-r1"),
    )
    result = dataset.materialize_profiled_mtf_forward_supervised_dataset(
        policy,
        receipt=readiness_receipt,
        catalog=catalog,
        market_data_root=root / "market-data",
        repo_root=repository,
    )
    receipt = dataset.write_profiled_mtf_forward_supervised_dataset_receipt(
        result,
        policy=policy,
        artifact_root=root / "model-artifacts",
        repo_root=repository,
        attempt_id="dataset-r1",
    )
    loaded_receipt = dataset.load_profiled_mtf_forward_supervised_dataset_receipt(
        receipt.receipt_path,
        market_data_root=root / "market-data",
        repo_root=repository,
    )
    materialization = dataset.load_profiled_mtf_forward_supervised_dataset_materialization(
        loaded_receipt,
        catalog=catalog,
        repo_root=repository,
    )
    assert materialization is not None
    return loaded_receipt, materialization


def _dataset_receipt_without_materialization(
    catalog: observer.KisMtfProfiledForwardOutcomeSnapshotCatalog,
    *,
    root: Path,
    repository: Path,
) -> dataset.ProfiledMtfForwardSupervisedDatasetReceipt:
    readiness_receipt = _readiness_receipt(
        catalog,
        artifact_root=root / "readiness-artifacts",
        repository=repository,
    )
    policy = dataset.freeze_profiled_mtf_forward_supervised_dataset_policy(
        readiness_receipt,
        code_revision_sha256=_sha256("dataset-code-r1"),
    )
    result = dataset.materialize_profiled_mtf_forward_supervised_dataset(
        policy,
        receipt=readiness_receipt,
        catalog=catalog,
        market_data_root=root / "market-data",
        repo_root=repository,
    )
    return dataset.write_profiled_mtf_forward_supervised_dataset_receipt(
        result,
        policy=policy,
        artifact_root=root / "model-artifacts",
        repo_root=repository,
        attempt_id="dataset-r1",
    )


def _catalog(
    *,
    pair_count: int = 32,
    pair_outcome_multipliers: dict[int, Decimal] | None = None,
) -> observer.KisMtfProfiledForwardOutcomeSnapshotCatalog:
    contract = _forward_contract()
    inventory = observer.KisMtfProfiledForwardOutcomeInventory(
        contract_sha256=contract.contract_sha256,
        target_ready_pair_count=pair_count,
        target_ready_manifest_sha256=_sha256(f"manifest-{pair_count}"),
        status="target_ready" if pair_count else "zero_target_ready",
    )
    multipliers = pair_outcome_multipliers or {}
    snapshots = tuple(
        _snapshot(
            contract,
            pair_index,
            session_date,
            outcome_multiplier=multipliers.get(pair_index, Decimal("1")),
        )
        for pair_index, session_date in enumerate(_regular_dates(count=pair_count))
    )
    return observer.KisMtfProfiledForwardOutcomeSnapshotCatalog(
        contract=contract,
        inventory=inventory,
        snapshots=snapshots,
    )


def _forward_contract() -> observer.KisMtfProfiledForwardOutcomeContract:
    observer_contract_sha256 = _sha256("observer-contract")
    return observer.KisMtfProfiledForwardOutcomeContract(
        observer_contract_sha256=observer_contract_sha256,
        profile_id=observer.KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID,
        outcome_bar_count=observer.KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT,
        contract_sha256=observer._forward_outcome_contract_sha256(
            observer_contract_sha256=observer_contract_sha256,
            profile_id=observer.KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID,
            outcome_bar_count=observer.KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT,
        ),
    )


def _snapshot(
    contract: observer.KisMtfProfiledForwardOutcomeContract,
    pair_index: int,
    session_date: date,
    *,
    outcome_multiplier: Decimal,
) -> observer.KisMtfProfiledForwardOutcomeSnapshot:
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    cutoff = session.window.open_ts + timedelta(hours=6)
    input_prefixes = []
    outcome_windows = []
    for leg_index, target_key in enumerate(
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
    ):
        symbol = target_key.split("/", maxsplit=1)[0]
        base = Decimal("100") + Decimal(leg_index) * Decimal("100")
        trend = Decimal((pair_index % 5) - 2 + leg_index) / Decimal("10000")
        inputs = tuple(
            _bar(
                symbol=symbol,
                start_ts=session.window.open_ts + timedelta(minutes=minute),
                close=base + trend * Decimal(minute),
                volume=Decimal("100") + Decimal((minute + pair_index) % 31),
            )
            for minute in range(360)
        )
        final_input_close = inputs[-1].close
        return_fraction = (
            Decimal((pair_index % 7) - 3 + leg_index) / Decimal("1000")
        ) * outcome_multiplier
        final_outcome_close = final_input_close * (Decimal("1") + return_fraction)
        outcomes = tuple(
            _bar(
                symbol=symbol,
                start_ts=cutoff + timedelta(minutes=minute),
                close=final_input_close
                + (final_outcome_close - final_input_close) * Decimal(minute + 1) / Decimal("15"),
                volume=Decimal("150") + Decimal(minute),
            )
            for minute in range(15)
        )
        input_prefixes.append(inputs)
        outcome_windows.append(outcomes)
    return observer.KisMtfProfiledForwardOutcomeSnapshot(
        contract_sha256=contract.contract_sha256,
        session_key_sha256=_sha256(f"session-{pair_index}"),
        input_observation_sha256=_sha256(f"input-{pair_index}"),
        witness_sha256=_sha256(f"witness-{pair_index}"),
        raw_snapshot_sha256=_sha256(f"snapshot-{pair_index}"),
        input_prefixes=tuple(input_prefixes),
        outcome_windows=tuple(outcome_windows),
    )


def _bar(*, symbol: str, start_ts, close: Decimal, volume: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=close,
        high=close + Decimal("0.01"),
        low=close - Decimal("0.01"),
        close=close,
        volume=volume,
        complete=True,
    )


def _regular_dates(*, count: int) -> tuple[date, ...]:
    dates = []
    session_date = date(2026, 8, 3)
    while len(dates) < count:
        session = us_equity_2026_session(session_date)
        if session is not None and session.kind == "regular":
            dates.append(session_date)
        session_date += timedelta(days=1)
    return tuple(dates)


def _readiness_receipt(
    catalog: observer.KisMtfProfiledForwardOutcomeSnapshotCatalog,
    *,
    artifact_root: Path,
    repository: Path,
) -> readiness.ProfiledMtfForwardCampaignReadinessReceipt:
    policy = readiness.freeze_profiled_mtf_forward_campaign_readiness_policy(
        forward_outcome_contract_sha256=catalog.contract.contract_sha256,
        code_revision_sha256=_sha256("readiness-code-r1"),
    )
    result = readiness.evaluate_profiled_mtf_forward_campaign_readiness(policy, catalog.inventory)
    return readiness.write_profiled_mtf_forward_campaign_readiness_receipt(
        result,
        policy=policy,
        artifact_root=artifact_root,
        repo_root=repository,
        attempt_id="ready-r1",
    )


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
