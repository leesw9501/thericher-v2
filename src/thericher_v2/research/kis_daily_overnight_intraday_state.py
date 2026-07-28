"""One deliberately bounded QQQ/SPY D1 state CPU smoke.

The external review rejected this as a performance candidate.  This module
therefore proves only a small offline path: causal actions, local-paper replay,
and source-safe external artifacts.  It cannot dispatch a full run, GPU work,
or any broker route.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    EmergencyState,
    ModelPrediction,
    Signal,
    Timeframe,
)
from thericher_v2.execution.local_paper import replay_local_paper_account
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
)

from .kis_daily_relative_regime_control import (
    DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT,
    KIS_DAILY_RELATIVE_REGIME_QUANTITY,
    KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
    KisDailyRelativeRegimeInput,
    load_current_kis_daily_relative_regime_input,
)
from .validation import InMemoryCampaignEventStore, ValidationConfig, run_local_paper_validation

KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID = "kis-daily-overnight-intraday-state-v1"
KIS_DAILY_OVERNIGHT_INTRADAY_STATE_RULE_ID = "qqq-spy-d1-up-count-state-20-v1"
KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS = ("QQQ", "SPY")
KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS = 20
KIS_DAILY_OVERNIGHT_INTRADAY_STATE_DECISION_STRIDE_SESSIONS = 2
KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SMOKE_SLOT_COUNT = 2
DEFAULT_KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ARTIFACT_ROOT = (
    DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT
)

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_ROLES = ("candidate", "always_long", "previous_bar_direction", "flat")
_RAW_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
)
_Role = Literal["candidate", "always_long", "previous_bar_direction", "flat"]


@dataclass(frozen=True, slots=True)
class KisDailyOvernightIntradayStateSmoke:
    """The only persisted identity for the CPU-only operational smoke."""

    precommit_path: Path
    summary_path: Path
    precommit_hash: str

    def __post_init__(self) -> None:
        if (
            not self.precommit_path.is_file()
            or not self.summary_path.is_file()
            or not _is_sha256(self.precommit_hash)
        ):
            raise ValueError("overnight/intraday smoke result is invalid")


class _ActionMapModel:
    """A fixed in-memory action map for the shared local-paper harness."""

    def __init__(
        self,
        *,
        model_id: str,
        symbol: str,
        actions: Mapping[datetime, str],
        reason: str,
    ) -> None:
        if (
            symbol not in KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS
            or not actions
            or any(action not in {"buy", "sell", "hold"} for action in actions.values())
        ):
            raise ValueError("overnight/intraday action map is invalid")
        self.model_id = model_id
        self.symbol = symbol
        self.actions = dict(actions)
        self.reason = reason
        self.lookback = 0

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if not bars:
            raise ValueError("overnight/intraday replay requires one completed bar")
        latest = bars[-1]
        action = self.actions.get(latest.end_ts)
        if (
            action is None
            or latest.symbol != self.symbol
            or latest.market != "US"
            or latest.timeframe is not Timeframe.D1
            or not latest.complete
        ):
            raise ValueError("overnight/intraday replay received an invalid decision bar")
        strength = Decimal("1") if action != "hold" else Decimal("0")
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=strength,
            reason=self.reason,
            timeframe=Timeframe.D1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=self.model_id,
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=strength,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={"rule_id": KIS_DAILY_OVERNIGHT_INTRADAY_STATE_RULE_ID},
        )


@dataclass(slots=True)
class _EmergencyStore:
    state: EmergencyState

    def read(self) -> EmergencyState:
        return self.state

    def write(self, state: EmergencyState) -> EmergencyState:
        self.state = state
        return state


def load_current_kis_daily_overnight_intraday_state_input(
    *,
    cache_root: Path | str,
    repository_root: Path | str | None = None,
) -> KisDailyRelativeRegimeInput:
    """Reattach the already hash-attested QQQ/SPY D1 source pair."""

    return load_current_kis_daily_relative_regime_input(
        cache_root=cache_root,
        repository_root=repository_root,
    )


def overnight_intraday_positive_count_should_enter(*, completed_bars: Sequence[Bar]) -> bool:
    """Compare non-telescoping positive directional counts over 20 observations."""

    bars = tuple(completed_bars)
    if len(bars) != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS + 1:
        raise ValueError("overnight/intraday state requires exactly 21 completed D1 bars")
    _validate_window(bars)
    intraday = sum(current.close > current.open for current in bars[1:])
    overnight = sum(
        current.open > prior.close for prior, current in zip(bars, bars[1:], strict=False)
    )
    return intraday > overnight


def run_kis_daily_overnight_intraday_state_cpu_smoke(
    source_input: KisDailyRelativeRegimeInput,
    *,
    artifact_root: Path | str = DEFAULT_KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ARTIFACT_ROOT,
    run_label: str,
    repository_root: Path | str | None = None,
) -> KisDailyOvernightIntradayStateSmoke:
    """Run exactly two validation slots and persist aggregate-only evidence."""

    _validate_run_label(run_label)
    repository = _repository_root(repository_root)
    validation_catalog = source_input.validation_catalog
    indices = _decision_indices(len(validation_catalog.common_sessions))
    selected = indices[:KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SMOKE_SLOT_COUNT]
    if len(selected) != KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SMOKE_SLOT_COUNT:
        raise ValueError("overnight/intraday smoke has insufficient slots")
    precommit = _precommit_payload(
        source_input=source_input,
        selected=selected,
        total_slots=len(indices),
    )
    precommit_hash = _sha256_json(precommit)
    output_dir = _artifact_root(artifact_root, repository) / "contracts" / "oi-state"
    output_dir = output_dir / precommit_hash.removeprefix("sha256:")[:16]
    output_dir = output_dir / f"{run_label}-{uuid.uuid4().hex[:8]}"
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_path = output_dir / "precommit.json"
    _write_json(precommit_path, {**precommit, "precommit_hash": precommit_hash})

    metrics = {
        symbol: {
            role: _replay(
                source_input=source_input,
                symbol=symbol,
                role=role,
                decision_indices=selected,
                precommit_hash=precommit_hash,
            )
            for role in _ROLES
        }
        for symbol in KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS
    }
    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID,
            "status": "complete",
            "mode": "cpu-smoke",
            "precommit_hash": precommit_hash,
            "outcome": "operational_smoke",
            "source": _source_payload(source_input),
            "validation": {
                "phase_local_eligible_slot_count": len(indices),
                "evaluated_slot_count": len(selected),
                "metrics_by_symbol": metrics,
                "performance_interpretation": "not_evaluated_cpu_smoke_only",
            },
            "review": {
                "claude_verdict": "unsupported",
                "resolution": "no_full_validation_gpu_or_paper_progression",
            },
            "scope": _scope_payload(),
            "artifact_policy": _artifact_policy(),
        },
    )
    return KisDailyOvernightIntradayStateSmoke(
        precommit_path=precommit_path,
        summary_path=summary_path,
        precommit_hash=precommit_hash,
    )


def _decision_indices(session_count: int) -> tuple[int, ...]:
    indices = tuple(
        range(
            KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS,
            session_count - 2,
            KIS_DAILY_OVERNIGHT_INTRADAY_STATE_DECISION_STRIDE_SESSIONS,
        )
    )
    if not indices or any(index + 2 >= session_count for index in indices):
        raise ValueError("overnight/intraday state decision slots are invalid")
    return indices


def _replay(
    *,
    source_input: KisDailyRelativeRegimeInput,
    symbol: str,
    role: _Role,
    decision_indices: tuple[int, ...],
    precommit_hash: str,
) -> dict[str, object]:
    bars = tuple(source_input.validation_catalog.bars_by_symbol[symbol].bars)
    actions: dict[datetime, str] = {}
    entries = 0
    for index in decision_indices:
        enter = role == "always_long" or (
            role == "candidate"
            and overnight_intraday_positive_count_should_enter(
                completed_bars=bars[
                    index - KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS : index + 1
                ]
            )
        ) or (
            role == "previous_bar_direction" and bars[index].close > bars[index - 1].close
        )
        actions[bars[index].end_ts] = "buy" if enter else "hold"
        actions[bars[index + 1].end_ts] = "sell" if enter else "hold"
        entries += int(enter)
    eligible_starts = frozenset(
        timestamp
        for index in decision_indices
        for timestamp in (bars[index].start_ts, bars[index + 1].start_ts)
    )
    if len(eligible_starts) != len(decision_indices) * 2:
        raise ValueError("overnight/intraday state decision cadence overlaps")
    events = InMemoryCampaignEventStore()
    emergency = _EmergencyStore(
        EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason=f"{KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID}-{symbol}-{role}",
            updated_at=bars[0].start_ts,
        )
    )
    with localcontext() as context:
        context.prec = KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        result = run_local_paper_validation(
            source_input.validation_catalog.bars_by_symbol[symbol],
            event_store=events,
            emergency_store=emergency,  # type: ignore[arg-type]
            model=_ActionMapModel(
                model_id=f"{KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID}-{symbol}-{role}",
                symbol=symbol,
                actions=actions,
                reason=KIS_DAILY_OVERNIGHT_INTRADAY_STATE_RULE_ID,
            ),
            config=ValidationConfig(
                run_id=f"{KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID}-{symbol}-{role}",
                starting_cash=KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
                quantity=KIS_DAILY_RELATIVE_REGIME_QUANTITY,
                fee_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
                slippage_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
            ),
            eligible_signal_starts=eligible_starts,
        )
    fills = tuple(event for event in events.iter_events() if event.event_type == "fill")
    replayed = replay_local_paper_account(
        events,
        starting_cash=KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
    )
    if (
        result.decisions_seen != len(decision_indices) * 2
        or len(result.trades) != entries * 2
        or len(fills) != len(result.trades)
        or any(event.payload.get("source") != "local_paper" for event in fills)
        or result.final_position != Decimal("0")
        or replayed.quantity(market="US", symbol=symbol) != Decimal("0")
        or replayed.cash != result.ending_cash
    ):
        raise RuntimeError("overnight/intraday local-paper replay invariants failed")
    metric = {
        "symbol": symbol,
        "role": role,
        "decision_slot_count": len(decision_indices),
        "entry_signal_count": entries,
        "trade_count": len(result.trades) // 2,
        "local_paper_fill_count": len(fills),
        "after_cost_pnl": str(result.after_cost_pnl),
        "gross_pnl": str(result.gross_pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "fill_source": "local_paper",
        "all_fills_local_paper": True,
        "replayable": True,
        "final_position": "0",
    }
    metric["replay_identity_hash"] = _sha256_json(
        {"precommit_hash": precommit_hash, **metric}
    )
    return metric


def _precommit_payload(
    *,
    source_input: KisDailyRelativeRegimeInput,
    selected: tuple[int, ...],
    total_slots: int,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ID,
        "status": "precommitted",
        "mode": "cpu-smoke",
        "source": _source_payload(source_input),
        "split": {
            "development_session_count": source_input.split.development_session_count,
            "purge_session_count": source_input.split.purge_session_count,
            "validation_session_count": source_input.split.validation_session_count,
            "phase_local_feature_window": True,
        },
        "rule": {
            "rule_id": KIS_DAILY_OVERNIGHT_INTRADAY_STATE_RULE_ID,
            "completed_d1_only": True,
            "feature_window_completed_d1_count": (
                KIS_DAILY_OVERNIGHT_INTRADAY_STATE_LOOKBACK_SESSIONS + 1
            ),
            "intraday_positive_definition": "close_i_strictly_gt_open_i",
            "overnight_positive_definition": "open_i_strictly_gt_prior_close",
            "entry_condition": "intraday_positive_count_strictly_gt_overnight_positive_count",
            "normalizer_fit_range": "none",
            "decision": "completed_session_t_close",
            "entry": "t_plus_1_open",
            "exit": "t_plus_2_open",
            "decision_stride_sessions": KIS_DAILY_OVERNIGHT_INTRADAY_STATE_DECISION_STRIDE_SESSIONS,
        },
        "validation": {
            "phase_local_eligible_slot_count": total_slots,
            "evaluated_slot_count": len(selected),
            "tuning_allowed": False,
        },
        "comparators": ["flat", "always_long", "previous_bar_direction"],
        "execution": {
            "fill_source": "local_paper",
            "quantity": str(KIS_DAILY_RELATIVE_REGIME_QUANTITY),
            "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
            "slippage_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL),
            "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
        },
        "review": {
            "claude_verdict": "unsupported",
            "resolution": "cpu_smoke_only_no_full_or_gpu_progression",
        },
        "scope": _scope_payload(),
        "artifact_policy": _artifact_policy(),
    }


def _source_payload(source_input: KisDailyRelativeRegimeInput) -> dict[str, object]:
    catalog = source_input.catalog
    return {
        "dataset_id": catalog.dataset_id,
        "dataset_hash": catalog.dataset_hash,
        "index_hash": catalog.index_hash,
        "symbols": list(KIS_DAILY_OVERNIGHT_INTRADAY_STATE_SYMBOLS),
        "completed_d1_session_count": len(catalog.common_sessions),
        "adjustment_mode": catalog.adjustment_mode,
        "limitations": list(catalog.raw_price_limitations),
        "source_mixing_allowed": False,
    }


def _scope_payload() -> dict[str, bool]:
    return {
        "cpu_smoke_only": True,
        "network_used": False,
        "credential_used": False,
        "broker_used": False,
        "paper_order_used": False,
        "gpu_used": False,
        "full_validation_eligible": False,
        "model_selection_eligible": False,
        "ensemble_eligible": False,
        "promotion_eligible": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "raw_market_data_persisted": False,
        "derived_feature_values_persisted": False,
        "labels_persisted": False,
        "event_logs_persisted": False,
        "model_weights_persisted": False,
        "local_paper_only": True,
        "network_used": False,
        "credentials_read": False,
        "broker_order_submitted": False,
        "gpu_used": False,
    }


def _validate_window(bars: tuple[Bar, ...]) -> None:
    if (
        len({bar.symbol for bar in bars}) != 1
        or any(
            bar.market != "US" or bar.timeframe is not Timeframe.D1 or not bar.complete
            for bar in bars
        )
        or any(
            later.start_ts <= earlier.start_ts
            for earlier, later in zip(bars, bars[1:], strict=False)
        )
    ):
        raise ValueError("overnight/intraday state requires aligned completed D1 bars")


def _artifact_root(artifact_root: Path | str, repository_root: Path) -> Path:
    candidate = Path(artifact_root)
    root = candidate.resolve()
    mounted = root == repository_root / "model_artifacts" and root.is_mount()
    if candidate.is_symlink() or (_contains(repository_root, root) and not mounted):
        raise ValueError("overnight/intraday artifacts must stay outside Git")
    return root


def _repository_root(repository_root: Path | str | None) -> Path:
    root = (Path.cwd() if repository_root is None else Path(repository_root)).resolve()
    if not root.is_dir():
        raise ValueError("repository root is invalid")
    return root


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    _reject_raw_fields(payload)
    with path.open("xb") as handle:
        handle.write(_json_bytes(payload))


def _reject_raw_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _RAW_FIELDS:
                raise ValueError("overnight/intraday artifact contains a raw market field")
            _reject_raw_fields(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            _reject_raw_fields(nested)


def _validate_run_label(run_label: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("run label must use 1-80 ASCII letters, digits, '.', '_' or '-'")


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _sha256_json(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(payload)).hexdigest()


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
