from __future__ import annotations

import dataclasses
import hashlib
import json
import socket
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_paper_daily_pair_forward_cache as cache
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KisPaperDailyPairForwardCacheError,
    KisPaperDailyPairForwardRow,
    load_kis_paper_daily_pair_observation_as_of,
    retain_kis_paper_daily_pair_forward_page,
)
from thericher_v2.execution import kis_paper_daily_pair_forward as collector
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
)

OBSERVED = datetime(2026, 7, 29, 21, tzinfo=UTC)
SESSIONS = (date(2026, 7, 23), date(2026, 7, 27), date(2026, 7, 29))


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        pytest.fail("observation tests cannot use network")
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "create_connection", reject)


def query() -> dict[str, str]:
    return {
        "endpoint": "/uapi/overseas-price/v1/quotations/dailyprice",
        "tr_id": "HHDFS76240000", "SYMB": "QQQ", "EXCD": "NAS", "GUBN": "0",
        "BYMD": "20260729", "MODP": "0", "continuation": "",
        "collector_source_sha256": "sha256:" + "a" * 64,
        "request_source_sha256": "sha256:" + "b" * 64,
    }


def rows() -> tuple[KisPaperDailyPairForwardRow, ...]:
    return tuple(KisPaperDailyPairForwardRow(
        symbol="QQQ", exchange="NAS", session_date=session,
        open=Decimal(100), high=Decimal(101), low=Decimal(99), close=Decimal(100),
        volume=Decimal(1000),
    ) for session in SESSIONS)


def retain(tmp_path: Path, **kwargs: object) -> dict[str, str]:
    options = dict(rows=rows(), query=query(), captured_at=OBSERVED,
                   observation_root=tmp_path / "observations", repo_root=tmp_path / "repo")
    options.update(kwargs)
    return retain_kis_paper_daily_pair_forward_page(**options)


def load(tmp_path: Path, reference: dict[str, str], **kwargs: object):
    options = dict(observation_root=tmp_path / "observations", repo_root=tmp_path / "repo",
                   query=query(), snapshot_sha256=reference["snapshot_sha256"],
                   observation_sha256=reference["observation_sha256"],
                   as_of=datetime.now(UTC) + timedelta(seconds=1), required_sessions=SESSIONS)
    options.update(kwargs)
    return load_kis_paper_daily_pair_observation_as_of(**options)


def test_exact_whole_page_roundtrip_keeps_preboundary_context(tmp_path: Path) -> None:
    reference = retain(tmp_path)
    assert load(tmp_path, reference) == rows()
    document = json.loads((tmp_path / "observations" / reference["relative_path"]).read_bytes())
    assert document["query"] == query()
    assert document["row_count"] == 3
    assert "not_CA" in document["price_basis"]
    assert not (tmp_path / "observations" / "index.json").exists()


def test_dedup_keeps_first_capture_retention_and_all_bytes(tmp_path: Path) -> None:
    first = retain(tmp_path)
    root = tmp_path / "observations"
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    second = retain(tmp_path, captured_at=OBSERVED + timedelta(hours=1))
    assert first == second
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_revision_is_another_generation_never_latest_row_stitch(tmp_path: Path) -> None:
    first = retain(tmp_path)
    revised = (dataclasses.replace(rows()[0], close=Decimal("100.5")), *rows()[1:])
    second = retain(tmp_path, rows=revised)
    assert second["snapshot_sha256"] != first["snapshot_sha256"]
    assert load(tmp_path, first) == rows()
    assert load(tmp_path, second) == revised
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="context is unavailable"):
        load(tmp_path, first, required_sessions=(*SESSIONS, date(2026, 7, 30)))


@pytest.mark.parametrize("field,value", [
    ("endpoint", "/uapi/overseas-stock/v1/trading/order"), ("tr_id", "WRONG"),
    ("EXCD", "AMS"), ("SYMB", "MSFT"), ("GUBN", "1"), ("MODP", "1"),
    ("BYMD", "20260230"), ("BYMD", "2026-729"), ("continuation", "NEXT"),
    ("collector_source_sha256", "secret"), ("request_source_sha256", "secret"),
    ("MODP", 0),
])
def test_public_query_is_exact_and_never_echoes_bad_values(
    tmp_path: Path, field: str, value: object,
) -> None:
    q = dict(query(), **{field: value})
    with pytest.raises(KisPaperDailyPairForwardCacheError) as error:
        retain(tmp_path, query=q)
    assert "secret" not in str(error.value)
    assert not (tmp_path / "observations").exists()


@pytest.mark.parametrize("field", ["headers", "authorization", "AUTH", "appkey", "account_no"])
def test_secret_or_unknown_query_fields_cannot_be_written(tmp_path: Path, field: str) -> None:
    with pytest.raises(KisPaperDailyPairForwardCacheError) as error:
        retain(tmp_path, query={**query(), field: "SYN_SECRET_DO_NOT_RETAIN"})
    assert "SYN_SECRET" not in str(error.value)
    assert not (tmp_path / "observations").exists()


@pytest.mark.parametrize("field,value", [
    ("collector_source_sha256", "sha256:" + "c" * 64),
    ("request_source_sha256", "sha256:" + "d" * 64),
    ("BYMD", "20260730"), ("continuation", "F"),
])
def test_exact_reader_cannot_select_another_source_or_query(
    tmp_path: Path, field: str, value: str,
) -> None:
    reference = retain(tmp_path)
    with pytest.raises(KisPaperDailyPairForwardCacheError):
        load(tmp_path, reference, query={**query(), field: value})


def test_hash_and_timestamp_binding_are_required(tmp_path: Path) -> None:
    reference = retain(tmp_path)
    for override in (
        {"observation_sha256": "sha256:" + "0" * 64},
        {"snapshot_sha256": "sha256:" + "0" * 64},
        {"as_of": OBSERVED}, {"as_of": OBSERVED.replace(tzinfo=None)},
        {"required_sessions": ()}, {"required_sessions": SESSIONS[::-1]},
    ):
        with pytest.raises(KisPaperDailyPairForwardCacheError):
            load(tmp_path, reference, **override)
    descriptor = tmp_path / "observations" / reference["relative_path"]
    document = json.loads(descriptor.read_bytes())
    document["captured_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    document["recorded_at"] = document["captured_at"]
    descriptor.write_text(json.dumps(document), encoding="utf-8")
    changed = dict(
        reference,
        observation_sha256="sha256:" + hashlib.sha256(descriptor.read_bytes()).hexdigest(),
    )
    with pytest.raises(KisPaperDailyPairForwardCacheError):
        load(tmp_path, changed, as_of=datetime.now(UTC) + timedelta(days=2))


@pytest.mark.parametrize("field,value", [
    ("price_basis", "MODP1"), ("schema", "unknown"), ("row_count", True),
    ("normalization", "latest_per_row"), ("captured_at", "invalid"),
    ("headers", "SYN_SECRET_DO_NOT_PUBLISH"),
])
def test_rebound_descriptor_cannot_bypass_schema_basis_clock_or_redaction(
    tmp_path: Path, field: str, value: object,
) -> None:
    reference = retain(tmp_path)
    path = tmp_path / "observations" / reference["relative_path"]
    document = json.loads(path.read_bytes())
    document[field] = value
    path.write_text(json.dumps(document), encoding="utf-8")
    changed = dict(
        reference,
        observation_sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    with pytest.raises(KisPaperDailyPairForwardCacheError) as error:
        load(tmp_path, changed)
    assert "SYN_SECRET" not in str(error.value)


def test_snapshot_corruption_is_not_a_new_valid_vintage(tmp_path: Path) -> None:
    reference = retain(tmp_path)
    descriptor = tmp_path / "observations" / reference["relative_path"]
    payload = descriptor.with_name("page.csv.gz")
    payload.write_bytes(payload.read_bytes() + b"SYN_CORRUPT")
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="snapshot hash"):
        load(tmp_path, reference)


def test_repository_and_reparse_roots_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="outside Git"):
        retain(tmp_path, observation_root=repo / "captures")
    assert not (repo / "captures").exists()
    root = tmp_path / "reparse"
    root.mkdir()
    original = Path.lstat
    def reparse(path: Path):
        value = original(path)
        if path == root:
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=1024)
        return value
    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="path is invalid"):
        retain(tmp_path, observation_root=root)


@pytest.mark.parametrize("override", [
    {"captured_at": datetime(2099, 1, 1, tzinfo=UTC)},
    {"captured_at": OBSERVED.replace(tzinfo=None)},
    {"captured_at": OBSERVED - timedelta(days=2)},
])
def test_capture_clock_cannot_backdate_the_query_or_be_future(
    tmp_path: Path, override: dict[str, object],
) -> None:
    with pytest.raises(KisPaperDailyPairForwardCacheError):
        retain(tmp_path, **override)
    assert not (tmp_path / "observations").exists()


def test_conflicting_in_page_duplicates_fail_before_any_output(tmp_path: Path) -> None:
    conflicting = (*rows(), dataclasses.replace(rows()[0], close=Decimal("100.5")))
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="duplicate conflict"):
        retain(tmp_path, rows=conflicting)
    assert not (tmp_path / "observations").exists()
    reference = retain(tmp_path, rows=(*rows(), rows()[0]))
    assert load(tmp_path, reference) == rows()


def test_missing_generation_is_not_created_by_reader(tmp_path: Path) -> None:
    with pytest.raises(KisPaperDailyPairForwardCacheError):
        load(tmp_path, {"snapshot_sha256": "sha256:" + "a" * 64,
                        "observation_sha256": "sha256:" + "b" * 64})
    assert not (tmp_path / "observations").exists()


def test_partial_capture_fault_is_preserved_and_never_reclaimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cache._write_bytes_new
    def fail_descriptor(path: Path, data: bytes) -> None:
        if path.name == "observation.json":
            raise OSError("SYN_RETENTION_FAILURE")
        original(path, data)
    monkeypatch.setattr(cache, "_write_bytes_new", fail_descriptor)
    with pytest.raises(OSError):
        retain(tmp_path)
    payload = next((tmp_path / "observations").rglob("page.csv.gz"))
    before = payload.read_bytes()
    monkeypatch.setattr(cache, "_write_bytes_new", original)
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="incomplete"):
        retain(tmp_path)
    assert payload.read_bytes() == before
    assert not list((tmp_path / "observations").rglob("observation.json"))


class Client:
    def __init__(self, *, revised: bool = False, mismatch: bool = False) -> None:
        self.revised, self.mismatch = revised, mismatch

    def fetch_daily_raw_page(self, q: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        raw = tuple(KisPaperDailyRawRow(
            xymd=s.strftime("%Y%m%d"), open="100", high="101", low="99",
            clos="100.5" if self.revised else "100", tvol="1000",
        ) for s in SESSIONS[::-1])
        actual_query = dataclasses.replace(q, by_date="20260728") if self.mismatch else q
        return KisPaperDailyRawPage(page=KisPaperDailyPage(
            query=actual_query, row_count=len(raw), newest_date=raw[0].xymd,
            oldest_date=raw[-1].xymd, required_ohlcv_fields_present=True,
            continuation_available=False, continuation_value=None,
        ), rows=raw)


def test_opt_in_keeps_default_canonical_bytes_ids_and_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cache.uuid, "uuid4", lambda: SimpleNamespace(hex="f" * 32))
    default_root, opt_root = tmp_path / "default", tmp_path / "opt"
    default = collector.collect_kis_paper_daily_pair_forward_once(
        Client(), cache_root=default_root, repository_root=tmp_path / "repo", observed_at=OBSERVED,
    )
    opt = collector.collect_kis_paper_daily_pair_forward_once(
        Client(), cache_root=opt_root, repository_root=tmp_path / "repo", observed_at=OBSERVED,
        retain_observations=True,
    )
    assert default.safe_payload() == opt.safe_payload()
    assert (default_root / "index.json").read_bytes() == (opt_root / "index.json").read_bytes()
    for path in (default_root / "snapshots").rglob("*.csv.gz"):
        assert path.read_bytes() == (opt_root / path.relative_to(default_root)).read_bytes()
    assert not (default_root / "observations-v1").exists()
    assert len(list((opt_root / "observations-v1").rglob("observation.json"))) == 2
    assert all(len(r) == 2 for r in opt.cache.rows_by_target.values())
    assert all(json.loads(p.read_bytes())["row_count"] == 3
               for p in (opt_root / "observations-v1").rglob("observation.json"))


def test_retention_does_not_clear_existing_revision_quarantine(tmp_path: Path) -> None:
    options = dict(cache_root=tmp_path / "cache", repository_root=tmp_path / "repo",
                   observed_at=OBSERVED, retain_observations=True)
    first = collector.collect_kis_paper_daily_pair_forward_once(Client(), **options)
    original_rows = first.cache.rows_by_target
    revised = collector.collect_kis_paper_daily_pair_forward_once(Client(revised=True), **options)
    assert revised.revision_quarantined_target_count == 2
    assert revised.cache.rows_by_target == original_rows
    later = collector.collect_kis_paper_daily_pair_forward_once(Client(), **options)
    assert later.revision_quarantined_target_count == 2
    assert len(list((tmp_path / "cache" / "observations-v1").rglob("observation.json"))) == 4


def test_capture_failure_stops_before_canonical_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**_kwargs: object) -> None:
        raise OSError("SYN_SECRET_STORAGE_ERROR")
    monkeypatch.setattr(collector, "retain_kis_paper_daily_pair_forward_page", fail)
    monkeypatch.setattr(collector, "commit_kis_paper_daily_pair_forward_observation",
                        lambda **_: pytest.fail("retention failure must not commit"))
    with pytest.raises(KisPaperDailyPairForwardCacheError, match="whole-page retention failed"):
        collector.collect_kis_paper_daily_pair_forward_once(
            Client(), cache_root=tmp_path / "cache", repository_root=tmp_path / "repo",
            observed_at=OBSERVED, retain_observations=True,
        )
    assert not (tmp_path / "cache" / "index.json").exists()


def test_returned_query_mismatch_aborts_opt_in_before_retention(tmp_path: Path) -> None:
    with pytest.raises(KisPaperDailyPairForwardCacheError):
        collector.collect_kis_paper_daily_pair_forward_once(
            Client(mismatch=True), cache_root=tmp_path / "cache",
            repository_root=tmp_path / "repo", observed_at=OBSERVED, retain_observations=True,
        )
    assert not (tmp_path / "cache").exists()


def test_library_default_does_not_read_sources_or_capture_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "_public_query_envelope", lambda *_: pytest.fail("default"))
    result = collector.collect_kis_paper_daily_pair_forward_observation(
        Client(), observed_at=OBSERVED, capture_clock=lambda: pytest.fail("default clock"),
    )
    assert tuple(dataclasses.asdict(result)) == (
        "rows_by_target", "failure_reasons_by_target", "observed_at",
    )


def test_cli_opt_in_requires_execute_before_any_environment_or_collector(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from test_collect_kis_paper_daily_pair_forward_script import _script_module
    script = _script_module()
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config",
                        lambda: pytest.fail("must stay inert"))
    assert script.main(["--preflight", "--retain-observations"]) == 2
    assert "observation_retention_requires_execute" in capsys.readouterr().out


def test_cli_execute_wires_opt_in_without_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_collect_kis_paper_daily_pair_forward_script import _script_module
    script = _script_module()
    seen = {}
    monkeypatch.setattr(script, "_canonical_roots", lambda **_: True)
    monkeypatch.setattr(script, "_run_credentialed_collection",
                        lambda **kwargs: seen.update(kwargs) or 0)
    assert script.main(["--execute", "--retain-observations"]) == 0
    assert seen["retain_observations"] is True


def test_opt_in_result_binds_only_public_query_and_page_refs(tmp_path: Path) -> None:
    result = collector.collect_kis_paper_daily_pair_forward_observation(
        Client(), observed_at=OBSERVED, observation_root=tmp_path / "observations",
        repository_root=tmp_path / "repo", capture_clock=lambda: OBSERVED,
    )
    assert isinstance(result, collector.KisPaperDailyPairForwardRetainedObservation)
    assert set(result.retained_pages) == {"QQQ/NAS", "SPY/AMS"}
    for target, reference in result.retained_pages.items():
        descriptor = tmp_path / "observations" / reference["relative_path"]
        data = json.loads(descriptor.read_bytes())
        assert f"{data['query']['SYMB']}/{data['query']['EXCD']}" == target
        assert data["query"]["MODP"] == "0"
        assert data["query"]["collector_source_sha256"] == (
            "sha256:" + hashlib.sha256(Path(collector.__file__).read_bytes()).hexdigest()
        )
        assert all(key not in data["query"] for key in ("headers", "AUTH", "authorization"))


def test_opt_in_empty_market_window_has_typed_empty_capture_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "latest_completed_us_equity_d1_session", lambda _: None)
    result = collector.collect_kis_paper_daily_pair_forward_observation(
        Client(), observation_root=tmp_path / "observations", observed_at=OBSERVED,
    )
    assert isinstance(result, collector.KisPaperDailyPairForwardRetainedObservation)
    assert result.retained_pages == {}
    assert not (tmp_path / "observations").exists()


def test_script_capture_fault_projects_only_safe_collection_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_collect_kis_paper_daily_pair_forward_script import (
        _RateGate,
        _script_module,
        _TokenGate,
    )
    script = _script_module()
    seen = {}
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", lambda **_: _RateGate())
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", lambda **_: _TokenGate())
    monkeypatch.setattr(script, "load_kis_paper_market_data_environment_config", object)
    monkeypatch.setattr(script, "UrllibKisPaperDailyPairForwardTransport", lambda **_: object())
    monkeypatch.setattr(script, "KisPaperMarketDataClient", lambda **_: object())
    def fail(*_args: object, **kwargs: object) -> None:
        assert kwargs["observation_root"] == tmp_path / "cache" / "observations-v1"
        raise KisPaperDailyPairForwardCacheError("SYN_SECRET_NOT_IN_RECEIPT")
    monkeypatch.setattr(script, "collect_kis_paper_daily_pair_forward_observation", fail)
    monkeypatch.setattr(script, "commit_kis_paper_daily_pair_forward_observation",
                        lambda **_: pytest.fail("must not commit"))
    monkeypatch.setattr(script, "_write_source_safe_receipt",
                        lambda **kwargs: seen.update(kwargs)
                        or (tmp_path / "r", "sha256:" + "a" * 64))
    assert script._run_credentialed_collection(
        cache_root=tmp_path / "cache", control_root=tmp_path / "control",
        artifact_root=tmp_path / "artifacts", repository_root=tmp_path / "repo",
        frozen_boundary=date(2026, 7, 24), observed_at=OBSERVED, retain_observations=True,
    ) == 20
    encoded = json.dumps(seen["receipt"])
    assert "SYN_SECRET" not in encoded
    assert seen["receipt"]["payload"]["failure_stage"] == "collection"
