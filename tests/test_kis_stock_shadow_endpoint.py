"""Synthetic one-page endpoint contracts; no IO, client or credential loading."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import InvalidOperation, localcontext

import pytest

from thericher_v2.data import kis_stock_shadow_endpoint as worker
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyPage,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
)
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

PIN = "sha256:" + "a" * 64
SECRET = "fake_secret_do_not_publish"


def scope(count=2, day=date(2026, 10, 12)):
    peers = tuple(
        worker.EndpointPeer(f"opaque-{i}", "S" + chr(65 + i), "NAS") for i in range(count)
    )
    session = us_equity_2026_session(day)
    return worker.EndpointScope(
        peers,
        worker.peer_sha256(peers),
        PIN,
        CrossAssetSession(day, session.window.open_ts, session.window.close_ts),
        datetime(2026, 10, 9, 20, tzinfo=UTC),
    )


def row(day="20261012", opening="7.0010"):
    return KisPaperDailyRawRow(day, opening, "8.00", "6.0", "7.200", "100.00")


def page(query, rows=None, **kwargs):
    rows = (row(query.by_date), row("20261009")) if rows is None else tuple(rows)
    days = [r.xymd for r in rows]
    metadata = KisPaperDailyPage(
        query, len(rows), max(days) if days else None, min(days) if days else None, True, True, "F"
    )
    return KisPaperDailyRawPage(replace(metadata, **kwargs), rows)


def clock(sc):
    return lambda: sc.session.close_at + timedelta(seconds=5)


def collect(sc, fetch=None, **kwargs):
    return worker.collect_endpoints(
        sc, fetch_daily_raw_page=fetch or page, clock=clock(sc), **kwargs
    )


def test_exact_scope_single_page_and_no_continuation():
    sc, seen = scope(), []

    def fetch(query):
        seen.append(query)
        return page(query)

    result = collect(sc, fetch)
    assert result.callback_attempts == len(sc.peers) == len(seen)
    assert result.next_index == 2 and result.stop_reason is None
    assert all(
        q.by_date == "20261012" and q.adjustment_mode == "0" and q.continuation is None
        for q in seen
    )
    assert tuple(q.symbol for q in seen) == tuple(p.symbol for p in sc.peers)
    assert all(
        o.status == "available"
        and o.endpoint_open == "7.0010"
        and len(o.rows) == 2
        and o.canonical_rows_sha256.startswith("sha256:")
        for o in result.observations
    )
    assert result.safe_facts()["available_count"] == 2


def test_before_close_zero_callback_entries():
    sc = scope()

    def never(query):
        pytest.fail("callback before endpoint completion")

    result = worker.collect_endpoints(
        sc,
        fetch_daily_raw_page=never,
        clock=lambda: sc.session.close_at - timedelta(microseconds=1),
    )
    assert result.callback_attempts == 0 and result.next_index == 0
    assert result.stop_reason == "endpoint_not_completed"
    assert result.safe_facts()["not_attempted_count"] == 2


def test_at_close_allowed_and_clock_backward_rejected():
    sc = scope(1)
    times = iter([sc.session.close_at, sc.session.close_at - timedelta(seconds=1)])
    result = worker.collect_endpoints(sc, fetch_daily_raw_page=page, clock=lambda: next(times))
    assert result.callback_attempts == 1 and result.next_index == 0
    assert result.stop_reason == "clock_invalid" and not result.observations[0].rows
    result = worker.collect_endpoints(
        sc, fetch_daily_raw_page=page, clock=lambda: sc.session.close_at
    )
    assert result.observations[0].status == "available"


@pytest.mark.parametrize("reason", sorted(worker._YIELDS))
def test_shared_failure_yields_only_owned_batch(reason):
    sc = scope()

    def fetch(query):
        raise KisPaperMarketDataError(reason)

    result = collect(sc, fetch)
    assert result.callback_attempts == 1 and result.next_index == 0
    assert result.stop_reason == reason and result.observations[1].status == "not_attempted"


@pytest.mark.parametrize(
    "error",
    [RuntimeError(SECRET), worker.EndpointInputError(SECRET), KisPaperMarketDataError(SECRET)],
)
def test_arbitrary_callback_errors_never_leave_helper(error):
    sc = scope()

    def fetch(query):
        raise error

    result = collect(sc, fetch)
    assert result.stop_reason == "provider_unavailable" and result.callback_attempts == 1
    assert SECRET not in repr(result) + str(result.safe_facts())
    assert not result.observations[0].rows


@pytest.mark.parametrize(
    "rows,reason",
    [
        ((), "endpoint_missing"),
        ((row("20261009"),), "endpoint_missing"),
        ((row(), row()), "duplicate_date"),
        ((row(), row(opening="7.0020")), "duplicate_date"),
        ((row(), row("20261013")), "future_date"),
        ((row(), row("20260230")), "page_schema_invalid"),
    ],
)
def test_missing_duplicate_future_and_calendar_schema(rows, reason):
    result = collect(scope(), lambda query: page(query, rows))
    assert result.callback_attempts == 2 and result.next_index == 2
    assert all(o.status == "input_unavailable" and o.reason == reason for o in result.observations)
    if reason == "endpoint_missing":
        assert result.observations[0].rows == rows
        assert result.observations[0].canonical_rows_sha256 is not None
    else:
        assert not result.observations[0].rows


@pytest.mark.parametrize("change", ["symbol", "venue", "anchor", "continuation", "allowlist"])
def test_entire_page_identity_must_match(change):
    def fetch(query):
        if change == "symbol":
            other = replace(
                query, symbol="OTHER", approved_symbol_exchanges={"OTHER": frozenset({"NAS"})}
            )
        elif change == "venue":
            other = replace(
                query, exchange="AMS", approved_symbol_exchanges={query.symbol: frozenset({"AMS"})}
            )
        elif change == "anchor":
            other = replace(query, by_date="20261009")
        elif change == "continuation":
            other = replace(query, continuation="F")
        else:
            other = replace(query, approved_symbol_exchanges={query.symbol: frozenset({"NAS"})})
        return page(other)

    result = collect(scope(), fetch)
    assert all(o.reason == "page_identity_invalid" for o in result.observations)


@pytest.mark.parametrize("change", ["bounds", "fields", "nonfinite", "count"])
def test_rechecks_typed_dto_schema_including_mutation(change):
    def fetch(query):
        value = page(query)
        if change == "bounds":
            return page(query, newest_date="20261009")
        if change == "fields":
            return page(query, required_ohlcv_fields_present=False)
        if change == "nonfinite":
            object.__setattr__(value.rows[0], "open", "NaN")
        else:
            object.__setattr__(value.page, "row_count", True)
        return value

    result = collect(scope(), fetch)
    assert all(o.status == "input_unavailable" and not o.rows for o in result.observations)


def test_cursor_budget_and_missing_peer_are_not_replaced():
    sc = scope(3)
    result = collect(sc, start_index=1, max_attempts=1)
    assert result.callback_attempts == 1 and result.next_index == 2
    assert tuple(o.status for o in result.observations) == (
        "not_attempted",
        "available",
        "not_attempted",
    )
    assert tuple(o.key for o in result.observations) == tuple(p.key for p in sc.peers)
    assert collect(sc, start_index=3).callback_attempts == 0


@pytest.mark.parametrize(
    "kwargs",
    [{"start_index": -1}, {"start_index": True}, {"max_attempts": 43}, {"max_attempts": -1}],
)
def test_invalid_cursor_budget_before_callback(kwargs):
    with pytest.raises(worker.EndpointInputError):
        collect(scope(), **kwargs)


def test_peer_set_hash_order_duplicates_count_and_route():
    sc = scope()
    for peers in (tuple(reversed(sc.peers)), sc.peers[:1]):
        with pytest.raises(worker.EndpointInputError, match="peer_binding_invalid"):
            replace(sc, peers=peers)
    duplicate = (sc.peers[0], sc.peers[0])
    with pytest.raises(worker.EndpointInputError, match="peer_identity_conflict"):
        replace(sc, peers=duplicate, expected_peer_sha256=worker.peer_sha256(duplicate))
    with pytest.raises(worker.EndpointInputError, match="peer_count_invalid"):
        replace(sc, peers=())
    with pytest.raises(worker.EndpointInputError, match="peer_route_invalid"):
        worker.EndpointPeer("opaque", "OTHER", "NYS")
    with pytest.raises(worker.EndpointInputError, match="binding_invalid"):
        replace(sc, parent_seal_sha256=SECRET)


def test_official_session_and_past_cutoff_not_backdated():
    sc = scope()
    with pytest.raises(worker.EndpointInputError, match="session_invalid"):
        replace(sc, session=replace(sc.session, close_at=sc.session.close_at - timedelta(hours=1)))
    with pytest.raises(worker.EndpointInputError, match="past_cutoff_invalid"):
        replace(sc, past_cutoff=sc.session.open_at)


def test_pair_mask_preserves_all_eligible_peers_not_winners():
    entry_scope, exit_scope = scope(3), scope(3, date(2026, 10, 19))
    entry = collect(entry_scope)
    exit = collect(
        exit_scope, lambda query: page(query, ()) if query.symbol == "SB" else page(query)
    )
    mask = worker.pair_endpoint_mask(entry, exit)
    assert mask.keys == tuple(p.key for p in entry_scope.peers)
    assert mask.complete_by_peer == (True, False, True) and not mask.target_complete
    assert mask.safe_facts() == {
        "peer_count": 3,
        "complete_peer_count": 2,
        "target_complete": False,
        "returns_calculated": False,
    }
    assert worker.pair_endpoint_mask(entry, collect(exit_scope)).target_complete


def test_pair_substitution_and_swapped_identity_reject():
    entry, exit = collect(scope()), collect(scope(day=date(2026, 10, 19)))
    with pytest.raises(worker.EndpointInputError, match="pair_binding_invalid"):
        worker.pair_endpoint_mask(
            entry, replace(exit, scope=replace(exit.scope, parent_seal_sha256="sha256:" + "b" * 64))
        )
    with pytest.raises(worker.EndpointInputError, match="pair_binding_invalid"):
        worker.pair_endpoint_mask(
            entry, replace(exit, observations=tuple(reversed(exit.observations)))
        )
    with pytest.raises(worker.EndpointInputError, match="pair_binding_invalid"):
        worker.pair_endpoint_mask(entry, entry)


def test_exact_decimal_strings_safe_projection_and_hostile_context():
    sc = scope(1)
    with localcontext() as context:
        context.prec = 2
        context.traps[InvalidOperation] = True
        result = collect(sc)
    assert result.observations[0].endpoint_open == "7.0010"
    text = repr(result) + str(result.safe_facts()) + repr(result.observations[0])
    assert "opaque-" not in text and "7.0010" not in text and "7.200" not in text


def test_attempt_ceiling_42_with_extra_history_does_not_pace_or_paginate():
    peers = tuple(
        worker.EndpointPeer(f"opaque-{i}", "S" + chr(65 + i // 26) + chr(65 + i % 26), "NAS")
        for i in range(42)
    )
    sc = replace(scope(), peers=peers, expected_peer_sha256=worker.peer_sha256(peers))
    result = collect(sc)
    assert result.callback_attempts == 42 and result.safe_facts()["available_count"] == 42
    assert result.next_index == 42 and result.stop_reason is None
