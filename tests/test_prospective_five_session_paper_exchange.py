"""Portable finite SYN exchange; no filesystem evidence, model or side effects."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import localcontext
from pathlib import Path

import pytest

import test_prospective_five_session_shadow_input as input_fixture
from thericher_v2.research import prospective_five_session_paper_exchange as s


@pytest.fixture
def packet(monkeypatch):
    chain = input_fixture.chain.__wrapped__(monkeypatch)
    loaded = input_fixture.load(chain)
    assert loaded.status == "ready"
    metadata = json.loads(chain[2].data_plan_bytes)["metadata"]
    links = loaded.link.expected_engine_links()
    # Synthetic independent pins only; production source/control facts unchanged.
    for name, value in (
        ("_JOB", chain[2].job_sha),
        ("_DATA", links["input_plan_sha256"]),
        ("_METADATA", links["input_metadata_sha256"]),
        ("_CALENDAR", metadata["calendar26_sha256"]),
        ("_IDENTITY", s._sha(json.dumps(metadata["keys"], separators=(",", ":")).encode())),
    ):
        monkeypatch.setattr(s, name, value)
    dto = loaded.decision
    pins = s.PaperExchangePins(
        chain[2].job_sha,
        "sha256:" + "f" * 64,
        s.SOURCE_PINS,
        tuple(metadata["keys"]),
        metadata["calendar26_sha256"],
        dto.prior_close_at,
        dto.nominal_decision_at,
        dto.session_opens,
        dto.session_closes,
        dto.entry_valid_until,
    )
    raw = s.encode_prospective_paper_exchange(loaded, pins=pins)
    return raw, pins, loaded


def restore(packet, *, raw=None, pins=None, as_of=input_fixture.MONDAY, expected=None):
    raw = packet[0] if raw is None else raw
    return s.restore_prospective_paper_exchange(
        raw,
        expected_sha256=s._sha(raw) if expected is None else expected,
        pins=packet[1] if pins is None else pins,
        as_of=as_of,
    )


def mutated(packet, path, value):
    body = json.loads(packet[0])
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def test_canonical_ready_projection_preserves_identity_target_links(packet):
    raw, pins, loaded = packet
    out = restore(packet)
    assert raw == s.encode_prospective_paper_exchange(loaded, pins=pins)
    assert out.decision == loaded.decision and out.cohort == loaded.cohort
    assert out.decision.proposal.target_exposure == loaded.decision.proposal.target_exposure
    assert out.cohort.fingerprint != out.decision.cohort_ref
    assert out.expected_engine_links() == loaded.link.expected_engine_links()
    assert len(out.links) == 15 and len(raw) < s.MAX_EXCHANGE_BYTES
    assert out.exchange_sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert out.restored_at == input_fixture.MONDAY
    assert out.decision.inference_completed_at.date() == input_fixture.FRIDAY.date()
    with pytest.raises(FrozenInstanceError):
        out.control_sha256 = "modified"
    independent = out.expected_engine_links()
    independent["source_count"] = 999
    assert out.expected_engine_links()["source_count"] != 999


def test_expired_metadata_survives_for_exact_retained_recovery(packet):
    late = datetime(2026, 10, 23, 19, 55, tzinfo=UTC)
    out = restore(packet, as_of=late)
    assert out.restored_at == late > out.decision.entry_valid_until
    assert out.decision == packet[2].decision and out.cohort == packet[2].cohort
    assert out.cohort.entry_window_end == packet[1].entry_valid_until
    assert out.cohort.exit_due == packet[1].session_closes[-1] - timedelta(minutes=10)


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_fixed_decimal_context_canonical_bytes_and_receipts(packet, precision):
    with localcontext() as context:
        context.prec = precision
        raw = s.encode_prospective_paper_exchange(packet[2], pins=packet[1])
        out = restore(packet, raw=raw)
        assert context.prec == precision
    assert raw == packet[0] and out.decision == packet[2].decision
    assert out.cohort == packet[2].cohort


@pytest.mark.parametrize("failure", ["no_intent", "grade", "cohort", "link", "reason"])
def test_encoder_requires_consistent_strict_loaded_ready(packet, failure):
    loaded = packet[2]
    if failure == "no_intent":
        loaded = replace(loaded, status="no_intent")
    elif failure == "grade":
        loaded = replace(loaded, source_grade="observed_final")
    elif failure == "cohort":
        loaded = replace(loaded, cohort=replace(loaded.cohort, source_ref="sha256:" + "0" * 64))
    elif failure == "link":
        loaded = replace(loaded, link=replace(loaded.link, job_sha="sha256:" + "0" * 64))
    else:
        loaded = replace(loaded, reason="modified")
    with pytest.raises(s.PaperExchangeError):
        s.encode_prospective_paper_exchange(loaded, pins=packet[1])


def test_encoder_rejects_foreign_dataclass_before_any_copy_hook(packet):
    class Trap:
        def __deepcopy__(self, memo):
            pytest.fail("foreign copy hook executed")

    @dataclass
    class Foreign:
        value: object

    loaded = replace(packet[2], decision=Foreign(Trap()))
    with pytest.raises(s.PaperExchangeError, match="exchange_loaded_types"):
        s.encode_prospective_paper_exchange(loaded, pins=packet[1])


@pytest.mark.parametrize(
    "field",
    [
        "job_sha256",
        "control_sha256",
        "calendar_ref",
        "source_pins",
        "identities",
        "entry_valid_until",
    ],
)
def test_independent_pins_are_not_selected_from_payload(packet, field):
    pins = packet[1]
    value = "sha256:" + "0" * 64
    if field == "source_pins":
        value = tuple(reversed(pins.source_pins))
    elif field == "identities":
        value = tuple(reversed(pins.identities))
    elif field == "entry_valid_until":
        value = pins.entry_valid_until + timedelta(minutes=1)
    with pytest.raises(s.PaperExchangeError):
        restore(packet, pins=replace(pins, **{field: value}))


@pytest.mark.parametrize(
    "name,version",
    [
        ("proposal", 2),
        ("proposal", 3),
        ("receipt", 2),
        ("receipt", 3),
    ],
)
def test_nested_schema1_only_even_with_rebound_byte_hash(packet, name, version):
    raw = mutated(packet, ("decision", name, "schema_version"), version)
    with pytest.raises(s.PaperExchangeError):
        restore(packet, raw=raw)


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), True),
        (("schema_version",), 2),
        (("decision", "proposal", "target_exposure"), 0.005),
        (("decision", "proposal", "target_exposure"), "0.02"),
        (("decision", "selected_slot"), 201),
        (("decision", "model_ref"), "ref:" + "0" * 64),
        (("links", "source_count"), True),
        (("links", "data_source_count"), 27),
        (("links", "worker_sha256"), "sha256:" + "0" * 64),
        (("links", "input_manifest_sha256"), "sha256:" + "0" * 64),
        (("cohort", "source_ref"), "sha256:" + "0" * 64),
        (("cohort", "entry_window_end"), "2026-10-19T13:41:00+00:00"),
        (("lineage", "claim_namespace"), "D:/substitute/runtime"),
    ],
)
def test_type_source_clock_slot_and_fraction_mutations_rejected(packet, path, value):
    with pytest.raises(s.PaperExchangeError):
        restore(packet, raw=mutated(packet, path, value))


@pytest.mark.parametrize("scope", ["outer", "decision", "cohort", "links"])
def test_extra_fields_are_not_silently_dropped(packet, scope):
    body = json.loads(packet[0])
    target = body if scope == "outer" else body[scope]
    target["unknown"] = "never_deserialized"
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(s.PaperExchangeError):
        restore(packet, raw=raw)


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_keys_rejected_before_constructor(packet, nested):
    raw = (
        packet[0].replace(b'"selected_slot":200', b'"selected_slot":200,"selected_slot":200')
        if nested
        else packet[0][:-1] + b',"schema_version":1}'
    )
    with pytest.raises(s.PaperExchangeError, match="exchange_duplicate_key"):
        restore(packet, raw=raw)


def test_hash_noncanonical_size_nonfinite_and_missing_bytes(packet):
    with pytest.raises(s.PaperExchangeError, match="exchange_hash"):
        restore(packet, raw=packet[0] + b" ", expected=s._sha(packet[0]))
    with pytest.raises(s.PaperExchangeError, match="exchange_noncanonical"):
        restore(packet, raw=packet[0] + b" ")
    for raw in (b"", b" " * (s.MAX_EXCHANGE_BYTES + 1)):
        with pytest.raises(s.PaperExchangeError, match="exchange_size"):
            restore(packet, raw=raw)
    raw = packet[0].replace(b'"schema_version":1', b'"schema_version":NaN', 1)
    with pytest.raises(s.PaperExchangeError, match="exchange_nonfinite"):
        restore(packet, raw=raw)
    with pytest.raises(s.PaperExchangeError, match="exchange_size"):
        s.restore_prospective_paper_exchange(
            None, expected_sha256=s._sha(packet[0]), pins=packet[1], as_of=input_fixture.MONDAY
        )


def test_actual_decode_clock_cannot_precede_friday_publication(packet):
    with pytest.raises(s.PaperExchangeError, match="exchange_actual_clocks"):
        restore(packet, as_of=packet[2].decision.prior_close_at)


def test_no_old_result_outer_contract_or_exposed_raw_values(packet):
    body = json.loads(packet[0])
    assert set(body) == s._FIELDS
    assert not set(body) & {"elapsed_seconds", "raw_rows", "scores", "account", "teacher_path"}
    assert set(body["links"]) == set(packet[2].link.expected_engine_links())
    assert "0.004998750312421894526368" in packet[0].decode()
    assert "target_exposure" not in repr(restore(packet))


def test_import_is_inert_without_models_providers_or_pickle():
    root = str(Path(__file__).resolve().parents[1] / "src")
    script = (
        f"import sys; sys.path.insert(0, {root!r}); "
        "import thericher_v2.research.prospective_five_session_paper_exchange; "
        "assert not any(m in sys.modules for m in ('torch','numpy','sklearn','pickle',"
        "'thericher_v2.execution.kis_paper','thericher_v2.research.five_session_tree'))"
    )
    run = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, timeout=10, check=False
    )
    assert run.returncode == 0 and run.stdout == run.stderr == b""
