from __future__ import annotations

import csv
import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CSV_FIELDS, bar_to_record
from thericher_v2.research import firstrate_m5_mean_reversion_after_cost_control as control
from thericher_v2.research.firstrate_5m_after_cost_control import FirstRateM5Sample


def test_completed_bar_rsi_uses_frozen_thresholds_and_terminal_flatten() -> None:
    downward = _m5_bars(start_close=Decimal("200"), step=Decimal("-1"))
    upward = _m5_bars(start_close=Decimal("100"), step=Decimal("1"))

    downward_model = _rule_model(downward)
    upward_model = _rule_model(upward)
    terminal_model = _rule_model(downward, terminal=True)

    entry = downward_model.predict(list(downward))
    exit = upward_model.predict(list(upward))
    terminal = terminal_model.predict(list(downward))

    assert entry.signal.action == "buy"
    assert entry.signal.reason == "firstrate_m5_completed_wilder_rsi14_le_30_entry"
    assert entry.feature_window_end == downward[-1].end_ts
    assert exit.signal.action == "sell"
    assert exit.signal.reason == "firstrate_m5_completed_wilder_rsi14_ge_50_exit"
    assert terminal.signal.action == "sell"
    assert terminal.signal.reason == "firstrate_m5_predeclared_terminal_flatten"


def test_frozen_rule_uses_local_paper_only_and_external_source_safe_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root, artifact_root = _install_source(tmp_path, minute_count=3_000)

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FirstRate mean-reversion rule must not access the network")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    run = control.run_firstrate_m5_mean_reversion_after_cost_control(
        run_label="unit-r1",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run.status == "complete"
    assert run.summary_path is not None
    receipt = control.validate_firstrate_m5_mean_reversion_after_cost_control(
        run_label="unit-r1",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )

    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert receipt.source_reattached is True
    assert summary["classification"] == receipt.classification
    assert summary["rule"] == {
        "candidate_id": "wilder_rsi14_30_50",
        "rsi_method": "wilder",
        "rsi_period_bars": 14,
        "entry_threshold": "30",
        "exit_threshold": "50",
        "calibration_free": True,
        "training_started": False,
    }
    assert summary["gpu_used"] is False
    assert summary["network_access"] is False
    assert summary["credentials_read"] is False
    assert summary["kis_or_broker_called"] is False
    assert summary["raw_market_data_written"] is False
    assert summary["raw_predictions_written"] is False
    assert summary["raw_local_paper_events_written"] is False
    assert len(summary["replay_cells"]) == 12
    assert {cell["fill_source"] for cell in summary["replay_cells"]} == {"local_paper"}
    assert all(cell["all_fills_local_paper"] for cell in summary["replay_cells"])
    assert all(cell["replayable"] for cell in summary["replay_cells"])
    assert all(cell["terminal_flat"] for cell in summary["replay_cells"])
    assert all(
        cell["entry_fill_count"] + cell["exit_fill_count"]
        == cell["local_paper_fill_count"]
        for cell in summary["replay_cells"]
    )
    assert not list(run.output_dir.rglob("events.jsonl"))
    assert "source_path" not in json.dumps(summary)
    assert "history_start" not in json.dumps(summary)
    _assert_source_safe(summary)
    assert run.output_dir.is_relative_to(artifact_root)
    assert not run.output_dir.is_relative_to(Path(__file__).resolve().parents[1])


def test_rule_is_deterministic_across_distinct_external_run_labels(tmp_path: Path) -> None:
    market_root, artifact_root = _install_source(tmp_path, minute_count=3_000)
    first = control.run_firstrate_m5_mean_reversion_after_cost_control(
        run_label="deterministic-r1",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )
    second = control.run_firstrate_m5_mean_reversion_after_cost_control(
        run_label="deterministic-r2",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert first.summary_path is not None
    assert second.summary_path is not None
    first_summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    second_summary = json.loads(second.summary_path.read_text(encoding="utf-8"))
    assert first.classification == second.classification
    assert first_summary["precommit_hash"] == second_summary["precommit_hash"]
    assert first_summary["replay_cells"] == second_summary["replay_cells"]


def test_geometry_failure_returns_input_unavailable_before_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root, artifact_root = _install_source(tmp_path, minute_count=350)

    def unexpected_replay(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("rule replay must not run when frozen geometry is unavailable")

    monkeypatch.setattr(control, "_run_replay_matrix", unexpected_replay)
    run = control.run_firstrate_m5_mean_reversion_after_cost_control(
        run_label="geometry-r1",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run.status == "input_unavailable"
    assert run.precommit_path is None
    assert run.summary_path is None
    assert run.input_unavailable_path is not None
    unavailable = json.loads(run.input_unavailable_path.read_text(encoding="utf-8"))
    assert unavailable["training_started"] is False
    assert unavailable["gpu_used"] is False
    assert unavailable["kis_or_broker_called"] is False
    assert unavailable["raw_market_data_written"] is False


def test_validation_rejects_changed_canonical_source(tmp_path: Path) -> None:
    market_root, artifact_root = _install_source(tmp_path, minute_count=3_000)
    run = control.run_firstrate_m5_mean_reversion_after_cost_control(
        run_label="changed-source-r1",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )
    assert run.status == "complete"
    source_path = market_root / "us_equities/firstrate_free_intraday/canonical/SPY_1m.csv"
    source_path.write_text(source_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="canonical CSV hash"):
        control.validate_firstrate_m5_mean_reversion_after_cost_control(
            run_label="changed-source-r1",
            market_data_root=market_root,
            artifact_root=artifact_root,
            repo_root=Path(__file__).resolve().parents[1],
        )


def test_rule_replays_only_contiguous_5m_chunks_across_source_gaps(tmp_path: Path) -> None:
    market_root, artifact_root = _install_source(
        tmp_path,
        minute_count=3_900,
        session_gap_after_minutes=390,
    )

    run = control.run_firstrate_m5_mean_reversion_after_cost_control(
        run_label="gapped-source-r1",
        market_data_root=market_root,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run.status == "complete"
    assert run.summary_path is not None
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert all(cell["terminal_flat"] for cell in summary["replay_cells"])
    assert all(cell["replayable"] for cell in summary["replay_cells"])


def test_rule_rejects_git_workspace_artifact_root(tmp_path: Path) -> None:
    market_root, _artifact_root = _install_source(tmp_path, minute_count=3_000)

    with pytest.raises(ValueError, match="artifact_root must stay outside Git"):
        control.run_firstrate_m5_mean_reversion_after_cost_control(
            run_label="repo-root-r1",
            market_data_root=market_root,
            artifact_root=Path(__file__).resolve().parents[1],
            repo_root=Path(__file__).resolve().parents[1],
        )


def test_module_has_no_kis_network_gpu_or_credential_route() -> None:
    source = Path(control.__file__).read_text(encoding="utf-8")

    assert "KIS_" not in source
    assert "requests" not in source
    assert "socket" not in source
    assert "torch" not in source
    assert "subprocess" not in source
    assert "environ" not in source


def _rule_model(
    bars: tuple[Bar, ...],
    *,
    terminal: bool = False,
) -> control._RsiDecisionModel:
    latest = bars[-1]
    sample = FirstRateM5Sample(
        symbol=latest.symbol,
        history_start=bars[0].start_ts,
        decision_start=latest.start_ts,
        decision_end=latest.end_ts,
        target_start=latest.end_ts,
        exit_start=latest.end_ts + Timeframe.M5.duration,
        features=(0.0,) * 60,
        label=0,
    )
    return control._RsiDecisionModel(
        symbol=latest.symbol,
        candidate_id="wilder_rsi14_30_50",
        samples_by_decision_start={sample.decision_start: sample},
        terminal_signal_start=sample.decision_start if terminal else None,
    )


def _m5_bars(*, start_close: Decimal, step: Decimal) -> tuple[Bar, ...]:
    start = datetime(2026, 1, 2, tzinfo=UTC)
    return tuple(
        Bar(
            symbol="SPY",
            market="US",
            timeframe=Timeframe.M5,
            start_ts=start + index * Timeframe.M5.duration,
            open=start_close + step * Decimal(index),
            high=start_close + step * Decimal(index) + Decimal("0.01"),
            low=start_close + step * Decimal(index) - Decimal("0.01"),
            close=start_close + step * Decimal(index),
            volume=Decimal("1000"),
            complete=True,
        )
        for index in range(60)
    )


def _install_source(
    tmp_path: Path,
    *,
    minute_count: int,
    session_gap_after_minutes: int | None = None,
) -> tuple[Path, Path]:
    market_root = tmp_path / "market-data"
    artifact_root = tmp_path / "model-artifacts"
    canonical_root = market_root / "us_equities/firstrate_free_intraday/canonical"
    canonical_root.mkdir(parents=True)
    artifact_root.mkdir(parents=True)
    normalizations: list[dict[str, object]] = []
    for symbol, offset in (("SPY", Decimal("0")), ("QQQ", Decimal("25"))):
        bars = _bars(
            symbol=symbol,
            offset=offset,
            minute_count=minute_count,
            session_gap_after_minutes=session_gap_after_minutes,
        )
        path = canonical_root / f"{symbol}_1m.csv"
        _write_canonical_csv(path, bars)
        normalizations.append(
            {
                "symbol": symbol,
                "market": "US",
                "timeframe": "1m",
                "canonical_market_data_relative_path": (
                    f"us_equities/firstrate_free_intraday/canonical/{symbol}_1m.csv"
                ),
                "canonical_sha256": _sha256(path.read_bytes()),
                "bar_count": len(bars),
                "emitted_timestamp_set_sha256": _timestamp_hash(
                    tuple(bar.start_ts for bar in bars)
                ),
                "timestamp_set_equal": True,
            }
        )
    receipt_path = artifact_root / (
        "data-receipts/firstrate-free-intraday/"
        "firstrate-free-intraday-source-local-normalization-v1.json"
    )
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "firstrate-free-intraday-normalization-receipt-v1",
                "status": "completed",
                "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
                "normalizations": normalizations,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return market_root, artifact_root


def _bars(
    *,
    symbol: str,
    offset: Decimal,
    minute_count: int,
    session_gap_after_minutes: int | None = None,
) -> list[Bar]:
    start = datetime(2026, 1, 2, tzinfo=UTC)
    bars: list[Bar] = []
    for index in range(minute_count):
        gap_count = (
            0 if session_gap_after_minutes is None else index // session_gap_after_minutes
        )
        timestamp = start + timedelta(minutes=index + gap_count * 900)
        open_price = Decimal("100") + offset + Decimal(index) / Decimal("500")
        pattern = Decimal((index * 17) % 11 - 5) / Decimal("1000")
        close_price = open_price * (Decimal("1") + pattern)
        bars.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.M1,
                start_ts=timestamp,
                open=open_price,
                high=max(open_price, close_price) + Decimal("0.01"),
                low=min(open_price, close_price) - Decimal("0.01"),
                close=close_price,
                volume=Decimal("1000"),
                complete=True,
            )
        )
    return bars


def _write_canonical_csv(path: Path, bars: list[Bar]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(bar_to_record(bar) for bar in bars)


def _timestamp_hash(values: tuple[datetime, ...]) -> str:
    return _sha256("".join(f"{value.isoformat()}\n" for value in values).encode("utf-8"))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _assert_source_safe(value: object) -> None:
    if isinstance(value, dict):
        forbidden = {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "features",
            "labels",
            "predictions",
        }
        assert not forbidden.intersection(value)
        for nested in value.values():
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)
