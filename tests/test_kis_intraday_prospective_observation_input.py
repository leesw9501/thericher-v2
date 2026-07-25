from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_intraday_prospective_observation as prospective_input
from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    KisIntradayProspectiveHeadObservationContract,
)

_HISTORICAL_DATES = KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
_PROSPECTIVE_DATES = (
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
)


def test_invalid_preparation_pair_rejects_before_any_raw_cache_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)

    def fail_reader(**_kwargs: object) -> CatalogedBars:
        raise AssertionError("raw cache reader must not run for an invalid preparation pair")

    monkeypatch.setattr(
        prospective_input,
        "load_verified_kis_paper_private_intraday_catalog",
        fail_reader,
    )

    for mutation in ("missing", "malformed", "hash", "unexpected", "digest", "dates"):
        case = _inputs(tmp_path / mutation)
        _mutate_pair(case["preparation_dir"], mutation)
        with pytest.raises(ValueError, match="preparation"):
            prospective_input.load_kis_intraday_prospective_observation_input(
                historical_cache_root=case["historical_cache_root"],
                head_cache_root=case["head_cache_root"],
                preparation_dir=case["preparation_dir"],
                repo_root=case["repo_root"],
            )

    assert inputs["preparation_dir"].is_dir()


def test_public_preparation_verifier_is_read_only_and_returns_safe_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)

    def fail_reader(**_kwargs: object) -> CatalogedBars:
        raise AssertionError("pair verifier must not open a raw cache")

    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective_input,
        "load_verified_kis_paper_private_intraday_catalog",
        fail_reader,
    )
    before_pair = _pair_bytes(inputs["preparation_dir"])

    preparation = prospective_input.verify_kis_intraday_prospective_observation_preparation(
        head_cache_root=inputs["head_cache_root"],
        preparation_dir=inputs["preparation_dir"],
        repo_root=inputs["repo_root"],
    )

    assert preparation.selected_session_dates == _PROSPECTIVE_DATES
    assert preparation.contract_hash.startswith("sha256:")
    assert preparation.precommit_hash.startswith("sha256:")
    assert preparation.artifact_slot_id.startswith("sha256:")
    assert preparation.selected_rows_fingerprint_sha256.startswith("sha256:")
    assert preparation.head_index_metadata_sha256.startswith("sha256:")
    assert not hasattr(preparation, "preparation_dir")
    assert _pair_bytes(inputs["preparation_dir"]) == before_pair


def test_public_preparation_verifier_preserves_crlf_index_byte_identity(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, index_line_ending="\r\n")

    preparation = prospective_input.verify_kis_intraday_prospective_observation_preparation(
        head_cache_root=inputs["head_cache_root"],
        preparation_dir=inputs["preparation_dir"],
        repo_root=inputs["repo_root"],
    )

    index_bytes = (inputs["head_cache_root"] / "v1" / "index.json").read_bytes()
    assert preparation.head_index_metadata_sha256 == (
        "sha256:" + hashlib.sha256(index_bytes).hexdigest()
    )


@pytest.mark.parametrize("mutation", ("append_qqq_session", "update_spy_metadata"))
def test_public_preparation_verifier_accepts_unselected_head_updates(
    tmp_path: Path,
    mutation: str,
) -> None:
    inputs = _inputs(tmp_path)
    original = prospective_input.verify_kis_intraday_prospective_observation_preparation(
        head_cache_root=inputs["head_cache_root"],
        preparation_dir=inputs["preparation_dir"],
        repo_root=inputs["repo_root"],
    )

    _mutate_head_index_without_changing_selected_qqq(
        inputs["head_cache_root"],
        mutation=mutation,
    )

    assert prospective_input.verify_kis_intraday_prospective_observation_preparation(
        head_cache_root=inputs["head_cache_root"],
        preparation_dir=inputs["preparation_dir"],
        repo_root=inputs["repo_root"],
    ) == original


def test_loads_exact_separate_pair_bound_streams_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    historical_catalog = _catalog(_HISTORICAL_DATES, dataset_hash="sha256:" + "1" * 64)
    prospective_catalog = _catalog(
        (*_PROSPECTIVE_DATES, date(2026, 7, 15)),
        dataset_hash="sha256:" + "2" * 64,
    )
    calls: list[tuple[Path, str, str]] = []

    def load_verified(
        *,
        cache_root: Path,
        repo_root: Path,
        symbol: str,
        exchange: str,
    ) -> CatalogedBars:
        assert repo_root == inputs["repo_root"].resolve()
        calls.append((cache_root, symbol, exchange))
        if cache_root == inputs["historical_cache_root"].resolve():
            return historical_catalog
        if cache_root == inputs["head_cache_root"].resolve():
            return prospective_catalog
        raise AssertionError("unexpected cache root")

    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective_input,
        "load_verified_kis_paper_private_intraday_catalog",
        load_verified,
    )
    before_pair = _pair_bytes(inputs["preparation_dir"])

    result = prospective_input.load_kis_intraday_prospective_observation_input(
        historical_cache_root=inputs["historical_cache_root"],
        head_cache_root=inputs["head_cache_root"],
        preparation_dir=inputs["preparation_dir"],
        repo_root=inputs["repo_root"],
    )

    assert calls == [
        (inputs["historical_cache_root"].resolve(), "QQQ", "NAS"),
        (inputs["head_cache_root"].resolve(), "QQQ", "NAS"),
    ]
    assert result.historical_session_dates == _HISTORICAL_DATES
    assert result.prospective_session_dates == _PROSPECTIVE_DATES
    assert len(result.historical_catalog.bars) == 10 * 390
    assert len(result.prospective_catalog.bars) == 5 * 390
    assert set(bar.start_ts.date() for bar in result.historical_catalog.bars) == set(
        _HISTORICAL_DATES
    )
    assert set(bar.start_ts.date() for bar in result.prospective_catalog.bars) == set(
        _PROSPECTIVE_DATES
    )
    assert result.historical_catalog.dataset_hash != result.prospective_catalog.dataset_hash
    assert result.input_hash.startswith("sha256:")
    assert _pair_bytes(inputs["preparation_dir"]) == before_pair

    payload = result.safe_payload()
    encoded = json.dumps(payload, sort_keys=True)
    assert set(payload) == {
        "schema_version",
        "kind",
        "observation_id",
        "contract_hash",
        "precommit_hash",
        "artifact_slot_id",
        "selected_rows_fingerprint_sha256",
        "head_index_metadata_sha256",
        "historical",
        "prospective",
        "input_hash",
    }
    assert "source_path" not in encoded
    assert "open" not in payload
    assert "close" not in payload
    assert "price" not in encoded

    with pytest.raises(ValueError, match="verified Data loader"):
        prospective_input.KisIntradayProspectiveObservationInput(
            historical_catalog=result.historical_catalog,
            prospective_catalog=result.prospective_catalog,
            historical_session_dates=result.historical_session_dates,
            prospective_session_dates=result.prospective_session_dates,
            historical_input_hash=result.historical_input_hash,
            prospective_input_hash=result.prospective_input_hash,
            contract_hash=result.contract_hash,
            precommit_hash=result.precommit_hash,
            artifact_slot_id=result.artifact_slot_id,
            selected_rows_fingerprint_sha256=result.selected_rows_fingerprint_sha256,
            head_index_metadata_sha256=result.head_index_metadata_sha256,
            input_hash=result.input_hash,
        )

    with pytest.raises(ValueError, match="input identity"):
        replace(
            result,
            prospective_catalog=_catalog(
                _PROSPECTIVE_DATES,
                dataset_hash="sha256:" + "3" * 64,
            ),
        )


def test_loader_rejects_selected_head_index_mutation_during_cache_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    historical_catalog = _catalog(_HISTORICAL_DATES, dataset_hash="sha256:" + "1" * 64)
    prospective_catalog = _catalog(_PROSPECTIVE_DATES, dataset_hash="sha256:" + "2" * 64)
    calls = 0

    def load_verified(*, cache_root: Path, **_kwargs: object) -> CatalogedBars:
        nonlocal calls
        calls += 1
        if cache_root == inputs["historical_cache_root"].resolve():
            return historical_catalog
        if cache_root == inputs["head_cache_root"].resolve():
            _mutate_selected_qqq_fingerprint(inputs["head_cache_root"])
            return prospective_catalog
        raise AssertionError("unexpected cache root")

    monkeypatch.setattr(
        prospective_input,
        "load_verified_kis_paper_private_intraday_catalog",
        load_verified,
    )

    with pytest.raises(ValueError, match="changed during cache read"):
        prospective_input.load_kis_intraday_prospective_observation_input(
            historical_cache_root=inputs["historical_cache_root"],
            head_cache_root=inputs["head_cache_root"],
            preparation_dir=inputs["preparation_dir"],
            repo_root=inputs["repo_root"],
        )

    assert calls == 2


@pytest.mark.parametrize("mutation", ("append_qqq_session", "update_spy_metadata"))
def test_loader_accepts_unselected_head_index_update_during_cache_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    inputs = _inputs(tmp_path)
    historical_catalog = _catalog(_HISTORICAL_DATES, dataset_hash="sha256:" + "1" * 64)
    prospective_catalog = _catalog(_PROSPECTIVE_DATES, dataset_hash="sha256:" + "2" * 64)
    calls = 0

    def load_verified(*, cache_root: Path, **_kwargs: object) -> CatalogedBars:
        nonlocal calls
        calls += 1
        if cache_root == inputs["historical_cache_root"].resolve():
            return historical_catalog
        if cache_root == inputs["head_cache_root"].resolve():
            _mutate_head_index_without_changing_selected_qqq(
                inputs["head_cache_root"],
                mutation=mutation,
            )
            return prospective_catalog
        raise AssertionError("unexpected cache root")

    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective_input,
        "load_verified_kis_paper_private_intraday_catalog",
        load_verified,
    )

    result = prospective_input.load_kis_intraday_prospective_observation_input(
        historical_cache_root=inputs["historical_cache_root"],
        head_cache_root=inputs["head_cache_root"],
        preparation_dir=inputs["preparation_dir"],
        repo_root=inputs["repo_root"],
    )

    assert calls == 2
    assert result.prospective_session_dates == _PROSPECTIVE_DATES


def test_incomplete_selected_source_session_is_rejected_without_artifact_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    historical_catalog = _catalog(_HISTORICAL_DATES, dataset_hash="sha256:" + "1" * 64)
    incomplete_prospective = _catalog(
        _PROSPECTIVE_DATES,
        dataset_hash="sha256:" + "2" * 64,
        excluded_minutes={120},
    )

    def load_verified(*, cache_root: Path, **_kwargs: object) -> CatalogedBars:
        if cache_root == inputs["historical_cache_root"].resolve():
            return historical_catalog
        return incomplete_prospective

    monkeypatch.setattr(
        prospective_input,
        "load_verified_kis_paper_private_intraday_catalog",
        load_verified,
    )
    before_pair = _pair_bytes(inputs["preparation_dir"])

    with pytest.raises(ValueError, match="incomplete"):
        prospective_input.load_kis_intraday_prospective_observation_input(
            historical_cache_root=inputs["historical_cache_root"],
            head_cache_root=inputs["head_cache_root"],
            preparation_dir=inputs["preparation_dir"],
            repo_root=inputs["repo_root"],
        )

    assert _pair_bytes(inputs["preparation_dir"]) == before_pair


def _inputs(tmp_path: Path, *, index_line_ending: str = "\n") -> dict[str, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    historical_cache_root = tmp_path / "market-data" / "intraday"
    head_cache_root = tmp_path / "market-data" / "intraday-head"
    preparation_dir = tmp_path / "model-artifacts" / "prepared-head"
    row_fingerprints, head_index_metadata_sha256 = _write_head_index(
        head_cache_root,
        line_ending=index_line_ending,
    )
    _write_preparation_pair(
        preparation_dir,
        row_fingerprints=row_fingerprints,
        head_index_metadata_sha256=head_index_metadata_sha256,
    )
    return {
        "repo_root": repo_root,
        "historical_cache_root": historical_cache_root,
        "head_cache_root": head_cache_root,
        "preparation_dir": preparation_dir,
    }


def _write_head_index(
    head_cache_root: Path,
    *,
    line_ending: str = "\n",
) -> tuple[dict[str, str], str]:
    row_fingerprints: dict[str, str] = {}
    for session_date in _PROSPECTIVE_DATES:
        session = us_equity_2026_session(session_date)
        assert session is not None
        for offset in range(390):
            timestamp = session.window.open_ts + Timeframe.M1.duration * offset
            row_key = timestamp.astimezone(prospective_input._KOREA_TZ).strftime("%Y%m%dT%H%M%S")
            row_fingerprints[row_key] = "sha256:" + "a" * 64
    final_session = us_equity_2026_session(_PROSPECTIVE_DATES[-1])
    assert final_session is not None
    chunk = {
        "chunk_key": _chunk_key(row_fingerprints),
        "outcome": "committed",
        "input_cursor": None,
        "output_cursor": None,
        "manifest_path": "snapshots/unit/manifest.json",
        "manifest_hash": "sha256:" + "b" * 64,
        "raw_sha256": "sha256:" + "c" * 64,
        "raw_market_data_retained": True,
        "row_count": len(row_fingerprints),
        "row_fingerprints": row_fingerprints,
        "exact_overlap_rows": 0,
        "conflicting_overlap_rows": 0,
        "collected_at_utc": (
            final_session.window.close_ts + Timeframe.M1.duration
        ).isoformat(),
        "reason": None,
    }
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "generation": 0,
        "targets": [
            {
                "target_key": "QQQ/NAS/1m",
                "symbol": "QQQ",
                "exchange": "NAS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": [chunk],
            },
            {
                "target_key": "SPY/AMS/1m",
                "symbol": "SPY",
                "exchange": "AMS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": [],
            },
        ],
    }
    index_path = head_cache_root / "v1" / "index.json"
    index_path.parent.mkdir(parents=True)
    if line_ending == "\n":
        contents = json.dumps(index).encode("utf-8")
    else:
        contents = (
            json.dumps(index, indent=2, sort_keys=True).replace("\n", line_ending)
            + line_ending
        ).encode("utf-8")
    index_path.write_bytes(contents)
    return row_fingerprints, "sha256:" + hashlib.sha256(contents).hexdigest()


def _mutate_head_index_without_changing_selected_qqq(
    head_cache_root: Path,
    *,
    mutation: str,
) -> None:
    index_path = head_cache_root / "v1" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq_target = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    if mutation == "append_qqq_session":
        rows = qqq_target["chunks"][0]["row_fingerprints"]
        session = us_equity_2026_session(date(2026, 7, 15))
        assert session is not None
        for offset in range(390):
            timestamp = session.window.open_ts + Timeframe.M1.duration * offset
            rows[timestamp.astimezone(prospective_input._KOREA_TZ).strftime("%Y%m%dT%H%M%S")] = (
                "sha256:" + "a" * 64
            )
        qqq_target["chunks"][0]["row_count"] = len(rows)
        qqq_target["chunks"][0]["chunk_key"] = _chunk_key(rows)
        qqq_target["chunks"][0]["collected_at_utc"] = (
            session.window.close_ts + Timeframe.M1.duration
        ).isoformat()
    elif mutation == "update_spy_metadata":
        spy_target = next(
            target for target in index["targets"] if target["target_key"] == "SPY/AMS/1m"
        )
        spy_target["last_reason"] = "collector_incomplete"
    else:
        raise AssertionError(f"unexpected mutation: {mutation}")
    index["generation"] += 1
    index_path.write_text(json.dumps(index), encoding="utf-8")


def _mutate_selected_qqq_fingerprint(head_cache_root: Path) -> None:
    index_path = head_cache_root / "v1" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq_target = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    chunk = qqq_target["chunks"][0]
    rows = chunk["row_fingerprints"]
    first_row_key = next(iter(rows))
    rows[first_row_key] = "sha256:" + "d" * 64
    chunk["chunk_key"] = _chunk_key(rows)
    index["generation"] += 1
    index_path.write_text(json.dumps(index), encoding="utf-8")


def _write_preparation_pair(
    preparation_dir: Path,
    *,
    row_fingerprints: dict[str, str],
    head_index_metadata_sha256: str,
) -> None:
    contract = KisIntradayProspectiveHeadObservationContract()
    selected_rows_fingerprint_sha256 = _sha256_payload({"selected_rows": row_fingerprints})
    artifact_slot_id = _sha256_payload(
        {
            "contract_hash": contract.contract_hash,
            "selected_session_dates": [item.isoformat() for item in _PROSPECTIVE_DATES],
            "target_key": "QQQ/NAS/1m",
        }
    )
    precommit = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_intraday_prospective_head_observation_precommit",
        "status": "prepared",
        "prepared_at_utc": datetime(2026, 7, 15, tzinfo=UTC).isoformat(),
        "contract": contract.to_payload(),
        "contract_hash": contract.contract_hash,
        "head_index": {
            "status": "available",
            "metadata_sha256": head_index_metadata_sha256,
            "target_key": "QQQ/NAS/1m",
        },
        "selected_session_dates": [item.isoformat() for item in _PROSPECTIVE_DATES],
        "artifact_slot_id": artifact_slot_id,
        "selected_rows_fingerprint_sha256": selected_rows_fingerprint_sha256,
    }
    precommit["precommit_hash"] = _sha256_payload(precommit)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_intraday_prospective_head_observation_planning_receipt",
        "status": "prepared",
        "prepared_at_utc": precommit["prepared_at_utc"],
        "contract_hash": contract.contract_hash,
        "artifact_slot_id": artifact_slot_id,
        "selected_session_dates": [item.isoformat() for item in _PROSPECTIVE_DATES],
        "selected_rows_fingerprint_sha256": selected_rows_fingerprint_sha256,
        "precommit_hash": precommit["precommit_hash"],
        "next_consumer_contract": {
            "historical_development_prefix_session_count": 10,
            "prospective_session_receipts_required": 5,
        },
    }
    preparation_dir.mkdir(parents=True)
    (preparation_dir / "precommit.json").write_text(json.dumps(precommit), encoding="utf-8")
    (preparation_dir / "planning-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")


def _mutate_pair(preparation_dir: Path, mutation: str) -> None:
    precommit_path = preparation_dir / "precommit.json"
    receipt_path = preparation_dir / "planning-receipt.json"
    if mutation == "missing":
        receipt_path.unlink()
        return
    if mutation == "malformed":
        precommit_path.write_text("{", encoding="utf-8")
        return
    if mutation == "unexpected":
        (preparation_dir / "unexpected.json").write_text("{}", encoding="utf-8")
        return
    precommit = json.loads(precommit_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if mutation == "hash":
        precommit["precommit_hash"] = "sha256:" + "0" * 64
    elif mutation == "digest":
        precommit["selected_rows_fingerprint_sha256"] = "sha256:" + "e" * 64
        receipt["selected_rows_fingerprint_sha256"] = precommit[
            "selected_rows_fingerprint_sha256"
        ]
        precommit["precommit_hash"] = _sha256_payload(
            {key: value for key, value in precommit.items() if key != "precommit_hash"}
        )
        receipt["precommit_hash"] = precommit["precommit_hash"]
    elif mutation == "dates":
        shifted_dates = [
            date(2026, 7, 9).isoformat(),
            date(2026, 7, 10).isoformat(),
            date(2026, 7, 13).isoformat(),
            date(2026, 7, 14).isoformat(),
            date(2026, 7, 15).isoformat(),
        ]
        precommit["selected_session_dates"] = shifted_dates
        receipt["selected_session_dates"] = shifted_dates
        precommit["artifact_slot_id"] = _sha256_payload(
            {
                "contract_hash": precommit["contract_hash"],
                "selected_session_dates": shifted_dates,
                "target_key": "QQQ/NAS/1m",
            }
        )
        receipt["artifact_slot_id"] = precommit["artifact_slot_id"]
        precommit["precommit_hash"] = _sha256_payload(
            {key: value for key, value in precommit.items() if key != "precommit_hash"}
        )
        receipt["precommit_hash"] = precommit["precommit_hash"]
    else:
        raise AssertionError("unknown mutation")
    precommit_path.write_text(json.dumps(precommit), encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


def _catalog(
    session_dates: tuple[date, ...],
    *,
    dataset_hash: str,
    excluded_minutes: set[int] | None = None,
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_date in session_dates:
        session = us_equity_2026_session(session_date)
        assert session is not None
        for offset in range(390):
            if excluded_minutes is not None and offset in excluded_minutes:
                continue
            price = Decimal("100") + Decimal(offset) / Decimal("100")
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * offset,
                    open=price,
                    high=price + Decimal("0.01"),
                    low=price - Decimal("0.01"),
                    close=price + Decimal("0.005"),
                    volume=Decimal("1000"),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.unit-v1",
        dataset_hash=dataset_hash,
        source_path=Path("external-kis-index.json"),
        bars=tuple(bars),
    )


def _chunk_key(row_fingerprints: dict[str, str]) -> str:
    return _sha256_payload(
        {
            "backfill_version": "v1",
            "input_cursor": None,
            "row_fingerprints": dict(sorted(row_fingerprints.items())),
            "target_key": "QQQ/NAS/1m",
        }
    )


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _pair_bytes(preparation_dir: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in preparation_dir.iterdir()}


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective observation input must stay offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective observation input must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)
