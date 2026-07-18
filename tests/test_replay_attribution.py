from __future__ import annotations

import hashlib
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from thericher_v2.research.replay_attribution import (
    FrozenReplayAttributionContract,
    attribute_frozen_local_paper_replay,
)


def test_attribution_is_hash_bound_read_only_and_local_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_fixture(tmp_path)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("attribution must not open a network connection")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == ".env":
            raise AssertionError("attribution must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    original_bytes = {
        path: path.read_bytes()
        for path in (
            source["summary_path"],
            source["validation_path"],
            source["events_path"],
            source["state_path"],
            source["emergency_path"],
        )
    }

    result = attribute_frozen_local_paper_replay(
        source_summary_path=source["summary_path"],
        contract=source["contract"],
        artifact_root=source["artifact_root"],
        attribution_id="attribution-r1",
        repository_root=source["repository_root"],
    )

    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert result.artifact_path == (
        source["artifact_root"] / "attribution" / "attribution-r1" / "summary.json"
    )
    assert payload["status"] == "attributed_only"
    assert payload["parent_verdict"] == "unsupported"
    assert payload["labels"]["profitability_claim"] is False
    assert payload["labels"]["ranking"] is False
    assert payload["totals"] == {
        "cell_count": 1,
        "baseline_cell_count": 1,
        "candidate_cell_count": 0,
        "local_paper_fill_count": 2,
        "all_final_positions_flat": True,
        "cross_cell_pnl_aggregation": "intentionally_omitted_non_independent_cells",
        "aggregate_omitted_reason": "cells_overlap_not_independent",
    }
    assert payload["verification_scope"] == {
        "fill_evidence": "shared_local_paper_replay_evidence",
        "claim": "arithmetic_consistency_only",
        "independent_execution_quality_evidence": False,
    }
    assert payload["cell_selection_scope"] == "fixed_pre_hoc_cells_selection_not_verified_here"
    assert payload["cells"][0]["accounting"] == {
        "realized_after_cost_pnl": "0.98",
        "gross_pnl": "1",
        "fee_cost": "0.02",
        "slippage_cost": "0",
        "fill_count": 2,
        "closed_segment_count": 1,
        "final_position": "0",
    }
    assert payload["cells"][0]["local_paper_verification"]["all_fills_local_paper"] is True
    assert result.local_paper_fill_count == 2
    assert all(path.read_bytes() == expected for path, expected in original_bytes.items())


def test_attribution_fails_closed_on_tampered_event_hash(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path)
    source["events_path"].write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="event JSONL hash mismatch"):
        attribute_frozen_local_paper_replay(
            source_summary_path=source["summary_path"],
            contract=source["contract"],
            artifact_root=source["artifact_root"],
            attribution_id="attribution-r1",
            repository_root=source["repository_root"],
        )

    assert not (source["artifact_root"] / "attribution" / "attribution-r1").exists()


def test_attribution_rejects_bad_summary_hash_and_repository_artifact_root(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path)
    bad_contract = FrozenReplayAttributionContract(
        **{**source["contract"].__dict__, "replay_summary_sha256": _sha256(b"wrong")}
    )

    with pytest.raises(ValueError, match="replay summary hash mismatch"):
        attribute_frozen_local_paper_replay(
            source_summary_path=source["summary_path"],
            contract=bad_contract,
            artifact_root=source["artifact_root"],
            attribution_id="attribution-r1",
            repository_root=source["repository_root"],
        )

    inside_repo = source["repository_root"] / "artifacts"
    inside_repo.mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        attribute_frozen_local_paper_replay(
            source_summary_path=source["summary_path"],
            contract=source["contract"],
            artifact_root=inside_repo,
            attribution_id="attribution-r2",
            repository_root=source["repository_root"],
        )


def _source_fixture(tmp_path: Path) -> dict[str, object]:
    repository_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repository_root.mkdir()
    artifact_root.mkdir()
    replay_dir = artifact_root / "daily-campaign" / "replay-r1" / "fold-1" / "baseline"
    replay_dir = replay_dir / "always_long" / "spy"
    replay_dir.mkdir(parents=True)
    events_path = replay_dir / "events.jsonl"
    state_path = replay_dir / "state.sqlite"
    emergency_path = replay_dir / "emergency.json"
    validation_path = artifact_root / "validation" / "replay-r1-fold-1-spy.json"
    validation_path.parent.mkdir()
    event_lines = (
        _event(
            seq=1,
            created_at="2026-01-02T00:00:00+00:00",
            side="buy",
            price="10",
            fee="0.01",
        ),
        _event(
            seq=2,
            created_at="2026-01-03T00:00:00+00:00",
            side="sell",
            price="11",
            fee="0.01",
        ),
    )
    events_path.write_text(
        "\n".join(json.dumps(line) for line in event_lines) + "\n",
        encoding="utf-8",
    )
    state_path.write_bytes(b"not-read-but-hash-bound")
    emergency_path.write_text('{"blocks_new_orders":false}\n', encoding="utf-8")
    event_reference = _docker_reference(events_path, artifact_root)
    state_reference = _docker_reference(state_path, artifact_root)
    emergency_reference = _docker_reference(emergency_path, artifact_root)
    validation = {
        "campaign_phase": "validation",
        "campaign_fold_id": "fold-1",
        "symbol": "SPY",
        "baseline_id": "always_long",
        "final_position": "0",
        "starting_cash": "10000",
        "ending_cash": "10000.98",
        "equity": "10000.98",
        "after_cost_pnl": "0.98",
        "pnl": "0.98",
        "gross_pnl": "1",
        "total_fees": "0.02",
        "total_slippage": "0",
        "trades": [{"client_order_id": "1"}, {"client_order_id": "2"}],
        "replay_evidence": {
            "event_jsonl": event_reference,
            "state_sqlite": state_reference,
            "emergency": emergency_reference,
        },
    }
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    validation_reference = _docker_reference(validation_path, artifact_root)
    source_campaign_summary_hash = _sha256(b"source-campaign")
    summary = {
        "schema_version": 1,
        "replay_id": "replay-r1",
        "source_campaign_id": "source-campaign-r1",
        "parent_sensitivity_verdict": "unsupported",
        "labels": {
            "development_only": True,
            "retrospective_only": True,
            "ranking": False,
            "promotion": False,
            "candidate_selection": False,
            "sealed_holdout": False,
            "profitability_claim": False,
        },
        "inputs": {
            "source_summary": {
                "path": "/app/model_artifacts/source.json",
                "sha256": source_campaign_summary_hash,
            },
            "r2": {
                "dataset_id": "r2-id",
                "dataset_hash": _sha256(b"r2-data"),
                "manifest_hash": _sha256(b"r2-manifest"),
            },
            "corporate_actions": {
                "dataset_id": "actions-id",
                "dataset_hash": _sha256(b"actions-data"),
                "manifest_hash": _sha256(b"actions-manifest"),
            },
        },
        "execution": {
            "backend": "torch_cpu",
            "training_runs": 0,
            "frozen_cells": 1,
            "baseline_cells": 1,
            "candidate_cells": 0,
            "fill_source": "local_paper",
            "all_final_positions_flat": True,
        },
        "cells": [
            {
                "fold_id": "fold-1",
                "kind": "baseline",
                "item_id": "always_long",
                "symbol": "SPY",
                "validation_artifact": validation_reference,
                "replay_evidence": {
                    "fill_source": "local_paper",
                    "event_jsonl": event_reference,
                    "state_sqlite": state_reference,
                    "emergency": emergency_reference,
                },
                "verification": {"events": 2, "trades": 2, "final_position": "0"},
            }
        ],
    }
    summary_path = artifact_root / "daily-campaign" / "replay-r1" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    contract = FrozenReplayAttributionContract(
        replay_id="replay-r1",
        source_campaign_id="source-campaign-r1",
        replay_summary_sha256=_sha256_file(summary_path),
        source_campaign_summary_sha256=source_campaign_summary_hash,
        parent_sensitivity_verdict="unsupported",
        r2_dataset_id="r2-id",
        r2_dataset_hash=summary["inputs"]["r2"]["dataset_hash"],
        r2_manifest_hash=summary["inputs"]["r2"]["manifest_hash"],
        corporate_action_dataset_id="actions-id",
        corporate_action_dataset_hash=summary["inputs"]["corporate_actions"]["dataset_hash"],
        corporate_action_manifest_hash=summary["inputs"]["corporate_actions"]["manifest_hash"],
        expected_cell_count=1,
        expected_baseline_cell_count=1,
        expected_candidate_cell_count=0,
    )
    return {
        "repository_root": repository_root,
        "artifact_root": artifact_root,
        "summary_path": summary_path,
        "validation_path": validation_path,
        "events_path": events_path,
        "state_path": state_path,
        "emergency_path": emergency_path,
        "contract": contract,
    }


def _event(*, seq: int, created_at: str, side: str, price: str, fee: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "seq": seq,
        "created_at": created_at,
        "event_type": "fill",
        "payload": {
            "source": "local_paper",
            "market": "US",
            "symbol": "SPY",
            "side": side,
            "quantity": "1",
            "price": price,
            "fee": fee,
        },
    }


def _docker_reference(path: Path, artifact_root: Path) -> dict[str, str]:
    return {
        "path": "/app/model_artifacts/" + path.relative_to(artifact_root).as_posix(),
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: Path) -> str:
    return _sha256(path.read_bytes())


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
