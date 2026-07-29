from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.campaign_registry import (
    CampaignRegistryLockedError,
    register_campaign_outcome,
    register_frozen_campaign,
)


def test_registry_appends_idempotent_frozen_contract_and_outcome(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    first = register_frozen_campaign(
        contract_hash=_digest("contract-1"),
        dataset_hash=_digest("dataset"),
        split_hash=_digest("split"),
        cost_model_hash=_digest("cost"),
        trial_family="norgate-target-free-representation",
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
        recorded_at=now,
    )

    assert first.trial_index == 1
    assert first.record_path == artifact_root / "_control" / "ledger" / "2026-07.jsonl"
    frozen_payload = _records(first.record_path)
    assert len(frozen_payload) == 1
    assert frozen_payload[0] == {
        "campaign_contract_hash": _digest("contract-1"),
        "cost_model_hash": _digest("cost"),
        "dataset_hash": _digest("dataset"),
        "holdout_access": "none",
        "promotion_eligible": False,
        "record_id": f"campaign:{_digest('contract-1')[7:]}",
        "record_sha256": first.record_sha256,
        "record_type": "campaign_frozen",
        "recorded_at": "2026-07-29T12:00:00+00:00",
        "registry_version": 1,
        "role": "engine_research",
        "schema_version": 1,
        "split_hash": _digest("split"),
        "trial_family": "norgate-target-free-representation",
        "trial_index": 1,
    }
    assert "price" not in first.record_path.read_text(encoding="utf-8").lower()
    assert "credential" not in first.record_path.read_text(encoding="utf-8").lower()

    reattached = register_frozen_campaign(
        contract_hash=_digest("contract-1"),
        dataset_hash=_digest("dataset"),
        split_hash=_digest("split"),
        cost_model_hash=_digest("cost"),
        trial_family="norgate-target-free-representation",
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
        recorded_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    assert reattached == first
    assert len(_records(first.record_path)) == 1

    second = register_frozen_campaign(
        contract_hash=_digest("contract-2"),
        dataset_hash=_digest("dataset"),
        split_hash=_digest("split"),
        cost_model_hash=_digest("cost"),
        trial_family="norgate-target-free-representation",
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
        recorded_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    assert second.trial_index == 2

    outcome = register_campaign_outcome(
        contract_hash=first.contract_hash,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=_digest("source-safe-summary"),
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
        recorded_at=datetime(2026, 7, 30, 1, 0, tzinfo=UTC),
    )
    assert outcome.contract_hash == first.contract_hash
    assert outcome.outcome_class == "non_promoting_completed"
    assert len(_records(second.record_path)) == 3


def test_registry_rejects_git_local_artifact_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = repo_root / "model-artifacts"
    artifact_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="outside the Git workspace"):
        register_frozen_campaign(
            contract_hash=_digest("contract"),
            dataset_hash=_digest("dataset"),
            split_hash=_digest("split"),
            cost_model_hash=_digest("cost"),
            trial_family="unit-test-family",
            holdout_access="none",
            artifact_root=artifact_root,
            repo_root=repo_root,
        )


def test_registry_requires_frozen_contract_before_outcome(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()

    with pytest.raises(ValueError, match="requires a frozen registry record"):
        register_campaign_outcome(
            contract_hash=_digest("missing-contract"),
            outcome_class="non_promoting_completed",
            outcome_reference_sha256=_digest("summary"),
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )


def test_registry_lock_is_scoped_to_the_external_ledger(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    ledger_root = artifact_root / "_control" / "ledger"
    ledger_root.mkdir(parents=True)
    (ledger_root / ".campaign-registry.lock").write_text("held\n", encoding="utf-8")

    with pytest.raises(CampaignRegistryLockedError, match="another writer"):
        register_frozen_campaign(
            contract_hash=_digest("contract"),
            dataset_hash=_digest("dataset"),
            split_hash=_digest("split"),
            cost_model_hash=_digest("cost"),
            trial_family="unit-test-family",
            holdout_access="none",
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
