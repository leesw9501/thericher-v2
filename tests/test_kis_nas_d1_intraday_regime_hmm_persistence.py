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
from thericher_v2.research import kis_nas_d1_intraday_regime_hmm_persistence as subject


def test_input_exposes_only_fit_and_later_tail_not_original_screen() -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        _development_phase(guard_original_screen=True),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )

    assert prepared.status == "ready"
    assert prepared.fit_target_free_slot_count == 6 * 599
    assert prepared.persistence_target_free_slot_count == 6 * 489
    assert {symbol: len(bars) for symbol, bars in prepared._fit_bars_by_symbol.items()} == {
        symbol: 600 for symbol in subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
    }
    assert {symbol: len(bars) for symbol, bars in prepared._tail_bars_by_symbol.items()} == {
        symbol: 510 for symbol in subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
    }
    payload = prepared.safe_payload()
    assert payload["source"]["omitted_original_screen_indices"] == [600, 999]
    assert payload["raw_market_data_written"] is False
    assert payload["target_values_persisted"] is False


def test_tail_labels_use_only_next_session_and_fitted_mapping_ignores_tail() -> None:
    baseline = subject.build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    changed = subject.build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        _development_phase(tail_mutation_index=1100),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    assert baseline.status == "ready"
    assert changed.status == "ready"

    baseline_models = subject._fit_model_set(baseline)
    changed_models = subject._fit_model_set(changed)
    bars = baseline._tail_bars_by_symbol["AAPL"]
    labels = subject._tail_labels(
        bars,
        cost_bps=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS,
    )
    expected = numpy.asarray(
        [
            subject.preflight._target_label_after_cost(
                bars[index + 1],
                cost_bps=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS,
            )
            for index in range(20, 509)
        ],
        dtype=numpy.int8,
    )

    assert baseline_models.model_set_sha256 == changed_models.model_set_sha256
    assert numpy.array_equal(labels, expected)


def test_tail_prefix_and_positive_ohlc_multiplier_are_invariant() -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    assert prepared.status == "ready"
    model = subject._fit_model_set(prepared).symbols["AAPL"].normal_model
    bars = prepared._tail_bars_by_symbol["AAPL"]
    features = subject._feature_matrix(bars)
    multiplier = Decimal("19")
    scaled_bars = list(bars)
    scaled_bars[300] = replace(
        scaled_bars[300],
        open=scaled_bars[300].open * multiplier,
        high=scaled_bars[300].high * multiplier,
        low=scaled_bars[300].low * multiplier,
        close=scaled_bars[300].close * multiplier,
    )
    scaled_features = subject._feature_matrix(tuple(scaled_bars))
    states, prefix_ok = subject._tail_states_with_prefix_proof(
        model,
        features,
        valid_features=numpy.ones(len(features), dtype=bool),
    )
    scaled_states, scaled_prefix_ok = subject._tail_states_with_prefix_proof(
        model,
        scaled_features,
        valid_features=numpy.ones(len(scaled_features), dtype=bool),
    )

    assert numpy.array_equal(features, scaled_features)
    assert numpy.array_equal(states, scaled_states)
    assert prefix_ok is True
    assert scaled_prefix_ok is True


def test_extreme_control_excludes_later_feature_and_target_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        _development_phase(extreme_index=1200),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    assert prepared.status == "ready"

    def fixed_states(*_args: object, **_kwargs: object) -> tuple[numpy.ndarray, bool]:
        return numpy.zeros(489, dtype=numpy.int8), True

    monkeypatch.setattr(subject, "_tail_states_with_prefix_proof", fixed_states)
    models = SimpleNamespace(
        symbols={
            symbol: SimpleNamespace(
                normal_model=object(),
                normal_long_state=0,
                extreme_control_model=object(),
                extreme_control_long_state=0,
            )
            for symbol in subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
        }
    )
    normal = subject._evaluate_variant(prepared, models, extreme_exclusion=False)
    controlled = subject._evaluate_variant(prepared, models, extreme_exclusion=True)

    assert controlled.extreme_exclusion is True
    assert all(
        controlled_count < normal_count
        for controlled_count, normal_count in zip(
            controlled.eligible_count_by_symbol,
            normal.eligible_count_by_symbol,
            strict=True,
        )
    )


def test_precommit_is_external_redacted_and_runs_before_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    precommit = subject.precommit_kis_nas_d1_intraday_regime_hmm_persistence(
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    payload = subject.preflight._read_json_object(precommit.precommit_path)

    assert precommit.precommit_path.is_relative_to(artifact_root)
    assert payload["geometry"]["original_screen_input_exposed"] is False
    serialized = precommit.precommit_path.read_text(encoding="utf-8")
    assert "2020-" not in serialized
    assert "100.0" not in serialized
    assert '"raw_rows_persisted":false' in serialized

    runner_path = (
        Path(__file__).parents[1] / "scripts" / "run_kis_nas_d1_intraday_regime_hmm_persistence.py"
    )
    spec = importlib.util.spec_from_file_location("run_hmm_persistence_test", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    events: list[str] = []
    prepared = SimpleNamespace()
    contract = SimpleNamespace(contract_sha256="sha256:" + "a" * 64)
    result = SimpleNamespace(
        status="persistence_falsified",
        reason="frozen_persistence_kill_test_failed",
        summary_sha256="sha256:" + "b" * 64,
        registry_outcome=SimpleNamespace(record_sha256="sha256:" + "c" * 64),
    )

    def precommit_stub(**kwargs: object) -> SimpleNamespace:
        events.append("precommit")
        assert kwargs["artifact_root"] == artifact_root
        return SimpleNamespace(precommit_sha256="sha256:" + "d" * 64)

    def load_stub(**kwargs: object) -> SimpleNamespace:
        events.append("load")
        assert kwargs["parent_contract_path"].name == "campaign-contract.json"
        return prepared

    def freeze_stub(value: object, **kwargs: object) -> SimpleNamespace:
        events.append("freeze")
        assert value is prepared
        return contract

    def run_stub(value: object) -> SimpleNamespace:
        events.append("run")
        assert value is contract
        return result

    monkeypatch.setattr(
        runner, "precommit_kis_nas_d1_intraday_regime_hmm_persistence", precommit_stub
    )
    monkeypatch.setattr(runner, "load_kis_nas_d1_intraday_regime_hmm_persistence_input", load_stub)
    monkeypatch.setattr(
        runner, "freeze_kis_nas_d1_intraday_regime_hmm_persistence_campaign", freeze_stub
    )
    monkeypatch.setattr(runner, "run_kis_nas_d1_intraday_regime_hmm_persistence", run_stub)
    runner.main(
        [
            "--market-data-root",
            str(tmp_path / "market-data"),
            "--artifact-root",
            str(artifact_root),
            "--repo-root",
            str(repo_root),
            "--attempt-id",
            "unit-r1",
        ]
    )

    assert events == ["precommit", "load", "freeze", "run"]
    assert runner._default_roots(system="Windows") == (
        Path(r"D:\market_data"),
        Path(r"D:\thericher-v2\model-artifacts"),
    )


def test_frozen_run_is_redacted_external_and_non_promoting(tmp_path: Path) -> None:
    prepared = subject.build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    precommit = subject.precommit_kis_nas_d1_intraday_regime_hmm_persistence(
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    contract = subject.freeze_kis_nas_d1_intraday_regime_hmm_persistence_campaign(
        prepared,
        precommit=precommit,
    )
    result = subject.run_kis_nas_d1_intraday_regime_hmm_persistence(contract)
    repeated = subject.run_kis_nas_d1_intraday_regime_hmm_persistence(contract)
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (precommit.precommit_path, contract.contract_path, result.summary_path)
    )

    assert contract.model_set is not None
    assert result.status in {"persistence_falsified", "source_local_non_promoting"}
    assert repeated.summary_sha256 == result.summary_sha256
    assert result.registry_outcome.record_sha256 == repeated.registry_outcome.record_sha256
    assert "2020-" not in serialized
    assert "100.0" not in serialized
    assert '"fitted_parameters_persisted":false' in serialized
    assert '"checkpoint_written":false' in serialized

    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.precommit_kis_nas_d1_intraday_regime_hmm_persistence(
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )


def test_leaf_and_runner_have_no_network_credential_broker_or_gpu_surface() -> None:
    source = Path(subject.__file__).read_text(encoding="utf-8")
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

    runner_source = (
        Path(__file__).parents[1] / "scripts" / "run_kis_nas_d1_intraday_regime_hmm_persistence.py"
    ).read_text(encoding="utf-8")
    for forbidden in (".env", "os.environ", "requests", "socket", "urllib", "torch"):
        assert forbidden not in runner_source


class _GuardedBars:
    def __init__(self, values: tuple[Bar, ...]) -> None:
        self._values = values

    def __getitem__(self, key: object) -> object:
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self._values))
            if step != 1 or not (stop <= 600 or start >= 1000):
                raise AssertionError("original screen bars must not be read")
            return self._values[key]
        index = int(key)
        if 600 <= index < 1000:
            raise AssertionError("original screen bars must not be read")
        return self._values[index]


def _development_phase(
    *,
    guard_original_screen: bool = False,
    extreme_index: int | None = None,
    tail_mutation_index: int | None = None,
) -> SimpleNamespace:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(1510))
    bars_by_symbol: OrderedDict[str, SimpleNamespace] = OrderedDict()
    for symbol_index, symbol in enumerate(
        subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
    ):
        bars = tuple(
            _bar(
                symbol=symbol,
                symbol_index=symbol_index,
                index=index,
                close_multiplier=(
                    Decimal("1.20")
                    if index == extreme_index
                    else Decimal("1.04")
                    if index == tail_mutation_index
                    else None
                ),
            )
            for index in range(1510)
        )
        bars_by_symbol[symbol] = SimpleNamespace(
            bars=_GuardedBars(bars) if guard_original_screen else bars
        )
    return SimpleNamespace(
        phase="development",
        parent_dataset_id=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID,
        parent_dataset_hash=subject.KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH,
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
