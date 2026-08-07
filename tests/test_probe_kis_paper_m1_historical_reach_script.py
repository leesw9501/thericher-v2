from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_m1_historical_reach.py"


def test_script_requires_explicit_execution_without_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    assert script.main([]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "reason": "execute_flag_required",
        "status": "not_executed",
    }


def test_script_rejects_an_unsupported_pace_before_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    with pytest.raises(SystemExit, match="2"):
        script.main(["--execute", "--minimum-request-interval-seconds", "0.5"])


def test_script_preflights_an_in_repository_artifact_root_before_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", repository_root)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    assert script.main(["--execute", "--artifact-root", str(repository_root / "artifacts")]) == 2

    assert json.loads(capsys.readouterr().out) == {
        "paper_only": True,
        "route_class": "kis_paper_market_data",
        "status": "unavailable",
    }


def test_script_builds_one_four_page_client_and_prints_only_safe_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = _load_script()
    observed: dict[str, object] = {}

    monkeypatch.setattr(script, "KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT", tmp_path / "market")
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataRateGate",
        lambda **kwargs: {"rate_gate": kwargs},
    )
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
    monkeypatch.setattr(script, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **kwargs: observed.setdefault("client", kwargs) or object(),
    )

    def probe_and_write(**kwargs: object) -> SimpleNamespace:
        observed["probe"] = kwargs
        return SimpleNamespace(
            status="complete",
            safe_payload=lambda: {
                "paper_only": True,
                "raw_market_data_retained": False,
                "route_class": "kis_paper_market_data",
                "status": "complete",
            },
            evidence_paths=(tmp_path / "qqq.json", tmp_path / "spy.json"),
        )

    monkeypatch.setattr(script, "probe_and_write_kis_paper_m1_historical_reach", probe_and_write)

    assert script.main(["--execute", "--artifact-root", str(tmp_path / "artifacts")]) == 0

    client = observed["client"]
    assert isinstance(client, dict)
    assert client["max_minute_page_attempts"] == 4
    probe = observed["probe"]
    assert isinstance(probe, dict)
    assert probe["tested_request_interval_seconds"] == 1.0
    assert probe["artifact_root"] == tmp_path / "artifacts"
    payload = json.loads(capsys.readouterr().out)
    assert payload["paper_only"] is True
    assert payload["raw_market_data_retained"] is False
    assert payload["evidence_paths"] == [str(tmp_path / "qqq.json"), str(tmp_path / "spy.json")]
    source = SCRIPT.read_text(encoding="utf-8")
    assert "KIS_PAPER_ACCOUNT" not in source
    assert "KIS_LIVE_" not in source


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "probe_kis_paper_m1_historical_reach_for_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
