from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def test_default_forward_cache_root_follows_market_data_root(tmp_path: Path) -> None:
    script = _load_script_module()
    market_data_root = tmp_path / "market-data"

    assert script._resolve_forward_cache_root(  # noqa: SLF001
        market_data_root=market_data_root,
        forward_cache_root=None,
    ) == market_data_root / script._FORWARD_CACHE_RELATIVE_ROOT  # noqa: SLF001


def test_invalid_forward_cache_writes_source_safe_external_recovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script_module()
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "external-artifacts"
    script._REPOSITORY_ROOT = tmp_path / "repository"  # noqa: SLF001
    script._REPOSITORY_ROOT.mkdir()  # noqa: SLF001
    monkeypatch.setattr(
        script,
        "load_kis_paper_daily_history_sequence_input",
        lambda *_args, **_kwargs: SimpleNamespace(
            validation=SimpleNamespace(common_sessions=(object(),))
        ),
    )
    monkeypatch.setattr(
        script,
        "build_kis_paper_daily_history_panel",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_daily_nas_forward_cache",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("tampered cache body must not be exposed")
        ),
    )

    exit_code = script.main(
        [
            "--run-label",
            "invalid-forward-cache",
            "--market-data-root",
            str(market_data_root),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    assert exit_code == 20
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "input_unavailable"
    assert payload["reason"] == "forward_cache_unavailable_or_invalid"
    assert payload["recovery"]["exception_detail_retained"] is False
    assert "tampered cache body" not in json.dumps(payload)
    receipt_path = (
        artifact_root
        / "research"
        / "kis-nas-d1-volatility-trend-prospective-observation-v1"
        / "invalid-forward-cache"
        / "input_unavailable.json"
    )
    assert receipt_path.is_file()
    assert not receipt_path.is_relative_to(script._REPOSITORY_ROOT)  # noqa: SLF001


def test_recovery_receipt_propagates_a_nonzero_cli_exit_code(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    launcher = tmp_path / "run_invalid_forward_cache.py"
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    script_path = (
        project_root
        / "scripts"
        / "run_kis_nas_d1_volatility_trend_prospective_observation.py"
    )
    sequence_input_line = (
        "module.load_kis_paper_daily_history_sequence_input = "
        "lambda *_args, **_kwargs: "
        "SimpleNamespace(validation=SimpleNamespace("
        "common_sessions=(date(2026, 7, 24),)))"
    )
    invalid_cache_line = (
        "module.load_verified_kis_paper_daily_nas_forward_cache = "
        "lambda *_args, **_kwargs: "
        "(_ for _ in ()).throw(ValueError('invalid cache'))"
    )
    command_line = (
        "raise SystemExit(module.main(['--run-label', 'invalid-cache-cli', "
        f"'--market-data-root', {str(market_data_root)!r}, "
        f"'--artifact-root', {str(artifact_root)!r}]))"
    )
    launcher.write_text(
        "\n".join(
            (
                "import importlib.util",
                "from datetime import date",
                "from pathlib import Path",
                "from types import SimpleNamespace",
                f"script_path = Path({str(script_path)!r})",
                "spec = importlib.util.spec_from_file_location('observer_cli', script_path)",
                "module = importlib.util.module_from_spec(spec)",
                "assert spec is not None and spec.loader is not None",
                "spec.loader.exec_module(module)",
                f"module._REPOSITORY_ROOT = Path({str(repository_root)!r})",
                sequence_input_line,
                "module.build_kis_paper_daily_history_panel = lambda *_args, **_kwargs: object()",
                invalid_cache_line,
                command_line,
            )
        )
        + "\n",
        encoding="ascii",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(project_root / "src")

    completed = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=project_root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 20
    assert json.loads(completed.stdout)["reason"] == "forward_cache_unavailable_or_invalid"


def _load_script_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_nas_d1_volatility_trend_prospective_observation.py"
    )
    spec = importlib.util.spec_from_file_location("prospective_observer_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load prospective observer script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
