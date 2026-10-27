from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_paper_snapshot_observer.ps1"

SCHEDULER_ENTRYPOINTS = (
    "Get-ScheduledTask", "Get-ScheduledTaskInfo", "Register-ScheduledTask",
    "Set-ScheduledTask", "Start-ScheduledTask", "Stop-ScheduledTask",
    "Enable-ScheduledTask", "Disable-ScheduledTask", "Export-ScheduledTask",
    "Unregister-ScheduledTask", "New-ScheduledTask", "New-ScheduledTaskAction",
    "New-ScheduledTaskPrincipal", "New-ScheduledTaskSettingsSet",
    "New-ScheduledTaskTrigger",
    "Get-ClusteredScheduledTask", "Register-ClusteredScheduledTask",
    "Set-ClusteredScheduledTask", "Unregister-ClusteredScheduledTask",
    "schtasks.exe", "at.exe",
)


def _isolated_powershell() -> list[str]:
    return [
        "$ErrorActionPreference = 'Stop'",
        "$PSModuleAutoLoadingPreference = 'None'",
        "Import-Module Microsoft.PowerShell.Management",
        "Import-Module Microsoft.PowerShell.Utility",
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)",
        *[
            f"function global:{name} {{ throw 'Scheduler entrypoint blocked' }}"
            for name in SCHEDULER_ENTRYPOINTS
        ],
    ]


def _parse_source() -> list[str]:
    return [
        "$tokens = $null; $parseErrors = $null",
        f"$sourcePath = {_powershell_literal(SCRIPT)}",
        "$source = [System.IO.File]::ReadAllText($sourcePath)",
        "$ast = [System.Management.Automation.Language.Parser]::ParseInput("
        "$source, [ref]$tokens, [ref]$parseErrors)",
        "if (@($parseErrors).Count -ne 0) { throw 'source_parse_failure' }",
    ]


def _run_powershell(wrapper_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(wrapper_path)],
        check=False, capture_output=True, encoding="utf-8", timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _powershell_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_with_fake_host_commands(
    tmp_path: Path,
    *,
    eligible_minutes: int,
    bridge_payload: dict[str, object],
    bridge_recheck_minutes: int | None = None,
    bridge_exit_code: int = 0,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    project_root = tmp_path / "project"
    inspector_path = (
        project_root / "scripts" / "inspect_kis_paper_account_snapshot_observer_session.py"
    )
    inspector_path.parent.mkdir(parents=True)
    inspector_path.write_text("# fixture\n", encoding="ascii")
    (inspector_path.parent / "run_kis_paper_snapshot_bridge.py").write_text("# fixture\n")
    (project_root / "docker-compose.yml").write_text("services: {}\n", encoding="ascii")
    docker_marker = tmp_path / "docker-called.txt"
    fixture_mutex_name = f"Global\\TheRicherPaperSnapshotObserver-fixture-{uuid4().hex}"
    bridge_json = json.dumps(bridge_payload, separators=(",", ":"))
    clock_fixture: list[str] = []
    if bridge_recheck_minutes is not None:
        clock_fixture = [
            "$global:fixtureBase = [datetime]::UtcNow",
            "$global:fixtureDateCalls = 0",
            "function global:Get-Date {",
            "    $global:fixtureDateCalls += 1",
            "    if ($global:fixtureDateCalls -le 2) {",
            "        return $global:fixtureBase",
            "    }",
            (
                "    return $global:fixtureBase.AddMinutes("
                f"{eligible_minutes - bridge_recheck_minutes})"
            ),
            "}",
        ]
        inspector_clock = "$global:fixtureBase"
    else:
        inspector_clock = "[datetime]::UtcNow"
    wrapper_path = tmp_path / "run-observer-fixture.ps1"
    adapted_path = tmp_path / "observer-adapted.ps1"
    wrapper_path.write_text(
        "\n".join(
            [
                *_isolated_powershell(),
                "function global:Get-Command {",
                "  [CmdletBinding()] param([string]$Name, [object]$CommandType)",
                "  if ($Name -eq 'uv.exe') {",
                "    if ($PSBoundParameters.ContainsKey('CommandType') -and",
                "        [string]$CommandType -ne 'Application') { throw 'uv_resolution_shape' }",
                "    return [pscustomobject]@{ Source = 'fixture-uv.exe' }",
                "  }",
                "  if ($Name -eq 'docker.exe') { return [pscustomobject]@{"
                " Source = 'fixture-docker.exe' } }",
                "  throw 'unmocked_command_resolution'",
                "}",
                "function global:Join-Path { param($Path,$ChildPath)",
                "  if ($ChildPath -eq '.venv\\Scripts\\python.exe') {",
                "    return 'fixture-python.exe' }",
                "  Microsoft.PowerShell.Management\\Join-Path $Path $ChildPath",
                "}",
                "function global:Test-Path { param($LiteralPath,$PathType)",
                "  if ($LiteralPath -eq 'fixture-python.exe') { return $true }",
                "  Microsoft.PowerShell.Management\\Test-Path `",
                "    -LiteralPath $LiteralPath -PathType $PathType",
                "}",
                *clock_fixture,
                "function global:Get-FixtureSessionOutput {",
                f"    $now = {inspector_clock}",
                "    $observed = $now.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')",
                (
                    "    $eligibleUntil = $now.AddMinutes("
                    f"{eligible_minutes}).ToString('yyyy-MM-ddTHH:mm:ss.fffZ')"
                ),
                "    [ordered]@{",
                "        eligible_until = $eligibleUntil",
                "        kind = 'kis_paper_snapshot_observer_session'",
                "        observed_at = $observed",
                "        status = 'eligible'",
                "    } | ConvertTo-Json -Compress",
                "    $global:LASTEXITCODE = 0",
                "}",
                "function global:docker.exe { throw 'Direct Docker launch forbidden' }",
                "function global:Get-FixtureBridgeOutput {",
                f"    $markerPath = {_powershell_literal(docker_marker)}",
                "    [System.IO.File]::WriteAllText($markerPath, ($args -join '|'))",
                f"    $bridgeJson = {_powershell_literal(bridge_json)}",
                (
                    "    $observerPosition = [Array]::IndexOf("
                    "[object[]]$args, '--observer-invocation-id')"
                ),
                "    if ($observerPosition -ge 0) {",
                (
                    "        $bridgeJson = $bridgeJson.Replace("
                    "'__observer_invocation_id__', "
                    "([string]$args[$observerPosition + 1]))"
                ),
                "    }",
                "    Write-Output $bridgeJson",
                f"    $global:LASTEXITCODE = {bridge_exit_code}",
                "}",
                *_parse_source(),
                "$nodes = @($ast.FindAll({ param($node)",
                "  $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and",
                "  $node.Name -ceq 'Invoke-ObserverNativeQuiet'",
                "}, $true))",
                "if ($nodes.Count -ne 1) {",
                "  [Console]::Error.WriteLine('exact_native_seam_missing_or_ambiguous'); exit 91",
                "}",
                "$replacement = @'",
                "function Invoke-ObserverNativeQuiet {",
                "  param([string]$FilePath, [string[]]$ArgumentList)",
                "  if ($FilePath -ceq 'fixture-uv.exe') {",
                "    if (($ArgumentList[0..3] -join '|') -cne",
                "        'run|--no-env-file|--no-sync|--project') { throw 'uv_argv_shape' }",
                "    $output = @(Get-FixtureSessionOutput @ArgumentList)",
                "  } elseif ($FilePath -ceq 'fixture-python.exe') {",
                "    $output = @(Get-FixtureBridgeOutput @ArgumentList)",
                "  } else { throw 'unmocked_native_executable' }",
                "  return [pscustomobject]@{ Output = $output; ExitCode = $global:LASTEXITCODE }",
                "}",
                "'@",
                "$extent = $nodes[0].Extent",
                "$adapted = $source.Remove($extent.StartOffset,",
                "  $extent.EndOffset - $extent.StartOffset).Insert("
                "$extent.StartOffset, $replacement)",
                "$null = [System.Management.Automation.Language.Parser]::ParseInput(",
                "  $adapted, [ref]$tokens, [ref]$parseErrors)",
                "if (@($parseErrors).Count -ne 0) { throw 'adapted_source_parse_failure' }",
                f"[System.IO.File]::WriteAllText({_powershell_literal(adapted_path)}, $adapted)",
                (
                    f"& {_powershell_literal(adapted_path)} "
                    f"-ProjectRoot {_powershell_literal(project_root)} "
                    f"-ObserverMutexName {_powershell_literal(fixture_mutex_name)}"
                ),
                "exit $LASTEXITCODE",
                "",
            ]
        ),
        encoding="utf-8",
    )
    completed = _run_powershell(wrapper_path)
    return completed, docker_marker


def test_paper_snapshot_observer_is_bounded_and_uses_only_the_readonly_service() -> None:
    source = SCRIPT.read_text(encoding="ascii")
    lowered = source.lower()

    assert "$RefreshCadenceMinutes = 4" in source
    assert "$SnapshotTtlMinutes = 5" in source
    assert "$MinimumSessionRemainingMinutes = 4" in source
    assert "$RefreshCadenceMinutes -ge $SnapshotTtlMinutes" in source
    assert "Global\\TheRicherPaperSnapshotObserver" in source
    assert '[string]$ObserverMutexName = "Global\\TheRicherPaperSnapshotObserver"' in source
    assert "New-Object System.Threading.Mutex" in source
    assert "$mutex.WaitOne(0)" in source
    assert "$mutex.ReleaseMutex()" in source
    assert "Start-Sleep" not in source
    assert "Start-Process" not in source

    assert "(Get-Command uv.exe -CommandType Application).Source" in source
    assert (
        "'run', '--no-env-file', '--no-sync', '--project', $ProjectRoot, 'python', $inspectorPath"
        in source
    )
    assert "inspect_kis_paper_account_snapshot_observer_session.py" in source
    assert "kis_paper_snapshot_observer_session" in source
    assert '"eligible"' in source
    assert '"outside_regular_session"' in source
    assert '"session_unavailable"' in source
    assert '"session_closing"' in source
    assert '"eligible_until"' in source
    assert "[TimeSpan]::FromMinutes($MinimumSessionRemainingMinutes)" in source
    assert "($eligibleUntil - $observedAt) -le" in source

    assert "& docker.exe compose" not in source
    assert "run_kis_paper_snapshot_bridge.py" in source
    assert "Invoke-ObserverNativeQuiet -FilePath $bridgePython -ArgumentList @(" in source
    assert "$bridgeLauncher, '--execute', '--project-root', $ProjectRoot" in source
    assert "'--paper-credential-path', (Join-Path $ProjectRoot '.env')" in source
    assert "--service-ports" not in source
    assert "--entrypoint" not in source
    assert "Get-SafeBridgeOutcome" in source
    assert "$info.UseShellExecute = $false" in source
    assert "$info.CreateNoWindow = $true" in source
    assert "$info.RedirectStandardOutput = $true" in source
    assert "$info.RedirectStandardError = $true" in source
    assert "$stdout = $process.StandardOutput.ReadToEndAsync()" in source
    assert "$stderr = $process.StandardError.ReadToEndAsync()" in source
    assert "$process.WaitForExit()" in source
    assert "ConvertFrom-Json -ErrorAction Stop" in source
    assert "observer_busy" in source
    assert "observer_unavailable" in source
    assert '"busy"' in source
    assert '"refresh_busy"' in source
    assert "$bridgeObservedAt = [datetimeoffset]::Parse(" in source
    assert 'Write-ObserverOutcome -Status "complete" -ObservedAt $bridgeObservedAt' in source
    assert "$bridgeLaunchAt = Get-ObserverUtcNow" in source
    assert '$observerInvocationId = [guid]::NewGuid().ToString("D")' in source
    assert "'--observer-invocation-id', $ObserverInvocationId" in source
    assert '$bridge.Status -eq "busy" -and $bridge.ExitCode -eq 0' in source
    assert '"observer_evidence_path"' in source
    assert '"observer_invocation_id"' in source
    assert '[string]$payload.observer_invocation_id -ne $ObserverInvocationId' in source

    for forbidden in (
        "kis_live",
        "kis_paper_app_key",
        "kis_paper_app_secret",
        "kis_paper_account_no",
        "kis_paper_account_product_code",
        "dashboard_token",
        "market_data",
        "modify",
        "cancel",
    ):
        assert forbidden not in lowered
    # The argument-quoting helper's local boolean is not a market-data command.
    assert "quote" not in re.sub(r"\$quote\b", "", lowered)
    for forbidden_action in ("submit", "modify", "cancel", "order"):
        assert re.search(rf"\\b{forbidden_action}\\b", lowered) is None


def test_pre_docker_session_recheck_does_not_invoke_docker(
    tmp_path: Path,
) -> None:
    completed, docker_marker = _run_with_fake_host_commands(
        tmp_path,
        eligible_minutes=5,
        bridge_payload={},
        bridge_recheck_minutes=3,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "session_closing"
    assert payload["scope"] == "read_only"
    assert payload["submit_capability"] is False
    assert not docker_marker.exists()


def test_complete_observer_uses_the_bridge_observed_time(
    tmp_path: Path,
) -> None:
    bridge_observed_at = "2026-07-21T14:31:02.123Z"
    completed, docker_marker = _run_with_fake_host_commands(
        tmp_path,
        eligible_minutes=10,
        bridge_payload={
            "account_snapshot_complete": True,
            "evidence_path": (
                "/app/model_artifacts/execution/kis-paper-console-bridge/"
                "bridge-fixture.json"
            ),
            "observed_at": bridge_observed_at,
            "observer_evidence_path": (
                "/app/model_artifacts/execution/kis-paper-snapshot-observer/"
                "observer-fixture.json"
            ),
            "observer_invocation_id": "__observer_invocation_id__",
            "reason_code": None,
            "scope": "read_only",
            "status": "complete",
        },
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "complete"
    assert datetime.fromisoformat(payload["observed_at"].replace("Z", "+00:00")) == datetime(
        2026, 7, 21, 14, 31, 2, 123000, tzinfo=UTC
    )
    invocation = docker_marker.read_text(encoding="utf-8")
    assert "--observer-invocation-id|" in invocation
    assert re.search(
        r"--observer-invocation-id\|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        invocation,
    )


def test_busy_bridge_with_nonzero_exit_is_observer_unavailable(tmp_path: Path) -> None:
    completed, docker_marker = _run_with_fake_host_commands(
        tmp_path,
        eligible_minutes=10,
        bridge_payload={
            "account_snapshot_complete": False,
            "evidence_path": None,
            "observed_at": "2026-07-21T14:31:02.123Z",
            "observer_evidence_path": None,
            "observer_invocation_id": None,
            "reason_code": "refresh_busy",
            "scope": "read_only",
            "status": "busy",
        },
        bridge_exit_code=1,
    )

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "observer_unavailable"
    assert payload["scope"] == "read_only"
    assert payload["submit_capability"] is False
    assert docker_marker.exists()


def test_mismatched_bridge_observer_invocation_is_observer_unavailable(tmp_path: Path) -> None:
    completed, docker_marker = _run_with_fake_host_commands(
        tmp_path,
        eligible_minutes=10,
        bridge_payload={
            "account_snapshot_complete": True,
            "evidence_path": (
                "/app/model_artifacts/execution/kis-paper-console-bridge/"
                "bridge-fixture.json"
            ),
            "observed_at": "2026-07-21T14:31:02.123Z",
            "observer_evidence_path": (
                "/app/model_artifacts/execution/kis-paper-snapshot-observer/"
                "observer-fixture.json"
            ),
            "observer_invocation_id": "6b991b8c-98ef-46de-ab4e-cbfa7fe1d00e",
            "reason_code": None,
            "scope": "read_only",
            "status": "complete",
        },
    )

    assert completed.returncode == 3, completed.stderr
    assert json.loads(completed.stdout)["status"] == "observer_unavailable"
    assert docker_marker.exists()


@pytest.mark.parametrize(
    "category", ["docker_timeout", "docker_timeout_cleanup_unknown", "PRIVATE"]
)
def test_launcher_timeout_category_is_allowlisted_and_failure_retained(
    tmp_path: Path,
    category: str,
) -> None:
    completed, _ = _run_with_fake_host_commands(
        tmp_path,
        eligible_minutes=10,
        bridge_payload={
            "kind": "kis_paper_snapshot_bridge_launcher",
            "status": "unavailable",
            "failure_category": category,
            "submit_capability": False,
        },
        bridge_exit_code=3,
    )
    assert completed.returncode == 3, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "observer_unavailable"
    if category == "PRIVATE":
        assert "reason_code" not in result and "PRIVATE" not in completed.stdout
    else:
        assert result["reason_code"] == category


def test_fixture_blocks_all_scheduler_entrypoints(tmp_path: Path) -> None:
    wrapper = tmp_path / "scheduler-guards.ps1"
    wrapper.write_text(
        "\n".join([
            *_isolated_powershell(),
            "$blocked = 0",
            *[
                "try { & " + _powershell_literal(name)
                + "; throw 'scheduler_guard_missing' } catch {"
                " if ($_.Exception.Message -cne 'Scheduler entrypoint blocked') { throw };"
                " $blocked++ }"
                for name in SCHEDULER_ENTRYPOINTS
            ],
            "[ordered]@{ blocked = $blocked; autoload = $PSModuleAutoLoadingPreference }"
            " | ConvertTo-Json -Compress",
        ]), encoding="ascii",
    )
    completed = _run_powershell(wrapper)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": len(SCHEDULER_ENTRYPOINTS), "autoload": "None",
    }


def test_fixture_requires_exact_native_helper_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed = tmp_path / "missing-helper.ps1"
    changed.write_text(
        SCRIPT.read_text(encoding="ascii").replace(
            "function Invoke-ObserverNativeQuiet {",
            "function Renamed-NativeHelper {",
        ), encoding="ascii",
    )
    monkeypatch.setitem(globals(), "SCRIPT", changed)
    completed, marker = _run_with_fake_host_commands(
        tmp_path, eligible_minutes=10, bridge_payload={},
    )
    assert completed.returncode == 91
    assert "exact_native_seam_missing_or_ambiguous" in completed.stderr
    assert not marker.exists()


def test_native_quiet_helper_preserves_argv_output_exit_and_has_no_console(
    tmp_path: Path,
) -> None:
    arguments = ["", "two words", 'x"y', "C:\\path space\\", "tail\\"]
    child = tmp_path / "harmless-native-child.py"
    child.write_text(
        "import ctypes, json, os, sys\n"
        "from ctypes import wintypes as w\n"
        "k = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "k.GetConsoleWindow.restype = w.HWND\n"
        "u = ctypes.WinDLL('user32', use_last_error=True)\n"
        "u.IsWindowVisible.argtypes = [w.HWND]\n"
        "u.IsWindowVisible.restype = w.BOOL\n"
        "h = k.GetConsoleWindow()\n"
        "print(json.dumps(dict(argv=sys.argv[1:], console_present=bool(h), "
        "console_visible=bool(h and u.IsWindowVisible(h)), "
        "pid=os.getpid())), flush=True)\n"
        "print('SYN_CATEGORICAL_STDERR', file=sys.stderr, flush=True)\n"
        "raise SystemExit(23)\n",
        encoding="ascii",
    )
    wrapper = tmp_path / "native-helper-only.ps1"
    wrapper.write_text(
        "\n".join([
            *_isolated_powershell(),
            *_parse_source(),
            "foreach ($name in @('ConvertTo-ObserverNativeArguments', "
            "'Invoke-ObserverNativeQuiet')) {",
            "  $nodes = @($ast.FindAll({ param($node)",
            "    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and",
            "    $node.Name -ceq $name",
            "  }, $true))",
            "  if ($nodes.Count -ne 1) { throw 'exact_helper_missing_or_ambiguous' }",
            "  . ([scriptblock]::Create($nodes[0].Extent.Text))",
            "}",
            "$native = Invoke-ObserverNativeQuiet -FilePath "
            + _powershell_literal(sys.executable) + " -ArgumentList @("
            + ", ".join(_powershell_literal(x) for x in ["-I", str(child), *arguments])
            + ")",
            "[ordered]@{ exit_code = $native.ExitCode; output = @($native.Output);",
            "  ps_major = $PSVersionTable.PSVersion.Major; "
            "ps_minor = $PSVersionTable.PSVersion.Minor",
            "} | ConvertTo-Json -Depth 5 -Compress",
            "exit $native.ExitCode",
        ]), encoding="ascii",
    )
    completed = _run_powershell(wrapper)
    assert completed.returncode == 23, completed.stderr
    assert completed.stderr == ""
    result = json.loads(completed.stdout)
    assert (result["ps_major"], result["ps_minor"]) == (5, 1)
    assert result["exit_code"] == 23
    assert len(result["output"]) == 2
    assert result["output"][1] == "SYN_CATEGORICAL_STDERR"
    native = json.loads(result["output"][0])
    assert native["argv"] == arguments
    assert native["console_present"] is False
    assert native["console_visible"] is False
    assert native["pid"] > 0
