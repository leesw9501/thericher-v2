from decimal import Decimal

import pytest

from test_kis_readonly_exact_orderability import _response, _Transport
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient
from thericher_v2.execution.kis_readonly import KisPaperConfig, KisPaperReadOnlyError


def client(transport):
    return KisPaperCanaryClient(
        config=KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01"),
        transport=transport,
    )


def test_delegate_keeps_one_in_memory_token_for_repeated_exact_reads():
    transport = _Transport([_response(), _response()])
    broker = client(transport)
    for price in (Decimal("500.12"), Decimal("501")):
        cash, funds = broker.orderable_funds_at_limit(
            symbol="QQQ",
            exchange="NASD",
            limit_price=price,
        )
        assert funds.reference_price == price and cash.currency == "USD"
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    assert broker._issue_access_token() == "synthetic-token"
    assert len(transport.requests) == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "SPY"),
        ("exchange", "NAS"),
        ("limit_price", Decimal(0)),
        ("limit_price", Decimal("NaN")),
        ("limit_price", "500"),
    ],
)
def test_delegate_validates_before_authentication(field, value):
    transport = _Transport([])
    arguments = dict(symbol="QQQ", exchange="NASD", limit_price=Decimal("500"))
    arguments[field] = value
    with pytest.raises(KisPaperReadOnlyError):
        client(transport).orderable_funds_at_limit(**arguments)
    assert transport.requests == []


def test_failed_read_does_not_discard_already_acquired_token():
    transport = _Transport([KisPaperReadOnlyError("orderable_funds_rejected"), _response()])
    broker = client(transport)
    with pytest.raises(KisPaperReadOnlyError, match="orderable_funds_rejected"):
        broker.orderable_funds_at_limit(symbol="QQQ", exchange="NASD", limit_price=Decimal(500))
    broker.orderable_funds_at_limit(symbol="QQQ", exchange="NASD", limit_price=Decimal(500))
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
