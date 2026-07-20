"""Pure, non-submitting paper-capital proposal from a sanitized runtime snapshot."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import require_utc
from thericher_v2.execution.paper_account_snapshot import (
    PaperAccountSnapshot,
    PaperAccountSnapshotRead,
    read_paper_account_snapshot,
)

DEFAULT_RUNTIME_SNAPSHOT_PATH = Path("runtime/state/paper_account_snapshot.json")

PaperCapitalProposalStatus = Literal["abstain", "awaiting_operator_approval"]
PaperCapitalProposalReason = Literal[
    "snapshot_unknown",
    "snapshot_unavailable",
    "snapshot_time_invalid",
    "snapshot_expired",
    "operator_ceiling_missing",
    "operator_ceiling_invalid",
    "currency_mismatch",
    "orderable_foreign_funds_unavailable",
    "reference_currency_mismatch",
    "reference_orderability_unavailable",
    "positions_present",
    "open_orders_present",
]


@dataclass(frozen=True)
class PaperCapitalPolicy:
    """An operator-supplied cap in the same native currency as the snapshot."""

    currency: str
    operator_ceiling: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "operator_ceiling", _positive_decimal(self.operator_ceiling))


@dataclass(frozen=True)
class PaperCapitalProposal:
    """Decision support only; it cannot approve or submit anything."""

    status: PaperCapitalProposalStatus
    reason_codes: tuple[PaperCapitalProposalReason, ...]
    currency: str | None
    candidate_ceiling: Decimal | None
    snapshot_observed_at: datetime | None
    valid_until: datetime | None
    basis: Literal["orderable_foreign_funds"] = "orderable_foreign_funds"
    reference_orderability_used: Literal[False] = False
    submission_capability: Literal[False] = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if self.currency is not None:
            object.__setattr__(self, "currency", _currency(self.currency))
        if self.candidate_ceiling is not None:
            object.__setattr__(self, "candidate_ceiling", _positive_decimal(self.candidate_ceiling))
        if self.snapshot_observed_at is not None:
            object.__setattr__(
                self,
                "snapshot_observed_at",
                require_utc(self.snapshot_observed_at, "snapshot_observed_at"),
            )
        if self.valid_until is not None:
            object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.status == "awaiting_operator_approval":
            if (
                self.reason_codes
                or self.currency is None
                or self.candidate_ceiling is None
                or self.snapshot_observed_at is None
                or self.valid_until is None
            ):
                raise ValueError("approval proposal is incomplete")
        elif self.status == "abstain":
            if not self.reason_codes or self.candidate_ceiling is not None:
                raise ValueError("abstention proposal is invalid")
        else:
            raise ValueError("proposal status is invalid")
        if self.reference_orderability_used is not False or self.submission_capability is not False:
            raise ValueError("proposal capabilities are invalid")

    @property
    def operator_approval_required(self) -> bool:
        return self.status == "awaiting_operator_approval"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "currency": self.currency,
            "candidate_ceiling": (
                None if self.candidate_ceiling is None else str(self.candidate_ceiling)
            ),
            "snapshot_observed_at": (
                None if self.snapshot_observed_at is None else self.snapshot_observed_at.isoformat()
            ),
            "valid_until": None if self.valid_until is None else self.valid_until.isoformat(),
            "basis": self.basis,
            "reference_orderability_used": False,
            "operator_approval_required": self.operator_approval_required,
            "submission_capability": False,
        }


def propose_paper_capital(
    snapshot_read: PaperAccountSnapshotRead,
    *,
    policy: PaperCapitalPolicy | None,
    now: datetime | None = None,
    policy_error: PaperCapitalProposalReason | None = None,
) -> PaperCapitalProposal:
    """Return a funds-basis candidate or fail closed without broker/network access."""

    current = require_utc(now or datetime.now(UTC), "now")
    if snapshot_read.status == "unknown":
        return _abstain("snapshot_unknown")
    if snapshot_read.status != "available" or snapshot_read.snapshot is None:
        return _abstain("snapshot_unavailable")

    snapshot = snapshot_read.snapshot
    context = _snapshot_context(snapshot)
    if current < snapshot.observed_at:
        return _abstain("snapshot_time_invalid", **context)
    if current >= snapshot.expires_at:
        return _abstain("snapshot_expired", **context)
    if policy_error is not None:
        return _abstain(policy_error, **context)
    if policy is None:
        return _abstain("operator_ceiling_missing", **context)
    if snapshot.positions:
        return _abstain("positions_present", **context)
    if snapshot.open_orders:
        return _abstain("open_orders_present", **context)

    funds = snapshot.orderable_foreign_funds
    reference = snapshot.reference_orderability
    if funds is None or funds.amount <= 0:
        return _abstain("orderable_foreign_funds_unavailable", **context)
    if reference is None or reference.orderable_funds <= 0:
        return _abstain("reference_orderability_unavailable", **context)
    if reference.currency != funds.currency:
        return _abstain("reference_currency_mismatch", **context)
    if policy.currency != funds.currency:
        return _abstain("currency_mismatch", **context)

    return PaperCapitalProposal(
        status="awaiting_operator_approval",
        reason_codes=(),
        currency=funds.currency,
        candidate_ceiling=min(funds.amount, policy.operator_ceiling),
        snapshot_observed_at=snapshot.observed_at,
        valid_until=snapshot.expires_at,
    )


def read_paper_capital_proposal(
    *,
    runtime_snapshot_path: Path,
    policy: PaperCapitalPolicy | None,
    now: datetime | None = None,
    policy_error: PaperCapitalProposalReason | None = None,
) -> PaperCapitalProposal:
    """Read only the generic runtime snapshot, then make a local proposal."""

    current = require_utc(now or datetime.now(UTC), "now")
    return propose_paper_capital(
        read_paper_account_snapshot(runtime_snapshot_path, now=current),
        policy=policy,
        now=current,
        policy_error=policy_error,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print a non-submitting paper-capital proposal")
    parser.add_argument("--runtime-snapshot", type=Path, default=DEFAULT_RUNTIME_SNAPSHOT_PATH)
    parser.add_argument("--currency")
    parser.add_argument("--operator-ceiling")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    policy, policy_error = _policy_from_arguments(
        currency=arguments.currency,
        operator_ceiling=arguments.operator_ceiling,
    )
    proposal = read_paper_capital_proposal(
        runtime_snapshot_path=arguments.runtime_snapshot,
        policy=policy,
        policy_error=policy_error,
    )
    print(json.dumps(proposal.to_dict(), sort_keys=True))
    return 0


def _snapshot_context(snapshot: PaperAccountSnapshot) -> dict[str, object]:
    funds = snapshot.orderable_foreign_funds
    return {
        "currency": None if funds is None else funds.currency,
        "snapshot_observed_at": snapshot.observed_at,
        "valid_until": snapshot.expires_at,
    }


def _abstain(
    reason: PaperCapitalProposalReason,
    *,
    currency: str | None = None,
    snapshot_observed_at: datetime | None = None,
    valid_until: datetime | None = None,
) -> PaperCapitalProposal:
    return PaperCapitalProposal(
        status="abstain",
        reason_codes=(reason,),
        currency=currency,
        candidate_ceiling=None,
        snapshot_observed_at=snapshot_observed_at,
        valid_until=valid_until,
    )


def _policy_from_arguments(
    *,
    currency: str | None,
    operator_ceiling: str | None,
) -> tuple[PaperCapitalPolicy | None, PaperCapitalProposalReason | None]:
    if currency is None and operator_ceiling is None:
        return None, None
    if not currency or operator_ceiling is None:
        return None, "operator_ceiling_missing"
    try:
        return (
            PaperCapitalPolicy(
                currency=currency,
                operator_ceiling=Decimal(operator_ceiling),
            ),
            None,
        )
    except (InvalidOperation, ValueError):
        return None, "operator_ceiling_invalid"


def _currency(value: str) -> str:
    result = value.strip().upper() if isinstance(value, str) else ""
    if len(result) != 3 or not result.isalpha():
        raise ValueError("currency is invalid")
    return result


def _positive_decimal(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("operator ceiling is invalid")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
