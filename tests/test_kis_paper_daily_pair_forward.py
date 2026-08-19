from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.data import kis_paper_daily_pair_forward_cache as pair_forward_cache
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_FAILURE_PHASES,
    KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_PREPARE_SUBPHASES,
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
    KisPaperDailyPairForwardCacheError,
    KisPaperDailyPairForwardRow,
    commit_kis_paper_daily_pair_forward_observation,
    get_kis_paper_daily_pair_forward_commit_failure_phase,
    get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase,
    load_verified_kis_paper_daily_pair_forward_cache,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_paper_daily_pair_forward import (
    collect_kis_paper_daily_pair_forward_observation,
    collect_kis_paper_daily_pair_forward_once,
)

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_pair_cache_is_external_source_separated_and_replayable(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"

    run = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=_rows_for_pair((date(2026, 7, 27), date(2026, 7, 28))),
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
        observed_at=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert run.status == "ready"
    assert run.changed_target_count == 2
    assert run.cache.common_sessions == (date(2026, 7, 27), date(2026, 7, 28))
    assert tuple(run.cache.rows_by_target) == ("QQQ/NAS", "SPY/AMS")
    assert run.cache.targets_by_key["QQQ/NAS"].row_count == 2
    assert cache_root.is_dir()
    assert not (repo_root / "cache").exists()
    reloaded = load_verified_kis_paper_daily_pair_forward_cache(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert reloaded.cache_hash == run.cache.cache_hash
    _assert_source_safe(run.safe_payload())


def test_pair_cache_drops_preboundary_rows_and_preserves_prior_snapshots_on_retry(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"
    rows = _rows_for_pair((date(2026, 7, 24), date(2026, 7, 27)))

    first = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=rows,
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    snapshots = tuple(sorted((cache_root / "snapshots").rglob("*.csv.gz")))
    snapshot_bytes = {path.relative_to(cache_root): path.read_bytes() for path in snapshots}
    index = json.loads((cache_root / "index.json").read_bytes())

    second = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=_rows_for_pair((date(2026, 7, 24), date(2026, 7, 27))),
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert first.status == "ready"
    assert all(len(rows) == 1 for rows in first.cache.rows_by_target.values())
    assert second.status == "unchanged"
    assert second.retained_revision_conflict_count == 0
    assert second.revision_quarantined_target_count == 0
    assert tuple(sorted((cache_root / "snapshots").rglob("*.csv.gz"))) == snapshots
    assert {
        path.relative_to(cache_root): path.read_bytes()
        for path in (cache_root / "snapshots").rglob("*.csv.gz")
    } == snapshot_bytes
    updated = json.loads((cache_root / "index.json").read_bytes())
    assert updated["generation"] == index["generation"] + 1
    assert all(target["accepted_page_count"] == 2 for target in updated["targets"])


def test_pair_cache_defers_only_failed_target_and_quarantines_retained_revision_conflicts(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"
    commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=_rows_for_pair((date(2026, 7, 27),)),
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    partial_rows = _rows_for_pair((date(2026, 7, 28),))
    partial_rows.pop("SPY/AMS")
    partial = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=partial_rows,
        failure_reasons_by_target={"SPY/AMS": "transport_failure"},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    index_bytes = (cache_root / "index.json").read_bytes()
    conflicting = _rows_for_pair((date(2026, 7, 27), date(2026, 7, 29)))
    conflicting["QQQ/NAS"] = (
        _row("QQQ", "NAS", date(2026, 7, 27), Decimal("999")),
        conflicting["QQQ/NAS"][1],
    )

    assert partial.status == "partial"
    assert partial.cache.targets_by_key["SPY/AMS"].status == "deferred"
    assert partial.cache.targets_by_key["QQQ/NAS"].row_count == 2
    reconciled = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=conflicting,
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert reconciled.status == "partial"
    assert reconciled.retained_revision_conflict_count == 1
    assert reconciled.revision_quarantined_target_count == 1
    assert reconciled.categorical_failure_count == 1
    assert reconciled.cache.targets_by_key["QQQ/NAS"].status == "input_unavailable"
    assert (
        reconciled.cache.targets_by_key["QQQ/NAS"].last_reason
        == pair_forward_cache.KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON
    )
    assert reconciled.cache.targets_by_key["SPY/AMS"].status == "ready"
    assert reconciled.cache.rows_by_target["QQQ/NAS"][:2] == partial.cache.rows_by_target["QQQ/NAS"]
    assert reconciled.cache.targets_by_key["QQQ/NAS"].row_count == 3
    assert (cache_root / "index.json").read_bytes() != index_bytes
    payload = reconciled.safe_payload()
    assert "retained_revision_conflict_sha256" not in payload
    _assert_source_safe(payload)

    retained = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=_rows_for_pair((date(2026, 7, 30),)),
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert retained.status == "partial"
    assert retained.retained_revision_conflict_count == 0
    assert retained.revision_quarantined_target_count == 1
    assert retained.cache.targets_by_key["QQQ/NAS"].status == "input_unavailable"


def test_pair_cache_rejects_conflicts_inside_one_incoming_target(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"
    incoming = _rows_for_pair((date(2026, 7, 27),))
    incoming["QQQ/NAS"] = (
        incoming["QQQ/NAS"][0],
        _row("QQQ", "NAS", date(2026, 7, 27), Decimal("999")),
    )

    with pytest.raises(KisPaperDailyPairForwardCacheError, match="duplicate conflict") as raised:
        commit_kis_paper_daily_pair_forward_observation(
            rows_by_target=incoming,
            failure_reasons_by_target={},
            cache_root=cache_root,
            repo_root=repo_root,
        )

    assert get_kis_paper_daily_pair_forward_commit_failure_phase(raised.value) is None
    assert not cache_root.exists()


def test_pair_cache_rejects_unseen_nonforward_session(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"
    commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=_rows_for_pair((date(2026, 7, 27), date(2026, 7, 29))),
        failure_reasons_by_target={},
        cache_root=cache_root,
        repo_root=repo_root,
    )
    prior_index = (cache_root / "index.json").read_bytes()
    nonforward = _rows_for_pair((date(2026, 7, 28),))

    with pytest.raises(KisPaperDailyPairForwardCacheError, match="non-forward append") as raised:
        commit_kis_paper_daily_pair_forward_observation(
            rows_by_target=nonforward,
            failure_reasons_by_target={},
            cache_root=cache_root,
            repo_root=repo_root,
        )

    assert (
        get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(raised.value)
        == "incoming_merge"
    )
    assert (cache_root / "index.json").read_bytes() == prior_index


@pytest.mark.parametrize(
    ("subphase", "patch_name"),
    [
        ("cache_access", "_external_root"),
        ("cache_state_load", "_load_or_initialize_index"),
        ("incoming_merge", "_compressed_rows"),
    ],
)
def test_pair_cache_attaches_prepare_subphase_at_fixed_region_without_mutating_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    subphase: str,
    patch_name: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    error = KisPaperDailyPairForwardCacheError("private-subphase-detail-canary", "opaque")
    expected_args = error.args

    monkeypatch.setattr(
        pair_forward_cache,
        patch_name,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(KisPaperDailyPairForwardCacheError) as raised:
        commit_kis_paper_daily_pair_forward_observation(
            rows_by_target=_rows_for_pair((date(2026, 7, 27),)),
            failure_reasons_by_target={},
            cache_root=tmp_path / "external" / "qqq-spy-forward",
            repo_root=repo_root,
        )

    assert raised.value is error
    assert type(raised.value) is KisPaperDailyPairForwardCacheError
    assert raised.value.args == expected_args
    assert get_kis_paper_daily_pair_forward_commit_failure_phase(raised.value) == "cache_prepare"
    assert (
        get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(raised.value)
        == subphase
    )


def test_pair_cache_keeps_prepare_subphase_absent_for_unclassified_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    error = KisPaperDailyPairForwardCacheError("private-subphase-detail-canary", "opaque")
    expected_args = error.args

    class _UnclassifiedLock:
        def __enter__(self) -> None:
            raise error

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(pair_forward_cache, "_exclusive_lock", lambda _path: _UnclassifiedLock())

    with pytest.raises(KisPaperDailyPairForwardCacheError) as raised:
        commit_kis_paper_daily_pair_forward_observation(
            rows_by_target=_rows_for_pair((date(2026, 7, 27),)),
            failure_reasons_by_target={},
            cache_root=tmp_path / "external" / "qqq-spy-forward",
            repo_root=repo_root,
        )

    assert raised.value is error
    assert type(raised.value) is KisPaperDailyPairForwardCacheError
    assert raised.value.args == expected_args
    assert get_kis_paper_daily_pair_forward_commit_failure_phase(raised.value) == "cache_prepare"
    assert get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(raised.value) is None


@pytest.mark.parametrize(
    ("phase", "patch_name"),
    [
        ("snapshot_persist", "_write_snapshot"),
        ("index_persist", "_write_json_atomic"),
        ("cache_reverify", "load_verified_kis_paper_daily_pair_forward_cache"),
    ],
)
def test_pair_cache_attaches_only_fixed_commit_phase_at_persist_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    phase: str,
    patch_name: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    error = KisPaperDailyPairForwardCacheError("private-phase-detail-canary")

    monkeypatch.setattr(
        pair_forward_cache,
        patch_name,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(KisPaperDailyPairForwardCacheError) as raised:
        commit_kis_paper_daily_pair_forward_observation(
            rows_by_target=_rows_for_pair((date(2026, 7, 27),)),
            failure_reasons_by_target={},
            cache_root=tmp_path / "external" / "qqq-spy-forward",
            repo_root=repo_root,
        )

    assert raised.value is error
    assert str(raised.value) == "private-phase-detail-canary"
    assert get_kis_paper_daily_pair_forward_commit_failure_phase(raised.value) == phase
    assert get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(raised.value) is None


def test_pair_cache_commit_phase_reader_rejects_unrecognized_or_noncache_errors() -> None:
    error = KisPaperDailyPairForwardCacheError("private-phase-detail-canary")
    error._commit_failure_phase = "not_allowlisted"  # noqa: SLF001
    error._commit_failure_prepare_subphase = "cache_access"  # noqa: SLF001

    assert KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_FAILURE_PHASES == (
        "cache_prepare",
        "snapshot_persist",
        "index_persist",
        "cache_reverify",
    )
    assert KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_PREPARE_SUBPHASES == (
        "cache_access",
        "cache_state_load",
        "incoming_merge",
    )
    assert get_kis_paper_daily_pair_forward_commit_failure_phase(error) is None
    assert get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(error) is None
    assert get_kis_paper_daily_pair_forward_commit_failure_phase(OSError("private")) is None
    assert (
        get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(OSError("private"))
        is None
    )


def test_pair_cache_rejects_git_root_and_wrong_exchange(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(KisPaperDailyPairForwardCacheError, match="outside Git"):
        commit_kis_paper_daily_pair_forward_observation(
            rows_by_target=_rows_for_pair((date(2026, 7, 27),)),
            failure_reasons_by_target={},
            cache_root=repo_root / "cache",
            repo_root=repo_root,
        )
    with pytest.raises(ValueError, match="pair forward row"):
        KisPaperDailyPairForwardRow(
            symbol="SPY",
            exchange="NAS",
            session_date=date(2026, 7, 27),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_collector_uses_only_pair_targets_and_filters_incomplete_or_preboundary_rows(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"
    client = _FakeDailyClient(
        {
            "QQQ/NAS": _daily_page("20260730", "20260729", "20260724"),
            "SPY/AMS": _daily_page("20260730", "20260729", "20260724"),
        }
    )

    run = collect_kis_paper_daily_pair_forward_once(
        client,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=datetime(2026, 7, 29, 22, tzinfo=UTC),
    )

    assert run.status == "ready"
    assert [(query.symbol, query.exchange) for query in client.queries] == [
        ("QQQ", "NAS"),
        ("SPY", "AMS"),
    ]
    expected_allowlist = {"QQQ": frozenset({"NAS"}), "SPY": frozenset({"AMS"})}
    assert all(query.approved_symbol_exchanges == expected_allowlist for query in client.queries)
    assert run.cache.common_sessions == (date(2026, 7, 29),)
    assert all(len(rows) == 1 for rows in run.cache.rows_by_target.values())


def test_collector_marks_one_transport_fault_without_network_or_credentials(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    client = _FakeDailyClient(
        {
            "QQQ/NAS": _daily_page("20260729"),
            "SPY/AMS": KisPaperMarketDataError("transport_failure"),
        }
    )

    run = collect_kis_paper_daily_pair_forward_once(
        client,
        cache_root=tmp_path / "external" / "qqq-spy-forward",
        repository_root=repo_root,
        observed_at=datetime(2026, 7, 29, 22, tzinfo=UTC),
    )

    assert run.status == "partial"
    assert run.cache.targets_by_key["SPY/AMS"].status == "deferred"
    assert run.cache.targets_by_key["QQQ/NAS"].status == "ready"


def test_uncommitted_collection_observation_does_not_create_a_cache(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "external" / "qqq-spy-forward"
    client = _FakeDailyClient(
        {
            "QQQ/NAS": _daily_page("20260729"),
            "SPY/AMS": _daily_page("20260729"),
        }
    )

    observation = collect_kis_paper_daily_pair_forward_observation(
        client,
        observed_at=datetime(2026, 7, 29, 22, tzinfo=UTC),
    )

    assert not cache_root.exists()
    run = commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=observation.rows_by_target,
        failure_reasons_by_target=observation.failure_reasons_by_target,
        cache_root=cache_root,
        repo_root=repo_root,
        observed_at=observation.observed_at,
    )
    assert run.status == "ready"


def test_pair_forward_compose_isolates_preflight_from_credentials_and_network() -> None:
    source = COMPOSE.read_text(encoding="ascii")
    collector = source.split("  kis-paper-daily-pair-forward:\n", maxsplit=1)[1].split(
        "  kis-paper-daily-pair-forward-readiness:\n",
        maxsplit=1,
    )[0]
    readiness = source.split(
        "  kis-paper-daily-pair-forward-readiness:\n",
        maxsplit=1,
    )[1].split(
        "  kis-paper-daily-pair-forward-preflight:\n",
        maxsplit=1,
    )[0]
    preflight = source.split("  kis-paper-daily-pair-forward-preflight:\n", maxsplit=1)[1].split(
        "  kis-paper-daily-nas-forward-preflight:\n",
        maxsplit=1,
    )[0]

    assert 'profiles: ["kis-paper-daily-pair-forward"]' in collector
    assert "KIS_PAPER_APP_KEY" in collector
    assert "KIS_PAPER_APP_SECRET" in collector
    assert "KIS_LIVE" not in collector
    assert "account" not in collector.lower()
    assert "order" not in collector.lower()
    expected_image = "image: localhost/thericher-v2/kis-paper-daily-pair-forward:local"
    assert expected_image in collector
    assert expected_image in readiness
    assert expected_image in preflight
    assert collector.count("image:") == 1
    assert readiness.count("image:") == 1
    assert preflight.count("image:") == 1
    assert 'profiles: ["kis-paper-daily-pair-forward"]' in readiness
    assert "network_mode: none" in readiness
    assert "KIS_PAPER_APP_KEY" in readiness
    assert "KIS_PAPER_APP_SECRET" in readiness
    assert "KIS_LIVE" not in readiness
    assert "account" not in readiness.lower()
    assert "order" not in readiness.lower()
    assert "--readiness" in readiness
    assert "/app/market_data" not in readiness
    assert "/app/collection_control" in readiness
    assert "read_only: true" in readiness
    assert "network_mode: none" in preflight
    assert "KIS_PAPER_APP_KEY" not in preflight
    assert "KIS_PAPER_APP_SECRET" not in preflight
    assert "KIS_LIVE" not in preflight
    assert "/app/market_data:ro" in preflight
    assert "read_only: true" in preflight


def _rows_for_pair(
    sessions: tuple[date, ...],
) -> dict[str, tuple[KisPaperDailyPairForwardRow, ...]]:
    return {
        f"{symbol}/{exchange}": tuple(
            _row(symbol, exchange, session, Decimal(100 + target_offset + index))
            for index, session in enumerate(sessions)
        )
        for target_offset, (symbol, exchange) in enumerate(
            KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
            start=1,
        )
    }


def _row(
    symbol: str,
    exchange: str,
    session: date,
    close: Decimal,
) -> KisPaperDailyPairForwardRow:
    return KisPaperDailyPairForwardRow(
        symbol=symbol,
        exchange=exchange,
        session_date=session,
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
    )


class _FakeDailyClient:
    def __init__(self, responses: dict[str, KisPaperDailyRawPage | BaseException]) -> None:
        self._responses = responses
        self.queries: list[KisPaperDailyQuery] = []

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        response = self._responses[f"{query.symbol}/{query.exchange}"]
        if isinstance(response, BaseException):
            raise response
        return response


def _daily_page(*dates: str) -> KisPaperDailyRawPage:
    query = KisPaperDailyQuery(
        symbol="QQQ",
        exchange="NAS",
        by_date="20260729",
        approved_symbol_exchanges={"QQQ": frozenset({"NAS"})},
    )
    rows = tuple(
        KisPaperDailyRawRow(
            xymd=value,
            open="100",
            high="101",
            low="99",
            clos="100",
            tvol="1000",
        )
        for value in dates
    )
    return KisPaperDailyRawPage(
        page=KisPaperDailyPage(
            query=query,
            row_count=len(rows),
            newest_date=dates[0] if dates else None,
            oldest_date=dates[-1] if dates else None,
            required_ohlcv_fields_present=True,
            continuation_available=False,
            continuation_value=None,
        ),
        rows=rows,
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
