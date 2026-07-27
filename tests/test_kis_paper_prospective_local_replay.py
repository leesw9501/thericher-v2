from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.research.kis_paper_prospective_local_replay import (
    replay_kis_paper_prospective_local_paper,
)


def test_replay_fills_an_enter_with_only_local_paper_evidence(tmp_path: Path) -> None:
    bars = _bars(2)
    result = replay_kis_paper_prospective_local_paper(
        _proposal(action="enter", bars=bars),
        signal_bar=bars[0],
        replay_bar=bars[1],
        state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
    )

    assert result.status == "filled"
    assert result.fill_source == "local_paper"
    assert result.event_log_sha256 is not None
    payload = result.safe_payload()
    assert payload["fill_source"] == "local_paper"
    assert "price" not in json.dumps(payload)
    assert "100" not in json.dumps(payload)


def test_replay_recovers_the_same_local_fill_without_appending_another(tmp_path: Path) -> None:
    bars = _bars(2)
    root = tmp_path / "runtime"
    kwargs = {
        "proposal": _proposal(action="enter", bars=bars),
        "signal_bar": bars[0],
        "replay_bar": bars[1],
        "state_root": root,
        "repo_root": tmp_path / "repo",
    }

    first = replay_kis_paper_prospective_local_paper(**kwargs)
    recovered = replay_kis_paper_prospective_local_paper(**kwargs)

    assert first.status == recovered.status == "filled"
    assert first.event_log_sha256 == recovered.event_log_sha256
    event_lines = (root / "qqq-prospective-local-paper-v1.jsonl").read_text().splitlines()
    assert sum('"event_type":"fill"' in line for line in event_lines) == 1


@pytest.mark.parametrize("action", ("hold", "abstain"))
def test_replay_keeps_non_delta_actions_as_no_intent(action: str, tmp_path: Path) -> None:
    bars = _bars(2)
    result = replay_kis_paper_prospective_local_paper(
        _proposal(action=action, bars=bars),
        signal_bar=bars[0],
        replay_bar=bars[1],
        state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
    )

    assert result.status == "no_intent"
    assert result.fill_source is None
    assert result.event_log_sha256 is None


def test_replay_maps_reduction_and_exit_from_a_replayable_local_position(tmp_path: Path) -> None:
    bars = _bars(6)
    root = tmp_path / "runtime"
    repository = tmp_path / "repo"
    entered = replay_kis_paper_prospective_local_paper(
        _proposal(action="enter", bars=bars[:2]),
        signal_bar=bars[0],
        replay_bar=bars[1],
        state_root=root,
        repo_root=repository,
    )
    reduced = replay_kis_paper_prospective_local_paper(
        _proposal(action="reduce", bars=bars[2:4]),
        signal_bar=bars[2],
        replay_bar=bars[3],
        state_root=root,
        repo_root=repository,
    )
    exited = replay_kis_paper_prospective_local_paper(
        _proposal(action="exit", bars=bars[4:6]),
        signal_bar=bars[4],
        replay_bar=bars[5],
        state_root=root,
        repo_root=repository,
    )

    assert entered.status == reduced.status == exited.status == "filled"
    assert entered.fill_source == reduced.fill_source == exited.fill_source == "local_paper"


def test_replay_rejects_a_claimed_position_without_a_replayable_local_position(
    tmp_path: Path,
) -> None:
    bars = _bars(2)
    result = replay_kis_paper_prospective_local_paper(
        _proposal(action="exit", bars=bars),
        signal_bar=bars[0],
        replay_bar=bars[1],
        state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
        current_quantity=Decimal("1"),
    )

    assert result.status == "no_intent"
    assert result.reason == "local_paper_position_mismatch"


def test_replay_does_not_fabricate_a_fill_without_the_next_completed_bar(tmp_path: Path) -> None:
    bars = _bars(1)
    result = replay_kis_paper_prospective_local_paper(
        _proposal(action="enter", bars=bars),
        signal_bar=bars[0],
        replay_bar=None,
        state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
    )

    assert result.status == "awaiting_replay_bar"
    assert result.fill_source is None


def test_replay_is_network_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bars = _bars(2)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective local replay must stay offline")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == ".env":
            raise AssertionError("prospective local replay must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = replay_kis_paper_prospective_local_paper(
        _proposal(action="enter", bars=bars),
        signal_bar=bars[0],
        replay_bar=bars[1],
        state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
    )

    assert result.status == "filled"


def test_replay_rejects_a_state_root_inside_the_repository(tmp_path: Path) -> None:
    bars = _bars(2)
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        replay_kis_paper_prospective_local_paper(
            _proposal(action="enter", bars=bars),
            signal_bar=bars[0],
            replay_bar=bars[1],
            state_root=repository / "runtime",
            repo_root=repository,
        )


def test_replay_accepts_only_a_docker_model_artifact_mount_inside_the_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bars = _bars(2)
    repository = tmp_path / "repo"
    artifacts = repository / "model_artifacts"
    original_is_mount = Path.is_mount

    def is_mount(path: Path) -> bool:
        return path.resolve() == artifacts.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_mount)
    result = replay_kis_paper_prospective_local_paper(
        _proposal(action="enter", bars=bars),
        signal_bar=bars[0],
        replay_bar=bars[1],
        state_root=artifacts / "_control" / "local-paper",
        repo_root=repository,
    )

    assert result.status == "filled"
    assert result.fill_source == "local_paper"


def _proposal(*, action: str, bars: list[Bar]) -> TargetExposureProposal:
    exposure = {
        "enter": Decimal("0.05"),
        "hold": Decimal("0.05"),
        "reduce": Decimal("0.025"),
        "exit": Decimal("0"),
        "abstain": Decimal("0"),
    }[action]
    return TargetExposureProposal(
        proposal_id=f"prospective-{action}",
        symbol="QQQ",
        market="US",
        action=action,  # type: ignore[arg-type]
        target_exposure=exposure,
        confidence=Decimal("0.55") if action != "abstain" else Decimal("0"),
        feature_schema_id="unit-prospective-baseline",
        input_status="ready",
        decided_at=bars[0].end_ts,
        valid_until=bars[0].end_ts + timedelta(minutes=10),
        feature_window_end=bars[0].end_ts,
        reason=f"unit_{action}",
    )


def _bars(count: int) -> list[Bar]:
    start = datetime(2026, 7, 27, 14, 30, tzinfo=UTC)
    bars: list[Bar] = []
    for index in range(count):
        open_price = Decimal("100") + Decimal(index)
        bars.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start + timedelta(minutes=index),
                open=open_price,
                high=open_price + Decimal("1"),
                low=open_price - Decimal("1"),
                close=open_price + Decimal("0.5"),
                volume=Decimal("1000"),
                complete=True,
            )
        )
    return bars
