from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from thericher_v2.data.kis_mtf_profiled_prospective_observer import (
    KisMtfProfiledForwardOutcomeInventory,
)
from thericher_v2.research import profiled_mtf_forward_campaign_readiness as readiness


def test_below_threshold_is_scoped_input_unavailable_with_the_fixed_campaign_shape() -> None:
    policy = _policy()

    result = readiness.evaluate_profiled_mtf_forward_campaign_readiness(
        policy,
        _inventory(29, policy.forward_outcome_contract_sha256),
    )

    assert result.status == "input_unavailable"
    assert result.target_ready_pair_count == 29
    assert policy.shape.required_pair_count == 30
    assert (
        policy.shape.train_pair_count,
        policy.shape.purge_pair_count,
        policy.shape.validation_pair_count,
    ) == (20, 2, 8)
    assert result.safe_payload()["scope"] == {
        "source_safe_inventory_only": True,
        "raw_snapshots_opened": False,
        "feature_values_opened": False,
        "target_or_return_values_opened": False,
        "model_trained": False,
        "gpu_allocated": False,
        "paper_input": False,
        "pnl_or_profitability_claim": False,
        "live_behavior": False,
    }


def test_threshold_or_larger_inventory_is_ready_without_opening_a_target() -> None:
    policy = _policy()

    result = readiness.evaluate_profiled_mtf_forward_campaign_readiness(
        policy,
        _inventory(31, policy.forward_outcome_contract_sha256),
    )

    assert result.status == "ready_for_private_campaign_freeze"
    assert result.target_ready_pair_count == 31
    rendered = json.dumps(result.safe_payload(), sort_keys=True)
    for forbidden in ("QQQ", "SPY", "100.5", "2026-", "local_paper"):
        assert forbidden not in rendered


def test_readiness_rejects_wrong_contract_and_stale_inventory_identity() -> None:
    policy = _policy()
    current = _inventory(30, policy.forward_outcome_contract_sha256, marker="current")
    result = readiness.evaluate_profiled_mtf_forward_campaign_readiness(policy, current)

    with pytest.raises(ValueError, match="stale or mismatched"):
        readiness.evaluate_profiled_mtf_forward_campaign_readiness(
            policy,
            _inventory(30, _digest("wrong-contract")),
        )
    with pytest.raises(ValueError, match="stale"):
        readiness.reattest_profiled_mtf_forward_campaign_readiness(
            result,
            policy=policy,
            inventory=_inventory(30, policy.forward_outcome_contract_sha256, marker="later"),
        )

    forged = object.__new__(KisMtfProfiledForwardOutcomeInventory)
    object.__setattr__(forged, "contract_sha256", policy.forward_outcome_contract_sha256)
    object.__setattr__(forged, "target_ready_pair_count", 1)
    object.__setattr__(forged, "target_ready_manifest_sha256", "not-a-hash")
    object.__setattr__(forged, "status", "target_ready")
    with pytest.raises(ValueError, match="forward outcome inventory is invalid"):
        readiness.evaluate_profiled_mtf_forward_campaign_readiness(policy, forged)


def test_receipt_is_external_idempotent_and_conflicts_on_changed_input(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    policy = _policy()
    result = readiness.evaluate_profiled_mtf_forward_campaign_readiness(
        policy,
        _inventory(0, policy.forward_outcome_contract_sha256),
    )

    first = readiness.write_profiled_mtf_forward_campaign_readiness_receipt(
        result,
        policy=policy,
        artifact_root=artifact_root,
        repo_root=repository,
        attempt_id="unit",
    )
    duplicate = readiness.write_profiled_mtf_forward_campaign_readiness_receipt(
        result,
        policy=policy,
        artifact_root=artifact_root,
        repo_root=repository,
        attempt_id="unit",
    )

    assert first == duplicate
    assert (
        readiness.load_profiled_mtf_forward_campaign_readiness_receipt(
            first.receipt_path,
            repo_root=repository,
        )
        == first
    )
    assert first.receipt_path.is_relative_to(artifact_root.resolve())
    text = first.receipt_path.read_text(encoding="utf-8")
    assert '"raw_rows_persisted":false' in text
    assert '"target_values_persisted":false' in text
    assert '"weights_persisted":false' in text
    assert "100.5" not in text

    tampered_path = artifact_root / "tampered.json"
    tampered_payload = json.loads(text)
    tampered_payload["readiness"]["target_ready_pair_count"] = 30
    tampered_path.write_text(json.dumps(tampered_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed|checksum"):
        readiness.load_profiled_mtf_forward_campaign_readiness_receipt(
            tampered_path,
            repo_root=repository,
        )

    changed = readiness.evaluate_profiled_mtf_forward_campaign_readiness(
        policy,
        _inventory(1, policy.forward_outcome_contract_sha256),
    )
    with pytest.raises(ValueError, match="conflicts"):
        readiness.write_profiled_mtf_forward_campaign_readiness_receipt(
            changed,
            policy=policy,
            artifact_root=artifact_root,
            repo_root=repository,
            attempt_id="unit",
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        readiness.write_profiled_mtf_forward_campaign_readiness_receipt(
            result,
            policy=policy,
            artifact_root=repository,
            repo_root=repository,
            attempt_id="repo",
        )


def test_core_and_runner_do_not_import_credential_network_or_execution_routes() -> None:
    script = """
import sys
import typing
import thericher_v2.research.profiled_mtf_forward_campaign_readiness as readiness
typing.get_type_hints(readiness.evaluate_profiled_mtf_forward_campaign_readiness)
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
    for path in (
        Path(readiness.__file__),
        Path("scripts/run_profiled_mtf_forward_campaign_readiness.py"),
    ):
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            ".env",
            "requests",
            "urllib",
            "socket",
            "thericher_v2.execution",
            "local_paper",
            "kis_live",
        ):
            assert forbidden not in source


def test_runner_closes_a_missing_local_inventory_without_external_access(tmp_path: Path) -> None:
    script = Path("scripts/run_profiled_mtf_forward_campaign_readiness.py")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--cache-root",
            str(tmp_path / "missing-cache"),
            "--market-data-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--repo-root",
            str(Path.cwd()),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 20
    assert json.loads(result.stdout) == {
        "campaign_id": readiness.PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
        "scope": {"source_safe_inventory_only": True},
        "status": "input_unavailable",
    }


def _policy() -> readiness.ProfiledMtfForwardCampaignReadinessPolicy:
    return readiness.freeze_profiled_mtf_forward_campaign_readiness_policy(
        forward_outcome_contract_sha256=_digest("forward-contract"),
        code_revision_sha256=_digest("code"),
    )


def _inventory(
    count: int,
    contract_sha256: str,
    *,
    marker: str = "inventory",
) -> KisMtfProfiledForwardOutcomeInventory:
    return KisMtfProfiledForwardOutcomeInventory(
        contract_sha256=contract_sha256,
        target_ready_pair_count=count,
        target_ready_manifest_sha256=_digest(f"{marker}-{count}"),
        status="target_ready" if count else "zero_target_ready",
    )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
