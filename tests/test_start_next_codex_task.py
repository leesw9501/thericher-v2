from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "start_next_codex_task.ps1"
)


def test_start_preflight_requires_and_reports_only_active_stateboards() -> None:
    source = SCRIPT.read_text(encoding="ascii")

    for stateboard in (
        "agents/data.md",
        "agents/engine-research.md",
        "agents/research-steward.md",
        "agents/execution.md",
        "agents/orchestration.md",
    ):
        assert f'"{stateboard}"' in source

    assert 'Write-Host "== Active agent stateboards =="' in source
    assert "$required += $activeStateboards" in source
    assert 'Get-ChildItem -LiteralPath "agents" -Filter "*.md"' not in source
    assert 'Write-Host "Fast local feedback: .\\scripts\\run_parallel_tests.ps1"' in source
