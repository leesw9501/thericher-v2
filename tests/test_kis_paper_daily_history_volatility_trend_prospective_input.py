from __future__ import annotations

import os
import socket
import urllib.request
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    kis_paper_daily_history_volatility_trend_prospective_input as prospective,
)
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KisPaperDailyNasHistoricalForwardProjection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader


def test_projects_exact_common_sessions_strictly_after_the_frozen_boundary(
    tmp_path: Path,
) -> None:
    panel = _panel(
        tmp_path,
        sessions_by_symbol={
            "AAPL": _sessions(1, 2, 3, 4, 5, 6),
            "AMZN": _sessions(1, 2, 3, 4, 5, 6),
            "GOOGL": _sessions(1, 2, 3, 4, 5, 6),
            "META": _sessions(1, 2, 3, 4, 5),
            "MSFT": _sessions(1, 2, 3, 4, 5, 6),
            "NVDA": _sessions(1, 2, 3, 4, 5, 6),
        },
    )
    index_before = panel.index_path.read_bytes()

    result = prospective.build_kis_paper_daily_history_volatility_trend_prospective_input(
        panel,
        frozen_boundary=date(2026, 7, 2),
    )

    assert result.status == "ready"
    assert result.input_available is True
    assert result.post_boundary_common_sessions == (
        date(2026, 7, 3),
        date(2026, 7, 4),
        date(2026, 7, 5),
    )
    assert result.eligible_target_slot_count == 1
    assert panel.index_path.read_bytes() == index_before
    payload = result.safe_payload()
    assert payload["freshness"]["post_boundary_common_sessions"] == {
        "all_symbols_exact": True,
        "count": 3,
        "dates_sha256": prospective._session_dates_hash(  # noqa: SLF001
            result.post_boundary_common_sessions
        ),
        "start": "2026-07-03",
        "end": "2026-07-05",
    }
    assert payload["freshness"]["target_slot_contract"]["eligible_target_slot_count"] == 1
    _assert_no_raw_fields(payload)


def test_distinguishes_input_unavailable_without_retaining_bars(tmp_path: Path) -> None:
    panel = _panel(tmp_path, sessions_by_symbol=_all_symbols(_sessions(1, 2, 3)))

    result = prospective.build_kis_paper_daily_history_volatility_trend_prospective_input(
        panel,
        frozen_boundary=date(2026, 7, 1),
    )

    assert result.status == "input_unavailable"
    assert result.input_available is False
    assert result.post_boundary_common_sessions == (date(2026, 7, 2), date(2026, 7, 3))
    assert result.eligible_target_slot_count == 0
    assert not hasattr(result, "bars_by_symbol")
    payload = result.safe_payload()
    assert payload["freshness"]["post_boundary_common_sessions"] == {
        "all_symbols_exact": True,
        "count": 2,
        "dates_sha256": prospective._session_dates_hash(  # noqa: SLF001
            result.post_boundary_common_sessions
        ),
        "start": "2026-07-02",
        "end": "2026-07-03",
    }
    assert payload["freshness"]["target_slot_contract"]["eligible_target_slot_count"] == 0
    _assert_no_raw_fields(payload)


def test_loader_reattests_the_local_panel_without_external_or_credential_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    panel = _panel(tmp_path / "panel", sessions_by_symbol=_all_symbols(_sessions(1, 2)))
    calls: list[tuple[Path | str, Path | str | None]] = []

    def load_panel(
        cache_root: Path | str,
        *,
        repo_root: Path | str | None,
    ) -> KisPaperDailyHistoryPanel:
        calls.append((cache_root, repo_root))
        return panel

    _deny_external_access(monkeypatch)
    monkeypatch.setattr(prospective, "build_kis_paper_daily_history_panel", load_panel)

    result = prospective.load_kis_paper_daily_history_volatility_trend_prospective_input(
        frozen_boundary=date(2026, 7, 1),
        cache_root=tmp_path / "cache",
        repo_root=tmp_path / "repo",
    )

    assert calls == [(tmp_path / "cache", tmp_path / "repo")]
    assert result.status == "input_unavailable"


def test_rejects_tampered_eligibility_and_non_date_boundary(tmp_path: Path) -> None:
    panel = _panel(tmp_path, sessions_by_symbol=_all_symbols(_sessions(1, 2)))
    result = prospective.build_kis_paper_daily_history_volatility_trend_prospective_input(
        panel,
        frozen_boundary=date(2026, 7, 1),
    )

    object.__setattr__(
        result,
        "eligible_target_slot_count",
        result.eligible_target_slot_count + 1,
    )
    with pytest.raises(ValueError, match="provenance"):
        prospective.require_attested_kis_paper_daily_history_volatility_trend_prospective_input(
            result
        )
    with pytest.raises(ValueError, match="frozen boundary"):
        prospective.build_kis_paper_daily_history_volatility_trend_prospective_input(
            panel,
            frozen_boundary="2026-07-01",  # type: ignore[arg-type]
        )


def test_verified_forward_projection_uses_only_three_exact_common_sessions(
    tmp_path: Path,
) -> None:
    frozen_sessions = tuple(date(2026, 6, 1) + timedelta(days=index) for index in range(29))
    frozen_boundary = frozen_sessions[-1]
    panel = _panel(tmp_path / "frozen", sessions_by_symbol=_all_symbols(frozen_sessions))
    index_before = panel.index_path.read_bytes()
    common_forward_sessions = tuple(
        frozen_boundary + timedelta(days=index) for index in range(1, 4)
    )
    projection = _forward_projection(
        panel,
        frozen_boundary=frozen_boundary,
        sessions_by_symbol={
            symbol: (
                *common_forward_sessions,
                *( (frozen_boundary + timedelta(days=4),) if symbol == "AAPL" else () ),
            )
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
    )

    result = prospective.build_kis_paper_daily_history_volatility_trend_prospective_input(
        panel,
        frozen_boundary=frozen_boundary,
        historical_forward_projection=projection,
        forward_cache_root=tmp_path / "forward-cache",
    )

    assert result.source_kind == "historical_forward_projection"
    assert result.status == "ready"
    assert result.post_boundary_common_sessions == common_forward_sessions
    assert result.eligible_target_slot_count == 1
    assert panel.index_path.read_bytes() == index_before
    payload = result.safe_payload()
    assert payload["source"]["kind"] == "historical_forward_projection"
    assert payload["forward_cache_sha256"] == projection.forward_cache_hash
    _assert_no_raw_fields(payload)


def test_verified_forward_projection_with_partial_or_two_session_data_is_unavailable(
    tmp_path: Path,
) -> None:
    frozen_sessions = tuple(date(2026, 6, 1) + timedelta(days=index) for index in range(29))
    frozen_boundary = frozen_sessions[-1]
    panel = _panel(tmp_path / "frozen", sessions_by_symbol=_all_symbols(frozen_sessions))
    first_two = tuple(frozen_boundary + timedelta(days=index) for index in range(1, 3))
    projection = _forward_projection(
        panel,
        frozen_boundary=frozen_boundary,
        sessions_by_symbol={
            symbol: (
                *first_two,
                *( (frozen_boundary + timedelta(days=3),) if symbol == "AAPL" else () ),
            )
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
    )

    result = prospective.build_kis_paper_daily_history_volatility_trend_prospective_input(
        panel,
        frozen_boundary=frozen_boundary,
        historical_forward_projection=projection,
        forward_cache_root=tmp_path / "forward-cache",
    )

    assert result.status == "input_unavailable"
    assert result.input_available is False
    assert result.post_boundary_common_sessions == first_two
    assert result.eligible_target_slot_count == 0


def test_forward_loader_reattests_without_external_or_credential_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen_sessions = tuple(date(2026, 6, 1) + timedelta(days=index) for index in range(29))
    frozen_boundary = frozen_sessions[-1]
    panel = _panel(tmp_path / "frozen", sessions_by_symbol=_all_symbols(frozen_sessions))
    projection = _forward_projection(
        panel,
        frozen_boundary=frozen_boundary,
        sessions_by_symbol=_all_symbols(
            tuple(frozen_boundary + timedelta(days=index) for index in range(1, 4))
        ),
    )
    calls: list[str] = []

    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective,
        "build_kis_paper_daily_history_panel",
        lambda *_args, **_kwargs: panel,
    )
    monkeypatch.setattr(
        prospective,
        "load_verified_kis_paper_daily_nas_forward_cache",
        lambda **_kwargs: calls.append("forward-cache") or object(),
    )
    monkeypatch.setattr(
        prospective,
        "build_kis_paper_daily_nas_historical_forward_projection",
        lambda **_kwargs: calls.append("projection") or projection,
    )

    result = prospective.load_kis_paper_daily_history_volatility_trend_prospective_input(
        frozen_boundary=frozen_boundary,
        cache_root=tmp_path / "historical-cache",
        forward_cache_root=tmp_path / "forward-cache",
        repo_root=tmp_path / "repository",
    )

    assert calls == ["forward-cache", "projection"]
    assert result.status == "ready"
    assert result.source_kind == "historical_forward_projection"


def _panel(
    root: Path,
    *,
    sessions_by_symbol: Mapping[str, tuple[date, ...]],
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    dataset_hash = "sha256:" + "a" * 64
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        sessions = sessions_by_symbol[symbol]
        bars = tuple(
            _bar(symbol=symbol, session=session, value=Decimal(100 + offset + index))
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
            coverage_start_bucket="2026-Q3",
            coverage_end_bucket="2026-Q3",
        )
    common_sessions = tuple(
        sorted(set.intersection(*(set(values) for values in sessions_by_symbol.values())))
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
        common_sessions=common_sessions,
    )


def _sessions(*days: int) -> tuple[date, ...]:
    return tuple(date(2026, 7, day) for day in days)


def _all_symbols(sessions: tuple[date, ...]) -> dict[str, tuple[date, ...]]:
    return {symbol: sessions for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS}


def _bar(*, symbol: str, session: date, value: Decimal) -> Bar:
    start_ts = datetime.combine(session, datetime.min.time(), tzinfo=UTC)
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("1000"),
        complete=True,
    )


def _forward_projection(
    panel: KisPaperDailyHistoryPanel,
    *,
    frozen_boundary: date,
    sessions_by_symbol: Mapping[str, tuple[date, ...]],
) -> KisPaperDailyNasHistoricalForwardProjection:
    common_sessions = tuple(
        sorted(set.intersection(*(set(values) for values in sessions_by_symbol.values())))
    )
    context_by_symbol = {
        symbol: tuple(panel.bars_by_symbol[symbol].bars[-29:])
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    forward_by_symbol = {
        symbol: tuple(
            _bar(
                symbol=symbol,
                session=session,
                value=Decimal(200 + symbol_offset + index),
            )
            for index, session in enumerate(sessions_by_symbol[symbol])
        )
        for symbol_offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1)
    }
    eligible_target_slot_count = len(common_sessions) // 3
    return KisPaperDailyNasHistoricalForwardProjection(
        frozen_panel_hash=panel.dataset_hash,
        forward_cache_hash="sha256:" + "c" * 64,
        frozen_boundary=frozen_boundary,
        context_by_symbol=MappingProxyType(context_by_symbol),
        forward_by_symbol=MappingProxyType(forward_by_symbol),
        forward_common_sessions=common_sessions,
        eligible_target_slot_count=eligible_target_slot_count,
        status="ready" if eligible_target_slot_count else "input_unavailable",
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("prospective input must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(os, "getenv", denied)


def _assert_no_raw_fields(value: object) -> None:
    forbidden = {
        "bars",
        "close",
        "entry",
        "exit",
        "high",
        "low",
        "open",
        "prediction",
        "price",
        "target",
        "volume",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden)
        for nested in value.values():
            _assert_no_raw_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_fields(nested)
