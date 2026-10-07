"""Fixed Board H.15 snapshot and a development-only, lagged same-date join.

Observation dates are not publication timestamps. Byte identity is verified
separately from decision-local availability; this revised source is not PIT.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import stat
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import require_utc

SNAPSHOT_RELATIVE_PATH = Path("us_equities/federal_reserve_h15/snapshot=20261007T204212Z")
TWO_YEAR_SERIES = "RIFLGFCY02_N.B"
TEN_YEAR_SERIES = "RIFLGFCY10_N.B"
SOURCE_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15"
    "&series=bf17364827e38702b42a58cf8eaa3f78&lastobs=&from=&to="
    "&filetype=csv&label=include&layout=seriescolumn&type=package"
)
RAW_SHA256 = "sha256:233311307ac2f3acf08ae34d5ca3677bba695ce69e7e78d513390a85ffc7d5a9"
RAW_RELATIVE_PATH = "raw/" + RAW_SHA256.removeprefix("sha256:") + ".csv"
SNAPSHOT_SHA256 = MappingProxyType(
    {
        "manifest.json": "sha256:6b2c62423470f12c17d22a634d4d5018ed7f6682d5a5875bc08c6ffd9e49e393",
        "source-attestation.json": (
            "sha256:d7f6ea428eb2d9a834cd39d2969dd435a678d3e45c4838f21268d1eb68697fd3"
        ),
        RAW_RELATIVE_PATH: RAW_SHA256,
        TWO_YEAR_SERIES
        + ".csv": "sha256:e67bc77bf95651a62bc00f758078b9ffb9de6942645e966b78d5f6e0a4c8560c",
        TEN_YEAR_SERIES
        + ".csv": "sha256:bb80f7eb1203274473b5a553d8711e7dce95338c85dba1f7fcead46cd4b9f3fd",
    }
)
_MISSING_CODES = frozenset({"", "NA", "N/A", "ND"})
_HEADER = ("observation_date", "yield_percent", "source_missing_code")
_ERROR_CODES = frozenset(
    {
        "source_unavailable",
        "source_hash_mismatch",
        "source_contract_invalid",
        "csv_invalid",
        "date_invalid",
        "duplicate_observation_date",
        "observation_date_order_invalid",
        "missing_code_invalid",
        "value_invalid",
        "decision_invalid",
    }
)


class FederalReserveH15Error(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code if code in _ERROR_CODES else "source_contract_invalid")


@dataclass(frozen=True, slots=True)
class H15Observation:
    observation_date: date
    yield_percent: Decimal | None = field(repr=False)
    source_missing_code: str | None = None

    def __post_init__(self) -> None:
        if type(self.observation_date) is not date:
            raise FederalReserveH15Error("date_invalid")
        if self.source_missing_code is not None and (
            not isinstance(self.source_missing_code, str)
            or self.source_missing_code not in _MISSING_CODES
        ):
            raise FederalReserveH15Error("missing_code_invalid")
        if self.yield_percent is not None and not isinstance(self.yield_percent, Decimal):
            raise FederalReserveH15Error("value_invalid")
        if self.source_missing_code is not None and self.yield_percent is not None:
            raise FederalReserveH15Error("missing_code_invalid")
        # Finiteness belongs to the selected pair, not every future observation.


@dataclass(frozen=True, slots=True)
class H15Snapshot:
    two_year: tuple[H15Observation, ...] = field(repr=False)
    ten_year: tuple[H15Observation, ...] = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("two_year", "ten_year"):
            rows = tuple(getattr(self, name))
            previous = None
            for row in rows:
                if not isinstance(row, H15Observation):
                    raise FederalReserveH15Error("csv_invalid")
                if previous is not None and row.observation_date == previous:
                    raise FederalReserveH15Error("duplicate_observation_date")
                if previous is not None and row.observation_date < previous:
                    raise FederalReserveH15Error("observation_date_order_invalid")
                previous = row.observation_date
            object.__setattr__(self, name, rows)

    def safe_summary(self) -> dict[str, object]:
        return {
            "source": "Board_H15_revised_development",
            "units": "percent",
            "two_year_rows": len(self.two_year),
            "ten_year_rows": len(self.ten_year),
            "two_year_missing_rows": sum(
                row.source_missing_code is not None for row in self.two_year
            ),
            "ten_year_missing_rows": sum(
                row.source_missing_code is not None for row in self.ten_year
            ),
        }


@dataclass(frozen=True, slots=True)
class H15AsOfPair:
    status: Literal["available", "input_unavailable"]
    decision_at: datetime
    anchor_date: date
    observation_date: date | None = None
    reason: (
        Literal["shared_observation_missing", "shared_observation_stale", "selected_value_invalid"]
        | None
    ) = None
    two_year_percent: Decimal | None = field(default=None, repr=False)
    ten_year_percent: Decimal | None = field(default=None, repr=False)
    spread_percent: Decimal | None = field(default=None, repr=False)

    def safe_summary(self) -> dict[str, object]:
        return {
            "status": self.status,
            "decision_at": self.decision_at.isoformat(),
            "anchor_date": self.anchor_date.isoformat(),
            "observation_date": self.observation_date.isoformat()
            if self.observation_date
            else None,
            "reason": self.reason,
            "units": "percent",
            "lag_calendar_days": 30,
            "max_age_calendar_days": 7,
        }


def read_federal_reserve_h15_snapshot(root: Path | str) -> H15Snapshot:
    """Read only the five exact retained files; no acquisition or reconstruction."""
    sources = {}
    for relative, expected in SNAPSHOT_SHA256.items():
        path = Path(root) / relative
        try:
            _unlinked_file(path)
            payload = path.read_bytes()
            _unlinked_file(path)
        except (OSError, ValueError):
            raise FederalReserveH15Error("source_unavailable") from None
        if "sha256:" + hashlib.sha256(payload).hexdigest() != expected:
            raise FederalReserveH15Error("source_hash_mismatch")
        sources[relative] = payload
    try:
        manifest = json.loads(sources["manifest.json"])
        attestation = json.loads(sources["source-attestation.json"])
        if (
            manifest["source_url"] != SOURCE_URL
            or attestation["source_url"] != SOURCE_URL
            or manifest["response_sha256"] != RAW_SHA256
            or attestation["original_manifest_sha256"] != SNAPSHOT_SHA256["manifest.json"]
            or any(
                attestation[key] != RAW_SHA256
                for key in ("original_response_sha256", "re_retrieved_response_sha256")
            )
            or attestation["raw_response_retained"] is not True
            or attestation["raw_path_relative"] != RAW_RELATIVE_PATH
            or attestation["parser_counts_and_canonical_hashes"] != manifest["series"]
        ):
            raise FederalReserveH15Error("source_contract_invalid")
        for series in (TWO_YEAR_SERIES, TEN_YEAR_SERIES):
            metadata = manifest["series"][series]
            if (
                metadata["board_series_id"] != "H15/H15/" + series
                or metadata["units"] != "percent"
                or metadata["canonical_sha256"] != SNAPSHOT_SHA256[series + ".csv"]
            ):
                raise FederalReserveH15Error("source_contract_invalid")
    except (KeyError, TypeError, ValueError):
        raise FederalReserveH15Error("source_contract_invalid") from None
    return H15Snapshot(
        _canonical_rows(sources[TWO_YEAR_SERIES + ".csv"]),
        _canonical_rows(sources[TEN_YEAR_SERIES + ".csv"]),
    )


def select_h15_asof_pair(snapshot: H15Snapshot, *, decision_at: datetime) -> H15AsOfPair:
    """Select dates first, then validate exactly one pair; never carry a maturity."""
    try:
        if not isinstance(decision_at, datetime) or decision_at.utcoffset() != timedelta(0):
            raise ValueError
        decision_at = require_utc(decision_at, "H15 decision")
    except (TypeError, ValueError, AttributeError):
        raise FederalReserveH15Error("decision_invalid") from None
    anchor = decision_at.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=30)
    observations = []
    for rows in (snapshot.two_year, snapshot.ten_year):
        observations.append(
            {
                row.observation_date: row
                for row in rows
                if row.observation_date <= anchor and row.source_missing_code is None
            }
        )
    shared = observations[0].keys() & observations[1].keys()
    selected = max(shared, default=None)
    reason = None
    if selected is None:
        reason = "shared_observation_missing"
    elif (anchor - selected).days > 7:
        reason = "shared_observation_stale"
    else:
        two = observations[0][selected].yield_percent
        ten = observations[1][selected].yield_percent
        if any(value is None or not value.is_finite() for value in (two, ten)):
            reason = "selected_value_invalid"
        else:
            # Preserve exact percent subtraction independently of ambient precision.
            with localcontext() as context:
                context.prec = max(
                    50,
                    max(two.adjusted(), ten.adjusted())
                    - min(two.as_tuple().exponent, ten.as_tuple().exponent)
                    + 2,
                )
                spread = ten - two
            return H15AsOfPair(
                "available",
                decision_at,
                anchor,
                selected,
                two_year_percent=two,
                ten_year_percent=ten,
                spread_percent=spread,
            )
    return H15AsOfPair("input_unavailable", decision_at, anchor, selected, reason)


def _canonical_rows(payload: bytes) -> tuple[H15Observation, ...]:
    try:
        reader = csv.reader(io.StringIO(payload.decode("utf-8"), newline=""), strict=True)
        if tuple(next(reader, ())) != _HEADER:
            raise FederalReserveH15Error("csv_invalid")
        rows = []
        for row in reader:
            if len(row) != 3:
                raise FederalReserveH15Error("csv_invalid")
            try:
                observed = date.fromisoformat(row[0])
                if observed.isoformat() != row[0]:
                    raise ValueError
            except ValueError:
                raise FederalReserveH15Error("date_invalid") from None
            value, missing = row[1:]
            if value:
                if missing:
                    raise FederalReserveH15Error("missing_code_invalid")
                try:
                    number = Decimal(value)
                except InvalidOperation:
                    raise FederalReserveH15Error("value_invalid") from None
                rows.append(H15Observation(observed, number))
            else:
                rows.append(H15Observation(observed, None, missing))
        return tuple(rows)
    except (UnicodeError, csv.Error):
        raise FederalReserveH15Error("csv_invalid") from None


def _unlinked_file(path: Path) -> None:
    for entry in (*reversed(path.absolute().parents), path.absolute()):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked source")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("source is not a file")
