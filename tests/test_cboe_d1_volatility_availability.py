from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import socket
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data.cboe_d1_volatility_availability import (
    CboeD1VolatilityAvailabilityError,
    read_cboe_d1_volatility_availability_outcome,
    validate_cboe_d1_volatility_availability_receipt,
    write_cboe_d1_volatility_availability_observation,
)

_SOURCE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
_VXN_SOURCE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv"
_PAYLOAD_LF = "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,20.0,21.0,19.0,20.5\n"
_PAYLOAD_CRLF = "DATE,OPEN,HIGH,LOW,CLOSE\r\n2026-08-06,20.0,21.0,19.0,20.5\r\n"


def _cli_module():
    script_path = (
        Path(__file__).parents[1]
        / "scripts"
        / "observe_cboe_d1_volatility_availability.py"
    )
    specification = importlib.util.spec_from_file_location("cboe_observation_cli", script_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _outcome_cli_module():
    script_path = (
        Path(__file__).parents[1]
        / "scripts"
        / "read_cboe_d1_volatility_availability_outcome.py"
    )
    specification = importlib.util.spec_from_file_location("cboe_outcome_reader_cli", script_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


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


def test_receipt_hashes_response_date_and_last_modified_without_retaining_them(
    tmp_path: Path,
) -> None:
    receipt = _write(
        tmp_path,
        response_date="Thu, 06 Aug 2026 20:30:00 GMT",
        last_modified="Thu, 06 Aug 2026 20:15:00 GMT",
    )
    document = _document(receipt.receipt_path)
    metadata = document["cache_metadata"]
    assert metadata["response_date_sha256"] == "sha256:" + hashlib.sha256(
        b"Thu, 06 Aug 2026 20:30:00 GMT"
    ).hexdigest()
    assert metadata["last_modified_sha256"] == "sha256:" + hashlib.sha256(
        b"Thu, 06 Aug 2026 20:15:00 GMT"
    ).hexdigest()
    content = receipt.receipt_path.read_text(encoding="utf-8")
    assert "Thu, 06 Aug 2026" not in content


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


def test_validator_rejects_a_rehashed_receipt_with_an_unmapped_source_url(tmp_path: Path) -> None:
    receipt = _write(tmp_path)
    root = tmp_path / "artifacts"
    document = _document(receipt.receipt_path)
    document["source_url_sha256"] = "sha256:" + hashlib.sha256(
        b"https://example.invalid/VIX_History.csv"
    ).hexdigest()
    body = {key: value for key, value in document.items() if key != "observation_sha256"}
    document["observation_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    forged = root / "cboe-d1-volatility-availability-observations" / document[
        "observation_sha256"
    ][7:] / "receipt.json"
    forged.parent.mkdir(parents=True)
    forged.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CboeD1VolatilityAvailabilityError, match="source scope"):
        validate_cboe_d1_volatility_availability_receipt(
            receipt_path=forged,
            artifact_root=root,
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


def test_outcome_reader_returns_unavailable_without_a_receipt_directory(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    outcome = read_cboe_d1_volatility_availability_outcome(
        series_symbol="VIX",
        session_label=date(2026, 8, 6),
        session_close=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert outcome.status == "unavailable"
    assert outcome.series_symbol == "VIX"
    assert outcome.session_label == "2026-08-06"
    assert outcome.receipt_sha256 is None
    assert outcome.observed_at_utc is None
    assert outcome.receipt_path is None


def test_outcome_reader_reattaches_one_exact_receipt_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _write(tmp_path)

    def forbid_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("outcome reader must stay offline")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    outcome = _read_outcome(tmp_path)

    assert outcome.status == "observed"
    assert outcome.series_symbol == "VIX"
    assert outcome.session_label == "2026-08-06"
    assert outcome.receipt_sha256 == receipt.observation_sha256
    assert outcome.observed_at_utc == "2026-08-06T16:20:00Z"
    assert outcome.receipt_path == receipt.receipt_path


def test_outcome_reader_ignores_a_different_series_receipt(tmp_path: Path) -> None:
    expected = _write(tmp_path)
    _write(tmp_path, source_url=_VXN_SOURCE_URL, series_symbol="VXN")

    outcome = _read_outcome(tmp_path)

    assert outcome.status == "observed"
    assert outcome.receipt_sha256 == expected.observation_sha256


def test_outcome_reader_disqualifies_multiple_exact_receipts(tmp_path: Path) -> None:
    _write(tmp_path)
    _write(tmp_path, observed_at=datetime(2026, 8, 6, 16, 25, tzinfo=UTC))

    outcome = _read_outcome(tmp_path)

    assert outcome.status == "disqualified"
    assert outcome.receipt_sha256 is None
    assert outcome.observed_at_utc is None
    assert outcome.receipt_path is None


def test_outcome_reader_disqualifies_another_boundary_for_the_exact_series_session(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    wrong_close = datetime(2026, 8, 6, 16, 0, tzinfo=UTC)
    _write(
        tmp_path,
        observed_at=wrong_close + timedelta(minutes=5),
        session_close=wrong_close,
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
    )

    outcome = _read_outcome(tmp_path)

    assert outcome.status == "disqualified"
    assert outcome.receipt_sha256 is None


def test_outcome_reader_cli_emits_only_source_safe_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _write(tmp_path)
    module = _outcome_cli_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "read_cboe_d1_volatility_availability_outcome.py",
            "--series",
            "VIX",
            "--session-label",
            "2026-08-06",
            "--session-close",
            "2026-08-06T16:15:00Z",
            "--next-market-open",
            "2026-08-07T09:15:00Z",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--repository-root",
            str(tmp_path / "repo"),
        ],
    )

    module.main()

    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result == {
        "observed_at_utc": "2026-08-06T16:20:00Z",
        "receipt_path": str(receipt.receipt_path),
        "receipt_sha256": receipt.observation_sha256,
        "series_symbol": "VIX",
        "session_label": "2026-08-06",
        "status": "observed",
    }
    assert output.err == ""
    for raw_value in (_PAYLOAD_LF, "20.5", "21.0", "19.0"):
        assert raw_value not in output.out


def test_outcome_reader_cli_has_no_kis_broker_research_or_execution_import_surface() -> None:
    script_path = (
        Path(__file__).parents[1]
        / "scripts"
        / "read_cboe_d1_volatility_availability_outcome.py"
    )
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
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


def test_cli_observes_one_vix_response_with_no_cache_and_source_safe_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _cli_module()
    requested: list[tuple[str, dict[str, str]]] = []

    def fetcher(url: str, headers: dict[str, str]):
        requested.append((url, dict(headers)))
        return module.CboeHttpResponse(
            status_code=200,
            body=_PAYLOAD_LF,
            headers={
                "Age": "12",
                "Cache-Control": "max-age=120",
                "ETag": '"revision-1"',
                "Date": "Thu, 06 Aug 2026 20:30:00 GMT",
                "Last-Modified": "Thu, 06 Aug 2026 20:15:00 GMT",
            },
        )

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "observe_cboe_d1_volatility_availability.py",
            "--series",
            "VIX",
            "--session-label",
            "2026-08-06",
            "--observed-at",
            "2026-08-06T16:20:00Z",
            "--session-close",
            "2026-08-06T16:15:00Z",
            "--next-market-open",
            "2026-08-07T09:15:00Z",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--repository-root",
            str(repo_root),
        ],
    )

    module.main(fetcher=fetcher)

    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == "observed"
    assert result["series"] == "VIX"
    assert result["receipt_sha256"].startswith("sha256:")
    assert output.err == ""
    assert requested == [
        (_SOURCE_URL, {"Cache-Control": "no-cache", "Pragma": "no-cache"})
    ]
    for raw_value in (_PAYLOAD_LF, "20.5", "max-age=120", '"revision-1"', "Thu, 06 Aug 2026"):
        assert raw_value not in output.out


def test_cli_observed_now_records_the_runtime_utc_instant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _cli_module()
    observed_at = datetime(2026, 8, 6, 16, 20, tzinfo=UTC)
    monkeypatch.setattr(module, "_utc_now", lambda: observed_at)

    def fetcher(url: str, headers: dict[str, str]):
        assert url == _SOURCE_URL
        assert headers == {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        return module.CboeHttpResponse(status_code=200, body=_PAYLOAD_LF, headers={})

    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "observe_cboe_d1_volatility_availability.py",
            "--series",
            "VIX",
            "--session-label",
            "2026-08-06",
            "--observed-now",
            "--session-close",
            "2026-08-06T16:15:00Z",
            "--next-market-open",
            "2026-08-07T09:15:00Z",
            "--artifact-root",
            str(artifact_root),
            "--repository-root",
            str(repo_root),
        ],
    )

    module.main(fetcher=fetcher)

    result = json.loads(capsys.readouterr().out)
    receipt_directory = artifact_root / "cboe-d1-volatility-availability-observations"
    receipt_path = next(receipt_directory.rglob("receipt.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result["status"] == "observed"
    assert receipt["observed_at_utc"] == "2026-08-06T16:20:00Z"


@pytest.mark.parametrize(
    "response",
    (
        (503, None),
        (200, "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-05,20.0,21.0,19.0,20.5\n"),
        (200, "DATE,OPEN,HIGH,LOW,SETTLE\n2026-08-06,20.0,21.0,19.0,20.5\n"),
        (200, "DATE,OPEN,HIGH,LOW,CLOSE\n2026-08-06,20.0,broken,19.0,20.5\n"),
    ),
)
def test_cli_collection_failures_are_one_symbol_unavailable_without_receipt(
    tmp_path: Path, response: tuple[int, str | None]
) -> None:
    module = _cli_module()

    def fetcher(url: str, headers: dict[str, str]):
        assert url == _SOURCE_URL
        assert headers == {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        return module.CboeHttpResponse(status_code=response[0], body=response[1], headers={})

    result = module.observe_once(
        series="VIX",
        session_label=date(2026, 8, 6),
        observed_at=datetime(2026, 8, 6, 16, 20, tzinfo=UTC),
        session_close=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        fetcher=fetcher,
    )

    assert result == {"receipt_sha256": None, "series": "VIX", "status": "unavailable"}
    assert not list((tmp_path / "artifacts").rglob("*.json"))


def test_cli_rejects_an_outside_bracket_before_network_access(tmp_path: Path) -> None:
    module = _cli_module()

    result = module.observe_once(
        series="VIX",
        session_label=date(2026, 8, 6),
        observed_at=datetime(2026, 8, 6, 16, 14, tzinfo=UTC),
        session_close=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        fetcher=lambda *_: pytest.fail("fetcher must not run outside the bracket"),
    )

    assert result == {"receipt_sha256": None, "series": None, "status": "unavailable"}
    assert not list((tmp_path / "artifacts").rglob("*.json"))


def test_cli_rejects_an_invalid_artifact_root_before_network_access(tmp_path: Path) -> None:
    module = _cli_module()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    result = module.observe_once(
        series="VIX",
        session_label=date(2026, 8, 6),
        observed_at=datetime(2026, 8, 6, 16, 20, tzinfo=UTC),
        session_close=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        artifact_root=repository_root / "artifacts",
        repository_root=repository_root,
        fetcher=lambda *_: pytest.fail("fetcher must not run for an unsafe artifact root"),
    )

    assert result == {"receipt_sha256": None, "series": None, "status": "unavailable"}
    assert not list(repository_root.rglob("*.json"))


def test_cli_rejects_an_invalid_direct_series_before_network_access(tmp_path: Path) -> None:
    module = _cli_module()

    result = module.observe_once(
        series="NOT_VIX",
        session_label=date(2026, 8, 6),
        observed_at=datetime(2026, 8, 6, 16, 20, tzinfo=UTC),
        session_close=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        fetcher=lambda *_: pytest.fail("fetcher must not run for an invalid series"),
    )

    assert result == {"receipt_sha256": None, "series": None, "status": "unavailable"}


def test_cli_requires_exactly_one_explicit_supported_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _cli_module()
    common = [
        "--session-label", "2026-08-06", "--observed-at", "2026-08-06T16:20:00Z",
        "--session-close", "2026-08-06T16:15:00Z", "--next-market-open", "2026-08-07T09:15:00Z",
        "--artifact-root", str(tmp_path / "artifacts"), "--repository-root", str(tmp_path / "repo"),
    ]
    monkeypatch.setattr(sys, "argv", ["observer", *common])
    with pytest.raises(SystemExit):
        module.main(fetcher=lambda *_: pytest.fail("fetcher must not run"))
    monkeypatch.setattr(sys, "argv", ["observer", "--series", "VIX", "--series", "VXN", *common])
    with pytest.raises(SystemExit):
        module.main(fetcher=lambda *_: pytest.fail("fetcher must not run"))


def test_cli_has_no_kis_broker_research_or_execution_import_surface() -> None:
    script_path = (
        Path(__file__).parents[1]
        / "scripts"
        / "observe_cboe_d1_volatility_availability.py"
    )
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
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
    response_date: str | None = None,
    last_modified: str | None = None,
    source_url: str = _SOURCE_URL,
    series_symbol: str = "VIX",
    session_close: datetime | None = None,
    next_market_open: datetime | None = None,
):
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(exist_ok=True)
    (repo_root / ".git").mkdir(exist_ok=True)
    close = session_close or datetime(2026, 8, 6, 16, 15, tzinfo=UTC)
    return write_cboe_d1_volatility_availability_observation(
        artifact_root=artifact_root,
        repository_root=repo_root,
        csv_payload=csv_payload,
        session_label=date(2026, 8, 6),
        observed_at=observed_at or close + timedelta(minutes=5),
        session_close=close,
        next_market_open=next_market_open or close + timedelta(hours=17),
        source_url=source_url,
        series_symbol=series_symbol,
        cache_control=cache_control,
        etag=etag,
        response_date=response_date,
        last_modified=last_modified,
    )


def _read_outcome(tmp_path: Path):
    return read_cboe_d1_volatility_availability_outcome(
        series_symbol="VIX",
        session_label=date(2026, 8, 6),
        session_close=datetime(2026, 8, 6, 16, 15, tzinfo=UTC),
        next_market_open=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
    )


def _document(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
