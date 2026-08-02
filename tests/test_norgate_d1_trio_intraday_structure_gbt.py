from __future__ import annotations

import ast
import inspect
import socket
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import norgate_d1_trio_intraday_structure_gbt as gbt


def test_contract_is_fixed_and_core_has_no_external_surface() -> None:
    contract = gbt.frozen_norgate_d1_trio_intraday_structure_gbt_contract()
    assert contract["features"] == {
        "same_session_ratio_features": ["body", "range", "close_location"],
        "windows": [1, 5, 10, 20],
        "cross_session_price_ratios_allowed": False,
        "price_levels_allowed": False,
        "calendar_features_allowed": False,
        "volume_allowed": False,
    }
    assert contract["split"] == {
        "development_decision_indices": [20, 348],
        "purge_session_indices": [350, 370],
        "validation_decision_indices": [371, 509],
        "development_date_groups": 329,
        "purge_session_count": 21,
        "validation_date_groups": 139,
        "development_validation_feature_overlap": False,
        "development_validation_target_overlap": False,
    }
    assert contract["evaluation"]["date_block_null"]["shifts"] == list(range(1, 65))
    assert contract["scope"]["gpu_eligible"] is False
    assert contract["scope"]["paper_input_allowed"] is False

    source = inspect.getsource(gbt)
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert not imported_roots.intersection({"os", "pathlib", "socket", "subprocess", "requests"})
    assert "KIS_" not in source
    assert ".env" not in source
    assert "OrderIntent" not in source


def test_multiplier_invariance_holds_for_features_labels_and_result() -> None:
    original = _panel()
    scaled = _scale_session(original, symbol="QQQ", index=400, multiplier=Decimal("7.25"))
    original_features, original_labels = gbt._sample_matrix(original, range(371, 510))
    scaled_features, scaled_labels = gbt._sample_matrix(scaled, range(371, 510))

    numpy.testing.assert_allclose(original_features, scaled_features, rtol=0.0, atol=1e-15)
    numpy.testing.assert_array_equal(original_labels, scaled_labels)
    assert gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(
        original
    ) == gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(scaled)


def test_future_validation_target_does_not_change_features_or_development_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _panel()
    changed = _replace_target_body(original, symbol="SPY", index=510)
    original_development = gbt._sample_matrix(original, range(20, 349))
    changed_development = gbt._sample_matrix(changed, range(20, 349))
    original_validation = gbt._sample_matrix(original, range(371, 510))
    changed_validation = gbt._sample_matrix(changed, range(371, 510))
    numpy.testing.assert_array_equal(original_development[0], changed_development[0])
    numpy.testing.assert_array_equal(original_development[1], changed_development[1])
    numpy.testing.assert_array_equal(original_validation[0], changed_validation[0])

    fitted: list[tuple[numpy.ndarray, numpy.ndarray]] = []

    class RecordingModel:
        def fit(self, features: numpy.ndarray, labels: numpy.ndarray) -> RecordingModel:
            fitted.append((features.copy(), labels.copy()))
            return self

        def predict(self, features: numpy.ndarray) -> numpy.ndarray:
            return numpy.ones(features.shape[0], dtype=numpy.int8)

    monkeypatch.setattr(gbt, "_new_model", RecordingModel)
    gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(original)
    gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(changed)
    assert len(fitted) == 2
    numpy.testing.assert_array_equal(fitted[0][0], fitted[1][0])
    numpy.testing.assert_array_equal(fitted[0][1], fitted[1][1])


def test_noise_outcome_and_date_block_null_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AlwaysLongModel:
        def fit(self, features: numpy.ndarray, labels: numpy.ndarray) -> AlwaysLongModel:
            return self

        def predict(self, features: numpy.ndarray) -> numpy.ndarray:
            return numpy.ones(features.shape[0], dtype=numpy.int8)

    monkeypatch.setattr(gbt, "_new_model", AlwaysLongModel)
    first = gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(_panel())
    second = gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(_panel())
    assert first == second
    assert first.status == "noise_not_separable"
    assert first.effect_floor_met is False
    assert first.safe_payload()["metrics"]["actual_balanced_accuracy"] in {
        "at_or_above_chance_below_effect_floor",
        "below_chance",
    }
    assert first.safe_payload()["pnl_evaluated"] is False


def test_single_class_development_target_is_input_unavailable() -> None:
    result = gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(_panel(all_positive=True))
    assert result.status == "input_unavailable"
    assert result.reason == "development_target_single_class"
    assert result.actual_balanced_accuracy is None
    assert result.safe_payload()["metrics"]["actual_balanced_accuracy"] == "not_evaluated"


@pytest.mark.parametrize("kind", ["missing", "misaligned", "future", "incomplete"])
def test_invalid_panel_contracts_are_rejected(kind: str) -> None:
    panel = _panel()
    invalid = dict(panel)
    if kind == "missing":
        del invalid["IWM"]
    elif kind == "misaligned":
        invalid["IWM"] = (
            *invalid["IWM"][:-1],
            replace(invalid["IWM"][-1], start_ts=datetime(2031, 1, 1, tzinfo=UTC)),
        )
    elif kind == "future":
        invalid["SPY"] = (
            *invalid["SPY"][:-1],
            replace(invalid["SPY"][-1], complete=False),
        )
    else:
        invalid["SPY"] = (replace(invalid["SPY"][0], complete=False), *invalid["SPY"][1:])

    with pytest.raises((TypeError, ValueError)):
        gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(invalid)


def test_core_does_not_use_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("core preflight must not use the network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("core preflight must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    result = gbt.run_norgate_d1_trio_intraday_structure_gbt_preflight(_panel())
    assert result.validation_row_count == 417
    assert result.validation_date_group_count == 139
    assert not (tmp_path / ".env").exists()


def _panel(*, all_positive: bool = False) -> dict[str, tuple[Bar, ...]]:
    return {
        symbol: tuple(_bar(symbol, index, all_positive=all_positive) for index in range(511))
        for symbol in gbt.NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_SYMBOLS
    }


def _bar(symbol: str, index: int, *, all_positive: bool) -> Bar:
    symbol_offset = {"SPY": 0, "QQQ": 3, "IWM": 7}[symbol]
    open_price = Decimal("100") + Decimal(index) / Decimal("10") + Decimal(symbol_offset)
    positive = all_positive or ((index * 7 + symbol_offset * 3) % 11) < 5
    body = Decimal("0.018") if positive else Decimal("-0.017")
    close = open_price * (Decimal("1") + body)
    high = max(open_price, close) * Decimal("1.012")
    low = min(open_price, close) * Decimal("0.988")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _scale_session(
    panel: dict[str, tuple[Bar, ...]],
    *,
    symbol: str,
    index: int,
    multiplier: Decimal,
) -> dict[str, tuple[Bar, ...]]:
    result = dict(panel)
    bars = list(result[symbol])
    bar = bars[index]
    bars[index] = replace(
        bar,
        open=bar.open * multiplier,
        high=bar.high * multiplier,
        low=bar.low * multiplier,
        close=bar.close * multiplier,
    )
    result[symbol] = tuple(bars)
    return result


def _replace_target_body(
    panel: dict[str, tuple[Bar, ...]],
    *,
    symbol: str,
    index: int,
) -> dict[str, tuple[Bar, ...]]:
    result = dict(panel)
    bars = list(result[symbol])
    bar = bars[index]
    close = bar.open * Decimal("0.97")
    bars[index] = replace(
        bar,
        high=max(bar.open, close) * Decimal("1.01"),
        low=min(bar.open, close) * Decimal("0.99"),
        close=close,
    )
    result[symbol] = tuple(bars)
    return result
