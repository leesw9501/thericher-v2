from __future__ import annotations

import hashlib
import inspect
import json
import os
import socket
from pathlib import Path

import pytest

import thericher_v2.data.official_symbol_directory_nas_probe as contract


def test_builds_a_fixed_source_safe_nas_registry_without_writing_artifacts(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)
    before = _tree(tmp_path)

    registry = _registry(manifest_path, listing_path)
    repeated = _registry(manifest_path, listing_path)

    assert registry.version == contract.OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_VERSION
    assert registry.prospective_only is True
    assert registry.historical_point_in_time_eligible is False
    assert (
        tuple(target.symbol for target in registry.targets)
        == contract.NAS_COMMON_STOCK_PROBE_SYMBOLS
    )
    assert tuple(target.exchange for target in registry.targets) == ("NAS",) * 6
    assert registry.target_keys == tuple(
        f"{symbol}/NAS" for symbol in contract.NAS_COMMON_STOCK_PROBE_SYMBOLS
    )
    assert registry.registry_sha256 == _sha256(registry.registry_payload)
    assert repeated == registry
    assert registry.source_manifest_sha256 == _sha256(manifest_path.read_bytes())
    assert registry.source_file_sha256 == _sha256(listing_path.read_bytes())
    assert _tree(tmp_path) == before

    payload_text = registry.registry_payload.decode("ascii")
    payload = json.loads(payload_text)
    assert payload["targets"] == [
        {"exchange": "NAS", "symbol": symbol}
        for symbol in contract.NAS_COMMON_STOCK_PROBE_SYMBOLS
    ]
    assert "Example Holdings" not in payload_text
    assert "ETF Trust" not in payload_text
    assert str(listing_path) not in payload_text
    assert payload["prospective_only"] is True
    assert "not_historical_point_in_time_universe" in payload["limitations"]


def test_registry_selection_is_fixed_and_file_order_does_not_change_targets(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path / "first")
    reverse_manifest_path, reverse_listing_path = _write_snapshot(
        tmp_path / "second", reverse_rows=True
    )

    first = _registry(manifest_path, listing_path)
    second = _registry(reverse_manifest_path, reverse_listing_path)

    assert first.targets == second.targets
    assert first.target_keys == second.target_keys
    assert first.registry_sha256 != second.registry_sha256
    assert first.source_file_sha256 != second.source_file_sha256


def test_public_builder_rejects_a_current_listing_snapshot_that_is_not_the_pinned_source(
    tmp_path: Path,
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)

    with pytest.raises(
        contract.OfficialSymbolDirectoryNasProbeError,
        match="manifest hash mismatch",
    ):
        contract.build_official_symbol_directory_nas_probe_registry(
            manifest_path=manifest_path,
            nasdaq_listing_path=listing_path,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", "wrong_kind", "kind is invalid"),
        ("immutable_snapshot", False, "must be immutable"),
        ("prospective_only", False, "must be prospective-only"),
    ],
)
def test_rejects_manifest_identity_drift(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match=message):
        _registry(manifest_path, listing_path)


def test_rejects_conflicting_scope_and_missing_source_hash(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scope"] = {"prospective_only": False}
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="prospective-only"):
        _build(manifest_path, listing_path, manifest)

    manifest.pop("scope")
    manifest["files"][0].pop("sha256")
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="sha256 is invalid"):
        _build(manifest_path, listing_path, manifest)


def test_rejects_source_not_declared_byte_unaltered(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["bytes_unaltered"] = False

    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="must be unaltered"):
        _build(manifest_path, listing_path, manifest)


def test_rejects_raw_hash_and_size_drift_before_selection(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)
    listing_path.write_bytes(listing_path.read_bytes() + b"# tampered\n")

    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="hash mismatch"):
        _registry(manifest_path, listing_path)

    manifest_path, listing_path = _write_snapshot(tmp_path / "size")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["size_bytes"] += 1
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="size mismatch"):
        _build(manifest_path, listing_path, manifest)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("Security Name", "Example Holdings - Preferred Stock"),
        ("Test Issue", "Y"),
        ("Financial Status", "D"),
        ("ETF", "Y"),
        ("NextShares", "Y"),
        ("Market Category", "Z"),
    ],
)
def test_rejects_non_common_or_excluded_fixed_targets(
    tmp_path: Path, column: str, value: str
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path, replacements={"AAPL": {column: value}})

    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="not an eligible"):
        _registry(manifest_path, listing_path)


def test_rejects_missing_duplicate_or_malformed_fixed_listing_rows(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path / "missing", omit_symbols={"NVDA"})
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="missing a fixed"):
        _registry(manifest_path, listing_path)

    manifest_path, listing_path = _write_snapshot(tmp_path / "duplicate", duplicate_symbol="AAPL")
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="duplicate symbols"):
        _registry(manifest_path, listing_path)

    manifest_path, listing_path = _write_snapshot(tmp_path / "bad-row")
    listing_path.write_bytes(listing_path.read_bytes().replace(b"MSFT|", b"MSFT", 1))
    _refresh_source_hash(manifest_path, listing_path)
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="row is incomplete"):
        _registry(manifest_path, listing_path)


def test_offline_contract_never_uses_network_or_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline source contract must not use this capability")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    registry = _registry(manifest_path, listing_path)

    assert len(registry.targets) == contract.NAS_COMMON_STOCK_PROBE_TARGET_COUNT
    source = inspect.getsource(contract)
    for forbidden_name in ("urllib", "requests", "KIS_", "os.environ", "dotenv"):
        assert forbidden_name not in source


def test_rejects_non_nasdaq_filename_and_ambiguous_source_entry(tmp_path: Path) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)
    wrong_name = listing_path.with_name("otherlisted.txt")
    wrong_name.write_bytes(listing_path.read_bytes())
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="filename is invalid"):
        _registry(manifest_path, wrong_name)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = dict(manifest["files"][0])
    duplicate["sha256"] = "sha256:" + "0" * 64
    manifest["files"].append(duplicate)
    with pytest.raises(contract.OfficialSymbolDirectoryNasProbeError, match="entry is ambiguous"):
        _build(manifest_path, listing_path, manifest)


def _build(manifest_path: Path, listing_path: Path, manifest: dict[str, object]) -> None:
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _registry(manifest_path, listing_path)


def _registry(
    manifest_path: Path,
    listing_path: Path,
) -> contract.OfficialSymbolDirectoryNasProbeRegistry:
    return contract._build_official_symbol_directory_nas_probe_registry(
        manifest_path=manifest_path,
        nasdaq_listing_path=listing_path,
        expected_manifest_sha256=_sha256(manifest_path.read_bytes()),
    )


def _write_snapshot(
    root: Path,
    *,
    reverse_rows: bool = False,
    replacements: dict[str, dict[str, str]] | None = None,
    omit_symbols: set[str] | None = None,
    duplicate_symbol: str | None = None,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    rows = _listing_rows(replacements=replacements, omit_symbols=omit_symbols)
    if duplicate_symbol is not None:
        rows.append(next(row.copy() for row in rows if row["Symbol"] == duplicate_symbol))
    if reverse_rows:
        rows.reverse()
    listing_path = root / contract.NASDAQ_LISTING_FILE_NAME
    listing_path.write_text(_listing_text(rows), encoding="utf-8", newline="")
    manifest_path = root / "manifest.json"
    manifest = {
        "kind": contract.OFFICIAL_SYMBOL_DIRECTORY_SNAPSHOT_KIND,
        "immutable_snapshot": True,
        "prospective_only": True,
        "scope": {"prospective_only": True},
        "files": [
            {
                "name": contract.NASDAQ_LISTING_FILE_NAME,
                "sha256": _sha256(listing_path.read_bytes()),
                "size_bytes": listing_path.stat().st_size,
                "bytes_unaltered": True,
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path, listing_path


def _listing_rows(
    *,
    replacements: dict[str, dict[str, str]] | None,
    omit_symbols: set[str] | None,
) -> list[dict[str, str]]:
    rows = [
        _row("AAPL", "Example Holdings - Common Stock"),
        _row("AMZN", "Example Retail - Common Stock"),
        _row("GOOGL", "Example Search - Class A Common Stock"),
        _row("META", "Example Social - Class A Common Stock"),
        _row("MSFT", "Example Software - Common Stock"),
        _row("NVDA", "Example Chips - Common Stock"),
        _row("QQQ", "Example ETF Trust - Unit", etf="Y"),
        _row("ZTEST", "Example Test - Common Stock", test_issue="Y"),
    ]
    updated: list[dict[str, str]] = []
    for row in rows:
        if omit_symbols is not None and row["Symbol"] in omit_symbols:
            continue
        replacement = (replacements or {}).get(row["Symbol"], {})
        updated.append({**row, **replacement})
    return updated


def _row(
    symbol: str,
    security_name: str,
    *,
    market_category: str = "Q",
    test_issue: str = "N",
    financial_status: str = "N",
    etf: str = "N",
    nextshares: str = "N",
) -> dict[str, str]:
    return {
        "Symbol": symbol,
        "Security Name": security_name,
        "Market Category": market_category,
        "Test Issue": test_issue,
        "Financial Status": financial_status,
        "Round Lot Size": "100",
        "ETF": etf,
        "NextShares": nextshares,
    }


def _listing_text(rows: list[dict[str, str]]) -> str:
    header = list(contract._REQUIRED_LISTING_COLUMNS)
    values = ["|".join(header)]
    values.extend("|".join(row[column] for column in header) for row in rows)
    values.append("File Creation Time: 20260727")
    return "\r\n".join(values) + "\r\n"


def _refresh_source_hash(manifest_path: Path, listing_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    document = manifest["files"][0]
    document["sha256"] = _sha256(listing_path.read_bytes())
    document["size_bytes"] = listing_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def _tree(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*")}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
