from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_intraday_head_coverage import (
    inspect_kis_paper_private_intraday_head_coverage,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    prepare_kis_intraday_prospective_head_observation,
)

_KOREA = ZoneInfo("Asia/Seoul")
_QQQ_TARGET_KEY = "QQQ/NAS/1m"


def test_head_coverage_reports_short_ranges_and_manifest_continuation_without_raw_reads(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "market-data" / "intraday-head"
    short_session = _regular_session(date(2026, 7, 21))
    complete_session = _regular_session(date(2026, 7, 22))
    _write_head_index(
        cache_root,
        chunks=(
            {
                "rows": _session_rows(short_session, range(240), "short"),
                "continuation_available": True,
                "exact_overlap_rows": 2,
                "collected_at": short_session.window.close_ts + timedelta(minutes=1),
            },
            {
                "rows": _session_rows(complete_session, range(390), "complete"),
                "continuation_available": False,
                "exact_overlap_rows": 0,
                "collected_at": complete_session.window.close_ts + timedelta(minutes=1),
            },
        ),
    )

    result = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=tmp_path / "repo",
        after_session_date=date(2026, 7, 7),
        required_complete_session_count=5,
    )

    assert result.status == "available"
    assert result.continuation_category == "mixed"
    assert result.exact_overlap_category == "exact_overlap"
    assert result.exact_overlap_row_count == 2
    assert result.last_reason_category == "minute_duplicate_conflict"
    assert result.conflicting_overlap_category == "none"
    assert [item.session_date for item in result.session_coverage] == [
        date(2026, 7, 21),
        date(2026, 7, 22),
    ]
    assert result.session_coverage[0].complete_minute_count == 240
    assert result.session_coverage[0].missing_minute_ranges == ((240, 389),)
    assert result.session_coverage[1].status == "complete"
    assert result.preparation_input_status == "pending_complete_sessions"

    payload = json.dumps(result.to_payload(), sort_keys=True)
    assert "manifest_path" not in payload
    assert "row_fingerprints" not in payload
    assert not list(cache_root.rglob("*.csv"))
    assert not list(cache_root.rglob("*.gz"))


def test_head_coverage_surfaces_retained_fingerprint_conflicts_without_raw_data(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "market-data" / "intraday-head"
    session = _regular_session(date(2026, 7, 21))
    first_key = _korea_key(session.window.open_ts)
    _write_head_index(
        cache_root,
        chunks=(
            {
                "rows": {first_key: _digest("first")},
                "continuation_available": False,
                "exact_overlap_rows": 0,
                "collected_at": session.window.close_ts + timedelta(minutes=1),
            },
            {
                "rows": {first_key: _digest("second")},
                "continuation_available": False,
                "exact_overlap_rows": 0,
                "collected_at": session.window.close_ts + timedelta(minutes=2),
            },
        ),
    )

    result = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=tmp_path / "repo",
        after_session_date=date(2026, 7, 7),
        required_complete_session_count=1,
    )

    assert result.conflicting_overlap_category == "retained_fingerprint_conflict"
    assert result.preparation_input_status == "metadata_conflict"
    assert result.session_coverage[0].complete_minute_count == 1
    assert not list(cache_root.rglob("*.csv"))
    assert not list(cache_root.rglob("*.gz"))


def test_head_coverage_and_preparer_share_exact_crlf_index_identity(tmp_path: Path) -> None:
    cache_root = tmp_path / "market-data" / "intraday-head"
    session_dates = (
        date(2026, 7, 8),
        date(2026, 7, 9),
        date(2026, 7, 10),
        date(2026, 7, 13),
        date(2026, 7, 14),
    )
    chunks = tuple(
        {
            "rows": _session_rows(_regular_session(session_date), range(390), "complete"),
            "continuation_available": False,
            "exact_overlap_rows": 0,
            "collected_at": _regular_session(session_date).window.close_ts
            + timedelta(minutes=1),
        }
        for session_date in session_dates
    )
    _write_head_index(cache_root, chunks=chunks)
    index_path = cache_root / "v1" / "index.json"
    index = json.loads(index_path.read_bytes())
    index_bytes = (
        json.dumps(index, indent=2, sort_keys=True).replace("\n", "\r\n") + "\r\n"
    ).encode("utf-8")
    index_path.write_bytes(index_bytes)

    coverage = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=tmp_path / "repo",
        after_session_date=date(2026, 7, 7),
        required_complete_session_count=5,
    )
    preparation = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=cache_root,
        artifact_root=tmp_path / "model-artifacts",
        run_label="crlf-index-r1",
        repo_root=tmp_path / "repo",
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert preparation.status == "prepared"
    assert coverage.index_metadata_sha256 == _sha256(index_bytes)
    assert preparation.head_index_sha256 == coverage.index_metadata_sha256


def test_head_coverage_reports_not_created_without_creating_a_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "market-data" / "intraday-head"

    result = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=tmp_path / "repo",
        after_session_date=date(2026, 7, 7),
        required_complete_session_count=5,
    )

    assert result.to_payload()["status"] == "not_created"
    assert not cache_root.exists()


def test_coverage_script_prints_only_the_safe_summary(monkeypatch, capsys, tmp_path: Path) -> None:
    script = _load_script()
    expected = {"kind": "kis_paper_intraday_head_coverage", "status": "available"}

    monkeypatch.setattr(
        script,
        "inspect_kis_paper_private_intraday_head_coverage",
        lambda **_kwargs: SimpleNamespace(to_payload=lambda: expected),
    )

    result = script.main(["--head-cache-root", str(tmp_path / "head")])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == expected


def _write_head_index(cache_root: Path, *, chunks: tuple[dict[str, object], ...]) -> None:
    version_root = cache_root / "v1"
    version_root.mkdir(parents=True)
    documents = []
    for index, specification in enumerate(chunks):
        rows = specification["rows"]
        collected_at = specification["collected_at"]
        continuation_available = specification["continuation_available"]
        exact_overlap_rows = specification["exact_overlap_rows"]
        assert isinstance(rows, dict)
        assert isinstance(collected_at, datetime)
        assert isinstance(continuation_available, bool)
        assert isinstance(exact_overlap_rows, int)
        manifest_relative = f"snapshots/unit-{index}/manifest.json"
        manifest_path = version_root / manifest_relative
        manifest_path.parent.mkdir(parents=True)
        manifest_bytes = json.dumps(
            {
                "source": {"symbol": "QQQ", "exchange": "NAS"},
                "pages": [{"continuation_available": continuation_available}],
            },
            sort_keys=True,
        ).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)
        row_fingerprints = {str(key): str(value) for key, value in rows.items()}
        documents.append(
            {
                "chunk_key": _chunk_key(row_fingerprints),
                "outcome": "committed",
                "input_cursor": None,
                "output_cursor": None,
                "manifest_path": manifest_relative,
                "manifest_hash": _sha256(manifest_bytes),
                "raw_sha256": _digest(f"raw-{index}"),
                "raw_market_data_retained": True,
                "row_count": len(row_fingerprints),
                "row_fingerprints": row_fingerprints,
                "exact_overlap_rows": exact_overlap_rows,
                "conflicting_overlap_rows": 0,
                "collected_at_utc": collected_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "generation": 7,
        "targets": [
            {
                "target_key": _QQQ_TARGET_KEY,
                "symbol": "QQQ",
                "exchange": "NAS",
                "next_cursor": None,
                "last_reason": "minute_duplicate_conflict",
                "last_observed_at_utc": "2026-07-22T00:00:00Z",
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
    (version_root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def _regular_session(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    return session


def _session_rows(session, offsets: range, label: str) -> dict[str, str]:
    return {
        _korea_key(session.window.open_ts + timedelta(minutes=offset)): _digest(
            f"{label}-{offset}"
        )
        for offset in offsets
    }


def _korea_key(timestamp: datetime) -> str:
    return timestamp.astimezone(_KOREA).strftime("%Y%m%dT%H%M%S")


def _chunk_key(rows: dict[str, str]) -> str:
    encoded = json.dumps(
        {
            "backfill_version": "v1",
            "input_cursor": None,
            "row_fingerprints": dict(sorted(rows.items())),
            "target_key": _QQQ_TARGET_KEY,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(encoded)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest(value: str) -> str:
    return _sha256(value.encode("utf-8"))


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "inspect_kis_intraday_head_coverage.py"
    spec = importlib.util.spec_from_file_location(
        "inspect_kis_intraday_head_coverage_for_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
