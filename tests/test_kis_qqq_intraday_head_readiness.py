from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_qqq_intraday_head_readiness import (
    KIS_QQQ_INTRADAY_HEAD_READINESS_CUTOFF,
    observe_kis_paper_qqq_intraday_head_readiness,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session

_KOREA = ZoneInfo("Asia/Seoul")
_SCRIPT = Path(__file__).parents[1] / "scripts" / "observe_kis_paper_qqq_intraday_head_readiness.py"


def test_observer_records_one_fresh_completed_window_without_raw_rows(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "fresh"), collected_at=collected_at),),
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )

    assert result.status == "observed"
    assert result.session_date == session_date
    assert result.evidence_path is not None and result.evidence_path.is_file()
    payload = json.loads(result.evidence_path.read_text(encoding="ascii"))
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["prospective_window"]["completed_m1_feature_bar_count"] == 90
    assert payload["prospective_window"]["future_m1_target_bar_count"] == 10
    assert payload["limits"]["raw_market_data_opened"] is False
    assert "row_fingerprints" not in rendered
    assert "fresh-260" not in rendered
    assert not list(cache_root.rglob("*.csv"))


def test_exact_observer_rerun_is_duplicate_and_keeps_one_receipt(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "fresh"), collected_at=collected_at),),
    )

    first = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )
    second = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )

    assert first.status == "observed"
    assert second.status == "duplicate"
    assert len(list((artifact_root / "runs").glob("*.json"))) == 1


def test_changed_same_session_commitment_is_contamination_not_overwrite(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "first"), collected_at=collected_at),),
    )
    first = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "changed"), collected_at=collected_at),),
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )

    assert first.status == "observed"
    assert result.status == "contaminated"
    assert result.reason == "artifact_identity_conflict"
    assert len(list((artifact_root / "runs").glob("*.json"))) == 2


def test_historical_complete_window_is_contamination(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = KIS_QQQ_INTRADAY_HEAD_READINESS_CUTOFF
    collected_at = _collection_time(session_date)
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "old"), collected_at=collected_at),),
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )

    assert result.status == "contaminated"
    assert result.reason == "historical_overlap"
    assert result.evidence_path is not None and result.evidence_path.is_file()


def test_incomplete_or_out_of_interval_data_stays_input_unavailable(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    incomplete = _window_rows(session_date, "incomplete")
    incomplete.pop(next(reversed(incomplete)))
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=incomplete, collected_at=collected_at),),
    )

    missing = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )
    outside_interval = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at + timedelta(minutes=10),
    )

    assert missing.status == "input_unavailable"
    assert missing.reason == "complete_window_unavailable"
    assert outside_interval.status == "input_unavailable"
    assert outside_interval.reason == "current_head_chunks_unavailable"
    assert not artifact_root.exists()


def test_conflicting_metadata_fingerprints_are_contaminated(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    rows = _window_rows(session_date, "first")
    changed = dict(rows)
    first_key = next(iter(changed))
    changed[first_key] = _digest("changed-fingerprint")
    _write_head_index(
        cache_root,
        chunks=(
            _chunk(rows=rows, collected_at=collected_at),
            _chunk(rows=changed, collected_at=collected_at + timedelta(minutes=1)),
        ),
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collected_at=collected_at,
    )

    assert result.status == "contaminated"
    assert result.reason == "fingerprint_metadata_conflict"


def test_observer_rejects_git_resident_cache_or_artifacts(tmp_path: Path) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "fresh"), collected_at=collected_at),),
    )
    git_cache_root = repository_root / "market-data"

    with pytest.raises(ValueError, match="cache root must stay outside Git"):
        _observe(
            cache_root=git_cache_root,
            artifact_root=artifact_root,
            repository_root=repository_root,
            collected_at=collected_at,
        )
    with pytest.raises(ValueError, match="artifact_root must be outside the Git workspace"):
        _observe(
            cache_root=cache_root,
            artifact_root=repository_root / "artifacts",
            repository_root=repository_root,
            collected_at=collected_at,
        )


def test_script_emits_source_safe_metadata_only_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache_root, artifact_root, repository_root = _roots(tmp_path)
    session_date = date(2026, 7, 22)
    collected_at = _collection_time(session_date)
    _write_head_index(
        cache_root,
        chunks=(_chunk(rows=_window_rows(session_date, "fresh"), collected_at=collected_at),),
    )
    script = _load_script()

    result = script.main(
        [
            "--collection-started-at",
            (collected_at - timedelta(minutes=1)).isoformat(),
            "--collector-returned-at",
            (collected_at + timedelta(minutes=1)).isoformat(),
            "--cache-root",
            str(cache_root),
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repository_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["status"] == "observed"
    assert payload["limits"]["credentials_read"] is False
    assert "evidence_path" not in payload
    assert "row_fingerprints" not in json.dumps(payload, sort_keys=True)


def test_readiness_code_has_no_network_credential_or_execution_dependency() -> None:
    readiness_path = Path(__file__).parents[1] / "src" / "thericher_v2" / "data"
    readiness_source = (readiness_path / "kis_qqq_intraday_head_readiness.py").read_text(
        encoding="ascii"
    )
    script_source = _SCRIPT.read_text(encoding="ascii")

    for forbidden in ("socket", "urllib", "requests", "os.environ", "KIS_LIVE", "execution."):
        assert forbidden not in readiness_source
        assert forbidden not in script_source


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "artifacts" / "kis-qqq-intraday-head-readiness-v1"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    return cache_root, artifact_root, repository_root


def _observe(
    *,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
    collected_at: datetime,
):
    return observe_kis_paper_qqq_intraday_head_readiness(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        collection_started_at=collected_at - timedelta(minutes=1),
        collector_returned_at=collected_at + timedelta(minutes=1),
    )


def _write_head_index(cache_root: Path, *, chunks: tuple[dict[str, object], ...]) -> None:
    version_root = cache_root / "v1"
    version_root.mkdir(parents=True, exist_ok=True)
    documents: list[dict[str, object]] = []
    for index, specification in enumerate(chunks):
        rows = specification["rows"]
        collected_at = specification["collected_at"]
        assert isinstance(rows, dict)
        assert isinstance(collected_at, datetime)
        fingerprints = {str(key): str(value) for key, value in rows.items()}
        documents.append(
            {
                "chunk_key": _chunk_key(fingerprints),
                "outcome": "committed",
                "input_cursor": None,
                "output_cursor": None,
                "manifest_path": f"snapshots/test-{index}/manifest.json",
                "manifest_hash": _digest(f"manifest-{index}"),
                "raw_sha256": _digest(f"raw-{index}"),
                "raw_market_data_retained": True,
                "row_count": len(fingerprints),
                "row_fingerprints": fingerprints,
                "exact_overlap_rows": 0,
                "conflicting_overlap_rows": 0,
                "collected_at_utc": collected_at.isoformat().replace("+00:00", "Z"),
                "reason": None,
                "collection_scope": "head",
            }
        )
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "generation": 1,
        "targets": [
            {
                "target_key": "QQQ/NAS/1m",
                "symbol": "QQQ",
                "exchange": "NAS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": documents,
            },
            {
                "target_key": "SPY/AMS/1m",
                "symbol": "SPY",
                "exchange": "AMS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": [],
            },
        ],
    }
    (version_root / "index.json").write_text(json.dumps(index), encoding="ascii")


def _chunk(*, rows: dict[str, str], collected_at: datetime) -> dict[str, object]:
    return {"rows": rows, "collected_at": collected_at}


def _window_rows(session_date: date, label: str) -> dict[str, str]:
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    return {
        (session.window.open_ts + timedelta(minutes=offset)).astimezone(_KOREA).strftime(
            "%Y%m%dT%H%M%S"
        ): _digest(f"{label}-{offset}")
        for offset in range(260, 360)
    }


def _collection_time(session_date: date) -> datetime:
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    return (session.window.open_ts + timedelta(minutes=360)).astimezone(UTC)


def _chunk_key(rows: dict[str, str]) -> str:
    return _sha256(
        json.dumps(
            {
                "backfill_version": "v1",
                "input_cursor": None,
                "row_fingerprints": dict(sorted(rows.items())),
                "target_key": "QQQ/NAS/1m",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def _digest(value: str) -> str:
    return _sha256(value.encode("ascii"))


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("qqq_readiness_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
