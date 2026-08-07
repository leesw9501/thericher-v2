"""Aggregate-only PnL attribution for the frozen source-local EMA replay."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.data.local import CatalogedBars
from thericher_v2.execution import LOCAL_PAPER_SOURCE, replay_local_paper_realized_pnl
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory
from thericher_v2.research.kis_intraday_ema_replay import (
    KIS_INTRADAY_EMA_REPLAY_ID,
    KIS_INTRADAY_EMA_STARTING_CASH,
    EmaLocalPaperReplay,
    KisIntradayEmaReplayReceipt,
    load_kis_intraday_ema_replay_receipt,
    replay_kis_intraday_session_reset_ema_local_paper,
)

KIS_INTRADAY_EMA_PNL_ATTRIBUTION_ID = "source-local-ema-local-paper-pnl-attribution-v1"

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_RunStatus = Literal["complete", "input_unavailable"]
_InputUnavailableReason = Literal[
    "parent_source_binding_mismatch",
    "invalid_replay_input",
    "parent_replay_consistency_mismatch",
    "non_local_fill_detected",
    "terminal_flattening_mismatch",
    "fifo_accounting_mismatch",
]


@dataclass(frozen=True)
class EmaLocalPaperPnlAggregate:
    """Source-safe aggregate accounting facts; no price, fill, or order payloads."""

    closed_segment_count: int
    closed_quantity: Decimal
    gross_delta: Decimal
    fee_total: Decimal
    net_delta: Decimal
    open_quantity: Decimal
    local_paper_fill_count: int


@dataclass(frozen=True)
class EmaLocalPaperPnlAttributionRun:
    """Immutable result for one source-local EMA PnL attribution attempt."""

    run_label: str
    status: _RunStatus
    contract_hash: str
    parent_replay_contract_hash: str
    precommit_path: Path
    summary_path: Path
    session_count: int
    input_unavailable_reason: _InputUnavailableReason | None
    aggregate: EmaLocalPaperPnlAggregate


class _InputUnavailable(ValueError):
    def __init__(self, reason: _InputUnavailableReason) -> None:
        super().__init__(reason)
        self.reason = reason


def run_source_local_ema_local_paper_pnl_attribution(
    catalog: CatalogedBars,
    *,
    parent_receipt: KisIntradayEmaReplayReceipt,
    artifact_root: Path,
    run_label: str,
    repo_root: Path = _REPOSITORY_ROOT,
) -> EmaLocalPaperPnlAttributionRun:
    """Reattest and attribute one fixed EMA replay without external side effects."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("EMA PnL attribution requires CatalogedBars")
    if not isinstance(parent_receipt, KisIntradayEmaReplayReceipt):
        raise TypeError("EMA PnL attribution requires an EMA replay receipt")
    _validate_run_label(run_label)
    parent_receipt = _reattest_parent_receipt(parent_receipt, repo_root=Path(repo_root))
    run_directory = _new_run_directory(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        run_label=run_label,
    )
    contract = _contract_payload(parent_receipt=parent_receipt)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json_once(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "source_local_ema_local_paper_pnl_attribution_precommit",
            "status": "frozen_before_attribution",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )

    try:
        replay = replay_kis_intraday_session_reset_ema_local_paper(
            catalog,
            expected_contract_hash=parent_receipt.contract_hash,
        )
        if replay.mechanics != parent_receipt.mechanics:
            raise _InputUnavailable("parent_replay_consistency_mismatch")
        aggregate = _aggregate_local_paper_pnl(replay)
    except _InputUnavailable as error:
        status: _RunStatus = "input_unavailable"
        reason: _InputUnavailableReason | None = error.reason
        session_count = 0
        aggregate = _empty_aggregate()
        replay = None
    except ValueError as error:
        status = "input_unavailable"
        reason = _input_unavailable_reason(error)
        session_count = 0
        aggregate = _empty_aggregate()
        replay = None
    else:
        status = "complete"
        reason = None
        session_count = len(replay.session_replays)

    summary_path = run_directory / "summary.json"
    _write_json_once(
        summary_path,
        _summary_payload(
            parent_receipt=parent_receipt,
            run_label=run_label,
            status=status,
            contract_hash=contract_hash,
            session_count=session_count,
            input_unavailable_reason=reason,
            aggregate=aggregate,
            replay=replay,
            artifact_directory=run_directory,
        ),
    )
    return EmaLocalPaperPnlAttributionRun(
        run_label=run_label,
        status=status,
        contract_hash=contract_hash,
        parent_replay_contract_hash=parent_receipt.contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=session_count,
        input_unavailable_reason=reason,
        aggregate=aggregate,
    )


def _reattest_parent_receipt(
    parent_receipt: KisIntradayEmaReplayReceipt,
    *,
    repo_root: Path,
) -> KisIntradayEmaReplayReceipt:
    reattached = load_kis_intraday_ema_replay_receipt(
        precommit_path=parent_receipt.precommit_path,
        summary_path=parent_receipt.summary_path,
        repo_root=repo_root,
    )
    if reattached != parent_receipt:
        raise ValueError("EMA PnL attribution requires an externally reattested parent receipt")
    return reattached


def _aggregate_local_paper_pnl(replay: EmaLocalPaperReplay) -> EmaLocalPaperPnlAggregate:
    closed_segment_count = 0
    closed_quantity = Decimal("0")
    fee_total = Decimal("0")
    net_delta = Decimal("0")
    local_paper_fill_count = 0

    for session_replay in replay.session_replays:
        fill_events = tuple(
            event for event in session_replay.events if event.event_type == "fill"
        )
        if (
            len(session_replay.events) != session_replay.mechanics.replay_event_count
            or len(fill_events) != session_replay.mechanics.local_paper_fill_count
            or any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fill_events)
        ):
            raise _InputUnavailable("non_local_fill_detected")
        if (
            session_replay.terminal_account.positions != ()
            or not session_replay.mechanics.all_terminal_flat
        ):
            raise _InputUnavailable("terminal_flattening_mismatch")
        realized = replay_local_paper_realized_pnl(session_replay.events)
        if (
            realized.open_quantity != 0
            or realized.local_paper_fill_count != len(fill_events)
            or session_replay.terminal_account.cash - KIS_INTRADAY_EMA_STARTING_CASH
            != realized.realized_after_cost_pnl
        ):
            raise _InputUnavailable("fifo_accounting_mismatch")
        closed_segment_count += realized.closed_segment_count
        closed_quantity += realized.closed_quantity
        fee_total += sum(
            (Decimal(str(event.payload["fee"])) for event in fill_events),
            Decimal("0"),
        )
        net_delta += realized.realized_after_cost_pnl
        local_paper_fill_count += realized.local_paper_fill_count

    gross_delta = net_delta + fee_total
    aggregate = EmaLocalPaperPnlAggregate(
        closed_segment_count=closed_segment_count,
        closed_quantity=closed_quantity,
        gross_delta=gross_delta,
        fee_total=fee_total,
        net_delta=net_delta,
        open_quantity=Decimal("0"),
        local_paper_fill_count=local_paper_fill_count,
    )
    if aggregate.gross_delta - aggregate.fee_total != aggregate.net_delta:
        raise _InputUnavailable("fifo_accounting_mismatch")
    return aggregate


def _contract_payload(*, parent_receipt: KisIntradayEmaReplayReceipt) -> dict[str, object]:
    return {
        "schema_version": 1,
        "attribution_id": KIS_INTRADAY_EMA_PNL_ATTRIBUTION_ID,
        "parent_replay": {
            "replay_id": KIS_INTRADAY_EMA_REPLAY_ID,
            "contract_hash": parent_receipt.contract_hash,
            "replay_digest": parent_receipt.mechanics.replay_digest,
            "local_paper_fill_count": parent_receipt.mechanics.local_paper_fill_count,
            "all_fills_local_paper": parent_receipt.mechanics.all_fills_local_paper,
            "all_terminal_flat": parent_receipt.mechanics.all_terminal_flat,
        },
        "source": {
            "dataset_id": parent_receipt.source_dataset_id,
            "dataset_hash": parent_receipt.source_dataset_hash,
            "selected_session_dates_sha256": parent_receipt.selected_session_dates_sha256,
            "calendar_scope": parent_receipt.calendar_scope,
            "session_count": parent_receipt.session_count,
        },
        "frozen_semantics": {
            "rule": parent_receipt.contract["rule"],
            "execution": parent_receipt.contract["execution"],
        },
        "aggregate_metric_schema": [
            "closed_segment_count",
            "closed_quantity",
            "gross_delta",
            "fee_total",
            "net_delta",
            "open_quantity",
            "local_paper_fill_count",
        ],
        "strongest_kill_test": (
            "recomputed fixed local-paper replay must exactly match the parent mechanics "
            "digest and counts while every session remains terminal-flat"
        ),
        "limits": _limits_payload(),
    }


def _summary_payload(
    *,
    parent_receipt: KisIntradayEmaReplayReceipt,
    run_label: str,
    status: _RunStatus,
    contract_hash: str,
    session_count: int,
    input_unavailable_reason: _InputUnavailableReason | None,
    aggregate: EmaLocalPaperPnlAggregate,
    replay: EmaLocalPaperReplay | None,
    artifact_directory: Path,
) -> dict[str, object]:
    parent_match = replay is not None and replay.mechanics == parent_receipt.mechanics
    return {
        "schema_version": 1,
        "kind": "source_local_ema_local_paper_pnl_attribution_summary",
        "status": status,
        "mode": "offline_local_cache_local_paper_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source_replay_contract_hash": parent_receipt.contract_hash,
        "source": {
            "dataset_id": parent_receipt.source_dataset_id,
            "dataset_hash": parent_receipt.source_dataset_hash,
            "session_count": session_count,
        },
        "aggregate": _aggregate_payload(aggregate),
        "replay_consistency": {
            "parent_mechanics_match": parent_match,
            "all_fills_local_paper": parent_match and replay.mechanics.all_fills_local_paper,
            "all_terminal_flat": parent_match and replay.mechanics.all_terminal_flat,
            "fee_aware_identity": aggregate.gross_delta - aggregate.fee_total
            == aggregate.net_delta,
            "replay_digest": None if replay is None else replay.mechanics.replay_digest,
        },
        "input_unavailable_reason": input_unavailable_reason,
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status(status),
    }


def _aggregate_payload(aggregate: EmaLocalPaperPnlAggregate) -> dict[str, object]:
    return {
        "closed_segment_count": aggregate.closed_segment_count,
        "closed_quantity": str(aggregate.closed_quantity),
        "gross_delta": str(aggregate.gross_delta),
        "fee_total": str(aggregate.fee_total),
        "net_delta": str(aggregate.net_delta),
        "open_quantity": str(aggregate.open_quantity),
        "local_paper_fill_count": aggregate.local_paper_fill_count,
    }


def _empty_aggregate() -> EmaLocalPaperPnlAggregate:
    return EmaLocalPaperPnlAggregate(
        closed_segment_count=0,
        closed_quantity=Decimal("0"),
        gross_delta=Decimal("0"),
        fee_total=Decimal("0"),
        net_delta=Decimal("0"),
        open_quantity=Decimal("0"),
        local_paper_fill_count=0,
    )


def _limits_payload() -> dict[str, object]:
    return {
        "decision_time_availability": "not_observed",
        "source_local_retrospective_only": True,
        "model_selection_allowed": False,
        "post_outcome_tuning_allowed": False,
        "promotion_allowed": False,
        "paper_input_allowed": False,
        "gpu_eligible": False,
    }


def _artifact_policy(artifact_directory: Path) -> dict[str, object]:
    return {
        "root": str(artifact_directory.parents[2]),
        "repo_storage_allowed": False,
        "raw_market_data_written": False,
        "raw_price_values_retained": False,
        "raw_fill_events_retained": False,
        "credential_read": False,
        "network_called": False,
        "broker_called": False,
    }


def _claim_for_status(status: _RunStatus) -> str:
    if status == "complete":
        return (
            "cost-aware aggregate attribution for one fixed source-local local-paper replay only; "
            "it does not establish decision-time validity, general profitability, model selection, "
            "ensemble value, Paper eligibility, or broker behavior"
        )
    if status == "input_unavailable":
        return (
            "the fixed source-local replay could not be reattached or reproduced; "
            "this record makes "
            "no PnL, profitability, model, Paper, or broker claim"
        )
    raise ValueError(f"unsupported EMA PnL attribution status: {status}")


def _input_unavailable_reason(error: ValueError) -> _InputUnavailableReason:
    message = str(error)
    if "contract does not match its parent receipt" in message:
        return "parent_source_binding_mismatch"
    if "twenty complete regular KIS M1 sessions" in message:
        return "parent_source_binding_mismatch"
    return "invalid_replay_input"


def _new_run_directory(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    parent = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        KIS_INTRADAY_EMA_PNL_ATTRIBUTION_ID,
    )
    if (parent / run_label).exists():
        raise FileExistsError(f"EMA PnL attribution artifact already exists: {parent / run_label}")
    return ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        KIS_INTRADAY_EMA_PNL_ATTRIBUTION_ID,
        run_label,
    )


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")


def _write_json_once(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"EMA PnL attribution artifact already exists: {path}")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()
