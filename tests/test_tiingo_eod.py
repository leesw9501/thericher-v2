from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data.corporate_actions import (
    CAMPAIGN_COVERAGE_END,
    CAMPAIGN_COVERAGE_START,
    CORPORATE_ACTION_SYMBOLS,
    load_cataloged_corporate_actions,
)
from thericher_v2.data.tiingo_eod import (
    MINIMUM_RETRIEVAL_LAG_DAYS,
    R2CorporateActionLineage,
    TiingoEodAcquisitionError,
    build_tiingo_eod_corporate_action_snapshot,
    fetch_tiingo_standard_eod_responses,
    normalize_tiingo_standard_eod_response,
)


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
        "divCash": div_cash,
        "splitFactor": split_factor,
        "adjClose": "this-must-not-enter-normalized-evidence",
    }


def _payload(rows: list[dict[str, str]]) -> bytes:
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


def _eligible_retrieval() -> datetime:
    return datetime(2026, 7, 18, 1, 2, 3, tzinfo=UTC)
