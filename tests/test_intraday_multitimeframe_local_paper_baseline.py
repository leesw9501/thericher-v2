from __future__ import annotations

import csv
import gzip
import hashlib
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data import CatalogedBars, load_cataloged_yahoo_intraday_1m_bars
from thericher_v2.execution import LOCAL_PAPER_SOURCE, replay_local_paper_account
from thericher_v2.research.validation import (
    run_intraday_multitimeframe_local_paper_baseline,
)
from thericher_v2.state import EventStore


def test_multitimeframe_baseline_replays_isolated_local_paper_cells(tmp_path: Path) -> None:
    source = _attested_source(tmp_path, minutes=390)
    result = run_intraday_multitimeframe_local_paper_baseline(
        source,
        run_id="unit-multitimeframe",
        work_root=tmp_path / "external-evidence",
        repo_root=Path.cwd(),
    )

    assert result.dataset_id == source.dataset_id
    assert result.dataset_hash == source.dataset_hash
    assert [cell.timeframe for cell in result.cells] == [
        Timeframe.M1,
        Timeframe.M5,
        Timeframe.M10,
        Timeframe.H1,
        Timeframe.H3,
    ]
    assert all(cell.status == "completed" for cell in result.cells)
    assert all(cell.local_paper_fill_count == 2 for cell in result.cells)
    assert all(cell.all_fills_local_paper for cell in result.cells)
    assert all(cell.final_position == 0 for cell in result.cells)
    assert all(cell.replayed_final_position == 0 for cell in result.cells)

    for cell in result.cells:
        assert cell.work_dir is not None
        store = EventStore(cell.work_dir / "state.sqlite", cell.work_dir / "events.jsonl")
        events = list(store.iter_events())
        fills = [event for event in events if event.event_type == "fill"]
        assert len(fills) == 2
        assert all(event.payload["source"] == LOCAL_PAPER_SOURCE for event in fills)
        assert cell.decision_bar_end is not None
        assert fills[0].created_at == cell.decision_bar_end
        assert fills[1].created_at == cell.decision_bar_end + Timeframe.M1.duration
        assert store.replay().positions[("US", "AAA")] == 0
        assert replay_local_paper_account(store).quantity(market="US", symbol="AAA") == 0


def test_multitimeframe_baseline_is_deterministic_across_isolated_work_roots(
    tmp_path: Path,
) -> None:
    source = _attested_source(tmp_path, minutes=390)
    first = run_intraday_multitimeframe_local_paper_baseline(
        source,
        run_id="deterministic-multitimeframe",
        work_root=tmp_path / "external-one",
        repo_root=Path.cwd(),
    )
    second = run_intraday_multitimeframe_local_paper_baseline(
        source,
        run_id="deterministic-multitimeframe",
        work_root=tmp_path / "external-two",
        repo_root=Path.cwd(),
    )

    assert _cell_projection(first) == _cell_projection(second)
    for first_cell, second_cell in zip(first.cells, second.cells, strict=True):
        assert first_cell.work_dir is not None
        assert second_cell.work_dir is not None
        first_events = list(
            EventStore(
                first_cell.work_dir / "state.sqlite",
                first_cell.work_dir / "events.jsonl",
            ).iter_events()
        )
        second_events = list(
            EventStore(
                second_cell.work_dir / "state.sqlite",
                second_cell.work_dir / "events.jsonl",
            ).iter_events()
        )
        assert [event.to_record() for event in first_events] == [
            event.to_record() for event in second_events
        ]


def test_multitimeframe_baseline_skips_unexecutable_partial_timeframes(tmp_path: Path) -> None:
    source = _attested_source(tmp_path, minutes=92, excluded_indices={90})
    result = run_intraday_multitimeframe_local_paper_baseline(source)
    cells = {cell.timeframe: cell for cell in result.cells}

    assert cells[Timeframe.M1].status == "completed"
    assert cells[Timeframe.M5].status == "completed"
    assert cells[Timeframe.M10].status == "completed"
    assert cells[Timeframe.H1].status == "skipped"
    assert cells[Timeframe.H1].skip_reason == "no_completed_bar_with_two_following_1m_bars"
    assert cells[Timeframe.H1].work_dir is None
    assert cells[Timeframe.H3].status == "skipped"
    assert cells[Timeframe.H3].skip_reason == "no_complete_resampled_bars"


def test_multitimeframe_baseline_is_offline_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _attested_source(tmp_path, minutes=390)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("multitimeframe baseline must stay offline")

    original_open = Path.open
    original_read_text = Path.read_text

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.lower().startswith(".env"):
            raise AssertionError("multitimeframe baseline must not read credentials")
        return original_open(path, *args, **kwargs)

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.lower().startswith(".env"):
            raise AssertionError("multitimeframe baseline must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "open", guard_open)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_intraday_multitimeframe_local_paper_baseline(source)

    assert all(cell.status == "completed" for cell in result.cells)
    assert all(cell.all_fills_local_paper for cell in result.cells)


def test_multitimeframe_baseline_requires_cataloged_bars_and_external_work_root(
    tmp_path: Path,
) -> None:
    source = _attested_source(tmp_path, minutes=390)

    with pytest.raises(TypeError, match="Data-owned CatalogedBars"):
        run_intraday_multitimeframe_local_paper_baseline(())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_intraday_multitimeframe_local_paper_baseline(
            source,
            run_id="repo-work-root",
            work_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
        )


def _attested_source(
    tmp_path: Path,
    *,
    minutes: int,
    excluded_indices: set[int] | None = None,
) -> CatalogedBars:
    path = tmp_path / f"snapshot-{minutes}" / "ohlcv_1m.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 2, 13, 30, tzinfo=UTC)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "symbol",
                "timestamp_utc",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ),
        )
        writer.writeheader()
        for index in range(minutes):
            if excluded_indices is not None and index in excluded_indices:
                continue
            open_price = Decimal("100") + Decimal(index) / Decimal("100")
            close = open_price + Decimal("0.01")
            writer.writerow(
                {
                    "symbol": "AAA",
                    "timestamp_utc": (start + timedelta(minutes=index)).isoformat(),
                    "open": str(open_price),
                    "high": str(close + Decimal("0.01")),
                    "low": str(open_price - Decimal("0.01")),
                    "close": str(close),
                    "volume": str(1000 + index),
                }
            )
    expected_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return load_cataloged_yahoo_intraday_1m_bars(
        path,
        dataset_id=f"unit.yahoo.1m.snapshot={minutes}",
        expected_dataset_hash=expected_hash,
        symbol="AAA",
        max_bars=minutes,
    )


def _cell_projection(result) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            cell.timeframe,
            cell.resampled_bar_count,
            cell.status,
            cell.skip_reason,
            cell.decision_bar_end,
            cell.decision_id,
            cell.local_paper_fill_count,
            cell.all_fills_local_paper,
            cell.final_position,
            cell.replayed_final_position,
        )
        for cell in result.cells
    )
