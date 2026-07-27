from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_paper_daily_history import (
    KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256,
    KisPaperDailyHistoryRun,
    KisPaperDailyHistoryTargetState,
)


def test_history_script_requires_explicit_execution_without_loading_credentials(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    script.main(["--cache-root", "/tmp/ignored-without-execute"])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


@pytest.mark.parametrize(
    ("flag", "noncanonical_root"),
    (
        ("--cache-root", "/tmp/market-data"),
        ("--control-root", "/tmp/control"),
        ("--artifact-root", "/tmp/artifacts"),
        ("--repository-root", "/tmp/repository"),
    ),
)
def test_history_script_rejects_noncanonical_execute_roots_before_config_or_network(
    monkeypatch,
    capsys,
    flag: str,
    noncanonical_root: str,
) -> None:
    script = _load_script()

    def unexpected(*_: object, **__: object) -> object:
        raise AssertionError("credentials or network setup must stay untouched")

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", unexpected)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", unexpected)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", unexpected)
    monkeypatch.setattr(script, "UrllibKisPaperDailyHistoryTransport", unexpected)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", unexpected)
    monkeypatch.setattr(script, "run_kis_paper_daily_history_collection", unexpected)
    arguments = [
        "--execute",
        "--cache-root",
        "/app/market_data",
        "--control-root",
        "/app/collection_control",
        "--artifact-root",
        "/app/model_artifacts",
        "--repository-root",
        "/app",
    ]
    arguments[arguments.index(flag) + 1] = noncanonical_root

    script.main(arguments)

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "canonical_container_roots_required",
    }


def test_history_script_uses_environment_only_configuration_and_safe_output(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    repo_root = Path("/app")
    cache_root = Path("/app/market_data")
    control_root = Path("/app/collection_control")
    artifact_root = Path("/app/model_artifacts")
    observed_at = datetime(2026, 7, 27, 1, 0, tzinfo=UTC)
    observed: dict[str, object] = {}
    gate_roots: list[Path] = []

    class FakeGate:
        def __init__(self, *, control_root: Path) -> None:
            gate_roots.append(control_root)

    class FakeTransport:
        def __init__(self, **_: object) -> None:
            pass

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(script, "UrllibKisPaperDailyHistoryTransport", FakeTransport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", FakeClient)

    def run_collection(**kwargs: object) -> KisPaperDailyHistoryRun:
        observed.update(kwargs)
        assert callable(kwargs["client_factory"])
        kwargs["client_factory"]()
        states = tuple(
            KisPaperDailyHistoryTargetState(
                target_key=key,
                state="ready",
                cursor_date="20260101",
                accepted_page_count=2,
                categorical_failure_count=0,
                coverage_bucket="2026-Q1",
                last_reason=None,
            )
            for key in ("AAPL/NAS", "AMZN/NAS", "GOOGL/NAS", "META/NAS", "MSFT/NAS", "NVDA/NAS")
        )
        return KisPaperDailyHistoryRun(
            status="collected",
            observed_at=observed_at,
            completed_at=observed_at,
            target_states=states,
            accepted_page_count=12,
            categorical_failure_count=0,
            chunk_attempt_count=6,
            measured_accepted_pages_per_minute=60.0,
            remaining_page_estimate=None,
            eta_bucket="unknown",
            next_due=None,
            recovery="resume",
            registry_sha256=KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256,
            evidence_sha256="sha256:" + "a" * 64,
        )

    monkeypatch.setattr(script, "run_kis_paper_daily_history_collection", run_collection)
    script.main(
        [
            "--execute",
            "--cache-root",
            str(cache_root),
            "--control-root",
            str(control_root),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repo_root),
            "--max-chunks",
            "6",
            "--max-runtime-seconds",
            "120",
        ],
        clock=lambda: observed_at,
        code_revision=lambda _: "git:test",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "collected"
    assert payload["accepted_page_count"] == 12
    assert payload["remaining_page_estimate"] is None
    assert payload["targets"][0]["target_key"] == "AAPL/NAS"
    assert observed["cache_root"] == cache_root
    assert observed["evidence_root"] == artifact_root
    assert observed["max_chunks"] == 6
    assert gate_roots == [control_root, control_root]
    assert "dotenv" not in script.__dict__


def test_daily_history_docker_profile_is_data_only_and_dedicated() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    section = compose.split("\n  kis-paper-daily-history:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-spy-head:\n", maxsplit=1
    )[0]

    assert 'profiles: ["kis-paper-daily-history"]' in section
    assert "collect_kis_paper_daily_history.py" in section
    assert "      - --cache-root\n      - /app/market_data" in section
    assert "      - --control-root\n      - /app/collection_control" in section
    assert "      - --artifact-root\n      - /app/model_artifacts" in section
    assert "      - --repository-root\n      - /app" in section
    assert "THERICHER_MODE: off" in section
    assert "read_only: true" in section
    assert "- /tmp" in section
    assert "KIS_PAPER_APP_KEY" in section
    assert "KIS_PAPER_APP_SECRET" in section
    assert "KIS_PAPER_ACCOUNT" not in section
    assert "KIS_LIVE" not in section
    assert "kis-readonly" not in section
    assert "canary" not in section
    assert "session" not in section
    assert "/app/runtime" not in section
    assert "thericher-v2-runtime" not in section
    assert "emergency" not in section
    assert "/app/private" not in section
    assert "${THERICHER_HOST_MARKET_DATA_ROOT:-D:/market_data}:/app/market_data" not in section
    assert "/daily-nas-history/v1:/app/market_data" in section
    assert "/collection-control-v1:/app/collection_control" in section
    assert "/data/kis-paper-daily-nas-history-v1:/app/model_artifacts" in section


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_daily_history.py"
    spec = importlib.util.spec_from_file_location(
        "collect_kis_paper_daily_history_for_test", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
