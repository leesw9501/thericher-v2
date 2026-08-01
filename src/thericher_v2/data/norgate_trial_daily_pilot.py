"""Small, date-indexed local Norgate D1 pilot with a pure ``Bar`` loader.

The pilot is intentionally narrow: three frozen source cases, local Windows
Norgate only, raw rows retained outside Git, and a read-only in-process loader.
It proves that the requested fields can be kept aligned by source date.  It
does not establish point-in-time availability, adjustment semantics, a model,
or any broker/Paper behavior.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib
import io
import json
import os
import shutil
import sys
import uuid
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from thericher_v2.contracts import Bar, Timeframe

from .norgate_trial_daily_capability_probe import (
    DEFAULT_NORGATE_TRIAL_DAILY_PROBE_CASES,
    NorgateTrialDailyCapabilityProbeResult,
    NorgateTrialDailyProbeCase,
    require_attested_norgate_trial_daily_capability_probe,
)

DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_NORGATE_TRIAL_DAILY_PILOT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT / "us_equities" / "norgate_trial" / "daily_pilot"
)
NORGATE_TRIAL_DAILY_PILOT_ID = "norgate-trial-daily-pilot-v1"
NORGATE_TRIAL_DAILY_PILOT_VERSION = "norgate-trial-daily-pilot-r2"
NORGATE_TRIAL_DAILY_NAMESPACE = "norgate_trial_daily_offline_research_only"
NORGATE_SP500_INDEX = "S&P 500"

_PRECOMMIT_FILE = "precommit.json"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_BARS_FILE = "d1_bars.csv.gz"
_MEMBERSHIP_FILE = "membership.csv.gz"
_LISTING_FILE = "listing.csv.gz"
_SNAPSHOT_SUFFIX = "-norgate-trial-daily-pilot-r2"
_VALID_STATUSES = ("qualified_for_offline_research", "unqualified", "input_unavailable")
_BARS_COLUMNS = ("role", "symbol", "date", "open", "high", "low", "close", "volume")
_MEMBERSHIP_COLUMNS = ("role", "symbol", "date", "index_constituent")
_LISTING_COLUMNS = ("role", "symbol", "date", "major_exchange_listed")
_REQUIRED_PRICE_FIELDS = ("Date", "Open", "High", "Low", "Close", "Volume")
_REQUIRED_MEMBERSHIP_FIELDS = ("Date", "Index Constituent")
_REQUIRED_LISTING_FIELDS = ("Date", "Major Exchange Listed")
_PILOT_ATTESTATION = object()
_LOADER_ATTESTATION = object()


class NorgateTrialDailyPilotError(ValueError):
    """Raised when the bounded external pilot is malformed or unsafe to use."""


class _NorgateSourceUnavailable(RuntimeError):
    """A local Norgate runtime or source call could not serve this pilot."""


class _NorgateSourceContractError(ValueError):
    """A source response cannot satisfy the pilot's explicit field contract."""


class _NorgateCaseContractError(_NorgateSourceContractError):
    """A source-contract failure tied to one fixed pilot case."""

    def __init__(
        self,
        case: NorgateTrialDailyProbeCase,
        reason: str,
        *,
        aggregate: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(reason)
        self.case = case
        self.reason = reason
        self.aggregate = dict(aggregate or {})

    def safe_payload(self) -> dict[str, object]:
        return {
            "role": self.case.role,
            "symbol": self.case.symbol,
            "status": "unqualified",
            "reason": self.reason,
            "aggregate": self.aggregate,
        }


@dataclass(frozen=True, slots=True, init=False)
class NorgateTrialDailyPilotResult:
    """Non-secret identity and scope facts from one immutable local pilot."""

    pilot_dir: Path
    manifest_hash: str
    precommit_hash: str
    status: str
    package_version: str
    database_build_metadata_sha256: str
    capability_receipt_hash: str
    source_namespace: str
    limitations: tuple[str, ...]
    scope: Mapping[str, bool]
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified Norgate trial daily-pilot builder")

    def safe_payload(self) -> dict[str, object]:
        """Return source-safe facts for logs and stateboards only."""

        require_attested_norgate_trial_daily_pilot(self)
        return {
            "pilot_dir": str(self.pilot_dir),
            "manifest_hash": self.manifest_hash,
            "precommit_hash": self.precommit_hash,
            "status": self.status,
            "package_version": self.package_version,
            "database_build_metadata_sha256": self.database_build_metadata_sha256,
            "capability_receipt_hash": self.capability_receipt_hash,
            "source_namespace": self.source_namespace,
            "limitations": list(self.limitations),
            "scope": dict(self.scope),
        }


@dataclass(frozen=True, slots=True)
class NorgateTrialDailyMembershipState:
    """One source-date-aligned state accompanying a completed daily bar."""

    symbol: str
    source_date: date
    index_constituent: bool
    major_exchange_listed: bool


@dataclass(frozen=True, slots=True, init=False)
class NorgateTrialDailyPilotBars:
    """Pure, verified completed-D1 bars plus exact source-date state lookup."""

    pilot: NorgateTrialDailyPilotResult
    bars: tuple[Bar, ...]
    _states: Mapping[tuple[str, date], NorgateTrialDailyMembershipState]
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the attested Norgate trial daily-pilot loader")

    def bars_for_symbol(self, symbol: str) -> tuple[Bar, ...]:
        """Return the completed D1 bars for one frozen pilot symbol."""

        normalized = _symbol(symbol)
        result = tuple(bar for bar in self.bars if bar.symbol == normalized)
        if not result:
            raise ValueError("Norgate pilot symbol is unavailable")
        return result

    def membership_state_at(
        self, symbol: str, source_date: date
    ) -> NorgateTrialDailyMembershipState:
        """Return the state attached to that exact source date; never backfill it."""

        if isinstance(source_date, datetime) or not isinstance(source_date, date):
            raise ValueError("Norgate pilot source date must be a date")
        try:
            return self._states[(_symbol(symbol), source_date)]
        except KeyError as exc:
            raise ValueError("Norgate pilot source-date state is unavailable") from exc


@dataclass(frozen=True, slots=True)
class _RawBar:
    role: str
    symbol: str
    session_date: date
    open: str
    high: str
    low: str
    close: str
    volume: str


@dataclass(frozen=True, slots=True)
class _RawState:
    role: str
    symbol: str
    session_date: date
    value: bool


@dataclass(frozen=True, slots=True)
class _MaterializedPilot:
    bars: tuple[_RawBar, ...]
    membership: tuple[_RawState, ...]
    listing: tuple[_RawState, ...]
    coverage: tuple[dict[str, object], ...]
    package_version: str


ClientLoader = Callable[[], Any]


def default_norgate_trial_daily_pilot_dir(run_label: str) -> Path:
    """Return one immutable external destination for a pilot invocation."""

    return DEFAULT_NORGATE_TRIAL_DAILY_PILOT_ROOT / (
        f"pilot={_safe_run_label(run_label)}{_SNAPSHOT_SUFFIX}"
    )


def build_norgate_trial_daily_pilot(
    *,
    destination: Path,
    retrieved_at_utc: datetime,
    capability_probe: NorgateTrialDailyCapabilityProbeResult,
    database_build_metadata_sha256: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    cases: tuple[NorgateTrialDailyProbeCase, ...] = DEFAULT_NORGATE_TRIAL_DAILY_PROBE_CASES,
    client_loader: ClientLoader | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTrialDailyPilotResult:
    """Materialize a small raw D1 pilot after persisting its immutable precommit.

    The source client is loaded only after the precommit and retention marker
    exist in a staging directory.  Source problems create a source-safe
    ``unqualified`` or ``input_unavailable`` external manifest, not a fallback.
    """

    probe = require_attested_norgate_trial_daily_capability_probe(capability_probe)
    if probe.status != "qualified_for_offline_research":
        raise ValueError("Norgate daily pilot requires a qualified capability receipt")
    retrieved_at = _utc_datetime(retrieved_at_utc, "Norgate daily pilot retrieval time")
    normalized_cases = _validate_cases(cases)
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_storage(root, disk_usage=disk_usage)
    build_hash = _sha256_value(database_build_metadata_sha256, "database build metadata hash")
    if build_hash != probe.database_build_metadata_sha256:
        raise ValueError("Norgate daily pilot database build differs from its capability receipt")
    if platform_name != "win32":
        raise NorgateTrialDailyPilotError("Norgate daily pilot requires Windows")

    precommit = _precommit_document(
        target=target,
        cases=normalized_cases,
        retrieved_at=retrieved_at,
        capability_probe=probe,
        database_build_metadata_sha256=build_hash,
    )
    precommit_bytes = _json_bytes(precommit)
    retention_bytes = _retention_marker_bytes()
    staging = _create_staging_directory(target)
    try:
        (staging / _PRECOMMIT_FILE).write_bytes(precommit_bytes)
        (staging / _RETENTION_FILE).write_bytes(retention_bytes)
        status, materialized, reasons, case_outcomes = _collect_or_classify(
            normalized_cases,
            client_loader=client_loader or _load_norgatedata,
        )
        files: dict[str, dict[str, object]] = {}
        if materialized is not None:
            for key, filename, payload, row_count in (
                (
                    "d1_bars",
                    _BARS_FILE,
                    _gzip_bytes(_bars_csv_bytes(materialized.bars)),
                    len(materialized.bars),
                ),
                (
                    "membership",
                    _MEMBERSHIP_FILE,
                    _gzip_bytes(_states_csv_bytes(materialized.membership, _MEMBERSHIP_COLUMNS)),
                    len(materialized.membership),
                ),
                (
                    "listing",
                    _LISTING_FILE,
                    _gzip_bytes(_states_csv_bytes(materialized.listing, _LISTING_COLUMNS)),
                    len(materialized.listing),
                ),
            ):
                (staging / filename).write_bytes(payload)
                files[key] = {
                    "name": filename,
                    "sha256": _sha256(payload),
                    "size_bytes": len(payload),
                    "row_count": row_count,
                }
        package_version = (
            materialized.package_version if materialized is not None else "unavailable"
        )
        manifest = _manifest_document(
            target=target,
            retrieved_at=retrieved_at,
            status=status,
            package_version=package_version,
            database_build_metadata_sha256=build_hash,
            capability_probe=probe,
            precommit_hash=_sha256(precommit_bytes),
            files=files,
            coverage=materialized.coverage if materialized is not None else (),
            case_outcomes=case_outcomes,
            reasons=reasons,
        )
        (staging / _MANIFEST_FILE).write_bytes(_json_bytes(manifest))
        os.rename(staging, target)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return verify_norgate_trial_daily_pilot(
        target,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def verify_norgate_trial_daily_pilot(
    pilot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateTrialDailyPilotResult:
    """Reattest the external pilot without importing Norgate or touching a network."""

    directory, _root = _validate_existing_pilot_dir(
        pilot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    precommit_bytes = _read_regular_file(directory / _PRECOMMIT_FILE)
    manifest_bytes = _read_regular_file(directory / _MANIFEST_FILE)
    if _read_regular_file(directory / _RETENTION_FILE) != _retention_marker_bytes():
        raise NorgateTrialDailyPilotError("Norgate daily pilot retention marker is invalid")
    precommit = _json_object(precommit_bytes, "precommit")
    manifest = _json_object(manifest_bytes, "manifest")
    _validate_precommit(precommit, directory)
    _validate_manifest(manifest, directory, precommit_hash=_sha256(precommit_bytes))
    status = manifest["status"]
    assert isinstance(status, str)
    if status == "qualified_for_offline_research":
        _load_payload_from_manifest(directory, manifest)
    expected_names = {_PRECOMMIT_FILE, _MANIFEST_FILE, _RETENTION_FILE}
    if status == "qualified_for_offline_research":
        expected_names |= {_BARS_FILE, _MEMBERSHIP_FILE, _LISTING_FILE}
    if {path.name for path in directory.iterdir()} != expected_names:
        raise NorgateTrialDailyPilotError("Norgate daily pilot files are invalid")
    result = object.__new__(NorgateTrialDailyPilotResult)
    source = manifest["source"]
    scope = manifest["scope"]
    assert isinstance(source, dict)
    assert isinstance(scope, dict)
    object.__setattr__(result, "pilot_dir", directory)
    object.__setattr__(result, "manifest_hash", _sha256(manifest_bytes))
    object.__setattr__(result, "precommit_hash", _sha256(precommit_bytes))
    object.__setattr__(result, "status", status)
    object.__setattr__(result, "package_version", source["package_version"])
    object.__setattr__(
        result,
        "database_build_metadata_sha256",
        source["database_build_metadata_sha256"],
    )
    object.__setattr__(result, "capability_receipt_hash", source["capability_receipt_sha256"])
    object.__setattr__(result, "source_namespace", source["namespace"])
    object.__setattr__(result, "limitations", tuple(manifest["limitations"]))
    object.__setattr__(result, "scope", MappingProxyType(dict(scope)))
    object.__setattr__(result, "_attestation", _PILOT_ATTESTATION)
    return result


def require_attested_norgate_trial_daily_pilot(
    value: object,
) -> NorgateTrialDailyPilotResult:
    """Reject forged, widened, or unqualified pilot references."""

    if (
        not isinstance(value, NorgateTrialDailyPilotResult)
        or getattr(value, "_attestation", None) is not _PILOT_ATTESTATION
        or getattr(value, "status", None) not in _VALID_STATUSES
        or getattr(value, "source_namespace", None) != NORGATE_TRIAL_DAILY_NAMESPACE
        or not isinstance(getattr(value, "manifest_hash", None), str)
        or not isinstance(getattr(value, "scope", None), Mapping)
        or dict(value.scope) != _scope()
    ):
        raise ValueError("Norgate daily pilot requires verified attestation")
    return value


def load_attested_norgate_trial_daily_pilot_bars(
    pilot: NorgateTrialDailyPilotResult,
) -> NorgateTrialDailyPilotBars:
    """Load only hash-attested raw rows as completed D1 bars and exact states."""

    verified = require_attested_norgate_trial_daily_pilot(pilot)
    if verified.status != "qualified_for_offline_research":
        raise ValueError("Norgate daily pilot source is not qualified for offline research")
    manifest = _json_object(
        _read_regular_file(verified.pilot_dir / _MANIFEST_FILE), "manifest"
    )
    bars, states = _load_payload_from_manifest(verified.pilot_dir, manifest)
    loaded = object.__new__(NorgateTrialDailyPilotBars)
    object.__setattr__(loaded, "pilot", verified)
    object.__setattr__(loaded, "bars", bars)
    object.__setattr__(loaded, "_states", MappingProxyType(states))
    object.__setattr__(loaded, "_attestation", _LOADER_ATTESTATION)
    return loaded


def require_attested_norgate_trial_daily_pilot_bars(
    value: object,
) -> NorgateTrialDailyPilotBars:
    """Ensure a consumer received the pure, verified pilot loader output."""

    if (
        not isinstance(value, NorgateTrialDailyPilotBars)
        or getattr(value, "_attestation", None) is not _LOADER_ATTESTATION
    ):
        raise ValueError("Norgate daily pilot bars require verified attestation")
    require_attested_norgate_trial_daily_pilot(value.pilot)
    return value


def _load_norgatedata() -> Any:
    return importlib.import_module("norgatedata")


def _collect_or_classify(
    cases: tuple[NorgateTrialDailyProbeCase, ...], *, client_loader: ClientLoader
) -> tuple[str, _MaterializedPilot | None, tuple[str, ...], tuple[dict[str, object], ...]]:
    try:
        client = _load_client(client_loader)
    except _NorgateSourceUnavailable:
        return "input_unavailable", None, ("source_client_unavailable",), ()
    try:
        materialized = _materialize_cases(client, cases)
        return (
            "qualified_for_offline_research",
            materialized,
            ("field_alignment_attested",),
            tuple(
                {
                    "role": item["role"],
                    "symbol": item["symbol"],
                    "status": "qualified",
                    "reason": "field_alignment_attested",
                }
                for item in materialized.coverage
            ),
        )
    except _NorgateSourceUnavailable:
        return "input_unavailable", None, ("source_call_unavailable",), ()
    except _NorgateCaseContractError as exc:
        return "unqualified", None, (exc.reason,), (exc.safe_payload(),)
    except _NorgateSourceContractError as exc:
        return "unqualified", None, (str(exc),), ()


def _load_client(client_loader: ClientLoader) -> Any:
    try:
        client = client_loader()
        _ = client.PaddingType.NONE
        _ = client.StockPriceAdjustmentType.NONE
        _ = client.price_timeseries
        _ = client.index_constituent_timeseries
        _ = client.major_exchange_listed_timeseries
    except Exception as exc:
        raise _NorgateSourceUnavailable() from exc
    return client


def _materialize_cases(
    client: Any, cases: tuple[NorgateTrialDailyProbeCase, ...]
) -> _MaterializedPilot:
    bars: list[_RawBar] = []
    membership: list[_RawState] = []
    listing: list[_RawState] = []
    coverage: list[dict[str, object]] = []
    for case in cases:
        try:
            raw_bars = _price_rows(client, case)
            raw_membership = _state_rows(
                client,
                case,
                method_name="index_constituent_timeseries",
                value_field="Index Constituent",
            )
            raw_listing = _state_rows(
                client,
                case,
                method_name="major_exchange_listed_timeseries",
                value_field="Major Exchange Listed",
            )
        except _NorgateSourceContractError as exc:
            raise _NorgateCaseContractError(case, str(exc)) from exc
        bar_dates = tuple(row.session_date for row in raw_bars)
        membership_dates = tuple(row.session_date for row in raw_membership)
        listing_dates = tuple(row.session_date for row in raw_listing)
        if bar_dates != membership_dates or bar_dates != listing_dates:
            raise _NorgateCaseContractError(
                case,
                "source_date_alignment_unavailable",
                aggregate={
                    "d1_bar_count": len(bar_dates),
                    "membership_row_count": len(membership_dates),
                    "listing_row_count": len(listing_dates),
                    "first_divergent_date": _first_divergent_date(
                        bar_dates,
                        membership_dates,
                        listing_dates,
                    ),
                },
            )
        bars.extend(raw_bars)
        membership.extend(raw_membership)
        listing.extend(raw_listing)
        coverage.append(
            {
                "role": case.role,
                "symbol": case.symbol,
                "requested_window": {
                    "start": case.requested_start.isoformat(),
                    "end": case.requested_end.isoformat(),
                },
                "d1_bar_count": len(raw_bars),
                "membership": _state_summary(raw_membership),
                "major_exchange_listing": _state_summary(raw_listing),
            }
        )
    return _MaterializedPilot(
        bars=tuple(bars),
        membership=tuple(membership),
        listing=tuple(listing),
        coverage=tuple(coverage),
        package_version=_package_version(client),
    )


def _price_rows(client: Any, case: NorgateTrialDailyProbeCase) -> tuple[_RawBar, ...]:
    response = _call_source(
        client.price_timeseries,
        case.symbol,
        stock_price_adjustment_setting=client.StockPriceAdjustmentType.NONE,
        padding_setting=client.PaddingType.NONE,
        start_date=case.requested_start.isoformat(),
        end_date=case.requested_end.isoformat(),
        limit=-1,
        timeseriesformat="numpy-recarray",
        interval="D",
    )
    rows = _validated_rows(response, required_fields=_REQUIRED_PRICE_FIELDS, case=case)
    parsed: list[_RawBar] = []
    for row in rows:
        session_date = _session_date(_row_value(row, "Date"))
        values = {
            field.lower(): _number_text(_row_value(row, field))
            for field in ("Open", "High", "Low", "Close", "Volume")
        }
        try:
            Bar(
                symbol=case.symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(session_date, datetime.min.time(), UTC),
                open=values["open"],
                high=values["high"],
                low=values["low"],
                close=values["close"],
                volume=values["volume"],
            )
        except (ArithmeticError, ValueError) as exc:
            raise _NorgateSourceContractError("unadjusted_d1_values_invalid") from exc
        parsed.append(
            _RawBar(
                role=case.role,
                symbol=case.symbol,
                session_date=session_date,
                open=values["open"],
                high=values["high"],
                low=values["low"],
                close=values["close"],
                volume=values["volume"],
            )
        )
    return tuple(parsed)


def _state_rows(
    client: Any,
    case: NorgateTrialDailyProbeCase,
    *,
    method_name: str,
    value_field: str,
) -> tuple[_RawState, ...]:
    response = _call_source(
        getattr(client, method_name),
        case.symbol,
        *( (NORGATE_SP500_INDEX,) if method_name == "index_constituent_timeseries" else () ),
        padding_setting=client.PaddingType.NONE,
        start_date=case.requested_start.isoformat(),
        end_date=case.requested_end.isoformat(),
        limit=-1,
        timeseriesformat="numpy-recarray",
    )
    fields = (
        _REQUIRED_MEMBERSHIP_FIELDS
        if method_name == "index_constituent_timeseries"
        else _REQUIRED_LISTING_FIELDS
    )
    rows = _validated_rows(response, required_fields=fields, case=case)
    return tuple(
        _RawState(
            role=case.role,
            symbol=case.symbol,
            session_date=_session_date(_row_value(row, "Date")),
            value=_flag(_row_value(row, value_field)),
        )
        for row in rows
    )


def _call_source(call: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    try:
        return call(*args, **kwargs)
    except Exception as exc:
        raise _NorgateSourceUnavailable() from exc


def _validated_rows(
    response: Any, *, required_fields: tuple[str, ...], case: NorgateTrialDailyProbeCase
) -> tuple[Any, ...]:
    fields = tuple(getattr(getattr(response, "dtype", None), "names", ()) or ())
    if not fields or any(field not in fields for field in required_fields):
        raise _NorgateSourceContractError("required_source_fields_unavailable")
    try:
        source_rows = tuple(response)
    except TypeError as exc:
        raise _NorgateSourceContractError("source_series_unreadable") from exc
    if not source_rows:
        raise _NorgateSourceContractError("required_source_series_empty")
    previous: date | None = None
    for row in source_rows:
        session_date = _session_date(_row_value(row, "Date"))
        if not case.requested_start <= session_date <= case.requested_end:
            raise _NorgateSourceContractError("source_series_outside_requested_window")
        if previous is not None and session_date <= previous:
            raise _NorgateSourceContractError("source_series_not_strictly_ordered")
        previous = session_date
    return source_rows


def _state_summary(rows: tuple[_RawState, ...]) -> dict[str, object]:
    values = tuple(row.value for row in rows)
    return {
        "row_count": len(rows),
        "start": rows[0].session_date.isoformat(),
        "end": rows[-1].session_date.isoformat(),
        "true_count": sum(values),
        "false_count": len(values) - sum(values),
        "transition_count": sum(
            prior != current for prior, current in zip(values, values[1:], strict=False)
        ),
        "latest_value": values[-1],
    }


def _first_divergent_date(*date_sequences: tuple[date, ...]) -> str | None:
    all_dates = sorted({value for sequence in date_sequences for value in sequence})
    for session_date in all_dates:
        if any(session_date not in sequence for sequence in date_sequences):
            return session_date.isoformat()
    return None


def _precommit_document(
    *,
    target: Path,
    cases: tuple[NorgateTrialDailyProbeCase, ...],
    retrieved_at: datetime,
    capability_probe: NorgateTrialDailyCapabilityProbeResult,
    database_build_metadata_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "norgate_trial_daily_pilot_precommit",
        "pilot_id": NORGATE_TRIAL_DAILY_PILOT_ID,
        "pilot_version": NORGATE_TRIAL_DAILY_PILOT_VERSION,
        "destination": str(target),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "capability_receipt_sha256": capability_probe.receipt_hash,
        "provider": {
            "name": "norgatedata",
            "access": "local_windows_host_only",
            "database_build_metadata_sha256": database_build_metadata_sha256,
        },
        "queries": [
            {
                "role": case.role,
                "symbol": case.symbol,
                "start": case.requested_start.isoformat(),
                "end": case.requested_end.isoformat(),
                "identity_scope": "provider_ticker_string_only",
                "price_fields": list(_REQUIRED_PRICE_FIELDS),
                "membership_fields": list(_REQUIRED_MEMBERSHIP_FIELDS),
                "listing_fields": list(_REQUIRED_LISTING_FIELDS),
            }
            for case in cases
        ],
        "scope": _scope(),
        "constraints": _constraints(),
    }


def _manifest_document(
    *,
    target: Path,
    retrieved_at: datetime,
    status: str,
    package_version: str,
    database_build_metadata_sha256: str,
    capability_probe: NorgateTrialDailyCapabilityProbeResult,
    precommit_hash: str,
    files: dict[str, dict[str, object]],
    coverage: tuple[dict[str, object], ...],
    case_outcomes: tuple[dict[str, object], ...],
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "norgate_trial_daily_pilot_manifest",
        "pilot_id": NORGATE_TRIAL_DAILY_PILOT_ID,
        "pilot_version": NORGATE_TRIAL_DAILY_PILOT_VERSION,
        "pilot_dir": str(target),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "status": status,
        "precommit_sha256": precommit_hash,
        "source": {
            "provider": "norgatedata",
            "package_version": package_version,
            "database_build_metadata_sha256": database_build_metadata_sha256,
            "capability_receipt_sha256": capability_probe.receipt_hash,
            "namespace": NORGATE_TRIAL_DAILY_NAMESPACE,
        },
        "scope": _scope(),
        "constraints": _constraints(),
        "files": files,
        "case_coverage": list(coverage),
        "case_outcomes": list(case_outcomes),
        "qualification_reasons": list(reasons),
        "limitations": [
            "Norgate trial data remains host-local and non-redistributable.",
            "Date-indexed membership and listing values can be restated; their availability "
            "time is unknown.",
            "Rows are keyed by provider ticker strings; historical ticker-to-entity identity "
            "is not established.",
            "Requested unadjusted setting is not proof of adjustment semantics.",
            "Corporate-action completeness and timing are unknown and not materialized "
            "by this pilot.",
            "This pilot is offline-research-only and cannot create a model, ranking, "
            "GPU, PnL, KIS, broker, or Paper input.",
        ],
        "recovery_fact": _recovery_fact(status),
    }


def _validate_precommit(document: dict[str, object], directory: Path) -> None:
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "norgate_trial_daily_pilot_precommit"
        or document.get("pilot_id") != NORGATE_TRIAL_DAILY_PILOT_ID
        or document.get("pilot_version") != NORGATE_TRIAL_DAILY_PILOT_VERSION
        or document.get("destination") != str(directory)
        or document.get("scope") != _scope()
        or document.get("constraints") != _constraints()
        or not _is_sha256(document.get("capability_receipt_sha256"))
    ):
        raise NorgateTrialDailyPilotError("Norgate daily pilot precommit is invalid")
    queries = document.get("queries")
    if not isinstance(queries, list) or len(queries) != 3:
        raise NorgateTrialDailyPilotError("Norgate daily pilot precommit queries are invalid")


def _validate_manifest(
    document: dict[str, object], directory: Path, *, precommit_hash: str
) -> None:
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "norgate_trial_daily_pilot_manifest"
        or document.get("pilot_id") != NORGATE_TRIAL_DAILY_PILOT_ID
        or document.get("pilot_version") != NORGATE_TRIAL_DAILY_PILOT_VERSION
        or document.get("pilot_dir") != str(directory)
        or document.get("status") not in _VALID_STATUSES
        or document.get("precommit_sha256") != precommit_hash
        or document.get("scope") != _scope()
        or document.get("constraints") != _constraints()
    ):
        raise NorgateTrialDailyPilotError("Norgate daily pilot manifest is invalid")
    source = document.get("source")
    limitations = document.get("limitations")
    files = document.get("files")
    coverage = document.get("case_coverage")
    case_outcomes = document.get("case_outcomes")
    if (
        not isinstance(source, dict)
        or source.get("provider") != "norgatedata"
        or source.get("namespace") != NORGATE_TRIAL_DAILY_NAMESPACE
        or not isinstance(source.get("package_version"), str)
        or not _is_sha256(source.get("database_build_metadata_sha256"))
        or not _is_sha256(source.get("capability_receipt_sha256"))
        or not isinstance(limitations, list)
        or not all(isinstance(item, str) and item for item in limitations)
        or not isinstance(files, dict)
        or not isinstance(coverage, list)
        or not isinstance(case_outcomes, list)
    ):
        raise NorgateTrialDailyPilotError("Norgate daily pilot manifest is invalid")
    status = document["status"]
    assert isinstance(status, str)
    if status == "qualified_for_offline_research":
        if (
            set(files) != {"d1_bars", "membership", "listing"}
            or len(coverage) != 3
            or len(case_outcomes) != 3
        ):
            raise NorgateTrialDailyPilotError("Norgate daily pilot raw payload is invalid")
        for key, expected_name in (
            ("d1_bars", _BARS_FILE),
            ("membership", _MEMBERSHIP_FILE),
            ("listing", _LISTING_FILE),
        ):
            _file_metadata(files.get(key), expected_name)
    elif files or coverage:
        raise NorgateTrialDailyPilotError("unqualified Norgate pilot must not retain raw rows")


def _load_payload_from_manifest(
    directory: Path, manifest: dict[str, object]
) -> tuple[tuple[Bar, ...], dict[tuple[str, date], NorgateTrialDailyMembershipState]]:
    files = manifest.get("files")
    coverage = manifest.get("case_coverage")
    if not isinstance(files, dict) or not isinstance(coverage, list):
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw payload is invalid")
    bar_rows = _read_csv_payload(directory, files.get("d1_bars"), _BARS_FILE, _BARS_COLUMNS)
    membership_rows = _read_csv_payload(
        directory, files.get("membership"), _MEMBERSHIP_FILE, _MEMBERSHIP_COLUMNS
    )
    listing_rows = _read_csv_payload(
        directory, files.get("listing"), _LISTING_FILE, _LISTING_COLUMNS
    )
    bars: dict[tuple[str, date], Bar] = {}
    identities: dict[str, str] = {}
    for row in bar_rows:
        role, symbol, session_date = _raw_identity(row)
        key = (symbol, session_date)
        if key in bars:
            raise NorgateTrialDailyPilotError("Norgate daily pilot has duplicate bars")
        try:
            bars[key] = Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(session_date, datetime.min.time(), UTC),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
        except (KeyError, ArithmeticError, ValueError) as exc:
            raise NorgateTrialDailyPilotError("Norgate daily pilot bar is invalid") from exc
        existing = identities.setdefault(symbol, role)
        if existing != role:
            raise NorgateTrialDailyPilotError("Norgate daily pilot symbol role is inconsistent")
    membership = _state_mapping(membership_rows, expected_column="index_constituent")
    listing = _state_mapping(listing_rows, expected_column="major_exchange_listed")
    if not bars or set(bars) != set(membership) or set(bars) != set(listing):
        raise NorgateTrialDailyPilotError("Norgate daily pilot source dates are misaligned")
    states: dict[tuple[str, date], NorgateTrialDailyMembershipState] = {}
    for key in sorted(bars, key=lambda item: (item[0], item[1])):
        symbol, session_date = key
        role = identities[symbol]
        membership_role, membership_value = membership[key]
        listing_role, listing_value = listing[key]
        if membership_role != role or listing_role != role:
            raise NorgateTrialDailyPilotError("Norgate daily pilot state identity is inconsistent")
        states[key] = NorgateTrialDailyMembershipState(
            symbol=symbol,
            source_date=session_date,
            index_constituent=membership_value,
            major_exchange_listed=listing_value,
        )
    _validate_coverage(coverage, bars=bars, states=states, identities=identities)
    ordered_bars = tuple(bars[key] for key in sorted(bars, key=lambda item: (item[0], item[1])))
    return ordered_bars, states


def _state_mapping(
    rows: list[dict[str, str]], *, expected_column: str
) -> dict[tuple[str, date], tuple[str, bool]]:
    result: dict[tuple[str, date], tuple[str, bool]] = {}
    for row in rows:
        role, symbol, session_date = _raw_identity(row)
        try:
            value = _flag(row[expected_column])
        except (KeyError, ValueError) as exc:
            raise NorgateTrialDailyPilotError("Norgate daily pilot state is invalid") from exc
        key = (symbol, session_date)
        if key in result:
            raise NorgateTrialDailyPilotError("Norgate daily pilot has duplicate source state")
        result[key] = (role, value)
    return result


def _validate_coverage(
    coverage: list[object],
    *,
    bars: Mapping[tuple[str, date], Bar],
    states: Mapping[tuple[str, date], NorgateTrialDailyMembershipState],
    identities: Mapping[str, str],
) -> None:
    if len(coverage) != len(identities):
        raise NorgateTrialDailyPilotError("Norgate daily pilot coverage is invalid")
    seen: set[str] = set()
    for item in coverage:
        if not isinstance(item, dict):
            raise NorgateTrialDailyPilotError("Norgate daily pilot coverage is invalid")
        symbol = _symbol(item.get("symbol"))
        role = item.get("role")
        if not isinstance(role, str):
            raise NorgateTrialDailyPilotError("Norgate daily pilot coverage is invalid")
        expected = identities.get(symbol)
        if expected is None or expected != role:
            raise NorgateTrialDailyPilotError("Norgate daily pilot coverage identity is invalid")
        matching = [key for key in bars if key[0] == symbol]
        if item.get("d1_bar_count") != len(matching) or not matching:
            raise NorgateTrialDailyPilotError("Norgate daily pilot coverage count is invalid")
        membership_values = [states[key].index_constituent for key in sorted(matching)]
        listing_values = [states[key].major_exchange_listed for key in sorted(matching)]
        _validate_state_summary(item.get("membership"), membership_values)
        _validate_state_summary(item.get("major_exchange_listing"), listing_values)
        seen.add(symbol)
    if seen != set(identities):
        raise NorgateTrialDailyPilotError("Norgate daily pilot coverage is incomplete")


def _validate_state_summary(value: object, states: list[bool]) -> None:
    if not isinstance(value, dict) or value.get("row_count") != len(states):
        raise NorgateTrialDailyPilotError("Norgate daily pilot state coverage is invalid")
    if (
        value.get("true_count") != sum(states)
        or value.get("false_count") != len(states) - sum(states)
    ):
        raise NorgateTrialDailyPilotError("Norgate daily pilot state coverage is invalid")
    transitions = sum(prior != current for prior, current in zip(states, states[1:], strict=False))
    if value.get("transition_count") != transitions or value.get("latest_value") != states[-1]:
        raise NorgateTrialDailyPilotError("Norgate daily pilot state coverage is invalid")


def _read_csv_payload(
    directory: Path, metadata: object, expected_name: str, columns: tuple[str, ...]
) -> list[dict[str, str]]:
    details = _file_metadata(metadata, expected_name)
    payload = _read_payload_file(directory, metadata, expected_name)
    try:
        decoded = gzip.decompress(payload).decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        fieldnames = tuple(reader.fieldnames or ())
        rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw CSV is invalid") from exc
    if fieldnames != columns or not rows or len(rows) != details["row_count"]:
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw CSV is invalid")
    if any(
        set(row) != set(columns) or any(value is None for value in row.values())
        for row in rows
    ):
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw CSV is invalid")
    return rows


def _read_payload_file(directory: Path, metadata: object, expected_name: str) -> bytes:
    details = _file_metadata(metadata, expected_name)
    payload = _read_regular_file(directory / expected_name)
    if details["size_bytes"] != len(payload) or details["sha256"] != _sha256(payload):
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw payload hash mismatch")
    return payload


def _file_metadata(value: object, expected_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise NorgateTrialDailyPilotError("Norgate daily pilot file metadata is invalid")
    if (
        value.get("name") != expected_name
        or not _is_sha256(value.get("sha256"))
        or not isinstance(value.get("size_bytes"), int)
        or value["size_bytes"] <= 0
        or not isinstance(value.get("row_count"), int)
        or value["row_count"] <= 0
    ):
        raise NorgateTrialDailyPilotError("Norgate daily pilot file metadata is invalid")
    return value


def _raw_identity(row: Mapping[str, str]) -> tuple[str, str, date]:
    try:
        role = row["role"]
        symbol = _symbol(row["symbol"])
        session_date = date.fromisoformat(row["date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw identity is invalid") from exc
    if not role:
        raise NorgateTrialDailyPilotError("Norgate daily pilot raw identity is invalid")
    return role, symbol, session_date


def _bars_csv_bytes(rows: tuple[_RawBar, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_BARS_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "role": row.role,
                "symbol": row.symbol,
                "date": row.session_date.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
        )
    return stream.getvalue().encode("utf-8")


def _states_csv_bytes(rows: tuple[_RawState, ...], columns: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    state_column = columns[-1]
    for row in rows:
        writer.writerow(
            {
                "role": row.role,
                "symbol": row.symbol,
                "date": row.session_date.isoformat(),
                state_column: "true" if row.value else "false",
            }
        )
    return stream.getvalue().encode("utf-8")


def _scope() -> dict[str, bool]:
    return {
        "offline_research_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "model_eligible": False,
        "gpu_eligible": False,
        "paper_trading_eligible": False,
        "pnl_eligible": False,
        "live_eligible": False,
    }


def _constraints() -> dict[str, bool]:
    return {
        "network_used": False,
        "credential_access_used": False,
        "kis_used": False,
        "broker_used": False,
        "docker_provider_used": False,
        "model_result_created": False,
        "gpu_used": False,
    }


def _recovery_fact(status: str) -> str:
    if status == "qualified_for_offline_research":
        return (
            "freeze a distinct campaign only after independently resolving availability "
            "and adjustment assumptions"
        )
    if status == "unqualified":
        return "repair only the documented source-contract deficiency or keep the source offline"
    return "restore the local Norgate runtime, then rerun a fresh bounded pilot"


def _validate_cases(
    cases: tuple[NorgateTrialDailyProbeCase, ...],
) -> tuple[NorgateTrialDailyProbeCase, ...]:
    expected_roles = ("current_member", "membership_change", "former_member")
    if not isinstance(cases, tuple) or tuple(case.role for case in cases) != expected_roles:
        raise NorgateTrialDailyPilotError("Norgate daily pilot roles are invalid")
    normalized: list[NorgateTrialDailyProbeCase] = []
    for case in cases:
        if not isinstance(case, NorgateTrialDailyProbeCase):
            raise NorgateTrialDailyPilotError("Norgate daily pilot case is invalid")
        if (
            isinstance(case.requested_start, datetime)
            or isinstance(case.requested_end, datetime)
            or not isinstance(case.requested_start, date)
            or not isinstance(case.requested_end, date)
            or case.requested_end < case.requested_start
        ):
            raise NorgateTrialDailyPilotError("Norgate daily pilot window is invalid")
        normalized.append(
            NorgateTrialDailyProbeCase(
                role=case.role,
                symbol=_symbol(case.symbol),
                requested_start=case.requested_start,
                requested_end=case.requested_end,
            )
        )
    if len({case.symbol for case in normalized}) != len(normalized):
        raise NorgateTrialDailyPilotError("Norgate daily pilot symbols must differ")
    return tuple(normalized)


def _validate_destination(
    destination: Path, *, market_data_root: Path, repo_root: Path | None
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or _is_link_like(root):
        raise NorgateTrialDailyPilotError("Norgate market-data root is unavailable")
    root = root.resolve()
    target = Path(destination)
    if target.exists() or _is_link_like(target):
        raise FileExistsError("Norgate daily pilot destination already exists")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise NorgateTrialDailyPilotError(
            "Norgate daily pilot destination must stay under market data"
        )
    if target.is_relative_to(_repository_root(repo_root)):
        raise NorgateTrialDailyPilotError("Norgate daily pilot destination must stay outside Git")
    if not target.name.startswith("pilot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise NorgateTrialDailyPilotError("Norgate daily pilot destination name is invalid")
    return target, root


def _validate_existing_pilot_dir(
    pilot_dir: Path, *, market_data_root: Path, repo_root: Path | None
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or _is_link_like(root):
        raise NorgateTrialDailyPilotError("Norgate market-data root is unavailable")
    root = root.resolve()
    directory = Path(pilot_dir)
    if not directory.is_dir() or _is_link_like(directory):
        raise NorgateTrialDailyPilotError("Norgate daily pilot directory is invalid")
    directory = directory.resolve()
    if not directory.is_relative_to(root) or directory.is_relative_to(_repository_root(repo_root)):
        raise NorgateTrialDailyPilotError("Norgate daily pilot must stay outside Git")
    if not directory.name.startswith("pilot=") or not directory.name.endswith(_SNAPSHOT_SUFFIX):
        raise NorgateTrialDailyPilotError("Norgate daily pilot directory is invalid")
    return directory, root


def _repository_root(repo_root: Path | None) -> Path:
    repository = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repository.is_dir() or _is_link_like(repository):
        raise NorgateTrialDailyPilotError("Norgate repository root is invalid")
    return repository.resolve()


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> None:
    try:
        usage = disk_usage(root)
        free_percent = float(usage.free) * 100 / float(usage.total)
    except (AttributeError, OSError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise NorgateTrialDailyPilotError("Norgate market-data storage is unavailable") from exc
    if free_percent < 15:
        raise NorgateTrialDailyPilotError(
            "Norgate market-data storage is below the hard free-space floor"
        )
    if free_percent < 20:
        warnings.warn(
            "Norgate market-data storage is below the warning free-space floor",
            stacklevel=2,
        )


def _create_staging_directory(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep the transient path short enough for Windows test/workspace roots.
    staging = target.parent / f".stage-{uuid.uuid4().hex[:12]}"
    staging.mkdir()
    return staging


def _read_regular_file(path: Path) -> bytes:
    if not path.is_file() or _is_link_like(path):
        raise NorgateTrialDailyPilotError("Norgate daily pilot file is invalid")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise NorgateTrialDailyPilotError("Norgate daily pilot file is unreadable") from exc


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NorgateTrialDailyPilotError(f"Norgate daily pilot {label} is invalid") from exc
    if not isinstance(value, dict):
        raise NorgateTrialDailyPilotError(f"Norgate daily pilot {label} is invalid")
    return value


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _gzip_bytes(value: bytes) -> bytes:
    return gzip.compress(value, mtime=0)


def _retention_marker_bytes() -> bytes:
    return (
        b"Norgate trial data is host-local and non-redistributable. "
        b"Delete this pilot when the trial or its permitted local use ends.\n"
    )


def _package_version(client: Any) -> str:
    value = getattr(client, "__version__", None)
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    return value.strip()


def _utc_datetime(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise NorgateTrialDailyPilotError(f"{label} must be timezone-aware UTC")
    normalized = value.astimezone(UTC)
    if normalized.utcoffset() != UTC.utcoffset(normalized):
        raise NorgateTrialDailyPilotError(f"{label} must be UTC")
    return normalized


def _safe_run_label(value: str) -> str:
    allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    if not isinstance(value, str) or not value or any(char not in allowed for char in value):
        raise ValueError("Norgate daily pilot run label is invalid")
    return value


def _symbol(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _NorgateSourceContractError("source_symbol_unavailable")
    result = value.strip().upper()
    if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ.-" for char in result):
        raise _NorgateSourceContractError("source_symbol_unavailable")
    return result


def _session_date(value: Any) -> date:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bytes):
        value = value.decode("ascii")
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise _NorgateSourceContractError("source_date_unavailable") from exc
    raise _NorgateSourceContractError("source_date_unavailable")


def _number_text(value: Any) -> str:
    if hasattr(value, "item"):
        value = value.item()
    result = str(value)
    if not result or result.lower() in {"nan", "inf", "-inf"}:
        raise _NorgateSourceContractError("unadjusted_d1_values_invalid")
    return result


def _flag(value: Any) -> bool:
    if hasattr(value, "item"):
        value = value.item()
    if value in (True, 1, "1", "true", "True"):
        return True
    if value in (False, 0, "0", "false", "False"):
        return False
    raise _NorgateSourceContractError("source_state_value_invalid")


def _row_value(row: Any, field_name: str) -> Any:
    try:
        return row[field_name]
    except (IndexError, KeyError, TypeError) as exc:
        raise _NorgateSourceContractError("source_row_unreadable") from exc


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_value(value: object, label: str) -> str:
    if not _is_sha256(value):
        raise NorgateTrialDailyPilotError(f"Norgate daily pilot {label} is invalid")
    assert isinstance(value, str)
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        char in "0123456789abcdef" for char in value[7:]
    )


def _is_link_like(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(path.lstat().st_file_attributes & 0x400)
    except (AttributeError, FileNotFoundError, OSError):
        return False
