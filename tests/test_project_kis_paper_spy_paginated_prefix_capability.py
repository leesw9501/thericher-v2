from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import thericher_v2.data.kis_spy_paginated_prefix_capability as capability

_EASTERN = ZoneInfo("America/New_York")
_SESSION_DATE = date(2026, 8, 3)
_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "project_kis_paper_spy_paginated_prefix_capability.py"
)


@dataclass(frozen=True)
class _Row:
    timestamp: datetime

    def as_document(self) -> dict[str, str]:
        eastern = self.timestamp.astimezone(_EASTERN)
        return {
            "xymd": eastern.strftime("%Y%m%d"),
            "xhms": eastern.strftime("%H%M%S"),
            "kymd": "20260804",
            "khms": "000000",
            "open": "913.111",
            "high": "914.111",
            "low": "912.111",
            "last": "913.611",
            "evol": "7777",
        }


@dataclass(frozen=True)
class _Page:
    bars: tuple[_Row, ...]
    next_cursor: str | None


def test_projector_binds_the_exact_safe_receipt_pair_without_raw_pages(tmp_path: Path) -> None:
    repository, cache_root, artifact_root, run_id = _write_receipts(tmp_path)

    fact = capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
    )

    payload = fact.safe_payload()
    rendered = json.dumps(payload, sort_keys=True)
    assert fact.result_class == "post_collection_completed_prefix"
    assert payload["decision_time_availability"] == "not_observed"
    assert payload["coverage"] == {
        "completed_minute_rule": "exchange_timestamp_plus_1m_at_or_before_1530_et",
        "expected_minute_count": 360,
        "complete_minute_count": 360,
        "missing_minute_count": 0,
        "page_seam_status": "continuous",
    }
    assert payload["control"]["receipt_sha256"].startswith("sha256:")
    assert payload["observation"]["receipt_sha256"].startswith("sha256:")
    assert "913.111" not in rendered
    assert "7777" not in rendered
    assert "raw-pages.json" not in rendered
    assert str(cache_root) not in rendered
    assert str(artifact_root) not in rendered


def test_projector_classifies_a_valid_incomplete_measurement_without_promoting_it(
    tmp_path: Path,
) -> None:
    repository, cache_root, artifact_root, run_id = _write_receipts(tmp_path, complete=False)

    fact = capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
    )

    assert fact.result_class == "measurement_incomplete_or_invalid"
    assert fact.observation_status == "incomplete_prefix"
    assert fact.complete_minute_count == 120
    assert fact.missing_minute_count == 240
    assert fact.safe_payload()["decision_time_availability"] == "not_observed"
    assert not (cache_root / "raw-pages.json").exists()


def test_projector_rejects_mismatched_or_tampered_exact_receipts(tmp_path: Path) -> None:
    repository, _cache_root, artifact_root, run_id = _write_receipts(tmp_path)

    with pytest.raises(ValueError, match="run id"):
        capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
            artifact_root=artifact_root,
            repository_root=repository,
            session_date=_SESSION_DATE,
            run_id="spy-prefix-20260802-v1",
        )

    evidence_path = (
        artifact_root
        / capability.KIS_SPY_PAGINATED_PREFIX_ARTIFACT_DIRECTORY
        / "runs"
        / run_id
        / "evidence.json"
    )
    payload = json.loads(evidence_path.read_text(encoding="ascii"))
    payload["decision_time_availability"] = "observed"
    evidence_path.write_text(json.dumps(payload, sort_keys=True), encoding="ascii")

    with pytest.raises(ValueError, match="observation receipt"):
        capability.read_spy_paginated_prefix_capability_fact_from_artifact_root(
            artifact_root=artifact_root,
            repository_root=repository,
            session_date=_SESSION_DATE,
        )


def test_projector_cli_reports_only_a_safe_exact_fact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository, _cache_root, artifact_root, run_id = _write_receipts(tmp_path)
    script = _load_script()

    assert script.main(
        [
            "--session-date",
            _SESSION_DATE.isoformat(),
            "--run-id",
            run_id,
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository),
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == capability.KIS_SPY_PAGINATED_PREFIX_FACT_KIND
    assert payload["result_class"] == "post_collection_completed_prefix"
    assert payload["decision_time_availability"] == "not_observed"
    assert "913.111" not in json.dumps(payload, sort_keys=True)


def test_projector_has_no_kis_or_execution_surface() -> None:
    module_source = Path(capability.__file__).read_text(encoding="ascii")
    script_source = _SCRIPT.read_text(encoding="ascii")

    assert "thericher_v2.execution" not in module_source
    assert "KIS_PAPER_APP_KEY" not in script_source
    assert "KIS_LIVE" not in script_source
    assert "dotenv" not in script_source


def _write_receipts(
    tmp_path: Path, *, complete: bool = True
) -> tuple[Path, Path, Path, str]:
    repository = tmp_path / "repo"
    cache_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    repository.mkdir()
    cutoff = _cutoff(_SESSION_DATE)
    run_id = capability.run_id_for_session(_SESSION_DATE)
    capability.record_spy_paginated_prefix_negative_control(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        observed_at=cutoff - timedelta(seconds=30),
    )
    pages = _pages(complete=complete)
    collection = capability.collect_spy_paginated_prefix_pages(
        fetch_page=lambda _next, _key: pages.pop(0)
    )
    capability.write_spy_paginated_prefix_collection_run(
        collection=collection,
        cache_root=cache_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        token_attempts=1,
        minute_page_attempts=3 if complete else 1,
    )
    capability.observe_spy_paginated_prefix_positive(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository,
        session_date=_SESSION_DATE,
        run_id=run_id,
        collection_started_at=cutoff + timedelta(seconds=1),
        collector_returned_at=cutoff + timedelta(seconds=4),
        collection_exit_code=0,
        observer_started_at=cutoff + timedelta(seconds=5),
        observer_finished_at=cutoff + timedelta(seconds=6),
    )
    return repository, cache_root, artifact_root, run_id


def _pages(*, complete: bool) -> list[_Page]:
    cutoff = _cutoff(_SESSION_DATE)
    stamps = [cutoff - timedelta(minutes=360 - index) for index in range(360)]
    if not complete:
        return [_Page(tuple(_Row(stamp) for stamp in stamps[:120]), None)]
    return [
        _Page(tuple(_Row(stamp) for stamp in stamps[240:]), "1"),
        _Page(tuple(_Row(stamp) for stamp in stamps[120:240]), "1"),
        _Page(tuple(_Row(stamp) for stamp in stamps[:120]), None),
    ]


def _cutoff(session_date: date) -> datetime:
    return datetime.combine(session_date, datetime.min.time(), _EASTERN).replace(
        hour=15,
        minute=30,
    ).astimezone(UTC)


def _load_script() -> object:
    spec = importlib.util.spec_from_file_location("spy_prefix_projector", _SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("projector script is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
