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

from thericher_v2.data.tiingo_coverage_probe import (
    TiingoCoverageProbeError,
    default_tiingo_coverage_probe_dir,
    load_tiingo_coverage_selection,
    run_tiingo_eod_coverage_probe,
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


def test_probe_uses_only_approved_token_and_persists_safe_external_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "KIS_PAPER_APP_SECRET=must-not-be-used\nTIINGO_API_TOKEN=token-for-test\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, str | None, float]] = []

    def opener(request, *, timeout: float):
        calls.append((request.full_url, request.get_header("Authorization"), timeout))
        return _Response(_payload("raw-value-must-not-persist"))

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("coverage probe must not cross this boundary")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    result = _run(
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
    assert result.empty_count == 0
    assert result.unavailable_count == 0
    assert [header for _, header, _ in calls] == ["Token token-for-test"] * 3
    assert all("token-for-test" not in url for url, _, _ in calls)
    assert all(f"startDate={_START.isoformat()}" in url for url, _, _ in calls)
    assert all(f"endDate={_END.isoformat()}" in url for url, _, _ in calls)

    summary_text = result.summary_path.read_text(encoding="utf-8")
    summary = json.loads(summary_text)
    assert result.summary_path.is_relative_to(root.parent / "artifacts")
    assert not result.summary_path.is_relative_to(repo)
    assert all(symbol not in summary_text for symbol in _SYMBOLS)
    assert "token-for-test" not in summary_text
    assert "must-not-be-used" not in summary_text
    assert "raw-value-must-not-persist" not in summary_text
    assert summary["candidate_union"]["selected_ranks"] == [1, 3, 6]
    assert summary["candidate_union"]["selected_symbols_persisted"] is False
    assert summary["responses"] == [
        {
            "candidate_rank": rank,
            "classification": "available",
            "error_class": None,
            "first_session": "2024-07-18",
            "http_status": 200,
            "last_session": "2024-07-19",
            "row_count": 2,
        }
        for rank in (1, 3, 6)
    ]
    assert not list(result.summary_path.parent.glob(".stage-*"))


@pytest.mark.parametrize("status", (401, 403, 429))
def test_auth_or_rate_limit_error_stops_without_retry(
    tmp_path: Path, status: int
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    calls = 0

    def opener(_request, *, timeout: float):
        nonlocal calls
        calls += 1
        raise HTTPError("https://api.tiingo.com", status, "denied", {}, None)

    result = _run(
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
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["request_budget"] == {"issued": 1, "maximum": 12, "retries": 0}
    assert summary["responses"][0]["error_class"] == f"http_{status}"


def test_not_found_continues_and_malformed_response_stops_cleanly(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    calls = 0

    def not_found_then_success(_request, *, timeout: float):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError("https://api.tiingo.com", 404, "missing", {}, None)
        return _Response(_payload())

    available = _run(
        root=root,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        expected_hash=expected_hash,
        env_path=_env(tmp_path),
        repo=repo,
        opener=not_found_then_success,
        sample_size=3,
    )
    assert available.completed is True
    assert available.request_count == 3
    assert available.unavailable_count == 1

    malformed_root, malformed_candidate, malformed_manifest, malformed_hash, malformed_repo = (
        _candidate_union(tmp_path / "malformed")
    )
    malformed_calls = 0

    def malformed(_request, *, timeout: float):
        nonlocal malformed_calls
        malformed_calls += 1
        return _Response(b'{"not": "an array"}')

    malformed_result = _run(
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
    assert malformed_result.completed is False
    assert malformed_result.stop_reason == "malformed_response"
    assert json.loads(malformed_result.summary_path.read_text(encoding="utf-8"))["responses"][0][
        "error_class"
    ] == "malformed_response"


def test_selection_is_hash_bound_and_storage_or_git_destination_fail_before_request(
    tmp_path: Path,
) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)
    selection = load_tiingo_coverage_selection(
        candidate_union_path=candidate_path,
        candidate_union_manifest_path=manifest_path,
        expected_candidate_union_hash=expected_hash,
        sample_size=3,
        market_data_root=root,
        repo_root=repo,
    )
    assert selection.selected_ranks == (1, 3, 6)
    assert selection.selected_symbols == ("ALFA", "CHARLIE", "FOXTROT")

    candidate_path.write_text("candidate_rank,symbol\n1,TAMPERED\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_tiingo_coverage_selection(
            candidate_union_path=candidate_path,
            candidate_union_manifest_path=manifest_path,
            expected_candidate_union_hash=expected_hash,
            sample_size=3,
            market_data_root=root,
            repo_root=repo,
        )

    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path / "floor")

    def unexpected_request(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("storage failure must happen before a request")

    with pytest.raises(ValueError, match="hard free-space"):
        _run(
            root=root,
            candidate_path=candidate_path,
            manifest_path=manifest_path,
            expected_hash=expected_hash,
            env_path=_env(tmp_path / "floor"),
            repo=repo,
            opener=unexpected_request,
            sample_size=3,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    assert not list((root.parent / "artifacts").glob("**/summary.json"))

    with pytest.raises(ValueError, match="outside Git"):
        _run(
            root=root,
            candidate_path=candidate_path,
            manifest_path=manifest_path,
            expected_hash=expected_hash,
            env_path=_env(tmp_path / "floor"),
            repo=repo,
            opener=unexpected_request,
            sample_size=3,
            destination=repo / "snapshot=2026-07-19-tiingo-eod-coverage-probe-r1",
        )


def test_redirect_is_classified_without_persisting_a_response(tmp_path: Path) -> None:
    root, candidate_path, manifest_path, expected_hash, repo = _candidate_union(tmp_path)

    def redirect(_request, *, timeout: float):
        raise TiingoCoverageProbeError("redirect")

    result = _run(
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


def test_default_destination_uses_external_artifact_root() -> None:
    destination = default_tiingo_coverage_probe_dir(date(2026, 7, 19))

    assert destination == Path(
        "D:/thericher-v2/model-artifacts/data-agent/tiingo-eod-coverage-probe/"
        "snapshot=2026-07-19-tiingo-eod-coverage-probe-r1"
    )


def _run(
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
    artifact_root = root.parent / "artifacts"
    return run_tiingo_eod_coverage_probe(
        candidate_union_path=candidate_path,
        candidate_union_manifest_path=manifest_path,
        expected_candidate_union_hash=expected_hash,
        env_path=env_path,
        destination=destination
        or artifact_root / "snapshot=2026-07-19-tiingo-eod-coverage-probe-r1",
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        sample_size=sample_size,
        market_data_root=root,
        artifact_root=artifact_root,
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


def _env(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / ".env"
    path.write_text("TIINGO_API_TOKEN=test-token\n", encoding="utf-8")
    return path


def _payload(raw_value: str = "value") -> bytes:
    return json.dumps(
        [
            {"date": "2024-07-18T00:00:00.000Z", "ignored_raw_value": raw_value},
            {"date": "2024-07-19T00:00:00.000Z", "ignored_raw_value": raw_value},
        ]
    ).encode("utf-8")
