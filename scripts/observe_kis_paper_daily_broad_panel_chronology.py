"""Record a source-safe chronology distribution for one frozen broad D1 panel."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    KisPaperDailyBroadPanel,
    KisPaperDailyBroadPanelContinuityComparison,
    compare_kis_paper_daily_broad_panels,
    load_materialized_kis_paper_daily_broad_panel,
)

_RECOVERY_EXIT = 20
_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-broad-panel-chronology-v1"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Reattach one complete postrun and write an aggregate-only observation."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--postrun-receipt", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_BROAD_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=KIS_PAPER_DAILY_BROAD_PANEL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_ARTIFACT_ROOT)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args(argv)

    repository_root = _repository_root(args.repository_root)
    try:
        postrun = _read_postrun_receipt(args.postrun_receipt, repository_root)
        if (
            postrun.get("status") != "complete"
            or postrun.get("reason") != "stable_full_breadth_panel"
        ):
            _emit({"status": "not_recorded", "reason": "postrun_not_complete"})
            return _RECOVERY_EXIT
        baseline_manifest, candidate_manifest = _resolve_manifest_paths(
            postrun=postrun,
            panel_root=args.panel_root,
            baseline_manifest=args.baseline_manifest,
            candidate_manifest=args.candidate_manifest,
        )
        baseline = load_materialized_kis_paper_daily_broad_panel(
            baseline_manifest,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            repo_root=repository_root,
        )
        candidate = load_materialized_kis_paper_daily_broad_panel(
            candidate_manifest,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            repo_root=repository_root,
        )
        comparison = compare_kis_paper_daily_broad_panels(baseline, candidate)
        _validate_complete_postrun(
            postrun=postrun,
            baseline=baseline,
            candidate=candidate,
            comparison=comparison,
            candidate_manifest_path=candidate_manifest,
        )
    except (OSError, ValueError):
        _emit({"status": "not_recorded", "reason": "postrun_reattest_failed"})
        return _RECOVERY_EXIT

    payload = {
        "schema_version": 1,
        "kind": "kis_paper_daily_broad_panel_chronology_observation",
        "status": "recorded",
        "candidate": {
            "dataset_hash": candidate.dataset_hash,
            "index_generation": candidate.index_generation,
        },
        "postrun_receipt_sha256": _sha256(args.postrun_receipt.read_bytes()),
        "distribution": _chronology_distribution(candidate),
        "limitations": [
            "current_listing_only_not_point_in_time_universe",
            "per_target_distribution_not_common_history",
            "source_limited_targets_remain_visible",
            "perishable_by_candidate_generation",
            "not_research_eligibility_or_campaign_contract",
        ],
        "route_isolation": {
            "network_accessed": False,
            "kis_accessed": False,
            "account_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
        },
        "artifact_policy": {
            "external_artifact_only": True,
            "raw_market_data_persisted": False,
            "raw_rows_persisted": False,
            "prices_persisted": False,
            "volumes_persisted": False,
            "credentials_accessed": False,
        },
    }
    receipt_sha256 = _write_receipt(
        artifact_root=args.artifact_root,
        repository_root=repository_root,
        payload=payload,
    )
    _emit({**payload, "receipt_sha256": receipt_sha256})
    return 0


def _validate_complete_postrun(
    *,
    postrun: Mapping[str, object],
    baseline: KisPaperDailyBroadPanel,
    candidate: KisPaperDailyBroadPanel,
    comparison: KisPaperDailyBroadPanelContinuityComparison,
    candidate_manifest_path: Path,
) -> None:
    baseline_payload = _mapping(postrun, "baseline")
    candidate_payload = _mapping(postrun, "candidate")
    continuity_payload = _mapping(postrun, "continuity")
    if (
        postrun.get("kind") != "kis_paper_daily_broad_panel_postrun"
        or _text(baseline_payload, "dataset_hash") != baseline.dataset_hash
        or _integer(baseline_payload, "index_generation") != baseline.index_generation
        or _text(candidate_payload, "dataset_hash") != candidate.dataset_hash
        or _integer(candidate_payload, "index_generation") != candidate.index_generation
        or _integer(candidate_payload, "target_count") != len(candidate.target_keys)
        or _integer(candidate_payload, "covered_target_count") != candidate.covered_target_count
        or _integer(candidate_payload, "zero_coverage_target_count")
        != candidate.zero_coverage_target_count
        or _integer(candidate_payload, "quarantined_target_count")
        != candidate.quarantined_target_count
        or _text(candidate_payload, "manifest_sha256")
        != _sha256(candidate_manifest_path.read_bytes())
        or continuity_payload.get("status") != comparison.status
        or _integer(continuity_payload, "shared_target_count")
        != comparison.shared_target_count
        or _integer(continuity_payload, "shared_row_count") != comparison.shared_row_count
        or _integer(continuity_payload, "mismatched_target_count")
        != comparison.mismatched_target_count
        or _integer(continuity_payload, "mismatched_row_count")
        != comparison.mismatched_row_count
        or comparison.status != "equal"
        or candidate.covered_target_count != len(candidate.target_keys)
        or candidate.zero_coverage_target_count != 0
        or candidate.quarantined_target_count != 0
        or comparison.shared_target_count < baseline.covered_target_count
        or comparison.shared_row_count < _row_count(baseline)
    ):
        raise ValueError("broad daily chronology postrun is invalid")


def _resolve_manifest_paths(
    *,
    postrun: Mapping[str, object],
    panel_root: Path,
    baseline_manifest: Path | None,
    candidate_manifest: Path | None,
) -> tuple[Path, Path]:
    if (baseline_manifest is None) != (candidate_manifest is None):
        raise ValueError("broad daily chronology manifest arguments are incomplete")
    if baseline_manifest is not None and candidate_manifest is not None:
        return baseline_manifest, candidate_manifest
    return (
        _manifest_path_for_dataset_hash(
            _text(_mapping(postrun, "baseline"), "dataset_hash"),
            panel_root,
        ),
        _manifest_path_for_dataset_hash(
            _text(_mapping(postrun, "candidate"), "dataset_hash"),
            panel_root,
        ),
    )


def _manifest_path_for_dataset_hash(dataset_hash: str, panel_root: Path) -> Path:
    prefix = "sha256:"
    digest = dataset_hash.removeprefix(prefix)
    if (
        not dataset_hash.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("broad daily chronology dataset hash is invalid")
    return Path(panel_root) / f"panel={digest[:20]}" / "manifest.json"


def _chronology_distribution(panel: KisPaperDailyBroadPanel) -> dict[str, object]:
    bar_count_buckets: Counter[str] = Counter()
    calendar_span_buckets: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    for target in panel.targets_by_key.values():
        state_counts[target.state] += 1
        if target.bar_count == 0 or target.coverage_start is None or target.coverage_end is None:
            raise ValueError("broad daily chronology target coverage is invalid")
        bar_count_buckets[_bar_count_bucket(target.bar_count)] += 1
        coverage_start = date.fromisoformat(target.coverage_start)
        coverage_end = date.fromisoformat(target.coverage_end)
        span_days = (coverage_end - coverage_start).days
        if span_days < 0:
            raise ValueError("broad daily chronology target coverage is invalid")
        calendar_span_buckets[_calendar_span_bucket(span_days)] += 1
    return {
        "target_count": len(panel.target_keys),
        "state_counts": dict(sorted(state_counts.items())),
        "bar_count_buckets": {
            label: bar_count_buckets[label]
            for label in ("1_63", "64_126", "127_252", "253_504", "505_plus")
        },
        "calendar_span_day_buckets": {
            label: calendar_span_buckets[label]
            for label in ("0_365", "366_731", "732_1826", "1827_plus")
        },
    }


def _bar_count_bucket(value: int) -> str:
    if value <= 63:
        return "1_63"
    if value <= 126:
        return "64_126"
    if value <= 252:
        return "127_252"
    if value <= 504:
        return "253_504"
    return "505_plus"


def _calendar_span_bucket(value: int) -> str:
    if value <= 365:
        return "0_365"
    if value <= 731:
        return "366_731"
    if value <= 1826:
        return "732_1826"
    return "1827_plus"


def _row_count(panel: KisPaperDailyBroadPanel) -> int:
    return sum(target.bar_count for target in panel.targets_by_key.values())


def _read_postrun_receipt(path: Path, repository_root: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(repository_root):
        raise ValueError("broad daily chronology postrun receipt is invalid")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("broad daily chronology postrun receipt is invalid") from error
    if not isinstance(payload, dict):
        raise ValueError("broad daily chronology postrun receipt is invalid")
    return payload


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError("broad daily chronology postrun is invalid")
    return result


def _integer(value: Mapping[str, object], key: str) -> int:
    result = value.get(key)
    if type(result) is not int or result < 0:
        raise ValueError("broad daily chronology postrun is invalid")
    return result


def _text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError("broad daily chronology postrun is invalid")
    return result


def _write_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    payload: Mapping[str, object],
) -> str:
    root = _external_artifact_root(artifact_root, repository_root)
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    digest = _sha256(encoded)
    destination = root / f"chronology-{digest.removeprefix('sha256:')[:24]}.json"
    try:
        with destination.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as error:
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("broad daily chronology receipt is invalid") from error
    return digest


def _external_artifact_root(root: Path, repository_root: Path) -> Path:
    if root.is_symlink():
        raise ValueError("broad daily chronology artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve(strict=True)
    if resolved.is_relative_to(repository_root):
        raise ValueError("broad daily chronology artifacts must stay outside Git")
    return resolved


def _repository_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("broad daily chronology repository root is invalid")
    return root.resolve()


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _emit(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
