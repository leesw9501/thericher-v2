from __future__ import annotations

import copy
import socket
import urllib.request
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from test_kis_paper_portfolio_budget import ACCOUNT, AS_OF, BASIS, _state
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryState
from thericher_v2.execution.kis_paper_portfolio_budget import KisPaperPortfolioBudgetError

D = Decimal
CYCLE = "synthetic-roundtrip"


@pytest.fixture(autouse=True)
def no_external_access(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("gross projection must not perform IO or broker access")

    for name in ("_read_json", "_load_binding", "_state"):
        monkeypatch.setattr(budget, name, forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def pair(*, buy="100.13", sell="101.29", prefix=False):
    def unit(digit, **arguments):
        state = _state(digit, **arguments)
        return replace(state, intent=replace(state.intent, run_id="bq-" + digit * 64))

    states = [
        unit("a", symbol="QQQ", filled="1", gross=buy, limit="120", index=1),
        unit(
            "b",
            symbol="QQQ",
            side="sell",
            filled="1",
            gross=sell,
            limit="90",
            index=2,
        ),
    ]
    if prefix:
        states.insert(
            0,
            unit(
                "c",
                symbol="QQQ",
                phase="rejected",
                category="provider_rejected",
                index=0,
            ),
        )
        states[0] = replace(states[0], reason_code="submit_rejected")
    records = [
        {"run_id": state.intent.run_id, "intent_ref": state.intent.fingerprint, "closed": True}
        for state in states
    ]
    binding = dict(
        version=2,
        account_ref=ACCOUNT,
        basis_usd=str(BASIS.basis_usd),
        allocated_usd=str(BASIS.allocated_usd),
        at=BASIS.frozen_at.isoformat(),
        orders=[],
        basis_ref=BASIS.fingerprint,
        spy_owner_ref=None,
        qqq={"cycle_id": CYCLE, "orders": records, "owner_ref": None},
        legacy_spy=None,
        terminal_evidence={
            state.intent.run_id: budget._terminal_payload(state) for state in states
        },
    )
    owner = budget._owner(binding, budget._owner_id(binding, CYCLE), "QQQ", "NASD", records)
    binding["qqq"]["owner_ref"] = owner.fingerprint
    return binding, {state.intent.run_id: state for state in states}


def project(binding, states, **changes):
    arguments = dict(
        binding=binding,
        states=states,
        cycle_id=CYCLE,
        expected_account_ref=ACCOUNT,
        expected_basis_ref=BASIS.fingerprint,
        expected_owner_ref=budget._owner(
            binding,
            budget._owner_id({**binding, "qqq": {**binding["qqq"], "cycle_id": CYCLE}}, CYCLE),
            "QQQ",
            "NASD",
            binding["qqq"]["orders"],
        ).fingerprint,
        as_of=AS_OF,
    )
    arguments.update(changes)
    return budget.project_qqq_unit_gross_pnl(**arguments)


@pytest.mark.parametrize(
    "sell,sign", [("101.29", "positive"), ("99.99", "negative"), ("100.13", "zero")]
)
def test_exact_gross_sign_and_safe_payload(sell, sign):
    binding, states = pair(sell=sell)
    result = project(binding, states)
    assert Fraction(result.gross_realized_usd) == Fraction(D(sell)) - Fraction(D("100.13"))
    safe = result.safe_payload()
    assert safe == dict(
        source="kis_paper",
        currency="USD",
        status="gross_realized_observed",
        gross_pnl_sign=sign,
        matched_fill_count=2,
        roundtrip_count=1,
        owned_flat=True,
        fees="not_observed",
        settled_cash="not_observed",
        net_pnl="not_observed",
    )
    assert "100.13" not in repr(result)
    assert not any(ref in str(safe) for ref in result.fill_refs)


@pytest.mark.parametrize("prefix", [False, True])
def test_json_restart_and_repeated_cumulative_final_snapshots_do_not_accumulate(prefix):
    binding, states = pair(prefix=prefix)
    expected = project(binding, states)
    restarted = {
        key: KisPaperCanaryState.from_dict(state.to_dict()) for key, state in states.items()
    }
    for _ in range(5):
        assert project(copy.deepcopy(binding), restarted) == expected


def test_exact_math_survives_low_decimal_context():
    binding, states = pair(buy="100.000000000000000001", sell="100.000000000000000009")
    with localcontext() as context:
        context.prec = 3
        assert project(binding, states).gross_realized_usd == D("0.000000000000000008")


def test_later_unavailable_read_keeps_exact_retained_fill_not_quote():
    binding, states = pair()
    advanced = {
        key: replace(
            state, fill_observation_status="unavailable", fill_observed_at=state.updated_at
        )
        for key, state in states.items()
    }
    assert all(state.current_fill is None for state in advanced.values())
    assert project(binding, advanced) == project(binding, states)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("account_ref", "f" * 64),
        ("basis_ref", "sha256:" + "f" * 64),
        ("allocated_usd", "999"),
        ("version", True),
    ],
)
def test_binding_conflict_rejects_only_supplied_segment(field, bad):
    binding, states = pair()
    binding[field] = bad
    with pytest.raises((ValueError, budget._RecoveryRequired, KisPaperPortfolioBudgetError)):
        project(binding, states)


@pytest.mark.parametrize(
    "change", ["cycle", "owner", "intent", "duplicate", "pending", "terminal", "missing", "extra"]
)
def test_missing_conflicting_or_duplicate_custody_cannot_be_gross_pnl(change):
    binding, states = pair()
    records = binding["qqq"]["orders"]
    if change == "cycle":
        binding["qqq"]["cycle_id"] = "different-cycle"
    elif change == "owner":
        binding["qqq"]["owner_ref"] = "sha256:" + "f" * 64
    elif change == "intent":
        records[0]["intent_ref"] = "sha256:" + "f" * 64
    elif change == "duplicate":
        records.append(copy.deepcopy(records[-1]))
    elif change == "pending":
        records[-1]["closed"] = False
    elif change == "terminal":
        del binding["terminal_evidence"][records[-1]["run_id"]]
    elif change == "missing":
        del states[records[-1]["run_id"]]
    else:
        states["unrelated"] = states[records[-1]["run_id"]]
    with pytest.raises((ValueError, budget._RecoveryRequired, KisPaperPortfolioBudgetError)):
        project(binding, states)


@pytest.mark.parametrize(
    "field,bad",
    [("quantity", D(0)), ("gross_amount", D("110")), ("identity_ref", "sha256:" + "f" * 64)],
)
def test_mutated_cumulative_or_unmatched_quantity_is_rejected(field, bad):
    binding, states = pair()
    exit_state = states[binding["qqq"]["orders"][-1]["run_id"]]
    object.__setattr__(exit_state.cumulative_fill, field, bad)
    with pytest.raises((ValueError, budget._RecoveryRequired, KisPaperPortfolioBudgetError)):
        project(binding, states)


def test_unrelated_spy_or_legacy_state_is_not_a_prerequisite_for_qqq_accounting():
    binding, states = pair()
    expected = project(binding, states)
    binding["orders"] = [{"unrelated_spy": "not part of supplied owner"}]
    binding["legacy_spy"] = {"unrelated_legacy": "unknown"}
    assert project(binding, states) == expected


def test_fill_cannot_manufacture_independent_account_proof():
    binding, states = pair()
    with pytest.raises(ValueError, match="binding_invalid"):
        project(binding, states, expected_account_ref="b" * 64)


def test_future_as_of_and_reordered_execution_refs_fail():
    binding, states = pair()
    with pytest.raises((ValueError, KisPaperPortfolioBudgetError)):
        project(binding, states, as_of=BASIS.frozen_at)
    binding["qqq"]["orders"].reverse()
    with pytest.raises((ValueError, budget._RecoveryRequired, KisPaperPortfolioBudgetError)):
        project(binding, states)


@pytest.mark.parametrize("status", ["conflict", "identity_mismatch"])
def test_later_contradiction_cannot_reuse_retained_totals(status):
    binding, states = pair()
    key = binding["qqq"]["orders"][-1]["run_id"]
    states[key] = replace(
        states[key], fill_observation_status=status, fill_observed_at=states[key].updated_at
    )
    with pytest.raises(ValueError, match="fill_conflict"):
        project(binding, states)


def test_coherent_pair_reset_fails_independently_frozen_owner_reference():
    binding, states = pair()
    frozen_owner = binding["qqq"]["owner_ref"]
    key = binding["qqq"]["orders"][-1]["run_id"]
    changed = replace(states[key], intent=replace(states[key].intent, decision_id="decision-reset"))
    states[key] = changed
    binding["qqq"]["orders"][-1]["intent_ref"] = changed.intent.fingerprint
    binding["terminal_evidence"][key] = budget._terminal_payload(changed)
    binding["qqq"]["owner_ref"] = budget._owner(
        binding, budget._owner_id(binding, CYCLE), "QQQ", "NASD", binding["qqq"]["orders"]
    ).fingerprint
    with pytest.raises(KisPaperPortfolioBudgetError, match="owner_binding_mismatch"):
        project(binding, states, expected_owner_ref=frozen_owner)


def test_coherent_basis_reset_fails_independently_frozen_basis_reference():
    binding, states = pair()
    binding["basis_usd"], binding["allocated_usd"] = "20000", "2000"
    binding["basis_ref"] = budget._basis(binding).fingerprint
    with pytest.raises(KisPaperPortfolioBudgetError, match="basis_binding_mismatch"):
        project(binding, states)
