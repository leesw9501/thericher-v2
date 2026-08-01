from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

from thericher_v2.research import mim30_campaign_contract as mim30


def test_mim30_is_a_frozen_long_only_derivative_not_a_source_replication() -> None:
    contract = mim30.build_mim30_campaign_contract()

    assert contract.campaign_id == "mim30-spy-long-only-derivative-v1"
    assert contract.symbol == "SPY"
    assert contract.market == "AMS"
    assert contract.signal.positive_signal_action == "long"
    assert contract.signal.nonpositive_signal_action == "flat"
    assert contract.signal.shorting_allowed is False
    assert contract.signal.source_replication is False
    assert contract.signal.additional_filters == ()
    with pytest.raises(ValueError, match="filter-free"):
        replace(contract.signal, additional_filters=("volume",))


def test_mim30_encodes_source_boundaries_and_two_sided_early_close_exclusion() -> None:
    contract = mim30.build_mim30_campaign_contract()

    assert contract.source.sample_start.isoformat() == "1993-02-01"
    assert contract.source.sample_end.isoformat() == "2013-12-31"
    assert contract.session.timezone == "America/New_York"
    assert contract.session.timeframe == "1m"
    assert contract.session.prior_regular_close.isoformat() == "16:00:00"
    assert contract.session.signal_cutoff.isoformat() == "10:00:00"
    assert contract.session.entry_time.isoformat() == "15:30:00"
    assert contract.session.exit_time.isoformat() == "16:00:00"
    assert contract.session.exclude_early_prior_session is True
    assert contract.session.exclude_early_trade_session is True
    assert contract.session.exact_source_execution_reproduction_claimed is False


def test_mim30_uses_the_predeclared_60_20_20_chronological_split_and_minimum_n() -> None:
    contract = mim30.build_mim30_campaign_contract()
    counts = contract.split.counts_for(252)

    assert (counts.development_sessions, counts.validation_sessions, counts.sealed_sessions) == (
        151,
        50,
        51,
    )
    assert counts.total_sessions == 252
    with pytest.raises(ValueError, match="252"):
        contract.split.counts_for(251)


def test_mim30_cost_band_requires_execution_parity_attestation_and_exact_fixed_band() -> None:
    contract = mim30.build_mim30_campaign_contract()
    evidence = _evidence(include_execution_parity_attestation=False)

    decision = contract.assess_sealed_evidence(evidence)

    assert tuple(str(value) for value in contract.costs.multipliers) == ("1.0", "1.5", "2.0")
    assert tuple(str(value) for value in contract.costs.round_trip_bps) == ("10", "15", "20")
    assert contract.costs.execution_attestation_required is True
    assert decision.disposition == "input_unavailable"
    assert decision.reasons == ("execution_parity_attestation_required",)
    assert decision.retuning_allowed is False

    changed_band = replace(
        _evidence(),
        observed_cost_multipliers=(Decimal("1.0"), Decimal("1.5")),
    )
    changed_decision = contract.assess_sealed_evidence(changed_band)
    assert changed_decision.reasons == ("fixed_cost_band_not_observed",)


def test_mim30_requires_current_local_execution_basis_without_source_reproduction() -> None:
    contract = mim30.build_mim30_campaign_contract()
    attestation = _execution_parity_attestation()

    assert attestation.entry_price_basis == "next_completed_bar_open"
    assert attestation.exit_price_basis == "terminal_1559_open"
    assert attestation.latency_basis == "decision_to_next_completed_bar_open"
    assert attestation.close_or_auction_fill_available is False
    assert attestation.source_window_compatible is False
    assert attestation.per_fill_bps == (
        (Decimal("5"), Decimal("5")),
        (Decimal("7.5"), Decimal("7.5")),
        (Decimal("10"), Decimal("10")),
    )
    assert contract.paper_eligible is False
    assert contract.later_execution_reattestation_required is True
    with pytest.raises(ValueError, match="current proxy"):
        replace(attestation, exit_price_basis="source_1600_close")
    with pytest.raises(ValueError, match="current proxy"):
        replace(attestation, close_or_auction_fill_available=True)
    with pytest.raises(ValueError, match="source-window-compatible"):
        replace(attestation, source_window_compatible=True)


def test_mim30_current_execution_proxy_cannot_clear_the_promotion_interpretation() -> None:
    contract = mim30.build_mim30_campaign_contract()

    decision = contract.assess_sealed_evidence(
        _evidence(source_window_compatible=False)
    )

    assert decision.disposition == "input_unavailable"
    assert decision.reasons == ("source_execution_window_unavailable",)
    assert decision.retuning_allowed is False


def test_mim30_kill_condition_rejects_without_retuning() -> None:
    contract = mim30.build_mim30_campaign_contract()
    evidence = _evidence(
        sealed_entry_count=mim30.MIM30_MINIMUM_SEALED_ENTRIES,
        positive_after_cost_at_middle_band=False,
        beats_same_window_always_long_at_middle_band=False,
    )

    decision = contract.assess_sealed_evidence(evidence)

    assert contract.comparators.ids == ("always_flat", "same_window_always_long")
    assert decision.disposition == "rejected"
    assert decision.reasons == (
        "not_positive_after_cost_at_1_5x",
        "does_not_beat_same_window_always_long_at_1_5x",
    )
    assert decision.retuning_allowed is False


def test_mim30_kill_condition_requires_minimum_sealed_entries() -> None:
    contract = mim30.build_mim30_campaign_contract()
    evidence = _evidence(sealed_entry_count=mim30.MIM30_MINIMUM_SEALED_ENTRIES - 1)

    decision = contract.assess_sealed_evidence(evidence)

    assert decision.disposition == "rejected"
    assert decision.reasons == ("insufficient_sealed_entries",)
    assert decision.retuning_allowed is False


def test_mim30_contract_hash_is_deterministic_and_carries_only_contract_scope() -> None:
    first = mim30.build_mim30_campaign_contract()
    second = mim30.build_mim30_campaign_contract()
    payload = first.to_payload()

    assert first.contract_hash == second.contract_hash
    assert payload["scope"] == {
        "training_allowed": False,
        "data_load_allowed": False,
        "network_allowed": False,
        "artifact_write_allowed": False,
        "kis_allowed": False,
        "execution_allowed": False,
        "model_path_allowed": False,
        "paper_eligible": False,
        "later_execution_reattestation_required": True,
    }
    with pytest.raises(ValueError, match="identity"):
        replace(first, market="NAS")


def test_mim30_contract_module_has_no_project_or_io_dependencies() -> None:
    tree = ast.parse(inspect.getsource(mim30))
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0
    )

    assert imported_roots <= {
        "__future__",
        "dataclasses",
        "datetime",
        "decimal",
        "hashlib",
        "json",
        "typing",
    }


def _evidence(
    *,
    include_execution_parity_attestation: bool = True,
    source_window_compatible: bool = True,
    sealed_entry_count: int = mim30.MIM30_MINIMUM_SEALED_ENTRIES,
    positive_after_cost_at_middle_band: bool | None = True,
    beats_same_window_always_long_at_middle_band: bool | None = True,
) -> mim30.Mim30SealedEvidence:
    return mim30.Mim30SealedEvidence(
        qualifying_session_count=mim30.MIM30_MINIMUM_QUALIFYING_SESSIONS,
        sealed_session_count=51,
        sealed_entry_count=sealed_entry_count,
        observed_cost_multipliers=(Decimal("1.0"), Decimal("1.5"), Decimal("2.0")),
        execution_parity_attestation=(
            (
                _source_window_compatible_execution_parity_attestation()
                if source_window_compatible
                else _execution_parity_attestation()
            )
            if include_execution_parity_attestation
            else None
        ),
        positive_after_cost_at_middle_band=positive_after_cost_at_middle_band,
        beats_same_window_always_long_at_middle_band=beats_same_window_always_long_at_middle_band,
    )


def _execution_parity_attestation() -> mim30.Mim30ExecutionParityAttestation:
    return mim30.Mim30ExecutionParityAttestation(
        entry_price_basis="next_completed_bar_open",
        exit_price_basis="terminal_1559_open",
        latency_basis="decision_to_next_completed_bar_open",
        round_trip_bps=(Decimal("10"), Decimal("15"), Decimal("20")),
        per_fill_bps=(
            (Decimal("5"), Decimal("5")),
            (Decimal("7.5"), Decimal("7.5")),
            (Decimal("10"), Decimal("10")),
        ),
        close_or_auction_fill_available=False,
        source_window_compatible=False,
        attested_by_execution=True,
    )


def _source_window_compatible_execution_parity_attestation(
) -> mim30.Mim30ExecutionParityAttestation:
    return mim30.Mim30ExecutionParityAttestation(
        entry_price_basis="scheduled_1530_entry",
        exit_price_basis="session_1600_close",
        latency_basis="execution_attested_signal_to_entry",
        round_trip_bps=(Decimal("10"), Decimal("15"), Decimal("20")),
        per_fill_bps=(
            (Decimal("5"), Decimal("5")),
            (Decimal("7.5"), Decimal("7.5")),
            (Decimal("10"), Decimal("10")),
        ),
        close_or_auction_fill_available=True,
        source_window_compatible=True,
        attested_by_execution=True,
    )
