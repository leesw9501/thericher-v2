from __future__ import annotations

import ast
import importlib
import os
import socket
import sys
import urllib.request
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.research.kis_paper_canary_intent import KisPaperCanaryBuyDecision

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


def test_canary_buy_decision_is_explicit_broker_neutral_evidence() -> None:
    decision = _decision()

    assert decision.market == "US"
    assert decision.side == "buy"
    assert decision.symbol == "QQQ"
    assert decision.exchange == "NASD"
    assert decision.quantity == Decimal("1")
    assert decision.limit_price == Decimal("500.25")
    assert decision.decision_as_of is NOW
    assert decision.valid_until == NOW + timedelta(minutes=2)
    assert decision.schema_id == "kis-paper-canary-buy-decision-v1"

    field_names = {field.name for field in fields(decision)}
    assert field_names == {
        "decision_id",
        "symbol",
        "exchange",
        "quantity",
        "limit_price",
        "decision_as_of",
        "valid_until",
        "schema_id",
        "market",
        "side",
        "schema_version",
    }
    assert not {"tr_id", "authorization", "token", "account_no", "broker_order_id"}.intersection(
        field_names
    )


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"decision_id": ""}, "decision_id"),
        ({"symbol": "qqq"}, "uppercase US ticker"),
        ({"symbol": "QQQ "}, "uppercase US ticker"),
        ({"symbol": "QQQ/US"}, "uppercase US ticker"),
        ({"exchange": "nasd"}, "uppercase supported US exchange"),
        ({"exchange": "NAS"}, "uppercase supported US exchange"),
        ({"quantity": Decimal("0")}, "quantity"),
        ({"quantity": Decimal("1.5")}, "whole shares"),
        ({"limit_price": Decimal("0")}, "limit_price"),
        ({"limit_price": Decimal("NaN")}, "limit_price"),
        ({"market": "KR"}, "market must be US"),
        ({"side": "sell"}, "side must be buy"),
        ({"decision_as_of": datetime(2026, 7, 22, 14, 30)}, "decision_as_of"),
        ({"valid_until": NOW}, "valid_until must follow"),
    ],
)
def test_canary_buy_decision_rejects_out_of_scope_or_invalid_values(
    overrides: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        _decision(**overrides)


def test_canary_buy_decision_keeps_distinct_explicit_us_exchanges() -> None:
    assert _decision(exchange="NYSE").exchange == "NYSE"
    assert _decision(exchange="AMEX").exchange == "AMEX"


def test_canary_buy_decision_is_offline_and_does_not_access_environment_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("canary decision must not access credentials, files, or network")

    monkeypatch.setattr(os, "getenv", fail_io)
    monkeypatch.setattr(socket, "socket", fail_io)
    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)

    module_name = "thericher_v2.research.kis_paper_canary_intent"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    decision = module.KisPaperCanaryBuyDecision(
        decision_id="canary-1",
        symbol="QQQ",
        exchange="NASD",
        quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
        decision_as_of=NOW,
        valid_until=NOW + timedelta(minutes=2),
    )

    assert decision.side == "buy"


def test_module_does_not_import_broker_or_model_runtime_dependencies() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "thericher_v2"
        / "research"
        / "kis_paper_canary_intent.py"
    )
    source = source_path.read_text(encoding="utf-8")
    imported_modules = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not any(
        name.startswith(("os", "socket", "urllib", "requests", "torch", "tensorflow"))
        for name in imported_modules
    )
    assert not any(name.startswith("thericher_v2.execution") for name in imported_modules)
    assert "OrderIntent" not in source
    assert "BrokerOrderRequest" not in source
    assert "TR_ID" not in source


def test_immutable_contract_cannot_be_replaced_with_invalid_value() -> None:
    decision = _decision()
    with pytest.raises(ValueError, match="whole shares"):
        replace(decision, quantity=Decimal("2.5"))


def _decision(**overrides: object) -> KisPaperCanaryBuyDecision:
    values: dict[str, object] = {
        "decision_id": "canary-qqq-20260722T143000Z",
        "symbol": "QQQ",
        "exchange": "NASD",
        "quantity": Decimal("1"),
        "limit_price": Decimal("500.25"),
        "decision_as_of": NOW,
        "valid_until": NOW + timedelta(minutes=2),
    }
    values.update(overrides)
    return KisPaperCanaryBuyDecision(**values)  # type: ignore[arg-type]
