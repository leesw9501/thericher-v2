from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest

from thericher_v2.data.kis_daily_event_boundary_audit import (
    KisDailyEventBoundaryAuditError,
    KisDailyEventBoundaryMaskedPair,
    load_kis_daily_event_boundary_audit,
)

_CATALOG_DATASET_HASH = "sha256:" + "a" * 64
_CATALOG_INDEX_HASH = "sha256:" + "b" * 64
_SIDECAR_DATASET_HASH = "sha256:" + "c" * 64
_SIDECAR_MANIFEST_HASH = "sha256:" + "d" * 64
_SESSION_DATES_HASH = "sha256:" + "e" * 64


def test_loads_a_hash_pinned_price_free_audit(tmp_path: Path) -> None:
    path, expected = _write_audit(tmp_path)

    loaded = load_kis_daily_event_boundary_audit(path, **expected)

    assert loaded.path == path.resolve()
    assert loaded.artifact_sha256 == expected["expected_artifact_sha256"]
    assert loaded.lineage.catalog_dataset_hash == _CATALOG_DATASET_HASH
    assert tuple(partition.name for partition in loaded.partitions) == (
        "development",
        "purge",
        "validation",
        "embargo",
        "untouched_tail",
    )
    assert loaded.partition("validation").session_count == 4
    assert loaded.masked_pairs_by_symbol["QQQ"] == (
        KisDailyEventBoundaryMaskedPair(
            "QQQ", date(2024, 1, 3), date(2024, 1, 4), ("event_buffer",)
        ),
        KisDailyEventBoundaryMaskedPair(
            "QQQ", date(2024, 1, 12), date(2024, 1, 13), ("chronological_boundary",)
        ),
    )
    with pytest.raises(TypeError):
        loaded.masked_pairs_by_symbol["QQQ"] = ()  # type: ignore[index]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"expected_artifact_sha256": "sha256:" + "f" * 64}, "artifact hash mismatch"),
        ({"expected_catalog_dataset_hash": "sha256:" + "f" * 64}, "lineage mismatch"),
        ({"expected_mask_identity": "sha256:" + "f" * 64}, "mask identity mismatch"),
        ({"expected_partition_identity": "sha256:" + "f" * 64}, "partition identity mismatch"),
    ],
)
def test_rejects_hash_lineage_mask_and_partition_drift(
    tmp_path: Path,
    override: dict[str, str],
    message: str,
) -> None:
    path, expected = _write_audit(tmp_path)

    with pytest.raises(KisDailyEventBoundaryAuditError, match=message):
        load_kis_daily_event_boundary_audit(path, **(expected | override))


def test_rejects_malformed_untouched_tail_geometry(tmp_path: Path) -> None:
    document = _audit_document()
    document["partitions"][-1]["session_count"] = 3
    _refresh_identities(document)
    path, expected = _write_audit(tmp_path, document=document)

    with pytest.raises(KisDailyEventBoundaryAuditError, match="partition geometry"):
        load_kis_daily_event_boundary_audit(path, **expected)


@pytest.mark.parametrize("field", ["close", "per_bar_return"])
def test_rejects_persisted_price_or_per_bar_return_fields(tmp_path: Path, field: str) -> None:
    document = _audit_document()
    document["masked_pairs"][0][field] = "forbidden"
    path, expected = _write_audit(tmp_path, document=document)

    with pytest.raises(KisDailyEventBoundaryAuditError, match="raw price or return fields"):
        load_kis_daily_event_boundary_audit(path, **expected)


def test_loader_needs_no_network_or_environment_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, expected = _write_audit(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the offline audit loader must not access network or environment")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    loaded = load_kis_daily_event_boundary_audit(path, **expected)

    assert loaded.mask_identity == expected["expected_mask_identity"]


def _write_audit(
    tmp_path: Path,
    *,
    document: dict[str, object] | None = None,
) -> tuple[Path, dict[str, str]]:
    resolved_document = deepcopy(document) if document is not None else _audit_document()
    _refresh_identities(resolved_document)
    payload = (json.dumps(resolved_document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = tmp_path / "event-boundary-audit.json"
    path.write_bytes(payload)
    return (
        path,
        {
            "expected_artifact_sha256": _sha256(payload),
            "expected_catalog_dataset_hash": _CATALOG_DATASET_HASH,
            "expected_catalog_index_hash": _CATALOG_INDEX_HASH,
            "expected_sidecar_dataset_hash": _SIDECAR_DATASET_HASH,
            "expected_sidecar_manifest_hash": _SIDECAR_MANIFEST_HASH,
            "expected_session_dates_sha256": _SESSION_DATES_HASH,
            "expected_mask_identity": str(resolved_document["mask_identity"]),
            "expected_partition_identity": str(resolved_document["partition_identity"]),
        },
    )


def _audit_document() -> dict[str, object]:
    sessions = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(20))
    partitions = [
        _partition("development", sessions[0], sessions[11], 12),
        _partition("purge", sessions[12], sessions[12], 1),
        _partition("validation", sessions[13], sessions[16], 4),
        _partition("embargo", sessions[17], sessions[17], 1),
        _partition("untouched_tail", sessions[18], sessions[19], 2),
    ]
    masked_pairs = [
        _masked_pair("QQQ", sessions[2], sessions[3], ("event_buffer",)),
        _masked_pair("QQQ", sessions[11], sessions[12], ("chronological_boundary",)),
        _masked_pair("SPY", sessions[15], sessions[16], ("event_buffer",)),
        _masked_pair("SPY", sessions[16], sessions[17], ("chronological_boundary",)),
    ]
    return {
        "schema_version": 1,
        "kind": "kis_daily_event_boundary_audit",
        "created_at_utc": "2026-07-25T00:00:00Z",
        "status": "qualified",
        "unqualified_reasons": [],
        "catalog_dataset_hash": _CATALOG_DATASET_HASH,
        "catalog_index_hash": _CATALOG_INDEX_HASH,
        "sidecar_dataset_hash": _SIDECAR_DATASET_HASH,
        "sidecar_manifest_hash": _SIDECAR_MANIFEST_HASH,
        "session_dates_sha256": _SESSION_DATES_HASH,
        "residual_threshold_absolute_return": "0.20",
        "residual_policy": "inspect_unmasked_pairs_in_memory_only_no_return_values_persisted",
        "event_buffer_policy": "exclude_pairs_when_either_endpoint_is_event_or_adjacent_session",
        "partition_policy": "fixed_60_20_20_with_one_session_purge_and_embargo_v1",
        "partition_identity": "",
        "mask_identity": "",
        "scope": {
            "retrospective_price_return_label_integrity_only": True,
            "point_in_time_feature_eligible": False,
            "model_training_eligible": False,
            "paper_decision_eligible": False,
            "total_return_eligible": False,
            "baseline_eligible": False,
            "raw_price_data_consumed_in_memory_only": True,
            "raw_prices_or_returns_persisted": False,
        },
        "partitions": partitions,
        "audit_counts": {
            "QQQ": _counts(masked_pair_count=2),
            "SPY": _counts(masked_pair_count=2),
        },
        "masked_pairs": masked_pairs,
        "future_comparator_requirement": (
            "use_exact_mask_identity_and_partition_identity_without_recomputing_or_tuning"
        ),
    }


def _partition(name: str, start: date, end: date, count: int) -> dict[str, object]:
    return {
        "name": name,
        "start_session": start.isoformat(),
        "end_session": end.isoformat(),
        "session_count": count,
    }


def _masked_pair(
    symbol: str,
    start: date,
    end: date,
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "start_session": start.isoformat(),
        "end_session": end.isoformat(),
        "reasons": list(reasons),
    }


def _counts(*, masked_pair_count: int) -> dict[str, int]:
    return {
        "event_count": 1,
        "mapped_event_count": 1,
        "interior_event_count": 1,
        "buffered_session_count": 3,
        "event_boundary_pair_count": 1,
        "masked_pair_count": masked_pair_count,
        "unmasked_residual_pairs_examined": 10,
        "unmasked_residual_exceedance_count": 0,
    }


def _refresh_identities(document: dict[str, object]) -> None:
    partitions = document["partitions"]
    masked_pairs = document["masked_pairs"]
    assert isinstance(partitions, list)
    assert isinstance(masked_pairs, list)
    document["partition_identity"] = _sha256_json(partitions)
    document["mask_identity"] = _sha256_json(masked_pairs)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))
