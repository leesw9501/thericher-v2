from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE,
    KisPaperIntradayRuntimeWindow,
    KisPaperIntradayRuntimeWindowLocalAvailability,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_paper_prospective_qqq_session import (
    run_kis_paper_prospective_qqq_session,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlySnapshot,
)
from thericher_v2.execution.paper_decision_bridge import receipt_attribution_ref

_SESSION_DATE = date(2026, 7, 20)


def test_preview_replays_locally_without_constructing_a_kis_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_catalog(monkeypatch, catalog)
    client = _FailClient()

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=False,
        cancel_after_submit=True,
        client=client,
        now=catalog.bars[-1].end_ts,
    )

    assert outcome.status == "preview"
    assert outcome.loop is not None
    assert outcome.loop.local_paper_replay is not None
    assert outcome.loop.local_paper_replay.fill_source == "local_paper"
    assert client.calls == []


def test_late_local_retention_never_reads_account_or_quote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_catalog(monkeypatch, catalog)
    module = __import__(
        "thericher_v2.execution.kis_paper_prospective_qqq_session",
        fromlist=["placeholder"],
    )

    def unavailable_local_input(*_args, runtime_window, decided_at, **_kwargs):
        return _local_input_availability(
            runtime_window=runtime_window,
            decided_at=decided_at,
            latest_local_retained_at=decided_at + timedelta(microseconds=1),
        )

    monkeypatch.setattr(
        module,
        "attest_kis_paper_intraday_runtime_window_local_availability",
        unavailable_local_input,
    )
    client = _FailClient()

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        client=client,
        now=catalog.bars[-1].end_ts,
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "runtime_window_not_locally_available"
    assert outcome.loop is not None
    assert outcome.local_input_availability is not None
    assert outcome.local_input_availability.local_input_available_by_decision is False
    assert client.calls == []
    rendered = outcome.evidence_path.read_text(encoding="ascii")
    assert '"local_input_available_by_decision": false' in rendered
    assert "not-used" not in rendered


def test_unavailable_local_retention_never_reads_account_or_quote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_catalog(monkeypatch, catalog)
    module = __import__(
        "thericher_v2.execution.kis_paper_prospective_qqq_session",
        fromlist=["placeholder"],
    )

    def unavailable_local_input(*_args, **_kwargs):
        raise ValueError("local retention is unavailable")

    monkeypatch.setattr(
        module,
        "attest_kis_paper_intraday_runtime_window_local_availability",
        unavailable_local_input,
    )
    client = _FailClient()

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        client=client,
        now=catalog.bars[-1].end_ts,
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "runtime_window_local_availability_unavailable"
    assert outcome.loop is not None
    assert outcome.local_input_availability is None
    assert client.calls == []


def test_flat_qqq_entry_reaches_only_the_receipt_canary_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_catalog(monkeypatch, catalog)
    client = _FlatQqqClient(captured_at=catalog.bars[-1].end_ts)
    calls: dict[str, object] = {}

    def prepare(receipt, *, limit_input, as_of):
        assert receipt.decision_class == "enter"
        assert limit_input is client.limit_input
        calls["prepared_at"] = as_of
        return SimpleNamespace(
            status="ready",
            receipt_ref=receipt_attribution_ref(receipt),
            kis_paper_decision=SimpleNamespace(side="buy"),
            safe_payload=lambda: {
                "kind": "paper_decision_bridge_result",
                "route": "kis_paper",
                "status": "ready",
            },
        )

    def run_canary(prepared, **kwargs):
        submit_permitted = kwargs["submit_permitted"]
        calls["canary"] = {
            "prepared": prepared,
            "execute": kwargs["execute"],
            "cancel_after_submit": kwargs["cancel_after_submit"],
            "submission_permitted": (
                submit_permitted(catalog.bars[-1].end_ts),
                submit_permitted(
                    catalog.bars[-1].end_ts
                    + KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE
                    + timedelta(microseconds=1)
                ),
            ),
        }
        return SimpleNamespace(
            run_id="receipt-" + prepared.receipt_ref.removeprefix("sha256:"),
            reason_code="cancelled",
            safe_payload=lambda: {
                "kind": "kis_paper_canary_outcome",
                "phase": "cancelled",
                "paper_only": True,
            },
        )

    module = __import__(
        "thericher_v2.execution.kis_paper_prospective_qqq_session",
        fromlist=["placeholder"],
    )
    monkeypatch.setattr(module, "prepare_kis_paper_qqq_receipt_decision", prepare)
    monkeypatch.setattr(module, "run_kis_paper_receipt_canary", run_canary)

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        state_root=tmp_path / "canary",
        runtime_projection_path=tmp_path / "runtime" / "projection.json",
        paper_account_snapshot_path=tmp_path / "runtime" / "account.json",
        emergency_state_path=tmp_path / "emergency" / "state.json",
        execution_control_path=tmp_path / "emergency" / "control.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        client=client,
        now=catalog.bars[-1].end_ts,
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "cancelled"
    assert client.calls == ["snapshot", "limit_input"]
    assert calls["canary"] is not None
    assert calls["canary"]["execute"] is True
    assert calls["canary"]["cancel_after_submit"] is True
    assert calls["canary"]["submission_permitted"] == (True, False)
    assert outcome.position_resolution is not None
    assert outcome.position_resolution.action == "buy"
    rendered = outcome.evidence_path.read_text(encoding="ascii")
    assert "not-used" not in rendered
    assert "101.00" not in rendered
    assert '"price"' not in rendered


def test_missing_runtime_window_never_reads_account_or_prepares_an_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(45)
    _install_catalog(monkeypatch, catalog)
    client = _FailClient()

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        client=client,
        now=catalog.bars[-1].end_ts,
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "runtime_window_missing"
    assert outcome.loop is not None
    assert outcome.loop.receipt.reason_class == "input_unavailable"
    assert client.calls == []
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["loop"]["local_paper_replay"] is None
    assert payload["canary"] is None


def test_stale_runtime_window_never_reads_account_or_prepares_an_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(90)
    _install_catalog(monkeypatch, catalog)
    client = _FailClient()

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        client=client,
        now=catalog.bars[-1].end_ts + timedelta(minutes=2, microseconds=1),
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "runtime_window_stale"
    assert outcome.loop is not None
    assert outcome.loop.window.freshness.category == "over_budget"
    assert outcome.pre_account_freshness is None
    assert outcome.pre_submit_freshness is None
    assert client.calls == []
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["loop"]["window"]["freshness"]["lag_category"] == "over_budget"
    assert payload["pre_account_freshness"] is None
    assert payload["pre_submit_freshness"] is None
    assert payload["canary"] is None


def test_runtime_window_expiring_during_preparation_never_reaches_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_catalog(monkeypatch, catalog)
    client = _FlatQqqClient(captured_at=catalog.bars[-1].end_ts)
    calls: list[datetime] = [
        catalog.bars[-1].end_ts,
        catalog.bars[-1].end_ts,
        catalog.bars[-1].end_ts,
        catalog.bars[-1].end_ts,
        catalog.bars[-1].end_ts,
        catalog.bars[-1].end_ts + timedelta(minutes=2, microseconds=1),
    ]

    def clock() -> datetime:
        return calls.pop(0)

    def prepare(receipt, *, limit_input, as_of):
        assert receipt.decision_class == "enter"
        assert limit_input is client.limit_input
        assert as_of == catalog.bars[-1].end_ts
        return SimpleNamespace(
            status="ready",
            receipt_ref=receipt_attribution_ref(receipt),
            kis_paper_decision=SimpleNamespace(side="buy"),
            safe_payload=lambda: {
                "kind": "paper_decision_bridge_result",
                "route": "kis_paper",
                "status": "ready",
            },
        )

    def fail_canary(*_args, **_kwargs):
        raise AssertionError("expired runtime window must not reach the canary")

    module = __import__(
        "thericher_v2.execution.kis_paper_prospective_qqq_session",
        fromlist=["placeholder"],
    )
    monkeypatch.setattr(module, "prepare_kis_paper_qqq_receipt_decision", prepare)
    monkeypatch.setattr(module, "run_kis_paper_receipt_canary", fail_canary)

    outcome = run_kis_paper_prospective_qqq_session(
        environment={"KIS_PAPER_APP_KEY": "not-used"},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        client=client,
        clock=clock,
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "runtime_window_expired_during_preparation"
    assert outcome.pre_submit_freshness is not None
    assert outcome.pre_submit_freshness.category == "over_budget"
    assert client.calls == ["snapshot", "limit_input"]
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["pre_submit_freshness"]["lag_category"] == "over_budget"
    assert payload["canary"] is None


def test_runtime_window_expiring_before_account_never_constructs_a_kis_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    _install_catalog(monkeypatch, catalog)
    calls = [
        catalog.bars[-1].end_ts,
        catalog.bars[-1].end_ts + KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE + timedelta(microseconds=1),
    ]

    def clock() -> datetime:
        return calls.pop(0)

    def fail_client_construction(**_kwargs: object) -> None:
        raise AssertionError("expired runtime input must not construct a KIS client")

    module = __import__(
        "thericher_v2.execution.kis_paper_prospective_qqq_session",
        fromlist=["placeholder"],
    )
    monkeypatch.setattr(module, "KisPaperCanaryClient", fail_client_construction)

    outcome = run_kis_paper_prospective_qqq_session(
        environment={},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        clock=clock,
    )

    assert outcome.status == "no_intent"
    assert outcome.reason_code == "runtime_window_expired_before_account"
    assert outcome.pre_account_freshness is not None
    assert outcome.pre_account_freshness.category == "over_budget"
    assert outcome.pre_submit_freshness is None
    payload = json.loads(outcome.evidence_path.read_text(encoding="ascii"))
    assert payload["pre_account_freshness"]["lag_category"] == "over_budget"
    assert payload["prepared"] is None
    assert payload["canary"] is None


def test_only_a_docker_model_artifacts_mount_may_be_nested_under_the_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(45)
    _install_catalog(monkeypatch, catalog)
    repository = tmp_path / "repo"
    artifacts = repository / "model_artifacts"
    original_is_mount = Path.is_mount

    def is_mount(path: Path) -> bool:
        return path.resolve() == artifacts.resolve() or original_is_mount(path)

    monkeypatch.setattr(Path, "is_mount", is_mount)
    outcome = run_kis_paper_prospective_qqq_session(
        environment={},
        cache_root=tmp_path / "cache",
        local_paper_state_root=tmp_path / "runtime",
        artifact_root=artifacts,
        repository_root=repository,
        execute=False,
        cancel_after_submit=True,
        now=catalog.bars[-1].end_ts,
    )

    assert outcome.status == "preview"
    assert outcome.evidence_path.is_relative_to(artifacts)


def test_session_evidence_refuses_a_conflicting_repeat_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = _catalog(45)
    _install_catalog(monkeypatch, catalog)
    kwargs = {
        "environment": {},
        "cache_root": tmp_path / "cache",
        "local_paper_state_root": tmp_path / "runtime",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
        "cancel_after_submit": True,
        "session_id": "fixed-session",
        "now": catalog.bars[-1].end_ts,
    }

    first = run_kis_paper_prospective_qqq_session(execute=False, **kwargs)
    assert first.status == "preview"
    with pytest.raises(ValueError, match="evidence identity conflicts"):
        run_kis_paper_prospective_qqq_session(execute=True, **kwargs)


def _install_catalog(monkeypatch: pytest.MonkeyPatch, catalog: CatalogedBars) -> None:
    module = __import__(
        "thericher_v2.execution.kis_paper_prospective_qqq_session",
        fromlist=["placeholder"],
    )
    monkeypatch.setattr(
        module,
        "load_verified_kis_paper_private_intraday_catalog",
        lambda **_kwargs: catalog,
    )
    monkeypatch.setattr(
        module,
        "attest_kis_paper_intraday_runtime_window_local_availability",
        lambda *_args, runtime_window, decided_at, **_kwargs: _local_input_availability(
            runtime_window=runtime_window,
            decided_at=decided_at,
        ),
    )


def _local_input_availability(
    *,
    runtime_window: KisPaperIntradayRuntimeWindow,
    decided_at: datetime,
    latest_local_retained_at: datetime | None = None,
) -> KisPaperIntradayRuntimeWindowLocalAvailability:
    retained_at = decided_at if latest_local_retained_at is None else latest_local_retained_at
    return KisPaperIntradayRuntimeWindowLocalAvailability(
        input_manifest_ref=runtime_window.input_manifest_ref,
        source_catalog_hash=runtime_window.source_catalog_hash,
        index_metadata_sha256="sha256:" + "b" * 64,
        selected_bar_count=len(runtime_window.decision_bars),
        latest_local_retained_at=retained_at,
        decided_at=decided_at,
        local_input_available_by_decision=retained_at <= decided_at,
    )


class _FailClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def snapshot(self):
        self.calls.append("snapshot")
        raise AssertionError("KIS client must not be reached")

    def fetch_qqq_limit_input(self, **_kwargs):
        self.calls.append("limit_input")
        raise AssertionError("KIS quote must not be reached")


class _FlatQqqClient:
    def __init__(self, *, captured_at: datetime) -> None:
        self.calls: list[str] = []
        self.limit_input = object()
        self._captured_at = captured_at

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        self.calls.append("snapshot")
        return KisPaperReadOnlySnapshot(
            identity=KisPaperAccountIdentity("****1234-**", self._captured_at),
            cash=KisPaperCashSnapshot("USD", Decimal("1000"), self._captured_at),
            orderable_funds=KisPaperOrderableFundsSnapshot(
                "USD",
                Decimal("1000"),
                "NASD",
                "QQQ",
                Decimal("1"),
                self._captured_at,
            ),
            positions=(),
            open_orders=KisPaperOpenOrdersSnapshot((), self._captured_at),
            captured_at=self._captured_at,
        )

    def fetch_qqq_limit_input(self, **_kwargs):
        self.calls.append("limit_input")
        return self.limit_input


def _catalog(count: int) -> CatalogedBars:
    session = us_equity_2026_session(_SESSION_DATE)
    assert session is not None
    bars = tuple(
        _bar(index=index, start_ts=session.window.open_ts + timedelta(minutes=index))
        for index in range(count)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("unit-index.json"),
        bars=bars,
    )


def _bar(*, index: int, start_ts: datetime) -> Bar:
    opened = Decimal("100") + Decimal(index) / Decimal("100")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("0.02"),
        low=opened - Decimal("0.01"),
        close=opened + Decimal("0.005"),
        volume=Decimal("1000"),
        complete=True,
    )
