from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from thericher_v2.backtest.five_session import ReplaySession, replay_five_session


def fixture(count=11):
    start = datetime(2026, 10, 5, 13, 30, tzinfo=UTC)
    calendar = [
        ReplaySession(i, start + timedelta(days=i), start + timedelta(days=i, hours=6, minutes=30))
        for i in range(count)
    ]
    return dict(
        calendar=calendar,
        entries=[1],
        decisions=[calendar[0].close_ts],
        weights=np.array([[0.1, 0.0]]),
        actions=np.array([[1.0, 0.0]]),
        opens=np.array([[100.0, np.nan]]),
        closes=np.array([[[100.0, np.nan]] * 5]),
    )


@pytest.mark.parametrize("bps,numerator", [(5, 1), (10, 2), (20, 4)])
def test_flat_round_trip_has_exact_cost_once_and_fixed_quantity(bps, numerator):
    result = replay_five_session(**fixture(), per_side_fee_bps=bps)
    assert result.status == "complete"
    assert result.nav[-1] == 1 - Fraction(numerator, 1001) / 10
    assert result.exposure[5] == 0 and result.legs == 2
    assert result.summary()["growth"] < 0


def test_exit_is_fifth_close_not_following_open_or_twentieth_mark():
    data = fixture(count=6)
    data["closes"][0, :, 0] = [101.0, 102.0, 103.0, 104.0, 120.0]
    result = replay_five_session(**data, starting_cash=Fraction(1001))
    assert result.nav[-1] == Fraction("1020.78")
    assert result.fees == Fraction("0.22")
    assert result.changed_notional == 220
    assert result.summary()["growth"] == float(Fraction("19.78") / 1001)


def test_zero_holdings_ignore_all_missing_quotes_and_keep_cash():
    data = fixture()
    data["weights"][:] = 0
    data["opens"][:] = np.nan
    data["closes"][:] = np.nan
    result = replay_five_session(**data)
    assert result.status == "complete" and set(result.nav) == {Fraction(1)}
    assert result.fees == result.changed_notional == result.legs == 0


@pytest.mark.parametrize("missing", ["open", "first", "middle", "last"])
def test_only_positive_position_missing_quote_is_unknown_not_zero(missing):
    data = fixture()
    if missing == "open":
        data["opens"][0, 0] = np.nan
    else:
        data["closes"][0, {"first": 0, "middle": 2, "last": 4}[missing], 0] = np.nan
    result = replay_five_session(**data)
    assert result.status == "input_unavailable" and result.missing_basket == 0
    assert result.nav == () and result.fees is None
    assert "growth" not in result.summary()


def test_cash_gaps_and_second_basket_do_not_compound_reference_quantities():
    data = fixture(13)
    data.update(
        entries=[1, 8],
        decisions=[data["calendar"][0].close_ts, data["calendar"][7].close_ts],
        weights=np.array([[0.1], [0.1]]),
        actions=np.ones((2, 1)),
        opens=np.array([[100.0], [100.0]]),
        closes=np.full((2, 5, 1), 100.0),
    )
    result = replay_five_session(**data)
    assert result.nav[6] == result.nav[7] == 1 - Fraction(2, 10010)
    assert result.nav[-1] == 1 - Fraction(4, 10010)
    assert result.legs == 4


@pytest.mark.parametrize(
    "fault",
    [
        "reordered",
        "overlap",
        "future",
        "not_prior_close",
        "missing_session",
        "short_horizon",
        "cost_bool",
        "bad_weights",
        "nonfinite_action",
    ],
)
def test_invalid_contract_rejected(fault):
    data = fixture()
    if fault in {"reordered", "overlap"}:
        data["entries"] = [2, 1] if fault == "reordered" else [1, 4]
        data["decisions"] *= 2
    elif fault == "future":
        data["decisions"] = [data["calendar"][1].open_ts]
    elif fault == "not_prior_close":
        data["decisions"] = [data["calendar"][0].close_ts - timedelta(seconds=1)]
    elif fault == "missing_session":
        data["calendar"].pop(3)
    elif fault == "short_horizon":
        data["closes"] = data["closes"][:, :4]
    elif fault == "cost_bool":
        data["per_side_fee_bps"] = True
    elif fault == "bad_weights":
        data["weights"][0, 0] = 0.11
    else:
        data["actions"][0, 0] = np.nan
    with pytest.raises(ValueError):
        replay_five_session(**data)


def test_boolean_actions_supported_but_boolean_prices_not_supported():
    data = fixture()
    data["actions"] = data["actions"].astype(bool)
    assert replay_five_session(**data).status == "complete"
    data["opens"] = np.ones((1, 2), dtype=bool)
    with pytest.raises(ValueError, match="numeric_matrix"):
        replay_five_session(**data)


def test_inactive_bad_quote_cannot_change_an_active_asset_result():
    data = fixture()
    original = replay_five_session(**data)
    data["opens"][0, 1] = -100
    data["closes"][0, :, 1] = np.inf
    assert replay_five_session(**data) == original


def test_positive_fraction_underflow_cannot_be_reclassified_as_zero_holding():
    data = fixture()
    data["weights"][0, 0] = 1e-310
    data["actions"][0, 0] = 1e-310
    data["opens"][0, 0] = np.nan
    assert replay_five_session(**data).status == "input_unavailable"


def test_terminal_cash_matches_existing_local_paper_fee_oracle(tmp_path, monkeypatch):
    import socket

    from thericher_v2.contracts import Bar, OrderIntent, Timeframe
    from thericher_v2.execution import EmergencyStore, LocalPaperBroker
    from thericher_v2.state import EventStore

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")),
    )
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        starting_cash=Decimal("1001"),
        fee_bps=Decimal("10"),
    )
    data = fixture(6)
    data["closes"][0, :, 0] = [101.0, 102.0, 103.0, 104.0, 120.0]
    for side, at, price in (
        ("buy", data["calendar"][1].open_ts, Decimal("100")),
        ("sell", data["calendar"][5].close_ts, Decimal("120")),
    ):
        # Point bars are a synthetic cash/fee oracle, not real next-open exit evidence.
        def point(timestamp, price=price):
            return Bar(
                symbol="SYN",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=timestamp,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal("100"),
            )

        order = OrderIntent(
            client_order_id="oracle-" + side,
            symbol="SYN",
            market="US",
            side=side,
            quantity=Decimal("1"),
            limit_price=None,
            decision_id="synthetic-point-oracle",
            created_at=at,
        )
        assert broker.submit_order(order).status == "accepted"
        fill = broker.fill_next_bar(
            order.client_order_id,
            signal_bar=point(at - timedelta(minutes=1)),
            execution_bar=point(at),
        )
        assert fill.fill.source == "local_paper"
    result = replay_five_session(**data, starting_cash=Fraction(1001))
    assert result.nav[-1] == Fraction(broker.account().cash)
    assert broker.account().quantity(market="US", symbol="SYN") == 0
