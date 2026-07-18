"""Prepare or explicitly execute the frozen RAW D1 explicit-event replay.

This is deliberately a local, read-only bridge between Data's immutable
corporate-action snapshot and the existing daily-campaign preparation contract.
It does not acquire data, read environment files, inspect CUDA, or train. By
default it only prepares the plan; ``--execute`` runs its already-frozen 36
cells through the local paper simulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from thericher_v2.data import (
    load_cataloged_corporate_actions,
    load_cataloged_yahoo_daily_1d_bars,
)
from thericher_v2.research.daily_campaign import (
    DAILY_SYMBOLS,
    DailyCampaignPlan,
    DailyCatalogFacts,
    DailyExplicitEventReplayPlan,
    build_daily_campaign_plan,
    prepare_daily_explicit_event_replay,
    run_daily_explicit_event_replay,
)

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True)
class PreparedReplay:
    campaign: DailyCampaignPlan
    replay_plan: DailyExplicitEventReplayPlan
    artifact_root: Path
    repo_root: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the fixed RAW D1 explicit-event replay; execute frozen "
            "local-paper cells only with --execute."
        )
    )
    parser.add_argument("--r2-subset", type=Path, required=True)
    parser.add_argument("--r2-dataset-id", required=True)
    parser.add_argument("--r2-dataset-hash", required=True)
    parser.add_argument("--r2-manifest-hash", required=True)
    parser.add_argument("--catalog-id", required=True)
    parser.add_argument("--catalog-constructed-as-utc", required=True)
    parser.add_argument("--corporate-action-snapshot", type=Path, required=True)
    parser.add_argument("--corporate-action-dataset-id", required=True)
    parser.add_argument("--corporate-action-dataset-hash", required=True)
    parser.add_argument("--corporate-action-manifest-hash", required=True)
    parser.add_argument("--source-campaign-id", required=True)
    parser.add_argument("--source-summary-sha256", required=True)
    parser.add_argument("--replay-id", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--execute", action="store_true")
    return parser


def prepare_frozen_explicit_event_replay(args: argparse.Namespace) -> dict[str, Any]:
    """Load attested local inputs and freeze a plan without replay execution."""

    prepared = _prepare_replay(args)
    return _prepared_payload(prepared.replay_plan)


def execute_frozen_explicit_event_replay(args: argparse.Namespace) -> dict[str, Any]:
    """Prepare and execute the frozen explicit-event cells only when requested."""

    prepared = _prepare_replay(args)
    result = run_daily_explicit_event_replay(
        prepared.campaign,
        replay_plan=prepared.replay_plan,
        artifact_root=prepared.artifact_root,
        work_root=(
            prepared.artifact_root / "daily-campaign" / prepared.replay_plan.replay_id
        ),
        repo_root=prepared.repo_root,
    )
    return _executed_payload(result)


def _prepare_replay(args: argparse.Namespace) -> PreparedReplay:
    repo_root = Path(args.repo_root).resolve()
    artifact_root = _external_directory(Path(args.artifact_root), "artifact root", repo_root)
    r2_subset = _external_file(Path(args.r2_subset), "r2 subset", repo_root)
    _verify_file_hash(
        r2_subset.parent / "manifest.json",
        args.r2_manifest_hash,
        "r2 manifest",
    )
    _require_sha256(args.r2_dataset_hash, "r2 dataset hash")
    _require_sha256(args.corporate_action_dataset_hash, "corporate-action dataset hash")
    _require_sha256(args.corporate_action_manifest_hash, "corporate-action manifest hash")
    _require_sha256(args.source_summary_sha256, "source summary hash")

    cataloged_bars = tuple(
        load_cataloged_yahoo_daily_1d_bars(
            r2_subset,
            dataset_id=args.r2_dataset_id,
            expected_dataset_hash=args.r2_dataset_hash,
            symbol=symbol,
        )
        for symbol in DAILY_SYMBOLS
    )
    campaign = build_daily_campaign_plan(
        cataloged_bars,
        catalog_facts=DailyCatalogFacts(
            catalog_id=args.catalog_id,
            constructed_as_of_utc=_parse_utc(args.catalog_constructed_as_utc),
            development_training_eligible=True,
        ),
        campaign_id=args.source_campaign_id,
    )
    observed_session_dates = {
        symbol: frozenset(session.date() for session in campaign.common_sessions)
        for symbol in DAILY_SYMBOLS
    }
    snapshot = _external_directory(
        Path(args.corporate_action_snapshot),
        "corporate-action snapshot",
        repo_root,
    )
    _assert_tiingo_snapshot_contract(snapshot)
    corporate_actions = load_cataloged_corporate_actions(
        snapshot,
        dataset_id=args.corporate_action_dataset_id,
        expected_dataset_hash=args.corporate_action_dataset_hash,
        expected_manifest_hash=args.corporate_action_manifest_hash,
        expected_r2_dataset_id=args.r2_dataset_id,
        expected_r2_dataset_hash=args.r2_dataset_hash,
        expected_r2_manifest_hash=args.r2_manifest_hash,
        observed_session_dates=observed_session_dates,
        require_replay_eligible=True,
        repo_root=repo_root,
    )

    replay_plan = prepare_daily_explicit_event_replay(
        campaign,
        corporate_actions=corporate_actions,
        source_summary_path=(
            artifact_root / "daily-campaign" / args.source_campaign_id / "summary.json"
        ),
        expected_source_summary_sha256=args.source_summary_sha256,
        replay_id=args.replay_id,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return PreparedReplay(
        campaign=campaign,
        replay_plan=replay_plan,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )


def _prepared_payload(prepared: Any) -> dict[str, Any]:
    baseline_cells = tuple(cell for cell in prepared.cells if cell.kind == "baseline")
    candidate_cells = tuple(cell for cell in prepared.cells if cell.kind == "candidate")
    checkpoint_paths = {cell.checkpoint_path for cell in candidate_cells}
    if (
        prepared.training_runs != 0
        or len(baseline_cells) != 18
        or len(candidate_cells) != 18
        or None in checkpoint_paths
        or len(checkpoint_paths) != 6
        or any(
            cell.standardization is None
            or cell.standardization.fold_id != cell.fold_id
            for cell in candidate_cells
        )
    ):
        raise RuntimeError("explicit-event preparation contract is incomplete")
    return {
        "status": "prepared_not_executed",
        "replay_id": prepared.replay_id,
        "source_campaign_id": prepared.source_campaign_id,
        "corporate_action_dataset_id": prepared.corporate_action_dataset_id,
        "corporate_action_dataset_hash": prepared.corporate_action_dataset_hash,
        "corporate_action_manifest_hash": prepared.corporate_action_manifest_hash,
        "r2_dataset_id": prepared.r2_dataset_id,
        "r2_dataset_hash": prepared.r2_dataset_hash,
        "r2_manifest_hash": prepared.r2_manifest_hash,
        "source_summary_sha256": prepared.source_summary_sha256,
        "parent_sensitivity_verdict": prepared.parent_sensitivity_verdict,
        "training_runs": 0,
        "verified_checkpoint_count": len(checkpoint_paths),
        "fold_local_prefit_standardization": "preserved",
        "replay_cells": {
            "frozen": len(prepared.cells),
            "baseline": len(baseline_cells),
            "candidate": len(candidate_cells),
            "executed": 0,
        },
    }


def _executed_payload(result: Any) -> dict[str, Any]:
    replay_plan = result.replay_plan
    baseline_cells = tuple(cell for cell in result.cells if cell.cell.kind == "baseline")
    candidate_cells = tuple(cell for cell in result.cells if cell.cell.kind == "candidate")
    return {
        "status": "executed",
        "replay_id": replay_plan.replay_id,
        "source_campaign_id": replay_plan.source_campaign_id,
        "parent_sensitivity_verdict": replay_plan.parent_sensitivity_verdict,
        "training_runs": replay_plan.training_runs,
        "execution_backend": result.execution_backend,
        "replay_cells": {
            "executed": len(result.cells),
            "baseline": len(baseline_cells),
            "candidate": len(candidate_cells),
            "fill_source": "local_paper",
            "all_final_positions_flat": all(
                cell.replay.result.final_position == 0 for cell in result.cells
            ),
        },
        "summary": {
            "path": str(result.summary_path),
            "sha256": result.summary_sha256,
        },
    }


def _assert_tiingo_snapshot_contract(snapshot: Path) -> None:
    try:
        payload = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo corporate-action manifest is not readable JSON") from exc
    if not isinstance(payload, dict) or payload.get("campaign_coverage") != {
        "start": "2022-11-22",
        "end": "2026-06-22",
    }:
        raise ValueError("Tiingo corporate-action snapshot has the wrong campaign coverage")
    if payload.get("scope") != {
        "retrospective_development_replay_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
    }:
        raise ValueError("Tiingo corporate-action snapshot scope is not replay-only")
    if payload.get("tiingo_source_contract") != {
        "source": "Tiingo standard EOD API",
        "endpoint_template": "https://api.tiingo.com/tiingo/daily/{symbol}/prices",
        "normalization_fields": ["date", "divCash", "splitFactor"],
        "raw_response_policy": "exact_per_symbol_bytes",
    }:
        raise ValueError("Tiingo corporate-action source contract is not pinned")
    expected_sources = {
        symbol: f"tiingo-standard-eod-{symbol.lower()}" for symbol in DAILY_SYMBOLS
    }
    sources = payload.get("raw_sources")
    if not isinstance(sources, list) or len(sources) != len(expected_sources):
        raise ValueError("Tiingo corporate-action raw source matrix is incomplete")
    by_id = {source.get("source_id"): source for source in sources if isinstance(source, dict)}
    if set(by_id) != set(expected_sources.values()):
        raise ValueError("Tiingo corporate-action source identifiers are not pinned")
    for symbol, source_id in expected_sources.items():
        source = by_id[source_id]
        if (
            source.get("provider") != "Tiingo standard EOD API"
            or source.get("source_kind") != "licensed_api"
            or source.get("acquisition_mode") != "authorized_api"
            or source.get("source_url")
            != f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
            or source.get("symbols") != [symbol]
            or source.get("event_types") != ["cash_distribution", "split"]
        ):
            raise ValueError("Tiingo corporate-action source entry is inconsistent")


def _external_file(path: Path, label: str, repo_root: Path) -> Path:
    resolved = _external_path(path, label, repo_root)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a readable file")
    return resolved


def _external_directory(path: Path, label: str, repo_root: Path) -> Path:
    resolved = _external_path(path, label, repo_root)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a readable directory")
    return resolved


def _external_path(path: Path, label: str, repo_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    resolved = candidate.resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        if repo_root == Path("/app").resolve():
            docker_mount_roots = (
                Path("/app/market_data").resolve(),
                Path("/app/model_artifacts").resolve(),
            )
            if any(
                resolved == mount_root or mount_root in resolved.parents
                for mount_root in docker_mount_roots
            ):
                return resolved
        raise ValueError(f"{label} must stay outside the Git workspace")
    return resolved


def _verify_file_hash(path: Path, expected_hash: str, label: str) -> None:
    _require_sha256(expected_hash, f"{label} hash")
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"{label} is not readable") from exc
    if f"{_SHA256_PREFIX}{digest}" != expected_hash:
        raise ValueError(f"{label} SHA-256 mismatch")


def _require_sha256(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith(_SHA256_PREFIX)
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must use lowercase sha256:<64 hex>")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("catalog constructed time must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("catalog constructed time must be UTC")
    return parsed.astimezone(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = (
            execute_frozen_explicit_event_replay(args)
            if args.execute
            else prepare_frozen_explicit_event_replay(args)
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
