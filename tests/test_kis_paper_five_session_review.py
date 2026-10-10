"""Independent synthetic lifecycle checks; no broker or private-state activity."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.execution.kis_paper_budget_strategy import _stock_identity
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
    project_five_session_cohort,
)
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
)
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument

D = Decimal
ACCOUNT = "a" * 64
BASIS = KisPaperPortfolioBudgetBasis(ACCOUNT, D(10000), D(1000), datetime(2026, 10, 1, tzinfo=UTC))


def _cohort():
    opens = tuple(datetime(2026, 10, 12 + i, 13, 30, tzinfo=UTC) for i in range(5))
    closes = tuple(o + timedelta(hours=6, minutes=30) for o in opens)
    return KisPaperFiveSessionCohort(
        KisPaperStockInstrument("SYN", "ref:" + "b" * 64),
        "decision:sha256:" + "d" * 64,
        "sha256:" + "c" * 64,
        "sha256:" + "e" * 64,
        opens,
        closes,
        opens[0] + timedelta(minutes=10),
        closes[-1] - timedelta(minutes=10),
    )


def _entry(cohort, *, pending=False, partial=False):
    identity = _stock_identity(
        {
            "account_ref": ACCOUNT,
            "basis_ref": BASIS.fingerprint,
            "stocks": {
                "SYN": {"exchange": "NASD", "instrument_binding_ref": cohort.instrument.binding_ref}
            },
        },
        "SYN",
        cohort.entry_request_id,
        "buy",
    )
    when = cohort.session_opens[0]
    intent = KisPaperCanaryIntent(
        "bk-" + identity,
        "stock-" + identity,
        "stock-" + identity,
        "SYN",
        "NASD",
        D(2),
        D(10),
        when,
        when + timedelta(seconds=30),
    )
    order_at = when + timedelta(seconds=1)
    if pending:
        return KisPaperCanaryState(
            intent,
            "outcome_unknown",
            when + timedelta(seconds=40),
            "reconciliation_unresolved",
            submission_started_at=order_at,
        )
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id="SYN-order",
            order_at=order_at,
            symbol="SYN",
            exchange="NASD",
            side="buy",
            quantity=D(2),
        ),
        D(2),
        D(1 if partial else 2),
        D(10 if partial else 20),
        when + timedelta(seconds=2),
        D(1 if partial else 0),
    )
    return KisPaperCanaryState(
        intent,
        "submitted",
        when + timedelta(seconds=40),
        "reconciliation_unresolved",
        broker_order_id="SYN-order",
        submitted_at=order_at,
        submission_started_at=order_at,
        cumulative_fill=fill,
        fill_observation_status="available",
        fill_observed_at=fill.observed_at,
    )


def _project(
    cohort, entry=None, *, now=None, input_status="ready", absent_owner=False, custody=None
):
    reference = (
        None
        if entry is None
        else KisPaperPortfolioStateRef(entry.intent.run_id, entry.intent.fingerprint)
    )
    owner = KisPaperPortfolioOwnerBinding(
        cohort.owner_ref,
        ACCOUNT,
        "SYN",
        "NASD",
        () if reference is None else (reference,),
        cohort.instrument.binding_ref,
    )
    owners = () if absent_owner else (owner,)
    return project_five_session_cohort(
        cohort=cohort,
        expected_cohort_ref=cohort.fingerprint,
        custody=custody or KisPaperFiveSessionCustody(reference),
        basis=BASIS,
        expected_basis_ref=BASIS.fingerprint,
        owners=owners,
        expected_owner_refs={o.owner_ref: o.fingerprint for o in owners},
        states={} if entry is None or absent_owner else {entry.intent.run_id: entry},
        as_of=now or cohort.exit_due,
        input_status=input_status,
    )


def test_five_intraday_windows_cannot_be_five_trading_sessions():
    cohort = _cohort()
    opens = tuple(cohort.session_opens[0] + timedelta(minutes=70 * i) for i in range(5))
    closes = tuple(o + timedelta(hours=1) for o in opens)
    with pytest.raises(ValueError, match="cohort_sessions_invalid"):
        replace(
            cohort,
            session_opens=opens,
            session_closes=closes,
            entry_window_end=opens[0] + timedelta(minutes=10),
            exit_due=closes[-1] - timedelta(minutes=10),
        )


@pytest.mark.parametrize("index", range(4))
def test_canonical_native_BUY_holds_first_four_closes(index):
    cohort = _cohort()
    entry = _entry(cohort)
    assert entry.intent.decision_id != cohort.entry_decision_id
    result = _project(cohort, entry, now=cohort.session_closes[index], input_status="unavailable")
    assert result.status == "hold" and result.owned_quantity == 2


@pytest.mark.parametrize("field", ["run_id", "client_order_id", "decision_id"])
def test_each_native_identity_field_is_exact_not_research_alias(field):
    cohort = _cohort()
    entry = _entry(cohort)
    changed = replace(entry, intent=replace(entry.intent, **{field: "foreign-identity"}))
    result = _project(cohort, changed)
    assert (result.status, result.reason) == ("reconcile", "entry_contract_mismatch")


@pytest.mark.parametrize("partial", [False, True])
def test_retained_unknown_or_partial_precedes_clock_and_input(partial):
    cohort = _cohort()
    entry = _entry(cohort, pending=not partial, partial=partial)
    result = _project(
        cohort, entry, now=cohort.exit_due + timedelta(days=10), input_status="unavailable"
    )
    assert (result.status, result.reason) == ("reconcile", "entry_recovery_pending")
    assert result.pending.run_id == entry.intent.run_id


def test_absent_owner_is_only_a_new_empty_custody_entry():
    cohort = _cohort()
    assert _project(cohort, now=cohort.session_opens[0], absent_owner=True).status == "entry_ready"
    entry = _entry(cohort)
    result = _project(cohort, entry, absent_owner=True)
    assert result.reason == "cohort_custody_mismatch"


def test_exact_fifth_exit_boundary_ignores_unavailable_model_input():
    cohort = _cohort()
    entry = _entry(cohort)
    before = _project(
        cohort, entry, now=cohort.exit_due - timedelta(microseconds=1), input_status="unavailable"
    )
    due = _project(cohort, entry, now=cohort.exit_due, input_status="unavailable")
    assert before.status == "hold"
    assert (due.status, due.reason, due.owned_quantity) == (
        "exit_ready",
        "fifth_session_exit_due",
        D(2),
    )
