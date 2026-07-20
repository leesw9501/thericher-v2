from __future__ import annotations

import ast
import importlib
import os
import socket
import sys
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.contracts import OrderIntent
from thericher_v2.execution.broker import (
    BrokerCapabilities,
    BrokerOrderRequest,
    create_kis_broker_adapter,
)

NOW = datetime(2026, 7, 21, 0, 0, tzinfo=UTC)


def test_maps_only_source_attested_paper_us_buy_limit_fields() -> None:
    mapper = _mapper_module()
    fields = mapper.map_kis_paper_us_buy_limit_order_fields(_request(), exchange="nasd")

    assert mapper.KIS_PAPER_US_BUY_LIMIT_SOURCE_REVISION in mapper.KIS_PAPER_US_BUY_LIMIT_SOURCE_URL
    assert fields == {
        "OVRS_EXCG_CD": "NASD",
        "PDNO": "AAPL",
        "ORD_QTY": "2",
        "OVRS_ORD_UNPR": "145.00",
        "SLL_TYPE": "",
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00",
    }
    assert not {"CANO", "ACNT_PRDT_CD", "CTAC_TLNO", "MGCO_APTM_ODNO"}.intersection(fields)


def test_explicit_exchange_is_never_derived_from_generic_us_market() -> None:
    request = _request()
    mapper = _mapper_module()
    nyse_fields = mapper.map_kis_paper_us_buy_limit_order_fields(request, exchange="NYSE")
    amex_fields = mapper.map_kis_paper_us_buy_limit_order_fields(request, exchange="AMEX")

    assert nyse_fields["OVRS_EXCG_CD"] == "NYSE"
    assert amex_fields["OVRS_EXCG_CD"] == "AMEX"


@pytest.mark.parametrize(
    ("request_overrides", "exchange", "match"),
    [
        ({"market": "KR"}, "NASD", "market US"),
        ({"side": "sell"}, "NASD", "buy orders only"),
        ({"limit_price": None}, "NASD", "positive limit price"),
        ({"quantity": Decimal("1.5")}, "NASD", "whole-share"),
        ({"symbol": "AAPL\n"}, "NASD", "ticker symbol"),
        ({"symbol": "AAPL/US"}, "NASD", "ticker symbol"),
        ({}, "US", "exchange is unsupported"),
        ({}, " NASD", "exchange must be explicit"),
    ],
)
def test_rejects_out_of_scope_order_shapes(
    request_overrides: dict[str, object],
    exchange: str,
    match: str,
) -> None:
    mapper = _mapper_module()
    with pytest.raises(ValueError, match=match):
        mapper.map_kis_paper_us_buy_limit_order_fields(
            _request(**request_overrides),
            exchange=exchange,
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("quantity", Decimal("0"), "positive quantity"),
        ("quantity", Decimal("NaN"), "positive quantity"),
        ("limit_price", Decimal("0"), "positive limit price"),
        ("limit_price", Decimal("NaN"), "positive limit price"),
    ],
)
def test_rejects_invalid_values_even_if_the_immutable_request_is_corrupted(
    field: str,
    value: Decimal,
    match: str,
) -> None:
    request = _request()
    object.__setattr__(request, field, value)

    mapper = _mapper_module()
    with pytest.raises(ValueError, match=match):
        mapper.map_kis_paper_us_buy_limit_order_fields(request, exchange="NASD")


def test_mapper_is_credential_network_and_transport_free(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline mapper must not use credentials, files, or network")

    monkeypatch.setattr(os, "getenv", fail_io)
    monkeypatch.setattr(socket, "socket", fail_io)
    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)

    module_name = "thericher_v2.execution.kis_paper_order_fields"
    sys.modules.pop(module_name, None)
    mapper = importlib.import_module(module_name)
    request = _request()
    fields = mapper.map_kis_paper_us_buy_limit_order_fields(request, exchange="NASD")
    assert fields["PDNO"] == "AAPL"
    adapter = create_kis_broker_adapter()
    assert adapter.capabilities == BrokerCapabilities()
    result = adapter.submit_order(
        OrderIntent(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            market=request.market,
            side=request.side,
            quantity=request.quantity,
            limit_price=request.limit_price,
            decision_id=request.decision_id,
            created_at=request.created_at,
        )
    )
    assert result.status == "unavailable"
    assert result.reason == "broker_execution_disabled"


def test_mapper_module_has_no_credential_or_transport_import() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "thericher_v2"
        / "execution"
        / "kis_paper_order_fields.py"
    )
    source = source_path.read_text(encoding="utf-8")
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not imported_modules.intersection({"os", "pathlib", "socket", "urllib"})
    assert "KIS_PAPER_APP_" not in source
    assert "urlopen" not in source


def _request(**overrides: object) -> BrokerOrderRequest:
    fields: dict[str, object] = {
        "client_order_id": "paper-buy-limit-1",
        "symbol": "AAPL",
        "market": "US",
        "side": "buy",
        "quantity": Decimal("2"),
        "limit_price": Decimal("145.00"),
        "decision_id": "decision-1",
        "created_at": NOW,
    }
    fields.update(overrides)
    return BrokerOrderRequest(**fields)  # type: ignore[arg-type]


def _mapper_module() -> ModuleType:
    return importlib.import_module("thericher_v2.execution.kis_paper_order_fields")
