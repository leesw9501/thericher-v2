from __future__ import annotations

import csv
import gzip
import io
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

import pandas_market_calendars as pmc
import pytest

from test_kis_broad_d1_explicit_keys import _fixture
from thericher_v2.data import kis_broad_d1_compact as compact
from thericher_v2.data import kis_broad_d1_explicit_keys as explicit
from thericher_v2.data.local import CSV_FIELDS, bar_to_record


@pytest.fixture(scope="module")
def dates():
    schedule = pmc.get_calendar("NYSE").schedule(start_date="2023-05-17", end_date="2026-07-27")
    return tuple(value.date() for value in schedule.index)


@pytest.fixture
def setup(tmp_path, monkeypatch, dates):
    args = _fixture(tmp_path, monkeypatch)
    args["calendar_path"].write_bytes(
        compact._encode({"session_dates": [day.isoformat() for day in dates]})
    )
    metadata = explicit.bind_kis_broad_d1_explicit_keys(**args)
    market = tmp_path / "market-data"
    return dict(
        metadata=metadata,
        scheduled_dates=dates,
        original_contract_sha256=compact._ORIGINAL,
        original_input_bindings_sha256="sha256:" + "a" * 64,
        output_root=market / compact._PREFIX / "synthetic-v1",
        repo_root=args["repo_root"],
        market_root=market,
    )


def _write(setup):
    return compact.materialize_kis_broad_d1_compact(**setup)


def _load(result, setup, *, pin=None):
    return compact.load_kis_broad_d1_compact(
        result.manifest_path,
        expected_manifest_sha256=result.manifest_sha256 if pin is None else pin,
        repo_root=setup["repo_root"],
        market_root=setup["market_root"],
    )


def _repack(result, change, *, columns=compact._COLUMNS):
    rows = list(
        csv.DictReader(io.StringIO(gzip.decompress(result.packed_path.read_bytes()).decode()))
    )
    rows = change(rows)
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = gzip.compress(text.getvalue().encode(), mtime=0)
    result.packed_path.write_bytes(raw)
    manifest = compact._document(result.manifest_path.read_bytes())
    manifest["packed"]["sha256"] = compact.storage.digest(raw)
    manifest["packed"]["size_bytes"] = len(raw)
    encoded = compact._encode(manifest)
    result.manifest_path.write_bytes(encoded)
    return compact.storage.digest(encoded)


def test_roundtrip_real_synthetic_loader_and_empty_keys(setup):
    originals = explicit.load_kis_broad_d1_explicit_keys(setup["metadata"])
    before = {info.path: info.path.read_bytes() for info in originals.source_bindings_after}
    result = _write(setup)
    loaded = _load(result, setup)
    assert loaded.selected_target_keys == setup["metadata"].selected_target_keys
    assert len(loaded.bars_by_target) == 8
    assert sum(len(rows) for rows in loaded.bars_by_target.values()) == 2
    assert sum(not rows for rows in loaded.bars_by_target.values()) == 6
    for key, rows in loaded.bars_by_target.items():
        assert tuple(bar_to_record(bar) for bar in rows) == tuple(
            bar_to_record(bar) for bar in originals.bars_by_target[key]
        )
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert "bars_by_target" not in repr(loaded)
    assert "close" not in loaded.safe_facts()
    assert loaded.scheduled_dates == setup["scheduled_dates"]
    manifest = compact._document(loaded.manifest_path.read_bytes())
    assert manifest["original_input_bindings_sha256"] == setup["original_input_bindings_sha256"]
    assert manifest["original_input_binding_count"] == 3044
    assert manifest["producer"]["sha256"] == compact.storage.digest(
        Path(compact.__file__).read_bytes()
    )
    with pytest.raises(TypeError):
        loaded.bars_by_target["EXTRA/NAS"] = ()


def test_exact_128_preserved_including_empty_streams(setup, monkeypatch):
    original = explicit.load_kis_broad_d1_explicit_keys(setup["metadata"])
    extra = tuple("Z" + chr(65 + i // 26) + chr(65 + i % 26) + "/NAS" for i in range(120))
    keys = tuple(sorted((*original.bars_by_target, *extra)))
    metadata = replace(setup["metadata"], selected_target_keys=keys)
    documents = explicit._document(metadata._targets_document)
    prototype = documents["targets"][0]
    documents["targets"] = sorted(
        [
            *documents["targets"],
            *(
                dict(prototype, target_key=key, symbol=key[:-4], exchange="NAS", chunks=[])
                for key in extra
            ),
        ],
        key=lambda item: item["target_key"],
    )
    metadata = replace(metadata, _targets_document=compact._encode(documents))
    rows = {key: original.bars_by_target.get(key, ()) for key in keys}
    value = replace(original, metadata=metadata, bars_by_target=MappingProxyType(rows))
    monkeypatch.setattr(explicit, "load_kis_broad_d1_explicit_keys", lambda _: value)
    result = _write(dict(setup, metadata=metadata))
    assert (
        len(result.bars_by_target) == 128
        and sum(not values for values in result.bars_by_target.values()) == 126
    )
    assert tuple(result.bars_by_target) == keys


def test_crop_only_declared_dates_and_preserve_decimal_strings(setup, monkeypatch):
    original = explicit.load_kis_broad_d1_explicit_keys(setup["metadata"])
    rows = dict(original.bars_by_target)
    key = next(key for key, values in rows.items() if values)
    bar = rows[key][0]
    exact = replace(
        bar,
        open=Decimal("100.0012300"),
        high=Decimal("102.0000000"),
        low=Decimal("99.0000000"),
        close=Decimal("101.0000450"),
        volume=Decimal("1000.00000"),
    )
    rows[key] = (
        replace(exact, start_ts=datetime(2023, 5, 16, tzinfo=UTC)),
        exact,
        replace(exact, start_ts=datetime(2026, 7, 28, tzinfo=UTC)),
    )
    value = replace(original, bars_by_target=MappingProxyType(rows))
    monkeypatch.setattr(explicit, "load_kis_broad_d1_explicit_keys", lambda _: value)
    with localcontext() as context:
        context.prec = 4
        result = _write(setup)
    assert len(result.bars_by_target[key]) == 1
    assert bar_to_record(result.bars_by_target[key][0]) == bar_to_record(exact)


def test_deterministic_gzip_and_existing_schema(setup):
    first = _write(setup)
    second = _write(dict(setup, output_root=setup["output_root"].with_name("synthetic-v2")))
    assert first.packed_path.read_bytes() == second.packed_path.read_bytes()
    assert first.packed_path.read_bytes()[4:8] == bytes(4)
    header = gzip.decompress(first.packed_path.read_bytes()).decode().splitlines()[0]
    assert header.split(",") == ["target_key", *CSV_FIELDS]


def test_existing_source_key_validator_not_new_symbol_grammar():
    keys = ("A-B/NAS", "ABCDEF/NAS")
    assert all(explicit.panel._is_target_key(key) for key in keys)
    assert compact._keys(keys) == keys


@pytest.mark.parametrize("kind", ["repo", "artifact", "outside", "wrong_subdir"])
def test_output_guard_before_numeric_access(setup, monkeypatch, kind):
    monkeypatch.setattr(
        explicit, "load_kis_broad_d1_explicit_keys", lambda _: pytest.fail("numeric read")
    )
    root = {
        "repo": setup["repo_root"] / "private",
        "artifact": setup["repo_root"].parent / "artifacts/output",
        "outside": setup["market_root"].parent / "outside",
        "wrong_subdir": setup["market_root"] / "wrong",
    }[kind]
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_scope_invalid"):
        _write(dict(setup, output_root=root))
    assert not root.exists()


def test_resolved_output_escape_rejected_before_numeric_access(setup, monkeypatch):
    original = Path.resolve

    def escape(path, *args, **kwargs):
        if path == setup["output_root"]:
            return setup["repo_root"] / "escaped-private"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", escape)
    monkeypatch.setattr(
        explicit, "load_kis_broad_d1_explicit_keys", lambda _: pytest.fail("numeric read")
    )
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_scope_invalid"):
        _write(setup)


@pytest.mark.parametrize("kind", ["short", "duplicate", "wrong_start", "datetime", "wrong_pin"])
def test_scope_rejected_before_loading(setup, monkeypatch, kind):
    monkeypatch.setattr(
        explicit, "load_kis_broad_d1_explicit_keys", lambda _: pytest.fail("numeric read")
    )
    values = setup["scheduled_dates"]
    if kind == "short":
        values = values[:-1]
    elif kind == "duplicate":
        values = (values[0], *values[:-1])
    elif kind == "wrong_start":
        values = (date(2023, 5, 16), *values[1:])
    elif kind == "datetime":
        values = (datetime(2023, 5, 17, tzinfo=UTC), *values[1:])
    args = dict(setup, scheduled_dates=values)
    if kind == "wrong_pin":
        args["original_contract_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_scope_invalid"):
        _write(args)


def test_no_overwrite_of_compact_outputs(setup):
    result = _write(setup)
    before = result.manifest_path.read_bytes(), result.packed_path.read_bytes()
    with pytest.raises(compact.KisBroadD1CompactUnavailable):
        _write(setup)
    assert before == (result.manifest_path.read_bytes(), result.packed_path.read_bytes())


@pytest.mark.parametrize("kind", ["gzip", "manifest", "wrong_pin"])
def test_pinned_bytes_mutation_rejected(setup, kind):
    result = _write(setup)
    if kind == "gzip":
        result.packed_path.write_bytes(result.packed_path.read_bytes() + b" ")
    elif kind == "manifest":
        result.manifest_path.write_bytes(result.manifest_path.read_bytes() + b" ")
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_binding_invalid"):
        _load(result, setup, pin="sha256:" + "0" * 64 if kind == "wrong_pin" else None)


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "order",
        "unknown",
        "symbol",
        "market",
        "timeframe",
        "future",
        "nonmidnight",
        "decimal",
        "complete",
        "changed_value",
    ],
)
def test_hash_consistent_malformed_rows_reject(setup, kind):
    result = _write(setup)

    def change(rows):
        if kind == "duplicate":
            return [rows[0], *rows]
        if kind == "order":
            return list(reversed(rows))
        field, value = {
            "unknown": ("target_key", "ZZZZZ/NAS"),
            "symbol": ("symbol", "WRONG"),
            "market": ("market", "KR"),
            "timeframe": ("timeframe", "1m"),
            "future": ("start_ts", "2026-07-28T00:00:00+00:00"),
            "nonmidnight": ("start_ts", "2026-07-27T01:00:00+00:00"),
            "decimal": ("open", "fake_secret"),
            "complete": ("complete", "false"),
            "changed_value": ("volume", "999"),
        }[kind]
        rows[0][field] = value
        return rows

    pin = _repack(result, change)
    with pytest.raises(compact.KisBroadD1CompactUnavailable) as caught:
        _load(result, setup, pin=pin)
    assert "fake_secret" not in str(caught.value)


@pytest.mark.parametrize("kind", ["lost_empty", "count_bool", "unknown_field", "claim", "digest"])
def test_manifest_consistency_rejects_even_with_new_hash(setup, kind):
    result = _write(setup)
    manifest = compact._document(result.manifest_path.read_bytes())
    empty = next(key for key, count in manifest["row_counts"].items() if count == 0)
    if kind == "lost_empty":
        manifest["selected_target_keys"].remove(empty)
    elif kind == "count_bool":
        manifest["row_counts"][empty] = False
    elif kind == "unknown_field":
        manifest["unapproved"] = "field"
    elif kind == "claim":
        manifest["scope"]["price_adjustment_applied"] = True
    else:
        manifest["logical_record_sha256"][empty] = "sha256:" + "0" * 64
    raw = compact._encode(manifest)
    result.manifest_path.write_bytes(raw)
    with pytest.raises(compact.KisBroadD1CompactUnavailable):
        _load(result, setup, pin=compact.storage.digest(raw))


@pytest.mark.parametrize(
    "columns", [tuple(reversed(compact._COLUMNS)), (*compact._COLUMNS, "extra")]
)
def test_noncanonical_headers_reject(setup, columns):
    result = _write(setup)
    pin = _repack(result, lambda rows: rows, columns=columns)
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_contents_invalid"):
        _load(result, setup, pin=pin)


def test_original_source_fault_categorical_and_no_output(setup, monkeypatch):
    def fail(_):
        raise explicit.KisBroadD1ExplicitKeysUnavailable("source_hash_changed")

    monkeypatch.setattr(explicit, "load_kis_broad_d1_explicit_keys", fail)
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_source_invalid"):
        _write(setup)
    assert not setup["output_root"].exists()


def test_original_bytes_changed_during_publication_cannot_return_usable(setup, monkeypatch):
    original = compact.load_kis_broad_d1_compact

    def drift(*args, **kwargs):
        result = original(*args, **kwargs)
        path = setup["metadata"].chunks[0].raw.path
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(compact, "load_kis_broad_d1_compact", drift)
    with pytest.raises(compact.KisBroadD1CompactUnavailable, match="compact_source_invalid"):
        _write(setup)


def test_compact_reader_never_reopens_original_sources(setup, monkeypatch):
    result = _write(setup)
    monkeypatch.setattr(
        explicit, "load_kis_broad_d1_explicit_keys", lambda _: pytest.fail("original source")
    )
    original = Path.read_bytes
    allowed = {result.manifest_path, result.packed_path}

    def only_outputs(path):
        assert path in allowed
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", only_outputs)
    assert _load(result, setup).bars_by_target == result.bars_by_target
