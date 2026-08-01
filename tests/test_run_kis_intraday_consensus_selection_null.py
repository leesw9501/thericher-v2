from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_kis_intraday_consensus_selection_null.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "intraday_consensus_selection_null_script",
    _SCRIPT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def test_script_uses_the_frozen_default_baseline_and_session_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog = object()
    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_kwargs: catalog,
    )
    artifact_root = tmp_path / "external-artifacts"

    def run_diagnostic(actual_catalog: object, **kwargs: object) -> SimpleNamespace:
        assert actual_catalog is catalog
        assert kwargs["session_dates"] == script._DEFAULT_SESSION_DATES
        assert kwargs["upstream_candidate_factory"] is script.predeclared_consensus_replay_candidate
        assert kwargs["baseline_summary_path"] == script._DEFAULT_BASELINE_SUMMARY
        summary_path = artifact_root / "summary.json"
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(
            json.dumps({"classification": "selection_unqualified"}),
            encoding="utf-8",
        )
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "run_kis_intraday_consensus_selection_null", run_diagnostic)
    script.main(["--run-label", "script-unit-r1", "--artifact-root", str(artifact_root)])

    assert json.loads(capsys.readouterr().out) == {"classification": "selection_unqualified"}
