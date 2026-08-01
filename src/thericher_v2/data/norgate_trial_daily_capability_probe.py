"""Bounded, host-only capability evidence for the local Norgate trial.

The probe deliberately retains aggregate field and coverage facts only.  It
does not persist source rows, create a market-data panel, or qualify a model,
GPU, ranking, broker, or Paper route.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ROOT = (
    DEFAULT_MARKET_DATA_ROOT / "us_equities" / "norgate_trial" / "daily_capability_probe"
)
DEFAULT_NORGATE_HOST_DATA_ROOT = Path(r"C:\ProgramData\Norgate Data")
NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ID = "norgate-trial-daily-capability-probe-v1"
NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_VERSION = "norgate-trial-daily-capability-r1"
NORGATE_CURRENT_PAST_WATCHLIST = "S&P 500 Current & Past"
NORGATE_SP500_INDEX = "S&P 500"
NORGATE_FORMER_MEMBER_SELECTION_RULE = (
    "AAL is the alphabetically first latest-false candidate in the local Norgate "
    "Current & Past snapshot=2026-07-18; the probe rechecks source membership."
)

_PRECOMMIT_FILE = "precommit.json"
_RECEIPT_FILE = "receipt.json"
_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_SNAPSHOT_SUFFIX = "-norgate-trial-daily-capability-r1"
_VALID_STATUSES = (
    "qualified_for_offline_research",
    "unqualified",
    "input_unavailable",
)
_REQUIRED_MEMBERSHIP_FIELDS = ("Date", "Index Constituent")
_REQUIRED_LISTING_FIELDS = ("Date", "Major Exchange Listed")
_REQUIRED_PRICE_FIELDS = ("Date", "Open", "High", "Low", "Close", "Volume")
_REQUIRED_CAPITAL_EVENT_FIELDS = ("Date", "Capital Event")
_DATABASE_BUILD_FILES = (
    "core_us.ngdb",
    "us.databaseinfo.cobra",
    "us.price.index.cobra",
    "us.ich.index.cobra",
    "us.dilutions.index.cobra",
)
_PROBE_ATTESTATION = object()


class NorgateTrialDailyCapabilityProbeError(ValueError):
    """Raised when local capability evidence is malformed or unsafe to retain."""


class _NorgateSourceUnavailable(RuntimeError):
    """A source-local failure that must become an ``input_unavailable`` receipt."""


class _NorgateSourceContractError(ValueError):
    """A returned source shape that cannot satisfy this bounded contract."""


@dataclass(frozen=True, slots=True)
class NorgateTrialDailyProbeCase:
    """One fixed, small source probe with a categorical membership role."""

    role: str
    symbol: str
    requested_start: date
    requested_end: date


DEFAULT_NORGATE_TRIAL_DAILY_PROBE_CASES = (
    NorgateTrialDailyProbeCase(
        role="current_member",
        symbol="AAPL",
        requested_start=date(2025, 6, 2),
        requested_end=date(2025, 6, 13),
    ),
    NorgateTrialDailyProbeCase(
        role="membership_change",
        symbol="PLTR",
        requested_start=date(2024, 9, 18),
        requested_end=date(2024, 9, 27),
    ),
    NorgateTrialDailyProbeCase(
        role="former_member",
        symbol="AAL",
        requested_start=date(2025, 6, 2),
        requested_end=date(2025, 6, 13),
    ),
)


@dataclass(frozen=True, slots=True, init=False)
class NorgateTrialDailyCapabilityProbeResult:
    """Attested aggregate result; raw source rows never leave the probe."""

    receipt_dir: Path
    receipt_hash: str
    precommit_hash: str
    status: str
    package_version: str
    database_build_metadata_sha256: str
    source_namespace: str
    limitations: tuple[str, ...]
    scope: Mapping[str, bool]
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified Norgate trial capability-probe builder")

    def safe_payload(self) -> dict[str, object]:
        """Return only source-safe receipt facts for logs and stateboards."""

        require_attested_norgate_trial_daily_capability_probe(self)
        return {
            "receipt_dir": str(self.receipt_dir),
            "receipt_hash": self.receipt_hash,
            "precommit_hash": self.precommit_hash,
            "status": self.status,
            "package_version": self.package_version,
            "database_build_metadata_sha256": self.database_build_metadata_sha256,
            "source_namespace": self.source_namespace,
            "limitations": list(self.limitations),
            "scope": dict(self.scope),
        }


ClientLoader = Callable[[], Any]


def default_norgate_trial_daily_capability_probe_dir(run_label: str) -> Path:
    """Return the immutable external destination for one capability receipt."""

    label = _safe_run_label(run_label)
    return DEFAULT_NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ROOT / (f"probe={label}{_SNAPSHOT_SUFFIX}")


def fingerprint_norgate_us_database_build(
    data_root: Path = DEFAULT_NORGATE_HOST_DATA_ROOT,
) -> str:
    """Fingerprint fixed US database metadata without reading market-data bytes."""

    root = Path(data_root)
    if not root.is_dir() or _is_link_like(root):
        raise NorgateTrialDailyCapabilityProbeError("Norgate host data root is unavailable")
    rows: list[dict[str, object]] = []
    for name in _DATABASE_BUILD_FILES:
        path = root / name
        if not path.is_file() or _is_link_like(path):
            raise NorgateTrialDailyCapabilityProbeError("Norgate US database build is unavailable")
        try:
            stat = path.stat()
        except OSError as exc:
            raise NorgateTrialDailyCapabilityProbeError(
                "Norgate US database build is unavailable"
            ) from exc
        rows.append(
            {
                "name": name,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return _sha256(_json_bytes(rows))


def build_norgate_trial_daily_capability_probe(
    *,
    destination: Path,
    retrieved_at_utc: datetime,
    database_build_metadata_sha256: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    cases: tuple[NorgateTrialDailyProbeCase, ...] = DEFAULT_NORGATE_TRIAL_DAILY_PROBE_CASES,
    client_loader: ClientLoader | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTrialDailyCapabilityProbeResult:
    """Write one precommitted, aggregate-only local Norgate capability receipt."""

    retrieved_at = _utc_datetime(retrieved_at_utc)
    normalized_cases = _validate_cases(cases)
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_storage(root, disk_usage=disk_usage)
    build_hash = _sha256_value(database_build_metadata_sha256, "database build metadata hash")
    if platform_name != "win32":
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability probe requires Windows")

    precommit = _precommit_document(
        target,
        normalized_cases,
        retrieved_at,
        database_build_metadata_sha256=build_hash,
    )
    precommit_bytes = _json_bytes(precommit)
    staging = _create_staging_directory(target)
    try:
        (staging / _PRECOMMIT_FILE).write_bytes(precommit_bytes)
        (staging / _RETENTION_FILE).write_bytes(_retention_marker_bytes())
        status, package_version, observations, reasons = _collect_or_classify_unavailable(
            normalized_cases,
            client_loader=client_loader or _load_norgatedata,
        )
        receipt = _receipt_document(
            target=target,
            retrieved_at=retrieved_at,
            status=status,
            package_version=package_version,
            database_build_metadata_sha256=build_hash,
            precommit_hash=_sha256(precommit_bytes),
            observations=observations,
            reasons=reasons,
        )
        (staging / _RECEIPT_FILE).write_bytes(_json_bytes(receipt))
        os.rename(staging, target)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return verify_norgate_trial_daily_capability_probe(
        target,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def verify_norgate_trial_daily_capability_probe(
    receipt_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateTrialDailyCapabilityProbeResult:
    """Reattest a local receipt without loading Norgate, network, or credentials."""

    directory, _root = _validate_existing_receipt_dir(
        receipt_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    expected_files = {_PRECOMMIT_FILE, _RECEIPT_FILE, _RETENTION_FILE}
    if {path.name for path in directory.iterdir()} != expected_files:
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability receipt files are invalid")
    precommit_bytes = _read_regular_file(directory / _PRECOMMIT_FILE)
    receipt_bytes = _read_regular_file(directory / _RECEIPT_FILE)
    if _read_regular_file(directory / _RETENTION_FILE) != _retention_marker_bytes():
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability retention marker is invalid"
        )
    precommit = _json_object(precommit_bytes, "precommit")
    receipt = _json_object(receipt_bytes, "receipt")
    _validate_precommit(precommit, directory)
    _validate_receipt(receipt, precommit_hash=_sha256(precommit_bytes))
    result = object.__new__(NorgateTrialDailyCapabilityProbeResult)
    source = receipt["source"]
    scope = receipt["scope"]
    assert isinstance(source, dict)
    assert isinstance(scope, dict)
    object.__setattr__(result, "receipt_dir", directory)
    object.__setattr__(result, "receipt_hash", _sha256(receipt_bytes))
    object.__setattr__(result, "precommit_hash", _sha256(precommit_bytes))
    object.__setattr__(result, "status", receipt["status"])
    object.__setattr__(result, "package_version", source["package_version"])
    object.__setattr__(
        result,
        "database_build_metadata_sha256",
        source["database_build_metadata_sha256"],
    )
    object.__setattr__(result, "source_namespace", source["namespace"])
    object.__setattr__(result, "limitations", tuple(receipt["limitations"]))
    object.__setattr__(result, "scope", MappingProxyType(dict(scope)))
    object.__setattr__(result, "_attestation", _PROBE_ATTESTATION)
    return result


def require_attested_norgate_trial_daily_capability_probe(
    value: object,
) -> NorgateTrialDailyCapabilityProbeResult:
    """Reject forged or widened inputs before a later Research consumer uses them."""

    if (
        not isinstance(value, NorgateTrialDailyCapabilityProbeResult)
        or getattr(value, "_attestation", None) is not _PROBE_ATTESTATION
        or getattr(value, "status", None) not in _VALID_STATUSES
        or getattr(value, "source_namespace", None) != "norgate_trial_daily_offline_research_only"
        or not isinstance(getattr(value, "receipt_hash", None), str)
        or not isinstance(getattr(value, "precommit_hash", None), str)
        or not isinstance(getattr(value, "scope", None), Mapping)
    ):
        raise ValueError("Norgate trial capability probe requires verified attestation")
    required_scope = _scope()
    if dict(value.scope) != required_scope:
        raise ValueError("Norgate trial capability probe scope is invalid")
    return value


def _load_norgatedata() -> Any:
    return importlib.import_module("norgatedata")


def _collect_or_classify_unavailable(
    cases: tuple[NorgateTrialDailyProbeCase, ...],
    *,
    client_loader: ClientLoader,
) -> tuple[str, str, dict[str, object], tuple[str, ...]]:
    try:
        client = _load_client(client_loader)
    except _NorgateSourceUnavailable:
        return "input_unavailable", "unavailable", {}, ("source_client_unavailable",)
    try:
        observations = _collect_observations(client, cases)
    except _NorgateSourceUnavailable:
        return "input_unavailable", _package_version(client), {}, ("source_call_unavailable",)
    except _NorgateSourceContractError as exc:
        return "unqualified", _package_version(client), {}, (str(exc),)
    reasons = _qualification_reasons(observations, cases)
    return (
        "qualified_for_offline_research" if not reasons else "unqualified",
        _package_version(client),
        observations,
        tuple(reasons or ("offline_research_scope_attested",)),
    )


def _load_client(client_loader: ClientLoader) -> Any:
    try:
        client = client_loader()
        _ = client.PaddingType.NONE
        _ = client.StockPriceAdjustmentType.NONE
        _ = client.watchlist_symbols
        _ = client.index_constituent_timeseries
        _ = client.major_exchange_listed_timeseries
        _ = client.price_timeseries
        _ = client.capital_event_timeseries
    except Exception as exc:
        raise _NorgateSourceUnavailable() from exc
    return client


def _collect_observations(
    client: Any,
    cases: tuple[NorgateTrialDailyProbeCase, ...],
) -> dict[str, object]:
    try:
        raw_candidates = client.watchlist_symbols(NORGATE_CURRENT_PAST_WATCHLIST)
    except Exception as exc:
        raise _NorgateSourceUnavailable() from exc
    if not isinstance(raw_candidates, (list, tuple)):
        raise _NorgateSourceContractError("current_past_watchlist_unreadable")
    candidates = {_symbol(value) for value in raw_candidates}
    if not candidates:
        raise _NorgateSourceContractError("current_past_watchlist_empty")
    cases_payload: dict[str, object] = {}
    for case in cases:
        cases_payload[case.role] = _collect_case(client, case, candidates)
    return {
        "watchlist": {
            "name": NORGATE_CURRENT_PAST_WATCHLIST,
            "candidate_count": len(candidates),
        },
        "cases": cases_payload,
    }


def _collect_case(
    client: Any, case: NorgateTrialDailyProbeCase, candidates: set[str]
) -> dict[str, object]:
    membership_rows = _call_series(
        client.index_constituent_timeseries,
        case.symbol,
        NORGATE_SP500_INDEX,
        padding_setting=client.PaddingType.NONE,
        start_date=case.requested_start.isoformat(),
        end_date=case.requested_end.isoformat(),
        limit=-1,
        timeseriesformat="numpy-recarray",
    )
    listing_rows = _call_series(
        client.major_exchange_listed_timeseries,
        case.symbol,
        padding_setting=client.PaddingType.NONE,
        start_date=case.requested_start.isoformat(),
        end_date=case.requested_end.isoformat(),
        limit=-1,
        timeseriesformat="numpy-recarray",
    )
    price_rows = _call_series(
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
    event_rows = _call_series(
        client.capital_event_timeseries,
        case.symbol,
        padding_setting=client.PaddingType.NONE,
        start_date=case.requested_start.isoformat(),
        end_date=case.requested_end.isoformat(),
        limit=-1,
        timeseriesformat="numpy-recarray",
    )
    return {
        "symbol": case.symbol,
        "in_current_past_watchlist": case.symbol in candidates,
        "requested_window": {
            "start": case.requested_start.isoformat(),
            "end": case.requested_end.isoformat(),
        },
        "membership": _boolean_series_summary(
            membership_rows,
            required_fields=_REQUIRED_MEMBERSHIP_FIELDS,
            value_field="Index Constituent",
            case=case,
            empty_is_error=True,
        ),
        "major_exchange_listing": _boolean_series_summary(
            listing_rows,
            required_fields=_REQUIRED_LISTING_FIELDS,
            value_field="Major Exchange Listed",
            case=case,
            empty_is_error=True,
        ),
        "unadjusted_d1_ohlcv": _field_series_summary(
            price_rows,
            required_fields=_REQUIRED_PRICE_FIELDS,
            case=case,
            empty_is_error=True,
        ),
        "capital_event_marker": _boolean_series_summary(
            event_rows,
            required_fields=_REQUIRED_CAPITAL_EVENT_FIELDS,
            value_field="Capital Event",
            case=case,
            empty_is_error=False,
            clip_outside_requested_window=True,
        ),
    }


def _call_series(call: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    try:
        return call(*args, **kwargs)
    except Exception as exc:
        raise _NorgateSourceUnavailable() from exc


def _boolean_series_summary(
    response: Any,
    *,
    required_fields: tuple[str, ...],
    value_field: str,
    case: NorgateTrialDailyProbeCase,
    empty_is_error: bool,
    clip_outside_requested_window: bool = False,
) -> dict[str, object]:
    rows = _validated_rows(
        response,
        required_fields=required_fields,
        case=case,
        empty_is_error=empty_is_error,
        clip_outside_requested_window=clip_outside_requested_window,
    )
    values = [_flag(_row_value(row, value_field)) for row in rows]
    return {
        **_row_summary(rows),
        "required_fields_present": True,
        "true_count": sum(values),
        "false_count": len(values) - sum(values),
        "transition_count": sum(
            previous != current for previous, current in zip(values, values[1:], strict=False)
        ),
        "latest_value": values[-1] if values else None,
    }


def _field_series_summary(
    response: Any,
    *,
    required_fields: tuple[str, ...],
    case: NorgateTrialDailyProbeCase,
    empty_is_error: bool,
) -> dict[str, object]:
    rows = _validated_rows(
        response,
        required_fields=required_fields,
        case=case,
        empty_is_error=empty_is_error,
        clip_outside_requested_window=False,
    )
    return {**_row_summary(rows), "required_fields_present": True}


def _validated_rows(
    response: Any,
    *,
    required_fields: tuple[str, ...],
    case: NorgateTrialDailyProbeCase,
    empty_is_error: bool,
    clip_outside_requested_window: bool,
) -> tuple[Any, ...]:
    fields = tuple(getattr(getattr(response, "dtype", None), "names", ()) or ())
    if not fields or any(field not in fields for field in required_fields):
        raise _NorgateSourceContractError("required_source_fields_unavailable")
    try:
        rows = tuple(response)
    except TypeError as exc:
        raise _NorgateSourceContractError("source_series_unreadable") from exc
    selected: list[Any] = []
    previous: date | None = None
    for row in rows:
        session_date = _session_date(_row_value(row, "Date"))
        if session_date < case.requested_start or session_date > case.requested_end:
            if clip_outside_requested_window:
                continue
            raise _NorgateSourceContractError("source_series_outside_requested_window")
        if previous is not None and session_date <= previous:
            raise _NorgateSourceContractError("source_series_not_strictly_ordered")
        previous = session_date
        selected.append(row)
    if empty_is_error and not selected:
        raise _NorgateSourceContractError("required_source_series_empty")
    return tuple(selected)


def _row_summary(rows: tuple[Any, ...]) -> dict[str, object]:
    if not rows:
        return {"row_count": 0, "start": None, "end": None}
    return {
        "row_count": len(rows),
        "start": _session_date(_row_value(rows[0], "Date")).isoformat(),
        "end": _session_date(_row_value(rows[-1], "Date")).isoformat(),
    }


def _qualification_reasons(
    observations: dict[str, object],
    cases: tuple[NorgateTrialDailyProbeCase, ...],
) -> list[str]:
    raw_cases = observations.get("cases")
    if not isinstance(raw_cases, dict):
        return ["case_observations_unavailable"]
    reasons: list[str] = []
    for case in cases:
        item = raw_cases.get(case.role)
        if not isinstance(item, dict):
            reasons.append(f"{case.role}_observations_unavailable")
            continue
        if item.get("in_current_past_watchlist") is not True:
            reasons.append(f"{case.role}_not_in_current_past_watchlist")
        if not _field_present(item, "major_exchange_listing"):
            reasons.append(f"{case.role}_listing_unavailable")
        if not _field_present(item, "unadjusted_d1_ohlcv"):
            reasons.append(f"{case.role}_unadjusted_d1_ohlcv_unavailable")
        if not _field_present(item, "capital_event_marker", allow_empty=True):
            reasons.append(f"{case.role}_capital_event_marker_unavailable")
    current = raw_cases.get("current_member")
    change = raw_cases.get("membership_change")
    former = raw_cases.get("former_member")
    if not isinstance(current, dict) or _latest_value(current, "membership") is not True:
        reasons.append("current_member_not_confirmed")
    if not isinstance(change, dict) or not _membership_change_observed(change):
        reasons.append("in_horizon_membership_change_not_confirmed")
    if not isinstance(former, dict) or _latest_value(former, "membership") is not False:
        reasons.append("former_member_not_confirmed")
    return sorted(set(reasons))


def _field_present(item: dict[str, object], key: str, *, allow_empty: bool = False) -> bool:
    detail = item.get(key)
    if not isinstance(detail, dict) or detail.get("required_fields_present") is not True:
        return False
    row_count = detail.get("row_count")
    return allow_empty or isinstance(row_count, int) and row_count > 0


def _latest_value(item: dict[str, object], key: str) -> bool | None:
    detail = item.get(key)
    if not isinstance(detail, dict):
        return None
    value = detail.get("latest_value")
    return value if isinstance(value, bool) else None


def _membership_change_observed(item: dict[str, object]) -> bool:
    detail = item.get("membership")
    if not isinstance(detail, dict):
        return False
    return (
        detail.get("true_count", 0) > 0
        and detail.get("false_count", 0) > 0
        and detail.get("transition_count", 0) > 0
    )


def _precommit_document(
    target: Path,
    cases: tuple[NorgateTrialDailyProbeCase, ...],
    retrieved_at: datetime,
    *,
    database_build_metadata_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "norgate_trial_daily_capability_precommit",
        "probe_id": NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ID,
        "probe_version": NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_VERSION,
        "destination": str(target),
        "retrieved_at_utc": retrieved_at.isoformat(),
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
                "membership": list(_REQUIRED_MEMBERSHIP_FIELDS),
                "major_exchange_listing": list(_REQUIRED_LISTING_FIELDS),
                "unadjusted_d1_ohlcv": list(_REQUIRED_PRICE_FIELDS),
                "capital_event_marker": list(_REQUIRED_CAPITAL_EVENT_FIELDS),
            }
            for case in cases
        ],
        "former_member_selection_rule": NORGATE_FORMER_MEMBER_SELECTION_RULE,
        "scope": _scope(),
        "constraints": {
            "network_used": False,
            "credential_access_used": False,
            "kis_used": False,
            "broker_used": False,
            "docker_provider_used": False,
            "raw_source_rows_persisted": False,
            "model_result_created": False,
            "gpu_used": False,
        },
    }


def _receipt_document(
    *,
    target: Path,
    retrieved_at: datetime,
    status: str,
    package_version: str,
    database_build_metadata_sha256: str,
    precommit_hash: str,
    observations: dict[str, object],
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "norgate_trial_daily_capability_receipt",
        "probe_id": NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ID,
        "probe_version": NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_VERSION,
        "receipt_dir": str(target),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "status": status,
        "precommit_sha256": precommit_hash,
        "source": {
            "provider": "norgatedata",
            "package_version": package_version,
            "database_build_metadata_sha256": database_build_metadata_sha256,
            "namespace": "norgate_trial_daily_offline_research_only",
        },
        "scope": _scope(),
        "source_observations": observations,
        "qualification_reasons": list(reasons),
        "limitations": [
            "Norgate trial data remains host-local and non-redistributable.",
            "Vendor membership availability time is unknown.",
            "Requested unadjusted setting is not proof of adjustment semantics.",
            "Capital-event marker completeness and timing are unknown.",
            "This receipt is offline-research-only and cannot create a model, ranking, GPU, "
            "or Paper input.",
        ],
        "receipt_constraints": {
            "network_used": False,
            "credential_access_used": False,
            "kis_used": False,
            "broker_used": False,
            "docker_provider_used": False,
            "raw_source_rows_persisted": False,
            "raw_ohlcv_persisted": False,
            "model_result_created": False,
            "gpu_used": False,
        },
        "recovery_fact": _recovery_fact(status),
    }


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


def _recovery_fact(status: str) -> str:
    if status == "qualified_for_offline_research":
        return "freeze a separate offline daily campaign contract before source rows are consumed"
    if status == "unqualified":
        return "repair only a documented source-contract deficiency or keep the source offline"
    return "restore the local Norgate host runtime, then rerun a fresh bounded probe"


def _validate_precommit(document: dict[str, object], directory: Path) -> None:
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "norgate_trial_daily_capability_precommit"
        or document.get("probe_id") != NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ID
        or document.get("probe_version") != NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_VERSION
        or document.get("destination") != str(directory)
        or document.get("scope") != _scope()
    ):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability precommit is invalid")
    queries = document.get("queries")
    if not isinstance(queries, list) or len(queries) != 3:
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability precommit queries are invalid"
        )


def _validate_receipt(document: dict[str, object], *, precommit_hash: str) -> None:
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "norgate_trial_daily_capability_receipt"
        or document.get("probe_id") != NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_ID
        or document.get("probe_version") != NORGATE_TRIAL_DAILY_CAPABILITY_PROBE_VERSION
        or document.get("status") not in _VALID_STATUSES
        or document.get("precommit_sha256") != precommit_hash
        or document.get("scope") != _scope()
    ):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability receipt is invalid")
    source = document.get("source")
    constraints = document.get("receipt_constraints")
    limitations = document.get("limitations")
    if (
        not isinstance(source, dict)
        or source.get("provider") != "norgatedata"
        or source.get("namespace") != "norgate_trial_daily_offline_research_only"
        or not isinstance(source.get("package_version"), str)
        or not _is_sha256(source.get("database_build_metadata_sha256"))
        or not isinstance(constraints, dict)
        or any(constraints.get(key) is not False for key in constraints)
        or not isinstance(limitations, list)
        or not all(isinstance(value, str) and value for value in limitations)
    ):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability receipt is invalid")


def _validate_cases(
    cases: tuple[NorgateTrialDailyProbeCase, ...],
) -> tuple[NorgateTrialDailyProbeCase, ...]:
    if not isinstance(cases, tuple) or tuple(case.role for case in cases) != (
        "current_member",
        "membership_change",
        "former_member",
    ):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability probe roles are invalid")
    normalized: list[NorgateTrialDailyProbeCase] = []
    for case in cases:
        if not isinstance(case, NorgateTrialDailyProbeCase):
            raise NorgateTrialDailyCapabilityProbeError("Norgate capability probe case is invalid")
        symbol = _symbol(case.symbol)
        if isinstance(case.requested_start, datetime) or isinstance(case.requested_end, datetime):
            raise NorgateTrialDailyCapabilityProbeError(
                "Norgate capability dates must not include a time"
            )
        if case.requested_end < case.requested_start:
            raise NorgateTrialDailyCapabilityProbeError(
                "Norgate capability probe window is invalid"
            )
        normalized.append(
            NorgateTrialDailyProbeCase(
                role=case.role,
                symbol=symbol,
                requested_start=case.requested_start,
                requested_end=case.requested_end,
            )
        )
    if len({case.symbol for case in normalized}) != len(normalized):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability probe symbols must differ")
    return tuple(normalized)


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or _is_link_like(root):
        raise NorgateTrialDailyCapabilityProbeError("Norgate market-data root is unavailable")
    root = root.resolve()
    target = Path(destination)
    if target.exists() or _is_link_like(target):
        raise FileExistsError("Norgate capability probe destination already exists")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability probe destination must stay under market data"
        )
    repository = _repository_root(repo_root)
    if target.is_relative_to(repository):
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability probe destination must stay outside Git"
        )
    if not target.name.startswith("probe=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability probe destination name is invalid"
        )
    return target, root


def _validate_existing_receipt_dir(
    receipt_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or _is_link_like(root):
        raise NorgateTrialDailyCapabilityProbeError("Norgate market-data root is unavailable")
    root = root.resolve()
    directory = Path(receipt_dir)
    if not directory.is_dir() or _is_link_like(directory):
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability receipt directory is invalid"
        )
    directory = directory.resolve()
    if not directory.is_relative_to(root) or directory.is_relative_to(_repository_root(repo_root)):
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability receipt must stay outside Git"
        )
    if not directory.name.startswith("probe=") or not directory.name.endswith(_SNAPSHOT_SUFFIX):
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability receipt directory is invalid"
        )
    return directory, root


def _repository_root(repo_root: Path | None) -> Path:
    repository = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repository.is_dir() or _is_link_like(repository):
        raise NorgateTrialDailyCapabilityProbeError("Norgate repository root is invalid")
    return repository.resolve()


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> None:
    try:
        usage = disk_usage(root)
        free_percent = 100 * usage.free / usage.total
    except (AttributeError, OSError, ZeroDivisionError) as exc:
        raise NorgateTrialDailyCapabilityProbeError("Norgate storage cannot be measured") from exc
    if free_percent < 15:
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate storage is below hard free-space floor"
        )


def _create_staging_directory(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.is_dir() or _is_link_like(target.parent):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability probe parent is invalid")
    # Keep the temporary child short: Windows test/temp paths can already be long.
    staging = target.parent / f".staging-{uuid.uuid4().hex[:12]}"
    staging.mkdir()
    return staging


def _read_regular_file(path: Path) -> bytes:
    if not path.is_file() or _is_link_like(path):
        raise NorgateTrialDailyCapabilityProbeError("Norgate capability receipt file is invalid")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise NorgateTrialDailyCapabilityProbeError(
            "Norgate capability receipt is unreadable"
        ) from exc


def _retention_marker_bytes() -> bytes:
    return (
        "This directory contains source-derived Norgate trial capability evidence.\n"
        "It is host-local, non-redistributable, and contains no raw Norgate rows.\n"
        "Delete it when the Norgate trial or its retained local source rights expire.\n"
    ).encode("ascii")


def _package_version(client: Any) -> str:
    value = getattr(client, "__version__", None)
    if not isinstance(value, str) or not value.strip():
        raise _NorgateSourceContractError("package_version_unavailable")
    return value.strip()


def _row_value(row: Any, field_name: str) -> Any:
    try:
        return row[field_name]
    except (IndexError, KeyError, TypeError) as exc:
        raise _NorgateSourceContractError("source_field_unreadable") from exc


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
            raise _NorgateSourceContractError("source_date_unreadable") from exc
    raise _NorgateSourceContractError("source_date_unreadable")


def _flag(value: Any) -> bool:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip() in ("0", "1"):
        return value.strip() == "1"
    raise _NorgateSourceContractError("source_boolean_field_unreadable")


def _symbol(value: object) -> str:
    if not isinstance(value, str):
        raise _NorgateSourceContractError("source_symbol_unreadable")
    symbol = value.strip().upper()
    if not symbol or any(character.isspace() for character in symbol):
        raise _NorgateSourceContractError("source_symbol_unreadable")
    return symbol


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise NorgateTrialDailyCapabilityProbeError("Norgate retrieval time must be timezone-aware")
    return value.astimezone(UTC)


def _safe_run_label(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            not (character.isascii() and (character.isalnum() or character in "-_"))
            for character in value
        )
    ):
        raise ValueError("Norgate capability probe run label is invalid")
    return value


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_value(value: object, label: str) -> str:
    if not _is_sha256(value):
        raise NorgateTrialDailyCapabilityProbeError(f"Norgate {label} is invalid")
    assert isinstance(value, str)
    return value


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value[7:], 16)
    except ValueError:
        return False
    return True


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _json_object(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NorgateTrialDailyCapabilityProbeError(
            f"Norgate capability {label} is invalid"
        ) from exc
    if not isinstance(value, dict):
        raise NorgateTrialDailyCapabilityProbeError(f"Norgate capability {label} is invalid")
    return value


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())
