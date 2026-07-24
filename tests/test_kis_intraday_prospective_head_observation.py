from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import thericher_v2.research.kis_intraday_prospective_head_observation as prospective_head
from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data import us_equity_2026_session
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
    prepare_kis_intraday_prospective_head_observation,
)

_KOREA_TZ = ZoneInfo("Asia/Seoul")
_SESSION_DATES = (
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
)


def test_pending_preparation_uses_only_index_metadata_without_network_credentials_or_raw_bars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    index_path = _write_head_index(head_cache_root, _SESSION_DATES[:4])
    raw_path = head_cache_root / "v1" / "snapshots" / "raw" / "ohlcv_1m.csv.gz"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw bars must stay unread")
    _deny_external_access(monkeypatch)

    original_read_text = Path.read_text

    def read_index_only(path: Path, *args: object, **kwargs: object) -> str:
        if path.resolve() != index_path.resolve():
            raise AssertionError("preparation may read only the head index metadata")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_index_only)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preparation must not read raw market-bar bytes")
        ),
    )

    result = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=tmp_path / "model-artifacts",
        run_label="pending-r1",
        repo_root=repo_root,
    )

    assert result.status == "pending"
    assert result.available_complete_session_dates == _SESSION_DATES[:4]
    assert result.missing_session_count == 1
    assert result.precommit_path is None
    assert result.planning_receipt_path is None
    assert not (tmp_path / "model-artifacts").exists()


def test_preparation_selects_exactly_the_first_five_complete_sessions_in_order(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    _write_head_index(
        head_cache_root,
        (
            _SESSION_DATES[5],
            _SESSION_DATES[2],
            _SESSION_DATES[0],
            _SESSION_DATES[4],
            _SESSION_DATES[1],
            _SESSION_DATES[3],
        ),
        incomplete_dates={_SESSION_DATES[3]},
    )

    result = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=tmp_path / "model-artifacts",
        run_label="ordered-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert result.status == "prepared"
    assert result.available_complete_session_dates == (
        _SESSION_DATES[0],
        _SESSION_DATES[1],
        _SESSION_DATES[2],
        _SESSION_DATES[4],
        _SESSION_DATES[5],
    )
    assert result.selected_session_dates == result.available_complete_session_dates
    assert len(result.selected_session_dates) == (
        KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
    )
    assert result.selected_session_dates[0] > (
        KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1]
    )


def test_current_final_minute_stays_incomplete_for_its_first_seen_chunk(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    latest_date = _SESSION_DATES[4]
    latest_session = us_equity_2026_session(latest_date)
    assert latest_session is not None
    index_path = _write_head_index(
        head_cache_root,
        _SESSION_DATES[:5],
        collected_at=latest_session.window.close_ts - Timeframe.M1.duration,
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    final_key = _row_key(latest_session.window.close_ts - Timeframe.M1.duration)
    index["targets"][0]["chunks"].append(
        _retained_chunk(
            {final_key: "sha256:" + "a" * 64},
            collected_at=latest_session.window.close_ts + Timeframe.M1.duration,
            input_cursor={"keyb": "20260714155900", "next": "1"},
        )
    )
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=tmp_path / "model-artifacts",
        run_label="current-minute-r1",
        repo_root=repo_root,
    )

    assert result.status == "pending"
    assert result.available_complete_session_dates == _SESSION_DATES[:4]
    assert result.missing_session_count == 1


def test_truncated_real_index_metadata_is_rejected(tmp_path: Path) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    index_path = _write_head_index(head_cache_root, _SESSION_DATES[:5])
    index = json.loads(index_path.read_text(encoding="utf-8"))
    del index["targets"][0]["chunks"][0]["collected_at_utc"]
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="index metadata is invalid"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=tmp_path / "model-artifacts",
            run_label="truncated-r1",
            repo_root=repo_root,
        )


def test_conflicting_duplicate_retained_timestamp_is_rejected(tmp_path: Path) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    index_path = _write_head_index(head_cache_root, _SESSION_DATES[:5])
    index = json.loads(index_path.read_text(encoding="utf-8"))
    first_session = us_equity_2026_session(_SESSION_DATES[0])
    assert first_session is not None
    duplicate_key = _row_key(first_session.window.open_ts)
    index["targets"][0]["chunks"].append(
        _retained_chunk(
            {duplicate_key: "sha256:" + "b" * 64},
            collected_at=first_session.window.close_ts + Timeframe.M1.duration,
            input_cursor={"keyb": "20260708093000", "next": "1"},
        )
    )
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="conflicting retained rows"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=tmp_path / "model-artifacts",
            run_label="conflict-r1",
            repo_root=repo_root,
        )


def test_preparation_writes_atomic_external_precommit_and_receipt_and_rejects_repo_artifacts(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])

    with pytest.raises(ValueError, match="outside the Git workspace"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=repo_root / "model-artifacts",
            run_label="repo-root-r1",
            repo_root=repo_root,
        )

    artifact_root = tmp_path / "model-artifacts"
    result = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="external-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert result.precommit_path is not None
    assert result.planning_receipt_path is not None
    assert result.precommit_path.is_relative_to(artifact_root)
    assert result.planning_receipt_path.is_relative_to(artifact_root)
    assert not result.precommit_path.is_relative_to(repo_root)
    assert not list(result.precommit_path.parent.glob("*.tmp"))
    precommit = json.loads(result.precommit_path.read_text(encoding="utf-8"))
    receipt = json.loads(result.planning_receipt_path.read_text(encoding="utf-8"))
    assert precommit["selected_session_dates"] == [
        session_date.isoformat() for session_date in _SESSION_DATES[:5]
    ]
    assert receipt["precommit_hash"] == precommit["precommit_hash"]
    assert precommit["contract"]["limits"]["metadata_only_preparation"] is True
    assert precommit["contract"]["limits"]["model_training"] is False


def test_pair_publication_failure_leaves_no_run_directory_and_retries_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])
    artifact_root = tmp_path / "model-artifacts"
    run_dir = artifact_root / "kis-intraday-prospective-head-observation" / "retry-r1"
    original_write = prospective_head._write_json_atomic_new

    def fail_receipt(path: Path, payload: object) -> None:
        if path.name == "planning-receipt.json":
            raise OSError("simulated receipt failure")
        original_write(path, payload)

    monkeypatch.setattr(prospective_head, "_write_json_atomic_new", fail_receipt)
    with pytest.raises(OSError, match="simulated receipt failure"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=artifact_root,
            run_label="retry-r1",
            repo_root=repo_root,
        )

    assert not run_dir.exists()
    assert not list(artifact_root.glob(".prospective-head-*.stage"))
    monkeypatch.setattr(prospective_head, "_write_json_atomic_new", original_write)
    retry = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="retry-r1",
        repo_root=repo_root,
    )

    assert retry.status == "prepared"
    assert retry.precommit_path is not None and retry.precommit_path.exists()
    assert retry.planning_receipt_path is not None and retry.planning_receipt_path.exists()


def test_preparation_reuses_first_five_slot_after_a_sixth_session_arrives(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "model-artifacts"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])

    first = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="reuse-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    assert first.precommit_path is not None
    assert first.planning_receipt_path is not None
    precommit_bytes = first.precommit_path.read_bytes()
    receipt_bytes = first.planning_receipt_path.read_bytes()

    _write_head_index(head_cache_root, _SESSION_DATES)
    replay = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="reuse-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    assert replay.status == "prepared"
    assert replay.available_complete_session_dates == _SESSION_DATES
    assert replay.selected_session_dates == _SESSION_DATES[:5]
    assert replay.head_index_sha256 != first.head_index_sha256
    assert replay.precommit_path == first.precommit_path
    assert replay.planning_receipt_path == first.planning_receipt_path
    assert replay.precommit_path.read_bytes() == precommit_bytes
    assert replay.planning_receipt_path.read_bytes() == receipt_bytes
    precommit = json.loads(precommit_bytes)
    receipt = json.loads(receipt_bytes)
    assert precommit["artifact_slot_id"] == receipt["artifact_slot_id"]
    assert (
        precommit["selected_rows_fingerprint_sha256"]
        == receipt["selected_rows_fingerprint_sha256"]
    )
    assert "selected_rows" not in precommit
    assert "selected_rows" not in receipt


def test_preparation_rejects_changed_selected_fingerprint_and_preserves_existing_pair(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "model-artifacts"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])
    first = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="selected-fingerprint-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    assert first.precommit_path is not None
    assert first.planning_receipt_path is not None
    precommit_bytes = first.precommit_path.read_bytes()
    receipt_bytes = first.planning_receipt_path.read_bytes()
    first_session = us_equity_2026_session(_SESSION_DATES[0])
    assert first_session is not None
    _write_head_index(
        head_cache_root,
        _SESSION_DATES[:5],
        row_fingerprint_overrides={
            _row_key(first_session.window.open_ts): "sha256:" + "b" * 64
        },
    )

    with pytest.raises(ValueError, match="selected-row fingerprints do not match"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=artifact_root,
            run_label="selected-fingerprint-r1",
            repo_root=repo_root,
            prepared_at=datetime(2026, 7, 23, tzinfo=UTC),
        )

    assert first.precommit_path.read_bytes() == precommit_bytes
    assert first.planning_receipt_path.read_bytes() == receipt_bytes
    assert sorted(path.name for path in first.precommit_path.parent.iterdir()) == [
        "planning-receipt.json",
        "precommit.json",
    ]
    assert not list(artifact_root.glob(".prospective-head-*.stage"))


@pytest.mark.parametrize("malformation", ("receipt_binding", "extra_file"))
def test_preparation_rejects_malformed_existing_pair_without_overwriting(
    tmp_path: Path,
    malformation: str,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "model-artifacts"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])
    first = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label=f"malformed-{malformation}-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    assert first.precommit_path is not None
    assert first.planning_receipt_path is not None
    artifact_dir = first.precommit_path.parent
    if malformation == "receipt_binding":
        receipt = json.loads(first.planning_receipt_path.read_text(encoding="utf-8"))
        receipt["precommit_hash"] = "sha256:" + "0" * 64
        first.planning_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    else:
        (artifact_dir / "unexpected.json").write_text("{}", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in artifact_dir.iterdir()}

    with pytest.raises(ValueError, match="artifact pair is invalid"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=artifact_root,
            run_label=f"malformed-{malformation}-r1",
            repo_root=repo_root,
            prepared_at=datetime(2026, 7, 23, tzinfo=UTC),
        )

    assert {path.name: path.read_bytes() for path in artifact_dir.iterdir()} == before
    assert not list(artifact_root.glob(".prospective-head-*.stage"))


def test_preparation_rejects_artifact_parent_link_that_escapes_root(tmp_path: Path) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "model-artifacts"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])
    source = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="source-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    assert source.precommit_path is not None
    output_parent = source.precommit_path.parent.parent
    escaped_parent = repo_root / "escaped-artifacts"
    shutil.copytree(source.precommit_path.parent, escaped_parent / "escape-r1")
    shutil.rmtree(output_parent)
    try:
        os.symlink(escaped_parent, output_parent, target_is_directory=True)
    except OSError:
        pytest.skip("this Windows test host does not permit directory symlinks")

    with pytest.raises(ValueError, match="artifact path is invalid"):
        prepare_kis_intraday_prospective_head_observation(
            head_cache_root=head_cache_root,
            artifact_root=artifact_root,
            run_label="escape-r1",
            repo_root=repo_root,
            prepared_at=datetime(2026, 7, 23, tzinfo=UTC),
        )


def test_preparation_reuses_pair_published_by_concurrent_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _repo_root(tmp_path)
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    artifact_root = tmp_path / "model-artifacts"
    _write_head_index(head_cache_root, _SESSION_DATES[:5])
    winner = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="winner-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    assert winner.precommit_path is not None
    assert winner.planning_receipt_path is not None
    winner_dir = winner.precommit_path.parent
    winner_bytes = {
        path.name: path.read_bytes()
        for path in (winner.precommit_path, winner.planning_receipt_path)
    }
    original_replace = prospective_head.os.replace

    def publish_winner_then_fail(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.name.startswith(".prospective-head-") and destination_path.name == "race-r1":
            shutil.copytree(winner_dir, destination_path)
            raise PermissionError("published concurrently")
        original_replace(source, destination)

    monkeypatch.setattr(prospective_head.os, "replace", publish_winner_then_fail)
    replay = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=head_cache_root,
        artifact_root=artifact_root,
        run_label="race-r1",
        repo_root=repo_root,
        prepared_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    assert replay.precommit_path is not None
    assert replay.planning_receipt_path is not None
    assert replay.precommit_path.parent.name == "race-r1"
    assert {
        path.name: path.read_bytes()
        for path in (replay.precommit_path, replay.planning_receipt_path)
    } == winner_bytes
    assert not list(artifact_root.glob(".prospective-head-*.stage"))


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective head preparation must stay offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective head preparation must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root


def _write_head_index(
    head_cache_root: Path,
    session_dates: tuple[date, ...],
    *,
    incomplete_dates: set[date] | None = None,
    collected_at: datetime | None = None,
    row_fingerprint_overrides: dict[str, str] | None = None,
) -> Path:
    row_fingerprints: dict[str, str] = {}
    for session_date in session_dates:
        session = us_equity_2026_session(session_date)
        assert session is not None
        for minute_offset in range(390):
            if (
                incomplete_dates is not None
                and session_date in incomplete_dates
                and minute_offset == 120
            ):
                continue
            timestamp = session.window.open_ts + Timeframe.M1.duration * minute_offset
            row_key = timestamp.astimezone(_KOREA_TZ).strftime("%Y%m%dT%H%M%S")
            row_fingerprints[row_key] = (row_fingerprint_overrides or {}).get(
                row_key,
                "sha256:" + "a" * 64,
            )
    latest_session = us_equity_2026_session(max(session_dates))
    assert latest_session is not None
    chunk_collected_at = collected_at or (
        latest_session.window.close_ts + Timeframe.M1.duration
    )
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "generation": 0,
        "targets": [
            {
                "target_key": "QQQ/NAS/1m",
                "symbol": "QQQ",
                "exchange": "NAS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": [
                    _retained_chunk(row_fingerprints, collected_at=chunk_collected_at),
                    {"historical_note": "unretained evidence", "raw_market_data_retained": False},
                ],
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
    index_path = head_cache_root / "v1" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return index_path


def _retained_chunk(
    row_fingerprints: dict[str, str],
    *,
    collected_at: datetime,
    input_cursor: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "chunk_key": _chunk_key(
            target_key="QQQ/NAS/1m",
            input_cursor=input_cursor,
            row_fingerprints=row_fingerprints,
        ),
        "outcome": "committed",
        "input_cursor": input_cursor,
        "output_cursor": None,
        "manifest_path": "snapshots/unit/manifest.json",
        "manifest_hash": "sha256:" + "c" * 64,
        "raw_sha256": "sha256:" + "d" * 64,
        "raw_market_data_retained": True,
        "row_count": len(row_fingerprints),
        "row_fingerprints": row_fingerprints,
        "exact_overlap_rows": 0,
        "conflicting_overlap_rows": 0,
        "collected_at_utc": collected_at.isoformat().replace("+00:00", "Z"),
        "reason": None,
    }


def _chunk_key(
    *,
    target_key: str,
    input_cursor: dict[str, str] | None,
    row_fingerprints: dict[str, str],
) -> str:
    payload = {
        "backfill_version": "v1",
        "input_cursor": input_cursor,
        "row_fingerprints": dict(sorted(row_fingerprints.items())),
        "target_key": target_key,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _row_key(timestamp: datetime) -> str:
    return timestamp.astimezone(_KOREA_TZ).strftime("%Y%m%dT%H%M%S")
