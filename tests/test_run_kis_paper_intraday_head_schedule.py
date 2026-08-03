from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_intraday_head_schedule.ps1"
)


def test_head_schedule_dispatcher_persists_terminal_recovery_evidence() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    collection_call = ' -Service "kis-paper-intraday-head"'
    spy_cycle_call = ' -Service "kis-paper-prospective-spy-cycle"'
    capture_call = ' -Service "profiled-mtf-forward-capture-cycle"'
    observation_call = ' -Service "kis-paper-intraday-pair-observation"'
    receipt_call = ' -Service "kis-paper-intraday-head-receipt"'
    assert "--profile kis-paper-intraday-head" in source
    assert "run --rm --no-deps --pull never $Service" in source
    assert collection_call in source
    assert spy_cycle_call in source
    assert capture_call in source
    assert observation_call in source
    assert source.index(collection_call) < source.index(spy_cycle_call)
    assert source.index(spy_cycle_call) < source.index(capture_call)
    assert source.index(collection_call) < source.index(observation_call)
    assert source.index(collection_call) < source.index(capture_call)
    assert source.index(capture_call) < source.index(observation_call)
    assert source.index(observation_call) < source.index(receipt_call)
    assert "Get-DispatchTerminalExitCode" in source
    assert "New-ScheduleRunId" in source
    assert "--observed-at" in source
    assert "kis_paper_intraday_head_schedule_receipt" in source
    assert "schedule_receipt_exit_code" in source
    assert "schedule_receipt_status" in source
    assert "terminal_exit_code" in source
    assert "exit $terminalExitCode" in source
    assert "exit $collectionExitCode" not in source
    assert "prospective_loop_exit_code" in source
    assert "prospective_loop_status" in source
    assert '$prospectiveLoopStatus = "not_applicable"' in source
    assert "kis-paper-prospective-loop" not in source
    assert "prospective_session_exit_code" in source
    assert "prospective_session_status" in source
    assert "prospective_validation_exit_code" in source
    assert "prospective_validation_status" in source
    assert "prospective_spy_cycle_exit_code" in source
    assert "prospective_spy_cycle_status" in source
    assert "$prospectiveSpyCycleStatus = \"not_applicable\"" in source
    assert "observation_exit_code" in source
    assert "observation_status" in source
    assert "capture_cycle_exit_code" in source
    assert "capture_cycle_status" in source
    assert '"scripts/run_profiled_mtf_forward_capture_cycle.py"' in source
    assert '"--observed-at",' in source
    assert "$scheduleObservedAtMarker" in source
    assert source.count(collection_call) == 1
    assert "if ($collectionExitCode -eq 0)" in source
    assert "Get-ProfileStatus" in source
    assert "2>&1" in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert '"observed"' in source
    assert '"not_observed"' in source
    assert "kis-paper-prospective-qqq-session" not in source
    assert "kis-paper-prospective-qqq-validation" not in source
    assert "kis-paper-intraday-observation" not in source


def test_head_schedule_dispatcher_has_no_secret_or_live_route_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source
