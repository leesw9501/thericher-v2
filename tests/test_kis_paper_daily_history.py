from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import thericher_v2.execution.kis_paper_daily_history as daily_history
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_DAILY_TR_ID,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_history import (
    KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE,
    KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256,
    KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES,
    KIS_PAPER_DAILY_HISTORY_VERSION,
    KisPaperDailyHistoryError,
    UrllibKisPaperDailyHistoryTransport,
    run_kis_paper_daily_history_collection,
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 27, 1, 0, tzinfo=UTC)
        self.monotonic_now = 0.0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.monotonic_now += seconds

    def monotonic(self) -> float:
        return self.monotonic_now


class _HistoryClient:
    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self._token_attempts = 0
        self._daily_attempts = 0
        self.auth_calls = 0
        self.queries: list[KisPaperDailyQuery] = []

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        return KisPaperMarketDataCallCounts(
            token_attempts=self._token_attempts,
            minute_page_attempts=0,
            daily_page_attempts=self._daily_attempts,
        )

    def ensure_authenticated(self) -> None:
        self.auth_calls += 1
        if self._token_attempts == 0:
            self._token_attempts += 1

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        self._daily_attempts += 1
        self._clock.advance(1)
        if query.continuation is None:
            dates = ("20260724", "20260401")
        else:
            dates = ("20260401", "20260101")
        rows = tuple(_row(date, close="987654.321") for date in dates)
        page = KisPaperDailyPage(
            query=query,
            row_count=len(rows),
            newest_date=max(dates),
            oldest_date=min(dates),
            required_ohlcv_fields_present=True,
            continuation_available=True,
            continuation_value="F",
        )
        return KisPaperDailyRawPage(page=page, rows=rows)


class _EmptyTerminalHistoryClient(_HistoryClient):
    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        self._daily_attempts += 1
        self._clock.advance(1)
        return KisPaperDailyRawPage(
            page=KisPaperDailyPage(
                query=query,
                row_count=0,
                newest_date=None,
                oldest_date=None,
                required_ohlcv_fields_present=True,
                continuation_available=False,
                continuation_value=None,
            ),
            rows=(),
        )


class _StalledHistoryClient(_HistoryClient):
    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        self._daily_attempts += 1
        self._clock.advance(1)
        rows = (_row(query.by_date, close="987654.321"),)
        return KisPaperDailyRawPage(
            page=KisPaperDailyPage(
                query=query,
                row_count=len(rows),
                newest_date=query.by_date,
                oldest_date=query.by_date,
                required_ohlcv_fields_present=True,
                continuation_available=False,
                continuation_value=None,
            ),
            rows=rows,
        )


class _HttpResponse:
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self) -> _HttpResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


class _RecordingOpener:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def open(self, request: object, *, timeout: float) -> _HttpResponse:
        assert timeout > 0
        self.requests.append(request)
        return _HttpResponse()


def test_history_collection_reuses_one_client_and_persists_resumable_safe_progress(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-history" / "v1"
    evidence_root = tmp_path / "artifacts" / "data" / "daily-nas-history"
    control_root = tmp_path / "market-data" / "collection-control-v1"
    request_gate = KisPaperMarketDataRateGate(control_root=control_root, clock=clock)
    token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root, clock=clock)
    first_client = _HistoryClient(clock)

    first = run_kis_paper_daily_history_collection(
        client_factory=lambda: first_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=2,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    assert first.status == "collected"
    assert first.accepted_page_count == 4
    assert first.categorical_failure_count == 0
    assert first.chunk_attempt_count == 2
    assert first.measured_accepted_pages_per_minute == 60.0
    assert first.remaining_page_estimate is None
    assert first.eta_bucket == "unknown"
    assert first.recovery == "resume"
    assert first.registry_sha256 == KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256
    assert first_client._token_attempts == 1
    assert [query.symbol for query in first_client.queries] == ["AAPL", "AAPL", "AMZN", "AMZN"]
    assert all(query.exchange == "NAS" for query in first_client.queries)
    assert all(
        query.approved_symbol_exchanges == KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES
        for query in first_client.queries
    )
    assert first.target_states[0].cursor_date == "20260101"
    assert first.target_states[1].cursor_date == "20260101"
    assert first.target_states[2].cursor_date == KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE

    index = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    assert index["version"] == KIS_PAPER_DAILY_HISTORY_VERSION
    assert index["targets"][0]["chunks"][0]["manifest_path"].startswith("snapshot=")
    assert index["redaction"]["credentials_persisted"] is False
    assert "987654.321" not in json.dumps(index)

    receipt = next(evidence_root.glob("run=*/receipt.json"))
    receipt_text = receipt.read_text(encoding="utf-8")
    assert "987654.321" not in receipt_text
    assert "paper-secret" not in receipt_text
    assert "account_number" not in receipt_text
    receipt_document = json.loads(receipt_text)
    assert receipt_document["scope"]["target_keys"] == [
        "AAPL/NAS",
        "AMZN/NAS",
        "GOOGL/NAS",
        "META/NAS",
        "MSFT/NAS",
        "NVDA/NAS",
    ]
    assert receipt_document["route_isolation"]["account_endpoints_used"] is False
    assert receipt_document["artifact_policy"]["raw_market_data_in_receipt"] is False

    second_client = _HistoryClient(clock)
    second = run_kis_paper_daily_history_collection(
        client_factory=lambda: second_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=1,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    assert second.status == "collected"
    assert second.target_states[0].cursor_date == "20260101"
    assert second_client.queries[0].symbol == "GOOGL"
    assert second.evidence_sha256 is not None


def test_history_cache_rejects_a_git_workspace_destination(tmp_path: Path) -> None:
    clock = _Clock()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    gate = KisPaperMarketDataRateGate(control_root=tmp_path / "control", clock=clock)
    token_gate = KisPaperMarketDataTokenStartGate(control_root=tmp_path / "control", clock=clock)

    with pytest.raises(KisPaperDailyHistoryError, match="outside Git"):
        run_kis_paper_daily_history_collection(
            client_factory=lambda: _HistoryClient(clock),  # type: ignore[arg-type]
            request_gate=gate,
            token_start_gate=token_gate,
            cache_root=repo_root / "market-data",
            evidence_root=tmp_path / "artifacts",
            repo_root=repo_root,
            code_revision="git:test",
            max_chunks=1,
            max_runtime=timedelta(minutes=1),
            clock=clock,
            monotonic_clock=clock.monotonic,
        )


def test_empty_terminal_daily_page_persists_source_limited_state_without_snapshot(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-history" / "v1"
    evidence_root = tmp_path / "artifacts" / "data" / "daily-nas-history"
    control_root = tmp_path / "market-data" / "collection-control-v1"
    request_gate = KisPaperMarketDataRateGate(control_root=control_root, clock=clock)
    token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root, clock=clock)
    first_client = _EmptyTerminalHistoryClient(clock)

    first = run_kis_paper_daily_history_collection(
        client_factory=lambda: first_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=6,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    assert first.status == "complete"
    assert first.accepted_page_count == 6
    assert first.categorical_failure_count == 0
    assert first.chunk_attempt_count == 6
    assert all(state.state == "source_limited" for state in first.target_states)
    assert all(
        state.cursor_date == KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE
        for state in first.target_states
    )
    assert all(state.last_reason == "empty_daily_response" for state in first.target_states)
    assert list(cache_root.glob("snapshot=*/manifest.json")) == []

    index = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    assert all(target["chunks"] == [] for target in index["targets"])
    assert "987654.321" not in json.dumps(index)

    resumed_client = _EmptyTerminalHistoryClient(clock)
    resumed = run_kis_paper_daily_history_collection(
        client_factory=lambda: resumed_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=1,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    assert resumed.status == "complete"
    assert resumed_client.queries == []


def test_nonadvancing_cursor_closes_target_without_writing_duplicate_snapshots(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-history" / "v1"
    evidence_root = tmp_path / "artifacts" / "data" / "daily-nas-history"
    control_root = tmp_path / "market-data" / "collection-control-v1"
    request_gate = KisPaperMarketDataRateGate(control_root=control_root, clock=clock)
    token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root, clock=clock)
    first_client = _StalledHistoryClient(clock)

    first = run_kis_paper_daily_history_collection(
        client_factory=lambda: first_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=6,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    assert first.status == "complete"
    assert first.accepted_page_count == 6
    assert first.categorical_failure_count == 6
    assert first.chunk_attempt_count == 6
    assert all(state.state == "source_limited" for state in first.target_states)
    assert all(state.last_reason == "no_cursor_progress" for state in first.target_states)
    assert list(cache_root.glob("snapshot=*/manifest.json")) == []

    index = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    assert all(target["chunks"] == [] for target in index["targets"])

    resumed_client = _StalledHistoryClient(clock)
    resumed = run_kis_paper_daily_history_collection(
        client_factory=lambda: resumed_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=1,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    assert resumed.status == "complete"
    assert resumed_client.queries == []


def test_history_recovers_an_orphan_snapshot_before_collecting_a_new_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily-nas-history" / "v1"
    evidence_root = tmp_path / "artifacts" / "data" / "daily-nas-history"
    control_root = tmp_path / "market-data" / "collection-control-v1"
    request_gate = KisPaperMarketDataRateGate(control_root=control_root, clock=clock)
    token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root, clock=clock)
    original_write_index = daily_history._write_index
    writes = 0

    def interrupt_after_snapshot(*, root: Path, index: object) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("simulated interruption after snapshot publication")
        original_write_index(root=root, index=index)  # type: ignore[arg-type]

    monkeypatch.setattr(daily_history, "_write_index", interrupt_after_snapshot)
    with pytest.raises(OSError, match="simulated interruption"):
        run_kis_paper_daily_history_collection(
            client_factory=lambda: _HistoryClient(clock),  # type: ignore[arg-type]
            request_gate=request_gate,
            token_start_gate=token_gate,
            cache_root=cache_root,
            evidence_root=evidence_root,
            repo_root=repo_root,
            code_revision="git:test",
            max_chunks=1,
            max_runtime=timedelta(minutes=1),
            clock=clock,
            monotonic_clock=clock.monotonic,
        )
    monkeypatch.setattr(daily_history, "_write_index", original_write_index)

    assert len(list(cache_root.glob("snapshot=*/manifest.json"))) == 1
    interrupted_index = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    assert interrupted_index["targets"][0]["chunks"] == []

    resumed_client = _HistoryClient(clock)
    resumed = run_kis_paper_daily_history_collection(
        client_factory=lambda: resumed_client,  # type: ignore[arg-type]
        request_gate=request_gate,
        token_start_gate=token_gate,
        cache_root=cache_root,
        evidence_root=evidence_root,
        repo_root=repo_root,
        code_revision="git:test",
        max_chunks=1,
        max_runtime=timedelta(minutes=1),
        clock=clock,
        monotonic_clock=clock.monotonic,
    )

    recovered_index = json.loads((cache_root / "index.json").read_text(encoding="utf-8"))
    assert len(recovered_index["targets"][0]["chunks"]) == 1
    assert recovered_index["targets"][0]["next_anchor_date"] == "20260101"
    assert all(query.symbol != "AAPL" for query in resumed_client.queries)
    assert resumed.status == "collected"


def test_history_transport_only_opens_token_and_fixed_daily_routes() -> None:
    transport = UrllibKisPaperDailyHistoryTransport()
    opener = _RecordingOpener()
    transport._opener = opener  # type: ignore[assignment]
    transport.request(
        KisMarketDataRequest(
            method="POST",
            url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
            headers={"content-type": "application/json", "accept": "application/json"},
            json_body={
                "grant_type": "client_credentials",
                "appkey": "unit-app-key",
                "appsecret": "unit-app-secret",
            },
        )
    )
    transport.request(
        KisMarketDataRequest(
            method="GET",
            url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
            headers={"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
            query={
                "AUTH": "",
                "EXCD": "NAS",
                "SYMB": "AAPL",
                "GUBN": "0",
                "BYMD": "20260724",
                "MODP": "0",
            },
        )
    )

    opened = opener.requests
    assert [request.get_method() for request in opened] == ["POST", "GET"]  # type: ignore[union-attr]
    assert [urlsplit(request.full_url).path for request in opened] == [  # type: ignore[union-attr]
        KIS_PAPER_TOKEN_PATH,
        KIS_PAPER_DAILY_PATH,
    ]
    assert json.loads(opened[0].data.decode("utf-8")) == {  # type: ignore[union-attr]
        "grant_type": "client_credentials",
        "appkey": "unit-app-key",
        "appsecret": "unit-app-secret",
    }
    assert parse_qs(urlsplit(opened[1].full_url).query, keep_blank_values=True) == {  # type: ignore[union-attr]
        "AUTH": [""],
        "EXCD": ["NAS"],
        "SYMB": ["AAPL"],
        "GUBN": ["0"],
        "BYMD": ["20260724"],
        "MODP": ["0"],
    }

    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_MINUTE_PATH}",
                headers={},
                query={},
            )
        )

    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
                headers={},
                query={
                    "AUTH": "",
                    "EXCD": "NAS",
                    "SYMB": "SPY",
                    "GUBN": "0",
                    "BYMD": "20260724",
                    "MODP": "0",
                },
            )
        )
    assert len(opener.requests) == 2


def _row(date: str, *, close: str) -> KisPaperDailyRawRow:
    return KisPaperDailyRawRow(
        xymd=date,
        open="100",
        high=close,
        low="99",
        clos=close,
        tvol="12345",
    )
