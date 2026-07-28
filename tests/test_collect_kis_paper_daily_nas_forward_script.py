from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data.kis_paper_daily_nas_forward_cache import KisPaperDailyNasForwardCacheError


def test_requires_explicit_execute_before_loading_market_data_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()

    def unexpected() -> object:
        raise AssertionError("script must not load credentials without --execute")

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    script.main([])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_rejects_noncanonical_execution_roots_before_loading_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()

    def unexpected() -> object:
        raise AssertionError("script must not load credentials for invalid roots")

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    script.main(["--execute", "--cache-root", "C:/not-the-docker-mount"])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "canonical_container_roots_required",
    }


def test_compose_profile_is_data_only_and_uses_dedicated_external_mounts() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    section = compose.split("\n  kis-paper-daily-nas-forward:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-spy-head:\n",
        maxsplit=1,
    )[0]

    assert 'profiles: ["kis-paper-daily-nas-forward"]' in section
    assert "read_only: true" in section
    assert "collect_kis_paper_daily_nas_forward.py" in section
    assert "daily-nas-forward/v1:/app/market_data" in section
    assert "collection-control-v1:/app/collection_control" in section
    assert "data/kis-paper-daily-nas-forward-v1:/app/model_artifacts" in section
    assert "KIS_LIVE" not in section
    assert "order" not in section.lower()


def test_cache_integrity_failure_writes_a_source_safe_recovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()
    captured: dict[str, object] = {}

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(
        script,
        "UrllibKisPaperDailyNasForwardTransport",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())

    def fail_collection(*_args: object, **_kwargs: object) -> object:
        raise KisPaperDailyNasForwardCacheError("forward duplicate conflict")

    def record_receipt(**kwargs: object) -> str:
        captured.update(kwargs)
        return "sha256:" + "f" * 64

    monkeypatch.setattr(script, "collect_kis_paper_daily_nas_forward_once", fail_collection)
    monkeypatch.setattr(script, "_write_source_safe_receipt", record_receipt)

    script.main(["--execute"], clock=lambda: datetime(2026, 7, 29, tzinfo=UTC))

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "unavailable"
    assert output["reason"] == "nas_forward_collection_unavailable"
    assert output["receipt_sha256"] == "sha256:" + "f" * 64
    assert "duplicate" not in json.dumps(output)
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["recovery"] == "reconcile"
    assert payload["credentials_in_payload"] is False
    assert payload["account_or_order_data_in_payload"] is False


def _script_module() -> object:
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_daily_nas_forward.py"
    specification = importlib.util.spec_from_file_location(
        "collect_kis_paper_daily_nas_forward_for_test",
        script_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
