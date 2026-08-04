from __future__ import annotations

import ast
import importlib.util
import json
import multiprocessing
import socket
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.data import kis_paper_daily_spy_stability_observer as observer
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_paper_daily_spy_head import (
    KisPaperDailySpyHeadSnapshot,
    collect_kis_paper_daily_spy_head_once,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OBSERVER_NOW = datetime(2026, 8, 4, 14, 15, tzinfo=UTC)
PRIOR_SESSION = "20260803"
CURRENT_SESSION = "20260804"


@dataclass
class _HeadClient:
    rows: tuple[KisPaperDailyRawRow, ...]

    def fetch_daily_raw_page(self, _query: KisPaperDailyQuery) -> object:
        return type("HeadPage", (), {"rows": self.rows})()


@dataclass
class _RecordingDailyClient:
    rows: tuple[KisPaperDailyRawRow, ...]
    queries: list[KisPaperDailyQuery] = field(default_factory=list)
    authentication_calls: int = 0

    def ensure_authenticated(self) -> None:
        self.authentication_calls += 1

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        return _daily_raw_page(query, self.rows)


class _NoClientFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> _RecordingDailyClient:
        self.calls += 1
        raise AssertionError("daily client must not be created")


class _AuthenticationFailureClient:
    def __init__(self) -> None:
        self.authentication_calls = 0
        self.dailyprice_calls = 0

    def ensure_authenticated(self) -> None:
        self.authentication_calls += 1
        raise KisPaperMarketDataError("auth_rejected")

    def fetch_daily_raw_page(self, _query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.dailyprice_calls += 1
        raise AssertionError("dailyprice GET must not start after authentication failure")


@dataclass
class _RecordingTransport:
    rows: tuple[KisPaperDailyRawRow, ...]
    requests: list[KisMarketDataRequest] = field(default_factory=list)

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        if request.method == "POST" and request.url.endswith(KIS_PAPER_TOKEN_PATH):
            return KisMarketDataResponse.from_payload({"access_token": "test-token"})
        if request.method == "GET" and request.url.endswith(KIS_PAPER_DAILY_PATH):
            return KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {},
                    "output2": [row.as_document() for row in self.rows],
                }
            )
        raise AssertionError("unexpected transport request")


def test_stable_measurement_filters_only_the_retained_prior_session_and_replays_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    artifact_root = tmp_path / "artifacts"
    client = _RecordingDailyClient(
        rows=(
            _row(CURRENT_SESSION, close="712.34"),
            _row(PRIOR_SESSION, close="701.23"),
        )
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        client_factory=lambda: client,
    )

    assert result.status == "stable"
    assert result.dailyprice_get_count == 1
    assert result.attempt_ordinal == 1
    assert client.authentication_calls == 1
    assert len(client.queries) == 1
    assert client.queries[0].symbol == "SPY"
    assert client.queries[0].exchange == "AMS"
    assert client.queries[0].adjustment_mode == "0"
    assert result.evidence_path is not None
    receipt_text = result.evidence_path.read_text(encoding="ascii")
    assert "712.34" not in receipt_text
    assert "701.23" not in receipt_text
    assert "test-token" not in receipt_text
    receipt = json.loads(receipt_text)
    assert receipt["provider_finality"] == "not_observed"
    assert receipt["virtual_paper_only"] is True
    assert receipt["nontransferable_to_live"] is True
    _assert_receipt_is_not_consumer_ready(receipt)

    def forbid_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("validator must not reach a network")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    replay = observer.validate_kis_paper_daily_spy_stability_receipt(
        result.evidence_path,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert replay.safe_payload() == receipt
    assert replay.status == "stable"


def test_changed_prior_session_row_is_changed_not_an_unreliable_result(tmp_path: Path) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    client = _RecordingDailyClient(
        rows=(
            _row(CURRENT_SESSION, close="712.34"),
            _row(PRIOR_SESSION, close="702.23"),
        )
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=tmp_path / "artifacts",
        repository_root=repository_root,
        client_factory=lambda: client,
    )

    assert result.status == "changed"
    assert result.reason == "prior_session_row_changed"
    assert result.dailyprice_get_count == 1
    assert result.response_row_sha256 != result.snapshot_row_sha256
    assert result.evidence_path is not None
    assert "unreliable" not in result.evidence_path.read_text(encoding="ascii").lower()


@pytest.mark.parametrize(
    ("mutator", "expected_reason"),
    (
        (
            lambda payload: payload["source"].update({"exchange": "NAS"}),
            "snapshot_unavailable",
        ),
        (
            lambda payload: payload.update({"collected_at": "invalid-timestamp"}),
            "snapshot_unavailable",
        ),
        (
            lambda payload: payload["collection"].update(
                {"last_retained_session": "2026-08-02"}
            ),
            "snapshot_unavailable",
        ),
    ),
)
def test_scope_or_timestamp_mismatch_fails_closed_before_client_creation(
    tmp_path: Path,
    mutator,
    expected_reason: str,
) -> None:
    cache_root, repository_root, snapshot = _head_snapshot(tmp_path)
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    mutator(manifest)
    snapshot.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    no_client = _NoClientFactory()

    result = _observe(
        cache_root=cache_root,
        artifact_root=tmp_path / "artifacts",
        repository_root=repository_root,
        client_factory=no_client,
    )

    assert result.status == "unavailable"
    assert result.reason == expected_reason
    assert result.dailyprice_get_count == 0
    assert result.attempt_ordinal is None
    assert no_client.calls == 0


def test_stale_snapshot_and_outside_window_never_create_the_daily_client(tmp_path: Path) -> None:
    stale_cache, stale_repository, _snapshot = _head_snapshot(
        tmp_path / "stale",
        collected_at=OBSERVER_NOW - timedelta(minutes=91),
    )
    stale_factory = _NoClientFactory()

    stale = _observe(
        cache_root=stale_cache,
        artifact_root=tmp_path / "stale-artifacts",
        repository_root=stale_repository,
        client_factory=stale_factory,
    )

    assert stale.status == "unavailable"
    assert stale.reason == "snapshot_age_outside_window"
    assert stale.snapshot_age_bucket == "over_90_minutes"
    assert stale.dailyprice_get_count == 0
    assert stale.attempt_ordinal is None
    assert stale_factory.calls == 0

    fresh_cache, fresh_repository, _fresh_snapshot = _head_snapshot(tmp_path / "outside")
    outside_factory = _NoClientFactory()
    outside = _observe(
        cache_root=fresh_cache,
        artifact_root=tmp_path / "outside-artifacts",
        repository_root=fresh_repository,
        client_factory=outside_factory,
        observed_at=OBSERVER_NOW - timedelta(minutes=20),
    )

    assert outside.status == "outside_window"
    assert outside.reason == "observer_window_outside"
    assert outside.dailyprice_get_count == 0
    assert outside.attempt_ordinal is None
    assert outside_factory.calls == 0


def test_missing_prior_session_response_fails_closed_after_the_single_call(tmp_path: Path) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    client = _RecordingDailyClient(rows=(_row(CURRENT_SESSION, close="712.34"),))

    result = _observe(
        cache_root=cache_root,
        artifact_root=tmp_path / "artifacts",
        repository_root=repository_root,
        client_factory=lambda: client,
    )

    assert result.status == "unavailable"
    assert result.reason == "dailyprice_response_unavailable"
    assert result.dailyprice_get_count == 1
    assert len(client.queries) == 1


def test_ten_dailyprice_attempts_exhaust_budget_without_creating_a_client(
    tmp_path: Path,
) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    artifact_root = tmp_path / "artifacts"
    client = _RecordingDailyClient(rows=(_row(PRIOR_SESSION, close="701.23"),))

    for offset in range(observer.KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS):
        result = _observe(
            cache_root=cache_root,
            artifact_root=artifact_root,
            repository_root=repository_root,
            client_factory=lambda: client,
            observed_at=OBSERVER_NOW + timedelta(seconds=offset),
        )
        assert result.dailyprice_get_count == 1
        assert result.attempt_ordinal == offset + 1

    no_client = _NoClientFactory()
    exhausted = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        client_factory=no_client,
        observed_at=OBSERVER_NOW + timedelta(seconds=20),
    )

    assert len(client.queries) == observer.KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_MAX_VALID_ATTEMPTS
    assert exhausted.status == "unavailable"
    assert exhausted.reason == "observation_budget_exhausted"
    assert exhausted.dailyprice_get_count == 0
    assert exhausted.attempt_ordinal is None
    assert exhausted.evidence_path is None
    assert no_client.calls == 0


def test_authentication_failure_does_not_consume_a_dailyprice_attempt(tmp_path: Path) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    artifact_root = tmp_path / "artifacts"
    failing_client = _AuthenticationFailureClient()

    unavailable = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        client_factory=lambda: failing_client,
    )

    assert unavailable.status == "unavailable"
    assert unavailable.reason == "dailyprice_auth_unavailable"
    assert unavailable.dailyprice_get_count == 0
    assert unavailable.attempt_ordinal is None
    assert failing_client.authentication_calls == 1
    assert failing_client.dailyprice_calls == 0

    succeeding_client = _RecordingDailyClient(rows=(_row(PRIOR_SESSION, close="701.23"),))
    recovered = _observe(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        client_factory=lambda: succeeding_client,
        observed_at=OBSERVER_NOW + timedelta(seconds=1),
    )

    assert recovered.status == "stable"
    assert recovered.attempt_ordinal == 1
    assert len(succeeding_client.queries) == 1


def test_client_factory_failure_does_not_consume_a_dailyprice_attempt(tmp_path: Path) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    calls = 0

    def failing_factory() -> _RecordingDailyClient:
        nonlocal calls
        calls += 1
        raise KisPaperMarketDataError("config_missing")

    unavailable = _observe(
        cache_root=cache_root,
        artifact_root=tmp_path / "artifacts",
        repository_root=repository_root,
        client_factory=failing_factory,
    )

    assert unavailable.status == "unavailable"
    assert unavailable.reason == "dailyprice_client_unavailable"
    assert unavailable.dailyprice_get_count == 0
    assert unavailable.attempt_ordinal is None
    assert calls == 1


def test_cross_process_lock_prevents_a_second_observer_from_using_budget_or_client(
    tmp_path: Path,
) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    artifact_root = tmp_path / "artifacts"
    receipt_directory = artifact_root.joinpath(
        *observer.KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_PARTS
    )
    receipt_directory.mkdir(parents=True)
    lock_path = receipt_directory.parent / observer._OBSERVER_LOCK_FILENAME
    context = multiprocessing.get_context("spawn")
    acquired = context.Queue()
    release = context.Event()
    holder = context.Process(
        target=_hold_stability_observer_lock,
        args=(str(lock_path), acquired, release),
    )
    holder.start()
    try:
        assert acquired.get(timeout=10) is True
        no_client = _NoClientFactory()
        blocked = _observe(
            cache_root=cache_root,
            artifact_root=artifact_root,
            repository_root=repository_root,
            client_factory=no_client,
        )
        assert blocked.status == "unavailable"
        assert blocked.reason == "observer_lock_held"
        assert blocked.dailyprice_get_count == 0
        assert blocked.attempt_ordinal is None
        assert no_client.calls == 0
    finally:
        release.set()
        holder.join(timeout=10)
    assert holder.exitcode == 0


def test_existing_market_client_uses_only_the_virtual_host_token_and_one_dailyprice_get(
    tmp_path: Path,
) -> None:
    cache_root, repository_root, _snapshot = _head_snapshot(tmp_path)
    transport = _RecordingTransport(
        rows=(
            _row(CURRENT_SESSION, close="712.34"),
            _row(PRIOR_SESSION, close="701.23"),
        )
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
        max_daily_page_attempts=1,
        max_minute_page_attempts=1,
    )

    result = _observe(
        cache_root=cache_root,
        artifact_root=tmp_path / "artifacts",
        repository_root=repository_root,
        client_factory=lambda: client,
    )

    assert result.status == "stable"
    daily_requests = [request for request in transport.requests if request.method == "GET"]
    assert len(daily_requests) == 1
    request = daily_requests[0]
    assert request.url == f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}"
    assert request.query == {
        "AUTH": "",
        "EXCD": "AMS",
        "SYMB": "SPY",
        "GUBN": "0",
        "BYMD": "20260804",
        "MODP": "0",
    }
    assert {request.url for request in transport.requests} == {
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
    }
    assert all(
        "account" not in request.url and "order" not in request.url
        for request in transport.requests
    )


def test_worker_uses_the_shared_control_gates_before_constructing_the_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_stability_worker_script()
    gates: list[object] = []
    transport_kwargs: dict[str, object] = {}
    client_kwargs: dict[str, object] = {}

    class FakeGate:
        def __init__(self, *, control_root: Path) -> None:
            self.control_root = control_root
            gates.append(self)

    class FakeTransport:
        def __init__(self, **kwargs: object) -> None:
            transport_kwargs.update(kwargs)

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_kwargs.update(kwargs)

    class FakeObservation:
        def safe_payload(self) -> dict[str, str]:
            return {"status": "unavailable"}

    def fake_observe(**kwargs: object) -> FakeObservation:
        factory = kwargs["client_factory"]
        assert callable(factory)
        factory()
        return FakeObservation()

    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", FakeGate)
    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", FakeGate)
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", FakeTransport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", FakeClient)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda *, environment: object(),
    )
    monkeypatch.setattr(script, "observe_kis_paper_daily_spy_stability", fake_observe)

    script.main(["--execute"], environment={"THERICHER_MODE": "off"})

    assert [gate.control_root for gate in gates] == [
        script._CANONICAL_CONTROL_ROOT,
        script._CANONICAL_CONTROL_ROOT,
    ]
    assert transport_kwargs == {
        "request_gate": gates[0],
        "token_start_gate": gates[1],
    }
    assert client_kwargs["config"] is not None
    assert client_kwargs["transport"] is not None
    assert client_kwargs["max_minute_page_attempts"] == 1
    assert client_kwargs["max_daily_page_attempts"] == 1
    assert json.loads(capsys.readouterr().out) == {"status": "unavailable"}


def test_observer_is_not_exported_to_engine_paths_and_has_no_order_or_account_surface() -> None:
    leaf = "kis_paper_daily_spy_stability_observer"
    package_root = REPOSITORY_ROOT / "src" / "thericher_v2"
    for directory in ("research", "models", "execution"):
        for path in (package_root / directory).rglob("*.py"):
            assert leaf not in path.read_text(encoding="utf-8")
    assert leaf not in (package_root / "data" / "_public_api.py").read_text(encoding="utf-8")

    tree = ast.parse(Path(observer.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        "kis_readonly" in module or "kis_paper_canary" in module
        for module in imported_modules
    )

    worker_source = (
        REPOSITORY_ROOT / "scripts" / "observe_kis_paper_daily_spy_stability.py"
    ).read_text(encoding="utf-8")
    for forbidden in (".env", "KIS_LIVE", "KIS_PAPER_ACCOUNT", "account", "order"):
        assert forbidden not in worker_source
    assert "load_kis_paper_market_data_environment_config" in worker_source
    assert "max_daily_page_attempts=1" in worker_source
    assert "KisPaperMarketDataRateGate" in worker_source
    assert "KisPaperMarketDataTokenStartGate" in worker_source
    assert "request_gate=request_gate" in worker_source
    assert "token_start_gate=token_start_gate" in worker_source

    validator_source = (
        REPOSITORY_ROOT / "scripts" / "validate_kis_paper_daily_spy_stability_receipt.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("os.environ", "urllib", "socket", "KIS_PAPER_APP_KEY", "KIS_LIVE"):
        assert forbidden not in validator_source


def test_observer_docker_profile_and_schedule_are_data_only_and_not_installed() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    service = compose.split("  kis-paper-daily-spy-stability-observer:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-spy-session:", maxsplit=1
    )[0]

    assert 'profiles: ["kis-paper-daily-spy-stability-observer"]' in service
    assert "read_only: true" in service
    assert "- /tmp" in service
    assert "scripts/observe_kis_paper_daily_spy_stability.py" in service
    assert "--control-root" in service
    assert "/app/collection_control" in service
    assert "KIS_PAPER_APP_KEY" in service
    assert "KIS_PAPER_APP_SECRET" in service
    assert "KIS_PAPER_ACCOUNT" not in service
    assert "KIS_LIVE" not in service
    assert "thericher-v2-runtime" not in service
    assert "thericher-v2-paper-canary-private" not in service
    assert "emergency" not in service
    assert "${THERICHER_HOST_MARKET_DATA_ROOT:-D:/market_data}:/app/market_data:ro" in service
    assert (
        "${THERICHER_HOST_MARKET_DATA_ROOT:-D:/market_data}/us_equities/kis_paper_private/"
        "collection-control-v1:/app/collection_control"
    ) in service
    assert (
        "${THERICHER_HOST_MODEL_ARTIFACT_ROOT:-D:/thericher-v2/model-artifacts}:/app/model_artifacts"
        in service
    )
    assert "network_mode: none" not in service

    schedule = (REPOSITORY_ROOT / "scripts" / "install_kis_paper_schedules.ps1").read_text(
        encoding="ascii"
    )
    task_name = "thericher-kis-paper-daily-spy-stability-observer"
    assert schedule.count(f'Name = "{task_name}"') == 1
    entry = schedule.split(f'Name = "{task_name}"', maxsplit=1)[1].split("    },", maxsplit=1)[0]
    assert 'Profile = "kis-paper-daily-spy-stability-observer"' in entry
    assert 'Service = "kis-paper-daily-spy-stability-observer"' in entry
    assert 'ImageServices = @("kis-paper-daily-spy-stability-observer")' in entry
    assert 'At = "23:15"' in entry
    assert 'DaysOfWeek = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")' in entry
    assert "RecoverMissedRun = $false" in entry
    assert "ExecutionLimitMinutes = 5" in entry
    assert "Runner" not in entry
    assert f'$selectedSchedules.Name -contains "{task_name}"' in schedule
    assert "Start-ScheduledTask" not in schedule


def _observe(
    *,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
    client_factory,
    observed_at: datetime = OBSERVER_NOW,
    snapshot_loader=None,
):
    kwargs = {}
    if snapshot_loader is not None:
        kwargs["snapshot_loader"] = snapshot_loader
    return observer.observe_kis_paper_daily_spy_stability(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
        client_factory=client_factory,
        **kwargs,
    )


def _head_snapshot(
    tmp_path: Path,
    *,
    collected_at: datetime = OBSERVER_NOW - timedelta(minutes=60),
) -> tuple[Path, Path, KisPaperDailySpyHeadSnapshot]:
    cache_root = tmp_path / "daily-head"
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    result = collect_kis_paper_daily_spy_head_once(
        _HeadClient(
            rows=(
                _row("20260731", close="690.12"),
                _row(PRIOR_SESSION, close="701.23"),
                _row(CURRENT_SESSION, close="712.34"),
            )
        ),
        cache_root=cache_root,
        repository_root=repository_root,
        observed_at=collected_at,
    )
    assert result.snapshot is not None
    return cache_root, repository_root, result.snapshot


def _daily_raw_page(
    query: KisPaperDailyQuery,
    rows: tuple[KisPaperDailyRawRow, ...],
) -> KisPaperDailyRawPage:
    dates = tuple(row.xymd for row in rows)
    return KisPaperDailyRawPage(
        page=KisPaperDailyPage(
            query=query,
            row_count=len(rows),
            newest_date=max(dates) if dates else None,
            oldest_date=min(dates) if dates else None,
            required_ohlcv_fields_present=bool(rows),
            continuation_available=False,
            continuation_value=None,
        ),
        rows=rows,
    )


def _row(session: str, *, close: str) -> KisPaperDailyRawRow:
    return KisPaperDailyRawRow(
        xymd=session,
        open="700.00",
        high="720.00",
        low="690.00",
        clos=close,
        tvol="123456",
    )


def _hold_stability_observer_lock(lock_path: str, acquired, release) -> None:
    with observer._try_exclusive_observer_lock(Path(lock_path)) as locked:
        acquired.put(locked)
        if locked:
            release.wait(timeout=10)


def _load_stability_worker_script() -> ModuleType:
    script_path = REPOSITORY_ROOT / "scripts" / "observe_kis_paper_daily_spy_stability.py"
    spec = importlib.util.spec_from_file_location(
        "observe_kis_paper_daily_spy_stability_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_receipt_is_not_consumer_ready(payload: Mapping[str, object]) -> None:
    rendered = json.dumps(payload, sort_keys=True).lower()
    for forbidden in (
        "capability",
        "qualified",
        "qualification",
        "model",
        "prediction",
        "engine",
        "consumer",
        "paper_permission",
        "performance",
    ):
        assert forbidden not in rendered
