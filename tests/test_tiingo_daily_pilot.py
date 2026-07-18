from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from thericher_v2.data.norgate_candidate_union import rank_quantile_ranks
from thericher_v2.data.tiingo_daily_pilot import (
    TIINGO_INTERNAL_USE_CLAUSE,
    TIINGO_TERMS_URL,
    TiingoDailyPilotError,
    acquire_tiingo_daily_pilot,
    default_tiingo_daily_pilot_dir,
    verify_tiingo_daily_pilot_snapshot,
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


def _candidate_union(tmp_path: Path) -> tuple[Path, Path, Path, str, Path]:
    root = tmp_path / "market_data"
    snapshot = root / "norgate" / "snapshot=fixture"
    snapshot.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate_path = snapshot / "candidate_union.csv"
    rows = "".join(f"{rank},{symbol}\n" for rank, symbol in enumerate(_SYMBOLS, start=1))
    candidate_bytes = ("candidate_rank,symbol\n" + rows).encode("utf-8")
    candidate_path.write_bytes(candidate_bytes)
    expected_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
    manifest_path = snapshot / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "norgate_sp500_current_past_membership_matrix",
                "candidate_count": len(_SYMBOLS),
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
