from __future__ import annotations

import os
import socket
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import select_complete_kis_paper_private_intraday_sessions
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session

_FIRST_SESSION = date(2026, 7, 20)
_SECOND_SESSION = date(2026, 7, 21)


def test_selects_exact_complete_sessions_with_deterministic_identity() -> None:
    source = _catalog((_FIRST_SESSION, _SECOND_SESSION))

    first = select_complete_kis_paper_private_intraday_sessions(
        source,
        session_dates=(_FIRST_SESSION, _SECOND_SESSION),
    )
    second = select_complete_kis_paper_private_intraday_sessions(
        source,
        session_dates=(_FIRST_SESSION, _SECOND_SESSION),
    )
    first_session = us_equity_2026_session(_FIRST_SESSION)
    second_session = us_equity_2026_session(_SECOND_SESSION)
    assert first_session is not None
    assert second_session is not None

    assert len(first.bars) == 780
    assert len(first.bars[:390]) == 390
    assert len(first.bars[390:]) == 390
    assert first.bars[0].start_ts == first_session.window.open_ts
    assert first.bars[389].end_ts == first_session.window.close_ts
    assert first.bars[390].start_ts == second_session.window.open_ts
    assert first.bars[-1].end_ts == second_session.window.close_ts
    assert first.bars[389].end_ts < first.bars[390].start_ts
    assert first.source_path == source.source_path
    assert first.dataset_id == (
        f"{source.dataset_id}:complete-sessions-20260720-20260721"
    )
    assert (first.dataset_id, first.dataset_hash) == (second.dataset_id, second.dataset_hash)
    assert all(bar.complete and bar.timeframe == Timeframe.M1 for bar in first.bars)


def test_selection_stays_offline_and_credential_free(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _catalog((_FIRST_SESSION,))

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("session selection must stay offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("session selection must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)

    selected = select_complete_kis_paper_private_intraday_sessions(
        source,
        session_dates=(_FIRST_SESSION,),
    )

    assert len(selected.bars) == 390


@pytest.mark.parametrize(
    ("session_dates", "match"),
    [
        ((_FIRST_SESSION, _FIRST_SESSION), "unique"),
        ((_SECOND_SESSION, _FIRST_SESSION), "chronological"),
        ((date(2026, 7, 3),), "closed"),
        ((date(2026, 11, 27),), "early-close"),
        ((date(2027, 1, 4),), "outside the 2026"),
    ],
)
def test_selection_rejects_invalid_session_date_contracts(
    session_dates: tuple[date, ...],
    match: str,
) -> None:
    source = _catalog((_FIRST_SESSION,))

    with pytest.raises(ValueError, match=match):
        select_complete_kis_paper_private_intraday_sessions(source, session_dates=session_dates)


def test_selection_rejects_incomplete_or_non_kis_source_catalogs() -> None:
    incomplete = _catalog((_FIRST_SESSION,), excluded_minutes={100})

    with pytest.raises(ValueError, match="incomplete"):
        select_complete_kis_paper_private_intraday_sessions(
            incomplete,
            session_dates=(_FIRST_SESSION,),
        )

    non_kis = _catalog((_FIRST_SESSION,), dataset_id="unit.external.intraday.m1")
    with pytest.raises(ValueError, match="verified KIS"):
        select_complete_kis_paper_private_intraday_sessions(
            non_kis,
            session_dates=(_FIRST_SESSION,),
        )


def test_selection_requires_an_explicit_tuple() -> None:
    source = _catalog((_FIRST_SESSION,))

    with pytest.raises(TypeError, match="must be a tuple"):
        select_complete_kis_paper_private_intraday_sessions(
            source,
            session_dates=[_FIRST_SESSION],  # type: ignore[arg-type]
        )


def _catalog(
    session_dates: tuple[date, ...],
    *,
    excluded_minutes: set[int] | None = None,
    dataset_id: str = "kis.paper.private.intraday.qqq.nas.m1.unit-v1",
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_date in session_dates:
        session = us_equity_2026_session(session_date)
        assert session is not None
        for minute in range(390):
            if excluded_minutes is not None and minute in excluded_minutes:
                continue
            price = Decimal("100") + Decimal(minute) / Decimal("100")
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=price,
                    high=price + Decimal("0.01"),
                    low=price - Decimal("0.01"),
                    close=price + Decimal("0.005"),
                    volume=Decimal("1000"),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
        dataset_hash="sha256:" + "1" * 64,
        source_path=Path("external-kis-index.json"),
        bars=tuple(bars),
    )
