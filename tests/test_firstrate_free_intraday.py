from __future__ import annotations

import csv
import hashlib
import io
import os
import socket
import stat
import zipfile
from pathlib import Path

import pytest

import thericher_v2.data.firstrate_free_intraday as firstrate
from thericher_v2.contracts import Timeframe
from thericher_v2.data.local import CSV_FIELDS, LocalCsvBarProvider
from thericher_v2.data.provider import BarQuery

_SPY_ENTRY = "SPY_1min_firstratedata.csv"
_QQQ_ENTRY = "QQQ_1min_firstratedata.csv"


@pytest.mark.parametrize(
    ("symbol", "entry_name"),
    [("SPY", _SPY_ENTRY), ("QQQ", _QQQ_ENTRY)],
)
def test_normalizes_sparse_rows_with_dst_conversion_and_no_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
    entry_name: str,
) -> None:
    archive_path, expected_hash = _zip_fixture(
        tmp_path,
        entry_name,
        "\ufeff"
        + _source_csv(
            ("2024-03-08 15:59:00", "100", "101", "99", "100.5", "10"),
            ("2024-03-11 09:30:00", "101", "102", "100", "101.5", "11"),
            ("2024-03-11 09:32:00", "102", "103", "101", "102.5", "12"),
        ),
    )
    output_path = tmp_path / "canonical" / f"{symbol}.csv"

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FirstRate normalizer must not access the network")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    result = firstrate.normalize_firstrate_free_intraday_zip(
        archive_path,
        expected_archive_sha256=expected_hash,
        symbol=symbol.lower(),
        output_csv_path=output_path,
    )

    header, records = _canonical_records(output_path)
    assert header == CSV_FIELDS
    assert [record["start_ts"] for record in records] == [
        "2024-03-08T20:59:00+00:00",
        "2024-03-11T13:30:00+00:00",
        "2024-03-11T13:32:00+00:00",
    ]
    assert [record["complete"] for record in records] == ["true", "true", "true"]
    assert result.symbol == symbol
    assert result.market == "US"
    assert result.source_entry_name == entry_name
    assert result.bar_count == 3
    assert result.input_sha256 == expected_hash
    assert result.output_sha256 == _sha256(output_path.read_bytes())
    assert result.decoded_timestamp_set_sha256 == result.emitted_timestamp_set_sha256

    provider_bars = LocalCsvBarProvider(output_path).get_bars(
        BarQuery(symbol=symbol, market="US", timeframe=Timeframe.M1)
    )
    assert [bar.start_ts.isoformat() for bar in provider_bars] == [
        "2024-03-08T20:59:00+00:00",
        "2024-03-11T13:30:00+00:00",
        "2024-03-11T13:32:00+00:00",
    ]
    assert all(bar.start_ts.isoformat() != "2024-03-11T13:31:00+00:00" for bar in provider_bars)
    assert [str(bar.open) for bar in provider_bars] == ["100", "101", "102"]
    assert [str(bar.high) for bar in provider_bars] == ["101", "102", "103"]
    assert [str(bar.low) for bar in provider_bars] == ["99", "100", "101"]
    assert [str(bar.close) for bar in provider_bars] == ["100.5", "101.5", "102.5"]
    assert [str(bar.volume) for bar in provider_bars] == ["10", "11", "12"]
    assert all(bar.complete for bar in provider_bars)


def test_rejects_duplicate_or_nonmonotonic_source_rows_without_output(
    tmp_path: Path,
) -> None:
    duplicate_path, duplicate_hash = _zip_fixture(
        tmp_path / "duplicate",
        _SPY_ENTRY,
        _source_csv(
            ("2024-03-11 09:30:00", "100", "101", "99", "100.5", "10"),
            ("2024-03-11 09:30:00", "101", "102", "100", "101.5", "11"),
        ),
    )
    duplicate_output = tmp_path / "duplicate.csv"
    with pytest.raises(ValueError, match="duplicate timestamps"):
        firstrate.normalize_firstrate_free_intraday_zip(
            duplicate_path,
            expected_archive_sha256=duplicate_hash,
            symbol="SPY",
            output_csv_path=duplicate_output,
        )
    assert not duplicate_output.exists()

    unordered_path, unordered_hash = _zip_fixture(
        tmp_path / "unordered",
        _SPY_ENTRY,
        _source_csv(
            ("2024-03-11 09:31:00", "100", "101", "99", "100.5", "10"),
            ("2024-03-11 09:30:00", "101", "102", "100", "101.5", "11"),
        ),
    )
    with pytest.raises(ValueError, match="not strictly increasing"):
        firstrate.normalize_firstrate_free_intraday_zip(
            unordered_path,
            expected_archive_sha256=unordered_hash,
            symbol="SPY",
            output_csv_path=tmp_path / "unordered.csv",
        )


@pytest.mark.parametrize(
    ("entry_name", "source", "expected_error"),
    [
        (
            _SPY_ENTRY,
            "timestamp,open,high,low,close\n2024-03-11 09:30:00,1,2,0.5,1.5\n",
            "header",
        ),
        (
            _SPY_ENTRY,
            "open,timestamp,high,low,close,volume\n1,2024-03-11 09:30:00,2,0.5,1.5,1\n",
            "header",
        ),
        (
            f"../{_SPY_ENTRY}",
            "timestamp,open,high,low,close,volume\n"
            "2024-03-11 09:30:00,1,2,0.5,1.5,1\n",
            "unsafe entry",
        ),
        (
            f"{_SPY_ENTRY}/",
            "timestamp,open,high,low,close,volume\n"
            "2024-03-11 09:30:00,1,2,0.5,1.5,1\n",
            "unsafe entry",
        ),
        (
            _QQQ_ENTRY,
            "timestamp,open,high,low,close,volume\n"
            "2024-03-11 09:30:00,1,2,0.5,1.5,1\n",
            "does not match requested symbol",
        ),
    ],
)
def test_rejects_hash_header_or_archive_identity_failures(
    tmp_path: Path,
    entry_name: str,
    source: str,
    expected_error: str,
) -> None:
    archive_path, expected_hash = _zip_fixture(tmp_path, entry_name, source)
    output_path = tmp_path / "output.csv"

    with pytest.raises(ValueError, match=expected_error):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=output_path,
        )
    assert not output_path.exists()

    with pytest.raises(ValueError, match="archive hash mismatch"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256="sha256:" + "0" * 64,
            symbol="SPY",
            output_csv_path=output_path,
        )
    assert not output_path.exists()


def test_rejects_extra_archive_member_and_invalid_ohlcv_or_dst_timestamp(
    tmp_path: Path,
) -> None:
    archive_path, expected_hash = _zip_fixture(
        tmp_path / "extra",
        _SPY_ENTRY,
        _source_csv(("2024-03-11 09:30:00", "1", "2", "0.5", "1.5", "1")),
        extra_entries={"notes.txt": "not a market row"},
    )
    with pytest.raises(ValueError, match="exactly one CSV entry"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=tmp_path / "extra.csv",
        )

    invalid_path, invalid_hash = _zip_fixture(
        tmp_path / "invalid",
        _SPY_ENTRY,
        _source_csv(
            ("2024-03-11 09:30:00", "1", "2", "0.5", "1.5", "1"),
            ("2024-03-11 09:31:00", "0", "2", "0.5", "1.5", "1"),
        ),
    )
    invalid_output = tmp_path / "invalid.csv"
    with pytest.raises(ValueError, match="invalid OHLCV"):
        firstrate.normalize_firstrate_free_intraday_zip(
            invalid_path,
            expected_archive_sha256=invalid_hash,
            symbol="SPY",
            output_csv_path=invalid_output,
        )
    assert not invalid_output.exists()

    dst_path, dst_hash = _zip_fixture(
        tmp_path / "dst",
        _SPY_ENTRY,
        _source_csv(("2024-03-10 02:30:00", "1", "2", "0.5", "1.5", "1")),
    )
    with pytest.raises(ValueError, match="ambiguous or nonexistent"):
        firstrate.normalize_firstrate_free_intraday_zip(
            dst_path,
            expected_archive_sha256=dst_hash,
            symbol="SPY",
            output_csv_path=tmp_path / "dst.csv",
        )


def test_rejects_declared_zip_expansion_without_publishing_output(tmp_path: Path) -> None:
    source = _source_csv(
        ("2024-03-11 09:30:00", "1", "2", "0.5", "1.5", "1" + "0" * 20_000)
    )
    archive_path, expected_hash = _zip_fixture(tmp_path, _SPY_ENTRY, source)
    output_path = tmp_path / "expansion.csv"

    with pytest.raises(ValueError, match="declared expansion limit"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=output_path,
        )
    assert not output_path.exists()


def test_rejects_source_archive_reparse_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path, expected_hash = _zip_fixture(
        tmp_path,
        _SPY_ENTRY,
        _source_csv(("2024-03-11 09:30:00", "1", "2", "0.5", "1.5", "1")),
    )
    _mark_paths_as_reparse(monkeypatch, archive_path)
    output_path = tmp_path / "output.csv"

    with pytest.raises(ValueError, match="reparse-point"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=output_path,
        )
    assert not output_path.exists()


def test_rejects_output_parent_or_target_reparse_path_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path, expected_hash = _zip_fixture(
        tmp_path,
        _SPY_ENTRY,
        _source_csv(("2024-03-11 09:30:00", "1", "2", "0.5", "1.5", "1")),
    )
    output_parent = tmp_path / "output-parent"
    output_parent.mkdir()
    preserved_target = tmp_path / "preserved.csv"
    preserved_target.write_text("preserve", encoding="utf-8")
    _mark_paths_as_reparse(monkeypatch, output_parent, preserved_target)

    with pytest.raises(ValueError, match="reparse-point"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=output_parent / "output.csv",
        )
    assert not (output_parent / "output.csv").exists()

    with pytest.raises(ValueError, match="reparse-point"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=preserved_target,
        )
    assert preserved_target.read_text(encoding="utf-8") == "preserve"


def _zip_fixture(
    tmp_path: Path,
    entry_name: str,
    source_csv: str,
    *,
    extra_entries: dict[str, str] | None = None,
) -> tuple[Path, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry_name, source_csv)
        for extra_name, extra_contents in (extra_entries or {}).items():
            archive.writestr(extra_name, extra_contents)
    archive_path = tmp_path / "fixture.zip"
    archive_bytes = buffer.getvalue()
    archive_path.write_bytes(archive_bytes)
    return archive_path, _sha256(archive_bytes)


def _source_csv(*rows: tuple[str, str, str, str, str, str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("timestamp", "open", "high", "low", "close", "volume"))
    writer.writerows(rows)
    return buffer.getvalue()


def _canonical_records(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), [dict(row) for row in reader]


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _mark_paths_as_reparse(
    monkeypatch: pytest.MonkeyPatch, *paths: Path
) -> None:
    original_lstat = firstrate._lstat_or_none
    flagged_paths = {path.absolute() for path in paths}

    def fake_lstat(path: Path, field_name: str) -> os.stat_result | None:
        if path.absolute() in flagged_paths:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        return original_lstat(path, field_name)

    monkeypatch.setattr(firstrate, "_lstat_or_none", fake_lstat)
