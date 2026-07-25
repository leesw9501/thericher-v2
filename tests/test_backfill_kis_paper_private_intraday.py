from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.execution.kis_private_intraday_backfill import (
    KisPaperPrivateIntradayBackfillRun,
)


def test_intraday_backfill_script_requires_explicit_execution_without_credentials(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_load_paper_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )

    assert script.main([]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_intraday_project_only_writes_metadata_without_reading_credentials(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    projected: dict[str, object] = {}
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    monkeypatch.setattr(
        script,
        "_load_paper_config",
        lambda _: (_ for _ in ()).throw(AssertionError("credentials must stay unread")),
    )
    monkeypatch.setattr(
        script,
        "build_kis_paper_private_intraday_freshness_snapshot",
        lambda **kwargs: projected.setdefault("build", kwargs) or object(),
    )
    monkeypatch.setattr(
        script,
        "write_market_data_freshness_runtime",
        lambda snapshot, path: projected.update({"snapshot": snapshot, "path": path}),
    )

    projection_path = tmp_path / "runtime" / "freshness.json"
    script.main(
        ["--project-only", "--runtime-projection", str(projection_path)],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    )

    assert json.loads(capsys.readouterr().out) == {
        "scope": "backfill_and_head",
        "status": "freshness_projected",
    }
    assert projected["build"] == {
        "cache_root": tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday",
        "repo_root": script._REPO_ROOT,
        "observed_at": datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    }
    assert projected["path"] == projection_path


def test_intraday_backfill_script_uses_only_injected_paper_values(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("dotenv must stay unread")),
    )

    def paper_client(**kwargs: object) -> object:
        config = kwargs["config"]
        assert config.app_key == "paper-key"
        assert config.app_secret == "paper-secret"
        assert kwargs["max_minute_page_attempts"] == 2
        return object()

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["cache_root"] == (
            tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday"
        )
        assert kwargs["pages_per_target"] == 1
        assert kwargs["resume_cursor"] is True
        return (
            KisPaperPrivateIntradayBackfillRun(
                status="recovered",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="source_exhausted",
                target_key="SPY/AMS/1m",
                row_count=0,
                exact_overlap_rows=0,
                reason="source_exhausted",
            ),
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)

    assert script.main(
        ["--execute", "--pages-per-target", "1"],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    ) == 0

    assert json.loads(capsys.readouterr().out) == {
        "mode": "backfill",
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "recovered",
                "target_key": "QQQ/NAS/1m",
            },
            {
                "exact_overlap_rows": 0,
                "reason": "source_exhausted",
                "row_count": 0,
                "status": "source_exhausted",
                "target_key": "SPY/AMS/1m",
            }
        ],
    }


def test_intraday_head_script_uses_a_separate_cache_without_resuming_cursor(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("KIS_PAPER_ACCOUNT_NO", "must-not-reach-child")
    monkeypatch.setenv("KIS_LIVE_APP_KEY", "must-not-reach-child")
    monkeypatch.setenv("THERICHER_DASHBOARD_TOKEN", "must-not-reach-child")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    artifact_root = tmp_path / "model-artifacts"
    child_calls: list[tuple[list[str], dict[str, object]]] = []

    def paper_client(**_kwargs: object) -> object:
        return object()

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["cache_root"] == (
            tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday-head"
        )
        assert kwargs["pages_per_target"] == 1
        assert kwargs["resume_cursor"] is False
        return (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="SPY/AMS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)

    def prepare_child(command: list[str], **kwargs: object) -> SimpleNamespace:
        child_calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "pending",
                    "artifacts": {"precommit_path": "must-not-appear-in-parent-output"},
                }
            ),
        )

    monkeypatch.setattr(script.subprocess, "run", prepare_child)

    assert script.main(
        [
            "--execute",
            "--mode",
            "head",
            "--pages-per-target",
            "1",
            "--preparation-artifact-root",
            str(artifact_root),
        ],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    ) == 0

    output = capsys.readouterr().out
    assert "must-not-appear-in-parent-output" not in output
    assert json.loads(output) == {
        "mode": "head",
        "preparation": {"status": "pending"},
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "QQQ/NAS/1m",
            },
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "SPY/AMS/1m",
            }
        ],
    }
    assert len(child_calls) == 1
    command, kwargs = child_calls[0]
    assert command == [
        script.sys.executable,
        str(script._HEAD_PREPARATION_SCRIPT),
        "--run-label",
        script._HEAD_PREPARATION_RUN_LABEL,
        "--head-cache-root",
        str(tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday-head"),
        "--artifact-root",
        str(artifact_root),
    ]
    assert kwargs["cwd"] == script._REPO_ROOT
    assert kwargs["check"] is False
    assert kwargs["timeout"] == script._HEAD_PREPARATION_TIMEOUT_SECONDS
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["text"] is True
    child_environment = kwargs["env"]
    assert isinstance(child_environment, dict)
    assert set(child_environment) <= {"PATH", "PYTHONPATH", "SYSTEMROOT"}
    assert child_environment["PYTHONPATH"] == str(script._REPO_ROOT / "src")
    assert not any(
        "KIS" in name or "ACCOUNT" in name or "ORDER" in name or "LIVE" in name
        for name in child_environment
    )


@pytest.mark.parametrize(
    ("child_outcome", "expected_reason"),
    [
        (SimpleNamespace(returncode=1, stdout="ignored"), "child_exit_nonzero"),
        (subprocess.TimeoutExpired(["python"], 10), "child_timeout"),
        (SimpleNamespace(returncode=0, stdout="not-json"), "child_output_invalid"),
    ],
)
def test_intraday_head_preparation_unavailable_does_not_change_collection_or_freshness(
    monkeypatch,
    capsys,
    tmp_path: Path,
    child_outcome: object,
    expected_reason: str,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))
    freshness_writes: list[dict[str, object]] = []

    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "run_kis_paper_private_intraday_backfill_cycle",
        lambda **_kwargs: (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="SPY/AMS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        ),
    )
    monkeypatch.setattr(
        script,
        "_write_freshness_projection",
        lambda **kwargs: freshness_writes.append(kwargs),
    )

    def prepare_child(*_args: object, **_kwargs: object) -> SimpleNamespace:
        if isinstance(child_outcome, BaseException):
            raise child_outcome
        assert isinstance(child_outcome, SimpleNamespace)
        return child_outcome

    monkeypatch.setattr(script.subprocess, "run", prepare_child)
    runtime_projection = tmp_path / "runtime" / "freshness.json"

    assert script.main(
        [
            "--execute",
            "--mode",
            "head",
            "--runtime-projection",
            str(runtime_projection),
            "--preparation-artifact-root",
            str(tmp_path / "model-artifacts"),
        ],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    ) == 0

    assert json.loads(capsys.readouterr().out) == {
        "freshness_projection": "written",
        "mode": "head",
        "preparation": {
            "reason": expected_reason,
            "status": "preparation_unavailable",
        },
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "QQQ/NAS/1m",
            },
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "SPY/AMS/1m",
            }
        ],
    }
    assert freshness_writes == [
        {
            "cache_root": tmp_path
            / "market-data"
            / "us_equities"
            / "kis_paper_private"
            / "intraday",
            "runtime_projection": runtime_projection,
            "observed_at": datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        }
    ]


@pytest.mark.parametrize("failure_stage", ("config", "collector"))
def test_intraday_head_does_not_prepare_after_collector_failure(
    monkeypatch,
    capsys,
    failure_stage: str,
) -> None:
    script = _load_script()
    child_calls: list[object] = []

    def unexpected_child(*args: object, **kwargs: object) -> SimpleNamespace:
        child_calls.append((args, kwargs))
        raise AssertionError("preparation must not run after a collector failure")

    monkeypatch.setattr(script.subprocess, "run", unexpected_child)
    if failure_stage == "config":
        monkeypatch.setattr(
            script,
            "_load_paper_config",
            lambda _: (_ for _ in ()).throw(script.KisPaperMarketDataError("config_missing")),
        )
    else:
        monkeypatch.setattr(script, "_load_paper_config", lambda _: object())
        monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
        monkeypatch.setattr(
            script,
            "run_kis_paper_private_intraday_backfill_cycle",
            lambda **_kwargs: (_ for _ in ()).throw(
                script.KisPaperMarketDataError("auth_rejected")
            ),
        )

    assert script.main(
        ["--execute", "--mode", "head"],
        code_revision=lambda _: "git:test",
    ) == 1

    assert json.loads(capsys.readouterr().out) == {
        "reason": "config_missing" if failure_stage == "config" else "auth_rejected",
        "status": "not_executed",
    }
    assert child_calls == []


def test_intraday_head_prepares_for_collected_qqq_despite_other_target_failure(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    child_calls: list[object] = []
    monkeypatch.setattr(script, "_load_paper_config", lambda _: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "run_kis_paper_private_intraday_backfill_cycle",
        lambda **_kwargs: (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="rejected",
                target_key="SPY/AMS/1m",
                row_count=0,
                exact_overlap_rows=0,
                reason="collector_incomplete",
            ),
        ),
    )

    def prepare_child(*args: object, **kwargs: object) -> SimpleNamespace:
        child_calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"status": "pending"}))

    monkeypatch.setattr(script.subprocess, "run", prepare_child)

    assert script.main(
        ["--execute", "--mode", "head"],
        code_revision=lambda _: "git:test",
    ) == 1

    assert json.loads(capsys.readouterr().out) == {
        "mode": "head",
        "preparation": {"status": "pending"},
        "status": "incomplete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "QQQ/NAS/1m",
            },
            {
                "exact_overlap_rows": 0,
                "reason": "collector_incomplete",
                "row_count": 0,
                "status": "rejected",
                "target_key": "SPY/AMS/1m",
            },
        ],
    }
    assert len(child_calls) == 1


@pytest.mark.parametrize("status", ("locked", "partial", "rejected"))
def test_intraday_head_returns_nonzero_for_incomplete_collector_results(
    monkeypatch,
    capsys,
    status: str,
) -> None:
    script = _load_script()
    child_calls: list[object] = []
    monkeypatch.setattr(script, "_load_paper_config", lambda _: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        script,
        "run_kis_paper_private_intraday_backfill_cycle",
        lambda **_kwargs: (
            KisPaperPrivateIntradayBackfillRun(
                status=status,
                target_key="QQQ/NAS/1m",
                row_count=0,
                exact_overlap_rows=0,
                reason="collector_incomplete",
            ),
        ),
    )
    monkeypatch.setattr(
        script.subprocess,
        "run",
        lambda *args, **kwargs: child_calls.append((args, kwargs)),
    )

    assert script.main(
        ["--execute", "--mode", "head"],
        code_revision=lambda _: "git:test",
    ) == 1

    assert json.loads(capsys.readouterr().out) == {
        "mode": "head",
        "status": "incomplete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": "collector_incomplete",
                "row_count": 0,
                "status": status,
                "target_key": "QQQ/NAS/1m",
            }
        ],
    }
    assert child_calls == []


def test_intraday_script_module_entrypoint_forwards_main_exit_code() -> None:
    source = (
        Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_private_intraday.py"
    ).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":\n    raise SystemExit(main())' in source


def test_intraday_head_docker_profile_mounts_only_the_explicit_preparation_artifact_root() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    section = compose.split("\n  kis-paper-intraday-head:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "--preparation-artifact-root" in section
    assert "/app/model_artifacts" in section
    assert (
        "THERICHER_MODEL_ARTIFACT_ROOT: "
        "${THERICHER_MODEL_ARTIFACT_ROOT:-/app/model_artifacts}" in section
    )
    assert "THERICHER_HOST_MODEL_ARTIFACT_ROOT" in section
    assert "KIS_PAPER_ACCOUNT" not in section
    assert "KIS_LIVE" not in section


def test_intraday_historical_probe_uses_a_separate_cache_without_seed_cursor(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    script = _load_script()
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market-data"))

    def paper_client(**_kwargs: object) -> object:
        return object()

    def run_cycle(**kwargs: object) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
        assert kwargs["cache_root"] == (
            tmp_path
            / "market-data"
            / "us_equities"
            / "kis_paper_private"
            / "intraday-historical-probe"
        )
        assert kwargs["pages_per_target"] == 1
        assert kwargs["resume_cursor"] is False
        return (
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="QQQ/NAS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
            KisPaperPrivateIntradayBackfillRun(
                status="collected",
                target_key="SPY/AMS/1m",
                row_count=120,
                exact_overlap_rows=0,
            ),
        )

    monkeypatch.setattr(script, "KisPaperMarketDataClient", paper_client)
    monkeypatch.setattr(script, "run_kis_paper_private_intraday_backfill_cycle", run_cycle)

    script.main(
        ["--execute", "--mode", "historical-probe", "--pages-per-target", "1"],
        clock=lambda: datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        code_revision=lambda _: "git:test",
    )

    assert json.loads(capsys.readouterr().out) == {
        "mode": "historical-probe",
        "status": "complete",
        "targets": [
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "QQQ/NAS/1m",
            },
            {
                "exact_overlap_rows": 0,
                "reason": None,
                "row_count": 120,
                "status": "collected",
                "target_key": "SPY/AMS/1m",
            }
        ],
    }


def test_intraday_backfill_script_rejects_live_mode_before_reading_config(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setenv("THERICHER_MODE", "live")
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_config",
        lambda _: (_ for _ in ()).throw(AssertionError("config must stay unread")),
    )

    script.main(["--execute"])

    assert json.loads(capsys.readouterr().out) == {
        "reason": "config_missing",
        "status": "not_executed",
    }


def test_current_code_revision_marks_staged_or_untracked_work_dirty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    script = _load_script()
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="test-revision\n")
        assert args == ["git", "status", "--porcelain", "--untracked-files=normal"]
        return SimpleNamespace(stdout="M  staged-file.py\n")

    monkeypatch.setattr(script.subprocess, "run", run)

    assert script._current_code_revision(tmp_path) == "git:test-revision+dirty"
    assert calls == [
        ["git", "rev-parse", "HEAD"],
        ["git", "status", "--porcelain", "--untracked-files=normal"],
    ]


def _load_script() -> ModuleType:
    script_path = (
        Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_private_intraday.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_kis_paper_private_intraday_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
