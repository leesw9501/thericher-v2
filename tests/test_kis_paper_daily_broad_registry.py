from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import socket
from pathlib import Path

import pytest

import thericher_v2.data.kis_paper_daily_broad_registry as registry_contract


def test_builds_source_safe_current_listing_registry_and_deterministic_bootstrap(
    tmp_path: Path,
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)

    registry = _build(manifest_path, listing_path)
    repeated = _build(manifest_path, listing_path)

    assert registry.version == registry_contract.KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION
    assert registry.scope.current_listing_only is True
    assert registry.scope.non_pit is True
    assert registry.scope.non_ranking is True
    assert registry.scope.provider_price_data is False
    assert len(registry.targets) == 10
    assert registry.target_keys == tuple(sorted(registry.target_keys))
    assert len(registry.bootstrap_targets) == registry_contract.BOOTSTRAP_TARGET_COUNT
    assert registry.bootstrap_target_keys == repeated.bootstrap_target_keys
    assert set(registry.bootstrap_target_keys).issubset(set(registry.target_keys))
    assert registry.registry_sha256 == _sha256(registry.registry_payload)
    assert repeated == registry

    payload_text = registry.registry_payload.decode("ascii")
    payload = json.loads(payload_text)
    assert payload["scope"] == {
        "current_listing_only": True,
        "non_pit": True,
        "non_ranking": True,
        "provider_price_data": False,
    }
    assert payload["targets"] == [
        {"exchange": "NAS", "symbol": symbol}
        for symbol in sorted(_eligible_symbols())
    ]
    assert all(set(target) == {"exchange", "symbol"} for target in payload["targets"])
    assert "Example Holdings" not in payload_text
    assert "Market Category" not in payload_text
    assert "current_listing_only" in payload_text


def test_canonical_targets_and_bootstrap_ignore_listing_row_order(tmp_path: Path) -> None:
    first_manifest, first_listing = _write_snapshot(tmp_path / "first")
    second_manifest, second_listing = _write_snapshot(tmp_path / "second", reverse_rows=True)

    first = _build(first_manifest, first_listing)
    second = _build(second_manifest, second_listing)

    assert first.target_keys == second.target_keys
    assert first.registry_identity_sha256 == second.registry_identity_sha256
    assert first.bootstrap_target_keys == second.bootstrap_target_keys
    assert first.source_file_sha256 != second.source_file_sha256
    assert first.registry_sha256 != second.registry_sha256


def test_public_builder_rejects_unpinned_source_identity_and_source_bytes_drift(
    tmp_path: Path,
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)

    with pytest.raises(
        registry_contract.KisPaperDailyBroadRegistryError,
        match="manifest hash mismatch",
    ):
        registry_contract.build_kis_paper_daily_broad_registry(
            manifest_path=manifest_path,
            nasdaq_listing_path=listing_path,
        )

    expected_manifest_sha256 = _sha256(manifest_path.read_bytes())
    listing_path.write_bytes(listing_path.read_bytes() + b"# source drift\n")
    with pytest.raises(
        registry_contract.KisPaperDailyBroadRegistryError,
        match="source file hash mismatch",
    ):
        registry_contract._build_kis_paper_daily_broad_registry(
            manifest_path=manifest_path,
            nasdaq_listing_path=listing_path,
            expected_manifest_sha256=expected_manifest_sha256,
        )


def test_rejects_manifest_contract_drift_and_symlink_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path / "manifest-drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["immutable_snapshot"] = False
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(
        registry_contract.KisPaperDailyBroadRegistryError,
        match="must be immutable",
    ):
        registry_contract._build_kis_paper_daily_broad_registry(
            manifest_path=manifest_path,
            nasdaq_listing_path=listing_path,
            expected_manifest_sha256=_sha256(manifest_path.read_bytes()),
        )

    manifest_path, listing_path = _write_snapshot(tmp_path / "symlink")
    original_is_symlink = Path.is_symlink

    def marked_symlink(path: Path) -> bool:
        return path == manifest_path.absolute() or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", marked_symlink)
    with pytest.raises(registry_contract.KisPaperDailyBroadRegistryError, match="symlink"):
        _build(manifest_path, listing_path)


def test_writer_and_reloader_stay_external_and_reject_repository_or_symlink_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path / "source")
    registry = _build(manifest_path, listing_path)
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external_root = tmp_path / "external"

    output_path = registry_contract.write_kis_paper_daily_broad_registry(
        registry=registry,
        output_root=external_root,
        repo_root=repository_root,
    )
    assert output_path == external_root / registry_contract.KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME
    assert registry_contract.load_kis_paper_daily_broad_registry(
        output_root=external_root,
        repo_root=repository_root,
    ) == registry

    before = _tree(repository_root)
    with pytest.raises(
        registry_contract.KisPaperDailyBroadRegistryError,
        match="outside the repository",
    ):
        registry_contract.write_kis_paper_daily_broad_registry(
            registry=registry,
            output_root=repository_root,
            repo_root=repository_root,
        )
    assert _tree(repository_root) == before

    linked_root = tmp_path / "external-link"
    original_is_symlink = Path.is_symlink

    def marked_symlink(path: Path) -> bool:
        return path == linked_root.absolute() or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", marked_symlink)
    with pytest.raises(registry_contract.KisPaperDailyBroadRegistryError, match="symlink"):
        registry_contract.write_kis_paper_daily_broad_registry(
            registry=registry,
            output_root=linked_root,
            repo_root=repository_root,
        )


def test_writer_accepts_only_the_explicit_market_data_mount_under_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path / "source")
    registry = _build(manifest_path, listing_path)
    repository_root = tmp_path / "repository"
    mounted_market_data = repository_root / "market_data"
    mounted_market_data.mkdir(parents=True)
    original_is_mount = Path.is_mount

    def marked_mount(path: Path) -> bool:
        return path == mounted_market_data.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", marked_mount)

    output_path = registry_contract.write_kis_paper_daily_broad_registry(
        registry=registry,
        output_root=mounted_market_data / "broad",
        repo_root=repository_root,
    )

    assert output_path.parent == mounted_market_data / "broad"


def test_offline_contract_does_not_import_or_access_network_environment_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, listing_path = _write_snapshot(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline registry must not use this capability")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    registry = _build(manifest_path, listing_path)

    assert len(registry.targets) == 10
    source = inspect.getsource(registry_contract)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint({"dotenv", "httpx", "os", "requests", "socket", "urllib"})
    assert ".env" not in source
    assert "KIS_PAPER_APP_KEY" not in source
    assert "KIS_PAPER_APP_SECRET" not in source


def _build(
    manifest_path: Path,
    listing_path: Path,
) -> registry_contract.KisPaperDailyBroadRegistry:
    return registry_contract._build_kis_paper_daily_broad_registry(
        manifest_path=manifest_path,
        nasdaq_listing_path=listing_path,
        expected_manifest_sha256=_sha256(manifest_path.read_bytes()),
    )


def _write_snapshot(root: Path, *, reverse_rows: bool = False) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    rows = _listing_rows()
    if reverse_rows:
        rows.reverse()
    listing_path = root / registry_contract.NASDAQ_LISTING_FILE_NAME
    listing_path.write_text(_listing_text(rows), encoding="utf-8", newline="")
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "bytes_unaltered": True,
                        "name": registry_contract.NASDAQ_LISTING_FILE_NAME,
                        "sha256": _sha256(listing_path.read_bytes()),
                        "size_bytes": listing_path.stat().st_size,
                    }
                ],
                "immutable_snapshot": True,
                "kind": registry_contract.OFFICIAL_SYMBOL_DIRECTORY_SNAPSHOT_KIND,
                "prospective_only": True,
                "scope": {"prospective_only": True},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest_path, listing_path


def _listing_rows() -> list[dict[str, str]]:
    return [
        _row("AAPL", "Example Holdings - Common Stock"),
        _row("AMZN", "Example Retail - Common Stock"),
        _row("GOOGL", "Example Search - Class A Common Stock"),
        _row("META", "Example Social - Class A Common Stock"),
        _row("MSFT", "Example Software - Common Stock"),
        _row("NVDA", "Example Chips - Common Stock"),
        _row("TSLA", "Example Motors - Common Stock"),
        _row("NFLX", "Example Streaming - Common Stock"),
        _row("ADBE", "Example Design - Common Stock"),
        _row("INTC", "Example Compute - Common Stock"),
        _row("QQQ", "Example ETF Trust - Unit", etf="Y"),
        _row("ZTEST", "Example Test - Common Stock", test_issue="Y"),
    ]


def _eligible_symbols() -> tuple[str, ...]:
    return ("AAPL", "ADBE", "AMZN", "GOOGL", "INTC", "META", "MSFT", "NFLX", "NVDA", "TSLA")


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
    header = list(registry_contract._REQUIRED_LISTING_COLUMNS)
    values = ["|".join(header)]
    values.extend("|".join(row[column] for column in header) for row in rows)
    values.append("File Creation Time: 20260728")
    return "\r\n".join(values) + "\r\n"


def _tree(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*")}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
