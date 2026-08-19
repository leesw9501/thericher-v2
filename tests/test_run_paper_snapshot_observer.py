from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_paper_snapshot_observer.ps1"


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
    wrapper_path.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                *clock_fixture,
                "function global:uv.exe {",
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
                "function global:docker.exe {",
                f"    $markerPath = {_powershell_literal(docker_marker)}",
                "    [System.IO.File]::WriteAllText($markerPath, ($args -join '|'))",
                f"    $bridgeJson = {_powershell_literal(bridge_json)}",
                (
                    "    $observerArgument = @($args | Where-Object { $_ -like "
                    "'THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID=*' })"
                ),
                "    if ($observerArgument.Count -eq 1) {",
                (
                    "        $bridgeJson = $bridgeJson.Replace("
                    "'__observer_invocation_id__', "
                    "([string]$observerArgument[0]).Split('=')[1])"
                ),
                "    }",
                "    Write-Output $bridgeJson",
                f"    $global:LASTEXITCODE = {bridge_exit_code}",
                "}",
                (
                    f"& {_powershell_literal(SCRIPT)} "
                    f"-ProjectRoot {_powershell_literal(project_root)} "
                    f"-ObserverMutexName {_powershell_literal(fixture_mutex_name)}"
                ),
                "exit $LASTEXITCODE",
                "",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper_path),
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
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

    assert "uv.exe run --no-sync --project $ProjectRoot python $inspectorPath" in source
    assert "inspect_kis_paper_account_snapshot_observer_session.py" in source
    assert "kis_paper_snapshot_observer_session" in source
    assert '"eligible"' in source
    assert '"outside_regular_session"' in source
    assert '"session_unavailable"' in source
    assert '"session_closing"' in source
    assert '"eligible_until"' in source
    assert "[TimeSpan]::FromMinutes($MinimumSessionRemainingMinutes)" in source
    assert "($eligibleUntil - $observedAt) -le" in source

    assert "docker.exe compose --project-directory $ProjectRoot --profile kis-readonly" in source
    assert "run --rm --no-deps --pull never" in source
    assert "kis-readonly 2>&1" in source
    assert "--service-ports" not in source
    assert "--entrypoint" not in source
    assert "Get-SafeBridgeOutcome" in source
    assert "2>&1" in source
    assert "ConvertFrom-Json -ErrorAction Stop" in source
    assert "observer_busy" in source
    assert "observer_unavailable" in source
    assert '"busy"' in source
    assert '"refresh_busy"' in source
    assert "$bridgeObservedAt = [datetimeoffset]::Parse(" in source
    assert 'Write-ObserverOutcome -Status "complete" -ObservedAt $bridgeObservedAt' in source
    assert "$bridgeLaunchAt = Get-ObserverUtcNow" in source
    assert '$observerInvocationId = [guid]::NewGuid().ToString("D")' in source
    assert "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID=$ObserverInvocationId" in source
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
        "quote",
        "modify",
        "cancel",
    ):
        assert forbidden not in lowered
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
    assert "THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID=" in invocation
    assert re.search(
        r"THERICHER_KIS_PAPER_SNAPSHOT_OBSERVER_INVOCATION_ID="
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

    assert completed.returncode == 3, completed.stderr
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
