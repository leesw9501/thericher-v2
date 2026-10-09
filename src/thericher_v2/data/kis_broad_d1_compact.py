"""Exact, date-cropped Bar serialization for the frozen broad D1 study."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_broad_d1_explicit_keys as explicit
from thericher_v2.data.kis_paper_daily_broad_registry import KisPaperDailyBroadRegistryTarget
from thericher_v2.data.local import CSV_FIELDS, bar_from_record, bar_to_record
from thericher_v2.research import kis_cross_asset_monthly_momentum as storage

_KIND = "kis_broad_d1_compact_v1"
_PREFIX = Path("us_equities/kis_paper_private/daily-nas-broad-compact/v1")
_MARKET = Path("D:/market_data")
_ARTIFACT = Path("D:/thericher-v2/model-artifacts")
_ORIGINAL = "sha256:6ee8fa568e364ed3a3f32a1ebcaff39467919fb623492b478ad4625475388a27"
_GRID = "sha256:69ad31e6b7a7fceba9d8e3f048f9e48ed11439e644c2d69d0d28dd873d83b4af"
_COLUMNS = ("target_key", *CSV_FIELDS)
_PIN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DIGEST_ENCODING = (
    "sha256(canonical sorted compact JSON bar_to_record + LF per row); empty bytes for empty key"
)
_SOURCE_SCOPE = (
    "loader stream/metadata files only; original3044 parent binding "
    "includes two additional listing files"
)
_LIMITATIONS = (
    "raw MODP0; corporate actions/dividends/total return unqualified",
    "current-listing-only/survivorship/non-PIT seen development",
    "historical producer code revision unattested",
    "UTC-midnight labels are date keys, not NYSE clocks",
    "provider publication/availability/finality not_observed",
    "serialization only; no model/holdout/Paper qualification",
)


class KisBroadD1CompactUnavailable(ValueError):
    def __init__(self, code: str) -> None:
        if code not in {
            "compact_scope_invalid",
            "compact_source_invalid",
            "compact_binding_invalid",
            "compact_contents_invalid",
            "compact_output_unavailable",
        }:
            raise ValueError("invalid_compact_code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class KisBroadD1CompactInput:
    manifest_path: Path
    manifest_sha256: str
    packed_path: Path
    packed_sha256: str
    original_contract_sha256: str
    dataset_hash: str
    selected_target_keys: tuple[str, ...]
    scheduled_dates: tuple[date, ...]
    bars_by_target: Mapping[str, tuple[Bar, ...]] = field(repr=False)
    logical_record_sha256: Mapping[str, str]

    def safe_facts(self) -> dict[str, object]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "packed_sha256": self.packed_sha256,
            "original_contract_sha256": self.original_contract_sha256,
            "dataset_hash": self.dataset_hash,
            "selected_key_count": len(self.selected_target_keys),
            "scheduled_date_count": len(self.scheduled_dates),
            "row_counts": {key: len(rows) for key, rows in self.bars_by_target.items()},
            "logical_record_sha256": dict(self.logical_record_sha256),
            "limitations": list(_LIMITATIONS),
        }


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise KisBroadD1CompactUnavailable(code)


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _dates(values: tuple[date, ...]) -> tuple[date, ...]:
    _require(
        type(values) is tuple and len(values) == 800 and all(type(day) is date for day in values),
        "compact_scope_invalid",
    )
    _require(
        values == tuple(sorted(set(values)))
        and values[0] == date(2023, 5, 17)
        and values[-1] == date(2026, 7, 27),
        "compact_scope_invalid",
    )
    grid = storage.digest(
        _encode(
            {"session_starts": [datetime.combine(day, time(), UTC).isoformat() for day in values]}
        )
    )
    _require(grid == _GRID, "compact_scope_invalid")
    return values


def _location(path: Path | str, *, market_root: Path | str, repo_root: Path | str) -> Path:
    market, repo = Path(market_root).absolute(), Path(repo_root).absolute()
    _require(
        not market.resolve().is_relative_to(repo.resolve())
        and not market.resolve().is_relative_to(_ARTIFACT.resolve()),
        "compact_scope_invalid",
    )
    path = Path(path).absolute()
    _require(
        path.is_relative_to((market / _PREFIX).absolute()) and not path.is_relative_to(repo),
        "compact_scope_invalid",
    )
    resolved = path.resolve()
    _require(
        resolved.is_relative_to(market.resolve() / _PREFIX)
        and not resolved.is_relative_to(repo.resolve())
        and not resolved.is_relative_to(_ARTIFACT.resolve()),
        "compact_scope_invalid",
    )
    _require(not any(item.is_symlink() for item in (path, *path.parents)), "compact_scope_invalid")
    return path


def _keys(keys: tuple[str, ...]) -> tuple[str, ...]:
    _require(
        type(keys) is tuple
        and 1 <= len(keys) <= 128
        and all(explicit.panel._is_target_key(key) for key in keys)
        and keys == tuple(sorted(set(keys))),
        "compact_scope_invalid",
    )
    return keys


def _bar_record(identity: Mapping[str, str], bar: Bar) -> dict[str, str]:
    _require(
        type(bar) is Bar
        and bar.symbol == identity["symbol"]
        and bar.market == "US"
        and bar.timeframe is Timeframe.D1
        and bar.start_ts == datetime.combine(bar.start_ts.date(), time(), UTC),
        "compact_contents_invalid",
    )
    return bar_to_record(bar)


def _record_digest(records: tuple[dict[str, str], ...]) -> str:
    value = hashlib.sha256()
    for record in records:
        value.update(_encode(record) + b"\n")
    return "sha256:" + value.hexdigest()


def _pack(
    rows: Mapping[str, tuple[Bar, ...]],
    keys: tuple[str, ...],
    dates: tuple[date, ...],
    identities: Mapping[str, Mapping[str, str]],
):
    allowed = set(dates)
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=_COLUMNS, lineterminator="\n")
    writer.writeheader()
    cropped, counts, digests = {}, {}, {}
    for key in keys:
        selected = tuple(bar for bar in rows[key] if bar.start_ts.date() in allowed)
        labels = tuple(bar.start_ts for bar in selected)
        _require(labels == tuple(sorted(set(labels))), "compact_contents_invalid")
        records = tuple(_bar_record(identities[key], bar) for bar in selected)
        writer.writerows(dict(target_key=key, **record) for record in records)
        cropped[key], counts[key], digests[key] = selected, len(selected), _record_digest(records)
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=packed, mode="wb", mtime=0) as stream:
        stream.write(text.getvalue().encode("utf-8"))
    return packed.getvalue(), cropped, counts, digests


def materialize_kis_broad_d1_compact(
    metadata: explicit.KisBroadD1ExplicitKeysMetadata,
    *,
    scheduled_dates: tuple[date, ...],
    original_contract_sha256: str,
    original_input_bindings_sha256: str,
    output_root: Path | str,
    repo_root: Path | str,
    market_root: Path | str = _MARKET,
) -> KisBroadD1CompactInput:
    """Validate original streams, crop only declared dates, write a new exact view."""
    try:
        root = _location(output_root, market_root=market_root, repo_root=repo_root)
        _require(
            not root.exists()
            and type(metadata) is explicit.KisBroadD1ExplicitKeysMetadata
            and original_contract_sha256 == _ORIGINAL
            and type(original_input_bindings_sha256) is str
            and bool(_PIN.fullmatch(original_input_bindings_sha256)),
            "compact_scope_invalid",
        )
        dates, keys = _dates(scheduled_dates), _keys(metadata.selected_target_keys)
        _require(
            tuple(day for day in metadata.calendar_session_dates if dates[0] <= day <= dates[-1])
            == dates,
            "compact_scope_invalid",
        )
        producer_path = Path(__file__)
        producer_raw = storage._read(producer_path)
        loaded = explicit.load_kis_broad_d1_explicit_keys(metadata)
        _require(
            tuple(loaded.bars_by_target) == keys
            and loaded.source_bindings_before == loaded.source_bindings_after,
            "compact_source_invalid",
        )
        documents = explicit._document(metadata._targets_document)["targets"]
        identities = {
            item["target_key"]: {"symbol": item["symbol"], "exchange": item["exchange"]}
            for item in documents
        }
        _require(
            tuple(identities) == keys and len(documents) == len(keys), "compact_source_invalid"
        )
        packed, cropped, counts, digests = _pack(loaded.bars_by_target, keys, dates, identities)
        manifest = {
            "kind": _KIND,
            "original_contract_sha256": original_contract_sha256,
            "dataset_hash": metadata.dataset_hash,
            "index_sha256": metadata.index_sha256,
            "selected_target_keys": list(keys),
            "target_identities": identities,
            "scheduled_dates": [day.isoformat() for day in dates],
            "calendar_grid_sha256": _GRID,
            "columns": list(_COLUMNS),
            "packed": {
                "path": "bars.csv.gz",
                "sha256": storage.digest(packed),
                "size_bytes": len(packed),
                "row_count": sum(counts.values()),
            },
            "row_counts": counts,
            "logical_record_sha256": digests,
            "logical_digest_encoding": _DIGEST_ENCODING,
            "producer": {
                "path": "src/thericher_v2/data/kis_broad_d1_compact.py",
                "sha256": storage.digest(producer_raw),
            },
            "original_input_bindings_sha256": original_input_bindings_sha256,
            "original_input_binding_count": 3044,
            "source_binding_count": len(loaded.source_bindings_after),
            "source_binding_scope": _SOURCE_SCOPE,
            "original_sources_before_after_equal": True,
            "scope": {
                "price_adjustment_applied": False,
                "date_crop_only": True,
                "no_key_filter_or_replacement": True,
                "sparse_and_empty_keys_preserved": True,
            },
            "limitations": list(_LIMITATIONS),
        }
        explicit._reattest(loaded.source_bindings_after)
        root.mkdir(parents=True)
        with (root / "bars.csv.gz").open("xb") as stream:
            stream.write(packed)
        manifest_raw = _encode(manifest)
        with (root / "manifest.json").open("xb") as stream:
            stream.write(manifest_raw)
        result = load_kis_broad_d1_compact(
            root / "manifest.json",
            expected_manifest_sha256=storage.digest(manifest_raw),
            repo_root=repo_root,
            market_root=market_root,
        )
        _require(
            all(
                tuple(bar_to_record(bar) for bar in result.bars_by_target[key])
                == tuple(bar_to_record(bar) for bar in cropped[key])
                for key in keys
            ),
            "compact_contents_invalid",
        )
        explicit._reattest(loaded.source_bindings_after)
        _require(storage._read(producer_path) == producer_raw, "compact_source_invalid")
        return result
    except KisBroadD1CompactUnavailable:
        raise
    except explicit.KisBroadD1ExplicitKeysUnavailable:
        raise KisBroadD1CompactUnavailable("compact_source_invalid") from None
    except (OSError, ArithmeticError, ValueError, TypeError, KeyError, csv.Error):
        raise KisBroadD1CompactUnavailable("compact_output_unavailable") from None


def _document(raw: bytes) -> dict[str, object]:
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, "compact_binding_invalid")
            result[key] = value
        return result

    result = json.loads(raw, object_pairs_hook=pairs)
    _require(type(result) is dict and _encode(result) == raw, "compact_binding_invalid")
    return result


def load_kis_broad_d1_compact(
    manifest_path: Path | str,
    *,
    expected_manifest_sha256: str,
    repo_root: Path | str,
    market_root: Path | str = _MARKET,
) -> KisBroadD1CompactInput:
    """Reattest two files and reconstruct every declared key without source rereads."""
    try:
        path = _location(manifest_path, market_root=market_root, repo_root=repo_root)
        _require(
            path.name == "manifest.json"
            and type(expected_manifest_sha256) is str
            and bool(_PIN.fullmatch(expected_manifest_sha256)),
            "compact_binding_invalid",
        )
        raw = storage._read(path)
        _require(storage.digest(raw) == expected_manifest_sha256, "compact_binding_invalid")
        manifest = _document(raw)
        _require(
            set(manifest)
            == {
                "kind",
                "original_contract_sha256",
                "dataset_hash",
                "index_sha256",
                "selected_target_keys",
                "target_identities",
                "scheduled_dates",
                "calendar_grid_sha256",
                "columns",
                "packed",
                "row_counts",
                "logical_record_sha256",
                "logical_digest_encoding",
                "producer",
                "original_input_bindings_sha256",
                "original_input_binding_count",
                "source_binding_count",
                "source_binding_scope",
                "original_sources_before_after_equal",
                "scope",
                "limitations",
            }
            and type(manifest["dataset_hash"]) is str
            and _PIN.fullmatch(manifest["dataset_hash"])
            and type(manifest["index_sha256"]) is str
            and _PIN.fullmatch(manifest["index_sha256"])
            and type(manifest["source_binding_count"]) is int
            and manifest["source_binding_count"] > 0
            and manifest["source_binding_scope"] == _SOURCE_SCOPE
            and type(manifest["original_input_binding_count"]) is int
            and manifest["original_input_binding_count"] == 3044
            and type(manifest["original_input_bindings_sha256"]) is str
            and _PIN.fullmatch(manifest["original_input_bindings_sha256"])
            and set(manifest["producer"]) == {"path", "sha256"}
            and manifest["producer"]["path"] == "src/thericher_v2/data/kis_broad_d1_compact.py"
            and type(manifest["producer"]["sha256"]) is str
            and _PIN.fullmatch(manifest["producer"]["sha256"])
            and manifest["logical_digest_encoding"] == _DIGEST_ENCODING
            and manifest["kind"] == _KIND
            and manifest["original_contract_sha256"] == _ORIGINAL
            and manifest["calendar_grid_sha256"] == _GRID
            and manifest["columns"] == list(_COLUMNS)
            and manifest["limitations"] == list(_LIMITATIONS)
            and manifest["original_sources_before_after_equal"] is True
            and manifest["scope"]
            == {
                "price_adjustment_applied": False,
                "date_crop_only": True,
                "no_key_filter_or_replacement": True,
                "sparse_and_empty_keys_preserved": True,
            },
            "compact_binding_invalid",
        )
        keys = _keys(tuple(manifest["selected_target_keys"]))
        identities = manifest["target_identities"]
        _require(
            set(identities) == set(keys)
            and all(
                set(identities[key]) == {"symbol", "exchange"}
                and all(type(value) is str for value in identities[key].values())
                and KisPaperDailyBroadRegistryTarget(**identities[key]).key == key
                for key in keys
            ),
            "compact_binding_invalid",
        )
        dates = _dates(tuple(date.fromisoformat(value) for value in manifest["scheduled_dates"]))
        counts, digests, info = (
            manifest[name] for name in ("row_counts", "logical_record_sha256", "packed")
        )
        _require(
            set(counts) == set(digests) == set(keys)
            and all(type(value) is int and 0 <= value <= 800 for value in counts.values())
            and all(type(value) is str and _PIN.fullmatch(value) for value in digests.values())
            and info["path"] == "bars.csv.gz"
            and type(info["row_count"]) is int
            and info["row_count"] == sum(counts.values())
            and type(info["size_bytes"]) is int
            and info["size_bytes"] > 0
            and type(info["sha256"]) is str
            and _PIN.fullmatch(info["sha256"]),
            "compact_binding_invalid",
        )
        packed_path = _location(
            path.parent / info["path"], market_root=market_root, repo_root=repo_root
        )
        packed = storage._read(packed_path)
        _require(
            len(packed) == info["size_bytes"] and storage.digest(packed) == info["sha256"],
            "compact_binding_invalid",
        )
        bars = {key: [] for key in keys}
        records = {key: [] for key in keys}
        allowed = set(dates)
        previous = None
        with gzip.GzipFile(fileobj=io.BytesIO(packed), mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                _require(tuple(reader.fieldnames or ()) == _COLUMNS, "compact_contents_invalid")
                for row in reader:
                    _require(
                        set(row) == set(_COLUMNS)
                        and all(type(value) is str for value in row.values())
                        and row["target_key"] in bars,
                        "compact_contents_invalid",
                    )
                    key = row.pop("target_key")
                    bar = bar_from_record(row)
                    _require(
                        _bar_record(identities[key], bar) == row and bar.start_ts.date() in allowed,
                        "compact_contents_invalid",
                    )
                    ordering = key, bar.start_ts
                    _require(previous is None or previous < ordering, "compact_contents_invalid")
                    previous = ordering
                    bars[key].append(bar)
                    records[key].append(row)
                    _require(len(bars[key]) <= counts[key], "compact_contents_invalid")
        _require(
            all(
                len(bars[key]) == counts[key]
                and _record_digest(tuple(records[key])) == digests[key]
                for key in keys
            ),
            "compact_contents_invalid",
        )
        _require(
            storage._read(path) == raw and storage._read(packed_path) == packed,
            "compact_binding_invalid",
        )
        return KisBroadD1CompactInput(
            path,
            expected_manifest_sha256,
            packed_path,
            info["sha256"],
            _ORIGINAL,
            manifest["dataset_hash"],
            keys,
            dates,
            MappingProxyType({key: tuple(values) for key, values in bars.items()}),
            MappingProxyType(dict(digests)),
        )
    except KisBroadD1CompactUnavailable:
        raise
    except (OSError, EOFError, ArithmeticError, ValueError, TypeError, KeyError, csv.Error):
        raise KisBroadD1CompactUnavailable("compact_contents_invalid") from None
