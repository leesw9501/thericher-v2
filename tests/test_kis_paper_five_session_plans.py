"""Synthetic canonical BUY/EXIT plan linkage; no actual bank or broker access."""

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_stock_exit_plan import _arguments as exit_arguments
from test_kis_paper_stock_plan_reservation import _arguments, _observed, _retained
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_stock_exit_plan as exit_plan
from thericher_v2.execution import kis_paper_stock_plan as entry_plan
from thericher_v2.execution.kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
    cohort_from_paper_decision,
    project_five_session_cohort,
)
from thericher_v2.execution.kis_paper_portfolio_budget import KisPaperPortfolioStateRef


def contract(args):
    # Caller-frozen synthetic clocks, not an attestation of an official calendar.
    first = args["as_of"] - timedelta(minutes=1)
    opens = tuple(first + timedelta(days=day) for day in (0, 3, 4, 5, 6))
    closes = tuple(opened + timedelta(hours=6) for opened in opens)
    return KisPaperFiveSessionCohort(
        args["instrument"],
        args["receipt"].decision_id,
        "sha256:" + "c" * 64,
        args["input_ref"],
        opens,
        closes,
        first + timedelta(minutes=10),
        closes[-1] - timedelta(minutes=10),
    )


def projection(cohort, binding, states, custody, at):
    pairs = budget._owners(binding)
    return project_five_session_cohort(
        cohort=cohort,
        expected_cohort_ref=cohort.fingerprint,
        custody=custody,
        basis=budget._basis(binding),
        expected_basis_ref=binding["basis_ref"],
        owners=tuple(owner for owner, _ in pairs),
        expected_owner_refs=dict((owner.owner_ref, ref) for owner, ref in pairs),
        states=states,
        as_of=at,
        input_status="unavailable" if custody.entry else "ready",
    )


@pytest.fixture(autouse=True)
def no_credentials_or_broker(monkeypatch):
    from thericher_v2.execution import kis_readonly
    from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient

    def forbidden(*args, **kwargs):
        pytest.fail("synthetic plan cannot call broker or load credentials")

    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", forbidden)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", forbidden)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", forbidden)


def test_native_entry_request_is_idempotent_and_exact_seed_reconciles_on_restart():
    args = _arguments()
    cohort = contract(args)
    args.update(request_id=cohort.entry_request_id)
    assert (
        projection(
            cohort, args["binding"], args["states"], KisPaperFiveSessionCustody(), args["as_of"]
        ).status
        == "entry_ready"
    )
    first = entry_plan.build_kis_paper_stock_plan(**args)
    assert first.status == "prepared"
    again = entry_plan.build_kis_paper_stock_plan(**_retained(args, first))
    assert again.intents == first.intents and again.plan_ref == first.plan_ref
    assert len(again.binding["stocks"][args["instrument"].symbol]["plans"]) == 1
    seed = budget._stock_seed_states(first.binding)[first.intents[0].run_id]
    custody = KisPaperFiveSessionCustody(
        KisPaperPortfolioStateRef(seed.intent.run_id, seed.intent.fingerprint)
    )
    result = projection(
        cohort, first.binding, args["states"] | {seed.intent.run_id: seed}, custody, args["as_of"]
    )
    assert result.status == "reconcile" and result.pending == custody.entry
    observed = _observed(seed.intent, filled="10", remaining="0")
    result = projection(
        cohort,
        first.binding,
        args["states"] | {seed.intent.run_id: observed},
        custody,
        cohort.session_closes[3],
    )
    assert result.status == "hold" and result.owned_quantity == Decimal(10)
    result = projection(
        cohort,
        first.binding,
        args["states"] | {seed.intent.run_id: observed},
        custody,
        cohort.exit_due,
    )
    assert result.status == "exit_ready" and result.owned_quantity == Decimal(10)


def test_existing_exit_builder_sells_only_exact_cohort_quantity_with_fresh_owned_reads():
    args = _arguments()
    cohort = contract(args)
    args.update(request_id=cohort.entry_request_id)
    prepared = entry_plan.build_kis_paper_stock_plan(**args)
    entry = prepared.intents[0]
    observed = _observed(entry, filled="10", remaining="0")
    prepared.binding["terminal_evidence"][entry.run_id] = budget._terminal_payload(observed)
    # Reuse existing synthetic account-read fixtures, rebinding all clocks to the
    # cohort's fifth session. These are not real account reads.
    exit_args = exit_arguments()
    at = cohort.exit_due
    proposal = replace(exit_args["proposal"], decided_at=at, valid_until=at + timedelta(minutes=5))
    from test_kis_paper_stock_plan import REFS
    from thericher_v2.research.decision_receipt import receipt_from_target_exposure_proposal

    reads = exit_args["reads"]
    snapshot = reads.snapshot
    reads = replace(
        reads,
        started_at=at,
        completed_at=at,
        quote=replace(reads.quote, quoted_at=at),
        snapshot=replace(
            snapshot,
            captured_at=at,
            identity=replace(snapshot.identity, captured_at=at),
            positions=tuple(replace(p, captured_at=at) for p in snapshot.positions),
            open_orders=replace(snapshot.open_orders, captured_at=at),
        ),
    )
    exit_args.update(
        binding=prepared.binding,
        states=args["states"] | {entry.run_id: observed},
        expected_basis_ref=prepared.binding["basis_ref"],
        expected_owner_refs={
            owner.owner_ref: ref for owner, ref in budget._owners(prepared.binding)
        },
        expected_binding_ref="sha256:" + budget._digest(prepared.binding),
        proposal=proposal,
        receipt=receipt_from_target_exposure_proposal(proposal, references=REFS),
        reads=reads,
        as_of=at,
        valid_until=proposal.valid_until,
    )
    result = exit_plan.build_kis_paper_stock_exit_plan(**exit_args)
    assert result.status == "prepared" and len(result.intents) == 1
    assert result.intents[0].side == "sell" and result.intents[0].quantity == Decimal(10)


def test_research_metadata_adapter_preserves_entry_and_five_clocks(monkeypatch):
    from test_five_session_paper_decision import MANIFEST, infer, make_frame
    from thericher_v2.contracts import decision_instrument_binding_ref
    from thericher_v2.research import five_session_paper_decision as paper
    from thericher_v2.research import five_session_tree as tree

    keys = tuple("SYN" + chr(65 + i // 26) + chr(65 + i % 26) + "/NAS" for i in range(512))
    monkeypatch.setattr(
        tree,
        "IDENTITY_SHA256",
        hashlib.sha256(json.dumps(list(keys), separators=(",", ":")).encode()).hexdigest(),
    )
    frame = replace(make_frame(), identities=keys)
    completed = frame.prior_closes[-1] + timedelta(hours=20)
    decision = paper.prepare_five_session_paper_decision(
        frame,
        infer(frame),
        campaign_ref="ref:" + "c" * 64,
        input_manifest_sha256=MANIFEST,
        expected_input_manifest_sha256=MANIFEST,
        feature_source_sha256="sha256:" + tree.FEATURE_SHA256,
        inference_source_sha256=paper.INFERENCE_SOURCE_SHA256,
        instrument_bindings={
            key: decision_instrument_binding_ref(
                symbol=key[:-4], market="US", decision_class="enter"
            )
            for key in keys
        },
        inference_completed_at=completed,
        as_of=completed,
        entry_valid_until=frame.target_open + timedelta(minutes=10),
    )
    out = cohort_from_paper_decision(decision, calendar_ref="sha256:" + "f" * 64)
    assert out.entry_decision_id == decision.receipt.decision_id
    assert out.instrument.binding_ref == decision.instrument_binding_ref
    assert out.source_ref == MANIFEST
    assert out.session_opens == frame.session_opens and out.session_closes == frame.session_closes
    assert out.entry_window_end == decision.entry_valid_until
    assert out.exit_due == frame.session_closes[-1] - timedelta(minutes=10)
    assert out.entry_request_id == "five-" + out.fingerprint.removeprefix("sha256:")


def test_execution_metadata_import_does_not_import_model_or_numerical_runtime():
    from pathlib import Path

    src = str(Path(__file__).resolve().parents[1] / "src")
    code = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in {'numpy','sklearn','torch','pickle'}
            or fullname.endswith(('.five_session_tree','.five_session_cohort'))):
            raise RuntimeError('model_runtime_imported')
sys.meta_path.insert(0, Block())
sys.path.insert(0, sys.argv[1])
import thericher_v2.execution.kis_paper_five_session
print('metadata_only')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, src], capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"metadata_only"
