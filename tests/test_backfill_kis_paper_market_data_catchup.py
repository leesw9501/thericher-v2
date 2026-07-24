from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_private_daily_backfill import KisPaperPrivateDailyBackfillRun


def test_catchup_script_requires_explicit_execution_without_loading_credentials(
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


def test_catchup_does_not_read_credentials_after_the_daily_cursor_is_drained(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("drained cursor must stay offline")),
    )

    def no_ready(**kwargs: object) -> KisPaperPrivateDailyBackfillRun:
        assert callable(kwargs["client_factory"])
        return KisPaperPrivateDailyBackfillRun(status="no_ready_target")

    monkeypatch.setattr(script, "run_kis_paper_private_daily_backfill_once", no_ready)

    script.main(
        [
            "--execute",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--repository-root",
            str(tmp_path / "repo"),
        ],
        code_revision=lambda _: "git:test",
    )

    assert json.loads(capsys.readouterr().out) == {
        "chunk_attempt_count": 0,
        "completed_target_count": 0,
        "reason": None,
        "retained_chunk_count": 0,
        "status": "drained",
    }


def test_catchup_reuses_one_paper_client_within_its_finite_budget(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    configurations_loaded = 0
    received_clients: list[object] = []
    runs = iter(("collected", "no_ready_target"))

    def load_config(_: Path) -> KisPaperMarketDataConfig:
        nonlocal configurations_loaded
        configurations_loaded += 1
        return KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret")

    def run_once(**kwargs: object) -> KisPaperPrivateDailyBackfillRun:
        client_factory = kwargs["client_factory"]
        assert callable(client_factory)
        received_clients.append(client_factory())
        status = next(runs)
        return KisPaperPrivateDailyBackfillRun(
            status=status,  # type: ignore[arg-type]
            target_key="QQQ/NAS/MODP=0" if status == "collected" else None,
        )

    monkeypatch.setattr(script, "load_kis_paper_market_data_config", load_config)
    monkeypatch.setattr(script, "run_kis_paper_private_daily_backfill_once", run_once)

    script.main(
        [
            "--execute",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--repository-root",
            str(tmp_path / "repo"),
            "--max-chunks",
            "2",
        ],
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    )

    assert configurations_loaded == 1
    assert received_clients[0] is received_clients[1]
    assert json.loads(capsys.readouterr().out) == {
        "chunk_attempt_count": 1,
        "completed_target_count": 0,
        "reason": None,
        "retained_chunk_count": 0,
        "status": "drained",
    }


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_market_data_catchup.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_kis_paper_market_data_catchup_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
