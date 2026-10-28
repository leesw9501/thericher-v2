"""Native serial entries with invented broker facts; no credentials or network."""

import copy
from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal

import pytest

import test_kis_paper_weight_cycle as weights
import test_liquid17_nas_nys_compatibility as venues
import test_model_paper_weights_h5 as metadata_fixture
import test_paper_account_session as serial
from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import paper_account_multileg_session as multileg
from thericher_v2.research.model_paper_weights import (
    ModelPaperWeightRow,
    prepare_model_paper_weights_input,
)

D = Decimal


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    serial.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path, monkeypatch):
    state = serial.h.__wrapped__(tmp_path, monkeypatch)
    old = metadata_fixture._prepared()
    rows = tuple(
        ModelPaperWeightRow(i, route, True, weight)
        for i, (route, weight) in enumerate(
            (
                ("SYNAA/NAS", D(".4")),
                ("SYNAB/NAS", D(".3")),
                ("SYNAC/NYS", D(".3")),
            )
        )
    )
    metadata = replace(
        metadata_fixture._metadata(old.entry_session, old.exit_session, rows),
        original_basis_gross_ceiling=D(".1"),
    )
    value = prepare_model_paper_weights_input(
        metadata,
        entry_session=old.entry_session,
        exit_session=old.exit_session,
        profile=venues.PROFILE.value,
    )
    weights.bind(state, value, venues.PROFILE)
    book = core.budget._load_binding(state["root"])
    # Expired original QQQ unknown and a historical SPY loss remain in ONE bank.
    run = book["qqq"]["orders"][0]["run_id"]
    unknown = core.canary.KisPaperCanaryStateStore(state["root"] / (run + ".json")).read()
    unknown = replace(
        unknown,
        phase="outcome_unknown",
        submission_started_at=unknown.intent.created_at,
        reason_code="submit_transport_unknown",
    )
    core.budget._atomic_json(state["root"] / (run + ".json"), unknown.to_dict())
    buy = core.canary.KisPaperCanaryStateStore(
        state["root"] / (book["orders"][0]["run_id"] + ".json")
    ).read()
    at = buy.updated_at + timedelta(seconds=10)
    intent = replace(
        buy.intent,
        run_id="bs-" + "3" * 64,
        client_order_id="invented-loss",
        decision_id="invented-loss",
        side="sell",
        limit_price=D(50),
        created_at=at,
        valid_until=at + timedelta(minutes=1),
    )
    fill = replace(
        buy.cumulative_fill,
        identity_ref=venues.fill_identity_ref(
            raw_order_id="invented-loss",
            order_at=at + timedelta(seconds=1),
            symbol=intent.symbol,
            exchange=intent.exchange,
            side="sell",
            quantity=intent.quantity,
        ),
        gross_amount=D(50),
        observed_at=at + timedelta(seconds=2),
    )
    loss = replace(
        buy,
        intent=intent,
        broker_order_id="invented-loss",
        submission_started_at=at + timedelta(seconds=1),
        submitted_at=at + timedelta(seconds=1),
        updated_at=at + timedelta(seconds=3),
        cumulative_fill=fill,
        fill_observed_at=fill.observed_at,
    )
    book["orders"].append(dict(run_id=intent.run_id, intent_ref=intent.fingerprint, closed=True))
    book["terminal_evidence"][intent.run_id] = core.budget._terminal_payload(loss)
    book["spy_owner_ref"] = core.budget._owners(book)[0][0].fingerprint
    core.budget._atomic_json(state["root"] / (intent.run_id + ".json"), loss.to_dict())
    book.update(version=4, stocks={})
    core.budget._atomic_json(state["root"] / core.budget.BUDGET_FILE, book)
    state.update(
        protected=copy.deepcopy(book),
        unknown_leg=None,
        admitted=True,
        source_ready=True,
        oldfiles={
            p.name: p.read_bytes()
            for p in state["root"].iterdir()
            if p.name.startswith(("bs-", "bq-"))
        },
    )
    original = serial.w.KisPaperStockCanaryClient

    class Client(venues.VenueSyntheticClient):
        def __init__(self, *, config, transport, instrument):
            super().__init__(state, instrument)
            assert self._config == config
            self._transport = transport
            state["clients"].append(self)

        get = original.get

        def stock_preview_snapshot(self, **kwargs):
            self.get()
            return super().stock_preview_snapshot(**kwargs)

        def reconcile(self, order_state, **kwargs):
            self.get()
            return super().reconcile(order_state, **kwargs)

        def submit_limit(self, intent, **kwargs):
            saved = weights.record(state)
            assert saved["pending"]["symbol"] == intent.symbol
            assert all(
                core.budget._terminal(
                    core.canary.KisPaperCanaryStateStore(
                        state["root"] / (previous.run_id + ".json")
                    ).read(),
                    core.budget._load_binding(state["root"])["terminal_evidence"].get(
                        previous.run_id
                    ),
                )
                for previous in state["submits"]
            )
            state["unknown"] = len(state["submits"]) + 1 == state["unknown_leg"]
            return original.submit_limit(self, intent, **kwargs)

    monkeypatch.setattr(serial.w, "KisPaperStockCanaryClient", Client)
    return state


def invoke(h, *, item=None, loader=None, deadline=None, **options):
    item = serial.cohort(h) if item is None else item
    deadline = h["now"] + timedelta(seconds=240) if deadline is None else deadline
    cap = options.get("max_effects", 3)
    factory = None

    def admitted():
        h["owner_checks"] += 1
        return h["admitted"] and h["source_ready"] and item.source_ref == serial.SOURCE

    # Caller-owned shared wire budget; production library never imports a script.
    class FiniteWireBudget(serial.w.RequestBudget):
        def _check(self, key):
            if (
                self.monotonic() + 8 >= self.deadline
                or sum(self.calls.values()) >= 128
                or key == "token_posts"
                and self.calls[key] >= 1
                or key in {"buy_posts", "sell_posts"}
                and self.calls["buy_posts"] + self.calls["sell_posts"] >= cap
                or key == "cancel_posts"
                and self.calls[key] >= 1
            ):
                raise core.canary.KisPaperCanaryError("request_budget_exhausted")

        def _execution_window_check(self, request):
            super()._execution_window_check(request)
            if not admitted():
                raise multileg.PaperAccountMultilegSessionError("multileg_admission_denied")
            if not item.slot.starts_at <= h["now"] < deadline:
                raise multileg.PaperAccountMultilegSessionError("multileg_deadline_closed")

    def client(instrument):
        nonlocal factory
        if factory is None:
            limits = FiniteWireBudget(
                control_root=h["root"].parent / "timing",
                clock=lambda: h["now"],
                monotonic=lambda: h["mono"],
                sleeper=lambda seconds: serial.advance(h, seconds),
            )
            limits.deadline = min(
                limits.deadline, h["mono"] + (deadline - h["now"]).total_seconds()
            )
            factory = serial.w.client_factory(CONFIG, limits)
        return factory(instrument)

    return multileg.run_native_account_multileg_session(
        cohort=item,
        paths=h["paths"],
        expected_account_ref=options.pop("expected_account_ref", ACCOUNT),
        target_loader=h["call"]["target_loader"] if loader is None else loader,
        client_factory=client,
        guard=admitted,
        deadline=deadline,
        clock=lambda: h["now"],
        monotonic=options.pop("monotonic", lambda: h["mono"]),
        max_effects=options.pop("max_effects", 3),
        **options,
    )


def preserved(h):
    book = core.budget._load_binding(h["root"])
    for key in ("basis_ref", "basis_usd", "allocated_usd", "orders", "qqq", "portfolio"):
        assert book[key] == h["protected"][key]
    for name, raw in h["oldfiles"].items():
        assert (h["root"] / name).read_bytes() == raw
    shared = core._projection(h["root"], book, h["now"])[3]
    assert shared.reserved_buys == sum((s.reserved_buys for s in shared.stocks_by_owner), D(0))
    assert shared.allocated_usd == D(h["protected"]["allocated_usd"])
    assert shared.gross_cash < shared.allocated_usd
    return shared


def test_three_native_legs_share_factory_token_and_original_bank(h):
    initial = preserved(h)
    outcome = invoke(h)
    assert outcome["stop"] == "original_entry_prefix_exhausted"
    assert outcome["cursor"] == outcome["persisted_plans"] == outcome["native_calls"] == 3
    assert [i.exchange for i in h["submits"]] == ["NASD", "NASD", "NYSE"]
    assert h["tokens"] == h["factories"] == 1 and h["wires"] == 3
    assert len(h["clients"]) == 3 and len({id(v) for v in h["limits"]}) == 1
    assert weights.record(h)["pending"] is None
    assert core._unpack(weights.record(h)["active"]["model_input"]) == h["data"]
    shared = preserved(h)
    assert shared.gross_cash < initial.gross_cash and shared.reserved_buys == initial.reserved_buys
    scoped = core.budget.project_budget(
        h["root"], core.budget._load_binding(h["root"]), as_of=h["now"]
    )
    for field in ("entry_cost", "reserved_buys", "gross_cash", "remaining_gross_cash"):
        assert getattr(scoped, field) == getattr(shared, field)
    assert asdict(scoped)["quantity"] == 0  # Historical SPY position was closed at a loss.
    assert invoke(h, loader=serial.forbidden)["native_calls"] == 0
    assert h["wires"] == 3 and outcome["outer_debits"] == 0


def test_unknown_second_leg_stops_third_and_restart_never_resubmits(h):
    h["unknown_leg"] = 2
    assert invoke(h)["stop"] == "pending_preserved"
    pending = copy.deepcopy(weights.record(h)["pending"])
    shared = preserved(h)
    assert h["wires"] == 2
    for _ in range(2):
        serial.advance(h, 61)
        outcome = invoke(h, loader=serial.forbidden)
        assert outcome["stop"] == "initial_pending_recovery_once" and outcome["pending"]
        assert h["wires"] == 2 and weights.record(h)["active"]["entries_done"] == ["SYNAA"]
        assert weights.record(h)["pending"]["seed"] == pending["seed"]
        assert weights.record(h)["pending"]["arguments"] == pending["arguments"]
        assert preserved(h).reserved_buys == shared.reserved_buys


def test_known_partial_pending_does_not_advance(h):
    h["partial"] = True
    assert invoke(h)["stop"] == "pending_preserved" and h["wires"] == 1
    state = core.canary.KisPaperCanaryStateStore(
        h["root"] / (h["submits"][0].run_id + ".json")
    ).read()
    assert state.submitted_at is not None and state.broker_order_id is not None
    assert weights.record(h)["active"]["entries_done"] == []
    serial.advance(h, 61)
    assert invoke(h, loader=serial.forbidden)["stop"] == "initial_pending_recovery_once"
    assert h["wires"] == 1
    preserved(h)


def test_cumulative_cap_and_retained_prefix_restart(h):
    first = invoke(h, max_effects=1)
    assert first["stop"] == "persisted_effect_cap" and first["persisted_plans"] == 1
    assert invoke(h, max_effects=1, loader=serial.forbidden)["native_calls"] == 0
    assert h["wires"] == h["tokens"] == 1
    preserved(h)


def test_call_limit_can_resume_same_input_without_reset(h):
    assert invoke(h, max_native_calls=1)["cursor"] == 1
    serial.advance(h, 61)
    second = invoke(h, loader=serial.forbidden)
    assert second["cursor"] == second["persisted_plans"] == 3
    assert h["loads"] == 1 and h["wires"] == 3
    preserved(h)


def test_foreign_registration_is_skipped_without_adoption(h):
    target = h["data"].targets[0]
    instrument = core._target_instrument(target, venues.PROFILE)
    book = core.budget._load_binding(h["root"])
    plan = core.entries.reserve_kis_paper_stock_plan(
        **{k: h["paths"][k] for k in ("state_root", "repository_root", "artifact_root")},
        expected_account_ref=ACCOUNT,
        expected_basis_ref=book["basis_ref"],
        expected_owner_refs=core._refs(book),
        expected_binding_ref="sha256:" + core.budget._digest(book),
        request_id="invented-foreign",
        input_ref=h["data"].input_ref,
        instrument=instrument,
        proposal=target.proposal,
        receipt=target.receipt,
        reads=venues.VenueSyntheticClient(h, instrument).stock_preview_snapshot(
            expected_account_ref=ACCOUNT, clock=lambda: h["now"]
        ),
        as_of=h["now"],
        valid_until=h["now"] + timedelta(minutes=5),
    )
    assert plan.status == "reserved"
    registration = copy.deepcopy(core.budget._load_binding(h["root"])["stocks"][instrument.symbol])
    outcome = invoke(h)
    assert outcome["cursor"] == 3 and outcome["skipped"] == 1 and h["wires"] == 2
    assert instrument.symbol not in weights.record(h)["owners"]
    assert core.budget._load_binding(h["root"])["stocks"][instrument.symbol] == registration
    preserved(h)


@pytest.mark.parametrize("kind", ["stale_quote", "foreign_inventory", "no_funds"])
def test_native_risk_rejections_do_not_force_effects(h, kind):
    h[{"stale_quote": "stale", "foreign_inventory": "foreign", "no_funds": "funds"}[kind]] = (
        D(0) if kind == "no_funds" else True
    )
    before = weights.bank_bytes(h)
    outcome = invoke(h)
    assert outcome["stop"] in {"native_no_order_complete", "original_entry_prefix_exhausted"}
    assert not h["submits"] and weights.bank_bytes(h) == before
    preserved(h)


@pytest.mark.parametrize("change", ["paths", "input", "policy", "basis", "account", "cursor"])
def test_tampered_retained_binding_refused_before_client(h, change):
    invoke(h, max_native_calls=1)
    item = serial.cohort(h)
    options = {}
    if change == "paths":
        h["paths"] = h["paths"] | {"runtime_projection_path": h["root"].parent / "other.json"}
    elif change in {"input", "policy"}:
        item = replace(item, slot=replace(item.slot, **{change + "_ref": "sha256:" + "9" * 64}))
    elif change == "basis":
        item = replace(item, basis_ref="sha256:" + "9" * 64)
    elif change == "account":
        options["expected_account_ref"] = "9" * 64
    else:
        saved = weights.record(h)
        saved["active"]["entries_done"] = ["SYNAB"]
        core._save(weights.pointer(h), saved)
    counts = h["tokens"], h["wires"]
    with pytest.raises((ValueError, core.budget._RecoveryRequired)):
        invoke(h, item=item, **options)
    assert (h["tokens"], h["wires"]) == counts


@pytest.mark.parametrize("change", ["source", "owner", "before_slot", "deadline", "widen"])
def test_source_admission_and_deadlines_precede_callbacks(h, change):
    item = serial.cohort(h)
    deadline = h["now"] + timedelta(seconds=200)
    if change == "source":
        item = replace(item, source_ref="sha256:" + "9" * 64)
    elif change == "owner":
        h["admitted"] = False
    elif change == "before_slot":
        item = replace(item, slot=replace(item.slot, starts_at=h["now"] + timedelta(seconds=10)))
    elif change == "deadline":
        deadline = h["now"]
    else:
        deadline = item.slot.ends_at + timedelta(seconds=1)
    with pytest.raises(ValueError):
        invoke(h, item=item, deadline=deadline, loader=serial.forbidden)
    assert h["loads"] == h["tokens"] == h["wires"] == 0


@pytest.mark.parametrize("cap", [0, 18, True, 1.0])
@pytest.mark.parametrize("field", ["max_effects", "max_native_calls"])
def test_invalid_caps_refuse_without_callbacks(h, cap, field):
    with pytest.raises(ValueError, match="limit_invalid"):
        invoke(h, **{field: cap}, loader=serial.forbidden)
    assert h["tokens"] == h["wires"] == 0


@pytest.mark.parametrize("mode", ["exit", "recovery"])
def test_not_an_exit_or_recovery_dispatcher(h, mode):
    with pytest.raises(ValueError, match="entry_profile_required"):
        invoke(h, item=serial.cohort(h, mode=mode), loader=serial.forbidden)


def test_unsupported_profile_is_refused(h):
    with pytest.raises(ValueError, match="entry_profile_required"):
        invoke(h, item=replace(serial.cohort(h), profile=core.StockCycleProfile.MODEL_WEIGHTS_NAS))


@pytest.mark.parametrize("late", ["source", "deadline"])
def test_pre_wire_guard_after_pacing_stops_submit(h, monkeypatch, late):
    original = serial.w.KisPaperMarketDataRateGate.wait_for_request_slot
    deadline = h["now"] + timedelta(seconds=240)

    def pace(gate):
        original(gate)
        if h["limits"] and h["limits"][0].calls["get_requests"] >= 2:
            if late == "source":
                h["source_ready"] = False
            else:
                h["now"] = deadline

    monkeypatch.setattr(serial.w.KisPaperMarketDataRateGate, "wait_for_request_slot", pace)
    with pytest.raises(ValueError, match="admission_denied|deadline_closed"):
        invoke(h, deadline=deadline)
    assert h["wires"] == 0


def test_nonfinite_monotonic_refuses_before_custody(h):
    with pytest.raises(ValueError, match="clock_invalid"):
        invoke(h, monotonic=lambda: float("nan"), loader=serial.forbidden)
    assert h["tokens"] == h["wires"] == 0


def test_nas_h5_uniform17_preserves_unsupported_mass(h):
    old = h["data"]
    rows = tuple(
        ModelPaperWeightRow(
            i,
            "SYN" + chr(65 + i) + ("/NAS" if i < 3 else "/NYS"),
            True,
            D(repr(1.0 / 17.0)),
        )
        for i in range(17)
    )
    metadata = replace(
        metadata_fixture._metadata(old.entry_session, old.exit_session, rows),
        model_id="DETERMINISTIC_UNIFORM17_ENGINEERING_BASELINE",
        feature_schema_id="invented-static-rule-not-market-features",
        original_basis_gross_ceiling=D(".1"),
    )
    profile = core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5
    value = prepare_model_paper_weights_input(
        metadata,
        entry_session=old.entry_session,
        exit_session=old.exit_session,
        profile=profile.value,
    )
    weights.bind(h, value, profile)
    assert len(value.metadata.rows) == 17 and len(value.targets) == 3
    assert D(".0176") < sum(t.proposal.target_exposure for t in value.targets) < D(".0177")
    outcome = invoke(h)
    assert outcome["cursor"] == outcome["persisted_plans"] == h["wires"] == 3
    assert all(intent.exchange == "NASD" for intent in h["submits"])
    assert h["factories"] == h["tokens"] == 1
    preserved(h)


def bind_axis(h, *, count=100, positive=10, routed=True):
    old = h["data"]
    rows = tuple(
        ModelPaperWeightRow(
            i,
            "SYN" + chr(65 + i // 26) + chr(65 + i % 26) + ("/NAS" if routed else "/NYS"),
            i < count - 2 if positive < count else True,
            D(repr(1.0 / positive)) if i < positive else D(0),
        )
        for i in range(count)
    )
    profile = core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5
    value = prepare_model_paper_weights_input(
        replace(
            metadata_fixture._metadata(old.entry_session, old.exit_session, rows),
            original_basis_gross_ceiling=D(".1"),
        ),
        entry_session=old.entry_session,
        exit_session=old.exit_session,
        profile=profile.value,
    )
    weights.bind(h, value, profile)
    return value


@pytest.mark.parametrize("positive", [10, 100])
def test_full100_candidates_preserve_axis_and_three_effect_cap(h, positive):
    value = bind_axis(h, positive=positive)
    assert multileg.MAX_TARGETS == len(value.metadata.rows) == 100
    assert len(value.targets) == positive
    before = preserved(h)
    result = invoke(h)
    assert result["stop"] == "persisted_effect_cap"
    assert result["cursor"] == result["persisted_plans"] == h["wires"] == 3
    assert h["factories"] == h["tokens"] == 1
    assert core._unpack(weights.record(h)["active"]["model_input"]) == value
    for target, intent in zip(value.targets, h["submits"], strict=False):
        assert intent.symbol == target.proposal.symbol
        assert intent.quantity * intent.limit_price <= (
            D(h["protected"]["basis_usd"]) * D(".1") * target.research_weight
        )
    assert preserved(h).reserved_buys == before.reserved_buys
    assert invoke(h, loader=serial.forbidden)["native_calls"] == 0
    assert h["wires"] == 3


def test_allpositive100_still_yields_after_seventeen_native_calls(h):
    value = bind_axis(h, positive=100)
    h["stale"] = True
    result = invoke(h)
    assert result["stop"] == "native_call_limit"
    assert result["cursor"] == result["native_calls"] == result["skipped"] == 17
    assert result["persisted_plans"] == h["wires"] == 0 and not h["submits"]
    assert len(value.targets) == 100
    serial.advance(h, 61)
    next_result = invoke(h, loader=serial.forbidden)
    assert next_result["cursor"] == 34 and next_result["native_calls"] == 17
    assert h["wires"] == 0 and h["loads"] == 1
    preserved(h)


def test_full100_zero_native_targets_never_construct_client(h):
    value = bind_axis(h, positive=100, routed=False)
    assert len(value.metadata.rows) == 100 and not value.targets
    before = weights.bank_bytes(h)
    result = invoke(h)
    assert result["stop"] == "empty_original_basket" and result["native_calls"] == 0
    assert h["tokens"] == h["factories"] == h["wires"] == 0
    assert weights.bank_bytes(h) == before and weights.record(h) is None


def test_full100_existing_default_still_yields_one_effect(h):
    bind_axis(h)
    result = serial.visit(h)
    assert result["stop"] == "yield_after_first_native_leg" and h["wires"] == 1
    preserved(h)


@pytest.mark.parametrize("partial", [False, True])
def test_full100_exact_unknown_or_partial_restart_preserves_original_reservations(h, partial):
    bind_axis(h)
    h["partial"] = partial
    h["unknown_leg"] = None if partial else 2
    result = invoke(h)
    assert result["pending"] and h["wires"] == (1 if partial else 2)
    pending = copy.deepcopy(weights.record(h)["pending"])
    reserved = preserved(h).reserved_buys
    count = len(h["submits"])
    serial.advance(h, 61)
    recovered = invoke(h, loader=serial.forbidden)
    assert recovered["stop"] == "initial_pending_recovery_once" and recovered["pending"]
    assert len(h["submits"]) == count and preserved(h).reserved_buys == reserved
    after = weights.record(h)["pending"]
    for key in ("plan_ref", "seed", "arguments", "side", "symbol", "session"):
        assert after[key] == pending[key]


def test_full100_prior_nonflat_cohort_token_floor_and_bounded_recovery(h, monkeypatch):
    value = bind_axis(h)
    assert invoke(h, max_native_calls=1)["persisted_plans"] == 1
    old_pointer = weights.pointer(h)
    old_bytes = old_pointer.read_bytes()
    symbol = h["submits"][0].symbol
    registration = copy.deepcopy(core.budget._load_binding(h["root"])["stocks"][symbol])
    replacement = prepare_model_paper_weights_input(
        replace(value.metadata, policy_ref="sha256:" + "b" * 64),
        entry_session=value.entry_session,
        exit_session=value.exit_session,
        profile=value.profile,
    )
    at = h["now"]
    weights.bind(h, replacement, core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5)
    h["now"] = at + timedelta(seconds=1)
    rejected_claims = []
    claim = serial.w.KisPaperMarketDataTokenStartGate.claim_token_request_start

    def observed_claim(gate):
        result = claim(gate)
        rejected_claims.append(not result)
        return result

    monkeypatch.setattr(
        serial.w.KisPaperMarketDataTokenStartGate, "claim_token_request_start", observed_claim
    )
    early = invoke(h)
    assert early["stop"] == "native_non_progress_stop" and rejected_claims == [True]
    assert h["wires"] == 1 and symbol not in weights.record(h)["owners"]
    assert weights.record(h)["pending"] is None
    assert old_pointer.read_bytes() == old_bytes
    serial.advance(h, 61)
    recovered = invoke(h, loader=serial.forbidden)
    assert recovered["stop"] == "persisted_effect_cap" and recovered["persisted_plans"] == 3
    assert h["wires"] == 4 and recovered["cursor"] == 4
    assert old_pointer.read_bytes() == old_bytes
    assert core.budget._load_binding(h["root"])["stocks"][symbol] == registration
    preserved(h)


@pytest.mark.parametrize("positive", [10, 101])
def test_101_axis_rows_rejected_before_client_token_wire(h, positive):
    bind_axis(h, count=101, positive=positive)
    before = {p.name: p.read_bytes() for p in h["root"].iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="target_limit"):
        invoke(h)
    assert h["tokens"] == h["factories"] == h["wires"] == 0
    assert weights.record(h) is None
    assert {p.name: p.read_bytes() for p in h["root"].iterdir() if p.is_file()} == before
