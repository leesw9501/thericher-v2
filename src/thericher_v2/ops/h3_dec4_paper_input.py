"""Translate the exact Dec4 shadow point into the existing NET25 guest ABI."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.data import us_equity_session as calendar
from thericher_v2.data.kis_paper_h3_capture import _read_native
from thericher_v2.models.h3_publisher_input import H3InputBinding
from thericher_v2.models.h3_shadow_point import (
    DEC4_BINDING_CLOCK,
    DEC4_DATA_HARD,
    STATS_SHA,
    WEIGHTS_SHA,
    read_dec4_h3_shadow_point,
)
from thericher_v2.ops import h3_dec4_point_owner as owner
from thericher_v2.ops.h3_dec4_point_join import read_supervised_point
from thericher_v2.ops.h3_dec4_retained_input import Dec4H3RetainedRef, retain_dec4_h3_input
from thericher_v2.ops.h3_dec4_run import Dec4H3Run
from thericher_v2.ops.paper_startup import Phase
from thericher_v2.research import model_paper_weights as weights

DEC4_NET25_PROFILE = weights.MODEL_PAPER_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3_PROFILE
_FEATURE_CLOSE = datetime(2026, 12, 3, 21, tzinfo=UTC)
_VALID_UNTIL = datetime(2026, 12, 4, 14, 35, tzinfo=UTC)
_OWNER_KEYS = {
    "schema",
    "source_sha256",
    "source72_sha256",
    "data_source_sha256",
    "data_attempt_sha256",
    "data_owner_sha256",
    "ready_sha256",
    "data_ready_sha256",
    "attempt_sha256",
    "point_sha256",
    "closed_at",
    "financial_authority",
}
_DATA_OWNER_KEYS = {
    "schema",
    "source_sha256",
    "attempt_sha256",
    "native_start",
    "closed_at",
    "ready_sha256",
    "target_status",
    "target_custody_sha256",
}


@dataclass(frozen=True)
class Dec4PaperInput:
    payload: bytes = field(repr=False)
    sha256: str
    policy_ref: str
    synthetic: bool


def _source_ref(filename: str) -> str:
    path = Path(filename)
    return "sha256:" + hashlib.sha256(_read_native(path.parent, str(path))).hexdigest()


def prepare_dec4_paper_input(
    run: Dec4H3Run,
    *,
    ready_sha256: str,
    point_sha256: str,
    policy_ref: str,
    adapter_ref: str,
    calendar_ref: str,
    fixture_now: datetime | None = None,
) -> Dec4PaperInput:
    """Read only; the caller owns publication closure, account and budget admission.

    Expected digests come from the current owned producer outcomes, not the
    latest file on disk. Actual mode never accepts an injected clock. This
    adapter does not convert local capture availability into provider finality.
    """
    if run.synthetic is not (fixture_now is not None):
        raise ValueError("h3_native_fixture_clock_mode")
    now = datetime.now(UTC) if fixture_now is None else fixture_now
    if now.utcoffset() != timedelta(0) or not DEC4_BINDING_CLOCK <= now < _VALID_UNTIL:
        raise ValueError("h3_native_point_outside_window")
    if calendar_ref != _source_ref(calendar.__file__) or adapter_ref != _source_ref(__file__):
        raise ValueError("h3_native_loaded_source_mismatch")

    root = run.input_root
    if (root / "DATA-READY.pending").exists():
        raise ValueError("h3_native_data_receipt_pending")
    if _read_native(root, str(root / "DATA-READY.json")) != run._receipt(ready_sha256):
        raise ValueError("h3_native_data_receipt_mismatch")
    raw = _read_native(root, str(root / "READY.json"))
    if hashlib.sha256(raw).hexdigest() != ready_sha256:
        raise ValueError("h3_native_ready_digest_mismatch")
    ready = json.loads(raw)
    binding = H3InputBinding(
        run.data_source_sha256, DEC4_BINDING_CLOCK, DEC4_DATA_HARD, run.synthetic
    )
    if (
        ready["schema"] != "H3_PUBLISHER_INPUT_READY_V1"
        or ready["source_sha256"] != binding.source_sha256
        or ready["synthetic"] is not binding.synthetic
        or ready["decision_at"] != binding.decision_at.isoformat()
    ):
        raise ValueError("h3_native_ready_binding_mismatch")
    closed, available = (datetime.fromisoformat(ready[k]) for k in ("closed_at", "ready_at"))
    if (
        closed.utcoffset() != timedelta(0)
        or available.utcoffset() != timedelta(0)
        or not _FEATURE_CLOSE < closed <= available < DEC4_DATA_HARD
    ):
        raise ValueError("h3_native_ready_clock_mismatch")

    point = read_dec4_h3_shadow_point(
        run.point_root, binding=binding, ready_sha256=ready_sha256, point_sha256=point_sha256
    )
    rows = tuple(
        weights.ModelPaperWeightRow(r["slot"], r["route"], r["known"], Decimal(r["weight"]))
        for r in point["rows"]
    )
    entry = calendar.us_equity_2026_session(date(2026, 12, 4)).window
    exit_ = calendar.us_equity_2026_session(date(2026, 12, 9)).window
    metadata = weights.ModelPaperWeightsMetadata(
        model_id="LSTM_H3_FIXED_SELECTED_INNER_BEST10",
        feature_schema_id="D1_OWN_SPY_QQQ_60X12_IND8_V1",
        model_ref="sha256:" + WEIGHTS_SHA,
        adapter_ref=adapter_ref,
        affine_ref="sha256:" + STATS_SHA,
        input_manifest_ref="sha256:" + ready_sha256,
        calendar_ref=calendar_ref,
        policy_ref=policy_ref,
        full_output_ref="sha256:" + point_sha256,
        feature_mask_ref=weights.model_weight_mask_ref(rows),
        weight_bytes_ref=weights.model_weight_bytes_ref(rows),
        feature_window_end=_FEATURE_CLOSE,
        source_available_at=available,
        input_asof=datetime.fromisoformat(point["input_verified_at"]),
        inference_started_at=datetime.fromisoformat(point["inference_started_at"]),
        inference_completed_at=datetime.fromisoformat(point["inference_completed_at"]),
        weights_observed_at=datetime.fromisoformat(point["observed_at"]),
        exit_not_before=exit_.open_ts,
        original_basis_gross_ceiling=Decimal(".1"),
        rows=rows,
    )
    value = weights.prepare_model_paper_weights_input(
        metadata, entry_session=entry, exit_session=exit_, profile=DEC4_NET25_PROFILE
    )
    payload = weights.serialize_model_paper_weights_input(value)
    digest = hashlib.sha256(payload).hexdigest()
    if (
        weights.load_model_paper_weights_input(
            payload, expected_sha256=digest, expected_policy_ref=policy_ref
        )
        != value
    ):
        raise ValueError("h3_native_codec_readback_mismatch")
    if fixture_now is None and not DEC4_BINDING_CLOCK <= datetime.now(UTC) < _VALID_UNTIL:
        raise ValueError("h3_native_point_outside_window")
    return Dec4PaperInput(payload, digest, policy_ref, run.synthetic)


def retain_completed_dec4_paper_input(
    run: Dec4H3Run,
    *,
    point_source_sha256: str,
    point_owner_sha256: str,
    prove_point_closed: Callable[[str], bool],
    retained_path: Path,
    source_sha256: str,
    policy_ref: str,
    adapter_ref: str,
    calendar_ref: str,
    fixture_now: datetime | None = None,
) -> Dec4H3RetainedRef:
    """Prepare an entry only after independently joined exact point publication.

    The bank-owned caller supplies the independently recorded closure digest
    and the probe; reading this file and echoing its digest is not that proof.
    Exit restores the returned reference and never calls this entry path.
    """
    if (
        run.synthetic is not (fixture_now is not None)
        or not owner._digest(point_source_sha256)
        or not owner._digest(point_owner_sha256)
        or run.data_source_sha256 != owner.DATA_SOURCE_SHA256
    ):
        raise ValueError("h3_entry_point_binding")
    if not run.synthetic:
        data_root = owner._DATA / "run"
        if (run.market_root, run.artifact_root, run.input_root, run.point_root) != (
            owner._MARKET,
            data_root / "capture",
            data_root / "input",
            data_root / "point",
        ):
            raise ValueError("h3_entry_point_binding")

    def read_completion():
        now = datetime.now(UTC) if fixture_now is None else fixture_now
        if not owner._is_utc(now) or not DEC4_BINDING_CLOCK <= now < _VALID_UNTIL:
            raise ValueError("h3_native_point_outside_window")
        if prove_point_closed(point_owner_sha256) is not True:
            raise ValueError("h3_entry_point_closure_unknown")
        for name in ("OWNER-CLOSED.pending", "POINT.pending"):
            owner._absent(run.point_root / name)
        root = run.point_root.parent
        raw = owner._pinned(run.point_root / "OWNER-CLOSED.json", point_owner_sha256, 16_384)
        done = owner._record(raw, _OWNER_KEYS)
        if (
            done["schema"] != "H3_DEC4_POINT_OWNER_CLOSED_V1"
            or done["source_sha256"] != point_source_sha256
            or done["source72_sha256"] != owner.SOURCE72_SHA256
            or done["data_source_sha256"] != run.data_source_sha256
            or done["financial_authority"] is not False
        ):
            raise ValueError("h3_entry_point_binding")
        locations = {
            "attempt_sha256": root / "POINT-ATTEMPT.json",
            "data_attempt_sha256": root / "owner/ATTEMPT.json",
            "data_owner_sha256": root / "OWNER-CLOSED.json",
            "ready_sha256": run.input_root / "READY.json",
            "data_ready_sha256": run.input_root / "DATA-READY.json",
            "point_sha256": run.point_root / "POINT.json",
        }
        if any(not owner._digest(done[key]) for key in locations):
            raise ValueError("h3_entry_point_binding")
        linked = {key: owner._pinned(path, done[key], 16_384) for key, path in locations.items()}
        attempt = owner._record(linked["attempt_sha256"], {"schema", "source_sha256", "started_at"})
        data = owner._record(linked["data_owner_sha256"], _DATA_OWNER_KEYS)
        if (
            attempt["schema"] != "H3_DEC4_POINT_ATTEMPT_V1"
            or attempt["source_sha256"] != done["source_sha256"]
            or data["schema"] != "H3_DEC3_OWNER_CLOSED_V1"
            or data["source_sha256"] != done["data_source_sha256"]
            or data["attempt_sha256"] != done["data_attempt_sha256"]
            or data["ready_sha256"] != done["ready_sha256"]
        ):
            raise ValueError("h3_entry_point_binding")
        started = owner._stamp(attempt["started_at"])
        closed = owner._stamp(done["closed_at"])
        observed = owner._stamp(json.loads(linked["point_sha256"])["observed_at"])
        data_closed = owner._stamp(data["closed_at"])
        if (
            not owner.OPENS <= started < owner.LAST_START
            or not started <= observed <= closed < owner.HARD_STOP <= now
            or not owner.CAPTURE_OPENS_UTC <= data_closed < owner.INPUT_HARD_STOP_UTC
        ):
            raise ValueError("h3_entry_point_clocks")
        return done

    done = read_completion()
    result = prepare_dec4_paper_input(
        run,
        ready_sha256=done["ready_sha256"],
        point_sha256=done["point_sha256"],
        policy_ref=policy_ref,
        adapter_ref=adapter_ref,
        calendar_ref=calendar_ref,
        fixture_now=fixture_now,
    )
    if read_completion() != done:
        raise ValueError("h3_entry_point_changed")
    return retain_dec4_h3_input(
        retained_path,
        result.payload,
        source_sha256=source_sha256,
        point_sha256=done["point_sha256"],
        policy_ref=policy_ref,
        synthetic=run.synthetic,
    )


@dataclass(frozen=True)
class Dec4BankPhaseInput:
    """Phase input callback for the existing single-bank coordinator."""

    run: Dec4H3Run
    point_completion_pin: Callable[[], str]
    original_retained: Callable[[], Dec4H3RetainedRef]
    fixture_now: datetime | None = None

    def __call__(self, ready, phase: Phase) -> Dec4H3RetainedRef:
        if ready.plan.phase != phase:
            raise ValueError("h3_entry_phase_mismatch")
        if phase == "exit":
            # BankLeg independently checks source/path/policy and restores
            # the exact bytes; point and new target callbacks are never used.
            return self.original_retained()
        if phase != "entry":
            raise ValueError("h3_entry_phase_mismatch")
        point_source = ready.source["point_owner_source_sha256"]
        control = Path(ready.source["point_control_path"])
        completion = self.point_completion_pin()

        def joined():
            return read_supervised_point(
                control=control, point_source_sha256=point_source, completion_sha256=completion
            )

        return retain_completed_dec4_paper_input(
            self.run,
            point_source_sha256=point_source,
            point_owner_sha256=joined(),
            prove_point_closed=lambda expected: joined() == expected,
            retained_path=Path(ready.source["retained_input_path"]),
            source_sha256=ready.plan.source_sha256,
            policy_ref=ready.source["execution_policy_ref"],
            adapter_ref=ready.source["paper_input_adapter_ref"],
            calendar_ref=ready.source["paper_input_calendar_ref"],
            fixture_now=self.fixture_now,
        )
