from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import replace
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
from thericher_v2.research import kis_daily_relative_regime_control as control


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> KisPaperPrivateDailyCatalog:
    return _catalog(tmp_path_factory.mktemp("relative-regime-source"))


def test_input_keeps_frozen_counts_and_phase_local_63_session_windows(
    catalog: KisPaperPrivateDailyCatalog,
) -> None:
    prepared = control.build_kis_daily_relative_regime_input(catalog)

    assert prepared.split.development_session_count == 3783
    assert prepared.split.purge_session_count == 22
    assert prepared.split.validation_session_count == 951
    assert len(prepared.development_catalog.common_sessions) == 3783
    assert len(prepared.validation_catalog.common_sessions) == 951
    assert prepared.validation_decision_indices[0] == 63
    assert prepared.validation_decision_indices[-1] + 2 < 951
    assert all(
        index - control.KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS >= 0
        and index + 2 < len(prepared.validation_catalog.common_sessions)
        for index in prepared.validation_decision_indices
    )
    assert all(
        later - earlier == control.KIS_DAILY_RELATIVE_REGIME_DECISION_STRIDE_SESSIONS
        for earlier, later in zip(
            prepared.validation_decision_indices,
            prepared.validation_decision_indices[1:],
            strict=False,
        )
    )


def test_rule_is_causal_and_requires_exactly_64_aligned_completed_bars(
    catalog: KisPaperPrivateDailyCatalog,
) -> None:
    prepared = control.build_kis_daily_relative_regime_input(catalog)
    qqq_bars = prepared.validation_catalog.bars_by_symbol["QQQ"].bars
    spy_bars = prepared.validation_catalog.bars_by_symbol["SPY"].bars
    index = prepared.validation_decision_indices[0]

    baseline = control.qqq_spy_relative_regime_should_enter(
        qqq_completed_bars=qqq_bars[index - 63 : index + 1],
        spy_completed_bars=spy_bars[index - 63 : index + 1],
    )
    changed_future = _catalog(
        Path("C:/unit-source"),
        qqq_close_overrides={
            prepared.split.validation_start_index + index + 1: Decimal("100000")
        },
    )
    changed = control.build_kis_daily_relative_regime_input(changed_future)
    changed_qqq = changed.validation_catalog.bars_by_symbol["QQQ"].bars
    changed_spy = changed.validation_catalog.bars_by_symbol["SPY"].bars

    assert (
        control.qqq_spy_relative_regime_should_enter(
            qqq_completed_bars=changed_qqq[index - 63 : index + 1],
            spy_completed_bars=changed_spy[index - 63 : index + 1],
        )
        is baseline
    )
    with pytest.raises(ValueError, match="exactly 64"):
        control.qqq_spy_relative_regime_should_enter(
            qqq_completed_bars=qqq_bars[index - 62 : index + 1],
            spy_completed_bars=spy_bars[index - 62 : index + 1],
        )


def test_full_and_smoke_controls_are_offline_local_paper_only_and_aggregate_safe(
    catalog: KisPaperPrivateDailyCatalog,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepared = control.build_kis_daily_relative_regime_input(catalog)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    _deny_external_access(monkeypatch)

    smoke = control.run_kis_daily_relative_regime_control(
        prepared,
        mode="cpu-smoke",
        artifact_root=artifact_root,
        run_label="smoke-a",
        repository_root=repo_root,
    )
    full = control.run_kis_daily_relative_regime_control(
        prepared,
        mode="cpu-full",
        artifact_root=artifact_root,
        run_label="full-a",
        repository_root=repo_root,
    )

    assert smoke.outcome == "operational_smoke"
    assert smoke.candidate.decision_slot_count == 2
    assert full.outcome == "falsified"
    assert full.candidate.local_paper_fill_count == full.candidate.trade_count * 2
    assert full.always_long.entry_signal_count == full.always_long.decision_slot_count
    assert full.flat.entry_signal_count == 0
    for metrics in (full.candidate, full.always_long, full.flat):
        assert metrics.fill_source == "local_paper"
        assert metrics.all_fills_local_paper is True
        assert metrics.replayable is True
        assert metrics.final_position == Decimal("0")
    assert full.precommit_path.is_relative_to(artifact_root)
    assert full.summary_path.is_relative_to(artifact_root)
    assert not full.summary_path.is_relative_to(repo_root)
    assert len(full.precommit_path.parents[1].name) == 20

    summary = json.loads(full.summary_path.read_text(encoding="utf-8"))
    assert summary["outcome"] == "falsified"
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
        control.run_kis_daily_relative_regime_control(
            prepared,
            mode="cpu-full",
            artifact_root=artifact_root,
            run_label="full-a",
            repository_root=repo_root,
        )


def test_strict_kill_rule_requires_a_trade_and_strict_after_cost_wins() -> None:
    always_long = _metrics(role="always_long", slots=3, entries=3, pnl=Decimal("1"))
    flat = _metrics(role="flat", slots=3, entries=0, pnl=Decimal("0"))

    assert (
        control.classify_kis_daily_relative_regime_outcome(
            mode="cpu-full",
            candidate=_metrics(role="candidate", slots=3, entries=0, pnl=Decimal("2")),
            always_long=always_long,
            flat=flat,
        )
        == "falsified"
    )
    assert (
        control.classify_kis_daily_relative_regime_outcome(
            mode="cpu-full",
            candidate=_metrics(role="candidate", slots=3, entries=1, pnl=Decimal("1")),
            always_long=always_long,
            flat=flat,
        )
        == "falsified"
    )
    assert (
        control.classify_kis_daily_relative_regime_outcome(
            mode="cpu-full",
            candidate=_metrics(role="candidate", slots=3, entries=1, pnl=Decimal("2")),
            always_long=always_long,
            flat=flat,
        )
        == "candidate_only"
    )


def test_current_loader_pins_qqq_spy_catalog_identity_before_building_input(
    catalog: KisPaperPrivateDailyCatalog,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_loader(*_args: object, **kwargs: object) -> KisPaperPrivateDailyCatalog:
        calls.append(dict(kwargs))
        return catalog

    monkeypatch.setattr(control, "load_kis_paper_private_daily_catalog", fake_loader)
    prepared = control.load_current_kis_daily_relative_regime_input(
        cache_root=tmp_path / "cache",
        repository_root=tmp_path,
    )

    assert prepared.catalog is catalog
    assert len(calls) == 1
    assert calls[0]["target_keys"] == ("QQQ/NAS/MODP=0", "SPY/AMS/MODP=0")
    assert calls[0]["expected_index_hash"] == control._EXPECTED_CATALOG_INDEX_HASH  # noqa: SLF001
    assert calls[0]["expected_full_dataset_hash"] == control._EXPECTED_CATALOG_DATASET_HASH  # noqa: SLF001


def test_rejects_source_mismatch_and_artifacts_inside_git(
    catalog: KisPaperPrivateDailyCatalog,
    tmp_path: Path,
) -> None:
    shifted_spy = tuple(
        replace(bar, start_ts=bar.start_ts + timedelta(days=1))
        for bar in catalog.bars_by_symbol["SPY"].bars
    )
    bad_catalog = replace(
        catalog,
        bars_by_symbol=MappingProxyType(
            {
                "QQQ": catalog.bars_by_symbol["QQQ"],
                "SPY": _cataloged_bars_from_verified_loader(
                    dataset_id=catalog.dataset_id,
                    dataset_hash=catalog.dataset_hash,
                    source_path=catalog.index_path,
                    bars=shifted_spy,
                ),
            }
        ),
    )
    with pytest.raises(ValueError, match="source streams"):
        control.build_kis_daily_relative_regime_input(bad_catalog)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        control.run_kis_daily_relative_regime_control(
            control.build_kis_daily_relative_regime_input(catalog),
            mode="cpu-smoke",
            artifact_root=repo_root / "artifacts",
            run_label="inside-git",
            repository_root=repo_root,
        )


def _metrics(
    *,
    role: str,
    slots: int,
    entries: int,
    pnl: Decimal,
) -> control.KisDailyRelativeRegimeReplayMetrics:
    return control.KisDailyRelativeRegimeReplayMetrics(
        role=role,  # type: ignore[arg-type]
        decision_slot_count=slots,
        entry_signal_count=entries,
        trade_count=entries,
        local_paper_fill_count=entries * 2,
        after_cost_pnl=pnl,
        gross_pnl=pnl,
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        fill_source="local_paper",
        all_fills_local_paper=True,
        replayable=True,
        final_position=Decimal("0"),
        replay_identity_hash=_sha256(f"{role}:{slots}:{entries}:{pnl}"),
    )


def _catalog(
    root: Path,
    *,
    qqq_close_overrides: dict[int, Decimal] | None = None,
) -> KisPaperPrivateDailyCatalog:
    qqq_close_overrides = qqq_close_overrides or {}
    sessions = tuple(
        (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=index)).date()
        for index in range(control.KIS_DAILY_RELATIVE_REGIME_TOTAL_SESSIONS)
    )
    index_path = root / "private-source-path-index.json"
    streams = {}
    for symbol, base in (("QQQ", Decimal("100")), ("SPY", Decimal("200"))):
        bars = tuple(
            _bar(
                symbol=symbol,
                session=session,
                close=(
                    qqq_close_overrides.get(index, base + Decimal(index))
                    if symbol == "QQQ"
                    else base + Decimal(index)
                ),
            )
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
        raise AssertionError("relative-regime control must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(control, "load_kis_paper_private_daily_catalog", forbidden)


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
