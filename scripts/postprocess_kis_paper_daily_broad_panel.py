"""Freeze and check one broad KIS Paper D1 panel after its collector exits."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_EVIDENCE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_EVIDENCE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    KisPaperDailyBroadPanel,
    KisPaperDailyBroadPanelContinuityComparison,
    load_materialized_kis_paper_daily_broad_panel,
    materialize_kis_paper_daily_broad_panel,
    materialize_kis_paper_daily_broad_panel_continuity,
)

_RECOVERY_EXIT = 20
_POSTRUN_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-broad-panel-postrun-v1"
)
_GENERATION_604_MANIFEST = (
    KIS_PAPER_DAILY_BROAD_PANEL_ROOT
    / "panel=2c3b9ddddc7160620210"
    / "manifest.json"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Materialize one stable panel and retain only source-safe outcome facts."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline-manifest",
        type=Path,
        default=_GENERATION_604_MANIFEST,
    )
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_BROAD_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=KIS_PAPER_DAILY_BROAD_PANEL_ROOT)
    parser.add_argument(
        "--panel-artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_BROAD_PANEL_EVIDENCE_ROOT,
    )
    parser.add_argument(
        "--continuity-artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_EVIDENCE_ROOT,
    )
    parser.add_argument(
        "--postrun-artifact-root",
        type=Path,
        default=_POSTRUN_ARTIFACT_ROOT,
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args(argv)

    repository_root = _repository_root(args.repository_root)
    try:
        candidate = materialize_kis_paper_daily_broad_panel(
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            artifact_root=args.panel_artifact_root,
            repo_root=repository_root,
        )
    except (OSError, ValueError) as error:
        return _emit_retry(
            artifact_root=args.postrun_artifact_root,
            repository_root=repository_root,
            reason=_materialization_reason(error),
        )

    try:
        baseline = load_materialized_kis_paper_daily_broad_panel(
            args.baseline_manifest,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            repo_root=repository_root,
        )
        continuity = materialize_kis_paper_daily_broad_panel_continuity(
            baseline_manifest_path=args.baseline_manifest,
            candidate_manifest_path=candidate.manifest_path,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            artifact_root=args.continuity_artifact_root,
            repo_root=repository_root,
        )
    except (OSError, ValueError) as error:
        return _emit_retry(
            artifact_root=args.postrun_artifact_root,
            repository_root=repository_root,
            reason=_continuity_reason(error),
            candidate=candidate.panel,
        )

    reason = _postrun_reason(
        baseline=baseline,
        candidate=candidate.panel,
        comparison=continuity.comparison,
    )
    payload = _postrun_payload(
        status="complete" if reason is None else "retry",
        reason="stable_full_breadth_panel" if reason is None else reason,
        baseline=baseline,
        candidate=candidate.panel,
        comparison=continuity.comparison,
        candidate_manifest_sha256=candidate.manifest_hash,
        continuity_receipt_sha256=continuity.receipt_hash,
    )
    receipt_sha256 = _write_receipt(
        artifact_root=args.postrun_artifact_root,
        repository_root=repository_root,
        payload=payload,
    )
    _emit({**payload, "receipt_sha256": receipt_sha256})
    return 0 if reason is None else _RECOVERY_EXIT


def _postrun_reason(
    *,
    baseline: KisPaperDailyBroadPanel,
    candidate: KisPaperDailyBroadPanel,
    comparison: KisPaperDailyBroadPanelContinuityComparison,
) -> str | None:
    if comparison.status != "equal":
        return "continuity_mismatch"
    if candidate.covered_target_count != len(candidate.target_keys):
        return "full_breadth_coverage_incomplete"
    if candidate.zero_coverage_target_count != 0:
        return "full_breadth_coverage_incomplete"
    if candidate.quarantined_target_count != 0:
        return "candidate_quarantine_present"
    if candidate.covered_target_count < baseline.covered_target_count:
        return "coverage_regressed_from_baseline"
    if candidate.zero_coverage_target_count > baseline.zero_coverage_target_count:
        return "coverage_regressed_from_baseline"
    if candidate.quarantined_target_count > baseline.quarantined_target_count:
        return "coverage_regressed_from_baseline"
    if comparison.shared_target_count < baseline.covered_target_count:
        return "shared_target_coverage_regressed"
    if comparison.shared_row_count < _row_count(baseline):
        return "shared_row_coverage_regressed"
    return None


def _row_count(panel: KisPaperDailyBroadPanel) -> int:
    return sum(target.bar_count for target in panel.targets_by_key.values())


def _emit_retry(
    *,
    artifact_root: Path,
    repository_root: Path,
    reason: str,
    candidate: KisPaperDailyBroadPanel | None = None,
) -> int:
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "kis_paper_daily_broad_panel_postrun",
        "status": "retry",
        "reason": reason,
        "route_isolation": _route_isolation(),
        "artifact_policy": _artifact_policy(),
    }
    if candidate is not None:
        payload["candidate"] = _candidate_payload(candidate, manifest_sha256=None)
    receipt_sha256 = _write_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        payload=payload,
    )
    _emit({**payload, "receipt_sha256": receipt_sha256})
    return _RECOVERY_EXIT


def _postrun_payload(
    *,
    status: str,
    reason: str,
    baseline: KisPaperDailyBroadPanel,
    candidate: KisPaperDailyBroadPanel,
    comparison: KisPaperDailyBroadPanelContinuityComparison,
    candidate_manifest_sha256: str,
    continuity_receipt_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_paper_daily_broad_panel_postrun",
        "status": status,
        "reason": reason,
        "baseline": _baseline_payload(baseline),
        "candidate": _candidate_payload(candidate, manifest_sha256=candidate_manifest_sha256),
        "continuity": {
            "status": comparison.status,
            "shared_target_count": comparison.shared_target_count,
            "shared_row_count": comparison.shared_row_count,
            "mismatched_target_count": comparison.mismatched_target_count,
            "mismatched_row_count": comparison.mismatched_row_count,
            "receipt_sha256": continuity_receipt_sha256,
        },
        "route_isolation": _route_isolation(),
        "artifact_policy": _artifact_policy(),
    }


def _baseline_payload(panel: KisPaperDailyBroadPanel) -> dict[str, object]:
    return {
        "dataset_hash": panel.dataset_hash,
        "index_generation": panel.index_generation,
        "target_count": len(panel.target_keys),
        "covered_target_count": panel.covered_target_count,
        "zero_coverage_target_count": panel.zero_coverage_target_count,
        "quarantined_target_count": panel.quarantined_target_count,
        "row_count": _row_count(panel),
    }


def _candidate_payload(
    panel: KisPaperDailyBroadPanel,
    *,
    manifest_sha256: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "dataset_hash": panel.dataset_hash,
        "index_generation": panel.index_generation,
        "target_count": len(panel.target_keys),
        "covered_target_count": panel.covered_target_count,
        "zero_coverage_target_count": panel.zero_coverage_target_count,
        "quarantined_target_count": panel.quarantined_target_count,
        "row_count": _row_count(panel),
    }
    if manifest_sha256 is not None:
        payload["manifest_sha256"] = manifest_sha256
    return payload


def _materialization_reason(error: Exception) -> str:
    if str(error) == "broad daily panel index changed during reattestation":
        return "index_changed_during_reattest"
    return "panel_materialization_unavailable"


def _continuity_reason(error: Exception) -> str:
    if str(error) == "broad daily panels do not share one registry contract":
        return "panel_registry_contract_changed"
    return "panel_continuity_unavailable"


def _route_isolation() -> dict[str, bool]:
    return {
        "network_accessed": False,
        "kis_accessed": False,
        "account_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "external_artifact_only": True,
        "raw_market_data_persisted": False,
        "raw_rows_persisted": False,
        "prices_persisted": False,
        "volumes_persisted": False,
        "credentials_accessed": False,
    }


def _write_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    payload: Mapping[str, object],
) -> str:
    root = _external_artifact_root(artifact_root, repository_root)
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    destination = root / f"postrun-{digest.removeprefix('sha256:')[:24]}.json"
    try:
        with destination.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as error:
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("broad daily postrun receipt is invalid") from error
    return digest


def _external_artifact_root(root: Path, repository_root: Path) -> Path:
    if root.is_symlink():
        raise ValueError("broad daily postrun artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve(strict=True)
    if resolved.is_relative_to(repository_root):
        raise ValueError("broad daily postrun artifacts must stay outside Git")
    return resolved


def _repository_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("broad daily postrun repository root is invalid")
    return root.resolve()


def _emit(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
