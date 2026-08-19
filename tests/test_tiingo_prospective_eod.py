from __future__ import annotations

import ast
import json
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

import thericher_v2.data.tiingo_prospective_eod as prospective


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


@pytest.fixture
def roots() -> Iterator[tuple[Path, Path, Path]]:
    with tempfile.TemporaryDirectory(prefix="tr-prospective-") as temporary:
        root = Path(temporary)
        market_root = root / "market-data"
        market_root.mkdir()
        repo_root = root / "repo"
        repo_root.mkdir()
        env_path = root / "test.env"
        env_path.write_text(
            "KIS_PAPER_APP_KEY=must-not-read\n"
            "TIINGO_API_TOKEN=test-tiingo-token\n"
            "KIS_LIVE_APP_KEY=must-not-read\n",
            encoding="utf-8",
        )
        yield market_root, repo_root, env_path


def test_acquires_exact_fixed_scope_with_safe_token_and_strict_offline_loader(
    roots: tuple[Path, Path, Path],
) -> None:
    market_root, repo_root, env_path = roots
    calls: list[tuple[str, str | None, float]] = []

    def opener(request, *, timeout: float):
        calls.append((request.full_url, request.get_header("Authorization"), timeout))
        return _Response(_payload(request.full_url.rsplit("/", 1)[-1].split("/", 1)[0]))

    snapshot = _acquire(
        market_root=market_root,
        repo_root=repo_root,
        env_path=env_path,
        opener=opener,
    )

    assert [url.split("/prices?", 1)[0].rsplit("/", 1)[-1] for url, _, _ in calls] == [
        "SPY",
        "QQQ",
        "IWM",
    ]
    assert len(calls) == prospective.MAX_TIINGO_PROSPECTIVE_EOD_REQUESTS
    assert [header for _, header, _ in calls] == ["Token test-tiingo-token"] * 3
    assert all("test-tiingo-token" not in url for url, _, _ in calls)
    assert all("startDate=2026-07-10" in url and "endDate=2026-07-13" in url for url, _, _ in calls)
    assert snapshot.snapshot_dir == prospective.default_tiingo_prospective_eod_dir(
        date(2026, 7, 20), market_data_root=market_root
    )
    assert tuple(item.symbol for item in snapshot.raw_files) == ("SPY", "QQQ", "IWM")
    assert snapshot.row_count == 6
    assert snapshot.prospective_lineage_only is True
    assert snapshot.model_eligible is False
    assert snapshot.training_eligible is False
    assert snapshot.campaign_eligible is False
    assert snapshot.paper_trading_eligible is False
    assert snapshot.ranking_eligible is False
    assert snapshot.order_eligible is False
    assert snapshot.point_in_time_eligible is False

    expected_files = {
        "manifest.json",
        "normalized_ohlcv_1d.csv",
        "raw/SPY.json",
        "raw/QQQ.json",
        "raw/IWM.json",
    }
    actual_files = {
        path.relative_to(snapshot.snapshot_dir).as_posix()
        for path in snapshot.snapshot_dir.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    manifest_text = (snapshot.snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["scope"] == {
        "prospective_lineage_only": True,
        "model_eligible": False,
        "training_eligible": False,
        "campaign_eligible": False,
        "paper_trading_eligible": False,
        "ranking_eligible": False,
        "order_eligible": False,
        "point_in_time_eligible": False,
    }
    assert manifest["rights"] == {
        "terms_url": prospective.TIINGO_TERMS_URL,
        "use_scope": "private_internal_use",
        "internal_use_clause": prospective.TIINGO_INTERNAL_USE_CLAUSE,
        "redistribution_eligible": False,
    }
    assert "test-tiingo-token" not in manifest_text
    assert "must-not-read" not in manifest_text
    loaded = prospective.load_tiingo_prospective_eod_snapshot(
        snapshot.snapshot_dir,
        expected_dataset_hash=snapshot.dataset_hash,
        expected_manifest_hash=snapshot.manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )
    assert loaded == snapshot
    assert not hasattr(loaded, "bars")


def test_loader_rejects_tampering_and_never_reads_token_or_network(
    roots: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root, repo_root, env_path = roots
    snapshot = _acquire(
        market_root=market_root,
        repo_root=repo_root,
        env_path=env_path,
        opener=lambda _request, *, timeout: _Response(_payload("SPY")),
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "offline prospective loader must not read a token or access the network"
        )

    monkeypatch.setattr(prospective, "read_tiingo_api_token", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    raw_path = snapshot.snapshot_dir / "raw" / "SPY.json"
    original = raw_path.read_bytes()
    raw_path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="raw (hash|size) mismatch"):
        prospective.load_tiingo_prospective_eod_snapshot(
            snapshot.snapshot_dir,
            market_data_root=market_root,
            repo_root=repo_root,
        )
    raw_path.write_bytes(original)

    normalized = snapshot.snapshot_dir / "normalized_ohlcv_1d.csv"
    normalized.write_bytes(normalized.read_bytes() + b"tampered\n")
    with pytest.raises(ValueError, match="normalized CSV"):
        prospective.load_tiingo_prospective_eod_snapshot(
            snapshot.snapshot_dir,
            market_data_root=market_root,
            repo_root=repo_root,
        )


def test_preflight_path_window_storage_and_overwrite_fail_before_requests(
    roots: tuple[Path, Path, Path],
) -> None:
    market_root, repo_root, env_path = roots

    def unexpected_request(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("preflight failure must happen before a Tiingo request")

    retrieved_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="predates the approved boundary"):
        prospective.acquire_tiingo_prospective_eod_snapshot(
            env_path=env_path,
            requested_start=date(2026, 7, 9),
            source_as_of=date(2026, 7, 13),
            retrieved_at_utc=retrieved_at,
            market_data_root=market_root,
            repo_root=repo_root,
            opener=unexpected_request,
        )
    with pytest.raises(ValueError, match="complete source boundary"):
        prospective.acquire_tiingo_prospective_eod_snapshot(
            env_path=env_path,
            requested_start=date(2026, 7, 10),
            source_as_of=date(2026, 7, 14),
            retrieved_at_utc=retrieved_at,
            market_data_root=market_root,
            repo_root=repo_root,
            opener=unexpected_request,
        )
    with pytest.raises(ValueError, match="hard free-space"):
        prospective.acquire_tiingo_prospective_eod_snapshot(
            env_path=env_path,
            requested_start=date(2026, 7, 10),
            source_as_of=date(2026, 7, 13),
            retrieved_at_utc=retrieved_at,
            market_data_root=market_root,
            repo_root=repo_root,
            opener=unexpected_request,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    with pytest.warns(RuntimeWarning, match="20%"):
        with pytest.raises(AssertionError, match="preflight failure"):
            prospective.acquire_tiingo_prospective_eod_snapshot(
                env_path=env_path,
                requested_start=date(2026, 7, 10),
                source_as_of=date(2026, 7, 13),
                retrieved_at_utc=retrieved_at,
                market_data_root=market_root,
                repo_root=repo_root,
                opener=unexpected_request,
                disk_usage=lambda _path: SimpleNamespace(total=100, free=19),
            )
    with pytest.raises(ValueError, match="outside its fixed canonical root"):
        prospective.acquire_tiingo_prospective_eod_snapshot(
            env_path=env_path,
            requested_start=date(2026, 7, 10),
            source_as_of=date(2026, 7, 13),
            retrieved_at_utc=retrieved_at,
            destination=(
                market_root
                / "wrong"
                / "snapshot=2026-07-20-tiingo-standard-eod-prospective-r1"
            ),
            market_data_root=market_root,
            repo_root=repo_root,
            opener=unexpected_request,
        )

    snapshot = _acquire(
        market_root=market_root,
        repo_root=repo_root,
        env_path=env_path,
        opener=lambda _request, *, timeout: _Response(_payload("SPY")),
    )
    with pytest.raises(FileExistsError, match="another window"):
        prospective.acquire_tiingo_prospective_eod_snapshot(
            env_path=env_path,
            requested_start=date(2026, 7, 10),
            source_as_of=date(2026, 7, 12),
            retrieved_at_utc=retrieved_at,
            destination=snapshot.snapshot_dir,
            market_data_root=market_root,
            repo_root=repo_root,
            opener=unexpected_request,
        )


def test_request_budget_is_exact_no_retry_and_redirects_are_rejected(
    roots: tuple[Path, Path, Path],
) -> None:
    market_root, repo_root, env_path = roots
    calls = 0

    def fail_first(_request, *, timeout: float):
        nonlocal calls
        calls += 1
        raise HTTPError("https://api.tiingo.com", 429, "rate", {}, None)

    with pytest.raises(prospective.TiingoProspectiveEodError, match="HTTP 429"):
        _acquire(
            market_root=market_root,
            repo_root=repo_root,
            env_path=env_path,
            opener=fail_first,
        )
    assert calls == 1
    target = prospective.default_tiingo_prospective_eod_dir(
        date(2026, 7, 20), market_data_root=market_root
    )
    assert not target.exists()
    assert not list(target.parent.glob(".stage-*")) if target.parent.exists() else True
    with pytest.raises(prospective.TiingoProspectiveEodError, match="redirects are not allowed"):
        prospective._RejectRedirect().redirect_request(None, None, 302, "", None, "https://elsewhere")


def test_script_clamps_source_as_of_and_module_has_no_bar_catalog_promotion() -> None:
    retrieved_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    assert prospective.latest_source_complete_date(retrieved_at) == date(2026, 7, 13)
    assert prospective.clamp_source_as_of(date(2026, 7, 18), retrieved_at_utc=retrieved_at) == date(
        2026, 7, 13
    )
    assert prospective.clamp_source_as_of(date(2026, 7, 11), retrieved_at_utc=retrieved_at) == date(
        2026, 7, 11
    )

    module_path = Path(prospective.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "Bar" not in imported
    assert "CatalogedBars" not in imported
    script_path = Path(__file__).parents[1] / "scripts" / "acquire_tiingo_prospective_eod.py"
    assert "env_path=Path(\".env\")" in script_path.read_text(encoding="utf-8")


def test_existing_matching_snapshot_is_reused_without_a_new_token_or_request(
    roots: tuple[Path, Path, Path],
) -> None:
    market_root, repo_root, env_path = roots
    snapshot = _acquire(
        market_root=market_root,
        repo_root=repo_root,
        env_path=env_path,
        opener=lambda _request, *, timeout: _Response(_payload("SPY")),
    )

    def unexpected_request(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("matching immutable snapshot must be reused")

    reused = prospective.acquire_tiingo_prospective_eod_snapshot(
        env_path=env_path,
        requested_start=snapshot.requested_start,
        source_as_of=snapshot.source_as_of,
        retrieved_at_utc=snapshot.retrieved_at_utc,
        market_data_root=market_root,
        repo_root=repo_root,
        opener=unexpected_request,
    )
    assert reused == snapshot


def _acquire(
    *,
    market_root: Path,
    repo_root: Path,
    env_path: Path,
    opener,
):
    return prospective.acquire_tiingo_prospective_eod_snapshot(
        env_path=env_path,
        requested_start=date(2026, 7, 10),
        source_as_of=date(2026, 7, 13),
        retrieved_at_utc=datetime(2026, 7, 20, 8, tzinfo=UTC),
        market_data_root=market_root,
        repo_root=repo_root,
        opener=opener,
        disk_usage=lambda _path: SimpleNamespace(total=100, free=100),
    )


def _payload(symbol: str) -> bytes:
    rows = [
        {
            "date": "2026-07-10T00:00:00.000Z",
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 1234,
            "divCash": 0,
            "splitFactor": 1,
            "adjClose": 999,
            "symbol": symbol,
        },
        {
            "date": "2026-07-13T00:00:00.000Z",
            "open": 101,
            "high": 103,
            "low": 100,
            "close": 102,
            "volume": 2345,
            "divCash": 0,
            "splitFactor": 1,
            "adjClose": 998,
            "symbol": symbol,
        },
    ]
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")
