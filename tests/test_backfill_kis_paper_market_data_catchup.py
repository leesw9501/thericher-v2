from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_market_data_catchup import (
    KisPaperMarketDataCatchupResult,
)
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


def test_catchup_writes_an_external_source_safe_receipt_for_a_drained_run(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("drained cursor must stay offline")),
    )
    monkeypatch.setattr(
        script,
        "run_kis_paper_private_daily_backfill_once",
        lambda **_: KisPaperPrivateDailyBackfillRun(status="no_ready_target"),
    )

    script.main(
        [
            "--execute",
            "--cache-root",
            str(tmp_path / "market-data"),
            "--repository-root",
            str(repo_root),
            "--receipt-root",
            str(artifact_root),
        ],
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    )

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "drained"
    assert output["receipt_sha256"].startswith("sha256:")
    receipts = list(artifact_root.glob("catchup-*.json"))
    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert payload["kind"] == "kis_paper_market_data_catchup_receipt"
    assert payload["outcome"] == {
        "chunk_attempt_count": 0,
        "completed_target_count": 0,
        "reason": None,
        "retained_chunk_count": 0,
        "status": "drained",
    }
    assert payload["execution"]["client_constructed"] is False
    assert payload["artifact_policy"]["raw_market_data_in_receipt"] is False
    rendered = json.dumps(payload, sort_keys=True)
    assert "paper-key" not in rendered
    assert "paper-secret" not in rendered
    assert "market-data" not in rendered
    assert str(repo_root) not in rendered


def test_catchup_receipt_rejects_a_root_inside_git(tmp_path: Path) -> None:
    script = _load_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        script._write_source_safe_receipt(
            receipt_root=repo_root / "artifacts",
            repo_root=repo_root,
            code_revision="git:test",
            observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
            result=KisPaperMarketDataCatchupResult(
                status="drained",
                chunk_attempt_count=0,
                retained_chunk_count=0,
                completed_target_count=0,
            ),
            client_constructed=False,
            max_chunks=48,
            max_runtime_seconds=21600,
        )


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
