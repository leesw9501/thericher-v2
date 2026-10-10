"""Synthetic byte custody and resume tests; no files, provider or credentials."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from thericher_v2.data import kis_stock_shadow_endpoint as endpoint
from thericher_v2.data import kis_stock_shadow_endpoint_storage as storage
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyPage,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
)
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

PIN = "sha256:" + "a" * 64
SECRET = "fake_secret_that_must_not_escape"


def binding(leg="entry", count=3):
    day = storage.LEG_DATES[leg]
    session = us_equity_2026_session(day)
    peers = tuple(
        endpoint.EndpointPeer(f"opaque-{i}", "S" + chr(65 + i), "NAS") for i in range(count)
    )
    scope = endpoint.EndpointScope(
        peers,
        endpoint.peer_sha256(peers),
        PIN,
        CrossAssetSession(day, session.window.open_ts, session.window.close_ts),
        datetime(2026, 10, 9, 20, tzinfo=UTC),
    )
    return storage.StorageBinding(
        scope,
        leg,
        PIN,
        (
            ("endpoint_worker.py", storage.ENDPOINT_WORKER_SHA256),
            ("native/kis_market_data.py", PIN),
        ),
    )


def page(query, *, missing=False):
    day = "20261009" if missing else query.by_date
    rows = (KisPaperDailyRawRow(day, "7.0010", "8.00", "6.0", "7.200", "100.00"),)
    return KisPaperDailyRawPage(KisPaperDailyPage(query, 1, day, day, True, True, "F"), rows)


def attempt(
    bind,
    *,
    start=0,
    budget=None,
    fail_index=None,
    reason="rate_limited",
    missing=None,
    seconds=5,
    invocation="1" * 32,
):
    pages = {}

    def fetch(query):
        i = next(i for i, p in enumerate(bind.scope.peers) if p.symbol == query.symbol)
        if i == fail_index:
            raise KisPaperMarketDataError(reason)
        pages[i] = page(query, missing=i == missing)
        return pages[i]

    now = bind.scope.session.close_at + timedelta(seconds=seconds)
    batch = endpoint.collect_endpoints(
        bind.scope,
        fetch_daily_raw_page=fetch,
        clock=lambda: now,
        start_index=start,
        max_attempts=budget,
    )
    stored = storage.dump_batch(
        bind,
        batch,
        pages_by_index=pages,
        invocation_id=invocation,
        start_index=start,
        completed_at=now,
    )
    return batch, pages, stored


def load(bind, stored):
    return storage.load_batch(bind, stored, receipt_sha256=stored.receipt_sha256)


def encode(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def change_receipt(stored, mutate):
    doc = json.loads(stored.receipt)
    mutate(doc)
    return replace(stored, receipt=encode(doc))


def change_page(stored, mutate, *, payload=False):
    blob = stored.pages[0]
    if payload:
        rows = json.loads(blob.payload)
        mutate(rows)
        blob = replace(blob, payload=encode(rows))
    else:
        doc = json.loads(blob.receipt)
        mutate(doc)
        blob = replace(blob, receipt=encode(doc))
    return replace(stored, pages=(blob,) + stored.pages[1:])


def relink_first_page(stored):
    """Give malformed bytes fresh pins to test parsing, not just hash rejection."""
    blob = stored.pages[0]
    page_doc = json.loads(blob.receipt)
    page_doc["payload_sha256"] = storage.sha256(blob.payload)
    page_doc["metadata"]["row_count"] = len(json.loads(blob.payload))
    blob = replace(blob, receipt=encode(page_doc))
    doc = json.loads(stored.receipt)
    doc["observations"][0]["payload_sha256"] = storage.sha256(blob.payload)
    doc["observations"][0]["page_receipt_sha256"] = storage.sha256(blob.receipt)
    return replace(stored, receipt=encode(doc), pages=(blob,) + stored.pages[1:])


@pytest.mark.parametrize("leg", ["entry", "exit"])
def test_exact_byte_roundtrip_and_metadata_separate_from_payload(leg):
    bind = binding(leg)
    batch, _, stored = attempt(bind, missing=1)
    read = load(bind, stored)
    assert read.observations == batch.observations and read.next_index == 3
    assert read.safe_facts()["available_count"] == 2 and not read.safe_facts()["endpoint_complete"]
    assert read.observations[1].reason == "endpoint_missing"
    assert len(read.observations) == len(bind.scope.peers)
    assert b"7.0010" not in stored.receipt
    assert all(b"7.0010" not in p.receipt and b"7.0010" in p.payload for p in stored.pages)
    assert "opaque-" not in repr(read) + str(read.safe_facts())
    assert b"7.0010" not in repr(stored).encode()


@pytest.mark.parametrize(
    "field,value",
    [
        ("endpoint_open", "7.001"),
        ("canonical_rows_sha256", PIN),
        ("status", "ready"),
        ("reason", SECRET),
        ("rows", ()),
        ("observed_at", None),
        ("request_entered_at", datetime(2026, 10, 12, 19, tzinfo=UTC)),
    ],
)
def test_forged_observation_rejected_before_serialization(field, value):
    bind = binding()
    batch, pages, _ = attempt(bind)
    fake = replace(batch.observations[0], **{field: value})
    batch = replace(batch, observations=(fake,) + batch.observations[1:])
    with pytest.raises(storage.StorageError) as error:
        storage.dump_batch(
            bind,
            batch,
            pages_by_index=pages,
            invocation_id="2" * 32,
            start_index=0,
            completed_at=bind.scope.session.close_at + timedelta(seconds=5),
        )
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("change", ["count", "cursor", "key", "order", "status", "gap"])
def test_forged_batch_and_noncontiguous_prefix_reject(change):
    bind = binding()
    batch, pages, _ = attempt(bind)
    if change == "count":
        fake = replace(batch, callback_attempts=True)
    elif change == "cursor":
        fake = replace(batch, next_index=2)
    elif change == "key":
        fake = replace(
            batch,
            observations=(replace(batch.observations[0], key="foreign"),) + batch.observations[1:],
        )
    elif change == "order":
        fake = replace(batch, observations=tuple(reversed(batch.observations)))
    elif change == "status":
        fake = replace(batch, stop_reason=SECRET)
    else:
        fake = replace(
            batch,
            observations=(
                endpoint.EndpointObservation(
                    bind.scope.peers[0].key, "not_attempted", None, None, None
                ),
            )
            + batch.observations[1:],
        )
    with pytest.raises(storage.StorageError):
        storage.dump_batch(
            bind,
            fake,
            pages_by_index=pages,
            invocation_id="2" * 32,
            start_index=0,
            completed_at=bind.scope.session.close_at + timedelta(seconds=5),
        )


@pytest.mark.parametrize("change", ["parent", "source", "pin", "leg", "scope", "duplicates"])
def test_exact_parent_source_leg_and_pin_bindings(change):
    bind = binding()
    _, _, stored = attempt(bind)
    if change == "parent":
        bad = replace(bind, scope=replace(bind.scope, parent_seal_sha256="sha256:" + "b" * 64))
    elif change == "source":
        bad = replace(bind, source_contract_sha256="sha256:" + "b" * 64)
    elif change == "pin":
        bad = replace(bind, source_pins=(("endpoint_worker.py", PIN),))
    elif change == "leg":
        bad = replace(bind, leg="exit")
    elif change == "scope":
        session = us_equity_2026_session(date(2026, 10, 13))
        bad = replace(
            bind,
            scope=replace(
                bind.scope,
                session=CrossAssetSession(
                    date(2026, 10, 13), session.window.open_ts, session.window.close_ts
                ),
            ),
        )
    else:
        bad = replace(bind, source_pins=bind.source_pins + (bind.source_pins[0],))
    with pytest.raises(storage.StorageError):
        load(bad, stored)


def test_arbitrary_later_exit_and_past_cutoff_reject():
    bind = binding("exit")
    session = us_equity_2026_session(date(2026, 10, 20))
    wrong = replace(
        bind,
        scope=replace(
            bind.scope,
            session=CrossAssetSession(
                date(2026, 10, 20), session.window.open_ts, session.window.close_ts
            ),
        ),
    )
    with pytest.raises(storage.StorageError, match="binding_invalid"):
        wrong.record()
    with pytest.raises(storage.StorageError, match="binding_invalid"):
        replace(
            bind, scope=replace(bind.scope, past_cutoff=datetime(2026, 10, 12, 15, tzinfo=UTC))
        ).record()


def test_query_hash_and_missing_or_extra_page_are_rejected():
    bind = binding()
    _, _, stored = attempt(bind)
    with pytest.raises(storage.StorageError, match="receipt_hash_mismatch"):
        storage.load_batch(bind, stored, receipt_sha256=PIN)
    wrong_query = change_page(stored, lambda d: d["query"].update(BYMD="20261019"))
    with pytest.raises(storage.StorageError):
        load(bind, wrong_query)
    for bad in (
        replace(stored, pages=stored.pages[1:]),
        replace(stored, pages=stored.pages + (stored.pages[0],)),
        replace(stored, pages=tuple(reversed(stored.pages))),
    ):
        with pytest.raises(storage.StorageError):
            load(bind, bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "foreign"),
        ("version", 2),
        ("next_index", 1),
        ("callback_attempts", 1),
        ("start_index", 1),
        ("stop_reason", SECRET),
    ],
)
def test_checkpoint_schema_mutations_even_with_new_hash_reject(field, value):
    bind = binding()
    _, _, stored = attempt(bind)
    bad = change_receipt(stored, lambda d: d.update({field: value}))
    with pytest.raises(storage.StorageError) as error:
        load(bind, bad)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[0].update(open="NaN"),
        lambda rows: rows[0].update(xymd="20261013"),
        lambda rows: rows.append(rows[0]),
        lambda rows: rows[0].update(secret=SECRET),
        lambda rows: rows[0].update(open="7.0010 "),
    ],
)
def test_payload_schema_tampering_rejects(mutate):
    bind = binding()
    _, _, stored = attempt(bind)
    with pytest.raises(storage.StorageError):
        load(bind, change_page(stored, mutate, payload=True))
    with pytest.raises(storage.StorageError):
        load(bind, relink_first_page(change_page(stored, mutate, payload=True)))


@pytest.mark.parametrize("field,value", [("kind", "other"), ("version", 9), ("foreign", SECRET)])
def test_rehashed_page_receipt_schema_is_exact(field, value):
    bind = binding()
    _, _, stored = attempt(bind)
    bad = relink_first_page(change_page(stored, lambda d: d.update({field: value})))
    with pytest.raises(storage.StorageError) as error:
        load(bind, bad)
    assert SECRET not in str(error.value)


def test_wrong_native_page_before_dump_and_future_clock_reject():
    bind = binding()
    batch, pages, _ = attempt(bind)
    pages[0] = replace(
        pages[0],
        page=replace(pages[0].page, query=replace(pages[0].page.query, by_date="20261019")),
    )
    with pytest.raises(storage.StorageError, match="page_invalid"):
        storage.dump_batch(
            bind,
            batch,
            pages_by_index=pages,
            invocation_id="2" * 32,
            start_index=0,
            completed_at=bind.scope.session.close_at + timedelta(seconds=5),
        )
    _, pages, _ = attempt(bind)
    with pytest.raises(storage.StorageError, match="clock_invalid"):
        storage.dump_batch(
            bind,
            batch,
            pages_by_index=pages,
            invocation_id="2" * 32,
            start_index=0,
            completed_at=bind.scope.session.close_at + timedelta(seconds=4),
        )


def test_strict_nested_duplicate_keys_noncanonical_and_nonfinite_json():
    bind = binding()
    _, _, stored = attempt(bind)
    for raw in (
        b'{"kind":"a","kind":"b"}',
        b'{"nested":{"msg1":"\\u0066ake_secret","msg1":"okay"}}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b" {}",
        b"null",
        b'"' + SECRET.encode() + b'"',
    ):
        with pytest.raises(storage.StorageError) as error:
            load(bind, replace(stored, receipt=raw))
        assert SECRET not in str(error.value)


@pytest.mark.parametrize("reason", sorted(storage._RETRY))
def test_yield_same_cursor_resume_preserves_immutable_prefix_and_failed_attempt(reason):
    bind = binding()
    before, _, first = attempt(bind, fail_index=1, reason=reason)
    if reason == "clock_invalid":
        # The endpoint helper categorizes this unknown provider error as provider_unavailable.
        assert before.stop_reason == "provider_unavailable"
    _, _, second = attempt(bind, start=1, seconds=6, invocation="2" * 32)
    original = first.receipt, first.pages
    read = storage.load_resume(
        bind, (first, second), receipt_sha256s=(first.receipt_sha256, second.receipt_sha256)
    )
    assert read.observations[0] == before.observations[0] and read.next_index == 3
    assert all(o.status == "available" for o in read.observations)
    assert (
        read.attempts[0] == before
        and read.attempts[0].observations[1].status == "input_unavailable"
    )
    assert read.safe_facts()["callback_attempts"] == 4
    assert original == (first.receipt, first.pages)


def test_budget_prefix_resume_and_missing_are_not_replaced():
    bind = binding()
    before, _, first = attempt(bind, budget=2, missing=0)
    _, _, second = attempt(bind, start=2, seconds=6, invocation="2" * 32)
    read = storage.load_resume(
        bind, (first, second), receipt_sha256s=(first.receipt_sha256, second.receipt_sha256)
    )
    assert read.observations[:2] == before.observations[:2]
    assert read.observations[0].reason == "endpoint_missing"
    assert not read.safe_facts()["endpoint_complete"] and len(read.observations) == 3


@pytest.mark.parametrize("change", ["skip", "replace", "same_id", "old_clock", "missing_prefix"])
def test_resume_does_not_skip_or_replace_prefix_or_replay_attempt(change):
    bind = binding()
    _, _, first = attempt(bind, budget=1)
    start = 2 if change == "skip" else 0 if change == "replace" else 1
    _, _, second = attempt(
        bind,
        start=start,
        seconds=4 if change == "old_clock" else 6,
        invocation="1" * 32 if change == "same_id" else "2" * 32,
    )
    checkpoints = (second,) if change == "missing_prefix" else (first, second)
    with pytest.raises(storage.StorageError):
        storage.load_resume(
            bind, checkpoints, receipt_sha256s=tuple(c.receipt_sha256 for c in checkpoints)
        )


def test_no_call_preclose_checkpoint_and_separate_pair_missingness():
    bind = binding()
    now = bind.scope.session.close_at - timedelta(seconds=1)
    batch = endpoint.collect_endpoints(
        bind.scope, fetch_daily_raw_page=lambda q: pytest.fail("call"), clock=lambda: now
    )
    stored = storage.dump_batch(
        bind, batch, pages_by_index={}, invocation_id="1" * 32, start_index=0, completed_at=now
    )
    read = load(bind, stored)
    assert read.safe_facts()["callback_attempts"] == 0 and read.next_index == 0
    assert read.safe_facts()["not_attempted_count"] == 3
    assert not read.safe_facts()["endpoint_complete"]
    exit_binding = binding("exit")
    _, _, exit_stored = attempt(exit_binding)
    with pytest.raises(storage.StorageError):
        load(bind, exit_stored)


def test_schema_version_and_forged_not_attempted_observation():
    bind = binding()
    batch, pages, _ = attempt(bind, budget=1)
    for schema in (True, 99):
        bad_pages = {0: replace(pages[0], page=replace(pages[0].page, schema_version=schema))}
        with pytest.raises(storage.StorageError, match="page_invalid"):
            storage.dump_batch(
                bind,
                batch,
                pages_by_index=bad_pages,
                invocation_id="2" * 32,
                start_index=0,
                completed_at=bind.scope.session.close_at + timedelta(seconds=5),
            )
    forged = replace(batch.observations[2], endpoint_open="7.0010")
    with pytest.raises(storage.StorageError, match="prefix_invalid"):
        storage.dump_batch(
            bind,
            replace(batch, observations=batch.observations[:2] + (forged,)),
            pages_by_index=pages,
            invocation_id="2" * 32,
            start_index=0,
            completed_at=bind.scope.session.close_at + timedelta(seconds=5),
        )
