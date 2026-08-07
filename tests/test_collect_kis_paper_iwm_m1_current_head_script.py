from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_iwm_m1_current_head.py"


def test_script_requires_explicit_execution_without_loading_credentials(
    monkeypatch, capsys
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _path: (_ for _ in ()).throw(AssertionError("credentials loaded")),
    )

    assert script.main([]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_script_rejects_in_repo_cache_before_loading_credentials(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", tmp_path / "repo")
    script._REPOSITORY_ROOT.mkdir()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _path: (_ for _ in ()).throw(AssertionError("credentials loaded")),
    )

    assert (
        script.main(
            ["--execute", "--cache-root", str(script._REPOSITORY_ROOT / "raw-cache")]
        )
        == 2
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "unavailable",
        "paper_only": True,
        "route_class": "kis_paper_market_data",
    }


def test_script_uses_the_fixed_one_page_iwm_route_and_prints_no_paths(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", repository_root)
    observed: dict[str, object] = {}
    monkeypatch.setattr(script, "load_kis_paper_market_data_config", lambda _path: object())

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            observed["client_kwargs"] = kwargs

    def collect_and_write(**kwargs: object) -> SimpleNamespace:
        observed["collect_kwargs"] = kwargs
        return SimpleNamespace(
            result=SimpleNamespace(
                outcome=SimpleNamespace(
                    status="collected",
                    safe_payload=lambda: {
                        "status": "collected",
                        "paper_only": True,
                        "route_class": "kis_paper_market_data",
                        "target_key": "IWM/AMS/1m",
                    },
                )
            )
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", _Client)
    monkeypatch.setattr(
        script,
        "collect_and_write_kis_paper_iwm_m1_current_head",
        collect_and_write,
    )

    assert (
        script.main(
            [
                "--execute",
                "--artifact-root",
                str(tmp_path / "artifacts"),
            ],
            clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        )
        == 0
    )

    client_kwargs = observed["client_kwargs"]
    assert isinstance(client_kwargs, dict)
    assert client_kwargs["max_minute_page_attempts"] == 1
    collect_kwargs = observed["collect_kwargs"]
    assert isinstance(collect_kwargs, dict)
    assert collect_kwargs["observed_at"] == datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "collected",
        "paper_only": True,
        "route_class": "kis_paper_market_data",
        "target_key": "IWM/AMS/1m",
    }
    assert "evidence_path" not in payload


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "collect_kis_paper_iwm_m1_current_head_for_test",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("script module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
