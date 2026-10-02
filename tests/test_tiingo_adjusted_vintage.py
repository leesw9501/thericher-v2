from __future__ import annotations

import json
import os
import socket
import stat
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.data.tiingo_adjusted_vintage as vintage
import thericher_v2.data.tiingo_etf_daily as daily

_SYMBOLS = ("SPY", "QQQ", "IWM")


@pytest.fixture
def source(tmp_path: Path, monkeypatch):
    def deny(*_args, **_kwargs):
        raise AssertionError("network, credentials and acquisition forbidden")

    monkeypatch.setattr(daily, "read_tiingo_api_token", deny)
    monkeypatch.setattr(daily, "build_opener", deny)
    monkeypatch.setattr(daily, "acquire_tiingo_etf_d1_snapshot", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    market = tmp_path / "market"
    repo = tmp_path / "repo"
    repo.mkdir()
    root = (
        market
        / "us_equities"
        / "tiingo_etf_daily"
        / "canonical"
        / "snapshot=20261003T010203Z-tiingo-etf-d1-r1"
    )
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True)
    payloads, rows, hashes = {}, {}, {}
    for symbol in _SYMBOLS:
        payloads[symbol] = [
            {
                "date": f"{session}T00:00:00.000Z",
                "open": "100",
                "high": "102",
                "low": "99",
                "close": "101",
                "volume": "1000",
                "divCash": "1",
                "splitFactor": "2",
                "adjOpen": 50.125,
                "adjHigh": "51",
                "adjLow": "49.5",
                "adjClose": "50.5",
            }
            for session in ("2025-07-01", "2026-09-30")
        ]
        raw = json.dumps(payloads[symbol]).encode()
        (raw_dir / f"{symbol}.json").write_bytes(raw)
        hashes[symbol] = daily._sha256(raw)
        rows[symbol] = daily.normalize_tiingo_etf_d1_response(symbol=symbol, raw_response=raw)
    canonical = daily._gzip_bytes(daily._canonical_csv_bytes(rows))
    (root / "ohlcv_1d.csv.gz").write_bytes(canonical)
    manifest = daily._manifest(
        target=root,
        requested_start=date(2025, 7, 1),
        requested_end=date(2026, 9, 30),
        retrieved_at=datetime(2026, 10, 3, 1, 2, 3, tzinfo=UTC),
        canonical_hash=daily._sha256(canonical),
        canonical_size=len(canonical),
        raw_hashes=hashes,
        rows_by_symbol=rows,
        raw_dir=raw_dir,
        free_percent=80,
    )
    pins = {
        "dataset_id": manifest["dataset_id"],
        "expected_dataset_hash": manifest["dataset_hash"],
        "expected_manifest_hash": "",
        "expected_raw_hashes": dict(hashes),
    }

    def write_manifest():
        content = json.dumps(manifest, sort_keys=True).encode()
        (root / "manifest.json").write_bytes(content)
        pins["expected_manifest_hash"] = daily._sha256(content)

    def write_raw(*, symbol="SPY", content=None, repin=True):
        raw = json.dumps(payloads[symbol]).encode() if content is None else content
        (root / "raw" / f"{symbol}.json").write_bytes(raw)
        if repin:
            pins["expected_raw_hashes"][symbol] = daily._sha256(raw)
            entry = next(
                item for item in manifest["files"]["raw_sources"] if item["symbol"] == symbol
            )
            entry.update(sha256=daily._sha256(raw), size_bytes=len(raw))
            write_manifest()

    write_manifest()
    return SimpleNamespace(
        root=root,
        market=market,
        repo=repo,
        pins=pins,
        payloads=payloads,
        manifest=manifest,
        write_raw=write_raw,
        write_manifest=write_manifest,
    )


def load(source, **overrides):
    arguments = {**source.pins, "market_data_root": source.market, "repo_root": source.repo}
    arguments.update(overrides)
    return vintage.load_verified_adjusted_etf_vintage(source.root, **arguments)


def reject(source, **overrides):
    with pytest.raises(ValueError, match="^adjusted ETF vintage verification failed$"):
        load(source, **overrides)


def test_verified_single_vintage_is_immutable_silent_and_read_only(source, monkeypatch, capsys):
    files = [source.root / "manifest.json", source.root / "ohlcv_1d.csv.gz"]
    files.extend(source.root / "raw" / f"{symbol}.json" for symbol in _SYMBOLS)
    before = {path: path.read_bytes() for path in files}
    upstream = vintage.load_verified_tiingo_etf_d1_snapshot
    reader = vintage._read_snapshot_file
    calls = []

    def verified(directory, **kwargs):
        assert directory == source.root
        assert kwargs == {
            key: value
            for key, value in {
                **source.pins,
                "market_data_root": source.market,
                "repo_root": source.repo,
            }.items()
            if key != "expected_raw_hashes"
        }
        result = upstream(directory, **kwargs)
        calls.append("verified")
        return result

    def read(*args):
        assert calls == ["verified"]
        return reader(*args)

    monkeypatch.setattr(vintage, "load_verified_tiingo_etf_d1_snapshot", verified)
    monkeypatch.setattr(vintage, "_read_snapshot_file", read)
    result = load(source)
    assert tuple(result) == _SYMBOLS
    assert all(isinstance(result[symbol], tuple) for symbol in _SYMBOLS)
    row = result["SPY"][0]
    assert isinstance(row, vintage.AdjustedEtfRow)
    assert row.adj_open == Decimal("50.125")
    assert row.adj_close == Decimal("50.5")
    assert not hasattr(row, "div_cash") and not hasattr(row, "split_factor")
    assert "50.125" not in repr(result) and "50.5" not in repr(row)
    with pytest.raises(TypeError):
        result["SPY"] = ()
    with pytest.raises(FrozenInstanceError):
        row.adj_close = Decimal("2")
    assert before == {path: path.read_bytes() for path in files}
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("pin", ["dataset_id", "expected_dataset_hash", "expected_manifest_hash"])
def test_wrong_dataset_manifest_or_identity_pin(source, pin):
    value = "wrong-vintage" if pin == "dataset_id" else "sha256:" + "0" * 64
    reject(source, **{pin: value})


@pytest.mark.parametrize("change", ["missing", "extra", "hash", "invalid_hash"])
def test_raw_pin_binding_requires_exact_trio(source, change):
    pins = dict(source.pins["expected_raw_hashes"])
    if change == "missing":
        del pins["IWM"]
    elif change == "extra":
        pins["DIA"] = pins["SPY"]
    else:
        pins["SPY"] = "sha256:" + "0" * 64 if change == "hash" else "private-invalid-pin"
    reject(source, expected_raw_hashes=pins)


def test_tamper_does_not_change_previous_frozen_result(source):
    result = load(source)
    source.payloads["SPY"][0]["adjClose"] = "50.75"
    source.write_raw(repin=False)
    reject(source)
    assert result["SPY"][0].adj_close == Decimal("50.5")


def test_raw_bytes_are_rehashed_after_upstream_verification(source, monkeypatch):
    upstream = vintage.load_verified_tiingo_etf_d1_snapshot

    def changed_after_verify(*args, **kwargs):
        result = upstream(*args, **kwargs)
        source.payloads["SPY"][0]["adjClose"] = "50.75"
        source.write_raw(repin=False)
        return result

    monkeypatch.setattr(vintage, "load_verified_tiingo_etf_d1_snapshot", changed_after_verify)
    reject(source)


@pytest.mark.parametrize("key", ["adjOpen", "adjHigh", "adjLow", "adjClose"])
def test_missing_adjusted_fields(source, key):
    del source.payloads["SPY"][0][key]
    source.write_raw()
    reject(source)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        0,
        -1,
        "NaN",
        "Infinity",
        "-Infinity",
        "bad",
        [],
        {},
        float("nan"),
        float("inf"),
    ],
)
def test_adjusted_numbers_must_be_finite_positive_decimals(source, value):
    source.payloads["SPY"][0]["adjClose"] = value
    source.write_raw()
    reject(source)


@pytest.mark.parametrize(("field", "value"), [("adjHigh", "50"), ("adjLow", "50.75")])
def test_adjusted_geometry(source, field, value):
    source.payloads["SPY"][0][field] = value
    source.write_raw()
    reject(source)


@pytest.mark.parametrize("change", ["duplicate", "reverse", "missing", "extra"])
def test_date_order_duplicates_and_count(source, change):
    rows = source.payloads["SPY"]
    if change == "duplicate":
        rows[1] = dict(rows[0])
    elif change == "reverse":
        rows.reverse()
    elif change == "missing":
        rows.pop()
    else:
        rows.append(dict(rows[-1]))
    source.write_raw()
    reject(source)


@pytest.mark.parametrize(
    "stamp",
    [
        "2025-07-02T00:00:00.000Z",
        "2025-07-01T01:00:00.000Z",
        "2025-07-01T00:00:00.001Z",
        "2025-07-01T00:00:00+00:00",
    ],
)
def test_exact_session_label_and_canonical_alignment(source, stamp):
    source.payloads["SPY"][0]["date"] = stamp
    source.write_raw()
    reject(source)


def test_duplicate_json_field(source):
    raw = (
        json.dumps(source.payloads["SPY"])
        .replace('"adjClose": "50.5"', '"adjClose": "50.5", "adjClose": "50.75"', 1)
        .encode()
    )
    source.write_raw(content=raw)
    reject(source)


@pytest.mark.parametrize("key", ["symbol", "ticker"])
def test_wrong_raw_symbol(source, key):
    source.payloads["SPY"][0][key] = "QQQ"
    source.write_raw()
    reject(source)


def test_extra_manifest_symbol(source):
    source.manifest["symbols"].append("DIA")
    source.write_manifest()
    reject(source)


def test_canonical_mismatch_even_if_upstream_result_is_replaced(source, monkeypatch):
    upstream = vintage.load_verified_tiingo_etf_d1_snapshot

    def mismatched(*args, **kwargs):
        verified = upstream(*args, **kwargs)
        rows = dict(verified.rows_by_symbol)
        rows["SPY"] = (replace(rows["SPY"][0], close=Decimal("100.5")), *rows["SPY"][1:])
        return replace(verified, rows_by_symbol=rows)

    monkeypatch.setattr(vintage, "load_verified_tiingo_etf_d1_snapshot", mismatched)
    reject(source)


@pytest.mark.parametrize("replacement", ["old_name", "other_parent", "repo"])
def test_vintage_path_substitution_and_repository_input(source, replacement):
    if replacement == "repo":
        reject(source, repo_root=source.market)
        return
    target = (
        source.root.with_name("snapshot=20260809T163557Z-tiingo-etf-d1-r1")
        if replacement == "old_name"
        else source.market / "other" / source.root.name
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    source.root = source.root.rename(target)
    reject(source)


@pytest.mark.parametrize("filename", ["manifest.json", "ohlcv_1d.csv.gz", "raw/SPY.json"])
def test_hardlink_rejected_with_own_link_removed_in_finally(source, filename):
    alias = source.market / "test-hardlink"
    try:
        os.link(source.root / filename, alias)
        reject(source)
    finally:
        alias.unlink(missing_ok=True)
    assert (source.root / filename).stat().st_nlink == 1


@pytest.mark.parametrize("filename", ["raw", "raw/SPY.json"])
def test_reparse_file_or_parent_rejected_portably(source, monkeypatch, filename):
    target = source.root / filename
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == target:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_nlink=result.st_nlink,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            )
        return result

    monkeypatch.setattr(Path, "lstat", reparse)
    reject(source)


def test_native_symlink_rejected_and_own_link_removed_in_finally(source):
    path = source.root / "raw" / "SPY.json"
    backing = path.with_name("SPY-backing.json")
    path.rename(backing)
    try:
        try:
            path.symlink_to(backing)
        except OSError:
            pytest.skip("host cannot create synthetic symlinks")
        reject(source)
    finally:
        path.unlink(missing_ok=True)
        backing.rename(path)
    assert not path.is_symlink()


def test_upstream_private_failure_is_masked_and_silent(source, monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise ValueError("private-value-not-for-output")

    monkeypatch.setattr(vintage, "load_verified_tiingo_etf_d1_snapshot", fail)
    reject(source)
    assert capsys.readouterr() == ("", "")
