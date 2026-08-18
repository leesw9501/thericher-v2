from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.data import kis_paper_intraday_capture_topology as topology
from thericher_v2.data.kis_intraday_head_coverage import (
    KisIntradayHeadCoverage,
    KisIntradayHeadSessionCoverage,
)
from thericher_v2.data.kis_paper_intraday_index_metadata import (
    KisPaperPrivateIntradayV1RetainedChunkMetadata,
)

_KOREA = ZoneInfo("Asia/Seoul")
_SCRIPT = Path(__file__).parents[1] / "scripts" / "inspect_kis_paper_intraday_capture_topology.py"
_POWERSHELL_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "inspect_kis_paper_intraday_capture_topology.ps1"
)


def test_audit_reports_missing_retained_slots_without_claiming_a_scheduler_miss(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 17)
    coverage = _coverage(session_date=session_date)
    chunks = (
        _chunk(
            session_date=session_date,
            start_offset=0,
            count=120,
            collected_hour=11,
            collected_minute=31,
        ),
        _chunk(
            session_date=session_date,
            start_offset=350,
            count=40,
            collected_hour=17,
            collected_minute=20,
        ),
    )
    monkeypatch.setattr(
        topology,
        "inspect_kis_paper_private_intraday_head_coverage",
        lambda **_kwargs: coverage,
    )
    monkeypatch.setattr(topology, "_read_qqq_head_chunks", lambda **_kwargs: chunks)

    result = topology.inspect_kis_paper_intraday_capture_topology(
        cache_root=tmp_path / "market-data",
        repository_root=tmp_path / "repository",
        task_facts=_task_facts(),
        after_session_date=date(2026, 8, 16),
        required_complete_session_count=5,
    )

    payload = result.to_payload()
    assert payload["evidence_status"] == "run_or_persistence_unresolved"
    assert payload["recommendation"].startswith("add source-safe start and terminal")
    assert payload["limitations"]["missing_retained_chunk_proves_scheduler_miss"] is False
    session = payload["sessions"][0]
    assert session["retained_slots"] == ["11:29", "17:20"]
    assert session["unretained_or_unstarted_slots"] == ["13:28", "15:24"]
    assert session["retained_chunks"][0]["terminal_page"] is True
    assert session["retained_chunks"][1]["terminal_page"] is True
    assert payload["task_scheduler"]["operational_log_state"] == "disabled"


def test_task_facts_require_one_safe_trigger() -> None:
    with pytest.raises(ValueError, match="triggers"):
        topology.KisPaperIntradayCaptureTaskFacts(
            task_name=topology.KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_TASK_NAME,
            state="Ready",
            enabled=True,
            action_count=1,
            trigger_start_boundaries=(),
            last_run_at=None,
            next_run_at=None,
            last_task_result=0,
            missed_run_count=0,
            operational_log_state="disabled",
        )


def test_python_audit_script_emits_safe_not_created_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    repository_root = tmp_path / "repository"
    cache_root = tmp_path / "market-data"
    repository_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", repository_root)

    assert (
        script.main(
            [
                "--head-cache-root",
                str(cache_root),
                "--task-name",
                topology.KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_TASK_NAME,
                "--task-state",
                "Ready",
                "--task-enabled",
                "true",
                "--task-action-count",
                "1",
                "--trigger-start-boundary",
                "2026-08-18T15:29:00Z",
                "--last-task-result",
                "0",
                "--missed-run-count",
                "0",
                "--operational-log-state",
                "disabled",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["evidence_status"] == "not_created"
    assert payload["limitations"]["raw_market_data_read"] is False
    assert (
        payload["task_scheduler"]["task_name"]
        == topology.KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_TASK_NAME
    )


def test_powershell_wrapper_is_read_only_and_credential_free() -> None:
    source = _POWERSHELL_SCRIPT.read_text(encoding="ascii").lower()

    assert "get-scheduledtask" in source
    assert "get-scheduledtaskinfo" in source
    assert "wevtutil.exe gl" in source
    assert "inspect_kis_paper_intraday_capture_topology.py" in source
    assert "docker" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_live" not in source
    assert "start-scheduledtask" not in source


def _task_facts() -> topology.KisPaperIntradayCaptureTaskFacts:
    return topology.KisPaperIntradayCaptureTaskFacts(
        task_name=topology.KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_TASK_NAME,
        state="Ready",
        enabled=True,
        action_count=1,
        trigger_start_boundaries=tuple(
            datetime(2026, 8, 18, hour, minute, tzinfo=_KOREA).astimezone(UTC)
            for hour, minute in ((0, 29), (2, 28), (4, 24), (6, 20))
        ),
        last_run_at=datetime(2026, 8, 18, 15, 29, tzinfo=UTC),
        next_run_at=datetime(2026, 8, 18, 17, 28, tzinfo=UTC),
        last_task_result=0,
        missed_run_count=0,
        operational_log_state="disabled",
    )


def _coverage(*, session_date: date) -> KisIntradayHeadCoverage:
    return KisIntradayHeadCoverage(
        status="available",
        target_key="QQQ/NAS/1m",
        required_complete_session_count=5,
        index_generation=1,
        index_metadata_sha256="sha256:" + "a" * 64,
        retained_chunk_count=2,
        last_reason_category="none",
        last_conflict_origin="none",
        continuation_category="terminal",
        exact_overlap_row_count=0,
        exact_overlap_category="none",
        conflicting_overlap_category="none",
        session_coverage=(
            KisIntradayHeadSessionCoverage(
                session_date=session_date,
                expected_minute_count=390,
                complete_minute_count=160,
                missing_minute_ranges=((120, 349),),
            ),
        ),
    )


def _chunk(
    *,
    session_date: date,
    start_offset: int,
    count: int,
    collected_hour: int,
    collected_minute: int,
) -> KisPaperPrivateIntradayV1RetainedChunkMetadata:
    session_open = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        13,
        30,
        tzinfo=UTC,
    )
    rows = tuple(
        (
            (session_open + timedelta(minutes=offset)).astimezone(_KOREA).strftime("%Y%m%dT%H%M%S"),
            "sha256:" + f"{offset:064x}",
        )
        for offset in range(start_offset, start_offset + count)
    )
    return KisPaperPrivateIntradayV1RetainedChunkMetadata(
        chunk_key="sha256:" + "b" * 64,
        manifest_hash="sha256:" + "c" * 64,
        raw_sha256="sha256:" + "d" * 64,
        input_cursor=None,
        output_cursor=None,
        rows=rows,
        collected_at=datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            collected_hour + 4,
            collected_minute,
            tzinfo=UTC,
        ),
        outcome="committed",
        reason=None,
        conflict_origin=None,
        collection_scope="head",
    )


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capture_topology_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
