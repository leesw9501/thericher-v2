"""Cash-profile local refusal precedes any custody, reads or runtime planning."""

import copy

import pytest

from test_model_paper_weights_cash import _cash_input
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.execution import kis_paper_model_qqq_h5 as core


def test_all_cash_rejected_locally_before_native_target_or_boundary_admission(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("inert_cash_reached_native_admission_or_private_scope")

    monkeypatch.setattr(core, "_validate_model_input", forbidden)
    monkeypatch.setattr(core, "_scope", forbidden)
    value = _cash_input("0.0", "1.0")
    with pytest.raises(core.QqqH5PlanningError, match="qqq_h5_cash_input_no_target"):
        core._input(value)


def test_forged_cash_mask_rejected_before_native_admission(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("forged_cash_reached_native_admission")

    monkeypatch.setattr(core, "_validate_model_input", forbidden)
    value = copy.deepcopy(_cash_input("0.0", "1.0"))
    object.__setattr__(value.metadata.rows[-1], "feature_known", False)
    with pytest.raises(ValueError, match="weights_cash_knownness_invalid"):
        core._input(value)


@pytest.mark.parametrize("q,cash", [
    ("0.5", "0.5"), ("1.0", "0.0"),
    ("0.608380138874054", "0.39161986112594604"),
])
def test_positive_cash_profile_reaches_exact_qqq_admission_without_redistribution(q, cash):
    value = _cash_input(q, cash)
    target = core._input(value)
    assert target == value.targets[0]
    assert target.route == "QQQ/NAS"
    assert target.research_weight == value.metadata.rows[1].weight
    assert target.proposal.target_exposure <= value.metadata.original_basis_gross_ceiling


def test_cash_profile_admission_cannot_be_relabelled_as_legacy_h5():
    value = _cash_input()
    with pytest.raises(cycle._CycleFault, match="cycle_input_invalid"):
        cycle._validate_model_input(
            value, value.entry_session.open_ts, cycle.StockCycleProfile.MODEL_WEIGHTS_NAS_H5
        )


def test_generic_stock_driver_cannot_create_or_recover_a_cash_profile(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("cash_profile_entered_generic_stock_driver")

    monkeypatch.setattr(cycle, "_unlinked", forbidden)
    monkeypatch.setattr(cycle.budget, "_load_binding", forbidden)
    monkeypatch.setattr(cycle.budget, "_atomic_json", forbidden)
    outcome = cycle.run_kis_paper_current_stock_cycle(
        state_root=object(), repository_root=object(), artifact_root=object(),
        runtime_projection_path=object(), paper_account_snapshot_path=object(),
        emergency_state_path=object(), execution_control_path=object(),
        expected_account_ref="a" * 64, target_loader=forbidden, client_factory=forbidden,
        clock=forbidden, execute=True,
        profile=cycle.StockCycleProfile.MODEL_WEIGHTS_NAS_CASH_H5,
    )
    assert outcome.status == "unavailable"
    assert outcome.reason == "cycle_cash_profile_requires_qqq_h5_adapter"
