"""Only two supplied-score identities are added; book defaults stay unchanged."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.research import kis_equity_rank_buffer_carry as book
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_score_replay as score

KEYS = tuple(f"opaque-{i:03}" for i in range(128))
DATES = tuple(date(2030, 1, 1) + timedelta(days=i) for i in range(113))


def snapshot(entry):
    opening = datetime.combine(DATES[entry], datetime.min.time(), UTC) + timedelta(hours=14)
    return core.EligibilitySnapshot(
        entry,
        DATES[entry - 1],
        DATES[entry],
        tuple(core.FeatureRow(k, ((0.0,) * 20,) * 2, (0.0,) * 3, 0.0) for k in KEYS),
        (),
        opening - timedelta(hours=18),
        opening,
        opening + timedelta(hours=6),
    )


@pytest.mark.parametrize("arm", ["patch20", "patch60"])
def test_new_ids_keep_exact_score_order_weights_and_book(arm):
    assert score.ARMS == ("ridge", "hgb", "gru", "equal_fixed_mean_blend")
    probabilities = {k: 0.5 for k in KEYS}
    seal = score.seal_scores(snapshot(61), (), probabilities, arm=arm)
    assert seal.arm == arm and seal.ranked_keys == KEYS
    assert seal.weights == tuple((k, Fraction(1, 10)) for k in KEYS[:10])

    def run(name):
        return score.replay_scores(
            book.CarryPlan(DATES, KEYS),
            snapshot,
            lambda _: probabilities,
            lambda *_: Decimal("100.01"),
            arm=name,
            round_trip_bps=10,
            liquidate_last_close=True,
            initial_state=book.Ledger.initial(KEYS),
        )

    reference, actual = run("tcn20"), run(arm)
    assert actual.final_state == reference.final_state and actual.public == reference.public


@pytest.mark.parametrize("arm", ["patch10", "patch120", "patch_blend"])
def test_other_patch_id_is_not_enabled(arm):
    with pytest.raises(ValueError, match="arm_invalid"):
        score.seal_scores(snapshot(61), (), dict.fromkeys(KEYS, 0.5), arm=arm)
