from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from thericher_v2.execution.kis_private_daily_backfill import KisPaperPrivateDailyBackfillRun


def test_backfill_script_requires_explicit_execution_without_loading_credentials(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    script.main([])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_backfill_script_can_report_recovery_without_loading_credentials(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    observed_at = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("recovery must stay offline")),
    )

    def recover(**kwargs: object) -> KisPaperPrivateDailyBackfillRun:
        assert callable(kwargs["client_factory"])
        return KisPaperPrivateDailyBackfillRun(
            status="recovered",
            target_key="QQQ/NAS/MODP=0",
            manifest_path=Path("D:/market_data/us_equities/kis_paper_private/daily/snapshot=unit/manifest.json"),
            manifest_hash="sha256:unit",
            row_count=2,
        )

    monkeypatch.setattr(script, "run_kis_paper_private_daily_backfill_once", recover)

    script.main(["--execute"], clock=lambda: observed_at, code_revision=lambda _: "git:test")

    assert json.loads(capsys.readouterr().out) == {
        "manifest_hash": "sha256:unit",
        "manifest_path": (
            "D:\\market_data\\us_equities\\kis_paper_private\\daily\\snapshot=unit\\manifest.json"
        ),
        "reason": None,
        "row_count": 2,
        "status": "recovered",
        "target_key": "QQQ/NAS/MODP=0",
    }


def test_backfill_script_forwards_container_safe_cache_and_repository_paths(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    cache_root = tmp_path / "market-data"
    repository_root = tmp_path / "repository"
    cache_root.mkdir()
    repository_root.mkdir()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("recovery must stay offline")),
    )

    def recover(**kwargs: object) -> KisPaperPrivateDailyBackfillRun:
        assert kwargs["cache_root"] == cache_root
        assert kwargs["repo_root"] == repository_root
        return KisPaperPrivateDailyBackfillRun(status="no_ready_target")

    monkeypatch.setattr(script, "run_kis_paper_private_daily_backfill_once", recover)

    script.main(
        [
            "--execute",
            "--cache-root",
            str(cache_root),
            "--repository-root",
            str(repository_root),
        ],
        code_revision=lambda _: "git:test",
    )

    assert json.loads(capsys.readouterr().out) == {
        "manifest_hash": None,
        "manifest_path": None,
        "reason": None,
        "row_count": 0,
        "status": "no_ready_target",
        "target_key": None,
    }


def test_daily_catchup_docker_profile_is_data_only() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    section = compose.split("\n  kis-paper-daily-backfill:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-spy-head:\n", maxsplit=1
    )[0]

    assert 'profiles: ["kis-paper-daily-backfill"]' in section
    assert "backfill_kis_paper_market_data_catchup.py" in section
    assert "--max-chunks" in section
    assert '"48"' in section
    assert "--max-runtime-seconds" in section
    assert "/app/market_data/us_equities/kis_paper_private/daily" in section
    assert "KIS_PAPER_APP_KEY" in section
    assert "KIS_PAPER_APP_SECRET" in section
    assert "KIS_PAPER_ACCOUNT" not in section
    assert "KIS_LIVE" not in section
    assert ":/app/market_data" in section


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_private_daily.py"
    spec = importlib.util.spec_from_file_location(
        "backfill_kis_paper_private_daily_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
