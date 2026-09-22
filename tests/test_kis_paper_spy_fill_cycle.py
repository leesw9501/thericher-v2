from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.execution import kis_paper_spy_fill_cycle as cycle
from thericher_v2.execution.emergency import EmergencyStore, PaperExecutionControlStore
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryReconciliation,
    KisPaperCanaryStateStore,
    _redacted_open_order_reference,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import parse_kis_paper_spy_limit_input
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

NOW = datetime(2026, 9, 22, 14, 30, tzinfo=UTC)
ENV = {
    "KIS_PAPER_APP_KEY": "synthetic-key",
    "KIS_PAPER_APP_SECRET": "synthetic-secret",
    "KIS_PAPER_ACCOUNT_NO": "12345678",
    "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
}


class SyntheticClient(KisPaperCanaryClient):
    def __init__(self, root):
        super().__init__(config=KisPaperConfig(*ENV.values()), transport=None)
        self.root = root
        self.now = NOW
        self.orders = {}
        self.submits = []
        self.cancels = []
        self.calls = []
        self.fill_immediately = True
        self.position_override = None
        self.foreign_open = False
        self.history_status = "available"
        self.component_age = {}
        self.quote_age = 0
        self.crash = False
        self.fail_cancel = False
        self.before_submit = None
        self.before_snapshot = None

    def snapshot(self):
        self.calls.append("snapshot")
        if self.before_snapshot:
            self.before_snapshot()
        quantity = (
            sum(
                order["quantity"] * (1 if side == "buy" else -1)
                for side, order in self.orders.items()
            )
            if self.position_override is None
            else self.position_override
        )

        def stamp(component):
            return self.now - timedelta(seconds=self.component_age.get(component, 0))

        positions = (
            ()
            if quantity == 0
            else (
                KisPaperPosition(
                    "SPY",
                    "AMEX",
                    "USD",
                    Decimal(quantity),
                    Decimal(600),
                    Decimal(600),
                    stamp("position"),
                ),
            )
        )
        orders = [
            KisPaperOpenOrder(
                _redacted_open_order_reference(order["id"]),
                "SPY",
                "AMEX",
                "USD",
                side,
                Decimal(1),
                Decimal(0),
                Decimal(1),
                order["intent"].limit_price,
                stamp("order"),
            )
            for side, order in self.orders.items()
            if order["open"]
        ]
        if self.foreign_open:
            orders.append(
                KisPaperOpenOrder(
                    "open-foreign",
                    "SPY",
                    "NASD",
                    "USD",
                    "buy",
                    Decimal(1),
                    Decimal(0),
                    Decimal(1),
                    Decimal(500),
                    stamp("order"),
                )
            )
        return KisPaperReadOnlySnapshot(
            KisPaperAccountIdentity(self._config.masked_account_identity, stamp("identity")),
            KisPaperCashSnapshot("USD", Decimal(10000), stamp("cash")),
            KisPaperOrderableFundsSnapshot(
                "USD", Decimal(10000), "AMEX", "SPY", Decimal(600), stamp("funds")
            ),
            positions,
            KisPaperOpenOrdersSnapshot(tuple(orders), stamp("open_orders")),
            stamp("snapshot"),
        )

    def fetch_spy_limit_input(self, *, observed_at):
        self.calls.append("quote")
        source_at = observed_at - timedelta(seconds=self.quote_age) + timedelta(hours=9)
        return parse_kis_paper_spy_limit_input(
            asking_price_payload={
                "rt_cd": "0",
                "output1": {
                    "last": "600.12",
                    "zdiv": "2",
                    "code": "SPY",
                    "rsym": "DAMSSPY",
                    "curr": "USD",
                    "dymd": source_at.strftime("%Y%m%d"),
                    "dhms": source_at.strftime("%H%M%S"),
                },
                "output2": {"pbid1": "600.11", "pask1": "600.13"},
                "output3": {},
            },
            price_detail_payload={"rt_cd": "0", "output": {"zdiv": "2", "e_hogau": "0.01"}},
            observed_at=observed_at,
        )

    def reconcile(self, state, *, now):
        self.calls.append(("reconcile", state.intent.side, state.submission_started_at))
        order = self.orders.get(state.intent.side)
        known = order is not None and state.broker_order_id == order["id"]
        observation = None
        if known:
            fill = None
            if self.history_status == "available":
                fill = KisPaperCumulativeFill(
                    fill_identity_ref(
                        raw_order_id=order["id"],
                        order_at=state.submission_started_at,
                        symbol="SPY",
                        exchange="AMEX",
                        side=state.intent.side,
                        quantity=Decimal(1),
                    ),
                    Decimal(1),
                    Decimal(order["quantity"]),
                    Decimal(order["quantity"]) * state.intent.limit_price,
                    now,
                )
            observation = KisPaperExecutionObservation(
                1, True, self.history_status, fill, observed_at=now
            )
        return KisPaperCanaryReconciliation(
            snapshot=self.snapshot(),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["open"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )

    def submit_limit(self, intent, **kwargs):
        state = KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started"
        active = json.loads((self.root / ".spy_fill_active.json").read_text())
        binding = json.loads(
            (self.root / ".spy_fill_cycles" / (active["cycle_ref"] + ".json")).read_text()
        )
        assert binding[intent.side + "_intent_ref"] == intent.fingerprint
        assert binding["initial_flat"] is True
        if self.before_submit:
            self.before_submit()
        self.submits.append(intent.side)
        self.orders[intent.side] = {
            "id": "SYNTHETIC-" + intent.side.upper(),
            "intent": intent,
            "quantity": int(self.fill_immediately),
            "open": not self.fill_immediately,
        }
        if self.crash:
            raise SystemExit("synthetic process loss after POST")
        return True, self.orders[intent.side]["id"]

    def cancel_order(self, intent, *, broker_order_id):
        self.cancels.append((intent.side, broker_order_id))
        if self.fail_cancel:
            raise KisPaperCanaryError("cancel_transport_failure")
        self.orders[intent.side]["open"] = False
        return True


@pytest.fixture
def setup(tmp_path):
    paths = {
        "state_root": tmp_path / "private" / "canary",
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency.json",
        "execution_control_path": tmp_path / "control.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
    }
    client = SyntheticClient(paths["state_root"])

    def visit(cycle_id="synthetic-cycle", **kwargs):
        return cycle.run_kis_paper_spy_fill_cycle(
            **(
                dict(
                    cycle_id=cycle_id,
                    environment=ENV,
                    execute=True,
                    client=client,
                    now=client.now,
                    **paths,
                )
                | kwargs
            )
        )

    return paths, client, visit


def _state(paths, side):
    binding = cycle._binding("synthetic-cycle", KisPaperConfig(*ENV.values()))
    return KisPaperCanaryStateStore(paths["state_root"] / (binding[side + "_run_id"] + ".json"))


@pytest.mark.parametrize(
    "execute,now,status", [(False, NOW, "preview"), (True, NOW.replace(hour=2), "not_due")]
)
def test_preview_and_closed_session_have_no_access(setup, execute, now, status):
    paths, client, visit = setup

    class NoAccess(dict):
        def get(self, *args):
            raise AssertionError("environment read")

    assert visit(environment=NoAccess(), execute=execute, now=now).status == status
    assert client.calls == []
    assert all(not path.exists() for path in paths.values())


def test_two_leg_success_reuses_ledger_and_public_output_has_no_values(setup):
    paths, client, visit = setup
    first = visit()
    assert first.status == "pending" and client.submits == ["buy"]
    assert cycle.conflicts_with_active_spy_fill_cycle(paths["state_root"], "other", "SPY")
    client.now += timedelta(seconds=15)
    second = visit()
    assert second.status == "complete" and client.submits == ["buy", "sell"]
    assert second.entry_gross_cashflow == Decimal("-600.13")
    assert second.exit_gross_cashflow == Decimal("600.11")
    assert not cycle.conflicts_with_active_spy_fill_cycle(paths["state_root"], "other", "SPY")
    public = json.dumps(second.safe_payload())
    for private in ("600.13", "600.11", "synthetic-cycle", "SYNTHETIC", *ENV.values()):
        assert private not in public
    for key in ("fees", "settled_cash", "net_pnl"):
        assert second.safe_payload()[key] == "not_observed"
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]
    assert _state(paths, "buy").read().position_contribution == 1
    assert _state(paths, "sell").read().position_contribution == -1


def test_binding_hash_excludes_secrets_and_same_cycle_date_independent(setup):
    paths, client, visit = setup
    assert visit().status == "pending"
    files = list((paths["state_root"] / ".spy_fill_cycles").glob("*.json"))
    before = files[0].read_bytes()
    for secret in (
        ENV["KIS_PAPER_APP_KEY"],
        ENV["KIS_PAPER_APP_SECRET"],
        ENV["KIS_PAPER_ACCOUNT_NO"],
    ):
        assert secret.encode() not in before
    assert ENV["KIS_PAPER_ACCOUNT_PRODUCT_CODE"] not in json.loads(before).values()
    client.now += timedelta(days=1)
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]
    assert _state(paths, "buy").read().submission_started_at == NOW
    assert any(call == ("reconcile", "buy", NOW) for call in client.calls)


def test_crash_after_post_never_duplicates_even_when_snapshot_flat(setup):
    paths, client, visit = setup
    client.crash = True
    with pytest.raises(SystemExit):
        visit()
    assert _state(paths, "buy").read().phase == "submission_started"
    client.crash = False
    client.position_override = 0
    assert visit().status == "recovery_required"
    calls = len(client.calls)
    assert visit("different-cycle").reason_code == "another_cycle_unresolved"
    assert len(client.calls) == calls
    assert client.submits == ["buy"]


@pytest.mark.parametrize(
    "history", ["ambiguous", "absent", "identity_mismatch", "fields_invalid", "unavailable"]
)
def test_current_fill_failure_is_retryable_without_new_entry(setup, history):
    paths, client, visit = setup
    assert visit().status == "pending"
    client.history_status = history
    expected = "pending" if history in {"absent", "unavailable"} else "recovery_required"
    assert visit().status == expected
    assert _state(paths, "buy").read().current_fill is None
    assert client.submits == ["buy"]
    client.history_status = "available"
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]


def test_regressive_fill_cannot_exit_but_corrected_evidence_can(setup):
    paths, client, visit = setup
    visit()
    client.orders["buy"]["quantity"] = 0
    assert visit().status == "recovery_required"
    assert _state(paths, "buy").read().fill_observation_status == "conflict"
    client.orders["buy"]["quantity"] = 1
    assert visit().status == "complete"


@pytest.mark.parametrize("position,open_order", [(1, False), (2, False), (0, True)])
def test_initial_foreign_position_or_order_never_creates_binding(setup, position, open_order):
    paths, client, visit = setup
    client.position_override, client.foreign_open = position, open_order
    assert visit().status == "recovery_required"
    assert not (paths["state_root"] / ".spy_fill_active.json").exists()
    assert client.submits == []


def test_sell_requires_one_owned_position_and_no_foreign_open(setup):
    _, client, visit = setup
    visit()
    client.position_override = 2
    assert visit().status == "recovery_required"
    client.position_override = 1
    client.foreign_open = True
    assert visit().status == "recovery_required"
    client.foreign_open = False
    client.position_override = None
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]


@pytest.mark.parametrize(
    "component", ["snapshot", "identity", "cash", "funds", "open_orders", "position"]
)
def test_stale_snapshot_components_prevent_exit(setup, component):
    _, client, visit = setup
    visit()
    client.component_age[component] = 121
    assert visit().reason_code == "snapshot_unavailable"
    assert client.submits == ["buy"]
    client.component_age.clear()
    assert visit().status == "complete"


def test_stale_quote_never_submits(setup):
    _, client, visit = setup
    client.quote_age = 121
    assert visit().status == "recovery_required"
    assert client.submits == []


@pytest.mark.parametrize("delta", [timedelta(seconds=301), timedelta(days=1)])
def test_old_open_entry_cancels_exact_order_without_replacement(setup, delta):
    paths, client, visit = setup
    client.fill_immediately = False
    assert visit().status == "pending"
    client.now += delta
    assert visit().status == "pending"
    assert client.cancels == [("buy", "SYNTHETIC-BUY")]
    assert _state(paths, "buy").read().submission_started_at == NOW
    assert visit().status == "recovery_required"
    assert client.submits == ["buy"]
    assert (paths["state_root"] / ".spy_fill_active.json").exists()


def test_emergency_cancel_is_not_blocked_by_ambiguous_fill_or_foreign_position(setup):
    paths, client, visit = setup
    client.fill_immediately = False
    visit()
    client.history_status, client.position_override = "ambiguous", 2
    EmergencyStore(paths["emergency_state_path"]).request_cancel_open_orders("synthetic")
    assert visit().status == "pending"
    assert client.cancels == [("buy", "SYNTHETIC-BUY")]


def test_cancel_failure_recovers_same_known_order(setup):
    _, client, visit = setup
    client.fill_immediately = False
    visit()
    client.now += timedelta(seconds=301)
    client.fail_cancel = True
    visit()
    client.fail_cancel = False
    visit()
    assert len(client.cancels) == 2
    assert client.submits == ["buy"]


def test_changed_account_refused_before_broker_even_with_reused_client(setup):
    _, client, visit = setup
    visit()
    calls = len(client.calls)
    swapped = ENV | {"KIS_PAPER_ACCOUNT_NO": "87654321"}
    assert visit(environment=swapped).status == "recovery_required"
    assert len(client.calls) == calls
    client._config = replace(client._config, account_number="87654321")
    assert visit(environment=swapped).status == "recovery_required"
    assert len(client.calls) == calls


def test_nonvirtual_injected_config_rejected_before_any_io(setup):
    paths, client, visit = setup
    object.__setattr__(client._config, "base_url", "https://invalid.example")
    assert visit().status == "recovery_required"
    assert client.calls == [] and all(not path.exists() for path in paths.values())


@pytest.mark.parametrize("mode", ["kis_live", " KIS_LIVE "])
def test_live_mode_rejected_before_config_loader_or_client_access(setup, monkeypatch, mode):
    paths, client, visit = setup
    reads = []

    class ModeOnlyEnvironment(dict):
        def get(self, key, default=None):
            reads.append(key)
            assert key == "THERICHER_MODE", "credential access is forbidden"
            return mode

    class ForbiddenClient:
        @property
        def _config(self):
            raise AssertionError("client access is forbidden")

    def forbidden_loader(*args, **kwargs):
        raise AssertionError("Paper config loader must not run")

    monkeypatch.setattr(cycle, "load_kis_paper_config_from_environment", forbidden_loader)
    outcome = visit(environment=ModeOnlyEnvironment(), client=ForbiddenClient())
    assert (outcome.status, outcome.reason_code) == ("recovery_required", "live_mode_unavailable")
    assert reads == ["THERICHER_MODE"]
    assert client.calls == [] and all(not path.exists() for path in paths.values())


def test_off_mode_explicit_execute_remains_usable_without_live_value_reads(setup):
    _, client, visit = setup

    class PaperOnlyEnvironment(dict):
        def get(self, key, default=None):
            assert not key.startswith("KIS_LIVE_")
            return super().get(key, default)

    environment = PaperOnlyEnvironment(ENV | {"THERICHER_MODE": "off"})
    assert visit(environment=environment).status == "pending"
    assert visit(environment=environment).status == "complete"
    assert client.submits == ["buy", "sell"]


@pytest.mark.parametrize("bad_path", ["state", "artifact", "public"])
def test_private_and_repository_root_isolation(setup, bad_path):
    paths, client, visit = setup
    kwargs = {
        "state": {"state_root": paths["repository_root"] / "src"},
        "artifact": {"artifact_root": paths["repository_root"] / "artifacts"},
        "public": {"runtime_projection_path": paths["state_root"] / "public.json"},
    }[bad_path]
    assert visit(**kwargs).status == "recovery_required"
    assert client.calls == [] and all(not path.exists() for path in paths.values())


def test_binding_tamper_or_missing_leg_never_replaces_intent(setup):
    paths, client, visit = setup
    visit()
    store = _state(paths, "buy")
    content = store.path.read_bytes()
    store.path.unlink()
    calls = len(client.calls)
    assert visit().reason_code == "leg_state_missing"
    assert len(client.calls) == calls
    store.path.write_bytes(content)
    state = store.read()
    store._write_unlocked(replace(state, intent=replace(state.intent, limit_price=Decimal(800))))
    assert visit().reason_code == "leg_binding_mismatch"
    assert len(client.calls) == calls


def test_shared_lock_order_and_no_nested_execution_lock(setup, monkeypatch):
    paths, _, visit = setup
    acquired = []
    real_lock = cycle.exclusive_kis_paper_canary_state_lock

    @contextmanager
    def tracked(path):
        assert path not in acquired
        acquired.append(path)
        with real_lock(path):
            yield

    monkeypatch.setattr(cycle, "exclusive_kis_paper_canary_state_lock", tracked)
    assert visit().status == "pending"
    assert acquired == [
        paths["state_root"] / ".session_execution",
        paths["state_root"] / ".canary_execution",
    ]


def test_active_conflict_predicate_is_scoped_to_spy_and_owned_ids(setup):
    paths, _, visit = setup
    root = paths["state_root"]
    assert not cycle.conflicts_with_active_spy_fill_cycle(root, "other", "SPY")
    visit()
    for side in ("buy", "sell"):
        run_id = cycle._binding("synthetic-cycle", KisPaperConfig(*ENV.values()))[side + "_run_id"]
        assert not cycle.conflicts_with_active_spy_fill_cycle(root, run_id, "SPY")
    assert cycle.conflicts_with_active_spy_fill_cycle(root, "other", "SPY")
    assert not cycle.conflicts_with_active_spy_fill_cycle(root, "other", "QQQ")
    (root / ".spy_fill_active.json").write_text("malformed")
    assert cycle.conflicts_with_active_spy_fill_cycle(root, "other", "SPY")
    assert not cycle.conflicts_with_active_spy_fill_cycle(root, "other", "QQQ")


def test_pre_submit_snapshot_change_cannot_use_initial_flat_check(setup):
    _, client, visit = setup

    def change():
        if sum(call == "snapshot" for call in client.calls) >= 3:
            client.position_override = 1

    client.before_snapshot = change
    assert visit().status == "recovery_required"
    assert client.submits == []


@pytest.mark.parametrize("symbol,exchange", [("SPY", "AMEX"), ("QQQ", "NASD")])
@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown"])
def test_old_unresolved_run_does_not_hold_fresh_flat_cycle(setup, symbol, exchange, phase):
    paths, client, visit = setup
    old_at = NOW - timedelta(days=30)
    intent = KisPaperCanaryIntent(
        "foreign",
        "foreign",
        "foreign",
        symbol,
        exchange,
        Decimal(1),
        Decimal(600),
        old_at,
        old_at + timedelta(seconds=120),
    )
    store = KisPaperCanaryStateStore(paths["state_root"] / "foreign.json")
    store.record_intent(intent, cancel_after_submit=False, now=old_at)
    store.transition(
        intent,
        expected=frozenset({"intent_recorded"}),
        phase="submission_started",
        reason_code="preview",
        now=old_at,
        submission_started_at=old_at,
    )
    if phase == "outcome_unknown":
        store.transition(
            intent,
            expected=frozenset({"submission_started"}),
            phase=phase,
            reason_code="reconciliation_unresolved",
            now=old_at,
        )
    before = store.path.read_bytes()
    assert visit().status == "pending"
    assert client.submits == ["buy"]
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]
    assert client.cancels == []
    assert store.path.read_bytes() == before


def test_malformed_unrelated_state_does_not_hold_fresh_flat_cycle(setup):
    paths, client, visit = setup
    paths["state_root"].mkdir(parents=True)
    old_path = paths["state_root"] / "unrelated-old-state.json"
    old_path.write_bytes(b"not a valid state")
    before = old_path.read_bytes()
    assert visit().status == "pending"
    assert client.submits == ["buy"]
    assert client.cancels == []
    assert old_path.read_bytes() == before


@pytest.mark.parametrize("history", ["absent", "unavailable"])
def test_delayed_history_for_exact_open_order_keeps_worker_pending_without_exit(setup, history):
    _, client, visit = setup
    client.fill_immediately = False
    client.history_status = history
    assert visit().reason_code == "awaiting_fill_observation"
    assert visit().status == "pending"
    assert client.submits == ["buy"]
    client.history_status = "available"
    client.orders["buy"].update(quantity=1, open=False)
    client.fill_immediately = True
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]


@pytest.mark.parametrize("history", ["absent", "unavailable"])
def test_filled_order_removed_from_open_book_waits_for_exact_history(setup, history):
    _, client, visit = setup
    client.history_status = history
    first = visit()
    assert (first.status, first.reason_code) == ("pending", "awaiting_fill_observation")
    assert not client.orders["buy"]["open"] and client.orders["buy"]["quantity"] == 1
    assert visit().status == "pending"
    assert client.submits == ["buy"]
    client.history_status = "available"
    assert visit().status == "complete"
    assert client.submits == ["buy", "sell"]


@pytest.mark.parametrize("payload", ["null", "[]", "{}", "broken"])
def test_malformed_active_binding_fails_closed_only_for_spy(setup, payload):
    paths, client, visit = setup
    paths["state_root"].mkdir(parents=True)
    (paths["state_root"] / ".spy_fill_active.json").write_text(payload)
    assert cycle.conflicts_with_active_spy_fill_cycle(paths["state_root"], "other", "SPY")
    assert not cycle.conflicts_with_active_spy_fill_cycle(paths["state_root"], "other", "QQQ")
    assert visit().status == "recovery_required"
    assert not client.calls


def test_closed_cycle_can_reconcile_without_releasing_other_active_binding(setup):
    paths, _, visit = setup
    visit()
    assert visit().status == "complete"
    active_path = paths["state_root"] / ".spy_fill_active.json"
    other = {"cycle_ref": "a" * 64, "account_ref": "b" * 64}
    active_path.write_text(json.dumps(other))
    assert visit().status == "complete"
    assert json.loads(active_path.read_text()) == other


def test_pause_buys_prevents_quote_and_new_binding(setup):
    paths, client, visit = setup
    PaperExecutionControlStore(paths["execution_control_path"]).set_pause_buys(True)
    assert visit().reason_code == "pause_buys_active"
    assert "quote" not in client.calls and client.submits == []
    assert not (paths["state_root"] / ".spy_fill_active.json").exists()
    assert not (paths["state_root"] / ".spy_fill_cycles").exists()


def test_pause_sells_prevents_new_exit_quote_but_retains_entry_ownership(setup):
    paths, client, visit = setup
    visit()
    quotes = client.calls.count("quote")
    PaperExecutionControlStore(paths["execution_control_path"]).set_pause_sells(True)
    assert visit().reason_code == "pause_sells_active"
    assert client.calls.count("quote") == quotes
    assert _state(paths, "sell").read() is None
    assert (paths["state_root"] / ".spy_fill_active.json").exists()


@pytest.mark.parametrize("rejected", [False, True])
def test_proven_no_effect_entry_releases_binding_without_replacing_intent(setup, rejected):
    paths, client, visit = setup
    control = PaperExecutionControlStore(paths["execution_control_path"])
    fetch = client.fetch_spy_limit_input

    def pause_after_quote(**kwargs):
        quote = fetch(**kwargs)
        control.set_pause_buys(True)
        return quote

    client.fetch_spy_limit_input = pause_after_quote
    assert visit().status == "no_intent"
    assert not (paths["state_root"] / ".spy_fill_active.json").exists()
    store = _state(paths, "buy")
    state = store.read()
    assert state.phase == "intent_recorded" and state.submission_started_at is None
    if rejected:
        store._write_unlocked(
            replace(
                state,
                phase="rejected",
                reason_code="submit_rejected",
                submit_response_category="provider_rejected",
            )
        )
    else:
        client.now += timedelta(seconds=121)
    before = store.path.read_bytes()
    client.fetch_spy_limit_input = fetch
    outcome = visit()
    assert (outcome.status, outcome.reason_code) == ("no_intent", "entry_not_submitted")
    assert not (paths["state_root"] / ".spy_fill_active.json").exists()
    assert store.path.read_bytes() == before and client.submits == []
    control.set_pause_buys(False)
    assert visit("different-fresh-cycle").status == "pending"
    assert client.submits == ["buy"] and store.path.read_bytes() == before


def test_mid_visit_buy_pause_releases_ownership_before_worker_stops(setup):
    paths, client, visit = setup
    control = PaperExecutionControlStore(paths["execution_control_path"])
    fetch = client.fetch_spy_limit_input

    def pause_after_quote(**kwargs):
        quote = fetch(**kwargs)
        control.set_pause_buys(True)
        return quote

    client.fetch_spy_limit_input = pause_after_quote
    assert visit().status == "no_intent"
    state = _state(paths, "buy").read()
    assert state.submission_started_at is None
    assert not (paths["state_root"] / ".spy_fill_active.json").exists()
    control.set_pause_buys(False)
    client.fetch_spy_limit_input = fetch
    assert visit("fresh-after-pause").status == "pending"
    assert client.submits == ["buy"]


def test_expired_unsubmitted_exit_retains_ownership_without_automatic_reprice(setup):
    paths, client, visit = setup
    assert visit().status == "pending"
    control = PaperExecutionControlStore(paths["execution_control_path"])
    fetch = client.fetch_spy_limit_input

    def pause_after_quote(**kwargs):
        quote = fetch(**kwargs)
        control.set_pause_sells(True)
        return quote

    client.fetch_spy_limit_input = pause_after_quote
    assert visit().status == "no_intent"
    store = _state(paths, "sell")
    before = store.path.read_bytes()
    client.now += timedelta(seconds=121)
    control.set_pause_sells(False)
    client.fetch_spy_limit_input = fetch
    outcome = visit()
    assert (outcome.status, outcome.reason_code) == (
        "recovery_required",
        "exit_not_submitted_expired",
    )
    assert (paths["state_root"] / ".spy_fill_active.json").exists()
    assert client.submits == ["buy"] and store.path.read_bytes() == before
