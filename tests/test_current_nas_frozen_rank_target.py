"""Invented inputs only; pure proposals and existing native planning boundaries."""

from __future__ import annotations

import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction

import numpy as np
import pytest

from test_kis_paper_stock_plan import AT, SYMBOL
from test_kis_paper_stock_plan import _arguments as _sizing_arguments
from test_kis_paper_stock_plan_reservation import _arguments as _plan_arguments
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient
from thericher_v2.execution.kis_paper_stock_plan import (
    build_kis_paper_stock_plan,
    size_kis_paper_stock_target,
)
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.current_nas_frozen_rank_target import (
    MODELS,
    FrozenScoreInput,
    FrozenScoreMetadata,
    SupportedScore,
    prepare_targets,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

D = Decimal
WINDOW = datetime(2026, 10, 8, 20, tzinfo=UTC)
SESSION = SessionWindow(AT - timedelta(minutes=30), AT + timedelta(hours=6))
PIN = "sha256:" + "f" * 64


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def deny(*_args, **_kwargs):
        pytest.fail("synthetic_target_cannot_use_provider_or_credentials")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", deny)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config_from_environment", deny)


def _panel():
    rows = tuple(
        SupportedScore(
            slot,
            SYMBOL if slot == 0 else "SYN" + chr(65 + slot // 26) + chr(65 + slot % 26),
            (D(243 - slot),) * 5,
        )
        for slot in range(243)
    )
    return FrozenScoreInput(
        rows=rows,
        models=MODELS,
        metadata=FrozenScoreMetadata(
            score_ref="sha256:" + "a" * 64,
            input_ref="sha256:" + "b" * 64,
            independent_readback_ref="sha256:" + "c" * 64,
            data_producer_ref="sha256:" + "d" * 64,
            score_producer_ref="sha256:" + "e" * 64,
            feature_window_end=WINDOW,
            data_first_available_at=WINDOW + timedelta(minutes=47),
            input_asof=WINDOW + timedelta(hours=1, minutes=31),
            inference_completed_at=WINDOW + timedelta(hours=2, minutes=3),
            score_first_available_at=WINDOW + timedelta(hours=2, minutes=4),
        ),
    )


def _prepare(panel=None, **changes):
    args = dict(
        intended_session=SESSION,
        latest_completed_close=WINDOW,
        official_calendar_ref=PIN,
        decided_at=AT,
        valid_until=AT + timedelta(minutes=5),
    )
    args.update(changes)
    return prepare_targets(_panel() if panel is None else panel, **args)


def test_fixed_five_common_pool_top10_original_basis_units_and_receipt():
    panel = _panel()
    targets = _prepare(panel)
    assert [item.slot for item in targets] == list(range(10))
    assert [item.mean_ordinal_rank for item in targets] == list(map(Fraction, range(1, 11)))
    assert sum(item.research_weight for item in targets) == D(".5")
    assert sum(item.proposal.target_exposure for item in targets) == D(".05")
    for item in targets:
        assert item.research_weight == D(".05") <= D(".1")
        assert item.proposal.target_exposure == D(".005")
        assert item.proposal.confidence == 0
        assert item.metadata is panel.metadata
        assert item.proposal.feature_window_end == WINDOW
        assert item.receipt.input_manifest_ref == panel.metadata.input_ref
        assert item.receipt.model_ref == "ref:" + panel.metadata.score_ref[7:]
        refs = DecisionReceiptReferences(
            item.receipt.campaign_ref,
            item.receipt.model_ref,
            item.receipt.input_manifest_ref,
            item.receipt.proposal_ref,
        )
        assert item.receipt == receipt_from_target_exposure_proposal(item.proposal, references=refs)


def test_exact_ranks_and_identities_survive_low_precision_and_input_permutation():
    panel = _panel()
    # Every unary Decimal negation would tie at precision 2; exact order is reversed.
    rows = tuple(
        replace(row, risk_scores=(D("1.000000000000000" + f"{row.slot:03d}"),) * 5)
        for row in panel.rows
    )
    panel = replace(panel, rows=rows)
    reference = _prepare(panel)
    assert [item.slot for item in reference] == list(range(242, 232, -1))
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        actual = _prepare(replace(panel, rows=tuple(reversed(rows))))
    assert actual == reference


def test_all_five_experts_and_slot_ties_not_a_single_outcome_winner():
    panel = _panel()
    rows = tuple(
        replace(row, risk_scores=(D(row.slot), D(-row.slot), D(-row.slot), D(0), D(0)))
        for row in panel.rows
    )
    targets = _prepare(replace(panel, rows=tuple(reversed(rows))))
    assert [item.slot for item in targets] == list(range(10))
    assert targets[0].mean_ordinal_rank == Fraction(247, 5)


def test_missing_slots_remain_missing_and_negative_scores_are_not_profit_filters():
    panel = _panel()
    rows = tuple(
        replace(row, slot=row.slot + 128, risk_scores=(D(-row.slot - 1),) * 5) for row in panel.rows
    )
    assert [item.slot for item in _prepare(replace(panel, rows=rows))] == list(range(128, 138))


@pytest.mark.parametrize("value", [True, np.bool_(True), np.int64(1), -1, 512, "1"])
def test_slot_types_reject_boolean_or_implicit_numpy_coercion(value):
    with pytest.raises(ValueError, match="^slot_invalid$"):
        SupportedScore(value, "SYN", (D(1),) * 5)


@pytest.mark.parametrize(
    "value", [True, np.bool_(True), np.float64(1), 1, "1", D("NaN"), D("Infinity"), D("-Infinity")]
)
def test_all_scores_require_explicit_finite_decimal(value):
    with pytest.raises(ValueError, match="^all_five_scores_finite$"):
        SupportedScore(0, "SYN", (D(1), D(1), D(1), D(1), value))


def test_243_numpy_numeric_scalars_explicitly_normalize_at_caller_boundary():
    panel = _panel()
    rows = tuple(
        SupportedScore(
            int(np.int64(row.slot)),
            row.symbol,
            tuple(D(str(np.float64(value))) for value in row.risk_scores),
        )
        for row in panel.rows
    )
    assert _prepare(replace(panel, rows=rows)) == _prepare(panel)


@pytest.mark.parametrize(
    "change,category",
    [
        (dict(models=MODELS[:-1]), "exact_five_models_required"),
        (dict(models=tuple(reversed(MODELS))), "exact_five_models_required"),
        (dict(metadata=None), "score_metadata_required"),
        (dict(rows=()), "supported_pool_insufficient"),
    ],
)
def test_missing_contract_facts_rejected(change, category):
    with pytest.raises(ValueError, match=f"^{category}$"):
        _prepare(replace(_panel(), **change))


def test_partial_pool_and_duplicate_identity_rejected():
    panel = _panel()
    with pytest.raises(ValueError, match="^outside_first128_insufficient$"):
        _prepare(replace(panel, rows=panel.rows[:191]))
    for row in (panel.rows[0], replace(panel.rows[-1], symbol=panel.rows[0].symbol)):
        with pytest.raises(ValueError, match="^duplicate_slot_or_symbol$"):
            _prepare(replace(panel, rows=panel.rows[:-1] + (row,)))


@pytest.mark.parametrize(
    "field",
    [
        "score_ref",
        "input_ref",
        "independent_readback_ref",
        "data_producer_ref",
        "score_producer_ref",
    ],
)
def test_producer_and_readback_refs_required_and_identity_bound(field):
    panel = _panel()
    with pytest.raises(ValueError, match="^source_pin_invalid$"):
        replace(panel.metadata, **{field: None})
    changed = replace(panel, metadata=replace(panel.metadata, **{field: PIN}))
    assert _prepare(changed)[0].proposal.proposal_id != _prepare(panel)[0].proposal.proposal_id


@pytest.mark.parametrize(
    "earlier,later",
    [
        ("feature_window_end", "data_first_available_at"),
        ("data_first_available_at", "input_asof"),
        ("input_asof", "inference_completed_at"),
        ("inference_completed_at", "score_first_available_at"),
    ],
)
def test_each_separate_causal_edge_rejects_reversal(earlier, later):
    metadata = _panel().metadata
    with pytest.raises(ValueError, match="^causal_score_clocks_required$"):
        replace(metadata, **{earlier: getattr(metadata, later) + timedelta(microseconds=1)})


@pytest.mark.parametrize(
    "change",
    [
        dict(latest_completed_close=WINDOW - timedelta(days=1)),
        dict(decided_at=WINDOW + timedelta(hours=2)),
        dict(valid_until=AT),
        dict(valid_until=SESSION.close_ts + timedelta(microseconds=1)),
        dict(intended_session=SessionWindow(WINDOW - timedelta(hours=6), WINDOW)),
    ],
)
def test_future_score_wrong_previous_close_wrong_or_expired_session_rejected(change):
    with pytest.raises(ValueError, match="^causal_intended_session_required$"):
        _prepare(**change)


@pytest.mark.parametrize("value", [None, AT.replace(tzinfo=None), "2026-10-09"])
def test_missing_or_naive_clocks_rejected_without_mtime_fallback(value):
    with pytest.raises(ValueError, match="^clock_invalid$"):
        replace(_panel().metadata, input_asof=value)


def test_preopen_preparation_is_not_session_order_permission():
    targets = _prepare(
        decided_at=SESSION.open_ts - timedelta(seconds=2),
        valid_until=SESSION.open_ts + timedelta(microseconds=1),
    )
    assert len(targets) == 10
    assert all(item.proposal.valid_until > SESSION.open_ts for item in targets)


@pytest.mark.parametrize("offset", [timedelta(seconds=-1), timedelta(0)])
def test_preopen_expiry_before_or_exactly_at_intended_open_rejected(offset):
    with pytest.raises(ValueError, match="^causal_intended_session_required$"):
        _prepare(
            decided_at=SESSION.open_ts - timedelta(seconds=2),
            valid_until=SESSION.open_ts + offset,
        )


def test_private_rows_and_containers_have_no_value_repr_and_are_frozen():
    panel = _panel()
    for item in (panel, panel.rows[0], panel.metadata, _prepare(panel)[0]):
        assert SYMBOL not in repr(item) and "Decimal(" not in repr(item)
    with pytest.raises(FrozenInstanceError):
        panel.rows[0].slot = 5


def _native_arguments():
    target = _prepare()[0]
    instrument = KisPaperStockInstrument(
        target.proposal.symbol, target.receipt.instrument_binding_ref
    )
    return target, instrument


def test_generated_confidence_zero_proposal_receipt_reaches_native_offline_intent():
    target, instrument = _native_arguments()
    args = _plan_arguments(target=".005")
    args.update(
        proposal=target.proposal,
        receipt=target.receipt,
        instrument=instrument,
        input_ref=target.metadata.input_ref,
    )
    original = args["binding"]
    result = build_kis_paper_stock_plan(**args)
    assert result.status == "prepared"
    assert len(result.intents) == 1
    assert result.intents[0].quantity == D(5)
    assert result.reservation == D(50)
    assert result.binding["basis_ref"] == original["basis_ref"]
    assert target.proposal.confidence == 0


@pytest.mark.parametrize("change", [dict(funds="0"), dict(broker_quantity="1")])
def test_confidence_zero_does_not_override_native_funding_or_inventory_risk(change):
    target, instrument = _native_arguments()
    args = _sizing_arguments(**change)
    args.update(proposal=target.proposal, receipt=target.receipt, instrument=instrument)
    assert size_kis_paper_stock_target(**args).status == "no_intent"
    assert target.proposal.confidence == 0
