from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
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
    summaries: list[dict[str, object]] = []

    def write_summary(**kwargs: object) -> str:
        summaries.append(kwargs["summary"])
        return "sha256:" + "b" * 64

    monkeypatch.setattr(script, "_write_source_safe_continuation_summary", write_summary)

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
    assert observed["recover_deferred_targets"] is False
    assert gate_roots == [control_root, control_root]
    assert payload["continuation_summary_sha256"] == "sha256:" + "b" * 64
    assert summaries[0]["outcome"]["internal_cycle_count"] == 1
    assert summaries[0]["scope"]["recovery_target_keys"] == []
    assert "dotenv" not in script.__dict__


def test_history_script_passes_fixed_deferred_recovery_scope(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    observed_at = datetime(2026, 7, 27, 2, 40, tzinfo=UTC)
    observed: dict[str, object] = {}
    summaries: list[dict[str, object]] = []

    class FakeGate:
        def __init__(self, **_: object) -> None:
            pass

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(
        script,
        "_write_source_safe_continuation_summary",
        lambda **kwargs: summaries.append(kwargs["summary"]) or "sha256:" + "a" * 64,
    )

    def run_collection(**kwargs: object) -> KisPaperDailyHistoryRun:
        observed.update(kwargs)
        return _run(
            observed_at=observed_at,
            status="deferred",
            recovery="reconcile",
        )

    monkeypatch.setattr(script, "run_kis_paper_daily_history_collection", run_collection)
    script.main(
        _canonical_execute_args(
            max_chunks=2,
            max_runtime_seconds=30,
            recover_deferred_targets=True,
        ),
        clock=lambda: observed_at,
        monotonic_clock=lambda: 0.0,
        code_revision=lambda _: "git:test",
    )

    payload = json.loads(capsys.readouterr().out)
    assert observed["recover_deferred_targets"] is True
    assert summaries[0]["scope"]["recovery_target_keys"] == ["MSFT/NAS", "NVDA/NAS"]
    assert payload["continuation"]["stop_reason"] == "no_future_retry_due_observed"


def test_history_script_reuses_closure_client_after_retry_due(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    now = {"value": datetime(2026, 7, 27, 2, 0, tzinfo=UTC)}
    monotonic = {"value": 0.0}
    calls: list[dict[str, object]] = []
    sleeps: list[float] = []
    summaries: list[dict[str, object]] = []
    created_clients: list[object] = []

    class FakeGate:
        def __init__(self, **_: object) -> None:
            pass

    class FakeTransport:
        def __init__(self, **_: object) -> None:
            pass

    class FakeClient:
        secret = "must-not-appear-in-summary"

        def __init__(self, **_: object) -> None:
            created_clients.append(self)

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(script, "UrllibKisPaperDailyHistoryTransport", FakeTransport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", FakeClient)
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", lambda: object())

    def run_collection(**kwargs: object) -> KisPaperDailyHistoryRun:
        calls.append(kwargs)
        if len(calls) == 1:
            assert "client" not in kwargs
            assert kwargs["client_factory"]() is created_clients[0]
            return _run(
                observed_at=now["value"],
                status="deferred",
                accepted_page_count=2,
                categorical_failure_count=1,
                chunk_attempt_count=2,
                next_due=now["value"] + timedelta(seconds=5),
            )
        assert kwargs["client"] is created_clients[0]
        return _run(
            observed_at=now["value"],
            status="complete",
            accepted_page_count=1,
            categorical_failure_count=0,
            chunk_attempt_count=1,
            recovery="complete",
        )

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now["value"] += timedelta(seconds=seconds)
        monotonic["value"] += seconds

    def write_summary(**kwargs: object) -> str:
        summaries.append(kwargs["summary"])
        return "sha256:" + "c" * 64

    monkeypatch.setattr(script, "run_kis_paper_daily_history_collection", run_collection)
    monkeypatch.setattr(script, "_write_source_safe_continuation_summary", write_summary)

    script.main(
        _canonical_execute_args(max_chunks=6, max_runtime_seconds=30),
        clock=lambda: now["value"],
        sleeper=sleeper,
        monotonic_clock=lambda: monotonic["value"],
        code_revision=lambda _: "git:test",
    )

    payload = json.loads(capsys.readouterr().out)
    assert sleeps == [5.0]
    assert [call["max_chunks"] for call in calls] == [6, 4]
    assert payload["continuation"] == {
        "internal_cycle_count": 2,
        "cumulative_accepted_page_count": 3,
        "cumulative_categorical_failure_count": 1,
        "cumulative_chunk_attempt_count": 3,
        "retry_wait_count": 1,
        "client_reused_across_internal_cycles": True,
        "client_reuse_outcome": "reused_after_owned_retry_due",
        "stop_reason": "cache_complete",
    }
    rendered_summary = json.dumps(summaries[0], sort_keys=True)
    assert "must-not-appear-in-summary" not in rendered_summary
    assert summaries[0]["worker_bounds"] == {
        "max_total_runtime_seconds": 30.0,
        "max_global_chunks": 6,
        "max_daily_page_attempts": 12,
    }
    assert summaries[0]["route_isolation"]["order_endpoints_used"] is False
    assert summaries[0]["artifact_policy"]["credentials_in_summary"] is False


def test_history_script_enforces_global_chunk_budget(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    calls: list[dict[str, object]] = []
    observed_at = datetime(2026, 7, 27, 2, 10, tzinfo=UTC)

    class FakeGate:
        def __init__(self, **_: object) -> None:
            pass

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: (_ for _ in ()).throw(AssertionError("client must stay unconstructed")),
    )

    def run_collection(**kwargs: object) -> KisPaperDailyHistoryRun:
        calls.append(kwargs)
        return _run(
            observed_at=observed_at,
            status="collected",
            accepted_page_count=3,
            categorical_failure_count=0,
            chunk_attempt_count=3,
        )

    monkeypatch.setattr(script, "run_kis_paper_daily_history_collection", run_collection)
    monkeypatch.setattr(
        script,
        "_write_source_safe_continuation_summary",
        lambda **_: "sha256:" + "d" * 64,
    )

    script.main(
        _canonical_execute_args(max_chunks=3, max_runtime_seconds=30),
        clock=lambda: observed_at,
        monotonic_clock=lambda: 0.0,
        code_revision=lambda _: "git:test",
    )

    payload = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert calls[0]["max_chunks"] == 3
    assert payload["continuation"]["cumulative_chunk_attempt_count"] == 3
    assert payload["continuation"]["stop_reason"] == "global_chunk_budget_exhausted"


def test_history_script_enforces_global_runtime_before_retry_sleep(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    now = {"value": datetime(2026, 7, 27, 2, 20, tzinfo=UTC)}
    monotonic = {"value": 0.0}
    calls: list[dict[str, object]] = []

    class FakeGate:
        def __init__(self, **_: object) -> None:
            pass

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)

    def run_collection(**kwargs: object) -> KisPaperDailyHistoryRun:
        calls.append(kwargs)
        monotonic["value"] = 2.0
        return _run(
            observed_at=now["value"],
            status="deferred",
            accepted_page_count=1,
            categorical_failure_count=1,
            chunk_attempt_count=1,
            next_due=now["value"] + timedelta(seconds=5),
        )

    def unexpected_sleep(_: float) -> None:
        raise AssertionError("total runtime exhaustion must not enter a retry sleep")

    monkeypatch.setattr(script, "run_kis_paper_daily_history_collection", run_collection)
    monkeypatch.setattr(
        script,
        "_write_source_safe_continuation_summary",
        lambda **_: "sha256:" + "e" * 64,
    )

    script.main(
        _canonical_execute_args(max_chunks=5, max_runtime_seconds=1),
        clock=lambda: now["value"],
        sleeper=unexpected_sleep,
        monotonic_clock=lambda: monotonic["value"],
        code_revision=lambda _: "git:test",
    )

    payload = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert calls[0]["max_runtime"] == timedelta(seconds=1)
    assert payload["continuation"]["stop_reason"] == "global_runtime_exhausted"


def test_history_script_records_reconcile_summary_when_a_core_cycle_is_unavailable(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    observed_at = datetime(2026, 7, 27, 2, 25, tzinfo=UTC)
    summaries: list[dict[str, object]] = []

    class FakeGate:
        def __init__(self, **_: object) -> None:
            pass

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(
        script,
        "run_kis_paper_daily_history_collection",
        lambda **_: (_ for _ in ()).throw(script.KisPaperDailyHistoryError("unavailable")),
    )

    def write_summary(**kwargs: object) -> str:
        summaries.append(kwargs["summary"])
        return "sha256:" + "f" * 64

    monkeypatch.setattr(script, "_write_source_safe_continuation_summary", write_summary)
    script.main(
        _canonical_execute_args(max_chunks=5, max_runtime_seconds=30),
        clock=lambda: observed_at,
        monotonic_clock=lambda: 0.0,
        code_revision=lambda _: "git:test",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unavailable"
    assert payload["reason"] == "daily_history_unavailable"
    assert payload["recovery"] == "reconcile"
    assert payload["continuation"]["stop_reason"] == "worker_unavailable"
    assert summaries[0]["outcome"]["recovery"] == "reconcile"
    assert summaries[0]["targets"] == []


def test_continuation_summary_is_immutable_and_redacted(tmp_path: Path) -> None:
    script = _load_script()
    observed_at = datetime(2026, 7, 27, 2, 30, tzinfo=UTC)
    summary = script._source_safe_continuation_summary(
        started_at=observed_at,
        completed_at=observed_at,
        elapsed_seconds=5,
        runs=[_run(observed_at=observed_at, status="complete", recovery="complete")],
        max_chunks=4,
        max_total_runtime_seconds=120,
        recovery_target_keys=(),
        accepted_page_count=2,
        categorical_failure_count=0,
        chunk_attempt_count=1,
        retry_wait_count=0,
        client_reused_across_internal_cycles=True,
        stop_reason="cache_complete",
        final_run=_run(observed_at=observed_at, status="complete", recovery="complete"),
        recovery=None,
    )
    artifact_root = tmp_path / "external-artifacts"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    first_hash = script._write_source_safe_continuation_summary(
        artifact_root=artifact_root,
        repository_root=repository_root,
        summary=summary,
        observed_at=observed_at,
    )
    second_hash = script._write_source_safe_continuation_summary(
        artifact_root=artifact_root,
        repository_root=repository_root,
        summary=summary,
        observed_at=observed_at,
    )

    summaries = sorted(artifact_root.glob("continuation=*/summary.json"))
    assert len(summaries) == 2
    assert first_hash == second_hash
    rendered = summaries[0].read_text(encoding="utf-8")
    assert "KIS_PAPER_APP_KEY" not in rendered
    assert "must-not-appear-in-summary" not in rendered
    assert "raw_daily_rows" not in rendered
    document = json.loads(rendered)
    assert document["worker_bounds"] == {
        "max_total_runtime_seconds": 120,
        "max_global_chunks": 4,
        "max_daily_page_attempts": 8,
    }
    assert document["scope"]["recovery_target_keys"] == []
    assert document["artifact_policy"]["raw_market_data_in_summary"] is False
    assert document["artifact_policy"]["credentials_in_summary"] is False
    assert document["route_isolation"]["live_endpoints_used"] is False


def test_continuation_summary_rejects_git_storage_before_creating_a_path(tmp_path: Path) -> None:
    script = _load_script()
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = repository_root / "model-artifacts"

    with pytest.raises(ValueError, match="must stay outside"):
        script._write_source_safe_continuation_summary(
            artifact_root=artifact_root,
            repository_root=repository_root,
            summary={},
            observed_at=datetime(2026, 7, 27, 2, 35, tzinfo=UTC),
        )

    assert not artifact_root.exists()


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
    assert "      - --recover-deferred-targets" in section
    assert '      - --max-chunks\n      - "288"' in section
    assert '      - --max-runtime-seconds\n      - "1800"' in section
    assert "THERICHER_MODE: off" in section
    assert "read_only: true" in section
    assert "- /tmp" in section
    assert "KIS_PAPER_APP_KEY" in section
    assert "KIS_PAPER_APP_SECRET" in section
    assert "KIS_PAPER_ACCOUNT" not in section
    assert "KIS_LIVE" not in section
    assert "env_file:" not in section
    assert "ports:" not in section
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


def _canonical_execute_args(
    *,
    max_chunks: int,
    max_runtime_seconds: int,
    recover_deferred_targets: bool = False,
) -> list[str]:
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
        "--max-chunks",
        str(max_chunks),
        "--max-runtime-seconds",
        str(max_runtime_seconds),
    ]
    if recover_deferred_targets:
        arguments.append("--recover-deferred-targets")
    return arguments


def _run(
    *,
    observed_at: datetime,
    status: str,
    accepted_page_count: int = 0,
    categorical_failure_count: int = 0,
    chunk_attempt_count: int = 0,
    next_due: datetime | None = None,
    recovery: str = "resume",
) -> KisPaperDailyHistoryRun:
    return KisPaperDailyHistoryRun(
        status=status,
        observed_at=observed_at,
        completed_at=observed_at,
        target_states=tuple(
            KisPaperDailyHistoryTargetState(
                target_key=key,
                state="complete" if status == "complete" else "ready",
                cursor_date="20260101",
                accepted_page_count=accepted_page_count,
                categorical_failure_count=categorical_failure_count,
                coverage_bucket="2026-Q1",
                last_reason=None,
            )
            for key in ("AAPL/NAS", "AMZN/NAS", "GOOGL/NAS", "META/NAS", "MSFT/NAS", "NVDA/NAS")
        ),
        accepted_page_count=accepted_page_count,
        categorical_failure_count=categorical_failure_count,
        chunk_attempt_count=chunk_attempt_count,
        measured_accepted_pages_per_minute=None,
        remaining_page_estimate=None,
        eta_bucket="unknown",
        next_due=next_due,
        recovery=recovery,
        registry_sha256=KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256,
        evidence_sha256="sha256:" + "a" * 64,
    )
