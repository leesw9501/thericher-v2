"""Finite host-verified R3 shadow metadata for the native Paper consumer.

This does not replay Data files or an old Goal82 result envelope. The caller
independently pins bytes produced after the current strict host loader. Expired
metadata remains restorable for owned recovery; Runtime owns fresh-entry expiry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Context, Decimal, localcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from thericher_v2.execution.kis_paper_five_session import KisPaperFiveSessionCohort

    from .five_session_paper_decision import FiveSessionPaperDecision
    from .prospective_five_session_shadow_input import ProspectiveShadowInput

MAX_EXCHANGE_BYTES = 65536
SOURCE_PINS = (
    (
        "src/thericher_v2/data/prospective_five_session_shadow_link.py",
        "sha256:2f77b48b534025c1c718fbc7555321c358ebde279a76de489a8c87816bf6f6d0",
    ),
    (
        "src/thericher_v2/execution/kis_paper_five_session.py",
        "sha256:b22da30fcbfbb24f81efd8622822e9382a31832fdbd570be261217dabf719fb6",
    ),
    (
        "src/thericher_v2/research/prospective_five_session_shadow_decision.py",
        "sha256:8691f40425925c64eb27e09c123dd78d1148a22372677dea174de7e0fb164692",
    ),
    (
        "src/thericher_v2/research/prospective_five_session_shadow_input.py",
        "sha256:525eff415a6f33453450a5ec043934c15105b041c0bb529ca0eb423b7a4ca136",
    ),
)
SOURCE_PINS_R4 = (
    (
        "src/thericher_v2/data/prospective_five_session_shadow_link.py",
        "sha256:69a75f1de570962c06880797780b4040c86e3a7fb37ede78fd595a01b1b1f95b",
    ),
    (
        "src/thericher_v2/execution/kis_paper_five_session.py",
        "sha256:b22da30fcbfbb24f81efd8622822e9382a31832fdbd570be261217dabf719fb6",
    ),
    (
        "src/thericher_v2/research/prospective_five_session_shadow_decision.py",
        "sha256:a18ecff797be9cb7399e2eae0981afaf803a5eb7609e744ec2fbafdfb2857831",
    ),
    (
        "src/thericher_v2/research/prospective_five_session_shadow_input.py",
        "sha256:f4b811d2a4197fe642ce1dc53afd4f84aea11b7122ba68261b544240d7e422af",
    ),
)
_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_CONTEXT = Context(prec=64, rounding=ROUND_DOWN)
_JOB = "sha256:90131beb0785da155beb6d435e2a9a07180408264b95ebe650e3d43cd5728e47"
_WORKER = "sha256:9846b862c878fbe68f5c5a38205db2aef0a774bec50b2b69680d6a9706c6bd97"
_IDENTITY = "sha256:533d35e49da24aa81255e7e540d7ddae216e5b7177a45cf3f7cd01252f4bfe09"
_CALENDAR = "sha256:096c904ad30cfaaa2fae4176d4bb9ffc226749e516faf81dacd8813dbb7b39d5"
_DATA = "sha256:37b8ba01b35b6f165d680b0c629adaceef604e4f68a5529c8b676bbf57fc4085"
_METADATA = "sha256:a596ed494ae7be6dd8176cc4ecbb749c6c36d1ef15b867b6a5816bc45421f7e4"
_GRADE = "hash_linked_metadata_availability_assumed_not_observed"
_KIND = "prospective_five_session_paper_exchange_v1"
_ROOT = (
    "D:/thericher-v2/model-artifacts/research/"
    "kis-stock-five-session-prospective512-shadow-delivery-v1"
)
_LINEAGE = {
    "delivery_root": _ROOT + "/delivery-r3",
    "claim_namespace": _ROOT + "/delivery-r2/runtime",
    "original_job_sha256": (
        "sha256:e8550670d5b18a9bbf81600cb9d399e591e73300e95d9bbf996de5f73837be0a"
    ),
    "original_installation_plan_sha256": (
        "sha256:d321f6211d68afb73d4e6555fc2f33c7b660e35dbca2cad01eb76714873e16df"
    ),
}
_FIELDS = frozenset(
    "schema_version kind lineage job_sha256 control_sha256 source_pins "
    "source_grade decision cohort links".split()
)


class PaperExchangeError(ValueError):
    """Static finite-exchange failure; never includes payload or exception bodies."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise PaperExchangeError(reason)


def _pin(value: object) -> str:
    _require(type(value) is str and bool(_PIN.fullmatch(value)), "exchange_pin")
    return value


def _utc(value: object) -> datetime:
    _require(type(value) is datetime and value.utcoffset() == timedelta(0), "exchange_clock")
    return value


def _clock(value: object) -> datetime:
    _require(type(value) is str, "exchange_clock")
    return _utc(datetime.fromisoformat(value))


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _default(value: object) -> str:
    if type(value) is datetime:
        return _utc(value).isoformat()
    if type(value) is Decimal and value.is_finite():
        return format(value, "f")
    raise PaperExchangeError("exchange_type")


def _encode(value: object) -> bytes:
    return json.dumps(
        value, default=_default, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _pairs(rows: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in rows:
        _require(key not in value, "exchange_duplicate_key")
        value[key] = item
    return value


@dataclass(frozen=True, slots=True, repr=False)
class PaperExchangePins:
    """Independent caller control facts; never populated from incoming JSON."""

    job_sha256: str
    control_sha256: str
    source_pins: tuple[tuple[str, str], ...]
    identities: tuple[str, ...]
    calendar_ref: str
    prior_close_at: datetime
    nominal_decision_at: datetime
    session_opens: tuple[datetime, ...]
    session_closes: tuple[datetime, ...]
    entry_valid_until: datetime


@dataclass(frozen=True, slots=True, repr=False)
class ProspectivePaperExchange:
    decision: FiveSessionPaperDecision
    cohort: KisPaperFiveSessionCohort
    links: tuple[tuple[str, object], ...]
    job_sha256: str
    control_sha256: str
    source_grade: str
    exchange_sha256: str
    restored_at: datetime

    def expected_engine_links(self) -> dict[str, object]:
        return dict(self.links)


def _pins(pins: PaperExchangePins) -> None:
    _require(type(pins) is PaperExchangePins, "exchange_caller_pins")
    _pin(pins.job_sha256)
    _, _, sources, _ = _source_contract(pins)
    _pin(pins.control_sha256)
    _require(type(pins.source_pins) is tuple and pins.source_pins == sources, "exchange_sources")
    _require(
        type(pins.identities) is tuple
        and len(pins.identities) == 512
        and all(
            type(k) is str and re.fullmatch(r"[A-Z][A-Z0-9.]{0,15}/NAS", k) for k in pins.identities
        )
        and len(set(pins.identities)) == 512
        and _sha(json.dumps(list(pins.identities), separators=(",", ":")).encode()) == _IDENTITY,
        "exchange_identity",
    )
    _require(_pin(pins.calendar_ref) == _CALENDAR, "exchange_calendar")
    _require(
        type(pins.session_opens) is type(pins.session_closes) is tuple
        and len(pins.session_opens) == len(pins.session_closes) == 5,
        "exchange_sessions",
    )
    for at in (
        pins.prior_close_at,
        pins.nominal_decision_at,
        pins.entry_valid_until,
        *pins.session_opens,
        *pins.session_closes,
    ):
        _utc(at)
    _require(
        pins.prior_close_at.isoformat() == "2026-10-16T20:00:00+00:00"
        and pins.nominal_decision_at.isoformat() == "2026-10-19T12:30:00+00:00"
        and all(
            o.isoformat() == f"2026-10-{19 + i}T13:30:00+00:00"
            and c.isoformat() == f"2026-10-{19 + i}T20:00:00+00:00"
            for i, (o, c) in enumerate(zip(pins.session_opens, pins.session_closes, strict=True))
        )
        and pins.entry_valid_until == pins.session_opens[0] + timedelta(minutes=10),
        "exchange_official_clocks",
    )


def _source_contract(pins: PaperExchangePins):
    if pins.job_sha256 == _JOB:
        return _DATA, _WORKER, SOURCE_PINS, _LINEAGE
    from thericher_v2.data.prospective_five_session_shadow_link import (
        _R4_PLAN_SHA,
        _R4_ROOT,
        _r4_binding,
    )

    try:
        binding = _r4_binding()
    except ValueError:
        raise PaperExchangeError("exchange_job") from None
    _require(pins.job_sha256 == binding["job_sha"], "exchange_job")
    _require(
        type(SOURCE_PINS_R4) is tuple
        and len(SOURCE_PINS_R4) == len(SOURCE_PINS)
        and tuple(name for name, _ in SOURCE_PINS_R4) == tuple(name for name, _ in SOURCE_PINS),
        "exchange_sources",
    )
    for _, wanted in SOURCE_PINS_R4:
        _pin(wanted)
    return (
        _R4_PLAN_SHA,
        binding["worker_sha"],
        SOURCE_PINS_R4,
        {**_LINEAGE, "delivery_root": _R4_ROOT},
    )


def _decision(payload: object, links: object, pins: PaperExchangePins, as_of: datetime):
    from thericher_v2.contracts import decision_instrument_binding_ref
    from thericher_v2.execution.kis_paper_five_session import cohort_from_paper_decision

    from .prospective_five_session_shadow_decision import EXPECTED_LINK_FIELDS, _restore

    _require(type(links) is dict and set(links) == EXPECTED_LINK_FIELDS, "exchange_links")
    for key, value in links.items():
        if key.endswith("sha256"):
            _pin(value)
    data_plan, worker, _, _ = _source_contract(pins)
    fixed = dict(
        worker_sha256=worker,
        input_plan_sha256=data_plan,
        input_metadata_sha256=_METADATA,
        calendar26_sha256=_CALENDAR,
    )
    _require(all(links[k] == v for k, v in fixed.items()), "exchange_fixed_links")
    _require(
        type(links["source_count"]) is int
        and 28 <= links["source_count"] <= 2048
        and type(links["data_source_count"]) is int
        and links["data_source_count"] == 28,
        "exchange_link_counts",
    )
    dto = _restore(payload)
    _require(
        dto.status == "prepared" and dto.reason == "frozen_first_surviving_slot",
        "exchange_prepared_only",
    )
    _require(
        dto.input_manifest_ref == links["input_manifest_sha256"]
        and dto.receipt.campaign_ref == "ref:" + links["plan_sha256"][7:]
        and dto.prior_close_at == pins.prior_close_at
        and dto.nominal_decision_at == pins.nominal_decision_at
        and dto.session_opens == pins.session_opens
        and dto.session_closes == pins.session_closes
        and dto.entry_valid_until == pins.entry_valid_until,
        "exchange_decision_links",
    )
    key = pins.identities[dto.selected_slot]
    _require(
        dto.instrument_key == key
        and dto.instrument_binding_ref
        == decision_instrument_binding_ref(symbol=key[:-4], market="US", decision_class="enter"),
        "exchange_selected_binding",
    )
    captured, started, finished = (
        _clock(links[k]) for k in ("input_captured_at", "engine_started_at", "engine_finished_at")
    )
    _require(
        pins.prior_close_at
        <= captured
        <= started
        <= dto.inference_completed_at
        <= dto.as_of
        <= finished
        <= as_of
        and finished < pins.entry_valid_until
        and (finished - started).total_seconds() < 120
        and started.date() == finished.date() == pins.prior_close_at.date(),
        "exchange_actual_clocks",
    )
    return dto, cohort_from_paper_decision(dto, calendar_ref=pins.calendar_ref)


def encode_prospective_paper_exchange(
    loaded: ProspectiveShadowInput, *, pins: PaperExchangePins
) -> bytes:
    """Encode only current strict-loaded ready input; persist/pin bytes externally."""
    from thericher_v2.data.prospective_five_session_shadow_link import VerifiedShadowLink
    from thericher_v2.execution.kis_paper_five_session import KisPaperFiveSessionCohort

    from .five_session_paper_decision import FiveSessionPaperDecision
    from .prospective_five_session_shadow_input import ProspectiveShadowInput

    try:
        _pins(pins)
        _require(
            type(loaded) is ProspectiveShadowInput
            and loaded.status == "ready"
            and loaded.source_grade == _GRADE
            and type(loaded.link) is VerifiedShadowLink,
            "exchange_loaded_input",
        )
        _require(
            type(loaded.decision) is FiveSessionPaperDecision
            and type(loaded.cohort) is KisPaperFiveSessionCohort,
            "exchange_loaded_types",
        )
        links = loaded.link.expected_engine_links()
        data_plan, _, _, lineage = _source_contract(pins)
        _require(
            loaded.link.job_sha == pins.job_sha256
            and loaded.link.data_plan_sha == data_plan
            and loaded.link.calendar_sha == _CALENDAR
            and loaded.link.engine_result_sha == links["result_sha256"]
            and loaded.link.engine_plan_sha == links["plan_sha256"]
            and loaded.link.input_manifest_ref.sha256 == links["input_manifest_sha256"],
            "exchange_verified_link",
        )
        payload = json.loads(_encode(asdict(loaded.decision)))
        with localcontext(_CONTEXT):
            dto, cohort = _decision(payload, links, pins, _clock(links["engine_finished_at"]))
            _require(
                dto == loaded.decision and cohort == loaded.cohort and loaded.reason == dto.reason,
                "exchange_loaded_cohort",
            )
            raw = _encode(
                dict(
                    schema_version=1,
                    kind=_KIND,
                    lineage=lineage,
                    job_sha256=pins.job_sha256,
                    control_sha256=pins.control_sha256,
                    source_pins=pins.source_pins,
                    source_grade=_GRADE,
                    decision=asdict(dto),
                    cohort=asdict(cohort),
                    links=links,
                )
            )
        _require(0 < len(raw) <= MAX_EXCHANGE_BYTES, "exchange_size")
        return raw
    except PaperExchangeError:
        raise
    except Exception:
        raise PaperExchangeError("exchange_invalid_metadata") from None


def restore_prospective_paper_exchange(
    raw: bytes, *, expected_sha256: str, pins: PaperExchangePins, as_of: datetime
) -> ProspectivePaperExchange:
    """Restore independently hash-bound metadata, including after entry expiry.

    No fresh-entry authorization follows from decoding. Retained recovery must
    still match Execution's original request/cohort/history and complete book.
    The host-verified projection is not independently rerun Data/OS evidence.
    """
    try:
        _pins(pins)
        _, _, _, lineage = _source_contract(pins)
        _utc(as_of)
        _require(type(raw) is bytes and 0 < len(raw) <= MAX_EXCHANGE_BYTES, "exchange_size")
        _require(_sha(raw) == _pin(expected_sha256), "exchange_hash")
        body = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=lambda _: _require(False, "exchange_number"),
            parse_constant=lambda _: _require(False, "exchange_nonfinite"),
        )
        _require(type(body) is dict and set(body) == _FIELDS, "exchange_fields")
        _require(
            type(body["schema_version"]) is int
            and body["schema_version"] == 1
            and body["kind"] == _KIND
            and body["lineage"] == lineage,
            "exchange_schema_lineage",
        )
        _require(
            body["job_sha256"] == pins.job_sha256
            and body["control_sha256"] == pins.control_sha256
            and body["source_grade"] == _GRADE
            and body["source_pins"] == [list(row) for row in pins.source_pins],
            "exchange_caller_binding",
        )
        with localcontext(_CONTEXT):
            dto, cohort = _decision(body["decision"], body["links"], pins, as_of)
            _require(_encode(body["cohort"]) == _encode(asdict(cohort)), "exchange_native_cohort")
            _require(raw == _encode(body), "exchange_noncanonical")
        return ProspectivePaperExchange(
            dto,
            cohort,
            tuple(sorted(body["links"].items())),
            pins.job_sha256,
            pins.control_sha256,
            _GRADE,
            expected_sha256,
            as_of,
        )
    except PaperExchangeError:
        raise
    except Exception:
        raise PaperExchangeError("exchange_invalid_metadata") from None
