from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.execution.kis_paper_spy_position import (
    resolve_kis_paper_qqq_position_target,
    resolve_kis_paper_spy_position_target,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


def test_current_flat_account_allows_only_an_entry_buy() -> None:
    resolution = resolve_kis_paper_spy_position_target(
        _receipt(action="enter"),
        snapshot=_snapshot(),
        as_of=NOW,
    )

    assert resolution.action == "buy"
    assert resolution.reason_code == "target_buy_one_share"
    assert resolution.position_state == "flat"
    assert resolution.open_order_state == "clear"


def test_current_one_share_account_allows_only_an_exit_sell() -> None:
    resolution = resolve_kis_paper_spy_position_target(
        _receipt(action="exit"),
        snapshot=_snapshot(positions=(_position(),)),
        as_of=NOW,
    )

    assert resolution.action == "sell"
    assert resolution.reason_code == "target_sell_one_share"
    assert resolution.position_state == "one_share"


def test_stale_account_fact_never_creates_a_sell_or_pnl_claim() -> None:
    resolution = resolve_kis_paper_spy_position_target(
        _receipt(action="exit"),
        snapshot=_snapshot(positions=(_position(),), captured_at=NOW - timedelta(seconds=121)),
        as_of=NOW,
    )

    assert resolution.action == "none"
    assert resolution.reason_code == "account_snapshot_not_current"
    safe_payload = resolution.safe_payload()
    assert safe_payload["pnl_status"] == "not_observed"
    rendered = str(safe_payload)
    for forbidden in ("1000", "500.25", "ORD-123456789", "****5678-**"):
        assert forbidden not in rendered


def test_open_spy_order_and_out_of_scope_inventory_do_not_create_a_second_order() -> None:
    open_order_resolution = resolve_kis_paper_spy_position_target(
        _receipt(action="enter"),
        snapshot=_snapshot(open_orders=(_open_order(),)),
        as_of=NOW,
    )
    inventory_resolution = resolve_kis_paper_spy_position_target(
        _receipt(action="exit"),
        snapshot=_snapshot(positions=(_position(quantity=Decimal("2")),)),
        as_of=NOW,
    )

    assert (open_order_resolution.action, open_order_resolution.reason_code) == (
        "none",
        "open_order_conflict",
    )
    assert (inventory_resolution.action, inventory_resolution.reason_code) == (
        "none",
        "position_out_of_scope",
    )


def test_current_flat_qqq_account_allows_only_a_qqq_entry_buy() -> None:
    resolution = resolve_kis_paper_qqq_position_target(
        _receipt(action="enter", symbol="QQQ"),
        snapshot=_snapshot(),
        as_of=NOW,
    )

    assert resolution.instrument == "QQQ"
    assert resolution.action == "buy"
    assert resolution.safe_payload()["kind"] == "kis_paper_qqq_position_resolution"


def test_qqq_open_order_or_wrong_exchange_never_creates_a_second_order() -> None:
    open_order_resolution = resolve_kis_paper_qqq_position_target(
        _receipt(action="enter", symbol="QQQ"),
        snapshot=_snapshot(open_orders=(_open_order(symbol="QQQ", exchange="NASD"),)),
        as_of=NOW,
    )
    inventory_resolution = resolve_kis_paper_qqq_position_target(
        _receipt(action="exit", symbol="QQQ"),
        snapshot=_snapshot(positions=(_position(symbol="QQQ", exchange="NAS"),)),
        as_of=NOW,
    )

    assert (open_order_resolution.action, open_order_resolution.reason_code) == (
        "none",
        "open_order_conflict",
    )
    assert (inventory_resolution.action, inventory_resolution.reason_code) == (
        "none",
        "position_out_of_scope",
    )


def _receipt(*, action: str, symbol: str = "SPY") -> ResearchDecisionReceipt:
    return receipt_from_target_exposure_proposal(
        TargetExposureProposal(
            proposal_id=f"test-{symbol.lower()}-{action}",
            symbol=symbol,
            market="US",
            action=action,
            target_exposure=Decimal("0.05") if action == "enter" else Decimal("0"),
            confidence=Decimal("0.55"),
            feature_schema_id="test.spy.position",
            input_status="ready",
            decided_at=NOW - timedelta(minutes=1),
            valid_until=NOW + timedelta(minutes=1),
            feature_window_end=NOW - timedelta(minutes=1),
            reason=f"test_{action}",
        ),
        references=DecisionReceiptReferences(
            campaign_ref="ref:" + "a" * 64,
            model_ref="ref:" + "b" * 64,
            input_manifest_ref="sha256:" + "c" * 64,
            proposal_ref="ref:" + "d" * 64,
        ),
    )


def _snapshot(
    *,
    positions: tuple[KisPaperPosition, ...] = (),
    open_orders: tuple[KisPaperOpenOrder, ...] = (),
    captured_at: datetime = NOW,
) -> KisPaperReadOnlySnapshot:
    return KisPaperReadOnlySnapshot(
        identity=KisPaperAccountIdentity("****5678-**", captured_at),
        cash=KisPaperCashSnapshot("USD", Decimal("1000"), captured_at),
        orderable_funds=KisPaperOrderableFundsSnapshot(
            "USD",
            Decimal("1000"),
            "NASD",
            "SPY",
            Decimal("1"),
            captured_at,
        ),
        positions=positions,
        open_orders=KisPaperOpenOrdersSnapshot(open_orders, captured_at),
        captured_at=captured_at,
    )


def _position(
    *,
    quantity: Decimal = Decimal("1"),
    symbol: str = "SPY",
    exchange: str = "AMEX",
) -> KisPaperPosition:
    return KisPaperPosition(
        symbol=symbol,
        exchange=exchange,
        currency="USD",
        quantity=quantity,
        average_price=Decimal("500.25"),
        market_price=Decimal("500.50"),
        captured_at=NOW,
    )


def _open_order(*, symbol: str = "SPY", exchange: str = "AMEX") -> KisPaperOpenOrder:
    return KisPaperOpenOrder(
        order_reference="open-" + "a" * 16,
        symbol=symbol,
        exchange=exchange,
        currency="USD",
        side="buy",
        requested_quantity=Decimal("1"),
        filled_quantity=Decimal("0"),
        remaining_quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
        captured_at=NOW,
    )
