from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_iwm_m1_temporal_reach.py"


def test_script_requires_explicit_execution_without_loading_credentials(capsys) -> None:
    script = _load_script()

    assert script.main([]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_paper_iwm_m1_temporal_reach_probe",
        "reason": "execute_flag_required",
        "status": "not_executed",
    }


def test_script_rejects_an_in_repo_artifact_root_before_loading_credentials(
    tmp_path: Path,
    capsys,
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    assert (
        script.main(
            [
                "--execute",
                "--repository-root",
                str(repository_root),
                "--artifact-root",
                str(repository_root / "artifacts"),
            ],
            config_loader=lambda _path: (_ for _ in ()).throw(AssertionError("credentials loaded")),
        )
        == 2
    )

    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_paper_iwm_m1_temporal_reach_probe",
        "model_input_eligibility": False,
        "paper_only": True,
        "route_class": "kis_paper_market_data",
        "status": "input_unavailable",
    }


def test_script_uses_the_named_two_page_probe_route_and_prints_no_paths(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    observed: dict[str, object] = {}

    class _RateGate:
        def __init__(self, **kwargs: object) -> None:
            observed["rate_gate"] = kwargs

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            observed["client"] = kwargs

    monkeypatch.setattr(script, "KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT", tmp_path / "market")
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataTokenStartGate",
        lambda **kwargs: {"token_gate": kwargs},
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperMarketDataTransport",
        lambda **kwargs: {"transport": kwargs},
    )
    monkeypatch.setattr(script, "KisPaperMarketDataClient", _Client)

    def run_and_write(**kwargs: object) -> SimpleNamespace:
        observed["run"] = kwargs
        return SimpleNamespace(
            outcome=SimpleNamespace(
                safe_payload=lambda: {
                    "kind": "kis_paper_iwm_m1_temporal_reach_probe",
                    "status": "continuation_not_observed",
                    "paper_only": True,
                    "route_class": "kis_paper_market_data",
                    "target_key": "IWM/AMS/1m",
                    "model_input_eligibility": False,
                }
            ),
            evidence_sha256="sha256:" + ("a" * 64),
        )

    monkeypatch.setattr(script, "run_and_write_kis_paper_iwm_temporal_reach_probe", run_and_write)

    assert (
        script.main(
            [
                "--execute",
                "--repository-root",
                str(repository_root),
                "--artifact-root",
                str(tmp_path / "artifacts"),
            ],
            config_loader=lambda _path: object(),
            monotonic_clock=lambda: 0.0,
        )
        == 0
    )

    client = observed["client"]
    assert isinstance(client, dict)
    assert client["max_minute_page_attempts"] == 2
    assert client["minute_route"] == "iwm_temporal_reach_probe"
    run = observed["run"]
    assert isinstance(run, dict)
    assert run["repo_root"] == repository_root
    assert run["artifact_root"] == tmp_path / "artifacts"
    assert callable(run["monotonic_clock"])
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "evidence_sha256": "sha256:" + ("a" * 64),
        "kind": "kis_paper_iwm_m1_temporal_reach_probe",
        "model_input_eligibility": False,
        "paper_only": True,
        "route_class": "kis_paper_market_data",
        "status": "continuation_not_observed",
        "target_key": "IWM/AMS/1m",
    }
    assert "evidence_path" not in payload
    source = SCRIPT.read_text(encoding="utf-8")
    assert "KIS_LIVE_" not in source
    assert "KIS_PAPER_ACCOUNT" not in source


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "probe_kis_paper_iwm_m1_temporal_reach_for_test",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("script module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
