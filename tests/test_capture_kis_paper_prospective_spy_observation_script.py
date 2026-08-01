from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_script_forwards_only_local_capture_arguments_and_prints_safe_payload(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    expected = SimpleNamespace(
        safe_payload=lambda: {
            "kind": "kis_paper_prospective_spy_capture",
            "status": "not_yet_observed",
            "receipt": None,
        }
    )
    captured: dict[str, object] = {}

    def run_capture(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(script, "capture_kis_paper_prospective_spy_observation", run_capture)

    result = script.main(
        [
            "--session-date",
            "2026-08-03",
            "--observed-at",
            "2026-08-03T19:30:00Z",
            "--cache-root",
            str(tmp_path / "cache"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ]
    )

    assert result == 0
    assert captured == {
        "cache_root": tmp_path / "cache",
        "artifact_root": tmp_path / "artifacts",
        "repo_root": script._REPO_ROOT,
        "session_date": date(2026, 8, 3),
        "observed_at": datetime(2026, 8, 3, 19, 30, tzinfo=UTC),
    }
    assert json.loads(capsys.readouterr().out) == expected.safe_payload()


def test_script_rejects_naive_observed_timestamp(capsys) -> None:
    script = _load_script()

    try:
        script.main(
            [
                "--session-date",
                "2026-08-03",
                "--observed-at",
                "2026-08-03T19:30:00",
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("naive observed timestamp must be rejected")

    assert "--observed-at must include a UTC offset" in capsys.readouterr().err


def _load_script() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "capture_kis_paper_prospective_spy_observation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "capture_kis_paper_prospective_spy_observation_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
