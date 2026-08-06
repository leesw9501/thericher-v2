from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import CatalogedBars, SessionWindow, us_equity_2026_session
from thericher_v2.models.session_reset_vwap_feature import build_session_reset_vwap_feature
from thericher_v2.research.kis_intraday_session_reset_vwap_feature_mechanics import (
    KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID,
    run_kis_intraday_session_reset_vwap_feature_mechanics,
)


def test_vwap_uses_only_completed_prefix_inside_declared_session() -> None:
    session = SessionWindow(
        open_ts=datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        close_ts=datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
    )
    bars = (
        _bar(start=session.open_ts, value="3", volume="2"),
        _bar(start=session.open_ts + timedelta(minutes=1), value="6", volume="1"),
        _bar(start=session.open_ts + timedelta(minutes=2), value="99", volume="1"),
    )

    feature = build_session_reset_vwap_feature(
        bars,
        session=session,
        as_of=bars[1].end_ts,
    )

    assert feature.bar_count == 2
    assert feature.cumulative_volume == Decimal("3")
    assert feature.vwap == Decimal("4")
    assert feature.feature_window_end == bars[1].end_ts


def test_vwap_rejects_noncontiguous_completed_prefix() -> None:
    session = SessionWindow(
        open_ts=datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        close_ts=datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
    )
    bars = (
        _bar(start=session.open_ts, value="3", volume="1"),
        _bar(start=session.open_ts + timedelta(minutes=2), value="4", volume="1"),
    )

    with pytest.raises(ValueError, match="contiguous"):
        build_session_reset_vwap_feature(bars, session=session, as_of=bars[-1].end_ts)


def test_vwap_rejects_a_prefix_that_omits_the_session_opening_bar() -> None:
    session = SessionWindow(
        open_ts=datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        close_ts=datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
    )
    bars = (
        _bar(start=session.open_ts + timedelta(minutes=1), value="3", volume="1"),
        _bar(start=session.open_ts + timedelta(minutes=2), value="4", volume="1"),
    )

    with pytest.raises(ValueError, match="opening bar"):
        build_session_reset_vwap_feature(bars, session=session, as_of=bars[-1].end_ts)


def test_mechanics_preflight_writes_only_source_safe_aggregate_artifact(tmp_path: Path) -> None:
    catalog = _complete_catalog(session_count=20)
    artifact_root = tmp_path / "model-artifacts"

    run = run_kis_intraday_session_reset_vwap_feature_mechanics(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
    )

    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert run.status == "complete"
    assert run.session_count == 20
    assert run.evaluated_window_count == 100
    assert run.feature_window_hash is not None
    assert run.summary_path == (
        artifact_root
        / "research"
        / KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID
        / "unit-r1"
        / "summary.json"
    )
    assert payload["mechanics"]["feature_window_hash"] == run.feature_window_hash
    assert payload["access"] == {
        "broker_access": "not_invoked",
        "credential_access": "not_invoked",
        "gpu_access": "not_invoked",
        "network_access": "not_invoked",
        "scheduler_access": "not_invoked",
    }
    assert payload["non_retention"] == {
        "feature_values_retained": False,
        "orders_retained": False,
        "pnl_retained": False,
        "raw_market_data_retained": False,
        "raw_price_values_retained": False,
        "raw_volume_values_retained": False,
        "signals_retained": False,
    }
    assert "12.34" not in run.summary_path.read_text(encoding="utf-8")


def test_mechanics_preflight_fails_closed_when_twenty_complete_sessions_are_absent(
    tmp_path: Path,
) -> None:
    run = run_kis_intraday_session_reset_vwap_feature_mechanics(
        _complete_catalog(session_count=19),
        artifact_root=tmp_path / "model-artifacts",
        run_label="missing-r1",
    )

    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "insufficient_complete_regular_sessions"
    assert run.feature_window_hash is None
    assert payload["mechanics"]["evaluated_window_count"] == 0
    assert payload["input_unavailable_reason"] == "insufficient_complete_regular_sessions"


def test_mechanics_preflight_fails_closed_for_zero_cumulative_volume(tmp_path: Path) -> None:
    run = run_kis_intraday_session_reset_vwap_feature_mechanics(
        _complete_catalog(session_count=20, volume="0"),
        artifact_root=tmp_path / "model-artifacts",
        run_label="zero-volume-r1",
    )

    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "invalid_completed_session_prefix"
    assert run.feature_window_hash is None
    assert payload["non_retention"]["raw_volume_values_retained"] is False


@pytest.mark.parametrize(
    ("dataset_id", "symbol", "market"),
    (
        ("local.fixture.intraday.m1.v1", "QQQ", "NAS"),
        ("kis.paper.private.intraday.qqq.nas.m1.v1", "SPY", "NAS"),
        ("kis.paper.private.intraday.qqq.nas.m1.v1", "QQQ", "NYS"),
    ),
)
def test_mechanics_preflight_rejects_non_qqq_nas_catalog_before_writing_artifacts(
    tmp_path: Path,
    dataset_id: str,
    symbol: str,
    market: str,
) -> None:
    catalog = _complete_catalog(
        session_count=20,
        dataset_id=dataset_id,
        symbol=symbol,
        market=market,
    )
    artifact_root = tmp_path / "model-artifacts"

    with pytest.raises(ValueError, match="QQQ/NAS"):
        run_kis_intraday_session_reset_vwap_feature_mechanics(
            catalog,
            artifact_root=artifact_root,
            run_label="wrong-source-r1",
        )

    assert not artifact_root.exists()


def test_mechanics_preflight_rejects_symlinked_artifact_descendant_before_writing(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    repository_escape = tmp_path / "repository-escape"
    repository_escape.mkdir()
    try:
        (artifact_root / "research").symlink_to(repository_escape, target_is_directory=True)
    except OSError:
        pytest.skip("the current Windows environment does not permit directory symlinks")

    with pytest.raises(ValueError, match="artifact directory must be direct"):
        run_kis_intraday_session_reset_vwap_feature_mechanics(
            _complete_catalog(session_count=20),
            artifact_root=artifact_root,
            run_label="symlink-r1",
        )

    assert not (repository_escape / KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID).exists()


def test_mechanics_preflight_rejects_a_link_like_artifact_descendant_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    research = artifact_root / "research"
    research.mkdir(parents=True)
    real_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == research or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)

    with pytest.raises(ValueError, match="artifact directory must be direct"):
        run_kis_intraday_session_reset_vwap_feature_mechanics(
            _complete_catalog(session_count=20),
            artifact_root=artifact_root,
            run_label="link-like-r1",
        )

    assert not (research / KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID).exists()


def test_mechanics_module_has_no_execution_or_runtime_access_path() -> None:
    path = (
        Path(__file__).parents[1]
        / "src"
        / "thericher_v2"
        / "research"
        / "kis_intraday_session_reset_vwap_feature_mechanics.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "thericher_v2.execution" not in source
    assert "os.environ" not in source
    assert "subprocess" not in source
    assert "torch" not in source


def _complete_catalog(
    *,
    session_count: int,
    volume: str | None = None,
    symbol: str = "QQQ",
    market: str = "NAS",
    dataset_id: str = "kis.paper.private.intraday.qqq.nas.m1.v1",
) -> CatalogedBars:
    sessions = _regular_sessions(count=session_count)
    bars = tuple(
        _bar(
            start=session.window.open_ts + timedelta(minutes=offset),
            value="12.34",
            volume=volume or str(100 + offset),
            symbol=symbol,
            market=market,
        )
        for session in sessions
        for offset in range(390)
    )
    result = object.__new__(CatalogedBars)
    object.__setattr__(result, "dataset_id", dataset_id)
    object.__setattr__(result, "dataset_hash", "sha256:" + "a" * 64)
    object.__setattr__(result, "source_path", Path("D:/market_data/fixture.csv"))
    object.__setattr__(result, "bars", bars)
    return result


def _regular_sessions(*, count: int):
    selected = []
    candidate = date(2026, 1, 1)
    while len(selected) < count:
        session = us_equity_2026_session(candidate)
        if session is not None and session.kind == "regular":
            selected.append(session)
        candidate += timedelta(days=1)
    return tuple(selected)


def _bar(
    *,
    start: datetime,
    value: str,
    volume: str,
    symbol: str = "QQQ",
    market: str = "NAS",
) -> Bar:
    decimal = Decimal(value)
    return Bar(
        symbol=symbol,
        market=market,
        timeframe=Timeframe.M1,
        start_ts=start,
        open=decimal,
        high=decimal,
        low=decimal,
        close=decimal,
        volume=Decimal(volume),
        complete=True,
    )
