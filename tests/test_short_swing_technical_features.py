import builtins
import math
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.research.short_swing_technical_features import (
    FEATURE_NAMES,
    WINDOW,
    short_swing_technical_features,
    short_swing_technical_features_at,
)


def bars(close, *, body=0.5, spread=1):
    close = np.asarray(close, dtype=np.float64)
    return np.column_stack((close - body, close + spread, close - spread, close))


def test_linear_rise_matches_independent_closed_form():
    values = bars(np.arange(10, 70))
    result = short_swing_technical_features(values[None])[0]
    expected = (
        4 * math.sqrt((20**2 - 1) / 12) / 59.5,
        7 / 69,
        7 / 69,
        0,
        1,
        0.5,
        0,
        14 / 15,
        14 / 15,
        1,
        0.25,
    )
    np.testing.assert_allclose(result, expected, rtol=1e-12, atol=1e-14)
    assert len(FEATURE_NAMES) == 11
    assert WINDOW == 60


def test_linear_fall_preserves_directional_signs():
    values = bars(np.arange(100, 40, -1), body=-0.5)
    result = short_swing_technical_features(values[None])[0]
    assert result[1] == pytest.approx(-7 / 41)
    assert result[2] == pytest.approx(-7 / 41)
    assert result[3] == pytest.approx(0, abs=1e-14)
    np.testing.assert_allclose(result[4:7], (1, 0, 0.5))
    np.testing.assert_allclose(result[7:], (1 / 15, 1 / 15, 1, -0.25))


def test_batch_scale_invariance_and_no_mutation():
    window = bars(100 + np.sin(np.arange(60) / 4) + np.arange(60) / 10)
    before = window.copy()
    batch = short_swing_technical_features(np.stack((window, window * 100)))
    np.testing.assert_allclose(batch[0], batch[1], rtol=1e-11, atol=1e-12)
    np.testing.assert_array_equal(before, window)
    np.testing.assert_allclose(batch[0], short_swing_technical_features(window[None])[0])


def test_flat_close_with_real_range_has_defined_features():
    result = short_swing_technical_features(bars(np.full(60, 100), body=0)[None])[0]
    np.testing.assert_allclose(result, (0, 0, 0, 0, 0, 0, 0, 0.5, 0.5, 1, 0))


def test_degenerate_prices_preserve_unknown_ratios():
    result = short_swing_technical_features(np.full((1, 60, 4), 100.0))[0]
    np.testing.assert_array_equal(result[:7], np.zeros(7))
    assert np.isnan(result[7:]).all()


@pytest.mark.parametrize("shape", [(60, 4), (1, 59, 4), (1, 61, 4), (1, 60, 5)])
def test_rejects_wrong_window_shape(shape):
    with pytest.raises(ValueError, match="requires_60_ohlc"):
        short_swing_technical_features(np.ones(shape))


@pytest.mark.parametrize("bad", [0, -1, np.nan, np.inf, -np.inf])
def test_unknown_or_nonpositive_price_is_not_imputed(bad):
    values = bars(np.arange(10, 70))[None]
    values[0, 5, 0] = bad
    with pytest.raises(ValueError, match="known_positive"):
        short_swing_technical_features(values)


@pytest.mark.parametrize("column,value", [(1, 1), (2, 200), (0, 300)])
def test_rejects_inconsistent_ohlc(column, value):
    values = bars(np.arange(10, 70))[None]
    values[0, 20, column] = value
    with pytest.raises(ValueError, match="inconsistent_ohlc"):
        short_swing_technical_features(values)


@pytest.mark.parametrize("entry", [True, 59, 61, 60.0, "60", None])
def test_rejects_invalid_entry_index(entry):
    with pytest.raises(ValueError, match="invalid_entry_index"):
        short_swing_technical_features_at(bars(np.arange(10, 70)), entry)


def test_entry_is_exclusive_and_future_values_cannot_change_features():
    values = bars(np.arange(10, 110))
    expected = short_swing_technical_features_at(values, 60)
    values[60:] = np.nan
    np.testing.assert_allclose(short_swing_technical_features_at(values, 60), expected)

    class PriorOnly:
        def __len__(self):
            return 100

        def __getitem__(self, key):
            assert isinstance(key, slice) and key.start == 0 and key.stop == 60
            return values[key]

    np.testing.assert_allclose(short_swing_technical_features_at(PriorOnly(), 60), expected)


def test_no_filesystem_or_runtime_code_dependency(monkeypatch):
    values = bars(np.arange(10, 70))[None]

    def deny(*_args, **_kwargs):
        raise AssertionError("feature kernel must not load artifact code or files")

    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(Path, "read_bytes", deny)
    monkeypatch.setattr(builtins, "exec", deny)
    result = short_swing_technical_features(values)
    assert result.shape == (1, 11)
    assert np.isfinite(result).all()
