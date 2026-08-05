"""Deterministic mapping from a target-state proposal to a local order intent."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from thericher_v2.contracts import OrderIntent, TargetExposureProposal, decimal_value, require_utc


def target_proposal_to_order_intent(
    proposal: TargetExposureProposal,
    *,
    client_order_id: str,
    current_quantity: Decimal | str | int,
    maximum_quantity: Decimal | str | int,
    as_of: datetime | None = None,
) -> OrderIntent | None:
    """Map only an eligible long-only target delta; abstention never becomes an order."""

    if not client_order_id.strip():
        raise ValueError("client_order_id is required")
    current = decimal_value(current_quantity, "current_quantity")
    maximum = decimal_value(maximum_quantity, "maximum_quantity")
    if current < 0 or maximum <= 0:
        raise ValueError("current_quantity must be non-negative and maximum_quantity positive")
    created_at = proposal.decided_at if as_of is None else require_utc(as_of, "as_of")
    if (
        created_at < proposal.decided_at
        or created_at > proposal.valid_until
        or proposal.input_status != "ready"
    ):
        return None
    if proposal.action in {"abstain", "hold"}:
        return None

    desired = proposal.target_exposure * maximum
    if proposal.action == "enter":
        if desired <= current:
            return None
        side = "buy"
        quantity = desired - current
    elif proposal.action in {"reduce", "exit"}:
        if desired >= current:
            return None
        side = "sell"
        quantity = current - desired
    else:  # pragma: no cover - TargetExposureProposal constrains the action.
        raise ValueError("unsupported target action")
    return OrderIntent(
        client_order_id=client_order_id,
        symbol=proposal.symbol,
        market=proposal.market,
        side=side,
        quantity=quantity,
        limit_price=None,
        decision_id=proposal.proposal_id,
        created_at=created_at,
        valid_until=proposal.valid_until,
    )
