from __future__ import annotations

import os
import socket
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import prepare_kis_paper_intraday_feature_input
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session

_FIRST_SESSION = date(2026, 7, 20)
_SECOND_SESSION = date(2026, 7, 21)


def test_prepares_exact_offline_kis_feature_input_with_deterministic_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _catalog((_FIRST_SESSION, _SECOND_SESSION))

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("feature input preparation must stay offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("feature input preparation must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)

    first = prepare_kis_paper_intraday_feature_input(
        source,
        session_dates=(_FIRST_SESSION, _SECOND_SESSION),
    )
    second = prepare_kis_paper_intraday_feature_input(
        source,
        session_dates=(_FIRST_SESSION, _SECOND_SESSION),
    )
    first_session = us_equity_2026_session(_FIRST_SESSION)
    second_session = us_equity_2026_session(_SECOND_SESSION)
    assert first_session is not None
    assert second_session is not None

    assert first.catalog.dataset_id == (
        f"{source.dataset_id}:complete-sessions-20260720-20260721"
    )
    assert len(first.catalog.bars) == 780
    assert first.session_dates == (_FIRST_SESSION, _SECOND_SESSION)
    assert first.session_windows == (first_session.window, second_session.window)
    assert first.input_id == (
        f"{first.catalog.dataset_id}:feature-input-20260720-20260721"
    )
    assert first.input_hash.startswith("sha256:")
    assert (first.input_id, first.input_hash) == (second.input_id, second.input_hash)


@pytest.mark.parametrize(
    ("session_dates", "match"),
    [
        ((_SECOND_SESSION, _FIRST_SESSION), "chronological"),
        ((date(2026, 7, 3),), "closed"),
        ((date(2026, 11, 27),), "early-close"),
    ],
)
def test_feature_input_rejects_invalid_session_contracts(
    session_dates: tuple[date, ...],
    match: str,
) -> None:
    source = _catalog((_FIRST_SESSION, _SECOND_SESSION))

    with pytest.raises(ValueError, match=match):
        prepare_kis_paper_intraday_feature_input(source, session_dates=session_dates)


def test_feature_input_rejects_incomplete_or_non_kis_catalogs() -> None:
    incomplete = _catalog((_FIRST_SESSION,), excluded_minutes={100})

    with pytest.raises(ValueError, match="incomplete"):
        prepare_kis_paper_intraday_feature_input(
            incomplete,
            session_dates=(_FIRST_SESSION,),
        )

    non_kis = _catalog((_FIRST_SESSION,), dataset_id="unit.external.intraday.m1")
    with pytest.raises(ValueError, match="verified KIS"):
        prepare_kis_paper_intraday_feature_input(
            non_kis,
            session_dates=(_FIRST_SESSION,),
        )


def test_feature_input_requires_ordered_date_tuple() -> None:
    source = _catalog((_FIRST_SESSION,))

    with pytest.raises(TypeError, match="must be a tuple"):
        prepare_kis_paper_intraday_feature_input(
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
        dataset_hash="sha256:" + "2" * 64,
        source_path=Path("external-kis-index.json"),
        bars=tuple(bars),
    )
