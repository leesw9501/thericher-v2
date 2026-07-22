from __future__ import annotations

from pathlib import Path

from thericher_v2.execution.emergency import PaperExecutionControlStore


def test_directional_controls_persist_without_changing_the_other_direction(tmp_path: Path) -> None:
    path = tmp_path / "paper_execution_control.json"
    store = PaperExecutionControlStore(path)

    assert store.read().pause_buys is False
    assert store.read().pause_sells is False

    buy_paused = store.set_pause_buys(True)
    assert buy_paused.pause_buys is True
    assert buy_paused.pause_sells is False
    assert buy_paused.reason == "dashboard_pause_buys"

    sell_paused = store.set_pause_sells(True)
    assert sell_paused.pause_buys is True
    assert sell_paused.pause_sells is True
    assert sell_paused.reason == "dashboard_pause_sells"

    resumed_buy = PaperExecutionControlStore(path).set_pause_buys(False)
    assert resumed_buy.pause_buys is False
    assert resumed_buy.pause_sells is True
    assert resumed_buy.reason == "dashboard_resume_buys"


def test_malformed_directional_control_fails_closed_without_using_an_external_service(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper_execution_control.json"
    path.write_text('{"pause_buys":"no"}', encoding="utf-8")

    state = PaperExecutionControlStore(path).read()

    assert state.pause_buys is True
    assert state.pause_sells is True
    assert state.reason == "execution_control_unreadable_or_malformed"
