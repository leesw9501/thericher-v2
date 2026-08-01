from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_kis_intraday_consensus_replay.py"
)
_SPEC = importlib.util.spec_from_file_location("intraday_consensus_replay_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def test_script_uses_the_fixed_local_cache_replay_contract(
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

    def run_replay(actual_catalog: object, **kwargs: object) -> SimpleNamespace:
        assert actual_catalog is catalog
        assert kwargs["session_dates"] == script._DEFAULT_SESSION_DATES
        assert kwargs["run_label"] == "script-unit-r1"
        summary_path = (
            artifact_root
            / "research"
            / "kis-intraday-multitimeframe-consensus-replay-v1"
            / "script-unit-r1"
            / "summary.json"
        )
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text(
            json.dumps({"mode": "offline_local_cache_local_paper_only"}),
            encoding="utf-8",
        )
        return SimpleNamespace(summary_path=summary_path)

    monkeypatch.setattr(script, "run_kis_intraday_consensus_replay", run_replay)

    script.main(
        [
            "--run-label",
            "script-unit-r1",
            "--artifact-root",
            str(artifact_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    summary_path = (
        artifact_root
        / "research"
        / "kis-intraday-multitimeframe-consensus-replay-v1"
        / "script-unit-r1"
        / "summary.json"
    )
    assert payload == json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "offline_local_cache_local_paper_only"
