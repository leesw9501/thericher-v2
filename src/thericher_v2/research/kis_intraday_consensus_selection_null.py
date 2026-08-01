"""Equal-count session-subset null diagnostic for the frozen QQQ consensus replay."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Literal

from thericher_v2.data import CatalogedBars

from .kis_intraday_campaign import (
    KIS_INTRADAY_SESSION_COUNT,
    build_kis_intraday_cpu_campaign_plan,
)
from .kis_intraday_consensus_replay import (
    KIS_INTRADAY_CONSENSUS_FEE_BPS,
    KIS_INTRADAY_CONSENSUS_QUANTITY,
    KIS_INTRADAY_CONSENSUS_REPLAY_ID,
    KIS_INTRADAY_CONSENSUS_SLIPPAGE_BPS,
    KIS_INTRADAY_CONSENSUS_STARTING_CASH,
    KisIntradayConsensusSessionReplay,
    consensus_session_replay_digest,
    replay_frozen_consensus_plan,
)

KIS_INTRADAY_CONSENSUS_SELECTION_NULL_ID = "kis-intraday-consensus-selection-null-v1"
KIS_INTRADAY_CONSENSUS_SELECTION_MINIMUM_ROUND_TRIPS = 30
KIS_INTRADAY_CONSENSUS_SELECTION_MAX_EXACT_COMBINATIONS = 100_000
KIS_INTRADAY_CONSENSUS_SELECTION_PERMUTATIONS = 4_096

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


@dataclass(frozen=True)
class KisIntradayConsensusSelectionNullRun:
    """Aggregate-only result for one immutable selection-null attempt."""

    run_label: str
    status: Literal["complete"]
    classification: Literal["selection_unqualified", "descriptive_null_only"]
    precommit_path: Path
    summary_path: Path
    selected_session_count: int
    null_subset_count: int
    null_method: Literal["exact_combinations", "deterministic_subset_samples"]
    one_sided_p_value: Decimal


@dataclass(frozen=True)
class _BaselineBinding:
    summary_path: Path
    precommit_path: Path
    summary_sha256: str
    precommit_sha256: str
    run_label: str
    dataset_id: str
    dataset_hash: str
    session_count: int
    selected_session_count: int
    consensus_after_cost_pnl: Decimal
    always_long_after_cost_pnl: Decimal
    replay_digest: str


@dataclass(frozen=True)
class _NullDistribution:
    method: Literal["exact_combinations", "deterministic_subset_samples"]
    values: tuple[Decimal, ...]


def run_kis_intraday_consensus_selection_null(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    baseline_summary_path: Path,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
) -> KisIntradayConsensusSelectionNullRun:
    """Measure the frozen selection mask against equal-count local-paper subsets.

    The diagnostic replays the immutable baseline only to attest its complete
    safe replay digest. It never creates a broker request, reads credentials,
    accesses the network, writes raw fills, or changes the baseline contract.
    """

    _validate_run_label(run_label)
    dates = tuple(session_dates)
    if len(dates) != KIS_INTRADAY_SESSION_COUNT:
        raise ValueError("selection null requires the fixed twenty-session consensus scope")
    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=dates,
        campaign_id=KIS_INTRADAY_CONSENSUS_REPLAY_ID,
    )
    root = Path(artifact_root).resolve()
    resolved_repo = Path(repo_root or Path.cwd()).resolve()
    _reject_repo_path(root, resolved_repo, "artifact root")
    binding = _load_baseline_binding(
        baseline_summary_path=Path(baseline_summary_path),
        repo_root=resolved_repo,
        dataset_id=plan.cataloged_bars.dataset_id,
        dataset_hash=plan.cataloged_bars.dataset_hash,
        session_dates=dates,
    )
    output_dir = root / "research" / KIS_INTRADAY_CONSENSUS_SELECTION_NULL_ID / run_label
    if output_dir.exists():
        raise FileExistsError(f"selection-null artifact already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_path = output_dir / "precommit.json"
    _write_json(
        precommit_path,
        _precommit_payload(
            binding=binding,
            dates=dates,
            artifact_root=root,
            run_label=run_label,
        ),
    )

    outcomes = replay_frozen_consensus_plan(plan)
    actual_replay_digest = consensus_session_replay_digest(outcomes)
    if actual_replay_digest != binding.replay_digest:
        raise RuntimeError("selection null must reproduce the immutable baseline replay digest")
    selected = tuple(outcome for outcome in outcomes if outcome.consensus.fill_count == 2)
    if len(selected) != binding.selected_session_count:
        raise RuntimeError("selection null reproduced a different baseline entry count")
    if any(
        not outcome.consensus.all_fills_local_paper
        or not outcome.always_long.all_fills_local_paper
        or not outcome.consensus.terminal_flat
        or not outcome.always_long.terminal_flat
        for outcome in outcomes
    ):
        raise RuntimeError("selection null requires replayable local-paper terminal-flat outcomes")

    selected_after_cost_pnl = sum(
        (outcome.always_long.after_cost_pnl for outcome in selected),
        Decimal("0"),
    )
    consensus_after_cost_pnl = sum(
        (outcome.consensus.after_cost_pnl for outcome in outcomes),
        Decimal("0"),
    )
    always_long_after_cost_pnl = sum(
        (outcome.always_long.after_cost_pnl for outcome in outcomes),
        Decimal("0"),
    )
    if (
        selected_after_cost_pnl != consensus_after_cost_pnl
        or consensus_after_cost_pnl != binding.consensus_after_cost_pnl
        or always_long_after_cost_pnl != binding.always_long_after_cost_pnl
    ):
        raise RuntimeError("selection null must preserve the fixed baseline aggregate outcomes")

    distribution = _equal_count_null_distribution(
        tuple(outcome.always_long.after_cost_pnl for outcome in outcomes),
        selected_session_count=len(selected),
        seed_material=f"{binding.summary_sha256}:{actual_replay_digest}",
    )
    one_sided_p_value = _one_sided_p_value(distribution.values, selected_after_cost_pnl)
    classification: Literal["selection_unqualified", "descriptive_null_only"]
    if len(selected) < KIS_INTRADAY_CONSENSUS_SELECTION_MINIMUM_ROUND_TRIPS:
        classification = "selection_unqualified"
    else:
        classification = "descriptive_null_only"
    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            binding=binding,
            artifact_root=root,
            run_label=run_label,
            actual_replay_digest=actual_replay_digest,
            selected=selected,
            selected_after_cost_pnl=selected_after_cost_pnl,
            distribution=distribution,
            one_sided_p_value=one_sided_p_value,
            classification=classification,
        ),
    )
    return KisIntradayConsensusSelectionNullRun(
        run_label=run_label,
        status="complete",
        classification=classification,
        precommit_path=precommit_path,
        summary_path=summary_path,
        selected_session_count=len(selected),
        null_subset_count=len(distribution.values),
        null_method=distribution.method,
        one_sided_p_value=one_sided_p_value,
    )


def _load_baseline_binding(
    *,
    baseline_summary_path: Path,
    repo_root: Path,
    dataset_id: str,
    dataset_hash: str,
    session_dates: tuple[date, ...],
) -> _BaselineBinding:
    summary_path = baseline_summary_path.resolve()
    _reject_repo_path(summary_path, repo_root, "baseline summary")
    precommit_path = summary_path.parent / "precommit.json"
    summary = _read_mapping(summary_path, "baseline summary")
    precommit = _read_mapping(precommit_path, "baseline precommit")
    if summary.get("kind") != "kis_intraday_consensus_replay_summary":
        raise ValueError("baseline summary kind is invalid")
    if precommit.get("kind") != "kis_intraday_consensus_replay_precommit":
        raise ValueError("baseline precommit kind is invalid")
    source = _mapping_value(summary, "source", "baseline summary")
    precommit_source = _mapping_value(precommit, "source", "baseline precommit")
    if (
        source.get("dataset_id") != dataset_id
        or source.get("dataset_hash") != dataset_hash
        or source.get("session_count") != KIS_INTRADAY_SESSION_COUNT
        or precommit_source.get("dataset_id") != dataset_id
        or precommit_source.get("dataset_hash") != dataset_hash
        or precommit_source.get("session_count") != KIS_INTRADAY_SESSION_COUNT
        or precommit_source.get("session_dates") != [item.isoformat() for item in session_dates]
    ):
        raise ValueError("baseline source does not match the frozen selection-null scope")
    consensus = _mapping_value(summary, "consensus", "baseline summary")
    comparator_root = _mapping_value(summary, "comparators", "baseline summary")
    always_long = _mapping_value(
        comparator_root,
        "always_long_time_matched",
        "baseline summary comparators",
    )
    replay_proof = _mapping_value(summary, "replay_proof", "baseline summary")
    selected_count = _integer_value(consensus.get("round_trip_count"), "baseline entry count")
    if selected_count < 0 or selected_count > KIS_INTRADAY_SESSION_COUNT:
        raise ValueError("baseline entry count is invalid")
    if replay_proof.get("local_paper_source") != "local_paper":
        raise ValueError("baseline replay source is invalid")
    contract = _mapping_value(precommit, "contract", "baseline precommit")
    if (
        contract.get("quantity") != str(KIS_INTRADAY_CONSENSUS_QUANTITY)
        or contract.get("starting_cash") != str(KIS_INTRADAY_CONSENSUS_STARTING_CASH)
        or contract.get("fee_bps") != str(KIS_INTRADAY_CONSENSUS_FEE_BPS)
        or contract.get("slippage_bps") != str(KIS_INTRADAY_CONSENSUS_SLIPPAGE_BPS)
        or contract.get("post_outcome_tuning_allowed") is not False
    ):
        raise ValueError("baseline local-paper contract is invalid")
    return _BaselineBinding(
        summary_path=summary_path,
        precommit_path=precommit_path,
        summary_sha256=_file_sha256(summary_path),
        precommit_sha256=_file_sha256(precommit_path),
        run_label=_string_value(summary.get("run_label"), "baseline run_label"),
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        session_count=KIS_INTRADAY_SESSION_COUNT,
        selected_session_count=selected_count,
        consensus_after_cost_pnl=_decimal_value(
            consensus.get("after_cost_pnl"),
            "baseline consensus after_cost_pnl",
        ),
        always_long_after_cost_pnl=_decimal_value(
            always_long.get("after_cost_pnl"),
            "baseline always-long after_cost_pnl",
        ),
        replay_digest=_string_value(
            replay_proof.get("event_replay_digest"),
            "baseline replay digest",
        ),
    )


def _equal_count_null_distribution(
    values: tuple[Decimal, ...],
    *,
    selected_session_count: int,
    seed_material: str,
) -> _NullDistribution:
    if not values:
        raise ValueError("selection null requires at least one session outcome")
    if not 0 <= selected_session_count <= len(values):
        raise ValueError("selection null selected session count is invalid")
    combination_count = math.comb(len(values), selected_session_count)
    if combination_count <= KIS_INTRADAY_CONSENSUS_SELECTION_MAX_EXACT_COMBINATIONS:
        return _NullDistribution(
            method="exact_combinations",
            values=tuple(
                sum((values[index] for index in subset), Decimal("0"))
                for subset in combinations(range(len(values)), selected_session_count)
            ),
        )
    seed = int(hashlib.sha256(seed_material.encode()).hexdigest()[:16], 16)
    generator = random.Random(seed)
    samples: set[tuple[int, ...]] = set()
    while len(samples) < KIS_INTRADAY_CONSENSUS_SELECTION_PERMUTATIONS:
        samples.add(tuple(sorted(generator.sample(range(len(values)), selected_session_count))))
    return _NullDistribution(
        method="deterministic_subset_samples",
        values=tuple(
            sum((values[index] for index in subset), Decimal("0")) for subset in sorted(samples)
        ),
    )


def _one_sided_p_value(values: Sequence[Decimal], observed: Decimal) -> Decimal:
    if not values:
        raise ValueError("selection null distribution is empty")
    return Decimal(sum(value >= observed for value in values)) / Decimal(len(values))


def _precommit_payload(
    *,
    binding: _BaselineBinding,
    dates: tuple[date, ...],
    artifact_root: Path,
    run_label: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_intraday_consensus_selection_null_precommit",
        "status": "frozen_before_diagnostic",
        "run_label": run_label,
        "baseline": {
            "replay_id": KIS_INTRADAY_CONSENSUS_REPLAY_ID,
            "run_label": binding.run_label,
            "summary_sha256": binding.summary_sha256,
            "precommit_sha256": binding.precommit_sha256,
            "replay_digest": binding.replay_digest,
        },
        "source": {
            "dataset_id": binding.dataset_id,
            "dataset_hash": binding.dataset_hash,
            "session_dates": [item.isoformat() for item in dates],
            "session_count": len(dates),
        },
        "null_contract": {
            "selected_session_count": binding.selected_session_count,
            "comparison": "time_matched_always_long_equal_count_subsets",
            "exact_combination_limit": KIS_INTRADAY_CONSENSUS_SELECTION_MAX_EXACT_COMBINATIONS,
            "deterministic_subset_sample_count": KIS_INTRADAY_CONSENSUS_SELECTION_PERMUTATIONS,
            "minimum_round_trips_for_any_follow_up": (
                KIS_INTRADAY_CONSENSUS_SELECTION_MINIMUM_ROUND_TRIPS
            ),
            "post_outcome_tuning_allowed": False,
        },
        "artifact_policy": _artifact_policy(artifact_root),
    }


def _summary_payload(
    *,
    binding: _BaselineBinding,
    artifact_root: Path,
    run_label: str,
    actual_replay_digest: str,
    selected: tuple[KisIntradayConsensusSessionReplay, ...],
    selected_after_cost_pnl: Decimal,
    distribution: _NullDistribution,
    one_sided_p_value: Decimal,
    classification: Literal["selection_unqualified", "descriptive_null_only"],
) -> dict[str, object]:
    ordered_values = tuple(sorted(distribution.values))
    null_mean = sum(ordered_values, Decimal("0")) / Decimal(len(ordered_values))
    return {
        "schema_version": 1,
        "kind": "kis_intraday_consensus_selection_null_summary",
        "status": "complete",
        "classification": classification,
        "mode": "offline_local_cache_local_paper_selection_null",
        "run_label": run_label,
        "baseline": {
            "run_label": binding.run_label,
            "summary_sha256": binding.summary_sha256,
            "precommit_sha256": binding.precommit_sha256,
            "baseline_replay_digest": binding.replay_digest,
            "reproduced_replay_digest": actual_replay_digest,
            "replay_digest_match": True,
        },
        "source": {
            "dataset_id": binding.dataset_id,
            "dataset_hash": binding.dataset_hash,
            "session_count": binding.session_count,
        },
        "selection": {
            "selected_session_count": len(selected),
            "selection_mask_digest": _selection_mask_digest(selected),
            "selected_after_cost_pnl": str(selected_after_cost_pnl),
            "minimum_round_trips_for_any_follow_up": (
                KIS_INTRADAY_CONSENSUS_SELECTION_MINIMUM_ROUND_TRIPS
            ),
        },
        "equal_count_null": {
            "method": distribution.method,
            "subset_count": len(ordered_values),
            "mean_after_cost_pnl": str(null_mean),
            "p95_after_cost_pnl": str(_p95(ordered_values)),
            "maximum_after_cost_pnl": str(ordered_values[-1]),
            "one_sided_p_value": str(one_sided_p_value),
        },
        "replay_proof": {
            "local_paper_source": "local_paper",
            "all_fills_local_paper": True,
            "all_terminal_flat": True,
            "raw_fill_events_retained": False,
        },
        "artifact_policy": _artifact_policy(artifact_root),
        "claim": (
            "selection-null diagnostic only; it does not select or tune a model, "
            "establish profitability, create an ensemble, allocate GPU, open a sealed "
            "evaluation, or change KIS Paper behavior"
        ),
    }


def _selection_mask_digest(selected: Sequence[KisIntradayConsensusSessionReplay]) -> str:
    payload = [outcome.consensus.replay_digest for outcome in selected]
    return "sha256:" + _sha256_json(payload)


def _p95(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("selection null distribution is empty")
    index = math.ceil(Decimal("0.95") * Decimal(len(values))) - 1
    return values[index]


def _artifact_policy(artifact_root: Path) -> dict[str, object]:
    return {
        "root": str(artifact_root),
        "repo_storage_allowed": False,
        "raw_market_data_written": False,
        "raw_fill_events_retained": False,
        "checkpoint_written": False,
        "credential_read": False,
        "network_called": False,
        "broker_called": False,
        "gpu_used": False,
    }


def _read_mapping(path: Path, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_value(value: Mapping[str, object], key: str, label: str) -> Mapping[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"{label} {key} is invalid")
    return nested


def _string_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    return value


def _integer_value(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} is invalid")
    return value


def _decimal_value(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    try:
        result = Decimal(value)
    except Exception as exc:  # pragma: no cover - Decimal's exception type is opaque.
        raise ValueError(f"{label} is invalid") from exc
    if not result.is_finite():
        raise ValueError(f"{label} is invalid")
    return result


def _file_sha256(path: Path) -> str:
    try:
        contents = path.read_bytes()
    except OSError as exc:
        raise ValueError("baseline evidence is unavailable") from exc
    return "sha256:" + hashlib.sha256(contents).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _reject_repo_path(path: Path, repo_root: Path, label: str) -> None:
    if path == repo_root or path.is_relative_to(repo_root):
        raise ValueError(f"{label} must stay outside the Git workspace")


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")
