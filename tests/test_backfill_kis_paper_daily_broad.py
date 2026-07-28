from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.execution.kis_paper_daily_broad_backfill import (
    KisPaperDailyBroadBackfillRun,
)


def test_requires_explicit_execution_without_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()

    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("credentials must stay unread without --execute"),
    )

    assert script.main([]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_rejects_noncanonical_roots_before_registry_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid roots must not reach registry, credentials, or network setup")

    monkeypatch.setattr(script, "build_kis_paper_daily_broad_registry", unexpected)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    assert script.main(["--execute", "--cache-root", "/tmp/market-data"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "canonical_container_roots_required",
    }


def test_preflight_is_source_safe_and_does_not_construct_kis_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    registry = _registry()

    monkeypatch.setattr(script, "build_kis_paper_daily_broad_registry", lambda **_kwargs: registry)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("preflight must not load credentials"),
    )
    monkeypatch.setattr(
        script,
        "KisPaperMarketDataClient",
        lambda **_kwargs: pytest.fail("preflight must not construct a KIS client"),
    )

    assert script.main(["--preflight"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "bootstrap_target_count": 8,
        "configuration_loaded": False,
        "market_data_request_attempt_count": 0,
        "registry_filename": "kis-paper-daily-broad-registry.json",
        "registry_sha256": registry.registry_sha256,
        "route_isolation": {
            "account_endpoints_used": False,
            "daily_market_data_only": True,
            "live_endpoints_used": False,
            "order_endpoints_used": False,
            "position_endpoints_used": False,
        },
        "scope": {
            "current_listing_only": True,
            "non_pit": True,
            "non_ranking": True,
            "provider_price_data": False,
        },
        "status": "ready",
        "target_count": 12,
    }


def test_execute_uses_environment_only_client_and_bounded_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    registry = _registry()
    observed: dict[str, object] = {}
    constructed: list[object] = []

    class FakeGate:
        def __init__(self, *, control_root: Path) -> None:
            constructed.append(control_root)

    class FakeTransport:
        def __init__(self, **_kwargs: object) -> None:
            constructed.append("transport")

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            constructed.append("client")

    def run_worker(**kwargs: object) -> KisPaperDailyBroadBackfillRun:
        observed.update(kwargs)
        kwargs["client_factory"]()
        return _run(bootstrap_only=bool(kwargs["bootstrap_only"]))

    monkeypatch.setattr(script, "build_kis_paper_daily_broad_registry", lambda **_kwargs: registry)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", FakeTransport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", FakeClient)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(script, "run_kis_paper_daily_broad_backfill", run_worker)

    observed_at = datetime(2026, 7, 29, 1, 0, tzinfo=UTC)
    assert script.main(
        ["--execute", "--max-chunks", "8", "--max-runtime-seconds", "300"],
        clock=lambda: observed_at,
        code_revision=lambda _root: "git:test",
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "collected"
    assert payload["bootstrap_only"] is True
    assert payload["accepted_page_count"] == 8
    assert "targets" not in payload
    assert observed["registry"] is registry
    assert observed["cache_root"] == Path("/app/market_data")
    assert observed["max_chunks"] == 8
    assert observed["max_runtime"].total_seconds() == 300
    assert observed["code_revision"] == "git:test"
    assert constructed == [
        Path("/app/collection_control"),
        Path("/app/collection_control"),
        "transport",
        "client",
    ]


def test_continuation_mode_is_explicit_and_source_has_no_account_or_live_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    registry = _registry()
    observed: dict[str, object] = {}

    class FakeGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

    monkeypatch.setattr(script, "build_kis_paper_daily_broad_registry", lambda **_kwargs: registry)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", lambda **_kwargs: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(
        script,
        "run_kis_paper_daily_broad_backfill",
        lambda **kwargs: observed.update(kwargs) or _run(bootstrap_only=False),
    )

    assert script.main(["--execute", "--continuation"], code_revision=lambda _root: "git:test") == 0
    assert observed["bootstrap_only"] is False
    script_path = Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_daily_broad.py"
    source = script_path.read_text(encoding="utf-8")
    assert "KIS_PAPER_ACCOUNT_" not in source
    assert "KIS_LIVE_" not in source
    assert ".env" not in source
    assert json.loads(capsys.readouterr().out)["bootstrap_only"] is False


def test_compose_profile_and_schedule_runner_stay_data_only_and_restartable() -> None:
    project_root = Path(__file__).parents[1]
    compose = (project_root / "docker-compose.yml").read_text(encoding="utf-8")
    section = compose.split("\n  kis-paper-daily-broad-backfill:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-nas-forward:\n", maxsplit=1
    )[0]
    runner = (project_root / "scripts" / "run_kis_paper_daily_broad_schedule.ps1").read_text(
        encoding="ascii"
    )

    assert 'profiles: ["kis-paper-daily-broad-backfill"]' in section
    assert "backfill_kis_paper_daily_broad.py" in section
    assert "--bootstrap-only" in section
    assert "/app/symbol_directory" in section
    assert "KIS_PAPER_APP_KEY" in section
    assert "KIS_PAPER_APP_SECRET" in section
    assert "KIS_PAPER_ACCOUNT" not in section
    assert "KIS_LIVE" not in section
    assert "--continuation" in runner
    assert "--max-chunks 24000" in runner
    assert "--max-runtime-seconds 50400" in runner
    assert "Start-Sleep" not in runner
    assert "KIS_PAPER_ACCOUNT" not in runner
    assert "KIS_LIVE" not in runner


def _registry() -> SimpleNamespace:
    return SimpleNamespace(
        registry_sha256="sha256:" + "a" * 64,
        targets=tuple(range(12)),
        bootstrap_targets=tuple(range(8)),
    )


def _run(*, bootstrap_only: bool) -> KisPaperDailyBroadBackfillRun:
    observed_at = datetime(2026, 7, 29, 1, 0, tzinfo=UTC)
    return KisPaperDailyBroadBackfillRun(
        status="collected",
        observed_at=observed_at,
        completed_at=observed_at,
        registry_sha256="sha256:" + "a" * 64,
        target_states=(),
        bootstrap_only=bootstrap_only,
        chunk_attempt_count=8,
        accepted_page_count=8,
        categorical_failure_count=0,
        remaining_target_count=4,
        next_due=None,
        recovery="resume",
        evidence_sha256="sha256:" + "b" * 64,
    )


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_daily_broad.py"
    specification = importlib.util.spec_from_file_location(
        "backfill_kis_paper_daily_broad_for_test",
        script_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
