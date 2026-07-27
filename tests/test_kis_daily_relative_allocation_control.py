from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_daily_relative_allocation_control as allocation
from thericher_v2.research import kis_daily_relative_regime_control as regime


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> KisPaperPrivateDailyCatalog:
    return _catalog(tmp_path_factory.mktemp("relative-allocation-source"))


def test_selection_is_phase_local_strict_and_ties_select_spy() -> None:
    sessions = tuple(
        (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=index)).date()
        for index in range(regime.KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS + 1)
    )
    qqq_bars = tuple(
        _bar(symbol="QQQ", session=session, close=Decimal("100") + Decimal(index))
        for index, session in enumerate(sessions)
    )
    spy_tie_bars = tuple(
        _bar(symbol="SPY", session=session, close=Decimal("100") + Decimal(index))
        for index, session in enumerate(sessions)
    )
    spy_loser_bars = tuple(
        _bar(symbol="SPY", session=session, close=Decimal("100")) for session in sessions
    )

    assert (
        allocation.qqq_spy_relative_allocation_symbol(
            qqq_completed_bars=qqq_bars,
            spy_completed_bars=spy_tie_bars,
        )
        == "SPY"
    )
    assert (
        allocation.qqq_spy_relative_allocation_symbol(
            qqq_completed_bars=qqq_bars,
            spy_completed_bars=spy_loser_bars,
        )
        == "QQQ"
    )
    with pytest.raises(ValueError, match="exactly 64"):
        allocation.qqq_spy_relative_allocation_symbol(
            qqq_completed_bars=qqq_bars[1:],
            spy_completed_bars=spy_tie_bars[1:],
        )


def test_cpu_controls_are_offline_replayable_single_account_and_aggregate_safe(
    catalog: KisPaperPrivateDailyCatalog,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepared = regime.build_kis_daily_relative_regime_input(catalog)
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    _deny_external_access(monkeypatch)

    smoke = allocation.run_kis_daily_relative_allocation_control(
        prepared,
        mode="cpu-smoke",
        artifact_root=artifact_root,
        run_label="smoke-a",
        repository_root=repository_root,
    )
    full = allocation.run_kis_daily_relative_allocation_control(
        prepared,
        mode="cpu-full",
        artifact_root=artifact_root,
        run_label="full-a",
        repository_root=repository_root,
    )

    assert smoke.outcome == "operational_smoke"
    assert smoke.candidate.decision_slot_count == 2
    assert full.outcome == "falsified"
    assert full.candidate.after_cost_pnl == full.always_qqq.after_cost_pnl
    assert full.candidate.decision_slot_count == full.always_spy.decision_slot_count
    assert full.candidate.qqq_selection_count + full.candidate.spy_selection_count == (
        full.candidate.decision_slot_count
    )
    assert full.always_qqq.qqq_selection_count == full.always_qqq.decision_slot_count
    assert full.always_spy.spy_selection_count == full.always_spy.decision_slot_count
    assert full.flat.trade_count == 0
    for metrics in (full.candidate, full.always_qqq, full.always_spy, full.flat):
        assert metrics.fill_source == "local_paper"
        assert metrics.all_fills_local_paper is True
        assert metrics.replayable is True
        assert metrics.flat_between_slots is True
        assert metrics.final_position_count == 0
        assert metrics.local_paper_fill_count == metrics.trade_count * 2
    assert full.precommit_path.is_relative_to(artifact_root)
    assert full.summary_path.is_relative_to(artifact_root)
    assert not full.summary_path.is_relative_to(repository_root)
    assert len(full.precommit_path.parents[1].name) == 20

    summary = json.loads(full.summary_path.read_text(encoding="utf-8"))
    assert summary["outcome"] == "falsified"
    assert summary["validation"]["candidate"]["flat_between_slots"] is True
    assert summary["artifact_policy"]["event_logs_persisted"] is False
    assert summary["artifact_policy"]["local_paper_only"] is True
    for document in artifact_root.rglob("*.json"):
        _assert_no_raw_fields(json.loads(document.read_text(encoding="utf-8")))
    assert not list(artifact_root.rglob("*.jsonl"))
    assert not list(artifact_root.rglob("*.sqlite"))
    assert not list(artifact_root.rglob("*.pt"))
    assert not list(artifact_root.rglob("*.pkl"))
    assert not list(artifact_root.rglob("*.joblib"))

    with pytest.raises(FileExistsError, match="run label"):
        allocation.run_kis_daily_relative_allocation_control(
            prepared,
            mode="cpu-full",
            artifact_root=artifact_root,
            run_label="full-a",
            repository_root=repository_root,
        )


def test_three_comparator_kill_rule_is_strict() -> None:
    always_qqq = _metrics(role="always_qqq", slots=3, pnl=Decimal("3"))
    always_spy = _metrics(role="always_spy", slots=3, pnl=Decimal("2"))
    flat = _metrics(role="flat", slots=3, pnl=Decimal("0"))

    assert (
        allocation.classify_kis_daily_relative_allocation_outcome(
            mode="cpu-full",
            candidate=_metrics(role="candidate", slots=3, pnl=Decimal("3")),
            always_qqq=always_qqq,
            always_spy=always_spy,
            flat=flat,
        )
        == "falsified"
    )
    assert (
        allocation.classify_kis_daily_relative_allocation_outcome(
            mode="cpu-full",
            candidate=_metrics(role="candidate", slots=3, pnl=Decimal("4")),
            always_qqq=always_qqq,
            always_spy=always_spy,
            flat=flat,
        )
        == "candidate_only"
    )
    assert (
        allocation.classify_kis_daily_relative_allocation_outcome(
            mode="cpu-smoke",
            candidate=_metrics(role="candidate", slots=3, pnl=Decimal("-9")),
            always_qqq=always_qqq,
            always_spy=always_spy,
            flat=flat,
        )
        == "operational_smoke"
    )


def test_rejects_artifacts_inside_git(
    catalog: KisPaperPrivateDailyCatalog,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        allocation.run_kis_daily_relative_allocation_control(
            regime.build_kis_daily_relative_regime_input(catalog),
            mode="cpu-smoke",
            artifact_root=repository_root / "artifacts",
            run_label="inside-git",
            repository_root=repository_root,
        )


def _metrics(
    *,
    role: str,
    slots: int,
    pnl: Decimal,
) -> allocation.KisDailyRelativeAllocationReplayMetrics:
    qqq_selection_count = slots if role in {"candidate", "always_qqq"} else 0
    spy_selection_count = slots if role == "always_spy" else 0
    trade_count = qqq_selection_count + spy_selection_count
    return allocation.KisDailyRelativeAllocationReplayMetrics(
        role=role,  # type: ignore[arg-type]
        decision_slot_count=slots,
        qqq_selection_count=qqq_selection_count,
        spy_selection_count=spy_selection_count,
        trade_count=trade_count,
        local_paper_fill_count=trade_count * 2,
        after_cost_pnl=pnl,
        gross_pnl=pnl,
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        fill_source="local_paper",
        all_fills_local_paper=True,
        replayable=True,
        flat_between_slots=True,
        final_position_count=0,
        replay_identity_hash=_sha256(f"{role}:{slots}:{pnl}"),
    )


def _catalog(root: Path) -> KisPaperPrivateDailyCatalog:
    sessions = tuple(
        (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=index)).date()
        for index in range(regime.KIS_DAILY_RELATIVE_REGIME_TOTAL_SESSIONS)
    )
    index_path = root / "private-source-path-index.json"
    streams = {}
    for symbol, base in (("QQQ", Decimal("100")), ("SPY", Decimal("200"))):
        bars = tuple(
            _bar(symbol=symbol, session=session, close=base + Decimal(index))
            for index, session in enumerate(sessions)
        )
        streams[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
            dataset_hash=_sha256("fixture-dataset"),
            source_path=index_path,
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
        dataset_hash=_sha256("fixture-dataset"),
        index_hash=_sha256("fixture-index"),
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(streams),
        common_sessions=sessions,
        raw_price_limitations=(
            "MODP=0_unadjusted",
            "corporate_action_semantics_not_qualified",
        ),
    )


def _bar(*, symbol: str, session: object, close: Decimal) -> Bar:
    if not hasattr(session, "year"):
        raise AssertionError("session fixture is invalid")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=close - Decimal("0.01"),
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("relative-allocation control must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_raw_fields(value: object) -> None:
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
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_fields(nested)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()
