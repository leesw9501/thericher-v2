from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import thericher_v2.data.tiingo_eod as tiingo_eod
from thericher_v2.data.corporate_actions import (
    CAMPAIGN_COVERAGE_END,
    CAMPAIGN_COVERAGE_START,
    CORPORATE_ACTION_SYMBOLS,
    load_cataloged_corporate_actions,
)
from thericher_v2.data.daily import (
    build_fixed_etf_daily_raw_subset,
    build_fixed_etf_daily_subset,
)
from thericher_v2.data.tiingo_eod import (
    MINIMUM_RETRIEVAL_LAG_DAYS,
    R2CorporateActionLineage,
    TiingoEodAcquisitionError,
    build_tiingo_eod_corporate_action_snapshot,
    build_tiingo_raw_d1_comparison_snapshot,
    fetch_tiingo_standard_eod_responses,
    load_cataloged_tiingo_raw_d1_bars,
    load_fixed_r2_corporate_action_lineage,
    normalize_tiingo_raw_d1_response,
    normalize_tiingo_standard_eod_response,
)

_DAILY_SOURCE_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    "asset_type",
    "yahoo_symbol",
    "source",
)


@dataclass(frozen=True)
class _RawD1LoaderFixture:
    repo_root: Path
    r2_lineage: R2CorporateActionLineage
    source_snapshot_dir: Path
    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_normalizer_uses_only_three_fields_and_maps_cash_and_split() -> None:
    sessions = _sessions()
    raw = _payload(
        [
            _row(CAMPAIGN_COVERAGE_START, div_cash="0", split_factor="1"),
            _row(CAMPAIGN_COVERAGE_END, div_cash="1.594937", split_factor="0.5"),
        ]
    )

    events = normalize_tiingo_standard_eod_response(
        symbol="SPY", raw_response=raw, expected_session_dates=sessions
    )

    assert [(event.event_type, event.affected_session_date) for event in events] == [
        ("cash_distribution", CAMPAIGN_COVERAGE_END),
        ("split", CAMPAIGN_COVERAGE_END),
    ]
    assert events[0].cash_amount is not None and str(events[0].cash_amount) == "1.594937"
    assert (events[1].split_numerator, events[1].split_denominator) == (1, 2)
    assert b"adjClose" in raw
    assert all("adjClose" not in event.event_id for event in events)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda row: row.pop("date"), "date is missing or malformed"),
        (lambda row: row.__setitem__("date", "not-a-date"), "date is missing or malformed"),
        (lambda row: row.pop("divCash"), "divCash is missing or malformed"),
        (lambda row: row.__setitem__("divCash", "NaN"), "divCash is missing or malformed"),
        (lambda row: row.pop("splitFactor"), "splitFactor is missing or malformed"),
        (lambda row: row.__setitem__("splitFactor", "0"), "splitFactor must be positive"),
    ],
)
def test_normalizer_fails_closed_for_required_tiingo_fields(mutate, match: str) -> None:
    rows = [
        _row(CAMPAIGN_COVERAGE_START, div_cash="0", split_factor="1"),
        _row(CAMPAIGN_COVERAGE_END, div_cash="0", split_factor="1"),
    ]
    mutate(rows[0])

    with pytest.raises(ValueError, match=match):
        normalize_tiingo_standard_eod_response(
            symbol="SPY", raw_response=_payload(rows), expected_session_dates=_sessions()
        )


def test_normalizer_rejects_missing_or_extra_r2_observed_sessions() -> None:
    missing = _payload([_row(CAMPAIGN_COVERAGE_START, div_cash="0", split_factor="1")])
    with pytest.raises(ValueError, match="session coverage is incomplete"):
        normalize_tiingo_standard_eod_response(
            symbol="SPY", raw_response=missing, expected_session_dates=_sessions()
        )

    extra = _payload(
        [
            _row(CAMPAIGN_COVERAGE_START, div_cash="0", split_factor="1"),
            _row(date(2024, 3, 15), div_cash="0", split_factor="1"),
            _row(CAMPAIGN_COVERAGE_END, div_cash="0", split_factor="1"),
        ]
    )
    with pytest.raises(ValueError, match="session coverage is incomplete"):
        normalize_tiingo_standard_eod_response(
            symbol="SPY", raw_response=extra, expected_session_dates=_sessions()
        )


def test_raw_d1_normalizer_is_prefix_invariant_and_ignores_adjusted_fields() -> None:
    rows = [
        _row(CAMPAIGN_COVERAGE_START),
        _row(CAMPAIGN_COVERAGE_END, div_cash="1.0", split_factor="2"),
    ]
    full = normalize_tiingo_raw_d1_response(
        symbol="SPY", raw_response=_payload(rows), expected_session_dates=_sessions()
    )
    prefix = tiingo_eod._normalize_tiingo_raw_d1_response(
        symbol="SPY",
        raw_response=_payload(rows[:1]),
        expected_session_dates=frozenset({CAMPAIGN_COVERAGE_START}),
        require_campaign_span=False,
    )

    assert full[:1] == prefix
    assert tiingo_eod._raw_d1_csv_bytes(full[:1]) == tiingo_eod._raw_d1_csv_bytes(prefix)
    assert b"adjClose" in _payload(rows)
    assert b"adjClose" not in tiingo_eod._raw_d1_csv_bytes(full)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("open", None, "open is missing or malformed"),
        ("volume", "-1", "raw volume cannot be negative"),
        ("high", "99", "raw OHLC range is invalid"),
    ],
)
def test_raw_d1_normalizer_rejects_invalid_raw_values(
    field: str, value: str | None, match: str
) -> None:
    rows = [_row(CAMPAIGN_COVERAGE_START), _row(CAMPAIGN_COVERAGE_END)]
    if value is None:
        rows[0].pop(field)
    else:
        rows[0][field] = value

    with pytest.raises(ValueError, match=match):
        normalize_tiingo_raw_d1_response(
            symbol="SPY", raw_response=_payload(rows), expected_session_dates=_sessions()
        )


def test_raw_d1_snapshot_is_external_and_hash_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    lineage = _lineage(market_root)
    source = market_root / "events" / "snapshot=2026-07-18-tiingo-eod-r1"
    source_result = build_tiingo_eod_corporate_action_snapshot(
        destination=source,
        raw_responses=_responses(),
        r2_lineage=lineage,
        retrieved_at_utc=_eligible_retrieval(),
        market_data_root=market_root,
        repo_root=repo_root,
    )
    destination = market_root / "daily" / "snapshot=2026-07-18-tiingo-raw-d1-r1"

    def unexpected_fetch(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("raw-D1 derivation must not fetch or read a token")

    monkeypatch.setattr(tiingo_eod, "fetch_tiingo_standard_eod_responses", unexpected_fetch)
    result = build_tiingo_raw_d1_comparison_snapshot(
        destination=destination,
        source_snapshot_dir=source,
        r2_lineage=lineage,
        derived_at_utc=datetime(2026, 7, 18, 2, 3, 4, tzinfo=UTC),
        market_data_root=market_root,
        repo_root=repo_root,
    )

    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    subset = gzip.decompress((destination / "ohlcv_1d.csv.gz").read_bytes())
    assert result.source_raw_hashes == source_result.raw_hashes
    assert result.row_count == 6
    assert not (destination / "raw").exists()
    assert b"adjClose" not in subset
    assert manifest["scope"] == {
        "retrospective_development_replay_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
    }
    assert manifest["source_lineage"]["tiingo_corporate_actions"]["dataset_hash"] == (
        source_result.dataset_hash
    )
    with pytest.raises(FileExistsError, match="already exists"):
        build_tiingo_raw_d1_comparison_snapshot(
            destination=destination,
            source_snapshot_dir=source,
            r2_lineage=lineage,
            derived_at_utc=datetime(2026, 7, 18, 2, 3, 4, tzinfo=UTC),
            market_data_root=market_root,
            repo_root=repo_root,
        )

    raw_path = source / "raw" / "SPY.json"
    raw_bytes = raw_path.read_bytes()
    raw_path.write_bytes(b"x" + raw_bytes[1:])
    with pytest.raises(ValueError, match="raw source hash mismatch"):
        build_tiingo_raw_d1_comparison_snapshot(
            destination=market_root / "daily" / "snapshot=tampered",
            source_snapshot_dir=source,
            r2_lineage=lineage,
            derived_at_utc=datetime(2026, 7, 18, 2, 3, 4, tzinfo=UTC),
            market_data_root=market_root,
            repo_root=repo_root,
        )


def test_raw_d1_loader_reattests_896_session_input_without_network_or_credentials(
    raw_d1_loader_fixture: _RawD1LoaderFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_access(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("raw-D1 loader must stay offline and never read a token")

    monkeypatch.setattr(tiingo_eod, "fetch_tiingo_standard_eod_responses", unexpected_access)
    monkeypatch.setattr(tiingo_eod, "read_tiingo_api_token", unexpected_access)

    loaded = _load_raw_d1_fixture(raw_d1_loader_fixture, symbol="SPY")

    assert loaded.dataset_id == raw_d1_loader_fixture.dataset_id
    assert loaded.dataset_hash == raw_d1_loader_fixture.dataset_hash
    assert loaded.source_path == raw_d1_loader_fixture.snapshot_dir / "ohlcv_1d.csv.gz"
    assert len(loaded.bars) == 896
    assert {bar.symbol for bar in loaded.bars} == {"SPY"}
    assert all(bar.timeframe.value == "1d" and bar.complete for bar in loaded.bars)
    assert loaded.bars[0].start_ts.date() == CAMPAIGN_COVERAGE_START
    assert loaded.bars[-1].start_ts.date() == CAMPAIGN_COVERAGE_END


def test_raw_d1_loader_accepts_a_pinned_portable_gzip_representation(
    raw_d1_loader_fixture: _RawD1LoaderFixture,
) -> None:
    snapshot = raw_d1_loader_fixture.snapshot_dir
    subset_path = snapshot / "ohlcv_1d.csv.gz"
    manifest_path = snapshot / "manifest.json"
    original_subset = subset_path.read_bytes()
    original_manifest = manifest_path.read_bytes()
    try:
        canonical_csv = gzip.decompress(original_subset)
        portable_subset = gzip.compress(canonical_csv, compresslevel=1, mtime=0)
        assert portable_subset != original_subset
        portable_hash = "sha256:" + hashlib.sha256(portable_subset).hexdigest()
        subset_path.write_bytes(portable_subset)
        manifest = json.loads(original_manifest)
        manifest["dataset_hash"] = portable_hash
        manifest["subset"]["sha256"] = portable_hash
        manifest["subset"]["size_bytes"] = len(portable_subset)
        portable_manifest_hash = _write_json(manifest_path, manifest)

        loaded = _load_raw_d1_fixture(
            raw_d1_loader_fixture,
            symbol="SPY",
            dataset_hash=portable_hash,
            manifest_hash=portable_manifest_hash,
        )

        assert len(loaded.bars) == 896
        assert loaded.dataset_hash == portable_hash
    finally:
        subset_path.write_bytes(original_subset)
        manifest_path.write_bytes(original_manifest)


def test_raw_d1_loader_rejects_parent_raw_and_r2_lineage_tampering(
    raw_d1_loader_fixture: _RawD1LoaderFixture,
) -> None:
    parent_raw = raw_d1_loader_fixture.source_snapshot_dir / "raw" / "SPY.json"
    original_parent_raw = parent_raw.read_bytes()
    try:
        parent_raw.write_bytes(original_parent_raw + b"tamper")
        with pytest.raises(ValueError, match="raw (source size|hash) mismatch"):
            _load_raw_d1_fixture(raw_d1_loader_fixture, symbol="SPY")
    finally:
        parent_raw.write_bytes(original_parent_raw)

    manifest_path = raw_d1_loader_fixture.snapshot_dir / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    try:
        manifest = json.loads(original_manifest)
        manifest["source_lineage"]["r2_calendar"]["dataset_hash"] = "sha256:" + "c" * 64
        tampered_manifest_hash = _write_json(manifest_path, manifest)
        with pytest.raises(ValueError, match="r2 calendar lineage is invalid"):
            _load_raw_d1_fixture(
                raw_d1_loader_fixture,
                symbol="SPY",
                manifest_hash=tampered_manifest_hash,
            )
    finally:
        manifest_path.write_bytes(original_manifest)


def test_raw_d1_loader_rejects_adjusted_or_noncanonical_subset_bytes(
    raw_d1_loader_fixture: _RawD1LoaderFixture,
) -> None:
    snapshot = raw_d1_loader_fixture.snapshot_dir
    subset_path = snapshot / "ohlcv_1d.csv.gz"
    manifest_path = snapshot / "manifest.json"
    original_subset = subset_path.read_bytes()
    original_manifest = manifest_path.read_bytes()
    try:
        raw_csv = gzip.decompress(original_subset)
        header, body = raw_csv.split(b"\n", 1)
        adjusted_csv = header + b",adjClose\n" + body
        adjusted_subset = tiingo_eod._gzip_bytes(adjusted_csv)
        adjusted_hash = "sha256:" + hashlib.sha256(adjusted_subset).hexdigest()
        subset_path.write_bytes(adjusted_subset)

        manifest = json.loads(original_manifest)
        manifest["dataset_hash"] = adjusted_hash
        manifest["subset"]["sha256"] = adjusted_hash
        manifest["subset"]["size_bytes"] = len(adjusted_subset)
        manifest["subset"]["schema"].append("adjClose")
        adjusted_manifest_hash = _write_json(manifest_path, manifest)
        with pytest.raises(ValueError, match="subset evidence is invalid"):
            _load_raw_d1_fixture(
                raw_d1_loader_fixture,
                symbol="SPY",
                dataset_hash=adjusted_hash,
                manifest_hash=adjusted_manifest_hash,
            )

        subset_path.write_bytes(original_subset)
        manifest_path.write_bytes(original_manifest)
        changed_csv = raw_csv.replace(b",100.0,101.0,99.0,100.5,", b",100.1,101.0,99.0,100.5,", 1)
        assert changed_csv != raw_csv
        changed_subset = tiingo_eod._gzip_bytes(changed_csv)
        changed_hash = "sha256:" + hashlib.sha256(changed_subset).hexdigest()
        subset_path.write_bytes(changed_subset)
        manifest = json.loads(original_manifest)
        manifest["dataset_hash"] = changed_hash
        manifest["subset"]["sha256"] = changed_hash
        manifest["subset"]["size_bytes"] = len(changed_subset)
        changed_manifest_hash = _write_json(manifest_path, manifest)
        with pytest.raises(ValueError, match="does not match attested raw source bytes"):
            _load_raw_d1_fixture(
                raw_d1_loader_fixture,
                symbol="SPY",
                dataset_hash=changed_hash,
                manifest_hash=changed_manifest_hash,
            )
    finally:
        subset_path.write_bytes(original_subset)
        manifest_path.write_bytes(original_manifest)


def test_snapshot_is_immutable_hash_bound_and_replay_only(tmp_path: Path) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    lineage = _lineage(market_root)
    destination = market_root / "events" / "snapshot=2026-07-18-tiingo-eod-r1"
    result = build_tiingo_eod_corporate_action_snapshot(
        destination=destination,
        raw_responses=_responses(),
        r2_lineage=lineage,
        retrieved_at_utc=_eligible_retrieval(),
        market_data_root=market_root,
    )

    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert result.catalog.dataset_hash == result.dataset_hash
    assert manifest["scope"] == {
        "retrospective_development_replay_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
    }
    assert manifest["event_finalization"]["minimum_retrieval_lag_days"] == 7
    assert manifest["tiingo_source_contract"]["normalization_fields"] == [
        "date",
        "divCash",
        "splitFactor",
    ]
    assert "adjClose" not in (destination / "corporate_actions.csv").read_text(encoding="utf-8")
    assert "adjClose" not in (destination / "manifest.json").read_text(encoding="utf-8")
    assert (destination / "raw" / "SPY.json").read_bytes() == _responses()["SPY"]
    assert result.raw_hashes["SPY"] == manifest["raw_sources"][0]["sha256"]

    raw_path = destination / "raw" / "SPY.json"
    raw_path.write_bytes(raw_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="raw source size mismatch"):
        load_cataloged_corporate_actions(
            destination,
            dataset_id=result.dataset_id,
            expected_dataset_hash=result.dataset_hash,
            expected_manifest_hash=result.manifest_hash,
            expected_r2_dataset_id=lineage.dataset_id,
            expected_r2_dataset_hash=lineage.dataset_hash,
            expected_r2_manifest_hash=lineage.manifest_hash,
            observed_session_dates=lineage.observed_session_dates,
        )


def test_snapshot_rejects_early_retrieval_overwrite_and_r2_overlap(tmp_path: Path) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    lineage = _lineage(market_root)
    destination = market_root / "events" / "snapshot=2026-07-18-tiingo-eod-r1"
    with pytest.raises(ValueError, match="too close to campaign end"):
        build_tiingo_eod_corporate_action_snapshot(
            destination=destination,
            raw_responses=_responses(),
            r2_lineage=lineage,
            retrieved_at_utc=datetime(
                2026, 6, 22, tzinfo=UTC
            ) + timedelta(days=MINIMUM_RETRIEVAL_LAG_DAYS - 1),
            market_data_root=market_root,
        )
    result = build_tiingo_eod_corporate_action_snapshot(
        destination=destination,
        raw_responses=_responses(),
        r2_lineage=lineage,
        retrieved_at_utc=_eligible_retrieval(),
        market_data_root=market_root,
    )
    with pytest.raises(FileExistsError, match="already exists"):
        build_tiingo_eod_corporate_action_snapshot(
            destination=destination,
            raw_responses=_responses(),
            r2_lineage=lineage,
            retrieved_at_utc=_eligible_retrieval(),
            market_data_root=market_root,
        )
    with pytest.raises(ValueError, match="cannot overlap the r2"):
        build_tiingo_eod_corporate_action_snapshot(
            destination=lineage.snapshot_dir / "snapshot=bad",
            raw_responses=_responses(),
            r2_lineage=lineage,
            retrieved_at_utc=_eligible_retrieval(),
            market_data_root=market_root,
        )
    assert result.snapshot_dir == destination


@pytest.fixture
def guarded_token_reader(tmp_path, monkeypatch):
    def install(payload):
        path = tmp_path / "token.env"
        path.write_bytes(payload)
        keys, values, offset = set(), set(), 0
        for line in payload.splitlines(keepends=True):
            body = line.rstrip(b"\r\n")
            separator = body.find(b"=")
            if separator >= 0:
                keys.add((offset, offset + separator))
                if body[:separator] == b"TIINGO_API_TOKEN":
                    values.add((offset + separator + 1, offset + len(body)))
            offset += len(line)
        slices, decodes, closed = [], [], []

        class KeyOnlyFile:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.handle.close()

            def fileno(self):
                return self.handle.fileno()

            def __iter__(self):
                raise AssertionError("line iteration must not materialize other values")

            def read(self, *_args):
                raise AssertionError("file reads must not materialize other values")

        original_open = Path.open

        def guarded_open(actual_path, *args, **kwargs):
            assert actual_path == path and args == ("rb",) and kwargs == {"buffering": 0}
            return KeyOnlyFile(original_open(actual_path, *args, **kwargs))

        class GuardedMap:
            def __init__(self, _fileno, length, *, access):
                assert length == 0 and access == tiingo_eod.mmap.ACCESS_READ

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                closed.append(True)

            def __len__(self):
                return len(payload)

            def find(self, needle, start=0, end=None):
                assert needle in {b"\r", b"\n", b"="}
                return payload.find(needle, start, len(payload) if end is None else end)

            def __getitem__(self, span):
                assert isinstance(span, slice) and span.step is None
                bounds = span.start, span.stop
                assert bounds in keys | values, "slice crossed into an unselected value"
                slices.append(bounds)

                class CheckedBytes(bytes):
                    def decode(self, encoding="utf-8", errors="strict"):
                        assert bounds in values and encoding == "utf-8" and errors == "strict"
                        decodes.append(bounds)
                        return super().decode(encoding, errors)

                return CheckedBytes(payload[span])

        monkeypatch.setattr(Path, "open", guarded_open)
        monkeypatch.setattr(tiingo_eod.mmap, "mmap", GuardedMap)
        return path, values, slices, decodes, closed

    return install


@pytest.mark.parametrize("newline", (b"\n", b"\r\n", b"\r"))
@pytest.mark.parametrize("final_newline", (False, True))
def test_token_reader_copies_and_decodes_only_selected_value(
    guarded_token_reader, newline, final_newline
):
    payload = newline.join(
        (
            b"KIS_LIVE_APP_KEY=forbidden-live-before\xff",
            b"TIINGO_API_TOKE=forbidden-short-prefix",
            b"OTHER=TIINGO_API_TOKEN=decoy",
            b"# TIINGO_API_TOKEN=comment",
            b"TIINGO_API_TOKEN=\t token-for-test \t",
            b"KIS_PAPER_APP_SECRET=forbidden-paper-after\xfe",
            b"KIS_LIVE_APP_SECRET=forbidden-live-after\xff",
        )
    ) + (newline if final_newline else b"")
    path, values, slices, decodes, closed = guarded_token_reader(payload)
    assert tiingo_eod.read_tiingo_api_token(path) == "token-for-test"
    assert set(decodes) == values and len(decodes) == 1
    assert all(bounds in slices for bounds in decodes) and closed == [True]


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (b"\r\n\n\rTIINGO_API_TOKEN=x=y==z\r\n", "x=y==z"),
        (b"TIINGO_API_TOKEN='literal'", "'literal'"),
        (b"TIINGO_API_TOKEN=\xce\xb1", "\u03b1"),
        (
            b"export TIINGO_API_TOKEN=wrong\n TIINGO_API_TOKEN=wrong\r"
            b"TIINGO_API_TOKEN_EXTRA=wrong\nTIINGO_API_TOKEN =wrong\r\n"
            b"TIINGO_API_TOKEN=correct",
            "correct",
        ),
    ),
)
def test_token_reader_preserves_exact_key_and_literal_value_grammar(
    guarded_token_reader, payload, expected
):
    path, values, _, decodes, closed = guarded_token_reader(payload)
    assert tiingo_eod.read_tiingo_api_token(path) == expected
    assert set(decodes) == values and closed == [True]


@pytest.mark.parametrize(
    ("payload", "decoded_count"),
    (
        (b"", 0),
        (b"TIINGO_API_TOKEN\r# TIINGO_API_TOKEN=comment\n", 0),
        (b"KIS_LIVE_APP_KEY=\xff\nTIINGO_API_TOKE=secret\rOTHER=decoy", 0),
        (b"TIINGO_API_TOKEN=\r\n", 1),
        (b"TIINGO_API_TOKEN= \t\r", 1),
        (b"TIINGO_API_TOKEN=first\nTIINGO_API_TOKEN=second", 1),
        (b"TIINGO_API_TOKEN=first\rKIS_LIVE_APP_KEY=\xff\rTIINGO_API_TOKEN=", 1),
        (b"TIINGO_API_TOKEN=\xff", 1),
    ),
)
def test_token_reader_masks_missing_empty_duplicate_and_invalid_selected_value(
    guarded_token_reader, payload, decoded_count
):
    path, _, _, decodes, closed = guarded_token_reader(payload)
    with pytest.raises(TiingoEodAcquisitionError, match="^Tiingo token is unavailable$") as error:
        tiingo_eod.read_tiingo_api_token(path)
    assert len(decodes) == decoded_count
    if error.value.__context__ is not None:
        assert error.value.__suppress_context__
    assert closed == ([True] if payload else [])


@pytest.mark.parametrize("empty_file", (False, True))
def test_token_reader_missing_or_empty_real_synthetic_file(tmp_path, empty_file):
    path = tmp_path / "token.env"
    if empty_file:
        path.write_bytes(b"")
    with pytest.raises(TiingoEodAcquisitionError, match="^Tiingo token is unavailable$"):
        tiingo_eod.read_tiingo_api_token(path)


def test_fetch_reads_only_the_approved_token_and_persists_no_secret(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("KIS_PAPER_APP_SECRET=never-read\nTIINGO_API_TOKEN=token-for-test\n")
    seen: list[object] = []

    def opener(request, *, timeout: float):
        seen.append((request.full_url, request.get_header("Authorization"), timeout))
        return _Response(_payload([_row(CAMPAIGN_COVERAGE_START), _row(CAMPAIGN_COVERAGE_END)]))

    responses = fetch_tiingo_standard_eod_responses(env_path=env_path, opener=opener)

    assert set(responses) == set(CORPORATE_ACTION_SYMBOLS)
    assert len(seen) == 3
    assert all(header == "Token token-for-test" for _, header, _ in seen)
    assert all("token-for-test" not in url for url, _, _ in seen)
    assert all("KIS_PAPER_APP_SECRET" not in raw.decode("utf-8") for raw in responses.values())


def test_fetch_masks_missing_token(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("KIS_PAPER_APP_SECRET=never-read\n")
    with pytest.raises(TiingoEodAcquisitionError, match="token is unavailable"):
        fetch_tiingo_standard_eod_responses(env_path=env_path)


def _sessions() -> frozenset[date]:
    return frozenset({CAMPAIGN_COVERAGE_START, CAMPAIGN_COVERAGE_END})


def _lineage(market_root: Path) -> R2CorporateActionLineage:
    snapshot_dir = market_root / "r2" / "snapshot=2026-07-18-r2"
    snapshot_dir.mkdir(parents=True)
    return R2CorporateActionLineage(
        snapshot_dir=snapshot_dir,
        dataset_id="us_equities.fixed_etf_daily.1d.snapshot=2026-07-18-r2",
        dataset_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        observed_session_dates={symbol: _sessions() for symbol in CORPORATE_ACTION_SYMBOLS},
    )


def _responses() -> dict[str, bytes]:
    return {
        symbol: _payload(
            [
                _row(CAMPAIGN_COVERAGE_START, div_cash="0", split_factor="1"),
                _row(
                    CAMPAIGN_COVERAGE_END,
                    div_cash="1.0" if symbol == "SPY" else "0",
                    split_factor="2" if symbol == "QQQ" else "1",
                ),
            ]
        )
        for symbol in CORPORATE_ACTION_SYMBOLS
    }


def _row(
    session: date,
    *,
    div_cash: str = "0",
    split_factor: str = "1",
) -> dict[str, str]:
    return {
        "date": f"{session.isoformat()}T00:00:00.000Z",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000",
        "divCash": div_cash,
        "splitFactor": split_factor,
        "adjClose": "this-must-not-enter-normalized-evidence",
    }


def _payload(rows: list[dict[str, str]]) -> bytes:
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


def _eligible_retrieval() -> datetime:
    return datetime(2026, 7, 18, 1, 2, 3, tzinfo=UTC)


@pytest.fixture(scope="module")
def raw_d1_loader_fixture(tmp_path_factory: pytest.TempPathFactory) -> _RawD1LoaderFixture:
    root = tmp_path_factory.mktemp("tiingo-raw-d1-loader")
    market_root = root / "market"
    market_root.mkdir()
    repo_root = root / "repo"
    repo_root.mkdir()
    sessions = _full_campaign_sessions()

    source_path = market_root / "source.csv.gz"
    _write_daily_source(source_path, sessions)
    r1_snapshot = market_root / "r1" / "snapshot=fixture-r1"
    r1_snapshot.parent.mkdir()
    build_fixed_etf_daily_subset(source_path, r1_snapshot)
    r2_snapshot = market_root / "r2" / "snapshot=fixture-r2"
    r2_snapshot.parent.mkdir()
    build_fixed_etf_daily_raw_subset(r1_snapshot, r2_snapshot)
    r2_lineage = load_fixed_r2_corporate_action_lineage(r2_snapshot)

    source_snapshot_dir = market_root / "events" / "snapshot=fixture-tiingo-eod-r1"
    source_snapshot_dir.parent.mkdir()
    build_tiingo_eod_corporate_action_snapshot(
        destination=source_snapshot_dir,
        raw_responses=_responses_for_sessions(sessions),
        r2_lineage=r2_lineage,
        retrieved_at_utc=_eligible_retrieval(),
        market_data_root=market_root,
        repo_root=repo_root,
    )
    snapshot_dir = market_root / "daily" / "snapshot=fixture-tiingo-raw-d1-r1"
    snapshot_dir.parent.mkdir()
    snapshot = build_tiingo_raw_d1_comparison_snapshot(
        destination=snapshot_dir,
        source_snapshot_dir=source_snapshot_dir,
        r2_lineage=r2_lineage,
        derived_at_utc=datetime(2026, 7, 18, 2, 3, 4, tzinfo=UTC),
        market_data_root=market_root,
        repo_root=repo_root,
    )
    return _RawD1LoaderFixture(
        repo_root=repo_root,
        r2_lineage=r2_lineage,
        source_snapshot_dir=source_snapshot_dir,
        snapshot_dir=snapshot_dir,
        dataset_id=snapshot.dataset_id,
        dataset_hash=snapshot.dataset_hash,
        manifest_hash=snapshot.manifest_hash,
    )


def _load_raw_d1_fixture(
    fixture: _RawD1LoaderFixture,
    *,
    symbol: str,
    dataset_hash: str | None = None,
    manifest_hash: str | None = None,
):
    return load_cataloged_tiingo_raw_d1_bars(
        fixture.snapshot_dir,
        dataset_id=fixture.dataset_id,
        expected_dataset_hash=dataset_hash or fixture.dataset_hash,
        expected_manifest_hash=manifest_hash or fixture.manifest_hash,
        source_snapshot_dir=fixture.source_snapshot_dir,
        r2_lineage=fixture.r2_lineage,
        symbol=symbol,
        repo_root=fixture.repo_root,
    )


def _full_campaign_sessions() -> tuple[date, ...]:
    weekdays: list[date] = []
    current = CAMPAIGN_COVERAGE_START
    while current <= CAMPAIGN_COVERAGE_END:
        if current.weekday() < 5:
            weekdays.append(current)
        current += timedelta(days=1)
    sessions = tuple(sorted({*weekdays[:895], CAMPAIGN_COVERAGE_END}))
    assert len(sessions) == 896
    assert sessions[0] == CAMPAIGN_COVERAGE_START
    assert sessions[-1] == CAMPAIGN_COVERAGE_END
    return sessions


def _responses_for_sessions(sessions: tuple[date, ...]) -> dict[str, bytes]:
    return {
        symbol: _payload(
            [
                _row(
                    session,
                    div_cash="1.0" if symbol == "SPY" and session == sessions[-1] else "0",
                    split_factor="2" if symbol == "QQQ" and session == sessions[-1] else "1",
                )
                for session in sessions
            ]
        )
        for symbol in CORPORATE_ACTION_SYMBOLS
    }


def _write_daily_source(path: Path, sessions: tuple[date, ...]) -> None:
    rows = [
        {
            "symbol": symbol,
            "date": session.isoformat(),
            "open": "100",
            "high": "110",
            "low": "90",
            "close": "100",
            "volume": "1000",
            "adj_close": "50",
            "asset_type": "stock",
            "yahoo_symbol": symbol,
            "source": "tiingo_raw_d1_loader_fixture",
        }
        for symbol in CORPORATE_ACTION_SYMBOLS
        for session in sessions
    ]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_DAILY_SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: object) -> str:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return "sha256:" + hashlib.sha256(payload).hexdigest()
