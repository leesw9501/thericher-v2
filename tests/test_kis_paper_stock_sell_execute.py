"""Synthetic owned SELL lifecycle; no private inputs or broker access."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG
from test_kis_paper_portfolio_preview import NOW
from test_kis_paper_stock_budget_binding import REF, _binding, _submitted
from test_kis_paper_stock_execute import no_actual_wire  # noqa: F401
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_stock_execute as execute
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_paper_stock_canary import KisPaperStockCanaryClient
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.execution.kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperPosition,
    KisPaperReadOnlyError,
)

D = Decimal


class ExitClient(KisPaperStockCanaryClient):
    def __init__(self, root, instrument):
        super().__init__(config=CONFIG, transport=None, instrument=instrument)
        self.root, self.now, self.submits = root, NOW, []
        self.filled = D(0)
        self.foreign = self.partial = self.unknown = self.unavailable = False
        self.stale = False
        self.on_read = None

    def account(self):
        quantity = D(2) - self.filled + int(self.foreign)
        positions = (
            ()
            if quantity == 0
            else (
                KisPaperPosition("AAPL", "NASD", "USD", quantity, D(100), quantity * 100, self.now),
            )
        )
        opens = ()
        if self.submits and self.filled < 2:
            intent = self.submits[0]
            opens = (
                KisPaperOpenOrder(
                    canary._redacted_open_order_reference("101"),
                    "AAPL",
                    "NASD",
                    "USD",
                    "sell",
                    intent.quantity,
                    self.filled,
                    intent.quantity - self.filled,
                    intent.limit_price,
                    self.now,
                ),
            )
        return KisPaperStockExitAccountSnapshot(
            KisPaperAccountIdentity(CONFIG.masked_account_identity, self.now),
            positions,
            KisPaperOpenOrdersSnapshot(opens, self.now, complete=True),
            self.now,
        )

    def stock_exit_snapshot(self, **kwargs):
        quote = KisPaperSpyLimitInput(
            last=D(100),
            decimal_places=2,
            best_bid=D(99),
            best_ask=D(101),
            tick_size=D("0.01"),
            quoted_at=self.now - timedelta(minutes=3) if self.stale else self.now,
        )
        value = KisPaperStockExitReads(
            ACCOUNT,
            self.instrument,
            self.account(),
            quote,
            self.now,
            self.now,
            0.0,
        )
        if self.on_read:
            self.on_read()
        return value

    def orderable_funds_at_limit(self, **kwargs):
        pytest.fail("SELL must not read buying power, cash or QQQ funds")

    def submit_limit(self, intent, **kwargs):
        retained = canary.KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert retained.phase == "submission_started" and retained.intent == intent
        assert intent.side == "sell" and intent.quantity == 2
        self.submits.append(intent)
        self.filled = D(1) if self.partial else D(2)
        if self.unknown:
            raise canary.KisPaperCanaryError("submit_transport_unknown")
        return True, "101"

    def reconcile(self, state, *, now):
        if self.unavailable:
            return canary._unavailable_reconciliation()
        known = bool(self.submits) and state.broker_order_id == "101"
        observation = None
        if known:
            fill = KisPaperCumulativeFill(
                fill_identity_ref(
                    raw_order_id="101",
                    order_at=state.submission_started_at,
                    symbol="AAPL",
                    exchange="NASD",
                    side="sell",
                    quantity=D(2),
                ),
                D(2),
                self.filled,
                self.filled * state.intent.limit_price,
                self.now,
                D(2) - self.filled,
            )
            observation = KisPaperExecutionObservation(1, True, "available", fill, self.now)
        return canary.KisPaperCanaryReconciliation(
            snapshot=self.account(),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and self.filled < 2),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )


@pytest.fixture
def sell_call(tmp_path):
    root = tmp_path / "p"
    binding, buy = _binding(account=ACCOUNT)
    filled = _submitted(buy, quantity="2", amount="200")
    parent = "sha256:" + budget._digest(binding)
    request, input_ref = "synthetic-owned-exit", "sha256:" + "e" * 64
    identity = budget._stock_identity(binding, "AAPL", request, "sell")
    intent = canary.KisPaperCanaryIntent(
        "bk-" + identity,
        "stock-" + identity,
        "stock-" + identity,
        "AAPL",
        "NASD",
        D(2),
        D(99),
        NOW,
        NOW + timedelta(minutes=1),
        side="sell",
        price_contract_ref=budget._stock_price_ref(binding, "AAPL", input_ref, D(99), "sell"),
    )
    seed = canary.KisPaperCanaryState(intent, "intent_recorded", NOW, "preview")
    plan = dict(
        request_id=request,
        input_ref=input_ref,
        parent_binding_ref=parent,
        states={intent.run_id: seed.to_dict()},
    )
    entry = binding["stocks"]["AAPL"]
    entry["plans"].append(plan)
    entry["owner_ref"] = budget._owners(binding)[-1][0].fingerprint
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    budget._atomic_json(root / (buy.intent.run_id + ".json"), filled.to_dict())
    instrument = KisPaperStockInstrument("AAPL", REF)
    proof = execute.KisPaperStockExecutionBinding(
        state_root=root.resolve(),
        instrument=instrument,
        account_ref=ACCOUNT,
        basis_ref=binding["basis_ref"],
        owner_refs=tuple((o.owner_ref, r) for o, r in budget._owners(binding)),
        binding_ref="sha256:" + budget._digest(binding),
        request_id=request,
        parent_binding_ref=parent,
        input_ref=input_ref,
        plan_ref="sha256:" + budget._digest(plan),
        run_id=intent.run_id,
        intent_ref=intent.fingerprint,
        side="sell",
    )
    client = ExitClient(root, instrument)
    return dict(
        proof=proof,
        state_root=root,
        client=client,
        execute=True,
        clock=lambda: client.now,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "control.json",
    )


def state(call):
    return canary.KisPaperCanaryStateStore(
        call["state_root"] / (call["proof"].run_id + ".json")
    ).read()


def test_cash_free_sell_fills_once_and_replays_flat(sell_call):
    first = execute.execute_kis_paper_stock_sell(**sell_call)
    assert first.phase == "submitted" and state(sell_call).cumulative_fill.status == "filled"
    assert not sell_call["paper_account_snapshot_path"].exists()
    execute.execute_kis_paper_stock_sell(**sell_call)
    assert len(sell_call["client"].submits) == 1
    binding = budget._load_binding(sell_call["state_root"], ACCOUNT)
    assert (
        budget.project_budget(
            sell_call["state_root"], binding, as_of=NOW, stock_symbol="AAPL"
        ).quantity
        == 0
    )


def test_unknown_sell_is_never_substituted(sell_call):
    sell_call["client"].unknown = True
    execute.execute_kis_paper_stock_sell(**sell_call)
    initial = state(sell_call)
    execute.execute_kis_paper_stock_sell(**sell_call)
    assert state(sell_call).intent == initial.intent and len(sell_call["client"].submits) == 1
    assert state(sell_call).phase == "outcome_unknown"


def test_partial_late_duplicate_fill_and_unavailable_recovery(sell_call):
    client = sell_call["client"]
    client.partial = True
    execute.execute_kis_paper_stock_sell(**sell_call)
    original = state(sell_call).cumulative_fill
    assert original.quantity == 1
    client.unavailable = True
    execute.execute_kis_paper_stock_sell(**sell_call)
    assert state(sell_call).cumulative_fill == original
    client.unavailable, client.filled = False, D(2)
    client.now += timedelta(seconds=5)
    execute.execute_kis_paper_stock_sell(**sell_call)
    execute.execute_kis_paper_stock_sell(**sell_call)
    assert state(sell_call).cumulative_fill.quantity == 2 and len(client.submits) == 1


@pytest.mark.parametrize("fault", ["foreign", "stale"])
def test_foreign_target_or_stale_bid_never_submits(sell_call, fault):
    setattr(sell_call["client"], fault, True)
    with pytest.raises((ValueError, _RecoveryRequired, KisPaperReadOnlyError)):
        execute.execute_kis_paper_stock_sell(**sell_call)
    assert sell_call["client"].submits == []


def test_expiry_after_fresh_read_never_submits(sell_call):
    client = sell_call["client"]
    client.on_read = lambda: setattr(client, "now", NOW + timedelta(minutes=2))
    execute.execute_kis_paper_stock_sell(**sell_call)
    assert client.submits == [] and state(sell_call).submission_started_at is None


def test_side_pin_cannot_turn_buy_wrapper_into_sell(sell_call):
    with pytest.raises(_RecoveryRequired, match="stock_side_mismatch"):
        execute.execute_kis_paper_stock_buy(**sell_call)
    assert sell_call["client"].submits == []
    sell_call["proof"] = replace(sell_call["proof"], side="buy")
    with pytest.raises(_RecoveryRequired, match="stock_side_mismatch"):
        execute.execute_kis_paper_stock_sell(**sell_call)
