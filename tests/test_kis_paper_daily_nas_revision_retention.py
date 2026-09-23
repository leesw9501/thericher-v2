from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from test_kis_paper_daily_nas_forward_cache import (
    _assert_source_safe,
    _row,
    _rows_for_all,
    _sessions,
)
from thericher_v2.data import kis_paper_daily_nas_forward_cache as forward_cache
from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KisPaperDailyNasForwardCacheError,
    KisPaperDailyNasForwardRow,
    KisPaperDailyNasForwardRun,
    commit_kis_paper_daily_nas_forward_observation,
    get_kis_paper_daily_nas_forward_failure_details,
    load_kis_paper_daily_nas_revision_as_of,
    load_verified_kis_paper_daily_nas_forward_cache,
)

_OBSERVED = datetime(2026, 7, 30, tzinfo=UTC)
_REASON = "daily_retained_revision_conflict"


@pytest.fixture(autouse=True)
def _offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("NAS revision tests must stay offline")

    monkeypatch.setattr(socket, "create_connection", unexpected)
    monkeypatch.setattr(socket.socket, "connect", unexpected)


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    return tmp_path / "external" / "forward", repo


def _commit(
    roots: tuple[Path, Path],
    rows: dict[str, tuple[KisPaperDailyNasForwardRow, ...]],
    *,
    failures: dict[str, str] | None = None,
    **kwargs: object,
) -> KisPaperDailyNasForwardRun:
    options: dict[str, object] = {"retain_revisions": True, "observed_at": _OBSERVED}
    options.update(kwargs)
    return commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows,
        failure_reasons_by_symbol=failures or {},
        cache_root=roots[0],
        repo_root=roots[1],
        **options,
    )


def _incoming(
    *, symbols: tuple[str, ...] = ("AAPL",), append: bool = True,
) -> dict[str, tuple[KisPaperDailyNasForwardRow, ...]]:
    rows = _rows_for_all(_sessions(27, 28, 29) if append else _sessions(27, 28))
    for symbol in symbols:
        original = rows[symbol][0]
        rows[symbol] = (
            _row(symbol, original.session_date, close=original.close + 50),
            *rows[symbol][1:],
        )
    return rows


def _index(roots: tuple[Path, Path]) -> dict:
    return json.loads((roots[0] / "index.json").read_bytes())


def _files(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _seed_revision(roots: tuple[Path, Path]) -> KisPaperDailyNasForwardRun:
    _commit(roots, _rows_for_all(_sessions(27, 28)))
    return _commit(roots, _incoming())


@pytest.mark.parametrize("symbols", [("AAPL",), KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS])
@pytest.mark.parametrize("append", [False, True])
def test_retains_full_revision_without_replacing_original_values_or_bytes(
    roots: tuple[Path, Path], symbols: tuple[str, ...], append: bool,
) -> None:
    first = _commit(roots, _rows_for_all(_sessions(27, 28)))
    original_index = _index(roots)
    original_snapshots = _files(roots[0] / "snapshots")
    incoming = _incoming(symbols=symbols, append=append)
    started = datetime.now(UTC)

    run = _commit(roots, incoming)

    ended = datetime.now(UTC)
    index = _index(roots)
    assert run.accepted_page_count == 6
    assert run.categorical_failure_count == len(symbols)
    assert run.changed_target_count == (6 if append else 0)
    assert run.status == ("deferred" if len(symbols) == 6 else "partial")
    assert run.prospective_input_status == "input_unavailable"
    assert run.recovery == "resume"
    assert run.cache.retained_revision_snapshot_count == len(symbols)
    assert run.cache.index_hash == _hash((roots[0] / "index.json").read_bytes())
    assert run.cache.cache_hash != first.cache.cache_hash
    for relative, content in original_snapshots.items():
        assert (roots[0] / "snapshots" / relative).read_bytes() == content
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        assert run.cache.rows_by_symbol[symbol][:2] == first.cache.rows_by_symbol[symbol]
        if append:
            assert run.cache.rows_by_symbol[symbol][-1] == incoming[symbol][-1]
        target = run.cache.targets_by_key[f"{symbol}/NAS"]
        assert target.status == ("deferred" if symbol in symbols else "ready")
        assert target.last_reason == (_REASON if symbol in symbols else None)
        assert target.accepted_page_count == 2
    for record in index["retained_revisions"]:
        symbol = record["symbol"]
        recorded = datetime.fromisoformat(record["recorded_at"])
        assert started <= recorded <= ended
        assert recorded >= run.observed_at
        assert record["prior_target"] == next(
            target for target in original_index["targets"]
            if target["target_key"] == f"{symbol}/NAS"
        )
        snapshot = roots[0] / record["snapshot_path"]
        assert snapshot.resolve().is_relative_to(roots[0].resolve())
        assert not snapshot.resolve().is_relative_to(roots[1].resolve())
        payload = snapshot.read_bytes()
        assert _hash(payload) == record["snapshot_sha256"]
        assert list(csv.reader(io.StringIO(gzip.decompress(payload).decode())))[1:] == [
            list(row.raw_record()) for row in incoming[symbol]
        ]
        expected_rows = "\n".join("\x1f".join(row.raw_record()) for row in incoming[symbol])
        assert record["rows_sha256"] == _hash(expected_rows.encode())
        assert record["row_count"] == len(incoming[symbol])
        assert record["revised_row_count"] == 1
    payload = run.safe_payload()
    _assert_source_safe(payload)
    assert payload["cache"]["canonical_revision_policy"] == "first_retained_not_point_in_time"
    assert payload["cache"]["retained_revision_snapshot_count"] == len(symbols)
    encoded = json.dumps(payload)
    assert "snapshot_path" not in encoded
    assert "prior_target" not in encoded
    assert "recorded_at" not in encoded
    assert "session_date" not in encoded
    assert str(roots[0]) not in encoded
    assert payload["target_failures"] == [
        {
            "failure_stage": "overlap_reconciliation",
            "failure_category": "duplicate_conflict",
            "failure_symbol": symbol,
        }
        for symbol in symbols
    ]
    loaded = load_verified_kis_paper_daily_nas_forward_cache(
        cache_root=roots[0], repo_root=roots[1],
    )
    assert loaded.cache_hash == run.cache.cache_hash
    assert loaded.rows_by_symbol == run.cache.rows_by_symbol


def test_identical_revision_retry_keeps_first_timestamp_snapshot_and_prior_target(
    roots: tuple[Path, Path],
) -> None:
    first = _seed_revision(roots)
    revisions = _index(roots)["retained_revisions"]
    snapshots = _files(roots[0] / "snapshots")

    second = _commit(roots, _incoming(), observed_at=datetime.now(UTC) + timedelta(days=1))

    assert _index(roots)["retained_revisions"] == revisions
    assert _files(roots[0] / "snapshots") == snapshots
    assert second.cache.retained_revision_snapshot_count == 1
    assert second.changed_target_count == 0
    assert second.accepted_page_count == 6
    assert second.cache.rows_by_symbol == first.cache.rows_by_symbol
    assert second.cache.targets_by_key["AAPL/NAS"].last_reason == _REASON


@pytest.mark.parametrize("layout", ["reverse", "identical_duplicate"])
def test_revision_retention_accepts_existing_api_order_and_identical_duplicate_semantics(
    roots: tuple[Path, Path], layout: str,
) -> None:
    _commit(roots, _rows_for_all(_sessions(27, 28)))
    rows = _incoming()
    expected = rows["AAPL"]
    rows["AAPL"] = expected[::-1] if layout == "reverse" else (*expected, expected[0])

    run = _commit(roots, rows)

    assert run.cache.retained_revision_snapshot_count == 1
    assert run.cache.targets_by_key["AAPL/NAS"].last_reason == _REASON
    loaded = load_verified_kis_paper_daily_nas_forward_cache(
        cache_root=roots[0], repo_root=roots[1],
    )
    assert loaded.cache_hash == run.cache.cache_hash
    retried = _commit(roots, _incoming())
    assert retried.cache.retained_revision_snapshot_count == 1


@pytest.mark.parametrize("surface", ["revision", "prior"])
@pytest.mark.parametrize("fault", ["corrupt", "missing"])
def test_missing_or_corrupt_revision_evidence_rejects_load_and_commit_before_rewrite(
    roots: tuple[Path, Path], surface: str, fault: str,
) -> None:
    _seed_revision(roots)
    record = _index(roots)["retained_revisions"][0]
    evidence = record if surface == "revision" else record["prior_target"]
    path = roots[0] / evidence["snapshot_path"]
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"synthetic-corrupted-snapshot")
    _assert_rejected_without_rewrite(roots)


@pytest.mark.parametrize(
    "fault",
    [
        "records_not_list", "duplicate_record", "extra_field", "missing_field",
        "row_count", "boolean_count", "revised_count", "rows_hash", "snapshot_hash",
        "naive_recorded_at", "invalid_recorded_at", "wrong_symbol", "prior_target",
        "path_escape", "prior_rows_hash", "revised_target_ready", "unbound_reason",
    ],
)
def test_revision_index_schema_and_hash_tamper_rejected_before_rewrite(
    roots: tuple[Path, Path], fault: str,
) -> None:
    _seed_revision(roots)
    index = _index(roots)
    record = index["retained_revisions"][0]
    if fault == "records_not_list":
        index["retained_revisions"] = {}
    elif fault == "duplicate_record":
        index["retained_revisions"].append(dict(record))
    elif fault == "extra_field":
        record["raw_rows"] = []
    elif fault == "missing_field":
        record.pop("prior_target")
    elif fault == "row_count":
        record["row_count"] += 1
    elif fault == "boolean_count":
        record["revised_row_count"] = True
    elif fault == "revised_count":
        record["revised_row_count"] += 1
    elif fault in {"rows_hash", "snapshot_hash"}:
        record["rows_sha256" if fault == "rows_hash" else "snapshot_sha256"] = "sha256:" + "0" * 64
    elif fault == "naive_recorded_at":
        record["recorded_at"] = "2026-07-30T00:00:00"
    elif fault == "invalid_recorded_at":
        record["recorded_at"] = None
    elif fault == "wrong_symbol":
        record["symbol"] = "MSFT"
    elif fault == "prior_target":
        record["prior_target"] = dict(index["targets"][1])
    elif fault == "path_escape":
        record["snapshot_path"] = "../outside.csv.gz"
    elif fault == "prior_rows_hash":
        record["prior_target"]["rows_sha256"] = "sha256:" + "0" * 64
    elif fault == "revised_target_ready":
        index["targets"][0]["status"] = "ready"
        index["targets"][0]["last_reason"] = None
    elif fault == "unbound_reason":
        index.pop("retained_revisions")
    (roots[0] / "index.json").write_text(json.dumps(index), encoding="utf-8")
    _assert_rejected_without_rewrite(roots)


def test_rehashed_revision_with_wrong_exchange_is_not_accepted_as_nas(
    roots: tuple[Path, Path],
) -> None:
    _seed_revision(roots)
    index = _index(roots)
    record = index["retained_revisions"][0]
    snapshot = roots[0] / record["snapshot_path"]
    rows = list(csv.reader(io.StringIO(gzip.decompress(snapshot.read_bytes()).decode())))
    rows[1][1] = "AMS"
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    payload = gzip.compress(buffer.getvalue().encode(), mtime=0)
    snapshot.write_bytes(payload)
    record["snapshot_sha256"] = _hash(payload)
    (roots[0] / "index.json").write_text(json.dumps(index), encoding="utf-8")
    _assert_rejected_without_rewrite(roots)


def _assert_rejected_without_rewrite(roots: tuple[Path, Path]) -> None:
    before = _files(roots[0])
    with pytest.raises(KisPaperDailyNasForwardCacheError):
        load_verified_kis_paper_daily_nas_forward_cache(cache_root=roots[0], repo_root=roots[1])
    assert _files(roots[0]) == before
    with pytest.raises(KisPaperDailyNasForwardCacheError) as caught:
        _commit(roots, _rows_for_all(_sessions(27, 28, 29, 30)))
    assert get_kis_paper_daily_nas_forward_failure_details(caught.value)["failure_stage"] == (
        "verified_base_load"
    )
    assert _files(roots[0]) == before


def test_incoming_conflicting_duplicates_rejected_before_cache_access(
    roots: tuple[Path, Path],
) -> None:
    rows = _incoming()
    rows["AAPL"] += _rows_for_all(_sessions(27))["AAPL"]

    with pytest.raises(KisPaperDailyNasForwardCacheError) as caught:
        _commit(roots, rows)

    assert get_kis_paper_daily_nas_forward_failure_details(caught.value) == {
        "failure_stage": "observation_input",
        "failure_category": "duplicate_conflict",
    }
    assert not roots[0].exists()


def test_atomic_index_replace_failure_leaves_old_index_and_verified_load_intact(
    roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _commit(roots, _rows_for_all(_sessions(27, 28)))
    index_path = roots[0] / "index.json"
    original = index_path.read_bytes()
    original_snapshots = _files(roots[0] / "snapshots")
    error = OSError("synthetic-index-replace-failure")

    def fail_replace(source: Path, destination: Path) -> None:
        assert Path(destination) == index_path
        assert Path(source).is_file()
        loaded = load_verified_kis_paper_daily_nas_forward_cache(
            cache_root=roots[0], repo_root=roots[1],
        )
        assert loaded.cache_hash == first.cache.cache_hash
        raise error

    with monkeypatch.context() as scoped:
        scoped.setattr(forward_cache.os, "replace", fail_replace)
        with pytest.raises(OSError) as caught:
            _commit(roots, _incoming())
    assert caught.value is error
    assert get_kis_paper_daily_nas_forward_failure_details(error) == {
        "failure_stage": "cache_publish", "failure_category": "io_error",
    }
    assert index_path.read_bytes() == original
    for path, content in original_snapshots.items():
        assert (roots[0] / "snapshots" / path).read_bytes() == content
    loaded = load_verified_kis_paper_daily_nas_forward_cache(
        cache_root=roots[0], repo_root=roots[1],
    )
    assert loaded.cache_hash == first.cache.cache_hash
    assert loaded.rows_by_symbol == first.cache.rows_by_symbol
    assert loaded.retained_revision_snapshot_count == 0
    assert not list(roots[0].glob("*.stage"))
    assert _commit(roots, _incoming()).cache.retained_revision_snapshot_count == 1


@pytest.mark.parametrize("intervening_failure", [False, True])
@pytest.mark.parametrize("retain_revisions", [False, True])
def test_later_new_rows_cannot_clear_unresolved_revision_and_other_targets_continue(
    roots: tuple[Path, Path], intervening_failure: bool, retain_revisions: bool,
) -> None:
    first = _seed_revision(roots)
    revisions = _index(roots)["retained_revisions"]
    if intervening_failure:
        rows = _rows_for_all(_sessions(27, 28, 29))
        rows.pop("AAPL")
        _commit(roots, rows, failures={"AAPL": "transport_failure"})
    rows = {
        symbol: values[-1:]
        for symbol, values in _rows_for_all(_sessions(27, 28, 29, 30)).items()
    }

    run = _commit(roots, rows, retain_revisions=retain_revisions)

    assert run.status == "partial"
    assert run.recovery == "resume"
    assert run.accepted_page_count == 6
    assert run.categorical_failure_count == 0
    assert run.changed_target_count == 6
    assert run.prospective_input_status == "input_unavailable"
    assert _index(roots)["retained_revisions"] == revisions
    assert "target_failures" not in run.safe_payload()
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        assert run.cache.rows_by_symbol[symbol][:-1] == first.cache.rows_by_symbol[symbol]
        assert run.cache.rows_by_symbol[symbol][-1] == rows[symbol][0]
        target = run.cache.targets_by_key[f"{symbol}/NAS"]
        assert target.status == ("deferred" if symbol == "AAPL" else "ready")
        assert target.last_reason == (_REASON if symbol == "AAPL" else None)


def test_target_failures_do_not_relabel_a_historical_revision_as_current_fetch_failure(
    roots: tuple[Path, Path],
) -> None:
    _seed_revision(roots)
    rows = _rows_for_all(_sessions(27, 28, 29, 30))
    rows.pop("MSFT")

    run = _commit(roots, rows, failures={"MSFT": "transport_failure"})

    assert run.categorical_failure_count == 1
    assert run.overlap_conflict_symbols == ()
    assert run.cache.targets_by_key["AAPL/NAS"].last_reason == _REASON
    assert run.safe_payload()["target_failures"] == [{
        "failure_stage": "target_fetch",
        "failure_category": "transport_failure",
        "failure_symbol": "MSFT",
    }]


@pytest.mark.parametrize("explicit_false", [False, True])
def test_default_and_explicit_false_preserve_strict_overlap_behavior(
    roots: tuple[Path, Path], explicit_false: bool,
) -> None:
    first = _commit(roots, _rows_for_all(_sessions(27, 28)), retain_revisions=False)
    previous = _index(roots)["targets"][0]
    options = {"retain_revisions": False} if explicit_false else {}

    run = commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=_incoming(), failure_reasons_by_symbol={},
        cache_root=roots[0], repo_root=roots[1], observed_at=_OBSERVED, **options,
    )

    assert run.cache.rows_by_symbol["AAPL"] == first.cache.rows_by_symbol["AAPL"]
    assert run.cache.targets_by_key["AAPL/NAS"].last_reason == "daily_duplicate_conflict"
    assert run.cache.targets_by_key["MSFT/NAS"].row_count == 3
    assert run.accepted_page_count == 5
    assert run.categorical_failure_count == 1
    assert run.changed_target_count == 5
    assert run.cache.retained_revision_snapshot_count == 0
    assert "retained_revisions" not in _index(roots)
    assert _index(roots)["targets"][0]["snapshot_path"] == previous["snapshot_path"]


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_exact_revision_as_of_respects_recording_time_and_returns_whole_incoming_page(
    roots: tuple[Path, Path], offset: int,
) -> None:
    run = _seed_revision(roots)
    record = _index(roots)["retained_revisions"][0]
    recorded = datetime.fromisoformat(record["recorded_at"])
    before = _files(roots[0])
    options = {
        "cache_root": roots[0],
        "repo_root": roots[1],
        "symbol": "AAPL",
        "snapshot_sha256": record["snapshot_sha256"],
        "as_of": recorded + timedelta(microseconds=offset),
    }

    if offset < 0:
        with pytest.raises(KisPaperDailyNasForwardCacheError):
            load_kis_paper_daily_nas_revision_as_of(**options)
    else:
        rows = load_kis_paper_daily_nas_revision_as_of(**options)
        assert rows == _incoming()["AAPL"]
        assert rows[0] != run.cache.rows_by_symbol["AAPL"][0]
    assert _files(roots[0]) == before
    reloaded = load_verified_kis_paper_daily_nas_forward_cache(
        cache_root=roots[0], repo_root=roots[1],
    )
    assert reloaded.cache_hash == run.cache.cache_hash
    assert reloaded.targets_by_key["AAPL/NAS"].status == "deferred"
    assert reloaded.targets_by_key["AAPL/NAS"].last_reason == _REASON


@pytest.mark.parametrize("fault", ["wrong_symbol", "unknown_hash", "canonical_hash", "naive_time"])
def test_revision_as_of_rejects_wrong_identity_without_latest_or_canonical_fallback(
    roots: tuple[Path, Path], fault: str,
) -> None:
    _seed_revision(roots)
    index = _index(roots)
    record = index["retained_revisions"][0]
    options = {
        "cache_root": roots[0],
        "repo_root": roots[1],
        "symbol": "AAPL",
        "snapshot_sha256": record["snapshot_sha256"],
        "as_of": datetime.fromisoformat(record["recorded_at"]),
    }
    if fault == "wrong_symbol":
        options["symbol"] = "MSFT"
    elif fault == "unknown_hash":
        options["snapshot_sha256"] = "sha256:" + "0" * 64
    elif fault == "canonical_hash":
        options["snapshot_sha256"] = index["targets"][0]["snapshot_sha256"]
    elif fault == "naive_time":
        options["as_of"] = options["as_of"].replace(tzinfo=None)
    before = _files(roots[0])

    expected = ValueError if fault == "naive_time" else KisPaperDailyNasForwardCacheError
    with pytest.raises(expected):
        load_kis_paper_daily_nas_revision_as_of(**options)

    assert _files(roots[0]) == before
