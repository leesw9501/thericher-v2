from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    kis_paper_daily_history_volatility_trend_prospective_input as prospective_input,
)
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KisPaperDailyNasHistoricalForwardProjection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE
from thericher_v2.research import (
    kis_nas_d1_volatility_trend_prospective_observation as prospective,
)


def test_local_paper_replay_is_offline_and_marks_intratrade_drawdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    slot = _unit_slot()
    campaign_input = SimpleNamespace(
        contract=SimpleNamespace(
            costs=SimpleNamespace(fee_bps=Decimal("1"), slippage_bps=Decimal("0"))
        )
    )

    result = prospective._evaluate_actions(  # noqa: SLF001
        result_id="unit-candidate:AAPL",
        model_family="unit",
        symbol="AAPL",
        lineage_hash="sha256:" + "1" * 64,
        actions=(True,),
        slots=(slot,),
        campaign_input=campaign_input,
    )

    assert result.fill_source == LOCAL_PAPER_SOURCE
    assert result.all_fills_local_paper is True
    assert result.replay_reconstructed is True
    assert result.terminal_position_zero is True
    assert result.fill_count == 2
    assert result.maximum_drawdown == Decimal("50.01")
    payload = result.safe_payload()
    assert payload["event_rows_retained"] is False
    prospective._assert_source_safe(payload)  # noqa: SLF001


def test_slots_use_causal_context_and_only_open_after_the_boundary(tmp_path: Path) -> None:
    sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(36))
    boundary = sessions[30]
    baseline = _panel(tmp_path / "baseline", sessions=sessions)
    future_changed = _panel(
        tmp_path / "future-changed",
        sessions=sessions,
        altered_symbol="AAPL",
        altered_index=32,
        alteration=Decimal("9"),
    )

    baseline_slots = prospective._prospective_slots(  # noqa: SLF001
        SimpleNamespace(prospective_panel=baseline, frozen_boundary=boundary)
    )
    changed_slots = prospective._prospective_slots(  # noqa: SLF001
        SimpleNamespace(prospective_panel=future_changed, frozen_boundary=boundary)
    )

    assert {len(slots) for slots in baseline_slots.values()} == {1}
    slot = baseline_slots["AAPL"][0]
    assert slot.signal_bar.start_ts.date() > boundary
    assert slot.entry_bar.start_ts.date() > boundary
    assert slot.exit_bar.start_ts.date() > boundary
    assert slot.feature_sequence == changed_slots["AAPL"][0].feature_sequence
    assert slot.entry_bar.start_ts == slot.signal_bar.start_ts + timedelta(days=1)
    assert slot.exit_bar.start_ts == slot.signal_bar.start_ts + timedelta(days=2)


def test_slots_resolve_entry_and_exit_on_all_symbol_common_dates(tmp_path: Path) -> None:
    sessions = tuple(date(2026, 1, 1) + timedelta(days=index * 2) for index in range(36))
    boundary = sessions[30]
    extra_session = sessions[31] + timedelta(days=1)
    panel = _panel(
        tmp_path,
        sessions=sessions,
        extra_symbol="AAPL",
        extra_session=extra_session,
    )

    slots = prospective._prospective_slots(  # noqa: SLF001
        SimpleNamespace(prospective_panel=panel, frozen_boundary=boundary)
    )

    expected_dates = (sessions[31], sessions[32], sessions[33])
    assert {
        tuple(
            (
                slot.signal_bar.start_ts.date(),
                slot.entry_bar.start_ts.date(),
                slot.exit_bar.start_ts.date(),
            )
            for slot in symbol_slots
        )
        for symbol_slots in slots.values()
    } == {(expected_dates,)}
    assert all(
        slot.entry_bar.start_ts.date() != extra_session for slot in slots["AAPL"]
    )


def test_forward_projection_slots_use_only_exact_common_future_sessions(
    tmp_path: Path,
) -> None:
    frozen_sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(29))
    frozen_boundary = frozen_sessions[-1]
    panel = _panel(tmp_path / "frozen", sessions=frozen_sessions)
    index_before = panel.index_path.read_bytes()
    common_sessions = tuple(frozen_boundary + timedelta(days=index) for index in range(1, 4))
    projection = _forward_projection(
        panel,
        frozen_boundary=frozen_boundary,
        sessions_by_symbol={
            symbol: (
                *common_sessions,
                *((frozen_boundary + timedelta(days=4),) if symbol == "AAPL" else ()),
            )
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
    )
    forward_input = (
        prospective_input.build_kis_paper_daily_history_volatility_trend_prospective_input(
            panel,
            frozen_boundary=frozen_boundary,
            historical_forward_projection=projection,
            forward_cache_root=tmp_path / "forward-cache",
        )
    )

    slots = prospective._prospective_slots(  # noqa: SLF001
        SimpleNamespace(
            prospective_panel=panel,
            prospective_input=forward_input,
            forward_projection=projection,
            frozen_boundary=frozen_boundary,
        )
    )

    assert {len(symbol_slots) for symbol_slots in slots.values()} == {1}
    assert {
        tuple(
            (
                slot.signal_bar.start_ts.date(),
                slot.entry_bar.start_ts.date(),
                slot.exit_bar.start_ts.date(),
            )
            for slot in symbol_slots
        )
        for symbol_slots in slots.values()
    } == {(common_sessions,)}
    assert panel.index_path.read_bytes() == index_before


def test_partial_forward_projection_does_not_open_a_target_slot(tmp_path: Path) -> None:
    frozen_sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(29))
    frozen_boundary = frozen_sessions[-1]
    panel = _panel(tmp_path / "frozen", sessions=frozen_sessions)
    first_two = tuple(frozen_boundary + timedelta(days=index) for index in range(1, 3))
    projection = _forward_projection(
        panel,
        frozen_boundary=frozen_boundary,
        sessions_by_symbol={
            symbol: (
                *first_two,
                *((frozen_boundary + timedelta(days=3),) if symbol == "AAPL" else ()),
            )
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
    )
    forward_input = (
        prospective_input.build_kis_paper_daily_history_volatility_trend_prospective_input(
            panel,
            frozen_boundary=frozen_boundary,
            historical_forward_projection=projection,
            forward_cache_root=tmp_path / "forward-cache",
        )
    )

    slots = prospective._prospective_slots(  # noqa: SLF001
        SimpleNamespace(
            prospective_panel=panel,
            prospective_input=forward_input,
            forward_projection=projection,
            frozen_boundary=frozen_boundary,
        )
    )

    assert forward_input.status == "input_unavailable"
    assert slots == {symbol: () for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS}


def test_unavailable_forward_input_skips_slots_models_and_external_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "external-model-artifacts"
    observation_input = _preflight_input()
    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective,
        "require_attested_kis_nas_d1_volatility_trend_prospective_observation_input",
        lambda _value: None,
    )
    monkeypatch.setattr(
        prospective,
        "_require_unchanged_prospective_input",
        lambda *_args, **_kwargs: (
            object(),
            SimpleNamespace(status="input_unavailable"),
            None,
        ),
    )
    monkeypatch.setattr(
        prospective,
        "_prospective_slots",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("slots opened")),
    )
    monkeypatch.setattr(
        prospective,
        "_validate_frozen_external_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("models opened")),
    )

    run = prospective.run_kis_nas_d1_volatility_trend_prospective_observation(
        observation_input,
        artifact_root=artifact_root,
        run_label="forward-input-unavailable",
        review_status="review_unavailable",
        repo_root=repository,
    )

    assert run.status == "input_unavailable"
    payload = json.loads(run.receipt_path.read_text(encoding="ascii"))
    assert payload["status"] == "input_unavailable"
    prospective._assert_source_safe(payload)  # noqa: SLF001


def test_forward_window_receipts_consume_only_new_three_session_windows(
    tmp_path: Path,
) -> None:
    frozen_sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(29))
    frozen_boundary = frozen_sessions[-1]
    panel = _panel(tmp_path / "frozen", sessions=frozen_sessions)
    lineage_input = SimpleNamespace(
        evidence=prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE,
        frozen_boundary=frozen_boundary,
    )
    observation_root = (
        tmp_path
        / "external-artifacts"
        / prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID
    )
    observation_root.mkdir(parents=True)

    slots_at_3 = _forward_slots(panel, frozen_boundary=frozen_boundary, common_count=3)
    selected_at_3, window_ids_at_3 = prospective._unconsumed_prospective_slots(  # noqa: SLF001
        lineage_input,
        slots_by_symbol=slots_at_3,
        completed_window_ids=frozenset(),
    )
    assert {len(slots) for slots in selected_at_3.values()} == {1}
    assert len(window_ids_at_3) == 1
    _write_completed_window_receipt(
        observation_root / "at-3",
        window_ids=window_ids_at_3,
    )
    completed = prospective._load_completed_window_ids(observation_root)  # noqa: SLF001
    assert completed == frozenset(window_ids_at_3)

    lineage_after_cache_append = SimpleNamespace(
        evidence=prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE,
        frozen_boundary=frozen_boundary,
        prospective_input=SimpleNamespace(forward_cache_hash="sha256:" + "d" * 64),
    )
    assert prospective._prospective_window_ids(  # noqa: SLF001
        lineage_after_cache_append,
        slots_by_symbol=slots_at_3,
    ) == window_ids_at_3

    for common_count in (4, 5):
        slots = _forward_slots(panel, frozen_boundary=frozen_boundary, common_count=common_count)
        selected, window_ids = prospective._unconsumed_prospective_slots(  # noqa: SLF001
            lineage_input,
            slots_by_symbol=slots,
            completed_window_ids=completed,
        )
        assert window_ids == ()
        assert selected == {symbol: () for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS}

    slots_at_6 = _forward_slots(panel, frozen_boundary=frozen_boundary, common_count=6)
    selected_at_6, window_ids_at_6 = prospective._unconsumed_prospective_slots(  # noqa: SLF001
        lineage_input,
        slots_by_symbol=slots_at_6,
        completed_window_ids=completed,
    )
    assert len(window_ids_at_6) == 1
    assert window_ids_at_6[0] != window_ids_at_3[0]
    assert {len(slots) for slots in selected_at_6.values()} == {1}
    assert {
        _slot_dates(slots[0]) for slots in selected_at_6.values()
    } == {
        tuple(
            frozen_boundary + timedelta(days=index)
            for index in range(4, 7)
        )
    }


@pytest.mark.parametrize("common_count", (4, 5))
def test_completed_window_short_circuits_before_model_or_replay_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    common_count: int,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "external-artifacts"
    observation_input = _preflight_input()
    frozen_sessions = tuple(
        date(2026, 1, 1) + timedelta(days=index) for index in range(29)
    )
    frozen_boundary = frozen_sessions[-1]
    observation_input.frozen_boundary = frozen_boundary
    panel = _panel(tmp_path / "frozen", sessions=frozen_sessions)
    slots = _forward_slots(
        panel,
        frozen_boundary=frozen_boundary,
        common_count=common_count,
    )
    completed_window_ids = prospective._prospective_window_ids(  # noqa: SLF001
        observation_input,
        slots_by_symbol=slots,
    )
    observation_root = (
        artifact_root / prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID
    )
    _write_completed_window_receipt(observation_root / "prior", window_ids=completed_window_ids)
    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective,
        "require_attested_kis_nas_d1_volatility_trend_prospective_observation_input",
        lambda _value: None,
    )
    monkeypatch.setattr(
        prospective,
        "_require_unchanged_prospective_input",
        lambda *_args, **_kwargs: (object(), SimpleNamespace(status="ready"), None),
    )
    monkeypatch.setattr(prospective, "_prospective_slots", lambda *_args, **_kwargs: slots)
    monkeypatch.setattr(
        prospective,
        "_validate_frozen_external_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("models loaded")),
    )
    monkeypatch.setattr(
        prospective,
        "_prediction_batches",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("predictions run")),
    )

    run = prospective.run_kis_nas_d1_volatility_trend_prospective_observation(
        observation_input,
        artifact_root=artifact_root,
        run_label="already-consumed",
        review_status="review_unavailable",
        repo_root=repository,
    )

    assert run.status == "input_unavailable"
    assert run.completed_window_ids == ()
    payload = json.loads(run.receipt_path.read_text(encoding="ascii"))
    assert payload["reason"] == "no_unconsumed_complete_all_symbol_post_boundary_t_plus_2_window"


def test_failed_window_evaluation_does_not_write_a_completion_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "external-artifacts"
    observation_input = _preflight_input()
    slots = _window_slots(
        frozen_boundary=observation_input.frozen_boundary,
        window_starts=(date(2026, 7, 25),),
    )
    _deny_external_access(monkeypatch)
    monkeypatch.setattr(
        prospective,
        "require_attested_kis_nas_d1_volatility_trend_prospective_observation_input",
        lambda _value: None,
    )
    monkeypatch.setattr(
        prospective,
        "_require_unchanged_prospective_input",
        lambda *_args, **_kwargs: (object(), SimpleNamespace(status="ready"), None),
    )
    monkeypatch.setattr(prospective, "_prospective_slots", lambda *_args, **_kwargs: slots)
    monkeypatch.setattr(
        prospective,
        "_validate_frozen_external_artifacts",
        lambda *_args, **_kwargs: ({}, {}),
    )
    monkeypatch.setattr(
        prospective,
        "_prediction_batches",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("evaluation failed")),
    )

    with pytest.raises(RuntimeError, match="evaluation failed"):
        prospective.run_kis_nas_d1_volatility_trend_prospective_observation(
            observation_input,
            artifact_root=artifact_root,
            run_label="failed-window",
            review_status="review_unavailable",
            repo_root=repository,
        )

    observation_root = (
        artifact_root / prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID
    )
    assert prospective._load_completed_window_ids(observation_root) == frozenset()  # noqa: SLF001


def test_cpu_predictions_require_the_frozen_r2_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature_sequence = _feature_sequence()
    slots_by_symbol = {
        symbol: (
            SimpleNamespace(feature_sequence=feature_sequence),
            SimpleNamespace(feature_sequence=feature_sequence),
        )
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    standardizers = {
        symbol: SimpleNamespace(
            standardizer_hash=f"sha256:{index + 1:064x}",
            transform=lambda values, *, sequence_length: values,
        )
        for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    }
    models = {
        symbol: SimpleNamespace(
            parameter_hash=f"sha256:{index + 11:064x}",
            weights=(0.0,) * 100,
            intercept=0.0,
        )
        for index, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    }
    campaign_input = SimpleNamespace(
        contract=SimpleNamespace(features=SimpleNamespace(sequence_length=20)),
        development_samples=lambda symbol: slots_by_symbol[symbol],
    )
    breadth_input = SimpleNamespace(
        campaign_input=campaign_input,
        standardizer=lambda symbol: standardizers[symbol],
    )
    observation_input = SimpleNamespace(
        campaign_input=campaign_input,
    )
    summary = {
        "candidates": [
            {
                "symbol": spec.symbol,
                "model_id": "l2_logistic",
                "model_parameter_hash": models[spec.symbol].parameter_hash,
                "standardizer_hash": standardizers[spec.symbol].standardizer_hash,
                "development_sample_count": len(slots_by_symbol[spec.symbol]),
                "steps": spec.steps,
                "seed": spec.seed,
            }
            for spec in prospective.KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
        ]
    }
    monkeypatch.setattr(
        prospective,
        "fit_kis_nas_d1_volatility_trend_l2_logistic_smoke",
        lambda _breadth_input, spec: models[spec.symbol],
    )

    batches = prospective._cpu_prediction_batches(  # noqa: SLF001
        observation_input,
        cpu_summary=summary,
        slots_by_symbol=slots_by_symbol,
        breadth_input=breadth_input,
    )

    assert len(batches) == len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    assert {len(batch.probabilities) for batch in batches} == {2}

    summary["candidates"][0]["model_parameter_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="CPU model lineage drifted"):
        prospective._cpu_prediction_batches(  # noqa: SLF001
            observation_input,
            cpu_summary=summary,
            slots_by_symbol=slots_by_symbol,
            breadth_input=breadth_input,
        )


def test_unavailable_receipt_is_immutable_and_source_safe(tmp_path: Path) -> None:
    observation_input = _preflight_input()
    payload = prospective._input_unavailable_payload(  # noqa: SLF001
        observation_input,
        precommit_hash="sha256:" + "2" * 64,
        review_status="review_unavailable",
    )
    receipt = tmp_path / "external" / "input_unavailable.json"
    receipt.parent.mkdir()

    receipt_hash = prospective._write_json_new(receipt, payload)  # noqa: SLF001

    assert receipt_hash.startswith("sha256:")
    assert json.loads(receipt.read_text(encoding="ascii"))["status"] == "input_unavailable"
    prospective._assert_source_safe(payload)  # noqa: SLF001
    with pytest.raises(FileExistsError, match="immutable"):
        prospective._write_json_new(receipt, payload)  # noqa: SLF001


def test_cache_mutation_after_precommit_rejects_before_target_opening(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observation_input = SimpleNamespace(
        frozen_boundary=date(2026, 7, 24),
        prospective_panel=SimpleNamespace(source_root=tmp_path / "cache"),
        prospective_input=SimpleNamespace(prospective_input_hash="sha256:" + "3" * 64),
    )
    reattested_panel = object()
    monkeypatch.setattr(
        prospective,
        "build_kis_paper_daily_history_panel",
        lambda **_kwargs: reattested_panel,
    )
    monkeypatch.setattr(
        prospective,
        "build_kis_paper_daily_history_volatility_trend_prospective_input",
        lambda *_args, **_kwargs: SimpleNamespace(prospective_input_hash="sha256:" + "4" * 64),
    )

    with pytest.raises(ValueError, match="changed after precommit"):
        prospective._require_unchanged_prospective_input(  # noqa: SLF001
            observation_input,
            repository=tmp_path / "repository",
        )


def test_cache_reattest_returns_the_verified_panel_for_target_opening(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected_hash = "sha256:" + "3" * 64
    reattested_panel = object()
    observation_input = SimpleNamespace(
        frozen_boundary=date(2026, 7, 24),
        prospective_panel=SimpleNamespace(source_root=tmp_path / "cache"),
        prospective_input=SimpleNamespace(prospective_input_hash=expected_hash),
    )
    monkeypatch.setattr(
        prospective,
        "build_kis_paper_daily_history_panel",
        lambda **_kwargs: reattested_panel,
    )
    monkeypatch.setattr(
        prospective,
        "build_kis_paper_daily_history_volatility_trend_prospective_input",
        lambda *_args, **_kwargs: SimpleNamespace(prospective_input_hash=expected_hash),
    )

    panel, reattested, projection = prospective._require_unchanged_prospective_input(  # noqa: SLF001
        observation_input,
        repository=tmp_path / "repository",
    )

    assert panel is reattested_panel
    assert reattested.prospective_input_hash == expected_hash
    assert projection is None


def test_frozen_lineage_failure_writes_external_source_safe_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifact_root = tmp_path / "external-model-artifacts"
    observation_input = _preflight_input()
    monkeypatch.setattr(
        prospective,
        "require_attested_kis_nas_d1_volatility_trend_prospective_observation_input",
        lambda _value: None,
    )

    def fail_frozen_lineage(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("frozen lineage drift")

    monkeypatch.setattr(prospective, "_validate_frozen_external_artifacts", fail_frozen_lineage)
    monkeypatch.setattr(
        prospective,
        "_require_unchanged_prospective_input",
        lambda *_args, **_kwargs: (
            object(),
            SimpleNamespace(status="ready"),
            None,
        ),
    )
    monkeypatch.setattr(
        prospective,
        "_prospective_slots",
        lambda *_args, **_kwargs: _window_slots(
            frozen_boundary=date(2026, 7, 24),
            window_starts=(date(2026, 7, 25),),
        ),
    )

    with pytest.raises(RuntimeError, match="frozen lineage drift"):
        prospective.run_kis_nas_d1_volatility_trend_prospective_observation(
            observation_input,
            artifact_root=artifact_root,
            run_label="frozen-lineage-failure",
            review_status="review_unavailable",
            repo_root=repository,
        )

    output_dir = (
        artifact_root
        / prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID
        / "frozen-lineage-failure"
    )
    failure = json.loads((output_dir / "failure.json").read_text(encoding="ascii"))
    assert failure["stage"] == "frozen_lineage"
    assert failure["precommit_hash"].startswith("sha256:")
    prospective._assert_source_safe(failure)  # noqa: SLF001


def test_output_root_and_runner_route_surface_are_restricted(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        prospective._prepare_output_dir(  # noqa: SLF001
            artifact_root=repository / "model-artifacts",
            repository=repository,
            run_label="repository-root",
        )

    source = Path("scripts/run_kis_nas_d1_volatility_trend_prospective_observation.py").read_text(
        encoding="utf-8"
    )
    assert "load_dotenv" not in source
    assert "os.environ" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert "requests" not in source
    assert "http" not in source
    assert "--forward-cache-root" in source


def _unit_slot() -> prospective.KisNasD1VolatilityTrendProspectiveSlot:
    boundary = date(2024, 1, 1)
    start = datetime(2024, 1, 2, tzinfo=UTC)
    signal_bar = _bar("AAPL", start, Decimal("99"), Decimal("98"))
    entry_bar = _bar("AAPL", start + timedelta(days=1), Decimal("100"), Decimal("50"))
    exit_bar = _bar("AAPL", start + timedelta(days=2), Decimal("100"), Decimal("99"))
    return prospective.KisNasD1VolatilityTrendProspectiveSlot(
        symbol="AAPL",
        feature_sequence=_feature_sequence(),
        signal_bar=signal_bar,
        entry_bar=entry_bar,
        exit_bar=exit_bar,
        frozen_boundary=boundary,
    )


def _panel(
    root: Path,
    *,
    sessions: tuple[date, ...],
    altered_symbol: str | None = None,
    altered_index: int = 0,
    alteration: Decimal = Decimal("0"),
    extra_symbol: str | None = None,
    extra_session: date | None = None,
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="ascii")
    dataset_hash = "sha256:" + "a" * 64
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for symbol_offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1):
        symbol_sessions = sessions
        if symbol == extra_symbol and extra_session is not None:
            symbol_sessions = tuple(sorted((*sessions, extra_session)))
        bars = tuple(
            _bar(
                symbol,
                datetime.combine(session, datetime.min.time(), tzinfo=UTC),
                Decimal("100") + Decimal(symbol_offset) + Decimal(index) / Decimal("10")
                + (
                    alteration
                    if symbol == altered_symbol and index >= altered_index
                    else Decimal("0")
                ),
                Decimal("99") + Decimal(symbol_offset) + Decimal(index) / Decimal("10"),
            )
            for index, session in enumerate(symbol_sessions)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state="complete",
            last_reason=None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket="2026-Q1",
            coverage_end_bucket="2026-Q1",
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "b" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(symbol: str, start: datetime, open_value: Decimal, low_value: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start,
        open=open_value,
        high=max(open_value, low_value) + Decimal("1"),
        low=low_value,
        close=open_value,
        volume=Decimal("1000"),
        complete=True,
    )


def _feature_sequence() -> tuple[tuple[float, ...], ...]:
    return tuple((0.0,) * 5 for _ in range(20))


def _forward_slots(
    panel: KisPaperDailyHistoryPanel,
    *,
    frozen_boundary: date,
    common_count: int,
) -> dict[str, tuple[prospective.KisNasD1VolatilityTrendProspectiveSlot, ...]]:
    sessions = tuple(
        frozen_boundary + timedelta(days=index)
        for index in range(1, common_count + 1)
    )
    projection = _forward_projection(
        panel,
        frozen_boundary=frozen_boundary,
        sessions_by_symbol={
            symbol: sessions for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        },
    )
    forward_input = (
        prospective_input.build_kis_paper_daily_history_volatility_trend_prospective_input(
            panel,
            frozen_boundary=frozen_boundary,
            historical_forward_projection=projection,
            forward_cache_root=panel.source_root.parent / "forward-cache",
        )
    )
    return prospective._prospective_slots(  # noqa: SLF001
        SimpleNamespace(
            prospective_panel=panel,
            prospective_input=forward_input,
            forward_projection=projection,
            frozen_boundary=frozen_boundary,
        )
    )


def _write_completed_window_receipt(path: Path, *, window_ids: tuple[str, ...]) -> None:
    path.mkdir(parents=True)
    prospective._write_json_new(  # noqa: SLF001
        path / "summary.json",
        {
            "kind": "kis_nas_d1_volatility_trend_prospective_observation",
            "status": "completed",
            "window_consumption": {
                "version": (
                    prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_WINDOW_CONSUMPTION_VERSION
                ),
                "completed_window_count": len(window_ids),
                "completed_window_ids": list(window_ids),
            },
        },
    )


def _slot_dates(
    slot: prospective.KisNasD1VolatilityTrendProspectiveSlot,
) -> tuple[date, date, date]:
    return (
        slot.signal_bar.start_ts.date(),
        slot.entry_bar.start_ts.date(),
        slot.exit_bar.start_ts.date(),
    )


def _window_slots(
    *,
    frozen_boundary: date,
    window_starts: tuple[date, ...],
) -> dict[str, tuple[prospective.KisNasD1VolatilityTrendProspectiveSlot, ...]]:
    return {
        symbol: tuple(
            prospective.KisNasD1VolatilityTrendProspectiveSlot(
                symbol=symbol,
                feature_sequence=_feature_sequence(),
                signal_bar=_bar(
                    symbol,
                    datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                    Decimal("100"),
                    Decimal("99"),
                ),
                entry_bar=_bar(
                    symbol,
                    datetime.combine(
                        start + timedelta(days=1),
                        datetime.min.time(),
                        tzinfo=UTC,
                    ),
                    Decimal("101"),
                    Decimal("100"),
                ),
                exit_bar=_bar(
                    symbol,
                    datetime.combine(
                        start + timedelta(days=2),
                        datetime.min.time(),
                        tzinfo=UTC,
                    ),
                    Decimal("102"),
                    Decimal("101"),
                ),
                frozen_boundary=frozen_boundary,
            )
            for start in window_starts
        )
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }


def _forward_projection(
    panel: KisPaperDailyHistoryPanel,
    *,
    frozen_boundary: date,
    sessions_by_symbol: dict[str, tuple[date, ...]],
) -> KisPaperDailyNasHistoricalForwardProjection:
    common_sessions = tuple(
        sorted(set.intersection(*(set(values) for values in sessions_by_symbol.values())))
    )
    context_by_symbol = {
        symbol: tuple(panel.bars_by_symbol[symbol].bars[-29:])
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    forward_by_symbol = {
        symbol: tuple(
            _bar(
                symbol,
                datetime.combine(session, datetime.min.time(), tzinfo=UTC),
                Decimal(200 + symbol_offset + index),
                Decimal(199 + symbol_offset + index),
            )
            for index, session in enumerate(sessions_by_symbol[symbol])
        )
        for symbol_offset, symbol in enumerate(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS, start=1)
    }
    eligible_target_slot_count = len(common_sessions) // 3
    return KisPaperDailyNasHistoricalForwardProjection(
        frozen_panel_hash=panel.dataset_hash,
        forward_cache_hash="sha256:" + "c" * 64,
        frozen_boundary=frozen_boundary,
        context_by_symbol=MappingProxyType(context_by_symbol),
        forward_by_symbol=MappingProxyType(forward_by_symbol),
        forward_common_sessions=common_sessions,
        eligible_target_slot_count=eligible_target_slot_count,
        status="ready" if eligible_target_slot_count else "input_unavailable",
    )


def _preflight_input() -> SimpleNamespace:
    return SimpleNamespace(
        evidence=prospective.KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE,
        frozen_boundary=date(2026, 7, 24),
        prospective_input=SimpleNamespace(
            safe_payload=lambda: {
                "kind": "prospective_test_input",
                "status": "input_unavailable",
                "raw_rows_persisted": False,
            }
        ),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(os, "getenv", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
