from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data import validate_kis_paper_private_intraday_v1_index_metadata
from thericher_v2.execution.kis_private_intraday_backfill import _validate_index

_EXPECTED_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
_VALIDATION_MESSAGE = "KIS private intraday v1 index metadata is invalid"


@pytest.mark.parametrize("key_kind", ["current", "legacy"])
def test_kis_paper_intraday_index_metadata_matches_writer_for_valid_retained_forms(
    key_kind: str,
) -> None:
    index = _valid_index(key_kind=key_kind)

    _validate_index(index)
    projection = validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=_EXPECTED_TARGETS,
    )

    assert projection.generation == 3
    assert tuple(target.target_key for target in projection.targets) == (
        "QQQ/NAS/1m",
        "SPY/AMS/1m",
    )
    qqq = projection.targets[0]
    assert qqq.symbol == "QQQ"
    assert qqq.exchange == "NAS"
    assert dict(qqq.next_cursor or {}) == {"keyb": "20260721123000", "next": "1"}
    assert len(qqq.retained_chunks) == 1
    assert qqq.retained_chunks[0].rows == (
        ("20260721T093100", _digest("b")),
        ("20260721T093000", _digest("a")),
    )
    assert qqq.retained_chunks[0].collected_at == datetime(2026, 7, 21, 20, 1, tzinfo=UTC)
    assert qqq.retained_chunks[0].input_cursor is None
    assert dict(qqq.retained_chunks[0].output_cursor or {}) == {
        "keyb": "20260721122900",
        "next": "1",
    }
    assert qqq.next_cursor is not None
    with pytest.raises(TypeError):
        qqq.next_cursor["next"] = "2"  # type: ignore[index]


def test_kis_paper_intraday_index_metadata_marks_legacy_candidate_conflict_chunks() -> None:
    index = _valid_index(key_kind="current")
    chunk = index["targets"][0]["chunks"][0]
    assert isinstance(chunk, dict)
    chunk.update(
        {
            "outcome": "partial",
            "reason": "minute_duplicate_conflict",
            "conflict_origin": "candidate_batch",
        }
    )

    projection = validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=_EXPECTED_TARGETS,
    )

    retained = projection.targets[0].retained_chunks[0]
    assert retained.candidate_batch_conflicted is True


def test_kis_paper_intraday_index_metadata_ignores_unretained_marker() -> None:
    index = _valid_index(key_kind="current")
    marker = index["targets"][0]["chunks"][1]
    assert marker == {
        "raw_market_data_retained": False,
        "historical_note": ["no", "cache", "semantics"],
    }

    projection = validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=_EXPECTED_TARGETS,
    )

    assert len(projection.targets[0].retained_chunks) == 1


def test_kis_paper_intraday_index_metadata_accepts_verified_head_quarantine_marker() -> None:
    index = _valid_index(key_kind="current")
    chunks = index["targets"][0]["chunks"]
    assert isinstance(chunks, list)
    chunks[1] = {
        "raw_market_data_retained": False,
        "historical_note": "quarantined_head_retained_cache_conflict",
        "quarantined_chunk_key": _digest("chunk"),
        "quarantined_manifest_hash": _digest("manifest"),
        "quarantined_raw_sha256": _digest("raw"),
    }

    projection = validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=_EXPECTED_TARGETS,
    )

    assert len(projection.targets[0].retained_chunks) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda marker: marker.pop("quarantined_chunk_key"),
        lambda marker: marker.update(quarantined_manifest_hash="sha256:" + "A" * 64),
        lambda marker: marker.update(historical_note="one-shot observation only"),
    ],
    ids=["missing_chunk_identity", "invalid_manifest_hash", "altered_note"],
)
def test_kis_paper_intraday_index_metadata_rejects_malformed_head_quarantine_marker(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    index = _valid_index(key_kind="current")
    chunks = index["targets"][0]["chunks"]
    assert isinstance(chunks, list)
    marker: dict[str, object] = {
        "raw_market_data_retained": False,
        "historical_note": "quarantined_head_retained_cache_conflict",
        "quarantined_chunk_key": _digest("chunk"),
        "quarantined_manifest_hash": _digest("manifest"),
        "quarantined_raw_sha256": _digest("raw"),
    }
    mutate(marker)
    chunks[1] = marker

    with pytest.raises(ValueError, match=_VALIDATION_MESSAGE):
        validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_EXPECTED_TARGETS,
        )


@pytest.mark.parametrize("origin", ["candidate_batch", "retained_cache"])
def test_kis_paper_intraday_index_metadata_accepts_safe_duplicate_conflict_origin(
    origin: str,
) -> None:
    index = _valid_index(key_kind="current")
    target = index["targets"][0]
    assert isinstance(target, dict)
    target["last_reason"] = "minute_duplicate_conflict"
    target["last_conflict_origin"] = origin

    validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=_EXPECTED_TARGETS,
    )


@pytest.mark.parametrize(
    ("reason", "origin"),
    [
        ("minute_duplicate_conflict", None),
        ("minute_response_empty", "candidate_batch"),
        (None, "retained_cache"),
        ("minute_duplicate_conflict", "unexpected"),
        ("minute_duplicate_conflict", ["candidate_batch"]),
        ("minute_duplicate_conflict", {"origin": "candidate_batch"}),
    ],
)
def test_kis_paper_intraday_index_metadata_rejects_invalid_duplicate_conflict_origin(
    reason: str | None,
    origin: object,
) -> None:
    index = _valid_index(key_kind="current")
    target = index["targets"][0]
    assert isinstance(target, dict)
    target["last_reason"] = reason
    target["last_conflict_origin"] = origin

    with pytest.raises(ValueError, match=_VALIDATION_MESSAGE):
        validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_EXPECTED_TARGETS,
        )


def test_kis_paper_intraday_index_metadata_accepts_legacy_duplicate_reason_without_origin() -> None:
    index = _valid_index(key_kind="current")
    target = index["targets"][0]
    assert isinstance(target, dict)
    target["last_reason"] = "minute_duplicate_conflict"

    validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=_EXPECTED_TARGETS,
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda index: index["targets"][0].pop("chunks"),
        lambda index: index["targets"][0]["chunks"][0].pop("collected_at_utc"),
    ],
    ids=["target", "chunk"],
)
def test_kis_paper_intraday_index_metadata_rejects_truncated_target_or_chunk(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    index = _valid_index(key_kind="current")

    mutate(index)

    with pytest.raises(ValueError, match=_VALIDATION_MESSAGE):
        validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_EXPECTED_TARGETS,
        )


def test_kis_paper_intraday_index_metadata_rejects_duplicate_chunk_key() -> None:
    index = _valid_index(key_kind="current")
    chunks = index["targets"][0]["chunks"]
    assert isinstance(chunks, list)
    chunks.append(deepcopy(chunks[0]))

    with pytest.raises(ValueError, match=_VALIDATION_MESSAGE):
        validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_EXPECTED_TARGETS,
        )


def test_kis_paper_intraday_index_metadata_rejects_invalid_row_fingerprint() -> None:
    index = _valid_index(key_kind="current")
    chunk = index["targets"][0]["chunks"][0]
    assert isinstance(chunk, dict)
    rows = chunk["row_fingerprints"]
    assert isinstance(rows, dict)
    rows["20260721T093100"] = "sha256:" + "A" * 64

    with pytest.raises(ValueError, match=_VALIDATION_MESSAGE):
        validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_EXPECTED_TARGETS,
        )


def _valid_index(*, key_kind: str) -> dict[str, object]:
    rows = {
        "20260721T093100": _digest("b"),
        "20260721T093000": _digest("a"),
    }
    current_key = _chunk_key(
        target_key="QQQ/NAS/1m",
        input_cursor=None,
        row_fingerprints=rows,
    )
    chunk_key = (
        current_key
        if key_kind == "current"
        else _legacy_chunk_key(target_key="QQQ/NAS/1m", input_cursor=None)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "generation": 3,
        "targets": [
            {
                "target_key": "QQQ/NAS/1m",
                "symbol": " qqq ",
                "exchange": " nas ",
                "next_cursor": {"keyb": " 20260721123000 ", "next": " 1 "},
                "last_reason": None,
                "last_observed_at_utc": "2026-07-21T20:01:00Z",
                "chunks": [
                    {
                        "chunk_key": chunk_key,
                        "outcome": "committed",
                        "input_cursor": None,
                        "output_cursor": {"keyb": "20260721122900", "next": "1"},
                        "manifest_path": "snapshots/unit/manifest.json",
                        "manifest_hash": _digest("manifest"),
                        "raw_sha256": _digest("raw"),
                        "raw_market_data_retained": True,
                        "row_count": len(rows),
                        "row_fingerprints": rows,
                        "exact_overlap_rows": 0,
                        "conflicting_overlap_rows": 0,
                        "collected_at_utc": "2026-07-21T20:01:00Z",
                    },
                    {
                        "raw_market_data_retained": False,
                        "historical_note": ["no", "cache", "semantics"],
                    },
                ],
            },
            {
                "target_key": "SPY/AMS/1m",
                "symbol": "SPY",
                "exchange": "AMS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": [],
            },
        ],
    }


def _chunk_key(
    *,
    target_key: str,
    input_cursor: dict[str, str] | None,
    row_fingerprints: dict[str, str],
) -> str:
    return _sha256_payload(
        {
            "backfill_version": "v1",
            "input_cursor": input_cursor,
            "row_fingerprints": dict(sorted(row_fingerprints.items())),
            "target_key": target_key,
        }
    )


def _legacy_chunk_key(*, target_key: str, input_cursor: dict[str, str] | None) -> str:
    return _sha256_payload(
        {
            "backfill_version": "v1",
            "input_cursor": input_cursor,
            "target_key": target_key,
        }
    )


def _sha256_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
