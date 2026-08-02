from __future__ import annotations

import ast
import importlib.util
from collections import OrderedDict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_nas_d1_intraday_regime_hmm as subject


def test_builds_fixed_development_prefix_and_ratio_invariant_features() -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )

    assert prepared.status == "ready"
    assert prepared.fit_target_free_slot_count == 6 * 599
    assert prepared.screen_target_free_slot_count == 6 * 377
    assert {symbol: len(bars) for symbol, bars in prepared._bars_by_symbol.items()} == {
        symbol: 1000 for symbol in subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
    }
    payload = prepared.safe_payload()
    assert payload["raw_market_data_written"] is False
    assert payload["feature_values_persisted"] is False
    assert payload["target_values_persisted"] is False

    bar = prepared._bars_by_symbol["AAPL"][25]
    multiplier = Decimal("17")
    scaled = replace(
        bar,
        open=bar.open * multiplier,
        high=bar.high * multiplier,
        low=bar.low * multiplier,
        close=bar.close * multiplier,
    )
    assert subject._feature_row(scaled) == subject._feature_row(bar)
    assert subject._target_label_after_cost(
        scaled,
        cost_bps=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS,
    ) == subject._target_label_after_cost(
        bar,
        cost_bps=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS,
    )

    bars = list(prepared._bars_by_symbol["AAPL"])
    bars[700] = replace(
        bars[700],
        open=bars[700].open * multiplier,
        high=bars[700].high * multiplier,
        low=bars[700].low * multiplier,
        close=bars[700].close * multiplier,
    )
    original_features = subject._feature_matrix(prepared._bars_by_symbol["AAPL"])
    scaled_features = subject._feature_matrix(tuple(bars))
    model = subject._fit_two_state_hmm(
        original_features[: subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP],
        deadline=subject.time.perf_counter() + 10.0,
    )
    original_states, _ = subject._screen_states_with_prefix_proof(
        model,
        original_features,
        valid_features=numpy.ones(len(original_features), dtype=bool),
    )
    scaled_states, _ = subject._screen_states_with_prefix_proof(
        model,
        scaled_features,
        valid_features=numpy.ones(len(scaled_features), dtype=bool),
    )
    assert numpy.array_equal(original_features, scaled_features)
    assert numpy.array_equal(original_states, scaled_states)


def test_invalid_or_malformed_source_closes_only_this_input() -> None:
    phase = _development_phase()
    invalid = phase.bars_by_symbol["AAPL"].bars[0]
    object.__setattr__(invalid, "open", Decimal("0"))

    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        phase,
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    malformed = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        SimpleNamespace(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )

    assert prepared.status == "input_unavailable"
    assert prepared.reason == "invalid_candle_ratio"
    assert prepared._bars_by_symbol == {}
    assert malformed.status == "input_unavailable"
    assert malformed.reason == "source_stream_mismatch"


def test_joint_null_reorders_all_symbols_by_the_same_date_blocks() -> None:
    labels = numpy.asarray([*([0] * 10), *([1] * 10), 0, 1, 0], dtype=numpy.int8)
    labels_by_symbol = {
        symbol: labels if index % 2 == 0 else 1 - labels
        for index, symbol in enumerate(subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS)
    }

    permuted = subject._joint_block_permute_labels(labels_by_symbol, seed=1234)

    assert numpy.array_equal(permuted["AAPL"], 1 - permuted["AMZN"])
    assert numpy.array_equal(permuted["GOOGL"], 1 - permuted["META"])
    for symbol, values in labels_by_symbol.items():
        assert numpy.array_equal(numpy.sort(permuted[symbol]), numpy.sort(values))
        assert numpy.array_equal(permuted[symbol][-3:], values[-3:])


def test_forward_filter_is_prefix_deterministic_and_ignores_future_mutation() -> None:
    bars = _development_phase().bars_by_symbol["AAPL"].bars[:1000]
    features = subject._feature_matrix(bars)
    model = subject._fit_two_state_hmm(
        features[: subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP],
        deadline=subject.time.perf_counter() + 10.0,
    )
    valid = numpy.ones(len(features), dtype=bool)
    states, prefix_deterministic = subject._screen_states_with_prefix_proof(
        model,
        features,
        valid_features=valid,
    )
    changed = features.copy()
    changed[900] = changed[900] * numpy.asarray((1.001, 1.002, 0.997, 1.0))
    changed_states, changed_prefix_deterministic = subject._screen_states_with_prefix_proof(
        model,
        changed,
        valid_features=valid,
    )
    index_before_future_change = 700 - subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START

    assert prefix_deterministic is True
    assert changed_prefix_deterministic is True
    assert states[index_before_future_change] == changed_states[index_before_future_change]


def test_fit_mapping_and_labels_are_closed_before_screen_targets() -> None:
    baseline = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    changed = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        _development_phase(screen_mutation_index=700),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    assert baseline.status == "ready"
    assert changed.status == "ready"

    baseline_models = subject._fit_model_set(baseline)
    changed_models = subject._fit_model_set(changed)
    labels = subject._labels_for_screen(
        baseline._bars_by_symbol["AAPL"],
        cost_bps=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS,
    )
    expected = numpy.asarray(
        [
            subject._target_label_after_cost(
                baseline._bars_by_symbol["AAPL"][index + 1],
                cost_bps=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS,
            )
            for index in range(622, 999)
        ],
        dtype=numpy.int8,
    )

    assert baseline_models.model_set_sha256 == changed_models.model_set_sha256
    assert numpy.array_equal(labels, expected)


def test_extreme_control_excludes_feature_and_target_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        _development_phase(extreme_index=700),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    assert prepared.status == "ready"

    def fixed_states(*_args: object, **_kwargs: object) -> tuple[numpy.ndarray, bool]:
        return numpy.zeros(377, dtype=numpy.int8), True

    monkeypatch.setattr(subject, "_screen_states_with_prefix_proof", fixed_states)
    models = SimpleNamespace(
        symbols={
            symbol: SimpleNamespace(
                normal_model=object(),
                normal_long_state=0,
                extreme_control_model=object(),
                extreme_control_long_state=0,
            )
            for symbol in subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
        }
    )
    normal = subject._evaluate_variant(prepared, models, extreme_exclusion=False)
    controlled = subject._evaluate_variant(prepared, models, extreme_exclusion=True)

    assert controlled.extreme_exclusion is True
    assert all(
        control_count < normal_count
        for control_count, normal_count in zip(
            controlled.eligible_count_by_symbol,
            normal.eligible_count_by_symbol,
            strict=True,
        )
    )


def test_frozen_cpu_run_is_external_redacted_and_non_promoting(
    tmp_path: Path,
) -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    contract = subject.freeze_kis_nas_d1_intraday_regime_hmm_campaign(
        prepared,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    same_contract = subject.freeze_kis_nas_d1_intraday_regime_hmm_campaign(
        prepared,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    result = subject.run_kis_nas_d1_intraday_regime_hmm(contract)
    repeated = subject.run_kis_nas_d1_intraday_regime_hmm(contract)
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in (contract.contract_path, result.summary_path)
    )

    assert contract.model_set is not None
    assert same_contract.contract_sha256 == contract.contract_sha256
    assert result.status in {"noise_not_separable", "source_local_non_promoting"}
    assert repeated.summary_sha256 == result.summary_sha256
    assert result.registry_outcome.record_sha256 == repeated.registry_outcome.record_sha256
    assert contract.run_directory.is_relative_to(artifact_root)
    assert "2020-" not in serialized
    assert "100.0" not in serialized
    assert '"raw_rows_persisted":false' in serialized
    assert '"fitted_parameters_persisted":false' in serialized
    assert not list(contract.run_directory.glob("*.npz"))

    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.freeze_kis_nas_d1_intraday_regime_hmm_campaign(
            prepared,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )


def test_leaf_and_runner_stay_offline_without_execution_or_gpu_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_path = Path(subject.__file__)
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)
    top_level_imports = {
        alias.name for node in module.body if isinstance(node, ast.Import) for alias in node.names
    }

    assert "from thericher_v2.execution" not in source
    assert "torch" not in source
    assert "os.environ" not in source
    assert "requests" not in source
    assert "socket" not in source
    assert "sklearn" not in top_level_imports

    runner_path = Path(__file__).parents[1] / "scripts" / "run_kis_nas_d1_intraday_regime_hmm.py"
    spec = importlib.util.spec_from_file_location(
        "run_kis_nas_d1_intraday_regime_hmm_test", runner_path
    )
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner._default_roots(system="Windows") == (
        Path(r"D:\market_data"),
        Path(r"D:\thericher-v2\model-artifacts"),
    )
    assert runner._default_roots(system="Linux") == (
        Path("/app/market_data"),
        Path("/app/model_artifacts"),
    )
    captured: dict[str, object] = {}
    prepared = SimpleNamespace()
    contract = SimpleNamespace(contract_sha256="sha256:" + "a" * 64)
    result = SimpleNamespace(
        status="noise_not_separable",
        reason="frozen_primary_kill_test_failed",
        summary_sha256="sha256:" + "b" * 64,
        registry_outcome=SimpleNamespace(record_sha256="sha256:" + "c" * 64),
    )

    def load(**kwargs: object) -> SimpleNamespace:
        captured["load"] = kwargs
        return prepared

    def freeze(value: object, **kwargs: object) -> SimpleNamespace:
        captured["freeze"] = {"value": value, **kwargs}
        return contract

    def run(value: object) -> SimpleNamespace:
        captured["run"] = value
        return result

    monkeypatch.setattr(runner, "load_kis_nas_d1_intraday_regime_hmm_input", load)
    monkeypatch.setattr(runner, "freeze_kis_nas_d1_intraday_regime_hmm_campaign", freeze)
    monkeypatch.setattr(runner, "run_kis_nas_d1_intraday_regime_hmm", run)
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "model-artifacts"
    runner.main(
        [
            "--market-data-root",
            str(market_data_root),
            "--artifact-root",
            str(artifact_root),
            "--repo-root",
            str(tmp_path),
            "--attempt-id",
            "unit-r1",
        ]
    )

    frozen = captured["freeze"]
    assert isinstance(frozen, dict)
    assert frozen["value"] is prepared
    assert frozen["artifact_root"] == artifact_root
    assert frozen["repo_root"] == tmp_path
    assert str(frozen["code_revision"]).startswith("sha256:")
    assert frozen["attempt_id"] == "unit-r1"
    assert captured["run"] is contract
    runner_source = runner_path.read_text(encoding="utf-8")
    for forbidden in (".env", "os.environ", "requests", "socket", "urllib", "torch"):
        assert forbidden not in runner_source


def _development_phase(
    *,
    extreme_index: int | None = None,
    screen_mutation_index: int | None = None,
) -> SimpleNamespace:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(1510))
    bars_by_symbol: OrderedDict[str, SimpleNamespace] = OrderedDict()
    for symbol_index, symbol in enumerate(subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS):
        bars_by_symbol[symbol] = SimpleNamespace(
            bars=tuple(
                _bar(
                    symbol=symbol,
                    symbol_index=symbol_index,
                    index=index,
                    close_multiplier=(
                        Decimal("1.20")
                        if index == extreme_index
                        else Decimal("1.04")
                        if index == screen_mutation_index
                        else None
                    ),
                )
                for index in range(1510)
            )
        )
    return SimpleNamespace(
        phase="development",
        parent_dataset_id=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID,
        parent_dataset_hash=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH,
        index_hash="sha256:" + "a" * 64,
        bars_by_symbol=bars_by_symbol,
        common_sessions=sessions,
    )


def _bar(
    *,
    symbol: str,
    symbol_index: int,
    index: int,
    close_multiplier: Decimal | None,
) -> Bar:
    opening = Decimal("100") + Decimal(symbol_index * 7) + Decimal(index % 23) / Decimal("10")
    regime = (index // 17 + symbol_index) % 2
    movement = Decimal("0.024") if regime else Decimal("-0.016")
    movement += Decimal((index % 5) - 2) / Decimal("10000")
    multiplier = close_multiplier or (Decimal("1") + movement)
    closing = opening * multiplier
    upper_wick = Decimal("0.35") + Decimal((index + symbol_index) % 4) / Decimal("100")
    lower_wick = Decimal("0.25") + Decimal((index + 2 * symbol_index) % 3) / Decimal("100")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open=opening,
        high=max(opening, closing) + upper_wick,
        low=min(opening, closing) - lower_wick,
        close=closing,
        volume=Decimal("1000") + Decimal(index),
        complete=True,
    )
