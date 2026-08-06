from __future__ import annotations

import ast
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data.cboe_d1_volatility_availability import (
    CboeD1VolatilityAvailabilityError,
    validate_cboe_d1_volatility_availability_receipt,
    write_cboe_d1_volatility_availability_observation,
)

_SOURCE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
_PAYLOAD_LF = "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,20.0,21.0,19.0,20.5\n"
_PAYLOAD_CRLF = "DATE,OPEN,HIGH,LOW,CLOSE\r\n2026-08-06,20.0,21.0,19.0,20.5\r\n"


def test_canonical_matching_row_hash_ignores_csv_line_endings(tmp_path: Path) -> None:
    first = _write(tmp_path, csv_payload=_PAYLOAD_LF)
    second = _write(tmp_path, csv_payload=_PAYLOAD_CRLF)

    first_document = _document(first.receipt_path)
    second_document = _document(second.receipt_path)

    assert first_document["normalized_row_sha256"] == second_document["normalized_row_sha256"]
    assert first.receipt_path == second.receipt_path
    assert first_document["session_close_utc"] == "2026-08-06T16:15:00Z"
    assert first_document["next_market_open_utc"] == "2026-08-07T09:15:00Z"


def test_changed_matching_row_changes_only_its_scoped_hash(tmp_path: Path) -> None:
    first = _write(tmp_path, csv_payload=_PAYLOAD_LF)
    changed = _write(
        tmp_path,
        csv_payload="DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,20.0,21.0,19.0,20.6\n",
    )

    assert _document(first.receipt_path)["normalized_row_sha256"] != _document(
        changed.receipt_path
    )["normalized_row_sha256"]


def test_semantically_equal_numeric_cells_have_one_canonical_row_hash(tmp_path: Path) -> None:
    first = _write(tmp_path, csv_payload=_PAYLOAD_LF)
    formatted = _write(
        tmp_path,
        csv_payload="DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,20.000,21.00,19.0,20.5000\n",
    )

    assert first.receipt_path == formatted.receipt_path


@pytest.mark.parametrize(
    "csv_payload",
    (
        "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-05,20.0,21.0,19.0,20.5\n",
        "DATE,OPEN,HIGH,LOW\n2026-08-06,20.0,21.0,19.0\n",
        "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,20.0,21.0,19.0\n",
        "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,not-a-price,21.0,19.0,20.5\n",
    ),
)
def test_missing_or_malformed_matching_row_fails_closed_without_receipt(
    tmp_path: Path,
    csv_payload: str,
) -> None:
    with pytest.raises(CboeD1VolatilityAvailabilityError):
        _write(tmp_path, csv_payload=csv_payload)

    assert not list((tmp_path / "artifacts").rglob("*.json"))


@pytest.mark.parametrize(
    ("source_url", "series_symbol"),
    (
        ("https://example.invalid/VIX_History.csv", "VIX"),
        ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv", "VIX"),
        (_SOURCE_URL, "VVIX"),
    ),
)
def test_non_cboe_or_mismatched_series_scope_fails_closed_without_receipt(
    tmp_path: Path,
    source_url: str,
    series_symbol: str,
) -> None:
    with pytest.raises(CboeD1VolatilityAvailabilityError):
        _write(tmp_path, source_url=source_url, series_symbol=series_symbol)

    assert not list((tmp_path / "artifacts").rglob("*.json"))


@pytest.mark.parametrize("observed_delta", (timedelta(seconds=-1), timedelta(days=1)))
def test_outside_close_relative_bracket_fails_closed_without_receipt(
    tmp_path: Path,
    observed_delta: timedelta,
) -> None:
    close = datetime(2026, 8, 6, 16, 15, tzinfo=UTC)
    with pytest.raises(CboeD1VolatilityAvailabilityError, match="close-relative bracket"):
        _write(tmp_path, observed_at=close + observed_delta)

    assert not list((tmp_path / "artifacts").rglob("*.json"))


def test_receipt_never_contains_raw_csv_prices_or_header_values(tmp_path: Path) -> None:
    receipt = _write(
        tmp_path,
        cache_control="max-age=120",
        etag='"vix-revision-7"',
    )
    content = receipt.receipt_path.read_text(encoding="utf-8")

    for forbidden in (
        _PAYLOAD_LF,
        "20.5",
        "max-age=120",
        '"vix-revision-7"',
        '"OPEN"',
        '"HIGH"',
        '"LOW"',
        '"CLOSE"',
    ):
        assert forbidden not in content
    document = json.loads(content)
    assert document["decision_time_availability"] == "not_observed"
    assert document["provider_finality"] == "not_observed"
    assert document["qualification"].startswith("observation_only")


def test_validator_rejects_unsafe_malformed_and_non_direct_receipts(tmp_path: Path) -> None:
    receipt = _write(tmp_path)
    root = tmp_path / "artifacts"
    repo = tmp_path / "repo"

    malformed = receipt.receipt_path.with_name("malformed.json")
    malformed.write_text("{}\n", encoding="utf-8")
    with pytest.raises(CboeD1VolatilityAvailabilityError, match="not direct"):
        validate_cboe_d1_volatility_availability_receipt(
            receipt_path=malformed,
            artifact_root=root,
            repository_root=repo,
        )
    with pytest.raises(CboeD1VolatilityAvailabilityError, match="receipt path is invalid"):
        validate_cboe_d1_volatility_availability_receipt(
            receipt_path=Path("receipt.json"),
            artifact_root=root,
            repository_root=repo,
        )

    document = _document(receipt.receipt_path)
    document["provider_finality"] = "final"
    receipt.receipt_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CboeD1VolatilityAvailabilityError, match="receipt categories"):
        validate_cboe_d1_volatility_availability_receipt(
            receipt_path=receipt.receipt_path,
            artifact_root=root,
            repository_root=repo,
        )


def test_validator_rechecks_persisted_close_relative_boundaries(tmp_path: Path) -> None:
    receipt = _write(tmp_path)
    document = _document(receipt.receipt_path)
    document["session_close_utc"] = document["next_market_open_utc"]
    receipt.receipt_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CboeD1VolatilityAvailabilityError, match="receipt time"):
        validate_cboe_d1_volatility_availability_receipt(
            receipt_path=receipt.receipt_path,
            artifact_root=tmp_path / "artifacts",
            repository_root=tmp_path / "repo",
        )


def test_symlinked_receipt_parent_is_rejected_before_any_write(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = artifact_root / "cboe-d1-volatility-availability-observations"
    try:
        os.symlink(outside, linked_parent, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")

    with pytest.raises(CboeD1VolatilityAvailabilityError, match="receipt path is not direct"):
        _write(tmp_path)

    assert not list(outside.rglob("*.json"))


def test_module_has_no_kis_broker_research_or_execution_import_surface() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "src"
        / "thericher_v2"
        / "data"
        / "cboe_d1_volatility_availability.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not [
        name
        for name in imports
        if any(token in name.lower() for token in ("kis", "broker", "research", "execution"))
    ]


def _write(
    tmp_path: Path,
    *,
    csv_payload: str = _PAYLOAD_LF,
    observed_at: datetime | None = None,
    cache_control: str | None = None,
    etag: str | None = None,
    source_url: str = _SOURCE_URL,
    series_symbol: str = "VIX",
):
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(exist_ok=True)
    (repo_root / ".git").mkdir(exist_ok=True)
    close = datetime(2026, 8, 6, 16, 15, tzinfo=UTC)
    return write_cboe_d1_volatility_availability_observation(
        artifact_root=artifact_root,
        repository_root=repo_root,
        csv_payload=csv_payload,
        session_label=date(2026, 8, 6),
        observed_at=observed_at or close + timedelta(minutes=5),
        session_close=close,
        next_market_open=close + timedelta(hours=17),
        source_url=source_url,
        series_symbol=series_symbol,
        cache_control=cache_control,
        etag=etag,
    )


def _document(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
