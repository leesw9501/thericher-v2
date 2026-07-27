from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_history_sequence_input as data_input
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_nas_d1_sequence_campaign as campaign
from thericher_v2.research.campaign import CampaignCosts


def test_phase_adapter_freezes_exact_geometry_and_rejects_source_drift(tmp_path: Path) -> None:
    panel = _panel(tmp_path / "good")

    prepared = data_input._prepare_kis_paper_daily_history_sequence_input(panel)  # noqa: SLF001

    assert [
        len(prepared.development.common_sessions),
        len(prepared.purge.common_sessions),
        len(prepared.validation.common_sessions),
    ] == [1510, 22, 647]
    assert prepared.development.common_sessions[-1] < prepared.purge.common_sessions[0]
    assert prepared.purge.common_sessions[-1] < prepared.validation.common_sessions[0]
    assert prepared.development.safe_payload()["source_local_only"] is True

    source_drift = _panel(tmp_path / "source-drift")
    changed_path = source_drift.source_root / "other-index.json"
    changed_path.write_text("{}\n", encoding="utf-8")
    object.__setattr__(source_drift, "index_path", changed_path)
    with pytest.raises(ValueError, match="panel"):
        data_input._prepare_kis_paper_daily_history_sequence_input(source_drift)  # noqa: SLF001

    incomplete = _panel(tmp_path / "incomplete")
    stream = incomplete.bars_by_symbol["AAPL"]
    object.__setattr__(
        stream,
        "bars",
        (replace(stream.bars[0], complete=False), *stream.bars[1:]),
    )
    with pytest.raises(ValueError, match="stream"):
        data_input._prepare_kis_paper_daily_history_sequence_input(incomplete)  # noqa: SLF001

    misaligned = _panel(tmp_path / "misaligned")
    shifted = misaligned.bars_by_symbol["AMZN"]
    object.__setattr__(
        shifted,
        "bars",
        (
            replace(shifted.bars[0], start_ts=shifted.bars[0].start_ts + timedelta(days=1)),
            *shifted.bars[1:],
        ),
    )
    with pytest.raises(ValueError, match="stream"):
        data_input._prepare_kis_paper_daily_history_sequence_input(misaligned)  # noqa: SLF001


def test_loader_reattaches_through_the_panel_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    panel = _panel(tmp_path / "source")
    seen: dict[str, object] = {}

    def fake_loader(
        manifest_path: Path | str,
        *,
        cache_root: Path | str,
        panel_root: Path | str,
        repo_root: Path | str | None,
    ) -> KisPaperDailyHistoryPanel:
        seen.update(
            {
                "manifest_path": manifest_path,
                "cache_root": cache_root,
                "panel_root": panel_root,
                "repo_root": repo_root,
            }
        )
        return panel

    monkeypatch.setattr(data_input, "load_materialized_kis_paper_daily_history_panel", fake_loader)

    loaded = data_input.load_kis_paper_daily_history_sequence_input(
        tmp_path / "panel-manifest.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        repo_root=tmp_path / "repo",
    )

    assert (
        loaded.panel_dataset_hash
        == data_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
    )
    assert seen["manifest_path"] == tmp_path / "panel-manifest.json"
    assert seen["cache_root"] == tmp_path / "cache"
    assert seen["panel_root"] == tmp_path / "panel"
    assert not hasattr(data_input, "prepare_kis_paper_daily_history_sequence_input")


def test_campaign_is_per_symbol_phase_local_and_hides_validation_labels(tmp_path: Path) -> None:
    campaign_input = _campaign_input(tmp_path / "source")

    assert campaign_input.contract.split.development_session_count == 1510
    assert campaign_input.contract.split.purge_session_count == 22
    assert campaign_input.contract.split.validation_session_count == 647
    assert campaign_input.contract.costs.fee_bps == Decimal("1")
    assert campaign_input.contract.costs.slippage_bps == Decimal("2")
    assert campaign_input.contract.comparators == (
        "flat",
        "always_long",
        "previous_bar_direction",
    )
    assert campaign_input.contract.development_decision_stride == 1
    assert campaign_input.contract.evaluation_decision_stride == 2
    assert (
        campaign_input.contract.previous_bar_direction_tie_rule
        == "strict_positive_long_else_flat"
    )
    split_payload = campaign_input.contract.safe_payload()["split"]
    assert split_payload["phase_boundaries"] == {
        "development": {
            "start": campaign_input.development_sessions[0].isoformat(),
            "end": campaign_input.development_sessions[-1].isoformat(),
        },
        "purge": {
            "start": campaign_input.contract.split.purge_start.isoformat(),
            "end": campaign_input.contract.split.purge_end.isoformat(),
        },
        "validation": {
            "start": campaign_input.validation_sessions[0].isoformat(),
            "end": campaign_input.validation_sessions[-1].isoformat(),
        },
    }
    shifted_contract = replace(
        campaign_input.contract,
        split=replace(
            campaign_input.contract.split,
            development_start=campaign_input.contract.split.development_start
            + timedelta(days=1),
        ),
    )
    assert shifted_contract.contract_hash != campaign_input.contract.contract_hash

    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        development = campaign_input.development_samples(symbol)
        validation = campaign_input.validation_samples(symbol)
        assert len(development) == 1488
        assert len(validation) == 313
        assert all(sample.label in {0, 1} for sample in development)
        assert not hasattr(validation[0], "label")
        assert not hasattr(campaign_input, "source_input")
        _assert_samples_inside_dates(
            development,
            set(campaign_input.development_sessions),
        )
        _assert_samples_inside_dates(
            validation,
            set(campaign_input.validation_sessions),
        )


def test_other_symbol_changes_cannot_change_a_symbol_sequence(tmp_path: Path) -> None:
    baseline = _campaign_input(tmp_path / "baseline")
    changed = _campaign_input(
        tmp_path / "changed",
        altered_symbol="AMZN",
        altered_from_index=300,
        alteration=Decimal("30"),
    )

    assert baseline.development_samples("AAPL") == changed.development_samples("AAPL")
    assert baseline.validation_samples("AAPL") == changed.validation_samples("AAPL")
    assert baseline.development_samples("AMZN") != changed.development_samples("AMZN")


def test_cost_label_is_strict_and_uses_the_frozen_fill_terms() -> None:
    costs = CampaignCosts(
        fee_bps=Decimal("1"),
        slippage_bps=Decimal("2"),
        slippage_source_id="unit-costs",
    )
    entry = _bar(symbol="AAPL", start_ts=datetime(2024, 1, 2, tzinfo=UTC), value=Decimal("100"))
    tied_exit = _bar(
        symbol="AAPL",
        start_ts=datetime(2024, 1, 3, tzinfo=UTC),
        value=Decimal("100"),
    )
    winning_exit = _bar(
        symbol="AAPL",
        start_ts=datetime(2024, 1, 3, tzinfo=UTC),
        value=Decimal("101"),
    )

    assert campaign._after_cost_label(entry_bar=entry, exit_bar=tied_exit, costs=costs) == 0  # noqa: SLF001
    expected = campaign._after_cost_label(  # noqa: SLF001
        entry_bar=entry,
        exit_bar=winning_exit,
        costs=costs,
    )
    with localcontext() as hostile_context:
        hostile_context.prec = 6
        hostile_context.rounding = ROUND_DOWN
        assert campaign._after_cost_label(  # noqa: SLF001
            entry_bar=entry,
            exit_bar=winning_exit,
            costs=costs,
        ) == expected
    assert expected == 1


def test_precommit_is_offline_immutable_and_contains_no_value_level_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    campaign_input = _campaign_input(tmp_path / "source")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    first = campaign.write_kis_nas_d1_sequence_campaign_precommit(
        campaign_input,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    second = campaign.write_kis_nas_d1_sequence_campaign_precommit(
        campaign_input,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    payload = json.loads(first.precommit_path.read_text(encoding="utf-8"))

    assert first.precommit_hash == second.precommit_hash
    assert first.precommit_path.is_relative_to(artifact_root)
    assert payload["source"]["target_states"][4]["state"] == "source_limited"
    assert payload["inputs"]["validation"]["labels_exposed"] is False
    assert payload["next_eligible_packages"]["cpu_smoke"]["package_id"] == (
        "nas-d1-per-symbol-l2-logistic-smoke-v1"
    )
    assert payload["next_eligible_packages"]["gpu_breadth"]["architectures"] == [
        "lstm",
        "causal_tcn",
        "compact_attention",
    ]
    _assert_no_value_level_fields(payload)

    first.precommit_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable"):
        campaign.write_kis_nas_d1_sequence_campaign_precommit(
            campaign_input,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        campaign.write_kis_nas_d1_sequence_campaign_precommit(
            campaign_input,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
        )


def _campaign_input(
    root: Path,
    *,
    altered_symbol: str | None = None,
    altered_from_index: int = 0,
    alteration: Decimal = Decimal("0"),
) -> campaign.KisNasD1SequenceCampaignInput:
    source = data_input._prepare_kis_paper_daily_history_sequence_input(  # noqa: SLF001
        _panel(
            root,
            altered_symbol=altered_symbol,
            altered_from_index=altered_from_index,
            alteration=alteration,
        )
    )
    return campaign.build_kis_nas_d1_sequence_campaign(source)


def _panel(
    root: Path,
    *,
    altered_symbol: str | None = None,
    altered_from_index: int = 0,
    alteration: Decimal = Decimal("0"),
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    start = datetime(2017, 1, 3, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(2179))
    dataset_hash = data_input.KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        bars = tuple(
            _bar(
                symbol=symbol,
                start_ts=start + timedelta(days=index),
                value=(
                    Decimal("100")
                    + Decimal(offset * 10)
                    + Decimal(index) / Decimal("10")
                    + (
                        alteration
                        if symbol == altered_symbol and index >= altered_from_index
                        else Decimal("0")
                    )
                ),
            )
            for index in range(2179)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        state = "source_limited" if symbol == "MSFT" else "complete"
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state=state,
            last_reason="daily_response_invalid" if state == "source_limited" else None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket=_quarter(sessions[0]),
            coverage_end_bucket=_quarter(sessions[-1]),
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "a" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(*, symbol: str, start_ts: datetime, value: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("1000"),
        complete=True,
    )


def _quarter(value: date) -> str:
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _assert_samples_inside_dates(samples: object, phase_dates: set[date]) -> None:
    for sample in samples:  # type: ignore[union-attr]
        assert sample.return_anchor_start.date() in phase_dates
        assert sample.feature_start.date() in phase_dates
        assert sample.decision_start.date() in phase_dates
        assert sample.entry_start.date() in phase_dates
        assert sample.exit_start.date() in phase_dates


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("NAS D1 campaign must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_value_level_fields(value: object) -> None:
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
        "label",
        "labels",
        "featurevalues",
        "targetvalues",
        "perdecision",
        "sourcepath",
        "workdir",
        "eventjsonl",
        "eventlog",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_value_level_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_value_level_fields(nested)
