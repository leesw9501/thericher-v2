import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_intraday_head_schedule.ps1"
)


def test_head_schedule_dispatcher_persists_terminal_recovery_evidence() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    collection_call = ' -Service "kis-paper-intraday-head"'
    timing_probe_call = ' -Service "kis-paper-prospective-spy-timing-probe"'
    spy_cycle_call = ' -Service "kis-paper-prospective-spy-cycle"'
    qqq_session_call = ' -Service "kis-paper-prospective-qqq-session"'
    qqq_validation_call = ' -Service "kis-paper-prospective-qqq-validation"'
    capture_call = ' -Service "profiled-mtf-forward-capture-cycle"'
    observation_call = ' -Service "kis-paper-intraday-pair-observation"'
    receipt_call = ' -Service "kis-paper-intraday-head-receipt"'
    assert "--profile kis-paper-intraday-head" in source
    assert "run --rm --no-deps --pull never $Service" in source
    assert collection_call in source
    assert timing_probe_call in source
    assert spy_cycle_call in source
    assert qqq_session_call in source
    assert qqq_validation_call in source
    assert capture_call in source
    assert observation_call in source
    assert source.index(collection_call) < source.index(qqq_session_call)
    assert source.index(qqq_session_call) < source.index(qqq_validation_call)
    assert source.index(qqq_validation_call) < source.index(timing_probe_call)
    assert source.index(collection_call) < source.index(timing_probe_call)
    assert source.index(timing_probe_call) < source.index(spy_cycle_call)
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
    assert '$prospectiveLoopStatus = "embedded"' in source
    assert "kis-paper-prospective-loop" not in source
    assert "prospective_session_exit_code" in source
    assert "prospective_session_status" in source
    assert "prospective_validation_exit_code" in source
    assert "prospective_validation_status" in source
    assert "prospective_spy_cycle_exit_code" in source
    assert "prospective_spy_cycle_status" in source
    assert "$prospectiveSpyCycleStatus = \"not_applicable\"" in source
    assert "$collectionStartedAt = (Get-Date).ToUniversalTime()" in source
    assert "$collectionReturnedAt = (Get-Date).ToUniversalTime()" in source
    assert "kis_paper_intraday_session_capture" in source
    assert "--scheduler-started-at" in source
    assert "--collector-returned-at" in source
    assert "prospective_spy_timing" not in source.split("$scheduleReceiptCommand", maxsplit=1)[1]
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
    assert "kis-paper-intraday-observation" not in source


def test_head_schedule_runs_qqq_route_only_after_collection_and_revalidates_it() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    collection_guard = source.index("if ($collectionExitCode -eq 0)")
    qqq_session = source.index(' -Service "kis-paper-prospective-qqq-session"')
    qqq_validation = source.index(' -Service "kis-paper-prospective-qqq-validation"')
    timing_probe = source.index(' -Service "kis-paper-prospective-spy-timing-probe"')
    qqq_block = source[collection_guard:timing_probe]

    assert collection_guard < qqq_session < qqq_validation < timing_probe
    assert '$prospectiveLoopStatus = "embedded"' in qqq_block
    assert "Get-SafeProfileSessionId" in qqq_block
    assert '"kis_paper_prospective_qqq_session"' in qqq_block
    assert '"kis_paper_prospective_qqq_validation"' in qqq_block
    assert '"--session-id",' in qqq_block
    assert "$prospectiveSessionId," in qqq_block
    assert '$prospectiveValidationStatus = "validated"' in qqq_block
    assert '"--execute"' not in qqq_block
    assert '"--cancel-after-submit"' not in qqq_block


@pytest.mark.skipif(os.name != "nt", reason="the dispatcher is a Windows PowerShell task")
def test_head_schedule_dispatches_qqq_before_slower_observers(tmp_path: Path) -> None:
    log_path = tmp_path / "fake-docker-services.log"
    project_root = SCRIPT.parents[1]
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _fake_dispatch_command(
                script_path=SCRIPT,
                project_root=project_root,
                log_path=log_path,
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert log_path.read_text(encoding="ascii").splitlines() == [
        "kis-paper-intraday-head",
        "kis-paper-prospective-qqq-session",
        "kis-paper-prospective-qqq-validation",
        "kis-paper-prospective-spy-timing-probe",
        "kis-paper-prospective-spy-cycle",
        "kis-paper-qqq-intraday-head-readiness",
        "profiled-mtf-forward-capture-cycle",
        "kis-paper-intraday-pair-observation",
        "kis-paper-intraday-head-receipt",
    ]


def _fake_dispatch_command(*, script_path: Path, project_root: Path, log_path: Path) -> str:
    escaped_script = str(script_path).replace("'", "''")
    escaped_root = str(project_root).replace("'", "''")
    escaped_log = str(log_path).replace("'", "''")
    return f"""
$ErrorActionPreference = 'Stop'
$env:THERICHER_FAKE_DOCKER_LOG = '{escaped_log}'
function docker.exe {{
    $dockerArgs = @($args)
    $knownServices = @(
        'kis-paper-intraday-head',
        'kis-paper-prospective-qqq-session',
        'kis-paper-prospective-qqq-validation',
        'kis-paper-prospective-spy-timing-probe',
        'kis-paper-prospective-spy-cycle',
        'kis-paper-qqq-intraday-head-readiness',
        'profiled-mtf-forward-capture-cycle',
        'kis-paper-intraday-pair-observation',
        'kis-paper-intraday-head-receipt'
    )
    $service = $null
    for ($index = $dockerArgs.Count - 1; $index -ge 0; $index--) {{
        $candidate = [string]$dockerArgs[$index]
        if ($candidate -in $knownServices) {{
            $service = $candidate
            break
        }}
    }}
    if ($null -eq $service) {{
        throw "fake docker could not identify exactly one service: $($dockerArgs -join ' ')"
    }}
    Add-Content -LiteralPath $env:THERICHER_FAKE_DOCKER_LOG -Value $service -Encoding ascii
    switch ($service) {{
        'kis-paper-intraday-head' {{
            Write-Output '{{"kind":"kis_paper_intraday_session_capture","targets":[]}}'
        }}
        'kis-paper-prospective-qqq-session' {{
            Write-Output (
                '{{"kind":"kis_paper_prospective_qqq_session","status":"no_intent",' +
                '"session_id":"qqq-unit"}}'
            )
        }}
        'kis-paper-prospective-qqq-validation' {{
            Write-Output (
                '{{"kind":"kis_paper_prospective_qqq_validation","status":"validated",' +
                '"session_id":"qqq-unit"}}'
            )
        }}
        'kis-paper-prospective-spy-cycle' {{
            Write-Output (
                '{{"kind":"kis_paper_prospective_spy_cycle","status":"no_intent",' +
                '"cycle_id":"spy-unit","execution":{{"canary_run_id":null}}}}'
            )
        }}
        'profiled-mtf-forward-capture-cycle' {{
            Write-Output (
                '{{"kind":"profiled-mtf-forward-capture-cycle-v1",' +
                '"status":"outside_cycle_slot"}}'
            )
        }}
        'kis-paper-intraday-pair-observation' {{
            Write-Output (
                '{{"kind":"kis_qqq_spy_mtf_prospective_observation",' +
                '"status":"not_observed"}}'
            )
        }}
        'kis-paper-intraday-head-receipt' {{
            Write-Output (
                '{{"kind":"kis_paper_intraday_head_schedule_receipt","status":"complete",' +
                '"terminal":{{"status":"complete","scheduler_exit_code":0}}}}'
            )
        }}
        default {{
            Write-Output '{{}}'
        }}
    }}
    $global:LASTEXITCODE = 0
}}
& '{escaped_script}' -ProjectRoot '{escaped_root}'
exit $LASTEXITCODE
"""


def test_head_schedule_dispatcher_has_no_secret_or_live_route_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source


def test_head_schedule_readiness_observer_is_ordered_and_failure_isolated() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    collection_call = ' -Service "kis-paper-intraday-head"'
    readiness_call = ' -Service "kis-paper-qqq-intraday-head-readiness"'
    spy_cycle_call = ' -Service "kis-paper-prospective-spy-cycle"'
    capture_cycle_call = ' -Service "profiled-mtf-forward-capture-cycle"'
    pair_observation_call = ' -Service "kis-paper-intraday-pair-observation"'
    spy_cycle_start = source.index(spy_cycle_call)
    spy_outcome_marker = (
        "$prospectiveSpyCanaryRunId = $prospectiveSpyCyclePayload.execution.canary_run_id"
    )
    spy_outcome_capture_start = source.index(spy_outcome_marker, spy_cycle_start)
    readiness_command_start = source.index("$qqqReadinessObserverCommand = @(")
    readiness_call_start = source.index(readiness_call, readiness_command_start)
    capture_cycle_start = source.index(capture_cycle_call, readiness_call_start)
    readiness_invoke_start = source.rfind(
        "$null = Invoke-HeadProfileService", 0, readiness_call_start
    )
    readiness_command = source[readiness_command_start:readiness_call_start]
    readiness_call_block = source[readiness_invoke_start:capture_cycle_start]
    between_spy_capture_and_readiness = source[
        spy_outcome_capture_start + len(spy_outcome_marker) : readiness_command_start
    ]

    assert source.index(collection_call) < spy_cycle_start < spy_outcome_capture_start
    assert spy_outcome_capture_start < readiness_call_start < capture_cycle_start
    assert readiness_call_start < source.index(pair_observation_call)
    assert "Invoke-HeadProfileService" not in between_spy_capture_and_readiness
    assert readiness_call_block.startswith("$null = Invoke-HeadProfileService")
    assert readiness_call in readiness_call_block
    assert "-CommandOverride $qqqReadinessObserverCommand" in readiness_call_block
    assert ".ExitCode" not in readiness_call_block
    assert ".Output" not in readiness_call_block
    assert "Get-Profile" not in readiness_call_block
    assert '"scripts/observe_kis_paper_qqq_intraday_head_readiness.py",' in readiness_command
    assert '"--collection-started-at",' in readiness_command
    assert "$collectionStartedAtMarker," in readiness_command
    assert '"--collector-returned-at",' in readiness_command
    assert "$collectionReturnedAtMarker," in readiness_command
    assert '"--cache-root",' in readiness_command
    assert '"/app/market_data",' in readiness_command
    assert '"--artifact-root",' in readiness_command
    assert '"/app/model_artifacts",' in readiness_command
    assert '"--repository-root",' in readiness_command
    assert '"/app"' in readiness_command
    assert "--execute" not in readiness_command
    assert "--cancel-after-submit" not in readiness_command
    assert "thericher_v2.execution" not in readiness_command
    assert "--state-root" not in readiness_command
    assert "--runtime-projection" not in readiness_command
    assert "--paper-account-snapshot" not in readiness_command
    assert "--emergency-state" not in readiness_command
    assert "--execution-control" not in readiness_command
    assert "local-paper" not in readiness_command
