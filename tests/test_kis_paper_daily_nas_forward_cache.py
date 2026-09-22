from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_nas_forward_cache as forward_cache
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KisPaperDailyNasForwardCacheError,
    KisPaperDailyNasForwardRow,
    build_kis_paper_daily_nas_historical_forward_projection,
    commit_kis_paper_daily_nas_forward_observation,
    get_kis_paper_daily_nas_forward_failure_details,
    load_verified_kis_paper_daily_nas_forward_cache,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader


def test_commits_and_reattests_six_symbol_forward_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
        observed_at=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert run.status == "ready"
    assert run.changed_target_count == 6
    assert run.cache.common_sessions == _sessions(27, 28, 29)
    assert run.cache.targets_by_key["AAPL/NAS"].row_count == 3
    assert run.prospective_input_status == "ready"
    reloaded = load_verified_kis_paper_daily_nas_forward_cache(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert reloaded.cache_hash == run.cache.cache_hash
    assert reloaded.common_sessions == _sessions(27, 28, 29)
    _assert_source_safe(run.safe_payload())


def test_preboundary_rows_are_not_retained_and_initial_index_is_recoverable(tmp_path: Path) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    first = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all((date(2026, 7, 24),)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
        observed_at=datetime(2026, 7, 28, tzinfo=UTC),
    )
    index = cache_root / "index.json"

    assert first.status == "input_unavailable"
    assert index.is_file()
    assert all(not rows for rows in first.cache.rows_by_symbol.values())
    second = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all((date(2026, 7, 27),)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
        observed_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    assert second.status == "ready"
    assert second.cache.common_sessions == (date(2026, 7, 27),)


def test_conflicting_duplicate_does_not_publish_or_replace_prior_snapshot(tmp_path: Path) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    first = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all((date(2026, 7, 27),)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    index_bytes = (cache_root / "index.json").read_bytes()
    conflicting = _rows_for_all((date(2026, 7, 27),))
    conflicting["AAPL"] = (_row("AAPL", date(2026, 7, 27), close=Decimal("999")),)

    snapshots = {path: path.read_bytes() for path in cache_root.rglob("*.csv.gz")}
    with pytest.raises(KisPaperDailyNasForwardCacheError, match="duplicate conflict") as caught:
        commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol=conflicting,
            failure_reasons_by_symbol={},
            cache_root=cache_root,
            repo_root=repo_root,
        )

    assert (cache_root / "index.json").read_bytes() == index_bytes
    assert {path: path.read_bytes() for path in cache_root.rglob("*.csv.gz")} == snapshots
    assert get_kis_paper_daily_nas_forward_failure_details(caught.value) == {
        "failure_stage": "overlap_reconciliation",
        "failure_category": "duplicate_conflict",
        "failure_symbol": "AAPL",
    }
    assert (
        load_verified_kis_paper_daily_nas_forward_cache(
            cache_root=cache_root,
            repo_root=repo_root,
        ).cache_hash
        == first.cache.cache_hash
    )


@pytest.mark.parametrize("fault", ["index", "snapshot", "boundary"])
def test_base_load_failure_is_distinct_from_incoming_overlap(tmp_path: Path, fault: str) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rows = _rows_for_all(_sessions(27, 28))
    commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    index_path = cache_root / "index.json"
    if fault == "index":
        index_path.write_text("{}", encoding="utf-8")
    elif fault == "snapshot":
        target = json.loads(index_path.read_bytes())["targets"][0]
        (cache_root / target["snapshot_path"]).write_bytes(b"synthetic-invalid-snapshot")
    before = {path: path.read_bytes() for path in cache_root.rglob("*") if path.is_file()}

    expected_type = ValueError if fault == "index" else KisPaperDailyNasForwardCacheError
    with pytest.raises(expected_type) as caught:
        commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol=rows,
            failure_reasons_by_symbol={},
            cache_root=cache_root,
            repo_root=repo_root,
            frozen_boundary=date(2026, 7, 23) if fault == "boundary" else date(2026, 7, 24),
        )

    details = get_kis_paper_daily_nas_forward_failure_details(caught.value)
    assert details["failure_stage"] == "verified_base_load"
    assert details["failure_category"] == ("value_error" if fault == "index" else "cache_contract")
    assert details.get("failure_symbol") == ("AAPL" if fault == "snapshot" else None)
    assert {path: path.read_bytes() for path in cache_root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    ("surface", "stage", "symbol"),
    [
        ("_write_snapshot", "cache_publish", "AAPL"),
        ("_write_json_atomic", "cache_publish", None),
        ("load_verified_kis_paper_daily_nas_forward_cache", "published_cache_load", None),
    ],
)
def test_persistence_failure_keeps_original_exception_and_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    stage: str,
    symbol: str | None,
) -> None:
    error = OSError("synthetic-private-path-must-not-be-emitted")

    def fail(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(forward_cache, surface, fail)
    with pytest.raises(OSError) as caught:
        commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol=_rows_for_all(_sessions(27, 28)),
            failure_reasons_by_symbol={},
            cache_root=tmp_path / "external",
            repo_root=tmp_path / "repo",
        )

    assert caught.value is error
    details = get_kis_paper_daily_nas_forward_failure_details(error)
    assert details["failure_stage"] == stage
    assert details["failure_category"] == "io_error"
    assert details.get("failure_symbol") == symbol
    assert str(error) not in json.dumps(details)


def test_exact_retry_preserves_snapshots_and_records_each_accepted_page(tmp_path: Path) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rows = _rows_for_all((date(2026, 7, 27),))
    first = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    index_bytes = (cache_root / "index.json").read_bytes()
    index = json.loads(index_bytes)
    snapshot_paths = tuple(sorted((cache_root / "snapshots").rglob("*.csv.gz")))
    snapshot_bytes = {path.relative_to(cache_root): path.read_bytes() for path in snapshot_paths}
    assert len(snapshot_paths) == 6

    second = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert second.status == "unchanged"
    assert second.changed_target_count == 0
    assert second.accepted_page_count == 6
    assert second.cache.cache_hash != first.cache.cache_hash
    updated_index = json.loads((cache_root / "index.json").read_bytes())
    assert updated_index["generation"] == index["generation"] + 1
    assert all(target["accepted_page_count"] == 2 for target in updated_index["targets"])
    assert tuple(sorted((cache_root / "snapshots").rglob("*.csv.gz"))) == snapshot_paths
    assert {
        path.relative_to(cache_root): path.read_bytes()
        for path in (cache_root / "snapshots").rglob("*.csv.gz")
    } == snapshot_bytes


def test_partial_target_failure_keeps_prior_peer_snapshots_and_marks_only_that_target(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all((date(2026, 7, 27),)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    rows = _rows_for_all((date(2026, 7, 28),))
    rows.pop("MSFT")
    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol={"MSFT": "transport_failure"},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == "partial"
    assert run.cache.targets_by_key["MSFT/NAS"].status == "deferred"
    assert len(run.cache.rows_by_symbol["MSFT"]) == 1
    assert len(run.cache.rows_by_symbol["AAPL"]) == 2
    assert run.cache.common_sessions == (date(2026, 7, 27),)


def test_all_transient_target_failures_remain_deferred_not_source_limited(tmp_path: Path) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol={},
        failure_reasons_by_symbol={
            symbol: "transport_failure" for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == "deferred"
    assert run.recovery == "resume"
    assert run.prospective_input_status == "input_unavailable"
    assert {
        target.status for target in run.cache.targets_by_key.values()
    } == {"deferred"}


def test_incomplete_valid_basket_is_not_ready_for_the_all_six_consumer(tmp_path: Path) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rows = _rows_for_all((date(2026, 7, 27),))
    rows["MSFT"] = ()

    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == "partial"
    assert not run.cache.common_sessions
    assert run.prospective_input_status == "input_unavailable"


def test_rejects_cache_root_inside_git_workspace(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(KisPaperDailyNasForwardCacheError, match="outside Git"):
        commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol=_rows_for_all((date(2026, 7, 27),)),
            failure_reasons_by_symbol={},
            cache_root=repo_root / "cache",
            repo_root=repo_root,
        )


def test_historical_forward_projection_is_read_only_and_requires_all_six_target_sessions(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    frozen_root = tmp_path / "external" / "frozen-panel"
    panel = _frozen_panel(frozen_root)
    frozen_index = panel.index_path.read_bytes()
    cache_root = tmp_path / "external" / "forward"
    cache = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    ).cache

    projection = build_kis_paper_daily_nas_historical_forward_projection(
        frozen_panel=panel,
        forward_cache=cache,
    )

    assert projection.status == "ready"
    assert projection.eligible_target_slot_count == 1
    assert projection.forward_common_sessions == _sessions(27, 28, 29)
    assert panel.index_path.read_bytes() == frozen_index
    _assert_source_safe(projection.safe_payload())

    incomplete = _rows_for_all(_sessions(27, 28, 29))
    incomplete["NVDA"] = incomplete["NVDA"][:-1]
    incomplete_cache = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=incomplete,
        failure_reasons_by_symbol={},
        cache_root=tmp_path / "external" / "incomplete-forward",
        repo_root=repo_root,
    ).cache
    unavailable = build_kis_paper_daily_nas_historical_forward_projection(
        frozen_panel=panel,
        forward_cache=incomplete_cache,
    )
    assert unavailable.status == "input_unavailable"
    assert unavailable.eligible_target_slot_count == 0


def test_retains_a_gapped_forward_cache_but_rejects_its_projection(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    frozen_root = tmp_path / "external" / "frozen-panel"
    panel = _frozen_panel(frozen_root)
    cache_root = tmp_path / "external" / "forward"

    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 29, 30)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == "ready"
    assert run.prospective_input_status == "input_unavailable"
    assert run.cache.common_sessions == _sessions(27, 29, 30)
    assert (cache_root / "index.json").is_file()
    with pytest.raises(ValueError, match="normal US session gap"):
        build_kis_paper_daily_nas_historical_forward_projection(
            frozen_panel=panel,
            forward_cache=run.cache,
        )


def test_retains_forward_rows_when_session_coverage_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "forward"
    monkeypatch.setattr(
        forward_cache,
        "has_complete_us_equity_session_coverage",
        lambda _sessions: (_ for _ in ()).throw(ValueError("calendar unavailable")),
    )

    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == "ready"
    assert run.prospective_input_status == "input_unavailable"
    assert (cache_root / "index.json").is_file()


def _rows_for_all(sessions: tuple[date, ...]) -> dict[str, tuple[KisPaperDailyNasForwardRow, ...]]:
    return {
        symbol: tuple(
            _row(symbol, session, close=Decimal(100 + offset + index))
            for index, session in enumerate(sessions)
        )
        for offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1)
    }


def _row(symbol: str, session: date, *, close: Decimal) -> KisPaperDailyNasForwardRow:
    return KisPaperDailyNasForwardRow(
        symbol=symbol,
        session_date=session,
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
    )


def _sessions(*days: int) -> tuple[date, ...]:
    return tuple(date(2026, 7, day) for day in days)


def _frozen_panel(root: Path) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    sessions = tuple(date(2026, 6, 20) + timedelta(days=offset) for offset in range(35))
    dataset_hash = "sha256:" + "a" * 64
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        bars = tuple(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(session, datetime.min.time(), tzinfo=UTC),
                open=Decimal(100 + offset + index),
                high=Decimal(101 + offset + index),
                low=Decimal(99 + offset + index),
                close=Decimal(100 + offset + index),
                volume=Decimal("1000"),
                complete=True,
            )
            for index, session in enumerate(sessions)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state="complete",
            last_reason=None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket="2026-Q2",
            coverage_end_bucket="2026-Q3",
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "b" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _assert_source_safe(value: object) -> None:
    forbidden = {"bars", "close", "entry", "exit", "high", "low", "open", "price", "volume"}
    if isinstance(value, dict):
        assert not (set(value) & forbidden)
        for nested in value.values():
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)


def test_safe_payload_is_json_serializable(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all((date(2026, 7, 27),)),
        failure_reasons_by_symbol={},
        cache_root=tmp_path / "external" / "forward",
        repo_root=repo_root,
    )
    assert json.loads(json.dumps(run.safe_payload()))["status"] == "ready"
