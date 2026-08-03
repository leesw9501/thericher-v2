from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_mtf_profiled_prospective_observer as observer
from thericher_v2.research import (
    profiled_mtf_forward_campaign_readiness as readiness,
)
from thericher_v2.research import (
    profiled_mtf_forward_supervised_dataset as dataset,
)


def test_materializes_first_thirty_pairs_with_exact_target_and_pair_purge(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    catalog = _catalog(pair_count=32)
    readiness_receipt = _readiness_receipt(
        catalog,
        artifact_root=tmp_path / "readiness-artifacts",
        repository=repository,
        attempt_id="ready-r1",
    )
    policy = dataset.freeze_profiled_mtf_forward_supervised_dataset_policy(
        readiness_receipt,
        code_revision_sha256=_sha256("dataset-code-r1"),
    )

    result = dataset.materialize_profiled_mtf_forward_supervised_dataset(
        policy,
        receipt=readiness_receipt,
        catalog=catalog,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
    )
    receipt = dataset.write_profiled_mtf_forward_supervised_dataset_receipt(
        result,
        policy=policy,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=repository,
        attempt_id="dataset-r1",
    )

    assert result.status == "materialized"
    assert result.selected_pair_count == 30
    assert result.row_count == 60
    assert result.dataset_path is not None
    assert result.dataset_path.is_relative_to(tmp_path / "market-data")
    payload = json.loads(result.dataset_path.read_text(encoding="utf-8"))
    rows = payload["rows"]
    assert payload["pair_count"] == 30
    assert payload["row_count"] == 60
    assert [row["pair_index"] for row in rows] == [
        pair_index
        for pair_index in range(30)
        for _ in range(len(observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS))
    ]
    assert {row["session_key_sha256"] for row in rows} == {
        snapshot.session_key_sha256 for snapshot in catalog.snapshots[:30]
    }
    assert {
        catalog.snapshots[30].session_key_sha256,
        catalog.snapshots[31].session_key_sha256,
    }.isdisjoint({row["session_key_sha256"] for row in rows})
    assert {row["split"] for row in rows[:40]} == {"train"}
    assert {row["split"] for row in rows[40:44]} == {"purge"}
    assert {row["split"] for row in rows[44:]} == {"validation"}
    assert rows[0]["input_end"].endswith("T19:30:00+00:00")
    assert rows[0]["outcome_end"].endswith("T19:45:00+00:00")
    first_snapshot = catalog.snapshots[0]
    assert Decimal(rows[0]["target_log_return"]) == dataset._log_return(
        first_snapshot.input_prefixes[0][-1].close,
        first_snapshot.outcome_windows[0][-1].close,
    )

    rendered_artifacts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "model-artifacts").rglob("*.json")
    )
    assert "target_log_return" not in rendered_artifacts
    assert rows[0]["target_log_return"] not in rendered_artifacts
    assert receipt.result.safe_payload()["dataset_materialization_sha256"] == (
        result.dataset_materialization_sha256
    )
    assert result == dataset.materialize_profiled_mtf_forward_supervised_dataset(
        policy,
        receipt=readiness_receipt,
        catalog=catalog,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
    )


def test_below_threshold_receipt_leaves_no_target_bearing_dataset(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    catalog = _catalog(pair_count=0)
    readiness_receipt = _readiness_receipt(
        catalog,
        artifact_root=tmp_path / "readiness-artifacts",
        repository=repository,
        attempt_id="zero-r1",
    )
    policy = dataset.freeze_profiled_mtf_forward_supervised_dataset_policy(
        readiness_receipt,
        code_revision_sha256=_sha256("dataset-code-r1"),
    )
    market_data_root = tmp_path / "market-data"

    result = dataset.materialize_profiled_mtf_forward_supervised_dataset(
        policy,
        receipt=readiness_receipt,
        catalog=catalog,
        market_data_root=market_data_root,
        repo_root=repository,
    )
    receipt = dataset.write_profiled_mtf_forward_supervised_dataset_receipt(
        result,
        policy=policy,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=repository,
        attempt_id="zero-dataset-r1",
    )

    assert result.status == "input_unavailable"
    assert result.dataset_path is None
    assert result.selected_pair_count == 0
    assert result.row_count == 0
    assert not market_data_root.exists()
    rendered = receipt.receipt_path.read_text(encoding="utf-8")
    assert "target_log_return" not in rendered
    assert "raw_snapshot_sha256" not in rendered


def test_rejects_stale_readiness_even_when_current_catalog_is_ready(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    original_catalog = _catalog(pair_count=30)
    readiness_receipt = _readiness_receipt(
        original_catalog,
        artifact_root=tmp_path / "readiness-artifacts",
        repository=repository,
        attempt_id="stale-r1",
    )
    policy = dataset.freeze_profiled_mtf_forward_supervised_dataset_policy(
        readiness_receipt,
        code_revision_sha256=_sha256("dataset-code-r1"),
    )

    with pytest.raises(ValueError, match="stale"):
        dataset.materialize_profiled_mtf_forward_supervised_dataset(
            policy,
            receipt=readiness_receipt,
            catalog=_catalog(pair_count=31),
            market_data_root=tmp_path / "market-data",
            repo_root=repository,
        )


def test_core_dataset_import_does_not_load_execution_or_transport_modules() -> None:
    source = Path(dataset.__file__).read_text(encoding="utf-8")
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
import thericher_v2.research.profiled_mtf_forward_supervised_dataset
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


def _catalog(
    *,
    pair_count: int,
) -> observer.KisMtfProfiledForwardOutcomeSnapshotCatalog:
    contract = _forward_contract()
    inventory = observer.KisMtfProfiledForwardOutcomeInventory(
        contract_sha256=contract.contract_sha256,
        target_ready_pair_count=pair_count,
        target_ready_manifest_sha256=_sha256(f"manifest-{pair_count}"),
        status="target_ready" if pair_count else "zero_target_ready",
    )
    snapshots = tuple(_snapshot(contract, pair_index) for pair_index in range(pair_count))
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
) -> observer.KisMtfProfiledForwardOutcomeSnapshot:
    input_end = datetime(2026, 8, 3, 19, 30, tzinfo=UTC) + timedelta(days=pair_index)
    input_prefixes = []
    outcome_windows = []
    for leg_index, target_key in enumerate(
        observer.KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
    ):
        symbol = target_key.split("/", maxsplit=1)[0]
        base = Decimal("100") + Decimal(pair_index) + Decimal(leg_index) * Decimal("10")
        input_prefixes.append(
            (
                _bar(
                    symbol=symbol,
                    start_ts=input_end - timedelta(minutes=1),
                    price=base,
                ),
            )
        )
        outcome_windows.append(
            tuple(
                _bar(
                    symbol=symbol,
                    start_ts=input_end + timedelta(minutes=minute),
                    price=base + Decimal(minute + 1) / Decimal("100"),
                )
                for minute in range(15)
            )
        )
    return observer.KisMtfProfiledForwardOutcomeSnapshot(
        contract_sha256=contract.contract_sha256,
        session_key_sha256=_sha256(f"session-{pair_index}"),
        input_observation_sha256=_sha256(f"input-{pair_index}"),
        witness_sha256=_sha256(f"witness-{pair_index}"),
        raw_snapshot_sha256=_sha256(f"snapshot-{pair_index}"),
        input_prefixes=tuple(input_prefixes),
        outcome_windows=tuple(outcome_windows),
    )


def _bar(*, symbol: str, start_ts: datetime, price: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price + Decimal("0.5"),
        volume=Decimal("100"),
        complete=True,
    )


def _readiness_receipt(
    catalog: observer.KisMtfProfiledForwardOutcomeSnapshotCatalog,
    *,
    artifact_root: Path,
    repository: Path,
    attempt_id: str,
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
        attempt_id=attempt_id,
    )


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
