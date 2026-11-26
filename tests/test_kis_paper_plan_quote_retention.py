import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)

NOW = datetime(2026, 11, 26, 15, tzinfo=UTC)


@pytest.fixture
def intent():
    return canary.KisPaperCanaryIntent(
        "invented", "invented-order", "invented-decision", "SPY", "NASD",
        Decimal("2"), Decimal("100"), NOW, NOW + timedelta(minutes=3), side="sell",
    )


@pytest.fixture
def quote():
    return canary.KisPaperCanaryPlanQuote(
        NOW - timedelta(seconds=1), Decimal("99.12"), Decimal("100.34"),
    )


def test_absent_quote_keeps_prior_format_and_existing_bytes(tmp_path, intent, quote):
    path = tmp_path / "state.json"
    store = canary.KisPaperCanaryStateStore(path)
    expected = {
        "schema_version": intent.schema_version,
        "kind": "kis_paper_canary_state",
        "intent": intent.to_dict(),
        "intent_fingerprint": intent.fingerprint,
        "phase": "intent_recorded",
        "updated_at": NOW.isoformat(),
        "reason_code": "preview",
        "broker_order_id": None,
        "submitted_at": None,
        "submission_started_at": None,
        "cancel_after_submit": False,
        "submit_upstream_code": None,
        "submit_response_category": None,
        "cumulative_fill": None,
        "fill_observation_status": "not_observed",
        "fill_observed_at": None,
    }
    first = store.record_intent(intent, now=NOW, cancel_after_submit=False)
    assert first.to_dict() == expected
    assert path.read_bytes() == json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()

    legacy = {key: expected[key] for key in (
        "schema_version", "kind", "intent", "intent_fingerprint", "phase", "updated_at",
        "reason_code", "broker_order_id",
    )}
    original = json.dumps(legacy, indent=2).encode()
    path.write_bytes(original)
    assert store.read() == first
    assert store.record_intent(intent, now=NOW, cancel_after_submit=True, plan_quote=quote) == first
    assert path.read_bytes() == original


def test_first_quote_wins_and_existing_state_needs_no_quote_equality(tmp_path, intent, quote):
    path = tmp_path / "state.json"
    store = canary.KisPaperCanaryStateStore(path)
    different = canary.KisPaperCanaryPlanQuote(NOW, Decimal("101"), Decimal("101"))
    first = store.record_intent(intent, now=NOW, cancel_after_submit=False, plan_quote=quote)
    raw = path.read_bytes()

    assert json.loads(raw)["plan_quote"] == quote.to_dict()
    assert canary.KisPaperCanaryStateStore(path).read() == first
    for requested in (None, different):
        assert store.record_intent(
            intent, now=NOW, cancel_after_submit=False, plan_quote=requested,
        ) == first
    assert path.read_bytes() == raw
    assert "99.12" not in repr(quote)
    assert "100.34" not in repr(first)


def test_quote_is_in_first_atomic_write_not_a_second_write(tmp_path, intent, quote, monkeypatch):
    path = tmp_path / "state.json"
    store = canary.KisPaperCanaryStateStore(path)
    original = canary.os.replace

    def interrupt(source, destination):
        assert destination == path and not path.exists()
        assert json.loads(Path(source).read_bytes())["plan_quote"] == quote.to_dict()
        raise OSError("invented atomic replace failure")

    with monkeypatch.context() as patch:
        patch.setattr(canary.os, "replace", interrupt)
        with pytest.raises(OSError, match="invented atomic replace failure"):
            store.record_intent(intent, now=NOW, cancel_after_submit=False, plan_quote=quote)
    assert canary.os.replace is original
    assert not path.exists() and not list(tmp_path.glob("*.tmp"))
    assert store.record_intent(
        intent, now=NOW, cancel_after_submit=False, plan_quote=quote,
    ).plan_quote == quote


def test_quote_survives_replay_submit_fill_and_later_transition(tmp_path, intent, quote):
    path = tmp_path / "state.json"
    store = canary.KisPaperCanaryStateStore(path)
    first = store.record_intent(intent, now=NOW, cancel_after_submit=False, plan_quote=quote)
    store = canary.KisPaperCanaryStateStore(path)
    submit_at = NOW + timedelta(seconds=1)
    started = store.transition(
        intent, expected=frozenset({"intent_recorded"}), phase="submission_started",
        reason_code="preview", now=submit_at, submission_started_at=submit_at,
    )
    submitted = store.transition(
        intent, expected=frozenset({"submission_started"}), phase="submitted",
        reason_code="reconciliation_unresolved", now=submit_at,
        broker_order_id="ORD-123456789", submitted_at=submit_at,
    )
    observed_at = submit_at + timedelta(seconds=1)
    fill = KisPaperCumulativeFill(
        identity_ref=fill_identity_ref(
            raw_order_id="ORD-123456789", order_at=submit_at, symbol=intent.symbol,
            exchange=intent.exchange, side=intent.side, quantity=intent.quantity,
        ),
        requested_quantity=intent.quantity, quantity=Decimal("1"),
        gross_amount=Decimal("101"), observed_at=observed_at, remaining_quantity=Decimal("1"),
    )
    observed = store.record_fill_observation(
        intent,
        KisPaperExecutionObservation(1, True, "available", fill=fill, observed_at=observed_at),
        now=observed_at,
    )
    later = store.transition(
        intent, expected=frozenset({"submitted"}), phase="cancel_started",
        reason_code="reconciliation_unresolved", now=observed_at + timedelta(seconds=1),
    )
    assert store.read() == later
    assert later.current_fill == fill
    for state in (first, started, submitted, observed, later):
        assert state.plan_quote == quote
        assert state.intent.fingerprint == intent.fingerprint
        assert canary.KisPaperCanaryState.from_dict(state.to_dict()) == state


@pytest.mark.parametrize(
    "edit",
    [
        None,
        {"best_bid": 100},
        {"best_bid": "0"},
        {"best_bid": "NaN"},
        {"best_ask": "Infinity"},
        {"best_ask": "98"},
        {"best_bid": "-1"},
        {"best_bid": None},
        {"extra": "not-allowed"},
        {"quoted_at": "2026-11-26T15:00:00"},
        {"quoted_at": "2026-11-26T14:00:00-01:00"},
        {"quoted_at": "2026-11-26T15:00:01+00:00"},
    ],
)
def test_corrupt_measurement_does_not_change_decoded_order(intent, quote, edit):
    state = canary.KisPaperCanaryState(intent, "intent_recorded", NOW, "preview")
    raw = state.to_dict() | {"plan_quote": None if edit is None else quote.to_dict() | edit}
    assert canary.KisPaperCanaryState.from_dict(raw) == state


def test_store_keeps_strict_json_but_reconciles_malformed_measurement(tmp_path, intent, quote):
    path = tmp_path / "state.json"
    store = canary.KisPaperCanaryStateStore(path)
    state = store.record_intent(intent, now=NOW, cancel_after_submit=False, plan_quote=quote)
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"best_bid":"99.12"', '"best_bid":"99.12","best_bid":"99.12"'),
                    encoding="utf-8")
    with pytest.raises(canary.KisPaperCanaryError, match="state_invalid"):
        store.read()
    path.write_text(
        json.dumps(state.to_dict() | {
            "plan_quote": {"quoted_at": NOW.isoformat(), "best_bid": "1"},
        }),
        encoding="utf-8",
    )
    before = path.read_bytes()
    assert store.read() == replace(state, plan_quote=None)
    assert path.read_bytes() == before
    started = store.transition(
        intent, expected=frozenset({"intent_recorded"}), phase="submission_started",
        reason_code="preview", now=NOW, submission_started_at=NOW,
    )
    assert store.read() == started
    assert "plan_quote" not in started.to_dict()


def test_typed_quote_and_first_write_validate_before_persistence(tmp_path, intent):
    offset = timezone(timedelta(hours=1))
    with pytest.raises(ValueError, match="quote time"):
        canary.KisPaperCanaryPlanQuote(NOW.astimezone(offset), Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError, match="quote prices"):
        canary.KisPaperCanaryPlanQuote(NOW, Decimal("sNaN"), Decimal("1"))
    with pytest.raises(ValueError, match="quote prices"):
        canary.KisPaperCanaryPlanQuote(NOW, 1, Decimal("1"))
    future = canary.KisPaperCanaryPlanQuote(
        NOW + timedelta(seconds=1), Decimal("1"), Decimal("1"),
    )
    path = tmp_path / "state.json"
    with pytest.raises(ValueError, match="quote binding"):
        canary.KisPaperCanaryStateStore(path).record_intent(
            intent, now=NOW, cancel_after_submit=False, plan_quote=future,
        )
    assert not path.exists()
