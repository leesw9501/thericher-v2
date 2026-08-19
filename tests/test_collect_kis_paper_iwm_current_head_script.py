from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_iwm_current_head.py"


def test_invalid_artifact_root_preflights_before_credentials_client_or_cache_write(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "iwm_current_head"
    events: list[str] = []
    _forbid_client_and_collection(monkeypatch, script, events)

    assert (
        script.main(
            [
                "--execute",
                "--repository-root",
                str(repository_root),
                "--cache-root",
                str(cache_root),
                "--artifact-root",
                str(repository_root / "artifacts"),
            ],
            config_loader=lambda _path: events.append("credentials") or object(),
        )
        == 2
    )

    assert events == []
    assert not cache_root.exists()
    assert not (repository_root / "artifacts").exists()
    assert _safe_failure_payload(capsys.readouterr().out)["status"] == "unavailable"


def test_invalid_cache_root_preflights_before_credentials_client_or_cache_write(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    cache_root = repository_root / "raw-cache"
    events: list[str] = []
    _forbid_client_and_collection(monkeypatch, script, events)

    assert (
        script.main(
            [
                "--execute",
                "--repository-root",
                str(repository_root),
                "--cache-root",
                str(cache_root),
                "--artifact-root",
                str(artifact_root),
            ],
            config_loader=lambda _path: events.append("credentials") or object(),
        )
        == 2
    )

    assert events == []
    assert not cache_root.exists()
    assert not artifact_root.exists()
    assert _safe_failure_payload(capsys.readouterr().out)["status"] == "unavailable"


def _forbid_client_and_collection(monkeypatch, script: ModuleType, events: list[str]) -> None:
    class _ForbiddenClient:
        def __init__(self, **_kwargs: object) -> None:
            events.append("client")
            raise AssertionError("client constructed")

    def forbidden_collection(**_kwargs: object) -> object:
        events.append("collection")
        raise AssertionError("collection invoked")

    monkeypatch.setattr(script, "KisPaperMarketDataClient", _ForbiddenClient)
    monkeypatch.setattr(script, "run_kis_paper_iwm_current_head_cycle", forbidden_collection)


def _safe_failure_payload(output: str) -> dict[str, object]:
    payload = json.loads(output)
    assert payload["paper_only"] is True
    assert payload["route_class"] == "kis_paper_market_data"
    return payload


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "collect_kis_paper_iwm_current_head_for_test",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("script module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
