"""Declared source-free operational inputs, not broker ownership or risk tests."""

from __future__ import annotations

import builtins
import json
import os
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, localcontext
from fractions import Fraction

import pytest

from thericher_v2.research import inventory_control_input as adapter

D = Decimal
NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)
REF = "sha256:" + "1" * 64
QUANTITY, RESERVED_CASH = D(1), D(100)


def target(weights=None):
    return adapter.DeclaredControlTarget(
        dict.fromkeys(adapter.SYMBOLS, D("0.3")) if weights is None else weights,
        D("0.1"),
        NOW - timedelta(minutes=2),
        REF,
    )


def positions():
    return [adapter.DeclaredPosition(s, D(0), D(0), NOW) for s in adapter.SYMBOLS]


def pending(
    *, status="retained", quantity=QUANTITY, cash=RESERVED_CASH, ref=REF, symbol="TLT", side="buy"
):
    return adapter.DeclaredPending(ref, symbol, side, quantity, cash, status, NOW)


def prepare(**changes):
    return adapter.prepare_inventory_control_input(
        **(
            dict(target=target(), positions=positions(), pending=[], basis_ref=REF, as_of=NOW)
            | changes
        )
    )


def test_declared_target_position_pending_api_no_decision_or_authority():
    result = prepare(pending=[pending()])
    assert tuple(result.target.weights_by_symbol) == adapter.SYMBOLS
    assert tuple(p.symbol for p in result.positions) == adapter.SYMBOLS
    assert result.pending[0].remaining_quantity == D(1)
    facts = result.safe_facts()
    assert facts["pending_count"] == 1 and facts["control"] == adapter.CONTROL
    assert not (
        {"safe_to_submit", "feasible", "target_quantities", "order", "capital"} & facts.keys()
    )
    assert "not_ownership_funding_or_execution_proof" in facts["scope"]


def test_caller_mutations_do_not_change_frozen_inputs():
    weights = dict.fromkeys(adapter.SYMBOLS, D("0.3"))
    declared = target(weights)
    book, retained = positions(), [pending()]
    result = prepare(target=declared, positions=book, pending=retained)
    weights["SPY"] = D(1)
    book.clear()
    retained.clear()
    assert result.target.weights_by_symbol["SPY"] == D("0.3")
    assert len(result.positions) == 3 and len(result.pending) == 1
    with pytest.raises(TypeError):
        result.target.weights_by_symbol["SPY"] = D(1)
    with pytest.raises(FrozenInstanceError):
        result.as_of = NOW + timedelta(days=1)


def test_existing_incumbent_quantities_not_replaced_by_target():
    book = positions()
    book[0] = replace(book[0], account_quantity=D(9), owned_quantity=D(9))
    result = prepare(positions=book)
    assert result.positions[0].owned_quantity == D(9)
    assert result.target.weights_by_symbol["SPY"] == D("0.3")


def test_missing_position_not_inferred_zero():
    with pytest.raises(adapter.InventoryControlInputError, match="position_scope_invalid"):
        prepare(positions=positions()[:2])


def test_explicit_unknown_position_preserved():
    book = positions()
    book[1] = replace(book[1], account_quantity=None, owned_quantity=None)
    result = prepare(positions=book)
    assert result.positions[1].account_quantity is None
    assert result.positions[1].owned_quantity is None
    assert result.safe_facts()["unknown_position_count"] == 1


def test_foreign_inventory_and_unmodelled_owned_instrument_not_adopted_or_dropped():
    book = positions()
    book[1] = replace(book[1], account_quantity=D(5), owned_quantity=D(0))
    book += [
        adapter.DeclaredPosition("AAPL", D(8), D(0), NOW),
        adapter.DeclaredPosition("QQQ", D(2), D(2), NOW),
    ]
    result = prepare(positions=tuple(reversed(book)))
    assert tuple(p.symbol for p in result.positions) == (*adapter.SYMBOLS, "AAPL", "QQQ")
    assert result.positions[1].owned_quantity == D(0)
    assert result.positions[-1].owned_quantity == D(2)
    assert result.safe_facts()["extra_instrument_count"] == 2
    assert result.safe_facts()["position_mismatch_count"] == 2


@pytest.mark.parametrize("status", ["submission_unknown", "cancellation_unknown"])
def test_unknown_pending_not_released_or_zeroed(status):
    retained = pending(status=status, quantity=None, cash=None)
    result = prepare(pending=[retained])
    assert result.pending == (retained,)
    assert result.pending[0].reserved_cash is None
    assert result.safe_facts()["unresolved_pending_count"] == 1


def test_zero_remaining_does_not_delete_pending_identity_or_reservation():
    retained = pending(quantity=D(0), cash=D(123), status="cancellation_unknown")
    result = prepare(pending=[retained])
    assert result.pending == (retained,) and result.pending[0].reserved_cash == D(123)
    assert result.safe_facts()["unresolved_pending_count"] == 1


def test_duplicate_pending_identity_not_double_counted():
    with pytest.raises(adapter.InventoryControlInputError, match="pending_identity_duplicate"):
        prepare(pending=[pending(), pending(symbol="GLD")])


def test_extra_pending_symbol_and_sell_descriptor_preserved():
    retained = pending(symbol="QQQ", side="sell", cash=D(0))
    result = prepare(pending=[retained])
    assert result.pending == (retained,)


def test_duplicate_position_rejected():
    book = positions()
    with pytest.raises(adapter.InventoryControlInputError, match="position_scope_invalid"):
        prepare(positions=book + [book[0]])


@pytest.mark.parametrize("value", [D(-1), D("-0"), D("NaN"), D("Infinity"), 1.0, True])
def test_private_bad_amount_errors_are_categorical(value):
    with pytest.raises(adapter.InventoryControlInputError, match="^amount_invalid$"):
        adapter.DeclaredPosition("SPY", value, D(0), NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("side", "unknown"),
        ("status", "filled"),
        ("source_ref", "private-order-id"),
        ("symbol", "bad private symbol"),
    ],
)
def test_pending_fields_validated_without_printing_input(field, value):
    with pytest.raises(adapter.InventoryControlInputError) as error:
        replace(pending(), **{field: value})
    assert value not in str(error.value)


def test_timezone_offsets_normalize_instant_and_naive_rejected():
    when = NOW.astimezone(timezone(timedelta(hours=9)))
    declared = replace(target(), as_of=when)
    assert declared.as_of == NOW and declared.as_of.utcoffset() == timedelta(0)
    book = [replace(p, observed_at=when) for p in positions()]
    result = prepare(
        target=declared, positions=book, pending=[replace(pending(), observed_at=when)], as_of=when
    )
    assert result.as_of.isoformat().endswith("+00:00")
    assert all(
        p.observed_at.isoformat().endswith("+00:00") for p in (*result.positions, *result.pending)
    )
    with pytest.raises(adapter.InventoryControlInputError, match="timestamp_invalid"):
        replace(target(), as_of=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("scope", ["target", "position", "pending"])
def test_future_input_never_silently_masked(scope):
    future = NOW + timedelta(seconds=1)
    changes = (
        dict(target=replace(target(), as_of=future))
        if scope == "target"
        else (
            dict(positions=[replace(p, observed_at=future) for p in positions()])
            if scope == "position"
            else dict(pending=[replace(pending(), observed_at=future)])
        )
    )
    with pytest.raises(adapter.InventoryControlInputError, match="future_input"):
        prepare(**changes)


def test_old_timestamps_retained_no_invented_freshness_gate():
    old = NOW - timedelta(days=500)
    result = prepare(
        target=replace(target(), as_of=old),
        positions=[replace(p, observed_at=old) for p in positions()],
    )
    assert result.target.as_of == old
    assert result.safe_facts()["target_as_of"] == old.isoformat()


@pytest.mark.parametrize(
    "weights,cash",
    [
        ({"SPY": D("0.3"), "TLT": D("0.3")}, D("0.4")),
        (dict.fromkeys(adapter.SYMBOLS, D("0.4")), D(0)),
        (dict.fromkeys(adapter.SYMBOLS, D("0.3")), D("0.2")),
    ],
)
def test_bad_target_scope_or_exact_sum_rejected(weights, cash):
    with pytest.raises(adapter.InventoryControlInputError):
        adapter.DeclaredControlTarget(weights, cash, NOW, REF)


def test_target_fraction_sum_independent_of_ambient_decimal_precision():
    w = D("0.12345678901234567890123456789012345678901234567890")
    with localcontext() as context:
        context.prec = 100
        cash = 1 - 3 * w
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        result = adapter.DeclaredControlTarget(dict.fromkeys(adapter.SYMBOLS, w), cash, NOW, REF)
    assert sum(map(Fraction, result.weights_by_symbol.values())) + Fraction(result.cash_weight) == 1


def test_public_facts_and_repr_hide_numeric_inputs_references():
    secret_quantity = D("918273.645")
    book = [
        replace(p, account_quantity=secret_quantity, owned_quantity=secret_quantity)
        for p in positions()
    ]
    result = prepare(positions=book, pending=[pending(cash=secret_quantity)])
    public = json.dumps(result.safe_facts(), sort_keys=True)
    representations = repr(result) + repr(result.target) + repr(result.pending[0])
    assert str(secret_quantity) not in public + representations
    assert REF not in public + representations
    assert "weights_by_symbol" not in representations


def test_repeated_preparation_is_exact_and_does_not_touch_sources_env_or_network(monkeypatch):
    arguments = dict(
        target=target(), positions=positions(), pending=[pending()], basis_ref=REF, as_of=NOW
    )

    def forbidden(*a, **k):
        pytest.fail("adapter performed source/credential/network access")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    before = adapter.prepare_inventory_control_input(**arguments)
    after = adapter.prepare_inventory_control_input(**arguments)
    assert before == after and before.safe_facts() == after.safe_facts()


def test_direct_constructor_revalidates_nested_objects():
    bad = replace(target())
    object.__setattr__(bad, "cash_weight", D("0.2"))
    with pytest.raises(adapter.InventoryControlInputError, match="target_sum_invalid"):
        prepare(target=bad)
    bad_pending = pending()
    object.__setattr__(bad_pending, "remaining_quantity", D(-1))
    with pytest.raises(adapter.InventoryControlInputError, match="amount_invalid"):
        prepare(pending=[bad_pending])
