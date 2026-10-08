from __future__ import annotations

import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe, decision_instrument_binding_ref
from thericher_v2.data.kis_paper_daily_spy_input import KisPaperDailySpyInput
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryReconciliation,
    KisPaperCanaryStateStore,
    _redacted_open_order_reference,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt, _derive_decision_id
from thericher_v2.research.kis_paper_daily_spy_baseline import (
    evaluate_kis_paper_daily_spy_baseline,
)

D = Decimal
NOW = datetime(2026, 9, 22, 14, 30, tzinfo=UTC)
ENV = {
    "KIS_PAPER_APP_KEY": "test-key",
    "KIS_PAPER_APP_SECRET": "test-secret",
    "KIS_PAPER_ACCOUNT_NO": "12345678",
    "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
}


def receipt(
    at,
    action="enter",
    digit="a",
    symbol="SPY",
    *,
    input_status="ready",
    reason_class=None,
    valid_until=None,
):
    fields = dict(
        campaign_ref="ref:" + digit * 64,
        model_ref="ref:" + "2" * 64,
        input_manifest_ref="sha256:" + "3" * 64,
        proposal_ref="ref:" + "4" * 64,
        decision_class=action,
        input_status=input_status,
        decided_at=at,
        valid_until=valid_until if valid_until is not None else at + timedelta(minutes=10),
        reason_class=reason_class or "eligible_" + action,
        instrument_binding_ref=decision_instrument_binding_ref(
            symbol=symbol,
            market="US",
            decision_class=action,
        ),
        target_binding_ref="ref:" + "5" * 64,
        schema_version=1,
    )
    return ResearchDecisionReceipt(decision_id=_derive_decision_id(**fields), **fields)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("budget tests must not use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


class Broker(KisPaperCanaryClient):
    def __init__(self, root):
        super().__init__(config=KisPaperConfig(*ENV.values()), transport=None)
        self.root = root
        self.now = NOW
        self.funds = D(100000)
        self.foreign = D(0)
        self.orders = {}
        self.submits = []
        self.cancels = []
        self.calls = []
        self.fill_fraction = D(1)
        self.price_improvement = D(0)
        self.history_status = "available"
        self.history_remaining = True
        self.reject = False
        self.crash = False
        self.fail_unknown = False
        self.quote_age = 0
        self.before_submit = None

    def snapshot(self):
        self.calls.append("snapshot")
        quantity = self.foreign + sum(
            (o["filled"] * (1 if o["intent"].side == "buy" else -1) for o in self.orders.values()),
            D(0),
        )
        positions = (
            ()
            if quantity == 0
            else (KisPaperPosition("SPY", "AMEX", "USD", quantity, D(600), D(600), self.now),)
        )
        opens = tuple(
            KisPaperOpenOrder(
                _redacted_open_order_reference(o["id"]),
                "SPY",
                "AMEX",
                "USD",
                o["intent"].side,
                o["intent"].quantity,
                o["filled"],
                o["remaining"],
                o["intent"].limit_price,
                self.now,
            )
            for o in self.orders.values()
            if o["remaining"]
        )
        return KisPaperReadOnlySnapshot(
            KisPaperAccountIdentity(self._config.masked_account_identity, self.now),
            KisPaperCashSnapshot("USD", self.funds, self.now),
            KisPaperOrderableFundsSnapshot("USD", self.funds, "AMEX", "SPY", D(600), self.now),
            positions,
            KisPaperOpenOrdersSnapshot(opens, self.now),
            self.now,
        )

    def fetch_spy_limit_input(self, *, observed_at):
        self.calls.append("quote")
        return KisPaperSpyLimitInput(
            D(600),
            2,
            D("0.01"),
            observed_at - timedelta(seconds=self.quote_age),
            best_bid=D("599.99"),
            best_ask=D("600.01"),
        )

    def submit_limit(self, intent, **kwargs):
        state = KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started"
        binding = budget._load_binding(self.root)
        assert binding["orders"][-1]["intent_ref"] == intent.fingerprint
        projection = budget.project_budget(self.root, binding)
        assert projection.entry_cost + projection.reserved_buys <= D(binding["allocated_usd"])
        if self.before_submit:
            self.before_submit()
        self.submits.append(intent)
        if self.reject:
            return False, None
        filled = (intent.quantity * self.fill_fraction).to_integral_value(rounding="ROUND_FLOOR")
        self.orders[intent.run_id] = {
            "intent": intent,
            "filled": filled,
            "remaining": intent.quantity - filled,
            "id": "TEST-" + str(len(self.submits)),
            "price": intent.limit_price - self.price_improvement,
        }
        if self.crash:
            raise RuntimeError("simulated process crash")
        if self.fail_unknown:
            raise KisPaperCanaryError("submit_transport_unknown")
        return True, self.orders[intent.run_id]["id"]

    def reconcile(self, state, *, now):
        self.calls.append("reconcile")
        order = self.orders.get(state.intent.run_id)
        known = order is not None and state.broker_order_id == order["id"]
        observation = None
        if known:
            fill = None
            if self.history_status == "available":
                fill = KisPaperCumulativeFill(
                    identity_ref=fill_identity_ref(
                        raw_order_id=order["id"],
                        order_at=state.submission_started_at,
                        symbol="SPY",
                        exchange="AMEX",
                        side=state.intent.side,
                        quantity=state.intent.quantity,
                    ),
                    requested_quantity=state.intent.quantity,
                    quantity=order["filled"],
                    gross_amount=order["filled"] * order["price"],
                    observed_at=now,
                    remaining_quantity=order["remaining"] if self.history_remaining else None,
                )
            observation = KisPaperExecutionObservation(1, True, self.history_status, fill, now)
        return KisPaperCanaryReconciliation(
            snapshot=self.snapshot(),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["remaining"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )

    def cancel_order(self, intent, *, broker_order_id):
        order = self.orders[intent.run_id]
        assert order["id"] == broker_order_id
        self.cancels.append(intent.run_id)
        order["remaining"] = D(0)
        return True


@pytest.fixture
def harness(tmp_path):
    root = tmp_path / "private"
    client = Broker(root)
    args = dict(
        environment=ENV,
        state_root=root,
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "controls.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        client=client,
        clock=lambda: client.now,
        receipt_loader=lambda at: receipt(at),
    )
    return root, client, args


def test_fixed_budget_sizes_more_than_one_and_duplicate_decision_is_not_resubmitted(harness):
    root, client, args = harness
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert outcome.status == "order_complete"
    assert client.submits[0].quantity == 16
    binding = budget._load_binding(root)
    assert D(binding["allocated_usd"]) == 10000
    assert budget.project_budget(root, binding).quantity == 16
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "target_already_satisfied"
    assert len(client.submits) == 1
    serialized = json.dumps(outcome.safe_payload())
    assert (
        "100000" not in serialized
        and "TEST-" not in serialized
        and ENV["KIS_PAPER_APP_KEY"] not in serialized
    )


def test_sell_releases_entry_cost_not_proceeds_and_budget_does_not_grow(harness):
    root, client, args = harness
    client.price_improvement = D("0.5")
    for enter_digit, exit_digit in (("a", "b"), ("c", "d"), ("e", "f")):
        assert (
            budget.run_kis_paper_budget_strategy(
                **{**args, "receipt_loader": lambda at, digit=enter_digit: receipt(at, digit=digit)}
            ).status
            == "order_complete"
        )
        client.funds *= 2
        assert (
            budget.run_kis_paper_budget_strategy(
                **{
                    **args,
                    "receipt_loader": lambda at, digit=exit_digit: receipt(at, "exit", digit),
                }
            ).status
            == "order_complete"
        )
        binding = budget._load_binding(root)
        projection = budget.project_budget(root, binding)
        assert projection.quantity == projection.entry_cost == projection.reserved_buys == 0
        assert D(binding["allocated_usd"]) == 10000
    assert all(o.quantity == 16 for o in client.submits)


def test_pending_reservation_survives_restart_and_recovers_before_missing_signal(harness):
    root, client, args = harness
    client.fill_fraction = D("0.5")
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    projection = budget.project_budget(root, budget._load_binding(root))
    assert projection.quantity == 8
    assert projection.entry_cost + projection.reserved_buys == D("9600.16")

    def no_input(at):
        raise ValueError("missing data")

    client.now += timedelta(seconds=10)
    assert (
        budget.run_kis_paper_budget_strategy(**{**args, "receipt_loader": no_input}).status
        == "pending"
    )
    assert len(client.submits) == 1
    order = next(iter(client.orders.values()))
    order["filled"], order["remaining"] = D(16), D(0)
    client.now += timedelta(seconds=10)
    outcome = budget.run_kis_paper_budget_strategy(**{**args, "receipt_loader": no_input})
    assert outcome.reason_code == "daily_input_unavailable"
    assert budget._load_binding(root)["orders"][-1]["closed"]


def test_old_partial_cancel_releases_only_observed_residual_and_keeps_owned_shares(harness):
    root, client, args = harness
    client.fill_fraction = D("0.5")
    budget.run_kis_paper_budget_strategy(**args)
    client.now += timedelta(minutes=6)
    assert (
        budget.run_kis_paper_budget_strategy(**args).reason_code
        == "own_order_cancellation_observed"
    )
    assert len(client.cancels) == 1
    client.now += timedelta(seconds=20)
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert outcome.reason_code == "target_already_satisfied"
    projection = budget.project_budget(root, budget._load_binding(root))
    assert projection.quantity == 8 and projection.reserved_buys == 0
    client.fill_fraction = D(1)
    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda at: receipt(at, "exit", "b")}
    )
    assert outcome.status == "order_complete" and client.submits[-1].quantity == 8


def test_unknown_remaining_is_not_terminal(harness):
    root, client, args = harness
    client.fill_fraction = D("0.5")
    client.history_remaining = False
    budget.run_kis_paper_budget_strategy(**args)
    next(iter(client.orders.values()))["remaining"] = D(0)
    client.now += timedelta(seconds=20)
    assert (
        budget.run_kis_paper_budget_strategy(**args).reason_code == "remaining_quantity_unresolved"
    )
    assert not budget._load_binding(root)["orders"][-1]["closed"]
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys > 0


@pytest.mark.parametrize(
    "status", ["absent", "ambiguous", "identity_mismatch", "fields_invalid", "unavailable"]
)
def test_bad_fill_does_not_claim_completion_or_replace_intent(harness, status):
    root, client, args = harness
    client.history_status = status
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    assert len(client.submits) == 1
    assert not budget._load_binding(root)["orders"][-1]["closed"]


def test_crash_after_post_before_ack_never_posts_again(harness):
    root, client, args = harness
    client.crash = True
    with pytest.raises(RuntimeError, match="simulated"):
        budget.run_kis_paper_budget_strategy(**args)
    client.crash = False
    client.now += timedelta(days=1)
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert outcome.status == "pending" and len(client.submits) == 1
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys > 0


@pytest.mark.parametrize("action", ["enter", "exit"])
def test_never_adopts_inherited_spy(harness, action):
    root, client, args = harness
    client.foreign = D(7)
    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda at: receipt(at, action)}
    )
    assert outcome.reason_code == "existing_inventory_or_order_conflict"
    assert not client.submits and not (root / budget.BUDGET_FILE).exists()


def test_other_spy_submit_conflicts_only_while_owned(harness):
    root, client, args = harness
    assert not budget.conflicts_with_budget_strategy(root, "legacy", "SPY")
    budget.run_kis_paper_budget_strategy(**args)
    assert budget.conflicts_with_budget_strategy(root, "legacy", "SPY")
    assert not budget.conflicts_with_budget_strategy(root, "legacy", "QQQ")
    budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda at: receipt(at, "exit", "b")}
    )
    assert not budget.conflicts_with_budget_strategy(root, "legacy", "SPY")
    assert budget.conflicts_with_budget_strategy(root, client.submits[0].run_id, "SPY")


def test_concurrent_visits_serialize_one_submission(harness):
    _root, client, args = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: budget.run_kis_paper_budget_strategy(**args), range(2)))
    assert len(client.submits) == 1
    assert {o.status for o in outcomes} == {"order_complete", "no_intent"}


@pytest.mark.parametrize("change", ["basis", "account", "missing_state", "fingerprint"])
def test_private_binding_corruption_does_not_reset_budget(harness, change):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    if change == "basis":
        binding["basis_usd"] = "9999999"
    elif change == "account":
        binding["account_ref"] = "0" * 64
    elif change == "fingerprint":
        binding["orders"][0]["intent_ref"] = "sha256:" + "0" * 64
    else:
        (root / (binding["orders"][0]["run_id"] + ".json")).unlink()
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    assert budget.run_kis_paper_budget_strategy(**args).status == "recovery_required"
    assert len(client.submits) == 1


def test_preview_and_closed_empty_mode_do_not_read_credentials_or_signal(harness):
    root, client, args = harness

    def forbidden(_at):
        pytest.fail("unexpected signal read")

    assert (
        budget.run_kis_paper_budget_strategy(
            **{**args, "execute": False, "environment": {}, "receipt_loader": forbidden}
        ).status
        == "preview"
    )
    client.now = NOW.replace(hour=3)
    assert (
        budget.run_kis_paper_budget_strategy(
            **{**args, "environment": {}, "receipt_loader": forbidden}
        ).status
        == "not_due"
    )
    assert not client.calls and not root.exists()


def test_live_mode_and_mismatching_injected_account_never_use_client(harness):
    _root, client, args = harness
    assert (
        budget.run_kis_paper_budget_strategy(
            **{**args, "environment": {"THERICHER_MODE": "kis_live"}}
        ).reason_code
        == "live_mode_unavailable"
    )
    client._config = replace(client._config, account_number="87654321")
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "account_binding_mismatch"
    assert not client.calls


def test_unqualified_or_wrong_instrument_receipt_never_submits(harness):
    _root, client, args = harness
    wrong = receipt(NOW, symbol="QQQ")
    outcome = budget.run_kis_paper_budget_strategy(**{**args, "receipt_loader": lambda _: wrong})
    assert outcome.reason_code == "receipt_binding_mismatch" and not client.submits


def test_low_funds_and_stale_quote_do_not_submit(harness):
    _root, client, args = harness
    client.funds = D(100)
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "budget_below_one_share"
    client.quote_age = 121
    assert budget.run_kis_paper_budget_strategy(**args).status == "recovery_required"
    assert not client.submits


def test_rejected_intent_releases_reservation_without_fake_fill(harness):
    root, client, args = harness
    client.reject = True
    outcome = budget.run_kis_paper_budget_strategy(**args)
    assert outcome.reason_code == "order_not_submitted_or_rejected"
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys == 0
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "decision_already_processed"


def test_lost_budget_binding_cannot_reinitialize_from_larger_funds(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    (root / budget.BUDGET_FILE).unlink()
    client.funds *= 2
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "budget_binding_missing"
    assert budget.conflicts_with_budget_strategy(root, "unrelated", "SPY")
    assert len(client.submits) == 1


def test_closed_flag_alone_cannot_release_reservation(harness):
    root, client, args = harness
    client.fill_fraction = D(0)
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    binding["orders"][-1]["closed"] = True
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    assert (
        budget.run_kis_paper_budget_strategy(**args).reason_code == "closed_order_evidence_missing"
    )
    assert len(client.submits) == 1


def test_crash_before_binding_has_no_post_and_recovers_orphan_intent(harness, monkeypatch):
    root, client, args = harness
    original = budget._atomic_json

    def interrupted(path, payload):
        if path.name == budget.BUDGET_FILE and payload["orders"]:
            raise RuntimeError("simulated metadata crash")
        return original(path, payload)

    monkeypatch.setattr(budget, "_atomic_json", interrupted)
    with pytest.raises(RuntimeError, match="metadata crash"):
        budget.run_kis_paper_budget_strategy(**args)
    assert not client.submits
    monkeypatch.setattr(budget, "_atomic_json", original)
    assert budget.run_kis_paper_budget_strategy(**args).status == "order_complete"
    assert len(client.submits) == 1


def test_signal_from_previous_day_does_not_skip_owned_order_recovery(harness):
    root, client, args = harness
    client.fill_fraction = D(0)
    budget.run_kis_paper_budget_strategy(**args)
    client.now += timedelta(days=1)
    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda _: pytest.fail("signal before recovery")}
    )
    assert outcome.reason_code == "own_order_cancellation_observed"
    assert len(client.submits) == 1 and len(client.cancels) == 1


@pytest.mark.parametrize("name", [".", "..", "../escape", "a/b"])
def test_invalid_session_path_is_rejected_without_io(harness, name):
    root, client, args = harness
    with pytest.raises(ValueError, match="identity"):
        budget.run_kis_paper_budget_strategy(**{**args, "session_id": name})
    assert not root.exists() and not client.calls


def test_invalid_owned_private_state_is_a_scoped_spy_conflict(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    (root / (binding["orders"][0]["run_id"] + ".json")).write_text("invalid synthetic state")
    assert budget.conflicts_with_budget_strategy(root, "legacy", "SPY")
    assert not budget.conflicts_with_budget_strategy(root, "legacy", "QQQ")


@pytest.mark.parametrize(
    "input_status,action,reason_class,decision_offset,validity_offset,failed_predicate",
    [
        (status, "abstain", "input_unavailable", 0, 0, "input_status")
        for status in (
            "missing",
            "stale",
            "incomplete",
            "duplicate",
            "non_contiguous",
            "misaligned",
            "future",
            "unqualified",
        )
    ]
    + [
        ("ready", "abstain", reason, 0, 0, "decision_class")
        for reason in ("model_abstain", "non_entry_proposal")
    ]
    + [
        ("ready", action, "eligible_" + action, start, end, failure)
        for action in ("enter", "exit")
        for start, end, failure in (
            (1, 600, "future_decision"),
            (-600, 0, "expired_validity"),
            (-600, -1, "expired_validity"),
            (0, 0, "expired_validity"),
        )
    ],
)
def test_daily_receipt_diagnostic_preserves_rejection_and_short_circuit_clock(
    harness,
    input_status,
    action,
    reason_class,
    decision_offset,
    validity_offset,
    failed_predicate,
):
    root, client, args = harness
    signal = receipt(
        NOW + timedelta(microseconds=decision_offset),
        action,
        input_status=input_status,
        reason_class=reason_class,
        valid_until=NOW + timedelta(microseconds=validity_offset),
    )
    expected_clock_calls = 4 if failed_predicate in {"input_status", "decision_class"} else 5
    clock_calls = []

    def clock():
        clock_calls.append(None)
        # Outcome serialization must not reclassify using this later timestamp.
        return NOW + timedelta(minutes=20) if len(clock_calls) >= expected_clock_calls else NOW

    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda _: signal, "clock": clock, "session_id": "diagnostic"}
    )
    assert (outcome.status, outcome.reason_code) == ("no_intent", "daily_receipt_not_eligible")
    payload = outcome.safe_payload()
    assert payload["daily_receipt_diagnostic"] == {
        "failed_predicate": failed_predicate,
        "input_status": input_status,
        "decision_class": action,
        "reason_class": reason_class,
    }
    assert len(clock_calls) == expected_clock_calls
    assert not client.calls and not client.submits and not client.cancels
    assert not (root / budget.BUDGET_FILE).exists() and not list(root.glob("bs-*.json"))
    destination = args["artifact_root"] / "execution/kis-paper-spy-budget/diagnostic/outcome.json"
    assert json.loads(destination.read_text()) == payload
    assert signal.decision_id not in json.dumps(payload)
    assert signal.input_manifest_ref not in json.dumps(payload)


@pytest.mark.parametrize("action", ["enter", "exit"])
@pytest.mark.parametrize("decision_offset,validity_offset", [(0, 1), (-600, 1)])
def test_daily_receipt_eligible_time_boundaries_do_not_gain_diagnostic(
    harness,
    action,
    decision_offset,
    validity_offset,
):
    _root, client, args = harness
    # Stop an eligible receipt at the existing account-conflict check.
    client.foreign = D(7)
    signal = receipt(
        NOW + timedelta(microseconds=decision_offset),
        action,
        valid_until=NOW + timedelta(microseconds=validity_offset),
    )
    outcome = budget.run_kis_paper_budget_strategy(**{**args, "receipt_loader": lambda _: signal})
    assert outcome.reason_code == "existing_inventory_or_order_conflict"
    assert "daily_receipt_diagnostic" not in outcome.safe_payload()
    assert client.calls == ["snapshot"] and not client.submits


@pytest.mark.parametrize(
    "unsafe", ["raw_error_account_12345678_price_600.01", {"secret": "x"}, None]
)
def test_daily_receipt_diagnostic_serialization_is_closed(unsafe):
    diagnostic = dict.fromkeys(
        ("failed_predicate", "input_status", "decision_class", "reason_class"), unsafe
    )
    diagnostic["price"] = "600.01"
    diagnostic["decision_id"] = "private-id"
    diagnostic["error"] = "raw-provider-error"
    outcome = budget.KisPaperBudgetOutcome(
        "no_intent", "daily_receipt_not_eligible", NOW, diagnostic
    )
    assert outcome.safe_payload()["daily_receipt_diagnostic"] == {
        "failed_predicate": "unrecognized",
        "input_status": "unrecognized",
        "decision_class": "unrecognized",
        "reason_class": "unrecognized",
    }
    for status, reason in (("preview", "preview"), ("no_intent", "daily_input_unavailable")):
        assert (
            "daily_receipt_diagnostic"
            not in replace(outcome, status=status, reason_code=reason).safe_payload()
        )


def test_legacy_budget_outcome_payload_is_unchanged():
    assert budget.KisPaperBudgetOutcome(
        "no_intent", "daily_receipt_not_eligible", NOW
    ).safe_payload() == {
        "kind": "kis_paper_spy_budget_strategy",
        "status": "no_intent",
        "reason_code": "daily_receipt_not_eligible",
        "observed_at": NOW.isoformat(),
        "paper_only": True,
        "allocation_fraction": "0.10",
        "decision_use": "existing_baseline_direction_only",
        "basis": "provisional_usd_orderable_funds_not_settled_cash",
        "net_pnl": "not_observed",
    }


@pytest.mark.parametrize(
    "previous_day,last_day,available_at,status,proposal_reason",
    [
        (18, 21, NOW, "future", "daily_input_not_yet_available"),
        (17, 18, NOW - timedelta(days=1), "stale", "daily_input_execution_window_expired"),
        (17, 18, NOW, "stale", "daily_input_available_after_execution_session"),
        (17, 21, NOW - timedelta(hours=1), "non_contiguous", "daily_input_sessions_non_contiguous"),
    ],
)
def test_baseline_input_failures_keep_only_the_available_closed_receipt_reason(
    harness,
    previous_day,
    last_day,
    available_at,
    status,
    proposal_reason,
):
    root, client, args = harness
    bars = tuple(
        Bar(
            symbol="SPY",
            market="US",
            timeframe=Timeframe.D1,
            start_ts=NOW.replace(day=day, hour=0, minute=0),
            open=D(600),
            high=D(602),
            low=D(599),
            close=D(601),
            volume=D(1000),
            complete=True,
        )
        for day in (previous_day, last_day)
    )
    input = KisPaperDailySpyInput(
        bars=bars,
        catalog_dataset_id="synthetic-daily",
        catalog_dataset_hash="sha256:" + "a" * 64,
        last_consumed_session=bars[-1].start_ts.date(),
        first_available_at=available_at,
        input_manifest_ref="sha256:" + "b" * 64,
        availability_record_path=root / "unused.json",
    )
    evaluation = evaluate_kis_paper_daily_spy_baseline(input, as_of=NOW)
    assert evaluation.proposal.reason == proposal_reason
    outcome = budget.run_kis_paper_budget_strategy(
        **{**args, "receipt_loader": lambda _: evaluation.receipt}
    )
    assert (outcome.status, outcome.reason_code) == ("no_intent", "daily_receipt_not_eligible")
    assert outcome.safe_payload()["daily_receipt_diagnostic"] == {
        "failed_predicate": "input_status",
        "input_status": status,
        "decision_class": "abstain",
        "reason_class": "input_unavailable",
    }
    assert not client.calls and not (root / budget.BUDGET_FILE).exists()


@pytest.mark.parametrize(
    "quantity",
    [D(0), D(-1), D("1.5"), D("NaN"), D("sNaN"), D("Infinity"), 1, 1.0, True, "1"],
)
def test_invalid_spy_reduction_is_rejected_before_io(harness, quantity):
    root, client, args = harness
    with pytest.raises(ValueError, match="SPY reduction quantity invalid"):
        budget.run_kis_paper_budget_strategy(**args, spy_reduction_quantity=quantity)
    assert not root.exists() and not client.calls


def test_spy_reduction_cannot_change_qqq_route(harness):
    root, client, args = harness
    with pytest.raises(ValueError, match="SPY reduction quantity invalid"):
        budget.run_kis_paper_budget_strategy(
            **args, qqq_cycle_id="synthetic-unit", spy_reduction_quantity=D(1)
        )
    assert not root.exists() and not client.calls


def test_spy_reduction_requires_exit_and_never_creates_buy(harness):
    root, client, args = harness
    outcome = budget.run_kis_paper_budget_strategy(**args, spy_reduction_quantity=D(1))
    assert (outcome.status, outcome.reason_code) == ("no_intent", "spy_reduction_requires_exit")
    assert not client.calls and not (root / budget.BUDGET_FILE).exists()


def test_spy_trim_then_default_full_exit_preserves_original_basis(harness):
    root, client, args = harness
    assert budget.run_kis_paper_budget_strategy(**args).status == "order_complete"
    original = budget._load_binding(root)
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D("4.0")}
    assert budget.run_kis_paper_budget_strategy(**trim_args).status == "order_complete"
    retained = budget._load_binding(root)
    assert client.submits[-1].side == "sell" and client.submits[-1].quantity == 4
    assert budget.project_budget(root, retained).quantity == 12
    assert {key: retained[key] for key in ("account_ref", "basis_usd", "allocated_usd", "at")} == {
        key: original[key] for key in ("account_ref", "basis_usd", "allocated_usd", "at")
    }
    assert (
        budget.run_kis_paper_budget_strategy(**trim_args).reason_code
        == "decision_already_processed"
    )
    assert len(client.submits) == 2
    assert budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda at: receipt(at, "exit", "c")})
    ).status == "order_complete"
    assert client.submits[-1].quantity == 12
    assert budget.project_budget(root, budget._load_binding(root)).quantity == 0


@pytest.mark.parametrize("owned", [False, True])
def test_spy_trim_never_clips_or_adopts_foreign_inventory(harness, owned):
    root, client, args = harness
    if owned:
        budget.run_kis_paper_budget_strategy(**args)
    else:
        client.foreign = D(17)
    before = (root / budget.BUDGET_FILE).read_bytes() if owned else None
    client.calls.clear()
    outcome = budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda at: receipt(at, "exit", "b")}),
        spy_reduction_quantity=D(17),
    )
    assert outcome.reason_code == (
        "spy_reduction_exceeds_owned_quantity" if owned else "existing_inventory_or_order_conflict"
    )
    assert "quote" not in client.calls and len(client.submits) == int(owned)
    if owned:
        assert (root / budget.BUDGET_FILE).read_bytes() == before
    else:
        assert not (root / budget.BUDGET_FILE).exists() and not list(root.glob("bs-*.json"))


@pytest.mark.parametrize("closed,trim_quantity", [(False, D(4)), (True, D(4)), (True, D(16))])
def test_retained_trim_rejects_changed_quantity_before_recovery_or_new_read(
    harness, closed, trim_quantity,
):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    client.fill_fraction = D(1) if closed else D("0.5")
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": trim_quantity}
    budget.run_kis_paper_budget_strategy(**trim_args)
    intent = client.submits[-1]
    before = (root / budget.BUDGET_FILE).read_bytes()
    state_before = (root / (intent.run_id + ".json")).read_bytes()
    client.calls.clear()
    client.now += timedelta(minutes=6)
    # An exact closed decision remains eligible only for this synthetic check.
    client.now = NOW if closed else client.now
    outcome = budget.run_kis_paper_budget_strategy(
        **(trim_args | {"spy_reduction_quantity": trim_quantity + 1})
    )
    assert (outcome.status, outcome.reason_code) == (
        "recovery_required", "spy_reduction_quantity_mismatch"
    )
    assert not client.calls and not client.cancels and len(client.submits) == 2
    assert (root / budget.BUDGET_FILE).read_bytes() == before
    assert (root / (intent.run_id + ".json")).read_bytes() == state_before


def _v2_trim_binding(root, client):
    binding = budget._load_binding(root)
    return budget._migrate_binding(
        root, binding, client._config, "synthetic-unit", as_of=client.now
    )


@pytest.mark.parametrize("omit_quantity", [False, True])
def test_partial_trim_restart_credits_only_observed_cumulative_sale(harness, omit_quantity):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    binding = _v2_trim_binding(root, client)
    before = budget.project_budget(root, binding, as_of=client.now)
    trim = receipt(client.now, "exit", "b")
    client.fill_fraction = D("0.5")
    assert budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda _: trim}), spy_reduction_quantity=D(4)
    ).status == "pending"
    intent = client.submits[-1]
    after = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    assert after.quantity == 14
    assert after.gross_cash == before.gross_cash + D(2) * intent.limit_price
    assert after.entry_cost == before.entry_cost * D(14) / D(16)
    after_binding = budget._load_binding(root)
    assert after_binding["basis_ref"] == binding["basis_ref"]
    assert after_binding["qqq"] == binding["qqq"]
    restart = args | {"receipt_loader": lambda _: pytest.fail("pending recovery skipped")}
    if not omit_quantity:
        restart["spy_reduction_quantity"] = D(4)
    client.now += timedelta(seconds=10)
    assert budget.run_kis_paper_budget_strategy(**restart).status == "pending"
    assert len(client.submits) == 2
    assert (
        budget.project_budget(root, budget._load_binding(root), as_of=client.now).gross_cash
        == after.gross_cash
    )
    client.orders[intent.run_id]["filled"] = D(4)
    client.orders[intent.run_id]["remaining"] = D(0)
    client.now += timedelta(seconds=10)
    outcome = budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda _: trim}),
        **({} if omit_quantity else {"spy_reduction_quantity": D(4)}),
    )
    assert outcome.reason_code == "decision_already_processed"
    final = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    assert final.quantity == 12
    assert final.gross_cash == before.gross_cash + D(4) * intent.limit_price
    assert len(client.submits) == 2


def test_unknown_trim_submission_never_reposts_or_credits_unobserved_sale(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    binding = _v2_trim_binding(root, client)
    before = budget.project_budget(root, binding, as_of=client.now)
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D(4)}
    client.crash = True
    with pytest.raises(RuntimeError, match="simulated process crash"):
        budget.run_kis_paper_budget_strategy(**trim_args)
    client.crash = False
    client.now += timedelta(seconds=10)
    assert budget.run_kis_paper_budget_strategy(**trim_args).status == "pending"
    projected = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    assert projected.quantity == before.quantity and projected.gross_cash == before.gross_cash
    assert len(client.submits) == 2


def test_orphan_trim_is_immutable_and_reuses_original_intent(harness, monkeypatch):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D(4)}
    original = budget._atomic_json

    def interrupted(path, payload):
        if path.name == budget.BUDGET_FILE and len(payload["orders"]) == 2:
            raise RuntimeError("trim binding crash")
        return original(path, payload)

    monkeypatch.setattr(budget, "_atomic_json", interrupted)
    with pytest.raises(RuntimeError, match="trim binding crash"):
        budget.run_kis_paper_budget_strategy(**trim_args)
    monkeypatch.setattr(budget, "_atomic_json", original)
    assert len(client.submits) == 1
    before = (root / budget.BUDGET_FILE).read_bytes()
    outcome = budget.run_kis_paper_budget_strategy(**(trim_args | {"spy_reduction_quantity": D(5)}))
    assert outcome.reason_code == "spy_reduction_quantity_mismatch"
    assert (root / budget.BUDGET_FILE).read_bytes() == before and len(client.submits) == 1
    assert budget.run_kis_paper_budget_strategy(**trim_args).status == "order_complete"
    assert client.submits[-1].quantity == 4 and len(client.submits) == 2


@pytest.mark.parametrize("trim_quantity", [D(1), D(2), D(3)])
@pytest.mark.parametrize("foreign_extra", [D(0), D(1)])
def test_v3_trim_reconciles_aggregate_and_never_sells_other_owner(
    harness, trim_quantity, foreign_extra,
):
    from test_kis_paper_portfolio_preview import NOW as PREVIEW_NOW
    from test_kis_paper_portfolio_preview import (
        _scope,
        _state,
    )
    from thericher_v2.execution.kis_paper_canary import KisPaperCanaryState
    from thericher_v2.execution.kis_paper_portfolio_plan import build_kis_paper_portfolio_plan

    root, client, args = harness
    client.now = PREVIEW_NOW
    incumbent = _state(requested="2", filled="2")
    inputs = _scope(incumbent)
    binding = inputs["binding"]
    account = budget._digest(
        [
            client._config.base_url,
            client._config.account_number,
            client._config.account_product_code,
        ]
    )
    binding["account_ref"] = account
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    inputs.update(
        expected_account_ref=account,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: pin for owner, pin in budget._owners(binding)},
        reads=replace(inputs["reads"], account_ref=account),
    )
    plan = build_kis_paper_portfolio_plan(
        **inputs,
        expected_binding_ref="sha256:" + budget._digest(binding),
        request_id="synthetic-trim-multi-owner",
        input_ref="sha256:" + "f" * 64,
        valid_until=PREVIEW_NOW + timedelta(minutes=5),
    )
    assert plan.status == "prepared"
    intent = next(intent for intent in plan.intents if intent.symbol == "SPY")
    assert intent.quantity == 1
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id="SYNTHETIC-PORTFOLIO", order_at=PREVIEW_NOW,
            symbol="SPY", exchange="AMEX", side="buy", quantity=D(1),
        ),
        D(1), D(1), D(100), PREVIEW_NOW, D(0),
    )
    portfolio_state = KisPaperCanaryState(
        intent, "submitted", PREVIEW_NOW, "reconciliation_clean",
        broker_order_id="SYNTHETIC-PORTFOLIO", submitted_at=PREVIEW_NOW,
        submission_started_at=PREVIEW_NOW, cumulative_fill=fill,
        fill_observation_status="available", fill_observed_at=PREVIEW_NOW,
    )
    for state in (incumbent, portfolio_state):
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
        client.orders[state.intent.run_id] = dict(
            intent=state.intent, filled=state.intent.quantity, remaining=D(0),
            id=state.broker_order_id,
            price=state.cumulative_fill.gross_amount / state.intent.quantity,
        )
    budget._atomic_json(root / budget.BUDGET_FILE, plan.binding)
    before = budget.project_budget(root, plan.binding, as_of=client.now)
    assert before.quantity == 2 and before.aggregate_quantity == 3
    client.foreign = foreign_extra
    outcome = budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda at: receipt(at, "exit", "e")}),
        spy_reduction_quantity=trim_quantity,
    )
    if foreign_extra:
        assert outcome.reason_code == "existing_inventory_or_order_conflict"
        assert not client.submits
    elif trim_quantity > 2:
        assert outcome.reason_code == "spy_reduction_exceeds_owned_quantity"
        assert not client.submits
    else:
        assert outcome.status == "order_complete"
        assert len(client.submits) == 1 and client.submits[0].quantity == trim_quantity
    retained = budget._load_binding(root)
    after = budget.project_budget(root, retained, as_of=client.now)
    sold = min(trim_quantity, D(2)) if client.submits else D(0)
    assert after.quantity == D(2) - sold and after.aggregate_quantity == D(3) - sold
    assert (
        budget.project_budget(root, retained, as_of=client.now, portfolio_symbol="SPY").quantity
        == 1
    )
    assert after.reserved_buys == before.reserved_buys
    assert retained["portfolio"] == plan.binding["portfolio"]
    assert retained["basis_ref"] == binding["basis_ref"] and retained["qqq"] == binding["qqq"]


def test_unavailable_trim_history_retains_proven_sale_credit_and_pending_identity(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    _v2_trim_binding(root, client)
    client.fill_fraction = D("0.5")
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D(4)}
    assert budget.run_kis_paper_budget_strategy(**trim_args).status == "pending"
    before = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    client.history_status = "unavailable"
    client.now += timedelta(seconds=10)
    assert budget.run_kis_paper_budget_strategy(**trim_args).status == "pending"
    after = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    assert after.quantity == before.quantity and after.gross_cash == before.gross_cash
    assert not budget._load_binding(root)["orders"][-1]["closed"]
    assert len(client.submits) == 2


def test_cancelled_partial_trim_never_credits_unfilled_sale_or_replaces_request(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    before = budget.project_budget(root, _v2_trim_binding(root, client), as_of=client.now)
    client.fill_fraction = D("0.5")
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D(4)}
    assert budget.run_kis_paper_budget_strategy(**trim_args).status == "pending"
    client.now += timedelta(minutes=6)
    assert (
        budget.run_kis_paper_budget_strategy(**trim_args).reason_code
        == "own_order_cancellation_observed"
    )
    client.now += timedelta(seconds=20)
    assert (
        budget.run_kis_paper_budget_strategy(**trim_args).reason_code
        == "decision_already_processed"
    )
    after = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    assert after.quantity == 14
    assert after.gross_cash == before.gross_cash + D(2) * client.submits[-1].limit_price
    assert len(client.submits) == 2 and len(client.cancels) == 1


def test_concurrent_exact_trim_visits_serialize_one_sell(harness):
    _root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D(4)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(lambda _: budget.run_kis_paper_budget_strategy(**trim_args), range(2))
        )
    assert len(client.submits) == 2 and client.submits[-1].quantity == 4
    assert {outcome.status for outcome in outcomes} == {"order_complete", "no_intent"}


def test_trim_pre_submit_callback_still_rejects_changed_aggregate_inventory(harness, monkeypatch):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    snapshot = client.snapshot
    client.calls.clear()

    def changed_book():
        if "snapshot" in client.calls:
            client.foreign = D(1)
        return snapshot()

    monkeypatch.setattr(client, "snapshot", changed_book)
    outcome = budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda at: receipt(at, "exit", "b")}),
        spy_reduction_quantity=D(4),
    )
    assert outcome.reason_code == "pre_submit_ownership_changed"
    assert len(client.submits) == 1
    binding = budget._load_binding(root)
    state = budget._state(root, binding["orders"][-1])
    assert state.intent.quantity == 4 and state.submission_started_at is None


@pytest.mark.parametrize("other_side", ["buy", "sell"])
@pytest.mark.parametrize("explicit", [False, True])
def test_unknown_other_owner_intent_blocks_new_spy_sale_without_provider_effects(
    harness, other_side, explicit,
):
    from test_kis_paper_portfolio_preview import NOW as PREVIEW_NOW
    from test_kis_paper_portfolio_preview import (
        _scope,
        _state,
    )

    root, client, args = harness
    client.now = PREVIEW_NOW
    incumbent = _state(requested="2", filled="2")
    prior = _state(2, symbol="QQQ")
    pending = _state(3, symbol="QQQ", pending=True)
    pending = replace(
        pending, intent=replace(pending.intent, side=other_side),
        phase="outcome_unknown", updated_at=PREVIEW_NOW,
        reason_code="submit_transport_unknown", submission_started_at=pending.intent.created_at,
    )
    # _scope's synthetic closed marker is deliberately replaced by actual proof.
    binding = _scope(incumbent, prior, pending)["binding"]
    binding["qqq"]["orders"][-1]["closed"] = False
    binding["account_ref"] = budget._digest(
        [
            client._config.base_url,
            client._config.account_number,
            client._config.account_product_code,
        ]
    )
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    for state in (incumbent, prior, pending):
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    before = (root / budget.BUDGET_FILE).read_bytes()
    assert budget.project_budget(root, binding, as_of=client.now).quantity == 2
    outcome = budget.run_kis_paper_budget_strategy(
        **(args | {"receipt_loader": lambda at: receipt(at, "exit", "e")}),
        **({"spy_reduction_quantity": D(1)} if explicit else {}),
    )
    assert (outcome.status, outcome.reason_code) == ("no_intent", "other_owned_intent_pending")
    assert not client.calls and not client.submits
    assert (root / budget.BUDGET_FILE).read_bytes() == before


def test_other_owner_pending_blocks_retry_of_never_submitted_trim(harness, monkeypatch):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    _v2_trim_binding(root, client)
    client.quote_age = 0
    from thericher_v2.execution.emergency import PaperExecutionControlStore

    control = PaperExecutionControlStore(args["execution_control_path"])
    control.set_pause_sells(True)
    trim = receipt(client.now, "exit", "b")
    trim_args = args | {"receipt_loader": lambda _: trim, "spy_reduction_quantity": D(4)}
    assert budget.run_kis_paper_budget_strategy(**trim_args).reason_code == "pause_sells_active"
    control.set_pause_sells(False)

    # Pause after the budget's first control read, leaving a retained SELL seed.
    original = client.fetch_spy_limit_input

    def pause_after_quote(**kwargs):
        quote = original(**kwargs)
        control.set_pause_sells(True)
        return quote

    monkeypatch.setattr(client, "fetch_spy_limit_input", pause_after_quote)
    budget.run_kis_paper_budget_strategy(**trim_args)
    binding = budget._load_binding(root)
    state = budget._state(root, binding["orders"][-1])
    assert state.intent.side == "sell" and state.submission_started_at is None
    control.set_pause_sells(False)
    client.calls.clear()
    monkeypatch.setattr(budget, "_other_owned_intent_pending", lambda *args: True)
    before = (root / (state.intent.run_id + ".json")).read_bytes()
    outcome = budget.run_kis_paper_budget_strategy(**trim_args)
    assert outcome.reason_code == "other_owned_intent_pending"
    assert not client.calls and len(client.submits) == 1
    assert (root / (state.intent.run_id + ".json")).read_bytes() == before


def _portfolio_hook_case(harness):
    from test_kis_paper_portfolio_preview import NOW as PREVIEW_NOW
    from test_kis_paper_portfolio_preview import (
        _reads,
        _scope,
    )
    from thericher_v2.execution import kis_paper_canary as canary
    from thericher_v2.execution.kis_paper_portfolio_execute import KisPaperPortfolioExecutionBinding
    from thericher_v2.execution.kis_paper_portfolio_plan import build_kis_paper_portfolio_plan

    root, client, args = harness
    client.now = PREVIEW_NOW
    inputs = _scope()
    binding = inputs["binding"]
    account = budget._digest(
        [
            client._config.base_url,
            client._config.account_number,
            client._config.account_product_code,
        ]
    )
    binding["account_ref"] = account
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    parent_ref, input_ref = "sha256:" + budget._digest(binding), "sha256:" + "f" * 64
    request = "synthetic-internal-hook"
    inputs.update(
        expected_account_ref=account,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: pin for owner, pin in budget._owners(binding)},
        reads=replace(_reads(spy=D(0)), account_ref=account),
    )
    plan = build_kis_paper_portfolio_plan(
        **inputs, expected_binding_ref=parent_ref, request_id=request,
        input_ref=input_ref, valid_until=PREVIEW_NOW + timedelta(minutes=5),
    )
    assert plan.status == "prepared"
    intent = next(intent for intent in plan.intents if intent.symbol == "SPY")
    budget._atomic_json(root / budget.BUDGET_FILE, plan.binding)
    KisPaperCanaryStateStore(root / (intent.run_id + ".json")).record_intent(
        intent, cancel_after_submit=False, now=client.now,
    )
    proof = KisPaperPortfolioExecutionBinding(
        state_root=root.resolve(), account_ref=account, basis_ref=binding["basis_ref"],
        owner_refs=tuple((owner.owner_ref, pin) for owner, pin in budget._owners(plan.binding)),
        binding_ref="sha256:" + budget._digest(plan.binding), request_id=request,
        parent_binding_ref=parent_ref, input_ref=input_ref, plan_ref=plan.plan_ref,
        run_id=intent.run_id, intent_ref=intent.fingerprint,
    )
    call = dict(
        decision=canary.KisPaperCanaryBuyDecision(
            decision_id=intent.decision_id, symbol=intent.symbol, exchange=intent.exchange,
            quantity=intent.quantity, limit_price=intent.limit_price,
            decision_as_of=intent.created_at, valid_until=intent.valid_until,
        ),
        run_id=intent.run_id, environment={}, state_path=root / (intent.run_id + ".json"),
        runtime_projection_path=args["runtime_projection_path"],
        paper_account_snapshot_path=args["paper_account_snapshot_path"],
        emergency_state_path=args["emergency_state_path"],
        artifact_root=args["artifact_root"], repository_root=args["repository_root"],
        execution_control_path=args["execution_control_path"], execute=True,
        cancel_after_submit=False, client=client, clock=lambda: client.now,
        require_existing_state=True, price_contract_ref=intent.price_contract_ref,
        submit_permitted=lambda _: True, submit_reconciliation_check=lambda *_: True,
        portfolio_execution=proof,
    )
    return root, client, intent, proof, call


def test_typed_internal_hook_preserves_portfolio_identity_and_public_guard(harness, monkeypatch):
    import inspect

    from thericher_v2.execution import kis_paper_canary as canary

    root, client, intent, proof, call = _portfolio_hook_case(harness)
    assert "portfolio_execution" not in inspect.signature(canary.run_kis_paper_canary).parameters
    assert budget.conflicts_with_budget_strategy(root, intent.run_id, intent.symbol)
    assert canary._conflicts_with_owned_spy_cycle(root, intent)
    assert not canary._conflicts_with_owned_spy_cycle(root, intent, portfolio_execution=proof)
    assert canary._conflicts_with_owned_spy_cycle(
        root, replace(intent, quantity=intent.quantity + 1), portfolio_execution=proof,
    )

    def reject_exact(retained, **kwargs):
        assert retained == intent
        state = KisPaperCanaryStateStore(call["state_path"]).read()
        assert state.phase == "submission_started" and state.intent == intent
        client.submits.append(retained)
        return False, None

    monkeypatch.setattr(client, "submit_limit", reject_exact)
    with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
        canary._run_kis_paper_canary(**call)
    assert client.submits == [intent]
    state = KisPaperCanaryStateStore(call["state_path"]).read()
    assert state.intent.client_order_id == intent.client_order_id
    assert state.phase == "rejected" and state.submit_response_category == "provider_rejected"


@pytest.mark.parametrize(
    "change", ["untyped", "quantity", "price", "clock", "callbacks", "account", "path"],
)
def test_internal_portfolio_hook_rejects_nonexact_proof_before_mutation(harness, change):
    from thericher_v2.execution import kis_paper_canary as canary
    from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired

    root, client, intent, proof, call = _portfolio_hook_case(harness)
    before = call["state_path"].read_bytes()
    binding_before = (root / budget.BUDGET_FILE).read_bytes()
    if change == "untyped":
        call["portfolio_execution"] = True
    elif change in {"quantity", "price", "clock"}:
        field = {"quantity": "quantity", "price": "limit_price", "clock": "decision_as_of"}[change]
        current = getattr(call["decision"], field)
        call["decision"] = replace(
            call["decision"],
            **{field: current + (timedelta(seconds=1) if change == "clock" else 1)},
        )
    elif change == "callbacks":
        call["submit_reconciliation_check"] = None
    elif change == "account":
        call["portfolio_execution"] = replace(proof, account_ref="0" * 64)
    else:
        call["state_path"] = root / "other.json"
    with pytest.raises((KisPaperCanaryError, _RecoveryRequired)):
        canary._run_kis_paper_canary(**call)
    assert not client.calls and not client.submits
    assert (root / (intent.run_id + ".json")).read_bytes() == before
    assert (root / budget.BUDGET_FILE).read_bytes() == binding_before
