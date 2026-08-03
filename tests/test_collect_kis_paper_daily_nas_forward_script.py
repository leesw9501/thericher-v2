from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data.kis_paper_daily_nas_forward_cache import KisPaperDailyNasForwardCacheError
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError
from thericher_v2.execution.kis_paper_daily_nas_forward import KisPaperDailyNasForwardError


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


def test_verified_current_cache_skips_configuration_client_and_page_requests(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()
    cache_payload = {
        "kind": "kis.paper.private.daily.nas.forward-v1",
        "index_sha256": "sha256:" + "a" * 64,
        "cache_sha256": "sha256:" + "b" * 64,
    }
    cached_row = SimpleNamespace(session_date=datetime(2026, 7, 28, tzinfo=UTC).date())
    cache = SimpleNamespace(
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        rows_by_symbol={
            symbol: (cached_row,) for symbol in script.KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
        safe_payload=lambda: cache_payload,
    )

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("verified cache no-op must not construct a KIS path")

    monkeypatch.setattr(
        script,
        "load_verified_kis_paper_daily_nas_forward_cache",
        lambda **_kwargs: cache,
    )
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", unexpected)
    monkeypatch.setattr(script, "collect_kis_paper_daily_nas_forward_once", unexpected)
    receipt_inputs: dict[str, object] = {}

    def record_receipt(**kwargs: object) -> str:
        receipt_inputs.update(kwargs)
        return "sha256:" + "f" * 64

    monkeypatch.setattr(script, "_write_source_safe_receipt", record_receipt)

    exit_code = script.main(
        ["--preflight"],
        clock=lambda: datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output == {
        "cache": cache_payload,
        "configuration_loaded": False,
        "eligible_through_session": "2026-07-28",
        "market_data_request_attempt_count": 0,
        "observed_at_bucket": "2026-07-29T01:00Z",
        "reason": "verified_forward_cache_covers_latest_completed_session",
        "receipt_sha256": "sha256:" + "f" * 64,
        "route_isolation": {
            "account_endpoints_used": False,
            "daily_market_data_only": True,
            "live_endpoints_used": False,
            "order_endpoints_used": False,
        },
        "status": "unchanged",
    }
    receipt_payload = receipt_inputs["payload"]
    assert isinstance(receipt_payload, dict)
    assert receipt_payload["status"] == "unchanged"
    assert "receipt_sha256" not in receipt_payload


def test_preflight_process_propagates_collection_required_exit_code() -> None:
    project_root = Path(__file__).parents[1]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(project_root / "src")

    completed = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "collect_kis_paper_daily_nas_forward.py"),
            "--preflight",
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 10
    assert json.loads(completed.stdout)["status"] == "collection_required"


def test_partial_collection_returns_recovery_exit_before_the_scheduler_can_observe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "collect_kis_paper_daily_nas_forward_once",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="partial",
            safe_payload=lambda: {"status": "partial"},
        ),
    )
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs) or "sha256:" + "a" * 64,
    )

    exit_code = script._run_credentialed_collection(  # noqa: SLF001
        cache_root=tmp_path / "cache",
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert exit_code == 20
    assert emitted["payload"] == {"status": "partial"}


@pytest.mark.parametrize(
    ("error", "expected_reason"),
    [
        (
            KisPaperDailyNasForwardCacheError("opaque-cache-marker"),
            "nas_forward_cache_unavailable",
        ),
        (
            KisPaperMarketDataError("opaque-provider-body-marker"),
            "nas_forward_market_data_unavailable",
        ),
        (
            KisPaperDailyNasForwardError("opaque-collector-marker"),
            "nas_forward_collector_unavailable",
        ),
        (OSError("opaque-runtime-marker"), "nas_forward_runtime_unavailable"),
        (ValueError("opaque-value-marker"), "nas_forward_runtime_unavailable"),
    ],
)
def test_credentialed_collection_uses_only_allowlisted_failure_categories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: BaseException,
    expected_reason: str,
) -> None:
    script = _script_module()
    emitted: dict[str, object] = {}

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())

    def fail_collection(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(script, "collect_kis_paper_daily_nas_forward_once", fail_collection)
    monkeypatch.setattr(
        script,
        "_write_source_safe_receipt",
        lambda **kwargs: emitted.update(kwargs) or "sha256:" + "a" * 64,
    )

    exit_code = script._run_credentialed_collection(  # noqa: SLF001
        cache_root=tmp_path / "cache",
        control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repository",
        frozen_boundary=datetime(2026, 7, 24, tzinfo=UTC).date(),
        observed_at=datetime(2026, 7, 29, tzinfo=UTC),
    )

    payload = emitted["payload"]
    assert isinstance(payload, dict)
    assert exit_code == 20
    assert payload["reason"] == expected_reason
    assert payload["reason"] in script._COLLECTOR_UNAVAILABLE_REASONS
    assert "nas_forward_collection_unavailable" not in json.dumps(payload)
    assert str(error) not in json.dumps(payload)


def test_compose_profile_splits_credentialed_collection_from_uncredentialed_preflight() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    collector_section = compose.split("\n  kis-paper-daily-nas-forward:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-nas-forward-preflight:\n",
        maxsplit=1,
    )[0]
    preflight_section = compose.split(
        "\n  kis-paper-daily-nas-forward-preflight:\n", maxsplit=1
    )[1].split(
        "\n  kis-paper-daily-spy-head:\n",
        maxsplit=1,
    )[0]

    assert 'profiles: ["kis-paper-daily-nas-forward"]' in collector_section
    assert "collect_kis_paper_daily_nas_forward.py" in collector_section
    assert "collection-control-v1:/app/collection_control" in collector_section
    assert "KIS_PAPER_APP_KEY" in collector_section
    assert "KIS_PAPER_APP_SECRET" in collector_section
    assert 'profiles: ["kis-paper-daily-nas-forward"]' in preflight_section
    assert "read_only: true" in preflight_section
    assert "--preflight" in preflight_section
    assert "daily-nas-forward/v1:/app/market_data" in preflight_section
    assert "data/kis-paper-daily-nas-forward-v1:/app/model_artifacts" in preflight_section
    assert "collection-control-v1" not in preflight_section
    assert "KIS_PAPER" not in preflight_section
    assert "KIS_LIVE" not in preflight_section
    assert "order" not in preflight_section.lower()


def test_compose_observer_is_network_disabled_and_credential_free() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    observer_section = compose.split(
        "\n  kis-paper-daily-nas-forward-observation:\n", maxsplit=1
    )[1].split("\n  kis-paper-daily-spy-head:\n", maxsplit=1)[0]

    assert 'profiles: ["kis-paper-daily-nas-forward"]' in observer_section
    assert "target: research" in observer_section
    assert "network_mode: none" in observer_section
    assert "read_only: true" in observer_section
    assert "gpus: all" in observer_section
    assert "run_kis_nas_d1_volatility_trend_prospective_observation.py" in observer_section
    assert "/app/market_data:ro" in observer_section
    assert "/app/model_artifacts" in observer_section
    assert "KIS_PAPER" not in observer_section
    assert "KIS_LIVE" not in observer_section
    assert "order" not in observer_section.lower()


def test_preflight_cache_recovery_failure_writes_a_source_safe_receipt_without_kis(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()
    captured: dict[str, object] = {}

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("preflight must not construct a KIS path")

    def fail_reattest(*_args: object, **_kwargs: object) -> object:
        raise KisPaperDailyNasForwardCacheError("forward duplicate conflict")

    def record_receipt(**kwargs: object) -> str:
        captured.update(kwargs)
        return "sha256:" + "f" * 64

    monkeypatch.setattr(script, "load_verified_kis_paper_daily_nas_forward_cache", fail_reattest)
    monkeypatch.setattr(script, "_cache_index_exists", lambda _root: True)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", unexpected)
    monkeypatch.setattr(script, "collect_kis_paper_daily_nas_forward_once", unexpected)
    monkeypatch.setattr(script, "_write_source_safe_receipt", record_receipt)

    exit_code = script.main(["--preflight"], clock=lambda: datetime(2026, 7, 29, tzinfo=UTC))

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 20
    assert output["status"] == "unavailable"
    assert output["reason"] == "forward_cache_reattest_unavailable"
    assert output["receipt_sha256"] == "sha256:" + "f" * 64
    assert "duplicate" not in json.dumps(output)
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["recovery"] == "reconcile"
    assert payload["credentials_in_payload"] is False
    assert payload["account_or_order_data_in_payload"] is False


def test_preflight_timing_guard_writes_a_source_safe_recovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()
    captured: dict[str, object] = {}

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("timing guard must not touch cache or KIS")

    def record_receipt(**kwargs: object) -> str:
        captured.update(kwargs)
        return "sha256:" + "e" * 64

    monkeypatch.setattr(script, "load_verified_kis_paper_daily_nas_forward_cache", unexpected)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", unexpected)
    monkeypatch.setattr(script, "_write_source_safe_receipt", record_receipt)

    exit_code = script.main(
        ["--preflight", "--schedule-guard-failed", "host_timezone_not_kst"],
        clock=lambda: datetime(2026, 7, 29, tzinfo=UTC),
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 20
    assert output["reason"] == "host_timezone_not_kst"
    assert output["receipt_sha256"] == "sha256:" + "e" * 64
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["configuration_loaded"] is False
    assert payload["market_data_request_attempt_count"] == 0


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
