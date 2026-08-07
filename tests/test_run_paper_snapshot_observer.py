from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_paper_snapshot_observer.ps1"


def test_paper_snapshot_observer_is_bounded_and_uses_only_the_readonly_service() -> None:
    source = SCRIPT.read_text(encoding="ascii")
    lowered = source.lower()

    assert "$RefreshCadenceMinutes = 4" in source
    assert "$SnapshotTtlMinutes = 5" in source
    assert "$RefreshCadenceMinutes -ge $SnapshotTtlMinutes" in source
    assert "Global\\TheRicherPaperSnapshotObserver" in source
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

    assert "docker.exe compose --project-directory $ProjectRoot --profile kis-readonly" in source
    assert "run --rm --no-deps --pull never kis-readonly" in source
    assert "--service-ports" not in source
    assert "--entrypoint" not in source
    assert "Get-SafeBridgeOutcome" in source
    assert "2>&1" in source
    assert "ConvertFrom-Json -ErrorAction Stop" in source
    assert "observer_busy" in source
    assert "observer_unavailable" in source

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
