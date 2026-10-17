"""Frozen equalrank4 proposals for a distinct provisional native Paper cycle.

No model/client loading, credentials, scheduler, account reads or new bank.
The parent contract and Data calendar are caller-pinned authority inputs;
research weights are not permission to spend or claims of Paper fills.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from thericher_v2.contracts import SCHEMA_VERSION, TargetExposureProposal, require_utc
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

if TYPE_CHECKING:
    from thericher_v2.execution.kis_paper_current_stock_cycle import CurrentStockCycleInput

CANDIDATE_ID = "current20-equalrank4-paper-20261018-v1"
POLICY = "equalrank4"
FEATURE_SCHEMA_ID = "current20-direct-d1-rule-hgb14-mlp-gru-f3-equalrank4-top5-paper-v1"
BUNDLE_SHA256 = "f9cbd3ee0fc4058bb8771ac47763c960665932299631e9ed6270c46761f3b55f"
WEIGHTS_SHA256 = "97c7f0f086d5cdec59860ef8d1bf5dfb457a5fc976a92af5c53ed223bae48348"
PREDICTIONS_SHA256 = "4028adde2b34fdb2c2242cc073e808ff2eecb81558f0ddb604f62129702de1eb"
SOURCE_BINDING_SHA256 = "343a80389b210acf53ef77b669cf0a84df523c0c129cca5ed0df2d491ae9fe42"
SHADOW_REVIEW_SHA256 = "c7a76993e8c40f7ff753368f9ddeb9b7d0934897e33448922e524aaacbb00963"
STOCK_KEYS = (
    "AAPL/NAS",
    "AMD/NAS",
    "AMZN/NAS",
    "GOOGL/NAS",
    "META/NAS",
    "MSFT/NAS",
    "NVDA/NAS",
    "TSLA/NAS",
    "JPM/NYS",
    "JNJ/NYS",
    "XOM/NYS",
    "PG/NYS",
    "KO/NYS",
    "HD/NYS",
    "V/NYS",
    "DIS/NYS",
    "UNH/NYS",
)
FEATURE_CLOSE = datetime(2026, 10, 16, 20, tzinfo=UTC)
PUBLICATION = datetime.fromisoformat("2026-10-17T13:28:52.404571+00:00")
SOURCE_OBSERVED = datetime.fromisoformat("2026-10-17T10:39:33.031783+00:00")
INFERENCE_COMPLETED = datetime.fromisoformat("2026-10-17T13:24:47.570853+00:00")
ENTRY_NOT_BEFORE = datetime(2026, 10, 19, 15, 10, tzinfo=UTC)
EXIT_NOT_BEFORE = datetime(2026, 11, 17, 15, 10, tzinfo=UTC)
_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _pin(value):
    _need(type(value) is str and _PIN.fullmatch(value) is not None, "candidate_pin_invalid")


def _digest(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    )


@dataclass(frozen=True, slots=True, repr=False)
class Current20PaperCalendar:
    """Data-attested exact calendar bytes, not acquisition or source authenticity.

    source_ref must identify Data's immutable typed binding. The local official
    calendar checks 21 scheduled source sessions plus the exit session: only
    20 RTH sessions are fully held between the proposed intraday visits.
    """

    source_ref: str
    previous_close: datetime
    sessions: tuple[SessionWindow, ...]

    def __post_init__(self):
        _pin(self.source_ref)
        _need(self.previous_close == FEATURE_CLOSE, "candidate_previous_close_invalid")
        expected = []
        day = date(2026, 10, 19)
        while day <= date(2026, 11, 17):
            session = us_equity_2026_session(day)
            if session is not None:
                expected.append(session.window)
            day += timedelta(days=1)
        _need(
            type(self.sessions) is tuple
            and len(self.sessions) == 22
            and all(type(s) is SessionWindow for s in self.sessions)
            and self.sessions == tuple(expected),
            "candidate_exact_21_sessions_and_exit_required",
        )


@dataclass(frozen=True, slots=True, repr=False)
class Current20PaperMetadata:
    contract_ref: str
    calendar: Current20PaperCalendar
    selected_slots: tuple[int, ...]
    decided_at: datetime
    bundle_ref: str = "sha256:" + BUNDLE_SHA256
    weights_ref: str = "sha256:" + WEIGHTS_SHA256
    source_binding_ref: str = "sha256:" + SOURCE_BINDING_SHA256
    feature_window_end: datetime = FEATURE_CLOSE
    score_first_available_at: datetime = PUBLICATION
    source_first_available_at: datetime = SOURCE_OBSERVED
    inference_completed_at: datetime = INFERENCE_COMPLETED

    def __post_init__(self):
        _pin(self.contract_ref)
        _need(type(self.calendar) is Current20PaperCalendar, "candidate_calendar_required")
        self.calendar.__post_init__()
        _need(
            type(self.selected_slots) is tuple
            and len(self.selected_slots) == 5
            and all(type(s) is int and 0 <= s < 17 for s in self.selected_slots)
            and self.selected_slots == tuple(sorted(set(self.selected_slots))),
            "candidate_five_unique_original_slots_required",
        )
        _need(
            type(self.decided_at) is datetime
            and PUBLICATION <= require_utc(self.decided_at) < self.calendar.sessions[0].close_ts,
            "candidate_decision_clock_invalid",
        )
        _need(
            (self.bundle_ref, self.weights_ref, self.source_binding_ref)
            == (
                "sha256:" + BUNDLE_SHA256,
                "sha256:" + WEIGHTS_SHA256,
                "sha256:" + SOURCE_BINDING_SHA256,
            )
            and self.feature_window_end == FEATURE_CLOSE
            and self.score_first_available_at == PUBLICATION
            and self.source_first_available_at == SOURCE_OBSERVED
            and self.inference_completed_at == INFERENCE_COMPLETED,
            "candidate_source_binding_invalid",
        )

    @property
    def input_ref(self):
        return _digest(
            dict(
                candidate_id=CANDIDATE_ID,
                policy=POLICY,
                contract=self.contract_ref,
                bundle=self.bundle_ref,
                weights=self.weights_ref,
                source=self.source_binding_ref,
                calendar=self.calendar.source_ref,
                decided_at=self.decided_at.isoformat(),
                selected_slots=self.selected_slots,
            )
        )


def current20_paper_calendar_from_binding(payload: bytes, *, expected_sha256: str):
    """Consume Data's pinned metadata only; future mark acquisition is not needed."""
    _pin("sha256:" + expected_sha256)
    _need(type(payload) is bytes and len(payload) <= 131072, "candidate_calendar_payload_invalid")
    _need(hashlib.sha256(payload).hexdigest() == expected_sha256, "candidate_calendar_pin_mismatch")
    data = json.loads(payload)

    def instant(value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _need(parsed.tzinfo is not None, "candidate_aware_clock_required")
        return parsed.astimezone(UTC)

    _need(
        instant(data["clocks"]["candidate_available_utc"]) == PUBLICATION
        and instant(data["clocks"]["source_available_utc"]) == SOURCE_OBSERVED
        and instant(data["clocks"]["output_written_by_utc"]) == INFERENCE_COMPLETED
        and instant(data["clocks"]["context_close_utc"]) == FEATURE_CLOSE
        and data["frozen_output"]["bundle_ref"]["sha256"] == BUNDLE_SHA256,
        "candidate_calendar_source_mismatch",
    )
    calendar = data["calendar"]
    days = [datetime.strptime(d, "%Y%m%d").date() for d in calendar["expected_session_dates"]]
    days.append(date.fromisoformat(calendar["exit"]["session_date"]))
    official = [us_equity_2026_session(d) for d in days]
    _need(all(s is not None for s in official), "candidate_calendar_closed_day")
    result = Current20PaperCalendar(
        "sha256:" + expected_sha256,
        FEATURE_CLOSE,
        tuple(s.window for s in official),
    )
    for key, session in (("entry", result.sessions[0]), ("exit", result.sessions[-1])):
        _need(
            instant(calendar[key]["open_utc"]) == session.open_ts
            and instant(calendar[key]["close_utc"]) == session.close_ts,
            "candidate_calendar_clock_mismatch",
        )
    return result


@dataclass(frozen=True, slots=True, repr=False)
class Current20PaperTarget:
    slot: int
    research_weight: Decimal
    proposal: TargetExposureProposal
    receipt: ResearchDecisionReceipt
    metadata: Current20PaperMetadata


def validate_current20_targets(value, at):
    """Native profile admission; never admit legacy PreparedTarget as ensemble."""
    _need(
        type(value.targets) is tuple and len(value.targets) == 5, "candidate_five_targets_required"
    )
    slots = []
    metadata = None
    for target in value.targets:
        _need(type(target) is Current20PaperTarget, "candidate_target_type_invalid")
        _need(type(target.metadata) is Current20PaperMetadata, "candidate_metadata_invalid")
        target.metadata.__post_init__()
        metadata = target.metadata if metadata is None else metadata
        _need(target.metadata == metadata, "candidate_metadata_mismatch")
        _need(type(target.slot) is int and 0 <= target.slot < 17, "candidate_slot_invalid")
        key = STOCK_KEYS[target.slot]
        p, receipt = target.proposal, target.receipt
        _need(type(p) is TargetExposureProposal, "candidate_proposal_invalid")
        _need(type(receipt) is ResearchDecisionReceipt, "candidate_receipt_invalid")
        _need(
            key.endswith("/NAS")
            and p.proposal_id == CANDIDATE_ID + "-" + str(target.slot)
            and p.reason == "provisional_frozen_equalrank4"
            and p.schema_version == SCHEMA_VERSION
            and p.symbol == key.split("/")[0]
            and p.market == "US"
            and p.action == "enter"
            and p.input_status == "ready"
            and p.feature_schema_id == FEATURE_SCHEMA_ID
            and p.confidence == Decimal(0)
            and p.target_exposure == Decimal(".005")
            and target.research_weight == Decimal(".2")
            and p.feature_window_end == FEATURE_CLOSE
            and PUBLICATION <= p.decided_at <= at < p.valid_until
            and p.decided_at == metadata.decided_at
            and p.valid_until == metadata.calendar.sessions[0].close_ts,
            "candidate_proposal_binding_invalid",
        )
        refs = DecisionReceiptReferences(
            "ref:" + metadata.contract_ref[7:],
            "ref:" + BUNDLE_SHA256,
            metadata.input_ref,
            "ref:" + metadata.input_ref[7:],
        )
        _need(
            receipt_from_target_exposure_proposal(p, references=refs) == receipt,
            "candidate_receipt_binding_invalid",
        )
        slots.append(target.slot)
    _need(tuple(slots) == metadata.selected_slots, "candidate_exact_original_top5_required")
    _need(
        value.input_ref == metadata.input_ref
        and value.policy_ref == metadata.contract_ref
        and value.entry_session == metadata.calendar.sessions[0]
        and value.exit_session == metadata.calendar.sessions[-1],
        "candidate_cycle_binding_invalid",
    )


def prepare_current20_paper_candidate(
    *,
    contract_bytes: bytes,
    expected_contract_sha256: str,
    bundle_bytes: bytes,
    weights_bytes: bytes,
    calendar: Current20PaperCalendar,
    decided_at: datetime,
) -> CurrentStockCycleInput:
    """Bind exact retained policy bytes to new proposals, without model inference.

    Pass the Parent-owned contract's independently pinned SHA, not a digest
    recomputed from an arbitrary candidate. No bytes or prices are printed.
    """
    import numpy as np

    from thericher_v2.execution.kis_paper_current_stock_cycle import (
        CurrentStockCycleInput,
        StockCycleProfile,
    )

    for payload, limit in ((contract_bytes, 65536), (bundle_bytes, 65536), (weights_bytes, 16384)):
        _need(type(payload) is bytes and len(payload) <= limit, "candidate_payload_invalid")
    _pin("sha256:" + expected_contract_sha256)
    _need(
        hashlib.sha256(contract_bytes).hexdigest() == expected_contract_sha256
        and hashlib.sha256(bundle_bytes).hexdigest() == BUNDLE_SHA256
        and hashlib.sha256(weights_bytes).hexdigest() == WEIGHTS_SHA256,
        "candidate_payload_pin_mismatch",
    )
    contract, bundle = json.loads(contract_bytes), json.loads(bundle_bytes)
    required = dict(
        schema="current20_equalrank4_provisional_paper_contract_v1",
        candidate_id=CANDIDATE_ID,
        policy=POLICY,
        signal_bundle_sha256=BUNDLE_SHA256,
        prediction_sha256=PREDICTIONS_SHA256,
        weights_sha256=WEIGHTS_SHA256,
        independent_shadow_readback_sha256=SHADOW_REVIEW_SHA256,
        entry_us_session="2026-10-19",
        latest_completed_feature_session="2026-10-16",
        earliest_owned_exit_us_session="2026-11-17",
        desired_targets=5,
        original_basis_fraction_per_target="0.005",
        maximum_original_basis_fraction_for_new_candidate="0.025",
    )
    _need(all(contract.get(k) == v for k, v in required.items()), "candidate_contract_mismatch")
    _need(
        type(calendar) is Current20PaperCalendar
        and tuple(bundle["tradable_order"]) == STOCK_KEYS
        and bundle["binding_sha256"] == SOURCE_BINDING_SHA256
        and bundle["weights_sha256"] == WEIGHTS_SHA256,
        "candidate_source_mismatch",
    )
    at = require_utc(decided_at)
    _need(PUBLICATION <= at < calendar.sessions[0].close_ts, "candidate_entry_expired")
    for field, expected in (
        ("immutable_seal_utc", PUBLICATION),
        ("logical_previous_close_utc", FEATURE_CLOSE),
        ("actual_source_observed_utc", SOURCE_OBSERVED),
        ("model_output_written_by_utc", INFERENCE_COMPLETED),
    ):
        observed = datetime.fromisoformat(bundle[field].replace("Z", "+00:00"))
        _need(observed.tzinfo is not None, "candidate_aware_clock_required")
        _need(observed.astimezone(UTC) == expected, "candidate_source_clock_mismatch")
    # Resolve by the literal policy name, never by an assumed numeric row.
    policies = bundle["policies"]
    _need(policies.count(POLICY) == 1, "candidate_literal_policy_required")
    with np.load(io.BytesIO(weights_bytes), allow_pickle=False) as arrays:
        weights = arrays["weights"]
        _need(
            weights.shape == (len(policies), 17)
            and np.isfinite(weights).all()
            and np.array_equal(arrays["source_slots"], np.arange(3, 20))
            and arrays["entry_ordinal"].shape == ()
            and arrays["entry_ordinal"].item() == 5230,
            "candidate_weight_coordinates_invalid",
        )
        row = weights[policies.index(POLICY)]
        selected = [int(i) for i in np.flatnonzero(row)]
        _need(
            len(selected) == 5 and all(row[i] == 0.2 for i in selected),
            "candidate_exact_frozen_top5_required",
        )
    metadata = Current20PaperMetadata(
        "sha256:" + expected_contract_sha256,
        calendar,
        tuple(selected),
        at,
    )
    refs = DecisionReceiptReferences(
        "ref:" + expected_contract_sha256,
        "ref:" + BUNDLE_SHA256,
        metadata.input_ref,
        "ref:" + metadata.input_ref[7:],
    )
    targets = []
    for slot in selected:
        proposal = TargetExposureProposal(
            CANDIDATE_ID + "-" + str(slot),
            STOCK_KEYS[slot].split("/")[0],
            "US",
            "enter",
            Decimal(".005"),
            Decimal(0),
            FEATURE_SCHEMA_ID,
            "ready",
            at,
            calendar.sessions[0].close_ts,
            FEATURE_CLOSE,
            "provisional_frozen_equalrank4",
        )
        targets.append(
            Current20PaperTarget(
                slot,
                Decimal(".2"),
                proposal,
                receipt_from_target_exposure_proposal(proposal, references=refs),
                metadata,
            )
        )
    value = CurrentStockCycleInput(
        tuple(targets),
        calendar.sessions[0],
        calendar.sessions[-1],
        metadata.input_ref,
        metadata.contract_ref,
        StockCycleProfile.CURRENT20_EQUALRANK4,
    )
    validate_current20_targets(value, max(ENTRY_NOT_BEFORE, at))
    return value


def serialize_current20_paper_input(value):
    """Offline create-once deployment payload, containing no model arrays."""
    from thericher_v2.execution import kis_paper_current_stock_cycle as cycle

    _need(type(value) is cycle.CurrentStockCycleInput, "candidate_cycle_type_invalid")
    _need(
        value.profile is cycle.StockCycleProfile.CURRENT20_EQUALRANK4, "candidate_profile_invalid"
    )
    validate_current20_targets(
        value, max(ENTRY_NOT_BEFORE, value.targets[0].proposal.decided_at)
    )
    payload = {"profile": value.profile.value}
    for key in ("targets", "entry_session", "exit_session", "input_ref", "policy_ref"):
        payload[key] = cycle._pack(getattr(value, key))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_current20_paper_input(payload: bytes, *, expected_sha256: str):
    """Read pinned native JSON only; never load research arrays at runtime."""
    from thericher_v2.execution import kis_paper_current_stock_cycle as cycle

    _pin("sha256:" + expected_sha256)
    _need(type(payload) is bytes and len(payload) <= 65536, "candidate_payload_invalid")
    _need(hashlib.sha256(payload).hexdigest() == expected_sha256, "candidate_payload_pin_mismatch")
    decoded = json.loads(payload)
    keys = {"profile", "targets", "entry_session", "exit_session", "input_ref", "policy_ref"}
    _need(type(decoded) is dict and set(decoded) == keys, "candidate_payload_fields_invalid")
    _need(
        decoded.pop("profile") == cycle.StockCycleProfile.CURRENT20_EQUALRANK4.value,
        "candidate_profile_invalid",
    )
    value = cycle.CurrentStockCycleInput(
        **{k: cycle._unpack(v) for k, v in decoded.items()},
        profile=cycle.StockCycleProfile.CURRENT20_EQUALRANK4,
    )
    validate_current20_targets(
        value, max(ENTRY_NOT_BEFORE, value.targets[0].proposal.decided_at)
    )
    return value


def run_current20_paper_visit(**arguments):
    """At most five native legs plus a terminal check; pending stops the wake.

    Parent supplies native client/config/paths only in a separately integrated
    owned deployment. Default execute=False stays inert before any callback.
    A daily wake outside the regular session never renews a signal or order.
    """
    from thericher_v2.execution.kis_paper_current_stock_cycle import (
        StockCycleProfile,
        run_kis_paper_current_stock_cycle,
    )

    _need("profile" not in arguments, "candidate_profile_not_overridable")
    outcomes = []
    deadline = time.monotonic() + 600
    for _ in range(6):
        if outcomes and time.monotonic() >= deadline:
            break
        result = run_kis_paper_current_stock_cycle(
            profile=StockCycleProfile.CURRENT20_EQUALRANK4,
            **arguments,
        )
        outcomes.append(result)
        if result.status not in {"advanced", "no_intent"}:
            break
    return tuple(outcomes)
