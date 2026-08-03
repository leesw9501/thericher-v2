from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_broad_d1_adjustment_semantics_probe as probe
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanelSelection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_DAILY_TR_ID,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyPage,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperDailyAdjustmentProbeTransport,
    UrllibKisPaperMarketDataTransport,
)


class _ProbeClient:
    def __init__(
        self,
        *,
        comparison_changes: bool = False,
        fail_mode_one: bool = False,
        nonrepeatable_mode_zero: bool = False,
    ) -> None:
        self.comparison_changes = comparison_changes
        self.fail_mode_one = fail_mode_one
        self.nonrepeatable_mode_zero = nonrepeatable_mode_zero
        self.auth_calls = 0
        self.queries: list[KisPaperDailyAdjustmentProbeQuery] = []
        self._daily_attempts = 0
        self._mode_zero_calls_by_key: dict[str, int] = {}

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        return KisPaperMarketDataCallCounts(
            token_attempts=1 if self.auth_calls else 0,
            minute_page_attempts=0,
            daily_page_attempts=self._daily_attempts,
        )

    def ensure_authenticated(self) -> None:
        self.auth_calls += 1

    def fetch_daily_raw_page(
        self, query: KisPaperDailyAdjustmentProbeQuery
    ) -> KisPaperDailyRawPage:
        self.queries.append(query)
        self._daily_attempts += 1
        if query.adjustment_mode == "1" and self.fail_mode_one:
            raise KisPaperMarketDataError("daily_response_rejected")
        key = f"{query.symbol}/{query.exchange}:{query.by_date}"
        zero_index = self._mode_zero_calls_by_key.get(key, 0)
        if query.adjustment_mode == "0":
            self._mode_zero_calls_by_key[key] = zero_index + 1
        close = "700.001"
        if query.adjustment_mode == "1" and self.comparison_changes:
            close = "700.009"
        if query.adjustment_mode == "0" and self.nonrepeatable_mode_zero and zero_index == 1:
            close = "700.017"
        row = KisPaperDailyRawRow(
            xymd=query.by_date,
            open="700.000",
            high="700.020",
            low="699.990",
            clos=close,
            tvol="12345",
        )
        page = KisPaperDailyPage(
            query=query,
            row_count=1,
            newest_date=query.by_date,
            oldest_date=query.by_date,
            required_ohlcv_fields_present=True,
            continuation_available=False,
            continuation_value=None,
        )
        return KisPaperDailyRawPage(page=page, rows=(row,))


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


class _KisShapeResponse:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers: dict[str, str] = {}
        self._body = body

    def __enter__(self) -> _KisShapeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _KisShapeRecordingOpener:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def open(self, request: object, *, timeout: float) -> _KisShapeResponse:
        assert timeout > 0
        self.requests.append(request)
        path = urlsplit(request.full_url).path  # type: ignore[union-attr]
        if path == KIS_PAPER_TOKEN_PATH:
            return _KisShapeResponse(b'{"access_token":"test-token"}')
        query = urlsplit(request.full_url).query  # type: ignore[union-attr]
        by_date = query.split("BYMD=")[1].split("&", maxsplit=1)[0]
        return _KisShapeResponse(
            json.dumps(
                {
                    "rt_cd": "0",
                    "output1": {},
                    "output2": [
                        {
                            "xymd": by_date,
                            "open": "700.000",
                            "high": "700.020",
                            "low": "699.990",
                            "clos": "700.001",
                            "tvol": "12345",
                        }
                    ],
                }
            ).encode("utf-8")
        )


def test_fixed_witness_selection_reuses_one_token_and_writes_only_aggregate_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repository.mkdir()
    artifact_root.mkdir()
    _deny_external_access(monkeypatch)
    selection = _selection(tmp_path / "panel")

    plan = probe.prepare_kis_broad_d1_adjustment_semantics_probe(selection)
    client = _ProbeClient()
    result = probe.run_kis_broad_d1_adjustment_semantics_probe(
        plan=plan,
        client=client,
        artifact_root=artifact_root,
        run_label="unit-unchanged",
        repo_root=repository,
    )

    assert len(plan.witnesses) == 2
    assert result.outcome.status == "unchanged"
    assert result.outcome.reason == "all_pairs_equal"
    assert client.auth_calls == 1
    assert client.call_counts == KisPaperMarketDataCallCounts(
        token_attempts=1,
        minute_page_attempts=0,
        daily_page_attempts=6,
    )
    assert [query.adjustment_mode for query in client.queries] == ["0", "1", "0"] * 2
    assert result.receipt_path.is_relative_to(artifact_root)
    assert not result.receipt_path.is_relative_to(repository)

    text = result.receipt_path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["scope"]["model_eligible"] is False
    assert payload["scope"]["paper_trading_eligible"] is False
    assert payload["artifact_policy"]["raw_market_data_persisted"] is False
    assert "A001" not in text
    assert "20200102" not in text
    assert "700.001" not in text
    assert "paper-secret" not in text
    _assert_no_raw_keys(payload)


def test_probe_classifies_changed_only_after_repeatable_consistent_witness_pairs(
    tmp_path: Path,
) -> None:
    plan = probe.prepare_kis_broad_d1_adjustment_semantics_probe(_selection(tmp_path / "panel"))
    result = probe.assess_kis_broad_d1_adjustment_semantics_probe(
        plan,
        _ProbeClient(comparison_changes=True),
    )

    assert result.status == "changed"
    assert result.reason == "all_pairs_different"
    assert result.accepted_daily_response_count == 6


def test_probe_contains_alternate_mode_rejection_without_retrying(
    tmp_path: Path,
) -> None:
    plan = probe.prepare_kis_broad_d1_adjustment_semantics_probe(_selection(tmp_path / "panel"))
    client = _ProbeClient(fail_mode_one=True)

    result = probe.assess_kis_broad_d1_adjustment_semantics_probe(plan, client)

    assert result.status == "unsupported"
    assert result.reason == "alternate_representation_rejected"
    assert result.accepted_daily_response_count == 1
    assert result.categorical_error_count == 1
    assert client.call_counts.daily_page_attempts == 2
    assert [query.adjustment_mode for query in client.queries] == ["0", "1"]


def test_probe_marks_nonrepeatable_control_inconsistent(tmp_path: Path) -> None:
    plan = probe.prepare_kis_broad_d1_adjustment_semantics_probe(_selection(tmp_path / "panel"))

    result = probe.assess_kis_broad_d1_adjustment_semantics_probe(
        plan,
        _ProbeClient(nonrepeatable_mode_zero=True),
    )

    assert result.status == "inconsistent"
    assert result.reason == "mode_zero_nonrepeatable"
    assert result.call_counts.daily_page_attempts == 3


def test_probe_closes_without_client_when_fixed_selector_has_no_witness(tmp_path: Path) -> None:
    plan = probe.prepare_kis_broad_d1_adjustment_semantics_probe(
        _selection(tmp_path / "panel", event_count=0)
    )

    result = probe.assess_kis_broad_d1_adjustment_semantics_probe(plan, None)

    assert result.status == "unavailable"
    assert result.reason == "no_fixed_witness"
    assert result.call_counts == KisPaperMarketDataCallCounts(0, 0, 0)


def test_dedicated_transport_permits_only_token_and_witness_scoped_daily_routes() -> None:
    transport = UrllibKisPaperDailyAdjustmentProbeTransport(
        daily_symbol_exchanges={"A001": frozenset({"NAS"})}
    )
    opener = _RecordingOpener()
    transport._opener = opener  # type: ignore[assignment]
    token_request = KisMarketDataRequest(
        method="POST",
        url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
        headers={"content-type": "application/json", "accept": "application/json"},
        json_body={
            "grant_type": "client_credentials",
            "appkey": "unit-app-key",
            "appsecret": "unit-app-secret",
        },
    )
    daily_request = KisMarketDataRequest(
        method="GET",
        url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
        headers={"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
        query={
            "AUTH": "",
            "EXCD": "NAS",
            "SYMB": "A001",
            "GUBN": "0",
            "BYMD": "20200102",
            "MODP": "1",
        },
        daily_adjustment_modes=frozenset({"0", "1"}),
    )
    transport.request(token_request)
    transport.request(daily_request)

    assert [request.get_method() for request in opener.requests] == ["POST", "GET"]  # type: ignore[union-attr]
    assert [urlsplit(request.full_url).path for request in opener.requests] == [  # type: ignore[union-attr]
        KIS_PAPER_TOKEN_PATH,
        KIS_PAPER_DAILY_PATH,
    ]
    for method, url in (
        ("GET", f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_MINUTE_PATH}"),
        ("GET", f"{KIS_PAPER_MARKET_DATA_BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance"),
        ("POST", f"{KIS_PAPER_MARKET_DATA_BASE_URL}/uapi/overseas-stock/v1/trading/order"),
        ("GET", "https://openapi.koreainvestment.com:9443/oauth2/tokenP"),
    ):
        with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
            transport.request(
                KisMarketDataRequest(
                    method=method,
                    url=url,
                    headers={},
                    query={},
                    json_body={} if method == "POST" else None,
                )
            )
    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
                headers={"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
                query={
                    "AUTH": "",
                    "EXCD": "NAS",
                    "SYMB": "A001",
                    "GUBN": "0",
                    "BYMD": "20200102",
                    "MODP": "0",
                },
            )
        )
    assert len(opener.requests) == 2


def test_normal_market_data_transport_cannot_open_adjustment_probe_mode() -> None:
    transport = UrllibKisPaperMarketDataTransport()
    opener = _RecordingOpener()
    transport._opener = opener  # type: ignore[assignment]

    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
                headers={"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
                query={
                    "AUTH": "",
                    "EXCD": "NAS",
                    "SYMB": "A001",
                    "GUBN": "0",
                    "BYMD": "20200102",
                    "MODP": "1",
                },
                daily_adjustment_modes=frozenset({"0", "1"}),
            )
        )

    assert opener.requests == []


def test_real_client_reuses_one_token_and_only_opens_six_daily_witness_calls(
    tmp_path: Path,
) -> None:
    plan = probe.prepare_kis_broad_d1_adjustment_semantics_probe(_selection(tmp_path / "panel"))
    transport = UrllibKisPaperDailyAdjustmentProbeTransport(
        daily_symbol_exchanges=plan.daily_symbol_exchanges
    )
    opener = _KisShapeRecordingOpener()
    transport._opener = opener  # type: ignore[assignment]
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
        max_daily_page_attempts=6,
    )

    result = probe.assess_kis_broad_d1_adjustment_semantics_probe(plan, client)

    assert result.status == "unchanged"
    assert client.call_counts == KisPaperMarketDataCallCounts(1, 0, 6)
    paths = [urlsplit(request.full_url).path for request in opener.requests]  # type: ignore[union-attr]
    assert paths == [KIS_PAPER_TOKEN_PATH, *([KIS_PAPER_DAILY_PATH] * 6)]
    queries = [urlsplit(request.full_url).query for request in opener.requests[1:]]  # type: ignore[union-attr]
    assert [query.split("MODP=")[1] for query in queries] == ["0", "1", "0"] * 2


def _selection(root: Path, *, event_count: int = 2) -> KisPaperDailyBroadPanelSelection:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    dataset_hash = "sha256:" + "a" * 64
    target_keys = tuple(f"A{index:03d}/NAS" for index in range(1, 129))
    starts = tuple(datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(801))
    bars_by_target: dict[str, object] = {}
    for target_index, target_key in enumerate(target_keys):
        symbol = target_key.partition("/")[0]
        bars = tuple(
            _bar(
                symbol=symbol,
                start=start,
                event=target_index < event_count and start == starts[1],
            )
            for start in starts
        )
        bars_by_target[target_key] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
    return KisPaperDailyBroadPanelSelection(
        dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
        dataset_hash=dataset_hash,
        manifest_sha256="sha256:" + "b" * 64,
        materialization_receipt_sha256="sha256:" + "c" * 64,
        index_sha256="sha256:" + "d" * 64,
        source_root=root,
        full_target_count=2119,
        coverage_eligible_target_count=1643,
        minimum_bar_count=801,
        common_session_count=800,
        terminal_buffer_sessions=1,
        raw_byte_attested_target_count=128,
        selected_target_keys=target_keys,
        bars_by_target=MappingProxyType(bars_by_target),
    )


def _bar(*, symbol: str, start: datetime, event: bool) -> Bar:
    value = Decimal("100")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start,
        open=value,
        high=Decimal("300") if event else Decimal("101"),
        low=Decimal("100") if event else Decimal("99"),
        close=value,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("adjustment probe logic must use only its supplied client")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_raw_keys(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "timestamp",
        "timestamps",
        "date",
        "dates",
        "symbol",
        "symbols",
        "sourcepath",
        "workdir",
        "eventlog",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_keys(nested)
