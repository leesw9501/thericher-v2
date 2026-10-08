from __future__ import annotations

import builtins
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from thericher_v2.data import kis_current_trio_context as current
from thericher_v2.data.kis_daily_price_endpoints import (
    KisDailyEndpointPage,
    KisDailyEndpointRow,
    parse_kis_daily_price_endpoints,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_market_data import (
    KisMarketDataResponse,
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyQuery,
    KisPaperMarketDataError,
)

REF = "sha256:" + "a" * 64
OTHER_REF = "sha256:" + "b" * 64
SCOPE = {"SPY": frozenset({"AMS"}), "TLT": frozenset({"NAS"}), "GLD": frozenset({"AMS"})}
ENTRY = date(2026, 10, 9)


def schedule(entry=ENTRY):
    days, day = [], entry
    while len(days) < 64:
        day -= timedelta(days=1)
        session = us_equity_2026_session(day)
        if session is not None:
            days.append(session)
    return tuple(reversed(days))


def wire_row(day, offset=0):
    return dict(
        xymd=day.strftime("%Y%m%d"),
        open=str(Decimal("10000.125") + offset),
        clos=str(Decimal("20000.375") + offset),
        high="30000",
        low="1",
        tvol="100",
    )


def page(symbol, days=None, *, anchor=None, exchange=None, continuation=None, extra=()):
    days = tuple(s.session_date for s in schedule()) if days is None else days
    query = KisPaperDailyQuery(
        symbol=symbol,
        exchange=exchange or next(iter(SCOPE[symbol])),
        by_date=(anchor or schedule()[-1].session_date).strftime("%Y%m%d"),
        continuation=continuation,
        approved_symbol_exchanges={
            "SPY": frozenset({"AMS"}),
            "TLT": frozenset({"NAS", "AMS"}),
            "GLD": frozenset({"AMS"}),
        },
    )
    offset = current.INSTRUMENT_ORDER.index(symbol) * 100
    rows = [wire_row(day, offset + i) for i, day in enumerate(days)] + list(extra)
    response = KisMarketDataResponse.from_payload(
        status_code=200,
        payload=dict(rt_cd="0", output1={}, output2=rows),
        headers={"tr_cont": "F"},
    )
    return parse_kis_daily_price_endpoints(response, query=query)


def bindings(pages, *, start=None, ref=REF):
    start = start or us_equity_2026_session(ENTRY).window.open_ts + timedelta(minutes=10)
    return current.KisCurrentTrioCollectionBinding(
        collection_ref=ref,
        started_at=start,
        completed_at=start + timedelta(seconds=8),
        pages=tuple(
            current.KisCurrentTrioPageBinding(
                collection_ref=ref,
                query=pages[symbol].query,
                source_body_sha256=pages[symbol].source_body_sha256,
                typed_page_sha256=current.current_trio_page_sha256(pages[symbol]),
                request_started_at=start + timedelta(seconds=i * 3),
                observed_at=start + timedelta(seconds=i * 3 + 2),
            )
            for i, symbol in enumerate(current.INSTRUMENT_ORDER)
        ),
    )


@pytest.fixture
def inputs():
    pages = {symbol: page(symbol) for symbol in current.INSTRUMENT_ORDER}
    return pages, bindings(pages)


def prepare(pages, binding, *, history=None, entry=None, decision=None):
    entry = entry or us_equity_2026_session(ENTRY)
    return current.prepare_current_trio_context(
        pages,
        scheduled_history=schedule() if history is None else history,
        entry_session=entry,
        decision_at=decision or entry.window.open_ts + timedelta(hours=2),
        collection_binding=binding,
    )


def expect_unavailable(code, call):
    with pytest.raises(current.KisCurrentTrioInputUnavailable, match=f"^{code}$") as caught:
        call()
    assert caught.value.safe_facts() == dict(status="input_unavailable", reason_code=code)
    assert "20000.375" not in str(caught.value)


def test_exact_intraday_context_has_private_canonical_64_closes_and_63_intervals(inputs):
    pages, binding = inputs
    result = prepare(pages, binding)
    assert result.session_dates == tuple(s.session_date for s in schedule())
    assert tuple(map(len, result.closes)) == (64, 64, 64)
    assert result.closes[0][0] == Decimal("20000.375")
    assert result.closes[1][0] == Decimal("20100.375")
    assert result.closes[2][-1] == Decimal("20263.375")
    assert result.decision_at > result.entry_at > result.feature_cutoff
    assert result.feature_cutoff == schedule()[-1].window.close_ts
    assert result.observed_at_by_symbol == tuple(p.observed_at for p in binding.pages)
    assert result.collection_completed_at <= result.decision_at
    assert result.safe_facts()["return_intervals_per_symbol"] == 63
    assert not hasattr(result, "returns")  # Engine owns the frozen return definition.


def test_mapping_order_cannot_reorder_assets_or_change_identity(inputs):
    pages, binding = inputs
    assert prepare(dict(reversed(tuple(pages.items()))), binding) == prepare(pages, binding)


def test_repr_projection_and_immutability_never_expose_closes(inputs):
    result = prepare(*inputs)
    facts = result.safe_facts()
    rendered = repr(result) + json.dumps(facts)
    assert "20000.375" not in rendered and "20263.375" not in rendered
    assert "closes" not in facts and "returns" not in facts
    assert facts["provider_publication_at"] == facts["finality"] == "not_observed"
    assert facts["point_in_time"] == "not_claimed"
    assert facts["raw_byte_custody"] == "caller_owned_not_verified_by_pure_selector"
    with pytest.raises(FrozenInstanceError):
        result.closes = ()
    facts["status"] = "changed"
    assert result.safe_facts()["status"] == "ready"


@pytest.mark.parametrize("symbols", [("SPY", "TLT"), ("SPY", "TLT", "GLD", "QQQ")])
def test_missing_or_extra_symbol_rejects_only_current_input(inputs, symbols):
    pages, binding = inputs
    source = {symbol: pages.get(symbol, pages["SPY"]) for symbol in symbols}
    expect_unavailable("source_symbols_invalid", lambda: prepare(source, binding))


def test_required_past_gap_does_not_use_64_available_dates(inputs):
    pages, _ = inputs
    dates = tuple(s.session_date for s in schedule())
    prior = dates[0] - timedelta(days=1)
    replacement = page("SPY", (prior,) + dates[1:])
    pages = {**pages, "SPY": replacement}
    expect_unavailable("required_session_missing", lambda: prepare(pages, bindings(pages)))


def test_valid_overhang_changes_provenance_but_never_selected_closes(inputs):
    pages, binding = inputs
    original = prepare(pages, binding)
    dates = tuple(s.session_date for s in schedule())
    pages = {**pages, "SPY": page("SPY", dates, extra=(wire_row(dates[0] - timedelta(days=1)),))}
    other = prepare(pages, bindings(pages))
    assert other.closes == original.closes and other.session_dates == original.session_dates
    assert other.context_sha256 != original.context_sha256


def test_valid_duplicate_oc_preserves_full_fingerprints_without_extra_observation(inputs):
    pages, _ = inputs
    last = wire_row(schedule()[-1].session_date, 63)
    pages = {**pages, "SPY": page("SPY", extra=({**last, "high": "1"},))}
    result = prepare(pages, bindings(pages))
    assert len(result.closes[0]) == 64 and result.duplicate_row_counts == (1, 0, 0)
    assert len(pages["SPY"].source_row_fingerprints) == 65
    assert pages["SPY"].rows[-1].unused_ohlcv_faults == ("high_below_open_close",)


def test_conflicting_duplicate_oc_cannot_produce_a_valid_page():
    bad = wire_row(schedule()[-1].session_date, 63)
    with pytest.raises(KisPaperMarketDataError, match="endpoint_duplicate_conflict"):
        page("SPY", extra=({**bad, "clos": "99999.777"},))


@pytest.mark.parametrize("change", ["missing", "extra", "reverse", "skip", "geometry", "sources"])
def test_calendar_is_exact_consecutive_official_64_not_caller_available_subset(inputs, change):
    history = schedule()
    if change == "missing":
        history = history[1:]
    elif change == "extra":
        history = history + (us_equity_2026_session(ENTRY),)
    elif change == "reverse":
        history = tuple(reversed(history))
    elif change == "skip":
        history = (us_equity_2026_session(history[0].session_date - timedelta(days=1)),) + history[
            1:
        ]
    elif change == "geometry":
        last = replace(
            history[-1],
            window=replace(
                history[-1].window, close_ts=history[-1].window.close_ts - timedelta(minutes=1)
            ),
        )
        history = history[:-1] + (last,)
    else:
        history = history[:-1] + (replace(history[-1], sources=("unverified", "unverified")),)
    expect_unavailable("calendar_invalid", lambda: prepare(*inputs, history=history))


def test_calendar_holiday_and_early_close_are_retained_in_geometry():
    entry = us_equity_2026_session(date(2026, 11, 30))
    history = schedule(entry.session_date)
    assert history[-1].session_date == date(2026, 11, 27)
    assert history[-1].kind == "early_close" and history[-1].window.close_ts.hour == 18
    assert date(2026, 11, 26) not in tuple(s.session_date for s in history)
    dates = tuple(s.session_date for s in history)
    pages = {symbol: page(symbol, dates, anchor=dates[-1]) for symbol in current.INSTRUMENT_ORDER}
    binding = bindings(pages, start=entry.window.open_ts + timedelta(minutes=5))
    result = prepare(pages, binding, history=history, entry=entry)
    assert result.feature_cutoff == history[-1].window.close_ts


@pytest.mark.parametrize(
    "decision",
    [
        datetime(2026, 10, 8, 20, tzinfo=UTC),
        datetime(2026, 10, 9, 13, 29, tzinfo=UTC),
        datetime(2026, 10, 9, 20, tzinfo=UTC),
        datetime(2026, 10, 9, 16),
        datetime(2026, 10, 10, 1, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_decision_is_actual_utc_intraday_not_previous_close_or_after_entry_close(inputs, decision):
    expect_unavailable("decision_not_in_entry_session", lambda: prepare(*inputs, decision=decision))


def test_current_date_query_cannot_silently_filter_to_previous_context(inputs):
    pages, _ = inputs
    pages = {**pages, "SPY": page("SPY", anchor=ENTRY, extra=(wire_row(ENTRY),))}
    expect_unavailable("page_identity_mismatch", lambda: prepare(pages, bindings(pages)))


@pytest.mark.parametrize("day", [ENTRY, date(2026, 10, 12)])
def test_current_future_rows_poisoned_into_past_bound_page_reject_whole_page(inputs, day):
    pages, binding = inputs
    original = pages["SPY"]
    injected = KisDailyEndpointRow(day.isoformat(), "10000.125", "99999.777", OTHER_REF)
    corrupted = replace(original)
    object.__setattr__(corrupted, "rows", original.rows + (injected,))
    pages = {**pages, "SPY": corrupted}
    expect_unavailable("page_invalid", lambda: prepare(pages, binding))


@pytest.mark.parametrize(
    "field,value", [("source_body_sha256", OTHER_REF), ("typed_page_sha256", OTHER_REF)]
)
def test_exact_source_and_typed_hash_binding(inputs, field, value):
    pages, binding = inputs
    first = replace(binding.pages[0], **{field: value})
    binding = replace(binding, pages=(first,) + binding.pages[1:])
    expect_unavailable("page_hash_mismatch", lambda: prepare(pages, binding))


def test_valid_numeric_mutation_without_reattestation_rejects(inputs):
    pages, binding = inputs
    original = pages["SPY"]
    mutated = replace(original.rows[0], close="99999.777")
    pages = {**pages, "SPY": replace(original, rows=(mutated,) + original.rows[1:])}
    expect_unavailable("page_hash_mismatch", lambda: prepare(pages, binding))


def test_canonical_unique_rows_must_not_be_mutated_to_duplicate(inputs):
    pages, binding = inputs
    bad = replace(pages["SPY"])
    object.__setattr__(bad, "rows", bad.rows + (bad.rows[-1],))
    expect_unavailable("page_invalid", lambda: prepare({**pages, "SPY": bad}, binding))


def test_mixed_collection_refs_cannot_blend_or_relabel_old_page(inputs):
    _, binding = inputs
    expect_unavailable(
        "collection_binding_invalid",
        lambda: replace(
            binding,
            pages=(replace(binding.pages[0], collection_ref=OTHER_REF),) + binding.pages[1:],
        ),
    )


@pytest.mark.parametrize(
    "field,value", [("source_kind", "frozen-research-cohort"), ("gubn", "1"), ("modp", "1")]
)
def test_source_grade_and_fixed_parameter_attestations_are_closed(inputs, field, value):
    expect_unavailable(
        "collection_binding_invalid", lambda: replace(inputs[1].pages[0], **{field: value})
    )


def test_tlt_ams_and_continuation_are_not_current_trio_binding(inputs):
    pages, _ = inputs
    for replacement in (page("TLT", exchange="AMS"), page("TLT", continuation="F")):
        expect_unavailable(
            "collection_binding_invalid",
            lambda replacement=replacement: bindings({**pages, "TLT": replacement}),
        )


def test_adjustment_probe_query_is_not_accepted_even_if_mode_looks_ordinary(inputs):
    bad = replace(inputs[0]["SPY"])
    query = KisPaperDailyAdjustmentProbeQuery("SPY", "20261008", "1", "AMS", SCOPE)
    object.__setattr__(bad, "query", query)
    expect_unavailable("page_invalid", lambda: current.current_trio_page_sha256(bad))


@pytest.mark.parametrize("change", ["before_cutoff", "after_decision", "before_request", "overlap"])
def test_local_collection_times_cannot_be_backdated_or_inferred_available(inputs, change):
    pages, binding = inputs

    def call():
        if change == "before_cutoff":
            early = bindings(pages, start=schedule()[-1].window.close_ts - timedelta(seconds=10))
            return prepare(pages, early)
        if change == "after_decision":
            late = us_equity_2026_session(ENTRY).window.open_ts + timedelta(hours=3)
            return prepare(pages, bindings(pages, start=late))
        if change == "before_request":
            return replace(binding.pages[0], observed_at=binding.started_at - timedelta(seconds=1))
        return replace(
            binding,
            pages=(
                binding.pages[0],
                replace(
                    binding.pages[1], request_started_at=binding.started_at + timedelta(seconds=1)
                ),
                binding.pages[2],
            ),
        )

    expect_unavailable("collection_time_invalid", call)


def test_local_receipt_does_not_become_previous_close_publication(inputs):
    result = prepare(*inputs)
    assert all(t > result.feature_cutoff for t in result.observed_at_by_symbol)
    assert (
        result.safe_facts()["source_datetime"] == "scheduled_session_close_not_provider_publication"
    )
    assert (
        result.safe_facts()["availability"] == "caller_attested_local_receipt_before_decision_only"
    )
    assert not hasattr(result, "provider_publication_at")


def test_page_validation_redacts_invalid_private_value(inputs):
    pages, binding = inputs
    bad = replace(pages["SPY"])
    poisoned = replace(bad.rows[0])
    object.__setattr__(poisoned, "close", "fake_private_secret")
    object.__setattr__(bad, "rows", (poisoned,) + bad.rows[1:])
    expect_unavailable("page_invalid", lambda: prepare({**pages, "SPY": bad}, binding))
    assert str(current.KisCurrentTrioInputUnavailable("fake_private_secret")) == "page_invalid"


def test_selector_has_no_io_or_network_and_does_not_mutate_originals(inputs, monkeypatch):
    pages, binding = inputs
    before = tuple(current.current_trio_page_sha256(pages[s]) for s in current.INSTRUMENT_ORDER)

    def forbidden(*args, **kwargs):
        pytest.fail("pure selector attempted external IO")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = prepare(pages, binding)
    assert result.typed_page_sha256_by_symbol == before
    assert (
        tuple(current.current_trio_page_sha256(pages[s]) for s in current.INSTRUMENT_ORDER)
        == before
    )


def test_close_selection_is_independent_of_decimal_context(inputs):
    normal = prepare(*inputs)
    with localcontext() as ctx:
        ctx.prec = 3
        assert prepare(*inputs) == normal


def test_unknown_calendar_scope_fails_categorically_not_weekday_guess(inputs):
    entry = replace(us_equity_2026_session(ENTRY), session_date=date(2027, 1, 4))
    expect_unavailable("calendar_invalid", lambda: prepare(*inputs, entry=entry))


def test_typed_page_helper_rejects_non_page_without_printing_it():
    expect_unavailable(
        "page_invalid", lambda: current.current_trio_page_sha256("fake_private_secret")
    )
    assert not isinstance("fake_private_secret", KisDailyEndpointPage)
