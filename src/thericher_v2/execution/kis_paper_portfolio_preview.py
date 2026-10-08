"""Transient portfolio sizing evidence, never an intent or execution permission.

Caller owns strict JSON decoding, private namespace custody and causal target/
covariance construction. Frozen funding is not refreshed from broker cash.
Risk uses provisional sleeve NAV = replayed gross cash + all owned marks;
fees, settlement and dividend cash are unknown, not fabricated account equity.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException, localcontext
from fractions import Fraction

from thericher_v2.contracts import require_utc

from .kis_paper_budget_strategy import (
    _QQQ_RUN_ID,
    _RUN_ID,
    _V2_KEYS,
    _V3_KEYS,
    _basis,
    _owners,
    _portfolio_seed_states,
    _retained_terminal,
    _terminal,
    _validate_orders,
)
from .kis_paper_canary import KisPaperCanaryError, KisPaperCanaryState
from .kis_paper_portfolio_budget import project_kis_paper_portfolio_budget
from .kis_paper_quote import (
    KIS_PAPER_PREVIEW_VENUES,
    KisPaperQuoteError,
    derive_kis_paper_marketable_limit,
)
from .kis_paper_spy_fill_cycle import _RecoveryRequired
from .kis_readonly import KisPaperPortfolioPreviewReads

SYMBOLS = tuple(KIS_PAPER_PREVIEW_VENUES)
ANNUAL_RISK_CAP = Decimal("0.10")


@dataclass(frozen=True, repr=False)
class KisPaperPortfolioPreview:
    status: str
    reason: str
    historical_order_count: int | None = None
    pending_count: int | None = None
    proposed_buy_leg_count: int | None = None
    target_quantities: tuple[Decimal, ...] | None = None
    additional_quantities: tuple[Decimal, ...] | None = None
    buy_notionals: tuple[Decimal, ...] | None = None
    incumbent_spy_quantity: Decimal | None = None
    shared_entry_cost: Decimal | None = None
    shared_reservations: Decimal | None = None
    proposed_reservation: Decimal | None = None
    provisional_risk_nav: Decimal | None = None
    rounded_annual_risk: Decimal | None = None

    def safe_payload(self) -> dict[str, object]:
        payload = {
            "kind": "kis_paper_portfolio_preview_v1",
            "status": self.status,
            "reason": self.reason,
            "instrument_count": 3,
            "new_submits": 0,
            "limitation": "provisional_gross_basis_risk_not_settled_cash_or_execution_permission",
        }
        payload.update(
            {
                key: value
                for key, value in (
                    ("historical_order_count", self.historical_order_count),
                    ("pending_count", self.pending_count),
                    ("proposed_buy_leg_count", self.proposed_buy_leg_count),
                )
                if value is not None
            }
        )
        return payload


class _Unavailable(ValueError):
    pass


def _check(predicate, reason):
    if not predicate:
        raise _Unavailable(reason)


def _decimal(value: Fraction) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return Decimal(value.numerator) / Decimal(value.denominator)


def _covariance(value):
    _check(isinstance(value, Mapping) and set(value) == set(SYMBOLS), "covariance_unavailable")
    matrix = []
    for symbol in SYMBOLS:
        row = value[symbol]
        _check(isinstance(row, Mapping) and set(row) == set(SYMBOLS), "covariance_invalid")
        _check(
            all(type(row[s]) is Decimal and row[s].is_finite() for s in SYMBOLS),
            "covariance_invalid",
        )
        matrix.append(tuple(Fraction(row[s]) for s in SYMBOLS))
    _check(
        all(matrix[i][j] == matrix[j][i] for i in range(3) for j in range(3)), "covariance_invalid"
    )
    _check(all(matrix[i][i] >= 0 for i in range(3)), "covariance_invalid")
    _check(
        all(matrix[i][i] * matrix[j][j] >= matrix[i][j] ** 2 for i in range(3) for j in range(i)),
        "covariance_invalid",
    )
    a, b, c = matrix[0]
    _, d, e = matrix[1]
    _, _, f = matrix[2]
    _check(a * d * f + 2 * b * c * e - a * e * e - d * c * c - f * b * b >= 0, "covariance_invalid")
    return matrix


def project_kis_paper_portfolio_preview(
    *,
    binding: Mapping[str, object],
    states: Mapping[str, KisPaperCanaryState],
    expected_account_ref: str,
    expected_basis_ref: str,
    expected_owner_refs: Mapping[str, str],
    reads: KisPaperPortfolioPreviewReads | None,
    weights_by_symbol: Mapping[str, Decimal] | None,
    covariance_by_symbol: Mapping[str, Mapping[str, Decimal]] | None,
    target_as_of: datetime,
    as_of: datetime,
) -> KisPaperPortfolioPreview:
    """No I/O, adoption, selling, basis reset, reservation write or leg resizing.

    Targets are fractions of provisional marked sleeve NAV; shared fixed-bank
    entry-cost/reservation enforcement is a separate constraint. All totals use
    exact Fractions. Tuple outputs are in SPY/TLT/GLD order.
    """
    funding_projection = None
    historical_count = None
    try:
        at = require_utc(as_of)
        _check(
            isinstance(binding, Mapping)
            and type(binding["version"]) is int
            and (binding["version"], set(binding)) in ((2, _V2_KEYS), (3, _V3_KEYS)),
            "ownership_binding_invalid",
        )
        _check(
            type(expected_account_ref) is str
            and re.fullmatch(r"[0-9a-f]{64}", expected_account_ref) is not None
            and binding["account_ref"] == expected_account_ref,
            "account_binding_mismatch",
        )
        _check(binding["legacy_spy"] is None, "legacy_scope_unsupported")
        qqq = binding["qqq"]
        _check(
            isinstance(qqq, dict)
            and set(qqq) == {"cycle_id", "owner_ref", "orders"}
            and type(qqq["cycle_id"]) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", qqq["cycle_id"]),
            "ownership_binding_invalid",
        )
        _validate_orders(binding["orders"], _RUN_ID)
        _validate_orders(qqq["orders"], _QQQ_RUN_ID)
        owners = tuple(owner for owner, _ in _owners(binding))
        _check(
            binding["basis_ref"] == expected_basis_ref
            and {owner.owner_ref: ref for owner, ref in _owners(binding)} == expected_owner_refs,
            "ownership_pin_mismatch",
        )
        records = binding["orders"] + qqq["orders"]
        records += [
            {"run_id": run_id, "intent_ref": state.intent.fingerprint,
             "closed": run_id in binding["terminal_evidence"]}
            for run_id, state in _portfolio_seed_states(binding).items()
        ]
        _check(
            isinstance(states, Mapping) and set(states) == {row["run_id"] for row in records},
            "state_scope_invalid",
        )
        terminal = binding["terminal_evidence"]
        _check(
            isinstance(terminal, dict) and set(terminal) <= set(states), "terminal_scope_invalid"
        )
        replay_states, proofs = {}, {}
        terminal_failure = False
        for record in records:
            run_id = record["run_id"]
            state = states[run_id]
            _check(type(state) is KisPaperCanaryState, "state_invalid")
            terminal_failure |= state.phase in {
                "submission_started",
                "outcome_unknown",
                "cancel_started",
            }
            if record["closed"]:
                try:
                    retained, proof = _retained_terminal(state, terminal.get(run_id))
                    _check(_terminal(retained, proof), "terminal_unproven")
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError,
                    DecimalException,
                    KisPaperCanaryError,
                    _RecoveryRequired,
                ):
                    terminal_failure = True
                else:
                    state = retained
                    if proof is not None:
                        proofs[run_id] = proof
            else:
                _check(run_id not in terminal, "terminal_scope_invalid")
            replay_states[run_id] = state
        projection = project_kis_paper_portfolio_budget(
            basis=_basis(binding),
            expected_basis_ref=expected_basis_ref,
            owners=owners,
            expected_owner_refs=expected_owner_refs,
            states=replay_states,
            as_of=at,
            cancellation_proofs=proofs,
        )
        funding_projection = projection
        historical_count = len(records)
        _check(not terminal_failure, "terminal_or_outcome_unproven")
        pending = sum(not row["closed"] for row in records)
        _check(type(reads) is KisPaperPortfolioPreviewReads, "reads_unavailable")
        _check(reads.account_ref == expected_account_ref, "account_binding_mismatch")
        _check(
            require_utc(target_as_of) <= reads.started_at <= reads.completed_at <= at,
            "input_clock_invalid",
        )
        snapshot = reads.snapshot
        replace(snapshot.cash)
        replace(snapshot.orderable_funds)
        _check(snapshot.open_orders.complete is True, "account_incomplete")
        _check(
            tuple(row.symbol for row in reads.instruments) == SYMBOLS, "instrument_scope_invalid"
        )
        times = [
            reads.started_at,
            reads.completed_at,
            snapshot.captured_at,
            snapshot.identity.captured_at,
            snapshot.cash.captured_at,
            snapshot.orderable_funds.captured_at,
            snapshot.open_orders.captured_at,
        ]
        times.extend(row.captured_at for row in (*snapshot.positions, *snapshot.open_orders.orders))
        limits, marks = [], []
        funds = [snapshot.cash.available_cash, snapshot.orderable_funds.orderable_funds]
        _check(
            snapshot.cash.currency == snapshot.orderable_funds.currency == "USD", "currency_invalid"
        )
        _check(
            all(type(v) is Decimal and v.is_finite() and v >= 0 for v in funds),
            "buying_power_invalid",
        )
        for row in reads.instruments:
            replace(row.cash)
            replace(row.orderable)
            _check(row.exchange == KIS_PAPER_PREVIEW_VENUES[row.symbol][1], "venue_mismatch")
            limit = derive_kis_paper_marketable_limit(row.quote, side="buy", observed_at=at)
            _check(
                type(row.quote.last) is Decimal
                and row.quote.last.is_finite()
                and row.quote.last > 0,
                "quote_unavailable",
            )
            _check(
                (
                    row.orderable.reference_symbol,
                    row.orderable.reference_exchange,
                    row.orderable.reference_price,
                )
                == (row.symbol, row.exchange, limit)
                and row.buy_limit == limit,
                "orderability_binding_mismatch",
            )
            _check(row.cash.currency == row.orderable.currency == "USD", "currency_invalid")
            _check(
                all(
                    type(v) is Decimal and v.is_finite() and v >= 0
                    for v in (row.cash.available_cash, row.orderable.orderable_funds)
                ),
                "buying_power_invalid",
            )
            times.extend((row.quote.quoted_at, row.cash.captured_at, row.orderable.captured_at))
            funds.extend((row.cash.available_cash, row.orderable.orderable_funds))
            limits.append(Fraction(limit))
            marks.append(Fraction(row.quote.last))
        _check(
            all(
                timedelta(seconds=-5) <= at - require_utc(t) <= timedelta(seconds=120)
                for t in times
            ),
            "reads_stale",
        )
        book = {}
        for position in snapshot.positions:
            if position.symbol in {*SYMBOLS, "QQQ"}:
                exchange = (
                    "NASD"
                    if position.symbol == "QQQ"
                    else KIS_PAPER_PREVIEW_VENUES[position.symbol][1]
                )
                _check(
                    position.symbol not in book
                    and position.exchange == exchange
                    and position.currency == "USD"
                    and position.quantity >= 0,
                    "inventory_mismatch",
                )
                book[position.symbol] = position.quantity
        owned = {stock.symbol: stock.quantity for stock in projection.stocks_by_instrument}
        _check(
            all(book.get(s, Decimal(0)) == owned.get(s, Decimal(0)) for s in (*SYMBOLS, "QQQ")),
            "inventory_mismatch",
        )
        if owned["QQQ"]:
            return KisPaperPortfolioPreview(
                "unreachable",
                "unmodelled_owned_inventory",
                len(records),
                pending,
            )
        _check(
            isinstance(weights_by_symbol, Mapping) and set(weights_by_symbol) == set(SYMBOLS),
            "targets_unavailable",
        )
        _check(
            all(
                type(w) is Decimal and w.is_finite() and 0 <= w <= 1
                for w in weights_by_symbol.values()
            ),
            "targets_invalid",
        )
        weights = tuple(Fraction(weights_by_symbol[s]) for s in SYMBOLS)
        _check(sum(weights) <= 1, "targets_invalid")
        covariance = _covariance(covariance_by_symbol)
        inventory = tuple(Fraction(owned.get(s, Decimal(0))) for s in SYMBOLS)
        spy = inventory[0]
        cost, reserved = Fraction(projection.entry_cost), Fraction(projection.reserved_buys)
        bank = Fraction(projection.allocated_usd)
        cash = Fraction(projection.gross_cash)
        nav = cash + sum(q * p for q, p in zip(inventory, marks, strict=True))
        _check(nav > 0, "risk_nav_unavailable")
        quantities = tuple((w * nav) // limit for w, limit in zip(weights, limits, strict=True))
        additional = tuple(max(Fraction(0), target - held)
                           for target, held in zip(quantities, inventory, strict=True))
        notionals = tuple(q * p for q, p in zip(additional, limits, strict=True))
        # Every incumbent is immutable; no sell or foreign-inventory adoption.
        exposures = tuple(max(Fraction(q), held) * p / nav
                          for q, held, p in zip(quantities, inventory, marks, strict=True))
        annual_variance = 252 * sum(
            exposures[i] * covariance[i][j] * exposures[j] for i in range(3) for j in range(3)
        )
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            risk = _decimal(annual_variance).sqrt()
        reason = (
            "incumbent_target_mismatch"
            if any(target < held for target, held in zip(quantities, inventory, strict=True))
            else "rounded_risk_exceeds_cap"
            if annual_variance > Fraction(ANNUAL_RISK_CAP) ** 2
            else "pending_identity"
            if pending
            else "open_order_conflict"
            if any(o.symbol in {*SYMBOLS, "QQQ"} for o in snapshot.open_orders.orders)
            else "shared_budget_exceeded"
            if sum(notionals) > bank - cost - reserved
            or sum(notionals) > cash - reserved
            else "buying_power_insufficient"
            if sum(notionals) + reserved > min(map(Fraction, funds))
            else "preview_only"
        )
        return KisPaperPortfolioPreview(
            "preview_feasible" if reason == "preview_only" else "unreachable",
            reason,
            len(records),
            pending,
            sum(q > 0 for q in additional),
            tuple(map(Decimal, quantities)),
            tuple(map(_decimal, additional)),
            tuple(map(_decimal, notionals)),
            _decimal(spy),
            _decimal(cost),
            _decimal(reserved),
            _decimal(sum(notionals)),
            _decimal(nav),
            risk,
        )
    except _Unavailable as error:
        reason = str(error)
    except KisPaperQuoteError:
        reason = "quote_unavailable"
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        DecimalException,
        KisPaperCanaryError,
        _RecoveryRequired,
    ):
        reason = "ownership_or_input_invalid"
    return KisPaperPortfolioPreview(
        "unavailable",
        reason,
        historical_order_count=historical_count,
        shared_entry_cost=None if funding_projection is None else funding_projection.entry_cost,
        shared_reservations=None
        if funding_projection is None
        else funding_projection.reserved_buys,
    )
