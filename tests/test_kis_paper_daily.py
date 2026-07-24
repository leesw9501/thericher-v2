from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data import kis_paper_daily as kis_daily_catalog
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    load_kis_paper_private_daily_catalog,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
    inspect_kis_paper_private_daily_backfill_snapshot,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectorPage,
    write_kis_paper_private_daily_cache,
)

_OBSERVED_AT = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)
_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"), ("IWM", "AMS"))


def test_loads_hash_attested_common_panel_offline_without_credentials_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_root, repo_root, _index_path = _build_cache(tmp_path)

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline cache loader must not open a network connection")

    def no_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline cache loader must not read environment variables")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(os, "getenv", no_environment)

    catalog = load_kis_paper_private_daily_catalog(
        cache_root,
        repo_root=repo_root,
    )

    assert catalog.dataset_id == KIS_PAPER_PRIVATE_DAILY_CATALOG_ID
    assert len(catalog.common_sessions) == 3
    assert tuple(catalog.bars_by_symbol) == ("QQQ", "SPY", "IWM")
    assert {bars.dataset_hash for bars in catalog.bars_by_symbol.values()} == {
        catalog.dataset_hash
    }
    assert all(
        bar.timeframe is Timeframe.D1
        for bars in catalog.bars_by_symbol.values()
        for bar in bars.bars
    )
    assert catalog.raw_price_limitations == (
        "MODP=0_unadjusted",
        "corporate_action_semantics_not_qualified",
    )


def test_session_ceiling_attests_full_rows_without_materializing_later_bars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_root, repo_root, _index_path = _build_cache(tmp_path)
    full_catalog = load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)
    cutoff = datetime(2026, 1, 2, tzinfo=UTC).date()
    constructed_sessions = []
    original_bar = kis_daily_catalog.Bar

    def bounded_bar(**kwargs: object):
        start_ts = kwargs["start_ts"]
        assert isinstance(start_ts, datetime)
        assert start_ts.date() <= cutoff
        constructed_sessions.append(start_ts.date())
        return original_bar(**kwargs)

    monkeypatch.setattr(kis_daily_catalog, "Bar", bounded_bar)
    catalog = load_kis_paper_private_daily_catalog(
        cache_root,
        repo_root=repo_root,
        expected_full_dataset_hash=full_catalog.dataset_hash,
        end_session=cutoff,
    )

    assert catalog.common_sessions == (
        datetime(2026, 1, 2, tzinfo=UTC).date(),
    )
    assert constructed_sessions
    assert all(session <= cutoff for session in constructed_sessions)


def test_full_dataset_hash_rejects_before_constructing_prefix_bars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_root, repo_root, _index_path = _build_cache(tmp_path)
    cutoff = datetime(2026, 1, 2, tzinfo=UTC).date()
    original_bar = kis_daily_catalog.Bar
    constructed = False

    def no_bar(**kwargs: object):
        nonlocal constructed
        constructed = True
        return original_bar(**kwargs)

    monkeypatch.setattr(kis_daily_catalog, "Bar", no_bar)

    with pytest.raises(ValueError, match="full dataset hash mismatch"):
        load_kis_paper_private_daily_catalog(
            cache_root,
            repo_root=repo_root,
            expected_full_dataset_hash="sha256:" + "0" * 64,
            end_session=cutoff,
        )

    assert constructed is False


def test_dataset_identity_is_stable_when_index_retry_metadata_changes(tmp_path: Path) -> None:
    cache_root, repo_root, index_path = _build_cache(tmp_path)
    first = load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["generation"] = 99
    index["network_retry_not_before_utc"] = "2026-07-21T20:00:00Z"
    index["last_shared_reason"] = "inter_chunk_pace"
    index["targets"][0]["chunks"].append({"outcome": "deferred"})
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    second = load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)

    assert second.dataset_hash == first.dataset_hash
    assert second.index_hash != first.index_hash
    assert second.common_sessions == first.common_sessions


def test_ignores_a_historical_unretained_marker_before_cursor_validation(tmp_path: Path) -> None:
    cache_root, repo_root, index_path = _build_cache(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["targets"][0]["chunks"].append(
        {
            "outcome": "committed",
            "raw_market_data_retained": False,
            "historical_note": "one-shot observation only",
        }
    )
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    catalog = load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)

    assert catalog.common_sessions == (
        datetime(2026, 1, 2, tzinfo=UTC).date(),
        datetime(2026, 1, 5, tzinfo=UTC).date(),
        datetime(2026, 1, 6, tzinfo=UTC).date(),
    )


def test_catalog_parses_only_the_expected_legacy_windows_daily_cache_prefix() -> None:
    legacy = PureWindowsPath(
        r"D:\market_data\us_equities\kis_paper_private\daily\snapshot=unit\manifest.json"
    )

    assert kis_daily_catalog._legacy_windows_daily_cache_relative_parts(legacy) == (
        "snapshot=unit",
        "manifest.json",
    )
    with pytest.raises(ValueError, match="path is invalid"):
        kis_daily_catalog._legacy_windows_daily_cache_relative_parts(
            PureWindowsPath(r"D:\other\snapshot=unit\manifest.json")
        )


def test_canonicalizes_target_order_and_refuses_non_us_market(tmp_path: Path) -> None:
    cache_root, repo_root, _index_path = _build_cache(tmp_path)
    default_catalog = load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)
    reordered_catalog = load_kis_paper_private_daily_catalog(
        cache_root,
        repo_root=repo_root,
        target_keys=("IWM/AMS/MODP=0", "SPY/AMS/MODP=0", "QQQ/NAS/MODP=0"),
    )

    assert tuple(reordered_catalog.bars_by_symbol) == ("QQQ", "SPY", "IWM")
    assert reordered_catalog.dataset_hash == default_catalog.dataset_hash
    with pytest.raises(ValueError, match="must be US"):
        load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root, market="KR")


def test_rejects_raw_hash_drift_before_exposing_any_bars(tmp_path: Path) -> None:
    cache_root, repo_root, index_path = _build_cache(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    manifest_path = Path(index["targets"][0]["chunks"][0]["manifest_path"])
    (manifest_path.parent / "raw" / "ohlcv_daily.csv.gz").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="raw hash mismatch"):
        load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)


def test_rejects_committed_row_count_drift(tmp_path: Path) -> None:
    cache_root, repo_root, index_path = _build_cache(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["targets"][0]["chunks"][0]["row_count"] += 1
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="committed chunk drift"):
        load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)


def test_rejects_conflicting_cross_chunk_overlap(tmp_path: Path) -> None:
    cache_root, repo_root, _index_path = _build_cache(tmp_path, conflicting_qqq_overlap=True)

    with pytest.raises(ValueError, match="conflicting overlap"):
        load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)


def test_loads_verified_partial_chunk_and_rejects_a_broken_cursor_seam(tmp_path: Path) -> None:
    cache_root, repo_root, index_path = _build_cache(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["targets"][0]["chunks"].append(
        _write_chunk(
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
            rows=(("20251230", "100"), ("20260102", "101")),
            run_number=99,
            partial=True,
        )
    )
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    catalog = load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)

    assert len(catalog.common_sessions) == 3
    index["targets"][0]["chunks"][-1]["input_cursor_date"] = "20251231"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cursor seam"):
        load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)


def test_rejects_unpinned_or_escaped_cache_evidence(tmp_path: Path) -> None:
    cache_root, repo_root, index_path = _build_cache(tmp_path)
    actual_index_hash = "sha256:" + hashlib.sha256(index_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="index hash mismatch"):
        load_kis_paper_private_daily_catalog(
            cache_root,
            repo_root=repo_root,
            expected_index_hash="sha256:" + "0" * 64,
        )

    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["targets"][0]["chunks"][0]["manifest_path"] = str(tmp_path / "outside.json")
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="path is invalid"):
        load_kis_paper_private_daily_catalog(cache_root, repo_root=repo_root)
    assert actual_index_hash.startswith("sha256:")


def _build_cache(
    tmp_path: Path,
    *,
    conflicting_qqq_overlap: bool = False,
) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    cache_root.mkdir()
    layouts = {
        "QQQ": (
            (("20260102", "101"), ("20260105", "102")),
            (
                ("20260105", "199" if conflicting_qqq_overlap else "102"),
                ("20260106", "103"),
            ),
        ),
        "SPY": ((("20260102", "201"), ("20260105", "202"), ("20260106", "203")),),
        "IWM": ((("20260102", "301"), ("20260105", "302"), ("20260106", "303")),),
    }
    targets: list[dict[str, object]] = []
    run_number = 0
    for symbol, exchange in _TARGETS:
        chunks: list[dict[str, object]] = []
        for rows in layouts[symbol]:
            run_number += 1
            chunks.append(
                _write_chunk(
                    cache_root=cache_root,
                    repo_root=repo_root,
                    symbol=symbol,
                    exchange=exchange,
                    rows=rows,
                    run_number=run_number,
                )
            )
        targets.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "target_key": f"{symbol}/{exchange}/MODP=0",
                "chunks": chunks,
            }
        )
    index = {
        "kind": "kis_paper_private_daily_backfill_index",
        "backfill_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
        "generation": 5,
        "targets": targets,
        "venue_attempts": [],
    }
    backfill_root = cache_root / "backfill-v1"
    backfill_root.mkdir()
    index_path = backfill_root / "index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cache_root, repo_root, index_path


def _write_chunk(
    *,
    cache_root: Path,
    repo_root: Path,
    symbol: str,
    exchange: str,
    rows: tuple[tuple[str, str], ...],
    run_number: int,
    partial: bool = False,
) -> dict[str, object]:
    raw_rows = tuple(_raw_row(session, close=close) for session, close in rows)
    result = KisPaperPrivateDailyCollectionResult(
        observed_at=_OBSERVED_AT,
        requested_anchor_date=rows[-1][0],
        code_revision="git:test",
        call_counts=KisPaperMarketDataCallCounts(1, 0, 2 if partial else 1),
        pages=(
            KisPaperPrivateDailyCollectorPage(
                page_number=1,
                row_count=len(raw_rows),
                newest_date=rows[-1][0],
                oldest_date=rows[0][0],
                continuation_advertised=partial,
            ),
        ),
        rows=raw_rows,
        dedupe_count=0,
        conflicting_duplicate_rows=0,
        inter_page_delay_seconds=(),
        status="partial" if partial else "observed",
        reason="daily_response_invalid" if partial else None,
        symbol=symbol,
        exchange=exchange,
    )
    target_key = f"{symbol}/{exchange}/MODP=0"
    manifest_path, _manifest_hash = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=cache_root,
        run_id=f"20260721T180000Z-{run_number:06d}",
        repo_root=repo_root,
        backfill_context={
            "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
            "cursor_strategy": "oldest_session_date_with_exact_overlap",
            "input_cursor_date": rows[-1][0],
            "logical_cursor_persisted": True,
            "output_cursor_date": rows[0][0],
            "target_key": target_key,
        },
    )
    snapshot = inspect_kis_paper_private_daily_backfill_snapshot(
        manifest_path=manifest_path,
        cache_root=cache_root,
        repo_root=repo_root,
    )
    return {
        "outcome": "partial" if partial else "committed",
        "input_cursor_date": rows[-1][0],
        "output_cursor_date": rows[0][0],
        "manifest_path": snapshot["manifest_path"],
        "manifest_hash": snapshot["manifest_hash"],
        "raw_sha256": snapshot["raw_sha256"],
        "raw_market_data_retained": snapshot["raw_market_data_retained"],
        "row_count": snapshot["row_count"],
        "row_fingerprints": snapshot["row_fingerprints"],
        "reason": "partial_daily_response_invalid" if partial else None,
    }


def _raw_row(session: str, *, close: str) -> KisPaperDailyRawRow:
    return KisPaperDailyRawRow(
        xymd=session,
        open="100",
        high="400",
        low="99",
        clos=close,
        tvol="777",
    )
