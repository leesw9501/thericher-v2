import json
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from decimal import ROUND_UP, Decimal, Inexact, Rounded, localcontext

import pytest

from thericher_v2.data.kis_sector_adjustment_comparison import (
    KisSectorAdjustmentComparison,
    compare_kis_sector_adjustment_pages,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyPage,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
)


def row(day="20251204", close="100", *, opening=None, volume="777"):
    value = Decimal(close)
    return KisPaperDailyRawRow(day, opening or close, str(value * 2), str(value / 2), close, volume)


def page(symbol="XLK", mode="0", *, pre="100", post="50", rows=None):
    query = KisPaperDailyAdjustmentProbeQuery(
        symbol,
        "20251205",
        mode,
        exchange="AMS",
        approved_symbol_exchanges={symbol: frozenset({"AMS"})},
    )
    rows = rows or (row(close=pre), row("20251205", post))
    facts = KisPaperDailyPage(
        query, len(rows), max(r.xymd for r in rows), min(r.xymd for r in rows), True, True, "F"
    )
    return KisPaperDailyRawPage(facts, rows)


def six(*, adjusted="50", post="50"):
    return tuple(
        p
        for symbol in ("XLK", "XLE")
        for p in (page(symbol), page(symbol, "1", pre=adjusted, post=post), page(symbol))
    )


def mutate(value, **fields):
    for key, field in fields.items():
        object.__setattr__(value, key, field)
    return value


def copy_pages(pages):
    return tuple(
        replace(p, page=replace(p.page), rows=tuple(replace(r) for r in p.rows)) for p in pages
    )


def test_half_signature_and_safe_counts_no_prices_or_rows():
    result = compare_kis_sector_adjustment_pages(six())
    assert [r.symbol for r in result] == ["XLK", "XLE"]
    for r in result:
        assert r.status == "consistent_with_half_split_signature"
        assert (r.date_count, r.pre_event_count, r.post_event_count) == (2, 1, 1)
        assert (r.changed_close_count, r.half_signature_count, r.post_changed_count) == (1, 1, 0)
        payload = r.safe_payload()
        assert payload["raw_repeatable"] is True
        assert payload["split_methodology_proven"] is False
        assert payload["dividend_total_return_PIT_finality_claimed"] is False
        assert set(payload.values()) <= {
            None,
            False,
            True,
            2,
            "XLK",
            "XLE",
            "kis_sector_adjustment_comparison_v1",
            "consistent_with_half_split_signature",
        }
        assert "777" not in json.dumps(payload) + repr(r)
        with pytest.raises(FrozenInstanceError):
            r.status = "unchanged"


@pytest.mark.parametrize(
    "adjusted,expected",
    [
        ("100", "unchanged"),
        ("50.005", "consistent_with_half_split_signature"),
        ("49.995", "consistent_with_half_split_signature"),
        ("50.00500000000000000000001", "changed_other_pattern"),
        ("49.99499999999999999999999", "changed_other_pattern"),
        ("60", "changed_other_pattern"),
    ],
)
def test_half_cent_inclusive_exact_edges(adjusted, expected):
    assert compare_kis_sector_adjustment_pages(six(adjusted=adjusted))[0].status == expected


def test_post_close_must_be_exact_not_half_cent_tolerance():
    r = compare_kis_sector_adjustment_pages(six(post="50.00000000000000000001"))[0]
    assert r.status == "changed_other_pattern" and r.post_changed_count == 1


def test_numeric_equality_ignores_mode1_formatting_not_raw_repeat():
    assert (
        compare_kis_sector_adjustment_pages(six(adjusted="100.00", post="50.00"))[0].status
        == "unchanged"
    )
    pages = list(six())
    pages[2] = page(pre="100.00")
    assert compare_kis_sector_adjustment_pages(tuple(pages))[0].status == "nonrepeatable"


@pytest.mark.parametrize(
    "field,value",
    [("clos", "100.01"), ("open", "100.01"), ("tvol", "778"), ("high", "201"), ("low", "49")],
)
def test_repeated_canonical_all_fields_not_close_only(field, value):
    pages = list(six())
    mutate(pages[2].rows[0], **{field: value})
    result = compare_kis_sector_adjustment_pages(tuple(pages))
    assert result[0].status == "nonrepeatable" and result[0].raw_repeatable is False
    assert result[1].status == "consistent_with_half_split_signature"


def test_row_order_and_response_continuation_metadata_are_not_repeat_identity():
    pages = list(six())
    pages[2] = replace(
        pages[2],
        rows=pages[2].rows[::-1],
        page=replace(pages[2].page, continuation_available=False, continuation_value=None),
    )
    assert compare_kis_sector_adjustment_pages(tuple(pages))[0].raw_repeatable is True


@pytest.mark.parametrize("change", ["symbol", "venue", "mode", "anchor", "continuation"])
def test_query_scope_must_be_fixed(change):
    pages = list(six())
    query = pages[1].page.query
    if change == "continuation":
        from thericher_v2.execution.kis_market_data import KisPaperDailyQuery

        query = KisPaperDailyQuery("XLK", "20251205", "F", "AMS", {"XLK": frozenset({"AMS"})})
        mutate(pages[1].page, query=query)
    else:
        key, value = {
            "symbol": ("symbol", "SPY"),
            "venue": ("exchange", "NAS"),
            "mode": ("adjustment_mode", "0"),
            "anchor": ("by_date", "20251204"),
        }[change]
        mutate(query, **{key: value})
    assert compare_kis_sector_adjustment_pages(tuple(pages))[0].status == "input_unavailable"


@pytest.mark.parametrize(
    "field,value",
    [
        ("clos", "NaN"),
        ("clos", "Infinity"),
        ("clos", "-1"),
        ("clos", "0"),
        ("clos", 50),
        ("clos", "fake_secret"),
        ("high", "1"),
        ("low", "101"),
        ("tvol", "-1"),
    ],
)
def test_mutated_native_rows_invalid_and_safe(field, value):
    pages = list(six())
    mutate(pages[1].rows[0], **{field: value})
    r = compare_kis_sector_adjustment_pages(tuple(pages))[0]
    assert r.status == "input_unavailable"
    assert "fake_secret" not in json.dumps(r.safe_payload()) + repr(r)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing",
        "future",
        "invalid_date",
        "date_sets",
        "count_bool",
        "bounds",
        "flag",
        "schema",
        "header",
    ],
)
def test_geometry_revalidated(change):
    pages = list(six())
    p = pages[1]
    if change == "duplicate":
        mutate(p, rows=(p.rows[0], p.rows[0], p.rows[1]))
        mutate(p.page, row_count=3)
    elif change == "missing":
        mutate(p.rows[0], xymd="20251203")
        mutate(p.page, oldest_date="20251203")
    elif change == "future":
        mutate(p.rows[1], xymd="20251208")
        mutate(p.page, newest_date="20251208")
    elif change == "invalid_date":
        mutate(p.rows[0], xymd="20250230")
    elif change == "date_sets":
        mutate(p, rows=(row("20251203", "50"), *p.rows))
        mutate(p.page, row_count=3, oldest_date="20251203")
    else:
        field, value = {
            "count_bool": ("row_count", True),
            "bounds": ("oldest_date", "20251203"),
            "flag": ("required_ohlcv_fields_present", False),
            "schema": ("schema_version", 999),
            "header": ("continuation_value", "N"),
        }[change]
        mutate(p.page, **{field: value})
    assert compare_kis_sector_adjustment_pages(tuple(pages))[0].status == "input_unavailable"


@pytest.mark.parametrize("outer", [None, (), (None,) * 6, [None] * 6, "fake_secret"])
def test_outer_input_safe_unavailable(outer):
    result = compare_kis_sector_adjustment_pages(outer)
    assert all(r.status == "input_unavailable" for r in result)
    assert "fake_secret" not in repr(result)


def test_maximum100_dates_all_pre_closes_checked():
    days = [(date(2025, 12, 5) - timedelta(days=i)).strftime("%Y%m%d") for i in range(100)]
    raw = tuple(row(d, "50" if d == "20251205" else "100") for d in days)
    adjusted = tuple(row(d, "50") for d in days)
    pages = tuple(
        p
        for symbol in ("XLK", "XLE")
        for p in (page(symbol, rows=raw), page(symbol, "1", rows=adjusted), page(symbol, rows=raw))
    )
    r = compare_kis_sector_adjustment_pages(pages)[0]
    assert (r.date_count, r.pre_event_count, r.half_signature_count) == (100, 99, 99)
    mutant = copy_pages(pages)
    mutate(mutant[1].rows[-1], clos="60")
    assert compare_kis_sector_adjustment_pages(mutant)[0].status == "changed_other_pattern"
    assert compare_kis_sector_adjustment_pages(pages)[0] == r


def test_hostile_decimal_context_exact_no_flags_or_input_mutation():
    pages = six(adjusted="50.00500000000000000000001")
    before = copy_pages(pages)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.Emax, context.Emin = 2, -2
        context.traps[Inexact] = context.traps[Rounded] = True
        context.clear_flags()
        r = compare_kis_sector_adjustment_pages(pages)[0]
        assert r.status == "changed_other_pattern"
        assert not any(context.flags.values())
    assert pages == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "fake_secret"),
        ("status", "fake_secret"),
        ("reason", "fake_secret"),
        ("date_count", True),
    ],
)
def test_public_result_rejects_unsafe_construction_and_mutation(field, value):
    with pytest.raises(ValueError, match="^result_invalid$") as caught:
        KisSectorAdjustmentComparison(
            **{**dict(symbol="XLK", status="input_unavailable"), field: value}
        )
    assert "fake_secret" not in str(caught.value)
    result = compare_kis_sector_adjustment_pages(six())[0]
    mutate(result, **{field: value})
    with pytest.raises(ValueError, match="^result_invalid$"):
        result.safe_payload()


def test_overfull_page_and_wrong_symbol_sequence_unavailable():
    pages = list(six())
    mutate(pages[0], rows=pages[0].rows + (pages[0].rows[0],) * 99)
    mutate(pages[0].page, row_count=101)
    assert compare_kis_sector_adjustment_pages(tuple(pages))[0].status == "input_unavailable"
    ordered = six()
    assert all(
        r.status == "input_unavailable"
        for r in compare_kis_sector_adjustment_pages(ordered[3:] + ordered[:3])
    )
