from __future__ import annotations

import builtins
import copy
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_preview import (
    SYMBOLS,
    project_kis_paper_portfolio_preview,
)
from thericher_v2.execution.kis_paper_quote import KIS_PAPER_PREVIEW_VENUES, KisPaperSpyLimitInput
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPortfolioPreviewInstrument,
    KisPaperPortfolioPreviewReads,
    KisPaperPosition,
    KisPaperReadOnlyClient,
    KisPaperReadOnlySnapshot,
)

D = Decimal
NOW = datetime(2026, 10, 8, 14, 30, tzinfo=UTC)
ACCOUNT = "a" * 64


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("preview cannot access network, account, order or store")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(KisPaperReadOnlyClient, "snapshot", deny)
    monkeypatch.setattr(KisPaperCanaryStateStore, "record_intent", deny)
    monkeypatch.setattr(budget, "_load_binding", deny)


def _state(index=1, *, symbol="SPY", pending=False, requested="1", filled="1", remaining="0"):
    created = NOW - timedelta(minutes=2, seconds=10 - index)
    intent = KisPaperCanaryIntent(
        ("bs-" if symbol == "SPY" else "bq-") + f"{index:064x}",
        f"synthetic-client-{index}",
        f"synthetic-decision-{index}",
        symbol,
        "AMEX" if symbol == "SPY" else "NASD",
        D(requested),
        D(100),
        created,
        NOW + timedelta(minutes=1),
        "buy",
    )
    if pending:
        return KisPaperCanaryState(intent, "intent_recorded", created, "preview")
    submitted = created + timedelta(seconds=1)
    order = f"SYNTHETIC-{index}"
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id=order,
            order_at=submitted,
            symbol=symbol,
            exchange=intent.exchange,
            side="buy",
            quantity=intent.quantity,
        ),
        D(requested),
        D(filled),
        D(60) if D(filled) else D(0),
        submitted + timedelta(seconds=1),
        None if remaining is None else D(remaining),
    )
    return KisPaperCanaryState(
        intent,
        "submitted",
        submitted + timedelta(seconds=2),
        "reconciliation_clean",
        broker_order_id=order,
        submission_started_at=submitted,
        submitted_at=submitted,
        cumulative_fill=fill,
        fill_observation_status="available",
        fill_observed_at=fill.observed_at,
    )


def _scope(*states):
    orders = {s: [] for s in ("SPY", "QQQ")}
    terminal = {}
    for state in states:
        closed = state.phase != "intent_recorded"
        orders[state.intent.symbol].append(
            dict(
                run_id=state.intent.run_id,
                intent_ref=state.intent.fingerprint,
                closed=closed,
            )
        )
        if closed and budget._terminal(state):
            terminal[state.intent.run_id] = budget._terminal_payload(state)
    binding = dict(
        version=2,
        account_ref=ACCOUNT,
        basis_usd="10000",
        allocated_usd="1000",
        at=(NOW - timedelta(days=1)).isoformat(),
        orders=orders["SPY"],
        basis_ref=None,
        spy_owner_ref=None,
        qqq=dict(cycle_id="synthetic-unit", owner_ref=None, orders=orders["QQQ"]),
        legacy_spy=None,
        terminal_evidence=terminal,
    )
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    return dict(
        binding=binding,
        states={s.intent.run_id: s for s in states},
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: pin for owner, pin in budget._owners(binding)},
        reads=_reads(
            spy=sum(
                s.cumulative_fill.quantity
                for s in states
                if s.intent.symbol == "SPY" and s.cumulative_fill
            )
        ),
        weights_by_symbol=dict(SPY=D("0.33"), TLT=D("0.33"), GLD=D("0.34")),
        covariance_by_symbol={
            s: {t: D("0.000001") if s == t else D(0) for t in SYMBOLS} for s in SYMBOLS
        },
        target_as_of=NOW - timedelta(hours=1),
        as_of=NOW,
    )


def _reads(*, spy=None, funds=None, prices=None, extra=()):
    spy = D(1) if spy is None else spy
    funds = D(10000) if funds is None else funds
    prices = (D(100), D(100), D(100)) if prices is None else prices
    cash = KisPaperCashSnapshot("USD", funds, NOW)
    instruments = tuple(
        KisPaperPortfolioPreviewInstrument(
            s,
            KIS_PAPER_PREVIEW_VENUES[s][1],
            KisPaperSpyLimitInput(p, 2, D("0.01"), NOW, p - D("0.01"), p),
            p,
            cash,
            KisPaperOrderableFundsSnapshot("USD", funds, KIS_PAPER_PREVIEW_VENUES[s][1], s, p, NOW),
        )
        for s, p in zip(SYMBOLS, prices, strict=True)
    )
    positions = (
        () if spy == 0 else (KisPaperPosition("SPY", "AMEX", "USD", spy, D(60), D(100), NOW),)
    )
    snapshot = KisPaperReadOnlySnapshot(
        KisPaperAccountIdentity("****5678-**01", NOW),
        cash,
        instruments[0].orderable,
        positions + extra,
        KisPaperOpenOrdersSnapshot((), NOW),
        NOW,
    )
    return KisPaperPortfolioPreviewReads(ACCOUNT, snapshot, instruments, NOW, NOW, 0.01)


def test_whole_share_shared_bank_incumbent_risk_and_source_safe_payload():
    inputs = _scope(_state())
    result = project_kis_paper_portfolio_preview(**inputs)
    assert result.status == "preview_feasible" and result.reason == "preview_only"
    assert result.target_quantities == (D(3), D(3), D(3))
    assert result.additional_quantities == (D(2), D(3), D(3))
    assert result.buy_notionals == (D(200), D(300), D(300))
    assert result.provisional_risk_nav == D(1040)
    assert result.shared_entry_cost == D(60) and result.proposed_reservation == D(800)
    assert result.rounded_annual_risk < D("0.1")
    text = json.dumps(result.safe_payload()) + repr(result)
    assert result.safe_payload()["new_submits"] == 0
    for value in (ACCOUNT, "SYNTHETIC-1", "1040", "800", inputs["binding"]["basis_ref"]):
        assert value not in text


def test_no_io_or_mutation_and_exact_restart_and_named_permutation(monkeypatch):
    inputs = _scope(_state())
    original = copy.deepcopy(inputs)
    monkeypatch.setattr(builtins, "open", lambda *a, **k: pytest.fail("no file I/O"))
    first = project_kis_paper_portfolio_preview(**inputs)
    assert inputs == original
    for _ in range(3):
        assert project_kis_paper_portfolio_preview(**copy.deepcopy(inputs)) == first
    inputs["weights_by_symbol"] = dict(reversed(list(inputs["weights_by_symbol"].items())))
    inputs["covariance_by_symbol"] = dict(reversed(list(inputs["covariance_by_symbol"].items())))
    assert project_kis_paper_portfolio_preview(**inputs) == first
    with pytest.raises(FrozenInstanceError):
        first.reason = "changed"


def test_incumbent_cannot_be_sold_adopted_or_ignored_to_meet_target():
    inputs = _scope(_state())
    inputs["weights_by_symbol"] = dict(SPY=D(0), TLT=D(0), GLD=D(0))
    result = project_kis_paper_portfolio_preview(**inputs)
    assert (result.status, result.reason) == ("unreachable", "incumbent_target_mismatch")
    assert result.incumbent_spy_quantity == D(1)
    assert result.additional_quantities == (D(0), D(0), D(0))
    assert result.rounded_annual_risk > 0


def test_rounding_can_destroy_hedge_and_total_risk_must_not_be_called_feasible():
    inputs = _scope(_state())
    inputs["reads"] = _reads(prices=(D(100), D(1000), D(100)))
    inputs["weights_by_symbol"] = dict(SPY=D("0.5"), TLT=D("0.5"), GLD=D(0))
    inputs["covariance_by_symbol"] = {
        "SPY": dict(SPY=D("0.0004"), TLT=D("-0.0004"), GLD=D(0)),
        "TLT": dict(SPY=D("-0.0004"), TLT=D("0.0004"), GLD=D(0)),
        "GLD": dict(SPY=D(0), TLT=D(0), GLD=D(0)),
    }
    result = project_kis_paper_portfolio_preview(**inputs)
    assert result.target_quantities == (D(5), D(0), D(0))
    assert result.status == "unreachable" and result.reason == "rounded_risk_exceeds_cap"


def test_pending_identity_and_reservations_survive_without_replacement_or_release():
    state, pending = _state(), _state(2, pending=True)
    inputs = _scope(state, pending)
    before = copy.deepcopy(inputs)
    result = project_kis_paper_portfolio_preview(**inputs)
    assert result.status == "unreachable" and result.reason == "pending_identity"
    assert result.pending_count == 1 and result.shared_reservations == D(100)
    assert inputs == before


@pytest.mark.parametrize(
    "filled,remaining,reservation",
    [
        ("1", "1", D(100)),
        ("1", None, D(100)),
        ("0", None, D(200)),
    ],
)
def test_false_closed_partial_or_unknown_zero_fill_retains_exact_reservation(
    filled,
    remaining,
    reservation,
):
    inputs = _scope(_state(requested="2", filled=filled, remaining=remaining))
    before = copy.deepcopy(inputs)
    result = project_kis_paper_portfolio_preview(**inputs)
    assert (result.status, result.reason) == ("unavailable", "terminal_or_outcome_unproven")
    assert result.shared_reservations == reservation
    assert result.pending_count is None and "pending_count" not in result.safe_payload()
    assert inputs == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("available_cash", D(-1)),
        ("available_cash", D("NaN")),
        ("orderable_funds", D(-1)),
        ("orderable_funds", D("Infinity")),
    ],
)
def test_cash_funds_dataclasses_are_revalidated_not_trusted_after_mutation(field, value):
    inputs = _scope(_state())
    snapshot = inputs["reads"].snapshot
    target = snapshot.cash if field == "available_cash" else snapshot.orderable_funds
    object.__setattr__(target, field, value)
    result = project_kis_paper_portfolio_preview(**inputs)
    assert result.status == "unavailable"


def test_unbound_extra_state_and_legacy_account_cannot_be_adopted():
    inputs = _scope(_state())
    inputs["states"]["unbound"] = _state(2)
    assert project_kis_paper_portfolio_preview(**inputs).reason == "state_scope_invalid"
    inputs = _scope(_state())
    inputs["binding"]["legacy_spy"] = {"account_ref": "b" * 64}
    assert project_kis_paper_portfolio_preview(**inputs).reason == "legacy_scope_unsupported"


def test_later_unavailable_read_retains_proven_consistent_fill():
    state = _state()
    inputs = _scope(state)
    original = project_kis_paper_portfolio_preview(**inputs)
    inputs["states"][state.intent.run_id] = replace(state, fill_observation_status="unavailable")
    assert project_kis_paper_portfolio_preview(**inputs) == original


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"expected_account_ref": "b" * 64}, "account_binding_mismatch"),
        ({"expected_basis_ref": "sha256:" + "b" * 64}, "ownership_pin_mismatch"),
        ({"expected_owner_refs": {}}, "ownership_pin_mismatch"),
        ({"states": {}}, "state_scope_invalid"),
        ({"reads": None}, "reads_unavailable"),
        ({"weights_by_symbol": None}, "targets_unavailable"),
        ({"weights_by_symbol": dict(SPY=D(1), TLT=D(1), GLD=D(0))}, "targets_invalid"),
        ({"weights_by_symbol": dict(SPY=True, TLT=D(0), GLD=D(0))}, "targets_invalid"),
        ({"covariance_by_symbol": None}, "covariance_unavailable"),
        ({"target_as_of": NOW + timedelta(seconds=1)}, "input_clock_invalid"),
    ],
)
def test_invalid_or_missing_inputs_are_scoped_unavailable(change, reason):
    inputs = _scope(_state())
    result = project_kis_paper_portfolio_preview(**(inputs | change))
    assert (result.status, result.reason) == ("unavailable", reason)


@pytest.mark.parametrize("kind", ["negative", "asymmetric", "indefinite", "nonfinite"])
def test_covariance_must_be_named_finite_symmetric_psd(kind):
    inputs = _scope(_state())
    c = inputs["covariance_by_symbol"]
    if kind == "negative":
        c["SPY"]["SPY"] = D(-1)
    elif kind == "asymmetric":
        c["SPY"]["TLT"] = D("0.0000001")
    elif kind == "indefinite":
        c["SPY"]["TLT"] = c["TLT"]["SPY"] = D(1)
    else:
        c["SPY"]["SPY"] = D("NaN")
    assert project_kis_paper_portfolio_preview(**inputs).reason == "covariance_invalid"


def test_shared_funds_are_not_three_independently_funded_sleeves():
    inputs = _scope(_state())
    inputs["reads"] = _reads(funds=D(500))
    result = project_kis_paper_portfolio_preview(**inputs)
    assert (result.status, result.reason) == ("unreachable", "buying_power_insufficient")
    assert result.proposed_reservation == D(800)  # no later-leg resizing


def test_gain_does_not_increase_initial_shared_funding_bank():
    inputs = _scope(_state())
    inputs["reads"] = _reads(prices=(D(1000), D(100), D(100)))
    inputs["weights_by_symbol"] = dict(SPY=D("0.6"), TLT=D("0.2"), GLD=D("0.2"))
    result = project_kis_paper_portfolio_preview(**inputs)
    assert result.provisional_risk_nav == D(1940)
    assert result.status == "preview_feasible"
    assert result.proposed_reservation == D(600)
    assert inputs["binding"]["allocated_usd"] == "1000"
    assert result.proposed_reservation + result.shared_entry_cost <= D(1000)


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("account", "account_binding_mismatch"),
        ("stale", "reads_stale"),
        ("limit", "orderability_binding_mismatch"),
        ("foreign", "inventory_mismatch"),
    ],
)
def test_read_binding_freshness_and_foreign_inventory(kind, reason):
    inputs = _scope(_state())
    reads = inputs["reads"]
    if kind == "account":
        reads = replace(reads, account_ref="b" * 64)
    elif kind == "stale":
        reads = replace(reads, started_at=NOW - timedelta(seconds=121))
    elif kind == "limit":
        leg = reads.instruments[1]
        leg = replace(leg, orderable=replace(leg.orderable, reference_price=D(99)))
        reads = replace(reads, instruments=(reads.instruments[0], leg, reads.instruments[2]))
    else:
        reads = _reads(extra=(KisPaperPosition("TLT", "NASD", "USD", D(1), D(100), D(100), NOW),))
    inputs["reads"] = reads
    assert project_kis_paper_portfolio_preview(**inputs).reason == reason
