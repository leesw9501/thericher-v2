from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data.market_data_contract_inventory import (
    MARKET_DATA_CONTRACT_INVENTORY_ID,
    SourceFootprint,
    build_market_data_contract_inventory,
    read_market_data_contract_inventory,
)


def test_builds_exact_categorical_schema_without_raw_data_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_root, footprints = _fixture(tmp_path)
    raw_row = tmp_path / "market-data" / "raw.csv"
    raw_row.parent.mkdir()
    raw_row.write_text("timestamp,close\n", encoding="ascii")
    original_read_bytes = Path.read_bytes

    def guard_raw_reads(path: Path) -> bytes:
        if path == raw_row:
            raise AssertionError("raw market rows must not be read")
        return original_read_bytes(path)

    def forbidden_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access must not occur")

    original_read_text = Path.read_text

    def guard_credential_reads(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == ".env":
            raise AssertionError("credentials must not be read")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guard_raw_reads)
    monkeypatch.setattr(Path, "read_text", guard_credential_reads)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    receipt = build_market_data_contract_inventory(
        inventory_label="fixture-r1",
        retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
        artifact_root=artifact_root,
        footprints=footprints,
        repo_root=tmp_path / "repo",
    )

    payload = json.loads(receipt.receipt_path.read_text(encoding="ascii"))
    assert set(payload) == {
        "schema_version",
        "receipt_id",
        "inventory_label",
        "retrieved_at_utc",
        "entries",
        "categorical_counts",
        "safety",
        "limitations",
    }
    assert payload["receipt_id"] == MARKET_DATA_CONTRACT_INVENTORY_ID
    assert [entry["source_class"] for entry in payload["entries"]] == [
        "kis_m1",
        "kis_d1",
        "firstrate_free_m1",
        "tiingo_etf_d1",
        "tiingo_iex_m5",
        "norgate_trial",
    ]
    assert payload["categorical_counts"] == {
        "input_unavailable": 2,
        "non_promoting_runtime_only": 1,
        "retrospective_control_only": 1,
        "source_local_mechanics_only": 2,
    }
    assert payload["safety"]["raw_market_data_read"] is False
    assert receipt.receipt_path.is_relative_to(artifact_root)


def test_missing_allowed_pointer_is_scoped_unavailable(tmp_path: Path) -> None:
    artifact_root, footprints = _fixture(tmp_path)
    (artifact_root / footprints[2].receipt_relative_path).unlink()
    receipt = build_market_data_contract_inventory(
        inventory_label="missing-r1",
        retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
        artifact_root=artifact_root,
        footprints=footprints,
        repo_root=tmp_path / "repo",
    )
    entry = receipt.entries[2]
    assert entry.presence == "unavailable"
    assert entry.evidence_sha256 is None
    assert entry.consumer_status == "input_unavailable"
    assert receipt.entries[3].consumer_status == "retrospective_control_only"


def test_reader_reattaches_only_immutable_external_receipt(tmp_path: Path) -> None:
    artifact_root, footprints = _fixture(tmp_path)
    written = build_market_data_contract_inventory(
        inventory_label="reader-r1",
        retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
        artifact_root=artifact_root,
        footprints=footprints,
        repo_root=tmp_path / "repo",
    )
    loaded = read_market_data_contract_inventory(
        source=written.receipt_path,
        artifact_root=artifact_root,
        repo_root=tmp_path / "repo",
    )
    assert loaded.receipt_sha256 == written.receipt_sha256
    assert loaded.categorical_counts() == written.categorical_counts()
    with pytest.raises(ValueError, match="outside Git"):
        build_market_data_contract_inventory(
            inventory_label="repo-r1",
            retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
            artifact_root=tmp_path / "repo" / "artifacts",
            footprints=footprints,
            repo_root=tmp_path / "repo",
        )


def test_rejects_tampered_or_nonfixed_schema(tmp_path: Path) -> None:
    artifact_root, footprints = _fixture(tmp_path)
    written = build_market_data_contract_inventory(
        inventory_label="tampered-r1",
        retrieved_at_utc=datetime(2026, 8, 19, tzinfo=UTC),
        artifact_root=artifact_root,
        footprints=footprints,
        repo_root=tmp_path / "repo",
    )
    payload = json.loads(written.receipt_path.read_text(encoding="ascii"))
    payload["entries"][0]["raw_rows"] = "forbidden"
    written.receipt_path.write_text(json.dumps(payload), encoding="ascii")
    with pytest.raises(ValueError, match="invalid"):
        read_market_data_contract_inventory(
            source=written.receipt_path,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )


def _fixture(tmp_path: Path) -> tuple[Path, tuple[SourceFootprint, ...]]:
    artifact_root = tmp_path / "artifacts"
    source_classes = (
        ("kis_m1", "input_unavailable"),
        ("kis_d1", "input_unavailable"),
        ("firstrate_free_m1", "source_local_mechanics_only"),
        ("tiingo_etf_d1", "retrospective_control_only"),
        ("tiingo_iex_m5", "non_promoting_runtime_only"),
        ("norgate_trial", "source_local_mechanics_only"),
    )
    footprints: list[SourceFootprint] = []
    for index, (source_class, status) in enumerate(source_classes):
        metadata_root = tmp_path / "metadata" / source_class
        metadata_root.mkdir(parents=True)
        relative_receipt = Path("evidence") / f"{index}.json"
        receipt = artifact_root / relative_receipt
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text('{"source_safe":true}\n', encoding="ascii")
        footprints.append(SourceFootprint(source_class, metadata_root, relative_receipt, status))
    return artifact_root, tuple(footprints)
