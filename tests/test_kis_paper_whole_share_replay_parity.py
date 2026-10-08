from __future__ import annotations

import copy
import socket
import urllib.request
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from test_kis_paper_portfolio_pnl import arguments, owner, roundtrip, state
from test_kis_paper_portfolio_preview import _reads, _scope, _state
from thericher_v2.execution import kis_paper_budget_strategy as custody
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryStateStore
from thericher_v2.execution.kis_paper_fill_accounting import fill_identity_ref
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetError,
    project_kis_paper_portfolio_budget,
)
from thericher_v2.execution.kis_paper_portfolio_pnl import project_kis_paper_portfolio_pnl
from thericher_v2.execution.kis_paper_portfolio_preview import (
    SYMBOLS,
    project_kis_paper_portfolio_preview,
)

D = Decimal
ZERO = Fraction(0)
BANK = Fraction(1000)
BASIS = Fraction(10000)
ANALYTICAL_COST_BPS = (0, 10)
INITIAL_PRICES = (D(100), D(200), D(100))
GAIN_PRICES = (D(150), D(200), D(100))
INITIAL_WEIGHTS = dict(SPY=D(".3"), TLT=D(".3"), GLD=D(".3"))
NEXT_WEIGHTS = dict(SPY=D(".6"), TLT=D(".2"), GLD=D(".2"))
COVARIANCE = {s: {t: D(".000001") if s == t else D(0) for t in SYMBOLS} for s in SYMBOLS}


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("synthetic pure parity bridge cannot access provider or persisted custody")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(custody, "_load_binding", deny)
    monkeypatch.setattr(KisPaperCanaryStateStore, "record_intent", deny)


def _fill(index, *, quantity, amount, limit="100", side="buy"):
    original = _state(index, requested=quantity, filled=quantity, remaining="0")
    intent = replace(original.intent, limit_price=D(limit), side=side)
    fill = replace(
        original.cumulative_fill,
        identity_ref=fill_identity_ref(
            raw_order_id=original.broker_order_id,
            order_at=original.submitted_at,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side=side,
            quantity=intent.quantity,
        ),
        gross_amount=D(amount),
    )
    return replace(original, intent=intent, cumulative_fill=fill)


def _preview_arguments(*fills, prices=INITIAL_PRICES, weights=INITIAL_WEIGHTS, held="0"):
    inputs = _scope(*fills)
    inputs.update(
        reads=_reads(spy=D(held), prices=prices),
        weights_by_symbol=copy.deepcopy(weights),
        covariance_by_symbol=copy.deepcopy(COVARIANCE),
    )
    return inputs


def _ledger_arguments(inputs):
    binding = inputs["binding"]
    return dict(
        basis=custody._basis(binding),
        expected_basis_ref=inputs["expected_basis_ref"],
        owners=tuple(o for o, _ in custody._owners(binding)),
        expected_owner_refs=inputs["expected_owner_refs"],
        states=inputs["states"],
        as_of=inputs["as_of"],
    )


def _oracle_targets(cash, holdings, prices, weights):
    nav = cash + sum((q * Fraction(p) for q, p in zip(holdings, prices, strict=True)), ZERO)
    fractional = tuple(
        Fraction(weights[s]) * nav / Fraction(p) for s, p in zip(SYMBOLS, prices, strict=True)
    )
    whole = tuple(q.numerator // q.denominator for q in fractional)
    return nav, fractional, whole


@pytest.mark.parametrize("cost_bps", ANALYTICAL_COST_BPS)
def test_two_linked_fills_floor_marked_gain_and_separate_analytical_fees(cost_bps):
    fee = Fraction(cost_bps, 10000)
    initial = _preview_arguments()
    before = project_kis_paper_portfolio_preview(**initial)
    _, fractional, targets = _oracle_targets(BANK, (ZERO,) * 3, INITIAL_PRICES, INITIAL_WEIGHTS)
    assert before.status == "preview_feasible"
    assert before.target_quantities == targets == (3, 1, 3)
    assert fractional == (Fraction(3), Fraction(3, 2), Fraction(3))
    assert fractional != targets  # Scaling a fractional NAV1 result does not implement flooring.

    # Supplied synthetic fills, not evidence that a preview submitted any leg.
    first_fill = _fill(1, quantity="3", amount="300")
    first = _preview_arguments(first_fill, prices=GAIN_PRICES, weights=NEXT_WEIGHTS, held="3")
    ledger1 = project_kis_paper_portfolio_budget(**_ledger_arguments(first))
    cash1, cost1, held1 = BANK - 3 * 100, Fraction(3 * 100), Fraction(3)
    nav1, _, targets1 = _oracle_targets(cash1, (held1, ZERO, ZERO), GAIN_PRICES, NEXT_WEIGHTS)
    marked = project_kis_paper_portfolio_preview(**first)
    assert (Fraction(ledger1.gross_cash), Fraction(ledger1.entry_cost)) == (cash1, cost1)
    assert marked.provisional_risk_nav == nav1 == 1150
    assert marked.target_quantities == targets1 == (4, 1, 2)
    assert marked.additional_quantities == (D(1), D(1), D(2))
    assert marked.proposed_reservation == 550 <= BANK - cost1

    second_fill = _fill(2, quantity="1", amount="150", limit="150")
    second = _preview_arguments(
        first_fill, second_fill, prices=GAIN_PRICES, weights=NEXT_WEIGHTS, held="4"
    )
    cash2, cost2, held2 = cash1 - 150, cost1 + 150, held1 + 1
    ledger2 = project_kis_paper_portfolio_budget(**_ledger_arguments(second))
    gross = project_kis_paper_portfolio_pnl(**_ledger_arguments(second))
    after = project_kis_paper_portfolio_preview(**second)
    assert (Fraction(ledger2.gross_cash), Fraction(ledger2.entry_cost)) == (cash2, cost2)
    assert ledger2.stocks_by_instrument[0].quantity == held2
    assert ledger2.allocated_usd == BANK and ledger2.basis_usd == BASIS
    assert second["expected_basis_ref"] == initial["expected_basis_ref"]
    assert ledger2.reserved_buys == 0 and ledger2.remaining_cap == BANK - cost2
    assert after.status == "preview_feasible" and after.target_quantities == targets1
    assert after.additional_quantities == (D(0), D(1), D(2))
    assert gross.gross_cash_usd == cash2 and gross.remaining_entry_cost_usd == cost2
    assert gross.gross_realized_usd == cash2 + cost2 - BANK == 0
    analytical_fees = fee * (3 * 100 + 150)
    analytical_nav = cash2 - analytical_fees + held2 * Fraction(GAIN_PRICES[0])
    assert analytical_nav == nav1 - analytical_fees
    assert gross.safe_payload()["fees"] == gross.safe_payload()["net_pnl"] == "not_observed"


def test_realized_gain_does_not_rebase_or_expand_original_funding_bank():
    buy = _fill(1, quantity="6", amount="600")
    sell = _fill(2, quantity="6", amount="900", limit="150", side="sell")
    inputs = _preview_arguments(buy, sell, prices=(D(100),) * 3, weights=NEXT_WEIGHTS, held="0")
    original = copy.deepcopy(inputs)
    args = _ledger_arguments(inputs)
    cash = BANK - 600 + 900
    _, _, targets = _oracle_targets(cash, (ZERO,) * 3, (D(100),) * 3, NEXT_WEIGHTS)
    for _ in range(3):
        ledger = project_kis_paper_portfolio_budget(**args)
        gross = project_kis_paper_portfolio_pnl(**args)
        preview = project_kis_paper_portfolio_preview(**inputs)
        assert ledger.gross_cash == cash and ledger.remaining_cap == BANK
        assert ledger.allocated_usd == BANK and ledger.basis_usd == BASIS
        assert gross.gross_realized_usd == cash - BANK == 300
        assert preview.target_quantities == targets == (7, 2, 2)
        assert preview.proposed_reservation == 1100 > BANK
        assert (preview.status, preview.reason) == ("unreachable", "shared_budget_exceeded")
    assert inputs == original


@pytest.mark.parametrize("price,expected", [("99.99", 3), ("100", 3), ("100.01", 2)])
def test_exact_floor_boundary_is_not_nearest_rounding(price, expected):
    prices = (D(price), D(200), D(100))
    weights = dict(SPY=D(".3"), TLT=D(0), GLD=D(0))
    result = project_kis_paper_portfolio_preview(
        **_preview_arguments(prices=prices, weights=weights)
    )
    _, fractional, whole = _oracle_targets(BANK, (ZERO,) * 3, prices, weights)
    assert result.status == "preview_feasible"
    assert result.target_quantities == whole == (expected, 0, 0)
    assert Fraction(expected) <= fractional[0] < expected + 1


@pytest.mark.parametrize("cost_bps", ANALYTICAL_COST_BPS)
def test_full_bank_native_preview_is_not_fee_inclusive_affordability(cost_bps):
    fee = Fraction(cost_bps, 10000)
    weights = dict(SPY=D(1), TLT=D(0), GLD=D(0))
    result = project_kis_paper_portfolio_preview(**_preview_arguments(weights=weights))
    notional = Fraction(result.proposed_reservation)
    analytical_cash = BANK - notional - notional * fee
    fractional_post_fee_nav = BANK / (1 + fee)
    assert result.status == "preview_feasible" and result.target_quantities == (D(10), D(0), D(0))
    assert notional == BANK and analytical_cash == -BANK * fee
    assert (analytical_cash < 0) is (cost_bps == 10)
    assert fractional_post_fee_nav / 100 <= result.target_quantities[0]
    assert int(fractional_post_fee_nav // 100) == (9 if cost_bps else 10)


@pytest.mark.parametrize("later_read", ["available", "unavailable"])
def test_cumulative_progress_replaces_observation_not_adds_fill_or_reservation(later_read):
    partial = state("cumulative", quantity="3", filled="1", amount="100", remaining="2")
    partial = replace(partial, intent=replace(partial.intent, limit_price=D(100)))
    complete = replace(
        partial,
        cumulative_fill=replace(
            partial.cumulative_fill, quantity=D(3), gross_amount=D(300), remaining_quantity=D(0)
        ),
        fill_observation_status=later_read,
    )
    early = arguments(owner("owner", partial))
    late = arguments(owner("owner", complete))
    first = project_kis_paper_portfolio_budget(**early)
    assert (first.entry_cost, first.reserved_buys, first.gross_cash) == (100, 200, 900)
    for _ in range(3):
        last = project_kis_paper_portfolio_budget(**late)
        gross = project_kis_paper_portfolio_pnl(**late)
        assert (last.entry_cost, last.reserved_buys, last.gross_cash) == (300, 0, 700)
        assert last.stocks_by_owner[0].quantity == 3
        assert gross.gross_cash_usd + gross.remaining_entry_cost_usd == BANK


@pytest.mark.parametrize("observation", ["conflict", "identity_mismatch"])
def test_contradictory_owner_does_not_relabel_independent_owner_or_aggregate(observation):
    bad = owner("bad", state("bad-buy", observation=observation))
    good = roundtrip("good", symbol="TLT")
    args = arguments(bad, good)
    ledger = project_kis_paper_portfolio_budget(**args)
    result = project_kis_paper_portfolio_pnl(**args)
    assert ledger.entry_cost == 100 and ledger.gross_cash == BANK + 20 - 100
    assert result.owners[0].reasons == ("fill_conflict",)
    assert result.owners[1].gross_realized_usd == 20
    assert (
        result.gross_realized_usd is None
        and result.safe_payload()["gross_pnl_sign"] == "not_observed"
    )


def test_pending_preview_reserves_once_but_never_becomes_a_fill():
    pending = _state(1, pending=True, requested="3")
    inputs = _preview_arguments(pending, weights=NEXT_WEIGHTS)
    original = copy.deepcopy(inputs)
    for _ in range(3):
        ledger = project_kis_paper_portfolio_budget(**_ledger_arguments(inputs))
        result = project_kis_paper_portfolio_preview(**inputs)
        assert (ledger.entry_cost, ledger.reserved_buys, ledger.gross_cash) == (0, 300, BANK)
        assert (result.status, result.reason) == ("unreachable", "pending_identity")
        assert result.shared_reservations == 300 and result.safe_payload()["new_submits"] == 0
    assert inputs == original


@pytest.mark.parametrize("sell_filled,sell_amount", [(None, "0"), ("1", "150")])
def test_buy_cannot_borrow_unobserved_sell_proceeds_or_unreleased_entry_cost(
    sell_filled, sell_amount
):
    buy = state("buy", quantity="2", amount="1000")
    sell = state(
        "sell",
        side="sell",
        quantity="2",
        filled=sell_filled,
        amount=sell_amount,
        index=1,
        phase="outcome_unknown",
    )
    premature = state("premature", amount="600", index=2)
    premature = replace(premature, intent=replace(premature.intent, limit_price=D(600)))
    for project in (project_kis_paper_portfolio_budget, project_kis_paper_portfolio_pnl):
        with pytest.raises(KisPaperPortfolioBudgetError, match="aggregate_budget_exceeded"):
            project(**arguments(owner("owner", buy, sell, premature)))
    partial = project_kis_paper_portfolio_pnl(**arguments(owner("owner", buy, sell)))
    assert partial.gross_realized_usd is None and partial.status == "incomplete"
    final_sell = state("sell", side="sell", quantity="2", amount="300", index=1)
    final_buy = state("after-sell", amount="200", index=2)
    final = arguments(owner("owner", buy, final_sell, final_buy))
    ledger = project_kis_paper_portfolio_budget(**final)
    gross = project_kis_paper_portfolio_pnl(**final)
    assert (ledger.entry_cost, ledger.gross_cash) == (200, 100)
    assert gross.gross_realized_usd == 300 - 1000 == -700
    assert gross.gross_cash_usd + gross.remaining_entry_cost_usd - BANK == -700


def test_coherent_basis_reset_cannot_change_independent_frozen_pin():
    inputs = _preview_arguments()
    expected = inputs["expected_basis_ref"]
    inputs["binding"]["basis_usd"] = "11000"
    inputs["binding"]["allocated_usd"] = "1100"
    inputs["binding"]["basis_ref"] = custody._basis(inputs["binding"]).fingerprint
    assert inputs["binding"]["basis_ref"] != expected
    result = project_kis_paper_portfolio_preview(**inputs)
    assert (result.status, result.reason) == ("unavailable", "ownership_pin_mismatch")


def test_duplicate_cumulative_state_cannot_be_reimported_as_second_owner():
    fill = state("same-fill", amount="100")
    for project in (project_kis_paper_portfolio_budget, project_kis_paper_portfolio_pnl):
        with pytest.raises(KisPaperPortfolioBudgetError, match="duplicate_state_reference"):
            project(**arguments(owner("first", fill), owner("second", fill)))


def test_sell_cannot_borrow_another_owners_same_symbol_inventory():
    retained = owner("retained", state("owned-buy", quantity="3", amount="300"))
    foreign_sell = owner("other", state("unowned-sell", side="sell", index=1))
    for project in (project_kis_paper_portfolio_budget, project_kis_paper_portfolio_pnl):
        with pytest.raises(KisPaperPortfolioBudgetError, match="unowned_sell"):
            project(**arguments(retained, foreign_sell))
