"""Declared inventory inputs for the existing fixed capped-thirds control.

Caller supplies the already-built target and independently parsed custody. This
adapter neither creates that control nor proves ownership, freshness, funding,
pending resolution or execution eligibility. Unknowns are never replaced by zero.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType

from thericher_v2.contracts import require_utc

SYMBOLS = ("SPY", "TLT", "GLD")
CONTROL = "fixed_capped_thirds_engineering_control"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,14}")


class InventoryControlInputError(ValueError):
    """Categorical local contract error, never a private value or global hold."""


def _check(condition, reason):
    if not condition:
        raise InventoryControlInputError(reason)


def _time(value):
    _check(type(value) is datetime, "timestamp_invalid")
    try:
        return require_utc(value)
    except (ValueError, TypeError, AttributeError):
        raise InventoryControlInputError("timestamp_invalid") from None


def _amount(value, *, unknown=False):
    if value is None and unknown:
        return
    _check(type(value) is Decimal and value.is_finite() and not value.is_signed(), "amount_invalid")


def _ref(value):
    _check(type(value) is str and _HASH.fullmatch(value) is not None, "reference_invalid")


def _symbol(value):
    _check(type(value) is str and _SYMBOL.fullmatch(value) is not None, "symbol_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class DeclaredControlTarget:
    weights_by_symbol: Mapping[str, Decimal] = field(repr=False)
    cash_weight: Decimal = field(repr=False)
    as_of: datetime
    source_ref: str = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "as_of", _time(self.as_of))
        _ref(self.source_ref)
        _check(
            isinstance(self.weights_by_symbol, Mapping)
            and set(self.weights_by_symbol) == set(SYMBOLS),
            "target_scope_invalid",
        )
        copied = {s: self.weights_by_symbol[s] for s in SYMBOLS}
        for value in (*copied.values(), self.cash_weight):
            _amount(value)
            _check(value <= 1, "target_weight_invalid")
        _check(
            sum(map(Fraction, copied.values()), Fraction(0)) + Fraction(self.cash_weight) == 1,
            "target_sum_invalid",
        )
        object.__setattr__(self, "weights_by_symbol", MappingProxyType(copied))


@dataclass(frozen=True, slots=True, repr=False)
class DeclaredPosition:
    symbol: str
    account_quantity: Decimal | None = field(repr=False)
    owned_quantity: Decimal | None = field(repr=False)
    observed_at: datetime

    def __post_init__(self):
        _symbol(self.symbol)
        _amount(self.account_quantity, unknown=True)
        _amount(self.owned_quantity, unknown=True)
        object.__setattr__(self, "observed_at", _time(self.observed_at))


@dataclass(frozen=True, slots=True, repr=False)
class DeclaredPending:
    source_ref: str = field(repr=False)
    symbol: str
    side: str
    remaining_quantity: Decimal | None = field(repr=False)
    reserved_cash: Decimal | None = field(repr=False)
    status: str
    observed_at: datetime

    def __post_init__(self):
        _ref(self.source_ref)
        _symbol(self.symbol)
        _check(type(self.side) is str and self.side in {"buy", "sell"}, "pending_side_invalid")
        _amount(self.remaining_quantity, unknown=True)
        _amount(self.reserved_cash, unknown=True)
        _check(
            type(self.status) is str
            and self.status in {"retained", "submission_unknown", "cancellation_unknown"},
            "pending_status_invalid",
        )
        object.__setattr__(self, "observed_at", _time(self.observed_at))


@dataclass(frozen=True, slots=True, repr=False)
class InventoryControlInput:
    target: DeclaredControlTarget = field(repr=False)
    positions: tuple[DeclaredPosition, ...] = field(repr=False)
    pending: tuple[DeclaredPending, ...] = field(repr=False)
    basis_ref: str = field(repr=False)
    as_of: datetime

    def __post_init__(self):
        at = _time(self.as_of)
        object.__setattr__(self, "as_of", at)
        _ref(self.basis_ref)
        _check(type(self.target) is DeclaredControlTarget, "target_invalid")
        target = replace(self.target)
        _check(
            type(self.positions) is tuple and type(self.pending) is tuple, "descriptors_not_frozen"
        )
        _check(
            all(type(p) is DeclaredPosition for p in self.positions)
            and all(type(p) is DeclaredPending for p in self.pending),
            "descriptor_invalid",
        )
        positions = tuple(replace(p) for p in self.positions)
        pending = tuple(replace(p) for p in self.pending)
        names = tuple(p.symbol for p in positions)
        _check(
            len(set(names)) == len(names) and set(SYMBOLS) <= set(names), "position_scope_invalid"
        )
        _check(len({p.source_ref for p in pending}) == len(pending), "pending_identity_duplicate")
        _check(
            target.as_of <= at and all(p.observed_at <= at for p in (*positions, *pending)),
            "future_input",
        )
        # Extra/foreign instruments stay visible; no broker row becomes an owned holding.
        book = {p.symbol: p for p in positions}
        order = SYMBOLS + tuple(sorted(set(names) - set(SYMBOLS)))
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "positions", tuple(book[s] for s in order))
        object.__setattr__(self, "pending", pending)

    def safe_facts(self):
        return dict(
            kind="inventory_control_input_v1",
            control=CONTROL,
            as_of=self.as_of.isoformat(),
            target_as_of=self.target.as_of.isoformat(),
            target_instrument_count=3,
            position_count=len(self.positions),
            extra_instrument_count=sum(p.symbol not in SYMBOLS for p in self.positions),
            unknown_position_count=sum(
                p.account_quantity is None or p.owned_quantity is None for p in self.positions
            ),
            position_mismatch_count=sum(
                p.account_quantity is not None
                and p.owned_quantity is not None
                and p.account_quantity != p.owned_quantity
                for p in self.positions
            ),
            pending_count=len(self.pending),
            unresolved_pending_count=sum(
                p.status != "retained" or p.remaining_quantity is None or p.reserved_cash is None
                for p in self.pending
            ),
            scope="declared_input_only_not_ownership_funding_or_execution_proof",
        )


def prepare_inventory_control_input(*, target, positions, pending, basis_ref, as_of):
    """Freeze caller inputs, preserving every pending descriptor and extra instrument.

    Missing SPY/TLT/GLD rows are not flat positions. A caller can explicitly
    supply unknown quantities, which remain unknown in the returned packet.
    There is no share rounding, covariance fit, cash netting or policy decision.
    """
    _check(
        isinstance(positions, (tuple, list)) and isinstance(pending, (tuple, list)),
        "descriptor_sequence_invalid",
    )
    return InventoryControlInput(target, tuple(positions), tuple(pending), basis_ref, as_of)
