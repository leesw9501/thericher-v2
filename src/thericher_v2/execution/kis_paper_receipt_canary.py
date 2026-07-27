"""Receipt-aware KIS Paper canary preparation and deterministic recovery.

This owns the narrow SPY/AMS-to-AMEX and QQQ/NAS-to-NASD price mappings for
receipt-backed virtual orders. It neither evaluates a model nor accepts a
price supplied by research.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import require_utc
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt

from .emergency import DEFAULT_PAPER_EXECUTION_CONTROL_STATE
from .kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryOutcome,
    run_kis_paper_canary,
)
from .kis_paper_quote import (
    DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
    KIS_PAPER_QQQ_ASKING_PRICE_MAX_AGE,
    KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
    KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE,
    KIS_PAPER_US_QQQ_ORDER_EXCHANGE,
    KIS_PAPER_US_SPY_ASKING_PRICE_EXCHANGE,
    KIS_PAPER_US_SPY_ORDER_EXCHANGE,
    KisPaperQqqLimitInput,
    KisPaperSpyLimitInput,
    derive_kis_paper_nonmarket_limit,
)
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_readonly import KisHttpTransport
from .paper_decision_bridge import (
    KisPaperLimitProof,
    PaperDecisionBridgeResult,
    PaperDecisionExecutionBinding,
    prepare_kis_paper_decision,
)

_RECEIPT_DECISION_ID = re.compile(r"receipt-([0-9a-f]{64})")


def prepare_kis_paper_spy_receipt_decision(
    receipt: ResearchDecisionReceipt,
    *,
    limit_input: KisPaperSpyLimitInput,
    as_of: datetime,
    discount_bps: Decimal = DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
) -> PaperDecisionBridgeResult:
    """Bind an eligible receipt to the only approved transient SPY price path."""

    observed_at = require_utc(as_of, "as_of")
    limit_price = derive_kis_paper_nonmarket_limit(
        limit_input.as_quote(),
        discount_bps=discount_bps,
        tick_size=limit_input.tick_size,
    )
    proof = KisPaperLimitProof(
        receipt_id=receipt.decision_id,
        price_contract_ref=_price_contract_ref(
            limit_input=limit_input,
            limit_price=limit_price,
            discount_bps=discount_bps,
            side="buy" if receipt.decision_class == "enter" else "sell",
        ),
        symbol="SPY",
        exchange=KIS_PAPER_US_SPY_ORDER_EXCHANGE,
        limit_price=limit_price,
        observed_at=limit_input.quoted_at,
        valid_until=limit_input.quoted_at + KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
        final_limit_tick_valid=True,
    )
    return prepare_kis_paper_decision(
        receipt,
        binding=PaperDecisionExecutionBinding(
            proposal_ref=receipt.proposal_ref,
            symbol="SPY",
            exchange=KIS_PAPER_US_SPY_ORDER_EXCHANGE,
            quantity=Decimal("1"),
        ),
        limit_proof=proof,
        as_of=observed_at,
    )


def prepare_kis_paper_qqq_receipt_decision(
    receipt: ResearchDecisionReceipt,
    *,
    limit_input: KisPaperQqqLimitInput,
    as_of: datetime,
    discount_bps: Decimal = DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
) -> PaperDecisionBridgeResult:
    """Bind an eligible receipt to the only approved transient NAS/QQQ price path."""

    observed_at = require_utc(as_of, "as_of")
    limit_price = derive_kis_paper_nonmarket_limit(
        limit_input.as_quote(),
        discount_bps=discount_bps,
        tick_size=limit_input.tick_size,
    )
    proof = KisPaperLimitProof(
        receipt_id=receipt.decision_id,
        price_contract_ref=_qqq_price_contract_ref(
            limit_input=limit_input,
            limit_price=limit_price,
            discount_bps=discount_bps,
            side="buy" if receipt.decision_class == "enter" else "sell",
        ),
        symbol="QQQ",
        exchange=KIS_PAPER_US_QQQ_ORDER_EXCHANGE,
        limit_price=limit_price,
        observed_at=limit_input.quoted_at,
        valid_until=limit_input.quoted_at + KIS_PAPER_QQQ_ASKING_PRICE_MAX_AGE,
        final_limit_tick_valid=True,
    )
    return prepare_kis_paper_decision(
        receipt,
        binding=PaperDecisionExecutionBinding(
            proposal_ref=receipt.proposal_ref,
            symbol="QQQ",
            exchange=KIS_PAPER_US_QQQ_ORDER_EXCHANGE,
            quantity=Decimal("1"),
        ),
        limit_proof=proof,
        as_of=observed_at,
    )


def run_kis_paper_receipt_canary(
    prepared: PaperDecisionBridgeResult,
    *,
    environment: Mapping[str, str],
    state_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    submit_permitted: Callable[[datetime], bool] = is_us_equity_regular_session_window,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
) -> KisPaperCanaryOutcome:
    """Run at most one virtual-paper canary for a receipt-backed decision.

    The state path and KIS client-order identity derive only from the immutable
    receipt digest.  On later calls the canary reuses the persisted intent and
    price proof; it cannot replace it with a newly observed quote.
    """

    if (
        prepared.route != "kis_paper"
        or prepared.status != "ready"
        or prepared.kis_paper_decision is None
        or prepared.price_contract_ref is None
    ):
        raise ValueError("receipt canary requires a ready KIS paper bridge result")
    receipt_ref = prepared.receipt_ref
    decision = prepared.kis_paper_decision
    run_id = receipt_canary_run_id(receipt_ref)
    expected_decision_id = f"receipt-{receipt_ref.removeprefix('sha256:')}"
    if decision.decision_id != expected_decision_id:
        raise ValueError("receipt canary decision identity is invalid")
    return run_kis_paper_canary(
        decision=decision,
        run_id=run_id,
        environment=environment,
        state_path=state_root / f"{run_id}.json",
        runtime_projection_path=runtime_projection_path,
        paper_account_snapshot_path=paper_account_snapshot_path,
        emergency_state_path=emergency_state_path,
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=execute,
        cancel_after_submit=cancel_after_submit,
        transport=transport,
        client=client,
        now=now,
        clock=clock,
        submit_permitted=submit_permitted,
        execution_control_path=execution_control_path,
        price_contract_ref=prepared.price_contract_ref,
        reuse_existing_intent_if_same_decision=True,
    )


def receipt_canary_run_id(receipt_ref: str) -> str:
    """Return the stable private run identity for one full receipt digest."""

    expected = receipt_ref.removeprefix("sha256:")
    if not receipt_ref.startswith("sha256:") or len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise ValueError("receipt reference is invalid")
    return f"receipt-{expected}"


def _price_contract_ref(
    *,
    limit_input: KisPaperSpyLimitInput,
    limit_price: Decimal,
    discount_bps: Decimal,
    side: Literal["buy", "sell"],
) -> str:
    """Bind transient AMS quote facts to the final AMEX limit without exposing them."""

    return _fixed_price_contract_ref(
        kind="kis_paper_spy_ams_limit_contract_v1",
        symbol="SPY",
        quote_venue=KIS_PAPER_US_SPY_ASKING_PRICE_EXCHANGE,
        execution_venue=KIS_PAPER_US_SPY_ORDER_EXCHANGE,
        limit_input=limit_input,
        limit_price=limit_price,
        discount_bps=discount_bps,
        side=side,
    )


def _qqq_price_contract_ref(
    *,
    limit_input: KisPaperQqqLimitInput,
    limit_price: Decimal,
    discount_bps: Decimal,
    side: Literal["buy", "sell"],
) -> str:
    """Bind transient NAS quote facts to the final NASD limit without exposing them."""

    return _fixed_price_contract_ref(
        kind="kis_paper_qqq_nas_limit_contract_v1",
        symbol="QQQ",
        quote_venue=KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE,
        execution_venue=KIS_PAPER_US_QQQ_ORDER_EXCHANGE,
        limit_input=limit_input,
        limit_price=limit_price,
        discount_bps=discount_bps,
        side=side,
    )


def _fixed_price_contract_ref(
    *,
    kind: str,
    symbol: str,
    quote_venue: str,
    execution_venue: str,
    limit_input: KisPaperSpyLimitInput,
    limit_price: Decimal,
    discount_bps: Decimal,
    side: Literal["buy", "sell"],
) -> str:
    payload = {
        "kind": kind,
        "symbol": symbol,
        "quote_venue": quote_venue,
        "execution_venue": execution_venue,
        "side": side,
        "quoted_at": limit_input.quoted_at.isoformat(),
        "last": _decimal_marker(limit_input.last),
        "decimal_places": limit_input.decimal_places,
        "tick_size": _decimal_marker(limit_input.tick_size),
        "discount_bps": _decimal_marker(discount_bps),
        "final_limit": _decimal_marker(limit_price),
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _decimal_marker(value: Decimal) -> str:
    sign, digits, exponent = value.as_tuple()
    if not any(digits):
        return "0"
    last_significant = len(digits)
    while digits[last_significant - 1] == 0:
        last_significant -= 1
        exponent += 1
    prefix = "-" if sign else ""
    significand = "".join(str(digit) for digit in digits[:last_significant])
    return f"{prefix}{significand}e{exponent}"
