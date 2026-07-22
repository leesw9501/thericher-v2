"""Host-only behavior tests for the sanitized lifecycle projection script."""

from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "project_kis_paper_canary_lifecycle.py"


def test_lifecycle_projection_defaults_to_host_artifact_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THERICHER_HOST_MODEL_ARTIFACT_ROOT", str(tmp_path / "host-artifacts"))
    monkeypatch.setenv("THERICHER_MODEL_ARTIFACT_ROOT", "/app/model_artifacts")

    script = runpy.run_path(str(SCRIPT_PATH))
    arguments = script["build_parser"]().parse_args(["--run-id", "canary-test-1"])

    assert arguments.artifact_root == tmp_path / "host-artifacts"
