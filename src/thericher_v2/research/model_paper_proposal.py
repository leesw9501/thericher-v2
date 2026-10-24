"""Sealed model composition for a provisional NAS-only native Paper profile.

All model rows survive venue eligibility. Weights are not money, and desired
exposures remain untrusted ceilings under the existing complete shared bank.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.model_paper_horizon import (
    MODEL_PAPER_20_SESSION_PROFILE,
    MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE,
    prior_official_session_close,
    validate_model_paper_horizon,
)

MODEL_PAPER_PROFILE = "model-proposal-nas-v1"
MODEL_PAPER_SCHEMA = "model-paper-proposal-input-v1"
# Claude REVISE: session 80b93f81-b232-4667-b531-84d3ae5d87bd, stdout SHA256
# 1bd7c16341e9c3d7eb36350854dc4776cc1301bdab31cb902db36db83c2658ea.
# Adopted: preserve weights/foreign ownership; no NYSE bank or routing mutation.
_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
# Preserve AMEX slots without making them executable: eligibility stays NAS-only.
_ROUTE = re.compile(r"[A-Z]{1,10}/(?:NAS|NYS|AMS)", re.ASCII)


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _pin(value):
    _need(type(value) is str and _PIN.fullmatch(value) is not None, "model_pin_invalid")


def _canonical(value):
    def convert(item):
        if type(item) is Decimal:
            return str(item)
        if type(item) is datetime:
            return item.isoformat()
        raise TypeError("model_payload_type_invalid")

    return json.dumps(
        value,
        default=convert,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value):
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "model_duplicate_field")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class ModelPaperRow:
    slot: int
    route: str
    score: Decimal
    rank: int
    weight: Decimal

    def __post_init__(self):
        _need(type(self.slot) is int and 0 <= self.slot < 512, "model_slot_invalid")
        _need(type(self.route) is str and _ROUTE.fullmatch(self.route), "model_route_invalid")
        _need(type(self.rank) is int and self.rank > 0, "model_rank_invalid")
        _need(type(self.score) is Decimal and self.score.is_finite(), "model_score_invalid")
        _need(
            type(self.weight) is Decimal and self.weight.is_finite() and 0 <= self.weight <= 1,
            "model_weight_invalid",
        )

    @property
    def eligibility(self):
        if not self.route.endswith("/NAS"):
            return "UNSUPPORTED_VENUE"
        return "ELIGIBLE_NAS" if self.weight > 0 else "NOT_SELECTED"


@dataclass(frozen=True, slots=True)
class ModelPaperMetadata:
    model_id: str
    feature_schema_id: str
    model_ref: str
    adapter_ref: str
    affine_ref: str
    input_manifest_ref: str
    calendar_ref: str
    policy_ref: str
    full_output_ref: str
    feature_window_end: datetime
    source_available_at: datetime
    input_asof: datetime
    inference_started_at: datetime
    inference_completed_at: datetime
    score_observed_at: datetime
    exit_not_before: datetime
    original_basis_gross_ceiling: Decimal
    rows: tuple[ModelPaperRow, ...]

    def __post_init__(self):
        _need(
            type(self.model_id) is str
            and self.model_id.strip()
            and type(self.feature_schema_id) is str
            and self.feature_schema_id.strip(),
            "model_identity_invalid",
        )
        for ref in (
            self.model_ref,
            self.adapter_ref,
            self.affine_ref,
            self.input_manifest_ref,
            self.calendar_ref,
            self.policy_ref,
            self.full_output_ref,
        ):
            _pin(ref)
        clocks = (
            self.feature_window_end,
            self.source_available_at,
            self.input_asof,
            self.inference_started_at,
            self.inference_completed_at,
            self.score_observed_at,
        )
        _need(
            all(type(t) is datetime and t.utcoffset() == timedelta(0) for t in clocks)
            and clocks == tuple(sorted(clocks)),
            "model_causal_clocks_invalid",
        )
        ceiling = self.original_basis_gross_ceiling
        _need(
            type(ceiling) is Decimal and ceiling.is_finite() and 0 < ceiling <= 1,
            "model_proposal_ceiling_invalid",
        )
        _need(type(self.rows) is tuple and 0 < len(self.rows) <= 512, "model_rows_invalid")
        for row in self.rows:
            _need(type(row) is ModelPaperRow, "model_row_type_invalid")
            row.__post_init__()
        _need(
            len({r.slot for r in self.rows}) == len(self.rows)
            and len({r.route.split("/")[0] for r in self.rows}) == len(self.rows)
            and tuple(r.slot for r in self.rows) == tuple(sorted(r.slot for r in self.rows)),
            "model_rows_duplicate_or_reordered",
        )
        _need(
            sum((Fraction(r.weight) for r in self.rows), Fraction()) <= 1 + Fraction(1, 10**12),
            "model_composition_exceeds_one",
        )

    @property
    def eligible_weight(self):
        return sum(
            (Fraction(r.weight) for r in self.rows if r.eligibility == "ELIGIBLE_NAS"), Fraction()
        )

    @property
    def skipped_weight(self):
        return sum(
            (Fraction(r.weight) for r in self.rows if r.eligibility == "UNSUPPORTED_VENUE"),
            Fraction(),
        )


@dataclass(frozen=True, slots=True)
class ModelPaperTarget:
    slot: int
    route: str
    research_weight: Decimal
    proposal: TargetExposureProposal
    receipt: ResearchDecisionReceipt


@dataclass(frozen=True, slots=True)
class ModelPaperInput:
    metadata: ModelPaperMetadata
    targets: tuple[ModelPaperTarget, ...]
    entry_session: SessionWindow
    exit_session: SessionWindow
    profile: str = MODEL_PAPER_PROFILE
    execution_payoff: str = "operational_execution_proxy_not_replay_equivalent"

    def __post_init__(self):
        validate_model_paper_input(self)

    @property
    def policy_ref(self):
        return self.metadata.policy_ref

    @property
    def input_ref(self):
        return "sha256:" + hashlib.sha256(serialize_model_paper_input(self)).hexdigest()


def _targets(metadata, entry_session):
    reference = _digest(asdict(metadata))
    refs = DecisionReceiptReferences(
        "ref:" + metadata.policy_ref[7:],
        "ref:" + metadata.model_ref[7:],
        metadata.input_manifest_ref,
        "ref:" + reference[7:],
    )
    remaining = Fraction(metadata.original_basis_gross_ceiling)
    targets = []
    for row in metadata.rows:
        if row.eligibility != "ELIGIBLE_NAS":
            continue
        # Floor independently; never normalize survivors or reuse a skipped slot.
        amount = min(
            Fraction(metadata.original_basis_gross_ceiling) * Fraction(row.weight), remaining
        )
        units = amount * 10**24
        digits = tuple(int(c) for c in str(units.numerator // units.denominator))
        exposure = Decimal((0, digits, -24))
        remaining -= Fraction(exposure)
        if exposure <= 0:
            continue
        proposal = TargetExposureProposal(
            f"model-nas-{reference[7:]}-{row.slot}",
            row.route.split("/")[0],
            "US",
            "enter",
            exposure,
            Decimal(0),
            metadata.feature_schema_id,
            "ready",
            metadata.score_observed_at,
            entry_session.close_ts,
            metadata.feature_window_end,
            "provisional_NAS_eligibility_of_full_model_rows_not_full_universe_performance",
        )
        targets.append(
            ModelPaperTarget(
                row.slot,
                row.route,
                row.weight,
                proposal,
                receipt_from_target_exposure_proposal(proposal, references=refs),
            )
        )
    return tuple(targets)


def prepare_model_paper_input(
    metadata, *, entry_session, exit_session, profile=MODEL_PAPER_PROFILE
):
    """Pure bridge; old profile remains the default and no bank is initialized."""
    _need(type(metadata) is ModelPaperMetadata, "model_metadata_invalid")
    metadata.__post_init__()
    return ModelPaperInput(
        metadata, _targets(metadata, entry_session), entry_session, exit_session, profile=profile
    )


def validate_model_paper_input(value):
    _need(
        type(value) is ModelPaperInput
        and value.profile
        in {
            MODEL_PAPER_PROFILE,
            MODEL_PAPER_20_SESSION_PROFILE,
            MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE,
        },
        "model_profile_invalid",
    )
    _need(
        value.execution_payoff == "operational_execution_proxy_not_replay_equivalent",
        "model_execution_payoff_invalid",
    )
    _need(type(value.metadata) is ModelPaperMetadata, "model_metadata_invalid")
    value.metadata.__post_init__()
    _need(
        type(value.entry_session) is SessionWindow and type(value.exit_session) is SessionWindow,
        "model_sessions_invalid",
    )
    first, last = value.entry_session, value.exit_session
    if value.profile == MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE:
        _need(
            first.open_ts
            < value.metadata.score_observed_at
            < first.close_ts
            < last.open_ts
            < last.close_ts,
            "model_session_clocks_invalid",
        )
    else:
        _need(
            value.metadata.score_observed_at
            < first.open_ts
            < first.close_ts
            < last.open_ts
            < last.close_ts,
            "model_session_clocks_invalid",
        )
    validate_model_paper_horizon(first, last, profile=value.profile)
    _need(
        value.profile != MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE
        or value.metadata.feature_window_end == prior_official_session_close(first),
        "model_prior_session_close_invalid",
    )
    _need(
        value.profile != MODEL_PAPER_20_SESSION_PROFILE
        or value.metadata.exit_not_before == last.close_ts - timedelta(minutes=15),
        "model_20session_exit_proxy_invalid",
    )
    _need(
        type(value.metadata.exit_not_before) is datetime
        and value.metadata.exit_not_before.utcoffset() == timedelta(0)
        and last.open_ts <= value.metadata.exit_not_before < last.close_ts,
        "model_exit_window_invalid",
    )
    _need(
        type(value.targets) is tuple and value.targets == _targets(value.metadata, first),
        "model_target_composition_changed",
    )
    return value


def serialize_model_paper_input(value):
    """Broker-free JSON ABI; no native private-state codec or model is imported."""
    _need(type(value) is ModelPaperInput, "model_input_type_invalid")
    return _canonical(dict(schema=MODEL_PAPER_SCHEMA, **asdict(value)))


def load_model_paper_input(
    payload, *, expected_sha256, expected_policy_ref, expected_profile=MODEL_PAPER_PROFILE
):
    """Verify source/temporal/target bindings before the native target-loader handoff."""
    _need(
        expected_profile
        in {
            MODEL_PAPER_PROFILE,
            MODEL_PAPER_20_SESSION_PROFILE,
            MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE,
        },
        "model_profile_invalid",
    )
    _need(
        type(payload) is bytes
        and len(payload) <= 1024 * 1024
        and hashlib.sha256(payload).hexdigest() == expected_sha256,
        "model_input_pin_mismatch",
    )
    document = json.loads(
        payload,
        object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("model_nonfinite")),
    )
    _need(
        set(document)
        == {
            "schema",
            "profile",
            "metadata",
            "targets",
            "entry_session",
            "exit_session",
            "execution_payoff",
        }
        and document.pop("schema") == MODEL_PAPER_SCHEMA
        and document["profile"] == expected_profile,
        "model_input_schema_invalid",
    )
    raw = document["metadata"]
    _need(set(raw) == {f.name for f in fields(ModelPaperMetadata)}, "model_metadata_fields_invalid")
    clocks = {
        "feature_window_end",
        "source_available_at",
        "input_asof",
        "inference_started_at",
        "inference_completed_at",
        "score_observed_at",
        "exit_not_before",
    }
    values = dict(raw)
    for name in clocks:
        values[name] = require_utc(datetime.fromisoformat(raw[name]))
    values["original_basis_gross_ceiling"] = Decimal(raw["original_basis_gross_ceiling"])
    values["rows"] = tuple(
        ModelPaperRow(r["slot"], r["route"], Decimal(r["score"]), r["rank"], Decimal(r["weight"]))
        for r in raw["rows"]
    )
    metadata = ModelPaperMetadata(**values)
    _need(metadata.policy_ref == expected_policy_ref, "model_policy_pin_mismatch")

    def session(value):
        _need(set(value) == {"open_ts", "close_ts"}, "model_session_fields_invalid")
        return SessionWindow(
            **{k: require_utc(datetime.fromisoformat(v)) for k, v in value.items()}
        )

    result = prepare_model_paper_input(
        metadata,
        entry_session=session(document["entry_session"]),
        exit_session=session(document["exit_session"]),
        profile=expected_profile,
    )
    # Re-derive every proposal/receipt rather than trusting executable fields in JSON.
    _need(serialize_model_paper_input(result) == payload, "model_payload_not_canonical_or_derived")
    return result
