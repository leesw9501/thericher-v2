from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_mtf_profiled_prospective_observer as observer
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import (
    profiled_mtf_forward_campaign_readiness as readiness,
)
from thericher_v2.research import (
    profiled_mtf_forward_cpu_campaign as cpu_campaign,
)
from thericher_v2.research import (
    profiled_mtf_forward_supervised_dataset as dataset,
)


def test_runs_fixed_cpu_controls_without_purge_or_external_value_artifacts(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    catalog = _catalog(outcome_multiplier=Decimal("1"))
    dataset_receipt, materialization = _materialization(
        catalog,
        root=tmp_path / "first",
        repository=repository,
    )
    policy = cpu_campaign.freeze_profiled_mtf_forward_cpu_campaign_policy(
        dataset_receipt,
        code_revision_sha256=_sha256("cpu-campaign-code-r1"),
    )

    feature_matrix = cpu_campaign.build_profiled_mtf_forward_cpu_feature_matrix(materialization)
    result = cpu_campaign.run_profiled_mtf_forward_cpu_campaign(
        policy,
        dataset_receipt=dataset_receipt,
        materialization=materialization,
    )
    receipt = cpu_campaign.write_profiled_mtf_forward_cpu_campaign_receipt(
        result,
        policy=policy,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=repository,
        attempt_id="fixture-r1",
    )

    assert len(feature_matrix.values) == 60
    assert all(len(row) == 50 for row in feature_matrix.values)
    assert result.status == "cpu_evaluated_not_promoting"
    assert (result.train_row_count, result.purge_row_count, result.validation_row_count) == (
        40,
        4,
        16,
    )
    assert tuple(metric.candidate_id for metric in result.candidate_metrics) == (
        "no_trade_zero",
        "ridge_alpha_10",
        "hist_gradient_depth_limited",
    )
    assert result == cpu_campaign.run_profiled_mtf_forward_cpu_campaign(
        policy,
        dataset_receipt=dataset_receipt,
        materialization=materialization,
    )
    rendered = receipt.receipt_path.read_text(encoding="utf-8")
    assert "target_log_return" not in rendered
    assert str(materialization.rows[0].target_log_return) not in rendered
    assert not list((tmp_path / "model-artifacts").rglob("*.pkl"))


def test_feature_matrix_does_not_use_outcome_window_values(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    first_catalog = _catalog(outcome_multiplier=Decimal("1"))
    _, first = _materialization(
        first_catalog,
        root=tmp_path / "first",
        repository=repository,
    )
    changed_catalog = _catalog(outcome_multiplier=Decimal("2"))
    _, changed = _materialization(
        changed_catalog,
        root=tmp_path / "changed",
        repository=repository,
    )

    first_features = cpu_campaign.build_profiled_mtf_forward_cpu_feature_matrix(first)
    changed_features = cpu_campaign.build_profiled_mtf_forward_cpu_feature_matrix(changed)

    assert first.rows[0].target_log_return != changed.rows[0].target_log_return
    assert first_features.values == changed_features.values
    assert first_features.control_sha256s == changed_features.control_sha256s


def test_zero_dataset_receipt_is_scoped_input_unavailable(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    catalog = _catalog(pair_count=0)
    dataset_receipt = _dataset_receipt_without_materialization(
        catalog,
        root=tmp_path / "zero",
        repository=repository,
    )
    policy = cpu_campaign.freeze_profiled_mtf_forward_cpu_campaign_policy(
        dataset_receipt,
        code_revision_sha256=_sha256("cpu-campaign-code-r1"),
    )

    result = cpu_campaign.run_profiled_mtf_forward_cpu_campaign(
        policy,
        dataset_receipt=dataset_receipt,
        materialization=None,
    )

    assert result.status == "input_unavailable"
    assert result.candidate_metrics == ()
    assert result.feature_matrix_sha256 is None
    assert result.safe_payload()["scope"]["model_trained_cpu_only_in_memory"] is False


def test_core_cpu_campaign_import_does_not_load_execution_transport_or_torch() -> None:
    source = Path(cpu_campaign.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "KIS_PAPER_",
        "KIS_LIVE_",
        "os.environ",
        "requests",
        "urllib",
        "socket",
        "OrderIntent",
        "torch",
    ):
        assert forbidden not in source
    script = """
import sys
import thericher_v2.research.profiled_mtf_forward_cpu_campaign
for name in sys.modules:
    if name.startswith('thericher_v2.execution'):
        raise SystemExit(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


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
    outcome_multiplier: Decimal = Decimal("1"),
) -> observer.KisMtfProfiledForwardOutcomeSnapshotCatalog:
    contract = _forward_contract()
    inventory = observer.KisMtfProfiledForwardOutcomeInventory(
        contract_sha256=contract.contract_sha256,
        target_ready_pair_count=pair_count,
        target_ready_manifest_sha256=_sha256(f"manifest-{pair_count}"),
        status="target_ready" if pair_count else "zero_target_ready",
    )
    session_dates = _regular_dates(count=pair_count)
    snapshots = tuple(
        _snapshot(contract, pair_index, session_date, outcome_multiplier=outcome_multiplier)
        for pair_index, session_date in enumerate(session_dates)
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
                + (final_outcome_close - final_input_close)
                * Decimal(minute + 1)
                / Decimal("15"),
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


def _regular_dates(*, count: int):
    result = []
    session_date = date(2026, 8, 3)
    while len(result) < count:
        session = us_equity_2026_session(session_date)
        if session is not None and session.kind == "regular":
            result.append(session_date)
        session_date += timedelta(days=1)
    return tuple(result)


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
