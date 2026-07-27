from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_intraday_head_schedule.ps1"
)


def test_head_schedule_dispatcher_persists_terminal_recovery_evidence() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    collection_call = ' -Service "kis-paper-intraday-head"'
    prospective_session_call = ' -Service "kis-paper-prospective-qqq-session"'
    prospective_validation_call = ' -Service "kis-paper-prospective-qqq-validation"'
    observation_call = ' -Service "kis-paper-intraday-observation"'
    receipt_call = ' -Service "kis-paper-intraday-head-receipt"'
    assert "--profile kis-paper-intraday-head" in source
    assert "run --rm --no-deps --pull never $Service" in source
    assert collection_call in source
    assert prospective_session_call in source
    assert prospective_validation_call in source
    assert observation_call in source
    assert source.index(collection_call) < source.index(prospective_session_call)
    assert source.index(prospective_session_call) < source.index(prospective_validation_call)
    assert source.index(prospective_validation_call) < source.index(observation_call)
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
    assert '$prospectiveLoopStatus = "embedded"' in source
    assert "kis-paper-prospective-loop" not in source
    assert "prospective_session_exit_code" in source
    assert "prospective_session_status" in source
    assert "prospective_validation_exit_code" in source
    assert "prospective_validation_status" in source
    assert "observation_exit_code" in source
    assert "observation_status" in source
    assert "Get-ProfileStatus" in source
    assert "2>&1" in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert "no_intent\", \"canary_completed" in source
    assert "canary_completed" in source
    assert "kis_paper_prospective_qqq_validation" in source
    assert '$prospectiveValidationStatus = "validated"' in source
    assert "CommandOverride" in source
    assert "pending\", \"unavailable\", \"complete" in source
    assert "Test-ProspectiveObservationPairReady" in source
    assert "precommit.json" in source
    assert "planning-receipt.json" in source
    assert source.index("Test-ProspectiveObservationPairReady") < source.index(observation_call)


def test_head_schedule_dispatcher_has_no_secret_or_live_route_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source
