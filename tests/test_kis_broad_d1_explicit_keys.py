from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import thericher_v2.data.kis_broad_d1_explicit_keys as explicit
import thericher_v2.data.kis_paper_daily_broad_panel as panel
from test_kis_paper_daily_broad_panel import (
    _assert_no_raw_fields,
    _deny_external_access,
    _json_bytes,
    _read_json,
    _write_broad_cache,
)


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    cache, repo = _write_broad_cache(tmp_path, monkeypatch)
    result = panel.materialize_kis_paper_daily_broad_panel(
        cache_root=cache,
        panel_root=tmp_path / "panel",
        artifact_root=tmp_path / "evidence",
        repo_root=repo,
    )
    calendar = tmp_path / "calendar.json"
    calendar.write_bytes(
        _json_bytes(
            {
                "session_dates": ["2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28"],
                "calendar_attestation": "synthetic_only",
            }
        )
    )
    _deny_external_access(monkeypatch)
    return {
        "manifest_path": result.manifest_path,
        "materialization_receipt_path": result.receipt_path,
        "calendar_path": calendar,
        "cache_root": cache,
        "panel_root": tmp_path / "panel",
        "repo_root": repo,
    }


def _bind(args: dict[str, object], **kwargs: object) -> explicit.KisBroadD1ExplicitKeysMetadata:
    return explicit.bind_kis_broad_d1_explicit_keys(**args, **kwargs)


def _republish_metadata(args: dict[str, object], payload: dict[str, object]) -> None:
    registry = explicit.load_kis_paper_daily_broad_registry(
        output_root=args["cache_root"],
        repo_root=args["repo_root"],
    )
    summaries = panel._target_summaries_from_manifest(payload, registry=registry)
    payload["dataset"]["dataset_hash"] = panel._dataset_hash(
        index_sha256=payload["source"]["index_sha256"],
        registry=registry,
        snapshot=payload["source_snapshot"],
        targets=summaries,
    )
    args["manifest_path"].write_bytes(_json_bytes(payload))
    receipt = _read_json(args["materialization_receipt_path"])
    receipt["manifest_sha256"] = panel._sha256(args["manifest_path"].read_bytes())
    receipt["coverage"] = payload["coverage"]
    args["materialization_receipt_path"].write_bytes(_json_bytes(receipt))


def _overlap(args: dict[str, object], *, conflicting: bool) -> str:
    payload = _read_json(args["manifest_path"])
    target = next(t for t in payload["source_snapshot"]["targets"] if t["chunks"])
    chunk = target["chunks"][0]
    old_path = args["cache_root"] / chunk["manifest_ref"]
    manifest = _read_json(old_path)
    old_raw = old_path.parent / manifest["files"]["raw_daily_rows"]["path"]
    data = old_raw.read_bytes()
    if conflicting:
        import gzip

        data = gzip.compress(gzip.decompress(data).replace(b",101,", b",102,"), mtime=0)
    path = args["cache_root"] / "snapshot=synthetic-second" / "manifest.json"
    raw_path = path.parent / "raw" / "ohlcv_daily.csv.gz"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(data)
    raw = manifest["files"]["raw_daily_rows"]
    raw["sha256"], raw["size_bytes"] = panel._sha256(data), len(data)
    manifest["backfill"]["input_cursor_date"] = chunk["output_cursor_date"]
    path.write_bytes(_json_bytes(manifest))
    target["chunks"].append(
        {
            **chunk,
            "input_cursor_date": chunk["output_cursor_date"],
            "manifest_ref": path.relative_to(args["cache_root"]).as_posix(),
            "manifest_sha256": panel._sha256(path.read_bytes()),
            "raw_sha256": raw["sha256"],
            "outcome": "source_limited",
        }
    )
    target["state"] = "source_limited"
    target["accepted_page_count"] += chunk["accepted_page_count"]
    summary = next(t for t in payload["targets"] if t["target_key"] == target["target_key"])
    summary["state"] = "source_limited"
    summary["chunk_count"] += 1
    summary["accepted_page_count"] = target["accepted_page_count"]
    summary["outcome_counts"]["source_limited"] = 1
    _republish_metadata(args, payload)
    return target["target_key"]


def test_metadata_binding_never_opens_raw_or_loads_numeric_rows(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    original = Path.read_bytes

    def metadata_only(path):
        assert path.suffix != ".gz"
        assert path.name != "index.json"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", metadata_only)
    monkeypatch.setattr(panel, "_load_target_records", lambda **kw: pytest.fail("numeric load"))
    binding = _bind(args)
    assert len(binding.selected_target_keys) == 8
    assert binding.source_bindings_before == binding.source_bindings_after
    assert binding.record()["raw_bytes_reattested"] is False
    assert "raw_market" not in binding.record()
    _assert_no_raw_fields(binding.record())


def test_default_lexicographic_cap_is_before_coverage_and_keeps_zero_streams(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args, cap=4)
    assert binding.selected_target_keys == ("AAPL/NAS", "ADBE/NAS", "AMZN/NAS", "GOOGL/NAS")
    assert any(t.bar_count == 0 for t in binding.targets_by_key.values())
    loaded = explicit.load_kis_broad_d1_explicit_keys(binding)
    assert tuple(loaded.bars_by_target) == binding.selected_target_keys
    assert any(not rows for rows in loaded.bars_by_target.values())


def test_load_preserves_all_sparse_partial_and_empty_streams_without_common_grid(
    tmp_path, monkeypatch
):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    loaded = explicit.load_kis_broad_d1_explicit_keys(binding)
    assert len(loaded.bars_by_target) == 8
    assert sum(len(rows) for rows in loaded.bars_by_target.values()) == 2
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert loaded.source_bindings_before == loaded.source_bindings_after
    assert loaded.safe_facts()["raw_bytes_reattested"] is True
    for rows in loaded.bars_by_target.values():
        for bar in rows:
            assert bar.start_ts.isoformat() == "2026-07-27T00:00:00+00:00"
    assert "open=" not in repr(loaded)
    _assert_no_raw_fields(loaded.safe_facts())


def test_explicit_keys_are_preserved_without_substituting_covered_keys(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    all_keys = _bind(args)
    empty_key = next(k for k, t in all_keys.targets_by_key.items() if t.bar_count == 0)
    binding = _bind(args, selected_target_keys=(empty_key,))
    assert binding.selected_target_keys == (empty_key,)
    assert explicit.load_kis_broad_d1_explicit_keys(binding).bars_by_target == {empty_key: ()}


@pytest.mark.parametrize(
    "keys",
    [(), ["AAPL/NAS"], ("UNKNOWN/NAS",), ("AAPL/NAS", "AAPL/NAS"), ("GOOGL/NAS", "AAPL/NAS"), (1,)],
)
def test_rejects_invalid_explicit_keys(tmp_path, monkeypatch, keys):
    args = _fixture(tmp_path, monkeypatch)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="selected_keys_invalid"):
        _bind(args, selected_target_keys=keys)


@pytest.mark.parametrize("cap", [0, 129, True, 1.0])
def test_rejects_invalid_default_caps(tmp_path, monkeypatch, cap):
    args = _fixture(tmp_path, monkeypatch)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="selected_keys_invalid"):
        _bind(args, cap=cap)


@pytest.mark.parametrize(
    "dates",
    [[], ["2026-07-27", "2026-07-27"], ["2026-07-28", "2026-07-27"], ["2026-02-30"], [True]],
)
def test_calendar_date_keys_strict_without_provider_clock_inference(tmp_path, monkeypatch, dates):
    args = _fixture(tmp_path, monkeypatch)
    args["calendar_path"].write_bytes(_json_bytes({"session_dates": dates}))
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="calendar_invalid"):
        _bind(args)


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_metadata_keys_are_rejected_and_redacted(tmp_path, monkeypatch, nested):
    args = _fixture(tmp_path, monkeypatch)
    duplicate = '"ignored":{"key":1,"key":2}' if nested else '"key":1,"key":2'
    args["calendar_path"].write_text(
        '{"session_dates":["2026-07-27"],' + duplicate + "}",
        encoding="utf-8",
    )
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable) as error:
        _bind(args)
    assert str(error.value) == "metadata_invalid"


def test_mutable_live_index_is_not_a_dependency(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)
    (args["cache_root"] / "index.json").unlink()
    assert _bind(args) == binding
    assert len(explicit.load_kis_broad_d1_explicit_keys(binding).bars_by_target) == 8


@pytest.mark.parametrize(
    "field", ["manifest_path", "materialization_receipt_path", "calendar_path"]
)
def test_metadata_mutation_after_binding_cannot_load_prices(tmp_path, monkeypatch, field):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)
    path = args[field]
    path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(panel, "_load_target_records", lambda **kw: pytest.fail("numeric load"))
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="source_hash_changed"):
        explicit.load_kis_broad_d1_explicit_keys(binding)


def test_raw_hash_is_only_checked_at_explicit_numeric_load(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)
    raw = binding.chunks[0].raw.path
    raw.write_bytes(raw.read_bytes() + b"synthetic-sensitive")
    assert _bind(args) == binding
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable) as error:
        explicit.load_kis_broad_d1_explicit_keys(binding)
    assert str(error.value) == "selected_source_invalid"


def test_manifest_hash_mismatch_is_safe_before_numeric_loading(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)
    path = binding.chunks[0].manifest.path
    path.write_bytes(path.read_bytes() + b"synthetic-sensitive")
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable) as error:
        _bind(args)
    assert str(error.value) == "source_hash_changed"


def test_bound_metadata_cannot_be_replaced_with_different_key_identity(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = replace(_bind(args), selected_target_keys=("AAPL/NAS",))
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="source_hash_changed"):
        explicit.load_kis_broad_d1_explicit_keys(binding)


def test_exact_overlap_is_deduplicated_but_partial_identity_remains(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    key = _overlap(args, conflicting=False)
    binding = _bind(args, selected_target_keys=(key,))
    loaded = explicit.load_kis_broad_d1_explicit_keys(binding)
    assert binding.targets_by_key[key].state == "source_limited"
    assert len(loaded.bars_by_target[key]) == 1
    assert len(binding.chunks) == 2


def test_conflicting_overlap_is_not_last_wins_or_replaced(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    key = _overlap(args, conflicting=True)
    binding = _bind(args, selected_target_keys=(key,))
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="selected_source_invalid"):
        explicit.load_kis_broad_d1_explicit_keys(binding)


def test_after_numeric_read_hash_change_never_returns_a_usable_stream(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)
    original = panel._load_target_records
    changed = False

    def read_then_mutate(**kwargs):
        nonlocal changed
        result = original(**kwargs)
        if not changed:
            changed = True
            path = binding.chunks[0].raw.path
            path.write_bytes(path.read_bytes() + b"synthetic-sensitive")
        return result

    monkeypatch.setattr(panel, "_load_target_records", read_then_mutate)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable) as error:
        explicit.load_kis_broad_d1_explicit_keys(binding)
    assert "synthetic-sensitive" not in str(error.value)


def test_parser_exception_text_is_never_exposed(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    binding = _bind(args)

    def fail(**kwargs):
        raise ValueError("synthetic-sensitive-body")

    monkeypatch.setattr(panel, "_load_target_records", fail)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable) as error:
        explicit.load_kis_broad_d1_explicit_keys(binding)
    assert str(error.value) == "selected_source_invalid"


def test_hash_consistent_invalid_cursor_is_rejected_without_raw_decode(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    payload = _read_json(args["manifest_path"])
    target = next(t for t in payload["source_snapshot"]["targets"] if t["chunks"])
    target["chunks"][0]["input_cursor_date"] = "20260726"
    _republish_metadata(args, payload)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="metadata_invalid"):
        _bind(args)


def test_hash_consistent_declared_count_does_not_override_numeric_readback(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    payload = _read_json(args["manifest_path"])
    target = next(t for t in payload["targets"] if t["bar_count"])
    target["bar_count"] += 1
    _republish_metadata(args, payload)
    binding = _bind(args)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="selected_source_invalid"):
        explicit.load_kis_broad_d1_explicit_keys(binding)


def test_historical_unknown_revision_does_not_invent_an_attestation_gate(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    payload = _read_json(args["manifest_path"])
    target = next(t for t in payload["source_snapshot"]["targets"] if t["chunks"])
    chunk = target["chunks"][0]
    path = args["cache_root"] / chunk["manifest_ref"]
    manifest = _read_json(path)
    manifest["code_revision"] = "git:unknown"
    path.write_bytes(_json_bytes(manifest))
    chunk["manifest_sha256"] = panel._sha256(path.read_bytes())
    _republish_metadata(args, payload)
    binding = _bind(args)
    assert "historical_code_revision_unattested" in binding.record()["limitations"]
    assert explicit.load_kis_broad_d1_explicit_keys(binding).safe_facts()["raw_bytes_reattested"]


def test_hash_consistent_truncated_gzip_is_scoped_without_decoder_text(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    payload = _read_json(args["manifest_path"])
    target = next(t for t in payload["source_snapshot"]["targets"] if t["chunks"])
    chunk = target["chunks"][0]
    path = args["cache_root"] / chunk["manifest_ref"]
    manifest = _read_json(path)
    raw = manifest["files"]["raw_daily_rows"]
    raw_path = path.parent / raw["path"]
    data = raw_path.read_bytes()[:-6]
    raw_path.write_bytes(data)
    raw["sha256"], raw["size_bytes"] = panel._sha256(data), len(data)
    path.write_bytes(_json_bytes(manifest))
    chunk["manifest_sha256"] = panel._sha256(path.read_bytes())
    chunk["raw_sha256"] = raw["sha256"]
    _republish_metadata(args, payload)
    binding = _bind(args)
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable) as error:
        explicit.load_kis_broad_d1_explicit_keys(binding)
    assert str(error.value) == "selected_source_invalid"


def test_selected_quarantine_fails_scope_without_substitution(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    payload = _read_json(args["manifest_path"])
    target = next(t for t in payload["source_snapshot"]["targets"] if t["chunks"])
    target["chunks"][0]["outcome"] = "conflict"
    target["next_anchor_date"] = target["initial_anchor_date"]
    target["state"] = "deferred"
    summary = next(t for t in payload["targets"] if t["target_key"] == target["target_key"])
    summary["next_anchor_date"] = target["next_anchor_date"]
    summary["state"] = "deferred"
    summary["quarantined"] = True
    summary["outcome_counts"] = {"conflict": 1}
    payload["coverage"]["quarantined_target_count"] = 1
    _republish_metadata(args, payload)
    binding = _bind(args)
    assert target["target_key"] in binding.selected_target_keys
    with pytest.raises(
        explicit.KisBroadD1ExplicitKeysUnavailable, match="selected_source_conflict"
    ):
        explicit.load_kis_broad_d1_explicit_keys(binding)


def test_metadata_after_read_drift_is_detected_without_raw_loading(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    original = Path.read_bytes
    changed = False

    def read_then_change(path):
        nonlocal changed
        data = original(path)
        if path == args["manifest_path"] and not changed:
            changed = True
            path.write_bytes(data + b" ")
        return data

    monkeypatch.setattr(Path, "read_bytes", read_then_change)
    monkeypatch.setattr(panel, "_load_target_records", lambda **kw: pytest.fail("numeric load"))
    with pytest.raises(explicit.KisBroadD1ExplicitKeysUnavailable, match="source_hash_changed"):
        _bind(args)
