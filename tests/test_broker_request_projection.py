from __future__ import annotations

import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import OrderIntent, TargetExposureProposal
from thericher_v2.execution import (
    BROKER_DISABLED_SOURCE,
    BrokerCapabilities,
    create_kis_broker_adapter,
    order_intent_to_broker_order_request,
    target_proposal_to_order_intent,
)


def test_explicit_limit_intent_round_trips_every_broker_request_field() -> None:
    intent = _limit_intent(schema_version=17)

    request = order_intent_to_broker_order_request(intent)

    assert request.client_order_id == intent.client_order_id
    assert request.symbol == intent.symbol
    assert request.market == intent.market
    assert request.side == intent.side
    assert request.quantity == intent.quantity
    assert request.limit_price == intent.limit_price
    assert request.decision_id == intent.decision_id
    assert request.created_at == intent.created_at
    assert request.schema_version == intent.schema_version
    assert intent.limit_price == Decimal("188.45")


def test_target_position_market_intent_stays_non_projectable() -> None:
    decided_at = datetime(2026, 1, 2, 14, 31, tzinfo=UTC)
    proposal = TargetExposureProposal(
        proposal_id="target-proposal-1",
        symbol="aapl",
        market="us",
        action="enter",
        target_exposure=Decimal("0.5"),
        confidence=Decimal("0.75"),
        feature_schema_id="target-schema-1",
        input_status="ready",
        decided_at=decided_at,
        valid_until=decided_at + timedelta(minutes=5),
        feature_window_end=decided_at,
        reason="unit_test_target",
    )
    intent = target_proposal_to_order_intent(
        proposal,
        client_order_id="target-intent-1",
        current_quantity=Decimal("0"),
        maximum_quantity=Decimal("4"),
    )

    assert intent is not None
    assert intent.limit_price is None
    assert (
        target_proposal_to_order_intent(
            proposal,
            client_order_id="target-intent-before-decision",
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("4"),
            as_of=decided_at - timedelta(microseconds=1),
        )
        is None
    )
    assert (
        target_proposal_to_order_intent(
            proposal,
            client_order_id="target-intent-at-expiry",
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("4"),
            as_of=proposal.valid_until,
        )
        is None
    )
    with pytest.raises(ValueError, match="limit_price must be explicit"):
        order_intent_to_broker_order_request(intent)


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("client_order_id", "", "client_order_id"),
        ("decision_id", "", "decision_id"),
        ("quantity", Decimal("-1"), "quantity"),
        ("limit_price", Decimal("NaN"), "limit_price"),
        ("created_at", datetime(2026, 1, 2, 14, 31), "created_at"),
    ],
)
def test_projection_reuses_broker_request_validation_for_corrupted_intents(
    field_name: str,
    value: object,
    match: str,
) -> None:
    intent = _limit_intent()
    object.__setattr__(intent, field_name, value)

    with pytest.raises(ValueError, match=match):
        order_intent_to_broker_order_request(intent)


def test_projection_rejects_non_intent_input() -> None:
    with pytest.raises(TypeError, match="OrderIntent"):
        order_intent_to_broker_order_request(object())  # type: ignore[arg-type]


def test_projection_is_offline_and_leaves_kis_adapter_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("projection must not use credentials, files, or network")

    monkeypatch.setattr(os, "getenv", fail_io)
    monkeypatch.setattr(socket, "socket", fail_io)
    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)

    intent = _limit_intent()
    request = order_intent_to_broker_order_request(intent)
    adapter = create_kis_broker_adapter()
    unavailable = adapter.submit_order(intent)

    assert request.limit_price == intent.limit_price
    assert adapter.capabilities == BrokerCapabilities()
    assert unavailable.status == "unavailable"
    assert unavailable.source == BROKER_DISABLED_SOURCE


def _limit_intent(*, schema_version: int = 1) -> OrderIntent:
    return OrderIntent(
        client_order_id="limit-intent-1",
        symbol="aapl",
        market="us",
        side="buy",
        quantity=Decimal("2"),
        limit_price=Decimal("188.45"),
        decision_id="decision-1",
        created_at=datetime(2026, 1, 2, 14, 31, tzinfo=UTC),
        schema_version=schema_version,
    )
