from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

import pytest

from thericher_v2.execution.kis_paper_quote import (
    KisPaperQuoteError,
    KisPaperSpyLimitInput,
    derive_kis_paper_marketable_limit,
    derive_kis_paper_nonmarket_limit,
    parse_kis_paper_qqq_limit_input,
    parse_kis_paper_spy_limit_input,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


def _quote() -> KisPaperSpyLimitInput:
    return KisPaperSpyLimitInput(
        last=Decimal("600.12"),
        decimal_places=2,
        tick_size=Decimal("0.05"),
        quoted_at=NOW,
        best_bid=Decimal("600.11"),
        best_ask=Decimal("600.13"),
    )


@pytest.mark.parametrize(("side", "expected"), (("buy", "600.15"), ("sell", "600.10")))
def test_marketable_limit_uses_correct_book_side_and_rounding(
    side: Literal["buy", "sell"], expected: str
) -> None:
    quote = _quote()

    limit = derive_kis_paper_marketable_limit(quote, side=side, observed_at=NOW)

    assert limit == Decimal(expected)
    assert limit > 0
    assert limit % quote.tick_size == 0
    assert limit.as_tuple().exponent == -quote.decimal_places
    assert (
        derive_kis_paper_marketable_limit(
            replace(quote, last=Decimal("999.99")), side=side, observed_at=NOW
        )
        == limit
    )


@pytest.mark.parametrize("side", ("buy", "sell"))
@pytest.mark.parametrize(
    ("bid", "ask", "buy", "sell"),
    (
        ("600.10", "600.15", "600.15", "600.10"),
        ("600.10", "600.10", "600.10", "600.10"),
        ("600.101", "600.149", "600.15", "600.10"),
        ("0.01", "0.06", "0.10", None),
    ),
)
def test_marketable_limit_tick_boundaries(
    side: Literal["buy", "sell"], bid: str, ask: str, buy: str, sell: str | None
) -> None:
    quote = replace(_quote(), best_bid=Decimal(bid), best_ask=Decimal(ask))
    expected = buy if side == "buy" else sell
    if expected is None:
        with pytest.raises(KisPaperQuoteError, match="^quote_limit_invalid$"):
            derive_kis_paper_marketable_limit(quote, side=side, observed_at=NOW)
    else:
        assert derive_kis_paper_marketable_limit(quote, side=side, observed_at=NOW) == Decimal(
            expected
        )


@pytest.mark.parametrize("side", ("buy", "sell"))
@pytest.mark.parametrize("age_seconds", (-5, 0, 120))
def test_marketable_limit_accepts_existing_freshness_boundaries(
    side: Literal["buy", "sell"], age_seconds: int
) -> None:
    observed_at = (NOW + timedelta(seconds=age_seconds)).astimezone(timezone(timedelta(hours=9)))
    assert derive_kis_paper_marketable_limit(_quote(), side=side, observed_at=observed_at) > 0


@pytest.mark.parametrize("side", ("buy", "sell"))
@pytest.mark.parametrize(
    "observed_at",
    (
        NOW + timedelta(seconds=120, microseconds=1),
        NOW - timedelta(seconds=5, microseconds=1),
        NOW.replace(tzinfo=None),
    ),
)
def test_marketable_limit_rejects_stale_future_and_naive_clocks(
    side: Literal["buy", "sell"], observed_at: datetime
) -> None:
    with pytest.raises(KisPaperQuoteError, match="^quote_timestamp_stale$"):
        derive_kis_paper_marketable_limit(_quote(), side=side, observed_at=observed_at)


@pytest.mark.parametrize("side", ("buy", "sell"))
@pytest.mark.parametrize("field", ("best_bid", "best_ask"))
@pytest.mark.parametrize(
    "value",
    (
        None,
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        "600.12",
        True,
    ),
)
def test_marketable_limit_requires_both_valid_prices(
    side: Literal["buy", "sell"], field: str, value: object
) -> None:
    quote = replace(_quote(), **{field: value})
    with pytest.raises(KisPaperQuoteError, match="^quote_bid_ask_invalid$"):
        derive_kis_paper_marketable_limit(quote, side=side, observed_at=NOW)


@pytest.mark.parametrize("side", ("buy", "sell"))
def test_marketable_limit_rejects_crossed_book(side: Literal["buy", "sell"]) -> None:
    quote = replace(_quote(), best_bid=Decimal("600.14"))
    with pytest.raises(KisPaperQuoteError, match="^quote_bid_ask_invalid$"):
        derive_kis_paper_marketable_limit(quote, side=side, observed_at=NOW)


@pytest.mark.parametrize("side", ("BUY", "hold", "", None))
def test_marketable_limit_rejects_invalid_side(side: object) -> None:
    with pytest.raises(ValueError, match="^side must be buy or sell$"):
        derive_kis_paper_marketable_limit(_quote(), side=side, observed_at=NOW)


def test_marketable_limit_requires_limit_input_and_explicit_clock() -> None:
    with pytest.raises(TypeError, match="^quote must be a KisPaperSpyLimitInput$"):
        derive_kis_paper_marketable_limit(_quote().as_quote(), side="buy", observed_at=NOW)
    with pytest.raises(KisPaperQuoteError, match="^quote_timestamp_invalid$"):
        derive_kis_paper_marketable_limit(_quote(), side="buy", observed_at=None)


@pytest.mark.parametrize(
    "parser", (parse_kis_paper_spy_limit_input, parse_kis_paper_qqq_limit_input)
)
@pytest.mark.parametrize(
    ("book", "retained"),
    (
        ({"pbid1": "600.10", "pask1": "600.15"}, True),
        ({"pbid1": "600.10", "pask1": "600.10"}, True),
        ({}, False),
        ({"pbid1": "600.10"}, False),
        ({"pask1": "600.15"}, False),
        ({"pbid1": "", "pask1": "600.15"}, False),
        ({"pbid1": "600.10", "pask1": "bad"}, False),
        ({"pbid1": "NaN", "pask1": "Infinity"}, False),
        ({"pbid1": "600.10", "pask1": "0"}, False),
        ({"pbid1": True, "pask1": "600.15"}, False),
        ({"pbid1": "600.20", "pask1": "600.15"}, False),
        ({"pbid1": "600.11", "pask1": "600.15"}, False),
        ({"pbid1": "600.10", "pask1": "600.151"}, False),
        ({"pbid1": "1e999999999", "pask1": "1e999999999"}, False),
    ),
)
def test_parser_retains_only_compatible_book_without_breaking_nonmarket(
    parser, book, retained
) -> None:
    quote = parser(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": "600.12",
                "zdiv": "2",
                "dymd": "20260722",
                "dhms": "233000",
            },
            "output2": book,
        },
        price_detail_payload={"rt_cd": "0", "output": {"zdiv": "2", "e_hogau": "0.05"}},
        observed_at=NOW,
    )

    assert quote.quoted_at == NOW
    assert derive_kis_paper_nonmarket_limit(quote.as_quote(), tick_size=quote.tick_size) == Decimal(
        "598.60"
    )
    if retained:
        assert quote.best_bid == Decimal(book["pbid1"])
        assert quote.best_ask == Decimal(book["pask1"])
        assert (
            derive_kis_paper_marketable_limit(quote, side="buy", observed_at=NOW) == quote.best_ask
        )
        with pytest.raises(KisPaperQuoteError, match="^quote_timestamp_stale$"):
            derive_kis_paper_marketable_limit(
                quote, side="sell", observed_at=NOW + timedelta(seconds=121)
            )
    else:
        assert quote.best_bid is quote.best_ask is None
        with pytest.raises(KisPaperQuoteError, match="^quote_bid_ask_invalid$"):
            derive_kis_paper_marketable_limit(quote, side="buy", observed_at=NOW)
    for value in ("600.12", "600.10", "600.15"):
        assert value not in repr(quote)
        assert value not in str(quote)


@pytest.mark.parametrize("book", (None, [], "invalid", [{"pbid1": "600", "pask1": "601"}]))
def test_header_prices_cannot_substitute_for_missing_real_book(book) -> None:
    quote = parse_kis_paper_spy_limit_input(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": "600.12", "zdiv": "2", "dymd": "20260722", "dhms": "233000",
                "pbid1": "600.10", "pask1": "600.15",
            },
            "output2": book,
        },
        price_detail_payload={"rt_cd": "0", "output": {"zdiv": "2", "e_hogau": "0.05"}},
        observed_at=NOW,
    )
    assert quote.best_bid is quote.best_ask is None
    assert quote.last == Decimal("600.12")


def test_legacy_positional_constructor_and_nonmarket_limit_are_unchanged() -> None:
    quote = KisPaperSpyLimitInput(Decimal("600.12"), 2, Decimal("0.01"), NOW)
    assert quote.best_bid is quote.best_ask is None
    assert derive_kis_paper_nonmarket_limit(quote.as_quote()) == Decimal("598.61")
    assert derive_kis_paper_nonmarket_limit(
        replace(quote, best_bid=Decimal("700"), best_ask=Decimal("500")).as_quote(),
        tick_size=quote.tick_size,
    ) == Decimal("598.61")
