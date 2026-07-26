from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import thericher_v2.execution.kis_paper_daily_universe_probe as probe
from thericher_v2.data.official_symbol_directory_nas_probe import (
    NAS_COMMON_STOCK_PROBE_SYMBOLS,
    OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256,
    NasProbeTarget,
    OfficialSymbolDirectoryNasProbeRegistry,
)
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_DAILY_TR_ID,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_MINUTE_TR_ID,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
)
from thericher_v2.execution.kis_paper_daily_universe_probe import (
    KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET,
    UrllibKisPaperDailyUniverseProbeTransport,
    run_kis_paper_daily_universe_probe,
)

_OBSERVED_AT = datetime(2026, 7, 27, 0, 0, tzinfo=UTC)


class _FakeProbeClient:
    def __init__(self, pages: dict[tuple[str, str | None], list[KisPaperDailyRawPage]]) -> None:
        self._pages = {key: list(value) for key, value in pages.items()}
        self._token_attempts = 0
        self._daily_page_attempts = 0
        self.queries: list[KisPaperDailyQuery] = []

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        return KisPaperMarketDataCallCounts(
            token_attempts=self._token_attempts,
            minute_page_attempts=0,
            daily_page_attempts=self._daily_page_attempts,
        )

    def ensure_authenticated(self) -> None:
        self._token_attempts += 1

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        self._daily_page_attempts += 1
        pages = self._pages[(query.symbol, query.continuation)]
        return pages.pop(0)


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.status = 200
        self.headers = {"content-type": "application/json"}
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class _FakeOpener:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def open(self, request: object, *, timeout: float) -> _FakeHttpResponse:
        self.urls.append(request.full_url)  # type: ignore[attr-defined]
        return _FakeHttpResponse({"rt_cd": "0", "output1": {}, "output2": []})


def test_probe_uses_exact_registry_targets_and_writes_source_safe_external_cache(
    tmp_path: Path,
) -> None:
    registry = _registry()
    client = _FakeProbeClient(_accepted_pages_for_registry(registry))

    result = run_kis_paper_daily_universe_probe(
        client,
        registry=registry,
        cache_root=tmp_path / "market-data" / "daily-universe-probe",
        artifact_root=tmp_path / "model-artifacts",
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        anchor_date="20260726",
        run_id="20260727T000000Z",
    )

    assert sum(state.classification == "accepted" for state in result.target_states) == 6
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 0, 7)
    assert [query.symbol for query in client.queries] == [
        "AAPL",
        "AAPL",
        "AMZN",
        "GOOGL",
        "META",
        "MSFT",
        "NVDA",
    ]
    assert client.queries[1].continuation == "F"
    assert client.queries[1].by_date == "20260725"
    assert all(
        query.approved_symbol_exchanges == {
            symbol: frozenset({"NAS"}) for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS
        }
        for query in client.queries
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    rendered = json.dumps(manifest, sort_keys=True)

    assert manifest["kind"] == "kis_paper_daily_universe_capability_probe"
    assert manifest["registry"]["registry_sha256"] == registry.registry_sha256
    assert manifest["registry"]["source_manifest_sha256"] == registry.source_manifest_sha256
    assert manifest["requests"] == {
        "token_attempts": 1,
        "minute_page_attempts": 0,
        "daily_page_attempts": 7,
    }
    assert len(manifest["targets"]) == 6
    assert len(manifest["files"]["raw_daily_rows"]) == 6
    assert manifest["source"]["account_or_order_endpoints_used"] is False
    assert "777.777" not in rendered
    assert "paper-key" not in rendered
    assert result.manifest_sha256 == "sha256:" + hashlib.sha256(
        result.manifest_path.read_bytes()
    ).hexdigest()
    raw_document = manifest["files"]["raw_daily_rows"]["AAPL/NAS"]
    assert (result.manifest_path.parent / raw_document["path"]).is_file()
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    evidence_rendered = json.dumps(evidence, sort_keys=True)
    assert evidence["kind"] == "kis_paper_daily_universe_capability_probe_evidence"
    assert evidence["cache_manifest"]["sha256"] == result.manifest_sha256
    assert evidence["redaction"]["raw_rows_persisted"] is False
    assert "777.777" not in evidence_rendered
    assert "paper-key" not in evidence_rendered
    assert not hasattr(result, "rows")


def test_probe_classifies_empty_source_as_source_limited_without_raw_cache(tmp_path: Path) -> None:
    registry = _registry()
    pages = _accepted_pages_for_registry(registry)
    pages[("META", None)] = [_page(_query("META"), [], continuation=None)]
    client = _FakeProbeClient(pages)

    result = run_kis_paper_daily_universe_probe(
        client,
        registry=registry,
        cache_root=tmp_path / "market-data",
        artifact_root=tmp_path / "model-artifacts",
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        anchor_date="20260726",
        run_id="20260727T000001Z",
    )

    meta = next(target for target in result.target_states if target.target_key == "META/NAS")
    assert meta.classification == "source_limited"
    assert meta.recovery == "complete"
    assert meta.reason == "empty_daily_response"

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert "META/NAS" not in manifest["files"]["raw_daily_rows"]


def test_probe_requires_strict_continuation_date_progress(tmp_path: Path) -> None:
    registry = _registry()
    pages = _accepted_pages_for_registry(registry)
    pages[("AAPL", "F")] = [
        _page(
            _query("AAPL", by_date="20260725", continuation="F"),
            [_row("20260725")],
            continuation=None,
        )
    ]

    result = run_kis_paper_daily_universe_probe(
        _FakeProbeClient(pages),
        registry=registry,
        cache_root=tmp_path / "market-data",
        artifact_root=tmp_path / "model-artifacts",
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        anchor_date="20260726",
        run_id="20260727T000003Z",
    )

    aapl = result.target_states[0]
    assert aapl.classification == "invalid"
    assert aapl.reason == "daily_cursor_not_progressed"
    assert aapl.recovery == "restart"


def test_probe_rejects_a_returned_page_bound_to_a_different_scope(tmp_path: Path) -> None:
    registry = _registry()
    pages = _accepted_pages_for_registry(registry)
    pages[("AAPL", None)] = [
        _page(
            KisPaperDailyQuery(
                symbol="AAPL",
                exchange="NAS",
                by_date="20260726",
                approved_symbol_exchanges={"AAPL": frozenset({"NAS"})},
            ),
            [_row("20260726"), _row("20260725")],
            continuation=None,
        )
    ]
    result = run_kis_paper_daily_universe_probe(
        _FakeProbeClient(pages),
        registry=registry,
        cache_root=tmp_path / "market-data",
        artifact_root=tmp_path / "model-artifacts",
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        anchor_date="20260726",
        run_id="20260727T000004Z",
    )

    assert result.target_states[0].classification == "invalid"
    assert result.target_states[0].reason == "daily_scope_mismatch"
    assert result.target_states[0].recovery == "restart"


def test_probe_rejects_registry_with_not_exactly_six_targets(tmp_path: Path) -> None:
    registry = _registry(symbols=NAS_COMMON_STOCK_PROBE_SYMBOLS[:5])
    client = _FakeProbeClient({})

    with pytest.raises(ValueError, match="registry"):
        run_kis_paper_daily_universe_probe(
            client,
            registry=registry,
            cache_root=tmp_path / "market-data",
            artifact_root=tmp_path / "model-artifacts",
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
            anchor_date="20260726",
        )

    assert client.call_counts == KisPaperMarketDataCallCounts(0, 0, 0)


def test_probe_cache_refuses_a_repo_local_path(tmp_path: Path) -> None:
    registry = _registry()
    result_client = _FakeProbeClient(_accepted_pages_for_registry(registry))
    with pytest.raises(ValueError, match="outside Git"):
        run_kis_paper_daily_universe_probe(
            result_client,
            registry=registry,
            cache_root=Path(__file__).resolve().parents[1] / "market-data",
            artifact_root=tmp_path / "model-artifacts",
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
            anchor_date="20260726",
            run_id="20260727T000002Z",
        )


def test_probe_rejects_overlapping_raw_cache_and_evidence_roots_before_auth(tmp_path: Path) -> None:
    registry = _registry()
    client = _FakeProbeClient(_accepted_pages_for_registry(registry))
    shared_root = tmp_path / "shared"

    with pytest.raises(ValueError, match="roots must be separate"):
        run_kis_paper_daily_universe_probe(
            client,
            registry=registry,
            cache_root=shared_root,
            artifact_root=shared_root,
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
            anchor_date="20260726",
            run_id="20260727T000005Z",
        )

    assert client.call_counts == KisPaperMarketDataCallCounts(0, 0, 0)


def test_probe_repairs_evidence_without_recollecting_a_committed_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry()
    cache_root = tmp_path / "market-data"
    artifact_root = tmp_path / "model-artifacts"
    first_client = _FakeProbeClient(_accepted_pages_for_registry(registry))
    original_writer = probe._write_source_safe_probe_evidence

    def fail_evidence_write(**_kwargs: object) -> tuple[Path, str]:
        raise OSError("evidence_write_failed")

    monkeypatch.setattr(probe, "_write_source_safe_probe_evidence", fail_evidence_write)
    with pytest.raises(OSError, match="evidence_write_failed"):
        run_kis_paper_daily_universe_probe(
            first_client,
            registry=registry,
            cache_root=cache_root,
            artifact_root=artifact_root,
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
            anchor_date="20260726",
            run_id="20260727T000006Z",
        )
    assert first_client.call_counts == KisPaperMarketDataCallCounts(1, 0, 7)

    monkeypatch.setattr(probe, "_write_source_safe_probe_evidence", original_writer)
    recovery_client = _FakeProbeClient({})
    recovered = run_kis_paper_daily_universe_probe(
        recovery_client,
        registry=registry,
        cache_root=cache_root,
        artifact_root=artifact_root,
        code_revision="git:ignored-on-recovery",
        observed_at=_OBSERVED_AT,
        anchor_date="20260726",
        run_id="20260727T000006Z",
    )

    assert recovery_client.call_counts == KisPaperMarketDataCallCounts(0, 0, 0)
    assert recovered.evidence_path.is_file()
    assert recovered.manifest_path.is_file()


def test_probe_rejects_wrong_ordered_six_symbol_registry(tmp_path: Path) -> None:
    registry = _registry(
        symbols=("AAPL", "AMZN", "GOOGL", "META", "MSFT", "TSLA"),
    )

    with pytest.raises(ValueError, match="registry"):
        run_kis_paper_daily_universe_probe(
            _FakeProbeClient({}),
            registry=registry,
            cache_root=tmp_path / "market-data",
            artifact_root=tmp_path / "model-artifacts",
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
        )


def test_probe_rejects_noncanonical_registry_source_manifest(tmp_path: Path) -> None:
    registry = _registry(source_manifest_sha256="sha256:" + "f" * 64)

    with pytest.raises(ValueError, match="registry"):
        run_kis_paper_daily_universe_probe(
            _FakeProbeClient({}),
            registry=registry,
            cache_root=tmp_path / "market-data",
            artifact_root=tmp_path / "model-artifacts",
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
        )


def test_special_transport_allows_only_registry_daily_pairs_and_inherited_token_route() -> None:
    registry = _registry()
    default_transport = UrllibKisPaperMarketDataTransport()
    default_opener = _FakeOpener()
    default_transport._opener = default_opener  # type: ignore[attr-defined]
    with pytest.raises(KisPaperMarketDataError, match="allowlisted"):
        default_transport.request(_daily_request("AAPL"))
    assert default_opener.urls == []

    transport = UrllibKisPaperDailyUniverseProbeTransport(registry=registry)
    opener = _FakeOpener()
    transport._opener = opener  # type: ignore[attr-defined]

    response = transport.request(_daily_request("AAPL"))
    token = transport.request(
        KisMarketDataRequest(
            method="POST",
            url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
            headers={"content-type": "application/json", "accept": "application/json"},
            json_body={"grant_type": "client_credentials", "appkey": "key", "appsecret": "secret"},
        )
    )

    assert response.status_code == 200
    assert token.status_code == 200
    assert len(opener.urls) == 2
    with pytest.raises(KisPaperMarketDataError, match="allowlisted"):
        transport.request(_daily_request("QQQ"))
    with pytest.raises(KisPaperMarketDataError, match="allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_MINUTE_PATH}",
                headers={"tr_id": KIS_PAPER_MINUTE_TR_ID, "tr_cont": "", "custtype": "P"},
                query={
                    "AUTH": "",
                    "EXCD": "NAS",
                    "SYMB": "QQQ",
                    "NMIN": "1",
                    "PINC": "0",
                    "NREC": "120",
                    "FILL": "",
                    "KEYB": "",
                    "NEXT": "",
                },
            )
        )
    assert KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET == 2


def _registry(
    *,
    symbols: tuple[str, ...] = NAS_COMMON_STOCK_PROBE_SYMBOLS,
    source_manifest_sha256: str = OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256,
) -> OfficialSymbolDirectoryNasProbeRegistry:
    payload = b"registry-payload"
    return OfficialSymbolDirectoryNasProbeRegistry(
        version="official-symbol-directory-nas-probe-r1",
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256="sha256:" + "b" * 64,
        source_file_size_bytes=123,
        targets=tuple(NasProbeTarget(symbol=symbol, exchange="NAS") for symbol in symbols),
        registry_payload=payload,
        registry_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def _accepted_pages_for_registry(
    registry: OfficialSymbolDirectoryNasProbeRegistry,
) -> dict[tuple[str, str | None], list[KisPaperDailyRawPage]]:
    pages: dict[tuple[str, str | None], list[KisPaperDailyRawPage]] = {}
    for target in registry.targets:
        pages[(target.symbol, None)] = [
            _page(
                _query(target.symbol),
                [_row("20260726"), _row("20260725")],
                continuation="F" if target.symbol == "AAPL" else None,
            )
        ]
    pages[("AAPL", "F")] = [
        _page(
            _query("AAPL", by_date="20260725", continuation="F"),
            [_row("20260725"), _row("20260724", close="101.5")],
            continuation=None,
        )
    ]
    return pages


def _query(
    symbol: str,
    *,
    by_date: str = "20260726",
    continuation: str | None = None,
) -> KisPaperDailyQuery:
    return KisPaperDailyQuery(
        symbol=symbol,
        exchange="NAS",
        by_date=by_date,
        continuation=continuation,
        approved_symbol_exchanges={
            value: frozenset({"NAS"}) for value in NAS_COMMON_STOCK_PROBE_SYMBOLS
        },
    )


def _page(
    query: KisPaperDailyQuery,
    rows: list[KisPaperDailyRawRow],
    *,
    continuation: str | None,
) -> KisPaperDailyRawPage:
    dates = [row.xymd for row in rows]
    return KisPaperDailyRawPage(
        page=KisPaperDailyPage(
            query=query,
            row_count=len(rows),
            newest_date=max(dates) if dates else None,
            oldest_date=min(dates) if dates else None,
            required_ohlcv_fields_present=bool(rows),
            continuation_available=continuation == "F",
            continuation_value=continuation,
        ),
        rows=tuple(rows),
    )


def _row(date: str, *, close: str = "101") -> KisPaperDailyRawRow:
    return KisPaperDailyRawRow(
        xymd=date,
        open="100",
        high="102",
        low="99",
        clos=close,
        tvol="777.777",
    )


def _daily_request(symbol: str) -> KisMarketDataRequest:
    return KisMarketDataRequest(
        method="GET",
        url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
        headers={"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
        query={
            "AUTH": "",
            "EXCD": "NAS",
            "SYMB": symbol,
            "GUBN": "0",
            "BYMD": "20260726",
            "MODP": "0",
        },
    )
