from __future__ import annotations

import hashlib
import inspect
import json
import os
import socket
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

import thericher_v2.data.kis_paper_daily_broad_panel as panel
import thericher_v2.data.kis_paper_daily_broad_registry as registry_contract
import thericher_v2.execution.kis_paper_daily_broad_backfill as broad_contract
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectionTarget,
    KisPaperPrivateDailyCollectorPage,
)

_OBSERVED_AT = datetime(2026, 7, 29, 0, 0, tzinfo=UTC)
_SYMBOLS = ("AAPL", "ADBE", "AMZN", "GOOGL", "INTC", "META", "MSFT", "NFLX")


def test_materializes_a_read_only_source_local_coverage_panel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root, repository_root = _write_broad_cache(tmp_path, monkeypatch)
    panel_root = tmp_path / "panel"
    artifact_root = tmp_path / "artifacts"
    index_before = (cache_root / "index.json").read_bytes()
    _deny_external_access(monkeypatch)

    result = panel.materialize_kis_paper_daily_broad_panel(
        cache_root=cache_root,
        panel_root=panel_root,
        artifact_root=artifact_root,
        repo_root=repository_root,
    )
    loaded = panel.load_materialized_kis_paper_daily_broad_panel(
        result.manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repository_root,
    )

    assert len(result.panel.target_keys) == len(_SYMBOLS)
    assert result.panel.covered_target_count == 2
    assert result.panel.zero_coverage_target_count == len(_SYMBOLS) - 2
    assert result.panel.quarantined_target_count == 0
    assert len(result.panel.bars_by_target) == 2
    assert loaded.dataset_hash == result.panel.dataset_hash
    assert (cache_root / "index.json").read_bytes() == index_before
    assert result.manifest_path.is_relative_to(panel_root)
    assert result.receipt_path.is_relative_to(artifact_root)
    assert not list(repository_root.rglob("*.json"))

    manifest = _read_json(result.manifest_path)
    receipt = _read_json(result.receipt_path)
    assert manifest["scope"] == {
        "adjustment_mode": "MODP=0_unadjusted",
        "corporate_action_qualified": False,
        "cross_source_blending_allowed": False,
        "current_listing_only": True,
        "endpoint": "dailyprice",
        "market": "US",
        "non_pit": True,
        "non_ranking": True,
        "provider": "KIS Open API virtual paper",
        "session_finality_attested": False,
        "timeframe": "1d",
    }
    assert receipt["artifact_policy"]["network_accessed"] is False
    assert receipt["artifact_policy"]["kis_accessed"] is False
    assert receipt["artifact_policy"]["broker_accessed"] is False
    for document in (manifest, receipt):
        _assert_no_raw_fields(document)


def test_retries_only_a_changed_index_snapshot_then_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root, repository_root = _write_broad_cache(tmp_path, monkeypatch)
    stable = (cache_root / "index.json").read_bytes()
    changed = _read_json_bytes(stable)
    changed["targets"][0]["categorical_failure_count"] += 1
    drifted = _json_bytes(changed)
    reads = iter((stable, drifted, stable, drifted, stable, drifted))
    monkeypatch.setattr(panel, "_read_index_bytes", lambda _path: next(reads))

    with pytest.raises(ValueError, match="changed during reattestation"):
        panel.build_kis_paper_daily_broad_panel(
            cache_root=cache_root,
            repo_root=repository_root,
        )


def test_rejects_raw_hash_drift_and_quarantines_a_conflicting_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root, repository_root = _write_broad_cache(tmp_path, monkeypatch)
    index = _read_json(cache_root / "index.json")
    first_target = next(target for target in index["targets"] if target["chunks"])
    raw_path = (
        cache_root
        / Path(str(first_target["chunks"][0]["manifest_path"])).parent
        / "raw"
        / "ohlcv_daily.csv.gz"
    )
    raw_path.write_bytes(raw_path.read_bytes() + b"drift")

    with pytest.raises(ValueError, match="raw hash mismatch"):
        panel.build_kis_paper_daily_broad_panel(
            cache_root=cache_root,
            repo_root=repository_root,
        )

    cache_root, repository_root = _write_broad_cache(tmp_path / "conflict", monkeypatch)
    index = _read_json(cache_root / "index.json")
    first_target = next(target for target in index["targets"] if target["chunks"])
    first_target["chunks"][0]["outcome"] = "conflict"
    first_target["chunks"][0]["reason"] = "cross_chunk_duplicate_conflict"
    first_target["state"] = "deferred"
    first_target["next_anchor_date"] = first_target["initial_anchor_date"]
    first_target["accepted_page_count"] = 0
    (cache_root / "index.json").write_bytes(_json_bytes(index))

    built = panel.build_kis_paper_daily_broad_panel(
        cache_root=cache_root,
        repo_root=repository_root,
    )

    target_key = str(first_target["target_key"])
    assert built.targets_by_key[target_key].quarantined is True
    assert target_key not in built.bars_by_target
    assert built.quarantined_target_count == 1


def test_materialized_snapshot_reattests_after_the_live_index_advances(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root, repository_root = _write_broad_cache(tmp_path, monkeypatch)
    panel_root = tmp_path / "panel"
    artifact_root = tmp_path / "artifacts"
    result = panel.materialize_kis_paper_daily_broad_panel(
        cache_root=cache_root,
        panel_root=panel_root,
        artifact_root=artifact_root,
        repo_root=repository_root,
    )
    index = _read_json(cache_root / "index.json")
    index["generation"] += 1
    index["targets"][-1]["categorical_failure_count"] += 1
    (cache_root / "index.json").write_bytes(_json_bytes(index))

    loaded = panel.load_materialized_kis_paper_daily_broad_panel(
        result.manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repository_root,
    )

    assert loaded.dataset_hash == result.panel.dataset_hash


def test_module_has_no_network_credential_or_broker_route() -> None:
    source = inspect.getsource(panel)

    assert "KisPaperMarketDataClient" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert ".env" not in source
    assert "worker.lock" not in source


def _write_broad_cache(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    registry = _registry(root / "source")
    repository_root = root / "repository"
    repository_root.mkdir(parents=True)
    cache_root = root / "market-data" / "daily-nas-broad"
    monkeypatch.setattr(
        broad_contract,
        "run_bounded_kis_paper_private_daily_collection",
        lambda _client, *, target, **_kwargs: _observed_result(target),
    )
    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: False,
    )
    broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=object,
        request_gate=KisPaperMarketDataRateGate(
            control_root=root / "control",
            clock=lambda: _OBSERVED_AT,
            sleeper=lambda _seconds: None,
        ),
        token_start_gate=KisPaperMarketDataTokenStartGate(
            control_root=root / "control",
            clock=lambda: _OBSERVED_AT,
        ),
        cache_root=cache_root,
        evidence_root=root / "artifacts",
        repo_root=repository_root,
        code_revision="git:test",
        bootstrap_only=True,
        max_chunks=2,
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    return cache_root, repository_root


def _observed_result(
    target: KisPaperPrivateDailyCollectionTarget,
) -> KisPaperPrivateDailyCollectionResult:
    row = KisPaperDailyRawRow(
        xymd="20260727",
        open="100",
        high="102",
        low="99",
        clos="101",
        tvol="1000",
    )
    return KisPaperPrivateDailyCollectionResult(
        observed_at=_OBSERVED_AT,
        requested_anchor_date=target.anchor_date,
        code_revision="git:test",
        call_counts=KisPaperMarketDataCallCounts(0, 0, 1),
        pages=(
            KisPaperPrivateDailyCollectorPage(
                page_number=1,
                row_count=1,
                newest_date=row.xymd,
                oldest_date=row.xymd,
                continuation_advertised=False,
            ),
        ),
        rows=(row,),
        dedupe_count=0,
        conflicting_duplicate_rows=0,
        inter_page_delay_seconds=(),
        status="observed",
        symbol=target.symbol,
        exchange=target.exchange,
        approved_symbol_exchanges=target.approved_symbol_exchanges,
    )


def _registry(root: Path) -> registry_contract.KisPaperDailyBroadRegistry:
    root.mkdir(parents=True)
    listing_path = root / registry_contract.NASDAQ_LISTING_FILE_NAME
    header = list(registry_contract._REQUIRED_LISTING_COLUMNS)
    rows = [
        {
            "Symbol": symbol,
            "Security Name": f"Example {symbol} Common Stock",
            "Market Category": "Q",
            "Test Issue": "N",
            "Financial Status": "N",
            "Round Lot Size": "100",
            "ETF": "N",
            "NextShares": "N",
        }
        for symbol in _SYMBOLS
    ]
    listing_path.write_text(
        "\r\n".join(
            ["|".join(header)]
            + ["|".join(row[column] for column in header) for row in rows]
            + ["File Creation Time: 20260728"]
        )
        + "\r\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": registry_contract.OFFICIAL_SYMBOL_DIRECTORY_SNAPSHOT_KIND,
                "immutable_snapshot": True,
                "prospective_only": True,
                "scope": {"prospective_only": True},
                "files": [
                    {
                        "name": registry_contract.NASDAQ_LISTING_FILE_NAME,
                        "bytes_unaltered": True,
                        "sha256": _sha256(listing_path.read_bytes()),
                        "size_bytes": listing_path.stat().st_size,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return registry_contract._build_kis_paper_daily_broad_registry(
        manifest_path=manifest_path,
        nasdaq_listing_path=listing_path,
        expected_manifest_sha256=_sha256(manifest_path.read_bytes()),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("broad panel must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _read_json(path: Path) -> dict[str, object]:
    return _read_json_bytes(path.read_bytes())


def _read_json_bytes(payload: bytes) -> dict[str, object]:
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise AssertionError("JSON fixture is invalid")
    return result


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _assert_no_raw_fields(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_fields(nested)
