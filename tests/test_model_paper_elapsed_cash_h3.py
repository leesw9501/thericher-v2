"""Distinct full17 plus derived CASH H3 contract, invented source rows only."""

import hashlib
import json
import struct
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from test_model_paper_weights_h5 import POLICY, _metadata, _window
from thericher_v2.execution import kis_paper_current_stock_cycle as native
from thericher_v2.research import model_paper_weights as weights

D = Decimal
PROFILE = weights.MODEL_PAPER_WEIGHTS_CASH_ELAPSED_H3_PROFILE
SYMBOLS = "AAPL AMD AMZN GOOGL META MSFT NVDA TSLA JPM JNJ XOM PG KO HD V DIS UNH".split()


def stock_rows(values=None):
    values = [D(0)] * 17 if values is None else values
    return tuple(
        weights.ModelPaperWeightRow(i, symbol + ("/NAS" if i < 8 else "/NYS"), True, value)
        for i, (symbol, value) in enumerate(zip(SYMBOLS, values, strict=True))
    )


def point(rows=None, first=date(2026, 11, 2), last=date(2026, 11, 5)):
    first, last = _window(first), _window(last)
    if rows is None:
        rows = stock_rows([D(".5"), *([D(0)] * 16)])
    rows = weights.append_derived_cash_h3_row(rows)
    return weights.prepare_model_paper_weights_input(
        _metadata(first, last, rows), entry_session=first, exit_session=last, profile=PROFILE
    )


def load(payload):
    return weights.load_model_paper_weights_input(
        payload, expected_sha256=hashlib.sha256(payload).hexdigest(), expected_policy_ref=POLICY
    )


def test_full17_original_stock_bytes_and_terminal_derived_cash_roundtrip():
    values = [D(repr((i % 4) / 51)) for i in range(17)]
    rows = stock_rows(values)
    value = point(rows)
    assert value.metadata.rows[:17] == rows
    before = b"".join(struct.pack("<d", float(row.weight)) for row in rows)
    after = b"".join(struct.pack("<d", float(row.weight)) for row in value.metadata.rows[:17])
    assert before == after
    residual = 1 - sum((Fraction(row.weight) for row in rows), Fraction())
    assert value.metadata.rows[17] == weights.ModelPaperWeightRow(
        17, "CASH", True, D(repr(float(residual)))
    )
    payload = weights.serialize_model_paper_weights_input(value)
    assert load(payload) == native._unpack(native._pack(value)) == value
    assert value.execution_basis == weights.CASH_ELAPSED_H3_EXECUTION_BASIS
    assert {target.slot for target in value.targets} <= set(range(8))
    assert value.metadata.skipped_weight > 0
    assert value.metadata.cash_weight != 1 - value.metadata.eligible_weight


def test_positive_unsupported_venue_mass_is_not_cash_or_redistributed():
    rows = stock_rows([D(".25"), *([D(0)] * 7), D(".25"), *([D(0)] * 8)])
    rows = (*rows[:9], replace(rows[9], route="SPY/AMS", weight=D(".25")), *rows[10:])
    value = point(rows)
    assert value.metadata.cash_weight == Fraction(1, 4)
    assert value.metadata.skipped_weight == Fraction(1, 2)
    assert len(value.targets) == 1 and value.targets[0].research_weight == D(".25")
    assert value.targets[0].proposal.target_exposure == D(".00125")
    assert all(target.route != "CASH" for target in value.targets)


def test_cash_derivation_is_context_independent_and_does_not_rewrite_stock_zeroes():
    rows = stock_rows([D("-0.0"), *[D(repr(3 / 51)) for _ in range(16)]])
    expected = weights.append_derived_cash_h3_row(rows)
    with localcontext() as context:
        context.prec = 3
        assert weights.append_derived_cash_h3_row(rows) == expected
    assert struct.pack("<d", float(expected[0].weight)) == struct.pack("<d", -0.0)


@pytest.mark.parametrize("length", [0, 16, 18])
def test_cash_helper_rejects_missing_or_extra_stock_slots(length):
    rows = stock_rows()
    with pytest.raises(ValueError, match="weights_cash_h3_axis_invalid"):
        weights.append_derived_cash_h3_row((rows + (rows[0],))[:length])


def test_negative_residual_is_not_silently_clamped_or_normalized():
    rows = stock_rows([D(".6"), D(".6"), *([D(0)] * 15)])
    with pytest.raises(ValueError, match="weights_cash_h3_stock_mass_invalid"):
        weights.append_derived_cash_h3_row(rows)


def test_unknown_feature_slot_stays_unavailable_with_its_original_zero_weight():
    rows = stock_rows()
    rows = (*rows[:2], replace(rows[2], feature_known=False, route="AMZN/UNAVAILABLE"), *rows[3:])
    value = point(rows)
    assert value.metadata.rows[:17] == rows
    assert value.metadata.rows[2].feature_known is False
    assert value.metadata.rows[2].route == "AMZN/UNAVAILABLE"
    assert value.metadata.cash_weight == 1 and value.targets == ()
    assert load(weights.serialize_model_paper_weights_input(value)) == value


def test_rehashed_tuned_cash_is_rejected_even_with_existing_mass_tolerance():
    value = point()
    rows = (*value.metadata.rows[:17], replace(value.metadata.rows[17], weight=D(".5000000000001")))
    meta = replace(value.metadata, rows=rows, weight_bytes_ref=weights.model_weight_bytes_ref(rows))
    with pytest.raises(ValueError, match="weights_cash_h3_residual_invalid"):
        weights.prepare_model_paper_weights_input(
            meta,
            entry_session=value.entry_session,
            exit_session=value.exit_session,
            profile=PROFILE,
        )


@pytest.mark.parametrize(
    "first,last,entry_hour,exit_hour",
    [
        (date(2026, 10, 29), date(2026, 11, 3), 20, 21),
        (date(2026, 3, 5), date(2026, 3, 10), 21, 20),
        (date(2026, 11, 23), date(2026, 11, 27), 21, 18),
    ],
)
def test_actual_cash_h3_window_uses_official_dst_early_close_and_weekends(
    first, last, entry_hour, exit_hour
):
    value = point(first=first, last=last)
    window = weights.model_paper_cash_h3_window(value)
    assert window.entry_end.hour == entry_hour and window.exit_end.hour == exit_hour
    assert window.entry_start == value.entry_session.close_ts - timedelta(minutes=5)
    assert window.exit_start == value.exit_session.close_ts - timedelta(minutes=15)
    assert load(weights.serialize_model_paper_weights_input(value)) == value


@pytest.mark.parametrize("last", [date(2026, 11, 4), date(2026, 11, 6)])
def test_wrong_elapsed_horizon_rejected(last):
    with pytest.raises(ValueError, match="model_elapsed_horizon_invalid"):
        point(last=last)


def test_derived_zero_cash_does_not_accept_negative_zero_binary64_identity():
    value = point(stock_rows([D(1), *([D(0)] * 16)]))
    rows = (*value.metadata.rows[:17], replace(value.metadata.rows[17], weight=D("-0.0")))
    meta = replace(value.metadata, rows=rows, weight_bytes_ref=weights.model_weight_bytes_ref(rows))
    with pytest.raises(ValueError, match="weights_cash_h3_residual_invalid"):
        weights.prepare_model_paper_weights_input(
            meta,
            entry_session=value.entry_session,
            exit_session=value.exit_session,
            profile=PROFILE,
        )


def test_later_owned_exit_window_is_whole_official_session():
    value = point()
    later = _window(date(2026, 11, 6))
    window = weights.model_paper_cash_h3_window(value, operational_session=later)
    assert (window.exit_start, window.exit_end) == (later.open_ts, later.close_ts)
    with pytest.raises(ValueError, match="weights_sessions_invalid"):
        weights.model_paper_cash_h3_window(value, operational_session=value.entry_session)


@pytest.mark.parametrize(
    "profile",
    [
        weights.MODEL_PAPER_WEIGHTS_ELAPSED_H1_PROFILE,
        weights.MODEL_PAPER_WEIGHTS_ELAPSED_H3_PROFILE,
        weights.MODEL_PAPER_WEIGHTS_ELAPSED_H5_PROFILE,
        weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        weights.MODEL_PAPER_WEIGHTS_PROFILE,
    ],
)
def test_new_cash_profile_cannot_be_retagged_into_old_or_other_elapsed_profile(profile):
    document = json.loads(weights.serialize_model_paper_weights_input(point()))
    document["profile"] = profile
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
    with pytest.raises(ValueError):
        load(raw)
