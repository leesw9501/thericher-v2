"""Materialize one host-only, source-local Norgate daily ETF snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Timeframe
from thericher_v2.data.norgate_daily import (
    NorgateClientUnavailableError,
    NorgateLocalUpdaterUnavailableError,
    NorgateMalformedResponseError,
    NorgateRawDailyBarProvider,
)
from thericher_v2.data.norgate_trial_raw_d1 import (
    NorgateCapitalEventUnavailableError,
    build_norgate_trial_raw_d1_snapshot,
    load_norgate_capital_event_evidence,
)
from thericher_v2.data.provider import BarQuery

_MARKET_DATA_ROOT = Path(r"D:\market_data")
_SNAPSHOT_ROOT = _MARKET_DATA_ROOT / "us_equities" / "norgate_trial" / "local_d1_etf"
_RECEIPT_ROOT = Path(r"D:\thericher-v2\model-artifacts\data\norgate-local-d1-capability-v1")
_SOURCE_SYMBOLS = ("SPY", "QQQ", "IWM")
_RUN_LABEL_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
_SCHEMA_VERSION = 1

_MaterializationStatus = Literal[
    "qualified_for_offline_research",
    "input_unavailable",
    "unqualified",
]
_Reason = Literal[
    "source_client_missing",
    "local_updater_unavailable",
    "malformed_daily_response",
    "capital_event_evidence_unavailable",
    "valid_bounded_response",
]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--start", type=_date_argument, default=date(1990, 1, 1))
    parser.add_argument("--end", type=_date_argument, default=date.today())
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--receipt-root", type=Path, default=_RECEIPT_ROOT)
    arguments = parser.parse_args(argv)
    if arguments.end < arguments.start:
        raise ValueError("Norgate local D1 end date must not precede start date")

    run_label = _validated_run_label(arguments.run_label)
    receipt_root = _validated_receipt_root(arguments.receipt_root, _repository_root())
    destination = arguments.destination or _default_destination(run_label)
    payload = _materialize_payload(
        destination=destination,
        requested_start=arguments.start,
        requested_end=arguments.end,
    )
    receipt_path = receipt_root / f"{run_label}.json"
    receipt_bytes = _canonical_json(payload)
    _write_or_verify(receipt_path, receipt_bytes)
    print(
        json.dumps(
            {
                "receipt_hash": _sha256(receipt_bytes),
                "result": payload,
            },
            sort_keys=True,
        )
    )


def _materialize_payload(
    *,
    destination: Path,
    requested_start: date,
    requested_end: date,
) -> dict[str, object]:
    provider = NorgateRawDailyBarProvider()

    def load_bars(symbol: str, start: date, end: date):
        return provider.get_bars(
            BarQuery(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(start, time(), UTC),
                end_ts=datetime.combine(end + timedelta(days=1), time(), UTC),
            )
        )

    try:
        result = build_norgate_trial_raw_d1_snapshot(
            destination=destination,
            requested_start=requested_start,
            requested_end=requested_end,
            retrieved_at_utc=datetime.now(UTC),
            norgate_bars=load_bars,
            capital_event_evidence=load_norgate_capital_event_evidence,
            norgate_package_version=_client_version(),
            repo_root=_repository_root(),
        )
    except NorgateClientUnavailableError:
        return _source_payload_with_outcome(
            status="input_unavailable",
            reason="source_client_missing",
        )
    except NorgateLocalUpdaterUnavailableError:
        return _source_payload_with_outcome(
            status="input_unavailable",
            reason="local_updater_unavailable",
        )
    except NorgateMalformedResponseError:
        return _source_payload_with_outcome(
            status="unqualified",
            reason="malformed_daily_response",
        )
    except NorgateCapitalEventUnavailableError:
        return _source_payload_with_outcome(
            status="input_unavailable",
            reason="capital_event_evidence_unavailable",
        )

    return {
        "schema_version": _SCHEMA_VERSION,
        "status": "qualified_for_offline_research",
        "reason": "valid_bounded_response",
        "source": _source_payload(),
        "coverage": {
            "common_session_count": result.common_session_count,
            "coverage_bucket": _coverage_bucket(result.common_session_count),
            "row_count": result.row_count,
        },
        "integrity": {
            "dataset_hash": result.dataset_hash,
            "manifest_hash": result.manifest_hash,
            "capital_event_marker_count": result.event_marker_count,
            "capital_event_exclusion_count": result.excluded_session_count,
        },
        "client": {"package": "norgatedata", "version": result.norgate_package_version},
        "raw_market_data_written": True,
        "research_readiness": "source_local_daily_campaign_contract_required",
    }


def _source_payload_with_outcome(
    *,
    status: _MaterializationStatus,
    reason: _Reason,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "source": _source_payload(),
        "raw_market_data_written": False,
        "research_readiness": "source_local_daily_candidate_unavailable",
    }


def _source_payload() -> dict[str, object]:
    return {
        "provider": "norgate_local_trial",
        "interval": "1d",
        "symbol_set": list(_SOURCE_SYMBOLS),
        "field_shape": "ohlcv",
        "requested_adjustment_setting": "NONE",
        "adjustment_semantics_verified": False,
        "capital_event_evidence": "query_scoped_observed_only",
        "availability_time_verified": False,
        "point_in_time_eligible": False,
        "paper_input_eligible": False,
        "promotion_eligible": False,
    }


def _coverage_bucket(session_count: int) -> str:
    if session_count < 1:
        raise ValueError("Norgate local D1 session count is invalid")
    if session_count < 252:
        return "under_252_sessions"
    if session_count < 504:
        return "252_to_503_sessions"
    if session_count < 756:
        return "504_to_755_sessions"
    return "756_or_more_sessions"


def _client_version() -> str:
    try:
        return version("norgatedata")
    except PackageNotFoundError as exc:
        raise NorgateClientUnavailableError(
            "Norgate Python client is unavailable; use the host-only norgate-host extra"
        ) from exc


def _default_destination(run_label: str) -> Path:
    return _SNAPSHOT_ROOT / f"snapshot={run_label}-norgate-trial-raw-d1-r2"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _validated_run_label(value: str) -> str:
    label = value.strip().lower()
    if not _RUN_LABEL_PATTERN.fullmatch(label):
        raise ValueError("Norgate local D1 run label is invalid")
    return label


def _validated_receipt_root(root: Path, repository: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_repository = repository.resolve(strict=False)
    if resolved_root.is_relative_to(resolved_repository):
        raise ValueError("Norgate local D1 receipts must stay outside Git")
    if resolved_root.exists() and (resolved_root.is_symlink() or not resolved_root.is_dir()):
        raise ValueError("Norgate local D1 receipt root is invalid")
    resolved_root.mkdir(parents=True, exist_ok=True)
    return resolved_root.resolve(strict=False)


def _write_or_verify(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError("Norgate local D1 receipt conflicts with existing evidence")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        stage.write_bytes(content)
        os.replace(stage, path)
    finally:
        if stage.exists():
            stage.unlink()


def _canonical_json(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    main()
