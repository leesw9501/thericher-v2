from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kis_paper_intraday_head_schedule.ps1"
)


def test_head_schedule_dispatcher_preserves_one_profile_and_collection_result() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    collection_call = ' -Service "kis-paper-intraday-head"'
    observation_call = ' -Service "kis-paper-intraday-observation"'
    assert "--profile kis-paper-intraday-head" in source
    assert "run --rm --no-deps --build $Service" in source
    assert collection_call in source
    assert observation_call in source
    assert source.index(collection_call) < source.index(observation_call)
    assert "exit $collectionExitCode" in source
    assert "observation_exit_code" in source
    assert "observation_status" in source
    assert "Get-ObservationStatus" in source
    assert "2>&1" in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert "pending\", \"unavailable\", \"complete" in source


def test_head_schedule_dispatcher_has_no_secret_or_live_route_surface() -> None:
    source = SCRIPT.read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source
    assert "submit" not in source
    assert "cancel" not in source
