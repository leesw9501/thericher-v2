"""Real native cycle with invented weights, custody and client; no wire or secrets."""

import copy
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_model_paper_profile as model_native
from test_model_paper_proposal import prepared as payoff_point
from test_model_paper_weights import metadata, prepared
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research import model_paper_proposal as payoff
from thericher_v2.research.model_paper_weights import (
    MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    MODEL_PAPER_WEIGHTS_PROFILE,
    ModelPaperWeightRow,
    ModelPaperWeightsInput,
)

D = Decimal
PROFILE = cycle.StockCycleProfile.MODEL_WEIGHTS_NAS
OTHER = "sha256:" + "3" * 64


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path):
    result = model_native.h.__wrapped__(tmp_path)
    bind(result, prepared(), PROFILE)
    return result


def bind(h, value, profile=PROFILE):
    h["data"] = value
    h["now"] = value.entry_session.open_ts + timedelta(minutes=30)
    h["call"].update(
        profile=profile,
        expected_input_ref=value.input_ref,
        expected_policy_ref=value.policy_ref,
    )


def run(h, **changes):
    return model_native.run(h, **changes)


def record(h):
    return model_native.record(h)


def pointer(h):
    return h["root"] / cycle.model_paper_pointer(h["data"].policy_ref)


def bank_bytes(h):
    return (h["root"] / cycle.budget.BUDGET_FILE).read_bytes()


def visit_all(h, **changes):
    return model_native.visit_all(h, **changes)


def test_weight_profile_and_exact_codec_are_not_legacy_scores(h, monkeypatch):
    value = h["data"]
    assert PROFILE.value == MODEL_PAPER_WEIGHTS_PROFILE
    assert cycle._unpack(cycle._pack(value)) == value
    assert cycle._unpack(cycle._pack(value.metadata.rows)) == value.metadata.rows
    assert type(value) is ModelPaperWeightsInput
    assert not isinstance(value, payoff.ModelPaperInput)
    assert all(type(t) is payoff.ModelPaperTarget for t in value.targets)
    assert cycle._validate_input(value, h["now"], PROFILE) is value
    for profile in (cycle.StockCycleProfile.MODEL_PROPOSAL_NAS, cycle.StockCycleProfile.LEGACY_NAS):
        with pytest.raises(cycle._CycleFault, match="cycle_input_invalid"):
            cycle._validate_input(value, h["now"], profile)
    with pytest.raises(cycle._CycleFault, match="cycle_input_invalid"):
        cycle._validate_input(payoff_point(), h["now"], PROFILE)

    # An old registry must reject the new private codec rather than reinterpret it.
    old_types = {k: v for k, v in cycle._TYPES.items() if not k.startswith("ModelPaperWeight")}
    packed = cycle._pack(value.metadata.rows)
    with monkeypatch.context() as old:
        old.setattr(cycle, "_TYPES", old_types)
        with pytest.raises(cycle._CycleFault, match="cycle_value_invalid"):
            cycle._unpack(packed)


def test_old_profile_values_and_codec_are_unchanged_by_additive_weights_profile():
    assert {p.name: p.value for p in cycle.StockCycleProfile} == {
        "LEGACY_NAS": "legacy_nas",
        "CURRENT20_EQUALRANK4": "current20-equalrank4-paper-20261018-v1",
        "MODEL_PROPOSAL_NAS": "model-proposal-nas-v1",
        "MODEL_WEIGHTS_NAS": MODEL_PAPER_WEIGHTS_PROFILE,
        "MODEL_WEIGHTS_NAS_H5": MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    }
    original = payoff_point()
    assert cycle._unpack(cycle._pack(original)) == original


def test_finite_visits_keep_all69_targets_in_original_weight_then_slot_order(h):
    rows = tuple(
        ModelPaperWeightRow(
            slot,
            f"SYN{chr(65 + slot // 26)}{chr(65 + slot % 26)}/NAS",
            True,
            D(".46875") if slot == 68 else D(".0078125"),
        )
        for slot in range(69)
    )
    bind(h, prepared(metadata(rows)))
    value = h["data"]
    assert len(value.targets) == 69
    assert [t.slot for t in value.targets] == [68, *range(68)]
    assert run(h).status == "advanced"
    assert len(h["submits"]) == 1 and h["submits"][0].symbol == "SYNCQ"
    assert h["submits"][0].quantity == D(2)
    for _ in range(2):
        assert (
            run(h, target_loader=lambda: pytest.fail("retain_original_target_order")).status
            == "no_intent"
        )
    retained = cycle._unpack(record(h)["active"]["model_input"])
    assert retained == value and retained.metadata.rows == rows
    assert cycle._unpack(record(h)["active"]["targets"]) == value.targets
    assert record(h)["active"]["entries_done"] == ["SYNCQ", "SYNAA", "SYNAB"]
    assert len(h["submits"]) == 1


def test_native_entries_keep_original_slot_mass_and_one_bank_after_skips(h, monkeypatch):
    rows = (
        ModelPaperWeightRow(0, "MSFT/NAS", True, D(".1")),
        ModelPaperWeightRow(1, "AAPL/NAS", True, D(".4")),
        ModelPaperWeightRow(2, "JPM/NYS", True, D(".25")),
        ModelPaperWeightRow(3, "AMZN/NAS", True, D(".25")),
        ModelPaperWeightRow(4, "NVDA/NAS", False, D(0)),
    )
    bind(h, prepared(metadata(rows)))
    targets = h["data"].targets
    ceilings = {t.slot: t.proposal.target_exposure for t in targets}
    assert ceilings == {0: D(".0005"), 1: D(".002"), 3: D(".00125")}

    def denied(*_args, **_kwargs):
        pytest.fail("weights_must_not_call_payoff_or_rank_composition")

    monkeypatch.setattr(payoff, "_targets", denied)
    monkeypatch.setattr(payoff, "prepare_model_paper_input", denied)
    original = model_native.SyntheticClient.stock_preview_snapshot

    def preview(client, **kwargs):
        if client.instrument.symbol == "AMZN":
            raise cycle.KisPaperReadOnlyError("quote_timestamp_unavailable")
        return original(client, **kwargs)

    monkeypatch.setattr(model_native.SyntheticClient, "stock_preview_snapshot", preview)
    basis = cycle.budget._basis(h["initial"])
    outcomes = visit_all(h)
    assert sorted(r.status for r in outcomes) == ["advanced", "hold", "no_intent", "no_intent"]
    assert len(h["submits"]) == 1
    intent = h["submits"][0]
    assert intent.symbol == "AAPL" and intent.quantity == D(2)
    assert Fraction(intent.quantity * intent.limit_price) <= Fraction(basis.basis_usd * ceilings[1])
    assert {
        t.slot: t.proposal.target_exposure for t in cycle._unpack(record(h)["active"]["targets"])
    } == ceilings
    assert record(h)["active"]["entries_done"] == [t.proposal.symbol for t in targets]
    assert cycle._unpack(record(h)["active"]["model_input"]).metadata.rows == rows
    binding = cycle.budget._load_binding(h["root"])
    assert binding["basis_ref"] == h["initial"]["basis_ref"]
    assert binding["allocated_usd"] == h["initial"]["allocated_usd"]
    assert set(binding["stocks"]) == {"AAPL"}
    gross = sum((i.quantity * i.limit_price for i in h["submits"]), D(0))
    assert gross <= basis.basis_usd * D(".005")
    assert gross < basis.basis_usd * sum(ceilings.values(), D(0))


def test_unknown_restart_holds_exact_request_without_resubmit_or_new_input(h):
    h["unknown"] = True
    assert run(h).status == "pending"
    pending = copy.deepcopy(record(h)["pending"])
    before = bank_bytes(h)
    args = cycle._unpack(pending["arguments"])
    assert args["request_id"] == "model-" + cycle.budget._digest(
        [
            h["data"].policy_ref,
            h["data"].input_ref,
            args["instrument"].binding_ref,
            "buy",
            0,
            h["data"].entry_session.open_ts.isoformat(),
        ]
    )
    h["now"] = h["data"].exit_session.close_ts + timedelta(days=1)
    for _ in range(2):
        assert (
            run(h, target_loader=lambda: pytest.fail("pending_before_loader")).status == "pending"
        )
    assert record(h)["pending"]["arguments"] == pending["arguments"]
    assert bank_bytes(h) == before and len(h["submits"]) == 1
    assert run(h, expected_input_ref=OTHER).status == "unavailable"
    assert bank_bytes(h) == before and record(h)["pending"]["arguments"] == pending["arguments"]


def test_partial_fill_with_unknown_cancel_keeps_exact_reservation(h):
    h["partial"] = True
    h["cancel_unknown"] = True
    assert run(h).status == "pending"
    saved = copy.deepcopy(record(h)["pending"])
    args = cycle._unpack(saved["arguments"])
    assert len(h["submits"]) == 1 and h["submits"][0].quantity == D(2)
    assert h["orders"][next(iter(h["orders"]))]["filled"] == D(1)
    before = bank_bytes(h)
    h["now"] = h["data"].metadata.exit_not_before
    assert (
        run(h, target_loader=lambda: pytest.fail("partial_unknown_before_loader")).status
        == "pending"
    )
    assert record(h)["pending"]["arguments"] == saved["arguments"]
    assert bank_bytes(h) == before and len(h["submits"]) == 1
    assert all(i.run_id == h["submits"][0].run_id for i in h["cancels"])
    binding = cycle.budget._load_binding(h["root"])
    assert [p["request_id"] for p in binding["stocks"][saved["symbol"]]["plans"]] == [
        args["request_id"]
    ]


def test_no_eligible_weight_keeps_mass_as_cash_without_registering_owner(h):
    rows = (
        ModelPaperWeightRow(0, "JPM/NYS", True, D(".5")),
        ModelPaperWeightRow(1, "XOM/NYS", True, D(".5")),
        ModelPaperWeightRow(2, "MSFT/NAS", False, D(0)),
    )
    bind(h, prepared(metadata(rows)))
    before = bank_bytes(h)
    assert run(h).safe_payload() == {
        "status": "no_intent",
        "reason": "native_risk_no_intent",
        "leg_count": 0,
    }
    assert bank_bytes(h) == before and record(h) is None
    assert h["factories"] == 0 and h["submits"] == []


@pytest.mark.parametrize("stage", ["reserve", "execute"])
def test_native_journal_crash_restarts_same_weight_request(h, monkeypatch, stage):
    name = "reserve_kis_paper_stock_plan" if stage == "reserve" else "execute_kis_paper_stock_buy"
    module = cycle.entries if stage == "reserve" else cycle.execution
    original = getattr(module, name)

    def crash(**_kwargs):
        raise RuntimeError("invented_interrupt")

    monkeypatch.setattr(module, name, crash)
    assert run(h).status == "unavailable"
    saved = copy.deepcopy(record(h)["pending"])
    monkeypatch.setattr(module, name, original)
    assert run(h, target_loader=lambda: pytest.fail("restart_before_loader")).status == "advanced"
    assert len(h["submits"]) == 1
    binding = cycle.budget._load_binding(h["root"])
    plans = binding["stocks"][saved["symbol"]]["plans"]
    args = cycle._unpack(saved["arguments"])
    assert [p["request_id"] for p in plans] == [args["request_id"]]
    assert record(h)["pending"] is None


@pytest.mark.parametrize(
    "fault", ["weight", "mask", "ceiling", "targets", "profile", "horizon", "units"]
)
def test_forged_full_weight_contract_denied_before_journal_or_client(h, fault):
    value = h["data"]
    if fault == "weight":
        object.__setattr__(value.metadata.rows[0], "weight", D(".9"))
    elif fault == "mask":
        object.__setattr__(value.metadata, "feature_mask_ref", OTHER)
    elif fault == "ceiling":
        object.__setattr__(value.metadata, "original_basis_gross_ceiling", D(".1"))
    elif fault == "targets":
        object.__setattr__(value, "targets", value.targets[::-1])
    elif fault == "profile":
        object.__setattr__(value, "profile", cycle.StockCycleProfile.MODEL_PROPOSAL_NAS.value)
    elif fault == "horizon":
        object.__setattr__(value, "exit_session", value.entry_session)
    else:
        object.__setattr__(value, "weight_units", "score")
    before = bank_bytes(h)
    outcome = run(h, expected_input_ref=value.input_ref)
    assert outcome.status == "unavailable" and outcome.reason == "cycle_input_invalid"
    assert bank_bytes(h) == before and not pointer(h).exists()
    assert h["factories"] == 0 and h["submits"] == []


def test_valid_larger_gross_contract_is_not_this_native_cohort(h):
    bind(h, prepared(metadata(original_basis_gross_ceiling=D(".01"))))
    before = bank_bytes(h)
    assert run(h).reason == "cycle_input_invalid"
    assert bank_bytes(h) == before and record(h) is None and h["factories"] == 0


def test_recomputed_retained_codec_cannot_expand_native_cohort_ceiling(h):
    assert run(h).status == "advanced"
    forged = prepared(metadata(original_basis_gross_ceiling=D(".01")))
    saved = record(h)
    assert saved["pending"] is None
    saved["active"].update(
        model_input=cycle._pack(forged),
        targets=cycle._pack(forged.targets),
        input_ref=forged.input_ref,
    )
    cycle._save(pointer(h), saved)
    before, bank = pointer(h).read_bytes(), bank_bytes(h)
    result = run(
        h,
        expected_input_ref=forged.input_ref,
        target_loader=lambda: pytest.fail("retained_ceiling_before_loader"),
        client_factory=lambda _: pytest.fail("retained_ceiling_before_client"),
    )
    assert result.reason == "cycle_input_binding_mismatch"
    assert pointer(h).read_bytes() == before and bank_bytes(h) == bank
    assert len(h["submits"]) == 1


@pytest.mark.parametrize("original_weights", [False, True])
def test_same_policy_pointer_cannot_adopt_other_input_type_pending(h, original_weights):
    weights, old = h["data"], payoff_point(entry=date(2026, 10, 23))
    original, replacement = (weights, old) if original_weights else (old, weights)
    original_profile = PROFILE if original_weights else cycle.StockCycleProfile.MODEL_PROPOSAL_NAS
    replacement_profile = (
        cycle.StockCycleProfile.MODEL_PROPOSAL_NAS if original_weights else PROFILE
    )
    bind(h, original, original_profile)
    h["unknown"] = True
    assert run(h).status == "pending"
    before, bank = pointer(h).read_bytes(), bank_bytes(h)
    bind(h, replacement, replacement_profile)
    assert (
        run(
            h,
            target_loader=lambda: pytest.fail("cross_type_before_loader"),
            client_factory=lambda _: pytest.fail("cross_type_before_client"),
        ).status
        == "unavailable"
    )
    assert pointer(h).read_bytes() == before and bank_bytes(h) == bank
    assert len(h["submits"]) == 1


@pytest.mark.parametrize(
    "fault", ["type", "profile", "owner", "targets", "input", "request", "weight"]
)
def test_retained_codec_drift_denied_without_replacing_pending(h, fault):
    h["unknown"] = True
    assert run(h).status == "pending"
    saved = record(h)
    if fault == "type":
        saved["active"]["model_input"] = cycle._pack(payoff_point())
    elif fault == "profile":
        saved["profile"] = cycle.StockCycleProfile.MODEL_PROPOSAL_NAS.value
    elif fault == "owner":
        saved["owner_key"] = OTHER
    elif fault == "targets":
        saved["active"]["targets"] = cycle._pack(())
    elif fault == "input":
        saved["active"]["input_ref"] = OTHER
    elif fault == "request":
        saved["pending"]["arguments"]["request_id"] = "nas-invented-foreign"
    else:
        packed = saved["active"]["model_input"]["value"]["metadata"]["value"]["rows"]["value"]
        packed[0]["value"]["weight"]["value"] = ".9"
    cycle._save(pointer(h), saved)
    before, bank = pointer(h).read_bytes(), bank_bytes(h)
    result = run(
        h,
        target_loader=lambda: pytest.fail("drift_before_loader"),
        client_factory=lambda _: pytest.fail("drift_before_client"),
    )
    assert result.status == "unavailable"
    assert pointer(h).read_bytes() == before and bank_bytes(h) == bank
    assert len(h["submits"]) == 1


@pytest.mark.parametrize("fault", ["stale", "foreign", "late_funds"])
def test_native_risk_remains_authoritative_without_survivor_reweight(h, fault):
    h[fault] = True
    visit_all(h)
    assert h["submits"] == []
    assert cycle._unpack(record(h)["active"]["model_input"]) == h["data"]
    if fault == "late_funds":
        # Call-time funds are checked after durable intent/reservation. A denial
        # cannot make that exact journal disappear or release it by inference.
        assert record(h)["pending"] is not None
        assert record(h)["pending"]["side"] == "buy"
    else:
        assert record(h)["pending"] is None


def test_h20_owned_exit_and_completed_restart_require_no_fresh_weights(h):
    assert visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 2
    h["now"] = h["data"].metadata.exit_not_before - timedelta(seconds=1)
    assert run(h, target_loader=lambda: pytest.fail("owned_hold_no_loader")).status == "hold"
    assert len(h["submits"]) == 2
    h["now"] += timedelta(seconds=1)
    assert (
        visit_all(h, target_loader=lambda: pytest.fail("owned_exit_no_loader"))[-1].status
        == "complete"
    )
    assert len(h["submits"]) == 4 and all(i.side == "sell" for i in h["submits"][2:])
    assert record(h)["pending"] is None and record(h)["active"] is None
    assert (
        run(
            h,
            target_loader=lambda: pytest.fail("completed_no_loader"),
            client_factory=lambda _: pytest.fail("completed_no_client"),
        ).status
        == "complete"
    )


def test_mixed_r5_hgb_weight_owners_project_reconcile_and_exit_only_their_scopes(h, monkeypatch):
    r5 = payoff_point(entry=date(2026, 10, 21), policy=OTHER)
    hgb = payoff_point(
        entry=date(2026, 10, 22),
        policy="sha256:" + "4" * 64,
        selected=(5, 8, 9, 10, 11),
    )
    for value in (r5, hgb):
        bind(h, value, cycle.StockCycleProfile.MODEL_PROPOSAL_NAS)
        assert visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 4
    old_paths = [h["root"] / cycle.model_paper_pointer(v.policy_ref) for v in (r5, hgb)]
    old_bytes = [p.read_bytes() for p in old_paths]
    binding = cycle.budget._load_binding(h["root"])
    old_stocks = copy.deepcopy(binding["stocks"])
    old_states = {k: v.to_dict() for k, v in cycle._states(h["root"], binding).items()}
    rows = (
        ModelPaperWeightRow(0, "AAPL/NAS", True, D(".25")),
        ModelPaperWeightRow(1, "NVDA/NAS", True, D(".5")),
        ModelPaperWeightRow(2, "JPM/NYS", True, D(".25")),
    )
    weights = prepared(metadata(rows))
    bind(h, weights)
    assert visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 5 and h["submits"][-1].symbol == "NVDA"
    assert set(record(h)["owners"]) == {"NVDA"}
    assert [p.read_bytes() for p in old_paths] == old_bytes
    binding = cycle.budget._load_binding(h["root"])
    assert all(binding["stocks"][symbol] == entry for symbol, entry in old_stocks.items())
    for key in ("basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert binding[key] == h["initial"][key]
    with monkeypatch.context() as guard:
        guard.setattr(cycle, "_unpack", lambda _: pytest.fail("global_projection_not_model_codec"))
        states, _, _, projection = cycle._projection(h["root"], binding, h["now"])
    assert all(states[k].to_dict() == v for k, v in old_states.items())
    assert projection.remaining_cap >= 0 and projection.remaining_gross_cash >= 0
    weights_path, weights_bytes = pointer(h), pointer(h).read_bytes()
    for value in (r5, hgb):
        bind(h, value, cycle.StockCycleProfile.MODEL_PROPOSAL_NAS)
        h["now"] = value.metadata.exit_not_before
        assert (
            visit_all(h, target_loader=lambda: pytest.fail("old_owned_no_new_loader"))[-1].status
            == "complete"
        )
    assert weights_path.read_bytes() == weights_bytes
    assert all(i.symbol != "NVDA" for i in h["submits"] if i.side == "sell")
    bind(h, weights)
    h["now"] = weights.metadata.exit_not_before
    assert (
        visit_all(h, target_loader=lambda: pytest.fail("weights_owned_only"))[-1].status
        == "complete"
    )
    assert h["submits"][-1].symbol == "NVDA" and h["submits"][-1].side == "sell"
    assert cycle.budget._load_binding(h["root"])["qqq"] == h["initial"]["qqq"]
