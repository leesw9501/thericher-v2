from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import InvalidOperation

import pytest

from test_kis_paper_budget_strategy import ENV, NOW
from test_kis_paper_budget_strategy import harness as harness
from test_kis_paper_budget_strategy import no_network as no_network
from thericher_v2.execution import kis_paper_budget_strategy as budget

PRIVATE = "synthetic-private-account-token-price-provider-body"


def fail_with(error_type, code=PRIVATE):
    class PrivateError(error_type):
        def __str__(self):
            raise AssertionError("exception text must not be inspected")

    def fail(*args, **kwargs):
        error = PrivateError(code)
        error.args = (PRIVATE,)
        error.diagnostic = {"account": PRIVATE, "upstream_code": PRIVATE}
        error.__cause__ = ValueError(PRIVATE)
        raise error

    return fail


def assert_failure(outcome, stage, category, *, code=None, reason="evidence_unavailable"):
    status = "no_intent" if reason == "daily_input_unavailable" else "recovery_required"
    assert (outcome.status, outcome.reason_code) == (status, reason)
    diagnostic = {"stage": stage, "category": category}
    if code is not None:
        diagnostic["code"] = code
    payload = outcome.safe_payload()
    legacy = replace(outcome, failure_diagnostic=None).safe_payload()
    assert payload == legacy | {"failure_diagnostic": diagnostic}
    encoded = json.dumps({key: value for key, value in payload.items() if key != "observed_at"})
    for private in (PRIVATE, *ENV.values()):
        assert private not in encoded
    return payload


@pytest.mark.parametrize(
    "target,error_type,stage,category,code",
    [
        ("paths", OSError, "paths", "io_error", None),
        ("config", budget.KisPaperReadOnlyError, "config", "readonly_error", "config_missing"),
        ("ownership", KeyError, "ownership", "validation_error", None),
        ("controls", ValueError, "controls", "validation_error", None),
        ("snapshot", budget.KisPaperCanaryError, "account", "canary_error", "auth_rejected"),
        (
            "snapshot",
            budget.KisPaperReadOnlyError,
            "account",
            "readonly_error",
            "orderable_funds_response_incomplete",
        ),
        ("snapshot", budget.KisPaperReadOnlyError, "account", "readonly_error", "balance_rejected"),
        ("book", TypeError, "account", "validation_error", None),
        ("quote", budget.KisPaperCanaryError, "quote", "canary_error", "quote_rejected"),
        ("price", budget.KisPaperQuoteError, "quote", "quote_error", "quote_timestamp_stale"),
        ("price", InvalidOperation, "quote", "decimal_error", None),
        ("prepare", ValueError, "prepare", "validation_error", None),
        ("persist", OSError, "persist", "io_error", None),
        ("order", budget.KisPaperCanaryError, "order", "canary_error", "state_intent_mismatch"),
    ],
)
def test_caught_failure_is_closed_and_retained(
    harness, monkeypatch, target, error_type, stage, category, code
):
    root, client, args = harness
    owner, attribute = {
        "paths": (budget, "_validate_paths"),
        "config": (budget, "load_kis_paper_config_from_environment"),
        "ownership": (budget, "_load_binding"),
        "controls": (budget.PaperExecutionControlStore, "read"),
        "snapshot": (client, "snapshot"),
        "book": (budget, "_spy_book"),
        "quote": (client, "fetch_spy_limit_input"),
        "price": (budget, "derive_kis_paper_marketable_limit"),
        "prepare": (budget, "prepare_kis_paper_decision"),
        "persist": (budget, "_atomic_json"),
        "order": (budget, "_run_kis_paper_canary"),
    }[target]
    fail = fail_with(error_type, code or PRIVATE)
    original_write = budget._atomic_json

    def fail_binding(path, payload):
        if path.name == budget.BUDGET_FILE:
            fail()
        return original_write(path, payload)

    monkeypatch.setattr(owner, attribute, fail_binding if target == "persist" else fail)
    outcome = budget.run_kis_paper_budget_strategy(**args, session_id="diagnostic")
    payload = assert_failure(outcome, stage, category, code=code)
    destination = args["artifact_root"] / "execution/kis-paper-spy-budget/diagnostic/outcome.json"
    if target == "paths":
        assert not destination.exists() and not root.exists()
    else:
        assert json.loads(destination.read_text()) == payload
    assert not client.submits and not client.cancels


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_caught_new_input_error_keeps_no_intent(harness, error_type):
    _root, client, args = harness
    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": fail_with(error_type)}
    )
    assert_failure(
        outcome,
        "new_input",
        "io_error" if error_type is OSError else "validation_error",
        reason="daily_input_unavailable",
    )
    assert not client.calls


def test_binding_failure_keeps_existing_reason(harness):
    root, client, args = harness
    root.mkdir()
    budget._atomic_json(root / budget.BUDGET_FILE, {"private": PRIVATE})
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert_failure(outcome, "ownership", "recovery_required", reason="budget_binding_invalid")
    assert not client.calls


@pytest.mark.parametrize("point", ["run", "finish", "cancel"])
def test_nested_recovery_failure_keeps_pending_identity(harness, monkeypatch, point):
    root, client, args = harness
    client.fill_fraction = 0
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    binding = budget._load_binding(root)
    client.now += timedelta(minutes=6 if point == "cancel" else 1)
    fail = fail_with(budget.KisPaperReadOnlyError, "auth_rejected")
    if point == "run":
        monkeypatch.setattr(budget, "_run_kis_paper_canary", fail)
    elif point == "cancel":
        monkeypatch.setattr(budget, "_cancel_submitted_canary", fail)
    else:
        run = budget._run_kis_paper_canary

        def finish_failure(**kwargs):
            outcome = run(**kwargs)
            monkeypatch.setattr(client, "snapshot", fail)
            return outcome

        monkeypatch.setattr(budget, "_run_kis_paper_canary", finish_failure)
    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda _: pytest.fail("new input before recovery")}
    )
    assert_failure(
        outcome,
        {"run": "reconcile", "finish": "account", "cancel": "order"}[point],
        "readonly_error",
        code="auth_rejected",
    )
    assert budget._load_binding(root) == binding
    assert len(client.submits) == 1 and not client.cancels


@pytest.mark.parametrize("point", ["projection", "account", "ownership", "after_permit"])
def test_nested_permit_failure_and_successful_stage_restore(harness, monkeypatch, point):
    _root, client, args = harness

    def run(**kwargs):
        if point == "projection":
            monkeypatch.setattr(budget, "project_budget", fail_with(ValueError))
        elif point == "account":
            monkeypatch.setattr(
                client, "snapshot", fail_with(budget.KisPaperReadOnlyError, "balance_rejected")
            )
        elif point == "ownership":
            client.foreign = 1
        assert kwargs["submit_permitted"](NOW)
        fail_with(ValueError)()

    monkeypatch.setattr(budget, "_run_kis_paper_canary", run)
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert_failure(
        outcome,
        {
            "projection": "ownership",
            "account": "account",
            "ownership": "ownership",
            "after_permit": "order",
        }[point],
        {"account": "readonly_error", "ownership": "recovery_required"}.get(
            point, "validation_error"
        ),
        code="balance_rejected" if point == "account" else None,
        reason="pre_submit_ownership_changed" if point == "ownership" else "evidence_unavailable",
    )
    assert not client.submits and not client.cancels


@pytest.mark.parametrize(
    "error_type",
    [budget.KisPaperCanaryError, budget.KisPaperReadOnlyError, budget.KisPaperQuoteError],
)
def test_unknown_typed_codes_never_escape(harness, monkeypatch, error_type):
    _root, client, args = harness
    monkeypatch.setattr(client, "snapshot", fail_with(error_type))
    outcome = budget.run_kis_paper_budget_strategy(**args)
    payload = assert_failure(
        outcome, "account", budget._failure_category(error_type(PRIVATE)).value
    )
    assert "code" not in payload["failure_diagnostic"]


def test_generic_exception_cannot_supply_a_typed_code(harness, monkeypatch):
    _root, client, args = harness

    def fail():
        error = ValueError(PRIVATE)
        error.code = "auth_rejected"
        raise error

    monkeypatch.setattr(client, "snapshot", fail)
    assert_failure(budget.run_kis_paper_budget_strategy(**args), "account", "validation_error")


@pytest.mark.parametrize("unsafe", [PRIVATE, {"secret": PRIVATE}, None])
def test_failure_payload_serialization_is_closed(unsafe):
    outcome = budget.KisPaperBudgetOutcome(
        "recovery_required",
        "evidence_unavailable",
        NOW,
        failure_diagnostic={"stage": unsafe, "category": unsafe, "code": unsafe, "raw": PRIVATE},
    )
    assert outcome.safe_payload()["failure_diagnostic"] == {
        "stage": "unrecognized",
        "category": "unrecognized",
    }
    assert PRIVATE not in json.dumps(outcome.safe_payload())


def test_failure_outcome_write_error_does_not_replace_original_diagnostic(harness, monkeypatch):
    _root, client, args = harness
    monkeypatch.setattr(client, "snapshot", fail_with(budget.KisPaperCanaryError, "auth_rejected"))
    monkeypatch.setattr(budget, "_atomic_json", fail_with(OSError))
    assert_failure(
        budget.run_kis_paper_budget_strategy(**args),
        "account",
        "canary_error",
        code="auth_rejected",
    )


@pytest.mark.parametrize(
    "status,reason",
    [
        ("recovery_required", "evidence_unavailable"),
        ("preview", "preview"),
        ("pending", "exact_fill_unavailable"),
        ("order_complete", "exact_order_and_position_reconciled"),
    ],
)
def test_legacy_outcome_payload_is_unchanged(status, reason):
    assert budget.KisPaperBudgetOutcome(status, reason, NOW).safe_payload() == {
        "kind": "kis_paper_spy_budget_strategy",
        "status": status,
        "reason_code": reason,
        "observed_at": NOW.isoformat(),
        "paper_only": True,
        "allocation_fraction": "0.10",
        "decision_use": "existing_baseline_direction_only",
        "basis": "provisional_usd_orderable_funds_not_settled_cash",
        "net_pnl": "not_observed",
    }


def test_successful_run_does_not_gain_failure_diagnostic(harness):
    _root, _client, args = harness
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert outcome.status == "order_complete"
    assert outcome.failure_diagnostic is None
    assert "failure_diagnostic" not in outcome.safe_payload()
