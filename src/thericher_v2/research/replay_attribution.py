"""Hash-bound, read-only accounting for frozen local-paper replay summaries."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    replay_local_paper_account,
)
from thericher_v2.research.trade_path_attribution import (
    TradePathEventArtifact,
    attribute_trade_paths_from_local_paper_events,
)
from thericher_v2.state import EventStore

_SHA256_PREFIX = "sha256:"
_DOCKER_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")


@dataclass(frozen=True)
class FrozenReplayAttributionContract:
    """Pinned source identities for one descriptive frozen-replay attribution."""

    replay_id: str
    source_campaign_id: str
    replay_summary_sha256: str
    source_campaign_summary_sha256: str
    parent_sensitivity_verdict: str
    r2_dataset_id: str
    r2_dataset_hash: str
    r2_manifest_hash: str
    corporate_action_dataset_id: str
    corporate_action_dataset_hash: str
    corporate_action_manifest_hash: str
    expected_cell_count: int = 36
    expected_baseline_cell_count: int = 18
    expected_candidate_cell_count: int = 18

    def __post_init__(self) -> None:
        for value, label in (
            (self.replay_id, "replay_id"),
            (self.source_campaign_id, "source_campaign_id"),
            (self.r2_dataset_id, "r2_dataset_id"),
            (self.corporate_action_dataset_id, "corporate_action_dataset_id"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label} is required")
        for value, label in (
            (self.replay_summary_sha256, "replay summary hash"),
            (self.source_campaign_summary_sha256, "source campaign summary hash"),
            (self.r2_dataset_hash, "r2 dataset hash"),
            (self.r2_manifest_hash, "r2 manifest hash"),
            (self.corporate_action_dataset_hash, "corporate-action dataset hash"),
            (self.corporate_action_manifest_hash, "corporate-action manifest hash"),
        ):
            _require_sha256(value, label)
        if self.parent_sensitivity_verdict != "unsupported":
            raise ValueError("frozen replay attribution requires parent unsupported")
        if (
            self.expected_cell_count <= 0
            or self.expected_baseline_cell_count < 0
            or self.expected_candidate_cell_count < 0
            or self.expected_baseline_cell_count + self.expected_candidate_cell_count
            != self.expected_cell_count
        ):
            raise ValueError("frozen replay attribution cell counts are inconsistent")


@dataclass(frozen=True)
class FrozenReplayAttributionResult:
    """One immutable descriptive attribution artifact written outside Git."""

    artifact_path: Path
    artifact_sha256: str
    cell_count: int
    local_paper_fill_count: int


def attribute_frozen_local_paper_replay(
    *,
    source_summary_path: Path,
    contract: FrozenReplayAttributionContract,
    artifact_root: Path,
    attribution_id: str,
    repository_root: Path | None = None,
) -> FrozenReplayAttributionResult:
    """Verify a frozen replay and write one compact descriptive accounting artifact.

    This routine never invokes a broker, reads credentials, accesses a network,
    trains a model, or mutates any source replay evidence.
    """

    root = _external_artifact_root(artifact_root, repository_root=repository_root)
    summary_path = _referenced_artifact_path(source_summary_path, root)
    _assert_hash(summary_path, contract.replay_summary_sha256, "replay summary")
    summary = _read_json_object(summary_path, "replay summary")
    cells = _validated_summary_cells(summary, contract)
    output_path = _new_attribution_path(root, attribution_id)

    attributed_cells = tuple(_attribute_cell(cell, root) for cell in cells)
    totals = _totals(attributed_cells)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frozen_local_paper_replay_attribution",
        "status": "attributed_only",
        "parent_verdict": contract.parent_sensitivity_verdict,
        "source_replay": {
            "replay_id": contract.replay_id,
            "source_campaign_id": contract.source_campaign_id,
            "summary": {
                "path": str(summary_path),
                "sha256": contract.replay_summary_sha256,
            },
            "parent_sensitivity_verdict": contract.parent_sensitivity_verdict,
        },
        "lineage": {
            "r2": {
                "dataset_id": contract.r2_dataset_id,
                "dataset_hash": contract.r2_dataset_hash,
                "manifest_hash": contract.r2_manifest_hash,
            },
            "corporate_actions": {
                "dataset_id": contract.corporate_action_dataset_id,
                "dataset_hash": contract.corporate_action_dataset_hash,
                "manifest_hash": contract.corporate_action_manifest_hash,
            },
            "source_campaign_summary_sha256": contract.source_campaign_summary_sha256,
        },
        "labels": {
            "development_only": True,
            "retrospective_only": True,
            "descriptive_only": True,
            "ranking": False,
            "promotion": False,
            "candidate_selection": False,
            "profitability_claim": False,
            "cells_are_not_independent": True,
        },
        "verification": {
            "source_summary_hash_verified": True,
            "all_referenced_artifact_hashes_verified": True,
            "all_fills_local_paper": True,
            "all_final_positions_flat": True,
            "training_runs": 0,
        },
        "verification_scope": {
            "fill_evidence": "shared_local_paper_replay_evidence",
            "claim": "arithmetic_consistency_only",
            "independent_execution_quality_evidence": False,
        },
        "cell_selection_scope": "fixed_pre_hoc_cells_selection_not_verified_here",
        "totals": totals,
        "cells": list(attributed_cells),
    }
    _write_json_once(output_path, payload)
    return FrozenReplayAttributionResult(
        artifact_path=output_path,
        artifact_sha256=_sha256_file(output_path),
        cell_count=len(attributed_cells),
        local_paper_fill_count=int(totals["local_paper_fill_count"]),
    )


def _validated_summary_cells(
    summary: Mapping[str, Any],
    contract: FrozenReplayAttributionContract,
) -> tuple[Mapping[str, Any], ...]:
    if (
        summary.get("schema_version") != SCHEMA_VERSION
        or summary.get("replay_id") != contract.replay_id
        or summary.get("source_campaign_id") != contract.source_campaign_id
        or summary.get("parent_sensitivity_verdict")
        != contract.parent_sensitivity_verdict
    ):
        raise ValueError("replay summary identity is not pinned to the attribution contract")
    labels = _mapping(summary.get("labels"), "replay summary labels")
    if labels != {
        "development_only": True,
        "retrospective_only": True,
        "ranking": False,
        "promotion": False,
        "candidate_selection": False,
        "sealed_holdout": False,
        "profitability_claim": False,
    }:
        raise ValueError("replay summary must remain development-only")
    inputs = _mapping(summary.get("inputs"), "replay summary inputs")
    _assert_lineage(
        _mapping(inputs.get("r2"), "replay summary r2 lineage"),
        dataset_id=contract.r2_dataset_id,
        dataset_hash=contract.r2_dataset_hash,
        manifest_hash=contract.r2_manifest_hash,
        label="r2",
    )
    _assert_lineage(
        _mapping(inputs.get("corporate_actions"), "replay summary corporate-action lineage"),
        dataset_id=contract.corporate_action_dataset_id,
        dataset_hash=contract.corporate_action_dataset_hash,
        manifest_hash=contract.corporate_action_manifest_hash,
        label="corporate actions",
    )
    source_summary = _mapping(inputs.get("source_summary"), "source campaign summary")
    if source_summary.get("sha256") != contract.source_campaign_summary_sha256:
        raise ValueError("source campaign summary hash is not pinned")
    execution = _mapping(summary.get("execution"), "replay execution")
    if execution != {
        "backend": "torch_cpu",
        "training_runs": 0,
        "frozen_cells": contract.expected_cell_count,
        "baseline_cells": contract.expected_baseline_cell_count,
        "candidate_cells": contract.expected_candidate_cell_count,
        "fill_source": LOCAL_PAPER_SOURCE,
        "all_final_positions_flat": True,
    }:
        raise ValueError("replay execution contract is not immutable")
    raw_cells = summary.get("cells")
    if not isinstance(raw_cells, list) or len(raw_cells) != contract.expected_cell_count:
        raise ValueError("replay summary has the wrong frozen cell count")
    cells = tuple(_mapping(cell, "replay summary cell") for cell in raw_cells)
    identities = {
        (
            cell.get("fold_id"),
            cell.get("kind"),
            cell.get("item_id"),
            cell.get("symbol"),
        )
        for cell in cells
    }
    if len(identities) != len(cells):
        raise ValueError("replay summary cells must be unique")
    if (
        sum(cell.get("kind") == "baseline" for cell in cells)
        != contract.expected_baseline_cell_count
    ):
        raise ValueError("replay summary baseline count is not pinned")
    if (
        sum(cell.get("kind") == "candidate" for cell in cells)
        != contract.expected_candidate_cell_count
    ):
        raise ValueError("replay summary candidate count is not pinned")
    if any(cell.get("kind") not in {"baseline", "candidate"} for cell in cells):
        raise ValueError("replay summary contains an unknown cell kind")
    return tuple(
        sorted(
            cells,
            key=lambda cell: (
                str(cell["fold_id"]),
                str(cell["kind"]),
                str(cell["item_id"]),
                str(cell["symbol"]),
            ),
        )
    )


def _attribute_cell(cell: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    fold_id = _text(cell.get("fold_id"), "cell fold_id")
    kind = _text(cell.get("kind"), "cell kind")
    item_id = _text(cell.get("item_id"), "cell item_id")
    symbol = _text(cell.get("symbol"), "cell symbol").upper()
    validation_reference = _artifact_reference(
        cell.get("validation_artifact"), artifact_root, "validation artifact"
    )
    evidence = _mapping(cell.get("replay_evidence"), "replay evidence")
    event_reference = _artifact_reference(
        evidence.get("event_jsonl"), artifact_root, "event JSONL"
    )
    state_reference = _artifact_reference(
        evidence.get("state_sqlite"), artifact_root, "state SQLite"
    )
    emergency_reference = _artifact_reference(
        evidence.get("emergency"), artifact_root, "emergency state"
    )
    if evidence.get("fill_source") != LOCAL_PAPER_SOURCE:
        raise ValueError("replay evidence does not use local_paper")
    validation = _read_json_object(validation_reference["path"], "validation artifact")
    _assert_validation_cell(
        validation,
        cell=cell,
        validation_reference=validation_reference,
        event_reference=event_reference,
        state_reference=state_reference,
        emergency_reference=emergency_reference,
    )
    trades = validation.get("trades")
    if not isinstance(trades, list):
        raise ValueError("validation artifact trades must be a list")
    expected_fill_count = len(trades)
    attribution = attribute_trade_paths_from_local_paper_events(
        event_artifacts=(
            TradePathEventArtifact(
                path=event_reference["path"],
                expected_fill_count=expected_fill_count,
                slice_id=fold_id,
                variant_id=f"{kind}:{item_id}",
                symbol=symbol,
            ),
        ),
        bars=(),
    )
    local_verification = attribution.local_paper_verification
    if (
        local_verification.get("all_fills_local_paper") is not True
        or local_verification.get("local_paper_fill_count_matches_expected") is not True
    ):
        raise ValueError("replay event evidence is not complete local-paper evidence")
    events = tuple(EventStore(state_reference["path"], event_reference["path"]).iter_events())
    if len(events) != _non_negative_int(
        _mapping(cell.get("verification"), "cell verification").get("events"),
        "cell event count",
    ):
        raise ValueError("replay event count does not match the summary")
    fills = tuple(event for event in events if event.event_type == "fill")
    if len(fills) != expected_fill_count or any(
        event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fills
    ):
        raise ValueError("replay fills do not match complete local-paper evidence")
    starting_cash = _decimal(validation.get("starting_cash"), "starting_cash")
    account = replay_local_paper_account(
        EventStore(state_reference["path"], event_reference["path"]),
        starting_cash=starting_cash,
    )
    if account.positions:
        raise ValueError("replayed local-paper account must finish flat")
    after_cost_pnl = _decimal(validation.get("after_cost_pnl"), "after_cost_pnl")
    if _decimal(validation.get("pnl"), "pnl") != after_cost_pnl:
        raise ValueError("validation pnl does not match after-cost pnl")
    if account.cash - starting_cash != after_cost_pnl:
        raise ValueError("replayed cash does not match validation after-cost pnl")
    if _decimal(attribution.metrics["fee_aware_delta_sum"], "fee-aware delta") != after_cost_pnl:
        raise ValueError("FIFO realized pnl does not match validation after-cost pnl")
    ending_cash = _decimal(validation.get("ending_cash"), "ending_cash")
    if ending_cash != account.cash or _decimal(validation.get("equity"), "equity") != ending_cash:
        raise ValueError("validation ending cash/equity does not match replay")
    verification = _mapping(cell.get("verification"), "cell verification")
    if (
        _decimal(verification.get("final_position"), "summary final position") != 0
        or _non_negative_int(verification.get("trades"), "summary trade count")
        != expected_fill_count
    ):
        raise ValueError("replay summary does not match flat local-paper accounting")
    return {
        "cell": {
            "fold_id": fold_id,
            "kind": kind,
            "item_id": item_id,
            "symbol": symbol,
        },
        "evidence": {
            "validation_artifact": _reference_payload(validation_reference),
            "event_jsonl": _reference_payload(event_reference),
            "state_sqlite": _reference_payload(state_reference),
            "emergency": _reference_payload(emergency_reference),
        },
        "accounting": {
            "realized_after_cost_pnl": _decimal_text(after_cost_pnl),
            "gross_pnl": _decimal_text(_decimal(validation.get("gross_pnl"), "gross_pnl")),
            "fee_cost": _decimal_text(_decimal(validation.get("total_fees"), "total_fees")),
            "slippage_cost": _decimal_text(
                _decimal(validation.get("total_slippage"), "total_slippage")
            ),
            "fill_count": expected_fill_count,
            "closed_segment_count": attribution.metrics["closed_segment_count"],
            "final_position": "0",
        },
        "local_paper_verification": {
            "all_fills_local_paper": True,
            "fill_count_matches_expected": True,
            "replayed_cash_delta": _decimal_text(account.cash - starting_cash),
        },
    }


def _assert_validation_cell(
    validation: Mapping[str, Any],
    *,
    cell: Mapping[str, Any],
    validation_reference: Mapping[str, Any],
    event_reference: Mapping[str, Any],
    state_reference: Mapping[str, Any],
    emergency_reference: Mapping[str, Any],
) -> None:
    if (
        validation.get("campaign_phase") != "validation"
        or validation.get("campaign_fold_id") != cell.get("fold_id")
        or str(validation.get("symbol") or "").upper() != str(cell.get("symbol") or "").upper()
        or validation.get("final_position") != "0"
    ):
        raise ValueError("validation artifact does not match its frozen replay cell")
    if cell.get("kind") == "baseline":
        if validation.get("baseline_id") != cell.get("item_id"):
            raise ValueError("validation baseline id does not match replay cell")
    elif cell.get("kind") == "candidate":
        run_id = _text(validation.get("run_id"), "validation run_id")
        if f"candidate-{cell.get('item_id')}-" not in run_id:
            raise ValueError("validation candidate id does not match replay cell")
    else:
        raise ValueError("validation cell kind is unknown")
    validation_evidence = _mapping(validation.get("replay_evidence"), "validation replay evidence")
    for key, expected in (
        ("event_jsonl", event_reference),
        ("state_sqlite", state_reference),
        ("emergency", emergency_reference),
    ):
        actual = _mapping(validation_evidence.get(key), f"validation {key}")
        if actual.get("sha256") != expected["sha256"]:
            raise ValueError("validation replay evidence hash does not match summary")
    if validation_reference["sha256"] == "":
        raise ValueError("validation artifact hash is required")


def _totals(cells: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {
        "cell_count": len(cells),
        "baseline_cell_count": sum(cell["cell"]["kind"] == "baseline" for cell in cells),
        "candidate_cell_count": sum(cell["cell"]["kind"] == "candidate" for cell in cells),
        "local_paper_fill_count": sum(cell["accounting"]["fill_count"] for cell in cells),
        "all_final_positions_flat": True,
        "cross_cell_pnl_aggregation": "intentionally_omitted_non_independent_cells",
        "aggregate_omitted_reason": "cells_overlap_not_independent",
    }


def _artifact_reference(value: object, artifact_root: Path, label: str) -> dict[str, Any]:
    reference = _mapping(value, label)
    path = _referenced_artifact_path(_text(reference.get("path"), f"{label} path"), artifact_root)
    expected_hash = _text(reference.get("sha256"), f"{label} hash")
    _require_sha256(expected_hash, f"{label} hash")
    _assert_hash(path, expected_hash, label)
    return {"path": path, "sha256": expected_hash}


def _reference_payload(reference: Mapping[str, Any]) -> dict[str, str]:
    return {"path": str(reference["path"]), "sha256": str(reference["sha256"])}


def _assert_lineage(
    observed: Mapping[str, Any],
    *,
    dataset_id: str,
    dataset_hash: str,
    manifest_hash: str,
    label: str,
) -> None:
    if observed != {
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "manifest_hash": manifest_hash,
    }:
        raise ValueError(f"{label} lineage is not pinned")


def _external_artifact_root(path: Path, *, repository_root: Path | None) -> Path:
    requested = Path(path)
    if requested.is_symlink():
        raise ValueError("attribution artifact root cannot be a symlink")
    try:
        root = requested.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("attribution artifact root is missing") from exc
    if not root.is_dir():
        raise ValueError("attribution artifact root must be a directory")
    if repository_root is not None:
        repo = Path(repository_root).resolve(strict=False)
        if _is_within(root, repo) and not (
            repo == Path("/app").resolve() and root == Path("/app/model_artifacts").resolve()
        ):
            raise ValueError("attribution artifact root must stay outside Git")
    return root


def _referenced_artifact_path(value: Path | str, artifact_root: Path) -> Path:
    raw = str(value)
    docker_path = PurePosixPath(raw)
    if docker_path.is_absolute() and _is_under_docker_artifact_root(docker_path):
        relative = docker_path.relative_to(_DOCKER_ARTIFACT_ROOT)
        candidate = artifact_root.joinpath(*relative.parts)
    else:
        candidate = Path(value)
    if candidate.is_symlink():
        raise ValueError("replay artifact cannot be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("replay artifact is missing") from exc
    if not resolved.is_file() or not _is_within(resolved, artifact_root):
        raise ValueError("replay artifact must be a file under the artifact root")
    return resolved


def _is_under_docker_artifact_root(path: PurePosixPath) -> bool:
    try:
        path.relative_to(_DOCKER_ARTIFACT_ROOT)
    except ValueError:
        return False
    return True


def _new_attribution_path(artifact_root: Path, attribution_id: str) -> Path:
    if (
        not isinstance(attribution_id, str)
        or not attribution_id
        or attribution_id in {".", ".."}
        or any(character in attribution_id for character in "\\/:")
    ):
        raise ValueError("attribution_id must be one safe path component")
    destination = artifact_root / "attribution" / attribution_id / "summary.json"
    if destination.parent.exists() or destination.exists():
        raise FileExistsError("attribution destination already exists")
    return destination


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=False)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc
    return _mapping(payload, label)


def _assert_hash(path: Path, expected_hash: str, label: str) -> None:
    _require_sha256(expected_hash, f"{label} hash")
    actual_hash = _sha256_file(path)
    if actual_hash != expected_hash:
        raise ValueError(f"{label} hash mismatch")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{_SHA256_PREFIX}{digest.hexdigest()}"


def _require_sha256(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith(_SHA256_PREFIX)
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must use lowercase sha256:<64 hex>")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    return value


def _decimal(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    return parsed


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if parsed < 0 or str(parsed) != str(value):
        raise ValueError(f"{label} must be a non-negative integer")
    return parsed


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
