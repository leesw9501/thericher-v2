import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_daily_nas_forward_schedule.ps1"
)


def test_nas_d1_schedule_runner_uses_preflight_exit_codes_without_parsing_output() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    preflight_call = ' -Service "kis-paper-daily-nas-forward-preflight"'
    collection_call = ' -Service "kis-paper-daily-nas-forward"'
    observation_call = ' -Service "kis-paper-daily-nas-forward-observation"'
    assert '"--profile",' in source
    assert '"kis-paper-daily-nas-forward",' in source
    assert '"run",' in source
    assert '"--rm",' in source
    assert '"--no-deps",' in source
    assert '"--pull",' in source
    assert '"never"' in source
    assert preflight_call in source
    assert collection_call in source
    assert observation_call in source
    assert source.index(preflight_call) < source.index(collection_call)
    assert '$CacheCurrentExitCode = 0' in source
    assert '$CollectionRequiredExitCode = 10' in source
    assert '$TimingRecoveryExitCode = 20' in source
    assert 'if ($preflightExitCode -eq $CacheCurrentExitCode)' in source
    assert 'if ($preflightExitCode -ne $CollectionRequiredExitCode)' in source
    assert '$collectionExitCode -ne 0' in source
    assert '$runObservation = $true' in source
    assert 'Invoke-NasForwardObservation -ProjectRoot $resolvedProjectRoot' in source
    assert 'New-NasForwardObservationRunLabel' in source
    assert '[Guid]::NewGuid()' in source
    assert '"--market-data-root"' in source
    assert '"/app/market_data"' in source
    assert '"--artifact-root"' in source
    assert '"/app/model_artifacts"' in source
    assert "ConvertFrom-Json" not in source
    assert "Start-Sleep" not in source


def test_nas_d1_schedule_runner_guards_host_timezone_with_uncredentialed_receipt() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert "test-koreastandardtime" in source
    assert "korea standard time" in source
    assert "host_timezone_not_kst" in source
    assert "--schedule-guard-failed" in source
    assert "--entrypoint" in source
    assert "kis-paper-daily-nas-forward-preflight" in source
    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source


def test_nas_d1_schedule_runner_wires_observer_only_after_a_cache_current_or_successful_collection(
) -> None:
    source = SCRIPT.read_text(encoding="ascii")
    dispatch = source.split("$runObservation = $false", maxsplit=1)[1]

    current_branch = dispatch.split(
        'if ($preflightExitCode -eq $CacheCurrentExitCode)', maxsplit=1
    )[1].split('elseif ($preflightExitCode -ne $CollectionRequiredExitCode)', maxsplit=1)[0]
    collection_branch = dispatch.split('} else {', maxsplit=1)[1].split(
        '\n}\n\nif ($runObservation)', maxsplit=1
    )[0]
    timing_guard = source.split('if (-not (Test-KoreaStandardTime))', maxsplit=1)[1].split(
        '$preflight =', maxsplit=1
    )[0]

    assert '$runObservation = $true' in current_branch
    assert '$collectionExitCode -ne 0' in collection_branch
    assert '$runObservation = $true' in collection_branch
    assert 'Invoke-NasForwardObservation' not in timing_guard
    assert 'return $collectionExitCode' in collection_branch


def test_schedule_runner_does_not_observe_after_a_partial_collection(tmp_path: Path) -> None:
    project_root = SCRIPT.parents[1]
    harness = tmp_path / "partial_collection.ps1"
    escaped_schedule = str(SCRIPT).replace("'", "''")
    escaped_project_root = str(project_root).replace("'", "''")
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f". '{escaped_schedule}'",
                "$script:observationCalls = 0",
                "function Test-KoreaStandardTime { return $true }",
                "function Invoke-NasForwardProfileService {",
                "    param(",
                "        [string]$ProjectRoot,",
                "        [string]$Service,",
                "        [string[]]$CommandOverride = @()",
                "    )",
                "    if ($Service -eq 'kis-paper-daily-nas-forward-preflight') {",
                "        return [pscustomobject]@{ ExitCode = 10; Output = @() }",
                "    }",
                "    if ($Service -eq 'kis-paper-daily-nas-forward') {",
                "        return [pscustomobject]@{ ExitCode = 20; Output = @() }",
                "    }",
                "    throw 'unexpected service'",
                "}",
                "function Invoke-NasForwardObservation {",
                "    $script:observationCalls += 1",
                "    return [pscustomobject]@{ ExitCode = 0; Output = @() }",
                "}",
                f"$exitCode = Invoke-NasForwardSchedule -ProjectRoot '{escaped_project_root}'",
                "if ($script:observationCalls -ne 0) { exit 91 }",
                "exit $exitCode",
            )
        )
        + "\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 20
