"""Inert allocation weights become untrusted gross ceilings, never payoff scores."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.model_paper_horizon import (
    MODEL_PAPER_5_SESSION_PROFILE,
    MODEL_PAPER_20_SESSION_PROFILE,
    validate_model_paper_horizon,
)
from thericher_v2.research.model_paper_proposal import (
    _ROUTE,
    ModelPaperTarget,
    _canonical,
    _digest,
    _pin,
    _unique,
)

MODEL_PAPER_WEIGHTS_PROFILE = "model-weights-nas-20session-2026-v1"
MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE = (
    "model-weights-nas-20session-early-exit-non-parity-2026-v1"
)
MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE = "model-weights-nas-5session-2026-v1"
MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE = "model-weights-nas-cash-5session-2026-v1"
MODEL_PAPER_WEIGHTS_SCHEMA = "model-paper-target-weight-input-v1"
WEIGHT_UNITS = "fraction_of_one_original_basis_gross_cohort_ceiling"
EXECUTION_BASIS = "gross_limit_cost_not_fees_settlement_or_replay_equivalence"
EARLY_EXIT_EXECUTION_BASIS = (
    "NON_PARITY_analytical_C_e19_early_exit_gross_limit_cost_not_fees_settlement"
)


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def model_paper_weights_horizon_profile(profile):
    """Map only explicit weight profiles; never infer a horizon from dates."""
    _need(type(profile) is str, "weights_profile_invalid")
    if profile in (MODEL_PAPER_WEIGHTS_PROFILE, MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE):
        return MODEL_PAPER_20_SESSION_PROFILE
    if profile in (
        MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE,
    ):
        return MODEL_PAPER_5_SESSION_PROFILE
    raise ValueError("weights_profile_invalid")


@dataclass(frozen=True, slots=True)
class ModelPaperWeightRow:
    slot: int
    route: str
    feature_known: bool
    weight: Decimal

    def __post_init__(self):
        _need(type(self.slot) is int and 0 <= self.slot < 512, "weights_slot_invalid")
        _need(type(self.route) is str, "weights_route_invalid")
        _need(type(self.feature_known) is bool, "weights_knownness_invalid")
        cash = self.route == "CASH"
        # CASH is an available allocation coordinate, never a market instrument.
        _need(not cash or self.feature_known, "weights_cash_knownness_invalid")
        # Missing features need no invented venue merely to preserve the full
        # symbol axis. Such rows cannot produce any routed proposal.
        unrouted = self.route.endswith("/UNAVAILABLE") and _ROUTE.fullmatch(
            self.route.removesuffix("/UNAVAILABLE") + "/NAS"
        )
        _need(
            cash or _ROUTE.fullmatch(self.route) or (not self.feature_known and unrouted),
            "weights_route_invalid",
        )
        _need(
            type(self.weight) is Decimal
            and self.weight.is_finite()
            and 0 <= self.weight <= 1
            and -324 <= self.weight.as_tuple().exponent <= 0,
            "weights_value_invalid",
        )
        _need(self.feature_known or self.weight == 0, "weights_unknown_positive")
        _need(
            Decimal(repr(float(self.weight))) == self.weight,
            "weights_not_binary64_canonical",
        )

    @property
    def eligibility(self):
        if self.route == "CASH":
            return "CASH_ALLOCATION"
        if not self.feature_known:
            return "FEATURE_UNAVAILABLE"
        if not self.route.endswith("/NAS"):
            return "UNSUPPORTED_VENUE"
        return "ELIGIBLE_NAS" if self.weight > 0 else "ZERO_WEIGHT"


def model_weight_bytes_ref(rows):
    """Hash the original full-axis binary64 values without normalization."""
    return (
        "sha256:"
        + hashlib.sha256(b"".join(struct.pack("<d", float(row.weight)) for row in rows)).hexdigest()
    )


def model_weight_mask_ref(rows):
    return "sha256:" + hashlib.sha256(_canonical([row.feature_known for row in rows])).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelPaperWeightsMetadata:
    model_id: str
    feature_schema_id: str
    model_ref: str
    adapter_ref: str
    affine_ref: str
    input_manifest_ref: str
    calendar_ref: str
    policy_ref: str
    full_output_ref: str
    feature_mask_ref: str
    weight_bytes_ref: str
    feature_window_end: datetime
    source_available_at: datetime
    input_asof: datetime
    inference_started_at: datetime
    inference_completed_at: datetime
    weights_observed_at: datetime
    exit_not_before: datetime
    original_basis_gross_ceiling: Decimal
    rows: tuple[ModelPaperWeightRow, ...]

    def __post_init__(self):
        _need(
            all(type(v) is str and v.strip() for v in (self.model_id, self.feature_schema_id)),
            "weights_identity_invalid",
        )
        for name in (
            "model_ref",
            "adapter_ref",
            "affine_ref",
            "input_manifest_ref",
            "calendar_ref",
            "policy_ref",
            "full_output_ref",
            "feature_mask_ref",
            "weight_bytes_ref",
        ):
            _pin(getattr(self, name))
        clocks = tuple(
            getattr(self, name)
            for name in (
                "feature_window_end",
                "source_available_at",
                "input_asof",
                "inference_started_at",
                "inference_completed_at",
                "weights_observed_at",
            )
        )
        _need(
            all(type(t) is datetime and t.utcoffset() == timedelta(0) for t in clocks)
            and clocks == tuple(sorted(clocks)),
            "weights_causal_clocks_invalid",
        )
        ceiling = self.original_basis_gross_ceiling
        _need(
            type(ceiling) is Decimal
            and ceiling.is_finite()
            and 0 < ceiling <= 1
            and -24 <= ceiling.as_tuple().exponent <= 0,
            "weights_cohort_ceiling_invalid",
        )
        _need(type(self.rows) is tuple and 0 < len(self.rows) <= 512, "weights_rows_invalid")
        for row in self.rows:
            _need(type(row) is ModelPaperWeightRow, "weights_row_type_invalid")
            row.__post_init__()
        _need(
            tuple(row.slot for row in self.rows) == tuple(range(len(self.rows)))
            and len({row.route.split("/")[0] for row in self.rows}) == len(self.rows),
            "weights_full_axis_invalid",
        )
        total = sum((Fraction(row.weight) for row in self.rows), Fraction())
        _need(abs(total - 1) <= Fraction(1, 10**12), "weights_unit_mass_invalid")
        _need(self.feature_mask_ref == model_weight_mask_ref(self.rows), "weights_mask_mismatch")
        _need(self.weight_bytes_ref == model_weight_bytes_ref(self.rows), "weights_bytes_mismatch")

    @property
    def eligible_weight(self):
        return sum(
            (Fraction(row.weight) for row in self.rows if row.eligibility == "ELIGIBLE_NAS"),
            Fraction(),
        )

    @property
    def skipped_weight(self):
        return sum(
            (Fraction(row.weight) for row in self.rows if row.eligibility == "UNSUPPORTED_VENUE"),
            Fraction(),
        )

    @property
    def cash_weight(self):
        return sum(
            (Fraction(row.weight) for row in self.rows if row.eligibility == "CASH_ALLOCATION"),
            Fraction(),
        )


def _validate_cash_profile(metadata, profile):
    slots = tuple(row.slot for row in metadata.rows if row.route == "CASH")
    if profile == MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE:
        _need(
            len(metadata.rows) > 1 and slots == (len(metadata.rows) - 1,),
            "weights_cash_axis_invalid",
        )
    else:
        _need(not slots, "weights_cash_profile_invalid")


@dataclass(frozen=True, slots=True)
class ModelPaperWeightsInput:
    metadata: ModelPaperWeightsMetadata
    targets: tuple[ModelPaperTarget, ...]
    entry_session: SessionWindow
    exit_session: SessionWindow
    profile: str = MODEL_PAPER_WEIGHTS_PROFILE
    weight_units: str = WEIGHT_UNITS
    execution_basis: str = EXECUTION_BASIS

    def __post_init__(self):
        validate_model_paper_weights_input(self)

    @property
    def policy_ref(self):
        return self.metadata.policy_ref

    @property
    def input_ref(self):
        return "sha256:" + hashlib.sha256(serialize_model_paper_weights_input(self)).hexdigest()


def _weight_targets(metadata, entry_session):
    reference = _digest(asdict(metadata))
    refs = DecisionReceiptReferences(
        "ref:" + metadata.policy_ref[7:],
        "ref:" + metadata.model_ref[7:],
        metadata.input_manifest_ref,
        "ref:" + reference[7:],
    )
    ceiling = Fraction(metadata.original_basis_gross_ceiling)
    remaining = ceiling
    targets = []
    for row in metadata.rows:
        if row.eligibility != "ELIGIBLE_NAS":
            continue
        # Each slot keeps its original ceiling. The remainder only trims roundoff;
        # it never reallocates an unsupported, unknown or rejected slot.
        amount = min(ceiling * Fraction(row.weight), remaining)
        units = amount * 10**24
        exposure = Decimal((0, tuple(map(int, str(units.numerator // units.denominator))), -24))
        remaining -= Fraction(exposure)
        if exposure <= 0:
            continue
        proposal = TargetExposureProposal(
            f"model-weights-nas-{reference[7:]}-{row.slot}",
            row.route.split("/")[0],
            "US",
            "enter",
            exposure,
            Decimal(0),
            metadata.feature_schema_id,
            "ready",
            metadata.weights_observed_at,
            entry_session.close_ts,
            metadata.feature_window_end,
            "untrusted_weight_gross_ceiling_native_risk_may_reduce_not_replay_or_alpha",
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
    # Finite native visits process the largest proposed budgets first. Every
    # eligible target remains; this is no TopK selection or weight transform.
    return tuple(
        sorted(targets, key=lambda target: (-Fraction(target.research_weight), target.slot))
    )


def prepare_model_paper_weights_input(
    metadata, *, entry_session, exit_session, profile=MODEL_PAPER_WEIGHTS_PROFILE
):
    model_paper_weights_horizon_profile(profile)
    _need(type(metadata) is ModelPaperWeightsMetadata, "weights_metadata_invalid")
    metadata.__post_init__()
    _validate_cash_profile(metadata, profile)
    return ModelPaperWeightsInput(
        metadata,
        _weight_targets(metadata, entry_session),
        entry_session,
        exit_session,
        profile=profile,
        execution_basis=(
            EARLY_EXIT_EXECUTION_BASIS
            if profile == MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE
            else EXECUTION_BASIS
        ),
    )


def validate_model_paper_weights_input(value):
    _need(type(value) is ModelPaperWeightsInput, "weights_profile_invalid")
    horizon_profile = model_paper_weights_horizon_profile(value.profile)
    early = value.profile == MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE
    _need(
        value.weight_units == WEIGHT_UNITS
        and value.execution_basis == (EARLY_EXIT_EXECUTION_BASIS if early else EXECUTION_BASIS),
        "weights_semantics_invalid",
    )
    _need(type(value.metadata) is ModelPaperWeightsMetadata, "weights_metadata_invalid")
    value.metadata.__post_init__()
    _validate_cash_profile(value.metadata, value.profile)
    first, last = value.entry_session, value.exit_session
    _need(type(first) is SessionWindow and type(last) is SessionWindow, "weights_sessions_invalid")
    validate_model_paper_horizon(first, last, profile=horizon_profile)
    _need(
        value.metadata.weights_observed_at < first.open_ts
        and value.metadata.exit_not_before
        == last.close_ts - timedelta(minutes=45 if early else 15),
        "weights_session_clocks_invalid",
    )
    _need(
        type(value.targets) is tuple and value.targets == _weight_targets(value.metadata, first),
        "weights_target_composition_changed",
    )
    return value


@dataclass(frozen=True, slots=True)
class ModelPaperEarlyExitWindow:
    """Operational deadlines, not an altered official session or closure proof."""

    entry_start: datetime
    entry_end: datetime
    exit_start: datetime
    exit_end: datetime
    cleanup_end: datetime
    closure_before: datetime


def model_paper_early_exit_window(value, *, operational_session=None):
    validate_model_paper_weights_input(value)
    _need(value.profile == MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE, "weights_profile_invalid")
    session = value.exit_session if operational_session is None else operational_session
    _need(type(session) is SessionWindow, "weights_sessions_invalid")
    official = us_equity_2026_session(session.open_ts.astimezone(US_EQUITY_EASTERN).date())
    _need(
        official is not None
        and official.window == session
        and session.open_ts >= value.exit_session.open_ts,
        "weights_sessions_invalid",
    )
    close = session.close_ts
    return ModelPaperEarlyExitWindow(
        value.entry_session.open_ts,
        value.entry_session.close_ts,
        close - timedelta(minutes=45),
        close - timedelta(minutes=25),
        close - timedelta(minutes=20),
        close - timedelta(minutes=15),
    )


def serialize_model_paper_weights_input(value):
    _need(type(value) is ModelPaperWeightsInput, "weights_input_type_invalid")
    return _canonical(dict(schema=MODEL_PAPER_WEIGHTS_SCHEMA, **asdict(value)))


def load_model_paper_weights_input(payload, *, expected_sha256, expected_policy_ref):
    """Reject ambiguous or executable payloads; regenerate every native proposal."""
    _pin(expected_policy_ref)
    _need(
        type(expected_sha256) is str and len(expected_sha256) == 64,
        "weights_input_pin_mismatch",
    )
    _pin("sha256:" + expected_sha256)
    _need(
        type(payload) is bytes
        and len(payload) <= 1024 * 1024
        and hashlib.sha256(payload).hexdigest() == expected_sha256,
        "weights_input_pin_mismatch",
    )
    document = json.loads(
        payload,
        object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("weights_nonfinite")),
    )
    _need(
        type(document) is dict
        and set(document)
        == {
            "schema",
            "profile",
            "metadata",
            "targets",
            "entry_session",
            "exit_session",
            "weight_units",
            "execution_basis",
        }
        and document["schema"] == MODEL_PAPER_WEIGHTS_SCHEMA
        and document["profile"]
        in (
            MODEL_PAPER_WEIGHTS_PROFILE,
            MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
            MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE,
            MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE,
        )
        and document["weight_units"] == WEIGHT_UNITS
        and document["execution_basis"]
        == (
            EARLY_EXIT_EXECUTION_BASIS
            if document["profile"] == MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE
            else EXECUTION_BASIS
        ),
        "weights_input_schema_invalid",
    )
    raw = document["metadata"]
    _need(
        type(raw) is dict and set(raw) == {f.name for f in fields(ModelPaperWeightsMetadata)},
        "weights_metadata_fields_invalid",
    )

    def decimal(text):
        _need(type(text) is str, "weights_decimal_invalid")
        try:
            return Decimal(text)
        except InvalidOperation:
            raise ValueError("weights_decimal_invalid") from None

    def timestamp(text):
        _need(type(text) is str, "weights_time_invalid")
        try:
            return require_utc(datetime.fromisoformat(text))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("weights_time_invalid") from None

    values = dict(raw)
    for name in (
        "feature_window_end",
        "source_available_at",
        "input_asof",
        "inference_started_at",
        "inference_completed_at",
        "weights_observed_at",
        "exit_not_before",
    ):
        values[name] = timestamp(raw[name])
    values["original_basis_gross_ceiling"] = decimal(raw["original_basis_gross_ceiling"])
    _need(type(raw["rows"]) is list, "weights_rows_invalid")
    rows = []
    for row in raw["rows"]:
        _need(
            type(row) is dict and set(row) == {f.name for f in fields(ModelPaperWeightRow)},
            "weights_row_fields_invalid",
        )
        rows.append(
            ModelPaperWeightRow(
                row["slot"], row["route"], row["feature_known"], decimal(row["weight"])
            )
        )
    values["rows"] = tuple(rows)
    metadata = ModelPaperWeightsMetadata(**values)
    _need(metadata.policy_ref == expected_policy_ref, "weights_policy_pin_mismatch")

    def session(raw_session):
        _need(
            type(raw_session) is dict and set(raw_session) == {"open_ts", "close_ts"},
            "weights_session_fields_invalid",
        )
        return SessionWindow(**{key: timestamp(value) for key, value in raw_session.items()})

    result = prepare_model_paper_weights_input(
        metadata,
        entry_session=session(document["entry_session"]),
        exit_session=session(document["exit_session"]),
        profile=document["profile"],
    )
    _need(
        serialize_model_paper_weights_input(result) == payload,
        "weights_payload_not_canonical_or_derived",
    )
    return result
