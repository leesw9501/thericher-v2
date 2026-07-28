from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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

_OBSERVED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def test_bootstrap_collects_exactly_the_registry_selection_with_injected_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-broad"
    artifact_root = tmp_path / "artifacts"
    targets: list[KisPaperPrivateDailyCollectionTarget] = []
    created_clients: list[object] = []

    def fake_collect(
        _client: object,
        *,
        target: KisPaperPrivateDailyCollectionTarget,
        **_kwargs: object,
    ) -> KisPaperPrivateDailyCollectionResult:
        targets.append(target)
        return _observed_result(target)

    monkeypatch.setattr(
        broad_contract,
        "run_bounded_kis_paper_private_daily_collection",
        fake_collect,
    )
    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: False,
    )

    run = broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=lambda: created_clients.append(object()) or created_clients[-1],
        request_gate=_request_gate(tmp_path),
        token_start_gate=_token_gate(tmp_path),
        cache_root=cache_root,
        evidence_root=artifact_root,
        repo_root=repository_root,
        code_revision="git:test",
        bootstrap_only=True,
        max_chunks=8,
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    expected_scope = {target.symbol: frozenset({target.exchange}) for target in registry.targets}
    assert tuple(f"{target.symbol}/{target.exchange}" for target in targets) == (
        registry.bootstrap_target_keys
    )
    assert len(created_clients) == 1
    assert all(target.approved_symbol_exchanges == expected_scope for target in targets)
    assert run.status == "collected"
    assert run.bootstrap_only is True
    assert run.chunk_attempt_count == 8
    assert run.accepted_page_count == 8
    assert run.categorical_failure_count == 0
    assert run.remaining_target_count == len(registry.targets) - 8
    assert run.evidence_sha256 is not None
    assert not any(repository_root.iterdir())
    assert len(list(cache_root.glob("snapshot=*/manifest.json"))) == 8

    receipt_paths = list(artifact_root.glob("run=*/receipt.json"))
    assert len(receipt_paths) == 1
    receipt = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    assert receipt["scope"] == {
        "provider": "KIS Open API virtual paper",
        "endpoint": "dailyprice",
        "mode": "off",
        "registry_version": registry_contract.KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
        "registry_sha256": registry.registry_sha256,
        "current_listing_only": True,
        "non_pit": True,
        "non_ranking": True,
        "provider_price_data": False,
    }
    assert receipt["route_isolation"] == {
        "account_endpoints_used": False,
        "position_endpoints_used": False,
        "open_order_endpoints_used": False,
        "quote_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }
    assert receipt["artifact_policy"]["raw_market_data_in_receipt"] is False


def test_rejected_rows_are_not_persisted_and_next_target_still_advances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-broad"
    attempted: list[str] = []

    def fake_collect(
        _client: object,
        *,
        target: KisPaperPrivateDailyCollectionTarget,
        **_kwargs: object,
    ) -> KisPaperPrivateDailyCollectionResult:
        attempted.append(f"{target.symbol}/{target.exchange}")
        if len(attempted) == 1:
            return _rejected_result_with_rows(target)
        return _observed_result(target)

    monkeypatch.setattr(
        broad_contract,
        "run_bounded_kis_paper_private_daily_collection",
        fake_collect,
    )
    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: False,
    )

    run = broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=object,
        request_gate=_request_gate(tmp_path),
        token_start_gate=_token_gate(tmp_path),
        cache_root=cache_root,
        evidence_root=tmp_path / "artifacts",
        repo_root=repository_root,
        code_revision="git:test",
        bootstrap_only=True,
        max_chunks=2,
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    first_key, second_key = registry.bootstrap_target_keys[:2]
    assert attempted == [first_key, second_key]
    assert run.status == "collected"
    assert run.accepted_page_count == 2
    assert run.categorical_failure_count == 1
    assert len(list(cache_root.glob("snapshot=*/manifest.json"))) == 1

    index = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    target_by_key = {item["target_key"]: item for item in index["targets"]}
    assert target_by_key[first_key]["state"] == "deferred"
    assert target_by_key[first_key]["accepted_page_count"] == 0
    assert target_by_key[first_key]["chunks"] == []
    assert target_by_key[second_key]["state"] == "complete"


def test_continuation_prioritizes_shallow_targets_before_deepening_one_target(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "source")
    index = broad_contract._initial_index(registry)
    first = index["targets"][0]
    assert isinstance(first, dict)
    first["accepted_page_count"] = 2

    selected = broad_contract._select_ready_target(
        index=index,
        allowed_keys=registry.target_keys,
        attempted_keys=(),
        observed_at=_OBSERVED_AT,
    )

    assert selected is not None
    assert selected["target_key"] == registry.target_keys[1]


def test_repeated_source_rejection_becomes_target_local_source_limit(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "source")
    index = broad_contract._initial_index(registry)
    target = index["targets"][0]
    assert isinstance(target, dict)

    assert broad_contract._record_unretained_failure(
        target=target,
        reason="daily_response_invalid",
        observed_at=_OBSERVED_AT,
    ) == 1
    assert target["state"] == "deferred"
    assert target["consecutive_failure_count"] == 1

    assert broad_contract._record_unretained_failure(
        target=target,
        reason="daily_response_invalid",
        observed_at=_OBSERVED_AT,
    ) == 1
    assert target["state"] == "source_limited"
    assert target["consecutive_failure_reason"] == "daily_response_invalid"
    assert target["consecutive_failure_count"] == 2


def test_rate_retry_yields_without_client_construction_or_foreground_sleep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    request_gate = _request_gate(tmp_path)
    request_gate.record_rate_limit()
    sleeps: list[float] = []

    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: pytest.fail("rate retry must yield before storage inspection"),
    )
    run = broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=lambda: pytest.fail("rate retry must not construct a client"),
        request_gate=request_gate,
        token_start_gate=_token_gate(tmp_path),
        cache_root=tmp_path / "market-data" / "daily-nas-broad",
        evidence_root=tmp_path / "artifacts",
        repo_root=repository_root,
        code_revision="git:test",
        max_chunks=1,
        clock=lambda: _OBSERVED_AT,
        sleeper=sleeps.append,
        monotonic_clock=lambda: 0.0,
    )

    assert run.status == "deferred"
    assert run.chunk_attempt_count == 0
    assert run.next_due == _OBSERVED_AT + timedelta(seconds=60)
    assert sleeps == []


def test_storage_floor_blocks_before_client_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: True,
    )
    run = broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=lambda: pytest.fail("storage floor must not construct a client"),
        request_gate=_request_gate(tmp_path),
        token_start_gate=_token_gate(tmp_path),
        cache_root=tmp_path / "market-data" / "daily-nas-broad",
        evidence_root=tmp_path / "artifacts",
        repo_root=repository_root,
        code_revision="git:test",
        max_chunks=1,
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert run.status == "storage_floor_would_be_crossed"
    assert run.chunk_attempt_count == 0
    assert run.accepted_page_count == 0


def test_legacy_index_is_migrated_only_while_the_worker_owns_its_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-broad"
    cache_root.mkdir(parents=True)
    index = broad_contract._initial_index(registry)
    for target in index["targets"]:
        assert isinstance(target, dict)
        target.pop("consecutive_failure_reason")
        target.pop("consecutive_failure_count")
    (cache_root / "index.json").write_text(
        json.dumps(index, sort_keys=True),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: True,
    )
    broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=lambda: pytest.fail("storage-floor probe must not construct a client"),
        request_gate=_request_gate(tmp_path),
        token_start_gate=_token_gate(tmp_path),
        cache_root=cache_root,
        evidence_root=tmp_path / "artifacts",
        repo_root=repository_root,
        code_revision="git:test",
        max_chunks=1,
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    migrated = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    assert all(
        target["consecutive_failure_reason"] is None
        and target["consecutive_failure_count"] == 0
        for target in migrated["targets"]
    )


def test_registry_drift_is_rejected_before_client_or_collection_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-broad"
    artifact_root = tmp_path / "artifacts"

    monkeypatch.setattr(
        broad_contract,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        broad_contract,
        "run_bounded_kis_paper_private_daily_collection",
        lambda *_args, **_kwargs: _observed_result(_kwargs["target"]),
    )
    broad_contract.run_kis_paper_daily_broad_backfill(
        registry=registry,
        client_factory=object,
        request_gate=_request_gate(tmp_path),
        token_start_gate=_token_gate(tmp_path),
        cache_root=cache_root,
        evidence_root=artifact_root,
        repo_root=repository_root,
        code_revision="git:test",
        max_chunks=1,
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    (cache_root / registry_contract.KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME).write_text(
        "{}\n", encoding="utf-8"
    )

    def forbidden_client() -> object:
        raise AssertionError("registry drift must fail before client construction")

    with pytest.raises(
        registry_contract.KisPaperDailyBroadRegistryError,
        match="different content",
    ):
        broad_contract.run_kis_paper_daily_broad_backfill(
            registry=registry,
            client_factory=forbidden_client,
            request_gate=_request_gate(tmp_path),
            token_start_gate=_token_gate(tmp_path),
            cache_root=cache_root,
            evidence_root=artifact_root,
            repo_root=repository_root,
            code_revision="git:test",
            max_chunks=1,
            clock=lambda: _OBSERVED_AT,
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )


def test_rejects_a_cache_inside_git_before_client_construction(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "source")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(broad_contract.KisPaperDailyBroadBackfillError, match="outside Git"):
        broad_contract.run_kis_paper_daily_broad_backfill(
            registry=registry,
            client_factory=lambda: pytest.fail("cache validation must precede client construction"),
            request_gate=_request_gate(tmp_path),
            token_start_gate=_token_gate(tmp_path),
            cache_root=repository_root / "cache",
            evidence_root=tmp_path / "artifacts",
            repo_root=repository_root,
            code_revision="git:test",
            max_chunks=1,
            clock=lambda: _OBSERVED_AT,
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )


def test_worker_has_no_credential_or_account_route_implementation() -> None:
    source = inspect.getsource(broad_contract)

    assert ".env" not in source
    assert "KIS_PAPER_ACCOUNT_" not in source
    assert "KIS_LIVE_" not in source
    assert "order-cash" not in source
    assert "inquire-balance" not in source


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


def _rejected_result_with_rows(
    target: KisPaperPrivateDailyCollectionTarget,
) -> KisPaperPrivateDailyCollectionResult:
    result = _observed_result(target)
    return KisPaperPrivateDailyCollectionResult(
        **{
            **result.__dict__,
            "status": "rejected",
            "reason": "daily_response_rejected",
        }
    )


def _request_gate(tmp_path: Path) -> KisPaperMarketDataRateGate:
    return KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        clock=lambda: _OBSERVED_AT,
        sleeper=lambda _seconds: None,
    )


def _token_gate(tmp_path: Path) -> KisPaperMarketDataTokenStartGate:
    return KisPaperMarketDataTokenStartGate(
        control_root=tmp_path / "control",
        clock=lambda: _OBSERVED_AT,
    )


def _registry(root: Path) -> registry_contract.KisPaperDailyBroadRegistry:
    root.mkdir(parents=True)
    listing_path = root / registry_contract.NASDAQ_LISTING_FILE_NAME
    rows = [_listing_row(symbol) for symbol in _SYMBOLS]
    header = list(registry_contract._REQUIRED_LISTING_COLUMNS)
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


def _listing_row(symbol: str) -> dict[str, str]:
    return {
        "Symbol": symbol,
        "Security Name": f"Example {symbol} Common Stock",
        "Market Category": "Q",
        "Test Issue": "N",
        "Financial Status": "N",
        "Round Lot Size": "100",
        "ETF": "N",
        "NextShares": "N",
    }


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


_SYMBOLS = (
    "AAPL",
    "ADBE",
    "AMZN",
    "GOOGL",
    "INTC",
    "META",
    "MSFT",
    "NFLX",
    "NVDA",
    "TSLA",
)
