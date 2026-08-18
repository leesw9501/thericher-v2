from __future__ import annotations

import csv
import hashlib
import io
import socket
import zipfile
from pathlib import Path

import pytest

import thericher_v2.data.firstrate_free_intraday as firstrate
from thericher_v2.data.local import CSV_FIELDS


def test_normalizes_sparse_rows_with_dst_conversion_and_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path, expected_hash = _zip_fixture(
        tmp_path,
        "SPY.csv",
        "\ufeff"
        + _source_csv(
            ("2024-03-08 15:59:00", "100", "101", "99", "100.5", "10"),
            ("2024-03-11 09:30:00", "101", "102", "100", "101.5", "11"),
            ("2024-03-11 09:32:00", "102", "103", "101", "102.5", "12"),
        ),
    )
    output_path = tmp_path / "canonical" / "SPY.csv"

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FirstRate normalizer must not access the network")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    result = firstrate.normalize_firstrate_free_intraday_zip(
        archive_path,
        expected_archive_sha256=expected_hash,
        symbol="spy",
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
    assert result.symbol == "SPY"
    assert result.market == "US"
    assert result.source_entry_name == "SPY.csv"
    assert result.bar_count == 3
    assert result.input_sha256 == expected_hash
    assert result.output_sha256 == _sha256(output_path.read_bytes())
    assert result.decoded_timestamp_set_sha256 == result.emitted_timestamp_set_sha256


def test_rejects_duplicate_or_nonmonotonic_source_rows_without_output(
    tmp_path: Path,
) -> None:
    duplicate_path, duplicate_hash = _zip_fixture(
        tmp_path / "duplicate",
        "SPY.csv",
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
        "SPY.csv",
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
            "SPY.csv",
            "timestamp,open,high,low,close\n2024-03-11 09:30:00,1,2,0.5,1.5\n",
            "header",
        ),
        (
            "SPY.csv",
            "open,timestamp,high,low,close,volume\n1,2024-03-11 09:30:00,2,0.5,1.5,1\n",
            "header",
        ),
        (
            "../SPY.csv",
            "timestamp,open,high,low,close,volume\n"
            "2024-03-11 09:30:00,1,2,0.5,1.5,1\n",
            "unsafe entry",
        ),
        (
            "SPY.csv/",
            "timestamp,open,high,low,close,volume\n"
            "2024-03-11 09:30:00,1,2,0.5,1.5,1\n",
            "unsafe entry",
        ),
        (
            "QQQ.csv",
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
        "SPY.csv",
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
        "SPY.csv",
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
        "SPY.csv",
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
    archive_path, expected_hash = _zip_fixture(tmp_path, "SPY.csv", source)
    output_path = tmp_path / "expansion.csv"

    with pytest.raises(ValueError, match="declared expansion limit"):
        firstrate.normalize_firstrate_free_intraday_zip(
            archive_path,
            expected_archive_sha256=expected_hash,
            symbol="SPY",
            output_csv_path=output_path,
        )
    assert not output_path.exists()


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
