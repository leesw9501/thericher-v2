from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

import thericher_v2.data.tiingo_adjusted_etf_daily as adjusted
import thericher_v2.data.tiingo_etf_daily as raw_module


@pytest.fixture
def source(tmp_path, monkeypatch):
    def deny(*_args, **_kwargs):
        raise AssertionError("network and credential access denied")

    monkeypatch.setattr(raw_module, "read_tiingo_api_token", deny)
    monkeypatch.setattr(raw_module, "build_opener", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    market = tmp_path / "market"
    repo = tmp_path / "repo"
    repo.mkdir()
    root = market / adjusted.SNAPSHOT_RELATIVE_PATH
    (root / "raw").mkdir(parents=True)
    (root / "manifest.json").write_bytes(b"synthetic manifest")
    (root / "ohlcv_1d.csv.gz").write_bytes(b"synthetic canonical")
    payloads, canonical, hashes, calls = {}, {}, {}, []
    for symbol in raw_module.TIINGO_ETF_D1_SYMBOLS:
        payloads[symbol] = [
            {
                "date": f"2024-01-0{day}T00:00:00.000Z",
                "open": "100", "high": "102", "low": "99", "close": "101",
                "volume": "1000", "divCash": "1", "splitFactor": "2",
                "adjOpen": 50.125, "adjHigh": "51", "adjLow": "49.5", "adjClose": "50.5",
            }
            for day in (2, 3)
        ]
        raw = json.dumps(payloads[symbol]).encode()
        (root / "raw" / f"{symbol}.json").write_bytes(raw)
        hashes[symbol] = "sha256:" + hashlib.sha256(raw).hexdigest()
        canonical[symbol] = raw_module.normalize_tiingo_etf_d1_response(
            symbol=symbol, raw_response=raw
        )

    def verified(directory, **kwargs):
        assert directory == root
        assert kwargs == {
            "dataset_id": adjusted.DATASET_ID,
            "expected_dataset_hash": adjusted.DATASET_SHA256,
            "expected_manifest_hash": adjusted.MANIFEST_SHA256,
            "market_data_root": market,
            "repo_root": repo,
        }
        calls.append("verified")
        return SimpleNamespace(rows_by_symbol=canonical)

    monkeypatch.setattr(adjusted, "load_verified_tiingo_etf_d1_snapshot", verified)
    monkeypatch.setattr(adjusted, "RAW_SHA256", MappingProxyType(hashes))

    def write(symbol="SPY", *, content=None, repin=True):
        raw = json.dumps(payloads[symbol]).encode() if content is None else content
        (root / "raw" / f"{symbol}.json").write_bytes(raw)
        if repin:
            hashes[symbol] = "sha256:" + hashlib.sha256(raw).hexdigest()

    return SimpleNamespace(
        root=root, market=market, repo=repo, payloads=payloads,
        canonical=canonical, calls=calls, write=write,
    )


def load(source):
    return adjusted.load_verified_adjusted_etf_snapshot(
        source.root, market_data_root=source.market, repo_root=source.repo
    )


def rejected(source):
    with pytest.raises(ValueError, match="^adjusted ETF snapshot verification failed$"):
        load(source)


def test_verified_loader_precedes_raw_reads(source, monkeypatch, capsys):
    before = {p: p.read_bytes() for p in source.root.rglob("*") if p.is_file()}
    reader = adjusted._read_snapshot_file

    def read(*args):
        assert source.calls == ["verified"]
        return reader(*args)

    monkeypatch.setattr(adjusted, "_read_snapshot_file", read)
    result = load(source)
    assert tuple(result) == ("SPY", "QQQ", "IWM")
    row = result["SPY"][0]
    assert row == adjusted.AdjustedEtfRow(
        "SPY", date(2024, 1, 2), Decimal("50.125"), Decimal("51"),
        Decimal("49.5"), Decimal("50.5"),
    )
    assert isinstance(result["SPY"], tuple)
    assert not hasattr(row, "div_cash") and not hasattr(row, "split_factor")
    assert "50.125" not in repr(row)
    with pytest.raises(FrozenInstanceError):
        row.adj_close = Decimal("1")
    with pytest.raises(TypeError):
        result["SPY"] = ()
    assert before == {p: p.read_bytes() for p in source.root.rglob("*") if p.is_file()}
    assert capsys.readouterr() == ("", "")


def test_upstream_verification_failure_is_masked(source, monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise ValueError("private-value-must-not-escape")

    monkeypatch.setattr(adjusted, "load_verified_tiingo_etf_d1_snapshot", fail)
    rejected(source)
    assert capsys.readouterr() == ("", "")


def test_raw_tamper_rejected_and_old_rows_stay_frozen(source):
    original = load(source)
    source.payloads["SPY"][0]["adjClose"] = "50.75"
    source.write(repin=False)
    rejected(source)
    assert original["SPY"][0].adj_close == Decimal("50.5")


@pytest.mark.parametrize("content", [b"{}", b"[]", b"[null]", b"not-json", b"\xff"])
def test_response_shape_and_encoding(source, content):
    source.write(content=content)
    rejected(source)


@pytest.mark.parametrize("change", ["missing", "extra", "reverse", "duplicate", "not_object"])
def test_count_order_duplicates_and_row_shape(source, change):
    rows = source.payloads["SPY"]
    if change == "missing":
        rows.pop()
    elif change == "extra":
        rows.append(dict(rows[-1]))
    elif change == "reverse":
        rows.reverse()
    elif change == "duplicate":
        rows[-1] = dict(rows[0])
    else:
        rows[0] = None
    source.write()
    rejected(source)


@pytest.mark.parametrize("stamp", [
    None, "2024-01-02", "2024-01-02T01:00:00.000Z", "2024-01-02T00:00:00+00:00",
    "2024-01-02T00:00:00.001Z", "2024-01-04T00:00:00.000Z",
    "2024-02-30T00:00:00.000Z",
])
def test_exact_utc_midnight_session_label(source, stamp):
    source.payloads["SPY"][0]["date"] = stamp
    source.write()
    rejected(source)


@pytest.mark.parametrize(
    "key", ["adjOpen", "adjHigh", "adjLow", "adjClose", "divCash", "splitFactor"]
)
def test_missing_required_fields(source, key):
    del source.payloads["SPY"][0][key]
    source.write()
    rejected(source)


@pytest.mark.parametrize("value", [
    None, True, 0, -1, "NaN", "Infinity", "-Infinity", "not-a-number", [], {},
    float("nan"), float("inf"),
])
def test_nonpositive_nonfinite_and_invalid_adjusted_fields(source, value):
    source.payloads["SPY"][0]["adjClose"] = value
    source.write()
    rejected(source)


@pytest.mark.parametrize(("key", "value"), [("adjHigh", "50"), ("adjLow", "50.75")])
def test_adjusted_ohlc_geometry(source, key, value):
    source.payloads["SPY"][0][key] = value
    source.write()
    rejected(source)


@pytest.mark.parametrize("key", ["symbol", "ticker"])
def test_explicit_wrong_symbol(source, key):
    source.payloads["SPY"][0][key] = "QQQ"
    source.write()
    rejected(source)


def test_duplicate_json_field(source):
    raw = json.dumps(source.payloads["SPY"]).replace(
        '"adjClose": "50.5"', '"adjClose": "50.5", "adjClose": "50.75"', 1
    ).encode()
    source.write(content=raw)
    rejected(source)


@pytest.mark.parametrize("change", ["price", "symbol", "date", "scope"])
def test_verified_canonical_mismatch(source, change):
    rows = source.canonical["SPY"]
    if change == "scope":
        del source.canonical["IWM"]
    else:
        values = {
            "price": {"close": Decimal("100.5")},
            "symbol": {"symbol": "QQQ"},
            "date": {"session_date": date(2024, 1, 4)},
        }
        source.canonical["SPY"] = (replace(rows[0], **values[change]), rows[1])
    rejected(source)


def test_snapshot_must_have_exact_external_identity(source):
    with pytest.raises(ValueError):
        adjusted.load_verified_adjusted_etf_snapshot(
            source.root, market_data_root=source.market, repo_root=source.market
        )
    source.root = source.root.rename(source.root.with_name("snapshot=other"))
    rejected(source)


@pytest.mark.parametrize("filename", ["manifest.json", "ohlcv_1d.csv.gz", "raw/SPY.json"])
def test_hardlinked_source_rejected_and_link_always_removed(source, filename):
    path = source.root / filename
    alias = source.root / "test-alias"
    try:
        os.link(path, alias)
        rejected(source)
    finally:
        alias.unlink(missing_ok=True)
    assert path.stat().st_nlink == 1


@pytest.mark.parametrize("filename", ["raw/SPY.json", "raw"])
def test_symlink_file_or_parent_rejected_and_link_always_removed(source, filename):
    path = source.root / filename
    backing = path.with_name(path.name + "-backing")
    directory = path.is_dir()
    path.rename(backing)
    try:
        try:
            path.symlink_to(backing, target_is_directory=directory)
        except OSError:
            pytest.skip("host cannot create test symlinks")
        rejected(source)
    finally:
        if path.is_symlink():
            path.unlink()
        backing.rename(path)


@pytest.mark.parametrize("filename", ["raw/SPY.json", "raw"])
@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_portable_link_or_reparse_attribute_rejected(source, monkeypatch, filename, kind):
    original = Path.lstat
    target = source.root / filename

    def lstat(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path != target:
            return info
        return SimpleNamespace(
            st_mode=stat.S_IFLNK if kind == "symlink" else info.st_mode,
            st_nlink=info.st_nlink,
            st_file_attributes=1024 if kind == "reparse" else 0,
        )

    monkeypatch.setattr(Path, "lstat", lstat)
    rejected(source)
