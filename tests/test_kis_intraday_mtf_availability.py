from __future__ import annotations

import json
import socket
from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_intraday_mtf_availability as availability
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session


def test_materializes_one_safe_aligned_multi_timeframe_receipt() -> None:
    session_date = date(2026, 7, 20)
    catalogs = _catalogs(session_date)
    contract = availability.freeze_kis_intraday_mtf_availability_contract(
        catalogs,
        code_revision=_sha256("code-r1"),
    )

    receipt = availability.materialize_kis_intraday_mtf_availability(contract, catalogs)

    assert receipt.status == "qualified_for_prospective_input"
    assert receipt.reason is None
    assert receipt.common_aligned_session_count == 1
    assert [target.cutoff_prefix_complete_count for target in receipt.targets] == [1, 1]
    assert [target.all_timeframes_available_count for target in receipt.targets] == [1, 1]
    assert [dict(target.available_session_counts) for target in receipt.targets] == [
        {
            Timeframe.M1: 1,
            Timeframe.M5: 1,
            Timeframe.M10: 1,
            Timeframe.H1: 1,
            Timeframe.H3: 1,
        },
        {
            Timeframe.M1: 1,
            Timeframe.M5: 1,
            Timeframe.M10: 1,
            Timeframe.H1: 1,
            Timeframe.H3: 1,
        },
    ]

    payload = receipt.safe_payload()
    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    assert session_date.isoformat() not in rendered
    assert "101.234" not in rendered
    assert "source_path" not in rendered
    assert payload["scope"] == {
        "prospective_input_only": True,
        "model_or_strategy_result": False,
        "target_or_return_opened": False,
        "pnl_calculated": False,
        "paper_or_broker_action": False,
        "gpu_used": False,
        "raw_market_data_written": False,
        "raw_market_data_persisted": False,
    }


@pytest.mark.parametrize(
    ("mutate", "unsafe_catalog"),
    [
        (lambda bars: bars[:-1], False),
        (lambda bars: bars + (bars[0],), False),
        (lambda bars: bars[:120] + (replace(bars[120], complete=False),) + bars[121:], False),
        (lambda bars: _future_bar_in_prefix(bars), True),
    ],
    ids=["missing", "duplicate", "incomplete", "future"],
)
def test_rejects_one_corrupt_exact_candidate_without_affecting_other_target(
    mutate: Callable[[tuple[Bar, ...]], tuple[Bar, ...]],
    unsafe_catalog: bool,
) -> None:
    session_date = date(2026, 7, 20)
    corrupted_bars = mutate(_bars("QQQ", session_date))
    qqq = (
        _unsafe_catalog("QQQ", "NAS", corrupted_bars)
        if unsafe_catalog
        else _catalog("QQQ", "NAS", session_date, bars=corrupted_bars)
    )
    spy = _catalog("SPY", "AMS", session_date)
    catalogs = {"QQQ/NAS/1m": qqq, "SPY/AMS/1m": spy}
    contract = availability.freeze_kis_intraday_mtf_availability_contract(
        catalogs,
        code_revision=_sha256("code-r1"),
    )

    receipt = availability.materialize_kis_intraday_mtf_availability(contract, catalogs)

    assert receipt.status == "input_unavailable"
    assert receipt.reason == "insufficient_contiguous_intraday_session_coverage"
    assert receipt.common_aligned_session_count == 0
    assert receipt.targets[0].cutoff_prefix_complete_count == 0
    assert receipt.targets[1].all_timeframes_available_count == 1


def test_requires_exact_common_session_dates() -> None:
    qqq_date = date(2026, 7, 20)
    spy_date = date(2026, 7, 21)
    catalogs = {
        "QQQ/NAS/1m": _catalog("QQQ", "NAS", qqq_date),
        "SPY/AMS/1m": _catalog("SPY", "AMS", spy_date),
    }
    contract = availability.freeze_kis_intraday_mtf_availability_contract(
        catalogs,
        code_revision=_sha256("code-r1"),
    )

    receipt = availability.materialize_kis_intraday_mtf_availability(contract, catalogs)

    assert receipt.status == "input_unavailable"
    assert [target.all_timeframes_available_count for target in receipt.targets] == [1, 1]
    assert receipt.common_aligned_session_count == 0


def test_ignores_a_future_calendar_row_outside_the_frozen_2026_scope() -> None:
    session_date = date(2026, 7, 20)
    qqq_bars = _bars("QQQ", session_date)
    qqq_with_future_row = qqq_bars + (
        Bar(
            symbol="QQQ",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=qqq_bars[-1].start_ts.replace(year=2027),
            open=qqq_bars[-1].open,
            high=qqq_bars[-1].high,
            low=qqq_bars[-1].low,
            close=qqq_bars[-1].close,
            volume=qqq_bars[-1].volume,
            complete=True,
        ),
    )
    catalogs = {
        "QQQ/NAS/1m": _catalog("QQQ", "NAS", session_date, bars=qqq_with_future_row),
        "SPY/AMS/1m": _catalog("SPY", "AMS", session_date),
    }
    contract = availability.freeze_kis_intraday_mtf_availability_contract(
        catalogs,
        code_revision=_sha256("code-r1"),
    )

    receipt = availability.materialize_kis_intraday_mtf_availability(contract, catalogs)

    assert receipt.status == "qualified_for_prospective_input"
    assert receipt.common_aligned_session_count == 1


@pytest.mark.parametrize("session_date", [date(2026, 3, 9), date(2026, 11, 2)])
def test_uses_fixed_1530_eastern_cutoff_across_dst(session_date: date) -> None:
    contract = availability.freeze_kis_intraday_mtf_availability_contract(
        _catalogs(session_date),
        code_revision=_sha256("code-r1"),
    )

    receipt = availability.materialize_kis_intraday_mtf_availability(
        contract,
        _catalogs(session_date),
    )

    assert receipt.status == "qualified_for_prospective_input"
    assert receipt.common_aligned_session_count == 1


def test_runner_is_idempotent_external_and_has_no_network_or_environment_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalogs = _catalogs(date(2026, 7, 20))
    calls: list[dict[str, object]] = []

    def load_catalog(**kwargs: object) -> CatalogedBars:
        calls.append(kwargs)
        return catalogs[f"{kwargs['symbol']}/{kwargs['exchange']}/1m"]

    monkeypatch.setattr(
        availability,
        "load_verified_kis_paper_private_intraday_catalog",
        load_catalog,
    )
    monkeypatch.setattr(socket, "create_connection", _forbid)
    monkeypatch.setattr(availability.os, "environ", _DenyEnvironment())
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    kwargs = {
        "cache_root": tmp_path / "market-data",
        "artifact_root": artifact_root,
        "repo_root": repo_root,
        "run_label": "unit-r1",
        "code_revision": _sha256("code-r1"),
    }

    first = availability.run_kis_intraday_mtf_availability_receipt(**kwargs)
    second = availability.run_kis_intraday_mtf_availability_receipt(**kwargs)

    assert first.receipt.status == "qualified_for_prospective_input"
    assert second.precommit_sha256 == first.precommit_sha256
    assert second.summary_sha256 == first.summary_sha256
    assert first.run_directory.is_relative_to(artifact_root)
    assert not first.run_directory.is_relative_to(repo_root)
    assert first.precommit_path.read_bytes() == second.precommit_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    rendered = first.summary_path.read_text(encoding="utf-8")
    for raw_value in ("101.234", str(kwargs["cache_root"]), str(repo_root)):
        assert raw_value not in rendered
    assert len(calls) == 4


def test_runner_rejects_changed_source_identity_for_an_existing_run_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalogs = _catalogs(date(2026, 7, 20))
    current_catalogs = catalogs

    def load_catalog(**kwargs: object) -> CatalogedBars:
        return current_catalogs[f"{kwargs['symbol']}/{kwargs['exchange']}/1m"]

    monkeypatch.setattr(
        availability,
        "load_verified_kis_paper_private_intraday_catalog",
        load_catalog,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    kwargs = {
        "cache_root": tmp_path / "market-data",
        "artifact_root": tmp_path / "artifacts",
        "repo_root": repo_root,
        "run_label": "identity-r1",
        "code_revision": _sha256("code-r1"),
    }
    availability.run_kis_intraday_mtf_availability_receipt(**kwargs)
    current_catalogs = {
        **catalogs,
        "SPY/AMS/1m": _catalog(
            "SPY",
            "AMS",
            date(2026, 7, 20),
            dataset_hash_character="b",
        ),
    }

    with pytest.raises(ValueError, match="immutable artifact conflicts"):
        availability.run_kis_intraday_mtf_availability_receipt(**kwargs)


def test_runner_rejects_expected_source_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalogs = _catalogs(date(2026, 7, 20))

    def load_catalog(**kwargs: object) -> CatalogedBars:
        return catalogs[f"{kwargs['symbol']}/{kwargs['exchange']}/1m"]

    monkeypatch.setattr(
        availability,
        "load_verified_kis_paper_private_intraday_catalog",
        load_catalog,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="expected source identity changed"):
        availability.run_kis_intraday_mtf_availability_receipt(
            cache_root=tmp_path / "market-data",
            artifact_root=tmp_path / "artifacts",
            repo_root=repo_root,
            run_label="expected-r1",
            code_revision=_sha256("code-r1"),
            expected_dataset_hashes={
                "QQQ/NAS/1m": _sha256("wrong"),
                "SPY/AMS/1m": catalogs["SPY/AMS/1m"].dataset_hash,
            },
        )


def _catalogs(session_date: date) -> dict[str, CatalogedBars]:
    return {
        "QQQ/NAS/1m": _catalog("QQQ", "NAS", session_date),
        "SPY/AMS/1m": _catalog("SPY", "AMS", session_date),
    }


def _catalog(
    symbol: str,
    exchange: str,
    session_date: date,
    *,
    bars: tuple[Bar, ...] | None = None,
    dataset_hash_character: str = "a",
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
        dataset_hash="sha256:" + dataset_hash_character * 64,
        source_path=Path(f"D:/market-data/{symbol.lower()}.index.json"),
        bars=bars if bars is not None else _bars(symbol, session_date),
    )


def _bars(symbol: str, session_date: date) -> tuple[Bar, ...]:
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    return tuple(
        Bar(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.M1,
            start_ts=session.window.open_ts + timedelta(minutes=offset),
            open=Decimal("101.234") + Decimal(offset) / Decimal("10000"),
            high=Decimal("102.234") + Decimal(offset) / Decimal("10000"),
            low=Decimal("100.234") + Decimal(offset) / Decimal("10000"),
            close=Decimal("101.734") + Decimal(offset) / Decimal("10000"),
            volume=Decimal("99123"),
            complete=True,
        )
        for offset in range(availability.KIS_INTRADAY_MTF_AVAILABILITY_PREFIX_MINUTES)
    )


def _future_bar_in_prefix(bars: tuple[Bar, ...]) -> tuple[Bar, ...]:
    last = bars[-1]
    future = Bar(
        symbol=last.symbol,
        market=last.market,
        timeframe=Timeframe.M5,
        start_ts=last.start_ts,
        open=last.open,
        high=last.high,
        low=last.low,
        close=last.close,
        volume=last.volume,
        complete=True,
    )
    return bars[:-1] + (future,)


def _unsafe_catalog(symbol: str, exchange: str, bars: tuple[Bar, ...]) -> CatalogedBars:
    result = object.__new__(CatalogedBars)
    object.__setattr__(
        result,
        "dataset_id",
        f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
    )
    object.__setattr__(result, "dataset_hash", _sha256(f"unsafe-{symbol}"))
    object.__setattr__(result, "source_path", Path(f"D:/market-data/{symbol.lower()}.index.json"))
    object.__setattr__(result, "bars", bars)
    return result


def _sha256(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _forbid(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("network access is forbidden")


class _DenyEnvironment(dict[str, str]):
    def get(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("environment access is forbidden")
