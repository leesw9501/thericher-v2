from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.ops.kis_paper_prospective_spy_timing_probe as timing_probe

_SUMMER_SCHEDULE = datetime(2026, 8, 3, 19, 31, tzinfo=UTC)
_WINTER_SCHEDULE = datetime(2026, 1, 5, 19, 31, tzinfo=UTC)


def test_timing_probe_records_post_collection_prefix_without_execution_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    capture_calls: list[dict[str, object]] = []

    def capture(**kwargs: object) -> SimpleNamespace:
        capture_calls.append(kwargs)
        return SimpleNamespace(status="captured", reason=None)

    monkeypatch.setattr(timing_probe, "capture_kis_paper_prospective_spy_observation", capture)
    artifact_root, repository_root = _roots(tmp_path)
    outcome = _run(
        artifact_root=artifact_root,
        repository_root=repository_root,
        probe_id="summer-unit",
    )

    assert outcome.schedule_relation == "at_or_after_execution_expiry"
    assert outcome.capture_status == "captured"
    assert outcome.post_collection_prefix_availability == "present_after_collection"
    assert capture_calls == [
        {
            "cache_root": tmp_path / "intraday-head",
            "artifact_root": artifact_root.resolve(),
            "repo_root": repository_root,
            "session_date": datetime(2026, 8, 3, tzinfo=UTC).date(),
            "observed_at": _SUMMER_SCHEDULE.replace(second=6),
        }
    ]
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["timing"]["scheduler_started_at"] == {
        "eastern": "2026-08-03T15:31:00-04:00",
        "eastern_dst": True,
        "eastern_utc_offset": "-0400",
        "utc": "2026-08-03T19:31:00Z",
    }
    assert payload["post_collection_prefix"] == {
        "availability": "present_after_collection",
        "capture_reason": None,
        "capture_status": "captured",
        "decision_time_availability": "not_observed",
    }
    assert "feasibility" not in json.dumps(payload, sort_keys=True)
    _assert_safe(payload, artifact_root)


def test_winter_schedule_is_before_cutoff_and_preserves_offset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        timing_probe,
        "capture_kis_paper_prospective_spy_observation",
        lambda **_kwargs: SimpleNamespace(
            status="not_yet_observed",
            reason="before_decision_cutoff",
        ),
    )
    artifact_root, repository_root = _roots(tmp_path)
    outcome = timing_probe.run_kis_paper_prospective_spy_timing_probe(
        scheduler_started_at=_WINTER_SCHEDULE,
        collector_returned_at=_WINTER_SCHEDULE.replace(second=5),
        collection_exit_code=0,
        spy_collection_status="collected",
        spy_row_count=120,
        spy_exact_overlap_rows=0,
        spy_reason=None,
        cache_root=tmp_path / "intraday-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        probe_started_at=_WINTER_SCHEDULE.replace(second=6),
        probe_finished_at=_WINTER_SCHEDULE.replace(second=7),
        probe_id="winter-unit",
    )

    assert outcome.schedule_relation == "before_decision_cutoff"
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["timing"]["scheduler_started_at"]["eastern"] == "2026-01-05T14:31:00-05:00"
    assert payload["timing"]["scheduler_started_at"]["eastern_dst"] is False
    assert outcome.capture_status == "not_yet_observed"
    assert outcome.capture_reason == "before_decision_cutoff"


def test_collector_failure_does_not_open_the_cache_or_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_capture(**_kwargs: object) -> None:
        raise AssertionError("failed collector must not inspect a post-collection cache")

    monkeypatch.setattr(timing_probe, "capture_kis_paper_prospective_spy_observation", fail_capture)
    artifact_root, repository_root = _roots(tmp_path)
    outcome = timing_probe.run_kis_paper_prospective_spy_timing_probe(
        scheduler_started_at=_SUMMER_SCHEDULE,
        collector_returned_at=_SUMMER_SCHEDULE.replace(second=5),
        collection_exit_code=7,
        spy_collection_status="unavailable",
        spy_row_count=0,
        spy_exact_overlap_rows=0,
        spy_reason="unavailable",
        cache_root=tmp_path / "intraday-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        probe_started_at=_SUMMER_SCHEDULE.replace(second=6),
        probe_finished_at=_SUMMER_SCHEDULE.replace(second=7),
        probe_id="failed-collector-unit",
    )

    assert outcome.capture_status == "not_run"
    assert outcome.capture_reason == "collector_payload_unavailable"
    assert outcome.post_collection_prefix_availability == "unavailable_after_collection"


def test_explicit_probe_replay_is_idempotent_and_artifacts_stay_external(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        timing_probe,
        "capture_kis_paper_prospective_spy_observation",
        lambda **_kwargs: SimpleNamespace(status="captured", reason=None),
    )
    artifact_root, repository_root = _roots(tmp_path)
    kwargs = {
        "artifact_root": artifact_root,
        "repository_root": repository_root,
        "probe_id": "same-probe",
    }
    first = _run(**kwargs)
    second = _run(**kwargs)

    assert first.evidence_path == second.evidence_path
    assert first.evidence_path.read_bytes() == second.evidence_path.read_bytes()
    with pytest.raises(ValueError, match="outside Git"):
        _run(
            artifact_root=repository_root / "artifacts",
            repository_root=repository_root,
            probe_id="repo-artifact",
        )


def test_timing_probe_has_no_execution_or_environment_route() -> None:
    source = Path(timing_probe.__file__).read_text(encoding="ascii")

    assert "thericher_v2.execution" not in source
    assert "os.environ" not in source
    assert "KIS_PAPER_APP_KEY" not in source
    assert "KIS_LIVE" not in source


def _run(
    *,
    artifact_root: Path,
    repository_root: Path,
    probe_id: str,
) -> timing_probe.KisPaperProspectiveSpyTimingProbeOutcome:
    return timing_probe.run_kis_paper_prospective_spy_timing_probe(
        scheduler_started_at=_SUMMER_SCHEDULE,
        collector_returned_at=_SUMMER_SCHEDULE.replace(second=5),
        collection_exit_code=0,
        spy_collection_status="collected",
        spy_row_count=120,
        spy_exact_overlap_rows=0,
        spy_reason=None,
        cache_root=artifact_root.parent / "intraday-head",
        artifact_root=artifact_root,
        repository_root=repository_root,
        probe_started_at=_SUMMER_SCHEDULE.replace(second=6),
        probe_finished_at=_SUMMER_SCHEDULE.replace(second=7),
        probe_id=probe_id,
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "artifacts"
    repository_root = tmp_path / "repo"
    artifact_root.mkdir()
    repository_root.mkdir()
    return artifact_root, repository_root


def _assert_safe(payload: dict[str, object], artifact_root: Path) -> None:
    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    for forbidden in (str(artifact_root), "KIS_PAPER_APP_SECRET", "token", "12345678", "500.25"):
        assert forbidden not in rendered
