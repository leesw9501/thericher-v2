"""Pure finite restore of Goal93 shadow evidence, not a broker consumer.

Expected links come from independently checked claim/terminal/Data custody.
The fixed worker pin attests first-surviving-slot/all-weight semantics; omitted
scores and weights cannot be reconstructed or independently ranked here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Context, Decimal, DecimalException, localcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .five_session_paper_decision import FiveSessionPaperDecision

_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_IDENTITY = "sha256:533d35e49da24aa81255e7e540d7ddae216e5b7177a45cf3f7cd01252f4bfe09"
_WORKER_R3 = "sha256:9846b862c878fbe68f5c5a38205db2aef0a774bec50b2b69680d6a9706c6bd97"
_FIXED_LINKS = {
    "worker_sha256": "sha256:a8dcd255b1d469c2de8e49b08105e30f2540ca2786a380d751fcabbd33615a5b",
    "input_plan_sha256": "sha256:37b8ba01b35b6f165d680b0c629adaceef604e4f68a5529c8b676bbf57fc4085",
    "input_metadata_sha256": (
        "sha256:a596ed494ae7be6dd8176cc4ecbb749c6c36d1ef15b867b6a5816bc45421f7e4"
    ),
    "calendar26_sha256": "sha256:096c904ad30cfaaa2fae4176d4bb9ffc226749e516faf81dacd8813dbb7b39d5",
}
_TEACHER = "ref:ca6b36d1686365fe4f6680589bb0927e7e2e143e1b69a7ab13dd88339d2ae5a0"
_SOURCES = (
    ("feature", "sha256:04df85bc83e18cba01718be9398bf7eaad1f716d399510fd1ec28e45c9c77709"),
    ("inference", "sha256:2f64a23813f1c617667d7632a9a1575f9532eeff36450d0f8dfa09fe823e91f5"),
    ("teacher_metadata", "sha256:2ce286eeec36093f412eb9b27966a6ab6869c9856cc24f7b5b06adc87b3eeb35"),
)
_LINKS = frozenset(
    "plan_sha256 worker_sha256 source_pins_sha256 input_plan_sha256 "
    "input_manifest_sha256 input_metadata_sha256 physical_capture_sha256 "
    "source_chunks_sha256 calendar26_sha256 source_count data_source_count "
    "input_captured_at".split()
)
EXPECTED_LINK_FIELDS = _LINKS | {"result_sha256", "engine_started_at", "engine_finished_at"}
_RESULT_FIELDS = frozenset(
    "added_eligible availability broker_calls calendar26_sha256 calendar_validation "
    "complete_prior21_count completed_at data_source_count decision elapsed_seconds eligible_count "
    "exposure_units fit_calls frame_sha256 identity_count inference_calls inference_completed_at "
    "input_captured_at input_manifest_sha256 input_metadata_sha256 input_plan_sha256 "
    "model_dump_retained order_consumer original_eligible phase physical_capture_sha256 "
    "plan_sha256 raw_rows_retained reason scores_retained shadow_only source_count "
    "source_pins_sha256 source_chunks_sha256 sources_reattested status supported "
    "worker_sha256 worker_started_at".split()
)


class ShadowDecisionError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ShadowDecisionError(reason)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _utc(at: object) -> datetime:
    _require(type(at) is datetime and at.utcoffset() == timedelta(0), "shadow_clock")
    return at


def _clock(raw: object) -> datetime:
    _require(type(raw) is str, "shadow_clock")
    return _utc(datetime.fromisoformat(raw))


def _pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        _require(key not in result, "shadow_duplicate_key")
        result[key] = value
    return result


def _fields(payload: object, cls: type) -> dict:
    _require(
        type(payload) is dict and set(payload) == {f.name for f in fields(cls)},
        "shadow_constructor_fields",
    )
    return dict(payload)


def _restore(payload: object) -> FiveSessionPaperDecision:
    from thericher_v2.contracts import TargetExposureProposal

    from .decision_receipt import ResearchDecisionReceipt
    from .five_session_paper_decision import FiveSessionPaperDecision

    args = _fields(payload, FiveSessionPaperDecision)
    for key in (
        "nominal_decision_at",
        "prior_close_at",
        "entry_valid_until",
        "inference_completed_at",
        "as_of",
    ):
        args[key] = _clock(args[key])
    for key in ("session_opens", "session_closes"):
        _require(type(args[key]) is list and len(args[key]) == 5, "shadow_sessions")
        args[key] = tuple(_clock(at) for at in args[key])
    rows = args["source_pins"]
    _require(
        type(rows) is list and all(type(row) is list and len(row) == 2 for row in rows),
        "shadow_sources",
    )
    args["source_pins"] = tuple(tuple(row) for row in rows)
    _require(args["source_pins"] == _SOURCES and args["model_ref"] == _TEACHER, "shadow_sources")
    for key, cls in (("proposal", TargetExposureProposal), ("receipt", ResearchDecisionReceipt)):
        if args[key] is None:
            continue
        item = _fields(args[key], cls)
        _require(
            type(item["schema_version"]) is int and item["schema_version"] == 1,
            "shadow_schema_version",
        )
        for field in ("decided_at", "valid_until"):
            item[field] = _clock(item[field])
        if key == "proposal":
            item["feature_window_end"] = _clock(item["feature_window_end"])
            for field in ("target_exposure", "confidence"):
                value = item[field]
                _require(
                    type(value) is str
                    and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value)
                    and len(value) <= 128,
                    "shadow_decimal",
                )
                item[field] = Decimal(value)
                _require(item[field].is_finite(), "shadow_decimal")
        args[key] = cls(**item)
        _require(
            all(getattr(args[key], name) == value for name, value in item.items()),
            "shadow_constructor_normalization",
        )
    return FiveSessionPaperDecision(**args)


@dataclass(frozen=True, slots=True)
class ProspectiveShadowDecisionBinding:
    """Shadow metadata only; Execution owns native cohort conversion and custody."""

    status: str
    reason: str
    decision: FiveSessionPaperDecision | None
    calendar_ref: str | None
    result_sha256: str | None
    shadow_only: bool = True
    order_consumer: bool = False

    def __post_init__(self) -> None:
        _require(
            self.shadow_only is True
            and self.order_consumer is False
            and self.status in ("bound_shadow_metadata", "unavailable"),
            "shadow_binding_scope",
        )


def restore_prospective_shadow_decision(
    raw: bytes | None,
    *,
    expected_links: Mapping[str, object],
    identities: tuple[str, ...],
    prior_close_at: datetime,
    nominal_decision_at: datetime,
    session_opens: tuple[datetime, ...],
    session_closes: tuple[datetime, ...],
    entry_valid_until: datetime,
    as_of: datetime,
    expected_worker_sha256: str = _FIXED_LINKS["worker_sha256"],
) -> ProspectiveShadowDecisionBinding:
    """Restore exact caller-bound evidence without I/O, inference or scaling.

    Expected fields are ``EXPECTED_LINK_FIELDS``; clock values are UTC ISO
    strings. The caller independently binds the full chain and source-map digest.
    This checks its finite projection, not physical capture/provider finality.
    Research ``decision.cohort_ref`` is ref:, never the native sha256 fingerprint.
    R3 requires an explicit independently frozen caller pin; omitted means R2.
    Only these two released worker byte identities are accepted.
    """
    _utc(as_of)
    if raw is None:
        return ProspectiveShadowDecisionBinding("unavailable", "missing_result", None, None, None)
    try:
        _require(type(raw) is bytes and 0 < len(raw) <= 1024**2, "shadow_size")
        _require(
            isinstance(expected_links, Mapping) and set(expected_links) == EXPECTED_LINK_FIELDS,
            "shadow_expected_fields",
        )
        for key, value in expected_links.items():
            if key.endswith("sha256"):
                _require(type(value) is str and bool(_PIN.fullmatch(value)), "shadow_expected_pin")
        _require(_sha(raw) == expected_links["result_sha256"], "shadow_result_hash")
        _require(
            type(expected_worker_sha256) is str
            and expected_worker_sha256 in (_FIXED_LINKS["worker_sha256"], _WORKER_R3)
            and expected_links["worker_sha256"] == expected_worker_sha256
            and all(
                expected_links[k] == v for k, v in _FIXED_LINKS.items() if k != "worker_sha256"
            ),
            "shadow_fixed_source",
        )
        r = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _require(False, "shadow_nonfinite"),
        )
        _require(type(r) is dict and set(r) == _RESULT_FIELDS, "shadow_result_fields")
        _require(all(r[k] == expected_links[k] for k in _LINKS), "shadow_expected_link")
        _require(
            r["status"] in ("prepared", "no_intent")
            and r["phase"] == "complete"
            and r["sources_reattested"] is True
            and r["shadow_only"] is True
            and r["order_consumer"]
            is r["raw_rows_retained"]
            is r["scores_retained"]
            is r["model_dump_retained"]
            is False
            and all(type(r[k]) is int for k in ("fit_calls", "broker_calls", "inference_calls"))
            and r["fit_calls"] == r["broker_calls"] == 0
            and r["inference_calls"] == 1
            and r["availability"] == "assumed_not_observed"
            and r["exposure_units"] == "fraction_of_original_shared_basis"
            and r["calendar_validation"] == "Data_pinned_21plus5_not_regenerated_in_worker",
            "shadow_scope",
        )
        limits = {
            "identity_count": (512, 512),
            "eligible_count": (0, 512),
            "original_eligible": (0, 128),
            "added_eligible": (0, 384),
            "complete_prior21_count": (0, 512),
            "source_count": (1, 2048),
            "data_source_count": (28, 28),
        }
        _require(
            all(type(r[k]) is int and lo <= r[k] <= hi for k, (lo, hi) in limits.items())
            and r["eligible_count"] == r["original_eligible"] + r["added_eligible"]
            and r["eligible_count"] <= r["complete_prior21_count"]
            and r["data_source_count"] <= r["source_count"]
            and type(r["supported"]) is bool
            and r["supported"] == (r["eligible_count"] >= 128 and r["added_eligible"] >= 64),
            "shadow_counts",
        )
        _require(
            type(r["elapsed_seconds"]) in (int, float)
            and math.isfinite(r["elapsed_seconds"])
            and 0 <= r["elapsed_seconds"] < 115
            and bool(_PIN.fullmatch(r["frame_sha256"])),
            "shadow_elapsed_or_frame",
        )
        _require(
            type(identities) is tuple
            and len(identities) == len(set(identities)) == 512
            and all(
                type(k) is str and re.fullmatch(r"[A-Z][A-Z0-9.]{0,15}/NAS", k) for k in identities
            )
            and _sha(json.dumps(list(identities), separators=(",", ":")).encode()) == _IDENTITY,
            "shadow_identity",
        )
        _require(
            type(session_opens) is type(session_closes) is tuple
            and len(session_opens) == len(session_closes) == 5,
            "shadow_sessions",
        )
        for at in (
            prior_close_at,
            nominal_decision_at,
            entry_valid_until,
            *session_opens,
            *session_closes,
        ):
            _utc(at)
        _require(
            prior_close_at.isoformat() == "2026-10-16T20:00:00+00:00"
            and nominal_decision_at.isoformat() == "2026-10-19T12:30:00+00:00"
            and all(
                o.isoformat() == f"2026-10-{19 + i}T13:30:00+00:00"
                and c.isoformat() == f"2026-10-{19 + i}T20:00:00+00:00"
                for i, (o, c) in enumerate(zip(session_opens, session_closes, strict=True))
            )
            and entry_valid_until == session_opens[0] + timedelta(minutes=10),
            "shadow_official_clocks",
        )
        started, inferred, finished, captured = (
            _clock(r[k])
            for k in (
                "worker_started_at",
                "inference_completed_at",
                "completed_at",
                "input_captured_at",
            )
        )
        _require(
            prior_close_at
            <= captured
            <= _clock(expected_links["engine_started_at"])
            <= started
            <= inferred
            <= finished
            <= _clock(expected_links["engine_finished_at"])
            <= as_of
            and finished < entry_valid_until
            and (finished - started).total_seconds() < 120
            and started.date() == finished.date() == prior_close_at.date(),
            "shadow_actual_clocks",
        )
        with localcontext(Context(prec=64, rounding=ROUND_DOWN)):
            dto = _restore(r["decision"])
            _require(
                dto.status == r["status"]
                and dto.reason == r["reason"]
                and dto.frame_ref == r["frame_sha256"]
                and dto.input_manifest_ref == r["input_manifest_sha256"]
                and dto.inference_completed_at == inferred
                and inferred <= dto.as_of <= finished
                and dto.nominal_decision_at == nominal_decision_at
                and dto.prior_close_at == prior_close_at
                and dto.session_opens == session_opens
                and dto.session_closes == session_closes
                and dto.entry_valid_until == entry_valid_until,
                "shadow_decision_binding",
            )
            if dto.selected_slot is not None:
                from thericher_v2.contracts import decision_instrument_binding_ref

                key = identities[dto.selected_slot]
                _require(
                    dto.instrument_key == key
                    and dto.instrument_binding_ref
                    == decision_instrument_binding_ref(
                        symbol=key[:-4], market="US", decision_class="enter"
                    ),
                    "shadow_selected_binding",
                )
            _require(
                dto.receipt is None or dto.receipt.campaign_ref == "ref:" + r["plan_sha256"][7:],
                "shadow_campaign_binding",
            )
            cohort = dict(
                campaign="ref:" + r["plan_sha256"][7:],
                frame=dto.frame_ref[7:],
                input=dto.input_manifest_ref,
                model=dto.model_ref,
                sources=dto.source_pins,
                allocation=dto.allocation_ref,
                slot=dto.selected_slot,
                instrument=dto.instrument_binding_ref,
            )
            _require(
                dto.cohort_ref
                == "ref:"
                + _sha(
                    json.dumps(
                        cohort, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode()
                )[7:],
                "shadow_research_cohort_binding",
            )
            if dto.status == "prepared":
                valid = r["supported"] and dto.reason == "frozen_first_surviving_slot"
            elif dto.reason == "prior_causal_support":
                valid = not r["supported"] and dto.selected_slot is None
            elif dto.reason == "model_cash_veto":
                valid = r["supported"] and dto.selected_slot is None
            else:
                valid = (
                    r["supported"]
                    and dto.selected_slot is not None
                    and dto.reason
                    in (
                        "selected_instrument_unavailable",
                        "selected_instrument_mismatch",
                        "exposure_underflow",
                    )
                )
            _require(bool(valid), "shadow_decision_reason")
        if as_of >= entry_valid_until:
            return ProspectiveShadowDecisionBinding(
                "unavailable",
                "entry_window_closed",
                None,
                r["calendar26_sha256"],
                expected_links["result_sha256"],
            )
        return ProspectiveShadowDecisionBinding(
            "bound_shadow_metadata" if dto.status == "prepared" else "unavailable",
            dto.reason,
            dto,
            r["calendar26_sha256"],
            expected_links["result_sha256"],
        )
    except ShadowDecisionError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        DecimalException,
        OverflowError,
    ) as error:
        raise ShadowDecisionError("shadow_invalid_metadata") from error
