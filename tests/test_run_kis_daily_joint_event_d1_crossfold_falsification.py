from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_runner_stays_offline_when_core_run_is_injected(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    script = _load_script()
    artifact_root = tmp_path / "model-artifacts"
    summary_path = artifact_root / "summary.json"

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("cross-fold runner must not use network or environment access")

    def run_falsification(**kwargs: object) -> object:
        assert kwargs == {
            "artifact_root": artifact_root,
            "run_label": "unit-a",
            "repo_root": script._REPO_ROOT,
        }
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(
        script, "run_kis_daily_joint_event_d1_crossfold_falsification", run_falsification
    )

    script.main(["--run-label", "unit-a", "--artifact-root", str(artifact_root)])

    assert json.loads(capsys.readouterr().out) == {"status": "complete"}


def _load_script() -> ModuleType:
    scripts_path = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts_path))
    try:
        path = scripts_path / "run_kis_daily_joint_event_d1_crossfold_falsification.py"
        spec = importlib.util.spec_from_file_location(
            "run_kis_daily_joint_event_d1_crossfold_falsification_for_test",
            path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            return module
        finally:
            sys.modules.pop(spec.name, None)
    finally:
        sys.path.remove(str(scripts_path))
