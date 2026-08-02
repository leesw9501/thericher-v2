from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_runner_prints_only_safe_aggregate_projection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    artifact_root = tmp_path / "external-artifacts"
    observed: dict[str, object] = {}
    payload = {
        "status": "input_unavailable",
        "reason": "active_symbol_or_session_coverage_unavailable",
        "selected_symbol_count": 523,
        "common_session_count": 483,
        "reference_bar_count": 252609,
        "observed_active_bar_count": 252608,
        "compared_symbol_count": 523,
        "exact_match_symbol_count": 522,
        "value_mismatch_symbol_count": 0,
        "symbol_absent_count": 1,
        "session_coverage_mismatch_count": 0,
        "nonrepeatable_symbol_count": 0,
        "malformed_symbol_count": 0,
        "source_unavailable_symbol_count": 0,
        "active_response_sha256": "sha256:" + "a" * 64,
        "per_symbol": [{"not": "printed"}],
    }

    def build(**kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(
            receipt_sha256="sha256:" + "b" * 64,
            safe_payload=lambda: payload,
        )

    monkeypatch.setattr(runner, "build_norgate_broad_active_build_conformance_receipt", build)
    runner.main(["--run-label", "unit-safe", "--artifact-root", str(artifact_root)])

    output = capsys.readouterr().out
    printed = json.loads(output)
    assert observed == {
        "destination": artifact_root / "unit-safe",
        "artifact_root": artifact_root,
        "repo_root": runner._REPOSITORY_ROOT,
    }
    assert printed["status"] == "input_unavailable"
    assert printed["symbol_absent_count"] == 1
    assert printed["reference_bar_count"] == 252609
    assert "per_symbol" not in printed
    assert "per_symbol" not in output


def test_runner_static_surface_excludes_credentials_brokers_and_models() -> None:
    source = _script_path().read_text(encoding="ascii").lower()
    for forbidden in (
        "kis_",
        "orderintent",
        "source: local_paper",
        "dotenv",
        "os.environ",
        "torch",
        "sklearn",
        "model_artifact_root=",
    ):
        assert forbidden not in source
    assert "build_norgate_broad_active_build_conformance_receipt" in source


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "norgate_broad_conformance_runner",
        _script_path(),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_norgate_broad_active_build_conformance.py"
    )
