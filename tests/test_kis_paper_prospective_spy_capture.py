from __future__ import annotations

import builtins
import io
import json
import os
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import thericher_v2.data.kis_paper_prospective_spy_capture as capture
import thericher_v2.models.prospective_spy_intraday_observation as observation_module
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

_FORBIDDEN_SAFE_KEYS = frozenset(
    {
        "account",
        "broker",
        "close",
        "credential",
        "file",
        "fill",
        "high",
        "low",
        "ohlcv",
        "open",
        "order",
        "password",
        "path",
        "position",
        "price",
        "quantity",
        "secret",
        "token",
        "volume",
    }
)


def test_capture_writes_one_canonical_external_receipt_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    catalog = _catalog(session_date)
    calls = _install_catalog(monkeypatch, catalog)
    _deny_external_or_credential_access(monkeypatch)
    repo_root = tmp_path / "repo"
    cache_root = tmp_path / "market-data"
    artifact_root = tmp_path / "model-artifacts"
    repo_root.mkdir()

    first = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=_cutoff(session),
    )

    assert first.status == "captured"
    assert first.receipt is not None
    assert first.artifact_path is not None
    assert first.artifact_path.is_relative_to(artifact_root)
    assert not first.artifact_path.is_relative_to(repo_root)
    assert first.artifact_path.read_text(encoding="utf-8").strip() == first.receipt.canonical_json()
    assert json.loads(first.artifact_path.read_text(encoding="utf-8")) == first.receipt.to_payload()
    _assert_safe_payload(first.safe_payload())
    rendered_payload = json.dumps(first.safe_payload(), ensure_ascii=True, sort_keys=True)
    assert str(cache_root) not in rendered_payload
    for raw_source_value in ("101.234", "102.234", "100.734", "99123"):
        assert raw_source_value not in rendered_payload

    second = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=_cutoff(session),
    )

    assert second.status == "captured"
    assert second.receipt is not None
    assert second.artifact_path == first.artifact_path
    assert second.receipt.receipt_id == first.receipt.receipt_id
    assert second.artifact_path.read_bytes() == first.artifact_path.read_bytes()
    assert calls == [
        {
            "cache_root": cache_root,
            "repo_root": repo_root,
            "symbol": "SPY",
            "exchange": "AMS",
        },
        {
            "cache_root": cache_root,
            "repo_root": repo_root,
            "symbol": "SPY",
            "exchange": "AMS",
        },
    ]


def test_receipt_loader_revalidates_the_exact_canonical_capture_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    _install_catalog(monkeypatch, _catalog(session_date))
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()

    captured = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=_cutoff(session),
    )
    loaded = capture.load_kis_paper_prospective_spy_observation_receipt(
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
    )

    assert captured.receipt is not None
    assert loaded == captured.receipt
    assert loaded.canonical_json() == captured.receipt.canonical_json()


def test_receipt_loader_rejects_a_noncanonical_or_wrong_session_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    _install_catalog(monkeypatch, _catalog(session_date))
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    captured = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=_cutoff(session),
    )
    assert captured.artifact_path is not None
    captured.artifact_path.write_text(captured.receipt.canonical_json() + "\n\n", encoding="utf-8")  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="canonical"):
        capture.load_kis_paper_prospective_spy_observation_receipt(
            artifact_root=artifact_root,
            repo_root=repo_root,
            session_date=session_date,
        )
    with pytest.raises(ValueError, match="unavailable"):
        capture.load_kis_paper_prospective_spy_observation_receipt(
            artifact_root=artifact_root,
            repo_root=repo_root,
            session_date=date(2026, 8, 4),
        )


def test_receipt_loader_rejects_a_rehashed_canonical_receipt_with_extended_ttl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    _install_catalog(monkeypatch, _catalog(session_date))
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    captured = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=_cutoff(session),
    )
    assert captured.receipt is not None
    assert captured.artifact_path is not None
    payload = captured.receipt.to_payload()
    extended_valid_until = captured.receipt.valid_until + timedelta(minutes=1)
    payload["valid_until"] = extended_valid_until.isoformat().replace("+00:00", "Z")
    payload["receipt_id"] = observation_module._receipt_id(
        {key: value for key, value in payload.items() if key != "receipt_id"}
    )
    captured.artifact_path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="decision timing"):
        capture.load_kis_paper_prospective_spy_observation_receipt(
            artifact_root=artifact_root,
            repo_root=repo_root,
            session_date=session_date,
        )


@pytest.mark.parametrize(
    ("session_date", "cutoff_utc"),
    [
        (date(2026, 3, 9), datetime(2026, 3, 9, 19, 30, tzinfo=UTC)),
        (date(2026, 11, 2), datetime(2026, 11, 2, 20, 30, tzinfo=UTC)),
    ],
    ids=["daylight-saving", "standard-time"],
)
def test_capture_requires_the_fixed_1530_eastern_cutoff_across_dst(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session_date: date,
    cutoff_utc: datetime,
) -> None:
    session = _regular_session(session_date)
    assert _cutoff(session) == cutoff_utc
    _install_catalog(monkeypatch, _catalog(session_date))
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()

    before_cutoff = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=cutoff_utc - timedelta(microseconds=1),
    )

    assert before_cutoff.status == "not_yet_observed"
    assert before_cutoff.receipt is None
    assert before_cutoff.artifact_path is None
    assert not _files_below(artifact_root)
    _assert_safe_payload(before_cutoff.safe_payload())

    at_cutoff = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=cutoff_utc,
    )

    assert at_cutoff.status == "captured"
    assert at_cutoff.receipt is not None
    assert at_cutoff.artifact_path is not None


def test_capture_returns_not_yet_observed_for_incomplete_or_noncurrent_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    incomplete = _catalog(session_date, minute_count=359)
    calls = _install_catalog(monkeypatch, incomplete)
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()

    incomplete_result = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=_cutoff(session),
    )

    assert incomplete_result.status == "not_yet_observed"
    assert incomplete_result.receipt is None
    assert incomplete_result.artifact_path is None
    assert not _files_below(artifact_root)
    _assert_safe_payload(incomplete_result.safe_payload())
    assert len(calls) == 1

    noncurrent_result = capture.capture_kis_paper_prospective_spy_observation(
        cache_root=tmp_path / "market-data",
        artifact_root=artifact_root,
        repo_root=repo_root,
        session_date=session_date,
        observed_at=datetime(2026, 8, 4, 19, 30, tzinfo=UTC),
    )

    assert noncurrent_result.status == "not_yet_observed"
    assert noncurrent_result.receipt is None
    assert noncurrent_result.artifact_path is None
    assert not _files_below(artifact_root)
    _assert_safe_payload(noncurrent_result.safe_payload())
    assert len(calls) == 1


def test_capture_rejects_a_different_receipt_for_the_same_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    catalog = _catalog(session_date)
    current_catalog = catalog

    def load_catalog(**_kwargs: object) -> CatalogedBars:
        return current_catalog

    monkeypatch.setattr(capture, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    kwargs = {
        "cache_root": tmp_path / "market-data",
        "artifact_root": artifact_root,
        "repo_root": repo_root,
        "session_date": session_date,
        "observed_at": _cutoff(session),
    }

    first = capture.capture_kis_paper_prospective_spy_observation(**kwargs)
    assert first.status == "captured"

    current_catalog = _catalog(session_date, changed_minute=358)
    with pytest.raises(ValueError, match="conflict"):
        capture.capture_kis_paper_prospective_spy_observation(**kwargs)


def test_capture_ignores_post_cutoff_cache_growth_for_the_same_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    current_catalog = _catalog(session_date, dataset_hash_character="a")

    def load_catalog(**_kwargs: object) -> CatalogedBars:
        return current_catalog

    monkeypatch.setattr(capture, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repo_root.mkdir()
    kwargs = {
        "cache_root": tmp_path / "market-data",
        "artifact_root": artifact_root,
        "repo_root": repo_root,
        "session_date": session_date,
        "observed_at": _cutoff(session),
    }

    first = capture.capture_kis_paper_prospective_spy_observation(**kwargs)
    assert first.status == "captured"
    assert first.receipt is not None

    current_catalog = _catalog(
        session_date,
        changed_minute=360,
        dataset_hash_character="b",
    )
    second = capture.capture_kis_paper_prospective_spy_observation(**kwargs)

    assert second.status == "captured"
    assert second.receipt == first.receipt
    assert second.artifact_path == first.artifact_path


def test_capture_rejects_artifacts_inside_the_git_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_date = date(2026, 8, 3)
    session = _regular_session(session_date)
    _install_catalog(monkeypatch, _catalog(session_date))
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        capture.capture_kis_paper_prospective_spy_observation(
            cache_root=tmp_path / "market-data",
            artifact_root=repo_root / "model-artifacts",
            repo_root=repo_root,
            session_date=session_date,
            observed_at=_cutoff(session),
        )


def _install_catalog(
    monkeypatch: pytest.MonkeyPatch,
    catalog: CatalogedBars,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def load_catalog(**kwargs: object) -> CatalogedBars:
        calls.append(dict(kwargs))
        return catalog

    monkeypatch.setattr(capture, "load_verified_kis_paper_private_intraday_catalog", load_catalog)
    return calls


def _catalog(
    session_date: date,
    *,
    minute_count: int = 390,
    changed_minute: int | None = None,
    dataset_hash_character: str = "a",
) -> CatalogedBars:
    session = _regular_session(session_date)
    bars = tuple(
        _bar(
            session.window.open_ts + Timeframe.M1.duration * index,
            changed=index == changed_minute,
        )
        for index in range(minute_count)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.spy.ams.m1.validation-v1",
        dataset_hash="sha256:" + dataset_hash_character * 64,
        source_path=Path("D:/market_data/spy-ams-validation-index.json"),
        bars=bars,
    )


def _bar(start_ts: datetime, *, changed: bool) -> Bar:
    opened = Decimal("101.234") + Decimal(start_ts.minute) / Decimal("1000")
    if changed:
        opened += Decimal("0.001")
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("1.000"),
        low=opened - Decimal("0.500"),
        close=opened + Decimal("0.200"),
        volume=Decimal("99123"),
        complete=True,
    )


def _regular_session(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None and session.kind == "regular"
    return session


def _cutoff(session) -> datetime:
    local_open = session.window.open_ts.astimezone(US_EQUITY_EASTERN)
    return datetime.combine(local_open.date(), datetime.min.time(), US_EQUITY_EASTERN).replace(
        hour=15,
        minute=30,
    ).astimezone(UTC)


def _files_below(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()] if root.exists() else []


def _assert_safe_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            assert key.casefold() not in _FORBIDDEN_SAFE_KEYS
            _assert_safe_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe_payload(nested)
    else:
        assert value is None or isinstance(value, (str, int, bool))


def _deny_external_or_credential_access(monkeypatch: pytest.MonkeyPatch) -> None:
    original_open = builtins.open
    original_io_open = io.open
    original_path_open = Path.open

    def guarded_open(file: object, *args: object, **kwargs: object) -> Any:
        _reject_dotenv_read(file)
        return original_open(file, *args, **kwargs)

    def guarded_io_open(file: object, *args: object, **kwargs: object) -> Any:
        _reject_dotenv_read(file)
        return original_io_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args: object, **kwargs: object) -> Any:
        _reject_dotenv_read(path)
        return original_path_open(path, *args, **kwargs)

    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("capture runner must not access the network or credentials")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_io_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(os, "getenv", deny)
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)


def _reject_dotenv_read(file: object) -> None:
    try:
        if Path(file).name.casefold() == ".env":
            raise AssertionError("capture runner must not read .env")
    except TypeError:
        return
