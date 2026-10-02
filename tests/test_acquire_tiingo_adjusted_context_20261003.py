from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import socket
import urllib.request
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

import thericher_v2.data.tiingo_etf_daily as daily

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "acquire_tiingo_adjusted_context_20261003.py"
)
_RETRIEVED_AT = datetime(2026, 10, 2, 17, 30, 1, tzinfo=UTC)
_SECRET = "synthetic-tiingo-secret-never-output"
_PRIVATE_BODY = "synthetic-private-error-body-never-output"


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _raw_payload() -> bytes:
    return json.dumps(
        [
            {
                "date": f"{session}T00:00:00.000Z",
                "open": "123.4567",
                "high": "125.4567",
                "low": "122.4567",
                "close": "124.4567",
                "volume": "1234567",
                "divCash": "0",
                "splitFactor": "1",
                "adjOpen": "121.4567",
                "adjHigh": "123.4567",
                "adjLow": "120.4567",
                "adjClose": "122.4567",
            }
            for session in ("2025-07-01", "2026-07-31", "2026-08-31", "2026-09-30")
        ],
        sort_keys=True,
    ).encode()


@pytest.fixture
def package(tmp_path: Path, monkeypatch):
    def deny(*_args: object, **_kwargs: object):
        raise AssertionError("real network or credential access forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(daily, "build_opener", deny)
    monkeypatch.setattr(daily, "read_tiingo_api_token", deny)
    spec = importlib.util.spec_from_file_location("adjusted_context_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    canonical_root = market_root / "us_equities" / "tiingo_etf_daily" / "canonical"
    monkeypatch.setattr(daily, "DEFAULT_TIINGO_ETF_D1_ROOT", canonical_root)
    monkeypatch.setattr(script, "DEFAULT_MARKET_DATA_ROOT", market_root)
    monkeypatch.setattr(script, "_REPOSITORY_ROOT", repo_root)
    monkeypatch.setattr(script, "datetime", SimpleNamespace(now=lambda _tz: _RETRIEVED_AT))
    return SimpleNamespace(
        script=script,
        market_root=market_root,
        repo_root=repo_root,
        destination=canonical_root / "snapshot=20261002T173001Z-tiingo-etf-d1-r1",
    )


def _install_fake_acquisition(package, monkeypatch, *, opener=None):
    requests = []
    token_paths = []

    def fake_token(path: Path) -> str:
        token_paths.append(path)
        assert path == package.repo_root / ".env"
        return _SECRET

    def fake_endpoint(request, *, timeout: float):
        requests.append(request)
        assert timeout == 30.0
        return _Response(_raw_payload())

    monkeypatch.setattr(daily, "read_tiingo_api_token", fake_token)
    monkeypatch.setattr(
        package.script,
        "acquire_tiingo_etf_d1_snapshot",
        partial(
            daily.acquire_tiingo_etf_d1_snapshot,
            opener=opener or fake_endpoint,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=80),
        ),
    )
    return requests, token_paths


def _safe_output(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    for forbidden in (_SECRET, _PRIVATE_BODY, "123.4567", "adjClose", "Authorization"):
        assert forbidden not in captured.out
    return json.loads(captured.out)


def test_default_is_plan_only_without_credentials_network_or_writes(package, capsys) -> None:
    assert package.script.main([]) == 0
    output = _safe_output(capsys)
    assert output["status"] == "plan_only"
    assert output["symbols"] == ["SPY", "QQQ", "IWM"]
    assert output["planned_request_count"] == 3
    assert output["request_range"] == {"start": "2025-07-01", "end": "2026-09-30"}
    assert output["snapshot_dir"] == str(package.destination)
    assert output["retrieved_at_utc"] == _RETRIEVED_AT.isoformat()
    assert "completed_request_count" not in output
    assert not tuple(package.market_root.iterdir())
    assert not tuple(package.repo_root.iterdir())


def test_explicit_acquire_retains_one_new_vintage_for_exact_trio(
    package, monkeypatch, capsys
) -> None:
    frozen = package.destination.parent / "snapshot=20260809T163557Z-tiingo-etf-d1-r1"
    frozen.mkdir(parents=True)
    sentinel = frozen / "sentinel"
    sentinel.write_bytes(b"unchanged frozen fixture")
    requests, token_paths = _install_fake_acquisition(package, monkeypatch)
    assert package.script.main(["--acquire"]) == 0
    output = _safe_output(capsys)
    assert output["status"] == "acquired"
    assert output["completed_request_count"] == 3
    assert output["row_count"] == 12
    assert output["session_counts"] == {symbol: 4 for symbol in ("SPY", "QQQ", "IWM")}
    assert len(requests) == 3
    assert token_paths == [package.repo_root / ".env"]
    assert not (package.repo_root / ".env").exists()
    assert [urlparse(request.full_url).path for request in requests] == [
        f"/tiingo/daily/{symbol}/prices" for symbol in ("SPY", "QQQ", "IWM")
    ]
    for request in requests:
        parsed = urlparse(request.full_url)
        assert parsed.scheme == "https" and parsed.netloc == "api.tiingo.com"
        assert parse_qs(parsed.query) == {"startDate": ["2025-07-01"], "endDate": ["2026-09-30"]}
        assert request.get_header("Authorization") == f"Token {_SECRET}"
        assert _SECRET not in request.full_url
    manifest_bytes = (package.destination / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["retrieved_at_utc"] == "2026-10-02T17:30:01Z"
    assert manifest["requested_window"] == output["request_range"]
    assert output["manifest_hash"] == "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    assert manifest["source_contract"]["adjusted_fields_used"] is False
    assert manifest["scope"]["point_in_time_eligible"] is False
    assert manifest["scope"]["sealed_holdout_eligible"] is False
    for symbol in ("SPY", "QQQ", "IWM"):
        raw = (package.destination / "raw" / f"{symbol}.json").read_bytes()
        assert raw == _raw_payload()
        assert output["raw_hashes"][symbol] == "sha256:" + hashlib.sha256(raw).hexdigest()
    loaded = daily.load_verified_tiingo_etf_d1_snapshot(
        package.destination,
        dataset_id=output["dataset_id"],
        expected_dataset_hash=output["dataset_hash"],
        expected_manifest_hash=output["manifest_hash"],
        market_data_root=package.market_root,
        repo_root=package.repo_root,
    )
    assert loaded.snapshot.row_count == 12
    assert sentinel.read_bytes() == b"unchanged frozen fixture"
    assert not tuple(package.repo_root.iterdir())


@pytest.mark.parametrize("collision_kind", ["file", "directory"])
def test_collision_stops_before_token_or_endpoint(package, capsys, collision_kind) -> None:
    package.destination.parent.mkdir(parents=True)
    if collision_kind == "file":
        package.destination.write_bytes(b"existing fixture")
    else:
        package.destination.mkdir()
        (package.destination / "sentinel").write_bytes(b"existing fixture")
    assert package.script.main(["--acquire"]) == 1
    assert _safe_output(capsys)["status"] == "destination_exists"
    sentinel = package.destination if collision_kind == "file" else package.destination / "sentinel"
    assert sentinel.read_bytes() == b"existing fixture"


def test_provider_failure_is_masked_without_retry(package, monkeypatch, capsys) -> None:
    calls = []

    def failed_endpoint(request, *, timeout: float):
        calls.append(request)
        raise HTTPError(request.full_url, 403, _SECRET, {}, io.BytesIO(_PRIVATE_BODY.encode()))

    _install_fake_acquisition(package, monkeypatch, opener=failed_endpoint)
    assert package.script.main(["--acquire"]) == 1
    output = _safe_output(capsys)
    assert output["status"] == "acquisition_unavailable"
    assert "completed_request_count" not in output
    assert len(calls) == 1
    assert not package.destination.exists()
    assert not tuple(package.destination.parent.iterdir())


@pytest.mark.parametrize("error_type", [OSError, ValueError, RuntimeError, KeyError])
def test_exception_text_never_reaches_output(package, monkeypatch, capsys, error_type) -> None:
    def fail(**_kwargs):
        raise error_type(f"{_SECRET} {_PRIVATE_BODY}")

    monkeypatch.setattr(package.script, "acquire_tiingo_etf_d1_snapshot", fail)
    assert package.script.main(["--acquire"]) == 1
    assert _safe_output(capsys)["status"] == "acquisition_unavailable"
    assert not tuple(package.market_root.iterdir())


@pytest.mark.parametrize("flag", ["--start", "--end", "--symbol", "--env-path", "--ac"])
def test_scope_and_credential_overrides_are_not_cli_options(package, capsys, flag) -> None:
    with pytest.raises(SystemExit) as error:
        package.script.main([flag])
    assert error.value.code == 2
    capsys.readouterr()
    assert not tuple(package.market_root.iterdir())
