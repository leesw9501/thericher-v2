from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import socket
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from thericher_v2.data.norgate_candidate_union import rank_quantile_ranks
from thericher_v2.data.tiingo_daily_pilot import (
    TIINGO_DAILY_SHARD_VERSION,
    TIINGO_INTERNAL_USE_CLAUSE,
    TIINGO_TERMS_URL,
    TiingoDailyPilotError,
    acquire_tiingo_daily_pilot,
    acquire_tiingo_daily_shard,
    default_tiingo_daily_pilot_dir,
    default_tiingo_daily_shard_dir,
    verify_tiingo_daily_pilot_snapshot,
    verify_tiingo_daily_shard_snapshot,
)

_START = date(2024, 7, 18)
_END = date(2026, 7, 17)
_SYMBOLS = ("ALFA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT")


class _Response:
    status = 200

    def __init__(self, payload: bytes, *, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_acquires_private_external_snapshot_and_attests_raw_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    env_path = _env(tmp_path, include_kis=True)
    calls: list[tuple[str, str | None, float]] = []

    def opener(request, *, timeout: float):
        calls.append((request.full_url, request.get_header("Authorization"), timeout))
        return _Response(_payload("raw-value-external-only"))

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pilot must not cross this boundary")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=env_path,
        repo=repo,
        opener=opener,
        sample_size=3,
    )

    assert result.completed is True
    assert result.request_count == 3
    assert result.available_count == 3
    assert result.row_count == 6
    assert result.snapshot_dir.is_relative_to(root)
    assert not result.snapshot_dir.is_relative_to(repo)
    assert [header for _, header, _ in calls] == ["Token test-token"] * 3
    assert all("test-token" not in url for url, _, _ in calls)
    assert all(f"startDate={_START.isoformat()}" in url for url, _, _ in calls)
    assert all(f"endDate={_END.isoformat()}" in url for url, _, _ in calls)

    manifest = json.loads((result.snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    marker = (result.snapshot_dir / "TIINGO_PRIVATE_INTERNAL_DATA_MARKER.txt").read_text(
        encoding="ascii"
    )
    assert manifest["candidate_union"]["selected_ranks"] == [1, 3, 6]
    assert manifest["source_contract"]["symbol_transform"] == "none"
    assert manifest["scope"]["model_eligible"] is False
    assert manifest["rights"]["terms_url"] == TIINGO_TERMS_URL
    assert manifest["rights"]["internal_use_clause"] == TIINGO_INTERNAL_USE_CLAUSE
    assert TIINGO_INTERNAL_USE_CLAUSE in marker
    assert "Do not redistribute" in marker
    assert sorted(path.name for path in (result.snapshot_dir / "raw").iterdir()) == [
        "0001.json",
        "0003.json",
        "0006.json",
    ]
    assert not list(result.snapshot_dir.parent.glob(".stage-*"))
    assert "raw-value-external-only" in (result.snapshot_dir / "raw" / "0001.json").read_text(
        encoding="utf-8"
    )
    assert "test-token" not in (result.snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    assert "must-not-be-used" not in (result.snapshot_dir / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert verify_tiingo_daily_pilot_snapshot(
        result.snapshot_dir,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=root,
        repo_root=repo,
    ) == result


@pytest.mark.parametrize("status", (401, 403, 429))
def test_auth_or_rate_error_publishes_stopped_partial_evidence(
    tmp_path: Path, status: int
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    calls = 0

    def opener(_request, *, timeout: float):
        nonlocal calls
        calls += 1
        raise HTTPError("https://api.tiingo.com", status, "denied", {}, None)

    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=opener,
        sample_size=3,
    )

    assert calls == 1
    assert result.completed is False
    assert result.stop_reason == f"http_{status}"
    assert result.request_count == 1
    assert result.row_count == 0
    manifest = json.loads((result.snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["aggregate"] == {
        "available": 0,
        "empty": 0,
        "errors": 1,
        "request_count": 1,
        "unavailable": 0,
    }
    assert not list((result.snapshot_dir / "raw").iterdir())


def test_unavailable_continues_but_malformed_response_stops_with_raw_evidence(
    tmp_path: Path,
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    calls = 0

    def unavailable_then_success(_request, *, timeout: float):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError("https://api.tiingo.com", 404, "missing", {}, None)
        return _Response(_payload())

    available = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=unavailable_then_success,
        sample_size=3,
    )
    assert available.completed is True
    assert available.unavailable_count == 1
    assert available.request_count == 3

    malformed_root, malformed_candidate, malformed_manifest, malformed_hash, malformed_repo = (
        _candidate_union(tmp_path / "malformed")
    )
    malformed_calls = 0

    def malformed(_request, *, timeout: float):
        nonlocal malformed_calls
        malformed_calls += 1
        return _Response(b'{"not": "an array"}')

    stopped = _acquire(
        root=malformed_root,
        candidate_path=malformed_candidate,
        manifest_path=malformed_manifest,
        expected_hash=malformed_hash,
        env_path=_env(tmp_path / "malformed"),
        repo=malformed_repo,
        opener=malformed,
        sample_size=3,
    )
    assert malformed_calls == 1
    assert stopped.completed is False
    assert stopped.stop_reason == "malformed_response"
    assert (stopped.snapshot_dir / "raw" / "0001.json").read_bytes() == b'{"not": "an array"}'


def test_tamper_and_preflight_fail_closed_without_request(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=3,
    )
    raw = result.snapshot_dir / "raw" / "0001.json"
    raw.write_bytes(raw.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="raw hash mismatch"):
        verify_tiingo_daily_pilot_snapshot(
            result.snapshot_dir,
            expected_dataset_hash=result.dataset_hash,
            expected_manifest_hash=result.manifest_hash,
            market_data_root=root,
            repo_root=repo,
        )

    marker_root, marker_candidate, marker_manifest, marker_hash, marker_repo = _candidate_union(
        tmp_path / "marker"
    )
    marker_result = _acquire(
        root=marker_root,
        candidate_path=marker_candidate,
        manifest_path=marker_manifest,
        expected_hash=marker_hash,
        env_path=_env(tmp_path / "marker"),
        repo=marker_repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=3,
    )
    (marker_result.snapshot_dir / "TIINGO_PRIVATE_INTERNAL_DATA_MARKER.txt").write_text(
        "tampered\n", encoding="ascii"
    )
    with pytest.raises(ValueError, match="retention marker"):
        verify_tiingo_daily_pilot_snapshot(
            marker_result.snapshot_dir,
            expected_dataset_hash=marker_result.dataset_hash,
            expected_manifest_hash=marker_result.manifest_hash,
            market_data_root=marker_root,
            repo_root=marker_repo,
        )

    floor_root, floor_candidate, floor_manifest, floor_hash, floor_repo = _candidate_union(
        tmp_path / "floor"
    )

    def unexpected_request(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("preflight failure must happen before a request")

    with pytest.raises(ValueError, match="hard free-space"):
        _acquire(
            root=floor_root,
            candidate_path=floor_candidate,
            manifest_path=floor_manifest,
            expected_hash=floor_hash,
            env_path=_env(tmp_path / "floor"),
            repo=floor_repo,
            opener=unexpected_request,
            sample_size=3,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    with pytest.raises(ValueError, match="outside Git"):
        _acquire(
            root=floor_root,
            candidate_path=floor_candidate,
            manifest_path=floor_manifest,
            expected_hash=floor_hash,
            env_path=_env(tmp_path / "floor"),
            repo=floor_repo,
            opener=unexpected_request,
            sample_size=3,
            destination=floor_repo / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r1",
        )
    with pytest.raises(ValueError, match="request budget"):
        _acquire(
            root=floor_root,
            candidate_path=floor_candidate,
            manifest_path=floor_manifest,
            expected_hash=floor_hash,
            env_path=_env(tmp_path / "floor"),
            repo=floor_repo,
            opener=unexpected_request,
            sample_size=31,
        )
    staging_parent = floor_root / "pilot"
    staging_parent.mkdir()
    (staging_parent / ".stage-interrupted").mkdir()
    with pytest.raises(FileExistsError, match="staging residue"):
        _acquire(
            root=floor_root,
            candidate_path=floor_candidate,
            manifest_path=floor_manifest,
            expected_hash=floor_hash,
            env_path=_env(tmp_path / "floor"),
            repo=floor_repo,
            opener=unexpected_request,
            sample_size=3,
        )


def test_reconstruction_compares_canonical_csv_not_gzip_encoding(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=3,
    )
    canonical_path = result.snapshot_dir / "ohlcv_1d.csv.gz"
    reencoded = gzip.compress(
        gzip.decompress(canonical_path.read_bytes()), compresslevel=1, mtime=0
    )
    assert reencoded != canonical_path.read_bytes()
    canonical_path.write_bytes(reencoded)
    # Re-encoding creates a distinct snapshot identity. This test verifies only
    # that canonical reconstruction is content-based once its new byte hashes
    # have been explicitly attested.
    snapshot_manifest = result.snapshot_dir / "manifest.json"
    manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    encoded_hash = "sha256:" + hashlib.sha256(reencoded).hexdigest()
    manifest["dataset_hash"] = encoded_hash
    manifest["files"]["canonical_raw_fields"]["sha256"] = encoded_hash
    manifest["files"]["canonical_raw_fields"]["size_bytes"] = len(reencoded)
    snapshot_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_hash = "sha256:" + hashlib.sha256(snapshot_manifest.read_bytes()).hexdigest()

    verified = verify_tiingo_daily_pilot_snapshot(
        result.snapshot_dir,
        expected_dataset_hash=encoded_hash,
        expected_manifest_hash=manifest_hash,
        market_data_root=root,
        repo_root=repo,
    )

    assert verified.dataset_hash == encoded_hash
    assert verified.manifest_hash == manifest_hash


def test_rejects_reordered_canonical_csv_after_new_snapshot_identity(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=3,
    )
    canonical_path = result.snapshot_dir / "ohlcv_1d.csv.gz"
    lines = gzip.decompress(canonical_path.read_bytes()).splitlines(keepends=True)
    assert len(lines) > 2
    lines[1], lines[2] = lines[2], lines[1]
    reordered = gzip.compress(b"".join(lines), mtime=0)
    canonical_path.write_bytes(reordered)

    snapshot_manifest = result.snapshot_dir / "manifest.json"
    manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    reordered_hash = "sha256:" + hashlib.sha256(reordered).hexdigest()
    manifest["dataset_hash"] = reordered_hash
    manifest["files"]["canonical_raw_fields"]["sha256"] = reordered_hash
    manifest["files"]["canonical_raw_fields"]["size_bytes"] = len(reordered)
    snapshot_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_hash = "sha256:" + hashlib.sha256(snapshot_manifest.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="canonical data does not match raw evidence"):
        verify_tiingo_daily_pilot_snapshot(
            result.snapshot_dir,
            expected_dataset_hash=reordered_hash,
            expected_manifest_hash=manifest_hash,
            market_data_root=root,
            repo_root=repo,
        )


def test_mounted_snapshot_still_rejects_raw_canonical_byte_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=3,
    )
    mounted_root = repo / root.name
    shutil.copytree(root, mounted_root)
    mounted_snapshot = mounted_root / result.snapshot_dir.relative_to(root)
    original_is_mount = Path.is_mount

    def is_market_data_mount(path: Path) -> bool:
        return path.resolve() == mounted_root.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_market_data_mount)
    assert verify_tiingo_daily_pilot_snapshot(
        mounted_snapshot,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=mounted_root,
        repo_root=repo,
    ).dataset_hash == result.dataset_hash

    canonical = mounted_snapshot / "ohlcv_1d.csv.gz"
    canonical.write_bytes(canonical.read_bytes() + b"tampered")
    import thericher_v2.data.tiingo_daily_pilot as pilot

    def unexpected_decompression(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("raw dataset hash must reject before decompression")

    monkeypatch.setattr(pilot, "_gzip_content", unexpected_decompression)
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        verify_tiingo_daily_pilot_snapshot(
            mounted_snapshot,
            expected_dataset_hash=result.dataset_hash,
            expected_manifest_hash=result.manifest_hash,
            market_data_root=mounted_root,
            repo_root=repo,
        )


def test_verification_failure_quarantines_external_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    import thericher_v2.data.tiingo_daily_pilot as pilot

    def fail_verification(*_args: object, **_kwargs: object) -> object:
        raise ValueError("forced verification failure")

    monkeypatch.setattr(pilot, "_verify_snapshot", fail_verification)
    with pytest.raises(TiingoDailyPilotError, match="evidence was retained"):
        _acquire(
            root=root,
            candidate_path=candidate_path,
            manifest_path=manifest_path,
            expected_hash=expected_hash,
            env_path=_env(tmp_path),
            repo=repo,
            opener=lambda _request, *, timeout: _Response(_payload()),
            sample_size=3,
        )
    quarantined = list((root / "pilot").glob(".rejected-*"))
    assert len(quarantined) == 1
    assert (quarantined[0] / "raw" / "0001.json").is_file()
    assert (quarantined[0] / "manifest.json").is_file()
    with pytest.raises(FileExistsError, match="staging residue"):
        _acquire(
            root=root,
            candidate_path=candidate_path,
            manifest_path=manifest_path,
            expected_hash=expected_hash,
            env_path=_env(tmp_path),
            repo=repo,
            opener=lambda _request, *, timeout: _Response(_payload()),
            sample_size=3,
        )


def test_shared_rank_quantile_schedule_is_unique_and_bounded() -> None:
    assert rank_quantile_ranks(6, sample_size=3) == (1, 3, 6)
    with pytest.raises(ValueError, match="smaller than the sample"):
        rank_quantile_ranks(2, sample_size=3)


def test_redirect_stops_without_retry(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)

    def redirect(_request, *, timeout: float):
        raise TiingoDailyPilotError("redirect")

    result = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=redirect,
        sample_size=3,
    )
    assert result.completed is False
    assert result.stop_reason == "redirect_blocked"
    assert result.request_count == 1


def test_default_destination_uses_external_market_data_root() -> None:
    assert default_tiingo_daily_pilot_dir(date(2026, 7, 19)) == Path(
        "D:/market_data/us_equities/tiingo_standard_eod_pilot/canonical/"
        "snapshot=2026-07-19-tiingo-standard-eod-pilot-r1"
    )


def test_disjoint_shard_rechecks_predecessor_and_uses_a_distinct_identity(
    tmp_path: Path,
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(
        tmp_path, symbol_count=60
    )
    predecessor = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=30,
        destination=root / "pilot" / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r1",
    )
    calls = 0

    def opener(_request, *, timeout: float) -> _Response:
        nonlocal calls
        calls += 1
        return _Response(_payload())

    shard = acquire_tiingo_daily_shard(
        candidate_union_path=candidate_path,
        candidate_union_manifest_path=manifest_path,
        expected_candidate_union_hash=expected_hash,
        predecessor_snapshot_dir=predecessor.snapshot_dir,
        expected_predecessor_dataset_hash=predecessor.dataset_hash,
        expected_predecessor_manifest_hash=predecessor.manifest_hash,
        env_path=_env(tmp_path),
        destination=root / "pilot" / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r2",
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, 1, tzinfo=UTC),
        market_data_root=root,
        repo_root=repo,
        opener=opener,
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )

    assert calls == 30
    assert shard.completed is True
    manifest = json.loads((shard.snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    predecessor_manifest = json.loads(
        (predecessor.snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["pilot_version"] == TIINGO_DAILY_SHARD_VERSION
    assert manifest["candidate_union"]["selection_algorithm"] == "rank_quantile_excluding_ranks_v1"
    assert len(manifest["candidate_union"]["selected_ranks"]) == 30
    assert not (
        set(manifest["candidate_union"]["selected_ranks"])
        & set(predecessor_manifest["candidate_union"]["selected_ranks"])
    )
    assert verify_tiingo_daily_shard_snapshot(
        shard.snapshot_dir,
        expected_dataset_hash=shard.dataset_hash,
        expected_manifest_hash=shard.manifest_hash,
        predecessor_snapshot_dir=predecessor.snapshot_dir,
        expected_predecessor_dataset_hash=predecessor.dataset_hash,
        expected_predecessor_manifest_hash=predecessor.manifest_hash,
        expected_candidate_union_hash=expected_hash,
        market_data_root=root,
        repo_root=repo,
    ) == shard

    manifest["retrieved_at_utc"] = "2026-07-19T00:59:00Z"
    tampered_manifest = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (shard.snapshot_dir / "manifest.json").write_bytes(tampered_manifest.encode("utf-8"))
    with pytest.raises(ValueError, match="pacing evidence"):
        verify_tiingo_daily_shard_snapshot(
            shard.snapshot_dir,
            expected_dataset_hash=shard.dataset_hash,
            expected_manifest_hash="sha256:"
            + hashlib.sha256(tampered_manifest.encode("utf-8")).hexdigest(),
            predecessor_snapshot_dir=predecessor.snapshot_dir,
            expected_predecessor_dataset_hash=predecessor.dataset_hash,
            expected_predecessor_manifest_hash=predecessor.manifest_hash,
            expected_candidate_union_hash=expected_hash,
            market_data_root=root,
            repo_root=repo,
        )

    def unexpected_request(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("predecessor mismatch must fail before a request")

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        acquire_tiingo_daily_shard(
            candidate_union_path=candidate_path,
            candidate_union_manifest_path=manifest_path,
            expected_candidate_union_hash=expected_hash,
            predecessor_snapshot_dir=predecessor.snapshot_dir,
            expected_predecessor_dataset_hash=predecessor.dataset_hash,
            expected_predecessor_manifest_hash="sha256:" + "0" * 64,
            env_path=_env(tmp_path),
            destination=root / "other" / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r2",
            requested_start=_START,
            requested_end=_END,
            retrieved_at_utc=datetime(2026, 7, 19, 1, tzinfo=UTC),
            market_data_root=root,
            repo_root=repo,
            opener=unexpected_request,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
        )


def test_shard_rejects_early_pacing_and_has_a_distinct_default_destination(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(
        tmp_path, symbol_count=60
    )
    predecessor = _acquire(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=lambda _request, *, timeout: _Response(_payload()),
        sample_size=30,
        destination=root / "pilot" / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r1",
    )

    def unexpected_request(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("early shard must fail before a request")

    with pytest.raises(ValueError, match="wait one hour"):
        acquire_tiingo_daily_shard(
            candidate_union_path=candidate_path,
            candidate_union_manifest_path=manifest_path,
            expected_candidate_union_hash=expected_hash,
            predecessor_snapshot_dir=predecessor.snapshot_dir,
            expected_predecessor_dataset_hash=predecessor.dataset_hash,
            expected_predecessor_manifest_hash=predecessor.manifest_hash,
            env_path=_env(tmp_path),
            destination=root / "pilot" / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r2",
            requested_start=_START,
            requested_end=_END,
            retrieved_at_utc=datetime(2026, 7, 19, 0, 59, tzinfo=UTC),
            market_data_root=root,
            repo_root=repo,
            opener=unexpected_request,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
        )
    assert default_tiingo_daily_shard_dir(date(2026, 7, 19)) == Path(
        "D:/market_data/us_equities/tiingo_standard_eod_pilot/canonical/"
        "snapshot=2026-07-19-tiingo-standard-eod-pilot-r2"
    )


def _acquire(
    *,
    root: Path,
    candidate_path: Path,
    manifest_path: Path,
    expected_hash: str,
    env_path: Path,
    repo: Path,
    opener,
    sample_size: int,
    destination: Path | None = None,
    disk_usage=None,
):
    return acquire_tiingo_daily_pilot(
        candidate_union_path=candidate_path,
        candidate_union_manifest_path=manifest_path,
        expected_candidate_union_hash=expected_hash,
        env_path=env_path,
        destination=destination
        or root / "pilot" / "snapshot=2026-07-19-tiingo-standard-eod-pilot-r1",
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        sample_size=sample_size,
        market_data_root=root,
        repo_root=repo,
        opener=opener,
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(total=100, free=50)),
    )


def _candidate_union(
    tmp_path: Path, *, symbol_count: int = len(_SYMBOLS)
) -> tuple[Path, Path, Path, str, Path]:
    root = tmp_path / "market_data"
    snapshot = root / "norgate" / "snapshot=fixture"
    snapshot.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate_path = snapshot / "candidate_union.csv"
    symbols = _SYMBOLS if symbol_count == len(_SYMBOLS) else tuple(
        f"SYMBOL{rank:04d}" for rank in range(1, symbol_count + 1)
    )
    rows = "".join(f"{rank},{symbol}\n" for rank, symbol in enumerate(symbols, start=1))
    candidate_bytes = ("candidate_rank,symbol\n" + rows).encode("utf-8")
    candidate_path.write_bytes(candidate_bytes)
    expected_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
    manifest_path = snapshot / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "norgate_sp500_current_past_membership_matrix",
                "candidate_count": len(symbols),
                "scope": {
                    "direct_historical_universe_list": False,
                    "publication_time_proven": False,
                    "pit_eligible": False,
                    "campaign_eligible": False,
                    "model_eligible": False,
                },
                "files": {
                    "candidate_union": {
                        "path": candidate_path.name,
                        "sha256": expected_hash,
                        "size_bytes": len(candidate_bytes),
                        "columns": ["candidate_rank", "symbol"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return root, candidate_path, manifest_path, expected_hash, repo


def _env(tmp_path: Path, *, include_kis: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / ".env"
    prefix = "KIS_PAPER_APP_SECRET=must-not-be-used\n" if include_kis else ""
    path.write_text(prefix + "TIINGO_API_TOKEN=test-token\n", encoding="utf-8")
    return path


def _payload(raw_value: str = "value") -> bytes:
    return json.dumps(
        [
            {
                "date": "2024-07-18T00:00:00.000Z",
                "open": "99",
                "high": "102",
                "low": "98",
                "close": "100",
                "volume": "1000",
                "divCash": "0",
                "splitFactor": "1",
                "ignored_raw_value": raw_value,
            },
            {
                "date": "2024-07-19T00:00:00.000Z",
                "open": "100",
                "high": "103",
                "low": "99",
                "close": "101",
                "volume": "1001",
                "divCash": "0",
                "splitFactor": "1",
                "ignored_raw_value": raw_value,
            },
        ]
    ).encode("utf-8")
