"""Invented categorical H3 display; no artifact imports or financial operations."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from thericher_v2.dashboard import operations as ops
from thericher_v2.dashboard import view

NOW = datetime(2026, 11, 3, 20, 56, tzinfo=UTC)


def test_h3_legacy_display_contracts_and_publisher_exclusion():
    assert [run.key for run in ops._RUNS] == ["h20", "googl"]
    assert ops.display_contract_sha256("h20") == (
        "8cff64ebbc54b638939fe20b5944015fa51cbd05468ee57a6a8753f363bb5287"
    )
    assert ops.display_contract_sha256("googl") == (
        "c747f75d7b248601044a6b875dff346b358b4e1d78c1e2115ce8db8e4cc23804"
    )
    assert ops._H3_RUN.read is None and ops._H3_RUN.evidence_pointer is None
    assert ops.display_contract_sha256("h3") == (
        "b8176d42d100a1c8805f6c8adf750f068509c13bfd40529893e91ce22800d593"
    )


def test_h3_missing_future_is_unknown_and_no_read_opportunity():
    row = ops.build_operations_snapshot(None, now=NOW)["runs"][-1]
    assert row["key"] == "h3" and row["symbol"] == "AMD"
    assert row["read_due_at"] is None and row["status"] == "unknown"
    assert all(row[field] == "unknown" for field in ops._FINANCIAL)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "validated"),
        ("submit", "accepted"),
        ("fill", "confirmed"),
        ("inventory", "owned"),
        ("evidence_at", "2026-11-03T20:55:30Z"),
        ("evidence_pointer", "artifact:foreign/RESULT.json"),
        ("result_sha256", "a" * 64),
        ("reason_code", "host_published_public_outcome"),
        ("private_id", "invented-marker"),
    ],
)
def test_h3_rejects_financial_promotion_or_extra_fields(field, value):
    packet = ops.build_h3_public_projection(now=NOW)
    packet[field] = value
    with pytest.raises(ValueError):
        ops._decode_projection(json.dumps(packet).encode(), ops._H3_RUN, NOW)


def test_h3_view_sanitizer_is_idempotent_and_read_clock_is_null():
    packet = ops.build_h3_public_projection(now=NOW)
    row = ops._decode_projection(json.dumps(packet).encode(), ops._H3_RUN, NOW)
    supplied = {"observed_at": ops._iso(NOW), "runs": [row]}
    first = view._safe_operations(supplied, now=ops._iso(NOW))
    second = view._safe_operations(first, now=ops._iso(NOW))
    assert first == second
    h3 = first["runs"][-1]
    assert h3["status"] == "unknown" and h3["read_due_at"] is None
    assert all(h3[name] == "unknown" for name in ops._FINANCIAL)


@pytest.mark.parametrize("field,value", [("submit", "accepted"), ("fill", "confirmed"),
                                        ("inventory", "owned"), ("status", "validated")])
def test_h3_view_cannot_promote_forged_financial_fields(field, value):
    row = ops.build_operations_snapshot(None, now=NOW)["runs"][-1]
    row[field] = value
    result = view._safe_operations({"observed_at": ops._iso(NOW), "runs": [row]},
                                   now=ops._iso(NOW))
    h3 = result["runs"][-1]
    assert h3["status"] == "invalid"
    assert all(h3[name] == "unknown" for name in ops._FINANCIAL)
    assert h3["read_due_at"] is h3["evidence_at"] is h3["evidence_pointer"] is None


def test_h3_stale_diagnostic_has_no_financial_claim():
    packet = ops.build_h3_public_projection(now=NOW)
    row = ops._decode_projection(
        json.dumps(packet).encode(),
        ops._H3_RUN,
        NOW + timedelta(seconds=301),
    )
    assert row["status"] == "unknown" and row["reason_code"] == "projection_stale"
    assert row["evidence_at"] is None and row["inventory"] == "unknown"
