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


@pytest.mark.parametrize(
    "conflict_symbols",
    [("AAPL",), ("META",), ("NVDA",), ("AAPL", "NVDA"), KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS],
)
def test_overlap_conflicts_preserve_failed_snapshots_and_commit_only_unaffected_targets(
    tmp_path: Path,
    conflict_symbols: tuple[str, ...],
) -> None:
    cache_root = tmp_path / "external" / "forward"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    first = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    index = json.loads((cache_root / "index.json").read_bytes())
    conflicting = _rows_for_all(_sessions(27, 28, 29, 30))
    for symbol in conflict_symbols:
        conflicting[symbol] = (
            _row(symbol, date(2026, 7, 27), close=Decimal("999")),
            *conflicting[symbol][1:],
        )
    snapshots = {path: path.read_bytes() for path in cache_root.rglob("*.csv.gz")}
    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=conflicting,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == ("deferred" if len(conflict_symbols) == 6 else "partial")
    assert run.recovery == "resume"
    assert run.accepted_page_count == run.changed_target_count == 6 - len(conflict_symbols)
    assert run.categorical_failure_count == len(conflict_symbols)
    assert run.prospective_input_status == "input_unavailable"
    assert run.cache.common_sessions == first.cache.common_sessions == _sessions(27, 28, 29)
    assert {path: path.read_bytes() for path in snapshots} == snapshots
    assert len(tuple(cache_root.rglob("*.csv.gz"))) == 12 - len(conflict_symbols)
    updated = json.loads((cache_root / "index.json").read_bytes())
    assert updated["generation"] == index["generation"] + 1
    for prior, target in zip(index["targets"], updated["targets"], strict=True):
        symbol = target["target_key"].split("/")[0]
        if symbol in conflict_symbols:
            assert target == {
                **prior,
                "status": "deferred",
                "categorical_failure_count": prior["categorical_failure_count"] + 1,
                "last_reason": "daily_duplicate_conflict",
            }
            assert run.cache.rows_by_symbol[symbol] == first.cache.rows_by_symbol[symbol]
        else:
            assert target["status"] == "ready"
            assert target["accepted_page_count"] == 2
            assert target["categorical_failure_count"] == 0
            assert run.cache.rows_by_symbol[symbol] == conflicting[symbol]
    assert run.safe_payload()["target_failures"] == [
        {
            "failure_stage": "overlap_reconciliation",
            "failure_category": "duplicate_conflict",
            "failure_symbol": symbol,
        }
        for symbol in conflict_symbols
    ]
    _assert_source_safe(run.safe_payload())
    assert (
        load_verified_kis_paper_daily_nas_forward_cache(
            cache_root=cache_root,
            repo_root=repo_root,
        ).cache_hash
        == run.cache.cache_hash
    )

    repeated = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=conflicting,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert repeated.status == run.status
    assert repeated.prospective_input_status == "input_unavailable"
    assert repeated.changed_target_count == 0
    assert repeated.categorical_failure_count == len(conflict_symbols)
    assert repeated.accepted_page_count == 6 - len(conflict_symbols)
    assert repeated.safe_payload()["target_failures"] == run.safe_payload()["target_failures"]
    assert {path: path.read_bytes() for path in snapshots} == snapshots
    assert len(tuple(cache_root.rglob("*.csv.gz"))) == 12 - len(conflict_symbols)
    for symbol in conflict_symbols:
        target = repeated.cache.targets_by_key[f"{symbol}/NAS"]
        assert target.accepted_page_count == 1
        assert target.categorical_failure_count == 2


def test_overlap_and_fetch_failures_share_counts_but_preserve_distinct_stages(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "external"
    repo_root = tmp_path / "repo"
    commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    rows = _rows_for_all(_sessions(27, 28, 29, 30))
    rows["AAPL"] = (_row("AAPL", date(2026, 7, 27), close=Decimal("999")),)
    rows.pop("MSFT")
    failures = {"MSFT": "daily_duplicate_conflict"}
    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol=MappingProxyType(failures),
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert failures == {"MSFT": "daily_duplicate_conflict"}
    assert run.status == "partial"
    assert run.accepted_page_count == run.changed_target_count == 4
    assert run.categorical_failure_count == 2
    assert run.prospective_input_status == "input_unavailable"
    assert run.cache.common_sessions == _sessions(27, 28, 29)
    assert run.safe_payload()["target_failures"] == [
        {
            "failure_stage": "overlap_reconciliation",
            "failure_category": "duplicate_conflict",
            "failure_symbol": "AAPL",
        },
        {
            "failure_stage": "target_fetch",
            "failure_category": "daily_duplicate_conflict",
            "failure_symbol": "MSFT",
        },
    ]


def test_fetch_failure_does_not_qualify_a_fresh_run_from_old_common_sessions(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "external"
    repo_root = tmp_path / "repo"
    first = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    rows = _rows_for_all(_sessions(27, 28, 29, 30))
    rows.pop("MSFT")
    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol={"MSFT": "transport_failure"},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert run.status == "partial"
    assert run.prospective_input_status == "input_unavailable"
    assert run.cache.common_sessions == first.cache.common_sessions
    assert run.cache.rows_by_symbol["MSFT"] == first.cache.rows_by_symbol["MSFT"]
    assert (
        run.cache.targets_by_key["MSFT/NAS"].rows_sha256
        == first.cache.targets_by_key["MSFT/NAS"].rows_sha256
    )


def test_compatible_later_batch_resolves_only_current_failure_and_retry_adds_no_rows(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "external"
    repo_root = tmp_path / "repo"
    commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    good_rows = _rows_for_all(_sessions(27, 28, 29, 30))
    conflicting = dict(good_rows)
    conflicting["AAPL"] = (
        _row("AAPL", date(2026, 7, 27), close=Decimal("999")),
        *good_rows["AAPL"][1:],
    )
    partial = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=conflicting,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    prior_snapshots = {path: path.read_bytes() for path in cache_root.rglob("*.csv.gz")}
    resolved = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=good_rows,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert resolved.status == "ready"
    assert resolved.recovery == "complete"
    assert resolved.changed_target_count == 1
    assert resolved.accepted_page_count == 6
    assert resolved.categorical_failure_count == 0
    assert resolved.prospective_input_status == "ready"
    assert "target_failures" not in resolved.safe_payload()
    assert resolved.cache.common_sessions == _sessions(27, 28, 29, 30)
    assert dict(resolved.cache.rows_by_symbol) == good_rows
    target = resolved.cache.targets_by_key["AAPL/NAS"]
    assert target.status == "ready"
    assert target.last_reason is None
    assert target.categorical_failure_count == 1
    assert target.accepted_page_count == 2
    assert {path: path.read_bytes() for path in prior_snapshots} == prior_snapshots
    assert partial.safe_payload()["target_failures"][0]["failure_stage"] == "overlap_reconciliation"
    assert partial.cache.targets_by_key["AAPL/NAS"].row_count == 3

    snapshots = {path: path.read_bytes() for path in cache_root.rglob("*.csv.gz")}
    repeated = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=good_rows,
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert repeated.status == "unchanged"
    assert repeated.changed_target_count == 0
    assert repeated.categorical_failure_count == 0
    assert repeated.cache.common_sessions == resolved.cache.common_sessions
    assert "target_failures" not in repeated.safe_payload()
    assert {path: path.read_bytes() for path in cache_root.rglob("*.csv.gz")} == snapshots


@pytest.mark.parametrize("failure", ["overlap", "fetch"])
def test_prospective_projection_rejects_deferred_target_but_historical_loader_stays_valid(
    tmp_path: Path,
    failure: str,
) -> None:
    cache_root = tmp_path / "external"
    repo_root = tmp_path / "repo"
    panel = _frozen_panel(tmp_path / "frozen")
    first = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    rows = _rows_for_all(_sessions(27, 28, 29, 30))
    failures = {}
    if failure == "overlap":
        rows["AAPL"] = (_row("AAPL", date(2026, 7, 27), close=Decimal("999")),)
    else:
        rows.pop("AAPL")
        failures["AAPL"] = "transport_failure"
    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol=failures,
        cache_root=cache_root,
        repo_root=repo_root,
    )
    before = {path: path.read_bytes() for path in cache_root.rglob("*") if path.is_file()}
    loaded = load_verified_kis_paper_daily_nas_forward_cache(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert loaded.cache_hash == run.cache.cache_hash
    assert loaded.rows_by_symbol["AAPL"] == first.cache.rows_by_symbol["AAPL"]
    assert loaded.common_sessions == first.cache.common_sessions == _sessions(27, 28, 29)
    with pytest.raises(ValueError, match="projection has deferred targets"):
        build_kis_paper_daily_nas_historical_forward_projection(
            frozen_panel=panel,
            forward_cache=loaded,
        )
    assert {path: path.read_bytes() for path in cache_root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    ("surface", "error", "stage", "category"),
    [
        (
            "_merge_rows", KisPaperDailyNasForwardCacheError("synthetic-private-detail"),
            "overlap_reconciliation", "cache_contract",
        ),
        ("_merge_rows", OSError("synthetic-private-detail"), "overlap_reconciliation", "io_error"),
        (
            "_merge_rows", ValueError("synthetic-private-detail"),
            "overlap_reconciliation", "value_error",
        ),
        (
            "_load_target_rows",
            KisPaperDailyNasForwardCacheError(
                "synthetic-private-detail", category="duplicate_conflict"
            ),
            "verified_base_load", "duplicate_conflict",
        ),
    ],
)
def test_unrelated_failure_after_overlap_still_aborts_without_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    error: Exception,
    stage: str,
    category: str,
) -> None:
    cache_root = tmp_path / "external"
    repo_root = tmp_path / "repo"
    commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_rows_for_all(_sessions(27, 28, 29)),
        failure_reasons_by_symbol={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    before = {path: path.read_bytes() for path in cache_root.rglob("*") if path.is_file()}
    rows = _rows_for_all(_sessions(27, 28, 29, 30))
    rows["AAPL"] = (_row("AAPL", date(2026, 7, 27), close=Decimal("999")),)
    original = getattr(forward_cache, surface)

    def fail_late(*args: object, **kwargs: object) -> object:
        if kwargs.get("symbol") == "NVDA" and (surface == "_load_target_rows" or args[0]):
            raise error
        return original(*args, **kwargs)

    monkeypatch.setattr(forward_cache, surface, fail_late)
    with pytest.raises(type(error)) as caught:
        commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol=rows,
            failure_reasons_by_symbol={},
            cache_root=cache_root,
            repo_root=repo_root,
        )
    assert caught.value is error
    details = get_kis_paper_daily_nas_forward_failure_details(error)
    assert details == {
        "failure_stage": stage,
        "failure_category": category,
        "failure_symbol": "NVDA",
    }
    assert str(error) not in json.dumps(details)
    assert {path: path.read_bytes() for path in cache_root.rglob("*") if path.is_file()} == before


def test_conflicting_duplicates_within_incoming_batch_still_fail_before_cache_access(
    tmp_path: Path,
) -> None:
    rows = _rows_for_all(_sessions(27, 28, 29))
    rows["AAPL"] += (_row("AAPL", date(2026, 7, 27), close=Decimal("999")),)
    cache_root = tmp_path / "external"
    with pytest.raises(KisPaperDailyNasForwardCacheError) as caught:
        commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol=rows,
            failure_reasons_by_symbol={},
            cache_root=cache_root,
            repo_root=tmp_path / "repo",
        )
    assert get_kis_paper_daily_nas_forward_failure_details(caught.value) == {
        "failure_stage": "observation_input",
        "failure_category": "duplicate_conflict",
    }
    assert not cache_root.exists()


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
